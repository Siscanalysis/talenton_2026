"""The observation operator: which record may be compared with which model
quantity (``docs/MODEL_SPEC.md`` section 6).

This module answers one question per record, and it answers it out loud:

``ASSIMILATE``      the record can enter the likelihood against a named model
                    quantity, after an explicit unit conversion;
``EVIDENCE_ONLY``   the record is kept, displayed and may count for data age,
                    but it does not enter the likelihood;
``REJECT``          the record cannot be read as the requested quantity at all.

The rules it enforces, all of them from the shared contract:

* only ``Pb`` and ``Hg`` records carry chemical information.  Temperature,
  conductivity, salinity, pH and turbidity are context: they constrain water
  conditions and QC, never a metal concentration;
* a ``total_recoverable`` result is **not** assimilated against a ``labile``
  model state unless an explicit ratio operator is switched on.  The default is
  off, and such records stay unassimilated evidence;
* a passive sampler reports an accumulated mass over an exposure window.  It is
  displayed and counted for data age, and it is never forced into ng/L;
* sediment and sorbent matrices are rejected as aqueous water-concentration
  inputs.  A sorbent assay is compared with a **loading** (kg/kg), and only when
  its ``media_id`` is the media that is installed now;
* records with quality flag 3 or 4 are kept as sensor-health evidence and stay
  out of the likelihood; a missing record contributes nothing at all.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

from ..contracts import (
    AcquisitionKind,
    CONTEXT_PARAMETERS,
    Fraction,
    Matrix,
    METAL_PARAMETERS,
    ObservationRecord,
    Parameter,
    Qualifier,
    QualityFlag,
)
from ..units import (
    UnitError,
    to_si_aqueous_concentration,
    to_si_mass,
    to_si_solid_loading,
)
from .qc import QCReport

__all__ = [
    "AssimilationDecision",
    "ModelQuantity",
    "FractionRatioOperator",
    "OperatorConfig",
    "ObservationUse",
    "AssimilationSet",
    "classify_record",
    "build_assimilation_set",
]


class AssimilationDecision(str, enum.Enum):
    ASSIMILATE = "assimilate"
    EVIDENCE_ONLY = "evidence_only"
    REJECT = "reject"


class ModelQuantity(str, enum.Enum):
    """What a record can be compared with, if anything."""

    AQUEOUS_CONCENTRATION = "aqueous_concentration"  # kg m^-3 at a station
    SOLID_LOADING = "solid_loading"  # kg kg^-1 on a named media id
    ACCUMULATED_MASS = "accumulated_mass"  # kg over an exposure window
    CONTEXT = "context"  # water conditions / instrument health
    NONE = "none"


@dataclass(frozen=True, slots=True)
class FractionRatioOperator:
    """An explicit, documented, uncertain fraction-ratio operator.

    Switched **off** by default.  When it is on, a record of the measured
    fraction is not converted into a point value of the model fraction: it
    becomes an *interval* observation ``[value / ratio_high, value / ratio_low]``
    which the censored likelihood already knows how to use.  The ratio is an
    assumption, so the honest result of using it is a wider interval, never a
    sharper number.
    """

    enabled: bool = False
    ratio: float = 1.6
    ratio_interval: tuple[float, float] = (1.05, 3.0)
    provenance: str = "assumption"
    source_ref: str = (
        "ASSUMPTION: total-recoverable to labile ratio for a demonstration. A real "
        "ratio depends on particle load, method and site and is not a constant."
    )

    def interval_si(self, value_si: float) -> tuple[float, float]:
        low, high = self.ratio_interval
        if low <= 0.0 or high < low:
            raise ValueError("ratio_interval must be positive and ordered")
        return (value_si / high, value_si / low)


@dataclass(frozen=True, slots=True)
class OperatorConfig:
    """Which records this build is willing to assimilate, and against what."""

    #: The chemical fraction each element's model state represents.
    model_fraction: Mapping[str, Fraction] = field(
        default_factory=lambda: {"Pb": Fraction.LABILE, "Hg": Fraction.LABILE}
    )
    #: Matrices accepted as an aqueous water-column concentration.
    aqueous_matrices: frozenset[Matrix] = frozenset({Matrix.SEAWATER})
    #: Matrices explicitly rejected as an aqueous water-column concentration.
    rejected_aqueous_matrices: frozenset[Matrix] = frozenset(
        {Matrix.SEDIMENT, Matrix.SORBENT}
    )
    #: The ratio operator for total-recoverable records.  Default: OFF.
    total_recoverable_operator: FractionRatioOperator = FractionRatioOperator()
    #: The media id installed on the panel right now.  A sorbent assay of any
    #: other media id is evidence about retrieved material, not about this panel.
    active_media_id: str | None = None
    #: Quality flags excluded from the likelihood but kept as evidence.
    sensor_health_flags: frozenset[QualityFlag] = frozenset(
        {QualityFlag.SUSPECT, QualityFlag.FAILED}
    )
    #: Records observed before this moment cannot describe the active media.
    active_media_installed_at_utc: datetime | None = None


@dataclass(frozen=True, slots=True)
class ObservationUse:
    """What the operator decided about one record, and why."""

    record_id: str
    station_id: str
    decision: AssimilationDecision
    model_quantity: ModelQuantity
    reason: str
    element: str | None = None
    observed_at_utc: datetime | None = None
    value_si: float | None = None
    lower_si: float | None = None
    upper_si: float | None = None
    sigma_si: float | None = None
    is_censored: bool = False
    counts_for_data_age: bool = False
    sensor_health_evidence: bool = False
    media_id: str | None = None
    quality_flag: QualityFlag = QualityFlag.NOT_EVALUATED
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def assimilable(self) -> bool:
        return self.decision is AssimilationDecision.ASSIMILATE


@dataclass(frozen=True, slots=True)
class AssimilationSet:
    uses: tuple[ObservationUse, ...]
    config: OperatorConfig

    @property
    def assimilable(self) -> tuple[ObservationUse, ...]:
        return tuple(u for u in self.uses if u.decision is AssimilationDecision.ASSIMILATE)

    @property
    def evidence_only(self) -> tuple[ObservationUse, ...]:
        return tuple(u for u in self.uses if u.decision is AssimilationDecision.EVIDENCE_ONLY)

    @property
    def rejected(self) -> tuple[ObservationUse, ...]:
        return tuple(u for u in self.uses if u.decision is AssimilationDecision.REJECT)

    @property
    def sensor_health_evidence(self) -> tuple[ObservationUse, ...]:
        return tuple(u for u in self.uses if u.sensor_health_evidence)

    def by_id(self, record_id: str) -> ObservationUse | None:
        for use in self.uses:
            if use.record_id == record_id:
                return use
        return None

    def record_ids(self, decision: AssimilationDecision | None = None) -> tuple[str, ...]:
        if decision is None:
            return tuple(u.record_id for u in self.uses)
        return tuple(u.record_id for u in self.uses if u.decision is decision)


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def _sigma_si(record: ObservationRecord) -> float | None:
    """Reported uncertainty in SI, or None when the record does not know it.

    Unknown uncertainty stays unknown here.  The estimator substitutes a stated
    assumption and records that it did so; the operator never invents one.
    """
    if record.uncertainty_std is None:
        return None
    try:
        return abs(to_si_aqueous_concentration(float(record.uncertainty_std), record.unit))
    except UnitError:
        return None


def classify_record(
    record: ObservationRecord,
    config: OperatorConfig,
    *,
    qc_report: QCReport | None = None,
) -> ObservationUse:
    """Decide how one record may be used.  Never mutates the record."""
    flag = record.quality_flag if qc_report is None else qc_report.flag_for(record)
    base = dict(
        record_id=record.record_id,
        station_id=record.station_id,
        element=record.parameter.value if record.is_metal else None,
        observed_at_utc=record.observed_at_utc,
        media_id=record.media_id,
        quality_flag=flag,
    )

    # 1. context channels: never a metal concentration.
    if record.parameter in CONTEXT_PARAMETERS or record.parameter not in METAL_PARAMETERS:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.CONTEXT,
            reason=(
                f"{record.parameter.value} is a context or housekeeping channel: it "
                "constrains water conditions, transport forcing or instrument health, "
                "never a Pb or Hg concentration"
            ),
            counts_for_data_age=False,
            sensor_health_evidence=flag in config.sensor_health_flags,
            **base,
        )

    # 2. solid and sediment matrices are not an aqueous concentration.
    if record.matrix in config.rejected_aqueous_matrices:
        if (
            record.matrix is Matrix.SORBENT
            and record.acquisition_kind is AcquisitionKind.MEDIA_ASSAY
        ):
            return _classify_media_assay(record, config, flag, base)
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            model_quantity=ModelQuantity.NONE,
            reason=(
                f"matrix {record.matrix.value!r} is rejected as an aqueous water "
                "concentration input; a solid assay uses the mass-based ladder and a "
                "separate interpretation"
            ),
            **base,
        )

    # 3. passive samplers report an accumulated mass, not a point concentration.
    if record.acquisition_kind is AcquisitionKind.PASSIVE_SAMPLER:
        mass_kg: float | None = None
        note = ""
        if record.value is not None:
            try:
                mass_kg = to_si_mass(float(record.value), record.unit)
            except UnitError as exc:
                note = f" (unit not on the mass ladder: {exc})"
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.ACCUMULATED_MASS,
            reason=(
                "integrated passive-sampler exposure: an accumulated mass over a "
                "window, displayed and counted for data age, never converted into "
                "ng/L without a justified sampler operator" + note
            ),
            value_si=mass_kg,
            counts_for_data_age=True,
            sensor_health_evidence=False,
            diagnostics={
                "sampling_start_utc": record.sampling_start_utc,
                "sampling_end_utc": record.sampling_end_utc,
                "accumulated_mass_unit": record.unit,
            },
            **base,
        )

    # 4. the aqueous ladder from here on.
    if record.matrix not in config.aqueous_matrices:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.NONE,
            reason=(
                f"matrix {record.matrix.value!r} is not the modelled water column; kept "
                "as evidence, not assimilated"
            ),
            counts_for_data_age=False,
            **base,
        )

    # 5. missing: no chemical information at all.
    if record.qualifier is Qualifier.MISSING:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.NONE,
            reason=(
                "missing result: it contributes nothing to the likelihood and does not "
                "refresh the data age; missing is not a non-detect"
            ),
            counts_for_data_age=False,
            sensor_health_evidence=True,
            **base,
        )

    # 6. quality flags 3 and 4: sensor-health evidence, out of the likelihood.
    if flag in config.sensor_health_flags:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.NONE,
            reason=(
                f"quality flag {int(flag)}: excluded from the likelihood and kept as "
                "sensor-health evidence"
            ),
            counts_for_data_age=False,
            sensor_health_evidence=True,
            **base,
        )

    # 7. chemical fraction.
    expected = config.model_fraction.get(record.parameter.value, Fraction.LABILE)
    if record.fraction is not expected:
        operator = config.total_recoverable_operator
        if record.fraction is Fraction.TOTAL_RECOVERABLE and operator.enabled:
            interval = _aqueous_interval(record)
            if interval is None:
                return ObservationUse(
                    decision=AssimilationDecision.REJECT,
                    model_quantity=ModelQuantity.NONE,
                    reason="total-recoverable record without a usable value or interval",
                    **base,
                )
            low, high = interval
            lower_si, _ = operator.interval_si(low)
            _, upper_si = operator.interval_si(high)
            return ObservationUse(
                decision=AssimilationDecision.ASSIMILATE,
                model_quantity=ModelQuantity.AQUEOUS_CONCENTRATION,
                reason=(
                    "total recoverable assimilated through the explicit ratio operator "
                    f"(ASSUMPTION ratio interval {operator.ratio_interval}); the record "
                    "enters as an interval, not as a point value"
                ),
                lower_si=lower_si,
                upper_si=upper_si,
                is_censored=True,
                counts_for_data_age=True,
                diagnostics={
                    "ratio_operator": True,
                    "ratio_interval": operator.ratio_interval,
                    "source_ref": operator.source_ref,
                },
                **base,
            )
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.NONE,
            reason=(
                f"chemical fraction {record.fraction.value!r} is not the model state "
                f"{expected.value!r}; it is retained as unassimilated evidence. Merging "
                "the two would need an explicit, documented, uncertain ratio operator, "
                "which is switched off"
            ),
            counts_for_data_age=True,
            diagnostics={"measured_fraction": record.fraction.value,
                         "model_fraction": expected.value},
            **base,
        )

    # 8. a quantified or censored aqueous record of the right fraction.
    if record.qualifier is Qualifier.QUANTIFIED:
        try:
            value_si = to_si_aqueous_concentration(float(record.value), record.unit)
        except (UnitError, TypeError) as exc:
            return ObservationUse(
                decision=AssimilationDecision.REJECT,
                model_quantity=ModelQuantity.NONE,
                reason=f"unit {record.unit!r} cannot be read as an aqueous concentration: {exc}",
                **base,
            )
        return ObservationUse(
            decision=AssimilationDecision.ASSIMILATE,
            model_quantity=ModelQuantity.AQUEOUS_CONCENTRATION,
            reason=f"quantified {record.fraction.value} {record.parameter.value} in seawater",
            value_si=value_si,
            sigma_si=_sigma_si(record),
            counts_for_data_age=True,
            **base,
        )

    interval = _aqueous_interval(record)
    if interval is None:
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            model_quantity=ModelQuantity.NONE,
            reason="censored record without a finite interval; a non-detect must be a bound",
            **base,
        )
    return ObservationUse(
        decision=AssimilationDecision.ASSIMILATE,
        model_quantity=ModelQuantity.AQUEOUS_CONCENTRATION,
        reason=(
            f"{record.qualifier.value}: used as the bound it is, never as a zero and "
            "never dropped"
        ),
        lower_si=interval[0],
        upper_si=interval[1],
        is_censored=True,
        sigma_si=_sigma_si(record),
        counts_for_data_age=True,
        **base,
    )


def _aqueous_interval(record: ObservationRecord) -> tuple[float, float] | None:
    """The censoring interval, or a degenerate interval around a point value."""
    try:
        if record.qualifier is Qualifier.QUANTIFIED and record.value is not None:
            value = to_si_aqueous_concentration(float(record.value), record.unit)
            return (value, value)
        if record.lower_bound is None or record.upper_bound is None:
            return None
        return (
            to_si_aqueous_concentration(float(record.lower_bound), record.unit),
            to_si_aqueous_concentration(float(record.upper_bound), record.unit),
        )
    except UnitError:
        return None


def _classify_media_assay(
    record: ObservationRecord,
    config: OperatorConfig,
    flag: QualityFlag,
    base: Mapping[str, Any],
) -> ObservationUse:
    """A sorbent assay constrains the loading of the media it was taken from."""
    if record.value is None:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.NONE,
            reason="sorbent assay without a value",
            **base,
        )
    try:
        loading = to_si_solid_loading(float(record.value), record.unit)
    except UnitError as exc:
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            model_quantity=ModelQuantity.NONE,
            reason=(
                f"unit {record.unit!r} is not a solid-loading unit; the aqueous ladder is "
                f"never used for a solid assay ({exc})"
            ),
            **base,
        )
    active = config.active_media_id
    if active is None or record.media_id != active:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.SOLID_LOADING,
            reason=(
                f"assay of media {record.media_id!r}, which is not the media installed "
                f"now ({active!r}): it is evidence about retrieved material and must not "
                "be read as the current active-panel loading"
            ),
            value_si=loading,
            counts_for_data_age=False,
            diagnostics={"retrieved_media": True},
            **base,
        )
    installed_at = config.active_media_installed_at_utc
    if installed_at is not None and record.observed_at_utc < installed_at:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.SOLID_LOADING,
            reason=(
                "assay observed before the active media was installed; it cannot "
                "describe the panel that is in the water now"
            ),
            value_si=loading,
            counts_for_data_age=False,
            diagnostics={"retrieved_media": True},
            **base,
        )
    if flag in config.sensor_health_flags:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.SOLID_LOADING,
            reason=f"quality flag {int(flag)}: kept as evidence, out of the likelihood",
            value_si=loading,
            counts_for_data_age=False,
            sensor_health_evidence=True,
            **base,
        )
    sigma = None
    if record.uncertainty_std is not None:
        try:
            sigma = abs(to_si_solid_loading(float(record.uncertainty_std), record.unit))
        except UnitError:
            sigma = None
    return ObservationUse(
        decision=AssimilationDecision.ASSIMILATE,
        model_quantity=ModelQuantity.SOLID_LOADING,
        reason=(
            f"assay of the media installed now ({active!r}): it constrains the loading "
            "in kg/kg on the mass-based ladder"
        ),
        value_si=loading,
        sigma_si=sigma,
        counts_for_data_age=True,
        **base,
    )


def build_assimilation_set(
    records: Sequence[ObservationRecord],
    config: OperatorConfig | None = None,
    *,
    qc_report: QCReport | None = None,
) -> AssimilationSet:
    """Classify a whole batch, preserving order and every original identifier."""
    resolved = config or OperatorConfig()
    uses = tuple(classify_record(record, resolved, qc_report=qc_report) for record in records)
    return AssimilationSet(uses=uses, config=resolved)
