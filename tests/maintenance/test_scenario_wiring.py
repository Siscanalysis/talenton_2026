"""The evidence loop against the real scenarios, not against fixtures.

These are the integration tests that catch what unit tests cannot: a station
list that names a tile a smaller mat never deployed, or a policy that changes
the run id but nothing else.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from reactive_seabed_mat.scenarios import registry
from reactive_seabed_mat.scenarios.run import run_mat_timeline

_SECONDS_PER_YEAR = 365.25 * 86400.0


def _short(name: str, years: float = 0.35):
    config = registry.build_scenario(name)
    return replace(config, duration_s=years * _SECONDS_PER_YEAR)


def test_the_undersized_mat_does_not_ask_for_a_tile_it_never_laid():
    """Regression: scenario F lays 2x2 tiles, the default chamber station names
    ``tile_2_2``, and the generator rightly refuses a tile that is not in the
    scene. It used to raise KeyError part-way through the run.

    Dropping the station is correct: you cannot put a benthic chamber on a tile
    that was never deployed. The undersized design is therefore also the least
    monitored one, which is a real consequence and not a workaround.
    """
    config = _short("undersized_mat")
    assert config.mat.tiles_x * config.mat.tiles_y == 4
    assert any(
        station.tile_id == "tile_2_2" for station in config.observations.stations
    ), "this test is only meaningful while a station names tile_2_2"

    result = run_mat_timeline(config)
    assert result.timeline
    tile_ids = {tile.tile_id for tile in result.final_tiles}
    assert "tile_2_2" not in tile_ids


@pytest.mark.parametrize("name", registry.list_scenarios())
def test_every_scenario_runs_its_evidence_loop(name):
    result = run_mat_timeline(_short(name))
    assert result.timeline
    assert result.recommendations, "a deployed mat must produce a decision record"
    for recommendation in result.recommendations:
        assert recommendation.human_confirmation_required is True
        assert recommendation.execution_mode == "simulation_only"


def test_the_none_policy_deploys_no_mat_and_attenuates_nothing():
    """The bug this guards against: averaging an empty list of tile fluxes to
    zero made a mat that does not exist report 100 per cent attenuation.
    """
    config = registry.policy_variant(_short("fresh_mat"), "none")
    result = run_mat_timeline(config)

    assert result.final_tiles == []
    assert result.recommendations == ()
    assert result.timeline[-1].attenuation["Pb"] == pytest.approx(0.0)
    assert result.hotspot_released_kg["Pb"] > 0.0


def test_the_three_policies_are_genuinely_different_runs():
    base = _short("fresh_mat")
    outcomes = {}
    for kind in registry.POLICIES:
        result = run_mat_timeline(registry.policy_variant(base, kind))
        outcomes[kind] = (
            len(result.recommendations),
            result.timeline[-1].attenuation["Pb"],
        )

    assert outcomes["none"][0] == 0
    assert outcomes["fixed"][0] > 0
    assert outcomes["evidence_informed"][0] > 0
    # 'none' must differ from both. fixed and evidence_informed may agree early,
    # before either has reason to service, and that is not a failure.
    assert outcomes["none"] != outcomes["fixed"]
    assert outcomes["none"] != outcomes["evidence_informed"]


def test_the_mat_ledger_closes_with_the_evidence_loop_running():
    """Adding servicing must not lose mass: metal moved into retrieved media has
    left the active layer but is still accounted for.
    """
    result = run_mat_timeline(_short("fresh_mat", years=0.5))
    for ledger in result.mat_ledger.values():
        assert abs(ledger.relative_imbalance) < 1e-9
