"""Scenarios A to F must differ only in what they claim to differ in."""

from __future__ import annotations

import pytest

from reactive_seabed_mat.config import config_to_dict
from reactive_seabed_mat.scenarios import registry

_SECONDS_PER_YEAR = 365.25 * 86400.0


def test_every_scenario_builds_and_is_described():
    letters = set()
    for name in registry.list_scenarios():
        config = registry.build_scenario(name)
        assert config.scenario == name
        assert registry.scenario_description(name)
        letters.add(registry.scenario_letter(name))
    assert letters == {"A", "B", "C", "D", "E", "F"}


def test_unknown_scenario_is_rejected():
    with pytest.raises(KeyError):
        registry.build_scenario("does_not_exist")


def test_policy_variants_share_everything_except_the_policy():
    base = registry.build_scenario("fresh_mat")
    for kind in registry.POLICIES:
        variant = registry.policy_variant(base, kind)
        assert variant.policy.kind == kind
        assert variant.seed == base.seed
        assert variant.forcing == base.forcing
        assert variant.hotspot == base.hotspot
        assert variant.mat == base.mat
        assert variant.observations == base.observations
        assert variant.domain == base.domain
        assert variant.degradation == base.degradation


def test_policy_variant_rejects_an_unknown_policy():
    with pytest.raises(KeyError):
        registry.policy_variant(registry.build_scenario("fresh_mat"), "autonomous")


def test_saturation_scenario_changes_only_the_duration():
    fresh = registry.build_scenario("fresh_mat")
    loaded = registry.build_scenario("progressive_saturation")
    assert loaded.duration_s > fresh.duration_s
    # Chemistry, layout and source are untouched: the medium loads because time
    # passes, not because the parameters were made favourable.
    assert loaded.mat == fresh.mat
    assert loaded.hotspot == fresh.hotspot
    assert loaded.forcing == fresh.forcing


def test_increased_leak_changes_the_source_and_nothing_else():
    base = registry.build_scenario("progressive_saturation")
    leak = registry.build_scenario("increased_leak")
    assert leak.mat == base.mat
    assert leak.degradation == base.degradation
    assert leak.forcing == base.forcing
    assert len(leak.hotspot.schedule) == 2
    first, second = leak.hotspot.schedule
    assert second.start_s == pytest.approx(2.0 * _SECONDS_PER_YEAR)
    for element, value in first.porewater_kg_per_m3.items():
        assert second.porewater_kg_per_m3[element] == pytest.approx(3.0 * value)
    assert second.seepage_velocity_m_per_s == pytest.approx(
        2.0 * first.seepage_velocity_m_per_s
    )


def test_displaced_section_is_local_and_not_chemical():
    base = registry.build_scenario("fresh_mat")
    failed = registry.build_scenario("displaced_section")
    # Same chemistry, same source, same forcing: only the physical condition
    # of individual tiles differs.
    assert failed.mat.media == base.mat.media
    assert failed.hotspot.schedule == base.hotspot.schedule
    assert failed.forcing == base.forcing
    events = failed.degradation.events
    assert len(events) == 2
    modes = {event.mode for event in events}
    assert modes == {"displacement", "local_damage"}
    tiles = {event.tile_id for event in events}
    assert len(tiles) == 2, "the failure must hit specific tiles, not the whole mat"
    assert failed.mat.n_tiles > len(tiles), "other tiles must keep working"


def test_delayed_chemistry_delays_evidence_without_changing_physics():
    base = registry.build_scenario("fresh_mat")
    delayed = registry.build_scenario("delayed_chemistry")
    assert delayed.mat == base.mat
    assert delayed.hotspot == base.hotspot
    assert delayed.degradation == base.degradation
    window = delayed.observations.sensor_dropout_window_s
    assert window is not None and window[1] > window[0]
    assert delayed.observations.sensor_drift_per_s > 0.0
    assert delayed.observations.lab_latency_s > base.observations.lab_latency_s


def test_undersized_mat_is_genuinely_a_poor_design():
    base = registry.build_scenario("fresh_mat")
    poor = registry.build_scenario("undersized_mat")
    assert poor.mat.coverage_fraction < 0.5, "most of the hotspot is left untreated"
    assert poor.mat.thickness_m < base.mat.thickness_m
    assert poor.mat.sorbent_loading_kg_per_m2 < base.mat.sorbent_loading_kg_per_m2
    assert poor.mat.edge_leakage_fraction > base.mat.edge_leakage_fraction
    assert (
        poor.hotspot.schedule[0].seepage_velocity_m_per_s
        > base.hotspot.schedule[0].seepage_velocity_m_per_s
    )
    # The chemistry is NOT sabotaged: a good medium can still be a bad design.
    for poor_medium, base_medium in zip(poor.mat.media, base.mat.media):
        assert poor_medium.kd_m3_per_kg == base_medium.kd_m3_per_kg
        assert poor_medium.q_max_kg_per_kg == base_medium.q_max_kg_per_kg
        assert poor_medium.k_rate_per_s == base_medium.k_rate_per_s


def test_preloading_when_used_is_explicit_in_the_exported_configuration():
    for name in registry.list_scenarios():
        config = registry.build_scenario(name)
        exported = config_to_dict(config)
        assert "preload_kg_per_m2" in exported["mat"]


def test_media_allocations_never_exceed_the_layer_in_any_scenario():
    for name in registry.list_scenarios():
        config = registry.build_scenario(name)
        total = sum(medium.allocation_fraction for medium in config.mat.media)
        assert total <= 1.0 + 1e-12, f"{name}: capacity assigned twice"


def test_every_scenario_keeps_a_multi_year_mat_timeline():
    for name in registry.list_scenarios():
        config = registry.build_scenario(name)
        assert config.duration_years >= 1.0, f"{name}: a cap is not a plume"
