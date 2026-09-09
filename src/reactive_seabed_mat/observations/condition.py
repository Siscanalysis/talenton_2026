"""Mat-condition observations: the channels that carry no chemistry.

The inherited observation stack had no concept of these at all.  Without them
every performance loss collapses into "the medium is saturated", which is
exactly the failure ``docs/MODEL_SPEC.md`` section 4 exists to prevent.  These
channels constrain **degradation modes 3 and 4** (displacement and local damage)
and, through the differential head, mode 2 (fouling):

===========================  =====================================  ============
Channel                      Instrument                             Mode
===========================  =====================================  ============
``mat_damage_class``         ROV or diver inspection, a class       4
``mat_coverage_fraction``    bathymetric survey                     3 and 4
``burial_depth``             bathymetric survey                     3
``scour_depth``              bathymetric survey                     3
``mat_displacement``         acoustic position (USBL)               3
``mat_tilt``                 inclinometer on the tile               3
``differential_head``        differential-pressure sensor           2
===========================  =====================================  ============

Two rules are structural, not stylistic:

* **Every record that describes a tile carries its ``tile_id``.**  Failure is
  local, and a condition record without a tile cannot support a partial
  replacement.
* **Burial reduces the apparent flux.**  A burial record is evidence about
  physical position, never evidence of success, and the operator classifies it
  as such.

A damage class is a **class**, not a number: ``qualifier=categorical`` and
``quantity_kind=categorical``, with the class itself in ``condition_class``.
:data:`DAMAGE_CLASS_INTEGRITY_BAND` states what interval of the integrity index
each class is taken to imply, so an estimator can use it as the interval it is
rather than as a false point value.

Every number in this module is an ASSUMPTION for a demonstration.  No inspection
standard, survey accuracy or vendor specification is claimed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping

from ..config import ObservationConfig, StationConfig
from ..contracts import (
    AcquisitionKind,
    DataOrigin,
    DegradationMode,
    Fraction,
    Matrix,
    ObservationRecord,
    Parameter,
    ProvenanceLabel,
    Qualifier,
    QualityFlag,
    QuantityKind,
    VerticalDatum,
)
from ..units import format_utc, from_si_length
from .generator import MatStateSample, ScriptedScene, SyntheticRecordFactory

__all__ = [
    "MAT_DAMAGE_CLASSES",
    "DAMAGE_CLASS_SEVERITY",
    "DAMAGE_CLASS_INTEGRITY_BAND",
    "CONDITION_METHOD_IDS",
    "CONDITION_MODE",
    "ConditionAssumptions",
    "MatConditionGenerator",
    "damage_class_from_integrity",
    "integrity_band_for_class",
]


#: Controlled vocabulary for ``mat_damage_class``, worst last.
MAT_DAMAGE_CLASSES: tuple[str, ...] = (
    "intact",
    "abraded",
    "punctured",
    "torn",
    "lost",
)

#: Ordinal severity, so two inspections can be compared without pretending the
#: classes are a measured quantity.
DAMAGE_CLASS_SEVERITY: Mapping[str, int] = {
    name: index for index, name in enumerate(MAT_DAMAGE_CLASSES)
}

#: What integrity index each class is taken to imply.  ASSUMPTION, and an
#: interval on purpose: an inspector reports a class, not a number.
DAMAGE_CLASS_INTEGRITY_BAND: Mapping[str, tuple[float, float]] = {
    "intact": (0.98, 1.00),
    "abraded": (0.85, 0.99),
    "punctured": (0.50, 0.90),
    "torn": (0.10, 0.60),
    "lost": (0.00, 0.10),
}

#: Which degradation mode each condition parameter constrains.  Mode 3 and mode
#: 4 stay apart: burial is not damage, and damage is not saturation.
CONDITION_MODE: Mapping[str, DegradationMode] = {
    Parameter.MAT_DAMAGE_CLASS.value: DegradationMode.LOCAL_DAMAGE,
    Parameter.MAT_COVERAGE_FRACTION.value: DegradationMode.DISPLACEMENT,
    Parameter.BURIAL_DEPTH.value: DegradationMode.DISPLACEMENT,
    Parameter.SCOUR_DEPTH.value: DegradationMode.DISPLACEMENT,
    Parameter.MAT_DISPLACEMENT.value: DegradationMode.DISPLACEMENT,
    Parameter.MAT_UPLIFT.value: DegradationMode.DISPLACEMENT,
    Parameter.MAT_TILT.value: DegradationMode.DISPLACEMENT,
    Parameter.MAT_PERMEABILITY.value: DegradationMode.FOULING,
    Parameter.DIFFERENTIAL_HEAD.value: DegradationMode.FOULING,
}

CONDITION_METHOD_IDS: Mapping[str, str] = {
    "damage_class": "SIM_ROV_DAMAGE_CLASS_V1",
    "diver_damage_class": "SIM_DIVER_DAMAGE_CLASS_V1",
    "coverage": "SIM_MULTIBEAM_COVERAGE_V1",
    "burial": "SIM_MULTIBEAM_BURIAL_V1",
    "scour": "SIM_MULTIBEAM_SCOUR_V1",
    "displacement": "SIM_USBL_POSITION_V1",
    "tilt": "SIM_TILT_V1",
    "differential_head": "SIM_DIFFERENTIAL_PRESSURE_V1",
}


def damage_class_from_integrity(integrity: float, displaced: bool = False) -> str:
    """The class an inspector would record for a given integrity.  ASSUMPTION."""
    if displaced:
        return "lost"
    for name in reversed(MAT_DAMAGE_CLASSES):
        low, high = DAMAGE_CLASS_INTEGRITY_BAND[name]
        if low <= integrity <= high:
            return name
    return "intact"


def integrity_band_for_class(condition_class: str) -> tuple[float, float]:
    """The integrity interval a class implies.  Raises on an unknown class."""
    try:
        return DAMAGE_CLASS_INTEGRITY_BAND[condition_class]
    except KeyError:
        raise KeyError(
            f"{condition_class!r} is not in the controlled damage vocabulary "
            f"{MAT_DAMAGE_CLASSES}; an unknown class is not silently mapped"
        ) from None


@dataclass(frozen=True, slots=True)
class ConditionAssumptions:
    """Survey and inspection assumptions.  Not verified survey accuracies."""

    #: Which inspection pathway the demonstration uses for the damage class.
    inspection_kind: AcquisitionKind = AcquisitionKind.ROV_INSPECTION
    #: Probability an inspector records the neighbouring class instead of the
    #: true one.  A class is a judgement, not a measurement.  ASSUMPTION.
    misclassification_probability: float = 0.10
    #: Probability a survey leg is aborted (weather, vessel).  ASSUMPTION.
    survey_abort_probability: float = 0.04
    coverage_absolute_noise: float = 0.03
    burial_absolute_noise_m: float = 0.010
    scour_absolute_noise_m: float = 0.010
    displacement_absolute_noise_m: float = 0.25
    tilt_absolute_noise_deg: float = 0.8
    differential_head_relative_noise: float = 0.08
    #: The differential-pressure sensor is a continuous instrument, not a
    #: campaign.  The default reports one daily aggregate per tile: pore
    #: blockage evolves over months, so a six-hourly record would multiply the
    #: stream without adding information.  ``None`` falls back to the
    #: bottom-water probe rhythm.
    differential_head_period_s: float | None = 86400.0
    #: Report burial and scour in centimetres, which is how a survey reports
    #: them.  The length ladder converts explicitly; nothing is inferred.
    burial_report_unit: str = "cm"
    scour_report_unit: str = "cm"
    displacement_report_unit: str = "m"
    #: Emit the scour and tilt channels as well as the core four.
    emit_scour: bool = True
    emit_tilt: bool = True
    record_id_prefix: str = "C"
    provenance: ProvenanceLabel = ProvenanceLabel.SYNTHETIC_DEMO


class MatConditionGenerator(SyntheticRecordFactory):
    """Emit mat-condition records for every tile in a scripted scene.

    Deterministic for a given seed and scene, and disjoint from the chemistry
    generator's record ids through its own prefix.
    """

    def __init__(
        self,
        config: ObservationConfig,
        *,
        seed: int,
        start_utc: datetime,
        assumptions: ConditionAssumptions | None = None,
        fast_validation: bool = True,
    ) -> None:
        resolved = assumptions or ConditionAssumptions()
        super().__init__(
            config,
            seed=seed,
            start_utc=start_utc,
            record_id_prefix=resolved.record_id_prefix,
            provenance=resolved.provenance,
            fast_validation=fast_validation,
        )
        self.assumptions = resolved

    # -- helpers ------------------------------------------------------------

    def _survey_station(self) -> StationConfig:
        for station in self.config.stations:
            if station.kind == "survey":
                return station
        if self.config.stations:
            return self.config.stations[0]
        raise KeyError("no station configured for a mat survey")

    def _tile_payload(
        self,
        station: StationConfig,
        scene: ScriptedScene,
        tile_id: str,
        moment: datetime,
        latency_s: float,
    ) -> dict:
        position = scene.position_of(tile_id)
        payload = self.base_payload(
            station,
            tile_id=tile_id,
            x_m=None if position is None else position[0],
            y_m=None if position is None else position[1],
        )
        payload.update(
            {
                "record_id": self.next_id(),
                "observed_at_utc": format_utc(moment),
                "available_at_utc": format_utc(moment + timedelta(seconds=latency_s)),
                "matrix": Matrix.MAT_STRUCTURE.value,
                "fraction": Fraction.NOT_APPLICABLE.value,
                "data_origin": DataOrigin.FIELD_SURVEY.value,
                "depth_m": 0.0,
                "vertical_datum": VerticalDatum.MAT_TOP.value,
            }
        )
        return payload

    def _quantified(
        self, payload: dict, value: float, sigma: float, *, low: float | None = None
    ) -> dict:
        reported = float(value)
        if low is not None:
            reported = max(reported, low)
        payload.update(
            {
                "value": reported,
                "uncertainty_std": abs(float(sigma)),
                "qualifier": Qualifier.QUANTIFIED.value,
                "lower_bound": None,
                "upper_bound": None,
                "quality_flag": int(QualityFlag.PASSED),
            }
        )
        return payload

    def _aborted(self, payload: dict, what: str) -> dict:
        payload.update(
            self.missing(
                f"simulated aborted survey leg ({what}); missing is not a "
                "non-detect and carries no information about the mat"
            )
        )
        return payload

    # -- channels -----------------------------------------------------------

    def damage_class_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """ROV or diver inspection: a class from a controlled vocabulary.

        A class, never a number.  The record carries ``condition_class`` and
        nothing in ``value``, so no downstream code can average two inspections
        into a fictitious 2.5.
        """
        records: list[ObservationRecord] = []
        station = self._survey_station()
        latency = self.config.survey_latency_s
        kind = self.assumptions.inspection_kind
        method = (
            CONDITION_METHOD_IDS["diver_damage_class"]
            if kind is AcquisitionKind.DIVER_INSPECTION
            else CONDITION_METHOD_IDS["damage_class"]
        )
        for moment in self.schedule(self.config.survey_period_s, duration_s):
            for tile_id in scene.tile_ids:
                sample = scene.sample_at(tile_id, moment)
                self.reading_rng("damage_class", moment, tile_id)
                misread = float(self._rng.random())
                direction = float(self._rng.random())
                abort = float(self._rng.random())
                payload = self._tile_payload(station, scene, tile_id, moment, latency)
                payload.update(
                    {
                        "parameter": Parameter.MAT_DAMAGE_CLASS.value,
                        "quantity_kind": QuantityKind.CATEGORICAL.value,
                        "unit": "class",
                        "acquisition_kind": kind.value,
                        "method_id": method,
                    }
                )
                if abort < self.assumptions.survey_abort_probability:
                    records.append(self.build(self._aborted(payload, "inspection")))
                    continue
                true_class = self._true_class(sample)
                reported_class = true_class
                if misread < self.assumptions.misclassification_probability:
                    index = DAMAGE_CLASS_SEVERITY[true_class]
                    shift = 1 if direction >= 0.5 else -1
                    index = min(max(index + shift, 0), len(MAT_DAMAGE_CLASSES) - 1)
                    reported_class = MAT_DAMAGE_CLASSES[index]
                payload.update(
                    {
                        "value": None,
                        "uncertainty_std": None,
                        "qualifier": Qualifier.CATEGORICAL.value,
                        "condition_class": reported_class,
                        "quality_flag": int(QualityFlag.PASSED),
                        "source_ref": (
                            "visual inspection class from the controlled vocabulary "
                            f"{MAT_DAMAGE_CLASSES}; a class, not a number. It implies "
                            f"integrity in {DAMAGE_CLASS_INTEGRITY_BAND[reported_class]} "
                            "(ASSUMPTION). Constrains local damage, mode 4, and carries "
                            "no chemistry. ASSUMPTION misclassification_probability="
                            f"{self.assumptions.misclassification_probability}"
                        ),
                    }
                )
                records.append(self.build(payload))
        return records

    @staticmethod
    def _true_class(sample: MatStateSample) -> str:
        if sample.damage_class in DAMAGE_CLASS_SEVERITY:
            return sample.damage_class
        return damage_class_from_integrity(sample.integrity_index, sample.displaced)

    def coverage_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """Bathymetric survey: the share of a tile's footprint still covered."""
        records: list[ObservationRecord] = []
        station = self._survey_station()
        latency = self.config.survey_latency_s
        sigma = self.assumptions.coverage_absolute_noise
        for moment in self.schedule(self.config.survey_period_s, duration_s):
            for tile_id in scene.tile_ids:
                sample = scene.sample_at(tile_id, moment)
                self.reading_rng("coverage", moment, tile_id)
                noise = float(self._rng.normal(0.0, sigma))
                abort = float(self._rng.random())
                payload = self._tile_payload(station, scene, tile_id, moment, latency)
                payload.update(
                    {
                        "parameter": Parameter.MAT_COVERAGE_FRACTION.value,
                        "quantity_kind": QuantityKind.FRACTION.value,
                        "unit": "1",
                        "acquisition_kind": AcquisitionKind.BATHYMETRIC_SURVEY.value,
                        "method_id": CONDITION_METHOD_IDS["coverage"],
                        "source_ref": (
                            "share of the tile footprint still covered by intact mat; "
                            f"ASSUMPTION absolute noise {sigma}. Constrains "
                            "displacement and local damage, never chemistry"
                        ),
                    }
                )
                if abort < self.assumptions.survey_abort_probability:
                    records.append(self.build(self._aborted(payload, "coverage")))
                    continue
                value = min(max(sample.coverage_fraction + noise, 0.0), 1.0)
                records.append(self.build(self._quantified(payload, value, sigma)))
        return records

    def burial_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """Bathymetric survey: sediment accumulated on top of a tile.

        Burial adds diffusive path and therefore *reduces* the apparent flux.
        A burial record is evidence about physical position and must never be
        read as improved performance; the ``source_ref`` says so and the
        observation operator classifies it as condition evidence for mode 3.
        """
        records: list[ObservationRecord] = []
        station = self._survey_station()
        latency = self.config.survey_latency_s
        sigma_m = self.assumptions.burial_absolute_noise_m
        unit = self.assumptions.burial_report_unit
        for moment in self.schedule(self.config.survey_period_s, duration_s):
            for tile_id in scene.tile_ids:
                sample = scene.sample_at(tile_id, moment)
                self.reading_rng("burial", moment, tile_id)
                noise = float(self._rng.normal(0.0, sigma_m))
                abort = float(self._rng.random())
                payload = self._tile_payload(station, scene, tile_id, moment, latency)
                payload.update(
                    {
                        "parameter": Parameter.BURIAL_DEPTH.value,
                        "quantity_kind": QuantityKind.LENGTH.value,
                        "unit": unit,
                        "acquisition_kind": AcquisitionKind.BATHYMETRIC_SURVEY.value,
                        "method_id": CONDITION_METHOD_IDS["burial"],
                        "source_ref": (
                            f"sediment accumulated on top of the tile, reported in "
                            f"{unit} and converted through the length ladder. Burial "
                            "REDUCES the apparent flux and must never be read as "
                            "success; it constrains displacement, mode 3. ASSUMPTION "
                            f"absolute noise {sigma_m} m"
                        ),
                    }
                )
                if abort < self.assumptions.survey_abort_probability:
                    records.append(self.build(self._aborted(payload, "burial")))
                    continue
                value_m = max(sample.burial_depth_m + noise, 0.0)
                value = from_si_length(value_m, unit)
                sigma = from_si_length(sigma_m, unit)
                records.append(self.build(self._quantified(payload, value, sigma)))
        return records

    def scour_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """Bathymetric survey: scour at the tile edge.  Mode 3, not chemistry."""
        records: list[ObservationRecord] = []
        station = self._survey_station()
        latency = self.config.survey_latency_s
        sigma_m = self.assumptions.scour_absolute_noise_m
        unit = self.assumptions.scour_report_unit
        for moment in self.schedule(self.config.survey_period_s, duration_s):
            for tile_id in scene.tile_ids:
                sample = scene.sample_at(tile_id, moment)
                self.reading_rng("scour", moment, tile_id)
                noise = float(self._rng.normal(0.0, sigma_m))
                payload = self._tile_payload(station, scene, tile_id, moment, latency)
                payload.update(
                    {
                        "parameter": Parameter.SCOUR_DEPTH.value,
                        "quantity_kind": QuantityKind.LENGTH.value,
                        "unit": unit,
                        "acquisition_kind": AcquisitionKind.BATHYMETRIC_SURVEY.value,
                        "method_id": CONDITION_METHOD_IDS["scour"],
                        "source_ref": (
                            "scour measured at the tile edge; constrains erosion and "
                            f"displacement, mode 3. ASSUMPTION absolute noise {sigma_m} m"
                        ),
                    }
                )
                # A displaced tile leaves a scour pit behind it.  ASSUMPTION.
                true_m = 0.06 if sample.displaced else 0.01
                value_m = max(true_m + noise, 0.0)
                records.append(
                    self.build(
                        self._quantified(
                            payload,
                            from_si_length(value_m, unit),
                            from_si_length(sigma_m, unit),
                        )
                    )
                )
        return records

    def displacement_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """Acoustic position: horizontal offset from the as-laid position."""
        records: list[ObservationRecord] = []
        station = self._survey_station()
        latency = self.config.survey_latency_s
        sigma = self.assumptions.displacement_absolute_noise_m
        unit = self.assumptions.displacement_report_unit
        for moment in self.schedule(self.config.survey_period_s, duration_s):
            for tile_id in scene.tile_ids:
                sample = scene.sample_at(tile_id, moment)
                self.reading_rng("displacement", moment, tile_id)
                noise = float(self._rng.normal(0.0, sigma))
                payload = self._tile_payload(station, scene, tile_id, moment, latency)
                payload.update(
                    {
                        "sensor_id": f"SIM_USBL_{station.station_id}",
                        "parameter": Parameter.MAT_DISPLACEMENT.value,
                        "quantity_kind": QuantityKind.LENGTH.value,
                        "unit": unit,
                        "acquisition_kind": AcquisitionKind.ACOUSTIC_POSITION.value,
                        "method_id": CONDITION_METHOD_IDS["displacement"],
                        "vertical_datum": VerticalDatum.SEABED.value,
                        "source_ref": (
                            "horizontal offset from the as-laid position; constrains "
                            f"displacement, mode 3. ASSUMPTION absolute noise {sigma} m"
                        ),
                    }
                )
                value_m = max(sample.displacement_m + noise, 0.0)
                records.append(
                    self.build(
                        self._quantified(
                            payload, from_si_length(value_m, unit),
                            from_si_length(sigma, unit),
                        )
                    )
                )
        return records

    def tilt_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """Inclinometer on the tile.  Mode 3, and instrument-mounted."""
        records: list[ObservationRecord] = []
        station = self._survey_station()
        sigma = self.assumptions.tilt_absolute_noise_deg
        for moment in self.schedule(self.config.survey_period_s, duration_s):
            for tile_id in scene.tile_ids:
                sample = scene.sample_at(tile_id, moment)
                self.reading_rng("tilt", moment, tile_id)
                noise = float(self._rng.normal(0.0, sigma))
                payload = self._tile_payload(station, scene, tile_id, moment, 0.0)
                payload.update(
                    {
                        "sensor_id": f"SIM_TILT_{tile_id}",
                        "parameter": Parameter.MAT_TILT.value,
                        "quantity_kind": QuantityKind.CONTEXT.value,
                        "unit": "deg",
                        "acquisition_kind": AcquisitionKind.IN_SITU_SENSOR.value,
                        "method_id": CONDITION_METHOD_IDS["tilt"],
                        "data_origin": DataOrigin.SENSOR.value,
                        "calibration_id": "CAL_SIM_V1",
                        "source_ref": (
                            "tile inclination; constrains uplift and displacement, "
                            f"mode 3. ASSUMPTION absolute noise {sigma} deg"
                        ),
                    }
                )
                if sample.tilt_deg is None:
                    payload.update(self.missing("the supplied scene has no tilt model or measurement"))
                    records.append(self.build(payload))
                    continue
                records.append(
                    self.build(self._quantified(payload, sample.tilt_deg + noise, sigma))
                )
        return records

    def differential_head_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """Differential pressure across the layer: fouling, not saturation.

        This is the channel that separates mode 2 from mode 1.  A saturated but
        clean layer passes the same flow it always did; a fouled one does not,
        and the head across it rises.  The record carries no chemistry at all.
        """
        records: list[ObservationRecord] = []
        station = self._survey_station()
        period = (
            self.assumptions.differential_head_period_s
            if self.assumptions.differential_head_period_s is not None
            else self.config.bottom_water_probe_period_s
        )
        sigma_rel = self.assumptions.differential_head_relative_noise
        for moment in self.schedule(period, duration_s):
            for tile_id in scene.tile_ids:
                sample = scene.sample_at(tile_id, moment)
                self.reading_rng("differential_head", moment, tile_id)
                noise = float(self._rng.normal(0.0, sigma_rel))
                payload = self._tile_payload(station, scene, tile_id, moment, 0.0)
                payload.update(
                    {
                        "sensor_id": f"SIM_DP_{tile_id}",
                        "parameter": Parameter.DIFFERENTIAL_HEAD.value,
                        "quantity_kind": QuantityKind.CONTEXT.value,
                        "unit": "Pa",
                        "acquisition_kind": AcquisitionKind.IN_SITU_SENSOR.value,
                        "method_id": CONDITION_METHOD_IDS["differential_head"],
                        "data_origin": DataOrigin.SENSOR.value,
                        "calibration_id": "CAL_SIM_V1",
                        "source_ref": (
                            "head loss across the reactive layer; a rising head means "
                            "pore blockage (mode 2), which a saturation measurement "
                            f"cannot distinguish. ASSUMPTION sigma_rel={sigma_rel}. "
                            "Carries no chemistry"
                        ),
                    }
                )
                if self.in_dropout(moment):
                    payload.update(self.missing("simulated sensor dropout window"))
                    records.append(self.build(payload))
                    continue
                if sample.differential_head_pa is None:
                    payload.update(self.missing("the supplied scene has no hydraulic head model or measurement"))
                    records.append(self.build(payload))
                    continue
                value = max(sample.differential_head_pa * (1.0 + noise), 0.0)
                records.append(
                    self.build(
                        self._quantified(
                            payload, value, abs(sample.differential_head_pa * sigma_rel)
                        )
                    )
                )
        return records

    # -- entry point --------------------------------------------------------

    def generate(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """Every condition channel, sorted by availability then observation."""
        records: list[ObservationRecord] = []
        records.extend(self.damage_class_records(scene, duration_s))
        records.extend(self.coverage_records(scene, duration_s))
        records.extend(self.burial_records(scene, duration_s))
        if self.assumptions.emit_scour:
            records.extend(self.scour_records(scene, duration_s))
        records.extend(self.displacement_records(scene, duration_s))
        if self.assumptions.emit_tilt:
            records.extend(self.tilt_records(scene, duration_s))
        records.extend(self.differential_head_records(scene, duration_s))
        records.sort(
            key=lambda record: (
                record.available_at_utc,
                record.observed_at_utc,
                record.record_id,
            )
        )
        return records
