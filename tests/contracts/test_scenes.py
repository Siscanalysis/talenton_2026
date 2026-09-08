"""The scenes must differ only in what they claim to differ in."""

from __future__ import annotations

from dataclasses import replace

import pytest

from reactive_seabed_mat.config import config_to_dict
from reactive_seabed_mat.scenarios import registry


def test_every_scene_builds_and_is_described():
    for name in registry.list_scenes():
        config = registry.build_scene(name)
        assert config.scenario == name
        assert registry.scene_description(name)


def test_unknown_scene_is_rejected():
    with pytest.raises(KeyError):
        registry.build_scene("does_not_exist")


def test_policy_variants_share_forcing_source_and_seed():
    base = registry.build_scene("baseline")
    variants = {
        kind: registry.policy_variant(base, kind) for kind in registry.POLICIES
    }
    for kind, variant in variants.items():
        assert variant.policy.kind == kind
        assert variant.seed == base.seed
        assert variant.forcing == base.forcing
        assert variant.source == base.source
        assert variant.observations == base.observations
        assert variant.domain == base.domain


def test_source_change_and_current_reversal_differ_only_where_intended():
    change = registry.build_scene("source_change")
    reversal = registry.build_scene("current_reversal")
    # The source scene keeps the baseline forcing; the reversal scene keeps the
    # baseline source. That is what makes the pair a fair comparison.
    baseline = registry.build_scene("baseline")
    assert change.forcing == baseline.forcing
    assert reversal.source == baseline.source
    assert change.source != baseline.source
    assert reversal.forcing != baseline.forcing
    assert reversal.forcing.kind == "tidal"
    assert reversal.forcing.tidal_amplitude_m_per_s > abs(
        reversal.forcing.u_mean_m_per_s
    ), "the tide must actually reverse the flow, not merely modulate it"


def test_preloading_is_explicit_and_not_hidden_parameter_inflation():
    baseline = registry.build_scene("baseline")
    loading = registry.build_scene("loading_fouling")
    replacement = registry.build_scene("replacement")
    assert baseline.panels[0].preload_kg == {}
    assert loading.panels[0].preload_kg["Pb"] > 0.0
    assert replacement.panels[0].preload_kg["Pb"] > loading.panels[0].preload_kg["Pb"]
    # Uptake parameters are untouched: saturation comes from the preload.
    assert loading.panels[0].materials == baseline.panels[0].materials
    assert replacement.panels[0].materials == baseline.panels[0].materials
    # And the preload is visible in the exported configuration.
    assert config_to_dict(loading)["panels"][0]["preload_kg"]["Pb"] > 0.0


def test_poor_performance_is_genuinely_unfavourable():
    baseline = registry.build_scene("baseline")
    poor = registry.build_scene("poor_performance")
    assert poor.panels[0].interception_efficiency < 0.15
    assert poor.panels[0].sorbent_mass_kg < baseline.panels[0].sorbent_mass_kg
    assert poor.forcing.u_mean_m_per_s > baseline.forcing.u_mean_m_per_s
    for slow, fast in zip(poor.panels[0].materials, baseline.panels[0].materials):
        assert slow.k_rate_per_s < fast.k_rate_per_s / 10.0
        # capacity is untouched: a high-capacity material can still perform badly
        assert slow.q_max_kg_per_kg == fast.q_max_kg_per_kg


def test_sensor_dropout_scene_actually_drops_out():
    config = registry.build_scene("sensor_dropout")
    window = config.observations.sensor_dropout_window_s
    assert window is not None and window[1] > window[0]
    assert config.observations.sensor_drift_per_s > 0.0
    assert config.observations.lab_latency_s > registry.build_scene(
        "baseline"
    ).observations.lab_latency_s


def test_material_allocations_never_exceed_the_panel():
    for name in registry.list_scenes():
        config = registry.build_scene(name)
        for panel in config.panels:
            total = sum(material.allocation_fraction for material in panel.materials)
            assert total <= 1.0 + 1e-12, f"{name}: capacity assigned twice"


def test_policy_variant_rejects_an_unknown_policy():
    with pytest.raises(KeyError):
        registry.policy_variant(registry.build_scene("baseline"), "autonomous")
