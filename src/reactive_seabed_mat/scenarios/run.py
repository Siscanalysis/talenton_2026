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
from copy import deepcopy
from bisect import bisect_right
from datetime import timedelta
from typing import Any, Mapping, Sequence

import numpy as np

from ..coastal_transport import domain as dm
from ..coastal_transport import fipy_engine as fe
from ..coastal_transport import seabed_source as ss
from ..config import RunConfig
from ..contracts import (
    Element,
    EstimateSnapshot,
    FieldState,
    LayerStep,
    MassLedger,
    MatTileGeometry,
    MatTileState,
    ObservationRecord,
    OperatorKnownMat,
    Recommendation,
    SeabedSourceField,
    ServiceEvent,
)
from ..estimation import estimate_tiles
from ..maintenance import PolicyState, accepted_service_tiles, recommend
from ..observations.generator import ObservationGenerator, scene_from_layer_history
from ..observations.records import observations_available
from ..observations.qc import run_qc, apply_qc_flags
from ..reactive_layer import (
    RetrievedMediaLedger,
    advance_reactive_layer,
    apply_degradation_events,
    build_material_map,
    build_tile_states,
    grow_burial,
    grow_fouling,
    replace_tiles,
)

_SECONDS_PER_YEAR = 365.25 * 86400.0

__all__ = [
    "MatTimelinePoint",
    "MatTimelineResult",
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
    #: What this mat would attenuate with no chemical capacity left: the pure
    #: physical barrier.  The sorbent's contribution is the difference between
    #: ``attenuation`` and this, and reporting only the first would credit the
    #: chemistry with the geometry's work.
    barrier_attenuation: Mapping[str, float]
    saturation: Mapping[str, float]
    retained_kg: Mapping[str, float]
    mean_fouling: float
    mean_integrity: float
    mean_coverage: float
    n_tiles_active: int
    column_attenuation: Mapping[str, float] = field(default_factory=dict)
    event: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "elapsed_s": self.elapsed_s,
            "elapsed_years": self.elapsed_years,
            "time_utc": str(self.time_utc),
            "mean_residual_flux_kg_per_m2_per_s": dict(self.mean_residual_flux),
            "mean_bare_flux_kg_per_m2_per_s": dict(self.mean_bare_flux),
            "attenuation": dict(self.attenuation),
            "barrier_only_attenuation": dict(self.barrier_attenuation),
            "sorbent_contribution": {
                element: self.attenuation.get(element, float("nan"))
                - self.barrier_attenuation.get(element, float("nan"))
                for element in self.attenuation
            },
            "saturation_fraction": dict(self.saturation),
            "retained_kg": dict(self.retained_kg),
            "mean_fouling_index": self.mean_fouling,
            "mean_integrity_index": self.mean_integrity,
            "mean_coverage_fraction": self.mean_coverage,
            "n_tiles_active": self.n_tiles_active,
            "column_attenuation": dict(self.column_attenuation),
            "event": self.event,
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
    tiles: Sequence[MatTileState] = ()

    def peak_concentration(self, element: str, *, with_mat: bool = True) -> float:
        state = self.field_with_mat if with_mat else self.field_without_mat
        return float(np.max(state.concentration_kg_per_m3[element]))


@dataclass(frozen=True, slots=True)
class MatTimelineResult:
    """Everything the mat clock produced.

    A record rather than a tuple because the maintenance loop added four more
    outputs and a seven-tuple is not an interface.
    """

    timeline: Sequence[MatTimelinePoint]
    final_tiles: Sequence[MatTileState]
    mat_ledger: Mapping[str, MassLedger]
    captured_tiles: Mapping[float, Sequence[MatTileState]]
    hotspot_released_kg: Mapping[str, float]
    #: Every recommendation the policy made, in order. Empty under ``none``.
    recommendations: Sequence[Recommendation] = ()
    #: Service events a human accepted.  Always ``simulation_only``.
    service_events: Sequence[ServiceEvent] = ()
    #: Mass moved out of the active mat and into retrieved media.
    retrieved_kg: Mapping[str, float] = field(default_factory=dict)
    assumed_service_cost_eur: float = 0.0
    #: The last estimate per tile, for the report.  Estimated, never true.
    final_estimates: Mapping[str, EstimateSnapshot] = field(default_factory=dict)
    n_observations: int = 0
    hotspot_into_water_kg: Mapping[str, float] = field(default_factory=dict)
    observations: Sequence[ObservationRecord] = ()
    estimate_history: Sequence[EstimateSnapshot] = ()
    degradation_events: Sequence[Mapping[str, Any]] = ()

    def __iter__(self):
        """Backwards compatibility with the original five-tuple return."""
        return iter(
            (
                self.timeline,
                self.final_tiles,
                self.mat_ledger,
                self.captured_tiles,
                self.hotspot_released_kg,
            )
        )


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
    #: The maintenance record for this run: recommendations, accepted service
    #: events and the retrieved-media totals.  ``None`` only if the timeline was
    #: built by an older caller.
    maintenance: "MatTimelineResult | None" = None
    checks: Sequence[Any] = ()
    hotspot_into_water_kg: Mapping[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Mat timeline
# ---------------------------------------------------------------------------

def _mean_over_tiles(values: Sequence[float]) -> float:
    return float(np.mean(values)) if len(values) else 0.0


def _hotspot_weights(grid, hotspot, tiles):
    """Exact footprint fractions on the same wet-cell hotspot as the maps."""
    mask = np.zeros((grid.ny, grid.nx), dtype=float)
    mask.reshape(-1)[list(hotspot.cell_indices)] = 1.0
    return {tile.tile_id: float(np.sum(ss.cell_area_weights(grid, tile.geometry) * mask)
                               / np.sum(mask)) for tile in tiles}


def _layer_steps(config, field_state, tiles, hotspot, forcing, materials, dt_s):
    """Advance distinct column states once, preserving each tile's identity.

    Reuse is local to this call and requires exact profile bytes and every
    input used by ``advance_reactive_layer``. No quantisation or approximate
    matching is used. Geometry position, media identity and installation date
    do not enter the column equations and are retained from the target tile.
    Returned mutable arrays and diagnostics remain independent per tile.
    """
    exchanges = ss.build_seabed_exchange(
        field_state, tiles, hotspot, forcing, max(dt_s, config.dt_s))
    by_tile = {exchange.tile_id: replace(exchange, environment={
        **exchange.environment,
        "burial_resistance_s_per_m": config.degradation.burial_resistance_s_per_m,
        "fouling_bypass_coupling": config.degradation.fouling_bypass_coupling,
    }) for exchange in exchanges}
    environment_keys = ("burial_resistance_s_per_m", "fouling_bypass_coupling",
                        "fouling_growth_per_s", "burial_growth_m_per_s")

    def profiles_key(profiles):
        return tuple((name, value.shape, value.dtype.str, value.tobytes())
                     for name, array in sorted(profiles.items())
                     for value in (np.asarray(array),))

    memo, steps = {}, []
    for tile in tiles:
        exchange = by_tile.get(tile.tile_id)
        if exchange is None:
            continue
        key = (replace(tile.geometry, x_m=0.0, y_m=0.0),
               tile.fouling_index, tile.integrity_index, tile.burial_depth_m,
               tile.displacement_m, tile.displaced, tile.active, tile.n_nodes,
               profiles_key(tile.porewater_kg_per_m3), profiles_key(tile.sorbed_kg_per_kg),
               tuple(sorted(exchange.sediment_porewater_kg_per_m3.items())),
               tuple(sorted(exchange.bottom_water_kg_per_m3.items())),
               tuple(sorted(exchange.bare_flux_kg_per_m2_per_s.items())),
               exchange.seepage_velocity_m_per_s, exchange.film_transfer_m_per_s,
               exchange.driving_is_measured,
               tuple((name, exchange.environment.get(name)) for name in environment_keys))
        prototype = memo.get(key)
        if prototype is None:
            step = advance_reactive_layer(tile, exchange, materials, dt_s)
            memo[key] = step
        else:
            updated = prototype.new_state
            state = replace(tile,
                porewater_kg_per_m3={name: array.copy() for name, array in updated.porewater_kg_per_m3.items()},
                sorbed_kg_per_kg={name: array.copy() for name, array in updated.sorbed_kg_per_kg.items()},
                fouling_index=updated.fouling_index, burial_depth_m=updated.burial_depth_m)
            diagnostics = deepcopy(prototype.diagnostics)
            diagnostics.update(tile_id=tile.tile_id, media_id=tile.media_id, time_utc=exchange.time_utc)
            step = replace(prototype, new_state=state, exchange=exchange,
                flux_in_kg_per_m2_per_s=dict(prototype.flux_in_kg_per_m2_per_s),
                flux_out_kg_per_m2_per_s=dict(prototype.flux_out_kg_per_m2_per_s),
                retained_delta_kg_per_m2=dict(prototype.retained_delta_kg_per_m2),
                released_kg_per_m2=dict(prototype.released_kg_per_m2), diagnostics=diagnostics)
        steps.append(step)
    return steps


def run_mat_timeline(config: RunConfig, *, sample_every_s: float | None = None,
                     progress: bool = False) -> MatTimelineResult:
    """Integrate exactly [0, T], resolving source, damage and decision boundaries.

    Samples at t=0 describe the commissioned state. Observations have one global
    campaign clock and seed; only arrived, QC-screened records reach decisions.
    The full-footprint column ledger and the area-mixed hotspot emission are
    separate diagnostics, not a claimed globally coupled sediment mass budget.
    """
    materials = build_material_map(config.mat)
    elements = list(config.elements)
    start, duration, dt = config.start_datetime, config.duration_s, config.dt_s
    if dt <= 0 or duration < 0 or config.policy.decision_period_s <= 0:
        raise ValueError("duration must be nonnegative and time steps positive")
    bundle = dm.build_domain(config, elapsed_s=0.0)
    grid, land_mask, field_state = bundle.grid, bundle.land_mask, bundle.field_state
    tiles = list(build_tile_states(config.mat, start, materials,
                 hotspot=config.hotspot, elements=elements)) if config.policy.kind != "none" else []
    deployed = bool(tiles)
    known = _operator_known_mat(config, tiles, grid) if deployed else None
    sample_every_s = sample_every_s or max(dt, duration / 240.0)
    want_years = sorted({float(y) for y in config.plume.sample_years
                         if 0 <= float(y) * _SECONDS_PER_YEAR <= duration}
                        | {duration / _SECONDS_PER_YEAR})
    capture_times = {year * _SECONDS_PER_YEAR for year in want_years}
    decision_times = set(float(t) for t in np.arange(
        config.policy.decision_period_s, duration + 1e-7, config.policy.decision_period_s))
    source_times = {float(entry.start_s) for entry in config.hotspot.schedule}
    event_times = {float(event.start_s) for event in config.degradation.events}
    boundaries = sorted({0.0, duration} | {float(t) for t in np.arange(dt, duration, dt)}
                        | {t for t in decision_times | source_times | event_times if 0 <= t <= duration}
                        | {year * _SECONDS_PER_YEAR for year in want_years})
    hotspot0 = dm.build_hotspot(config, elapsed_s=0, grid=grid,
                               land_mask=land_mask, elements=elements)
    weights = _hotspot_weights(grid, hotspot0, tiles)
    hotspot_area = dm.hotspot_area_m2(grid, hotspot0)
    zero = lambda: {element: 0.0 for element in elements}
    entered, left, correction = zero(), zero(), zero()
    hotspot_released, into_water = zero(), zero()
    initial_inventory = {e: sum(tile.retained_kg(e) for tile in tiles) for e in elements}
    timeline, captured, degradation_log = [], {}, []
    policy_state, media_ledger = PolicyState(), RetrievedMediaLedger()
    all_records, recommendations, service_events, estimate_history = [], [], [], []
    estimates, history = {}, {}
    present = {tile.tile_id for tile in tiles}
    observation_config = replace(config.observations, stations=tuple(
        station for station in config.observations.stations
        if station.tile_id is None or station.tile_id in present))
    generator = ObservationGenerator(observation_config, seed=config.seed, start_utc=start)
    observed_until, next_sample, previous = 0.0, 0.0, 0.0

    def sample(elapsed, hotspot, steps, event=""):
        return _sample_point(elapsed, start + timedelta(seconds=elapsed), tiles,
            steps, hotspot, materials, elements, weights=weights,
            fouling_bypass_coupling=config.degradation.fouling_bypass_coupling, event=event)

    for index, elapsed in enumerate(boundaries):
        now = start + timedelta(seconds=elapsed)
        if index:
            interval = elapsed - previous
            prior_hotspot = dm.build_hotspot(config, elapsed_s=previous, grid=grid,
                                            land_mask=land_mask, elements=elements)
            forcing = dm.forcing_at(config.forcing, grid, land_mask, previous, start)
            steps = _layer_steps(config, field_state, tiles, prior_hotspot, forcing, materials, interval)
            # Implicit column flux with the condition used during this interval.
            interval_sample = sample(elapsed, prior_hotspot, steps)
            for e in elements:
                hotspot_released[e] += prior_hotspot.bare_flux_kg_per_m2_per_s[e] * hotspot_area * interval
                into_water[e] += interval_sample.mean_residual_flux[e] * hotspot_area * interval
            advanced = {step.new_state.tile_id: step.new_state for step in steps}
            for step in steps:
                area = step.new_state.geometry.footprint_area_m2
                for e in elements:
                    entered[e] += step.flux_in_kg_per_m2_per_s.get(e, 0.0) * area * interval
                    left[e] += step.flux_out_kg_per_m2_per_s.get(e, 0.0) * area * interval
                    correction[e] += step.diagnostics.get("clip_correction_kg_per_m2", {}).get(e, 0.0) * area
            tiles = [grow_burial(grow_fouling(advanced.get(tile.tile_id, tile),
                        config.degradation.fouling_growth_per_s, interval),
                        config.degradation.burial_growth_m_per_s, interval) for tile in tiles]
        hotspot = dm.build_hotspot(config, elapsed_s=elapsed, grid=grid,
                                   land_mask=land_mask, elements=elements)
        forcing = dm.forcing_at(config.forcing, grid, land_mask, elapsed, start)
        if elapsed > 0 and elapsed in source_times:
            before_source = dm.build_hotspot(config, elapsed_s=np.nextafter(elapsed, -np.inf),
                grid=grid, land_mask=land_mask, elements=elements)
            before_steps = _layer_steps(config, field_state, tiles, before_source,
                                        forcing, materials, 0.0)
            timeline.append(sample(elapsed, before_source, before_steps, "before source change"))
        steps = _layer_steps(config, field_state, tiles, hotspot, forcing, materials, 0.0)
        changed = elapsed in event_times and deployed
        if changed:
            timeline.append(sample(elapsed, hotspot, steps, "before degradation"))
            tiles, fired = apply_degradation_events(tiles, config.degradation.events,
                                                    elapsed, np.nextafter(elapsed, np.inf))
            tiles = list(tiles)
            degradation_log.extend(fired)
            steps = _layer_steps(config, field_state, tiles, hotspot, forcing, materials, 0.0)
        for step in steps:
            history.setdefault(step.new_state.tile_id, []).append((now, step))
        if deployed and (elapsed in decision_times or elapsed == duration):
            all_records.extend(generator.generate_window(scene_from_layer_history(history),
                observed_until, elapsed, include_environmental=False, include_dgt=True))
            observed_until = elapsed
            # Keep a predecessor and enough history for a campaign whose
            # exposure straddles the next decision boundary. This bounds memory
            # without truncating any chamber/DGT integration interval.
            lookback = max(observation_config.porewater_sample_period_s,
                observation_config.chamber_deployment_period_s,
                observation_config.dgt_deployment_period_s,
                observation_config.bottom_water_probe_period_s,
                observation_config.survey_period_s,
                observation_config.environmental_period_s) + max(
                    observation_config.dgt_exposure_s, 86400.0)
            cutoff = now - timedelta(seconds=lookback)
            for tile_id, samples in history.items():
                keep = max(0, bisect_right(samples, cutoff, key=lambda item: item[0]) - 1)
                history[tile_id] = samples[keep:]
            visible = list(observations_available(all_records, now))
            qc = run_qc(visible, now_utc=now)
            estimates = estimate_tiles(apply_qc_flags(visible, qc), known, config, now)
            estimate_history.extend(estimates.values())
            if elapsed in decision_times:
                batch = recommend(estimates, known, config, now, elapsed, policy_state)
                recommendations.extend(batch)
                accepted = accepted_service_tiles(batch)
                if accepted:
                    timeline.append(sample(elapsed, hotspot, steps, "before service"))
                    tiles, event = replace_tiles(tiles, accepted, now, ledger=media_ledger,
                        costs=config.costs, triggered_by_recommendation_id=batch[0].recommendation_id)
                    tiles = list(tiles)
                    service_events.append(event)
                    policy_state.last_service_s = elapsed
                    policy_state.accepted_events.append(event.event_id)
                    known = replace(known, accepted_service_events=tuple(service_events))
                    steps = _layer_steps(config, field_state, tiles, hotspot, forcing, materials, 0.0)
                    for step in steps:
                        history.setdefault(step.new_state.tile_id, []).append((now, step))
                    changed = True
        if elapsed >= next_sample or elapsed in capture_times or changed or elapsed in source_times:
            timeline.append(sample(elapsed, hotspot, steps,
                                   "after event/service" if changed else
                                   "after source change" if elapsed > 0 and elapsed in source_times else ""))
            next_sample = elapsed + sample_every_s
        for year in want_years:
            if abs(elapsed - year * _SECONDS_PER_YEAR) < 1e-6:
                captured[year] = list(tiles)
        previous = elapsed
        if progress and index % max(1, len(boundaries) // 10) == 0:
            print(f"  mat timeline {100 * elapsed / max(duration, 1):5.1f} %", flush=True)
    ledger = {e: MassLedger(element=e, released_from_sediment_kg=entered[e],
        boundary_in_kg=initial_inventory[e],
        retained_in_mat_kg=sum(tile.retained_kg(e) for tile in tiles),
        retained_in_retrieved_media_kg=media_ledger.total_kg(e),
        boundary_out_kg=left[e], numerical_correction_kg=correction[e]) for e in elements}
    return MatTimelineResult(timeline=timeline, final_tiles=tiles, mat_ledger=ledger,
        captured_tiles=captured, hotspot_released_kg=hotspot_released,
        recommendations=tuple(recommendations), service_events=tuple(service_events),
        retrieved_kg=dict(media_ledger.totals_kg), assumed_service_cost_eur=media_ledger.assumed_cost_eur,
        final_estimates=estimates, n_observations=len(all_records),
        hotspot_into_water_kg=into_water, observations=tuple(all_records),
        estimate_history=tuple(estimate_history), degradation_events=tuple(degradation_log))


def _operator_known_mat(
    config: RunConfig, tiles: Sequence[MatTileState], grid
) -> OperatorKnownMat:
    """What the operator legitimately knows without opening the simulator.

    Design geometry, what was installed and when, and which service events were
    accepted. No tile inventory, no hidden condition, no truth of any kind.
    """
    if not tiles:
        raise ValueError(
            "an operator-known mat needs at least one deployed tile; the "
            "'none' policy has no mat and must not build one"
        )
    geometry = tiles[0].geometry
    covered = sum(tile.geometry.footprint_area_m2 for tile in tiles)
    return OperatorKnownMat(
        mat_id=f"MAT-{config.run_id}",
        tile_ids=tuple(tile.tile_id for tile in tiles),
        media_id=tiles[0].media_id if tiles else "media_A0",
        installed_at_utc=config.start_datetime,
        geometry=geometry,
        hotspot_area_m2=float(config.hotspot.width_m * config.hotspot.length_m),
        covered_area_m2=float(covered),
        accepted_service_events=(),
    )


def _sample_point(elapsed, now, tiles, layer_steps, hotspot, materials, elements,
                  *, weights, fouling_bypass_coupling=0.35, event="") -> MatTimelinePoint:
    by_tile = {step.new_state.tile_id: step for step in layer_steps}
    out, bare_map, attenuation, barrier_a, saturation, retained, column_a = {}, {}, {}, {}, {}, {}, {}
    for element in elements:
        bare = float(hotspot.bare_flux_kg_per_m2_per_s.get(element, 0.0))
        mixed, barrier, column_values = bare, bare, []
        for tile in tiles:
            step = by_tile.get(tile.tile_id)
            if step is None or tile.coverage_fraction <= 0:
                continue
            effective = weights[tile.tile_id] * tile.coverage_fraction * (1 - ss.bypass_fraction(
                tile, fouling_bypass_coupling=fouling_bypass_coupling))
            flux = float(step.flux_out_kg_per_m2_per_s.get(element, 0.0))
            barrier_flux = float(step.diagnostics.get("barrier_flux_kg_per_m2_per_s", {}).get(element, bare))
            mixed += effective * (flux - bare)
            barrier += effective * (barrier_flux - bare)
            column_values.append(flux)
        out[element], bare_map[element] = mixed, bare
        attenuation[element] = 1 - mixed / bare if bare > 0 else float("nan")
        barrier_a[element] = 1 - barrier / bare if bare > 0 else float("nan")
        column_a[element] = 1 - np.mean(column_values) / bare if bare > 0 and column_values else 0.0
        params = materials.get(element)
        saturation[element] = _mean_over_tiles([tile.saturation_fraction(params) for tile in tiles]) if params else 0.0
        retained[element] = sum(tile.retained_kg(element) for tile in tiles)
    return MatTimelinePoint(elapsed_s=elapsed, elapsed_years=elapsed / _SECONDS_PER_YEAR,
        time_utc=now, mean_residual_flux=out, mean_bare_flux=bare_map, attenuation=attenuation,
        barrier_attenuation=barrier_a, saturation=saturation, retained_kg=retained,
        mean_fouling=_mean_over_tiles([tile.fouling_index for tile in tiles]),
        mean_integrity=_mean_over_tiles([tile.integrity_index for tile in tiles]),
        mean_coverage=sum(weights[tile.tile_id] * tile.coverage_fraction for tile in tiles),
        n_tiles_active=sum(tile.active and not tile.displaced for tile in tiles),
        column_attenuation=column_a, event=event)


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
    n_steps = max(1, int(np.ceil(config.plume.window_s / dt)))

    results = {}
    for with_mat in (True, False):
        field_state = dm.initial_field_state(
            config, grid=grid, land_mask=land_mask, elements=elements
        )
        field_state = replace(field_state, time_utc=start + timedelta(seconds=elapsed_s))
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
            layer_steps = _layer_steps(config, field_state, active_tiles, hotspot,
                                       forcing0, materials, 0.0)
        else:
            layer_steps = []
        source = ss.residual_source_flux_detailed(grid, hotspot, active_tiles, layer_steps, now0,
            fouling_bypass_coupling=config.degradation.fouling_bypass_coupling)

        for step in range(n_steps):
            elapsed = elapsed_s + step * dt
            forcing = dm.forcing_at(config.forcing, grid, land_mask, elapsed, start)
            transport = fe.transport_step(field_state, forcing, source, min(dt, config.plume.window_s - step * dt))
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
        tiles=tuple(tiles),
    )


def run_scenario(config: RunConfig, *, progress: bool = False) -> ScenarioResult:
    """Full scenario: the mat timeline plus a plume window at each sample year."""
    mat = run_mat_timeline(config, progress=progress)

    windows: list[PlumeWindowResult] = []
    for year in sorted(mat.captured_tiles):
        if progress:
            print(f"  plume window at {year:.1f} yr")
        windows.append(
            run_plume_window(
                config,
                mat.captured_tiles[year],
                year * _SECONDS_PER_YEAR,
                label=f"{year:.1f} yr",
            )
        )

    return ScenarioResult(
        config=config,
        timeline=mat.timeline,
        windows=windows,
        final_tiles=mat.final_tiles,
        mat_ledger=mat.mat_ledger,
        hotspot_released_kg=mat.hotspot_released_kg,
        hotspot_into_water_kg=mat.hotspot_into_water_kg,
        maintenance=mat,
    )
