"""The coupled run.  Coordinator-owned integration surface.

Two clocks, as ``docs/MODEL_SPEC.md`` section 2 requires:

* the **mat timeline** advances for the whole simulated duration at
  ``RunConfig.dt_s`` (6 h by default), solving the 1-D reactive layer per tile;
* at each time named in ``PlumeWindowConfig.sample_years`` a short **plume
  window** runs the 2-D coastal model with the residual flux held at that mat
  state, to produce the maps and the water-column budget.

The two ledgers are reported separately and each carries its own window, so
nothing implies the coastal model was integrated for years.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Any, Mapping, Sequence

import numpy as np

from ..coastal_transport import domain as dm
from ..coastal_transport import fipy_engine as fe
from ..coastal_transport import seabed_source as ss
from ..config import RunConfig
from ..contracts import (
    Element,
    FieldState,
    LayerStep,
    MassLedger,
    MatTileState,
    SeabedSourceField,
)
from ..reactive_layer import (
    advance_reactive_layer,
    apply_degradation_events,
    build_material_map,
    build_tile_states,
    grow_burial,
    grow_fouling,
)

_SECONDS_PER_YEAR = 365.25 * 86400.0

__all__ = [
    "MatTimelinePoint",
    "PlumeWindowResult",
    "ScenarioResult",
    "run_mat_timeline",
    "run_plume_window",
    "run_scenario",
]


@dataclass(frozen=True, slots=True)
class MatTimelinePoint:
    """One sample of the mat timeline, for plotting and export."""

    elapsed_s: float
    elapsed_years: float
    time_utc: Any
    #: Area-weighted mean over the hotspot, per element [kg m^-2 s^-1].
    mean_residual_flux: Mapping[str, float]
    mean_bare_flux: Mapping[str, float]
    attenuation: Mapping[str, float]
    saturation: Mapping[str, float]
    retained_kg: Mapping[str, float]
    mean_fouling: float
    mean_integrity: float
    mean_coverage: float
    n_tiles_active: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "elapsed_s": self.elapsed_s,
            "elapsed_years": self.elapsed_years,
            "time_utc": str(self.time_utc),
            "mean_residual_flux_kg_per_m2_per_s": dict(self.mean_residual_flux),
            "mean_bare_flux_kg_per_m2_per_s": dict(self.mean_bare_flux),
            "attenuation": dict(self.attenuation),
            "saturation_fraction": dict(self.saturation),
            "retained_kg": dict(self.retained_kg),
            "mean_fouling_index": self.mean_fouling,
            "mean_integrity_index": self.mean_integrity,
            "mean_coverage_fraction": self.mean_coverage,
            "n_tiles_active": self.n_tiles_active,
        }


@dataclass(frozen=True, slots=True)
class PlumeWindowResult:
    """A short 2-D run at one mat state, plus the same run with no mat."""

    elapsed_years: float
    label: str
    field_with_mat: FieldState
    field_without_mat: FieldState
    source_with_mat: SeabedSourceField
    source_without_mat: SeabedSourceField
    ledger_with_mat: Mapping[str, MassLedger]
    ledger_without_mat: Mapping[str, MassLedger]
    window_s: float
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def peak_concentration(self, element: str, *, with_mat: bool = True) -> float:
        state = self.field_with_mat if with_mat else self.field_without_mat
        return float(np.max(state.concentration_kg_per_m3[element]))


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    config: RunConfig
    timeline: Sequence[MatTimelinePoint]
    windows: Sequence[PlumeWindowResult]
    final_tiles: Sequence[MatTileState]
    #: The reactive layer's own budget: what entered through the sediment face
    #: equals what is retained plus what left into the water.
    mat_ledger: Mapping[str, MassLedger]
    #: Gross mass leaving the whole hotspot over the timeline, including the
    #: part that never touches a tile.  Reported separately on purpose.
    hotspot_released_kg: Mapping[str, float] = field(default_factory=dict)
    checks: Sequence[Any] = ()


# ---------------------------------------------------------------------------
# Mat timeline
# ---------------------------------------------------------------------------

def _mean_over_tiles(values: Sequence[float]) -> float:
    return float(np.mean(values)) if len(values) else 0.0


def run_mat_timeline(
    config: RunConfig,
    *,
    sample_every_s: float | None = None,
    progress: bool = False,
) -> tuple[list[MatTimelinePoint], list[MatTileState], dict[str, MassLedger], dict[float, list]]:
    """Advance the reactive layer over the whole simulated duration.

    Returns the sampled timeline, the final tile states, the per-element mat
    ledger, and the tile states captured at each requested plume-window time.
    """
    materials = build_material_map(config.mat)
    elements = [element for element in config.elements]
    start = config.start_datetime

    bundle = dm.build_domain(config, elapsed_s=0.0)
    grid, land_mask = bundle.grid, bundle.land_mask
    field_state = bundle.field_state

    tiles = list(
        build_tile_states(
            config.mat, start, materials, hotspot=config.hotspot, elements=elements
        )
    )

    dt = config.dt_s
    n_steps = config.n_steps
    if sample_every_s is None:
        sample_every_s = max(dt, config.duration_s / 240.0)

    want_years = sorted(set(float(y) for y in config.plume.sample_years))
    captured: dict[float, list] = {}

    # The MAT ledger is the budget of the reactive layer's own control volume:
    # what entered through the sediment face equals what is retained plus what
    # left into the water. The gross mass leaving the hotspot as a whole,
    # including the part that never touches a tile, is a different quantity and
    # is tracked separately as ``hotspot_released``.
    entered = {element: 0.0 for element in elements}
    left = {element: 0.0 for element in elements}
    hotspot_released = {element: 0.0 for element in elements}
    retained_delta = {element: 0.0 for element in elements}
    correction = {element: 0.0 for element in elements}

    timeline: list[MatTimelinePoint] = []
    degradation_log: list[dict[str, Any]] = []
    next_sample = 0.0

    for step in range(n_steps + 1):
        elapsed = step * dt
        now = start + timedelta(seconds=elapsed)

        hotspot = dm.build_hotspot(
            config, elapsed_s=elapsed, grid=grid, land_mask=land_mask, elements=elements
        )
        forcing = dm.forcing_at(config.forcing, grid, land_mask, elapsed, start)

        tiles, fired = apply_degradation_events(
            tiles, config.degradation.events, elapsed, elapsed + dt
        )
        tiles = list(tiles)
        if fired:
            degradation_log.extend(fired)

        exchanges = ss.build_seabed_exchange(field_state, tiles, hotspot, forcing, dt)
        by_tile = {exchange.tile_id: exchange for exchange in exchanges}

        layer_steps: list[LayerStep] = []
        new_tiles: list[MatTileState] = []
        for tile in tiles:
            exchange = by_tile.get(tile.tile_id)
            if exchange is None:
                new_tiles.append(tile)
                continue
            layer_step = advance_reactive_layer(tile, exchange, materials, dt)
            layer_steps.append(layer_step)
            advanced = grow_fouling(
                layer_step.new_state, config.degradation.fouling_growth_per_s, dt
            )
            advanced = grow_burial(
                advanced, config.degradation.burial_growth_m_per_s, dt
            )
            new_tiles.append(advanced)

            area = tile.geometry.footprint_area_m2
            for element in elements:
                entered[element] += (
                    float(layer_step.flux_in_kg_per_m2_per_s.get(element, 0.0))
                    * area
                    * dt
                )
                left[element] += (
                    float(layer_step.flux_out_kg_per_m2_per_s.get(element, 0.0))
                    * area
                    * dt
                )
                retained_delta[element] += (
                    layer_step.retained_delta_kg_per_m2.get(element, 0.0) * area
                )
                correction[element] += float(
                    layer_step.diagnostics.get("clip_correction_kg_per_m2", {}).get(
                        element, 0.0
                    )
                    if isinstance(layer_step.diagnostics.get("clip_correction_kg_per_m2"), dict)
                    else 0.0
                ) * area
        tiles = new_tiles

        hotspot_area = dm.hotspot_area_m2(grid, hotspot)
        for element in elements:
            bare = hotspot.bare_flux_kg_per_m2_per_s.get(element, 0.0)
            hotspot_released[element] += bare * hotspot_area * dt

        if elapsed >= next_sample or step == n_steps:
            timeline.append(
                _sample_point(elapsed, now, tiles, layer_steps, hotspot, materials, elements)
            )
            next_sample = elapsed + sample_every_s

        for year in want_years:
            if year not in captured and elapsed >= year * _SECONDS_PER_YEAR - 0.5 * dt:
                captured[year] = [replace(tile) for tile in tiles]

        if progress and step % max(1, n_steps // 10) == 0:
            print(f"  mat timeline {100.0 * step / max(1, n_steps):5.1f} %")

    for year in want_years:
        captured.setdefault(year, [replace(tile) for tile in tiles])

    ledger = {
        element: MassLedger(
            element=element,
            # Inflow through the sediment face of every tile.
            released_from_sediment_kg=entered[element],
            # Still held in the active layer.
            retained_in_mat_kg=float(
                sum(tile.retained_kg(element) for tile in tiles)
            ),
            # Residual flux that left the layer into the overlying water.
            boundary_out_kg=left[element],
            numerical_correction_kg=correction[element],
        )
        for element in elements
    }
    return timeline, tiles, ledger, captured, hotspot_released


def _sample_point(
    elapsed: float,
    now,
    tiles: Sequence[MatTileState],
    layer_steps: Sequence[LayerStep],
    hotspot,
    materials: Mapping[str, Any],
    elements: Sequence[str],
) -> MatTimelinePoint:
    mean_out: dict[str, float] = {}
    mean_bare: dict[str, float] = {}
    attenuation: dict[str, float] = {}
    saturation: dict[str, float] = {}
    retained: dict[str, float] = {}

    for element in elements:
        bare = float(hotspot.bare_flux_kg_per_m2_per_s.get(element, 0.0))
        outs = [
            float(step.flux_out_kg_per_m2_per_s.get(element, 0.0))
            for step in layer_steps
        ]
        out = _mean_over_tiles(outs)
        mean_out[element] = out
        mean_bare[element] = bare
        attenuation[element] = (1.0 - out / bare) if bare > 0.0 else float("nan")
        params = materials.get(element)
        saturation[element] = (
            _mean_over_tiles([tile.saturation_fraction(params) for tile in tiles])
            if params is not None
            else 0.0
        )
        retained[element] = float(sum(tile.retained_kg(element) for tile in tiles))

    return MatTimelinePoint(
        elapsed_s=elapsed,
        elapsed_years=elapsed / _SECONDS_PER_YEAR,
        time_utc=now,
        mean_residual_flux=mean_out,
        mean_bare_flux=mean_bare,
        attenuation=attenuation,
        saturation=saturation,
        retained_kg=retained,
        mean_fouling=_mean_over_tiles([tile.fouling_index for tile in tiles]),
        mean_integrity=_mean_over_tiles([tile.integrity_index for tile in tiles]),
        mean_coverage=_mean_over_tiles([tile.coverage_fraction for tile in tiles]),
        n_tiles_active=sum(1 for tile in tiles if tile.active and not tile.displaced),
    )


# ---------------------------------------------------------------------------
# Plume window
# ---------------------------------------------------------------------------

def run_plume_window(
    config: RunConfig,
    tiles: Sequence[MatTileState],
    elapsed_s: float,
    *,
    label: str = "",
) -> PlumeWindowResult:
    """Run the 2-D coastal model over a short window at one mat state.

    Runs twice under identical forcing: once with the mat in place, once with no
    mat at all, so the comparison is genuinely like for like.
    """
    elements = [element for element in config.elements]
    materials = build_material_map(config.mat)
    start = config.start_datetime

    bundle = dm.build_domain(config, elapsed_s=elapsed_s)
    grid, land_mask = bundle.grid, bundle.land_mask
    hotspot = dm.build_hotspot(
        config, elapsed_s=elapsed_s, grid=grid, land_mask=land_mask, elements=elements
    )

    dt = config.plume.dt_s
    n_steps = max(1, int(round(config.plume.window_s / dt)))

    results = {}
    for with_mat in (True, False):
        field_state = dm.initial_field_state(
            config, grid=grid, land_mask=land_mask, elements=elements
        )
        initial_state = field_state
        active_tiles = list(tiles) if with_mat else []
        transport_steps = []

        # The mat state is HELD FIXED across the window, which is the whole
        # point of running the two scales on separate clocks: a cap changes over
        # years, a plume equilibrates in hours. So the residual flux is computed
        # once, at this mat state, and reused for every transport step.
        now0 = start + timedelta(seconds=elapsed_s)
        forcing0 = dm.forcing_at(config.forcing, grid, land_mask, elapsed_s, start)
        if with_mat and active_tiles:
            exchanges = ss.build_seabed_exchange(
                field_state, active_tiles, hotspot, forcing0, config.dt_s
            )
            by_tile = {exchange.tile_id: exchange for exchange in exchanges}
            layer_steps = [
                advance_reactive_layer(tile, by_tile[tile.tile_id], materials, config.dt_s)
                for tile in active_tiles
                if tile.tile_id in by_tile
            ]
        else:
            layer_steps = []
        source = ss.residual_source_flux(grid, hotspot, active_tiles, layer_steps, now0)

        for step in range(n_steps):
            elapsed = elapsed_s + step * dt
            forcing = dm.forcing_at(config.forcing, grid, land_mask, elapsed, start)
            transport = fe.transport_step(field_state, forcing, source, dt)
            transport_steps.append(transport)
            field_state = transport.new_field

        # The WATER ledger accounts only for what entered the water during this
        # window. The mat's own inventory belongs to the mat ledger and is
        # accumulated over the whole timeline, not over three days; adding it
        # here would double-count it.
        ledger = {
            element: fe.accumulate_ledger(element, initial_state, transport_steps)
            for element in elements
        }
        results[with_mat] = (field_state, source, ledger)

    field_mat, source_mat, ledger_mat = results[True]
    field_bare, source_bare, ledger_bare = results[False]

    return PlumeWindowResult(
        elapsed_years=elapsed_s / _SECONDS_PER_YEAR,
        label=label or f"{elapsed_s / _SECONDS_PER_YEAR:.1f} yr",
        field_with_mat=field_mat,
        field_without_mat=field_bare,
        source_with_mat=source_mat,
        source_without_mat=source_bare,
        ledger_with_mat=ledger_mat,
        ledger_without_mat=ledger_bare,
        window_s=config.plume.window_s,
    )


def run_scenario(config: RunConfig, *, progress: bool = False) -> ScenarioResult:
    """Full scenario: the mat timeline plus a plume window at each sample year."""
    timeline, tiles, ledger, captured, hotspot_released = run_mat_timeline(
        config, progress=progress
    )

    windows: list[PlumeWindowResult] = []
    for year in sorted(captured):
        if progress:
            print(f"  plume window at {year:.1f} yr")
        windows.append(
            run_plume_window(
                config,
                captured[year],
                year * _SECONDS_PER_YEAR,
                label=f"{year:.1f} yr",
            )
        )

    return ScenarioResult(
        config=config,
        timeline=timeline,
        windows=windows,
        final_tiles=tiles,
        mat_ledger=ledger,
        hotspot_released_kg=hotspot_released,
    )
