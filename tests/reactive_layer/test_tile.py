"""Tile construction, the frozen advance, allocation and reporting."""

from __future__ import annotations

import inspect
from dataclasses import replace

import numpy as np
import pytest

from reactive_seabed_mat.config import MatLayoutConfig
from reactive_seabed_mat.contracts import LayerStep, MatTileState
from reactive_seabed_mat.reactive_layer import (
    advance_reactive_layer,
    bare_flux_from_exchange,
    build_material_map,
    build_tile_states,
    ensemble_flux_interval,
    flux_budget,
    release_from_damage,
    scripted_exchange,
    sorbed_kg_per_m2,
    tile_id_for,
    tile_summary,
    validate_allocation,
)

DT_S = 6.0 * 3600.0


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def test_tile_grid_ids_and_geometry(mat_config, hotspot_config, tiles):
    assert len(tiles) == mat_config.n_tiles == 9
    assert [tile.tile_id for tile in tiles[:3]] == [
        "tile_0_0",
        "tile_1_0",
        "tile_2_0",
    ]
    assert tile_id_for(2, 2) == "tile_2_2"
    # The scenarios in the registry name these identifiers directly.
    ids = {tile.tile_id for tile in tiles}
    assert {"tile_2_0", "tile_0_2", "tile_1_1", "tile_2_2"} <= ids

    covered = sum(tile.geometry.footprint_area_m2 for tile in tiles)
    assert covered == pytest.approx(
        mat_config.coverage_fraction * hotspot_config.area_m2
    )
    for tile in tiles:
        assert tile.geometry.thickness_m == mat_config.thickness_m
        assert tile.n_nodes == mat_config.n_layer_nodes
        assert tile.dz_m() == pytest.approx(
            mat_config.thickness_m / mat_config.n_layer_nodes
        )
        assert tile.coverage_fraction == 1.0
        assert tile.service_count == 0


def test_a_partly_covering_mat_covers_less(hotspot_config, start_utc):
    config = MatLayoutConfig(coverage_fraction=0.45, tiles_x=2, tiles_y=2)
    materials = build_material_map(config)
    tiles = build_tile_states(
        config, start_utc, materials, hotspot=hotspot_config
    )
    covered = sum(tile.geometry.footprint_area_m2 for tile in tiles)
    assert covered == pytest.approx(0.45 * hotspot_config.area_m2)
    assert len(tiles) == 4


def test_preload_lays_a_uniform_profile_and_refuses_to_exceed_capacity(
    hotspot_config, start_utc
):
    capacity = 400.0 * 0.010 * 0.6 * 1.0e-3
    config = MatLayoutConfig(preload_kg_per_m2={"Pb": 0.5 * capacity})
    materials = build_material_map(config)
    tiles = build_tile_states(config, start_utc, materials, hotspot=hotspot_config)
    tile = tiles[0]
    assert sorbed_kg_per_m2(tile, "Pb") == pytest.approx(0.5 * capacity)
    assert tile.saturation_fraction(materials["Pb"]) == pytest.approx(0.5)
    assert np.allclose(
        tile.sorbed_kg_per_kg["Pb"], tile.sorbed_kg_per_kg["Pb"][0]
    )
    assert np.all(tile.porewater_kg_per_m3["Pb"] == 0.0)

    too_much = MatLayoutConfig(preload_kg_per_m2={"Pb": 2.0 * capacity})
    with pytest.raises(ValueError, match="exceeds the allocated capacity"):
        build_tile_states(
            too_much, start_utc, build_material_map(too_much), hotspot=hotspot_config
        )


def test_a_naive_installation_time_is_refused(mat_config, materials):
    from datetime import datetime

    with pytest.raises(ValueError, match="timezone-aware"):
        build_tile_states(mat_config, datetime(2026, 9, 8), materials)


# ---------------------------------------------------------------------------
# Allocation between Pb and Hg
# ---------------------------------------------------------------------------

def test_allocations_sum_to_at_most_one(materials):
    total = validate_allocation(materials)
    assert total == pytest.approx(1.0)
    assert total <= 1.0 + 1e-12


def test_over_allocation_is_refused(materials):
    greedy = {
        key: replace(params, allocation_fraction=0.8)
        for key, params in materials.items()
    }
    with pytest.raises(ValueError, match="allocation fractions sum"):
        validate_allocation(greedy)


def test_the_two_elements_have_independent_capacities(tiles, materials, start_utc):
    tile = tiles[0]
    pb_capacity = tile.capacity_kg_per_m2(materials["Pb"])
    hg_capacity = tile.capacity_kg_per_m2(materials["Hg"])
    loading = tile.geometry.sorbent_loading_kg_per_m2
    # Read the capacities from the material parameters rather than hard-coding
    # them: the keratin values are literature-derated and are expected to move
    # as the material evidence improves (docs/MATERIAL_KERATIN.md).
    for element in ("Pb", "Hg"):
        params = materials[element]
        expected = loading * params.allocation_fraction * params.q_max_kg_per_kg
        assert tile.capacity_kg_per_m2(params) == pytest.approx(expected)
    assert pb_capacity != hg_capacity

    # Loading one element must not touch the other's inventory or capacity.
    state = tile
    for _ in range(20):
        exchange = scripted_exchange(
            state, start_utc, DT_S, {"Pb": 1.0e-3, "Hg": 0.0}
        )
        state = advance_reactive_layer(state, exchange, materials, DT_S).new_state
    assert sorbed_kg_per_m2(state, "Pb") > 0.0
    assert sorbed_kg_per_m2(state, "Hg") == 0.0
    assert state.capacity_kg_per_m2(materials["Hg"]) == hg_capacity


# ---------------------------------------------------------------------------
# The frozen advance
# ---------------------------------------------------------------------------

def test_advance_reactive_layer_matches_the_frozen_signature():
    from reactive_seabed_mat.contracts import AdvanceReactiveLayer

    expected = list(
        inspect.signature(AdvanceReactiveLayer.__call__).parameters
    )[1:]
    actual = list(inspect.signature(advance_reactive_layer).parameters)
    assert actual == expected, (
        f"signature drifted from the frozen contract: {actual} vs {expected}"
    )


def test_the_step_echoes_back_the_exchange_it_answered(tiles, materials, start_utc):
    tile = tiles[0]
    exchange = scripted_exchange(tile, start_utc, DT_S, {"Pb": 1.0e-3})
    step = advance_reactive_layer(tile, exchange, materials, DT_S)
    assert isinstance(step, LayerStep)
    assert step.exchange is exchange
    assert isinstance(step.new_state, MatTileState)
    assert step.new_state.tile_id == tile.tile_id


def test_an_exchange_for_another_tile_is_refused(tiles, materials, start_utc):
    exchange = scripted_exchange(tiles[1], start_utc, DT_S, {"Pb": 1.0e-3})
    with pytest.raises(ValueError, match="exchange is for tile"):
        advance_reactive_layer(tiles[0], exchange, materials, DT_S)


def test_a_negative_time_step_is_refused(tiles, materials, start_utc):
    exchange = scripted_exchange(tiles[0], start_utc, DT_S, {"Pb": 1.0e-3})
    with pytest.raises(ValueError, match="non-negative"):
        advance_reactive_layer(tiles[0], exchange, materials, -1.0)


def test_the_step_conserves_mass_per_element(tiles, materials, start_utc):
    state = tiles[0]
    for _ in range(50):
        exchange = scripted_exchange(
            state, start_utc, DT_S, {"Pb": 1.0e-3, "Hg": 8.0e-6}
        )
        step = advance_reactive_layer(state, exchange, materials, DT_S)
        for key in ("Pb", "Hg"):
            expected = (
                step.flux_in_kg_per_m2_per_s[key]
                - step.flux_out_kg_per_m2_per_s[key]
            ) * DT_S
            assert step.retained_delta_kg_per_m2[key] == pytest.approx(
                expected, rel=1e-12, abs=1e-20
            )
            assert step.released_kg_per_m2[key] == 0.0
        state = step.new_state


def test_the_attenuation_helper_needs_a_bare_flux(tiles, materials, start_utc):
    tile = tiles[0]
    exchange = scripted_exchange(tile, start_utc, DT_S, {"Pb": 1.0e-3})
    step = advance_reactive_layer(tile, exchange, materials, DT_S)
    bare, source = bare_flux_from_exchange(exchange, "Pb")
    assert source == "declared_by_exchange"
    assert step.attenuation("Pb", bare) == pytest.approx(
        1.0 - step.flux_out_kg_per_m2_per_s["Pb"] / bare
    )
    assert step.attenuation("Pb", 0.0) is None


def test_the_flux_budget_carries_the_barrier_floor(tiles, materials, start_utc):
    tile = tiles[0]
    exchange = scripted_exchange(tile, start_utc, DT_S, {"Pb": 1.0e-3})
    step = advance_reactive_layer(tile, exchange, materials, DT_S)
    budget = flux_budget(step, exchange, "Pb")
    assert budget.bare_flux_kg_per_m2_per_s > 0.0
    assert budget.barrier_flux_kg_per_m2_per_s > 0.0
    assert budget.attenuation is not None
    assert budget.barrier_attenuation is not None
    assert budget.chemical_attenuation_contribution == pytest.approx(
        budget.attenuation - budget.barrier_attenuation
    )
    assert "chemical" in budget.notes


def test_the_residual_flux_interval_is_an_interval_and_brackets_the_nominal(
    tiles, materials, start_utc
):
    state = tiles[0]
    for _ in range(60):
        exchange = scripted_exchange(state, start_utc, DT_S, {"Pb": 1.0e-3})
        state = advance_reactive_layer(state, exchange, materials, DT_S).new_state
    exchange = scripted_exchange(state, start_utc, DT_S, {"Pb": 1.0e-3})
    intervals = ensemble_flux_interval(
        state, exchange, materials, DT_S, ensemble_size=16, seed=4
    )
    interval = intervals["Pb"]
    low, high = interval.flux_out_interval
    assert low <= high
    assert interval.attenuation_interval is not None
    assert interval.attenuation_interval[0] <= interval.attenuation_interval[1]
    assert interval.ensemble_size == 16
    assert "conditional on the current profile" in interval.notes


# ---------------------------------------------------------------------------
# Explicit release
# ---------------------------------------------------------------------------

def test_release_from_damage_is_explicit_and_bounded(
    saturated_tiles, materials, start_utc
):
    tile = saturated_tiles[0]
    held = sorbed_kg_per_m2(tile, "Pb")
    exchange = scripted_exchange(tile, start_utc, DT_S, {"Pb": 1.0e-3})

    step = release_from_damage(
        tile, exchange, released_fraction_by_element={"Pb": 0.25}
    )
    assert step.released_kg_per_m2["Pb"] == pytest.approx(0.25 * held)
    assert sorbed_kg_per_m2(step.new_state, "Pb") == pytest.approx(0.75 * held)
    assert step.retained_delta_kg_per_m2["Pb"] == pytest.approx(-0.25 * held)

    over = release_from_damage(
        tile, exchange, released_kg_per_m2_by_element={"Pb": 10.0 * held}
    )
    assert over.released_kg_per_m2["Pb"] == pytest.approx(held)
    assert over.diagnostics["corrections"][0]["kind"] == (
        "release_clipped_to_sorbed_mass"
    )
    with pytest.raises(ValueError, match="exactly one of"):
        release_from_damage(tile, exchange)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def test_tile_summary_reports_the_four_modes_and_never_a_health_score(
    tiles, materials, start_utc
):
    tile = tiles[0]
    exchange = scripted_exchange(tile, start_utc, DT_S, {"Pb": 1.0e-3, "Hg": 8.0e-6})
    step = advance_reactive_layer(tile, exchange, materials, DT_S)
    summary = tile_summary(step.new_state, materials, layer_step=step)

    assert summary["tile_id"] == tile.tile_id
    assert set(summary["capacity_kg_per_m2"]) == {"Pb", "Hg"}
    assert "saturation" in summary["degradation"]
    assert "fouling" in summary["degradation"]
    assert "displacement" in summary["degradation"]
    assert "local_damage" in summary["degradation"]
    assert "health" not in summary
    assert summary["flux"]["Pb"]["bare_flux_kg_per_m2_per_s"] > 0.0
    assert summary["provenance"] == "synthetic_demo"


def test_diagnostics_record_every_number_the_frozen_signature_cannot_carry(
    tiles, materials, start_utc
):
    tile = tiles[0]
    exchange = scripted_exchange(
        tile,
        start_utc,
        DT_S,
        {"Pb": 1.0e-3},
        environment={
            "burial_resistance_s_per_m": 1.0e9,
            "fouling_bypass_coupling": 0.5,
            "fouling_growth_per_s": 5.0e-9,
            "burial_growth_m_per_s": 1.0e-9,
        },
    )
    step = advance_reactive_layer(tile, exchange, materials, DT_S)
    assert step.diagnostics["burial_resistance_s_per_m"] == 1.0e9
    assert step.diagnostics["fouling_bypass_coupling"] == 0.5
    assert step.diagnostics["fouling_growth_source"].endswith(
        "['fouling_growth_per_s']"
    )
    assert step.new_state.fouling_index > 0.0
    assert step.new_state.burial_depth_m > 0.0
    assert step.diagnostics["clip_correction_kg"] == {"Pb": 0.0, "Hg": 0.0}
    assert step.diagnostics["picard_converged"] is True

    # Without the growth rates the caller owns degradation, and the step says so.
    plain = scripted_exchange(tile, start_utc, DT_S, {"Pb": 1.0e-3})
    quiet = advance_reactive_layer(tile, plain, materials, DT_S)
    assert quiet.diagnostics["fouling_growth_source"] == (
        "not_applied_caller_owns_fouling"
    )
    assert quiet.new_state.fouling_index == tile.fouling_index
