"""Shared fixtures for the observation branch.

The streams here are small on purpose: they cover every channel while staying
fast enough that a test can push every record through the **public**, uncached
validator when the point of the test is the contract rather than the speed.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from reactive_seabed_mat.config import (
    DegradationEvent,
    ObservationConfig,
    StationConfig,
)
from reactive_seabed_mat.observations import generator as gen
from reactive_seabed_mat.observations import records as obs
from reactive_seabed_mat.observations.condition import (
    ConditionAssumptions,
    MatConditionGenerator,
)

DAY = 86400.0
YEAR = 365.25 * DAY
START = datetime(2026, 9, 8, tzinfo=timezone.utc)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "synthetic" / "observations.jsonl"
)


@pytest.fixture(scope="session")
def start_utc() -> datetime:
    return START


@pytest.fixture(scope="session")
def fixture_records():
    """The coordinator's edge-case fixture file, parsed."""
    return obs.read_jsonl(FIXTURE_PATH)


@pytest.fixture(scope="session")
def small_config() -> ObservationConfig:
    """Every channel, on a rhythm short enough for a 40-day test stream."""
    return ObservationConfig(
        environmental_period_s=10.0 * DAY,
        bottom_water_probe_period_s=2.0 * DAY,
        porewater_sample_period_s=15.0 * DAY,
        chamber_deployment_period_s=15.0 * DAY,
        survey_period_s=15.0 * DAY,
        dgt_deployment_period_s=15.0 * DAY,
    )


@pytest.fixture(scope="session")
def small_scene(small_config):
    """A 40-day scene with all three tiles healthy."""
    return gen.synthetic_mat_history(START, 40.0 * DAY, step_s=DAY)


@pytest.fixture(scope="session")
def small_stream(small_config, small_scene):
    """A complete, short stream covering every channel."""
    generator = gen.ObservationGenerator(small_config, seed=20260908, start_utc=START)
    return generator.generate(small_scene, 40.0 * DAY)


@pytest.fixture(scope="session")
def multi_year_config() -> ObservationConfig:
    """The campaign rhythm of a real cap: months between chemistry."""
    return ObservationConfig(environmental_period_s=30.0 * DAY)


@pytest.fixture(scope="session")
def multi_year_scene():
    """Four years: loading, breakthrough, fouling, one tile lost, one torn, one buried.

    Each failure is placed on the tile whose station can actually observe it,
    which is the only way the demonstration says anything:

    ``tile_0_0``  bottom-water probe   displaced at 1.5 yr, so the probe sees the
                                       near-bed concentration rise;
    ``tile_1_1``  porewater station    torn at 2.2 yr and its media replaced at
                                       3.0 yr, so the assay describes the old batch;
    ``tile_2_2``  benthic chamber      buried at 1.0 yr, so the chamber measures a
                                       falling apparent flux that is not success.

    The degradation events touch position and integrity only.  Nothing about the
    chemistry changes, which is what keeps the four modes independent.
    """
    events = (
        DegradationEvent(start_s=1.5 * YEAR, tile_id="tile_0_0", mode="displacement",
                         magnitude=1.0),
        DegradationEvent(start_s=2.2 * YEAR, tile_id="tile_1_1", mode="local_damage",
                         magnitude=0.35),
        DegradationEvent(start_s=1.0 * YEAR, tile_id="tile_2_2", mode="burial",
                         magnitude=0.045),
    )
    return gen.synthetic_mat_history(
        START,
        4.0 * YEAR,
        step_s=DAY,
        events=events,
        replacements=(
            gen.MediaReplacement(
                start_s=3.0 * YEAR, tile_id="tile_1_1", new_media_id="media_B1"
            ),
        ),
    )


@pytest.fixture(scope="session")
def multi_year_stream(multi_year_config, multi_year_scene):
    generator = gen.ObservationGenerator(
        multi_year_config, seed=20260908, start_utc=START
    )
    return generator.generate(multi_year_scene, 4.0 * YEAR)


@pytest.fixture(scope="session")
def censoring_stream():
    """A stream built to cross every detection and range threshold on purpose.

    The bottom water ramps from far below the probe's LOD to past the top of its
    range, so below_lod, below_loq, quantified and above_range all occur.  A
    forced missingness and the categorical damage class complete the six.
    """
    config = ObservationConfig(
        bottom_water_probe_period_s=2.0 * DAY,
        environmental_period_s=30.0 * DAY,
        porewater_sample_period_s=60.0 * DAY,
        chamber_deployment_period_s=60.0 * DAY,
        survey_period_s=60.0 * DAY,
        dgt_deployment_period_s=60.0 * DAY,
        missing_probability=0.05,
    )
    scene = gen.ramp_mat_scene(
        START,
        200.0 * DAY,
        tile_ids=("tile_0_0", "tile_1_1", "tile_2_2"),
        start_bottom_water_kg_per_m3={"Pb": 1.0e-9, "Hg": 1.0e-11},
        end_bottom_water_kg_per_m3={"Pb": 8.0e-6, "Hg": 1.0e-8},
    )
    generator = gen.ObservationGenerator(config, seed=771, start_utc=START)
    return generator.generate(scene, 200.0 * DAY)


@pytest.fixture(scope="session")
def condition_stream(small_config, small_scene):
    generator = MatConditionGenerator(small_config, seed=11, start_utc=START)
    return generator.generate(small_scene, 40.0 * DAY)
