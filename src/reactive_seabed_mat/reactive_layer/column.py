"""The 1-D reactive layer: one fully implicit coupled transport-sorption step.

This is ``docs/MODEL_SPEC.md`` section 3, and it is a direct transcription of
``docs/reactive_layer_numerics_probe.py``, which was measured before any
repository code was written.  Governing equations, per element, through the
layer thickness ``z`` in ``[0, L]``::

    theta dC/dt = -dJ/dz - rho_b dq/dt ,   J = v C - theta D_eff dC/dz
    dq/dt       = k_eff (q_eq(C) - q) ,    q_eq(C) = min(Kd C, q_max_eff)

Why it is written this way, and not the obvious way
---------------------------------------------------

An operator split (transport substep, then sorption substep) **must not** be
used here.  It was tried.  With ``rho_b Kd / theta ~ 6000`` the sorption
substep drains the porewater every step; refining the time step made the answer
*worse*, moving breakthrough from 4.21 years at ``dt = 6 h`` to 1.03 years at
``dt = 0.5 h``, while conserving mass to 1e-14 throughout.  **A conserving
scheme is not automatically a correct scheme**, which is why
``tests/reactive_layer/test_refinement.py`` exists at all.

So ``q^{n+1}`` is eliminated analytically and the sorption exchange becomes a
diagonal term and a source in the same tridiagonal system, solved once with
``scipy.linalg.solve_banded``::

    q^{n+1} = (q^n + dt k q_eq^{n+1}) / (1 + dt k)

    unsaturated (q_eq = Kd C):   rho_b (q^{n+1} - q^n)/dt = A C^{n+1} - B
        A = rho_b k Kd / (1 + dt k)        B = rho_b k q^n / (1 + dt k)
    saturated   (q_eq = q_max):  rho_b (q^{n+1} - q^n)/dt = -Dsat
        Dsat = rho_b k (q_max - q^n) / (1 + dt k)
    capacity locked (q^n >= q_max_eff):    no exchange at all

The third branch is MODEL_SPEC section 4, mode 2: "if ``q_max_eff`` falls below
the current load, further uptake stops and ``q`` is unchanged".  It also makes
a fully loaded cell inert rather than letting the capped isotherm pull metal
back out of it.  That is the conservative reading, and it is stated here rather
than buried: a cell at capacity neither takes up nor releases.

The branch is chosen per cell by Picard iteration on ``Kd C >= q_max_eff``, and
``q^{n+1}`` is then evaluated with **the same branch mask the matrix used**, so
the discrete balance closes exactly rather than approximately.

Boundary treatment (also from the probe, unchanged)
---------------------------------------------------

* ``z = 0``, sediment face: prescribed porewater ``C_sed`` half a cell below
  the first node, with advective inflow ``v C_sed``.
* ``z = L``, water face: advection out plus the benthic boundary layer in
  series, ``g_top = 1 / (dz / (2 theta D_eff) + 1 / k_film)``.

Boundary fluxes are evaluated at the new time level with the same discrete
coefficients the matrix uses.  Sorption moves mass inside a cell and crosses no
boundary, so summing the rows telescopes exactly to::

    d/dt integral_0^L (theta C + rho_b q) dz = J_in - J_out

Capacity clipping returns the excess to the porewater rather than deleting it,
and the corrected mass is reported.  Clipping is never silent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.linalg import solve_banded

from ..contracts import MaterialParameters, MatTileGeometry, ProvenanceLabel
from .material import fouling_factors

__all__ = [
    "ColumnParameters",
    "ColumnStep",
    "DEFAULT_PICARD_ITERATIONS",
    "build_column_parameters",
    "top_conductance",
    "solve_column_step",
    "stored_kg_per_m2",
    "steady_state_flux_kg_per_m2_per_s",
]

#: Picard sweeps used to settle the saturated / unsaturated branch mask.  Two
#: is what the probe used and what the refinement study was measured with; the
#: loop exits early when the mask stops moving, so this is an upper bound.
DEFAULT_PICARD_ITERATIONS = 6


@dataclass(frozen=True, slots=True)
class ColumnParameters:
    """Everything one element's 1-D column needs, already in SI.

    ``kd_m3_per_kg`` and ``q_max_kg_per_kg`` are the **column** values: the
    material values multiplied by ``allocation_fraction`` (see the allocation
    convention in ``material.py``), so ``q`` is per kilogram of total medium and
    ``rho_b L q_max`` is exactly ``MatTileState.capacity_kg_per_m2``.

    ``d_eff_m2_per_s``, ``k_rate_per_s`` and ``q_max_kg_per_kg`` are already
    fouled: :func:`build_column_parameters` applies the fouling factors, so the
    solver itself has no opinion about degradation.
    """

    thickness_m: float
    n_nodes: int
    porosity: float
    bulk_density_kg_per_m3: float
    d_eff_m2_per_s: float
    seepage_velocity_m_per_s: float
    film_transfer_m_per_s: float
    kd_m3_per_kg: float
    q_max_kg_per_kg: float
    k_rate_per_s: float

    def __post_init__(self) -> None:
        if self.n_nodes < 1:
            raise ValueError(f"n_nodes must be at least 1, got {self.n_nodes!r}")
        for name in (
            "thickness_m",
            "porosity",
            "bulk_density_kg_per_m3",
            "d_eff_m2_per_s",
            "seepage_velocity_m_per_s",
            "film_transfer_m_per_s",
            "kd_m3_per_kg",
            "q_max_kg_per_kg",
            "k_rate_per_s",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative, got {value!r}")
        if self.thickness_m <= 0.0:
            raise ValueError("thickness_m must be strictly positive")
        if self.porosity <= 0.0 or self.porosity > 1.0:
            raise ValueError(f"porosity must lie in (0, 1], got {self.porosity!r}")

    @property
    def dz_m(self) -> float:
        return self.thickness_m / self.n_nodes

    @property
    def capacity_kg_per_m2(self) -> float:
        """``rho_b L q_max_eff``: what this column can hold, per unit area."""
        return (
            self.bulk_density_kg_per_m3 * self.thickness_m * self.q_max_kg_per_kg
        )

    @property
    def peclet(self) -> float:
        """``v L / (theta D_eff)``: advection against diffusion in the layer."""
        denominator = self.porosity * self.d_eff_m2_per_s
        if denominator <= 0.0:
            return math.inf
        return self.seepage_velocity_m_per_s * self.thickness_m / denominator


@dataclass(frozen=True, slots=True)
class ColumnStep:
    """The result of one implicit column step, per unit seabed area."""

    porewater_kg_per_m3: np.ndarray
    sorbed_kg_per_kg: np.ndarray
    flux_in_kg_per_m2_per_s: float
    flux_out_kg_per_m2_per_s: float
    stored_before_kg_per_m2: float
    stored_after_kg_per_m2: float
    clip_correction_kg_per_m2: float
    negative_clip_kg_per_m2: float
    picard_iterations: int
    picard_converged: bool
    diagnostics: dict[str, Any]

    @property
    def stored_delta_kg_per_m2(self) -> float:
        return self.stored_after_kg_per_m2 - self.stored_before_kg_per_m2

    def conservation_residual_kg_per_m2(self, dt_s: float) -> float:
        """``(stored_after - stored_before - clipped) - (J_in - J_out) dt``.

        Zero to round-off for this scheme.  ``negative_clip_kg_per_m2`` is a
        *recorded* numerical correction (mass added when clipping a negative
        porewater concentration to zero) and is subtracted here so the residual
        measures the scheme, not the correction.  Capacity clipping is not
        subtracted because it moves mass between the sorbed and dissolved pools
        inside a cell and adds none.
        """
        return (
            self.stored_delta_kg_per_m2
            - self.negative_clip_kg_per_m2
            - (self.flux_in_kg_per_m2_per_s - self.flux_out_kg_per_m2_per_s)
            * float(dt_s)
        )


def build_column_parameters(
    geometry: MatTileGeometry,
    params: MaterialParameters,
    *,
    n_nodes: int,
    seepage_velocity_m_per_s: float,
    film_transfer_m_per_s: float,
    fouling_index: float = 0.0,
) -> ColumnParameters:
    """Column parameters for one element, with fouling already applied.

    Fouling enters here and nowhere else in the solver:
    ``k_eff = k (1 - gamma_k f)``, ``q_max_eff = q_max (1 - gamma_c f)`` and
    ``D_eff_eff = D_eff (1 - gamma_D f)`` (MODEL_SPEC section 4, mode 2).  The
    allocation fraction scales both ``Kd`` and ``q_max``, so the isotherm knee
    ``q_max / Kd`` does not depend on how the medium was split between the
    elements.
    """
    factors = fouling_factors(params, fouling_index)
    allocation = float(params.allocation_fraction)
    return ColumnParameters(
        thickness_m=float(geometry.thickness_m),
        n_nodes=int(n_nodes),
        porosity=float(geometry.porosity),
        bulk_density_kg_per_m3=float(geometry.bulk_density_kg_per_m3),
        d_eff_m2_per_s=float(params.d_eff_m2_per_s) * factors.diffusivity_factor,
        seepage_velocity_m_per_s=float(seepage_velocity_m_per_s),
        film_transfer_m_per_s=float(film_transfer_m_per_s),
        kd_m3_per_kg=float(params.kd_m3_per_kg) * allocation,
        q_max_kg_per_kg=float(params.q_max_kg_per_kg)
        * factors.capacity_factor
        * allocation,
        k_rate_per_s=float(params.k_rate_per_s) * factors.kinetics_factor,
    )


def top_conductance(params: ColumnParameters) -> float:
    """``g_top = 1 / (dz / (2 theta D_eff) + 1 / k_film)`` [m s^-1].

    The half cell of layer porewater and the benthic boundary layer in series.
    Burial adds a third resistance in series; that lives in ``degradation.py``
    because it is a degradation mode, not a property of a clean layer.
    """
    diffusive_resistance = (
        math.inf
        if params.d_eff_m2_per_s <= 0.0
        else params.dz_m / (2.0 * params.porosity * params.d_eff_m2_per_s)
    )
    film_resistance = (
        math.inf
        if params.film_transfer_m_per_s <= 0.0
        else 1.0 / params.film_transfer_m_per_s
    )
    total = diffusive_resistance + film_resistance
    if not math.isfinite(total) or total <= 0.0:
        return 0.0
    return 1.0 / total


def stored_kg_per_m2(
    porewater_kg_per_m3: np.ndarray,
    sorbed_kg_per_kg: np.ndarray,
    params: ColumnParameters,
) -> float:
    """``integral_0^L (theta C + rho_b q) dz`` [kg m^-2]."""
    porewater = np.asarray(porewater_kg_per_m3, dtype=float)
    sorbed = np.asarray(sorbed_kg_per_kg, dtype=float)
    return float(
        np.sum(
            params.porosity * porewater + params.bulk_density_kg_per_m3 * sorbed
        )
        * params.dz_m
    )


def solve_column_step(
    porewater_kg_per_m3: np.ndarray,
    sorbed_kg_per_kg: np.ndarray,
    params: ColumnParameters,
    dt_s: float,
    sediment_porewater_kg_per_m3: float,
    bottom_water_kg_per_m3: float,
    *,
    top_conductance_m_per_s: float | None = None,
    picard_iterations: int = DEFAULT_PICARD_ITERATIONS,
) -> ColumnStep:
    """One fully implicit coupled step of the 1-D reactive layer.

    ``top_conductance_m_per_s`` overrides ``g_top``; the caller passes the
    burial-reduced conductance when the tile is buried.  Everything else is
    exactly the scheme of the numerics probe.

    Returns a :class:`ColumnStep` whose fluxes are evaluated at the new time
    level with the matrix's own coefficients, so
    ``stored_after - stored_before == (J_in - J_out) dt`` to round-off.
    """
    dt = float(dt_s)
    if dt < 0.0:
        raise ValueError(f"dt_s must be non-negative, got {dt_s!r}")
    if picard_iterations < 1:
        raise ValueError(
            f"picard_iterations must be at least 1, got {picard_iterations!r}"
        )

    nz = params.n_nodes
    concentration = np.asarray(porewater_kg_per_m3, dtype=float).copy()
    sorbed = np.asarray(sorbed_kg_per_kg, dtype=float).copy()
    if concentration.shape != (nz,) or sorbed.shape != (nz,):
        raise ValueError(
            f"profiles must both have shape ({nz},), got "
            f"{concentration.shape} and {sorbed.shape}"
        )

    stored_before = stored_kg_per_m2(concentration, sorbed, params)
    if dt == 0.0:
        return ColumnStep(
            porewater_kg_per_m3=concentration,
            sorbed_kg_per_kg=sorbed,
            flux_in_kg_per_m2_per_s=0.0,
            flux_out_kg_per_m2_per_s=0.0,
            stored_before_kg_per_m2=stored_before,
            stored_after_kg_per_m2=stored_before,
            clip_correction_kg_per_m2=0.0,
            negative_clip_kg_per_m2=0.0,
            picard_iterations=0,
            picard_converged=True,
            diagnostics={"note": "dt_s == 0, the state is returned unchanged"},
        )

    theta = params.porosity
    rho_b = params.bulk_density_kg_per_m3
    dz = params.dz_m
    d_eff = params.d_eff_m2_per_s
    velocity = params.seepage_velocity_m_per_s
    kd = params.kd_m3_per_kg
    q_max = params.q_max_kg_per_kg
    k_rate = params.k_rate_per_s

    c_sed = float(sediment_porewater_kg_per_m3)
    c_water = float(bottom_water_kg_per_m3)
    g_top = (
        top_conductance(params)
        if top_conductance_m_per_s is None
        else max(0.0, float(top_conductance_m_per_s))
    )

    kd_diff = theta * d_eff / dz**2
    advect = velocity / dz
    relax = 1.0 + dt * k_rate

    #: Capacity-locked cells (MODEL_SPEC section 4, mode 2): the current load is
    #: at or above the accessible capacity, so uptake stops and q is held.
    #: Fouling must never delete sorbed metal, and a full cell must not be
    #: emptied by the capped isotherm either.
    locked = sorbed >= q_max

    guess = concentration.copy()
    saturated = np.zeros(nz, dtype=bool)
    converged = False
    used_iterations = 0
    solution = concentration

    for iteration in range(int(picard_iterations)):
        used_iterations = iteration + 1
        saturated = (~locked) & ((kd * guess) >= q_max)
        unsaturated = (~locked) & (~saturated)

        exchange_a = np.where(unsaturated, rho_b * k_rate * kd / relax, 0.0)
        exchange_b = np.where(
            unsaturated,
            rho_b * k_rate * sorbed / relax,
            np.where(saturated, -rho_b * k_rate * (q_max - sorbed) / relax, 0.0),
        )

        ab = np.zeros((3, nz))
        ab[0, 1:] = -kd_diff                    # upper: C_{i+1}
        ab[2, :-1] = -(kd_diff + advect)        # lower: C_{i-1}
        ab[1, :] = theta / dt + exchange_a + 2.0 * kd_diff + advect
        rhs = theta / dt * concentration + exchange_b

        # Sediment face: Dirichlet half a cell below node 0, advective inflow.
        ab[1, 0] += kd_diff
        rhs[0] += (2.0 * kd_diff + advect) * c_sed
        # Water face: advection out plus the benthic film (and any burial) in
        # series, replacing the interior diffusive face of the last cell.
        ab[1, -1] += g_top / dz - kd_diff
        rhs[-1] += g_top / dz * c_water

        solution = solve_banded((1, 1), ab, rhs)

        next_saturated = (~locked) & ((kd * solution) >= q_max)
        if np.array_equal(next_saturated, saturated):
            converged = True
            break
        guess = solution

    # q^{n+1} uses the SAME branch mask the matrix used, so the discrete balance
    # closes exactly even when the Picard sweep has not settled.
    q_eq = np.where(saturated, q_max, kd * solution)
    new_sorbed = np.where(locked, sorbed, (sorbed + dt * k_rate * q_eq) / relax)

    new_concentration = solution
    clip_correction = 0.0
    # Capacity-locked cells are exempt: they were never updated, so they cannot
    # have overshot, and clipping them would push already-sorbed metal back into
    # the porewater and out of the layer.  That is exactly the "fouling deletes
    # sorbed metal" failure MODEL_SPEC section 4 forbids.
    over = (~locked) & (new_sorbed > q_max)
    if np.any(over):
        excess = new_sorbed[over] - q_max
        new_sorbed = new_sorbed.copy()
        new_concentration = new_concentration.copy()
        new_sorbed[over] = q_max
        # Mass returned to the porewater, not destroyed.
        new_concentration[over] += rho_b * excess / theta
        clip_correction = float(np.sum(rho_b * excess) * dz)

    negative = new_concentration < 0.0
    negative_clip_kg_per_m2 = 0.0
    if np.any(negative):
        negative_clip_kg_per_m2 = float(
            -np.sum(theta * new_concentration[negative]) * dz
        )
        new_concentration = new_concentration.copy()
        new_concentration[negative] = 0.0

    flux_in = velocity * c_sed + 2.0 * theta * d_eff * (c_sed - solution[0]) / dz
    flux_out = velocity * solution[-1] + g_top * (solution[-1] - c_water)

    stored_after = stored_kg_per_m2(new_concentration, new_sorbed, params)

    diagnostics: dict[str, Any] = {
        "model_ref": "docs/MODEL_SPEC.md section 3, fully implicit coupled solve",
        "scheme": "scipy_banded_implicit_with_analytic_sorption_elimination",
        "operator_split": False,
        "dz_m": dz,
        "top_conductance_m_per_s": g_top,
        "top_conductance_overridden": top_conductance_m_per_s is not None,
        "peclet": params.peclet,
        "capacity_kg_per_m2": params.capacity_kg_per_m2,
        "locked_cells": int(np.count_nonzero(locked)),
        "saturated_cells": int(np.count_nonzero(saturated)),
        "desorbing_cells": int(np.count_nonzero(new_sorbed < sorbed - 1e-30)),
        "picard_iterations": used_iterations,
        "picard_converged": bool(converged),
        "clip_correction_kg_per_m2": clip_correction,
        "negative_concentration_clip_kg_per_m2": negative_clip_kg_per_m2,
        "provenance": ProvenanceLabel.SYNTHETIC_DEMO.value,
    }
    if negative_clip_kg_per_m2 > 0.0:
        diagnostics["corrections"] = (
            {
                "kind": "negative_porewater_clipped_to_zero",
                "mass_kg_per_m2": negative_clip_kg_per_m2,
            },
        )
    else:
        diagnostics["corrections"] = ()

    return ColumnStep(
        porewater_kg_per_m3=new_concentration,
        sorbed_kg_per_kg=new_sorbed,
        flux_in_kg_per_m2_per_s=float(flux_in),
        flux_out_kg_per_m2_per_s=float(flux_out),
        stored_before_kg_per_m2=stored_before,
        stored_after_kg_per_m2=stored_after,
        clip_correction_kg_per_m2=clip_correction,
        negative_clip_kg_per_m2=negative_clip_kg_per_m2,
        picard_iterations=used_iterations,
        picard_converged=bool(converged),
        diagnostics=diagnostics,
    )


def steady_state_flux_kg_per_m2_per_s(
    params: ColumnParameters,
    sediment_porewater_kg_per_m3: float,
    bottom_water_kg_per_m3: float = 0.0,
    *,
    top_conductance_m_per_s: float | None = None,
) -> float:
    """Analytic **continuum** steady-state flux through a non-sorbing layer.

    Solving ``v C - theta D C' = J`` on ``0 <= z <= L`` with ``C(0) = C_sed``
    and ``J = (v + k_film)(C_L - C_water)`` gives::

        a = v / (theta D) ,  E = exp(a L)
        J = E (C_sed - C_water) / [ 1/(v + k_film) + (E - 1)/v ]

    This is the barrier limit a mat with no remaining chemical capacity tends
    to, and it is the honest floor of the attenuation claim: the chemical
    contribution of the sorbent is the *difference* between the fresh value and
    this one, not the whole of it.

    It is a **continuum** expression, so the discrete solver agrees with it only
    to the order of ``dz`` (the discrete ``g_top`` folds half a cell of layer
    porewater into the top conductance).  It is a sanity oracle and an
    interpretation aid, never a substitute for the solver.  Pass
    ``top_conductance_m_per_s`` to substitute a burial-reduced conductance for
    ``k_film``.
    """
    velocity = params.seepage_velocity_m_per_s
    conductance = (
        params.film_transfer_m_per_s
        if top_conductance_m_per_s is None
        else float(top_conductance_m_per_s)
    )
    driving = float(sediment_porewater_kg_per_m3) - float(bottom_water_kg_per_m3)
    if driving == 0.0:
        return 0.0
    layer_resistance = (
        math.inf
        if params.d_eff_m2_per_s <= 0.0
        else params.thickness_m / (params.porosity * params.d_eff_m2_per_s)
    )
    top_resistance = math.inf if conductance <= 0.0 else 1.0 / conductance
    if velocity <= 0.0:
        total = layer_resistance + top_resistance
        return 0.0 if not math.isfinite(total) or total <= 0.0 else driving / total
    if not math.isfinite(layer_resistance):
        return 0.0
    exponent = velocity * layer_resistance
    growth = math.exp(exponent)
    denominator = 1.0 / (velocity + conductance) + (growth - 1.0) / velocity
    return growth * driving / denominator
