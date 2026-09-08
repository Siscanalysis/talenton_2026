"""The demonstration scenes, as configuration variations.  Coordinator-owned.

Each scene is a pure function of the default :class:`~reactive_seabed_mat.config.RunConfig`,
so two scenes differ only in what their description says they differ in.  The
policy comparison (``none`` / ``fixed`` / ``evidence_informed``) is applied on
top of a scene, which is what makes "under identical assumptions" true rather
than merely claimed: same seed, same forcing, same source schedule, same
observation schedule.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Mapping

from ..config import (
    ForcingConfig,
    MaterialConfig,
    ObservationConfig,
    PanelConfig,
    PolicyConfig,
    RunConfig,
    SourceConfig,
    SourceScheduleEntry,
    default_run_config,
)

__all__ = [
    "SCENES",
    "POLICIES",
    "build_scene",
    "scene_description",
    "policy_variant",
    "list_scenes",
]


def _base(run_id: str, scenario: str, **overrides) -> RunConfig:
    return default_run_config(run_id=run_id, scenario=scenario, **overrides)


# ---------------------------------------------------------------------------
# Scene 1 - baseline
# ---------------------------------------------------------------------------

def scene_baseline() -> RunConfig:
    """Fresh panel under steady forcing, against the same run with no mesh."""
    return _base("baseline", "baseline")


# ---------------------------------------------------------------------------
# Scene 2 - loading and fouling
# ---------------------------------------------------------------------------

def scene_loading_fouling() -> RunConfig:
    """A partially preloaded panel that fouls, so predicted performance falls
    and the interval widens.  The preload is explicit in the exported config;
    uptake parameters are not inflated to force saturation."""
    config = _base("loading_fouling", "loading_fouling", duration_s=345600.0)
    panel = config.panels[0]
    preloaded = replace(
        panel,
        preload_kg={"Pb": 0.55 * panel.sorbent_mass_kg * 0.6 * 6.0e-5, "Hg": 0.0},
        fouling_growth_per_s=6.0e-6,
    )
    return replace(config, panels=(preloaded,))


# ---------------------------------------------------------------------------
# Scene 3a - source change,  3b - current reversal
# ---------------------------------------------------------------------------

def scene_source_change() -> RunConfig:
    """The release triples half-way through.  Station readings rise."""
    config = _base("source_change", "source_change")
    schedule = (
        SourceScheduleEntry(0.0, {"Pb": 2.0e-7, "Hg": 2.0e-9}),
        SourceScheduleEntry(129600.0, {"Pb": 6.0e-7, "Hg": 6.0e-9}),
    )
    return replace(config, source=replace(config.source, schedule=schedule))


def scene_current_reversal() -> RunConfig:
    """The source is unchanged, but the tide reverses the flow.  Station
    readings change for a completely different reason.  This is the pair that
    shows why current data and targeted sampling are worth their cost."""
    config = _base("current_reversal", "current_reversal")
    forcing = ForcingConfig(
        kind="tidal",
        u_mean_m_per_s=0.02,
        tidal_amplitude_m_per_s=0.22,
        diffusivity_m2_per_s=0.6,
    )
    return replace(config, forcing=forcing)


# ---------------------------------------------------------------------------
# Scene 4 - sensor dropout, drift and delayed chemistry
# ---------------------------------------------------------------------------

def scene_sensor_dropout() -> RunConfig:
    """The metal probe drops out for a day and drifts afterwards, while the
    laboratory result for the missing period is still in transit.  The correct
    behaviour is a wider interval and an evidence-limited recommendation, never
    a confident 'all safe'."""
    config = _base("sensor_dropout", "sensor_dropout")
    observations = replace(
        config.observations,
        sensor_dropout_window_s=(86400.0, 172800.0),
        sensor_drift_start_s=172800.0,
        sensor_drift_per_s=2.5e-6,
        lab_latency_s=216000.0,
    )
    return replace(config, observations=observations)


# ---------------------------------------------------------------------------
# Scene 5 - replacement
# ---------------------------------------------------------------------------

def scene_replacement() -> RunConfig:
    """A heavily preloaded panel reaches the replacement trigger, a simulated
    operator accepts, capacity resets and the retrieved mass stays on the
    ledger."""
    config = _base("replacement", "replacement", duration_s=345600.0)
    panel = config.panels[0]
    preloaded = replace(
        panel,
        preload_kg={"Pb": 0.74 * panel.sorbent_mass_kg * 0.6 * 6.0e-5, "Hg": 0.0},
    )
    policy = replace(config.policy, replacement_loading_threshold=0.78)
    return replace(config, panels=(preloaded,), policy=policy)


# ---------------------------------------------------------------------------
# Scene 6 - the unfavourable case
# ---------------------------------------------------------------------------

def scene_poor_performance() -> RunConfig:
    """A deliberately unfavourable case: weak interception and slow kinetics in
    a faster current.  Capture is negligible and the cost per captured kg is
    absurd.  This is a real outcome of the same equations, and it is included
    so the demonstration is not tuned to succeed."""
    config = _base("poor_performance", "poor_performance")
    panel = config.panels[0]
    slow_materials = tuple(
        replace(
            material,
            k_rate_per_s=material.k_rate_per_s / 40.0,
            k_rate_interval=(
                material.k_rate_interval[0] / 40.0,
                material.k_rate_interval[1] / 40.0,
            ),
        )
        for material in panel.materials
    )
    weak_panel = replace(
        panel,
        interception_efficiency=0.05,
        interception_interval=(0.01, 0.12),
        sorbent_mass_kg=8.0,
        materials=slow_materials,
    )
    forcing = replace(config.forcing, u_mean_m_per_s=0.30)
    return replace(config, panels=(weak_panel,), forcing=forcing)


SCENES: Mapping[str, Callable[[], RunConfig]] = {
    "baseline": scene_baseline,
    "loading_fouling": scene_loading_fouling,
    "source_change": scene_source_change,
    "current_reversal": scene_current_reversal,
    "sensor_dropout": scene_sensor_dropout,
    "replacement": scene_replacement,
    "poor_performance": scene_poor_performance,
}

_DESCRIPTIONS: Mapping[str, str] = {
    "baseline": (
        "Scene 1. Fresh panel versus no mesh under identical forcing. Shows "
        "captured and escaped mass per element."
    ),
    "loading_fouling": (
        "Scene 2. An explicitly preloaded panel fouls: predicted performance "
        "declines and the uncertainty interval widens. Inspect or replace?"
    ),
    "source_change": (
        "Scene 3a. The release triples. Station readings rise because more "
        "metal is entering the water."
    ),
    "current_reversal": (
        "Scene 3b. The release is unchanged and the tide reverses. Station "
        "readings change for a different reason. Same symptom, different "
        "mechanism."
    ),
    "sensor_dropout": (
        "Scene 4. Probe dropout, then drift, with laboratory chemistry still in "
        "transit. Recommendations stay evidence-limited."
    ),
    "replacement": (
        "Scene 5. The replacement trigger is reached, a simulated operator "
        "accepts, active capacity resets and retrieved mass stays on the ledger."
    ),
    "poor_performance": (
        "Scene 6. The unfavourable case: weak interception, slow kinetics, "
        "faster current. Negligible capture and no economic advantage."
    ),
}

POLICIES: Mapping[str, str] = {
    "none": "No mesh deployed. The reference case.",
    "fixed": "Fixed-interval servicing, ignoring the evidence.",
    "evidence_informed": "Servicing recommended from the observations and their uncertainty.",
}


def scene_description(name: str) -> str:
    return _DESCRIPTIONS[name]


def list_scenes() -> list[str]:
    return list(SCENES)


def build_scene(name: str) -> RunConfig:
    try:
        factory = SCENES[name]
    except KeyError:
        raise KeyError(f"unknown scene {name!r}; known scenes: {list(SCENES)}") from None
    return factory()


def policy_variant(config: RunConfig, policy_kind: str) -> RunConfig:
    """Same scene, different maintenance policy.

    Only ``PolicyConfig.kind`` changes, so a comparison across policies really
    is a comparison under identical assumptions.  The run id records which
    variant it is, and the seed is untouched.
    """
    if policy_kind not in POLICIES:
        raise KeyError(f"unknown policy {policy_kind!r}; known: {list(POLICIES)}")
    return replace(
        config,
        run_id=f"{config.run_id}__{policy_kind}",
        policy=replace(config.policy, kind=policy_kind),
    )
