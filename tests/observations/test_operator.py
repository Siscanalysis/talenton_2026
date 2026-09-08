"""The observation operator: what may be compared with what, and what may not.

These tests encode the rules of ``docs/MODEL_SPEC.md`` section 8.  Several of
them exist because the inherited operator got the answer wrong: porewater was
rejected evidence, ``dgt_labile`` did not exist, an areal flux had no route at
all, and mat condition was not a concept.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from reactive_seabed_mat.contracts import (
    CONTEXT_PARAMETERS,
    DegradationMode,
    Fraction,
    MAT_CONDITION_PARAMETERS,
    Matrix,
    METAL_PARAMETERS,
    Parameter,
    Qualifier,
    QualityFlag,
    QuantityKind,
)
from reactive_seabed_mat.observations import operator as op
from reactive_seabed_mat.observations import qc
from reactive_seabed_mat.observations import records as obs
from reactive_seabed_mat.units import to_si_areal_flux, to_si_aqueous_concentration

DAY = 86400.0
YEAR = 365.25 * DAY
START = datetime(2026, 9, 8, tzinfo=timezone.utc)


def _payload(**overrides):
    payload = {
        "record_id": "O0001",
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
        "source_ref": "operator test",
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


def _record(**overrides):
    return obs.record_from_dict(_payload(**overrides))


def _porewater(**overrides):
    return _record(
        **{
            "record_id": "O_PW",
            "station_id": "ST_MAT_B",
            "sensor_id": None,
            "sample_id": "PW_0001",
            "tile_id": "tile_1_1",
            "matrix": "porewater",
            "unit": "ug/L",
            "fraction": "dissolved_filtered",
            "acquisition_kind": "grab_sample",
            "data_origin": "laboratory",
            "method_id": "SIM_LAB_ICPMS_DISSFILT_V1",
            "calibration_id": None,
            "value": 940.0,
            "uncertainty_std": 85.0,
            "depth_m": 0.01,
            "vertical_datum": "mat_base",
            "z_in_mat_m": 0.0,
            **overrides,
        }
    )


def _chamber(**overrides):
    return _record(
        **{
            "record_id": "O_BC",
            "station_id": "ST_MAT_C",
            "sensor_id": None,
            "sample_id": "BC_0001",
            "tile_id": "tile_2_2",
            "observed_at_utc": "2026-09-09T12:00:00Z",
            "available_at_utc": "2026-09-30T12:00:00Z",
            "sampling_start_utc": "2026-09-08T12:00:00Z",
            "sampling_end_utc": "2026-09-09T12:00:00Z",
            "quantity_kind": "areal_flux",
            "unit": "ug/m2/d",
            "matrix": "bottom_water",
            "fraction": "total_recoverable",
            "acquisition_kind": "benthic_chamber",
            "data_origin": "laboratory",
            "method_id": "SIM_BENTHIC_CHAMBER_V1",
            "calibration_id": None,
            "value": 2.6,
            "uncertainty_std": 0.9,
            "chamber_area_m2": 0.196,
            "depth_m": 0.0,
            "vertical_datum": "mat_top",
            **overrides,
        }
    )


def _dgt(**overrides):
    return _record(
        **{
            "record_id": "O_DGT",
            "station_id": "ST_MAT_B",
            "sensor_id": None,
            "sample_id": "DGT_0001",
            "tile_id": "tile_1_1",
            "observed_at_utc": "2026-09-11T09:00:00Z",
            "available_at_utc": "2026-10-02T09:00:00Z",
            "sampling_start_utc": "2026-09-08T09:00:00Z",
            "sampling_end_utc": "2026-09-11T09:00:00Z",
            "quantity_kind": "accumulated_mass",
            "unit": "ng",
            "matrix": "porewater",
            "fraction": "dgt_labile",
            "acquisition_kind": "passive_sampler",
            "data_origin": "laboratory",
            "method_id": "SIM_DGT_ACCUM_MASS_V1",
            "calibration_id": None,
            "value": 128.0,
            "uncertainty_std": 26.0,
            "quality_flag": 2,
            "depth_m": 0.01,
            "vertical_datum": "mat_base",
            **overrides,
        }
    )


def _assay(**overrides):
    return _record(
        **{
            "record_id": "O_MED",
            "station_id": "ST_MAT_B",
            "sensor_id": None,
            "sample_id": "MED_media_A0",
            "media_id": "media_A0",
            "tile_id": "tile_1_1",
            "quantity_kind": "solid_loading",
            "unit": "ng/g",
            "matrix": "sorbent",
            "fraction": "sorbed_total",
            "acquisition_kind": "media_assay",
            "data_origin": "laboratory",
            "method_id": "SIM_MEDIA_DIGEST_ICPMS_V1",
            "calibration_id": None,
            "value": 415000.0,
            "uncertainty_std": 41000.0,
            "depth_m": 0.0,
            "vertical_datum": "mat_top",
            **overrides,
        }
    )


def _condition(parameter, **overrides):
    return _record(
        **{
            "record_id": f"O_{parameter}",
            "station_id": "SURVEY_01",
            "sensor_id": None,
            "tile_id": "tile_0_0",
            "parameter": parameter,
            "matrix": "mat_structure",
            "fraction": "not_applicable",
            "acquisition_kind": "bathymetric_survey",
            "data_origin": "field_survey",
            "method_id": "SIM_MULTIBEAM_V1",
            "calibration_id": None,
            "depth_m": 0.0,
            "vertical_datum": "mat_top",
            **overrides,
        }
    )


# --- dispatch is on the declared quantity kind ------------------------------

def test_dispatch_uses_the_declared_quantity_kind_not_the_matrix_and_unit():
    aqueous = _record()
    flux = _chamber()
    mass = _dgt()
    loading = _assay(media_id="media_A0")
    assert op.classify_record(aqueous).model_quantity is op.ModelQuantity.AQUEOUS_CONCENTRATION
    assert op.classify_record(flux).model_quantity is op.ModelQuantity.AREAL_FLUX
    assert op.classify_record(mass).model_quantity is op.ModelQuantity.ACCUMULATED_MASS
    assert op.classify_record(loading).model_quantity is op.ModelQuantity.SOLID_LOADING


def test_a_metal_record_with_a_nonsense_quantity_kind_is_refused():
    record = _record(
        record_id="O_BAD",
        quantity_kind="categorical",
        unit="class",
        qualifier="categorical",
        value=None,
        uncertainty_std=None,
        condition_class="intact",
    )
    use = op.classify_record(record)
    assert use.decision is op.AssimilationDecision.REJECT


# --- porewater is a primary channel ----------------------------------------

def test_porewater_is_assimilable_and_names_the_state_it_constrains():
    use = op.classify_record(_porewater())
    assert use.assimilable
    assert use.model_quantity is op.ModelQuantity.AQUEOUS_CONCENTRATION
    assert use.model_target == "sediment_face_porewater"
    assert use.value_si == pytest.approx(to_si_aqueous_concentration(940.0, "ug/L"))
    assert use.si_unit == "kg/m3"
    assert use.carries_chemistry


def test_mat_porewater_is_assimilable_against_the_layer_state():
    use = op.classify_record(
        _porewater(record_id="O_MATPW", matrix="mat_porewater", z_in_mat_m=0.005)
    )
    assert use.assimilable
    assert use.model_target == "mat_layer_porewater"


def test_bottom_water_and_seawater_constrain_the_water_above_the_mat():
    bottom = op.classify_record(_record())
    seawater = op.classify_record(_record(record_id="O_SW", matrix="seawater"))
    assert bottom.model_target == "bottom_water"
    assert seawater.model_target == "bottom_water"
    assert bottom.assimilable and seawater.assimilable


def test_sediment_is_not_accepted_as_a_water_concentration():
    """A sediment porewater sample is water; a sediment solid is not."""
    as_water = _record(
        record_id="O_SED_WATER",
        matrix="sediment",
        sensor_id=None,
        sample_id="SED_1",
        acquisition_kind="sediment_core",
        data_origin="laboratory",
        method_id="SIM_SEDIMENT_DIGEST_V1",
        calibration_id=None,
    )
    use = op.classify_record(as_water)
    assert use.decision is op.AssimilationDecision.REJECT
    assert "rejected as an aqueous" in use.reason

    as_solid = _record(
        record_id="O_SED_SOLID",
        matrix="sediment",
        sensor_id=None,
        sample_id="SED_2",
        quantity_kind="solid_loading",
        unit="mg/kg",
        fraction="total_recoverable",
        acquisition_kind="sediment_core",
        data_origin="laboratory",
        method_id="SIM_SEDIMENT_DIGEST_V1",
        calibration_id=None,
        value=0.42,
        uncertainty_std=0.05,
        depth_m=0.1,
        vertical_datum="seabed",
    )
    solid_use = op.classify_record(as_solid)
    assert solid_use.decision is op.AssimilationDecision.EVIDENCE_ONLY
    assert solid_use.model_quantity is op.ModelQuantity.SOLID_LOADING
    assert "source reservoir" in solid_use.reason


def test_sorbent_is_never_read_as_a_water_concentration():
    use = op.classify_record(_assay(record_id="O_SORB_WATER", quantity_kind="aqueous_concentration", unit="ng/L"))
    assert use.decision is op.AssimilationDecision.REJECT


# --- fractions --------------------------------------------------------------

def test_labile_and_dgt_labile_are_never_merged():
    """Two different operational definitions, measured by different physics."""
    assert frozenset({Fraction.LABILE, Fraction.DGT_LABILE}) in op.NEVER_MERGED_FRACTIONS
    assert op.never_merged(Fraction.DGT_LABILE, Fraction.LABILE)
    assert op.never_merged(Fraction.LABILE, Fraction.DGT_LABILE)

    # bottom water, where the model state is the voltammetric labile pool
    record = _record(record_id="O_DGTLAB", fraction="dgt_labile")
    use = op.classify_record(record)
    assert not use.assimilable
    assert use.decision is op.AssimilationDecision.EVIDENCE_ONLY
    assert use.diagnostics["never_merged"] is True
    assert use.value_si is None, "an unmerged record contributes no number"


def test_dgt_labile_is_not_merged_with_a_filtered_porewater_state_either():
    use = op.classify_record(_porewater(record_id="O_DGTPW", fraction="dgt_labile"))
    assert not use.assimilable
    assert use.diagnostics["never_merged"] is True


def test_dgt_labile_is_not_merged_even_with_the_ratio_operator_on():
    config = op.OperatorConfig(
        total_recoverable_operator=op.FractionRatioOperator(enabled=True)
    )
    use = op.classify_record(_record(record_id="O_DGT2", fraction="dgt_labile"), config)
    assert not use.assimilable
    assert use.diagnostics["never_merged"] is True


def test_total_recoverable_is_not_assimilated_by_default():
    use = op.classify_record(_record(record_id="O_TR", fraction="total_recoverable"))
    assert use.decision is op.AssimilationDecision.EVIDENCE_ONLY
    assert "switched off" in use.reason


def test_the_ratio_operator_widens_rather_than_sharpens():
    config = op.OperatorConfig(
        total_recoverable_operator=op.FractionRatioOperator(
            enabled=True, ratio_interval=(1.05, 3.0)
        )
    )
    record = _record(record_id="O_TR2", fraction="total_recoverable", value=300.0)
    use = op.classify_record(record, config)
    assert use.assimilable
    assert use.is_censored, "the record enters as an interval, not a number"
    assert use.value_si is None
    point = to_si_aqueous_concentration(300.0, "ng/L")
    assert use.lower_si == pytest.approx(point / 3.0)
    assert use.upper_si == pytest.approx(point / 1.05)
    assert use.upper_si > use.lower_si


def test_methylmercury_is_never_merged_with_the_inorganic_pool():
    record = _porewater(
        record_id="O_MEHG", parameter="Hg", fraction="methylmercury", value=3.4
    )
    use = op.classify_record(record)
    assert not use.assimilable
    assert use.diagnostics["never_merged"] is True


def test_the_porewater_state_is_a_filtered_pool_not_a_labile_one():
    """One fraction for every matrix would be a fiction (MODEL_SPEC section 3)."""
    config = op.OperatorConfig()
    assert config.expected_fraction("Pb", Matrix.POREWATER) is Fraction.DISSOLVED_FILTERED
    assert config.expected_fraction("Pb", Matrix.MAT_POREWATER) is Fraction.DISSOLVED_FILTERED
    assert config.expected_fraction("Pb", Matrix.BOTTOM_WATER) is Fraction.LABILE
    labile_in_porewater = op.classify_record(
        _porewater(record_id="O_PW_LAB", fraction="labile")
    )
    assert labile_in_porewater.decision is op.AssimilationDecision.EVIDENCE_ONLY


# --- DGT --------------------------------------------------------------------

def test_a_dgt_record_is_never_converted_into_a_point_concentration():
    use = op.classify_record(_dgt())
    assert use.model_quantity is op.ModelQuantity.ACCUMULATED_MASS
    assert use.model_quantity is not op.ModelQuantity.AQUEOUS_CONCENTRATION
    assert use.decision is op.AssimilationDecision.EVIDENCE_ONLY
    assert use.si_unit == "kg"
    assert use.value_si == pytest.approx(128.0e-12)
    assert use.diagnostics["never_a_point_concentration"] is True
    assert use.diagnostics["exposure_window_s"] == pytest.approx(3.0 * DAY)
    assert use.counts_for_data_age


def test_a_saturated_dgt_stays_a_one_sided_bound():
    record = _dgt(
        record_id="O_DGT_AR",
        qualifier="above_range",
        value=None,
        uncertainty_std=None,
        lower_bound=50000.0,
        upper_bound=None,
    )
    use = op.classify_record(record)
    assert use.is_one_sided
    assert use.lower_si == pytest.approx(50000.0e-12)
    assert use.upper_si is None
    assert use.value_si is None


def test_a_record_claiming_a_passive_sampler_gave_a_point_concentration_is_refused():
    record = _record(
        record_id="O_DGT_FAKE",
        sensor_id=None,
        sample_id="DGT_X",
        sampling_start_utc="2026-09-08T09:00:00Z",
        sampling_end_utc="2026-09-11T09:00:00Z",
        acquisition_kind="passive_sampler",
        data_origin="laboratory",
        method_id="SIM_DGT_ACCUM_MASS_V1",
        calibration_id=None,
    )
    use = op.classify_record(record)
    assert use.decision is op.AssimilationDecision.REJECT
    assert "accumulated mass" in use.reason


# --- benthic chamber --------------------------------------------------------

def test_a_chamber_flux_is_assimilated_against_the_residual_flux():
    use = op.classify_record(_chamber())
    assert use.assimilable
    assert use.model_quantity is op.ModelQuantity.AREAL_FLUX
    assert use.model_target == "residual_flux_out"
    assert use.si_unit == "kg/m2/s"
    assert use.value_si == pytest.approx(to_si_areal_flux(2.6, "ug/m2/d"))
    assert use.diagnostics["chamber_area_m2"] == pytest.approx(0.196)


def test_a_chamber_record_without_area_is_refused_by_the_operator_too():
    """Belt and braces: a hand-built record that skipped validation is caught."""
    record = replace(_chamber(), chamber_area_m2=None)
    use = op.classify_record(record)
    assert use.decision is op.AssimilationDecision.REJECT
    assert "chamber_area_m2" in use.reason


def test_a_chamber_record_without_a_window_is_refused_by_the_operator_too():
    record = replace(_chamber(), sampling_start_utc=None, sampling_end_utc=None)
    use = op.classify_record(record)
    assert use.decision is op.AssimilationDecision.REJECT
    assert "deployment window" in use.reason


def test_a_chamber_record_of_the_wrong_fraction_is_not_assimilated():
    record = _chamber(record_id="O_BC_FRAC", fraction="labile")
    use = op.classify_record(record)
    assert use.decision is op.AssimilationDecision.EVIDENCE_ONLY


def test_a_censored_chamber_flux_is_used_as_the_bound_it_is():
    record = _chamber(
        record_id="O_BC_ND",
        qualifier="below_loq",
        value=None,
        uncertainty_std=None,
        lower_bound=0.02,
        upper_bound=0.08,
    )
    use = op.classify_record(record)
    assert use.assimilable
    assert use.is_censored
    assert use.value_si is None
    assert use.lower_si == pytest.approx(to_si_areal_flux(0.02, "ug/m2/d"))


# --- media assays -----------------------------------------------------------

def test_a_media_assay_after_a_replacement_describes_the_old_media():
    """The tile is the same; the media in it is not."""
    config = op.OperatorConfig(
        active_media_id_by_tile={"tile_1_1": "media_B1"},
        active_media_installed_at_utc=START,
    )
    retrieved = _assay(media_id="media_A0", tile_id="tile_1_1")
    use = op.classify_record(retrieved, config)
    assert use.decision is op.AssimilationDecision.EVIDENCE_ONLY
    assert use.diagnostics["retrieved_media"] is True
    assert use.diagnostics["assayed_media_id"] == "media_A0"
    assert use.diagnostics["active_media_id"] == "media_B1"
    assert use.tile_id == "tile_1_1", "the coupon still says where it came from"
    assert "must not be read as the loading of the tile now in place" in use.reason
    assert not use.counts_for_data_age


def test_an_assay_of_the_installed_media_is_assimilable():
    config = op.OperatorConfig(active_media_id="media_A0")
    use = op.classify_record(_assay(media_id="media_A0"), config)
    assert use.assimilable
    assert use.model_quantity is op.ModelQuantity.SOLID_LOADING
    assert use.value_si == pytest.approx(415000.0e-9)


def test_an_assay_predating_the_installation_is_not_the_current_media():
    config = op.OperatorConfig(
        active_media_id="media_A0",
        active_media_installed_at_utc=START + timedelta(days=10),
    )
    use = op.classify_record(_assay(media_id="media_A0"), config)
    assert use.decision is op.AssimilationDecision.EVIDENCE_ONLY
    assert "before the active media was installed" in use.reason


def test_a_generated_replacement_assay_describes_the_retired_batch(multi_year_stream):
    """The same rule, end to end, on a stream the generator actually produced."""
    assays = [
        record for record in multi_year_stream
        if record.acquisition_kind.value == "media_assay"
    ]
    assert assays, "the four-year scene replaces the media in tile_1_1"
    assert {record.media_id for record in assays} == {"media_A0"}
    assert {record.tile_id for record in assays} == {"tile_1_1"}

    config = op.OperatorConfig(active_media_id_by_tile={"tile_1_1": "media_B1"})
    uses = op.build_assimilation_set(assays, config)
    assert all(use.decision is op.AssimilationDecision.EVIDENCE_ONLY for use in uses.uses)
    assert all(use.diagnostics["retrieved_media"] is True for use in uses.uses)
    assert all(use.diagnostics["assayed_media_id"] == "media_A0" for use in uses.uses)
    assert not uses.assimilable, (
        "a coupon from the retired batch must not constrain the tile now in place"
    )


def test_a_solid_assay_in_an_aqueous_unit_is_refused():
    record = replace(_assay(media_id="media_A0"), unit="ng/L")
    config = op.OperatorConfig(active_media_id="media_A0")
    use = op.classify_record(record, config)
    assert use.decision is op.AssimilationDecision.REJECT


# --- mat condition ----------------------------------------------------------

def test_condition_records_are_condition_evidence_and_carry_no_chemistry():
    coverage = _condition(
        "mat_coverage_fraction", quantity_kind="fraction", unit="1", value=0.87,
        uncertainty_std=0.05,
    )
    use = op.classify_record(coverage)
    assert use.condition_evidence
    assert not use.carries_chemistry
    assert use.element is None
    assert use.degradation_mode is DegradationMode.DISPLACEMENT
    assert use.model_quantity is op.ModelQuantity.MAT_COVERAGE_FRACTION


def test_a_condition_record_without_a_tile_cannot_support_a_local_decision():
    record = _condition(
        "mat_coverage_fraction", quantity_kind="fraction", unit="1", value=0.87,
        uncertainty_std=0.05, tile_id=None,
    )
    use = op.classify_record(record)
    assert use.decision is op.AssimilationDecision.EVIDENCE_ONLY
    assert use.diagnostics["tile_missing"] is True
    assert "failure is local" in use.reason


def test_a_damage_class_becomes_an_interval_never_a_number():
    record = _condition(
        "mat_damage_class",
        quantity_kind="categorical",
        unit="class",
        acquisition_kind="rov_inspection",
        qualifier="categorical",
        value=None,
        uncertainty_std=None,
        condition_class="punctured",
    )
    use = op.classify_record(record)
    assert use.assimilable
    assert use.degradation_mode is DegradationMode.LOCAL_DAMAGE
    assert use.value_si is None
    assert use.is_censored
    assert use.lower_si < use.upper_si
    assert use.condition_class == "punctured"


def test_an_invented_damage_class_is_refused():
    record = replace(
        _condition(
            "mat_damage_class",
            quantity_kind="categorical",
            unit="class",
            acquisition_kind="rov_inspection",
            qualifier="categorical",
            value=None,
            uncertainty_std=None,
            condition_class="punctured",
        ),
        condition_class="mostly_fine",
    )
    use = op.classify_record(record)
    assert use.decision is op.AssimilationDecision.REJECT


def test_the_differential_head_is_a_fouling_channel_not_a_context_channel():
    record = _condition(
        "differential_head",
        quantity_kind="context",
        unit="Pa",
        acquisition_kind="in_situ_sensor",
        data_origin="sensor",
        sensor_id="SIM_DP_tile_0_0",
        value=46.0,
        uncertainty_std=6.0,
    )
    use = op.classify_record(record)
    assert use.condition_evidence
    assert use.degradation_mode is DegradationMode.FOULING
    assert use.model_quantity is op.ModelQuantity.DIFFERENTIAL_HEAD
    assert not use.carries_chemistry
    assert use.si_unit == "Pa", "there is no pressure ladder; the unit is reported"


# --- burial is not success --------------------------------------------------

def test_a_burial_observation_is_condition_evidence_for_mode_three():
    """Burial reduces the apparent flux.  It must never read as performance."""
    record = _condition(
        "burial_depth", quantity_kind="length", unit="cm", value=4.5, uncertainty_std=1.5
    )
    use = op.classify_record(record)

    assert use.degradation_mode is DegradationMode.DISPLACEMENT      # mode 3
    assert use.model_quantity is op.ModelQuantity.BURIAL_DEPTH
    assert use.model_quantity is not op.ModelQuantity.AREAL_FLUX
    assert use.condition_evidence is True
    assert use.carries_chemistry is False
    assert use.element is None
    assert use.diagnostics["burial_masquerades_as_success"] is True
    assert "REDUCES the apparent flux" in use.diagnostics["interpretation"]
    assert use.value_si == pytest.approx(0.045), "cm converted on the length ladder"
    assert use.si_unit == "m"


def test_burial_never_enters_the_chemistry_set(multi_year_stream):
    uses = op.build_assimilation_set(multi_year_stream)
    burial = [
        use for use in uses.uses
        if use.model_quantity is op.ModelQuantity.BURIAL_DEPTH
    ]
    assert burial, "the four-year stream must contain burial observations"
    assert all(not use.carries_chemistry for use in burial)
    assert not any(use in uses.chemistry for use in burial)
    assert all(use in uses.for_mode(DegradationMode.DISPLACEMENT) for use in burial)


def test_a_buried_tile_shows_a_lower_flux_with_the_condition_evidence_beside_it(
    multi_year_stream,
):
    """The apparent improvement and its explanation arrive together.

    ``tile_0_0`` is buried at one year.  Its chamber flux falls, and burial
    records for the same tile are available to say why.  Nothing in the operator
    turns the falling flux into an attenuation claim.
    """
    uses = op.build_assimilation_set(multi_year_stream)
    fluxes = [
        (use.observed_at_utc, use.value_si)
        for use in uses.uses
        if use.model_quantity is op.ModelQuantity.AREAL_FLUX
        and use.tile_id == "tile_2_2"
        and use.element == "Pb"
        and use.value_si is not None
    ]
    assert len(fluxes) >= 4
    fluxes.sort()
    before = [value for moment, value in fluxes
              if (moment - START).total_seconds() < 1.0 * YEAR]
    after = [value for moment, value in fluxes
             if (moment - START).total_seconds() > 1.2 * YEAR]
    assert before and after
    assert min(after) < max(before), "burial lowers the measured flux"

    burial = [
        use for use in uses.for_tile("tile_2_2")
        if use.model_quantity is op.ModelQuantity.BURIAL_DEPTH
        and use.value_si is not None
        and (use.observed_at_utc - START).total_seconds() > 1.2 * YEAR
    ]
    assert burial, "the explanation must be observable, not inferred"
    assert all(use.value_si > 0.0 for use in burial)
    assert all(use.degradation_mode is DegradationMode.DISPLACEMENT for use in burial)


# --- context ----------------------------------------------------------------

def test_context_channels_never_produce_chemistry(small_stream):
    uses = op.build_assimilation_set(small_stream)
    for use in uses.uses:
        if use.model_quantity is op.ModelQuantity.CONTEXT:
            assert not use.carries_chemistry
            assert use.element is None
            assert not use.assimilable


def test_removing_every_context_record_leaves_the_metal_set_unchanged(small_stream):
    """MODEL_SPEC section 8: no chemistry is derived from a proxy.

    Deleting every non-metal record must not change one metal-bearing decision,
    value or bound.
    """
    metal_only = [
        record for record in small_stream
        if record.parameter in METAL_PARAMETERS
    ]
    assert len(metal_only) < len(small_stream)

    full = op.build_assimilation_set(small_stream)
    reduced = op.build_assimilation_set(metal_only)

    def _signature(assimilation_set):
        return [
            (
                use.record_id,
                use.decision,
                use.model_quantity,
                use.model_target,
                use.value_si,
                use.lower_si,
                use.upper_si,
                use.sigma_si,
                use.is_censored,
            )
            for use in assimilation_set.uses
            if use.carries_chemistry or use.element is not None
        ]

    assert _signature(full) == _signature(reduced)
    assert _signature(reduced), "there must be metal records to compare"


def test_removing_context_also_leaves_the_qc_flags_of_metal_records_unchanged(
    small_stream,
):
    metal_only = [r for r in small_stream if r.parameter in METAL_PARAMETERS]
    full_report = qc.run_qc(small_stream)
    reduced_report = qc.run_qc(metal_only)
    for record in metal_only:
        assert full_report.flag_for(record) is reduced_report.flag_for(record)


# --- quality flags ----------------------------------------------------------

def test_flag_three_and_four_stay_out_of_the_likelihood():
    for flag in (3, 4):
        use = op.classify_record(_record(quality_flag=flag))
        assert use.decision is op.AssimilationDecision.EVIDENCE_ONLY
        assert use.sensor_health_evidence


def test_a_missing_record_contributes_nothing():
    record = _record(qualifier="missing", value=None, uncertainty_std=None, quality_flag=9)
    use = op.classify_record(record)
    assert use.decision is op.AssimilationDecision.EVIDENCE_ONLY
    assert use.model_quantity is op.ModelQuantity.NONE
    assert not use.counts_for_data_age
    assert use.value_si is None


def test_the_qc_report_can_veto_a_record():
    record = _record()
    good = op.classify_record(record)
    assert good.assimilable
    report = qc.run_qc([replace(record, quality_flag=QualityFlag.FAILED)])
    vetoed = op.classify_record(record, qc_report=report)
    assert vetoed.decision is op.AssimilationDecision.EVIDENCE_ONLY


# --- whole streams ----------------------------------------------------------

def test_the_fixture_file_classifies_without_error(fixture_records):
    uses = op.build_assimilation_set(fixture_records)
    assert len(uses.uses) == len(fixture_records)
    assert uses.assimilable
    by_id = {use.record_id: use for use in uses.uses}
    assert by_id["R0001"].model_target == "sediment_face_porewater"
    assert by_id["R0004"].model_quantity is op.ModelQuantity.AREAL_FLUX
    assert by_id["R0007"].model_quantity is op.ModelQuantity.ACCUMULATED_MASS
    assert by_id["R0010"].degradation_mode is DegradationMode.DISPLACEMENT
    assert by_id["R0011"].model_quantity is op.ModelQuantity.MAT_DAMAGE_CLASS
    assert by_id["R0017"].decision is op.AssimilationDecision.EVIDENCE_ONLY
    assert by_id["R0019"].degradation_mode is DegradationMode.FOULING


def test_every_record_of_a_real_stream_gets_a_decision_and_a_reason(multi_year_stream):
    uses = op.build_assimilation_set(multi_year_stream)
    assert len(uses.uses) == len(multi_year_stream)
    assert all(use.reason for use in uses.uses)
    assert all(use.record_id for use in uses.uses)


def test_the_operator_never_mutates_a_record(small_stream):
    before = [obs.record_to_dict(record) for record in small_stream]
    op.build_assimilation_set(small_stream)
    after = [obs.record_to_dict(record) for record in small_stream]
    assert before == after
