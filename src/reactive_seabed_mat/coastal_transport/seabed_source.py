"""Coupling: from mat tile states to the residual flux the water receives.

``docs/MODEL_SPEC.md`` section 5.  Per contaminated seabed cell::

    covered_fraction = sum over tiles overlapping the cell of
                       (tile coverage_fraction * area weight)
    bypass           = edge_leakage_fraction + fouling_bypass_coupling * f
    effective_cover  = covered_fraction * (1 - bypass)

    J_cell = effective_cover * J_out(tile) + (1 - effective_cover) * J_bare

Cells outside the mat footprint emit ``J_bare``.  Cells outside the hotspot emit
nothing.  This is the whole coupling: **nothing is subtracted from a
water-column cell**, and there is no interception efficiency anywhere.

Geometry conventions used here, stated because the frozen contract does not fix
them:

* ``MatTileGeometry.x_m`` and ``y_m`` are the **lower-left corner** of the tile
  footprint, matching :class:`~reactive_seabed_mat.config.HotspotConfig` and the
  station positions the default configuration assigns to named tiles.  See
  :func:`tile_bounds`, which is the single place the convention is applied.
* The area weight of a tile in a cell is the fraction of that **cell's** area
  covered by the tile footprint, so partial coverage is represented exactly.
  A mat covering 45 % of the hotspot therefore leaves exactly 55 % of the
  hotspot area emitting the bare flux, whatever the cell size.
* ``SeabedExchange.cell_weights`` are the fractions of the **tile's** footprint
  that fall in each listed cell, so a weighted mean over them is a tile average.

Every degradation mode keeps its own component in
:attr:`SeabedSourceField.components`, so a map can show why a cell emits:
saturation moves ``J_out``, fouling moves ``edge_leakage``, displacement moves
``displaced``, local damage moves ``damaged``, and an undersized mat moves
``uncovered``.  Burial is not a component: it acts inside the layer by lowering
``J_out``, which is exactly why it can masquerade as success.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

import numpy as np

from ..config import HotspotConfig, MatLayoutConfig, RunConfig
from ..contracts import (
    FieldState,
    Forcing,
    GridSpec,
    LayerStep,
    MatTileGeometry,
    MatTileState,
    SeabedExchange,
    SeabedHotspot,
    SeabedSourceField,
)
from .domain import bare_flux

__all__ = [
    "CONTRIBUTION_COMPONENTS",
    "DIAGNOSTIC_COMPONENTS",
    "DEFAULT_FOULING_BYPASS_COUPLING",
    "OverlappingTilesRefused",
    "TilePlan",
    "tile_bounds",
    "plan_tile_layout",
    "plan_tile_layout_for",
    "check_tile_overlaps",
    "cell_area_weights",
    "bypass_fraction",
    "residual_source_flux",
    "residual_source_flux_detailed",
    "build_seabed_exchange",
    "component_total",
]


#: The five contribution components.  They are areal fluxes in kg m^-2 s^-1 and
#: they sum, cell by cell, to ``flux_kg_per_m2_per_s``.
#:
#: ``docs/MODEL_SPEC.md`` section 5 names four (covered, uncovered, damaged,
#: edge leakage).  ``displaced`` is split out of ``damaged`` here because
#: degradation modes 3 and 4 must stay independent: a displaced tile and a torn
#: tile are different failures with different remedies, and merging them would
#: hide exactly what the demonstrator exists to show.
CONTRIBUTION_COMPONENTS: tuple[str, ...] = (
    "covered",
    "uncovered",
    "damaged",
    "displaced",
    "edge_leakage",
)

#: Components that describe a cell rather than contributing flux to it.  They
#: are excluded from the component sum.  ``bare_reference`` is kg m^-2 s^-1;
#: ``effective_cover`` and ``covered_fraction`` are dimensionless.
DIAGNOSTIC_COMPONENTS: tuple[str, ...] = (
    "bare_reference",
    "effective_cover",
    "covered_fraction",
    "clamped_negative_flux",
)

#: A clean layer under contaminated bottom water can take metal DOWNWARD out of
#: the water column, giving a small negative outward flux.  As a source term
#: that would be negative, which the coastal ledger does not model, so it is
#: clamped to zero and the clamped amount is reported in
#: ``components['clamped_negative_flux']`` rather than being silently dropped.
#: Anything larger than this fraction of the bare reference flux is treated as
#: an error, not as noise.
NEGATIVE_FLUX_TOLERANCE: float = 1.0e-3

#: ASSUMPTION, duplicated from :class:`~reactive_seabed_mat.config.DegradationConfig`
#: because :class:`~reactive_seabed_mat.contracts.ResidualSourceFlux` is frozen
#: with no configuration argument.  Pore blockage raises the head across the
#: layer and pushes flow around the tile edge, so fouling is never a free
#: benefit.  Callers holding a ``DegradationConfig`` should use
#: :func:`residual_source_flux_detailed` and pass the configured value.
DEFAULT_FOULING_BYPASS_COUPLING: float = 0.35

_AREA_TOLERANCE = 1e-12


class OverlappingTilesRefused(ValueError):
    """Two tiles overlap by more than the configured ``overlap_m`` allowance.

    Refused rather than silently double counted, which is the behaviour the
    build brief asks for in this version.
    """


@dataclass(frozen=True, slots=True)
class TilePlan:
    """A planned tile: an identifier and its footprint.

    :class:`~reactive_seabed_mat.contracts.MatTileGeometry` carries no
    identifier, so the layout planner pairs the two.  Tile *state* (loading,
    fouling, integrity) belongs to the reactive-layer branch; this is footprint
    geometry only.
    """

    tile_id: str
    geometry: MatTileGeometry


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def tile_bounds(geometry: MatTileGeometry) -> tuple[float, float, float, float]:
    """``(x0, y0, x1, y1)`` footprint of a tile in metres.

    ``x_m`` and ``y_m`` are the lower-left corner.  This function is the only
    place that convention is applied, so a contract change would touch one line.
    """
    x0 = float(geometry.x_m)
    y0 = float(geometry.y_m)
    return (x0, y0, x0 + float(geometry.width_m), y0 + float(geometry.length_m))


def plan_tile_layout(
    mat: MatLayoutConfig,
    hotspot: HotspotConfig,
) -> tuple[TilePlan, ...]:
    """Lay ``mat.tiles_x * mat.tiles_y`` abutting tiles over the hotspot.

    The mat is a centred rectangle whose area is ``coverage_fraction`` of the
    hotspot rectangle, so a coverage of 0.45 leaves 55 % of the hotspot area
    uncovered by construction.  Tiles abut rather than overlap: ``overlap_m`` is
    an *allowance* checked by :func:`check_tile_overlaps`, not a construction
    parameter, so the default layout has zero overlap and nothing is double
    counted.

    Tile identifiers are ``tile_<ix>_<iy>``, matching the identifiers the
    coordinator-owned scenario registry and station list already use.
    """
    if mat.tiles_x < 1 or mat.tiles_y < 1:
        raise ValueError("tiles_x and tiles_y must be at least 1")
    coverage = float(mat.coverage_fraction)
    if not 0.0 <= coverage <= 1.0:
        raise ValueError(f"coverage_fraction must lie in [0, 1], got {coverage}")
    if coverage == 0.0:
        return ()
    scale = float(np.sqrt(coverage))
    mat_width = float(hotspot.width_m) * scale
    mat_length = float(hotspot.length_m) * scale
    x0 = float(hotspot.x_m) + 0.5 * (float(hotspot.width_m) - mat_width)
    y0 = float(hotspot.y_m) + 0.5 * (float(hotspot.length_m) - mat_length)
    tile_w = mat_width / mat.tiles_x
    tile_l = mat_length / mat.tiles_y
    plans: list[TilePlan] = []
    for iy in range(mat.tiles_y):
        for ix in range(mat.tiles_x):
            plans.append(
                TilePlan(
                    tile_id=f"tile_{ix}_{iy}",
                    geometry=MatTileGeometry(
                        width_m=tile_w,
                        length_m=tile_l,
                        thickness_m=float(mat.thickness_m),
                        x_m=x0 + ix * tile_w,
                        y_m=y0 + iy * tile_l,
                        bulk_density_kg_per_m3=float(mat.bulk_density_kg_per_m3),
                        porosity=float(mat.porosity),
                        edge_leakage_fraction=float(mat.edge_leakage_fraction),
                        edge_leakage_interval=tuple(mat.edge_leakage_interval),
                    ),
                )
            )
    return tuple(plans)


def plan_tile_layout_for(config: RunConfig) -> tuple[TilePlan, ...]:
    """:func:`plan_tile_layout` from a whole :class:`RunConfig`."""
    return plan_tile_layout(config.mat, config.hotspot)


def _overlap_extent(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> tuple[float, float]:
    """Overlap width and height of two axis-aligned rectangles, in metres."""
    ox = min(a[2], b[2]) - max(a[0], b[0])
    oy = min(a[3], b[3]) - max(a[1], b[1])
    return (max(ox, 0.0), max(oy, 0.0))


def check_tile_overlaps(
    plans: Sequence[TilePlan] | Sequence[MatTileState],
    overlap_m: float,
) -> None:
    """Refuse tiles that overlap by more than ``overlap_m`` in both directions.

    A designed seam overlap is a thin strip: it is thin in one direction and
    long in the other.  Two tiles that overlap by more than the allowance in
    *both* directions are laid on top of one another, and their coverage would
    be double counted.  That is refused rather than approximated.
    """
    entries = [(plan.tile_id, tile_bounds(plan.geometry)) for plan in plans]
    allowance = float(overlap_m)
    if allowance < 0.0:
        raise ValueError("overlap_m must not be negative")
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            ox, oy = _overlap_extent(entries[i][1], entries[j][1])
            if ox <= _AREA_TOLERANCE or oy <= _AREA_TOLERANCE:
                continue
            if min(ox, oy) > allowance + _AREA_TOLERANCE:
                raise OverlappingTilesRefused(
                    f"tiles {entries[i][0]!r} and {entries[j][0]!r} overlap by "
                    f"{ox:.3f} m x {oy:.3f} m, which exceeds the configured "
                    f"overlap allowance of {allowance:.3f} m in both "
                    "directions. Overlapping coverage is refused in this "
                    "version rather than silently double counted."
                )


def cell_area_weights(grid: GridSpec, geometry: MatTileGeometry) -> np.ndarray:
    """``(ny, nx)`` fraction of each cell's area covered by the tile footprint.

    Exact for a partially covered cell, which is what makes the coverage
    bookkeeping exact rather than a cell-count approximation.
    """
    x0, y0, x1, y1 = tile_bounds(geometry)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("tile width_m and length_m must be strictly positive")
    edges_x = grid.origin_x_m + np.arange(grid.nx + 1) * grid.dx_m
    edges_y = grid.origin_y_m + np.arange(grid.ny + 1) * grid.dy_m
    overlap_x = np.clip(np.minimum(edges_x[1:], x1) - np.maximum(edges_x[:-1], x0),
                        0.0, None)
    overlap_y = np.clip(np.minimum(edges_y[1:], y1) - np.maximum(edges_y[:-1], y0),
                        0.0, None)
    return np.outer(overlap_y, overlap_x) / grid.cell_area_m2


def bypass_fraction(
    tile: MatTileState,
    *,
    fouling_bypass_coupling: float = DEFAULT_FOULING_BYPASS_COUPLING,
) -> float:
    """``edge_leakage_fraction + fouling_bypass_coupling * fouling_index``.

    Clipped into ``[0, 1]``.  Lower permeability also lowers the flux *through*
    the layer, so pore blockage would look like an improvement if it were
    modelled alone.  This term is what stops that.
    """
    value = (
        float(tile.geometry.edge_leakage_fraction)
        + float(fouling_bypass_coupling) * float(tile.fouling_index)
    )
    return float(min(max(value, 0.0), 1.0))


# ---------------------------------------------------------------------------
# Tile states to a distributed source flux
# ---------------------------------------------------------------------------

def _element_names(
    hotspot: SeabedHotspot, layer_steps: Sequence[LayerStep]
) -> tuple[str, ...]:
    names = list(hotspot.bare_flux_kg_per_m2_per_s)
    for step in layer_steps:
        for key in step.flux_out_kg_per_m2_per_s:
            if key not in names:
                names.append(key)
    return tuple(names)


def _steps_by_tile(layer_steps: Sequence[LayerStep]) -> dict[str, LayerStep]:
    out: dict[str, LayerStep] = {}
    for step in layer_steps:
        tile_id = step.new_state.tile_id
        if tile_id in out:
            raise ValueError(
                f"two layer steps were supplied for tile {tile_id!r}; one step "
                "per tile per call, otherwise its flux would be counted twice"
            )
        out[tile_id] = step
    return out


def residual_source_flux_detailed(
    grid: GridSpec,
    hotspot: SeabedHotspot,
    tiles: Sequence[MatTileState],
    layer_steps: Sequence[LayerStep],
    time_utc: datetime,
    *,
    fouling_bypass_coupling: float = DEFAULT_FOULING_BYPASS_COUPLING,
    overlap_m: float | None = None,
    elements: Sequence[str] | None = None,
) -> SeabedSourceField:
    """:func:`residual_source_flux` with the coupling parameters exposed.

    ``overlap_m`` enables the overlapping-tile refusal; pass the configured
    ``MatLayoutConfig.overlap_m``.  ``None`` skips the check, which is only
    appropriate when the caller has already run :func:`check_tile_overlaps`.
    """
    shape = (grid.ny, grid.nx)
    names = tuple(elements) if elements is not None else _element_names(hotspot, layer_steps)
    if overlap_m is not None:
        check_tile_overlaps(tiles, overlap_m)

    hotspot_mask = np.zeros(grid.n_cells, dtype=bool)
    indices = np.asarray(list(hotspot.cell_indices), dtype=int)
    if indices.size:
        if indices.min() < 0 or indices.max() >= grid.n_cells:
            raise IndexError(
                f"hotspot {hotspot.hotspot_id!r} names a cell outside the "
                f"{grid.nx}x{grid.ny} grid"
            )
        hotspot_mask[indices] = True
    hotspot_mask = hotspot_mask.reshape(shape)

    steps = _steps_by_tile(layer_steps)

    # Per-tile weights, accumulated over cells.
    covered_fraction = np.zeros(shape)          # sum of coverage * area weight
    damaged_weight = np.zeros(shape)            # torn share of a tile footprint
    displaced_weight = np.zeros(shape)          # displaced or retired tile
    edge_weight = np.zeros(shape)               # bypassed share of covered area
    cover_weight = np.zeros(shape)              # effective cover, all tiles
    footprint_weight = np.zeros(shape)          # any tile footprint at all
    covered_flux = {name: np.zeros(shape) for name in names}
    clamped_flux = {name: np.zeros(shape) for name in names}
    bare_override = {name: np.zeros(shape) for name in names}
    bare_override_weight = np.zeros(shape)
    tiles_without_step: list[str] = []

    for tile in tiles:
        weights = cell_area_weights(grid, tile.geometry) * hotspot_mask
        if not np.any(weights > 0.0):
            continue
        footprint_weight += weights
        coverage = float(tile.coverage_fraction)
        bypass = bypass_fraction(
            tile, fouling_bypass_coupling=fouling_bypass_coupling
        )
        step = steps.get(tile.tile_id)
        if step is None:
            if coverage > 0.0:
                raise KeyError(
                    f"tile {tile.tile_id!r} still covers seabed cells "
                    f"(coverage_fraction {coverage:.3f}) but no LayerStep was "
                    "supplied, so its residual flux J_out is unknown. Supply "
                    "one step per active tile."
                )
            tiles_without_step.append(tile.tile_id)

        lost = weights * (1.0 - coverage)
        if tile.displaced or not tile.active:
            displaced_weight += lost
        else:
            damaged_weight += lost
        edge_weight += weights * coverage * bypass
        effective = weights * coverage * (1.0 - bypass)
        cover_weight += effective
        covered_fraction += weights * coverage

        if step is not None:
            for name in names:
                j_out = float(step.flux_out_kg_per_m2_per_s.get(name, 0.0))
                if j_out < 0.0:
                    # A small negative outward flux is physically meaningful: a
                    # clean layer under contaminated bottom water takes metal
                    # DOWNWARD out of the water column. As a *source* term that
                    # would be negative, which the coastal ledger does not model,
                    # so it is clamped to zero and the clamped amount reported.
                    # A large negative value is a different matter and still
                    # fails loudly.
                    reference = abs(
                        float(
                            (step.exchange.bare_flux_kg_per_m2_per_s.get(name, 0.0))
                            if step.exchange is not None
                            else 0.0
                        )
                    )
                    tolerance = max(NEGATIVE_FLUX_TOLERANCE * reference, 1e-30)
                    if -j_out > tolerance:
                        raise ValueError(
                            f"tile {tile.tile_id!r} reports a negative residual "
                            f"flux for {name!r} ({j_out} kg/m2/s), larger than "
                            f"the {tolerance:.3e} tolerance; the mat cannot pump "
                            "contaminant back into the sediment"
                        )
                    clamped_flux[name] += effective * (-j_out)
                    j_out = 0.0
                covered_flux[name] += effective * j_out
            exchange = step.exchange
            if exchange is not None:
                bare_override_weight += weights
                for name in names:
                    bare_override[name] += weights * float(
                        exchange.bare_flux_kg_per_m2_per_s.get(name, 0.0)
                    )

    # The tile weights on one cell sum to the footprint weight, and the four
    # tile-derived components partition it exactly.  A footprint weight above 1
    # can only come from overlapping tiles, which check_tile_overlaps refuses;
    # a caller may skip that check, so every tile-derived weight is rescaled by
    # the same factor (which keeps the components summing to the total) and the
    # correction is recorded rather than applied silently.
    excess = np.maximum(footprint_weight - 1.0, 0.0)
    cover_clip_cells = int(np.count_nonzero(excess > _AREA_TOLERANCE))
    cover_clip_max = float(excess.max()) if excess.size else 0.0
    if cover_clip_cells:
        safe = np.where(footprint_weight > 1.0, footprint_weight, 1.0)
        scale = np.where(footprint_weight > 1.0, 1.0 / safe, 1.0)
        cover_weight = cover_weight * scale
        edge_weight = edge_weight * scale
        damaged_weight = damaged_weight * scale
        displaced_weight = displaced_weight * scale
        covered_fraction = covered_fraction * scale
        footprint_weight = footprint_weight * scale
        for name in names:
            covered_flux[name] = covered_flux[name] * scale
    uncovered_weight = np.clip(1.0 - footprint_weight, 0.0, 1.0) * hotspot_mask

    flux: dict[str, np.ndarray] = {}
    components: dict[str, dict[str, np.ndarray]] = {}
    for name in names:
        reference = float(hotspot.bare_flux_kg_per_m2_per_s.get(name, 0.0))
        j_bare = np.where(hotspot_mask, reference, 0.0)
        has_override = bare_override_weight > _AREA_TOLERANCE
        j_bare = np.where(
            has_override & hotspot_mask,
            np.divide(
                bare_override[name],
                np.where(has_override, bare_override_weight, 1.0),
            ),
            j_bare,
        )
        covered = covered_flux[name] * hotspot_mask
        uncovered = uncovered_weight * j_bare
        damaged = damaged_weight * j_bare
        displaced = displaced_weight * j_bare
        edge = edge_weight * j_bare
        total = covered + uncovered + damaged + displaced + edge
        flux[name] = total
        components[name] = {
            "covered": covered,
            "uncovered": uncovered,
            "damaged": damaged,
            "displaced": displaced,
            "edge_leakage": edge,
            "bare_reference": j_bare,
            "effective_cover": cover_weight * hotspot_mask,
            "covered_fraction": covered_fraction * hotspot_mask,
            "clamped_negative_flux": clamped_flux[name] * hotspot_mask,
        }

    notes = (
        "Residual seabed flux, docs/MODEL_SPEC.md section 5. Cells outside the "
        "hotspot emit nothing; cells inside it that no intact tile covers emit "
        "the bare flux. Components are areal fluxes in kg m^-2 s^-1 and the "
        f"{len(CONTRIBUTION_COMPONENTS)} contribution components sum to the "
        "total; bare_reference is a flux and effective_cover and "
        "covered_fraction are dimensionless."
    )
    if tiles_without_step:
        notes += (
            " No LayerStep was supplied for "
            f"{', '.join(sorted(tiles_without_step))}; those tiles cover "
            "nothing, so only the bare flux applies to their cells."
        )
    if cover_clip_cells:
        notes += (
            f" NUMERICAL CORRECTION: the tile footprint weight exceeded 1 in "
            f"{cover_clip_cells} cell(s) by up to {cover_clip_max:.4f}, so "
            "tiles overlap. Every tile-derived weight was rescaled by the same "
            "factor. Overlapping tiles should be refused with "
            "check_tile_overlaps rather than rescaled."
        )

    return SeabedSourceField(
        time_utc=time_utc,
        flux_kg_per_m2_per_s=flux,
        components=components,
        provenance=hotspot.label,
        notes=notes,
    )


def residual_source_flux(
    grid: GridSpec,
    hotspot: SeabedHotspot,
    tiles: Sequence[MatTileState],
    layer_steps: Sequence[LayerStep],
    time_utc: datetime,
) -> SeabedSourceField:
    """Tile states plus hotspot to the distributed source the water receives.

    Implements :class:`~reactive_seabed_mat.contracts.ResidualSourceFlux`
    exactly.  The fouling-to-bypass coupling is taken from
    :data:`DEFAULT_FOULING_BYPASS_COUPLING` because the frozen signature carries
    no configuration; use :func:`residual_source_flux_detailed` to pass the
    configured value and to enable the overlapping-tile refusal.
    """
    return residual_source_flux_detailed(
        grid, hotspot, tiles, layer_steps, time_utc
    )


def component_total(
    source: SeabedSourceField, element: str, grid: GridSpec, component: str
) -> float:
    """Total rate contributed by one component, kg s^-1."""
    if component not in CONTRIBUTION_COMPONENTS:
        raise KeyError(
            f"{component!r} is not a contribution component; "
            f"contributions are {CONTRIBUTION_COMPONENTS} and diagnostics are "
            f"{DIAGNOSTIC_COMPONENTS}"
        )
    array = source.components[element][component]
    return float(np.sum(array) * grid.cell_area_m2)


# ---------------------------------------------------------------------------
# Driving conditions per tile
# ---------------------------------------------------------------------------

def build_seabed_exchange(
    field_state: FieldState,
    tiles: Sequence[MatTileState],
    hotspot: SeabedHotspot,
    forcing: Forcing,
    dt_s: float,
) -> Sequence[SeabedExchange]:
    """Driving conditions per tile, from the hotspot and the overlying field.

    Implements :class:`~reactive_seabed_mat.contracts.BuildSeabedExchange`
    exactly.  For each tile:

    * the sediment-side porewater concentration comes from the hotspot
      schedule;
    * the **bottom-water** concentration is read from the overlying field cells
      the tile occupies, so a rising plume genuinely reduces the driving
      gradient;
    * the seepage velocity and the benthic film coefficient come from the
      hotspot;
    * ``bare_flux_kg_per_m2_per_s`` is ``(v + k_film) * (C_sed - C_water)``
      evaluated with that same bottom water, so attenuation is measured against
      the flux the *same* conditions would have produced with no mat.

    ASSUMPTION: the film coefficient is a fixed benthic boundary-layer value and
    is not made a function of the overlying current.  A stronger current would
    thin the diffusive sublayer and raise ``k_film`` in reality.  ``forcing`` is
    therefore used for context and time stamping only, and the assumption is
    recorded in ``diagnostics['film_transfer_is_current_dependent']``.
    """
    if dt_s <= 0.0:
        raise ValueError(f"dt_s must be strictly positive, got {dt_s}")
    grid = field_state.grid
    land = np.asarray(field_state.land_mask, dtype=bool)
    shape = (grid.ny, grid.nx)

    hotspot_mask = np.zeros(grid.n_cells, dtype=bool)
    indices = np.asarray(list(hotspot.cell_indices), dtype=int)
    if indices.size:
        hotspot_mask[indices] = True
    hotspot_mask = hotspot_mask.reshape(shape)
    usable = hotspot_mask & ~land

    names = tuple(field_state.concentration_kg_per_m3)
    u = np.asarray(forcing.u_east_m_per_s, dtype=float)
    v = np.asarray(forcing.v_north_m_per_s, dtype=float)

    exchanges: list[SeabedExchange] = []
    for tile in tiles:
        weights = cell_area_weights(grid, tile.geometry)
        footprint_total = float(weights.sum())
        usable_weights = weights * usable
        usable_total = float(usable_weights.sum())
        flat = usable_weights.reshape(-1)
        cell_indices = tuple(int(i) for i in np.flatnonzero(flat > _AREA_TOLERANCE))
        denominator = float(flat[list(cell_indices)].sum()) if cell_indices else 0.0
        cell_weights = tuple(
            float(flat[i] / denominator) for i in cell_indices
        ) if denominator > 0.0 else ()

        bottom_water: dict[str, float] = {}
        for name in names:
            field = np.asarray(field_state.concentration_kg_per_m3[name], dtype=float)
            if denominator > 0.0:
                bottom_water[name] = float(
                    np.sum(usable_weights * field) / denominator
                )
            else:
                bottom_water[name] = 0.0

        porewater = {
            name: float(hotspot.sediment_porewater_kg_per_m3.get(name, 0.0))
            for name in names
        }
        signed = bare_flux(
            hotspot.seepage_velocity_m_per_s,
            hotspot.film_transfer_m_per_s,
            porewater,
            bottom_water_kg_per_m3=bottom_water,
            elements=names,
            clamp_at_zero=False,
        )
        clamped = {name: max(value, 0.0) for name, value in signed.items()}
        clamped_elements = tuple(
            name for name, value in signed.items() if value < 0.0
        )

        if denominator > 0.0:
            speed = float(
                np.sum(usable_weights * np.hypot(u, v)) / denominator
            )
        else:
            speed = 0.0

        diagnostics: dict[str, Any] = {
            "footprint_area_m2": tile.geometry.footprint_area_m2,
            "footprint_inside_hotspot_fraction": (
                usable_total / footprint_total if footprint_total > 0.0 else 0.0
            ),
            "n_bottom_water_cells": len(cell_indices),
            "film_transfer_is_current_dependent": False,
            "bare_flux_signed_kg_per_m2_per_s": signed,
            "bare_flux_clamped_elements": clamped_elements,
            "coverage_fraction": float(tile.coverage_fraction),
            "fouling_index": float(tile.fouling_index),
            "integrity_index": float(tile.integrity_index),
            "burial_depth_m": float(tile.burial_depth_m),
            "displaced": bool(tile.displaced),
            "forcing_provenance": forcing.provenance.value,
            "notes": (
                "Bottom water is the footprint-weighted mean of the overlying "
                "water cells, excluding land. J_bare uses that same bottom "
                "water, so the mat and the no-mat reference see identical "
                "driving conditions."
            ),
        }
        if clamped_elements:
            diagnostics["notes"] += (
                " NUMERICAL CORRECTION: the bare flux was negative for "
                f"{', '.join(clamped_elements)} (bottom water above the "
                "sediment porewater) and was clamped to zero; the signed value "
                "is kept in bare_flux_signed_kg_per_m2_per_s."
            )
        if not cell_indices:
            diagnostics["notes"] += (
                " This tile overlaps no usable hotspot water cell, so its "
                "bottom water is reported as zero."
            )

        exchanges.append(
            SeabedExchange(
                tile_id=tile.tile_id,
                time_utc=field_state.time_utc,
                dt_s=float(dt_s),
                sediment_porewater_kg_per_m3=porewater,
                bottom_water_kg_per_m3=bottom_water,
                seepage_velocity_m_per_s=float(hotspot.seepage_velocity_m_per_s),
                film_transfer_m_per_s=float(hotspot.film_transfer_m_per_s),
                bare_flux_kg_per_m2_per_s=clamped,
                cell_indices=cell_indices,
                cell_weights=cell_weights,
                driving_is_measured=False,
                environment={
                    "current_speed_m_per_s": speed,
                    "diffusivity_m2_per_s": float(forcing.diffusivity_m2_per_s),
                    "mixing_depth_m": float(grid.mixing_depth_m),
                },
                diagnostics=diagnostics,
            )
        )
    return tuple(exchanges)
