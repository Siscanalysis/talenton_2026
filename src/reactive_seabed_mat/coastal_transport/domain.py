"""Domain, land mask, initial field, prescribed forcing and the seabed hotspot.

This module turns the coordinator-owned configuration objects
(:mod:`reactive_seabed_mat.config`) into the frozen contract objects
(:mod:`reactive_seabed_mat.contracts`) that
:mod:`reactive_seabed_mat.coastal_transport.fipy_engine` and
:mod:`reactive_seabed_mat.coastal_transport.seabed_source` consume.  It contains
no solver: it only prepares inputs.

Conventions, all SI (see ``src/reactive_seabed_mat/units.py``):

* arrays are ``(ny, nx)``; ``arr.reshape(-1)`` is the FiPy ``Grid2D`` cell
  order, identical to :meth:`reactive_seabed_mat.contracts.GridSpec.cell_index`
  (flat index ``iy * nx + ix``);
* ``land_mask[iy, ix] is True`` marks a no-flux cell that holds no water;
* velocities are depth-averaged, in m s^-1, positive east / positive north;
* an areal flux is on the flux ladder, kg m^-2 s^-1.

Nothing here is a hydrodynamic solution.  The current field is *prescribed*:
a uniform mean flow, optionally modulated by a single sinusoidal tidal
constituent.  It is a synthetic demonstration field, labelled as such.

The hotspot is an **authorised contaminated seabed area**, an abstract
contaminant source.  Nothing in this module locates, simulates or recommends
the handling of any object on the seabed.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping, Sequence

import numpy as np

from ..config import DomainConfig, ForcingConfig, HotspotConfig, RunConfig
from ..contracts import (
    Element,
    FieldState,
    Forcing,
    GridSpec,
    ProvenanceLabel,
    SeabedHotspot,
    StateOrigin,
)

__all__ = [
    "build_grid",
    "build_land_mask",
    "initial_field_state",
    "forcing_at",
    "forcing_timeline",
    "forcing_signature",
    "mean_velocity_at",
    "tidal_factor",
    "assert_tide_resolving",
    "hotspot_entry_at",
    "hotspot_cell_mask",
    "bare_flux",
    "build_hotspot",
    "hotspot_area_m2",
    "DomainBundle",
    "build_domain",
    "TidalForcingRefused",
    "SYNTHETIC_FORCING_NOTE",
    "HOTSPOT_DISCRETISATION_NOTE",
    "NON_TIDE_RESOLVING_AVERAGING",
]


# --- assumptions -----------------------------------------------------------
# ASSUMPTION: the prescribed current field is uniform in space.  A real coastal
# flow is not.  This is a synthetic demonstration field, not a calibrated
# hydrodynamic solution, and it is labelled ProvenanceLabel.SYNTHETIC_DEMO.
SYNTHETIC_FORCING_NOTE = (
    "Prescribed uniform depth-averaged current, optionally modulated by one "
    "sinusoidal tidal constituent. Synthetic demonstration field: it is not a "
    "hydrodynamic solution, it is not calibrated to any site, and its spatial "
    "resolution carries no information finer than the prescription itself."
)

# ASSUMPTION: a cell counts as land, or as part of the hotspot, when its centre
# falls inside the configured rectangle.  Partial coverage of a cell by land is
# not represented.  Partial coverage of a cell by a *mat tile* is represented,
# because coverage is the quantity the mat is judged on
# (see coastal_transport.seabed_source).
HOTSPOT_DISCRETISATION_NOTE = (
    "The hotspot is discretised by cell-centre containment, so the gridded "
    "hotspot area can differ from the configured rectangle area when the "
    "rectangle does not align with cell boundaries. The gridded area is the "
    "one every flux and mass number below is computed on."
)

#: Temporal-averaging labels that cannot resolve a tide.  Used to refuse a
#: de-tided or daily-mean product for a tide-resolving scenario [S10].
NON_TIDE_RESOLVING_AVERAGING: frozenset[str] = frozenset(
    {
        "daily_mean",
        "daily",
        "de_tided",
        "detided",
        "monthly_mean",
        "monthly",
        "climatology",
        "residual",
    }
)


class TidalForcingRefused(ValueError):
    """Raised when a tide-resolving scenario is asked for a non-tidal field."""


# ---------------------------------------------------------------------------
# Grid and land
# ---------------------------------------------------------------------------

def build_grid(domain: DomainConfig) -> GridSpec:
    """Build the frozen :class:`GridSpec` from the run configuration."""
    if domain.nx < 1 or domain.ny < 1:
        raise ValueError(f"grid must have at least one cell, got {domain.nx}x{domain.ny}")
    if domain.dx_m <= 0.0 or domain.dy_m <= 0.0:
        raise ValueError("dx_m and dy_m must be strictly positive")
    if domain.mixing_depth_m <= 0.0:
        raise ValueError(
            "mixing_depth_m must be strictly positive: it is the effective "
            "depth over which the 2D model averages, not a bathymetric depth"
        )
    return GridSpec(
        nx=int(domain.nx),
        ny=int(domain.ny),
        dx_m=float(domain.dx_m),
        dy_m=float(domain.dy_m),
        mixing_depth_m=float(domain.mixing_depth_m),
        crs=domain.crs,
    )


def build_land_mask(domain: DomainConfig, grid: GridSpec | None = None) -> np.ndarray:
    """``(ny, nx)`` boolean land mask from the configured land rectangles.

    A land cell is no-flux and holds no water.  The rule is deliberately blunt
    (cell-centre containment); partial land coverage of a cell is not modelled.
    """
    grid = build_grid(domain) if grid is None else grid
    mask = np.zeros((grid.ny, grid.nx), dtype=bool)
    xx, yy = _cell_centre_grids(grid)
    for rect in domain.land_rectangles:
        x0, y0, x1, y1 = (float(v) for v in rect)
        lo_x, hi_x = min(x0, x1), max(x0, x1)
        lo_y, hi_y = min(y0, y1), max(y0, y1)
        mask |= (xx >= lo_x) & (xx <= hi_x) & (yy >= lo_y) & (yy <= hi_y)
    if mask.all():
        raise ValueError("the land rectangles cover the whole domain: no water left")
    return mask


def _cell_centre_grids(grid: GridSpec) -> tuple[np.ndarray, np.ndarray]:
    """``(xx, yy)`` cell-centre coordinate arrays, both ``(ny, nx)`` in metres."""
    ix = np.arange(grid.nx)
    iy = np.arange(grid.ny)
    xc = grid.origin_x_m + (ix + 0.5) * grid.dx_m
    yc = grid.origin_y_m + (iy + 0.5) * grid.dy_m
    return np.meshgrid(xc, yc)


def initial_field_state(
    config: RunConfig | None = None,
    *,
    grid: GridSpec | None = None,
    land_mask: np.ndarray | None = None,
    elements: Sequence[str] | None = None,
    time_utc: datetime | None = None,
    initial_concentration: Mapping[str, np.ndarray | float] | None = None,
    origin: StateOrigin = StateOrigin.TRUE_SIMULATED,
) -> FieldState:
    """Build the initial :class:`FieldState`, zero everywhere by default.

    ``initial_concentration`` may give a scalar or an ``(ny, nx)`` array per
    element; values on land cells are forced to zero because a land cell holds
    no water.
    """
    if grid is None:
        if config is None:
            raise ValueError("initial_field_state needs either a RunConfig or a GridSpec")
        grid = build_grid(config.domain)
    if land_mask is None:
        land_mask = (
            build_land_mask(config.domain, grid)
            if config is not None
            else np.zeros((grid.ny, grid.nx), dtype=bool)
        )
    land_mask = np.asarray(land_mask, dtype=bool)
    if land_mask.shape != (grid.ny, grid.nx):
        raise ValueError(
            f"land_mask has shape {land_mask.shape}, expected {(grid.ny, grid.nx)}"
        )
    if elements is None:
        elements = tuple(config.elements) if config is not None else (Element.PB.value,)
    fields: dict[str, np.ndarray] = {}
    for name in elements:
        if initial_concentration is not None and name in initial_concentration:
            raw = np.asarray(initial_concentration[name], dtype=float)
            values = np.broadcast_to(raw, (grid.ny, grid.nx)).astype(float).copy()
        else:
            values = np.zeros((grid.ny, grid.nx), dtype=float)
        if np.any(values < 0.0):
            raise ValueError(f"initial concentration for {name!r} has negative values")
        values[land_mask] = 0.0
        fields[name] = values
    if time_utc is None:
        time_utc = (
            config.start_datetime
            if config is not None
            else datetime.now(timezone.utc)
        )
    return FieldState(
        grid=grid,
        time_utc=time_utc,
        concentration_kg_per_m3=fields,
        land_mask=land_mask,
        origin=origin,
    )


# ---------------------------------------------------------------------------
# Forcing
# ---------------------------------------------------------------------------

def _along_channel_unit(cfg: ForcingConfig) -> tuple[float, float]:
    """Unit vector the tidal constituent oscillates along.

    It follows the configured mean flow; when the mean flow is zero it defaults
    to east, so that ``u_mean = 0`` with a tidal amplitude still gives a genuine
    east-west reversal.  ASSUMPTION: one rectilinear constituent, no ellipse.
    """
    ux, uy = float(cfg.u_mean_m_per_s), float(cfg.v_mean_m_per_s)
    norm = math.hypot(ux, uy)
    if norm <= 0.0:
        return (1.0, 0.0)
    return (ux / norm, uy / norm)


def tidal_factor(cfg: ForcingConfig, elapsed_s: float) -> float:
    """Signed tidal modulation ``sin(2 pi t / T + phase)`` (dimensionless)."""
    if cfg.tidal_period_s <= 0.0:
        raise ValueError("tidal_period_s must be strictly positive for kind='tidal'")
    return math.sin(2.0 * math.pi * float(elapsed_s) / float(cfg.tidal_period_s)
                    + float(cfg.tidal_phase_rad))


def mean_velocity_at(cfg: ForcingConfig, elapsed_s: float) -> tuple[float, float]:
    """Spatially uniform ``(u_east, v_north)`` in m s^-1 at ``elapsed_s``."""
    kind = str(cfg.kind).lower()
    if kind == "steady":
        return (float(cfg.u_mean_m_per_s), float(cfg.v_mean_m_per_s))
    if kind == "tidal":
        ex, ey = _along_channel_unit(cfg)
        amp = float(cfg.tidal_amplitude_m_per_s) * tidal_factor(cfg, elapsed_s)
        return (float(cfg.u_mean_m_per_s) + amp * ex,
                float(cfg.v_mean_m_per_s) + amp * ey)
    raise ValueError(
        f"unknown forcing kind {cfg.kind!r}; supported: 'steady', 'tidal'"
    )


def assert_tide_resolving(cfg: ForcingConfig) -> None:
    """Refuse a de-tided or daily-mean field for a tide-resolving scenario.

    ``ForcingConfig.kind == 'tidal'`` claims the run resolves the tide.  A
    daily-mean or de-tided product cannot support that claim, so it is refused
    here rather than quietly averaged away [S10].
    """
    if str(cfg.kind).lower() != "tidal":
        return
    averaging = str(cfg.temporal_averaging).strip().lower()
    if averaging in NON_TIDE_RESOLVING_AVERAGING:
        raise TidalForcingRefused(
            f"forcing kind 'tidal' needs a tide-resolving field, but the "
            f"temporal averaging is {cfg.temporal_averaging!r}. A de-tided or "
            "daily-mean current field cannot stand in for a tidal reversal; "
            "use an hourly instantaneous product or the synthetic tidal field."
        )
    if cfg.tidal_amplitude_m_per_s == 0.0:
        raise TidalForcingRefused(
            "forcing kind 'tidal' with zero tidal amplitude does not reverse; "
            "either set an amplitude or declare kind='steady'"
        )


def forcing_at(
    cfg: ForcingConfig,
    grid: GridSpec,
    land_mask: np.ndarray,
    elapsed_s: float,
    start_utc: datetime,
    *,
    extra_note: str = "",
) -> Forcing:
    """Prescribed :class:`Forcing` at ``elapsed_s`` after ``start_utc``.

    Velocities are set to exactly zero on land cells: a land cell holds no
    water, so it carries no depth-averaged current either.
    """
    land_mask = np.asarray(land_mask, dtype=bool)
    if land_mask.shape != (grid.ny, grid.nx):
        raise ValueError(
            f"land_mask has shape {land_mask.shape}, expected {(grid.ny, grid.nx)}"
        )
    if float(cfg.diffusivity_m2_per_s) < 0.0:
        raise ValueError("diffusivity_m2_per_s must not be negative")
    u_scalar, v_scalar = mean_velocity_at(cfg, elapsed_s)
    u = np.full((grid.ny, grid.nx), u_scalar, dtype=float)
    v = np.full((grid.ny, grid.nx), v_scalar, dtype=float)
    u[land_mask] = 0.0
    v[land_mask] = 0.0
    note = SYNTHETIC_FORCING_NOTE
    if str(cfg.kind).lower() == "tidal":
        note += (
            f" Tidal constituent: amplitude {cfg.tidal_amplitude_m_per_s} m/s, "
            f"period {cfg.tidal_period_s} s (M2 by default); the sign of the "
            "along-channel velocity reverses within each period."
        )
    if extra_note:
        note = f"{note} {extra_note}"
    try:
        provenance = ProvenanceLabel(cfg.provenance)
    except ValueError:  # pragma: no cover - configuration typo guard
        raise ValueError(
            f"forcing provenance {cfg.provenance!r} is not a ProvenanceLabel; "
            "every number needs a valid label"
        ) from None
    return Forcing(
        time_utc=start_utc + timedelta(seconds=float(elapsed_s)),
        u_east_m_per_s=u,
        v_north_m_per_s=v,
        diffusivity_m2_per_s=float(cfg.diffusivity_m2_per_s),
        provenance=provenance,
        product_ref=cfg.product_ref,
        temporal_averaging=cfg.temporal_averaging,
        notes=note,
    )


def forcing_timeline(
    cfg: ForcingConfig,
    grid: GridSpec,
    land_mask: np.ndarray,
    n_steps: int,
    dt_s: float,
    start_utc: datetime,
    *,
    stamp_at_step_end: bool = True,
) -> tuple[Forcing, ...]:
    """One :class:`Forcing` per step.

    ``stamp_at_step_end`` evaluates the field at the end of each step, which is
    the value the implicit solver actually uses.
    """
    offset = 1 if stamp_at_step_end else 0
    return tuple(
        forcing_at(cfg, grid, land_mask, (i + offset) * float(dt_s), start_utc)
        for i in range(int(n_steps))
    )


def forcing_signature(forcings: Iterable[Forcing]) -> str:
    """Stable hash of a forcing timeline.

    Two runs that claim to share forcing (for example no-mat against mat) must
    produce the same signature; the arrays themselves are compared in the tests
    as well, because a hash proves equality only as far as it is trusted.
    """
    digest = hashlib.sha256()
    for forcing in forcings:
        digest.update(np.ascontiguousarray(forcing.u_east_m_per_s, dtype=np.float64).tobytes())
        digest.update(np.ascontiguousarray(forcing.v_north_m_per_s, dtype=np.float64).tobytes())
        digest.update(np.float64(forcing.diffusivity_m2_per_s).tobytes())
        digest.update(forcing.time_utc.isoformat().encode("utf-8"))
    return digest.hexdigest()[:16]


# ---------------------------------------------------------------------------
# The authorised contaminated seabed hotspot
# ---------------------------------------------------------------------------

def hotspot_entry_at(cfg: HotspotConfig, elapsed_s: float):
    """The active :class:`~reactive_seabed_mat.config.HotspotScheduleEntry`.

    The active entry is the last one whose ``start_s`` is at or before
    ``elapsed_s``.  Before the first entry there is no driving condition at all,
    which is returned as ``None`` rather than as a silent zero.
    """
    active = None
    for entry in sorted(cfg.schedule, key=lambda item: float(item.start_s)):
        if float(entry.start_s) <= float(elapsed_s):
            active = entry
        else:
            break
    return active


def hotspot_cell_mask(grid: GridSpec, cfg: HotspotConfig) -> np.ndarray:
    """``(ny, nx)`` boolean mask of the contaminated seabed cells.

    ``HotspotConfig.x_m`` and ``y_m`` are the **lower-left corner** of the
    rectangle, matching the way the default configuration places its stations
    inside the tiles it names.  Containment is by cell centre; see
    :data:`HOTSPOT_DISCRETISATION_NOTE`.
    """
    if cfg.width_m <= 0.0 or cfg.length_m <= 0.0:
        raise ValueError("hotspot width_m and length_m must be strictly positive")
    xx, yy = _cell_centre_grids(grid)
    x0, y0 = float(cfg.x_m), float(cfg.y_m)
    x1, y1 = x0 + float(cfg.width_m), y0 + float(cfg.length_m)
    return (xx >= x0) & (xx <= x1) & (yy >= y0) & (yy <= y1)


def bare_flux(
    seepage_velocity_m_per_s: float,
    film_transfer_m_per_s: float,
    porewater_kg_per_m3: Mapping[str, float],
    *,
    bottom_water_kg_per_m3: Mapping[str, float] | None = None,
    elements: Sequence[str] | None = None,
    clamp_at_zero: bool = True,
) -> dict[str, float]:
    """Uncapped bare-sediment areal flux, ``kg m^-2 s^-1`` per element.

    ``docs/MODEL_SPEC.md`` section 3::

        J_bare = (v + k_film) * (C_sed - C_water)

    With ``C_water = 0`` this reduces to ``(v + k_film) * C_sed``, which is the
    reference value stored on :class:`SeabedHotspot`.  The bottom-water term is
    what makes a rising plume genuinely reduce the driving gradient.

    ASSUMPTION: a reversed gradient (``C_water > C_sed``) is clamped to zero
    rather than modelled as deposition.  The sediment reservoir in this
    demonstrator is prescribed and never depleted, so a negative source would
    be a sink with no inventory behind it.  The clamp is reported by the caller,
    never applied silently.
    """
    if seepage_velocity_m_per_s < 0.0:
        raise ValueError(
            "seepage velocity is positive upward in this model; a negative "
            "value would drive water into the sediment and is not supported"
        )
    if film_transfer_m_per_s < 0.0:
        raise ValueError("film transfer coefficient must not be negative")
    names = list(elements) if elements is not None else list(porewater_kg_per_m3)
    transfer = float(seepage_velocity_m_per_s) + float(film_transfer_m_per_s)
    out: dict[str, float] = {}
    for name in names:
        c_sed = float(porewater_kg_per_m3.get(name, 0.0))
        if c_sed < 0.0:
            raise ValueError(f"sediment porewater for {name!r} is negative ({c_sed})")
        c_water = 0.0
        if bottom_water_kg_per_m3 is not None:
            c_water = float(bottom_water_kg_per_m3.get(name, 0.0))
        value = transfer * (c_sed - c_water)
        out[name] = max(value, 0.0) if clamp_at_zero else value
    return out


def build_hotspot(
    config: RunConfig,
    *,
    elapsed_s: float = 0.0,
    grid: GridSpec | None = None,
    land_mask: np.ndarray | None = None,
    elements: Sequence[str] | None = None,
) -> SeabedHotspot:
    """The :class:`SeabedHotspot` active at ``elapsed_s`` after the run start.

    Computes the cell indices of the contaminated area and the bare flux
    ``J_bare = (v + k_film) * C_sed`` per element from the hotspot schedule.
    The stored bare flux is the **reference** value, evaluated against clean
    bottom water; the plume-aware value is recomputed per tile in
    :func:`reactive_seabed_mat.coastal_transport.seabed_source.build_seabed_exchange`.

    Land cells inside the rectangle are excluded (a land cell holds no water and
    can receive no flux) and the exclusion is stated in the description.
    """
    cfg = config.hotspot
    grid = build_grid(config.domain) if grid is None else grid
    if land_mask is None:
        land_mask = build_land_mask(config.domain, grid)
    land_mask = np.asarray(land_mask, dtype=bool)
    if land_mask.shape != (grid.ny, grid.nx):
        raise ValueError(
            f"land_mask has shape {land_mask.shape}, expected {(grid.ny, grid.nx)}"
        )

    mask = hotspot_cell_mask(grid, cfg)
    n_requested = int(mask.sum())
    n_on_land = int((mask & land_mask).sum())
    mask &= ~land_mask
    indices = tuple(int(i) for i in np.flatnonzero(mask.reshape(-1)))
    if not indices:
        raise ValueError(
            f"hotspot {cfg.hotspot_id!r} covers no water cell of the "
            f"{grid.nx}x{grid.ny} grid; check its position, size and the land "
            "rectangles"
        )

    names = tuple(elements) if elements is not None else tuple(config.elements)
    entry = hotspot_entry_at(cfg, elapsed_s)
    if entry is None:
        porewater = {name: 0.0 for name in names}
        seepage = 0.0
        schedule_note = (
            f"No hotspot schedule entry is active at t = {float(elapsed_s):.0f} s, "
            "so the driving porewater concentration and the seepage velocity "
            "are zero. Nothing is released implicitly."
        )
    else:
        porewater = {
            name: float(entry.porewater_kg_per_m3.get(name, 0.0)) for name in names
        }
        seepage = float(entry.seepage_velocity_m_per_s)
        schedule_note = (
            f"Driving conditions from the schedule entry starting at "
            f"{float(entry.start_s):.0f} s, read at t = {float(elapsed_s):.0f} s."
        )

    flux = bare_flux(seepage, float(cfg.film_transfer_m_per_s), porewater,
                     elements=names)

    try:
        label = ProvenanceLabel(cfg.label)
    except ValueError:  # pragma: no cover - configuration typo guard
        raise ValueError(
            f"hotspot label {cfg.label!r} is not a ProvenanceLabel; every "
            "number needs a valid label"
        ) from None

    description = " ".join(
        part
        for part in (
            cfg.description,
            schedule_note,
            HOTSPOT_DISCRETISATION_NOTE,
            (
                f"{n_on_land} of {n_requested} cells inside the configured "
                "rectangle are land and were excluded: a land cell holds no "
                "water and receives no flux."
                if n_on_land
                else ""
            ),
        )
        if part
    )

    return SeabedHotspot(
        hotspot_id=cfg.hotspot_id,
        cell_indices=indices,
        sediment_porewater_kg_per_m3=porewater,
        bare_flux_kg_per_m2_per_s=flux,
        seepage_velocity_m_per_s=seepage,
        film_transfer_m_per_s=float(cfg.film_transfer_m_per_s),
        label=label,
        description=description,
    )


def hotspot_area_m2(grid: GridSpec, hotspot: SeabedHotspot) -> float:
    """Gridded area of the hotspot, which is what every flux is applied to."""
    return float(hotspot.n_cells) * grid.cell_area_m2


# ---------------------------------------------------------------------------
# Convenience bundle
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DomainBundle:
    """Convenience container: everything a run needs before the first step."""

    grid: GridSpec
    land_mask: np.ndarray
    field_state: FieldState
    hotspot: SeabedHotspot

    @property
    def water_cells(self) -> int:
        return int((~self.land_mask).sum())

    @property
    def land_cells(self) -> int:
        return int(self.land_mask.sum())


def build_domain(config: RunConfig, *, elapsed_s: float = 0.0) -> DomainBundle:
    """Grid, land mask, zero initial field and hotspot from one :class:`RunConfig`."""
    grid = build_grid(config.domain)
    land = build_land_mask(config.domain, grid)
    field = initial_field_state(config, grid=grid, land_mask=land)
    hotspot = build_hotspot(config, elapsed_s=elapsed_s, grid=grid, land_mask=land)
    return DomainBundle(grid=grid, land_mask=land, field_state=field, hotspot=hotspot)
