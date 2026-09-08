"""The four degradation modes, and the two that can be misread as success.

MODEL_SPEC section 4.  Each mode is exercised on its own, because the whole
point of keeping them independent is that a symptom must not be attributed to
the wrong mechanism.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from conftest import PROBE_J_BARE, probe_column, run_column
from reactive_seabed_mat.config import DegradationEvent
from reactive_seabed_mat.contracts import AmbiguityFlag, DegradationMode
from reactive_seabed_mat.reactive_layer import (
    BURIAL_WARNING,
    advance_reactive_layer,
    apply_degradation_event,
    apply_degradation_events,
    buried_top_conductance,
    bypass_fraction,
    degradation_state,
    effective_d_eff_m2_per_s,
    effective_q_max_kg_per_kg,
    effective_rate_per_s,
    fouling_factors,
    grow_burial,
    grow_fouling,
    scripted_exchange,
    sorbed_kg_per_m2,
    tile_effective_flux_kg_per_m2_per_s,
    top_conductance,
)

SETTLE_YEARS = 0.6
DT_S = 6.0 * 3600.0


# ---------------------------------------------------------------------------
# Mode 2: fouling
# ---------------------------------------------------------------------------

def test_fouling_reduces_rate_capacity_and_diffusivity(materials):
    """All three factors fall, and none of them goes negative."""
    from reactive_seabed_mat.reactive_layer.material import scale_material

    # The configured media have gamma_c = 0, so a medium with a real capacity
    # sensitivity is built explicitly rather than pretending the default has one.
    params = replace(materials["Pb"], fouling_rate_capacity=0.4)
    clean = fouling_factors(params, 0.0)
    fouled = fouling_factors(params, 1.0)

    assert clean.kinetics_factor == 1.0
    assert clean.capacity_factor == 1.0
    assert clean.diffusivity_factor == 1.0
    assert fouled.kinetics_factor < clean.kinetics_factor
    assert fouled.capacity_factor < clean.capacity_factor
    assert fouled.diffusivity_factor < clean.diffusivity_factor
    assert effective_rate_per_s(params, 1.0) < params.k_rate_per_s
    assert effective_q_max_kg_per_kg(params, 1.0) < params.q_max_kg_per_kg
    assert effective_d_eff_m2_per_s(params, 1.0) < params.d_eff_m2_per_s
    assert scale_material(params, k_rate_scale=0.5).k_rate_per_s < params.k_rate_per_s


def test_fouling_clipping_is_recorded_never_silent(materials):
    params = replace(materials["Pb"], fouling_rate_kinetics=1.0)
    factors = fouling_factors(params, 1.5)
    assert factors.clipped is True
    assert factors.raw_fouling_fraction == 1.5
    assert factors.fouling_fraction == 1.0
    assert factors.as_dict()["clipped"] is True


def test_fouling_never_reduces_sorbed_mass(saturated_tiles, materials, start_utc):
    """A fouled layer holds what it held, at every fouling level.

    MODEL_SPEC section 4: if ``q_max_eff`` falls below the current load, further
    uptake stops and ``q`` is unchanged.  It is never deleted.
    """
    tile = saturated_tiles[0]
    fouled_materials = {
        key: replace(params, fouling_rate_capacity=0.4)
        for key, params in materials.items()
    }
    held_before = sorbed_kg_per_m2(tile, "Pb")
    assert held_before > 0.0

    for fouling in (0.0, 0.5, 1.0):
        state = replace(tile, fouling_index=fouling)
        for _ in range(40):
            exchange = scripted_exchange(
                state, start_utc, DT_S, {"Pb": 1.0e-3, "Hg": 8.0e-6}
            )
            state = advance_reactive_layer(
                state, exchange, fouled_materials, DT_S
            ).new_state
        held_after = sorbed_kg_per_m2(state, "Pb")
        assert held_after >= held_before - 1.0e-18, (
            f"fouling at f = {fouling} destroyed sorbed metal: "
            f"{held_before:.6e} -> {held_after:.6e} kg/m2"
        )


def test_fouling_lowers_the_flux_through_the_layer_but_is_never_a_benefit(
    saturated_tiles, materials, start_utc
):
    """The bypass coupling is what stops pore blockage looking like success.

    Through the layer alone, fouling *does* lower ``J_out``: that is the trap.
    What the tile's footprint actually emits rises monotonically with fouling,
    because the head across the layer pushes flow around the tile edge.
    """
    tile = saturated_tiles[0]
    through_layer: list[float] = []
    emitted: list[float] = []

    for fouling in (0.0, 0.25, 0.5, 0.75, 1.0):
        state = replace(tile, fouling_index=fouling)
        for _ in range(int(SETTLE_YEARS * 365.25 * 86400 / DT_S)):
            exchange = scripted_exchange(
                state, start_utc, DT_S, {"Pb": 1.0e-3, "Hg": 8.0e-6}
            )
            step = advance_reactive_layer(state, exchange, materials, DT_S)
            state = step.new_state
        bare = exchange.bare_flux_kg_per_m2_per_s["Pb"]
        through_layer.append(step.flux_out_kg_per_m2_per_s["Pb"] / bare)
        emitted.append(
            step.diagnostics["effective_flux_out_kg_per_m2_per_s"]["Pb"] / bare
        )

    assert through_layer[-1] < through_layer[0], (
        "pore blockage should lower the flux through the layer; if it does not, "
        "the trap this test exists for is not being modelled at all"
    )
    assert all(
        later > earlier for earlier, later in zip(emitted, emitted[1:])
    ), f"fouling looked like an improvement for the tile as a whole: {emitted}"
    assert emitted[-1] > 5.0 * emitted[0]


def test_bypass_fraction_is_edge_leakage_plus_coupled_fouling():
    bypass = bypass_fraction(0.02, 0.5, 0.35)
    assert bypass.value == pytest.approx(0.02 + 0.35 * 0.5)
    assert bypass.clipped is False
    clipped = bypass_fraction(0.9, 1.0, 0.35)
    assert clipped.value == 1.0
    assert clipped.clipped is True


def test_fouling_growth_leaves_the_inventory_alone(tiles):
    tile = tiles[0]
    grown = grow_fouling(tile, 5.0e-9, 86400.0 * 365.25)
    assert grown.fouling_index > tile.fouling_index
    assert grown.fouling_index <= 1.0
    for key in tile.sorbed_kg_per_kg:
        assert np.array_equal(grown.sorbed_kg_per_kg[key], tile.sorbed_kg_per_kg[key])


# ---------------------------------------------------------------------------
# Mode 3: burial and displacement
# ---------------------------------------------------------------------------

def test_burial_reduces_the_apparent_flux_which_is_the_dangerous_case():
    """**A falling flux under a buried tile is not success.**

    Burial adds diffusive resistance above the layer, so the residual flux drops
    while the mat may be doing nothing at all.  This test asserts the direction
    of the effect and records its size honestly: with the documented seepage
    velocity the layer's own resistance dominates, so half a metre of sediment
    buys only a few per cent.  With no seepage the same burial halves the flux.
    A monitoring system must not read either as an improvement.
    """
    params = probe_column()
    clean_conductance = top_conductance(params)

    unburied = run_column(
        params,
        years=SETTLE_YEARS,
        dt_s=DT_S,
        initial_sorbed_kg_per_kg=params.q_max_kg_per_kg,
    )
    buried = run_column(
        params,
        years=SETTLE_YEARS,
        dt_s=DT_S,
        initial_sorbed_kg_per_kg=params.q_max_kg_per_kg,
        top_conductance_m_per_s=buried_top_conductance(clean_conductance, 0.5),
    )
    reduction = 1.0 - buried["final_ratio"] / unburied["final_ratio"]
    assert buried["final_ratio"] < unburied["final_ratio"], (
        "burial did not reduce the apparent flux, so the ambiguity the "
        "estimator has to resolve is not being modelled"
    )
    assert 0.0 < reduction < 0.10, (
        f"burial changed the flux by {reduction:.4f}; with this seepage "
        "velocity the layer's own resistance dominates and only a few per cent "
        "is expected"
    )

    # The same mechanism with no advection, where it is large enough to fool a
    # monitoring programme outright.
    still = probe_column(seepage_velocity_m_per_s=0.0)
    still_clean = run_column(
        still,
        years=1.5,
        dt_s=DT_S,
        initial_sorbed_kg_per_kg=still.q_max_kg_per_kg,
    )
    still_buried = run_column(
        still,
        years=1.5,
        dt_s=DT_S,
        initial_sorbed_kg_per_kg=still.q_max_kg_per_kg,
        top_conductance_m_per_s=buried_top_conductance(top_conductance(still), 0.5),
    )
    big_reduction = 1.0 - still_buried["final_ratio"] / still_clean["final_ratio"]
    assert big_reduction > 0.3, (
        f"with no seepage, burial only reduced the flux by {big_reduction:.3f}"
    )


def test_buried_conductance_is_never_larger_than_the_clean_one():
    clean = 3.0e-7
    assert buried_top_conductance(clean, 0.0) == clean
    assert buried_top_conductance(clean, 0.05) < clean
    assert buried_top_conductance(clean, 5.0) < buried_top_conductance(clean, 0.05)
    assert buried_top_conductance(0.0, 1.0) == 0.0


def test_a_buried_tile_carries_the_burial_warning_and_the_ambiguity_flag(
    tiles, materials, start_utc
):
    buried = grow_burial(tiles[0], 1.0e-8, 365.25 * 86400.0)
    assert buried.burial_depth_m > 0.0
    state = degradation_state(buried, materials)
    assert state[DegradationMode.DISPLACEMENT.value]["warning"] == BURIAL_WARNING
    assert AmbiguityFlag.BURIAL.value in state["ambiguity_flags"]

    exchange = scripted_exchange(buried, start_utc, DT_S, {"Pb": 1.0e-3})
    step = advance_reactive_layer(buried, exchange, materials, DT_S)
    assert step.diagnostics["burial_warning"] == BURIAL_WARNING


def test_a_displaced_tile_has_coverage_fraction_zero_and_emits_the_bare_flux(
    tiles, materials, start_utc
):
    tile = tiles[0]
    event = DegradationEvent(
        start_s=0.0, tile_id=tile.tile_id, mode="displacement", magnitude=1.0
    )
    displaced, record = apply_degradation_event(tile, event)

    assert displaced.displaced is True
    assert displaced.coverage_fraction == 0.0
    assert record["coverage_fraction_after"] == 0.0

    exchange = scripted_exchange(displaced, start_utc, DT_S, {"Pb": 1.0e-3})
    step = advance_reactive_layer(displaced, exchange, materials, DT_S)
    bare = exchange.bare_flux_kg_per_m2_per_s["Pb"]
    emitted = step.diagnostics["effective_flux_out_kg_per_m2_per_s"]["Pb"]

    assert emitted == pytest.approx(bare, rel=1e-15), (
        "a seabed cell with no mat on it must emit exactly the bare flux"
    )
    assert "out_of_service" in step.diagnostics["layer_status"]
    # Nothing enters or leaves the layer, and its inventory is frozen.
    assert step.flux_in_kg_per_m2_per_s["Pb"] == 0.0
    assert step.retained_delta_kg_per_m2["Pb"] == 0.0
    assert np.array_equal(
        step.new_state.sorbed_kg_per_kg["Pb"], displaced.sorbed_kg_per_kg["Pb"]
    )


# ---------------------------------------------------------------------------
# Mode 4: local damage
# ---------------------------------------------------------------------------

def test_a_tile_with_integrity_065_passes_35_percent_of_the_bare_flux(
    tiles, materials, start_utc
):
    tile = replace(tiles[0], integrity_index=0.65)
    # Edge leakage is set aside so the 35 % is exactly the torn share; the
    # combined case is covered by tile_effective_flux_kg_per_m2_per_s below.
    tile = replace(
        tile, geometry=replace(tile.geometry, edge_leakage_fraction=0.0)
    )
    assert tile.coverage_fraction == 0.65

    exchange = scripted_exchange(
        tile,
        start_utc,
        DT_S,
        {"Pb": 1.0e-3},
        environment={"fouling_bypass_coupling": 0.0},
    )
    step = advance_reactive_layer(tile, exchange, materials, DT_S)
    bare = exchange.bare_flux_kg_per_m2_per_s["Pb"]
    flux_out = step.flux_out_kg_per_m2_per_s["Pb"]
    emitted = step.diagnostics["effective_flux_out_kg_per_m2_per_s"]["Pb"]

    assert emitted == pytest.approx(0.65 * flux_out + 0.35 * bare, rel=1e-15)
    # A fresh layer passes almost nothing, so the tear is nearly all of it.
    assert emitted == pytest.approx(0.35 * bare, rel=1e-6)


def test_effective_flux_combines_coverage_and_bypass():
    j_out, j_bare = 1.0e-11, 5.3e-10
    assert tile_effective_flux_kg_per_m2_per_s(j_out, j_bare, 1.0, 0.0) == j_out
    assert tile_effective_flux_kg_per_m2_per_s(j_out, j_bare, 0.0, 0.0) == j_bare
    combined = tile_effective_flux_kg_per_m2_per_s(j_out, j_bare, 0.8, 0.25)
    cover = 0.8 * 0.75
    assert combined == pytest.approx(cover * j_out + (1.0 - cover) * j_bare)


# ---------------------------------------------------------------------------
# The modes stay apart
# ---------------------------------------------------------------------------

def test_scheduled_events_apply_once_and_only_to_their_own_tile(tiles):
    events = (
        DegradationEvent(
            start_s=1.5 * 365.25 * 86400.0,
            tile_id="tile_2_0",
            mode="displacement",
            magnitude=1.0,
        ),
        DegradationEvent(
            start_s=2.2 * 365.25 * 86400.0,
            tile_id="tile_0_2",
            mode="local_damage",
            magnitude=0.35,
        ),
    )
    year = 365.25 * 86400.0
    states, applied = apply_degradation_events(tiles, events, 0.0, 2.0 * year)
    assert len(applied) == 1
    by_id = {state.tile_id: state for state in states}
    assert by_id["tile_2_0"].displaced is True
    assert by_id["tile_0_2"].integrity_index == 1.0
    assert all(
        state.fouling_index == 0.0 and state.burial_depth_m == 0.0
        for state in states
    ), "a displacement event touched another mode"

    states, applied = apply_degradation_events(states, events, 2.0 * year, 3.0 * year)
    assert len(applied) == 1
    by_id = {state.tile_id: state for state in states}
    assert by_id["tile_0_2"].integrity_index == pytest.approx(0.65)
    assert by_id["tile_2_0"].displaced is True
    assert by_id["tile_1_1"].integrity_index == 1.0


def test_saturation_cannot_be_scheduled_as_an_event(tiles):
    event = DegradationEvent(
        start_s=0.0, tile_id=tiles[0].tile_id, mode="saturation", magnitude=1.0
    )
    with pytest.raises(ValueError, match="not a schedulable event"):
        apply_degradation_event(tiles[0], event)


def test_an_event_for_an_unknown_tile_is_an_error(tiles):
    event = DegradationEvent(
        start_s=0.0, tile_id="tile_9_9", mode="fouling", magnitude=0.1
    )
    with pytest.raises(KeyError, match="unknown tile"):
        apply_degradation_events(tiles, (event,), 0.0, 1.0)


def test_all_four_modes_are_reported_side_by_side(tiles, materials):
    tile = replace(
        tiles[0], fouling_index=0.3, integrity_index=0.8, burial_depth_m=0.02
    )
    state = degradation_state(tile, materials)
    for mode in DegradationMode:
        assert mode.value in state, f"{mode.value} is missing from the report"
    assert state["modes_are_independent"] is True
    assert set(state["ambiguity_flags"]) >= {
        AmbiguityFlag.BURIAL.value,
        AmbiguityFlag.FOULING.value,
        AmbiguityFlag.TEAR_PUNCTURE.value,
    }
    assert PROBE_J_BARE > 0.0  # the reference the whole module is judged against
