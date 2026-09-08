"""Synthetic measurement generator (``docs/MODEL_SPEC.md`` section 6).

The generator turns a **scripted environment history** into observation
records.  It is deliberately the only place in this branch where a simulated
concentration becomes a measurement, and it is the place where every
degradation of that measurement is introduced explicitly:

* separate instrument noise per channel (relative, assumption),
* a sampling cycle per channel (artificial schedules, assumption),
* LOD / LOQ censoring, so a non-detect stays a bound and never a zero,
* random missingness and a hard sensor-dropout window,
* multiplicative sensor drift after a configurable start time,
* laboratory latency, so ``available_at_utc`` is later than ``observed_at_utc``.

The caller supplies the series to be measured (:class:`ScriptedScene`).  The
generator never opens a results directory and never reads a stored simulator
state itself: the boundary between the hidden simulated state and the
measurement stream is this function call, and it is one directional argument.

Every record is built as a plain dictionary and then passed through
``reactive_seabed_mat.observations.records.record_from_dict``, so the coordinator-owned
schema and semantic checks validate everything this module emits.  The schema is
not forked and no field is invented.

Provenance: every number produced here is ``synthetic_demo`` or an explicit
``assumption``.  None of the noise levels, detection limits or sampling rates is
a verified instrument specification (see ``docs/SENSOR_SUPPLIERS.md``,
[S13]-[S22]); they are demonstration assumptions and are named as such in each
record's ``source_ref``.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

import numpy as np

from ..config import ObservationConfig, StationConfig
from ..contracts import (
    AcquisitionKind,
    DataOrigin,
    Fraction,
    Matrix,
    ObservationRecord,
    Parameter,
    Qualifier,
    QualityFlag,
)
from ..units import format_utc, from_si_aqueous_concentration, from_si_mass
from .records import record_from_dict

__all__ = [
    "CONTEXT_UNITS",
    "METHOD_IDS",
    "StationSample",
    "ScriptedScene",
    "GeneratorAssumptions",
    "ObservationGenerator",
    "constant_scene",
    "ramp_scene",
]


#: Display unit of every context / housekeeping channel.  There is no automatic
#: inference from the parameter name anywhere: this table is explicit, and
#: ``reactive_seabed_mat.units`` refuses any unit that is not on a declared ladder.
CONTEXT_UNITS: Mapping[str, str] = {
    Parameter.TEMPERATURE.value: "degC",
    Parameter.CONDUCTIVITY.value: "mS/cm",
    Parameter.SALINITY.value: "1",
    Parameter.PH.value: "pH",
    Parameter.TURBIDITY.value: "NTU",
    Parameter.CURRENT_EAST.value: "m/s",
    Parameter.CURRENT_NORTH.value: "m/s",
    Parameter.MESH_TILT.value: "deg",
    Parameter.BATTERY_VOLTAGE.value: "V",
}

#: Method identifiers.  ``SIM_`` marks a simulated method definition; none of
#: these is a vendor method reference.
METHOD_IDS: Mapping[str, str] = {
    "probe_labile": "SIM_VOLTAMMETRY_LABILE_V1",
    "lab_labile": "SIM_LAB_DGT_LABILE_V1",
    "lab_total_recoverable": "SIM_LAB_ICPMS_TOTREC_V1",
    "lab_hg_dissolved_inorganic": "SIM_LAB_CVAFS_DISSINORG_V1",
    "passive_sampler": "SIM_DGT_ACCUM_MASS_V1",
    "media_assay": "SIM_MEDIA_DIGEST_ICPMS_V1",
    "temperature": "SIM_CTZN_TEMP_V1",
    "conductivity": "SIM_CTZN_COND_V1",
    "salinity": "PRACTICAL_SALINITY_PSS78",
    "pH": "SIM_PH_ELECTRODE_V1",
    "turbidity": "SIM_TURB_NTU_V1",
    "current": "SIM_CURRENT_METER_V1",
    "housekeeping": "SIM_HOUSEKEEPING_V1",
}


# ---------------------------------------------------------------------------
# The scripted environment the generator measures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class StationSample:
    """One instant of the scripted environment at one station.

    ``concentration_kg_per_m3`` is the *dissolved* pool per element in SI.
    ``environment`` holds context channels in their display unit (degC, mS/cm,
    NTU, m/s, ...), because those channels have no SI ladder in
    ``reactive_seabed_mat.units``; the unit of each is fixed by :data:`CONTEXT_UNITS`.
    """

    time_utc: datetime
    concentration_kg_per_m3: Mapping[str, float]
    environment: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScriptedScene:
    """A scripted environment history, supplied by the caller.

    ``station_samples`` maps a station id to a time-ordered series.  Between two
    samples the generator uses a **zero-order hold** (the last sample is held);
    this is an explicit interpolation assumption, not a physical statement.

    ``media_loading_kg_per_kg`` maps a media id to its loading per element, used
    only by :meth:`ObservationGenerator.media_assay_record`.
    """

    station_samples: Mapping[str, Sequence[StationSample]]
    media_loading_kg_per_kg: Mapping[str, Mapping[str, float]] = field(
        default_factory=dict
    )
    notes: str = "scripted synthetic scene; not measured data"

    def series(self, station_id: str) -> Sequence[StationSample]:
        try:
            return self.station_samples[station_id]
        except KeyError:
            raise KeyError(
                f"station {station_id!r} is not in the scripted scene; "
                f"available: {sorted(self.station_samples)}"
            ) from None

    def sample_at(self, station_id: str, moment: datetime) -> StationSample:
        """Zero-order hold lookup (the last sample at or before ``moment``)."""
        series = self.series(station_id)
        if not series:
            raise KeyError(f"station {station_id!r} has an empty series")
        times = [sample.time_utc for sample in series]
        index = bisect_right(times, moment) - 1
        if index < 0:
            index = 0  # before the first sample: hold the first value forward
        return series[index]

    def mean_concentration(
        self, station_id: str, element: str, start: datetime, end: datetime
    ) -> float:
        """Time-weighted zero-order-hold mean over ``[start, end]`` in kg m^-3."""
        if end <= start:
            return float(self.sample_at(station_id, start).concentration_kg_per_m3.get(element, 0.0))
        series = self.series(station_id)
        edges = [start]
        for sample in series:
            if start < sample.time_utc < end:
                edges.append(sample.time_utc)
        edges.append(end)
        total = 0.0
        span = (end - start).total_seconds()
        for left, right in zip(edges[:-1], edges[1:]):
            width = (right - left).total_seconds()
            value = self.sample_at(station_id, left).concentration_kg_per_m3.get(element, 0.0)
            total += float(value) * width
        return total / span


# ---------------------------------------------------------------------------
# Generator assumptions (everything here is an ASSUMPTION, not a specification)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GeneratorAssumptions:
    """Assumptions the run configuration does not carry.

    Every field is an ASSUMPTION for a demonstration.  None of them is a
    vendor specification, a validated calibration or a measured ratio.
    """

    #: c_labile = chi_labile * c_dissolved.  Default 1.0: the simulated
    #: dissolved pool *is* the labile pool, stated rather than hidden
    #: (MODEL_SPEC section 6).  ASSUMPTION.
    chi_labile: float = 1.0
    #: c_total_recoverable = ratio * c_labile.  ASSUMPTION; a real ratio is
    #: site, particle-load and method dependent and is not a constant.
    total_recoverable_ratio: float = 1.6
    #: c_dissolved_inorganic(Hg) = ratio * c_labile(Hg).  ASSUMPTION [S04].
    hg_dissolved_inorganic_ratio: float = 1.0
    #: Report ``uncertainty_std`` on quantified records.  When False the
    #: uncertainty stays unknown, and the estimator must fall back to a stated
    #: assumption instead of inventing one.
    report_uncertainty_std: bool = True
    #: Probability that a quantified record reports no uncertainty at all.
    unknown_uncertainty_probability: float = 0.0
    #: Illustrative passive-sampler uptake rate.  ASSUMPTION: order of
    #: magnitude for a standard piston sampler, not a calibrated Rs.
    passive_sampler_rate_l_per_h: float = 0.02
    passive_sampler_period_s: float = 172800.0
    passive_sampler_latency_s: float = 259200.0
    media_assay_latency_s: float = 259200.0
    #: Emit a total-recoverable record beside each laboratory labile record, so
    #: the fraction-mismatch path is always exercised.
    emit_total_recoverable_with_lab: bool = True
    #: Elements the in-situ metal probe can measure.  A Pb-selective
    #: voltammetric probe is not a mercury sensor: an Hg-bearing working
    #: electrode is not evidence of Hg measurement [S19].
    probe_elements: tuple[str, ...] = ("Pb",)
    #: Elements the laboratory path measures.
    lab_elements: tuple[str, ...] = ("Pb", "Hg")
    #: Forced stuck-value window (seconds from start) for the QC demonstration.
    stuck_window_s: tuple[float, float] | None = None
    #: Value the sensor sticks at, in ng/L.  ASSUMPTION.
    stuck_value_ng_per_l: float = 148.2
    #: Station used for the passive sampler and the media assay.
    passive_sampler_station_id: str | None = None
    media_assay_station_id: str = "ST_MESH"
    record_id_prefix: str = "G"


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class ObservationGenerator:
    """Emit valid :class:`~reactive_seabed_mat.contracts.ObservationRecord` streams.

    The generator is deterministic for a given ``seed`` and scene: it draws a
    fixed number of random numbers per scheduled reading, in a fixed order.
    """

    def __init__(
        self,
        config: ObservationConfig,
        *,
        seed: int,
        start_utc: datetime,
        assumptions: GeneratorAssumptions | None = None,
    ) -> None:
        if start_utc.tzinfo is None:
            raise ValueError("start_utc must be timezone-aware UTC")
        self.config = config
        self.seed = int(seed)
        self.start_utc = start_utc.astimezone(timezone.utc)
        self.assumptions = assumptions or GeneratorAssumptions()
        self._rng = np.random.default_rng(self.seed)
        self._counter = 0

    # -- helpers ------------------------------------------------------------

    def _next_id(self) -> str:
        self._counter += 1
        return f"{self.assumptions.record_id_prefix}{self._counter:05d}"

    def _elapsed_s(self, moment: datetime) -> float:
        return (moment - self.start_utc).total_seconds()

    def _in_dropout(self, moment: datetime) -> bool:
        window = self.config.sensor_dropout_window_s
        if window is None:
            return False
        elapsed = self._elapsed_s(moment)
        return window[0] <= elapsed <= window[1]

    def _in_stuck_window(self, moment: datetime) -> bool:
        window = self.assumptions.stuck_window_s
        if window is None:
            return False
        elapsed = self._elapsed_s(moment)
        return window[0] <= elapsed <= window[1]

    def _drift_factor(self, moment: datetime) -> float:
        """Multiplicative sensor drift ``1 + drift(t)`` (MODEL_SPEC section 6)."""
        start = self.config.sensor_drift_start_s
        if start is None or self.config.sensor_drift_per_s == 0.0:
            return 1.0
        elapsed = self._elapsed_s(moment)
        if elapsed <= start:
            return 1.0
        return 1.0 + self.config.sensor_drift_per_s * (elapsed - start)

    def _schedule(self, period_s: float, duration_s: float) -> list[datetime]:
        if period_s <= 0.0:
            raise ValueError("a sampling period must be positive")
        count = int(math.floor(duration_s / period_s)) + 1
        return [self.start_utc + timedelta(seconds=index * period_s) for index in range(count)]

    def _base_payload(self, station: StationConfig) -> dict[str, Any]:
        return {
            "sensor_id": None,
            "sample_id": None,
            "media_id": None,
            "sampling_start_utc": None,
            "sampling_end_utc": None,
            "value": None,
            "uncertainty_std": None,
            "lower_bound": None,
            "upper_bound": None,
            "calibration_id": None,
            "source_ref": None,
            "x_m": station.x_m,
            "y_m": station.y_m,
            "depth_m": station.depth_m,
            "crs": "LOCAL_METRIC",
        }

    def _censor(
        self,
        value: float,
        lod: float,
        loq: float,
        sigma_rel: float,
        *,
        report_uncertainty: bool,
    ) -> dict[str, Any]:
        """Apply the LOD / LOQ ladder.  A non-detect is a bound, never a zero."""
        if value < lod:
            return {
                "value": None,
                "uncertainty_std": None,
                "qualifier": Qualifier.BELOW_LOD.value,
                "lower_bound": 0.0,
                "upper_bound": float(lod),
                "quality_flag": int(QualityFlag.PASSED),
            }
        if value < loq:
            return {
                "value": None,
                "uncertainty_std": None,
                "qualifier": Qualifier.BELOW_LOQ.value,
                "lower_bound": float(lod),
                "upper_bound": float(loq),
                "quality_flag": int(QualityFlag.PASSED),
            }
        uncertainty = float(value * sigma_rel) if report_uncertainty else None
        return {
            "value": float(value),
            "uncertainty_std": uncertainty,
            "qualifier": Qualifier.QUANTIFIED.value,
            "lower_bound": None,
            "upper_bound": None,
            "quality_flag": int(QualityFlag.PASSED),
        }

    @staticmethod
    def _missing(reason: str) -> dict[str, Any]:
        """A missing result: no value, no interval, flag 9, no information."""
        return {
            "value": None,
            "uncertainty_std": None,
            "qualifier": Qualifier.MISSING.value,
            "lower_bound": None,
            "upper_bound": None,
            "quality_flag": int(QualityFlag.MISSING),
            "source_ref": reason,
        }

    def _build(self, payload: Mapping[str, Any]) -> ObservationRecord:
        """Validate against the coordinator-owned schema and type the record."""
        return record_from_dict(dict(payload), validate=True)

    # -- channels -----------------------------------------------------------

    def metal_probe_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """In-situ metal probe: labile fraction, seawater, one point per cycle."""
        records: list[ObservationRecord] = []
        stations = [s for s in self.config.stations if s.kind == "metal_probe"]
        sigma_rel = self.config.metal_probe_relative_noise
        lod = self.config.metal_probe_lod_ng_per_l
        loq = self.config.metal_probe_loq_ng_per_l
        for moment in self._schedule(self.config.metal_probe_period_s, duration_s):
            for station in stations:
                sensor_id = f"SIM_PBPROBE_{station.station_id}"
                for element in self.assumptions.probe_elements:
                    # Fixed draw order keeps the stream reproducible.
                    noise = float(self._rng.normal(0.0, sigma_rel))
                    missing_draw = float(self._rng.random())
                    unknown_draw = float(self._rng.random())
                    payload = self._base_payload(station)
                    payload.update(
                        {
                            "record_id": self._next_id(),
                            "station_id": station.station_id,
                            "sensor_id": sensor_id,
                            "observed_at_utc": format_utc(moment),
                            "available_at_utc": format_utc(
                                moment + timedelta(seconds=self.config.metal_probe_latency_s)
                            ),
                            "parameter": element,
                            "unit": "ng/L",
                            "matrix": Matrix.SEAWATER.value,
                            "fraction": Fraction.LABILE.value,
                            "acquisition_kind": AcquisitionKind.IN_SITU_SENSOR.value,
                            "method_id": METHOD_IDS["probe_labile"],
                            "calibration_id": "CAL_SIM_V1",
                            "data_origin": DataOrigin.SYNTHETIC.value,
                        }
                    )
                    if self._in_dropout(moment):
                        payload.update(
                            self._missing(
                                "simulated sensor dropout window; missing is not a "
                                "non-detect and carries no chemical information"
                            )
                        )
                        records.append(self._build(payload))
                        continue
                    if missing_draw < self.config.missing_probability:
                        payload.update(
                            self._missing(
                                "simulated missing result (ASSUMPTION: "
                                f"missing_probability={self.config.missing_probability})"
                            )
                        )
                        records.append(self._build(payload))
                        continue
                    sample = scene.sample_at(station.station_id, moment)
                    dissolved = float(sample.concentration_kg_per_m3.get(element, 0.0))
                    labile_si = self.assumptions.chi_labile * dissolved
                    true_ng_per_l = from_si_aqueous_concentration(labile_si, "ng/L")
                    if self._in_stuck_window(moment):
                        reported = self.assumptions.stuck_value_ng_per_l
                        stuck_note = "; simulated stuck sensor value"
                    else:
                        reported = true_ng_per_l * self._drift_factor(moment) * (1.0 + noise)
                        stuck_note = ""
                    reported = max(reported, 0.0)
                    report_uncertainty = self.assumptions.report_uncertainty_std and (
                        unknown_draw >= self.assumptions.unknown_uncertainty_probability
                    )
                    payload.update(
                        self._censor(
                            reported, lod, loq, sigma_rel,
                            report_uncertainty=report_uncertainty,
                        )
                    )
                    payload["source_ref"] = (
                        "synthetic_demo in-situ probe; ASSUMPTION sigma_rel="
                        f"{sigma_rel}, LOD={lod} ng/L, LOQ={loq} ng/L, "
                        f"chi_labile={self.assumptions.chi_labile}" + stuck_note
                    )
                    records.append(self._build(payload))
        return records

    def environmental_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """Context and housekeeping channels.

        These constrain water conditions and instrument health only.  They are
        never converted into a Pb or Hg concentration anywhere in this package.
        """
        records: list[ObservationRecord] = []
        stations = [s for s in self.config.stations if s.kind == "environmental"]
        sigma_rel = self.config.environmental_relative_noise
        for moment in self._schedule(self.config.environmental_period_s, duration_s):
            for station in stations:
                sample = scene.sample_at(station.station_id, moment)
                for parameter, unit in CONTEXT_UNITS.items():
                    if parameter not in sample.environment:
                        continue
                    noise = float(self._rng.normal(0.0, sigma_rel))
                    true_value = float(sample.environment[parameter])
                    reported = true_value * (1.0 + noise)
                    if parameter == Parameter.BATTERY_VOLTAGE.value:
                        matrix = Matrix.INSTRUMENT.value
                        method = METHOD_IDS["housekeeping"]
                        sensor_id = f"SIM_HOUSEKEEPING_{station.station_id}"
                    elif parameter in (
                        Parameter.CURRENT_EAST.value,
                        Parameter.CURRENT_NORTH.value,
                    ):
                        matrix = Matrix.SEAWATER.value
                        method = METHOD_IDS["current"]
                        sensor_id = f"SIM_ADCP_{station.station_id}"
                    elif parameter == Parameter.MESH_TILT.value:
                        matrix = Matrix.INSTRUMENT.value
                        method = METHOD_IDS["housekeeping"]
                        sensor_id = f"SIM_TILT_{station.station_id}"
                    else:
                        matrix = Matrix.SEAWATER.value
                        method = METHOD_IDS.get(parameter, METHOD_IDS["housekeeping"])
                        sensor_id = f"SIM_CTZN_{station.station_id}"
                    payload = self._base_payload(station)
                    payload.update(
                        {
                            "record_id": self._next_id(),
                            "station_id": station.station_id,
                            "sensor_id": sensor_id,
                            "observed_at_utc": format_utc(moment),
                            "available_at_utc": format_utc(moment),
                            "parameter": parameter,
                            "unit": unit,
                            "matrix": matrix,
                            "fraction": Fraction.NOT_APPLICABLE.value,
                            "acquisition_kind": AcquisitionKind.IN_SITU_SENSOR.value,
                            "method_id": method,
                            "calibration_id": "CAL_SIM_V1",
                            "data_origin": DataOrigin.SYNTHETIC.value,
                            "value": float(reported),
                            "uncertainty_std": abs(float(true_value * sigma_rel)),
                            "qualifier": Qualifier.QUANTIFIED.value,
                            "quality_flag": int(QualityFlag.PASSED),
                            "source_ref": (
                                "synthetic_demo context channel; ASSUMPTION sigma_rel="
                                f"{sigma_rel}; constrains water conditions or QC only, "
                                "never a metal concentration"
                            ),
                        }
                    )
                    if self._in_dropout(moment) and matrix == Matrix.SEAWATER.value:
                        payload.update(
                            self._missing("simulated sensor dropout window")
                        )
                    records.append(self._build(payload))
        return records

    def laboratory_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """Delayed grab-sample results.

        ``available_at_utc = observed_at_utc + lab_latency_s``: the result of a
        sample taken now cannot influence a decision taken now.  Each sample
        emits a labile record (assimilable against the labile model state) and,
        for Pb, a total-recoverable record from the *same* sample, which is a
        different chemical fraction and must not be merged with it silently.
        """
        records: list[ObservationRecord] = []
        stations = [s for s in self.config.stations if s.kind in ("metal_probe", "reference")]
        sigma_rel = self.config.lab_relative_noise
        lod = self.config.lab_lod_ng_per_l
        loq = self.config.lab_loq_ng_per_l
        latency = timedelta(seconds=self.config.lab_latency_s)
        sample_index = 0
        for moment in self._schedule(self.config.lab_sample_period_s, duration_s):
            for station in stations:
                sample_index += 1
                sample_id = f"SMP_{sample_index:04d}"
                scene_sample = scene.sample_at(station.station_id, moment)
                for element in self.assumptions.lab_elements:
                    dissolved = float(scene_sample.concentration_kg_per_m3.get(element, 0.0))
                    labile_si = self.assumptions.chi_labile * dissolved
                    labile_ng_per_l = from_si_aqueous_concentration(labile_si, "ng/L")
                    noise = float(self._rng.normal(0.0, sigma_rel))
                    reported = max(labile_ng_per_l * (1.0 + noise), 0.0)
                    if element == "Hg":
                        fraction = Fraction.DISSOLVED_INORGANIC.value
                        method = METHOD_IDS["lab_hg_dissolved_inorganic"]
                        reported *= self.assumptions.hg_dissolved_inorganic_ratio
                        note = (
                            "laboratory Hg path [S21]; dissolved inorganic is not the "
                            "labile model state and is not merged with it"
                        )
                    else:
                        fraction = Fraction.LABILE.value
                        method = METHOD_IDS["lab_labile"]
                        note = "laboratory labile-fraction result; delayed by lab latency"
                    payload = self._base_payload(station)
                    payload.update(
                        {
                            "record_id": self._next_id(),
                            "station_id": station.station_id,
                            "sample_id": sample_id,
                            "observed_at_utc": format_utc(moment),
                            "available_at_utc": format_utc(moment + latency),
                            "parameter": element,
                            "unit": "ng/L",
                            "matrix": Matrix.SEAWATER.value,
                            "fraction": fraction,
                            "acquisition_kind": AcquisitionKind.GRAB_SAMPLE.value,
                            "method_id": method,
                            "data_origin": DataOrigin.LABORATORY.value,
                        }
                    )
                    payload.update(
                        self._censor(
                            reported, lod, loq, sigma_rel,
                            report_uncertainty=self.assumptions.report_uncertainty_std,
                        )
                    )
                    payload["source_ref"] = (
                        f"synthetic_demo laboratory result; ASSUMPTION sigma_rel={sigma_rel}, "
                        f"LOD={lod} ng/L, LOQ={loq} ng/L, latency="
                        f"{self.config.lab_latency_s} s. {note}"
                    )
                    records.append(self._build(payload))

                    if element == "Pb" and self.assumptions.emit_total_recoverable_with_lab:
                        total = reported * self.assumptions.total_recoverable_ratio
                        payload_tr = self._base_payload(station)
                        payload_tr.update(
                            {
                                "record_id": self._next_id(),
                                "station_id": station.station_id,
                                "sample_id": sample_id,
                                "observed_at_utc": format_utc(moment),
                                "available_at_utc": format_utc(moment + latency),
                                "parameter": element,
                                "unit": "ng/L",
                                "matrix": Matrix.SEAWATER.value,
                                "fraction": Fraction.TOTAL_RECOVERABLE.value,
                                "acquisition_kind": AcquisitionKind.GRAB_SAMPLE.value,
                                "method_id": METHOD_IDS["lab_total_recoverable"],
                                "data_origin": DataOrigin.LABORATORY.value,
                            }
                        )
                        payload_tr.update(
                            self._censor(
                                total, lod, loq, sigma_rel,
                                report_uncertainty=self.assumptions.report_uncertainty_std,
                            )
                        )
                        payload_tr["source_ref"] = (
                            "synthetic_demo laboratory result; total recoverable is NOT "
                            "interchangeable with labile (ASSUMPTION ratio="
                            f"{self.assumptions.total_recoverable_ratio}, which a real site "
                            "would not hold constant)"
                        )
                        records.append(self._build(payload_tr))
        return records

    def passive_sampler_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """Integrated passive-sampler exposures.

        The record stores an **accumulated mass in ng** with an exposure window.
        It is not forced into ng/L: that would need a sampler-specific operator
        and a calibrated uptake rate, which this demonstration does not have.
        """
        records: list[ObservationRecord] = []
        station_id = self.assumptions.passive_sampler_station_id
        if station_id is None:
            candidates = [s for s in self.config.stations if s.kind == "metal_probe"]
            if not candidates:
                return records
            station = candidates[-1]
        else:
            matches = [s for s in self.config.stations if s.station_id == station_id]
            if not matches:
                raise KeyError(f"passive-sampler station {station_id!r} is not configured")
            station = matches[0]
        period = self.assumptions.passive_sampler_period_s
        rate_m3_per_s = self.assumptions.passive_sampler_rate_l_per_h * 1.0e-3 / 3600.0
        window_index = 0
        start = self.start_utc
        while (start - self.start_utc).total_seconds() + period <= duration_s:
            end = start + timedelta(seconds=period)
            window_index += 1
            for element in self.assumptions.lab_elements:
                mean_si = scene.mean_concentration(station.station_id, element, start, end)
                mass_kg = rate_m3_per_s * mean_si * period
                mass_ng = from_si_mass(mass_kg, "ng")
                payload = self._base_payload(station)
                payload.update(
                    {
                        "record_id": self._next_id(),
                        "station_id": station.station_id,
                        "sample_id": f"PS_{window_index:04d}",
                        "observed_at_utc": format_utc(end),
                        "available_at_utc": format_utc(
                            end + timedelta(seconds=self.assumptions.passive_sampler_latency_s)
                        ),
                        "sampling_start_utc": format_utc(start),
                        "sampling_end_utc": format_utc(end),
                        "parameter": element,
                        "unit": "ng",
                        "matrix": Matrix.SEAWATER.value,
                        "fraction": Fraction.LABILE.value,
                        "acquisition_kind": AcquisitionKind.PASSIVE_SAMPLER.value,
                        "method_id": METHOD_IDS["passive_sampler"],
                        "data_origin": DataOrigin.LABORATORY.value,
                        "value": float(mass_ng),
                        "uncertainty_std": float(0.2 * mass_ng),
                        "qualifier": Qualifier.QUANTIFIED.value,
                        "quality_flag": int(QualityFlag.NOT_EVALUATED),
                        "source_ref": (
                            "accumulated mass over an exposure window; NOT an instantaneous "
                            "ng/L point value. ASSUMPTION uptake rate="
                            f"{self.assumptions.passive_sampler_rate_l_per_h} L/h "
                            "(illustrative order of magnitude, not a calibrated Rs)"
                        ),
                    }
                )
                records.append(self._build(payload))
            start = end
        return records

    def media_assay_record(
        self,
        media_id: str,
        loading_kg_per_kg: float,
        observed_at: datetime,
        *,
        element: str = "Pb",
        station_id: str | None = None,
        x_m: float = 300.0,
        y_m: float = 220.0,
        depth_m: float = 3.0,
        relative_uncertainty: float = 0.10,
    ) -> ObservationRecord:
        """An assay of retrieved (or in-place sampled) sorbent.

        Units are on the **mass-fraction ladder** (ng/g).  The aqueous
        conversion is never applied to this record, and the record's
        ``media_id`` decides whether it says anything about the panel that is
        active now (see ``reactive_seabed_mat.observations.operator``).
        """
        station = station_id or self.assumptions.media_assay_station_id
        value_ng_per_g = loading_kg_per_kg / 1.0e-9  # kg/kg -> ng/g, explicit ladder
        payload = {
            "record_id": self._next_id(),
            "station_id": station,
            "sensor_id": None,
            "sample_id": f"MED_{media_id}",
            "media_id": media_id,
            "observed_at_utc": format_utc(observed_at),
            "available_at_utc": format_utc(
                observed_at + timedelta(seconds=self.assumptions.media_assay_latency_s)
            ),
            "sampling_start_utc": None,
            "sampling_end_utc": None,
            "parameter": element,
            "unit": "ng/g",
            "matrix": Matrix.SORBENT.value,
            "fraction": Fraction.SORBED_TOTAL.value,
            "acquisition_kind": AcquisitionKind.MEDIA_ASSAY.value,
            "value": float(value_ng_per_g),
            "uncertainty_std": float(abs(value_ng_per_g) * relative_uncertainty),
            "qualifier": Qualifier.QUANTIFIED.value,
            "lower_bound": None,
            "upper_bound": None,
            "quality_flag": int(QualityFlag.PASSED),
            "method_id": METHOD_IDS["media_assay"],
            "calibration_id": None,
            "data_origin": DataOrigin.LABORATORY.value,
            "source_ref": (
                "sorbent assay; mass-based unit, never the aqueous conversion. "
                "It reports the loading of the assayed media id, not of whichever "
                "panel happens to be active now."
            ),
            "x_m": x_m,
            "y_m": y_m,
            "depth_m": depth_m,
            "crs": "LOCAL_METRIC",
        }
        return self._build(payload)

    # -- entry point --------------------------------------------------------

    def generate(
        self,
        scene: ScriptedScene,
        duration_s: float,
        *,
        include_passive_sampler: bool = True,
    ) -> list[ObservationRecord]:
        """Generate the whole stream, sorted by availability then observation."""
        records: list[ObservationRecord] = []
        records.extend(self.metal_probe_records(scene, duration_s))
        records.extend(self.environmental_records(scene, duration_s))
        records.extend(self.laboratory_records(scene, duration_s))
        if include_passive_sampler:
            records.extend(self.passive_sampler_records(scene, duration_s))
        for media_id, loading in scene.media_loading_kg_per_kg.items():
            for element, value in loading.items():
                records.append(
                    self.media_assay_record(
                        media_id,
                        float(value),
                        self.start_utc + timedelta(seconds=duration_s),
                        element=element,
                    )
                )
        records.sort(
            key=lambda record: (
                record.available_at_utc,
                record.observed_at_utc,
                record.record_id,
            )
        )
        return records


# ---------------------------------------------------------------------------
# Small scene builders (synthetic_demo)
# ---------------------------------------------------------------------------

_DEFAULT_ENVIRONMENT: Mapping[str, float] = {
    Parameter.TEMPERATURE.value: 14.5,
    Parameter.CONDUCTIVITY.value: 52.1,
    Parameter.SALINITY.value: 34.9,
    Parameter.PH.value: 8.05,
    Parameter.TURBIDITY.value: 8.4,
    Parameter.CURRENT_EAST.value: 0.12,
    Parameter.CURRENT_NORTH.value: -0.004,
    Parameter.BATTERY_VOLTAGE.value: 11.6,
}


def constant_scene(
    start_utc: datetime,
    duration_s: float,
    *,
    step_s: float = 600.0,
    concentrations: Mapping[str, Mapping[str, float]],
    environment: Mapping[str, float] | None = None,
    environment_station_id: str = "ST_ENV",
) -> ScriptedScene:
    """A flat scene: constant concentration per station, constant context."""
    env = dict(_DEFAULT_ENVIRONMENT if environment is None else environment)
    n_steps = int(math.floor(duration_s / step_s)) + 1
    samples: dict[str, list[StationSample]] = {}
    station_ids = set(concentrations) | {environment_station_id}
    for station_id in station_ids:
        series: list[StationSample] = []
        for index in range(n_steps):
            moment = start_utc + timedelta(seconds=index * step_s)
            series.append(
                StationSample(
                    time_utc=moment,
                    concentration_kg_per_m3=dict(concentrations.get(station_id, {})),
                    environment=dict(env) if station_id == environment_station_id else {},
                )
            )
        samples[station_id] = series
    return ScriptedScene(station_samples=samples)


def ramp_scene(
    start_utc: datetime,
    duration_s: float,
    *,
    step_s: float = 600.0,
    start_concentrations: Mapping[str, Mapping[str, float]],
    end_concentrations: Mapping[str, Mapping[str, float]],
    environment: Mapping[str, float] | None = None,
    end_environment: Mapping[str, float] | None = None,
    environment_station_id: str = "ST_ENV",
) -> ScriptedScene:
    """A linear ramp between two states, for source-increase demonstrations."""
    env_start = dict(_DEFAULT_ENVIRONMENT if environment is None else environment)
    env_end = dict(env_start if end_environment is None else end_environment)
    n_steps = int(math.floor(duration_s / step_s)) + 1
    samples: dict[str, list[StationSample]] = {}
    station_ids = set(start_concentrations) | set(end_concentrations) | {environment_station_id}
    for station_id in station_ids:
        series: list[StationSample] = []
        first = start_concentrations.get(station_id, {})
        last = end_concentrations.get(station_id, first)
        for index in range(n_steps):
            weight = index / max(n_steps - 1, 1)
            moment = start_utc + timedelta(seconds=index * step_s)
            concentration = {
                element: (1.0 - weight) * float(first.get(element, 0.0))
                + weight * float(last.get(element, first.get(element, 0.0)))
                for element in set(first) | set(last)
            }
            environment_now = {
                key: (1.0 - weight) * float(env_start.get(key, 0.0))
                + weight * float(env_end.get(key, env_start.get(key, 0.0)))
                for key in set(env_start) | set(env_end)
            }
            series.append(
                StationSample(
                    time_utc=moment,
                    concentration_kg_per_m3=concentration,
                    environment=environment_now if station_id == environment_station_id else {},
                )
            )
        samples[station_id] = series
    return ScriptedScene(station_samples=samples)
