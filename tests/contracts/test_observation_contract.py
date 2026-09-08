"""Observation-contract tests (coordinator-owned).

These encode the rules the whole demonstrator depends on: a non-detect is a
bound, a missing result carries no information, no future result may reach a
decision, and fractions/units are never silently merged.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from reactive_seabed_mat.contracts import (
    AcquisitionKind,
    DataOrigin,
    Fraction,
    Matrix,
    Parameter,
    Qualifier,
    QualityFlag,
)
from reactive_seabed_mat.observations import records as obs

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "observations.jsonl"


def _base_payload(**overrides):
    payload = {
        "record_id": "T0001",
        "station_id": "ST_UP",
        "sensor_id": "SIM_PBPROBE_01",
        "sample_id": None,
        "media_id": None,
        "observed_at_utc": "2026-09-08T06:00:00Z",
        "available_at_utc": "2026-09-08T06:00:00Z",
        "sampling_start_utc": None,
        "sampling_end_utc": None,
        "parameter": "Pb",
        "unit": "ng/L",
        "matrix": "seawater",
        "fraction": "labile",
        "acquisition_kind": "in_situ_sensor",
        "value": 100.0,
        "uncertainty_std": 20.0,
        "qualifier": "quantified",
        "lower_bound": None,
        "upper_bound": None,
        "quality_flag": 1,
        "method_id": "SIM_VOLTAMMETRY_LABILE_V1",
        "calibration_id": "CAL_2026_09_01",
        "data_origin": "synthetic",
        "source_ref": "test",
        "x_m": 200.0,
        "y_m": 220.0,
        "depth_m": 3.0,
        "crs": "LOCAL_METRIC",
    }
    payload.update(overrides)
    return payload


def test_fixture_file_is_valid_and_complete():
    parsed = obs.read_jsonl(FIXTURE)
    assert len(parsed) == 15
    ids = [record.record_id for record in parsed]
    assert len(set(ids)) == len(ids)


def test_fixture_covers_the_declared_edge_cases():
    parsed = {record.record_id: record for record in obs.read_jsonl(FIXTURE)}
    assert parsed["R0002"].qualifier is Qualifier.BELOW_LOD
    assert parsed["R0002"].value is None
    assert parsed["R0002"].upper_bound == 12.0
    assert parsed["R0003"].qualifier is Qualifier.MISSING
    assert parsed["R0003"].quality_flag is QualityFlag.MISSING
    assert parsed["R0006"].acquisition_kind is AcquisitionKind.PASSIVE_SAMPLER
    assert parsed["R0006"].sampling_start_utc is not None
    assert parsed["R0007"].matrix is Matrix.SORBENT and parsed["R0007"].unit == "ng/g"
    assert parsed["R0013"].quality_flag is QualityFlag.FAILED
    assert parsed["R0014"].matrix is Matrix.SEDIMENT


def test_non_detect_is_not_a_zero():
    record = obs.record_from_dict(
        _base_payload(
            record_id="T_ND",
            qualifier="below_lod",
            value=None,
            lower_bound=0.0,
            upper_bound=12.0,
        )
    )
    assert record.value is None
    assert record.is_censored
    assert record.carries_chemical_information


def test_missing_carries_no_chemical_information():
    record = obs.record_from_dict(
        _base_payload(
            record_id="T_MISS", qualifier="missing", value=None, quality_flag=9
        )
    )
    assert not record.carries_chemical_information


def test_non_detect_without_interval_is_rejected():
    with pytest.raises(obs.ObservationValidationError):
        obs.record_from_dict(
            _base_payload(qualifier="below_lod", value=None, lower_bound=None,
                          upper_bound=None)
        )


def test_missing_with_a_value_is_rejected():
    with pytest.raises(obs.ObservationValidationError):
        obs.record_from_dict(
            _base_payload(qualifier="missing", value=3.0, quality_flag=9)
        )


def test_missing_must_carry_flag_nine():
    with pytest.raises(obs.ObservationValidationError):
        obs.record_from_dict(
            _base_payload(qualifier="missing", value=None, quality_flag=1)
        )


def test_result_cannot_be_available_before_it_was_measured():
    with pytest.raises(obs.ObservationValidationError):
        obs.record_from_dict(
            _base_payload(
                observed_at_utc="2026-09-08T09:00:00Z",
                available_at_utc="2026-09-08T06:00:00Z",
            )
        )


def test_passive_sampler_requires_an_exposure_window():
    with pytest.raises(obs.ObservationValidationError):
        obs.record_from_dict(
            _base_payload(
                acquisition_kind="passive_sampler",
                sampling_start_utc=None,
                sampling_end_utc=None,
            )
        )


def test_timestamp_gate_excludes_future_results():
    early = obs.record_from_dict(_base_payload(record_id="A"))
    delayed = obs.record_from_dict(
        _base_payload(
            record_id="B",
            observed_at_utc="2026-09-08T09:00:00Z",
            available_at_utc="2026-09-10T09:00:00Z",
        )
    )
    decision_time = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    visible = obs.observations_available([early, delayed], decision_time)
    assert [record.record_id for record in visible] == ["A"]

    later = decision_time + timedelta(days=3)
    visible_later = obs.observations_available([early, delayed], later)
    assert [record.record_id for record in visible_later] == ["A", "B"]


def test_gate_preserves_ids_flags_and_fractions():
    parsed = obs.read_jsonl(FIXTURE)
    decision_time = datetime(2026, 9, 30, tzinfo=timezone.utc)
    visible = obs.observations_available(parsed, decision_time)
    assert len(visible) == len(parsed)
    for original, passed in zip(parsed, visible):
        assert original is passed


def test_gate_requires_timezone_aware_decision_time():
    with pytest.raises(ValueError):
        obs.observations_available([], datetime(2026, 9, 8, 12, 0))


def test_round_trip_serialisation(tmp_path):
    parsed = obs.read_jsonl(FIXTURE)
    target = obs.write_jsonl(tmp_path / "round_trip.jsonl", parsed)
    reparsed = obs.read_jsonl(target)
    assert [obs.record_to_dict(r) for r in parsed] == [
        obs.record_to_dict(r) for r in reparsed
    ]


def test_schema_file_is_valid_json():
    schema = obs.load_schema()
    assert schema["title"].startswith("Mesh demonstrator observation record")
    assert "record_id" in schema["required"]
    json.dumps(schema)


def test_quantified_and_labile_stay_distinct_from_total_recoverable():
    labile = obs.record_from_dict(_base_payload(record_id="L", fraction="labile"))
    total = obs.record_from_dict(
        _base_payload(record_id="T", fraction="total_recoverable")
    )
    assert labile.fraction is Fraction.LABILE
    assert total.fraction is Fraction.TOTAL_RECOVERABLE
    assert labile.fraction != total.fraction


def test_parameter_and_origin_enums_round_trip():
    record = obs.record_from_dict(_base_payload(data_origin="laboratory"))
    assert record.parameter is Parameter.PB
    assert record.data_origin is DataOrigin.LABORATORY
