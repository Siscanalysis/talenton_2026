"""Domain, land mask, initial field, prescribed forcing and source schedule.

This module turns the coordinator-owned configuration objects
(:mod:`mesh_demo.config`) into the frozen contract objects
(:mod:`mesh_demo.contracts`) that :mod:`mesh_demo.transport.fipy_engine`
consumes.  It contains no solver: it only prepares inputs.

Conventions, all SI (see ``src/mesh_demo/units.py``):

* arrays are ``(ny, nx)``; ``arr.reshape(-1)`` is the FiPy ``Grid2D`` cell
  order, identical to :meth:`mesh_demo.contracts.GridSpec.cell_index`
  (flat index ``iy * nx + ix``);
* ``land_mask[iy, ix] is True`` marks a no-flux cell that holds no water;
* velocities are depth-averaged, in m s^-1, positive east / positive north.

Nothing here is a hydrodynamic solution.  The current field is *prescribed*:
a uniform mean flow, optionally modulated by a single sinusoidal tidal
constituent.  It is a synthetic demonstration field, labelled as such.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Mapping, Sequence

import numpy as np

from ..config import DomainConfig, ForcingConfig, RunConfig, SourceConfig
from ..contracts import (
    Element,
    FieldState,
    Forcing,
    GridSpec,
    ProvenanceLabel,
    SourceTerm,
    StateOrigin,
)

__all__ = [
    "build_grid",
    "build_land_mask",
    "initial_field_state",
    "forcing_at",
    "forcing_timeline",
    "forcing_signature",
    "schedule_rate_at",
    "sources_at",
    "source_timeline",
    "TidalForcingRefused",
    "SYNTHETIC_FORCING_NOTE",
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

# ASSUMPTION: a cell counts as land when its centre falls inside a configured
# land rectangle.  Partial coverage is not represented in this version.
_LAND_RULE_NOTE = "cell centre inside the rectangle (inclusive bounds)"


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
    ix = np.arange(grid.nx)
    iy = np.arange(grid.ny)
    xc = grid.origin_x_m + (ix + 0.5) * grid.dx_m
    yc = grid.origin_y_m + (iy + 0.5) * grid.dy_m
    xx, yy = np.meshgrid(xc, yc)
    for rect in domain.land_rectangles:
        x0, y0, x1, y1 = (float(v) for v in rect)
        lo_x, hi_x = min(x0, x1), max(x0, x1)
        lo_y, hi_y = min(y0, y1), max(y0, y1)
        mask |= (xx >= lo_x) & (xx <= hi_x) & (yy >= lo_y) & (yy <= hi_y)
    if mask.all():
        raise ValueError("the land rectangles cover the whole domain: no water left")
    return mask


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
        time_utc = config.start_datetime if config is not None else datetime.now().astimezone()
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

    Two scenarios that claim to share forcing (for example no-mesh versus
    mesh) must produce the same signature; the arrays themselves are compared
    in the tests as well.
    """
    digest = hashlib.sha256()
    for forcing in forcings:
        digest.update(np.ascontiguousarray(forcing.u_east_m_per_s, dtype=np.float64).tobytes())
        digest.update(np.ascontiguousarray(forcing.v_north_m_per_s, dtype=np.float64).tobytes())
        digest.update(np.float64(forcing.diffusivity_m2_per_s).tobytes())
        digest.update(forcing.time_utc.isoformat().encode("utf-8"))
    return digest.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def schedule_rate_at(
    schedule: Sequence, elapsed_s: float, elements: Sequence[str] | None = None
) -> dict[str, float]:
    """Piecewise-constant release rate in kg s^-1 at ``elapsed_s``.

    The active entry is the last one whose ``start_s`` is at or before
    ``elapsed_s``.  Before the first entry the rate is zero for every element:
    nothing is released implicitly.
    """
    active = None
    for entry in sorted(schedule, key=lambda item: float(item.start_s)):
        if float(entry.start_s) <= float(elapsed_s):
            active = entry
        else:
            break
    names: list[str] = list(elements) if elements is not None else []
    if not names:
        seen: list[str] = []
        for entry in schedule:
            for key in entry.rate_kg_per_s:
                if key not in seen:
                    seen.append(key)
        names = seen
    if active is None:
        return {name: 0.0 for name in names}
    rates = {name: float(active.rate_kg_per_s.get(name, 0.0)) for name in names}
    for name, value in rates.items():
        if value < 0.0:
            raise ValueError(
                f"source rate for {name!r} is negative ({value} kg/s); a negative "
                "release would be a sink and this model has no destruction term"
            )
    return rates


def sources_at(
    source_cfg: SourceConfig | Sequence[SourceConfig],
    elapsed_s: float,
    elements: Sequence[str] | None = None,
) -> tuple[SourceTerm, ...]:
    """The :class:`SourceTerm` list active at ``elapsed_s``."""
    configs = (source_cfg,) if isinstance(source_cfg, SourceConfig) else tuple(source_cfg)
    terms = []
    for cfg in configs:
        rates = schedule_rate_at(cfg.schedule, elapsed_s, elements)
        try:
            label = ProvenanceLabel(cfg.label)
        except ValueError:  # pragma: no cover - configuration typo guard
            raise ValueError(
                f"source label {cfg.label!r} is not a ProvenanceLabel"
            ) from None
        terms.append(
            SourceTerm(
                source_id=cfg.source_id,
                x_m=float(cfg.x_m),
                y_m=float(cfg.y_m),
                rate_kg_per_s=rates,
                label=label,
                description=cfg.description,
            )
        )
    return tuple(terms)


def source_timeline(
    source_cfg: SourceConfig | Sequence[SourceConfig],
    n_steps: int,
    dt_s: float,
    elements: Sequence[str] | None = None,
    *,
    stamp_at_step_end: bool = True,
) -> tuple[tuple[SourceTerm, ...], ...]:
    """One source list per step, matching :func:`forcing_timeline`."""
    offset = 1 if stamp_at_step_end else 0
    return tuple(
        sources_at(source_cfg, (i + offset) * float(dt_s), elements)
        for i in range(int(n_steps))
    )


@dataclass(frozen=True, slots=True)
class DomainBundle:
    """Convenience container: everything a run needs before the first step."""

    grid: GridSpec
    land_mask: np.ndarray
    field_state: FieldState

    @property
    def water_cells(self) -> int:
        return int((~self.land_mask).sum())

    @property
    def land_cells(self) -> int:
        return int(self.land_mask.sum())


def build_domain(config: RunConfig) -> DomainBundle:
    """Grid, land mask and zero initial field from one :class:`RunConfig`."""
    grid = build_grid(config.domain)
    land = build_land_mask(config.domain, grid)
    field = initial_field_state(config, grid=grid, land_mask=land)
    return DomainBundle(grid=grid, land_mask=land, field_state=field)
