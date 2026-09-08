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
B       ``progressive_saturation``  same source, the mat progressively saturates
C       ``increased_leak``          the leak rate increases
D       ``displaced_section``       a section is displaced and a tile is punctured
E       ``delayed_chemistry``       late chemistry changes the maintenance decision
F       ``undersized_mat``          a deliberately poor design
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
# B - the mat progressively saturates
# ---------------------------------------------------------------------------

def scenario_progressive_saturation() -> RunConfig:
    """Same source, run long enough for the medium to load and break through.

    Nothing about the chemistry is changed: only the simulated duration. The
    attenuation falls because capacity is consumed, which is what makes
    criterion 4 (loading affects later performance) demonstrable rather than
    asserted.
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

    The porewater concentration triples and the seepage velocity doubles. The
    mat is unchanged, so a rising residual flux here means a stronger source,
    not a failing cap. Distinguishing the two is the estimator's job.
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

    Chemistry, source and forcing are untouched. The failure is spatially local:
    the affected cells return to the bare-sediment flux while their neighbours
    keep attenuating. This is the scenario that proves criterion 5, and the one
    where reading the loss as saturation would be wrong.
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
# E - late chemistry changes the decision
# ---------------------------------------------------------------------------

def scenario_delayed_chemistry() -> RunConfig:
    """The probe drops out and drifts while the laboratory result is in transit.

    The correct behaviour is a wider interval and an evidence-limited
    recommendation, never a confident "all safe". When the delayed result
    finally becomes available it must be compared with the prediction at
    *sampling* time, and it is allowed to change the decision then, not
    retrospectively.
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
# F - a deliberately poor design
# ---------------------------------------------------------------------------

def scenario_undersized_mat() -> RunConfig:
    """Too small, too thin, and laid over a stronger seep.

    The mat covers only 45 % of the hotspot and is 2 mm thick instead of 10 mm,
    so most of the area is never treated and the treated part saturates quickly.
    Capture is poor and the cost per kilogram retained is bad. This scenario
    exists so the demonstration is not tuned to succeed, and it is a real
    outcome of the same equations, not a special case.
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
        "Scenario B. The same source over six years: the medium loads, "
        "attenuation falls and the layer breaks through. Only the duration "
        "differs from A."
    ),
    "increased_leak": (
        "Scenario C. After two years the porewater concentration triples and "
        "the seepage velocity doubles. The mat is unchanged, so a rising "
        "residual flux means a stronger source, not a failing cap."
    ),
    "displaced_section": (
        "Scenario D. One tile is displaced off its footprint and another is "
        "punctured. The failure is local: those cells return to the bare flux "
        "while their neighbours keep working."
    ),
    "delayed_chemistry": (
        "Scenario E. Probe dropout, then drift, with laboratory chemistry "
        "still in transit. The late result changes the maintenance decision "
        "when it arrives, and not before."
    ),
    "undersized_mat": (
        "Scenario F. A deliberately poor design: 45 % coverage, 2 mm thick, "
        "over a stronger seep. Poor capture and a bad cost per kilogram."
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
