"""Observation-contract tests (coordinator-owned).

These encode the rules the whole demonstrator depends on: a non-detect is a
bound, a missing result carries no information, no future result may reach a
decision, units are never inferred, and mat condition is observable per tile.
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
    ProvenanceLabel,
    Qualifier,
    QualityFlag,
    QuantityKind,
    VerticalDatum,
)
from reactive_seabed_mat.observations import records as obs

FIXTURE = (
    Path(__file__).resolve().parents[2] / "data" / "synthetic" / "observations.jsonl"
)


def _base_payload(**overrides):
    payload = {
        "record_id": "T0001",
        "station_id": "ST_MAT_A",
        "sensor_id": "SIM_PBPROBE_A",
        "sample_id": None,
        "media_id": None,
        "tile_id": "tile_A1",
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
        "value": 100.0,
        "uncertainty_std": 20.0,
        "qualifier": "quantified",
        "lower_bound": None,
        "upper_bound": None,
        "condition_class": None,
        "quality_flag": 1,
        "method_id": "SIM_VOLTAMMETRY_LABILE_V1",
        "calibration_id": "CAL_2026_09_01",
        "data_origin": "sensor",
        "provenance": "synthetic_demo",
        "source_ref": "test",
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


# --- fixture ---------------------------------------------------------------

def test_fixture_file_is_valid_and_complete():
    parsed = obs.read_jsonl(FIXTURE)
    assert len(parsed) == 20
    ids = [record.record_id for record in parsed]
    assert len(set(ids)) == len(ids)


def test_fixture_covers_the_declared_edge_cases():
    parsed = {record.record_id: record for record in obs.read_jsonl(FIXTURE)}
    assert parsed["R0001"].matrix is Matrix.POREWATER          # driving condition
    assert parsed["R0002"].qualifier is Qualifier.BELOW_LOD
    assert parsed["R0002"].value is None and parsed["R0002"].upper_bound == 12.0
    assert parsed["R0003"].qualifier is Qualifier.MISSING
    assert parsed["R0003"].quality_flag is QualityFlag.MISSING
    assert parsed["R0004"].quantity_kind is QuantityKind.AREAL_FLUX
    assert parsed["R0004"].chamber_area_m2 == pytest.approx(0.196)
    assert parsed["R0006"].fraction is Fraction.METHYLMERCURY   # the Hg risk channel
    assert parsed["R0007"].acquisition_kind is AcquisitionKind.PASSIVE_SAMPLER
    assert parsed["R0007"].fraction is Fraction.DGT_LABILE
    assert parsed["R0008"].matrix is Matrix.SORBENT and parsed["R0008"].unit == "ng/g"
    assert parsed["R0010"].unit == "cm"                          # length ladder
    assert parsed["R0011"].qualifier is Qualifier.CATEGORICAL
    assert parsed["R0011"].condition_class == "punctured"
    assert parsed["R0014"].unit == "cm/yr"                       # velocity ladder
    assert parsed["R0018"].qualifier is Qualifier.ABOVE_RANGE


def test_fixture_makes_local_failure_observable():
    parsed = obs.read_jsonl(FIXTURE)
    tiles = {record.tile_id for record in parsed if record.tile_id}
    assert len(tiles) >= 3, "condition must be attributable to individual tiles"
    condition = [record for record in parsed if record.is_mat_condition]
    assert condition, "the mat's physical condition must be observable"
    assert {record.tile_id for record in condition if record.tile_id}


def test_fixture_separates_pathway_from_truth_status():
    parsed = {record.record_id: record for record in obs.read_jsonl(FIXTURE)}
    fabricated_lab = parsed["R0004"]
    assert fabricated_lab.data_origin is DataOrigin.LABORATORY
    assert fabricated_lab.provenance is ProvenanceLabel.SYNTHETIC_DEMO


# --- censoring ladder ------------------------------------------------------

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
        _base_payload(record_id="T_MISS", qualifier="missing", value=None, quality_flag=9)
    )
    assert not record.carries_chemical_information


def test_above_range_is_a_lower_bound():
    record = obs.record_from_dict(
        _base_payload(
            record_id="T_AR",
            qualifier="above_range",
            value=None,
            lower_bound=5000.0,
            upper_bound=None,
        )
    )
    assert record.value is None
    assert record.lower_bound == 5000.0
    assert record.carries_chemical_information


def test_categorical_needs_a_class_and_the_matching_quantity_kind():
    record = obs.record_from_dict(
        _base_payload(
            record_id="T_CAT",
            parameter="mat_damage_class",
            quantity_kind="categorical",
            unit="class",
            matrix="mat_structure",
            fraction="not_applicable",
            acquisition_kind="rov_inspection",
            data_origin="field_survey",
            qualifier="categorical",
            value=None,
            condition_class="torn",
        )
    )
    assert record.condition_class == "torn"
    assert record.is_mat_condition
    with pytest.raises(obs.ObservationValidationError):
        obs.record_from_dict(
            _base_payload(
                qualifier="categorical", value=None, condition_class=None,
                quantity_kind="categorical", unit="class",
            )
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"qualifier": "below_lod", "value": None, "lower_bound": None, "upper_bound": None},
        {"qualifier": "below_lod", "value": 3.0, "lower_bound": 0.0, "upper_bound": 12.0},
        {"qualifier": "missing", "value": 3.0, "quality_flag": 9},
        {"qualifier": "missing", "value": None, "quality_flag": 1},
        {"qualifier": "quantified", "value": 3.0, "lower_bound": 0.0, "upper_bound": 12.0},
        {"qualifier": "above_range", "value": None, "lower_bound": None, "upper_bound": None},
    ],
)
def test_malformed_censoring_is_rejected(overrides):
    with pytest.raises(obs.ObservationValidationError):
        obs.record_from_dict(_base_payload(**overrides))


# --- units and quantity kind ----------------------------------------------

def test_unit_must_match_the_declared_quantity_kind():
    with pytest.raises(obs.ObservationValidationError):
        # a flux reported in a concentration unit
        obs.record_from_dict(
            _base_payload(quantity_kind="areal_flux", unit="ng/L")
        )
    with pytest.raises(obs.ObservationValidationError):
        # a length reported in a mass unit
        obs.record_from_dict(
            _base_payload(quantity_kind="length", unit="kg", parameter="burial_depth")
        )


def test_flux_units_are_accepted_only_from_the_flux_ladder():
    record = obs.record_from_dict(
        _base_payload(
            record_id="T_FLUX",
            quantity_kind="areal_flux",
            unit="ug/m2/d",
            acquisition_kind="benthic_chamber",
            sampling_start_utc="2026-09-08T00:00:00Z",
            sampling_end_utc="2026-09-08T06:00:00Z",
            chamber_area_m2=0.196,
        )
    )
    assert record.quantity_kind is QuantityKind.AREAL_FLUX


# --- acquisition-specific rules -------------------------------------------

def test_passive_sampler_requires_an_exposure_window():
    with pytest.raises(obs.ObservationValidationError):
        obs.record_from_dict(
            _base_payload(
                acquisition_kind="passive_sampler",
                sampling_start_utc=None,
                sampling_end_utc=None,
            )
        )


def test_benthic_chamber_requires_area_and_window():
    with pytest.raises(obs.ObservationValidationError):
        obs.record_from_dict(
            _base_payload(
                quantity_kind="areal_flux",
                unit="ug/m2/d",
                acquisition_kind="benthic_chamber",
                sampling_start_utc="2026-09-08T00:00:00Z",
                sampling_end_utc="2026-09-08T06:00:00Z",
                chamber_area_m2=None,
            )
        )


def test_depth_without_a_vertical_datum_is_rejected():
    with pytest.raises(obs.ObservationValidationError):
        obs.record_from_dict(_base_payload(depth_m=5.0, vertical_datum=None))


def test_result_cannot_be_available_before_it_was_measured():
    with pytest.raises(obs.ObservationValidationError):
        obs.record_from_dict(
            _base_payload(
                observed_at_utc="2026-09-08T09:00:00Z",
                available_at_utc="2026-09-08T06:00:00Z",
            )
        )


# --- the availability gate -------------------------------------------------

def test_timestamp_gate_excludes_future_results():
    early = obs.record_from_dict(_base_payload(record_id="A"))
    delayed = obs.record_from_dict(
        _base_payload(
            record_id="B",
            observed_at_utc="2026-09-08T09:00:00Z",
            available_at_utc="2026-09-30T09:00:00Z",
        )
    )
    decision_time = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    visible = obs.observations_available([early, delayed], decision_time)
    assert [record.record_id for record in visible] == ["A"]

    later = decision_time + timedelta(days=30)
    visible_later = obs.observations_available([early, delayed], later)
    assert [record.record_id for record in visible_later] == ["A", "B"]


def test_gate_preserves_ids_flags_and_fractions():
    parsed = obs.read_jsonl(FIXTURE)
    decision_time = datetime(2026, 10, 30, tzinfo=timezone.utc)
    visible = obs.observations_available(parsed, decision_time)
    assert len(visible) == len(parsed)
    for original, passed in zip(parsed, visible):
        assert original is passed


def test_gate_requires_timezone_aware_decision_time():
    with pytest.raises(ValueError):
        obs.observations_available([], datetime(2026, 9, 8, 12, 0))


# --- serialisation and validation robustness ------------------------------

def test_round_trip_serialisation(tmp_path):
    parsed = obs.read_jsonl(FIXTURE)
    target = obs.write_jsonl(tmp_path / "round_trip.jsonl", parsed)
    reparsed = obs.read_jsonl(target)
    assert [obs.record_to_dict(r) for r in parsed] == [
        obs.record_to_dict(r) for r in reparsed
    ]


def test_bad_enum_is_reported_with_file_and_line(tmp_path):
    payload = _base_payload(parameter="Ni")
    target = tmp_path / "bad.jsonl"
    target.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(obs.ObservationValidationError) as excinfo:
        obs.read_jsonl(target)
    assert "bad.jsonl:1" in str(excinfo.value)


def test_bad_timestamp_is_reported_with_file_and_line(tmp_path):
    payload = _base_payload(observed_at_utc="2026-09-08T06:00:00")
    target = tmp_path / "bad_time.jsonl"
    target.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(obs.ObservationValidationError) as excinfo:
        obs.read_jsonl(target)
    assert "bad_time.jsonl:1" in str(excinfo.value)


def test_enum_membership_is_checked_without_jsonschema(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "jsonschema":
            raise ModuleNotFoundError("jsonschema disabled for this test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # Without jsonschema the same rules must still bite.
    with pytest.raises(obs.ObservationValidationError):
        obs.validate_record_dict(_base_payload(matrix="lava"))
    with pytest.raises(obs.ObservationValidationError):
        obs.validate_record_dict(
            _base_payload(qualifier="quantified", value=1.0, lower_bound=0.0)
        )
    obs.validate_record_dict(_base_payload())


def test_schema_ships_inside_the_package():
    # The packaging defect the audit found: the schema used to live outside
    # src/, so an installed wheel could not load it.
    assert obs.SCHEMA_PATH.exists()
    assert "reactive_seabed_mat" in obs.SCHEMA_PATH.parts
    schema = obs.load_schema()
    assert schema["title"].startswith("Reactive seabed mat observation record")
    assert "quantity_kind" in schema["required"]
    assert "provenance" in schema["required"]


def test_fractions_stay_distinct():
    labile = obs.record_from_dict(_base_payload(record_id="L", fraction="labile"))
    dgt = obs.record_from_dict(_base_payload(record_id="D", fraction="dgt_labile"))
    total = obs.record_from_dict(
        _base_payload(record_id="T", fraction="total_recoverable")
    )
    assert labile.fraction is Fraction.LABILE
    assert dgt.fraction is Fraction.DGT_LABILE
    assert total.fraction is Fraction.TOTAL_RECOVERABLE
    assert len({labile.fraction, dgt.fraction, total.fraction}) == 3


def test_parameter_and_datum_enums_round_trip():
    record = obs.record_from_dict(_base_payload(data_origin="laboratory"))
    assert record.parameter is Parameter.PB
    assert record.data_origin is DataOrigin.LABORATORY
    assert record.vertical_datum is VerticalDatum.SEABED
