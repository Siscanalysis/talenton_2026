"""The observation operator: which record may be compared with which model
quantity (``docs/MODEL_SPEC.md`` section 8).

This module answers one question per record, and it answers it out loud:

``ASSIMILATE``      the record can enter the likelihood against a named model
                    quantity, after an explicit unit conversion;
``EVIDENCE_ONLY``   the record is kept, displayed and may count for data age,
                    but it does not enter the likelihood;
``REJECT``          the record cannot be read as the requested quantity at all.

Dispatch is on the **declared** :class:`~reactive_seabed_mat.contracts.QuantityKind`,
never on a guess assembled from ``(matrix, fraction, unit)``.  That is the whole
reason the contract carries the field.

The rules it enforces:

* only ``Pb`` and ``Hg`` records carry chemical information.  Temperature,
  conductivity, salinity, pH, turbidity, oxygen, redox and sulfide are context:
  they constrain conditions and QC, never a metal concentration;
* **porewater is a primary channel.**  The porewater concentration at the
  sediment face is the driving boundary condition of the reactive layer, and
  ``mat_porewater`` is the layer's own state variable.  Demoting them to
  evidence was the single most damaging assumption inherited from the
  vertical-panel concept;
* sediment and sorbent matrices are never read as a water concentration.  A
  sorbent assay is compared with a **loading** (kg/kg), and only when its
  ``media_id`` is the media installed now: after a replacement the assay
  describes the retrieved batch, not the tile now in place;
* a benthic-chamber record constrains the **areal flux**, which is the quantity
  the mat is judged on.  It needs its enclosed area and its deployment window;
* a DGT record is an integrated exposure: an accumulated mass over a window,
  never a point ng/L.  ``dgt_labile`` and ``labile`` are different operationally
  defined pools and are never merged, in either direction, with or without a
  ratio operator;
* a ``total_recoverable`` result is not assimilated against a ``labile`` model
  state unless the explicit ratio operator is switched on.  Default off; when on
  it **widens** the record into an interval rather than sharpening it into a
  number;
* mat-condition records constrain the degradation modes, per tile, and carry no
  chemistry.  **A burial record is evidence about physical position, never
  evidence of success:** burial reduces the apparent flux, and reading that as
  performance is the specific error :class:`~reactive_seabed_mat.contracts.AmbiguityFlag`
  ``BURIAL`` exists to prevent;
* records with quality flag 3 or 4 are kept as health evidence and stay out of
  the likelihood; a missing record contributes nothing at all.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

from ..contracts import (
    AcquisitionKind,
    CONTEXT_PARAMETERS,
    DegradationMode,
    Fraction,
    METAL_PARAMETERS,
    Matrix,
    ObservationRecord,
    Parameter,
    Qualifier,
    QualityFlag,
    QuantityKind,
)
from ..units import (
    UnitError,
    to_si_areal_flux,
    to_si_aqueous_concentration,
    to_si_length,
    to_si_mass,
    to_si_solid_loading,
    to_si_velocity,
)
from .condition import CONDITION_MODE, integrity_band_for_class
from .qc import QCReport

__all__ = [
    "AssimilationDecision",
    "ModelQuantity",
    "NEVER_MERGED_FRACTIONS",
    "UNMERGEABLE_FRACTIONS",
    "never_merged",
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

    # chemistry
    AQUEOUS_CONCENTRATION = "aqueous_concentration"   # kg m^-3 at a named target
    SOLID_LOADING = "solid_loading"                   # kg kg^-1 on a media id
    ACCUMULATED_MASS = "accumulated_mass"             # kg over an exposure window
    AREAL_FLUX = "areal_flux"                         # kg m^-2 s^-1, J_out
    # mat condition: no chemistry at all
    MAT_COVERAGE_FRACTION = "mat_coverage_fraction"
    BURIAL_DEPTH = "burial_depth"
    SCOUR_DEPTH = "scour_depth"
    MAT_DISPLACEMENT = "mat_displacement"
    MAT_TILT = "mat_tilt"
    MAT_DAMAGE_CLASS = "mat_damage_class"
    MAT_PERMEABILITY = "mat_permeability"
    DIFFERENTIAL_HEAD = "differential_head"
    # everything else
    CONTEXT = "context"
    NONE = "none"


#: Model targets an aqueous record can constrain.  A concentration is not a
#: concentration: the driving condition beneath the mat, the layer's own
#: porewater and the water above it are three different states.
_AQUEOUS_TARGET: Mapping[Matrix, str] = {
    Matrix.POREWATER: "sediment_face_porewater",
    Matrix.MAT_POREWATER: "mat_layer_porewater",
    Matrix.BOTTOM_WATER: "bottom_water",
    Matrix.SEAWATER: "bottom_water",
}

#: Fraction pairs that are never merged, in either direction, whatever operator
#: is switched on.  A DGT-labile pool and a voltammetric labile pool are
#: different operational definitions measured by different physics; a ratio
#: between them would be an invention.
NEVER_MERGED_FRACTIONS: frozenset[frozenset[Fraction]] = frozenset(
    {
        frozenset({Fraction.LABILE, Fraction.DGT_LABILE}),
        frozenset({Fraction.METHYLMERCURY, Fraction.DISSOLVED_INORGANIC}),
        frozenset({Fraction.METHYLMERCURY, Fraction.LABILE}),
        frozenset({Fraction.ACID_VOLATILE_SULFIDE, Fraction.SIMULTANEOUSLY_EXTRACTED_METAL}),
    }
)

#: Fractions that are never merged with **any** other pool, in any matrix.  A
#: DGT-labile mass, a methylmercury concentration and the AVS/SEM pair each mean
#: something a ratio cannot carry into another operational definition.
UNMERGEABLE_FRACTIONS: frozenset[Fraction] = frozenset(
    {
        Fraction.DGT_LABILE,
        Fraction.METHYLMERCURY,
        Fraction.ACID_VOLATILE_SULFIDE,
        Fraction.SIMULTANEOUSLY_EXTRACTED_METAL,
    }
)


def never_merged(measured: Fraction, model: Fraction) -> bool:
    """Whether these two fractions may never be related by any ratio."""
    if measured is model:
        return False
    if measured in UNMERGEABLE_FRACTIONS or model in UNMERGEABLE_FRACTIONS:
        return True
    return frozenset({measured, model}) in NEVER_MERGED_FRACTIONS


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

    #: The chemical fraction the **water-column** model state represents, per
    #: element.  A near-bed voltammetric probe reports a labile pool.
    model_fraction: Mapping[str, Fraction] = field(
        default_factory=lambda: {"Pb": Fraction.LABILE, "Hg": Fraction.LABILE}
    )
    #: The fraction the **porewater** state represents.  ``C_sed`` in MODEL_SPEC
    #: section 3 is a total dissolved porewater concentration, which a filtered
    #: laboratory result reports and a voltammetric labile pool does not.  One
    #: fraction for every matrix would be a fiction.
    porewater_fraction: Mapping[str, Fraction] = field(
        default_factory=lambda: {
            "Pb": Fraction.DISSOLVED_FILTERED,
            "Hg": Fraction.DISSOLVED_INORGANIC,
        }
    )
    #: The fraction a benthic-chamber flux is reported as.  A chamber measures
    #: the total dissolved release into the enclosed water, which is not the
    #: same operational pool as a voltammetric labile concentration.
    flux_fraction: Mapping[str, Fraction] = field(
        default_factory=lambda: {
            "Pb": Fraction.TOTAL_RECOVERABLE,
            "Hg": Fraction.DISSOLVED_INORGANIC,
        }
    )
    #: Matrices accepted as an assimilable aqueous pool.  ``POREWATER`` and
    #: ``MAT_POREWATER`` are primary channels, not background evidence.
    aqueous_matrices: frozenset[Matrix] = frozenset(
        {Matrix.SEAWATER, Matrix.BOTTOM_WATER, Matrix.POREWATER, Matrix.MAT_POREWATER}
    )
    #: Matrices explicitly rejected as an aqueous concentration input.
    rejected_aqueous_matrices: frozenset[Matrix] = frozenset(
        {Matrix.SEDIMENT, Matrix.SORBENT, Matrix.MAT_STRUCTURE, Matrix.INSTRUMENT}
    )
    #: The ratio operator for total-recoverable records.  Default: OFF.
    total_recoverable_operator: FractionRatioOperator = FractionRatioOperator()
    #: The media id installed in the tile right now.  A sorbent assay of any
    #: other media id is evidence about retrieved material.
    active_media_id: str | None = None
    #: Per-tile override, for a mat whose tiles were serviced at different times.
    active_media_id_by_tile: Mapping[str, str] = field(default_factory=dict)
    #: Records observed before this moment cannot describe the active media.
    active_media_installed_at_utc: datetime | None = None
    #: Quality flags excluded from the likelihood but kept as evidence.
    sensor_health_flags: frozenset[QualityFlag] = frozenset(
        {QualityFlag.SUSPECT, QualityFlag.FAILED}
    )
    #: Require a ``tile_id`` on a condition record before assimilating it.
    #: Failure is local (MODEL_SPEC rule 7): a condition record that names no
    #: tile cannot support a partial replacement.
    require_tile_on_condition: bool = True

    def active_media_for(self, tile_id: str | None) -> str | None:
        if tile_id is not None and tile_id in self.active_media_id_by_tile:
            return self.active_media_id_by_tile[tile_id]
        return self.active_media_id

    def expected_fraction(self, element: str, matrix: Matrix) -> Fraction:
        """Which pool the model state represents for this element and matrix."""
        if matrix in (Matrix.POREWATER, Matrix.MAT_POREWATER):
            return self.porewater_fraction.get(
                element, self.model_fraction.get(element, Fraction.LABILE)
            )
        return self.model_fraction.get(element, Fraction.LABILE)


@dataclass(frozen=True, slots=True)
class ObservationUse:
    """What the operator decided about one record, and why."""

    record_id: str
    station_id: str
    decision: AssimilationDecision
    model_quantity: ModelQuantity
    reason: str
    element: str | None = None
    tile_id: str | None = None
    media_id: str | None = None
    observed_at_utc: datetime | None = None
    #: Value in the SI unit of ``model_quantity``, when there is a point value.
    value_si: float | None = None
    lower_si: float | None = None
    upper_si: float | None = None
    sigma_si: float | None = None
    si_unit: str | None = None
    is_censored: bool = False
    #: A one-sided bound: an above-range result has a lower bound and no upper.
    is_one_sided: bool = False
    counts_for_data_age: bool = False
    sensor_health_evidence: bool = False
    #: True for a mat-condition record: physical state, never chemistry.
    condition_evidence: bool = False
    #: Which degradation mode this record constrains, when it constrains one.
    degradation_mode: DegradationMode | None = None
    #: Which model state an aqueous record constrains.
    model_target: str | None = None
    #: False for every record that carries no chemical information.
    carries_chemistry: bool = False
    condition_class: str | None = None
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

    @property
    def chemistry(self) -> tuple[ObservationUse, ...]:
        """Every use that carries chemical information about Pb or Hg."""
        return tuple(u for u in self.uses if u.carries_chemistry)

    @property
    def condition(self) -> tuple[ObservationUse, ...]:
        return tuple(u for u in self.uses if u.condition_evidence)

    def for_mode(self, mode: DegradationMode) -> tuple[ObservationUse, ...]:
        return tuple(u for u in self.uses if u.degradation_mode is mode)

    def for_tile(self, tile_id: str) -> tuple[ObservationUse, ...]:
        return tuple(u for u in self.uses if u.tile_id == tile_id)

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
# unit conversion per declared quantity kind
# ---------------------------------------------------------------------------

#: SI unit of each model quantity, for the record.
_SI_UNIT: Mapping[QuantityKind, str] = {
    QuantityKind.AQUEOUS_CONCENTRATION: "kg/m3",
    QuantityKind.SOLID_LOADING: "kg/kg",
    QuantityKind.ACCUMULATED_MASS: "kg",
    QuantityKind.AREAL_FLUX: "kg/m2/s",
    QuantityKind.LENGTH: "m",
    QuantityKind.VELOCITY: "m/s",
    QuantityKind.FRACTION: "1",
    QuantityKind.CATEGORICAL: "class",
    QuantityKind.CONTEXT: "context",
}


def _to_si(value: float, unit: str, kind: QuantityKind) -> float:
    """Convert on the ladder the declared quantity kind names, and no other."""
    if kind is QuantityKind.AQUEOUS_CONCENTRATION:
        return to_si_aqueous_concentration(value, unit)
    if kind is QuantityKind.SOLID_LOADING:
        return to_si_solid_loading(value, unit)
    if kind is QuantityKind.ACCUMULATED_MASS:
        return to_si_mass(value, unit)
    if kind is QuantityKind.AREAL_FLUX:
        return to_si_areal_flux(value, unit)
    if kind is QuantityKind.LENGTH:
        return to_si_length(value, unit)
    if kind is QuantityKind.VELOCITY:
        return to_si_velocity(value, unit)
    if kind is QuantityKind.FRACTION:
        if unit != "1":
            raise UnitError(f"a fraction must be dimensionless, not {unit!r}")
        return float(value)
    raise UnitError(
        f"quantity kind {kind.value!r} has no SI ladder; it is not converted"
    )


def _converted(record: ObservationRecord) -> tuple[float | None, float | None, float | None, str | None]:
    """``(value, lower, upper, error)`` in SI for the declared quantity kind."""
    kind = record.quantity_kind
    try:
        value = (
            None if record.value is None else _to_si(float(record.value), record.unit, kind)
        )
        lower = (
            None
            if record.lower_bound is None
            else _to_si(float(record.lower_bound), record.unit, kind)
        )
        upper = (
            None
            if record.upper_bound is None
            else _to_si(float(record.upper_bound), record.unit, kind)
        )
    except (UnitError, TypeError, ValueError) as exc:
        return None, None, None, str(exc)
    return value, lower, upper, None


def _sigma_si(record: ObservationRecord) -> float | None:
    """Reported uncertainty in SI, or None when the record does not know it.

    Unknown uncertainty stays unknown here.  The estimator substitutes a stated
    assumption and records that it did so; the operator never invents one.
    """
    if record.uncertainty_std is None:
        return None
    try:
        return abs(_to_si(float(record.uncertainty_std), record.unit, record.quantity_kind))
    except (UnitError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def classify_record(
    record: ObservationRecord,
    config: OperatorConfig | None = None,
    *,
    qc_report: QCReport | None = None,
) -> ObservationUse:
    """Decide how one record may be used.  Never mutates the record."""
    resolved = config or OperatorConfig()
    flag = record.quality_flag if qc_report is None else qc_report.flag_for(record)
    base: dict[str, Any] = dict(
        record_id=record.record_id,
        station_id=record.station_id,
        element=record.parameter.value if record.is_metal else None,
        tile_id=record.tile_id,
        media_id=record.media_id,
        observed_at_utc=record.observed_at_utc,
        condition_class=record.condition_class,
        quality_flag=flag,
    )

    # 1. missing: no information of any kind, and not a non-detect.
    if record.qualifier is Qualifier.MISSING:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.NONE,
            reason=(
                "missing result: it contributes nothing to the likelihood and does "
                "not refresh the data age; missing is not a non-detect"
            ),
            counts_for_data_age=False,
            sensor_health_evidence=True,
            **base,
        )

    # 2. mat condition, including the differential head.  No chemistry at all.
    if record.is_mat_condition or record.parameter is Parameter.DIFFERENTIAL_HEAD:
        return _classify_condition(record, resolved, flag, base)

    # 3. context and housekeeping: never a metal concentration.
    if record.parameter in CONTEXT_PARAMETERS or record.parameter not in METAL_PARAMETERS:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.CONTEXT,
            reason=(
                f"{record.parameter.value} is a context or housekeeping channel: it "
                "constrains conditions, transport forcing or instrument health, never "
                "a Pb or Hg concentration"
            ),
            counts_for_data_age=False,
            sensor_health_evidence=flag in resolved.sensor_health_flags,
            **base,
        )

    # 4. from here the record is Pb or Hg.  Dispatch on the DECLARED kind.
    kind = record.quantity_kind
    if kind is QuantityKind.SOLID_LOADING:
        return _classify_solid_loading(record, resolved, flag, base)
    if kind is QuantityKind.ACCUMULATED_MASS:
        return _classify_accumulated_mass(record, resolved, flag, base)
    if kind is QuantityKind.AREAL_FLUX:
        return _classify_areal_flux(record, resolved, flag, base)
    if kind is QuantityKind.AQUEOUS_CONCENTRATION:
        return _classify_aqueous(record, resolved, flag, base)
    return ObservationUse(
        decision=AssimilationDecision.REJECT,
        model_quantity=ModelQuantity.NONE,
        reason=(
            f"quantity kind {kind.value!r} is not a chemical observable for "
            f"{record.parameter.value}; nothing is inferred from the matrix or unit"
        ),
        **base,
    )


# --- mat condition ---------------------------------------------------------

_CONDITION_QUANTITY: Mapping[str, ModelQuantity] = {
    Parameter.MAT_COVERAGE_FRACTION.value: ModelQuantity.MAT_COVERAGE_FRACTION,
    Parameter.BURIAL_DEPTH.value: ModelQuantity.BURIAL_DEPTH,
    Parameter.SCOUR_DEPTH.value: ModelQuantity.SCOUR_DEPTH,
    Parameter.MAT_DISPLACEMENT.value: ModelQuantity.MAT_DISPLACEMENT,
    Parameter.MAT_UPLIFT.value: ModelQuantity.MAT_DISPLACEMENT,
    Parameter.MAT_TILT.value: ModelQuantity.MAT_TILT,
    Parameter.MAT_DAMAGE_CLASS.value: ModelQuantity.MAT_DAMAGE_CLASS,
    Parameter.MAT_PERMEABILITY.value: ModelQuantity.MAT_PERMEABILITY,
    Parameter.DIFFERENTIAL_HEAD.value: ModelQuantity.DIFFERENTIAL_HEAD,
}


def _classify_condition(
    record: ObservationRecord,
    config: OperatorConfig,
    flag: QualityFlag,
    base: Mapping[str, Any],
) -> ObservationUse:
    """Physical condition of the mat.  Constrains a degradation mode, not a metal."""
    parameter = record.parameter.value
    quantity = _CONDITION_QUANTITY.get(parameter, ModelQuantity.NONE)
    mode = CONDITION_MODE.get(parameter)
    diagnostics: dict[str, Any] = {
        "degradation_mode": None if mode is None else mode.value,
        "carries_chemistry": False,
    }
    if parameter == Parameter.BURIAL_DEPTH.value:
        diagnostics["burial_masquerades_as_success"] = True
        diagnostics["interpretation"] = (
            "burial adds diffusive path and REDUCES the apparent flux; it is "
            "evidence about physical position, never evidence of performance"
        )

    common = dict(
        model_quantity=quantity,
        condition_evidence=True,
        degradation_mode=mode,
        carries_chemistry=False,
        **base,
    )

    if config.require_tile_on_condition and record.tile_id is None:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            reason=(
                "mat-condition record without a tile_id: failure is local, so a "
                "condition observation that names no tile cannot support a per-tile "
                "state or a partial replacement; kept as mat-level evidence"
            ),
            counts_for_data_age=True,
            diagnostics=dict(diagnostics, tile_missing=True),
            **common,
        )

    if flag in config.sensor_health_flags:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            reason=(
                f"quality flag {int(flag)}: excluded from the likelihood and kept as "
                "condition and health evidence"
            ),
            counts_for_data_age=False,
            sensor_health_evidence=True,
            diagnostics=diagnostics,
            **common,
        )

    if record.qualifier is Qualifier.CATEGORICAL:
        try:
            band = integrity_band_for_class(record.condition_class or "")
        except KeyError as exc:
            return ObservationUse(
                decision=AssimilationDecision.REJECT,
                reason=f"unknown condition class: {exc}",
                diagnostics=diagnostics,
                **common,
            )
        return ObservationUse(
            decision=AssimilationDecision.ASSIMILATE,
            reason=(
                f"inspection class {record.condition_class!r} on tile "
                f"{record.tile_id!r}: a class, not a number. It constrains "
                f"{mode.value if mode else 'a degradation mode'} as the integrity "
                f"interval {band} (ASSUMPTION), never as a point value"
            ),
            lower_si=band[0],
            upper_si=band[1],
            is_censored=True,
            si_unit="1",
            counts_for_data_age=True,
            diagnostics=dict(diagnostics, integrity_band=band),
            **common,
        )

    if record.quantity_kind is QuantityKind.CONTEXT:
        # Differential head, tilt and permeability keep their reported unit:
        # units.py has no pressure, angle or permeability ladder, and inventing
        # one here would break the single-source rule.  The unit is reported
        # beside the number so nothing downstream has to guess it.
        value_si = None if record.value is None else float(record.value)
        lower_si = None if record.lower_bound is None else float(record.lower_bound)
        upper_si = None if record.upper_bound is None else float(record.upper_bound)
        sigma_si = (
            None if record.uncertainty_std is None else abs(float(record.uncertainty_std))
        )
        si_unit = record.unit
    else:
        value_si, lower_si, upper_si, error = _converted(record)
        if error is not None:
            return ObservationUse(
                decision=AssimilationDecision.REJECT,
                reason=(
                    f"unit {record.unit!r} cannot be read as "
                    f"{record.quantity_kind.value}: {error}"
                ),
                diagnostics=diagnostics,
                **common,
            )
        sigma_si = _sigma_si(record)
        si_unit = _SI_UNIT[record.quantity_kind]

    if value_si is None and lower_si is None and upper_si is None:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            reason="condition record without a usable value or bound",
            diagnostics=diagnostics,
            **common,
        )
    return ObservationUse(
        decision=AssimilationDecision.ASSIMILATE,
        reason=(
            f"{parameter} on tile {record.tile_id!r} constrains "
            f"{mode.value if mode else 'a degradation mode'}; it carries no chemistry "
            "and is never read as an attenuation"
        ),
        value_si=value_si,
        lower_si=lower_si,
        upper_si=upper_si,
        sigma_si=sigma_si,
        si_unit=si_unit,
        is_censored=record.is_censored or record.qualifier is Qualifier.ABOVE_RANGE,
        is_one_sided=record.qualifier is Qualifier.ABOVE_RANGE,
        counts_for_data_age=True,
        diagnostics=diagnostics,
        **common,
    )


# --- solid loading ---------------------------------------------------------

def _classify_solid_loading(
    record: ObservationRecord,
    config: OperatorConfig,
    flag: QualityFlag,
    base: Mapping[str, Any],
) -> ObservationUse:
    """A sorbent assay constrains the loading of the media it was taken from.

    A sediment core constrains the source reservoir and is never a mat loading.
    """
    if record.matrix is Matrix.SEDIMENT:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.SOLID_LOADING,
            reason=(
                "sediment solid loading characterises the source reservoir; it is not "
                "the mat's loading and is never read as a water concentration"
            ),
            counts_for_data_age=False,
            carries_chemistry=True,
            diagnostics={"source_characterisation": True},
            **base,
        )
    if record.matrix is not Matrix.SORBENT:
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            model_quantity=ModelQuantity.NONE,
            reason=(
                f"matrix {record.matrix.value!r} is not a sorbent: a solid loading "
                "must name the material it was measured on"
            ),
            **base,
        )
    if record.acquisition_kind is not AcquisitionKind.MEDIA_ASSAY:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.SOLID_LOADING,
            reason=(
                f"acquisition {record.acquisition_kind.value!r} is not a media assay; "
                "kept as evidence about the material"
            ),
            carries_chemistry=True,
            **base,
        )

    value_si, _, _, error = _converted(record)
    if error is not None:
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            model_quantity=ModelQuantity.NONE,
            reason=(
                f"unit {record.unit!r} is not a solid-loading unit; the aqueous ladder "
                f"is never used for a solid assay ({error})"
            ),
            **base,
        )
    if value_si is None:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.SOLID_LOADING,
            reason="sorbent assay without a value",
            carries_chemistry=True,
            **base,
        )

    active = config.active_media_for(record.tile_id)
    common = dict(
        model_quantity=ModelQuantity.SOLID_LOADING,
        value_si=value_si,
        si_unit=_SI_UNIT[QuantityKind.SOLID_LOADING],
        carries_chemistry=True,
        **base,
    )
    if active is None or record.media_id != active:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            reason=(
                f"assay of media {record.media_id!r}, which is not the media installed "
                f"now ({active!r}) in tile {record.tile_id!r}: it is evidence about the "
                "retrieved batch and must not be read as the loading of the tile now "
                "in place"
            ),
            counts_for_data_age=False,
            diagnostics={
                "retrieved_media": True,
                "assayed_media_id": record.media_id,
                "active_media_id": active,
            },
            **common,
        )
    installed_at = config.active_media_installed_at_utc
    if installed_at is not None and record.observed_at_utc < installed_at:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            reason=(
                "assay observed before the active media was installed; it cannot "
                "describe the media that is in the water now"
            ),
            counts_for_data_age=False,
            diagnostics={"retrieved_media": True},
            **common,
        )
    if flag in config.sensor_health_flags:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            reason=f"quality flag {int(flag)}: kept as evidence, out of the likelihood",
            counts_for_data_age=False,
            sensor_health_evidence=True,
            **common,
        )
    return ObservationUse(
        decision=AssimilationDecision.ASSIMILATE,
        reason=(
            f"assay of the media installed now ({active!r}): it constrains the loading "
            "in kg/kg on the mass-based ladder"
        ),
        sigma_si=_sigma_si(record),
        counts_for_data_age=True,
        **common,
    )


# --- accumulated mass (DGT and other integrating samplers) -----------------

def _classify_accumulated_mass(
    record: ObservationRecord,
    config: OperatorConfig,
    flag: QualityFlag,
    base: Mapping[str, Any],
) -> ObservationUse:
    """An integrated exposure: a mass over a window, never a point ng/L."""
    value_si, lower_si, upper_si, error = _converted(record)
    note = "" if error is None else f" (unit not on the mass ladder: {error})"
    window = (
        None
        if record.sampling_start_utc is None or record.sampling_end_utc is None
        else (record.sampling_end_utc - record.sampling_start_utc).total_seconds()
    )
    return ObservationUse(
        decision=AssimilationDecision.EVIDENCE_ONLY,
        model_quantity=ModelQuantity.ACCUMULATED_MASS,
        reason=(
            f"integrated {record.fraction.value} exposure: an accumulated mass over a "
            "window, displayed and counted for data age. It is never converted into a "
            "point concentration without a calibrated, temperature and ionic-strength "
            "dependent sampler operator, which this build does not have" + note
        ),
        value_si=value_si,
        lower_si=lower_si,
        upper_si=upper_si,
        sigma_si=_sigma_si(record),
        si_unit=_SI_UNIT[QuantityKind.ACCUMULATED_MASS],
        is_censored=record.is_censored or record.qualifier is Qualifier.ABOVE_RANGE,
        is_one_sided=record.qualifier is Qualifier.ABOVE_RANGE,
        counts_for_data_age=True,
        sensor_health_evidence=flag in config.sensor_health_flags,
        carries_chemistry=True,
        model_target="integrated_exposure",
        diagnostics={
            "sampling_start_utc": record.sampling_start_utc,
            "sampling_end_utc": record.sampling_end_utc,
            "exposure_window_s": window,
            "reported_unit": record.unit,
            "measured_fraction": record.fraction.value,
            "never_a_point_concentration": True,
        },
        **base,
    )


# --- areal flux ------------------------------------------------------------

def _classify_areal_flux(
    record: ObservationRecord,
    config: OperatorConfig,
    flag: QualityFlag,
    base: Mapping[str, Any],
) -> ObservationUse:
    """A benthic-chamber flux constrains ``J_out``, the quantity the mat is judged on."""
    if record.acquisition_kind is not AcquisitionKind.BENTHIC_CHAMBER:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.AREAL_FLUX,
            reason=(
                f"an areal flux from acquisition {record.acquisition_kind.value!r} is "
                "not a chamber measurement; kept as evidence"
            ),
            carries_chemistry=True,
            **base,
        )
    if record.chamber_area_m2 is None or record.chamber_area_m2 <= 0.0:
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            model_quantity=ModelQuantity.NONE,
            reason=(
                "a benthic-chamber flux without a positive chamber_area_m2 is not "
                "interpretable: the enclosed area is what turns a mass change into a "
                "flux"
            ),
            **base,
        )
    if record.sampling_start_utc is None or record.sampling_end_utc is None:
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            model_quantity=ModelQuantity.NONE,
            reason=(
                "a benthic-chamber flux without a deployment window is not "
                "interpretable: the flux is a rate over that window, not a point value"
            ),
            **base,
        )

    expected = config.flux_fraction.get(record.parameter.value)
    if expected is not None and record.fraction is not expected:
        if never_merged(record.fraction, expected):
            return ObservationUse(
                decision=AssimilationDecision.EVIDENCE_ONLY,
                model_quantity=ModelQuantity.AREAL_FLUX,
                reason=(
                    f"chamber fraction {record.fraction.value!r} and flux state "
                    f"{expected.value!r} are different operational pools that are never "
                    "merged; retained as unassimilated evidence"
                ),
                counts_for_data_age=True,
                carries_chemistry=True,
                **base,
            )
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.AREAL_FLUX,
            reason=(
                f"chamber fraction {record.fraction.value!r} is not the modelled flux "
                f"fraction {expected.value!r}; retained as unassimilated evidence"
            ),
            counts_for_data_age=True,
            carries_chemistry=True,
            diagnostics={
                "measured_fraction": record.fraction.value,
                "model_fraction": expected.value,
            },
            **base,
        )

    value_si, lower_si, upper_si, error = _converted(record)
    if error is not None:
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            model_quantity=ModelQuantity.NONE,
            reason=f"unit {record.unit!r} cannot be read as an areal flux: {error}",
            **base,
        )
    common = dict(
        model_quantity=ModelQuantity.AREAL_FLUX,
        si_unit=_SI_UNIT[QuantityKind.AREAL_FLUX],
        model_target="residual_flux_out",
        carries_chemistry=True,
        diagnostics={
            "chamber_area_m2": record.chamber_area_m2,
            "sampling_start_utc": record.sampling_start_utc,
            "sampling_end_utc": record.sampling_end_utc,
            "apparent_flux_only": (
                "a chamber measures the apparent flux; burial also reduces it, so the "
                "attribution needs the condition channels"
            ),
        },
        **base,
    )
    if flag in config.sensor_health_flags:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            reason=(
                f"quality flag {int(flag)}: excluded from the likelihood and kept as "
                "health evidence"
            ),
            value_si=value_si,
            lower_si=lower_si,
            upper_si=upper_si,
            counts_for_data_age=False,
            sensor_health_evidence=True,
            **common,
        )
    if record.qualifier is Qualifier.QUANTIFIED:
        return ObservationUse(
            decision=AssimilationDecision.ASSIMILATE,
            reason=(
                f"quantified {record.parameter.value} areal flux over a chamber "
                "deployment: the residual flux the mat is judged on"
            ),
            value_si=value_si,
            sigma_si=_sigma_si(record),
            counts_for_data_age=True,
            **common,
        )
    return _bounded_use(record, common, lower_si, upper_si)


# --- aqueous concentration -------------------------------------------------

def _classify_aqueous(
    record: ObservationRecord,
    config: OperatorConfig,
    flag: QualityFlag,
    base: Mapping[str, Any],
) -> ObservationUse:
    """Porewater, mat porewater, bottom water and seawater."""
    if record.matrix in config.rejected_aqueous_matrices:
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            model_quantity=ModelQuantity.NONE,
            reason=(
                f"matrix {record.matrix.value!r} is rejected as an aqueous "
                "concentration input; a solid assay uses the mass-based ladder and a "
                "separate interpretation"
            ),
            **base,
        )
    if record.matrix not in config.aqueous_matrices:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            model_quantity=ModelQuantity.NONE,
            reason=(
                f"matrix {record.matrix.value!r} is not a modelled aqueous pool; kept "
                "as evidence, not assimilated"
            ),
            counts_for_data_age=False,
            carries_chemistry=True,
            **base,
        )
    if record.acquisition_kind is AcquisitionKind.PASSIVE_SAMPLER:
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            model_quantity=ModelQuantity.NONE,
            reason=(
                "a passive sampler reports an accumulated mass over a window; a record "
                "declaring it as a point aqueous concentration has already been "
                "converted without a justified sampler operator and is refused"
            ),
            carries_chemistry=True,
            **base,
        )

    target = _AQUEOUS_TARGET[record.matrix]
    common: dict[str, Any] = dict(
        model_quantity=ModelQuantity.AQUEOUS_CONCENTRATION,
        si_unit=_SI_UNIT[QuantityKind.AQUEOUS_CONCENTRATION],
        model_target=target,
        carries_chemistry=True,
        **base,
    )

    if flag in config.sensor_health_flags:
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            reason=(
                f"quality flag {int(flag)}: excluded from the likelihood and kept as "
                "health evidence"
            ),
            counts_for_data_age=False,
            sensor_health_evidence=True,
            **common,
        )

    expected = config.expected_fraction(record.parameter.value, record.matrix)
    if record.fraction is not expected:
        if never_merged(record.fraction, expected):
            return ObservationUse(
                decision=AssimilationDecision.EVIDENCE_ONLY,
                reason=(
                    f"{record.fraction.value!r} and the model state {expected.value!r} "
                    "are different operationally defined pools that are never merged, "
                    "with or without a ratio operator: no ratio between them exists to "
                    "be assumed"
                ),
                counts_for_data_age=True,
                diagnostics={
                    "measured_fraction": record.fraction.value,
                    "model_fraction": expected.value,
                    "never_merged": True,
                },
                **common,
            )
        operator = config.total_recoverable_operator
        if record.fraction is Fraction.TOTAL_RECOVERABLE and operator.enabled:
            return _ratio_operator_use(record, operator, common)
        return ObservationUse(
            decision=AssimilationDecision.EVIDENCE_ONLY,
            reason=(
                f"chemical fraction {record.fraction.value!r} is not the model state "
                f"{expected.value!r}; it is retained as unassimilated evidence. Merging "
                "the two would need an explicit, documented, uncertain ratio operator, "
                "which is switched off"
            ),
            counts_for_data_age=True,
            diagnostics={
                "measured_fraction": record.fraction.value,
                "model_fraction": expected.value,
            },
            **common,
        )

    value_si, lower_si, upper_si, error = _converted(record)
    if error is not None:
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            model_quantity=ModelQuantity.NONE,
            reason=f"unit {record.unit!r} cannot be read as an aqueous concentration: {error}",
            **base,
        )
    if record.qualifier is Qualifier.QUANTIFIED:
        return ObservationUse(
            decision=AssimilationDecision.ASSIMILATE,
            reason=(
                f"quantified {record.fraction.value} {record.parameter.value} in "
                f"{record.matrix.value}: constrains {target}"
            ),
            value_si=value_si,
            sigma_si=_sigma_si(record),
            counts_for_data_age=True,
            **common,
        )
    return _bounded_use(record, common, lower_si, upper_si)


def _bounded_use(
    record: ObservationRecord,
    common: Mapping[str, Any],
    lower_si: float | None,
    upper_si: float | None,
) -> ObservationUse:
    """A censored or above-range record used as the bound it is."""
    if record.qualifier is Qualifier.ABOVE_RANGE:
        if lower_si is None:
            return ObservationUse(
                decision=AssimilationDecision.REJECT,
                reason="above-range record without a lower bound",
                **{**common, "model_quantity": ModelQuantity.NONE},
            )
        return ObservationUse(
            decision=AssimilationDecision.ASSIMILATE,
            reason=(
                "above range: used as the one-sided lower bound it is, never as the "
                "range top and never as a number"
            ),
            lower_si=lower_si,
            upper_si=None,
            is_censored=True,
            is_one_sided=True,
            sigma_si=_sigma_si(record),
            counts_for_data_age=True,
            **common,
        )
    if lower_si is None or upper_si is None:
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            reason="censored record without a finite interval; a non-detect is a bound",
            **{**common, "model_quantity": ModelQuantity.NONE},
        )
    return ObservationUse(
        decision=AssimilationDecision.ASSIMILATE,
        reason=(
            f"{record.qualifier.value}: used as the bound it is, never as a zero and "
            "never dropped"
        ),
        lower_si=lower_si,
        upper_si=upper_si,
        is_censored=True,
        sigma_si=_sigma_si(record),
        counts_for_data_age=True,
        **common,
    )


def _ratio_operator_use(
    record: ObservationRecord,
    operator: FractionRatioOperator,
    common: Mapping[str, Any],
) -> ObservationUse:
    """Assimilate a total-recoverable record as a WIDER interval, never a number."""
    value_si, lower_si, upper_si, error = _converted(record)
    if error is not None:
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            reason=f"total-recoverable record with an unusable unit: {error}",
            **{**common, "model_quantity": ModelQuantity.NONE},
        )
    if value_si is not None:
        low, high = value_si, value_si
    elif lower_si is not None and upper_si is not None:
        low, high = lower_si, upper_si
    else:
        return ObservationUse(
            decision=AssimilationDecision.REJECT,
            reason="total-recoverable record without a usable value or interval",
            **{**common, "model_quantity": ModelQuantity.NONE},
        )
    widened_low, _ = operator.interval_si(low)
    _, widened_high = operator.interval_si(high)
    return ObservationUse(
        decision=AssimilationDecision.ASSIMILATE,
        reason=(
            "total recoverable assimilated through the explicit ratio operator "
            f"(ASSUMPTION ratio interval {operator.ratio_interval}); the record enters "
            "as an interval, not as a point value, so using it WIDENS the estimate"
        ),
        lower_si=widened_low,
        upper_si=widened_high,
        is_censored=True,
        counts_for_data_age=True,
        diagnostics={
            "ratio_operator": True,
            "ratio_interval": operator.ratio_interval,
            "source_ref": operator.source_ref,
        },
        **common,
    )


def build_assimilation_set(
    records: Sequence[ObservationRecord],
    config: OperatorConfig | None = None,
    *,
    qc_report: QCReport | None = None,
) -> AssimilationSet:
    """Classify a whole batch, preserving order and every original identifier."""
    resolved = config or OperatorConfig()
    uses = tuple(
        classify_record(record, resolved, qc_report=qc_report) for record in records
    )
    return AssimilationSet(uses=uses, config=resolved)
