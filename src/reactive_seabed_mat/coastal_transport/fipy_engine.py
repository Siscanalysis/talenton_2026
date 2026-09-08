"""The 2-D coastal engine: advection, diffusion and the seabed source.

``docs/MODEL_SPEC.md`` section 6.  Per element, over the overlying layer of
effective mixing depth ``H``::

    dc/dt + div(u c) - div(D grad c) = J_seabed / H

``J_seabed`` is the :class:`~reactive_seabed_mat.contracts.SeabedSourceField` in
kg m^-2 s^-1, so dividing by ``H`` gives the volumetric source.  **There is no
decay term**: Pb and Hg are elements and are not destroyed, only moved between
ledger compartments.

Discretisation: FiPy finite volume, ``TransientTerm`` + ``PowerLawConvectionTerm``
+ ``DiffusionTerm``, implicit in time [S06].  ``Grid2D`` cell order is row-major,
flat index ``iy * nx + ix``, identical to
:meth:`reactive_seabed_mat.contracts.GridSpec.cell_index` and to
``FieldState`` arrays reshaped with ``.reshape(-1)``.

Boundaries
----------

*Land.* A land cell holds no water.  Every face that touches a land cell gets a
zero velocity and a zero diffusivity, which is an exact internal no-flux
boundary in a finite-volume flux form.  Land cells therefore keep whatever they
started with, which the engine requires to be exactly zero.

*Open boundaries.* FiPy leaves an unconstrained exterior face closed to **both**
convection and diffusion, because its convection term is assembled from interior
faces only.  That was measured, not assumed.  The open boundary is therefore
added explicitly as an implicit sink on the boundary cells:

    outflow rate  = sum over exterior faces of max(u.n, 0) * A / V     [s^-1]
    exchange rate = sum over exterior faces of D * A / (d_AP * V)      [s^-1]

so the exported mass is ``(outflow + exchange) * c_new * V * dt`` with the same
coefficients the matrix used, evaluated at the new time level.

ASSUMPTION: the water outside the modelled domain is clean and well mixed, so
nothing advects in and the diffusive exchange is with a zero concentration.
``boundary_in_kg`` is consequently zero in every default run; it exists so the
ledger stays complete if that assumption is ever relaxed.

A **closed** domain is expressed by surrounding the water with land cells: the
water then has no exterior face at all and no open-boundary term is built.  That
keeps the frozen signature intact and exercises the same code path.

Accounting
----------

Over one step, with ``m`` the dissolved mass in the water::

    net_boundary_export = released_from_seabed - (m_after - m_before)
    boundary_out = max(net_boundary_export, 0)
    boundary_in  = max(-net_boundary_export, 0)

which is exact for a conservative scheme, so any numerical loss lands in
``boundary_out``.  It is cross-checked against the independent exterior-face
flux sum above and the difference is reported as ``closure_error_kg``.  Negative
concentrations are clipped **after** the ledger is formed and the clipped mass
is reported in ``clip_correction_kg``.  Clipping is never silent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from typing import Any, Sequence

import numpy as np

from ..contracts import (
    FieldState,
    Forcing,
    GridSpec,
    MassLedger,
    SeabedSourceField,
    TransportStep,
)

__all__ = [
    "transport_step",
    "MeshBundle",
    "mesh_bundle",
    "step_ledger",
    "accumulate_ledger",
    "ENGINE_NAME",
    "OPEN_BOUNDARY_NOTE",
]

ENGINE_NAME = "fipy_grid2d_powerlaw_implicit"

OPEN_BOUNDARY_NOTE = (
    "Open boundary: advective outflow plus a diffusive exchange with clean "
    "exterior water, both applied as implicit sinks on the boundary cells. "
    "Nothing advects in, so boundary_in_kg is zero unless the clean-exterior "
    "assumption is relaxed. A closed domain is built by ringing the water with "
    "land cells."
)

_TINY = 1.0e-15


# ---------------------------------------------------------------------------
# Mesh geometry, cached per grid signature
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MeshBundle:
    """FiPy mesh plus the geometry arrays the accounting needs.

    Cached per ``(nx, ny, dx, dy)``: the mesh is pure geometry and holds no
    solution state, so sharing it between calls cannot leak anything.
    """

    mesh: Any
    owner: np.ndarray          # (nFaces,) owning cell of every face
    neighbour: np.ndarray      # (nFaces,) neighbour cell, valid where has_neighbour
    has_neighbour: np.ndarray  # (nFaces,) bool
    exterior: np.ndarray       # (nFaces,) bool
    normals: np.ndarray        # (2, nFaces) outward from the owner
    face_length_m: np.ndarray  # (nFaces,) face length in the horizontal plane
    cell_distance_m: np.ndarray  # (nFaces,) owner-centre to neighbour-centre


@lru_cache(maxsize=16)
def _mesh_bundle_cached(nx: int, ny: int, dx_m: float, dy_m: float) -> MeshBundle:
    from fipy import Grid2D

    mesh = Grid2D(nx=nx, ny=ny, dx=dx_m, dy=dy_m)
    # FiPy 4.0.3 exposes the face areas of a UniformGrid2D only as the private
    # ``_faceAreas``; the public name exists on other mesh classes.  Try both
    # and fail loudly rather than silently using the wrong geometry, because
    # every boundary flux in this module is scaled by it.
    face_length = getattr(mesh, "_faceAreas", None)
    if face_length is None:
        face_length = getattr(mesh, "faceAreas", None)
    if face_length is None:  # pragma: no cover - guards a future FiPy rename
        raise AttributeError(
            "this FiPy mesh exposes neither '_faceAreas' nor 'faceAreas'; the "
            "boundary flux accounting cannot be scaled without the face areas"
        )
    face_cells = mesh.faceCellIDs
    owner = np.asarray(face_cells[0], dtype=int)
    has_neighbour = ~np.ma.getmaskarray(face_cells[1])
    neighbour = np.asarray(np.ma.filled(face_cells[1], 0), dtype=int)
    return MeshBundle(
        mesh=mesh,
        owner=owner,
        neighbour=neighbour,
        has_neighbour=np.asarray(has_neighbour, dtype=bool),
        exterior=np.asarray(mesh.exteriorFaces.value, dtype=bool),
        normals=np.asarray(mesh.faceNormals, dtype=float),
        face_length_m=np.asarray(face_length, dtype=float),
        cell_distance_m=np.asarray(mesh._cellDistances, dtype=float),
    )


def mesh_bundle(grid: GridSpec) -> MeshBundle:
    """The cached :class:`MeshBundle` for a :class:`GridSpec`."""
    return _mesh_bundle_cached(
        int(grid.nx), int(grid.ny), float(grid.dx_m), float(grid.dy_m)
    )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _check_field(field_state: FieldState) -> tuple[GridSpec, np.ndarray, tuple[str, ...]]:
    grid = field_state.grid
    land = np.asarray(field_state.land_mask, dtype=bool)
    if land.shape != (grid.ny, grid.nx):
        raise ValueError(
            f"land_mask has shape {land.shape}, expected {(grid.ny, grid.nx)}"
        )
    if land.all():
        raise ValueError("every cell is land: there is no water to transport in")
    names = tuple(field_state.concentration_kg_per_m3)
    if not names:
        raise ValueError("the field state carries no element")
    for name in names:
        array = np.asarray(field_state.concentration_kg_per_m3[name], dtype=float)
        if array.shape != (grid.ny, grid.nx):
            raise ValueError(
                f"concentration for {name!r} has shape {array.shape}, expected "
                f"{(grid.ny, grid.nx)}"
            )
        if not np.all(np.isfinite(array)):
            raise ValueError(f"concentration for {name!r} is not finite everywhere")
        if np.any(array < 0.0):
            raise ValueError(
                f"concentration for {name!r} is negative before the step; "
                "clipping is reported, not silently accepted on input"
            )
        if np.any(array[land] != 0.0):
            raise ValueError(
                f"concentration for {name!r} is non-zero on a land cell; a land "
                "cell holds no water, so this is a construction error rather "
                "than something to correct silently"
            )
    return grid, land, names


def _face_velocity(
    bundle: MeshBundle, cell_values: np.ndarray, touches_land: np.ndarray
) -> np.ndarray:
    """Cell-centred velocity component interpolated to faces, zero on land."""
    flat = np.asarray(cell_values, dtype=float).reshape(-1)
    face = flat[bundle.owner].astype(float)
    interior = bundle.has_neighbour
    face[interior] = 0.5 * (flat[bundle.owner[interior]] + flat[bundle.neighbour[interior]])
    face[touches_land] = 0.0
    return face


# ---------------------------------------------------------------------------
# The frozen boundary function
# ---------------------------------------------------------------------------

def transport_step(
    field_state: FieldState,
    forcing: Forcing,
    sources: SeabedSourceField,
    dt_s: float,
) -> TransportStep:
    """One implicit 2-D step for every element in ``field_state``.

    Implements :class:`~reactive_seabed_mat.contracts.TransportStepFn` exactly.
    ``sources`` is a :class:`SeabedSourceField` in kg m^-2 s^-1; the volumetric
    source is ``J_seabed / mixing_depth``.  There is no decay term anywhere.
    """
    from fipy import (
        CellVariable,
        DiffusionTerm,
        FaceVariable,
        ImplicitSourceTerm,
        PowerLawConvectionTerm,
        TransientTerm,
    )
    from fipy.solvers.scipy import LinearLUSolver

    if dt_s <= 0.0:
        raise ValueError(f"dt_s must be strictly positive, got {dt_s}")
    grid, land, names = _check_field(field_state)
    diffusivity = float(forcing.diffusivity_m2_per_s)
    if diffusivity < 0.0:
        raise ValueError("diffusivity_m2_per_s must not be negative")

    u_cell = np.asarray(forcing.u_east_m_per_s, dtype=float)
    v_cell = np.asarray(forcing.v_north_m_per_s, dtype=float)
    for label, array in (("u_east_m_per_s", u_cell), ("v_north_m_per_s", v_cell)):
        if array.shape != (grid.ny, grid.nx):
            raise ValueError(
                f"forcing {label} has shape {array.shape}, expected "
                f"{(grid.ny, grid.nx)}"
            )
        if not np.all(np.isfinite(array)):
            raise ValueError(f"forcing {label} is not finite everywhere")

    unknown = set(sources.flux_kg_per_m2_per_s) - set(names)
    if unknown:
        raise KeyError(
            f"the source field carries element(s) {sorted(unknown)} that the "
            "water field does not; an element cannot be released into a field "
            "that does not track it"
        )

    bundle = mesh_bundle(grid)
    land_flat = land.reshape(-1)
    water_flat = ~land_flat
    cell_volume = grid.cell_volume_m3
    n_cells = grid.n_cells

    touches_land = land_flat[bundle.owner].copy()
    interior = bundle.has_neighbour
    touches_land[interior] |= land_flat[bundle.neighbour[interior]]

    u_face = _face_velocity(bundle, u_cell, touches_land)
    v_face = _face_velocity(bundle, v_cell, touches_land)
    d_face = np.where(touches_land, 0.0, diffusivity)
    face_area = bundle.face_length_m * grid.mixing_depth_m
    u_dot_n = u_face * bundle.normals[0] + v_face * bundle.normals[1]

    # Discrete divergence of the masked velocity field, reported because a
    # prescribed uniform current is not divergence free once land is imposed.
    # Mass is still conserved exactly (a flux form conserves whatever the
    # divergence), but concentration piles up where the flow meets land.
    divergence = np.zeros(n_cells)
    np.add.at(divergence, bundle.owner, u_dot_n * face_area)
    np.add.at(
        divergence,
        bundle.neighbour[interior],
        -u_dot_n[interior] * face_area[interior],
    )
    divergence /= cell_volume
    max_divergence = float(np.max(np.abs(divergence[water_flat]))) if water_flat.any() else 0.0

    # Open boundary: exterior faces of water cells only.
    open_face = bundle.exterior & ~land_flat[bundle.owner]
    open_idx = np.flatnonzero(open_face)
    outflow_rate = np.zeros(n_cells)
    exchange_rate = np.zeros(n_cells)
    if open_idx.size:
        np.add.at(
            outflow_rate,
            bundle.owner[open_idx],
            np.maximum(u_dot_n[open_idx], 0.0) * face_area[open_idx] / cell_volume,
        )
        np.add.at(
            exchange_rate,
            bundle.owner[open_idx],
            d_face[open_idx]
            * face_area[open_idx]
            / (bundle.cell_distance_m[open_idx] * cell_volume),
        )
    sink_rate = outflow_rate + exchange_rate

    mesh = bundle.mesh
    u_var = FaceVariable(mesh=mesh, rank=1, value=(u_face, v_face))
    d_var = FaceVariable(mesh=mesh, value=d_face)
    sink_var = CellVariable(mesh=mesh, value=sink_rate)
    source_var = CellVariable(mesh=mesh, value=np.zeros(n_cells))
    # One equation object serves every element: the operator is identical and
    # only the explicit source and the solution variable change.  Verified
    # bit-for-bit against per-element equations in tests/coastal_transport.
    equation = (
        TransientTerm()
        == DiffusionTerm(coeff=d_var)
        - PowerLawConvectionTerm(coeff=u_var)
        - ImplicitSourceTerm(coeff=sink_var)
        + source_var
    )
    solver = LinearLUSolver()

    new_concentration: dict[str, np.ndarray] = {}
    boundary_in: dict[str, float] = {}
    boundary_out: dict[str, float] = {}
    released: dict[str, float] = {}
    closure_error: dict[str, float] = {}
    clip_correction: dict[str, float] = {}
    face_export: dict[str, float] = {}
    source_on_land: dict[str, float] = {}
    clipped_cells: dict[str, int] = {}
    min_before_clip: dict[str, float] = {}

    for name in names:
        old = np.asarray(field_state.concentration_kg_per_m3[name], dtype=float)
        flux = sources.flux_kg_per_m2_per_s.get(name)
        if flux is None:
            areal = np.zeros((grid.ny, grid.nx))
        else:
            areal = np.asarray(flux, dtype=float)
            if areal.shape != (grid.ny, grid.nx):
                raise ValueError(
                    f"source flux for {name!r} has shape {areal.shape}, expected "
                    f"{(grid.ny, grid.nx)}"
                )
            if not np.all(np.isfinite(areal)):
                raise ValueError(f"source flux for {name!r} is not finite everywhere")
            if np.any(areal < 0.0):
                raise ValueError(
                    f"source flux for {name!r} is negative; a negative seabed "
                    "flux would be a sink with no inventory behind it, and this "
                    "model never subtracts mass from a water cell"
                )
        areal_flat = areal.reshape(-1)
        source_on_land[name] = float(
            np.sum(areal_flat[land_flat]) * grid.cell_area_m2 * dt_s
        )
        volumetric = np.where(land_flat, 0.0, areal_flat) / grid.mixing_depth_m

        mass_before = float(np.sum(old.reshape(-1)[water_flat]) * cell_volume)
        released[name] = float(
            np.sum(areal_flat[water_flat]) * grid.cell_area_m2 * dt_s
        )

        variable = CellVariable(mesh=mesh, value=old.reshape(-1).copy(), hasOld=True)
        source_var.setValue(volumetric)
        variable.updateOld()
        # A land face has u = 0 and D = 0, so FiPy's face Peclet number there is
        # 0/0.  The resulting weight multiplies a zero coefficient and cannot
        # reach the matrix, so the warning is suppressed and the solved field is
        # checked for finiteness instead of trusting that.
        with np.errstate(invalid="ignore", divide="ignore"):
            equation.solve(var=variable, dt=float(dt_s), solver=solver)
        raw = np.asarray(variable.value, dtype=float).copy()
        if not np.all(np.isfinite(raw)):
            raise FloatingPointError(
                f"the transport solve produced a non-finite concentration for "
                f"{name!r}; the step is refused rather than reported"
            )

        mass_after_raw = float(np.sum(raw[water_flat]) * cell_volume)
        net_export = released[name] - (mass_after_raw - mass_before)
        boundary_out[name] = max(net_export, 0.0)
        boundary_in[name] = max(-net_export, 0.0)
        face_export[name] = float(np.sum(sink_rate * raw) * cell_volume * dt_s)
        closure_error[name] = face_export[name] - net_export

        negative = np.minimum(raw, 0.0)
        # the trailing "+ 0.0" turns a negative zero into a plain zero, so an
        # exported ledger never shows "-0.0" for a correction that did not happen
        clip_correction[name] = float(
            -np.sum(negative[water_flat]) * cell_volume
        ) + 0.0
        clipped_cells[name] = int(np.count_nonzero(negative[water_flat] < 0.0))
        min_before_clip[name] = float(raw[water_flat].min())
        clipped = np.maximum(raw, 0.0)
        clipped[land_flat] = 0.0
        new_concentration[name] = clipped.reshape(grid.ny, grid.nx)

    speed = float(np.max(np.hypot(u_cell, v_cell)))
    diagnostics: dict[str, Any] = {
        "engine": ENGINE_NAME,
        "solver": "scipy.LinearLUSolver (direct)",
        "dt_s": float(dt_s),
        "elements": list(names),
        "closure_error_kg": closure_error,
        "boundary_face_export_kg": face_export,
        "clip_correction_kg": clip_correction,
        "clipped_cells": clipped_cells,
        "min_concentration_before_clip_kg_per_m3": min_before_clip,
        "source_on_land_kg": source_on_land,
        "water_cells": int(water_flat.sum()),
        "land_cells": int(land_flat.sum()),
        "open_boundary_faces": int(open_idx.size),
        "max_velocity_divergence_per_s": max_divergence,
        "advective_courant": float(
            speed * dt_s / min(grid.dx_m, grid.dy_m)
        ),
        "diffusion_number": float(
            diffusivity * dt_s / min(grid.dx_m, grid.dy_m) ** 2
        ),
        "decay_term": "none: Pb and Hg are elements and are never destroyed",
        "notes": OPEN_BOUNDARY_NOTE,
    }
    if max_divergence > _TINY:
        diagnostics["notes"] += (
            " The masked velocity field is not divergence free "
            f"(max |div u| = {max_divergence:.3e} s^-1), so concentration can "
            "pile up where the prescribed flow meets land. Mass is still "
            "conserved exactly, because the scheme is in flux form."
        )
    if any(value > 0.0 for value in clip_correction.values()):
        diagnostics["notes"] += (
            " NUMERICAL CORRECTION: negative concentrations were clipped to "
            "zero; the added mass is in clip_correction_kg and is reported, "
            "never hidden."
        )
    if any(value > 0.0 for value in source_on_land.values()):
        diagnostics["notes"] += (
            " A source flux was supplied on land cells and was not released "
            "into the water; the amount is in source_on_land_kg."
        )

    new_field = FieldState(
        grid=grid,
        time_utc=field_state.time_utc + timedelta(seconds=float(dt_s)),
        concentration_kg_per_m3=new_concentration,
        land_mask=land,
        origin=field_state.origin,
    )
    return TransportStep(
        new_field=new_field,
        boundary_in_kg=boundary_in,
        boundary_out_kg=boundary_out,
        released_from_seabed_kg=released,
        diagnostics=diagnostics,
    )


# ---------------------------------------------------------------------------
# Ledgers
# ---------------------------------------------------------------------------

def step_ledger(
    element: str,
    before: FieldState,
    step: TransportStep,
) -> MassLedger:
    """The single-step water-column ledger for one element.

    ``numerical_correction_kg`` is the **negative** of the clipped mass: the
    clip adds mass to ``in_water_kg``, so the correction on the accounted side
    must remove it again for the ledger identity in ``docs/MODEL_SPEC.md``
    section 7 to hold.
    """
    clip = float(step.diagnostics.get("clip_correction_kg", {}).get(element, 0.0))
    return MassLedger(
        element=element,
        initial_water_kg=before.water_mass_kg(element),
        released_from_sediment_kg=float(step.released_from_seabed_kg.get(element, 0.0)),
        boundary_in_kg=float(step.boundary_in_kg.get(element, 0.0)),
        in_water_kg=step.new_field.water_mass_kg(element),
        boundary_out_kg=float(step.boundary_out_kg.get(element, 0.0)),
        numerical_correction_kg=-clip + 0.0,
    )


def accumulate_ledger(
    element: str,
    initial: FieldState,
    steps: Sequence[TransportStep],
    *,
    retained_in_mat_kg: float = 0.0,
    retained_in_retrieved_media_kg: float = 0.0,
) -> MassLedger:
    """Water-column ledger for a whole plume window.

    ``retained_in_mat_kg`` and ``retained_in_retrieved_media_kg`` belong to the
    reactive-layer branch and are passed straight through, so the coastal window
    never invents a mat inventory of its own.
    """
    if not steps:
        return MassLedger(
            element=element,
            initial_water_kg=initial.water_mass_kg(element),
            in_water_kg=initial.water_mass_kg(element),
            retained_in_mat_kg=float(retained_in_mat_kg),
            retained_in_retrieved_media_kg=float(retained_in_retrieved_media_kg),
        )
    released = sum(float(s.released_from_seabed_kg.get(element, 0.0)) for s in steps)
    into = sum(float(s.boundary_in_kg.get(element, 0.0)) for s in steps)
    out = sum(float(s.boundary_out_kg.get(element, 0.0)) for s in steps)
    clip = sum(
        float(s.diagnostics.get("clip_correction_kg", {}).get(element, 0.0))
        for s in steps
    )
    return MassLedger(
        element=element,
        initial_water_kg=initial.water_mass_kg(element),
        released_from_sediment_kg=released,
        boundary_in_kg=into,
        in_water_kg=steps[-1].new_field.water_mass_kg(element),
        retained_in_mat_kg=float(retained_in_mat_kg),
        retained_in_retrieved_media_kg=float(retained_in_retrieved_media_kg),
        boundary_out_kg=out,
        numerical_correction_kg=-clip + 0.0,
    )
