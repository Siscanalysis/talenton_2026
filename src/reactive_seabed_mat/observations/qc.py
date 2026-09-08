"""Transparent, QARTOD-inspired quality control (MODEL_SPEC section 8).

Four checks and one age rule, all of them readable and all of them
configurable:

``gross_range``   the value lies inside a plausibility band for its channel;
``spike``         the value differs from the mean of its neighbours by more
                  than a threshold;
``stuck_value``   a channel repeats the same number too many times in a row;
``vocabulary``    a categorical result names a class from the controlled
                  vocabulary for that parameter;
``data_age``      the newest usable record of an asset is older than its limit.

The thresholds in :data:`DEMO_THRESHOLDS` are **demonstration assumptions**.
They are instrument-plausibility bands chosen so the demonstration shows a
failed sensor; they are explicitly **not** official heavy-metal quality
standards, and they are not a QARTOD certification.  The flag vocabulary is
taken from the shared contract (1 passed, 2 not evaluated, 3 suspect, 4 failed,
9 missing), inspired by [S23]-[S24].

Thresholds are looked up on a **band key** built from the record itself:
``parameter|quantity_kind|matrix``, falling back to ``parameter|quantity_kind``
and then to ``parameter``.  A single band per parameter is not enough here:
porewater Pb beneath the mat and bottom-water Pb above it differ by five orders
of magnitude, and one band for both would either pass everything or fail
everything.

Health is kept strictly separate from material saturation: an
:class:`AssetHealth` object says something about an instrument, a tile survey or
a laboratory station, and nothing at all about how loaded the mat is.  Nothing
here deletes or repairs a record; checks return outcomes, and an escalated flag
is always reported beside the original one.

Three defects found by the audit in the inherited version are fixed here, and
each has a regression test in ``tests/observations/test_qc_regressions.py``:

1. ``_sensor_health`` never updated ``last_seen`` for a missing record, so the
   data-age check was skipped for exactly the sensor that needed it: a sensor
   whose readings were all missing looked fine.  Health now tracks
   ``last_observed_at_utc`` (any contact) and ``last_usable_at_utc``
   (information) separately, and an asset with no usable reading at all is
   stale by definition.
2. Stuck detection matched the substring ``"stuck value"`` inside a prose
   reason, so rewording the message silently disabled the check.  Outcomes now
   carry a structured :attr:`QCOutcome.failed_checks` set, and health reads
   that.
3. Records with ``sensor_id = None`` (every laboratory, chamber, DGT, assay and
   survey record) never entered the health summary at all.  Health is now
   computed per **asset**: a sensor when there is one, otherwise the tile, and
   otherwise the station.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Mapping, Sequence

from ..contracts import (
    ObservationRecord,
    Parameter,
    Qualifier,
    QualityFlag,
    QuantityKind,
)
from ..units import UnitError, convert_scalar
from .condition import MAT_DAMAGE_CLASSES

__all__ = [
    "QCThresholds",
    "DEMO_THRESHOLDS",
    "QCOutcome",
    "AssetHealth",
    "SensorHealth",
    "QCReport",
    "STUCK_REASON_TEMPLATE",
    "band_keys",
    "asset_key",
    "channel_key",
    "gross_range_check",
    "spike_check",
    "stuck_value_check",
    "vocabulary_check",
    "run_qc",
    "apply_qc_flags",
]

_SECONDS_PER_DAY = 86400.0

#: Ordering used when a check escalates a flag.  ``MISSING`` is not "worse"
#: than ``FAILED``: it is a different statement, and it is never overwritten.
_SEVERITY: Mapping[int, int] = {
    int(QualityFlag.PASSED): 0,
    int(QualityFlag.NOT_EVALUATED): 1,
    int(QualityFlag.SUSPECT): 2,
    int(QualityFlag.FAILED): 3,
}

#: The stuck-value reason.  It is a template on purpose: the health summary
#: reads the structured ``failed_checks`` set, never this prose, so rewording it
#: cannot disable the check.  ``tests/observations/test_qc_regressions.py``
#: rewords it and asserts the detection survives.
STUCK_REASON_TEMPLATE = (
    "stuck value: {count} consecutive readings within {tolerance:g} of each "
    "other (demo threshold {limit}, ASSUMPTION)"
)


def band_keys(record: ObservationRecord) -> tuple[str, ...]:
    """Threshold lookup keys for one record, most specific first.

    ``parameter|quantity_kind|matrix`` then ``parameter|quantity_kind`` then
    ``parameter``.  Nothing is inferred from the parameter name alone.
    """
    parameter = record.parameter.value
    kind = record.quantity_kind.value
    matrix = record.matrix.value
    return (f"{parameter}|{kind}|{matrix}", f"{parameter}|{kind}", parameter)


def _lookup(table: Mapping[str, object], record: ObservationRecord):
    for key in band_keys(record):
        if key in table:
            return table[key]
    return None


def asset_key(record: ObservationRecord) -> tuple[str, str]:
    """Which physical asset a record says something about.

    A sensor when the record names one; otherwise the tile it describes;
    otherwise the station.  Without this, every laboratory, chamber, DGT, media
    assay and survey record (all of which have ``sensor_id = None``) fell out of
    the health summary entirely.
    """
    if record.sensor_id:
        return ("sensor", record.sensor_id)
    if record.tile_id:
        return ("tile", record.tile_id)
    return ("station", record.station_id)


def channel_key(record: ObservationRecord) -> tuple[str, str, str, str]:
    """A channel is one parameter, from one asset, at one station, one method.

    Identity falls back from the sensor to the tile before the sample, so
    successive chamber deployments or porewater samples on the same tile form
    one series that the spike and stuck checks can actually work on.
    """
    kind, identifier = asset_key(record)
    return (
        record.station_id,
        f"{kind}:{identifier}",
        record.parameter.value,
        record.method_id,
    )


@dataclass(frozen=True, slots=True)
class QCThresholds:
    """Demo QC thresholds.  ASSUMPTION, not an environmental standard.

    ``gross_range`` and ``spike`` are expressed in ``expected_unit`` for the
    channel.  A record in another unit on the same physical ladder is converted
    with ``reactive_seabed_mat.units``; a record on a different ladder is not
    checked at all and is flagged ``NOT_EVALUATED`` with a reason, because
    silently comparing ng/g with ng/L would be worse than not checking.

    Every mapping is keyed by a band key (see :func:`band_keys`).
    """

    gross_range: Mapping[str, tuple[float, float]]
    spike: Mapping[str, float]
    stuck_tolerance: Mapping[str, float]
    expected_unit: Mapping[str, str]
    #: Relative spike allowance, as a fraction of the neighbour mean.  A channel
    #: with multiplicative noise cannot be policed by an absolute threshold: at
    #: 20 % relative noise the excursion from the neighbour mean scales with the
    #: value, so a fixed limit either passes everything at low concentration or
    #: fails a third of the readings at high concentration.  The effective limit
    #: is ``max(absolute, relative * |neighbour mean|)``.
    spike_relative: Mapping[str, float] = field(default_factory=dict)
    #: Controlled vocabulary per categorical parameter.
    categorical_vocabulary: Mapping[str, frozenset[str]] = field(default_factory=dict)
    #: Per-band data-age limits [s].  A campaign channel measured twice a year
    #: is not stale after six hours, and a probe is.
    max_data_age: Mapping[str, float] = field(default_factory=dict)
    stuck_repeat_count: int = 5
    default_max_data_age_s: float = 21600.0
    provenance: str = "assumption"
    source_ref: str = (
        "demonstration thresholds, docs/MODEL_SPEC.md section 8; QARTOD-inspired "
        "[S23]-[S24]; not an official heavy-metal standard and not a certification"
    )

    def max_data_age_for(self, record: ObservationRecord) -> float:
        value = _lookup(self.max_data_age, record)
        return self.default_max_data_age_s if value is None else float(value)


#: Demonstration thresholds.  Every number below is an ASSUMPTION.
DEMO_THRESHOLDS = QCThresholds(
    gross_range={
        # --- aqueous metal, by matrix: five orders of magnitude apart --------
        "Pb|aqueous_concentration|bottom_water": (0.0, 5.0e3),      # ng/L
        "Pb|aqueous_concentration|seawater": (0.0, 5.0e3),          # ng/L
        "Pb|aqueous_concentration|porewater": (0.0, 5.0e3),         # ug/L
        "Pb|aqueous_concentration|mat_porewater": (0.0, 5.0e3),     # ug/L
        "Hg|aqueous_concentration|bottom_water": (0.0, 5.0e2),      # ng/L
        "Hg|aqueous_concentration|seawater": (0.0, 5.0e2),          # ng/L
        "Hg|aqueous_concentration|porewater": (0.0, 5.0e1),         # ug/L
        "Hg|aqueous_concentration|mat_porewater": (0.0, 5.0e1),     # ug/L
        # --- the flux the mat is judged on ----------------------------------
        "Pb|areal_flux": (0.0, 2.0e5),                              # ug/m2/d
        "Hg|areal_flux": (0.0, 2.0e3),                              # ug/m2/d
        # --- integrated and solid channels ----------------------------------
        "Pb|accumulated_mass": (0.0, 1.0e7),                        # ng
        "Hg|accumulated_mass": (0.0, 1.0e6),                        # ng
        "Pb|solid_loading": (0.0, 5.0e7),                           # ng/g, 5 % w/w
        "Hg|solid_loading": (0.0, 5.0e6),                           # ng/g
        # --- mat condition ---------------------------------------------------
        "mat_coverage_fraction": (0.0, 1.0),                        # 1
        "burial_depth": (0.0, 5.0),                                 # m
        "scour_depth": (0.0, 5.0),                                  # m
        "mat_displacement": (0.0, 5.0e2),                           # m
        "mat_uplift": (0.0, 5.0),                                   # m
        "mat_tilt": (-90.0, 90.0),                                  # deg
        "mat_permeability": (0.0, 1.0e-8),                          # m2
        "differential_head": (-1.0e3, 5.0e3),                       # Pa
        # --- context ---------------------------------------------------------
        "temperature": (-2.0, 35.0),                                # degC
        "sediment_temperature": (-2.0, 35.0),                       # degC
        "conductivity": (0.0, 70.0),                                # mS/cm
        "salinity": (0.0, 42.0),                                    # practical
        "pH": (6.0, 9.5),
        "turbidity": (0.0, 1000.0),                                 # NTU
        "dissolved_oxygen": (0.0, 20.0),                            # mg/L
        "redox_potential": (-500.0, 500.0),                         # mV
        "sulfide": (0.0, 100.0),                                    # mg/L
        "current_east": (-3.0, 3.0),                                # m/s
        "current_north": (-3.0, 3.0),                               # m/s
        "seepage_velocity": (-1.0e-5, 1.0e-5),                      # m/s
        "battery_voltage": (9.0, 16.0),                             # V
    },
    spike={
        # Absolute floors, so a spike at low concentration is still caught.
        "Pb|aqueous_concentration|bottom_water": 400.0,
        "Pb|aqueous_concentration|seawater": 400.0,
        "Pb|aqueous_concentration|porewater": 400.0,
        "Hg|aqueous_concentration|bottom_water": 60.0,
        "Hg|aqueous_concentration|porewater": 6.0,
        "Pb|areal_flux": 2.0e3,
        "Hg|areal_flux": 5.0e1,
        # Deliberately NOT declared for mat_coverage_fraction, burial_depth,
        # scour_depth, mat_displacement or mat_damage_class.  Those channels
        # measure a step process: a tile can genuinely move, tear or be buried
        # between two surveys, and a spike test would flag exactly the evidence
        # of failure as suspect and push it out of the likelihood.
        "differential_head": 150.0,
        "temperature": 3.0,
        "sediment_temperature": 2.0,
        "conductivity": 5.0,
        "salinity": 3.0,
        "pH": 0.6,
        "turbidity": 200.0,
        "dissolved_oxygen": 3.0,
        "redox_potential": 200.0,
        "sulfide": 20.0,
        "current_east": 0.6,
        "current_north": 0.6,
        "battery_voltage": 1.0,
    },
    spike_relative={
        # Chosen at roughly 3.5 to 4 standard deviations of the configured
        # relative noise of each channel, so a real excursion still fails and
        # ordinary noise does not.  ASSUMPTIONS.
        "Pb|aqueous_concentration|bottom_water": 0.90,   # 20 % probe noise
        "Pb|aqueous_concentration|seawater": 0.90,
        "Pb|aqueous_concentration|porewater": 0.45,      # 8 % laboratory noise
        "Hg|aqueous_concentration|bottom_water": 0.90,
        "Hg|aqueous_concentration|porewater": 0.45,
        "Pb|areal_flux": 1.60,                           # 35 % chamber noise
        "Hg|areal_flux": 1.60,
        "differential_head": 0.40,                       # 8 % sensor noise
    },
    stuck_tolerance={
        "Pb": 1.0e-9,
        "Hg": 1.0e-9,
        "mat_coverage_fraction": 1.0e-9,
        "burial_depth": 1.0e-9,
        "scour_depth": 1.0e-9,
        "mat_displacement": 1.0e-9,
        "mat_tilt": 1.0e-9,
        "differential_head": 1.0e-9,
        "temperature": 1.0e-6,
        "sediment_temperature": 1.0e-6,
        "conductivity": 1.0e-6,
        "salinity": 1.0e-6,
        "pH": 1.0e-6,
        "turbidity": 1.0e-6,
        "dissolved_oxygen": 1.0e-6,
        "redox_potential": 1.0e-6,
        "sulfide": 1.0e-6,
        "current_east": 1.0e-9,
        "current_north": 1.0e-9,
        "battery_voltage": 1.0e-6,
    },
    expected_unit={
        "Pb|aqueous_concentration|bottom_water": "ng/L",
        "Pb|aqueous_concentration|seawater": "ng/L",
        "Pb|aqueous_concentration|porewater": "ug/L",
        "Pb|aqueous_concentration|mat_porewater": "ug/L",
        "Hg|aqueous_concentration|bottom_water": "ng/L",
        "Hg|aqueous_concentration|seawater": "ng/L",
        "Hg|aqueous_concentration|porewater": "ug/L",
        "Hg|aqueous_concentration|mat_porewater": "ug/L",
        "Pb|areal_flux": "ug/m2/d",
        "Hg|areal_flux": "ug/m2/d",
        "Pb|accumulated_mass": "ng",
        "Hg|accumulated_mass": "ng",
        "Pb|solid_loading": "ng/g",
        "Hg|solid_loading": "ng/g",
        "mat_coverage_fraction": "1",
        "burial_depth": "m",
        "scour_depth": "m",
        "mat_displacement": "m",
        "mat_uplift": "m",
        "mat_tilt": "deg",
        "mat_permeability": "m2",
        "differential_head": "Pa",
        "temperature": "degC",
        "sediment_temperature": "degC",
        "conductivity": "mS/cm",
        "salinity": "1",
        "pH": "pH",
        "turbidity": "NTU",
        "dissolved_oxygen": "mg/L",
        "redox_potential": "mV",
        "sulfide": "mg/L",
        "current_east": "m/s",
        "current_north": "m/s",
        "seepage_velocity": "m/s",
        "battery_voltage": "V",
    },
    categorical_vocabulary={
        Parameter.MAT_DAMAGE_CLASS.value: frozenset(MAT_DAMAGE_CLASSES),
    },
    max_data_age={
        # campaign channels: months between readings by design
        "Pb|areal_flux": 400.0 * _SECONDS_PER_DAY,
        "Hg|areal_flux": 400.0 * _SECONDS_PER_DAY,
        "Pb|accumulated_mass": 400.0 * _SECONDS_PER_DAY,
        "Hg|accumulated_mass": 400.0 * _SECONDS_PER_DAY,
        "Pb|aqueous_concentration|porewater": 250.0 * _SECONDS_PER_DAY,
        "Hg|aqueous_concentration|porewater": 250.0 * _SECONDS_PER_DAY,
        "Pb|solid_loading": 3650.0 * _SECONDS_PER_DAY,
        "Hg|solid_loading": 3650.0 * _SECONDS_PER_DAY,
        "mat_coverage_fraction": 400.0 * _SECONDS_PER_DAY,
        "mat_damage_class": 400.0 * _SECONDS_PER_DAY,
        "burial_depth": 400.0 * _SECONDS_PER_DAY,
        "scour_depth": 400.0 * _SECONDS_PER_DAY,
        "mat_displacement": 400.0 * _SECONDS_PER_DAY,
        "mat_tilt": 400.0 * _SECONDS_PER_DAY,
    },
)


@dataclass(frozen=True, slots=True)
class QCOutcome:
    """The result of running the checks on one record.

    ``flag`` is never milder than ``original_flag``: quality control may raise a
    concern, it may not clear one that the source already declared.

    ``failed_checks`` is the structured statement of *which* checks bit.  The
    health summary reads this, never the prose in ``reasons``.
    """

    record_id: str
    original_flag: QualityFlag
    flag: QualityFlag
    reasons: tuple[str, ...] = ()
    checks: Mapping[str, str] = field(default_factory=dict)
    failed_checks: frozenset[str] = frozenset()

    @property
    def escalated(self) -> bool:
        return self.flag != self.original_flag

    @property
    def usable(self) -> bool:
        """Usable for the likelihood: passed or not-evaluated, and not missing."""
        return self.flag in (QualityFlag.PASSED, QualityFlag.NOT_EVALUATED)


@dataclass(frozen=True, slots=True)
class AssetHealth:
    """Health of one instrument, tile survey or sampling station.

    Says nothing about mat loading or capacity.  A saturated mat and a broken
    probe are different problems with different actions, and this object is only
    ever evidence about the second one.
    """

    asset_id: str
    asset_kind: str
    n_records: int
    #: Newest record of any kind: the last time the asset was heard from.
    last_observed_at_utc: datetime | None = None
    #: Newest record that carried information: what the data age is measured on.
    last_usable_at_utc: datetime | None = None
    failed: bool = False
    stuck: bool = False
    suspect: bool = False
    #: No usable reading inside the age limit, including "none at all".
    stale: bool = False
    missing_fraction: float = 0.0
    data_age_s: float | None = None
    max_data_age_s: float | None = None
    reasons: tuple[str, ...] = ()

    @property
    def sensor_id(self) -> str:
        """Backwards-compatible accessor for the sensor case."""
        return self.asset_id

    @property
    def healthy(self) -> bool:
        return not (self.failed or self.stuck or self.suspect or self.stale)


#: The inherited name.  Health is now computed for every asset, not only for
#: records that happen to carry a ``sensor_id``.
SensorHealth = AssetHealth


@dataclass(frozen=True, slots=True)
class QCReport:
    outcomes: Mapping[str, QCOutcome]
    #: Keyed ``"<kind>:<id>"``, for example ``"sensor:SIM_PBPROBE_ST_MAT_A"`` or
    #: ``"tile:tile_1_1"``.
    asset_health: Mapping[str, AssetHealth]
    thresholds: QCThresholds
    notes: tuple[str, ...] = ()

    @property
    def sensor_health(self) -> Mapping[str, AssetHealth]:
        """Only the instrument assets, keyed by bare sensor id."""
        return {
            health.asset_id: health
            for health in self.asset_health.values()
            if health.asset_kind == "sensor"
        }

    def flag_for(self, record: ObservationRecord) -> QualityFlag:
        outcome = self.outcomes.get(record.record_id)
        return record.quality_flag if outcome is None else outcome.flag

    def health_for(self, record: ObservationRecord) -> AssetHealth | None:
        kind, identifier = asset_key(record)
        return self.asset_health.get(f"{kind}:{identifier}")

    def failed_sensor_ids(self) -> tuple[str, ...]:
        return self._ids(lambda health: health.failed)

    def stuck_sensor_ids(self) -> tuple[str, ...]:
        return self._ids(lambda health: health.stuck)

    def suspect_sensor_ids(self) -> tuple[str, ...]:
        return self._ids(lambda health: health.suspect)

    def stale_asset_keys(self) -> tuple[str, ...]:
        return tuple(sorted(k for k, v in self.asset_health.items() if v.stale))

    def _ids(self, predicate) -> tuple[str, ...]:
        return tuple(
            sorted(
                health.asset_id
                for health in self.asset_health.values()
                if health.asset_kind == "sensor" and predicate(health)
            )
        )


# ---------------------------------------------------------------------------
# individual checks
# ---------------------------------------------------------------------------

def _value_in_expected_unit(
    record: ObservationRecord, thresholds: QCThresholds
) -> tuple[float | None, str | None]:
    """Convert the record's value into the channel's expected unit.

    Returns ``(value, None)`` on success and ``(None, reason)`` when the check
    cannot be run.  No unit is inferred from the parameter name.
    """
    if record.value is None:
        if record.qualifier is Qualifier.ABOVE_RANGE:
            return None, "not evaluated: above-range result is a lower bound"
        if record.qualifier is Qualifier.CATEGORICAL:
            return None, "not evaluated: categorical result carries a class"
        return None, "no value to check"
    expected = _lookup(thresholds.expected_unit, record)
    if expected is None:
        return None, (
            f"no expected unit declared for {'|'.join(band_keys(record)[:2])}"
        )
    if record.unit == expected:
        return float(record.value), None
    try:
        return float(convert_scalar(float(record.value), record.unit, expected)), None
    except UnitError as exc:
        return None, (
            f"unit {record.unit!r} is not on the same physical ladder as "
            f"{expected!r}; check not evaluated ({exc})"
        )


def gross_range_check(
    record: ObservationRecord, thresholds: QCThresholds = DEMO_THRESHOLDS
) -> tuple[QualityFlag, str]:
    """QARTOD-inspired gross-range test.  Demo band, not a standard."""
    band = _lookup(thresholds.gross_range, record)
    if band is None:
        return QualityFlag.NOT_EVALUATED, "no demo range band for this channel"
    value, reason = _value_in_expected_unit(record, thresholds)
    if value is None:
        return QualityFlag.NOT_EVALUATED, reason or "not evaluated"
    low, high = band
    if value < low or value > high:
        unit = _lookup(thresholds.expected_unit, record) or record.unit
        return QualityFlag.FAILED, (
            f"gross range: {value:.6g} outside the demo band [{low:g}, {high:g}] "
            f"{unit} (ASSUMPTION)"
        )
    return QualityFlag.PASSED, "gross range: inside the demo band"


def spike_check(
    record: ObservationRecord,
    previous: ObservationRecord | None,
    following: ObservationRecord | None,
    thresholds: QCThresholds = DEMO_THRESHOLDS,
) -> tuple[QualityFlag, str]:
    """QARTOD-inspired spike test against the mean of the two neighbours.

    The effective limit is ``max(absolute, relative * |neighbour mean|)``.  Some
    channels declare neither, and are deliberately not spike-tested at all: a
    mat can genuinely move, tear or be buried between two surveys, and flagging
    that step as suspect would push the evidence of failure out of the
    likelihood.
    """
    absolute = _lookup(thresholds.spike, record)
    relative = _lookup(thresholds.spike_relative, record)
    if absolute is None and relative is None:
        return QualityFlag.NOT_EVALUATED, (
            "no demo spike threshold for this channel; a step change here is a "
            "physical event, not an instrument fault"
        )
    if previous is None or following is None:
        return QualityFlag.NOT_EVALUATED, "spike test needs both neighbours"
    values = []
    for item in (record, previous, following):
        value, reason = _value_in_expected_unit(item, thresholds)
        if value is None:
            return QualityFlag.NOT_EVALUATED, reason or "neighbour without a value"
        values.append(value)
    centre, before, after = values
    neighbour_mean = 0.5 * (before + after)
    excursion = abs(centre - neighbour_mean)
    limit = max(
        float(absolute or 0.0), float(relative or 0.0) * abs(neighbour_mean)
    )
    if limit <= 0.0:
        return QualityFlag.NOT_EVALUATED, "spike threshold resolves to zero"
    if excursion > limit:
        return QualityFlag.SUSPECT, (
            f"spike: |{centre:.6g} - mean(neighbours)| = {excursion:.6g} exceeds the "
            f"demo threshold {limit:.6g} (ASSUMPTION)"
        )
    return QualityFlag.PASSED, "spike: within the demo threshold"


def stuck_value_check(
    series: Sequence[ObservationRecord], thresholds: QCThresholds = DEMO_THRESHOLDS
) -> dict[str, tuple[QualityFlag, str]]:
    """QARTOD-inspired flat-line test over one channel, in observation order.

    Every record inside a run of at least ``stuck_repeat_count`` identical
    values is flagged ``FAILED``: an instrument that repeats a number exactly is
    not measuring.
    """
    results: dict[str, tuple[QualityFlag, str]] = {}
    if not series:
        return results
    tolerance = _lookup(thresholds.stuck_tolerance, series[0])
    if tolerance is None:
        return results
    tolerance = float(tolerance)
    ordered = sorted(series, key=lambda item: (item.observed_at_utc, item.record_id))
    run: list[ObservationRecord] = []

    def _close(left: ObservationRecord, right: ObservationRecord) -> bool:
        if left.value is None or right.value is None:
            return False
        if left.unit != right.unit:
            return False
        return abs(float(left.value) - float(right.value)) <= tolerance

    def _flush(run_records: list[ObservationRecord]) -> None:
        if len(run_records) >= thresholds.stuck_repeat_count:
            reason = STUCK_REASON_TEMPLATE.format(
                count=len(run_records),
                tolerance=tolerance,
                limit=thresholds.stuck_repeat_count,
            )
            for item in run_records:
                results[item.record_id] = (QualityFlag.FAILED, reason)

    for record in ordered:
        if record.value is None:
            _flush(run)
            run = []
            continue
        if run and _close(run[-1], record):
            run.append(record)
        else:
            _flush(run)
            run = [record]
    _flush(run)
    return results


def vocabulary_check(
    record: ObservationRecord, thresholds: QCThresholds = DEMO_THRESHOLDS
) -> tuple[QualityFlag, str]:
    """A categorical result must name a class from the controlled vocabulary."""
    if record.quantity_kind is not QuantityKind.CATEGORICAL:
        return QualityFlag.NOT_EVALUATED, "not a categorical result"
    allowed = thresholds.categorical_vocabulary.get(record.parameter.value)
    if allowed is None:
        return QualityFlag.NOT_EVALUATED, (
            f"no controlled vocabulary declared for {record.parameter.value}"
        )
    if record.condition_class not in allowed:
        return QualityFlag.FAILED, (
            f"vocabulary: {record.condition_class!r} is not in the controlled "
            f"vocabulary {sorted(allowed)} for {record.parameter.value}"
        )
    return QualityFlag.PASSED, "vocabulary: class is in the controlled vocabulary"


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def _escalate(original: QualityFlag, candidate: QualityFlag) -> QualityFlag:
    if original is QualityFlag.MISSING:
        return QualityFlag.MISSING
    if candidate is QualityFlag.MISSING:
        return original
    return original if _SEVERITY[int(original)] >= _SEVERITY[int(candidate)] else candidate


def run_qc(
    records: Sequence[ObservationRecord],
    *,
    thresholds: QCThresholds = DEMO_THRESHOLDS,
    now_utc: datetime | None = None,
) -> QCReport:
    """Run every check and return flags plus reasons.  Nothing is deleted."""
    channels: dict[tuple[str, str, str, str], list[ObservationRecord]] = {}
    for record in records:
        channels.setdefault(channel_key(record), []).append(record)

    outcomes: dict[str, QCOutcome] = {}
    for series in channels.values():
        ordered = sorted(series, key=lambda item: (item.observed_at_utc, item.record_id))
        stuck = stuck_value_check(ordered, thresholds)
        for index, record in enumerate(ordered):
            reasons: list[str] = []
            checks: dict[str, str] = {}
            failed_checks: set[str] = set()
            # The aggregate is the worst result among the checks that could
            # actually run.  ``NOT_EVALUATED`` is reserved for a record no check
            # applied to, so a channel with an inapplicable test is not demoted
            # for having one.
            applied: list[QualityFlag] = []

            if record.qualifier is Qualifier.MISSING:
                for name in ("gross_range", "spike", "stuck_value", "vocabulary"):
                    checks[name] = "not evaluated: missing result"
                outcomes[record.record_id] = QCOutcome(
                    record_id=record.record_id,
                    original_flag=record.quality_flag,
                    flag=QualityFlag.MISSING,
                    reasons=(
                        "missing result: no information, and not a non-detect",
                    ),
                    checks=checks,
                    failed_checks=frozenset({"missing"}),
                )
                continue

            if record.is_censored:
                checks["gross_range"] = (
                    "not evaluated: censored result carries a bound, not a value"
                )
            else:
                range_flag, range_reason = gross_range_check(record, thresholds)
                checks["gross_range"] = range_reason
                if range_flag is not QualityFlag.NOT_EVALUATED:
                    applied.append(range_flag)
                if range_flag in (QualityFlag.SUSPECT, QualityFlag.FAILED):
                    reasons.append(range_reason)
                    failed_checks.add("gross_range")

            previous = ordered[index - 1] if index > 0 else None
            following = ordered[index + 1] if index + 1 < len(ordered) else None
            spike_flag, spike_reason = spike_check(record, previous, following, thresholds)
            checks["spike"] = spike_reason
            if spike_flag is not QualityFlag.NOT_EVALUATED:
                applied.append(spike_flag)
            if spike_flag in (QualityFlag.SUSPECT, QualityFlag.FAILED):
                reasons.append(spike_reason)
                failed_checks.add("spike")

            if record.record_id in stuck:
                stuck_flag, stuck_reason = stuck[record.record_id]
                checks["stuck_value"] = stuck_reason
                applied.append(stuck_flag)
                reasons.append(stuck_reason)
                failed_checks.add("stuck_value")
            else:
                checks["stuck_value"] = "stuck value: no flat-line run detected"

            vocabulary_flag, vocabulary_reason = vocabulary_check(record, thresholds)
            checks["vocabulary"] = vocabulary_reason
            if vocabulary_flag is not QualityFlag.NOT_EVALUATED:
                applied.append(vocabulary_flag)
            if vocabulary_flag in (QualityFlag.SUSPECT, QualityFlag.FAILED):
                reasons.append(vocabulary_reason)
                failed_checks.add("vocabulary")

            if applied:
                worst = max(applied, key=lambda item: _SEVERITY[int(item)])
                flag = _escalate(record.quality_flag, worst)
            else:
                flag = _escalate(record.quality_flag, QualityFlag.NOT_EVALUATED)

            if record.quality_flag in (QualityFlag.SUSPECT, QualityFlag.FAILED):
                reasons.append(
                    f"source flag {int(record.quality_flag)} retained; QC never clears "
                    "a concern declared upstream"
                )

            outcomes[record.record_id] = QCOutcome(
                record_id=record.record_id,
                original_flag=record.quality_flag,
                flag=flag,
                reasons=tuple(reasons),
                checks=checks,
                failed_checks=frozenset(failed_checks),
            )

    health = _asset_health(records, outcomes, thresholds, now_utc)
    notes = (
        "QARTOD-inspired demo checks [S23]-[S24]; not an official certification",
        "thresholds are ASSUMPTIONS, not heavy-metal quality standards",
        "health is separate from material saturation",
        "health covers every asset, including records without a sensor_id",
    )
    return QCReport(
        outcomes=outcomes, asset_health=health, thresholds=thresholds, notes=notes
    )


def _asset_health(
    records: Sequence[ObservationRecord],
    outcomes: Mapping[str, QCOutcome],
    thresholds: QCThresholds,
    now_utc: datetime | None,
) -> dict[str, AssetHealth]:
    """Health per asset.

    Every record contributes, whether or not it names a sensor.  ``last_seen``
    is split in two: the newest contact of any kind, and the newest reading that
    carried information.  The age check runs on the second, and an asset with no
    usable reading at all is stale by definition instead of being skipped.
    """
    grouped: dict[str, list[ObservationRecord]] = {}
    for record in records:
        kind, identifier = asset_key(record)
        grouped.setdefault(f"{kind}:{identifier}", []).append(record)

    health: dict[str, AssetHealth] = {}
    for key, series in grouped.items():
        kind, identifier = key.split(":", 1)
        failed = stuck = suspect = False
        reasons: list[str] = []
        missing = 0
        last_observed: datetime | None = None
        last_usable: datetime | None = None
        age_limit = thresholds.default_max_data_age_s
        for record in series:
            outcome = outcomes.get(record.record_id)
            flag = record.quality_flag if outcome is None else outcome.flag
            age_limit = max(age_limit, thresholds.max_data_age_for(record))
            if last_observed is None or record.observed_at_utc > last_observed:
                last_observed = record.observed_at_utc
            if flag is QualityFlag.MISSING:
                missing += 1
                continue
            if last_usable is None or record.observed_at_utc > last_usable:
                last_usable = record.observed_at_utc
            if flag is QualityFlag.FAILED:
                failed = True
            if flag is QualityFlag.SUSPECT:
                suspect = True
            if outcome is not None and "stuck_value" in outcome.failed_checks:
                stuck = True
        if failed:
            reasons.append("at least one reading failed a demo QC check")
        if stuck:
            reasons.append("flat-line run detected: the channel repeats a value")
        if suspect:
            reasons.append("at least one reading is suspect")
        missing_fraction = missing / max(len(series), 1)
        if missing_fraction > 0.0:
            reasons.append(
                f"{missing}/{len(series)} scheduled readings are missing "
                "(missing is not a non-detect: no information)"
            )

        stale = False
        age: float | None = None
        if last_usable is None:
            stale = True
            reasons.append(
                "no usable reading at all: every record from this asset is missing, "
                "so the data age is unbounded (this is exactly the case the "
                "inherited version skipped)"
            )
        elif now_utc is not None:
            age = (now_utc - last_usable).total_seconds()
            if age > age_limit:
                stale = True
                reasons.append(
                    f"newest usable reading is {age:.0f} s old, beyond the demo data "
                    f"age limit {age_limit:.0f} s (ASSUMPTION)"
                )
        health[key] = AssetHealth(
            asset_id=identifier,
            asset_kind=kind,
            n_records=len(series),
            last_observed_at_utc=last_observed,
            last_usable_at_utc=last_usable,
            failed=failed,
            stuck=stuck,
            suspect=suspect,
            stale=stale,
            missing_fraction=missing_fraction,
            data_age_s=age,
            max_data_age_s=age_limit,
            reasons=tuple(reasons),
        )
    return health


def apply_qc_flags(
    records: Sequence[ObservationRecord], report: QCReport
) -> list[ObservationRecord]:
    """Return copies carrying the escalated flag.

    This is offered for export and display.  The estimator does **not** need it:
    it reads the report as a side channel so the original records keep their
    source flags verbatim.  Escalation is one-way, and the original flag stays
    visible in the report.
    """
    updated: list[ObservationRecord] = []
    for record in records:
        outcome = report.outcomes.get(record.record_id)
        if outcome is None or outcome.flag is record.quality_flag:
            updated.append(record)
        else:
            updated.append(replace(record, quality_flag=outcome.flag))
    return updated
