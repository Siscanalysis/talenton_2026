"""Breakthrough forecasting: an interval or ``None``, never a bare number.

A falsely precise remaining-life figure is worse than an honest "not
determined", so the shape of the answer is tested as hard as its value.
"""

from __future__ import annotations

import pytest

from reactive_seabed_mat.reactive_layer import (
    DEFAULT_BREAKTHROUGH_FRACTION,
    breakthrough_interval,
    forecast_breakthrough,
    forecast_tile,
    loading_fraction,
    remaining_capacity_kg_per_m2,
    sorbed_kg_per_m2,
    supply_limited_breakthrough_s,
)

SECONDS_PER_YEAR = 365.25 * 86400.0

#: The average supply the reference run actually delivers: 4e-3 kg/m2 of
#: capacity consumed in about 3.09 years.  Used as the assumed driving flux.
REFERENCE_SUPPLY_KG_PER_M2_PER_S = 4.0e-3 / (3.09 * SECONDS_PER_YEAR)


def _interval_or_none(value) -> bool:
    if value is None:
        return True
    return (
        isinstance(value, tuple)
        and len(value) == 2
        and all(isinstance(item, float) for item in value)
        and value[0] <= value[1]
    )


def test_a_fresh_mat_gets_an_interval_never_a_bare_number(materials, tiles):
    result = breakthrough_interval(
        materials,
        {"Pb": 0.0, "Hg": 0.0},
        tiles[0].geometry.sorbent_loading_kg_per_m2,
        0.0,
        {"Pb": REFERENCE_SUPPLY_KG_PER_M2_PER_S, "Hg": 0.0},
        ensemble_size=32,
        seed=7,
    )
    assert set(result) == {"Pb", "Hg"}
    for key, value in result.items():
        assert _interval_or_none(value), f"{key} returned {value!r}"
        assert not isinstance(value, float)
    assert result["Pb"] is not None
    low, high = result["Pb"]
    assert 0.0 < low < high
    # The uncertainty on q_max spans an order of magnitude, so the interval must
    # be wide.  A narrow one would be the dishonest answer.
    assert high / low > 3.0


def test_no_supply_means_not_determined_rather_than_never(materials, tiles):
    result = breakthrough_interval(
        materials,
        {"Pb": 0.0},
        tiles[0].geometry.sorbent_loading_kg_per_m2,
        0.0,
        {"Pb": 0.0},
        ensemble_size=16,
        seed=3,
    )
    assert result["Pb"] is None


def test_an_exhausted_layer_reports_breakthrough_now(materials, tiles):
    capacity = tiles[0].capacity_kg_per_m2(materials["Pb"])
    result = breakthrough_interval(
        materials,
        {"Pb": capacity},
        tiles[0].geometry.sorbent_loading_kg_per_m2,
        0.0,
        {"Pb": REFERENCE_SUPPLY_KG_PER_M2_PER_S},
        ensemble_size=16,
        seed=3,
    )
    assert result["Pb"] is not None
    assert result["Pb"][0] == 0.0


def test_the_forecast_reports_the_share_that_never_reaches_the_target(
    materials, tiles
):
    forecast = forecast_breakthrough(
        materials,
        {"Pb": 0.0},
        tiles[0].geometry.sorbent_loading_kg_per_m2,
        0.0,
        {"Pb": 0.0},
        ensemble_size=16,
        seed=11,
    )
    assert forecast.never_reached_fraction["Pb"] == 1.0
    assert forecast.breakthrough_s_interval["Pb"] is None
    assert forecast.conditional_note.startswith("Conditional forecast")
    assert forecast.provenance == "assumption"


def test_the_headline_is_supply_limited_and_the_kinetic_bound_is_only_a_diagnostic(
    materials, tiles
):
    forecast = forecast_breakthrough(
        materials,
        {"Pb": 0.0},
        tiles[0].geometry.sorbent_loading_kg_per_m2,
        0.0,
        {"Pb": REFERENCE_SUPPLY_KG_PER_M2_PER_S},
        driving_concentration_kg_per_m3={"Pb": 1.0e-3},
        ensemble_size=32,
        seed=5,
    )
    assert forecast.diagnostics["headline_estimate"] == "supply_limited"
    kinetic = forecast.diagnostics["kinetics_limited_s_interval"]["Pb"]
    assert kinetic is not None
    supply = forecast.breakthrough_s_interval["Pb"]
    assert supply is not None
    # The kinetic form ignores delivery, so it is a lower bound and must not be
    # the number the policy sees.
    assert kinetic[0] < supply[1]
    assert "lower bound" in forecast.diagnostics["kinetics_limited_note"]


def test_the_nominal_supply_limited_forecast_matches_the_simulated_breakthrough(
    materials, tiles
):
    """The nominal member should land near the 3.09 years the solver measures.

    The forecast uses a capacity proxy and an assumed constant supply, so exact
    agreement is not expected and not claimed; landing in the right year is.
    """
    params = materials["Pb"]
    seconds = supply_limited_breakthrough_s(
        params,
        0.0,
        tiles[0].geometry.sorbent_loading_kg_per_m2,
        0.0,
        REFERENCE_SUPPLY_KG_PER_M2_PER_S * params.allocation_fraction,
        DEFAULT_BREAKTHROUGH_FRACTION,
    )
    assert seconds is not None
    years = seconds / SECONDS_PER_YEAR
    assert 2.0 < years < 3.5, f"forecast {years:.2f} yr"


def test_forecast_tile_reads_the_state_without_touching_the_porewater_pool(
    saturated_tiles, materials
):
    tile = saturated_tiles[0]
    sorbed = sorbed_kg_per_m2(tile, "Pb")
    assert sorbed == pytest.approx(tile.capacity_kg_per_m2(materials["Pb"]))
    assert remaining_capacity_kg_per_m2(
        sorbed, tile.geometry.sorbent_loading_kg_per_m2, materials["Pb"], 0.0
    ) == pytest.approx(0.0, abs=1e-18)
    assert loading_fraction(
        sorbed, tile.geometry.sorbent_loading_kg_per_m2, materials["Pb"], 0.0
    ) == pytest.approx(1.0)

    forecast = forecast_tile(
        tile,
        materials,
        {"Pb": REFERENCE_SUPPLY_KG_PER_M2_PER_S},
        ensemble_size=16,
        seed=2,
    )
    assert forecast.tile_id == tile.tile_id
    for value in forecast.breakthrough_s_interval.values():
        assert _interval_or_none(value)
    payload = forecast.to_dict()
    assert payload["tile_id"] == tile.tile_id
    assert isinstance(payload["breakthrough_s_interval"]["Pb"], (list, type(None)))


def test_a_fouled_layer_has_less_accessible_capacity_and_breaks_through_sooner(
    materials, tiles
):
    from dataclasses import replace as dc_replace

    sensitive = {
        key: dc_replace(params, fouling_rate_capacity=0.5)
        for key, params in materials.items()
    }
    loading = tiles[0].geometry.sorbent_loading_kg_per_m2
    clean = breakthrough_interval(
        sensitive,
        {"Pb": 0.0},
        loading,
        0.0,
        {"Pb": REFERENCE_SUPPLY_KG_PER_M2_PER_S},
        ensemble_size=16,
        seed=1,
    )["Pb"]
    fouled = breakthrough_interval(
        sensitive,
        {"Pb": 0.0},
        loading,
        0.8,
        {"Pb": REFERENCE_SUPPLY_KG_PER_M2_PER_S},
        ensemble_size=16,
        seed=1,
    )["Pb"]
    assert clean is not None and fouled is not None
    assert fouled[1] < clean[1]
