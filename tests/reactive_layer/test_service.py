"""Replacement, partial replacement and the retrieved-media ledger.

MODEL_SPEC section 7: replacement moves the retained inventory of the replaced
tiles into the retrieved-media ledger and issues a new ``media_id``.  Capacity
resets, captured mass does not disappear, and nothing is returned to the sea.

The mat is modular, so the interesting case is **partial** replacement: two
tiles out of nine, with the other seven untouched.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from reactive_seabed_mat.config import CostConfig
from reactive_seabed_mat.reactive_layer import (
    MEDIA_DISPOSAL_NOTE,
    RetrievedMediaLedger,
    next_media_id,
    replace_media,
    replace_tiles,
    replacement_cost_eur,
)


def _load_tiles(tiles, sorbed_kg_per_kg=2.0e-4, porewater_kg_per_m3=1.0e-5):
    """Give every tile a distinguishable, non-zero inventory."""
    loaded = []
    for index, tile in enumerate(tiles):
        scale = 1.0 + index
        loaded.append(
            replace(
                tile,
                porewater_kg_per_m3={
                    key: np.full(tile.n_nodes, porewater_kg_per_m3 * scale)
                    for key in tile.porewater_kg_per_m3
                },
                sorbed_kg_per_kg={
                    key: np.full(tile.n_nodes, sorbed_kg_per_kg * scale)
                    for key in tile.sorbed_kg_per_kg
                },
            )
        )
    return tuple(loaded)


def test_media_id_succession_is_deterministic():
    assert next_media_id("media_A0") == "media_A1"
    assert next_media_id("media_A09") == "media_A10"
    assert next_media_id("media_A") == "media_A_r1"


def test_replacement_conserves_total_inventory_exactly(tiles, start_utc):
    tile = _load_tiles(tiles)[0]
    before = {key: tile.retained_kg(key) for key in tile.porewater_kg_per_m3}
    assert all(value > 0.0 for value in before.values())

    ledger = RetrievedMediaLedger()
    new_state, event = replace_media(tile, start_utc, ledger=ledger)

    for key, value in before.items():
        after = new_state.retained_kg(key) + ledger.total_kg(key)
        assert after == value, (
            f"{key}: {value!r} kg before, {after!r} kg after the replacement"
        )
        assert new_state.retained_kg(key) == 0.0
        assert event.retrieved_kg[key] == value

    assert new_state.media_id != tile.media_id
    assert new_state.service_count == tile.service_count + 1
    assert new_state.installed_at_utc == start_utc
    assert event.execution_mode == "simulation_only"
    assert tuple(event.tile_ids) == (tile.tile_id,)
    assert ledger.as_dict()["disposal_note"] == MEDIA_DISPOSAL_NOTE


def test_partial_replacement_of_two_tiles_out_of_nine(tiles, start_utc):
    loaded = _load_tiles(tiles)
    assert len(loaded) == 9
    targets = ("tile_1_0", "tile_0_2")
    expected = {}
    for key in loaded[0].porewater_kg_per_m3:
        expected[key] = sum(
            tile.retained_kg(key) for tile in loaded if tile.tile_id in targets
        )
    total_before = {
        key: sum(tile.retained_kg(key) for tile in loaded)
        for key in loaded[0].porewater_kg_per_m3
    }

    ledger = RetrievedMediaLedger()
    new_states, event = replace_tiles(loaded, targets, start_utc, ledger=ledger)

    assert len(new_states) == 9
    assert tuple(event.tile_ids) == targets
    assert event.kind == "partial_media_replacement"

    by_id_before = {tile.tile_id: tile for tile in loaded}
    for state in new_states:
        original = by_id_before[state.tile_id]
        if state.tile_id in targets:
            assert state.media_id != original.media_id
            assert state.service_count == original.service_count + 1
            for key in state.porewater_kg_per_m3:
                assert state.retained_kg(key) == 0.0
        else:
            assert state is original, (
                f"{state.tile_id} was not named but was replaced anyway"
            )

    for key, value in expected.items():
        assert ledger.total_kg(key) == value, (
            f"{key}: the ledger received {ledger.total_kg(key)!r} kg but exactly "
            f"{value!r} kg belonged to the two replaced tiles"
        )
        remaining = sum(state.retained_kg(key) for state in new_states)
        assert remaining + ledger.total_kg(key) == pytest.approx(
            total_before[key], rel=1e-15
        )


def test_replacement_resets_every_degradation_mode(tiles, start_utc):
    tile = replace(
        _load_tiles(tiles)[0],
        fouling_index=0.7,
        integrity_index=0.4,
        burial_depth_m=0.3,
        displacement_m=2.0,
        displaced=True,
    )
    new_state, _ = replace_media(tile, start_utc)
    assert new_state.fouling_index == 0.0
    assert new_state.integrity_index == 1.0
    assert new_state.burial_depth_m == 0.0
    assert new_state.displacement_m == 0.0
    assert new_state.displaced is False
    assert new_state.coverage_fraction == 1.0

    kept, _ = replace_media(tile, start_utc, reset_physical_condition=False)
    assert kept.fouling_index == 0.7
    assert kept.displaced is True


def test_replacing_an_unknown_tile_is_an_error(tiles, start_utc):
    with pytest.raises(KeyError, match="unknown tiles"):
        replace_tiles(tiles, ("tile_9_9",), start_utc)
    with pytest.raises(ValueError, match="at least one tile"):
        replace_tiles(tiles, (), start_utc)


def test_the_cost_breakdown_is_an_assumption_and_shows_its_parts(tiles, start_utc):
    costs = CostConfig()
    breakdown = replacement_cost_eur(
        costs, n_tiles=2, media_area_m2=100.0, retrieved_media_mass_kg=400.0
    )
    assert breakdown["vessel_visit_eur"] == costs.deployment_vessel_day_eur
    assert breakdown["tile_handling_eur"] == 2 * costs.tile_replacement_eur
    assert breakdown["new_media_eur"] == 100.0 * costs.mat_material_eur_per_m2
    assert (
        breakdown["used_media_handling_eur"]
        == 400.0 * costs.used_media_handling_eur_per_kg
    )
    assert breakdown["total_eur"] == pytest.approx(
        breakdown["vessel_visit_eur"]
        + breakdown["tile_handling_eur"]
        + breakdown["new_media_eur"]
        + breakdown["used_media_handling_eur"]
    )
    assert breakdown["provenance"] == "assumption"

    # One vessel visit services however many tiles are named, which is the whole
    # economic argument for partial replacement.
    ledger = RetrievedMediaLedger()
    replace_tiles(tiles, ("tile_0_0", "tile_1_1"), start_utc, ledger=ledger, costs=costs)
    assert ledger.assumed_cost_eur > 0.0
    assert ledger.as_dict()["cost_provenance"] == "assumption"


def test_the_ledger_refuses_a_negative_retrieved_mass(tiles, start_utc):
    from reactive_seabed_mat.contracts import ServiceEvent

    ledger = RetrievedMediaLedger()
    bad = ServiceEvent(
        event_id="SVC-bad",
        time_utc=start_utc,
        tile_ids=("tile_0_0",),
        kind="media_replacement",
        old_media_id="media_A0",
        new_media_id="media_A1",
        retrieved_kg={"Pb": -1.0},
    )
    with pytest.raises(ValueError, match="non-negative"):
        ledger.record(bad)
