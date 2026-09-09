"""The demonstration scenarios, as configuration variations.  Coordinator-owned.

Each scenario is a pure function of the default
:class:`~reactive_seabed_mat.config.RunConfig`, so two scenarios differ only in
what their description says they differ in.  The policy comparison
(``none`` / ``fixed`` / ``evidence_informed``) is applied on top of a scenario,
which is what makes "under identical assumptions" true rather than merely
claimed: same seed, same forcing, same hotspot schedule, same observation
schedule.

Scenarios A to F follow the brief:

======  ==========================  =================================================
A       ``fresh_mat``               fresh mat, moderate source
B       ``progressive_saturation``  same source, longer loading history
C       ``increased_leak``          the leak rate increases
D       ``displaced_section``       a section is displaced and a tile is punctured
E       ``delayed_chemistry``       delayed chemistry changes available evidence
F       ``undersized_mat``          reduced coverage and thickness, stronger seep
======  ==========================  =================================================
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Mapping

from ..config import (
    DegradationConfig,
    DegradationEvent,
    HotspotScheduleEntry,
    RunConfig,
    default_run_config,
)

_SECONDS_PER_DAY = 86400.0
_SECONDS_PER_YEAR = 365.25 * _SECONDS_PER_DAY

__all__ = [
    "SCENARIOS",
    "POLICIES",
    "build_scenario",
    "scenario_description",
    "scenario_letter",
    "policy_variant",
    "list_scenarios",
]


def _base(run_id: str, scenario: str, **overrides) -> RunConfig:
    return default_run_config(run_id=run_id, scenario=scenario, **overrides)


# ---------------------------------------------------------------------------
# A - fresh mat, moderate source
# ---------------------------------------------------------------------------

def scenario_fresh_mat() -> RunConfig:
    """A fresh, fully covering mat over a moderate hotspot.

    The reference case, and the one the no-mat run is compared against under
    identical forcing.
    """
    return _base("fresh_mat", "fresh_mat", duration_s=1.0 * _SECONDS_PER_YEAR)


# ---------------------------------------------------------------------------
# B - longer loading history
# ---------------------------------------------------------------------------

def scenario_progressive_saturation() -> RunConfig:
    """Same source and material, with the duration extended to six years.

    The medium accumulates loading under the configured affinity and kinetics.
    A plateau can represent equilibrium below nominal capacity; the scenario
    does not guarantee complete saturation or a breakthrough event.
    """
    return _base(
        "progressive_saturation",
        "progressive_saturation",
        duration_s=6.0 * _SECONDS_PER_YEAR,
    )


# ---------------------------------------------------------------------------
# C - the leak rate increases
# ---------------------------------------------------------------------------

def scenario_increased_leak() -> RunConfig:
    """The sediment-side driving conditions worsen after two years.

    The porewater concentration triples and the seepage velocity doubles.
    The event changes the source without directly changing mat parameters.
    Subsequent flux depends on the changed source and evolving material state;
    attribution remains limited by the available observations.
    """
    config = _base("increased_leak", "increased_leak", duration_s=6.0 * _SECONDS_PER_YEAR)
    base_entry = config.hotspot.schedule[0]
    schedule = (
        base_entry,
        HotspotScheduleEntry(
            start_s=2.0 * _SECONDS_PER_YEAR,
            porewater_kg_per_m3={
                element: 3.0 * value
                for element, value in base_entry.porewater_kg_per_m3.items()
            },
            seepage_velocity_m_per_s=2.0 * base_entry.seepage_velocity_m_per_s,
        ),
    )
    return replace(config, hotspot=replace(config.hotspot, schedule=schedule))


# ---------------------------------------------------------------------------
# D - a section is displaced or fails locally
# ---------------------------------------------------------------------------

def scenario_displaced_section() -> RunConfig:
    """One tile is swept off its footprint; another is punctured.

    Source and material coefficients are unchanged by the scheduled faults.
    Displacement uncovers one tile's footprint; partial damage adds bare flux
    over the lost integrity fraction of another. The remaining area retains
    its column contribution. Observation and policy timing determine service.
    """
    config = _base(
        "displaced_section", "displaced_section", duration_s=4.0 * _SECONDS_PER_YEAR
    )
    events = (
        DegradationEvent(
            start_s=1.5 * _SECONDS_PER_YEAR,
            tile_id="tile_2_0",
            mode="displacement",
            magnitude=1.0,          # fully displaced off its footprint
        ),
        DegradationEvent(
            start_s=2.2 * _SECONDS_PER_YEAR,
            tile_id="tile_0_2",
            mode="local_damage",
            magnitude=0.35,         # 35 % of the tile area torn open
        ),
    )
    return replace(config, degradation=replace(config.degradation, events=events))


# ---------------------------------------------------------------------------
# E - delayed chemistry changes available evidence
# ---------------------------------------------------------------------------

def scenario_delayed_chemistry() -> RunConfig:
    """The probe drops out and drifts while the laboratory result is in transit.

    Dropout, drift and laboratory delay change the evidence available to
    estimation. Completed records become usable only after availability and
    QC/fraction checks. Their sample times remain explicit, and newly available
    evidence need not change the selected maintenance action.
    """
    config = _base(
        "delayed_chemistry", "delayed_chemistry", duration_s=4.0 * _SECONDS_PER_YEAR
    )
    observations = replace(
        config.observations,
        sensor_dropout_window_s=(1.0 * _SECONDS_PER_YEAR, 1.25 * _SECONDS_PER_YEAR),
        sensor_drift_start_s=1.25 * _SECONDS_PER_YEAR,
        sensor_drift_per_s=6.0e-9,
        lab_latency_s=75.0 * _SECONDS_PER_DAY,
    )
    return replace(config, observations=observations)


# ---------------------------------------------------------------------------
# F - smaller footprint and thinner core over a stronger seep
# ---------------------------------------------------------------------------

def scenario_undersized_mat() -> RunConfig:
    """Reduced coverage and thickness, with stronger seepage and more bypass.

    The mat covers 45 % of the hotspot with a 2 mm core and four tiles.
    Seepage triples and nominal edge leakage rises to 10 %. This compound
    stress case tests untreated-area emission and lower material inventory.
    Performance and any cost comparison must be read from the generated run.
    """
    config = _base("undersized_mat", "undersized_mat", duration_s=4.0 * _SECONDS_PER_YEAR)
    mat = replace(
        config.mat,
        coverage_fraction=0.45,
        thickness_m=0.002,
        tiles_x=2,
        tiles_y=2,
        edge_leakage_fraction=0.10,
    )
    base_entry = config.hotspot.schedule[0]
    schedule = (
        HotspotScheduleEntry(
            start_s=0.0,
            porewater_kg_per_m3=dict(base_entry.porewater_kg_per_m3),
            seepage_velocity_m_per_s=3.0 * base_entry.seepage_velocity_m_per_s,
        ),
    )
    return replace(
        config,
        mat=mat,
        hotspot=replace(config.hotspot, schedule=schedule),
    )


SCENARIOS: Mapping[str, Callable[[], RunConfig]] = {
    "fresh_mat": scenario_fresh_mat,
    "progressive_saturation": scenario_progressive_saturation,
    "increased_leak": scenario_increased_leak,
    "displaced_section": scenario_displaced_section,
    "delayed_chemistry": scenario_delayed_chemistry,
    "undersized_mat": scenario_undersized_mat,
}

_LETTERS: Mapping[str, str] = {
    "fresh_mat": "A",
    "progressive_saturation": "B",
    "increased_leak": "C",
    "displaced_section": "D",
    "delayed_chemistry": "E",
    "undersized_mat": "F",
}

_DESCRIPTIONS: Mapping[str, str] = {
    "fresh_mat": (
        "Scenario A. A fresh, fully covering mat over a moderate hotspot, "
        "against the same hotspot with no mat under identical forcing."
    ),
    "progressive_saturation": (
        "Scenario B. The same source and material over six years. Loading "
        "can approach equilibrium below nominal capacity. Only duration "
        "differs from A."
    ),
    "increased_leak": (
        "Scenario C. After two years the porewater concentration triples and "
        "the seepage velocity doubles. The source changes without directly "
        "altering the mat; later flux also depends on evolving material state."
    ),
    "displaced_section": (
        "Scenario D. One tile is displaced off its footprint and another is "
        "partially punctured. Uncovered and damaged fractions emit bare flux; "
        "the remaining area retains its column contribution."
    ),
    "delayed_chemistry": (
        "Scenario E. Probe dropout, then drift, with laboratory chemistry "
        "still in transit. A result can affect estimation only after its "
        "availability and QC checks; a different action is not guaranteed."
    ),
    "undersized_mat": (
        "Scenario F. A compound stress case: 45 % coverage, a 2 mm core, "
        "four tiles, tripled seepage and 10 % nominal edge leakage."
    ),
}

POLICIES: Mapping[str, str] = {
    "none": "No mat deployed. The bare-sediment reference case.",
    "fixed": "Fixed-interval servicing, ignoring the evidence.",
    "evidence_informed": (
        "Servicing recommended from the observations and their uncertainty."
    ),
}


def scenario_description(name: str) -> str:
    return _DESCRIPTIONS[name]


def scenario_letter(name: str) -> str:
    return _LETTERS[name]


def list_scenarios() -> list[str]:
    return list(SCENARIOS)


def build_scenario(name: str) -> RunConfig:
    try:
        factory = SCENARIOS[name]
    except KeyError:
        raise KeyError(
            f"unknown scenario {name!r}; known: {list(SCENARIOS)}"
        ) from None
    return factory()


def policy_variant(config: RunConfig, policy_kind: str) -> RunConfig:
    """Same scenario, different maintenance policy.

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
