"""Mat-condition channels: the evidence that keeps the four modes apart.

The inherited stack had no concept of these at all, so every one of these
assertions is new ground.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from reactive_seabed_mat.config import DegradationEvent, ObservationConfig
from reactive_seabed_mat.contracts import (
    AcquisitionKind,
    DataOrigin,
    DegradationMode,
    Fraction,
    MAT_CONDITION_PARAMETERS,
    Matrix,
    Parameter,
    Qualifier,
    QualityFlag,
    QuantityKind,
)
from reactive_seabed_mat.observations import condition as cond
from reactive_seabed_mat.observations import generator as gen
from reactive_seabed_mat.observations import records as obs
from reactive_seabed_mat.units import to_si_length

DAY = 86400.0
YEAR = 365.25 * DAY
START = datetime(2026, 9, 8, tzinfo=timezone.utc)


# --- the vocabulary ---------------------------------------------------------

def test_damage_vocabulary_is_ordered_and_closed():
    assert cond.MAT_DAMAGE_CLASSES == (
        "intact", "abraded", "punctured", "torn", "lost"
    )
    severities = [cond.DAMAGE_CLASS_SEVERITY[name] for name in cond.MAT_DAMAGE_CLASSES]
    assert severities == sorted(severities)
    assert set(cond.DAMAGE_CLASS_INTEGRITY_BAND) == set(cond.MAT_DAMAGE_CLASSES)


def test_a_class_implies_an_interval_not_a_number():
    low, high = cond.integrity_band_for_class("punctured")
    assert low < high, "a class is a band, never a point value"
    assert 0.0 <= low <= 1.0 and 0.0 <= high <= 1.0


def test_an_unknown_class_is_refused_rather_than_mapped():
    with pytest.raises(KeyError):
        cond.integrity_band_for_class("mostly_fine")


def test_classes_get_worse_as_integrity_falls():
    order = [
        cond.DAMAGE_CLASS_SEVERITY[cond.damage_class_from_integrity(value)]
        for value in (1.0, 0.95, 0.7, 0.3, 0.05)
    ]
    assert order == sorted(order)
    assert cond.damage_class_from_integrity(1.0, displaced=True) == "lost"


# --- every condition record names its tile ---------------------------------

def test_every_condition_record_carries_a_tile_id(condition_stream):
    assert condition_stream
    for record in condition_stream:
        assert record.tile_id, (
            f"{record.record_id} ({record.parameter.value}) has no tile_id: "
            "failure is local, and an unattributed condition record cannot "
            "support a partial replacement"
        )


def test_condition_records_carry_no_chemistry(condition_stream):
    for record in condition_stream:
        assert not record.is_metal
        assert record.fraction is Fraction.NOT_APPLICABLE
        assert record.matrix is Matrix.MAT_STRUCTURE
        assert not record.carries_chemical_information


def test_condition_channels_cover_modes_three_and_four(condition_stream):
    parameters = {record.parameter for record in condition_stream}
    assert Parameter.MAT_DAMAGE_CLASS in parameters       # mode 4
    assert Parameter.MAT_COVERAGE_FRACTION in parameters  # modes 3 and 4
    assert Parameter.BURIAL_DEPTH in parameters           # mode 3
    assert Parameter.MAT_DISPLACEMENT in parameters       # mode 3
    assert Parameter.DIFFERENTIAL_HEAD in parameters      # mode 2
    modes = {
        cond.CONDITION_MODE[record.parameter.value]
        for record in condition_stream
        if record.parameter.value in cond.CONDITION_MODE
    }
    assert DegradationMode.DISPLACEMENT in modes
    assert DegradationMode.LOCAL_DAMAGE in modes
    assert DegradationMode.FOULING in modes
    assert DegradationMode.SATURATION not in modes, (
        "no condition channel may claim to measure chemical saturation"
    )


def test_every_condition_record_validates_against_the_frozen_schema(condition_stream):
    for record in condition_stream:
        payload = obs.record_to_dict(record)
        rebuilt = obs.record_from_dict(payload, validate=True)
        assert obs.record_to_dict(rebuilt) == payload


# --- the individual channels ------------------------------------------------

def test_damage_class_is_categorical_and_never_a_number(condition_stream):
    classes = [
        r for r in condition_stream if r.parameter is Parameter.MAT_DAMAGE_CLASS
    ]
    assert classes
    for record in classes:
        assert record.quantity_kind is QuantityKind.CATEGORICAL
        assert record.unit == "class"
        if record.qualifier is Qualifier.MISSING:
            continue
        assert record.qualifier is Qualifier.CATEGORICAL
        assert record.value is None
        assert record.condition_class in cond.MAT_DAMAGE_CLASSES
        assert record.acquisition_kind in (
            AcquisitionKind.ROV_INSPECTION, AcquisitionKind.DIVER_INSPECTION
        )
        assert record.data_origin is DataOrigin.FIELD_SURVEY


def test_coverage_is_a_fraction_between_zero_and_one(condition_stream):
    coverage = [
        r for r in condition_stream
        if r.parameter is Parameter.MAT_COVERAGE_FRACTION
        and r.qualifier is not Qualifier.MISSING
    ]
    assert coverage
    for record in coverage:
        assert record.quantity_kind is QuantityKind.FRACTION
        assert record.unit == "1"
        assert 0.0 <= record.value <= 1.0
        assert record.acquisition_kind is AcquisitionKind.BATHYMETRIC_SURVEY


def test_burial_is_reported_on_the_length_ladder_in_centimetres(condition_stream):
    burial = [
        r for r in condition_stream
        if r.parameter is Parameter.BURIAL_DEPTH
        and r.qualifier is not Qualifier.MISSING
    ]
    assert burial
    for record in burial:
        assert record.quantity_kind is QuantityKind.LENGTH
        assert record.unit == "cm"
        assert to_si_length(record.value, record.unit) == pytest.approx(
            record.value / 100.0
        )


def test_burial_record_says_it_is_not_success(condition_stream):
    burial = [r for r in condition_stream if r.parameter is Parameter.BURIAL_DEPTH]
    assert burial
    for record in burial:
        text = (record.source_ref or "").lower()
        if record.qualifier is Qualifier.MISSING:
            continue
        assert "reduces the apparent flux" in text
        assert "never be read as success" in text


def test_displacement_is_reported_in_metres(condition_stream):
    displacement = [
        r for r in condition_stream if r.parameter is Parameter.MAT_DISPLACEMENT
    ]
    assert displacement
    for record in displacement:
        assert record.unit == "m"
        assert record.acquisition_kind is AcquisitionKind.ACOUSTIC_POSITION


def test_differential_head_is_a_fouling_channel_with_no_chemistry(condition_stream):
    head = [r for r in condition_stream if r.parameter is Parameter.DIFFERENTIAL_HEAD]
    assert head
    for record in head:
        assert record.unit == "Pa"
        assert record.data_origin is DataOrigin.SENSOR
        assert record.sensor_id, "a continuous sensor must be identifiable"
        assert cond.CONDITION_MODE[record.parameter.value] is DegradationMode.FOULING


# --- the channels track the hidden state -----------------------------------

def test_the_condition_stream_reports_the_tile_that_was_displaced():
    events = (
        DegradationEvent(start_s=1.0 * YEAR, tile_id="tile_2_2", mode="displacement",
                         magnitude=1.0),
    )
    scene = gen.synthetic_mat_history(START, 2.0 * YEAR, events=events)
    config = ObservationConfig(survey_period_s=90.0 * DAY)
    assumptions = cond.ConditionAssumptions(
        misclassification_probability=0.0, survey_abort_probability=0.0
    )
    records = cond.MatConditionGenerator(
        config, seed=2, start_utc=START, assumptions=assumptions
    ).generate(scene, 2.0 * YEAR)

    late = START + timedelta(seconds=1.5 * YEAR)
    lost = [
        r for r in records
        if r.parameter is Parameter.MAT_DAMAGE_CLASS
        and r.observed_at_utc >= late
        and r.condition_class == "lost"
    ]
    assert {r.tile_id for r in lost} == {"tile_2_2"}, (
        "only the displaced tile may be reported as lost: failure is local"
    )
    coverage_late = {
        r.tile_id: r.value
        for r in records
        if r.parameter is Parameter.MAT_COVERAGE_FRACTION
        and r.observed_at_utc >= late
        and r.value is not None
    }
    assert coverage_late["tile_2_2"] < 0.2
    assert coverage_late["tile_0_0"] > 0.8


def test_differential_head_rises_with_fouling():
    scene = gen.synthetic_mat_history(START, 4.0 * YEAR)
    config = ObservationConfig()
    records = cond.MatConditionGenerator(
        config, seed=3, start_utc=START
    ).differential_head_records(scene, 4.0 * YEAR)
    first = [r for r in records if r.tile_id == "tile_0_0"][0]
    last = [r for r in records if r.tile_id == "tile_0_0"][-1]
    assert last.value > 2.0 * first.value, (
        "pore blockage must be visible in the head, which is what separates it "
        "from chemical saturation"
    )


def test_misclassification_is_possible_but_bounded():
    """An inspection class is a judgement, and the generator says so."""
    scene = gen.synthetic_mat_history(START, 6.0 * YEAR)
    config = ObservationConfig(survey_period_s=30.0 * DAY)
    assumptions = cond.ConditionAssumptions(
        misclassification_probability=1.0, survey_abort_probability=0.0
    )
    records = cond.MatConditionGenerator(
        config, seed=4, start_utc=START, assumptions=assumptions
    ).damage_class_records(scene, 6.0 * YEAR)
    reported = {r.condition_class for r in records}
    assert reported <= set(cond.MAT_DAMAGE_CLASSES)
    assert reported != {"intact"}, "with p=1 the reported class must move"


def test_an_aborted_survey_is_missing_not_a_zero():
    scene = gen.synthetic_mat_history(START, 4.0 * YEAR)
    config = ObservationConfig(survey_period_s=15.0 * DAY)
    assumptions = cond.ConditionAssumptions(survey_abort_probability=1.0)
    records = cond.MatConditionGenerator(
        config, seed=5, start_utc=START, assumptions=assumptions
    ).coverage_records(scene, 4.0 * YEAR)
    assert records
    for record in records:
        assert record.qualifier is Qualifier.MISSING
        assert record.value is None
        assert record.lower_bound is None and record.upper_bound is None
        assert record.quality_flag is QualityFlag.MISSING


def test_condition_parameters_are_the_contract_ones(condition_stream):
    reported = {
        record.parameter for record in condition_stream if record.is_mat_condition
    }
    assert reported <= MAT_CONDITION_PARAMETERS
    assert reported, "at least one contract mat-condition parameter must be reported"
