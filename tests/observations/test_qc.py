"""Quality control: the checks, the escalation rule and the new channels."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from reactive_seabed_mat.contracts import (
    ObservationRecord,
    Parameter,
    Qualifier,
    QualityFlag,
    QuantityKind,
)
from reactive_seabed_mat.observations import qc
from reactive_seabed_mat.observations import records as obs

DAY = 86400.0
START = datetime(2026, 9, 8, tzinfo=timezone.utc)


def _payload(**overrides):
    payload = {
        "record_id": "Q0001",
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


def _record(**overrides) -> ObservationRecord:
    return obs.record_from_dict(_payload(**overrides))


def _series(values, *, step_h=6, **overrides) -> list[ObservationRecord]:
    records = []
    for index, value in enumerate(values):
        moment = START + timedelta(hours=index * step_h)
        stamp = moment.isoformat().replace("+00:00", "Z")
        records.append(
            _record(
                record_id=f"S{index:03d}",
                observed_at_utc=stamp,
                available_at_utc=stamp,
                value=value,
                **overrides,
            )
        )
    return records


# --- band keys --------------------------------------------------------------

def test_band_key_is_specific_before_general():
    record = _record()
    assert qc.band_keys(record) == (
        "Pb|aqueous_concentration|bottom_water",
        "Pb|aqueous_concentration",
        "Pb",
    )


def test_porewater_and_bottom_water_use_different_bands():
    """One band per parameter cannot work: these differ by 10^5."""
    bottom = _record(value=4000.0)
    porewater = _record(
        record_id="Q_PW",
        matrix="porewater",
        unit="ug/L",
        fraction="dissolved_filtered",
        acquisition_kind="grab_sample",
        data_origin="laboratory",
        sensor_id=None,
        sample_id="PW_1",
        value=940.0,
        vertical_datum="mat_base",
        depth_m=0.05,
    )
    assert qc.gross_range_check(bottom)[0] is QualityFlag.PASSED
    assert qc.gross_range_check(porewater)[0] is QualityFlag.PASSED
    # ... and the porewater value would have failed the bottom-water band.
    low, high = qc.DEMO_THRESHOLDS.gross_range["Pb|aqueous_concentration|bottom_water"]
    assert 940.0 * 1000.0 > high, "940 ug/L is far outside the bottom-water band"


# --- individual checks ------------------------------------------------------

def test_gross_range_flags_an_impossible_value():
    flag, reason = qc.gross_range_check(_record(value=9.0e6))
    assert flag is QualityFlag.FAILED
    assert "gross range" in reason


def test_gross_range_converts_within_a_ladder():
    record = _record(
        record_id="Q_CM",
        parameter="burial_depth",
        quantity_kind="length",
        unit="cm",
        matrix="mat_structure",
        fraction="not_applicable",
        acquisition_kind="bathymetric_survey",
        data_origin="field_survey",
        sensor_id=None,
        value=4.5,
        vertical_datum="mat_top",
        depth_m=0.0,
    )
    flag, _ = qc.gross_range_check(record)
    assert flag is QualityFlag.PASSED
    # 4.5 m of burial would be at the edge of the band; 4500 cm is not.
    flag_big, _ = qc.gross_range_check(
        obs.record_from_dict(
            _payload(
                record_id="Q_CM2",
                parameter="burial_depth",
                quantity_kind="length",
                unit="cm",
                matrix="mat_structure",
                fraction="not_applicable",
                acquisition_kind="bathymetric_survey",
                data_origin="field_survey",
                sensor_id=None,
                value=4500.0,
                vertical_datum="mat_top",
                depth_m=0.0,
            )
        )
    )
    assert flag_big is QualityFlag.FAILED


def test_a_cross_ladder_unit_is_not_checked_instead_of_being_mis_checked():
    record = _record(
        record_id="Q_SOLID",
        quantity_kind="solid_loading",
        unit="ng/g",
        matrix="sorbent",
        fraction="sorbed_total",
        acquisition_kind="media_assay",
        data_origin="laboratory",
        sensor_id=None,
        media_id="media_A0",
        value=415000.0,
        depth_m=0.0,
        vertical_datum="mat_top",
    )
    flag, reason = qc.gross_range_check(record)
    assert flag is QualityFlag.PASSED
    assert "band" in reason


def test_spike_needs_both_neighbours():
    flag, reason = qc.spike_check(_record(), None, None)
    assert flag is QualityFlag.NOT_EVALUATED
    assert "neighbours" in reason


def test_spike_flags_an_excursion():
    series = _series([100.0, 4000.0, 110.0])
    flag, _ = qc.spike_check(series[1], series[0], series[2])
    assert flag is QualityFlag.SUSPECT


def test_spike_uses_a_relative_allowance_on_a_noisy_channel():
    """An absolute threshold alone fails a third of a 20 %-noise channel."""
    quiet = _series([100.0, 350.0, 110.0])
    loud = _series([2400.0, 2900.0, 2500.0])
    assert qc.spike_check(quiet[1], quiet[0], quiet[2])[0] is QualityFlag.PASSED
    assert qc.spike_check(loud[1], loud[0], loud[2])[0] is QualityFlag.PASSED
    # the same 450 ng/L excursion at low concentration is still caught
    caught = _series([100.0, 900.0, 110.0])
    assert qc.spike_check(caught[1], caught[0], caught[2])[0] is QualityFlag.SUSPECT


@pytest.mark.parametrize(
    "parameter,quantity_kind,unit,values",
    [
        ("mat_displacement", "length", "m", [0.1, 5.0, 5.1]),
        ("mat_coverage_fraction", "fraction", "1", [1.0, 0.0, 0.0]),
        ("burial_depth", "length", "cm", [0.5, 12.0, 12.5]),
    ],
)
def test_a_step_process_is_not_spike_tested(parameter, quantity_kind, unit, values):
    """A tile can genuinely move, tear or be buried between two surveys.

    Flagging that step as suspect would push the evidence of failure out of the
    likelihood, which is the opposite of what QC is for.
    """
    series = [
        obs.record_from_dict(
            _payload(
                record_id=f"STEP{index}",
                sensor_id=None,
                station_id="SURVEY_01",
                observed_at_utc=(START + timedelta(days=90 * index))
                .isoformat().replace("+00:00", "Z"),
                available_at_utc=(START + timedelta(days=90 * index + 1))
                .isoformat().replace("+00:00", "Z"),
                parameter=parameter,
                quantity_kind=quantity_kind,
                unit=unit,
                matrix="mat_structure",
                fraction="not_applicable",
                acquisition_kind="bathymetric_survey",
                data_origin="field_survey",
                method_id="SIM_MULTIBEAM_V1",
                calibration_id=None,
                value=value,
                uncertainty_std=0.01,
                depth_m=0.0,
                vertical_datum="mat_top",
            )
        )
        for index, value in enumerate(values)
    ]
    flag, reason = qc.spike_check(series[1], series[0], series[2])
    assert flag is QualityFlag.NOT_EVALUATED
    assert "physical event" in reason
    report = qc.run_qc(series)
    assert all(
        not report.outcomes[record.record_id].failed_checks for record in series
    )


def test_stuck_value_detects_a_flat_line():
    series = _series([148.2] * 6)
    results = qc.stuck_value_check(series)
    assert len(results) == 6
    assert all(flag is QualityFlag.FAILED for flag, _ in results.values())


def test_stuck_value_ignores_a_short_run():
    series = _series([148.2] * 3 + [200.0, 250.0])
    assert qc.stuck_value_check(series) == {}


def test_vocabulary_check_rejects_an_invented_class():
    good = _record(
        record_id="Q_CLASS",
        parameter="mat_damage_class",
        quantity_kind="categorical",
        unit="class",
        matrix="mat_structure",
        fraction="not_applicable",
        acquisition_kind="rov_inspection",
        data_origin="field_survey",
        sensor_id=None,
        qualifier="categorical",
        value=None,
        uncertainty_std=None,
        condition_class="punctured",
        depth_m=0.0,
        vertical_datum="mat_top",
    )
    assert qc.vocabulary_check(good)[0] is QualityFlag.PASSED
    bad = obs.record_from_dict(
        _payload(
            record_id="Q_CLASS2",
            parameter="mat_damage_class",
            quantity_kind="categorical",
            unit="class",
            matrix="mat_structure",
            fraction="not_applicable",
            acquisition_kind="rov_inspection",
            data_origin="field_survey",
            sensor_id=None,
            qualifier="categorical",
            value=None,
            uncertainty_std=None,
            condition_class="mostly_fine",
            depth_m=0.0,
            vertical_datum="mat_top",
        )
    )
    flag, reason = qc.vocabulary_check(bad)
    assert flag is QualityFlag.FAILED
    assert "controlled vocabulary" in reason


# --- escalation -------------------------------------------------------------

def test_escalation_is_one_way():
    series = _series([120.0, 130.0, 125.0], quality_flag=3)
    report = qc.run_qc(series)
    for record in series:
        outcome = report.outcomes[record.record_id]
        assert outcome.flag is QualityFlag.SUSPECT
        assert outcome.original_flag is QualityFlag.SUSPECT
        assert any("never clears" in reason for reason in outcome.reasons)


def test_missing_is_never_overwritten_by_a_check():
    stamp = "2026-09-08T06:00:00Z"
    record = _record(
        qualifier="missing", value=None, uncertainty_std=None, quality_flag=9,
        observed_at_utc=stamp, available_at_utc=stamp,
    )
    report = qc.run_qc([record])
    assert report.outcomes[record.record_id].flag is QualityFlag.MISSING


def test_a_censored_record_is_not_range_checked_as_a_value():
    record = _record(
        qualifier="below_lod", value=None, uncertainty_std=None,
        lower_bound=0.0, upper_bound=12.0,
    )
    report = qc.run_qc([record])
    outcome = report.outcomes[record.record_id]
    assert "censored" in outcome.checks["gross_range"]
    assert not outcome.failed_checks, "a bound must not be failed for lacking a value"
    assert outcome.usable


def test_an_above_range_record_is_not_range_checked_as_a_value():
    record = _record(
        qualifier="above_range", value=None, uncertainty_std=None,
        lower_bound=5000.0, upper_bound=None,
    )
    report = qc.run_qc([record])
    outcome = report.outcomes[record.record_id]
    assert not outcome.failed_checks
    assert outcome.usable
    assert "lower bound" in outcome.checks["gross_range"]


def test_a_record_that_passes_an_applicable_check_is_flagged_passed():
    """``NOT_EVALUATED`` is for a record no check applied to, not for one whose
    spike test happened to lack a neighbour."""
    record = _record()
    report = qc.run_qc([record])
    outcome = report.outcomes[record.record_id]
    assert outcome.checks["spike"].startswith("spike test needs")
    assert outcome.flag is QualityFlag.PASSED
    assert not outcome.failed_checks


def test_a_record_no_check_applies_to_stays_not_evaluated():
    record = _record(
        record_id="Q_UNCHECKED",
        parameter="mat_uplift",
        quantity_kind="length",
        unit="m",
        matrix="mat_structure",
        fraction="not_applicable",
        acquisition_kind="bathymetric_survey",
        data_origin="field_survey",
        sensor_id=None,
        value=0.02,
        uncertainty_std=0.01,
        depth_m=0.0,
        vertical_datum="mat_top",
    )
    report = qc.run_qc([record])
    outcome = report.outcomes[record.record_id]
    # a range band exists for mat_uplift, so remove it to reach the branch
    bare = qc.QCThresholds(
        gross_range={}, spike={}, stuck_tolerance={}, expected_unit={}
    )
    stripped = qc.run_qc([record], thresholds=bare)
    assert stripped.outcomes[record.record_id].flag is QualityFlag.NOT_EVALUATED
    assert outcome.flag is QualityFlag.PASSED


def test_apply_qc_flags_does_not_touch_the_originals():
    series = _series([148.2] * 6)
    report = qc.run_qc(series)
    updated = qc.apply_qc_flags(series, report)
    assert all(record.quality_flag is QualityFlag.PASSED for record in series)
    assert all(record.quality_flag is QualityFlag.FAILED for record in updated)


def test_qc_never_deletes_a_record(small_stream):
    report = qc.run_qc(small_stream)
    assert len(report.outcomes) == len(small_stream)


# --- health -----------------------------------------------------------------

def test_health_is_separate_from_material_state(small_stream):
    report = qc.run_qc(small_stream, now_utc=START + timedelta(days=41))
    for health in report.asset_health.values():
        assert not hasattr(health, "saturation")
        assert not hasattr(health, "loading")


def test_a_campaign_channel_is_not_stale_after_six_hours(small_stream):
    """A chamber deployed twice a year is not a broken sensor."""
    report = qc.run_qc(small_stream, now_utc=START + timedelta(days=41))
    chamber_assets = [
        health
        for key, health in report.asset_health.items()
        if key.startswith("tile:") or key.startswith("station:")
    ]
    assert chamber_assets
    assert any(health.max_data_age_s > 6.0 * 3600.0 for health in chamber_assets)


def test_a_stale_probe_is_reported(small_stream):
    report = qc.run_qc(small_stream, now_utc=START + timedelta(days=400))
    stale = report.stale_asset_keys()
    assert stale, "after 400 days nothing in a 40-day stream can be fresh"


def test_the_whole_stream_runs_through_qc(multi_year_stream):
    report = qc.run_qc(multi_year_stream, now_utc=START + timedelta(days=1500))
    assert len(report.outcomes) == len(multi_year_stream)
    assert report.asset_health
    assert all(
        outcome.flag in tuple(QualityFlag) for outcome in report.outcomes.values()
    )
