"""Transparent, QARTOD-inspired quality control (MODEL_SPEC section 6).

Three checks and one channel rule, all of them readable and all of them
configurable:

``gross_range``   the value lies inside a plausibility band for its channel;
``spike``         the value differs from the mean of its neighbours by more
                  than a threshold;
``stuck_value``   a channel repeats the same number too many times in a row;
``data_age``      the newest record of a channel is older than an age limit.

The thresholds in :data:`DEMO_THRESHOLDS` are **demonstration assumptions**.
They are instrument-plausibility bands chosen so the demonstration shows a
failed sensor; they are explicitly **not** official heavy-metal quality
standards, and they are not a QARTOD certification.  The flag vocabulary is
taken from the shared contract (1 passed, 2 not evaluated, 3 suspect, 4 failed,
9 missing), inspired by [S23]-[S24].

Sensor health is kept strictly separate from material saturation: a
:class:`SensorHealth` object says something about an instrument and nothing at
all about how loaded the mesh is.  Nothing here deletes or repairs a record;
checks return outcomes, and an escalated flag is always reported beside the
original one.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from ..contracts import ObservationRecord, Parameter, Qualifier, QualityFlag
from ..units import UnitError, convert_scalar

__all__ = [
    "QCThresholds",
    "DEMO_THRESHOLDS",
    "QCOutcome",
    "SensorHealth",
    "QCReport",
    "gross_range_check",
    "spike_check",
    "stuck_value_check",
    "run_qc",
    "apply_qc_flags",
    "channel_key",
]

#: Ordering used when a check escalates a flag.  ``MISSING`` is not "worse"
#: than ``FAILED``: it is a different statement, and it is never overwritten.
_SEVERITY: Mapping[int, int] = {
    int(QualityFlag.PASSED): 0,
    int(QualityFlag.NOT_EVALUATED): 1,
    int(QualityFlag.SUSPECT): 2,
    int(QualityFlag.FAILED): 3,
}


@dataclass(frozen=True, slots=True)
class QCThresholds:
    """Demo QC thresholds.  ASSUMPTION, not an environmental standard.

    ``gross_range`` and ``spike`` are expressed in ``expected_unit`` for the
    channel.  A record in another unit on the same physical ladder is
    converted with ``mesh_demo.units``; a record on a different ladder is not
    checked at all and is flagged ``NOT_EVALUATED`` with a reason, because
    silently comparing ng/g with ng/L would be worse than not checking.
    """

    gross_range: Mapping[str, tuple[float, float]]
    spike: Mapping[str, float]
    stuck_tolerance: Mapping[str, float]
    expected_unit: Mapping[str, str]
    stuck_repeat_count: int = 5
    max_data_age_s: float = 21600.0
    provenance: str = "assumption"
    source_ref: str = (
        "demonstration thresholds, docs/MODEL_SPEC.md section 6; QARTOD-inspired "
        "[S23]-[S24]; not an official heavy-metal standard and not a certification"
    )


#: Demonstration thresholds.  Every number below is an ASSUMPTION.
DEMO_THRESHOLDS = QCThresholds(
    gross_range={
        Parameter.PB.value: (0.0, 5000.0),  # ng/L, instrument plausibility band
        Parameter.HG.value: (0.0, 500.0),  # ng/L
        Parameter.TEMPERATURE.value: (-2.0, 35.0),  # degC
        Parameter.CONDUCTIVITY.value: (0.0, 70.0),  # mS/cm
        Parameter.SALINITY.value: (0.0, 42.0),  # practical salinity
        Parameter.PH.value: (6.0, 9.5),
        Parameter.TURBIDITY.value: (0.0, 1000.0),  # NTU
        Parameter.CURRENT_EAST.value: (-3.0, 3.0),  # m/s
        Parameter.CURRENT_NORTH.value: (-3.0, 3.0),  # m/s
        Parameter.MESH_TILT.value: (-90.0, 90.0),  # deg
        Parameter.BATTERY_VOLTAGE.value: (9.0, 16.0),  # V
    },
    spike={
        Parameter.PB.value: 400.0,
        Parameter.HG.value: 60.0,
        Parameter.TEMPERATURE.value: 3.0,
        Parameter.CONDUCTIVITY.value: 5.0,
        Parameter.SALINITY.value: 3.0,
        Parameter.PH.value: 0.6,
        Parameter.TURBIDITY.value: 200.0,
        Parameter.CURRENT_EAST.value: 0.6,
        Parameter.CURRENT_NORTH.value: 0.6,
        Parameter.BATTERY_VOLTAGE.value: 1.0,
    },
    stuck_tolerance={
        Parameter.PB.value: 1.0e-9,
        Parameter.HG.value: 1.0e-9,
        Parameter.TEMPERATURE.value: 1.0e-6,
        Parameter.CONDUCTIVITY.value: 1.0e-6,
        Parameter.SALINITY.value: 1.0e-6,
        Parameter.PH.value: 1.0e-6,
        Parameter.TURBIDITY.value: 1.0e-6,
        Parameter.CURRENT_EAST.value: 1.0e-9,
        Parameter.CURRENT_NORTH.value: 1.0e-9,
        Parameter.BATTERY_VOLTAGE.value: 1.0e-6,
    },
    expected_unit={
        Parameter.PB.value: "ng/L",
        Parameter.HG.value: "ng/L",
        Parameter.TEMPERATURE.value: "degC",
        Parameter.CONDUCTIVITY.value: "mS/cm",
        Parameter.SALINITY.value: "1",
        Parameter.PH.value: "pH",
        Parameter.TURBIDITY.value: "NTU",
        Parameter.CURRENT_EAST.value: "m/s",
        Parameter.CURRENT_NORTH.value: "m/s",
        Parameter.MESH_TILT.value: "deg",
        Parameter.BATTERY_VOLTAGE.value: "V",
    },
)


@dataclass(frozen=True, slots=True)
class QCOutcome:
    """The result of running the checks on one record.

    ``flag`` is never milder than ``original_flag``: quality control may raise
    a concern, it may not clear one that the source already declared.
    """

    record_id: str
    original_flag: QualityFlag
    flag: QualityFlag
    reasons: tuple[str, ...] = ()
    checks: Mapping[str, str] = field(default_factory=dict)

    @property
    def escalated(self) -> bool:
        return self.flag != self.original_flag

    @property
    def usable(self) -> bool:
        """Usable for the likelihood: passed or not-evaluated, and not missing."""
        return self.flag in (QualityFlag.PASSED, QualityFlag.NOT_EVALUATED)


@dataclass(frozen=True, slots=True)
class SensorHealth:
    """Instrument health.  Says nothing about mesh loading or capacity.

    A saturated mesh and a broken probe are different problems with different
    actions, and this object is only ever evidence about the second one.
    """

    sensor_id: str
    n_records: int
    last_observed_at_utc: datetime | None
    failed: bool = False
    stuck: bool = False
    suspect: bool = False
    missing_fraction: float = 0.0
    reasons: tuple[str, ...] = ()

    @property
    def healthy(self) -> bool:
        return not (self.failed or self.stuck or self.suspect)


@dataclass(frozen=True, slots=True)
class QCReport:
    outcomes: Mapping[str, QCOutcome]
    sensor_health: Mapping[str, SensorHealth]
    thresholds: QCThresholds
    notes: tuple[str, ...] = ()

    def flag_for(self, record: ObservationRecord) -> QualityFlag:
        outcome = self.outcomes.get(record.record_id)
        return record.quality_flag if outcome is None else outcome.flag

    def failed_sensor_ids(self) -> tuple[str, ...]:
        return tuple(sorted(k for k, v in self.sensor_health.items() if v.failed))

    def stuck_sensor_ids(self) -> tuple[str, ...]:
        return tuple(sorted(k for k, v in self.sensor_health.items() if v.stuck))

    def suspect_sensor_ids(self) -> tuple[str, ...]:
        return tuple(sorted(k for k, v in self.sensor_health.items() if v.suspect))


def channel_key(record: ObservationRecord) -> tuple[str, str, str, str]:
    """A channel is one parameter, from one sensor, at one station, one method."""
    return (
        record.station_id,
        record.sensor_id or record.sample_id or "unidentified",
        record.parameter.value,
        record.method_id,
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
        return None, "no value to check"
    expected = thresholds.expected_unit.get(record.parameter.value)
    if expected is None:
        return None, f"no expected unit declared for {record.parameter.value}"
    if record.unit == expected:
        return float(record.value), None
    try:
        return float(convert_scalar(float(record.value), record.unit, expected)), None
    except UnitError as exc:
        return None, (
            f"unit {record.unit!r} is not on the same physical ladder as "
            f"{expected!r}; range check not evaluated ({exc})"
        )


def gross_range_check(
    record: ObservationRecord, thresholds: QCThresholds = DEMO_THRESHOLDS
) -> tuple[QualityFlag, str]:
    """QARTOD-inspired gross-range test.  Demo band, not a standard."""
    band = thresholds.gross_range.get(record.parameter.value)
    if band is None:
        return QualityFlag.NOT_EVALUATED, "no demo range band for this parameter"
    value, reason = _value_in_expected_unit(record, thresholds)
    if value is None:
        return QualityFlag.NOT_EVALUATED, reason or "not evaluated"
    low, high = band
    if value < low or value > high:
        return QualityFlag.FAILED, (
            f"gross range: {value:.6g} outside the demo band [{low:g}, {high:g}] "
            f"{thresholds.expected_unit[record.parameter.value]} (ASSUMPTION)"
        )
    return QualityFlag.PASSED, "gross range: inside the demo band"


def spike_check(
    record: ObservationRecord,
    previous: ObservationRecord | None,
    following: ObservationRecord | None,
    thresholds: QCThresholds = DEMO_THRESHOLDS,
) -> tuple[QualityFlag, str]:
    """QARTOD-inspired spike test against the mean of the two neighbours."""
    limit = thresholds.spike.get(record.parameter.value)
    if limit is None:
        return QualityFlag.NOT_EVALUATED, "no demo spike threshold for this parameter"
    if previous is None or following is None:
        return QualityFlag.NOT_EVALUATED, "spike test needs both neighbours"
    values = []
    for item in (record, previous, following):
        value, reason = _value_in_expected_unit(item, thresholds)
        if value is None:
            return QualityFlag.NOT_EVALUATED, reason or "neighbour without a value"
        values.append(value)
    centre, before, after = values
    excursion = abs(centre - 0.5 * (before + after))
    if excursion > limit:
        return QualityFlag.SUSPECT, (
            f"spike: |{centre:.6g} - mean(neighbours)| = {excursion:.6g} exceeds the demo "
            f"threshold {limit:g} (ASSUMPTION)"
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
    parameter = series[0].parameter.value
    tolerance = thresholds.stuck_tolerance.get(parameter)
    if tolerance is None:
        return results
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
            reason = (
                f"stuck value: {len(run_records)} consecutive readings within "
                f"{tolerance:g} of each other (demo threshold "
                f"{thresholds.stuck_repeat_count}, ASSUMPTION)"
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
    for key, series in channels.items():
        ordered = sorted(series, key=lambda item: (item.observed_at_utc, item.record_id))
        stuck = stuck_value_check(ordered, thresholds)
        for index, record in enumerate(ordered):
            reasons: list[str] = []
            checks: dict[str, str] = {}
            flag = record.quality_flag

            if record.qualifier is Qualifier.MISSING:
                checks["gross_range"] = "not evaluated: missing result"
                checks["spike"] = "not evaluated: missing result"
                checks["stuck_value"] = "not evaluated: missing result"
                outcomes[record.record_id] = QCOutcome(
                    record_id=record.record_id,
                    original_flag=record.quality_flag,
                    flag=QualityFlag.MISSING,
                    reasons=("missing result: no chemical information, not a non-detect",),
                    checks=checks,
                )
                continue

            if record.is_censored:
                checks["gross_range"] = (
                    "not evaluated: censored result carries a bound, not a value"
                )
            else:
                range_flag, range_reason = gross_range_check(record, thresholds)
                checks["gross_range"] = range_reason
                flag = _escalate(flag, range_flag)
                if range_flag in (QualityFlag.SUSPECT, QualityFlag.FAILED):
                    reasons.append(range_reason)

            previous = ordered[index - 1] if index > 0 else None
            following = ordered[index + 1] if index + 1 < len(ordered) else None
            spike_flag, spike_reason = spike_check(record, previous, following, thresholds)
            checks["spike"] = spike_reason
            flag = _escalate(flag, spike_flag)
            if spike_flag in (QualityFlag.SUSPECT, QualityFlag.FAILED):
                reasons.append(spike_reason)

            if record.record_id in stuck:
                stuck_flag, stuck_reason = stuck[record.record_id]
                checks["stuck_value"] = stuck_reason
                flag = _escalate(flag, stuck_flag)
                reasons.append(stuck_reason)
            else:
                checks["stuck_value"] = "stuck value: no flat-line run detected"

            if record.quality_flag in (QualityFlag.SUSPECT, QualityFlag.FAILED):
                reasons.append(
                    f"source flag {int(record.quality_flag)} retained; QC never clears a "
                    "concern declared upstream"
                )

            outcomes[record.record_id] = QCOutcome(
                record_id=record.record_id,
                original_flag=record.quality_flag,
                flag=flag,
                reasons=tuple(reasons),
                checks=checks,
            )

    health = _sensor_health(records, outcomes, thresholds, now_utc)
    notes = [
        "QARTOD-inspired demo checks [S23]-[S24]; not an official certification",
        "thresholds are ASSUMPTIONS, not heavy-metal quality standards",
        "sensor health is separate from material saturation",
    ]
    return QCReport(
        outcomes=outcomes, sensor_health=health, thresholds=thresholds, notes=tuple(notes)
    )


def _sensor_health(
    records: Sequence[ObservationRecord],
    outcomes: Mapping[str, QCOutcome],
    thresholds: QCThresholds,
    now_utc: datetime | None,
) -> dict[str, SensorHealth]:
    grouped: dict[str, list[ObservationRecord]] = {}
    for record in records:
        if record.sensor_id is None:
            continue
        grouped.setdefault(record.sensor_id, []).append(record)

    health: dict[str, SensorHealth] = {}
    for sensor_id, series in grouped.items():
        failed = False
        stuck = False
        suspect = False
        reasons: list[str] = []
        missing = 0
        last_seen: datetime | None = None
        for record in series:
            outcome = outcomes.get(record.record_id)
            flag = record.quality_flag if outcome is None else outcome.flag
            if flag is QualityFlag.MISSING:
                missing += 1
                continue
            if last_seen is None or record.observed_at_utc > last_seen:
                last_seen = record.observed_at_utc
            if flag is QualityFlag.FAILED:
                failed = True
            if flag is QualityFlag.SUSPECT:
                suspect = True
            if outcome is not None and any("stuck value" in r for r in outcome.reasons):
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
                "(missing is not a non-detect: no chemical information)"
            )
        if now_utc is not None and last_seen is not None:
            age = (now_utc - last_seen).total_seconds()
            if age > thresholds.max_data_age_s:
                reasons.append(
                    f"newest usable reading is {age:.0f} s old, beyond the demo age limit "
                    f"{thresholds.max_data_age_s:.0f} s (ASSUMPTION)"
                )
        health[sensor_id] = SensorHealth(
            sensor_id=sensor_id,
            n_records=len(series),
            last_observed_at_utc=last_seen,
            failed=failed,
            stuck=stuck,
            suspect=suspect,
            missing_fraction=missing_fraction,
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
