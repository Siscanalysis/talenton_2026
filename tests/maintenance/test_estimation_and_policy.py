"""The evidence loop: what it estimates, what it refuses to estimate, and what
it then recommends.

The tests that matter here are the negative ones. Anyone can check that a
saturated mat triggers a replacement; the question is whether the policy also
declines to replace when the same evidence would be produced by a stronger
sediment source, and whether the estimator admits it cannot see what it cannot
see.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from reactive_seabed_mat.config import default_run_config
from reactive_seabed_mat.contracts import (
    AcquisitionKind,
    ActionKind,
    AmbiguityFlag,
    DataOrigin,
    Fraction,
    MatTileGeometry,
    Matrix,
    ObservationRecord,
    OperatorKnownMat,
    Parameter,
    ProvenanceLabel,
    QualityFlag,
    QuantityKind,
    Qualifier,
    StateOrigin,
    VerticalDatum,
)
from reactive_seabed_mat.estimation import estimate_tiles, interval_quotient
from reactive_seabed_mat.estimation.estimate import _widen
from reactive_seabed_mat.maintenance import (
    PolicyState,
    accepted_service_tiles,
    recommend,
    saturation_interval,
)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
TILE = "tile_0_0"


@pytest.fixture
def known() -> OperatorKnownMat:
    geometry = MatTileGeometry(
        width_m=26.67,
        length_m=26.67,
        thickness_m=0.010,
        x_m=0.0,
        y_m=0.0,
        bulk_density_kg_per_m3=400.0,
        porosity=0.5,
        edge_leakage_fraction=0.02,
    )
    return OperatorKnownMat(
        mat_id="MAT-test",
        tile_ids=(TILE,),
        media_id="media_A0",
        installed_at_utc=START,
        geometry=geometry,
        hotspot_area_m2=711.1,
        covered_area_m2=711.1,
        accepted_service_events=(),
    )


def _record(
    *,
    record_id: str,
    parameter: Parameter,
    quantity: QuantityKind,
    matrix: Matrix,
    unit: str,
    value: float | None,
    day: int,
    acquisition: AcquisitionKind,
    qualifier: Qualifier = Qualifier.QUANTIFIED,
    condition_class: str | None = None,
    flag: QualityFlag = QualityFlag.PASSED,
) -> ObservationRecord:
    when = START + timedelta(days=day)
    return ObservationRecord(
        record_id=record_id,
        station_id="ST_TEST",
        observed_at_utc=when,
        available_at_utc=when,
        parameter=parameter,
        quantity_kind=quantity,
        unit=unit,
        matrix=matrix,
        fraction=Fraction.LABILE,
        acquisition_kind=acquisition,
        qualifier=qualifier,
        quality_flag=flag,
        method_id="SIM_TEST_V1",
        data_origin=DataOrigin.SENSOR,
        provenance=ProvenanceLabel.SYNTHETIC_DEMO,
        tile_id=TILE,
        value=value,
        uncertainty_std=(abs(value) * 0.05 if value is not None else None),
        condition_class=condition_class,
        vertical_datum=VerticalDatum.SEABED,
    )


def _chemistry(days, porewater_ug_per_l, flux_ug_per_m2_per_d):
    """A porewater series and a chamber series over the same days."""
    records = []
    for index, day in enumerate(days):
        records.append(
            _record(
                record_id=f"PW-{index}",
                parameter=Parameter.PB,
                quantity=QuantityKind.AQUEOUS_CONCENTRATION,
                matrix=Matrix.POREWATER,
                unit="ug/L",
                value=porewater_ug_per_l,
                day=day,
                acquisition=AcquisitionKind.GRAB_SAMPLE,
            )
        )
        records.append(
            _record(
                record_id=f"BC-{index}",
                parameter=Parameter.PB,
                quantity=QuantityKind.AREAL_FLUX,
                matrix=Matrix.BOTTOM_WATER,
                unit="ug/m2/d",
                value=flux_ug_per_m2_per_d,
                day=day,
                acquisition=AcquisitionKind.BENTHIC_CHAMBER,
            )
        )
    return records


# ---------------------------------------------------------------------------
# Interval arithmetic
# ---------------------------------------------------------------------------

def test_widening_a_positive_interval_keeps_it_positive():
    """The bug this guards against cost the estimator every downstream ratio.

    Arithmetic widening of ``(1e-11, 9e-11)`` pushes the lower bound below zero,
    the clip pins it at zero, and every quotient built on it then reports "not
    computable" instead of an answer.
    """
    widened = _widen((1.0e-11, 9.0e-11), 1.0)
    assert widened[0] > 0.0
    assert widened[0] < 1.0e-11 < 9.0e-11 < widened[1]


def test_widening_by_zero_is_the_identity():
    assert _widen((2.0, 8.0), 0.0) == (2.0, 8.0)
    assert _widen((2.0, 8.0), -1.0) == (2.0, 8.0)


def test_a_quotient_against_a_divisor_spanning_zero_is_refused():
    """No answer, not a wide answer.  An infinite bound would propagate."""
    assert interval_quotient((1.0, 2.0), (-1.0, 1.0)) is None
    assert interval_quotient((1.0, 2.0), (2.0, 4.0)) == (0.25, 1.0)


# ---------------------------------------------------------------------------
# What the estimator refuses to do
# ---------------------------------------------------------------------------

def test_with_no_observations_at_all_nothing_is_claimed(known):
    config = default_run_config()
    now = START + timedelta(days=400)
    snapshot = estimate_tiles([], known, config, now)[TILE]

    assert AmbiguityFlag.INSUFFICIENT_DATA in snapshot.ambiguity_flags
    assert snapshot.origin is StateOrigin.ESTIMATED
    assert snapshot.breakthrough_s_interval["Pb"] is None
    # An unmeasured source must not produce a confident attenuation.
    assert snapshot.attenuation_interval["Pb"] == (0.0, 1.0)


def test_a_missing_value_is_not_evidence_but_a_non_detect_is(known):
    config = default_run_config()
    now = START + timedelta(days=200)

    missing = _record(
        record_id="M1",
        parameter=Parameter.PB,
        quantity=QuantityKind.AREAL_FLUX,
        matrix=Matrix.BOTTOM_WATER,
        unit="ug/m2/d",
        value=None,
        day=100,
        acquisition=AcquisitionKind.BENTHIC_CHAMBER,
        qualifier=Qualifier.MISSING,
        flag=QualityFlag.MISSING,
    )
    non_detect = replace(
        missing,
        record_id="ND1",
        qualifier=Qualifier.BELOW_LOD,
        quality_flag=QualityFlag.PASSED,
        value=None,
        upper_bound=0.05,
        uncertainty_std=None,
    )

    from_missing = estimate_tiles([missing], known, config, now)[TILE]
    from_bound = estimate_tiles([non_detect], known, config, now)[TILE]

    assert from_missing.residual_flux_interval["Pb"] == (0.0, 0.0)
    # The non-detect carries a real upper bound, so it constrains something.
    assert from_bound.residual_flux_interval["Pb"][1] > 0.0


def test_the_true_loading_lies_inside_the_estimated_interval(known):
    """Calibration, not sharpness.

    The estimator is allowed to be wide. It is not allowed to be wrong: a
    consistent source and residual must bracket the mass the mat really took up.
    """
    config = default_run_config()
    days = [30, 120, 210, 300, 390]
    records = _chemistry(days, porewater_ug_per_l=1000.0, flux_ug_per_m2_per_d=20.0)
    now = START + timedelta(days=400)

    snapshot = estimate_tiles(records, known, config, now)[TILE]
    low, high = snapshot.loading_kg_per_m2_interval["Pb"]

    # Independently: (source - residual) * elapsed, at the design seepage.
    source = 1.0e-3 * 3.0e-8                       # kg/m3 * m/s
    residual = 20.0e-9 / 86400.0                   # ug/m2/d -> kg/m2/s
    expected = (source - residual) * 400 * 86400.0
    assert low < expected < high
    assert low > 0.0, "a consistent series must bound capture away from zero"


def test_an_unmeasured_tile_borrows_and_says_so(known):
    """Nine tiles, chemistry on one.  The rest are extrapolation, and labelled."""
    config = default_run_config()
    records = _chemistry([30, 120], porewater_ug_per_l=1000.0, flux_ug_per_m2_per_d=20.0)
    two_tiles = replace(known, tile_ids=(TILE, "tile_1_1"))
    now = START + timedelta(days=200)

    snapshots = estimate_tiles(records, two_tiles, config, now)
    borrowed = snapshots["tile_1_1"]
    own = snapshots[TILE]

    assert "extrapolated" in borrowed.notes
    own_width = own.source_flux_interval["Pb"]
    borrowed_width = borrowed.source_flux_interval["Pb"]
    assert borrowed_width[1] / borrowed_width[0] > own_width[1] / own_width[0]


def test_replacing_a_tile_resets_the_loading_it_is_judged_on(known):
    """Otherwise the estimator recommends replacing a tile it just watched
    being replaced.

    Loading accumulates on the current media. Integrating from the original
    deployment would carry the old media's consumed capacity into the new one.
    """
    from reactive_seabed_mat.contracts import ServiceEvent

    config = default_run_config()
    days = [30, 120, 210, 300, 390, 480, 570, 660]
    records = _chemistry(days, porewater_ug_per_l=1000.0, flux_ug_per_m2_per_d=20.0)
    now = START + timedelta(days=700)

    before = estimate_tiles(records, known, config, now)[TILE]

    serviced = replace(
        known,
        accepted_service_events=(
            ServiceEvent(
                event_id="SVC-1",
                time_utc=START + timedelta(days=600),
                tile_ids=(TILE,),
                kind="partial_media_replacement",
                old_media_id="media_A0",
                new_media_id="media_A1",
                retrieved_kg={"Pb": 1.0},
                cost_eur=0.0,
                triggered_by_recommendation_id=None,
                execution_mode="simulation_only",
            ),
        ),
    )
    after = estimate_tiles(records, serviced, config, now)[TILE]

    assert after.loading_kg_per_m2_interval["Pb"][1] < (
        before.loading_kg_per_m2_interval["Pb"][1]
    )
    assert after.remaining_capacity_kg_per_m2["Pb"][1] >= (
        before.remaining_capacity_kg_per_m2["Pb"][1]
    )


def test_no_evidence_anywhere_is_not_reported_as_extrapolation(known):
    """"Borrowed from another tile" must not be said when nothing was borrowed."""
    snapshot = estimate_tiles([], known, default_run_config(), START)[TILE]
    assert "extrapolated" not in snapshot.notes
    assert AmbiguityFlag.INSUFFICIENT_DATA in snapshot.ambiguity_flags


def test_burial_is_flagged_rather_than_read_as_success(known):
    """A buried mat emits less.  That is a longer path, not better chemistry."""
    config = default_run_config()
    records = _chemistry([30], porewater_ug_per_l=1000.0, flux_ug_per_m2_per_d=1.0)
    records.append(
        _record(
            record_id="BUR-1",
            parameter=Parameter.BURIAL_DEPTH,
            quantity=QuantityKind.LENGTH,
            matrix=Matrix.MAT_STRUCTURE,
            unit="m",
            value=0.08,
            day=60,
            acquisition=AcquisitionKind.BATHYMETRIC_SURVEY,
        )
    )
    snapshot = estimate_tiles(records, known, config, START + timedelta(days=90))[TILE]
    assert AmbiguityFlag.BURIAL in snapshot.ambiguity_flags
    assert "not evidence of capture" in snapshot.notes


def test_degradation_mode_weights_are_a_distribution(known):
    config = default_run_config()
    snapshot = estimate_tiles([], known, config, START + timedelta(days=90))[TILE]
    weights = snapshot.degradation_mode_weights
    assert set(weights) == {"saturation", "fouling", "displacement", "local_damage"}
    assert math.isclose(sum(weights.values()), 1.0, rel_tol=1e-12)
    assert all(value > 0.0 for value in weights.values())


# ---------------------------------------------------------------------------
# What the policy does with it
# ---------------------------------------------------------------------------

def test_the_none_policy_never_recommends_anything(known):
    config = replace(default_run_config(), policy=replace(default_run_config().policy, kind="none"))
    out = recommend({}, known, config, START, 0.0, PolicyState())
    assert out == []


def test_the_fixed_policy_ignores_every_observation(known):
    """It must reach the same decision with rich evidence and with none."""
    base = default_run_config()
    config = replace(base, policy=replace(base.policy, kind="fixed"))
    due = config.policy.fixed_interval_s + 1.0

    rich = _chemistry([30, 120], porewater_ug_per_l=1000.0, flux_ug_per_m2_per_d=20.0)
    with_evidence = recommend(
        estimate_tiles(rich, known, config, START), known, config, START, due,
        PolicyState(),
    )
    without = recommend({}, known, config, START, due, PolicyState())

    assert [r.action for r in with_evidence] == [r.action for r in without]
    assert with_evidence[0].action is ActionKind.PLAN_PARTIAL_REPLACEMENT
    assert with_evidence[0].diagnostics["evidence_used"] is False


def test_every_recommendation_requires_a_human_and_actuates_nothing(known):
    base = default_run_config()
    config = replace(base, policy=replace(base.policy, kind="fixed"))
    out = recommend(
        {}, known, config, START, config.policy.fixed_interval_s + 1.0, PolicyState()
    )
    assert out
    for recommendation in out:
        assert recommendation.human_confirmation_required is True
        assert recommendation.execution_mode == "simulation_only"


def test_replacement_is_refused_while_the_source_could_explain_it(known):
    """The rule this whole package exists for.

    Consumed capacity and a stronger sediment source produce the same falling
    attenuation. New media does not fix a source that grew, so the policy asks
    for chemistry instead of a vessel.
    """
    base = default_run_config()
    config = replace(
        base,
        policy=replace(base.policy, kind="evidence_informed"),
    )
    now = START + timedelta(days=900)
    snapshot = estimate_tiles([], known, config, now)[TILE]

    saturated = replace(
        snapshot,
        loading_kg_per_m2_interval={"Pb": (0.05, 0.05), "Hg": (0.0, 0.0)},
        evidence_record_ids=("A", "B", "C", "D"),
        data_age_s={"Pb|areal_flux": 86400.0},
        integrity_index_interval=(0.99, 1.0),
        ambiguity_flags=(AmbiguityFlag.SEDIMENT_SOURCE_INCREASE,),
    )
    blocked = recommend({TILE: saturated}, known, config, now, 9.0e7, PolicyState())
    actions = {r.action for r in blocked}
    assert ActionKind.PLAN_PARTIAL_REPLACEMENT not in actions
    assert ActionKind.PERFORMANCE_UNCERTAIN in actions
    assert accepted_service_tiles(blocked) == ()

    unambiguous = replace(saturated, ambiguity_flags=())
    allowed = recommend({TILE: unambiguous}, known, config, now, 9.0e7, PolicyState())
    assert ActionKind.PLAN_PARTIAL_REPLACEMENT in {r.action for r in allowed}
    assert accepted_service_tiles(allowed) == (TILE,)


def test_stale_or_thin_evidence_asks_for_more_rather_than_deciding(known):
    base = default_run_config()
    config = replace(base, policy=replace(base.policy, kind="evidence_informed"))
    now = START + timedelta(days=900)
    snapshot = estimate_tiles([], known, config, now)[TILE]
    stale = replace(
        snapshot,
        evidence_record_ids=("A", "B", "C", "D"),
        data_age_s={"Pb|areal_flux": config.policy.max_data_age_s * 2.0},
    )
    out = recommend({TILE: stale}, known, config, now, 9.0e7, PolicyState())
    assert {r.action for r in out} == {ActionKind.TAKE_CHEMICAL_SAMPLE}


def test_the_decision_bound_is_a_stated_risk_posture(known):
    """lower / mid / upper genuinely change the decision, and are named."""
    base = default_run_config()
    now = START + timedelta(days=900)
    snapshot = estimate_tiles([], known, base, now)[TILE]
    wide = replace(
        snapshot,
        loading_kg_per_m2_interval={"Pb": (0.0, 0.01), "Hg": (0.0, 0.0)},
        evidence_record_ids=("A", "B", "C", "D"),
        data_age_s={"Pb|areal_flux": 86400.0},
        integrity_index_interval=(0.99, 1.0),
        ambiguity_flags=(),
    )
    decisions = {}
    for bound in ("lower", "mid", "upper"):
        config = replace(
            base, policy=replace(base.policy, kind="evidence_informed",
                                 saturation_decision_bound=bound)
        )
        out = recommend({TILE: wide}, known, config, now, 9.0e7, PolicyState())
        decisions[bound] = {r.action for r in out}

    assert ActionKind.PLAN_PARTIAL_REPLACEMENT in decisions["upper"]
    assert ActionKind.PLAN_PARTIAL_REPLACEMENT not in decisions["lower"]


def test_an_unknown_decision_bound_is_refused(known):
    base = default_run_config()
    config = replace(
        base,
        policy=replace(base.policy, kind="evidence_informed",
                       saturation_decision_bound="whatever"),
    )
    now = START + timedelta(days=900)
    snapshot = replace(
        estimate_tiles([], known, base, now)[TILE],
        evidence_record_ids=("A", "B", "C", "D"),
        data_age_s={"Pb|areal_flux": 86400.0},
    )
    with pytest.raises(KeyError):
        recommend({TILE: snapshot}, known, config, now, 9.0e7, PolicyState())


def test_an_unknown_policy_is_refused(known):
    base = default_run_config()
    config = replace(base, policy=replace(base.policy, kind="vibes"))
    with pytest.raises(KeyError):
        recommend({}, known, config, START, 0.0, PolicyState())


def test_commissioned_capacity_narrows_saturation_against_the_literature(known):
    """The value of the laboratory work, as a number.

    Without a commissioning isotherm the capacity spans a factor of 27 and the
    saturation interval is too wide to decide on. With one it is not. That
    contrast is the argument for doing experiment 1 in MATERIAL_KERATIN.md.
    """
    base = default_run_config()
    now = START + timedelta(days=900)
    snapshot = replace(
        estimate_tiles([], known, base, now)[TILE],
        loading_kg_per_m2_interval={"Pb": (1.0e-3, 2.0e-3), "Hg": (0.0, 0.0)},
    )
    with_commissioning = saturation_interval(snapshot, base, "Pb")

    uncommissioned = replace(
        base,
        mat=replace(
            base.mat,
            media=tuple(
                replace(medium, commissioned_q_max_interval=None)
                for medium in base.mat.media
            ),
        ),
    )
    without = saturation_interval(snapshot, uncommissioned, "Pb")

    assert with_commissioning is not None and without is not None
    width_with = with_commissioning[1] - with_commissioning[0]
    width_without = without[1] - without[0]
    assert width_with < width_without
