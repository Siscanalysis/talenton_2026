"""Actual reactive-column integration, beyond the coastal stub contracts."""
from dataclasses import replace

import numpy as np
import pytest

from reactive_seabed_mat.config import default_run_config, DegradationEvent
from reactive_seabed_mat.scenarios.run import run_mat_timeline, run_plume_window


def short_config():
    config = default_run_config()
    return replace(config, duration_s=2.5 * config.dt_s,
        plume=replace(config.plume, sample_years=(0.0, 3.0), window_s=1250, dt_s=600),
        degradation=replace(config.degradation, fouling_growth_per_s=0.0))


def test_zero_is_unadvanced_and_final_time_is_exact():
    config = short_config()
    result = run_mat_timeline(config)
    assert result.timeline[0].elapsed_s == 0
    assert all(value == 0 for value in result.timeline[0].retained_kg.values())
    assert result.timeline[-1].elapsed_s == config.duration_s
    assert max(result.captured_tiles) == config.duration_years
    assert 3.0 not in result.captured_tiles
    for entry in result.mat_ledger.values():
        assert abs(entry.relative_imbalance) < 1e-9


def test_no_mat_integral_uses_exact_duration_without_an_extra_step():
    config = short_config()
    config = replace(config, policy=replace(config.policy, kind="none"))
    result = run_mat_timeline(config)
    for e in config.elements:
        expected = result.timeline[0].mean_bare_flux[e] * 6400 * config.duration_s
        assert result.hotspot_released_kg[e] == pytest.approx(expected)
        assert result.hotspot_into_water_kg[e] == pytest.approx(expected)


def test_timeline_flux_and_coverage_match_spatial_source():
    config = short_config()
    mat = run_mat_timeline(config)
    window = run_plume_window(config, mat.final_tiles, config.duration_s)
    point = mat.timeline[-1]
    assert point.mean_coverage == pytest.approx(config.mat.coverage_fraction)
    grid = window.field_with_mat.grid
    for e in config.elements:
        spatial_rate = np.sum(window.source_with_mat.flux_kg_per_m2_per_s[e]) * grid.dx_m * grid.dy_m
        assert spatial_rate == pytest.approx(point.mean_residual_flux[e] * 6400)
        assert window.ledger_with_mat[e].released_from_sediment_kg == pytest.approx(spatial_rate * 1250)
    assert window.tiles == tuple(mat.final_tiles)


def test_displacement_lowers_hotspot_attenuation_at_exact_event_time():
    config = short_config()
    event_time = config.dt_s * 1.25
    config = replace(config, degradation=replace(config.degradation, events=(
        DegradationEvent(event_time, "tile_2_0", "displacement", 1.0),)))
    result = run_mat_timeline(config)
    at_event = [p for p in result.timeline if p.elapsed_s == event_time]
    assert len(at_event) == 2
    assert at_event[1].attenuation["Pb"] < at_event[0].attenuation["Pb"]
    assert at_event[1].mean_coverage == pytest.approx(config.mat.coverage_fraction * 8 / 9)


def test_piecewise_source_integral_and_plot_jump_use_exact_change_time():
    config = short_config()
    change_time = 0.75 * config.dt_s
    initial = config.hotspot.schedule[0]
    changed = replace(initial, start_s=change_time,
                      porewater_kg_per_m3={e: 3*v for e,v in initial.porewater_kg_per_m3.items()})
    config = replace(config, policy=replace(config.policy, kind="none"),
                     hotspot=replace(config.hotspot, schedule=(initial, changed)))
    result = run_mat_timeline(config)
    points = [p for p in result.timeline if p.elapsed_s == change_time]
    assert len(points) == 2
    for e in config.elements:
        before, after = [p.mean_bare_flux[e] for p in points]
        assert after == pytest.approx(3 * before)
        assert result.hotspot_into_water_kg[e] == pytest.approx(
            6400 * (before * change_time + after * (config.duration_s - change_time)))


def test_preloaded_inventory_is_a_commissioning_input_not_created_mass():
    config = short_config()
    config = replace(config, mat=replace(config.mat, preload_kg_per_m2={"Pb": 1e-4}))
    result = run_mat_timeline(config)
    initial = result.timeline[0].retained_kg['Pb']
    assert initial == pytest.approx(0.64)
    assert result.mat_ledger['Pb'].boundary_in_kg == pytest.approx(initial)
    assert abs(result.mat_ledger['Pb'].relative_imbalance) < 1e-9
