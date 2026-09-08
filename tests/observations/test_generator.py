"""The synthetic generator: does it emit records the contract accepts, and does
it keep the censoring ladder honest?

These are the first tests this code has ever had.  The inherited version was
about 1 950 lines with no consumer and no test, so nothing here may be taken on
trust.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from reactive_seabed_mat.config import ObservationConfig
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
)
from reactive_seabed_mat.observations import generator as gen
from reactive_seabed_mat.observations import records as obs
from reactive_seabed_mat.units import (
    from_si_areal_flux,
    from_si_solid_loading,
    to_si_areal_flux,
    to_si_solid_loading,
)

DAY = 86400.0
YEAR = 365.25 * DAY
START = datetime(2026, 9, 8, tzinfo=timezone.utc)


# --- every record validates against the frozen schema ----------------------

def test_every_generated_record_validates_through_the_public_entry_point(small_stream):
    """The whole short stream, through ``record_from_dict`` with validation on.

    This deliberately uses the public, uncached path: the point is that the
    coordinator's own validator accepts every record, not that the branch's
    cached shim does.
    """
    assert small_stream, "the stream must not be empty"
    for record in small_stream:
        payload = obs.record_to_dict(record)
        rebuilt = obs.record_from_dict(payload, validate=True)
        assert obs.record_to_dict(rebuilt) == payload


def test_stream_round_trips_through_jsonl(small_stream, tmp_path):
    target = obs.write_jsonl(tmp_path / "stream.jsonl", small_stream)
    reparsed = obs.read_jsonl(target)
    assert [obs.record_to_dict(r) for r in small_stream] == [
        obs.record_to_dict(r) for r in reparsed
    ]


def test_record_ids_are_unique_across_chemistry_and_condition(small_stream):
    ids = [record.record_id for record in small_stream]
    assert len(set(ids)) == len(ids)


def test_generation_is_deterministic_for_a_seed(small_config, small_scene):
    first = gen.ObservationGenerator(small_config, seed=4242, start_utc=START).generate(
        small_scene, 40.0 * DAY
    )
    second = gen.ObservationGenerator(small_config, seed=4242, start_utc=START).generate(
        small_scene, 40.0 * DAY
    )
    assert [obs.record_to_dict(r) for r in first] == [
        obs.record_to_dict(r) for r in second
    ]


def test_a_different_seed_changes_the_numbers(small_config, small_scene):
    first = gen.ObservationGenerator(small_config, seed=1, start_utc=START).generate(
        small_scene, 40.0 * DAY
    )
    second = gen.ObservationGenerator(small_config, seed=2, start_utc=START).generate(
        small_scene, 40.0 * DAY
    )
    values_a = [r.value for r in first if r.value is not None]
    values_b = [r.value for r in second if r.value is not None]
    assert values_a != values_b


# --- the cached validator is the coordinator's validator -------------------

_BAD_PAYLOAD_CASES = [
    ("bad enum", {"parameter": "Ni"}),
    ("bad quantity kind", {"quantity_kind": "vibes"}),
    ("quantified without a value", {"value": None}),
    ("quantified with an interval", {"lower_bound": 0.0, "upper_bound": 1.0}),
    ("non-detect with a value", {"qualifier": "below_lod", "value": 3.0,
                                 "lower_bound": 0.0, "upper_bound": 12.0}),
    ("non-detect without an interval", {"qualifier": "below_lod", "value": None}),
    ("above range with an upper bound", {"qualifier": "above_range", "value": None,
                                         "lower_bound": 1.0, "upper_bound": 2.0}),
    ("categorical without a class", {"qualifier": "categorical", "value": None,
                                     "quantity_kind": "categorical", "unit": "class",
                                     "condition_class": None}),
    ("missing with the wrong flag", {"qualifier": "missing", "value": None,
                                     "quality_flag": 1}),
    ("depth without a datum", {"vertical_datum": None}),
    ("flux in a concentration unit", {"quantity_kind": "areal_flux", "unit": "ng/L"}),
    ("length in a mass unit", {"quantity_kind": "length", "unit": "kg"}),
    ("available before observed", {"available_at_utc": "2026-09-07T00:00:00Z"}),
    ("naive timestamp", {"observed_at_utc": "2026-09-08T06:00:00"}),
    ("negative uncertainty", {"uncertainty_std": -1.0}),
    ("missing required field", {"method_id": None}),
]


def _reference_payload(**overrides):
    payload = {
        "record_id": "V0001",
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
    if overrides.get("method_id", "keep") is None:
        payload.pop("method_id")
    return payload


def _accepts(validate) -> bool:
    try:
        validate()
    except Exception:  # noqa: BLE001 - the point is only accept vs reject
        return False
    return True


@pytest.mark.parametrize("label,overrides", _BAD_PAYLOAD_CASES, ids=[c[0] for c in _BAD_PAYLOAD_CASES])
def test_cached_validator_rejects_exactly_what_the_public_one_rejects(label, overrides):
    """The speed-up must not weaken a single rule.

    ``jsonschema.validate`` recompiles the schema on every call (38.7 ms per
    record here, against 0.57 ms for a compiled validator).  The branch caches
    the compiled validator; this test is what makes that safe.
    """
    assert gen.CACHED_VALIDATOR.available, "the cached validator must be usable"
    payload = _reference_payload(**overrides)
    slow = _accepts(lambda: obs.validate_record_dict(payload))
    fast = _accepts(lambda: gen.CACHED_VALIDATOR.validate(payload))
    assert slow is False, f"{label}: the public validator should reject this"
    assert fast == slow, f"{label}: the cached validator disagrees with the public one"


def test_cached_validator_accepts_what_the_public_one_accepts():
    payload = _reference_payload()
    obs.validate_record_dict(payload)
    gen.CACHED_VALIDATOR.validate(payload)


def test_slow_validation_can_be_forced(small_config, small_scene):
    generator = gen.ObservationGenerator(
        small_config, seed=3, start_utc=START, fast_validation=False
    )
    records = generator.porewater_records(small_scene, 20.0 * DAY)
    assert records
    assert generator.fast_validation is False


# --- the censoring ladder ---------------------------------------------------

def test_every_qualifier_stays_distinct_in_one_stream(censoring_stream):
    """quantified / below_lod / below_loq / above_range / categorical / missing.

    All six appear, and none of them is silently turned into another.  The
    stream is built to cross every threshold rather than hoping it happens to.
    """
    seen = {record.qualifier for record in censoring_stream}
    assert seen == {
        Qualifier.QUANTIFIED,
        Qualifier.BELOW_LOD,
        Qualifier.BELOW_LOQ,
        Qualifier.ABOVE_RANGE,
        Qualifier.CATEGORICAL,
        Qualifier.MISSING,
    }


def test_a_ramp_crosses_the_thresholds_in_order(censoring_stream):
    """The ladder is monotonic in the true value, in one channel, in time."""
    probe = sorted(
        (
            record
            for record in censoring_stream
            if record.acquisition_kind is AcquisitionKind.IN_SITU_SENSOR
            and record.is_metal
            and record.qualifier is not Qualifier.MISSING
        ),
        key=lambda record: record.observed_at_utc,
    )
    assert probe
    order = {
        Qualifier.BELOW_LOD: 0,
        Qualifier.BELOW_LOQ: 1,
        Qualifier.QUANTIFIED: 2,
        Qualifier.ABOVE_RANGE: 3,
    }
    first_seen = {}
    for record in probe:
        first_seen.setdefault(record.qualifier, record.observed_at_utc)
    ordered = sorted(first_seen, key=lambda qualifier: first_seen[qualifier])
    assert [order[qualifier] for qualifier in ordered] == sorted(
        order[qualifier] for qualifier in ordered
    )


def test_the_six_qualifiers_carry_different_payload_shapes(censoring_stream):
    by_qualifier: dict[Qualifier, list] = {}
    for record in censoring_stream:
        by_qualifier.setdefault(record.qualifier, []).append(record)

    for record in by_qualifier[Qualifier.QUANTIFIED]:
        assert record.value is not None
        assert record.lower_bound is None and record.upper_bound is None
    for qualifier in (Qualifier.BELOW_LOD, Qualifier.BELOW_LOQ):
        for record in by_qualifier[qualifier]:
            assert record.value is None
            assert record.lower_bound is not None and record.upper_bound is not None
            assert record.upper_bound >= record.lower_bound
    for record in by_qualifier[Qualifier.ABOVE_RANGE]:
        assert record.value is None
        assert record.lower_bound is not None
        assert record.upper_bound is None, "above range is a LOWER bound only"
    for record in by_qualifier[Qualifier.CATEGORICAL]:
        assert record.value is None
        assert record.condition_class
        assert record.quantity_kind is QuantityKind.CATEGORICAL
    for record in by_qualifier[Qualifier.MISSING]:
        assert record.value is None
        assert record.lower_bound is None and record.upper_bound is None
        assert record.quality_flag is QualityFlag.MISSING
        assert not record.carries_chemical_information


def test_a_non_detect_is_never_a_zero(multi_year_stream):
    censored = [r for r in multi_year_stream if r.is_censored]
    assert censored
    assert all(record.value is None for record in censored)
    assert all(record.carries_chemical_information for record in censored if record.is_metal)


def test_missing_is_not_a_non_detect(multi_year_stream):
    missing = [r for r in multi_year_stream if r.qualifier is Qualifier.MISSING]
    assert missing
    assert not any(record.is_censored for record in missing)


def test_censoring_ladder_boundaries():
    factory = gen.SyntheticRecordFactory(
        ObservationConfig(), seed=1, start_utc=START, record_id_prefix="X"
    )
    below_lod = factory.censor(0.5, lod=1.0, loq=4.0, sigma_rel=0.1, range_top=100.0)
    below_loq = factory.censor(2.0, lod=1.0, loq=4.0, sigma_rel=0.1, range_top=100.0)
    quantified = factory.censor(9.0, lod=1.0, loq=4.0, sigma_rel=0.1, range_top=100.0)
    above = factory.censor(150.0, lod=1.0, loq=4.0, sigma_rel=0.1, range_top=100.0)
    assert below_lod["qualifier"] == Qualifier.BELOW_LOD.value
    assert below_lod["upper_bound"] == 1.0 and below_lod["value"] is None
    assert below_loq["qualifier"] == Qualifier.BELOW_LOQ.value
    assert (below_loq["lower_bound"], below_loq["upper_bound"]) == (1.0, 4.0)
    assert quantified["qualifier"] == Qualifier.QUANTIFIED.value
    assert quantified["value"] == 9.0
    assert above["qualifier"] == Qualifier.ABOVE_RANGE.value
    assert above["lower_bound"] == 100.0 and above["upper_bound"] is None


# --- the channels themselves ------------------------------------------------

def test_the_stream_contains_every_required_channel(small_stream):
    channels = {
        (record.parameter.value, record.quantity_kind, record.matrix)
        for record in small_stream
    }
    assert ("Pb", QuantityKind.AQUEOUS_CONCENTRATION, Matrix.POREWATER) in channels
    assert ("Pb", QuantityKind.AQUEOUS_CONCENTRATION, Matrix.BOTTOM_WATER) in channels
    assert ("Pb", QuantityKind.AREAL_FLUX, Matrix.BOTTOM_WATER) in channels
    assert ("Pb", QuantityKind.ACCUMULATED_MASS, Matrix.POREWATER) in channels
    assert ("Hg", QuantityKind.AQUEOUS_CONCENTRATION, Matrix.POREWATER) in channels


def test_benthic_chamber_records_carry_area_and_window(small_stream):
    chamber = [
        r for r in small_stream
        if r.acquisition_kind is AcquisitionKind.BENTHIC_CHAMBER
    ]
    assert chamber
    for record in chamber:
        assert record.chamber_area_m2 is not None and record.chamber_area_m2 > 0
        assert record.sampling_start_utc is not None
        assert record.sampling_end_utc is not None
        assert record.sampling_end_utc > record.sampling_start_utc
        assert record.quantity_kind is QuantityKind.AREAL_FLUX
        assert record.unit == "ug/m2/d"


def test_a_chamber_record_without_area_or_window_is_rejected_by_the_contract():
    """The schema and the semantic rules both refuse an uninterpretable flux."""
    base = _reference_payload(
        record_id="BC_BAD",
        quantity_kind="areal_flux",
        unit="ug/m2/d",
        acquisition_kind="benthic_chamber",
        matrix="bottom_water",
        fraction="total_recoverable",
        value=2.6,
        uncertainty_std=0.9,
        sampling_start_utc="2026-09-08T00:00:00Z",
        sampling_end_utc="2026-09-08T06:00:00Z",
        chamber_area_m2=0.196,
    )
    obs.record_from_dict(base)  # the well-formed one is accepted

    without_area = dict(base, chamber_area_m2=None)
    with pytest.raises(obs.ObservationValidationError):
        obs.record_from_dict(without_area)

    without_window = dict(base, sampling_start_utc=None, sampling_end_utc=None)
    with pytest.raises(obs.ObservationValidationError):
        obs.record_from_dict(without_window)


def test_dgt_records_are_an_accumulated_mass_over_a_window(small_stream):
    dgt = [
        r for r in small_stream
        if r.acquisition_kind is AcquisitionKind.PASSIVE_SAMPLER
    ]
    assert dgt
    for record in dgt:
        assert record.quantity_kind is QuantityKind.ACCUMULATED_MASS
        assert record.unit == "ng"
        assert record.fraction is Fraction.DGT_LABILE
        assert record.sampling_start_utc is not None
        assert record.sampling_end_utc is not None


def test_a_saturated_dgt_is_an_above_range_lower_bound(multi_year_stream):
    """A sediment-face DGT exhausts its binding gel; that is a bound, not a number."""
    saturated = [
        r for r in multi_year_stream
        if r.acquisition_kind is AcquisitionKind.PASSIVE_SAMPLER
        and r.qualifier is Qualifier.ABOVE_RANGE
    ]
    assert saturated, "the porewater DGT must saturate somewhere in four years"
    for record in saturated:
        assert record.value is None
        assert record.lower_bound is not None
        assert record.upper_bound is None


def test_porewater_records_are_the_driving_boundary_condition(small_stream):
    porewater = [
        r for r in small_stream
        if r.matrix is Matrix.POREWATER
        and r.is_metal
        and r.quantity_kind is QuantityKind.AQUEOUS_CONCENTRATION
    ]
    assert porewater
    for record in porewater:
        assert record.tile_id, "porewater beneath a tile must name the tile"
        assert record.vertical_datum is not None
        assert record.data_origin is DataOrigin.LABORATORY
        assert record.available_at_utc > record.observed_at_utc, "laboratory latency"


def test_methylmercury_is_a_separate_risk_channel(small_stream):
    mehg = [r for r in small_stream if r.fraction is Fraction.METHYLMERCURY]
    assert mehg
    for record in mehg:
        assert record.parameter is Parameter.HG
        assert "risk" in (record.source_ref or "").lower()


def test_media_assay_uses_the_solid_loading_ladder_not_a_hard_coded_factor():
    """The inherited version hard-coded ``1.0e-9`` instead of the ladder."""
    config = ObservationConfig()
    generator = gen.ObservationGenerator(
        config,
        seed=5,
        start_utc=START,
        assumptions=gen.GeneratorAssumptions(media_assay_relative_noise=0.0),
    )
    batch = gen.MediaBatch(
        media_id="media_A0",
        tile_id="tile_1_1",
        installed_at_utc=START,
        retrieved_at_utc=START + timedelta(days=30),
        loading_kg_per_kg={"Pb": 4.15e-4},
    )
    record = generator.media_assay_record(batch, "Pb", START + timedelta(days=30))
    assert record.unit == "ng/g"
    assert record.value == pytest.approx(from_si_solid_loading(4.15e-4, "ng/g"))
    assert to_si_solid_loading(record.value, record.unit) == pytest.approx(4.15e-4)
    assert record.media_id == "media_A0"
    assert record.tile_id == "tile_1_1"


def test_flux_records_convert_back_to_the_scene_value():
    """A chamber record must be the scene's flux, on the flux ladder."""
    config = ObservationConfig(chamber_deployment_period_s=10.0 * DAY)
    scene = gen.constant_mat_scene(
        START,
        30.0 * DAY,
        flux_out_kg_per_m2_per_s={"Pb": 3.0e-12, "Hg": 1.0e-13},
    )
    generator = gen.ObservationGenerator(
        config,
        seed=9,
        start_utc=START,
        assumptions=gen.GeneratorAssumptions(report_uncertainty_std=True),
    )
    records = [
        r for r in generator.benthic_chamber_records(scene, 30.0 * DAY)
        if r.parameter is Parameter.PB and r.value is not None
    ]
    assert records
    recovered = [to_si_areal_flux(r.value, r.unit) for r in records]
    # 35 % relative noise is the configured chamber assumption.
    assert all(1.0e-12 < value < 9.0e-12 for value in recovered)
    assert from_si_areal_flux(3.0e-12, "ug/m2/d") == pytest.approx(259.2, rel=1e-6)


# --- provenance -------------------------------------------------------------

def test_every_record_declares_pathway_and_truth_status_separately(small_stream):
    for record in small_stream:
        assert record.provenance is ProvenanceLabel.SYNTHETIC_DEMO
        assert record.data_origin in (
            DataOrigin.SENSOR,
            DataOrigin.LABORATORY,
            DataOrigin.FIELD_SURVEY,
        )


def test_a_fabricated_laboratory_record_is_labelled_as_such(small_stream):
    laboratory = [r for r in small_stream if r.data_origin is DataOrigin.LABORATORY]
    assert laboratory
    assert all(r.provenance is ProvenanceLabel.SYNTHETIC_DEMO for r in laboratory)


def test_every_record_carries_a_source_reference(small_stream):
    assert all(record.source_ref for record in small_stream)


# --- dropout, drift and stuck values ---------------------------------------

def test_dropout_window_produces_missing_records(small_scene):
    config = ObservationConfig(
        bottom_water_probe_period_s=DAY,
        sensor_dropout_window_s=(10.0 * DAY, 20.0 * DAY),
        missing_probability=0.0,
    )
    generator = gen.ObservationGenerator(config, seed=3, start_utc=START)
    records = generator.bottom_water_records(small_scene, 40.0 * DAY)
    missing = [r for r in records if r.qualifier is Qualifier.MISSING]
    assert missing
    for record in missing:
        elapsed = (record.observed_at_utc - START).total_seconds()
        assert 10.0 * DAY <= elapsed <= 20.0 * DAY


def test_drift_moves_the_reported_value(small_scene):
    plain = ObservationConfig(bottom_water_probe_period_s=DAY, missing_probability=0.0)
    drifting = replace(
        plain, sensor_drift_start_s=5.0 * DAY, sensor_drift_per_s=2.0e-6
    )
    baseline = gen.ObservationGenerator(plain, seed=8, start_utc=START).bottom_water_records(
        small_scene, 40.0 * DAY
    )
    drifted = gen.ObservationGenerator(drifting, seed=8, start_utc=START).bottom_water_records(
        small_scene, 40.0 * DAY
    )
    last_plain = [r.value for r in baseline if r.value is not None][-1]
    last_drift = [r.value for r in drifted if r.value is not None][-1]
    assert last_drift > last_plain * 2.0


def test_stuck_window_repeats_one_value(small_scene):
    config = ObservationConfig(bottom_water_probe_period_s=DAY, missing_probability=0.0)
    assumptions = gen.GeneratorAssumptions(
        stuck_window_s=(5.0 * DAY, 20.0 * DAY), stuck_value_ng_per_l=148.2
    )
    records = gen.ObservationGenerator(
        config, seed=8, start_utc=START, assumptions=assumptions
    ).bottom_water_records(small_scene, 40.0 * DAY)
    stuck = [r.value for r in records if r.value == pytest.approx(148.2)]
    assert len(stuck) >= 5


# --- the scene adapters -----------------------------------------------------

def test_synthetic_history_keeps_the_four_modes_independent(multi_year_scene):
    displaced = multi_year_scene.sample_at(
        "tile_0_0", START + timedelta(seconds=2.0 * YEAR)
    )
    torn = multi_year_scene.sample_at("tile_1_1", START + timedelta(seconds=3.0 * YEAR))
    buried = multi_year_scene.sample_at("tile_2_2", START + timedelta(seconds=2.0 * YEAR))
    assert displaced.displaced and displaced.coverage_fraction == 0.0
    assert torn.integrity_index == pytest.approx(0.65)
    assert not torn.displaced
    assert buried.burial_depth_m == pytest.approx(0.045)
    assert buried.integrity_index == 1.0, "burial is not damage"
    # the chemistry of the buried tile is untouched by its burial
    assert buried.sorbed_kg_per_kg["Pb"] > 0.0


def test_burial_reduces_the_apparent_flux(multi_year_scene):
    """The trap the whole design exists to avoid, reproduced in the history."""
    before = multi_year_scene.sample_at(
        "tile_2_2", START + timedelta(seconds=0.9 * YEAR)
    )
    after = multi_year_scene.sample_at(
        "tile_2_2", START + timedelta(seconds=1.1 * YEAR)
    )
    assert after.burial_depth_m > before.burial_depth_m
    assert after.flux_out_kg_per_m2_per_s["Pb"] < before.flux_out_kg_per_m2_per_s["Pb"]


def test_a_displaced_tile_emits_the_bare_flux(multi_year_scene):
    sample = multi_year_scene.sample_at(
        "tile_0_0", START + timedelta(seconds=2.0 * YEAR)
    )
    assert sample.flux_out_kg_per_m2_per_s["Pb"] == pytest.approx(
        sample.bare_flux_kg_per_m2_per_s["Pb"]
    )


def test_replacement_retires_the_old_media_batch(multi_year_scene):
    retired = [
        batch for batch in multi_year_scene.media
        if batch.tile_id == "tile_1_1" and batch.retrieved_at_utc is not None
    ]
    assert len(retired) == 1
    assert retired[0].media_id == "media_A0"
    assert retired[0].loading_kg_per_kg["Pb"] > 0.0
    current = multi_year_scene.media_in_tile(
        "tile_1_1", START + timedelta(seconds=3.5 * YEAR)
    )
    assert current is not None and current.media_id == "media_B1"


def test_scene_from_layer_history_refuses_a_step_without_its_exchange():
    """The integration seam with feat/reactive-layer, and its refusal."""
    import numpy as np

    from reactive_seabed_mat.contracts import (
        LayerStep,
        MatTileGeometry,
        MatTileState,
    )

    geometry = MatTileGeometry(
        width_m=10.0, length_m=10.0, thickness_m=0.01, x_m=0.0, y_m=0.0
    )
    state = MatTileState(
        tile_id="tile_0_0",
        media_id="media_A0",
        installed_at_utc=START,
        geometry=geometry,
        porewater_kg_per_m3={"Pb": np.zeros(4)},
        sorbed_kg_per_kg={"Pb": np.zeros(4)},
    )
    step = LayerStep(
        new_state=state,
        flux_in_kg_per_m2_per_s={"Pb": 1.0e-10},
        flux_out_kg_per_m2_per_s={"Pb": 1.0e-12},
        retained_delta_kg_per_m2={"Pb": 0.0},
        released_kg_per_m2={"Pb": 0.0},
        exchange=None,
    )
    with pytest.raises(ValueError, match="SeabedExchange"):
        gen.scene_from_layer_history({"tile_0_0": [(START, step)]})
