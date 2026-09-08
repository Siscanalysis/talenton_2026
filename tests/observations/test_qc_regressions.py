"""Regression tests for the three QC defects the audit found.

Each test carries the **inherited algorithm** beside the fixed one and asserts
that the old one misses the case.  Without that, a regression test proves only
that the current code does what the current code does.

The three defects, from ``REFACTOR_PLAN.md`` section 5b:

(a) ``_sensor_health`` never updated ``last_seen`` for a missing record, so the
    data-age check was skipped for exactly the sensor that needed it;
(b) stuck detection substring-matched prose inside a reason string, so
    rewording the message silently disabled it;
(c) records with ``sensor_id = None`` (every laboratory, chamber, DGT, assay and
    survey record) never entered the health summary at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence

import pytest

from reactive_seabed_mat.contracts import ObservationRecord, QualityFlag
from reactive_seabed_mat.observations import qc
from reactive_seabed_mat.observations import records as obs

DAY = 86400.0
START = datetime(2026, 9, 8, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The inherited implementation, kept verbatim so the tests can discriminate
# ---------------------------------------------------------------------------

def _inherited_sensor_health(
    records: Sequence[ObservationRecord],
    outcomes: Mapping[str, qc.QCOutcome],
    thresholds: qc.QCThresholds,
    now_utc: datetime | None,
) -> dict[str, dict]:
    """The pre-refactor ``_sensor_health``, transcribed.

    Three behaviours are reproduced exactly: the ``sensor_id is None`` skip, the
    ``continue`` that jumps over the ``last_seen`` update for a missing record,
    and the substring match on prose.
    """
    grouped: dict[str, list[ObservationRecord]] = {}
    for record in records:
        if record.sensor_id is None:
            continue  # defect (c)
        grouped.setdefault(record.sensor_id, []).append(record)

    health: dict[str, dict] = {}
    for sensor_id, series in grouped.items():
        failed = stuck = suspect = False
        reasons: list[str] = []
        missing = 0
        last_seen: datetime | None = None
        for record in series:
            outcome = outcomes.get(record.record_id)
            flag = record.quality_flag if outcome is None else outcome.flag
            if flag is QualityFlag.MISSING:
                missing += 1
                continue  # defect (a): last_seen is never updated
            if last_seen is None or record.observed_at_utc > last_seen:
                last_seen = record.observed_at_utc
            if flag is QualityFlag.FAILED:
                failed = True
            if flag is QualityFlag.SUSPECT:
                suspect = True
            if outcome is not None and any(
                "stuck value" in reason for reason in outcome.reasons
            ):  # defect (b): prose matching
                stuck = True
        if failed:
            reasons.append("at least one reading failed a demo QC check")
        if stuck:
            reasons.append("flat-line run detected: the channel repeats a value")
        if suspect:
            reasons.append("at least one reading is suspect")
        stale = False
        if now_utc is not None and last_seen is not None:
            age = (now_utc - last_seen).total_seconds()
            if age > thresholds.default_max_data_age_s:
                stale = True
                reasons.append("newest usable reading is beyond the demo age limit")
        health[sensor_id] = {
            "sensor_id": sensor_id,
            "n_records": len(series),
            "last_seen": last_seen,
            "failed": failed,
            "stuck": stuck,
            "suspect": suspect,
            "stale": stale,
            "missing_fraction": missing / max(len(series), 1),
            "reasons": tuple(reasons),
        }
    return health


# ---------------------------------------------------------------------------
# record helpers
# ---------------------------------------------------------------------------

def _payload(**overrides):
    payload = {
        "record_id": "R0001",
        "station_id": "ST_MAT_A",
        "sensor_id": "SIM_PBPROBE_A",
        "sample_id": None,
        "media_id": None,
        "tile_id": "tile_0_0",
        "observed_at_utc": "2026-09-08T06:00:00Z",
        "available_at_utc": "2026-09-08T06:00:00Z",
        "sampling_start_utc": None,
        "sampling_end_utc": None,
        "parameter": "Pb",
        "quantity_kind": "aqueous_concentration",
        "unit": "ng/L",
        "matrix": "bottom_water",
        "fraction": "labile",
        "acquisition_kind": "in_situ_sensor",
        "value": 120.0,
        "uncertainty_std": 20.0,
        "qualifier": "quantified",
        "lower_bound": None,
        "upper_bound": None,
        "condition_class": None,
        "quality_flag": 1,
        "method_id": "SIM_VOLTAMMETRY_LABILE_V1",
        "calibration_id": "CAL_SIM_V1",
        "data_origin": "sensor",
        "provenance": "synthetic_demo",
        "source_ref": "regression test",
        "x_m": 300.0,
        "y_m": 220.0,
        "depth_m": 0.3,
        "vertical_datum": "seabed",
        "z_in_mat_m": None,
        "chamber_area_m2": None,
        "crs": "LOCAL_METRIC",
    }
    payload.update(overrides)
    return payload


def _at(index: int, step_h: float = 6.0) -> str:
    moment = START + timedelta(hours=index * step_h)
    return moment.isoformat().replace("+00:00", "Z")


def _reading(index: int, value: float | None, **overrides) -> ObservationRecord:
    stamp = _at(index)
    base = dict(
        record_id=f"R{index:04d}",
        observed_at_utc=stamp,
        available_at_utc=stamp,
        value=value,
    )
    if value is None:
        base.update(
            qualifier="missing", uncertainty_std=None, quality_flag=9,
        )
    base.update(overrides)
    return obs.record_from_dict(_payload(**base))


# ---------------------------------------------------------------------------
# (a) a sensor whose readings are all missing must not look fresh
# ---------------------------------------------------------------------------

def test_defect_a_all_missing_sensor_is_reported_as_stale():
    """The data-age check used to be skipped for the sensor that needed it most."""
    records = [_reading(index, None) for index in range(6)]
    report = qc.run_qc(records, now_utc=START + timedelta(days=30))

    health = report.sensor_health["SIM_PBPROBE_A"]
    assert health.n_records == 6
    assert health.missing_fraction == 1.0
    assert health.last_usable_at_utc is None
    assert health.last_observed_at_utc is not None, (
        "the sensor was heard from, it just said nothing useful"
    )
    assert health.stale is True
    assert not health.healthy
    assert any("no usable reading" in reason for reason in health.reasons)


def test_defect_a_the_inherited_version_missed_it():
    records = [_reading(index, None) for index in range(6)]
    report = qc.run_qc(records, now_utc=START + timedelta(days=30))
    old = _inherited_sensor_health(
        records, report.outcomes, qc.DEMO_THRESHOLDS, START + timedelta(days=30)
    )
    assert old["SIM_PBPROBE_A"]["last_seen"] is None
    assert old["SIM_PBPROBE_A"]["stale"] is False, (
        "this is the defect: no usable reading in 30 days, and the age check was "
        "skipped entirely"
    )


def test_defect_a_a_stale_but_once_usable_sensor_is_still_caught():
    """A sensor that worked, then went missing, is stale from its last good reading."""
    records = [_reading(0, 120.0)] + [_reading(index, None) for index in range(1, 6)]
    report = qc.run_qc(records, now_utc=START + timedelta(days=10))
    health = report.sensor_health["SIM_PBPROBE_A"]
    assert health.last_usable_at_utc == records[0].observed_at_utc
    assert health.last_observed_at_utc == records[-1].observed_at_utc
    assert health.stale is True
    assert health.data_age_s == pytest.approx(10.0 * DAY, rel=1e-6)


# ---------------------------------------------------------------------------
# (b) rewording the stuck message must not disable the check
# ---------------------------------------------------------------------------

def test_defect_b_stuck_detection_survives_a_reworded_message(monkeypatch):
    """Health reads the structured ``failed_checks`` set, never the prose."""
    monkeypatch.setattr(
        qc,
        "STUCK_REASON_TEMPLATE",
        "flat line: {count} identical readings inside {tolerance:g} "
        "(limit {limit})",
    )
    records = [_reading(index, 148.2) for index in range(6)]
    report = qc.run_qc(records, now_utc=START + timedelta(hours=6))

    outcome = report.outcomes["R0000"]
    assert "stuck_value" in outcome.failed_checks
    assert not any("stuck value" in reason for reason in outcome.reasons), (
        "the reword must really have removed the old substring"
    )
    assert report.stuck_sensor_ids() == ("SIM_PBPROBE_A",)
    assert report.sensor_health["SIM_PBPROBE_A"].stuck is True


def test_defect_b_the_inherited_version_missed_it(monkeypatch):
    monkeypatch.setattr(
        qc,
        "STUCK_REASON_TEMPLATE",
        "flat line: {count} identical readings inside {tolerance:g} "
        "(limit {limit})",
    )
    records = [_reading(index, 148.2) for index in range(6)]
    report = qc.run_qc(records, now_utc=START + timedelta(hours=6))
    old = _inherited_sensor_health(
        records, report.outcomes, qc.DEMO_THRESHOLDS, START + timedelta(hours=6)
    )
    assert old["SIM_PBPROBE_A"]["stuck"] is False, (
        "this is the defect: the check still ran and still failed the records, but "
        "the health summary matched prose and so reported a healthy channel"
    )
    # The records themselves are still failed, which is what makes the defect
    # subtle: only the summary lies.
    assert old["SIM_PBPROBE_A"]["failed"] is True


def test_defect_b_unreworded_stuck_detection_still_works():
    records = [_reading(index, 148.2) for index in range(6)]
    report = qc.run_qc(records, now_utc=START + timedelta(hours=6))
    assert report.stuck_sensor_ids() == ("SIM_PBPROBE_A",)


# ---------------------------------------------------------------------------
# (c) records without a sensor_id must still get a health summary
# ---------------------------------------------------------------------------

def _laboratory_record(index: int, value: float, **overrides) -> ObservationRecord:
    stamp = _at(index, step_h=24.0 * 90.0)
    base = dict(
        record_id=f"L{index:04d}",
        sensor_id=None,
        sample_id=f"PW_{index:04d}",
        station_id="ST_MAT_B",
        tile_id="tile_1_1",
        observed_at_utc=stamp,
        available_at_utc=stamp,
        parameter="Pb",
        quantity_kind="aqueous_concentration",
        unit="ug/L",
        matrix="porewater",
        fraction="dissolved_filtered",
        acquisition_kind="grab_sample",
        data_origin="laboratory",
        method_id="SIM_LAB_ICPMS_DISSFILT_V1",
        calibration_id=None,
        value=value,
        uncertainty_std=abs(value) * 0.08,
        depth_m=0.01,
        vertical_datum="mat_base",
        z_in_mat_m=0.0,
    )
    base.update(overrides)
    return obs.record_from_dict(_payload(**base))


def test_defect_c_sensorless_records_get_a_health_summary():
    """Every laboratory, chamber, DGT, assay and survey record has no sensor_id."""
    records = [_laboratory_record(index, 940.0) for index in range(6)]
    assert all(record.sensor_id is None for record in records)

    report = qc.run_qc(records, now_utc=START + timedelta(days=600))
    assert report.asset_health, "the summary must not be empty"
    key = "tile:tile_1_1"
    assert key in report.asset_health
    health = report.asset_health[key]
    assert health.asset_kind == "tile"
    assert health.n_records == 6
    assert health.last_usable_at_utc is not None
    assert report.health_for(records[0]) is health


def test_defect_c_a_flat_lined_laboratory_channel_is_caught():
    """The old summary could not see a laboratory channel at all, stuck or not."""
    records = [_laboratory_record(index, 940.0) for index in range(6)]
    report = qc.run_qc(records, now_utc=START + timedelta(days=600))
    health = report.asset_health["tile:tile_1_1"]
    assert health.stuck is True
    assert health.failed is True


def test_defect_c_the_inherited_version_missed_it():
    records = [_laboratory_record(index, 940.0) for index in range(6)]
    report = qc.run_qc(records, now_utc=START + timedelta(days=600))
    old = _inherited_sensor_health(
        records, report.outcomes, qc.DEMO_THRESHOLDS, START + timedelta(days=600)
    )
    assert old == {}, (
        "this is the defect: six identical porewater results, and the health "
        "summary was empty because none of them named a sensor"
    )


def test_defect_c_a_sensor_record_still_keys_on_its_sensor():
    """The fix must not move instrument health onto the tile."""
    records = [_reading(index, 120.0 + index) for index in range(4)]
    report = qc.run_qc(records, now_utc=START + timedelta(hours=6))
    assert "sensor:SIM_PBPROBE_A" in report.asset_health
    assert "tile:tile_0_0" not in report.asset_health
    assert set(report.sensor_health) == {"SIM_PBPROBE_A"}


def test_defect_c_every_record_of_a_real_stream_is_covered(small_stream):
    report = qc.run_qc(small_stream, now_utc=START + timedelta(days=41))
    covered = {
        f"{kind}:{identifier}"
        for kind, identifier in (qc.asset_key(record) for record in small_stream)
    }
    assert covered == set(report.asset_health)
    assert all(report.health_for(record) is not None for record in small_stream)
