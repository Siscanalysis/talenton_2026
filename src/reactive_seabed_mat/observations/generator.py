"""Synthetic measurement generator for the reactive seabed mat.

Implements the measurement side of ``docs/MODEL_SPEC.md`` section 8.  The
generator turns a **scripted model history** into observation records.  It is
the only place in this branch where a simulated quantity becomes a measurement,
and every degradation of that measurement is introduced explicitly:

* separate instrument noise per channel (relative, assumption),
* a campaign rhythm per channel (months between chemistry, not minutes),
* the LOD / LOQ / above-range ladder, so a non-detect stays a bound, an
  over-range reading stays a lower bound, and neither becomes a number,
* random missingness and a hard sensor-dropout window,
* multiplicative sensor drift after a configurable start time,
* laboratory and survey latency, so ``available_at_utc`` is later than
  ``observed_at_utc``.

The channels are the ones a reactive cap is actually judged on:

============================  =========================================
porewater at the sediment face  the driving boundary condition ``C_sed``
bottom water above the mat      ``C_water`` and the residual flux
benthic-chamber areal flux      ``J_out`` directly, in ug/m2/d
DGT accumulated mass            a time-integrated labile pool, in ng
retrieved-media assay           the loading of the **old** media, in ng/g
context and housekeeping        conditions and instrument health only
============================  =========================================

Mat-condition channels (ROV, bathymetric survey, acoustic position and
differential head) live in :mod:`reactive_seabed_mat.observations.condition`.

The caller supplies the history to be measured (:class:`ScriptedScene`).  The
generator never opens a results directory and never reads a stored simulator
state itself: the boundary between the hidden simulated state and the
measurement stream is this function call, and it is one directional argument.

Every record is built as a plain dictionary and then passed through
``reactive_seabed_mat.observations.records.record_from_dict``, so the
coordinator-owned schema and semantic checks validate everything this module
emits.  The schema is not forked and no field is invented.

Provenance: every number produced here is ``synthetic_demo`` or an explicit
``assumption``.  None of the noise levels, detection limits, uptake rates or
sampling rhythms is a verified instrument specification (see
``docs/SENSOR_SUPPLIERS.md``, [S13]-[S22]); they are demonstration assumptions
and are named as such in each record's ``source_ref``.
"""

from __future__ import annotations

import math
import hashlib
from bisect import bisect_right
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from ..config import DegradationEvent, ObservationConfig, StationConfig
from ..contracts import (
    AcquisitionKind,
    DataOrigin,
    Fraction,
    LayerStep,
    Matrix,
    ObservationRecord,
    Parameter,
    ProvenanceLabel,
    Qualifier,
    QualityFlag,
    QuantityKind,
    VerticalDatum,
)
from ..units import (
    convert_scalar,
    format_utc,
    from_si_aqueous_concentration,
    from_si_areal_flux,
    from_si_mass,
    from_si_solid_loading,
)
from .records import ObservationValidationError, load_schema, record_from_dict

__all__ = [
    "CACHED_VALIDATOR",
    "CachedRecordValidator",
    "CONTEXT_CHANNELS",
    "CONTEXT_UNITS",
    "METHOD_IDS",
    "ContextChannel",
    "MatStateSample",
    "EnvironmentSample",
    "MediaBatch",
    "ScriptedScene",
    "GeneratorAssumptions",
    "SyntheticRecordFactory",
    "ObservationGenerator",
    "MediaReplacement",
    "MatHistorySpec",
    "constant_mat_scene",
    "ramp_mat_scene",
    "synthetic_mat_history",
    "scene_from_layer_history",
]

_SECONDS_PER_DAY = 86400.0
_SECONDS_PER_YEAR = 365.25 * _SECONDS_PER_DAY


# ---------------------------------------------------------------------------
# Validation: the coordinator's rules, with the JSON-schema validator compiled
# once instead of once per record
# ---------------------------------------------------------------------------

class CachedRecordValidator:
    """``records.validate_record_dict`` with the schema validator compiled once.

    ``jsonschema.validate(instance, schema)`` re-checks the schema against its
    own metaschema on **every** call.  Measured on this machine, against
    ``observation.schema.json``: 38.7 ms per record for
    ``jsonschema.validate``, 0.57 ms for a pre-built
    ``Draft202012Validator``, a factor of 68.  A multi-year stream is of order
    10^4 records, so the difference is seven minutes against six seconds, and
    it decides whether the demonstration can be run at all.

    This shim does **not** weaken validation:

    * the schema is ``records.load_schema()``, not a copy;
    * the required-key, enum and semantic checks are the coordinator's own
      functions, called in the coordinator's own order;
    * if the private helpers ever move, :attr:`available` goes false and every
      record falls back to the public ``record_from_dict(..., validate=True)``.

    ``tests/observations/test_generator.py`` asserts that the fast path and the
    public path accept and reject exactly the same payloads.

    CONTRACT REQUEST (``docs/handoffs/observations.md``): cache the compiled
    validator inside ``records.validate_record_dict`` and delete this class.
    """

    def __init__(self) -> None:
        self._validator: Any = None
        self._schema_error: type[Exception] | None = None
        self._check_enums: Any = None
        self._check_semantics: Any = None
        self._required: tuple[str, ...] = ()
        try:  # pragma: no cover - environment dependent
            import jsonschema  # type: ignore

            from .records import _check_enums, _check_semantics  # type: ignore
        except (ModuleNotFoundError, ImportError):  # pragma: no cover
            return
        self._validator = jsonschema.Draft202012Validator(load_schema())
        self._schema_error = jsonschema.ValidationError
        self._check_enums = _check_enums
        self._check_semantics = _check_semantics
        self._required = tuple(load_schema()["required"])

    @property
    def available(self) -> bool:
        return self._validator is not None and self._check_semantics is not None

    def validate(self, payload: Mapping[str, Any]) -> None:
        """Exactly the checks ``validate_record_dict`` runs, in the same order."""
        if not self.available:  # pragma: no cover - defensive
            raise RuntimeError("cached validator is unavailable")
        missing = [key for key in self._required if key not in payload]
        if missing:
            raise ObservationValidationError(
                f"{payload.get('record_id')}: missing required fields {missing}"
            )
        try:
            self._validator.validate(dict(payload))
        except self._schema_error as exc:  # type: ignore[misc]
            raise ObservationValidationError(
                f"{payload.get('record_id')}: schema violation: {exc.message}"
            ) from exc
        self._check_enums(payload)
        self._check_semantics(payload)


#: One process-wide compiled validator.  Building it costs about 40 ms once.
CACHED_VALIDATOR = CachedRecordValidator()


# ---------------------------------------------------------------------------
# Context and housekeeping channels
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ContextChannel:
    """One declared context channel: parameter, unit, kind and matrix.

    There is no inference of a unit or a quantity kind from a parameter name
    anywhere in this package; this table is the declaration.
    """

    parameter: str
    unit: str
    quantity_kind: QuantityKind
    matrix: Matrix
    method_key: str
    sensor_prefix: str


#: Context and housekeeping channels the environmental station reports.  None of
#: them is ever converted into a Pb or Hg concentration (MODEL_SPEC section 8).
#: ``dissolved_oxygen`` and ``sulfide`` are aqueous concentrations by kind, so
#: they use the aqueous ladder; they remain context parameters, so the operator
#: still refuses to derive chemistry from them.
CONTEXT_CHANNELS: Mapping[str, ContextChannel] = {
    channel.parameter: channel
    for channel in (
        ContextChannel(Parameter.TEMPERATURE.value, "degC", QuantityKind.CONTEXT,
                       Matrix.BOTTOM_WATER, "temperature", "SIM_CTZN"),
        ContextChannel(Parameter.SEDIMENT_TEMPERATURE.value, "degC", QuantityKind.CONTEXT,
                       Matrix.POREWATER, "sediment_temperature", "SIM_SEDTEMP"),
        ContextChannel(Parameter.CONDUCTIVITY.value, "mS/cm", QuantityKind.CONTEXT,
                       Matrix.BOTTOM_WATER, "conductivity", "SIM_CTZN"),
        ContextChannel(Parameter.SALINITY.value, "1", QuantityKind.CONTEXT,
                       Matrix.BOTTOM_WATER, "salinity", "SIM_CTZN"),
        ContextChannel(Parameter.PH.value, "pH", QuantityKind.CONTEXT,
                       Matrix.BOTTOM_WATER, "pH", "SIM_PH"),
        ContextChannel(Parameter.TURBIDITY.value, "NTU", QuantityKind.CONTEXT,
                       Matrix.BOTTOM_WATER, "turbidity", "SIM_TURB"),
        ContextChannel(Parameter.DISSOLVED_OXYGEN.value, "mg/L",
                       QuantityKind.AQUEOUS_CONCENTRATION, Matrix.BOTTOM_WATER,
                       "dissolved_oxygen", "SIM_OPTODE"),
        ContextChannel(Parameter.REDOX_POTENTIAL.value, "mV", QuantityKind.CONTEXT,
                       Matrix.POREWATER, "redox_potential", "SIM_ORP"),
        ContextChannel(Parameter.SULFIDE.value, "mg/L",
                       QuantityKind.AQUEOUS_CONCENTRATION, Matrix.POREWATER,
                       "sulfide", "SIM_SULFIDE"),
        ContextChannel(Parameter.CURRENT_EAST.value, "m/s", QuantityKind.VELOCITY,
                       Matrix.BOTTOM_WATER, "current", "SIM_ADCP"),
        ContextChannel(Parameter.CURRENT_NORTH.value, "m/s", QuantityKind.VELOCITY,
                       Matrix.BOTTOM_WATER, "current", "SIM_ADCP"),
        ContextChannel(Parameter.SEEPAGE_VELOCITY.value, "cm/yr", QuantityKind.VELOCITY,
                       Matrix.POREWATER, "seepage", "SIM_SEEPMETER"),
        ContextChannel(Parameter.BATTERY_VOLTAGE.value, "V", QuantityKind.CONTEXT,
                       Matrix.INSTRUMENT, "housekeeping", "SIM_HOUSEKEEPING"),
    )
}

#: Display unit of every context channel, kept for convenience.
CONTEXT_UNITS: Mapping[str, str] = {
    key: channel.unit for key, channel in CONTEXT_CHANNELS.items()
}

#: Method identifiers.  ``SIM_`` marks a simulated method definition; none of
#: these is a vendor method reference.
METHOD_IDS: Mapping[str, str] = {
    "porewater_pb": "SIM_LAB_ICPMS_DISSFILT_V1",
    "porewater_hg": "SIM_LAB_CVAFS_DISSINORG_V1",
    "porewater_mehg": "SIM_LAB_MEHG_V1",
    "bottom_water_probe": "SIM_VOLTAMMETRY_LABILE_V1",
    "bottom_water_lab": "SIM_LAB_ICPMS_LABILE_V1",
    "lab_total_recoverable": "SIM_LAB_ICPMS_TOTREC_V1",
    "benthic_chamber_pb": "SIM_BENTHIC_CHAMBER_V1",
    "benthic_chamber_hg": "SIM_BENTHIC_CHAMBER_HG_V1",
    "dgt": "SIM_DGT_ACCUM_MASS_V1",
    "media_assay": "SIM_MEDIA_DIGEST_ICPMS_V1",
    "sediment_core": "SIM_SEDIMENT_DIGEST_V1",
    "temperature": "SIM_CTZN_TEMP_V1",
    "sediment_temperature": "SIM_SEDIMENT_TEMP_V1",
    "conductivity": "SIM_CTZN_COND_V1",
    "salinity": "PRACTICAL_SALINITY_PSS78",
    "pH": "SIM_PH_ELECTRODE_V1",
    "turbidity": "SIM_TURB_NTU_V1",
    "dissolved_oxygen": "SIM_OPTODE_DO_V1",
    "redox_potential": "SIM_ORP_V1",
    "sulfide": "SIM_SULFIDE_ISE_V1",
    "current": "SIM_CURRENT_METER_V1",
    "seepage": "SIM_SEEPAGE_METER_V1",
    "housekeeping": "SIM_HOUSEKEEPING_V1",
}


# ---------------------------------------------------------------------------
# The scripted model history the generator measures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MatStateSample:
    """One instant of the hidden model state at one tile.

    Concentrations are SI (kg m^-3); the areal flux is SI (kg m^-2 s^-1); the
    loading is a mass fraction (kg kg^-1).  Conversion to a display unit happens
    once, in the channel that reports it, through ``reactive_seabed_mat.units``.

    The four degradation modes are carried as four independent fields, exactly
    as they are modelled: nothing here collapses them into one "health" number.
    """

    time_utc: datetime
    #: Sediment-face porewater concentration driving the layer [kg m^-3].
    sediment_porewater_kg_per_m3: Mapping[str, float]
    #: Bottom-water concentration above the mat [kg m^-3].
    bottom_water_kg_per_m3: Mapping[str, float]
    #: Residual areal flux leaving the mat [kg m^-2 s^-1].  The quantity a
    #: benthic chamber measures and the one the mat is judged on.
    flux_out_kg_per_m2_per_s: Mapping[str, float]
    #: Uncapped reference flux for the same driving conditions [kg m^-2 s^-1].
    bare_flux_kg_per_m2_per_s: Mapping[str, float] = field(default_factory=dict)
    #: Porewater concentration inside the reactive layer [kg m^-3].
    mat_porewater_kg_per_m3: Mapping[str, float] = field(default_factory=dict)
    #: Sorbed loading of the medium in this tile [kg kg^-1].
    sorbed_kg_per_kg: Mapping[str, float] = field(default_factory=dict)
    #: Which media batch is installed in this tile at this instant.
    media_id: str | None = None
    #: Mode 2.
    fouling_index: float = 0.0
    #: Mode 4.
    integrity_index: float = 1.0
    #: Mode 3.
    burial_depth_m: float = 0.0
    displacement_m: float = 0.0
    displaced: bool = False
    #: Share of the tile footprint still covered by intact mat.
    coverage_fraction: float = 1.0
    #: Head loss across the layer [Pa].  Separates fouling from saturation.
    differential_head_pa: float | None = None
    #: Tilt of the tile [deg].
    tilt_deg: float | None = None
    #: Effective permeability of the layer [m2].
    permeability_m2: float | None = None
    #: True damage class from the controlled vocabulary in ``condition.py``.
    damage_class: str = "intact"


@dataclass(frozen=True, slots=True)
class EnvironmentSample:
    """Context channels at one station, in each channel's display unit."""

    time_utc: datetime
    values: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class MediaBatch:
    """A batch of reactive medium, and the tile it was laid in.

    ``media_id`` is not interchangeable with ``tile_id``: one batch can be laid
    across several tiles, and a tile outlives the batches that pass through it.
    An assay describes the **batch**, and after a replacement that batch is no
    longer in the water.
    """

    media_id: str
    tile_id: str
    installed_at_utc: datetime
    retrieved_at_utc: datetime | None = None
    #: Loading per element at retrieval [kg kg^-1].
    loading_kg_per_kg: Mapping[str, float] = field(default_factory=dict)

    def active_at(self, moment: datetime) -> bool:
        if moment < self.installed_at_utc:
            return False
        return self.retrieved_at_utc is None or moment < self.retrieved_at_utc


def _mean_zero_order_hold(
    series: Sequence[MatStateSample],
    start: datetime,
    end: datetime,
    getter: Callable[[MatStateSample], float],
) -> float:
    """Time-weighted zero-order-hold mean of ``getter`` over ``[start, end]``.

    Zero-order hold is an explicit interpolation ASSUMPTION, not a physical
    statement: between two scripted samples the last one is held.
    """
    if not series:
        raise KeyError("empty series")
    if end <= start:
        return float(getter(_hold(series, start)))
    edges = [start]
    for sample in series:
        if start < sample.time_utc < end:
            edges.append(sample.time_utc)
    edges.append(end)
    total = 0.0
    span = (end - start).total_seconds()
    for left, right in zip(edges[:-1], edges[1:]):
        total += float(getter(_hold(series, left))) * (right - left).total_seconds()
    return total / span


def _hold(series: Sequence[MatStateSample], moment: datetime) -> MatStateSample:
    times = [sample.time_utc for sample in series]
    index = bisect_right(times, moment) - 1
    return series[max(index, 0)]


@dataclass(frozen=True, slots=True)
class ScriptedScene:
    """A scripted model history, supplied by the caller.

    ``tile_samples`` maps a tile id to a time-ordered series of hidden states.
    ``environment_samples`` maps a station id to its context history.  Between
    two samples a **zero-order hold** is used, which is an explicit
    interpolation assumption.
    """

    tile_samples: Mapping[str, Sequence[MatStateSample]]
    environment_samples: Mapping[str, Sequence[EnvironmentSample]] = field(
        default_factory=dict
    )
    media: Sequence[MediaBatch] = ()
    tile_positions: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    notes: str = "scripted synthetic history; not measured data"

    @property
    def tile_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.tile_samples))

    def series(self, tile_id: str) -> Sequence[MatStateSample]:
        try:
            return self.tile_samples[tile_id]
        except KeyError:
            raise KeyError(
                f"tile {tile_id!r} is not in the scripted scene; "
                f"available: {sorted(self.tile_samples)}"
            ) from None

    def sample_at(self, tile_id: str, moment: datetime) -> MatStateSample:
        series = self.series(tile_id)
        if not series:
            raise KeyError(f"tile {tile_id!r} has an empty series")
        return _hold(series, moment)

    def mean_of(
        self,
        tile_id: str,
        start: datetime,
        end: datetime,
        getter: Callable[[MatStateSample], float],
    ) -> float:
        return _mean_zero_order_hold(self.series(tile_id), start, end, getter)

    def environment_at(self, station_id: str, moment: datetime) -> EnvironmentSample:
        series = self.environment_samples.get(station_id)
        if not series:
            return EnvironmentSample(time_utc=moment, values={})
        times = [sample.time_utc for sample in series]
        index = bisect_right(times, moment) - 1
        return series[max(index, 0)]

    def media_in_tile(self, tile_id: str, moment: datetime) -> MediaBatch | None:
        for batch in self.media:
            if batch.tile_id == tile_id and batch.active_at(moment):
                return batch
        return None

    def position_of(self, tile_id: str) -> tuple[float, float] | None:
        return self.tile_positions.get(tile_id)


# ---------------------------------------------------------------------------
# Generator assumptions (everything here is an ASSUMPTION, not a specification)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GeneratorAssumptions:
    """Assumptions the run configuration does not carry.

    Every field is an ASSUMPTION for a demonstration.  None of them is a vendor
    specification, a validated calibration or a measured ratio.
    """

    #: c_labile = chi_labile * c_dissolved.  Default 1.0: the simulated
    #: dissolved pool *is* the labile pool, stated rather than hidden.
    chi_labile: float = 1.0
    #: c_total_recoverable = ratio * c_labile.  ASSUMPTION; a real ratio is
    #: site, particle-load and method dependent and is not a constant.
    total_recoverable_ratio: float = 1.6
    #: c_dissolved_inorganic(Hg) = ratio * c_labile(Hg).  ASSUMPTION [S04].
    hg_dissolved_inorganic_ratio: float = 1.0
    #: Share of the porewater Hg reported as methylmercury.  A RISK channel,
    #: never a benefit: capping can increase MeHg production [S04].
    methylmercury_fraction: float = 0.04
    #: Report ``uncertainty_std`` on quantified records.
    report_uncertainty_std: bool = True
    #: Probability that a quantified record reports no uncertainty at all.
    unknown_uncertainty_probability: float = 0.0
    #: Probability that a laboratory sample is lost or voided.  ASSUMPTION.
    sample_loss_probability: float = 0.02

    # --- benthic chamber ---------------------------------------------------
    #: Enclosed area of the simulated chamber [m2].  ASSUMPTION: a 0.5 m
    #: diameter benthic chamber, an order of magnitude, not a product.
    chamber_area_m2: float = 0.196
    #: Duration of one chamber deployment [s].  ASSUMPTION.
    chamber_deployment_s: float = 24.0 * 3600.0

    # --- DGT ---------------------------------------------------------------
    #: Effective DGT sampling rate [m3 s^-1].  ASSUMPTION: order of magnitude of
    #: D * A / dg for a standard open-pore disc, NOT a calibrated Rs.
    dgt_sampling_rate_m3_per_s: float = 2.8e-10
    #: Binding-gel capacity [ng].  Beyond it the record is an ABOVE-RANGE lower
    #: bound, never an extrapolated number.  ASSUMPTION: order of magnitude of a
    #: Chelex binding disc, which a sediment-face deployment can genuinely
    #: exhaust.
    dgt_capacity_ng: float = 5.0e4
    dgt_lod_ng: float = 0.2
    dgt_loq_ng: float = 0.6
    dgt_relative_noise: float = 0.15

    # --- media assay -------------------------------------------------------
    media_assay_relative_noise: float = 0.10
    #: Delay between retrieval and the assay reaching the operator [s].
    media_assay_latency_s: float = 21.0 * _SECONDS_PER_DAY

    # --- channel switches --------------------------------------------------
    #: Elements the in-situ metal probe can measure.  A Pb-selective
    #: voltammetric probe is not a mercury sensor [S19].
    probe_elements: tuple[str, ...] = ("Pb",)
    #: Elements the laboratory path measures.
    lab_elements: tuple[str, ...] = ("Pb", "Hg")
    #: Emit a total-recoverable record beside each laboratory labile record, so
    #: the fraction-mismatch path is always exercised.
    emit_total_recoverable_with_lab: bool = True
    #: Emit the methylmercury risk channel with each porewater Hg sample.
    emit_methylmercury: bool = True
    #: Deploy a DGT at the porewater stations as well as the bottom-water ones.
    dgt_at_porewater_stations: bool = True

    # --- QC demonstration --------------------------------------------------
    #: Forced stuck-value window (seconds from start) for the QC demonstration.
    stuck_window_s: tuple[float, float] | None = None
    #: Value the sensor sticks at, in ng/L.  ASSUMPTION.
    stuck_value_ng_per_l: float = 148.2

    record_id_prefix: str = "G"
    provenance: ProvenanceLabel = ProvenanceLabel.SYNTHETIC_DEMO


# ---------------------------------------------------------------------------
# Shared record-building primitives
# ---------------------------------------------------------------------------

class SyntheticRecordFactory:
    """Deterministic record identifiers, schedules and the censoring ladder.

    Shared by :class:`ObservationGenerator` and by the mat-condition generator
    in :mod:`reactive_seabed_mat.observations.condition`, so both streams use
    exactly one censoring ladder and one schedule rule.
    """

    def __init__(
        self,
        config: ObservationConfig,
        *,
        seed: int,
        start_utc: datetime,
        record_id_prefix: str,
        provenance: ProvenanceLabel = ProvenanceLabel.SYNTHETIC_DEMO,
        fast_validation: bool = True,
    ) -> None:
        if start_utc.tzinfo is None:
            raise ValueError("start_utc must be timezone-aware UTC")
        self.config = config
        self.seed = int(seed)
        self.start_utc = start_utc.astimezone(timezone.utc)
        self.record_id_prefix = record_id_prefix
        self.provenance = provenance
        #: Use the compiled validator (identical checks) rather than recompiling
        #: the schema per record.  Set False to force the public slow path.
        self.fast_validation = bool(fast_validation)
        self._rng = np.random.default_rng(self.seed)
        self._counter = 0
        self._window_start_s = 0.0
        self._window_lookback_s = 0.0

    def reading_rng(self, channel: str, moment: datetime, asset: str, parameter: str = "") -> None:
        """Key measurement noise to its channel, asset and experiment time.

        Changing decision cadence, adding a proxy or losing another sample must
        not change an existing laboratory result's random error.
        """
        key = f"{self.seed}|{channel}|{format_utc(moment)}|{asset}|{parameter}"
        seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:16], "little")
        self._rng = np.random.default_rng(seed)

    # -- identifiers and time ----------------------------------------------

    def next_id(self) -> str:
        self._counter += 1
        return f"{self.record_id_prefix}{self._counter:05d}"

    def elapsed_s(self, moment: datetime) -> float:
        return (moment - self.start_utc).total_seconds()

    def schedule(self, period_s: float, duration_s: float) -> list[datetime]:
        if period_s <= 0.0:
            raise ValueError("a sampling period must be positive")
        count = int(math.floor(duration_s / period_s)) + 1
        first = max(0, int(math.floor(
            (self._window_start_s - self._window_lookback_s) / period_s
        )))
        return [
            self.start_utc + timedelta(seconds=index * period_s)
            for index in range(first, count)
        ]

    def in_dropout(self, moment: datetime) -> bool:
        window = self.config.sensor_dropout_window_s
        if window is None:
            return False
        elapsed = self.elapsed_s(moment)
        return window[0] <= elapsed <= window[1]

    def drift_factor(self, moment: datetime) -> float:
        """Multiplicative sensor drift ``1 + drift(t)``."""
        start = self.config.sensor_drift_start_s
        if start is None or self.config.sensor_drift_per_s == 0.0:
            return 1.0
        elapsed = self.elapsed_s(moment)
        if elapsed <= start:
            return 1.0
        return 1.0 + self.config.sensor_drift_per_s * (elapsed - start)

    # -- payloads -----------------------------------------------------------

    def base_payload(
        self,
        station: StationConfig,
        *,
        tile_id: str | None = None,
        x_m: float | None = None,
        y_m: float | None = None,
    ) -> dict[str, Any]:
        """A payload with every schema key present, so nothing is implicit."""
        return {
            "record_id": None,
            "station_id": station.station_id,
            "sensor_id": None,
            "sample_id": None,
            "media_id": None,
            "tile_id": tile_id if tile_id is not None else station.tile_id,
            "observed_at_utc": None,
            "available_at_utc": None,
            "sampling_start_utc": None,
            "sampling_end_utc": None,
            "parameter": None,
            "quantity_kind": None,
            "unit": None,
            "matrix": None,
            "fraction": Fraction.NOT_APPLICABLE.value,
            "acquisition_kind": None,
            "value": None,
            "uncertainty_std": None,
            "qualifier": None,
            "lower_bound": None,
            "upper_bound": None,
            "condition_class": None,
            "quality_flag": int(QualityFlag.PASSED),
            "method_id": None,
            "calibration_id": None,
            "data_origin": None,
            "provenance": self.provenance.value,
            "source_ref": None,
            "x_m": station.x_m if x_m is None else float(x_m),
            "y_m": station.y_m if y_m is None else float(y_m),
            "depth_m": station.depth_m,
            "vertical_datum": VerticalDatum(station.vertical_datum).value,
            "z_in_mat_m": None,
            "chamber_area_m2": None,
            "crs": "LOCAL_METRIC",
        }

    # -- the censoring ladder ----------------------------------------------

    def censor(
        self,
        value: float,
        *,
        lod: float,
        loq: float,
        sigma_rel: float,
        range_top: float | None = None,
        report_uncertainty: bool = True,
    ) -> dict[str, Any]:
        """Apply the LOD / LOQ / above-range ladder.

        A non-detect is a bound, never a zero.  An over-range reading is a
        **lower** bound, never an extrapolated number.
        """
        if range_top is not None and value >= range_top:
            return {
                "value": None,
                "uncertainty_std": None,
                "qualifier": Qualifier.ABOVE_RANGE.value,
                "lower_bound": float(range_top),
                "upper_bound": None,
                "quality_flag": int(QualityFlag.PASSED),
            }
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
        uncertainty = abs(float(value * sigma_rel)) if report_uncertainty else None
        return {
            "value": float(value),
            "uncertainty_std": uncertainty,
            "qualifier": Qualifier.QUANTIFIED.value,
            "lower_bound": None,
            "upper_bound": None,
            "quality_flag": int(QualityFlag.PASSED),
        }

    @staticmethod
    def missing(reason: str) -> dict[str, Any]:
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

    def build(self, payload: Mapping[str, Any]) -> ObservationRecord:
        """Validate against the coordinator-owned schema and type the record.

        Every record this package emits goes through the frozen schema and the
        frozen semantic rules.  The only choice here is whether the JSON-schema
        validator is compiled once or once per record; see
        :class:`CachedRecordValidator`.
        """
        payload = dict(payload)
        identity = "|".join(str(payload.get(key) or "") for key in (
            "station_id", "tile_id", "media_id", "observed_at_utc",
            "sampling_start_utc", "parameter", "quantity_kind", "matrix",
            "fraction", "acquisition_kind", "method_id",
        ))
        payload["record_id"] = self.record_id_prefix + hashlib.sha256(identity.encode()).hexdigest()[:24]
        if payload.get("sample_id"):
            sample_identity = "|".join(str(payload.get(key) or "") for key in (
                "station_id", "tile_id", "observed_at_utc", "sampling_start_utc", "acquisition_kind",
            ))
            payload["sample_id"] = "S_" + hashlib.sha256(sample_identity.encode()).hexdigest()[:20]
        if self.fast_validation and CACHED_VALIDATOR.available:
            CACHED_VALIDATOR.validate(payload)
            return record_from_dict(dict(payload), validate=False)
        return record_from_dict(dict(payload), validate=True)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class ObservationGenerator(SyntheticRecordFactory):
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
        fast_validation: bool = True,
    ) -> None:
        resolved = assumptions or GeneratorAssumptions()
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

    def _stations(self, kind: str) -> list[StationConfig]:
        return [station for station in self.config.stations if station.kind == kind]

    def _tile_for(self, station: StationConfig, scene: ScriptedScene) -> str:
        if station.tile_id is not None:
            return station.tile_id
        tiles = scene.tile_ids
        if not tiles:
            raise KeyError(
                f"station {station.station_id!r} has no tile_id and the scene has "
                "no tiles; a mat observation must be attributable to a tile"
            )
        return tiles[0]

    def _in_stuck_window(self, moment: datetime) -> bool:
        window = self.assumptions.stuck_window_s
        if window is None:
            return False
        elapsed = self.elapsed_s(moment)
        return window[0] <= elapsed <= window[1]

    # -- porewater at the sediment face -------------------------------------

    def porewater_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """Porewater chemistry at the sediment face beneath a tile.

        This is the **driving boundary condition** of the reactive layer, and
        therefore a primary assimilable channel, not background evidence.  It is
        a laboratory result: ``available_at_utc = observed_at_utc + lab_latency_s``.
        """
        records: list[ObservationRecord] = []
        stations = self._stations("porewater")
        sigma_rel = self.config.lab_relative_noise
        lod = convert_scalar(self.config.lab_lod_ng_per_l, "ng/L", "ug/L")
        loq = convert_scalar(self.config.lab_loq_ng_per_l, "ng/L", "ug/L")
        latency = timedelta(seconds=self.config.lab_latency_s)
        sample_index = 0
        for moment in self.schedule(self.config.porewater_sample_period_s, duration_s):
            for station in stations:
                tile_id = self._tile_for(station, scene)
                sample = scene.sample_at(tile_id, moment)
                sample_index += 1
                sample_id = f"PW_{sample_index:05d}"
                for element in self.assumptions.lab_elements:
                    self.reading_rng("porewater", moment, station.station_id, element)
                    noise = float(self._rng.normal(0.0, sigma_rel))
                    loss_draw = float(self._rng.random())
                    driving_si = float(
                        sample.sediment_porewater_kg_per_m3.get(element, 0.0)
                    )
                    true_ug_per_l = from_si_aqueous_concentration(driving_si, "ug/L")
                    reported = max(true_ug_per_l * (1.0 + noise), 0.0)
                    if element == "Hg":
                        fraction = Fraction.DISSOLVED_INORGANIC.value
                        method = METHOD_IDS["porewater_hg"]
                        reported *= self.assumptions.hg_dissolved_inorganic_ratio
                    else:
                        fraction = Fraction.DISSOLVED_FILTERED.value
                        method = METHOD_IDS["porewater_pb"]
                    payload = self.base_payload(station, tile_id=tile_id)
                    payload.update(
                        {
                            "record_id": self.next_id(),
                            "sample_id": sample_id,
                            "observed_at_utc": format_utc(moment),
                            "available_at_utc": format_utc(moment + latency),
                            "parameter": element,
                            "quantity_kind": QuantityKind.AQUEOUS_CONCENTRATION.value,
                            "unit": "ug/L",
                            "matrix": Matrix.POREWATER.value,
                            "fraction": fraction,
                            "acquisition_kind": AcquisitionKind.GRAB_SAMPLE.value,
                            "method_id": method,
                            "data_origin": DataOrigin.LABORATORY.value,
                            "z_in_mat_m": 0.0,
                        }
                    )
                    if loss_draw < self.assumptions.sample_loss_probability:
                        payload.update(
                            self.missing(
                                "simulated lost or voided laboratory sample; missing is "
                                "not a non-detect and carries no chemical information "
                                "(ASSUMPTION sample_loss_probability="
                                f"{self.assumptions.sample_loss_probability})"
                            )
                        )
                        records.append(self.build(payload))
                        continue
                    payload.update(
                        self.censor(
                            reported,
                            lod=lod,
                            loq=loq,
                            sigma_rel=sigma_rel,
                            report_uncertainty=self.assumptions.report_uncertainty_std,
                        )
                    )
                    payload["source_ref"] = (
                        "synthetic_demo porewater at the sediment face: the driving "
                        "boundary condition of the reactive layer. ASSUMPTION "
                        f"sigma_rel={sigma_rel}, LOD={lod:g} ug/L, LOQ={loq:g} ug/L, "
                        f"latency={self.config.lab_latency_s:g} s"
                    )
                    records.append(self.build(payload))

                    if element == "Hg" and self.assumptions.emit_methylmercury:
                        records.append(
                            self._methylmercury_record(
                                station, tile_id, sample_id, moment, latency,
                                reported, sigma_rel, lod, loq,
                            )
                        )
        return records

    def _methylmercury_record(
        self,
        station: StationConfig,
        tile_id: str,
        sample_id: str,
        moment: datetime,
        latency: timedelta,
        inorganic_ug_per_l: float,
        sigma_rel: float,
        lod: float,
        loq: float,
    ) -> ObservationRecord:
        """The methylmercury risk channel.  A risk, never a benefit.

        Capping alters sediment redox and can *increase* MeHg production
        (MODEL_SPEC section 11).  The record exists so that risk is visible.
        """
        self.reading_rng("methylmercury", moment, station.station_id, "Hg")
        noise = float(self._rng.normal(0.0, sigma_rel))
        reported = max(
            inorganic_ug_per_l
            * self.assumptions.methylmercury_fraction
            * (1.0 + noise),
            0.0,
        )
        payload = self.base_payload(station, tile_id=tile_id)
        payload.update(
            {
                "record_id": self.next_id(),
                "sample_id": sample_id,
                "observed_at_utc": format_utc(moment),
                "available_at_utc": format_utc(moment + latency),
                "parameter": "Hg",
                "quantity_kind": QuantityKind.AQUEOUS_CONCENTRATION.value,
                "unit": "ug/L",
                "matrix": Matrix.POREWATER.value,
                "fraction": Fraction.METHYLMERCURY.value,
                "acquisition_kind": AcquisitionKind.GRAB_SAMPLE.value,
                "method_id": METHOD_IDS["porewater_mehg"],
                "data_origin": DataOrigin.LABORATORY.value,
                "z_in_mat_m": 0.0,
            }
        )
        payload.update(
            self.censor(
                reported,
                lod=lod,
                loq=loq,
                sigma_rel=sigma_rel,
                report_uncertainty=self.assumptions.report_uncertainty_std,
            )
        )
        payload["source_ref"] = (
            "methylmercury RISK channel: capping alters sediment redox and can "
            "INCREASE MeHg production [S04]. ASSUMPTION methylmercury_fraction="
            f"{self.assumptions.methylmercury_fraction}. Never a benefit term, and "
            "not the dissolved-inorganic pool"
        )
        return self.build(payload)

    # -- bottom water above the mat ----------------------------------------

    def bottom_water_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """In-situ probe in the bottom water above the mat.

        Constrains ``C_water`` and, together with the driving condition, the
        residual flux.  This is the channel that carries the dropout, drift and
        stuck-value machinery.
        """
        records: list[ObservationRecord] = []
        stations = self._stations("bottom_water_probe")
        sigma_rel = self.config.probe_relative_noise
        lod = self.config.probe_lod_ng_per_l
        loq = self.config.probe_loq_ng_per_l
        range_top = self.config.probe_range_top_ng_per_l
        latency = timedelta(seconds=self.config.probe_latency_s)
        for moment in self.schedule(self.config.bottom_water_probe_period_s, duration_s):
            for station in stations:
                tile_id = self._tile_for(station, scene)
                sensor_id = f"SIM_PBPROBE_{station.station_id}"
                for element in self.assumptions.probe_elements:
                    self.reading_rng("bottom_water", moment, station.station_id, element)
                    noise = float(self._rng.normal(0.0, sigma_rel))
                    missing_draw = float(self._rng.random())
                    unknown_draw = float(self._rng.random())
                    payload = self.base_payload(station, tile_id=tile_id)
                    payload.update(
                        {
                            "record_id": self.next_id(),
                            "sensor_id": sensor_id,
                            "observed_at_utc": format_utc(moment),
                            "available_at_utc": format_utc(moment + latency),
                            "parameter": element,
                            "quantity_kind": QuantityKind.AQUEOUS_CONCENTRATION.value,
                            "unit": "ng/L",
                            "matrix": Matrix.BOTTOM_WATER.value,
                            "fraction": Fraction.LABILE.value,
                            "acquisition_kind": AcquisitionKind.IN_SITU_SENSOR.value,
                            "method_id": METHOD_IDS["bottom_water_probe"],
                            "calibration_id": "CAL_SIM_V1",
                            "data_origin": DataOrigin.SENSOR.value,
                        }
                    )
                    if self.in_dropout(moment):
                        payload.update(
                            self.missing(
                                "simulated sensor dropout window; missing is not a "
                                "non-detect and carries no chemical information"
                            )
                        )
                        records.append(self.build(payload))
                        continue
                    if missing_draw < self.config.missing_probability:
                        payload.update(
                            self.missing(
                                "simulated missing result (ASSUMPTION "
                                f"missing_probability={self.config.missing_probability})"
                            )
                        )
                        records.append(self.build(payload))
                        continue
                    sample = scene.sample_at(tile_id, moment)
                    dissolved = float(sample.bottom_water_kg_per_m3.get(element, 0.0))
                    labile_si = self.assumptions.chi_labile * dissolved
                    true_ng_per_l = from_si_aqueous_concentration(labile_si, "ng/L")
                    if self._in_stuck_window(moment):
                        reported = self.assumptions.stuck_value_ng_per_l
                        stuck_note = "; simulated stuck sensor value"
                    else:
                        reported = (
                            true_ng_per_l * self.drift_factor(moment) * (1.0 + noise)
                        )
                        stuck_note = ""
                    reported = max(reported, 0.0)
                    report_uncertainty = self.assumptions.report_uncertainty_std and (
                        unknown_draw >= self.assumptions.unknown_uncertainty_probability
                    )
                    payload.update(
                        self.censor(
                            reported,
                            lod=lod,
                            loq=loq,
                            sigma_rel=sigma_rel,
                            range_top=range_top,
                            report_uncertainty=report_uncertainty,
                        )
                    )
                    payload["source_ref"] = (
                        "synthetic_demo in-situ probe above the mat; ASSUMPTION "
                        f"sigma_rel={sigma_rel}, LOD={lod} ng/L, LOQ={loq} ng/L, "
                        f"range top={range_top} ng/L, chi_labile="
                        f"{self.assumptions.chi_labile}" + stuck_note
                    )
                    records.append(self.build(payload))
        return records

    # -- benthic chamber ----------------------------------------------------

    def benthic_chamber_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """Benthic-chamber areal flux, in ug/m2/d.

        The only channel that measures what the mat is judged on.  It needs a
        deployment window and an enclosed area to be interpretable at all, so
        both are always written and the schema enforces them.

        A chamber measures the *apparent* flux.  A buried tile emits less and
        the chamber will say so; the record therefore carries no claim about
        why, and burial must never be read as success.
        """
        records: list[ObservationRecord] = []
        stations = self._stations("chamber")
        sigma_rel = self.config.chamber_relative_noise
        lod = self.config.chamber_lod_ug_per_m2_per_d
        loq = self.config.chamber_loq_ug_per_m2_per_d
        latency = timedelta(seconds=self.config.lab_latency_s)
        window = timedelta(seconds=self.assumptions.chamber_deployment_s)
        area = self.assumptions.chamber_area_m2
        deployment = 0
        for start in self.schedule(self.config.chamber_deployment_period_s, duration_s):
            end = start + window
            if self.elapsed_s(end) > duration_s:
                break
            for station in stations:
                tile_id = self._tile_for(station, scene)
                deployment += 1
                sample_id = f"BC_{deployment:05d}"
                for element in self.assumptions.lab_elements:
                    self.reading_rng("chamber", start, station.station_id, element)
                    noise = float(self._rng.normal(0.0, sigma_rel))
                    loss_draw = float(self._rng.random())
                    mean_flux_si = scene.mean_of(
                        tile_id,
                        start,
                        end,
                        lambda item, key=element: float(
                            item.flux_out_kg_per_m2_per_s.get(key, 0.0)
                        ),
                    )
                    reported = max(
                        from_si_areal_flux(mean_flux_si, "ug/m2/d") * (1.0 + noise), 0.0
                    )
                    if element == "Hg":
                        fraction = Fraction.DISSOLVED_INORGANIC.value
                        method = METHOD_IDS["benthic_chamber_hg"]
                    else:
                        fraction = Fraction.TOTAL_RECOVERABLE.value
                        method = METHOD_IDS["benthic_chamber_pb"]
                    payload = self.base_payload(station, tile_id=tile_id)
                    payload.update(
                        {
                            "record_id": self.next_id(),
                            "sample_id": sample_id,
                            "observed_at_utc": format_utc(end),
                            "available_at_utc": format_utc(end + latency),
                            "sampling_start_utc": format_utc(start),
                            "sampling_end_utc": format_utc(end),
                            "parameter": element,
                            "quantity_kind": QuantityKind.AREAL_FLUX.value,
                            "unit": "ug/m2/d",
                            "matrix": Matrix.BOTTOM_WATER.value,
                            "fraction": fraction,
                            "acquisition_kind": AcquisitionKind.BENTHIC_CHAMBER.value,
                            "method_id": method,
                            "data_origin": DataOrigin.LABORATORY.value,
                            "chamber_area_m2": float(area),
                        }
                    )
                    if loss_draw < self.assumptions.sample_loss_probability:
                        payload.update(
                            self.missing(
                                "simulated failed chamber deployment (seal lost); "
                                "missing is not a non-detect"
                            )
                        )
                        records.append(self.build(payload))
                        continue
                    payload.update(
                        self.censor(
                            reported,
                            lod=lod,
                            loq=loq,
                            sigma_rel=sigma_rel,
                            report_uncertainty=self.assumptions.report_uncertainty_std,
                        )
                    )
                    payload["source_ref"] = (
                        "synthetic_demo benthic chamber: the areal flux the mat is "
                        f"judged on, over a {self.assumptions.chamber_deployment_s:g} s "
                        f"deployment enclosing {area:g} m2. ASSUMPTION sigma_rel="
                        f"{sigma_rel}, LOD={lod} ug/m2/d, LOQ={loq} ug/m2/d. It reports "
                        "the APPARENT flux and says nothing about why: burial also "
                        "reduces it"
                    )
                    records.append(self.build(payload))
        return records

    # -- DGT ----------------------------------------------------------------

    def dgt_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """DGT accumulated mass in ng over an exposure window.

        The record stores an accumulated **mass** with its window.  It is never
        forced into a point ng/L: that would need a calibrated, temperature and
        ionic-strength dependent uptake rate this demonstration does not have.
        ``dgt_labile`` is an operationally different pool from voltammetric
        ``labile`` and the two are never merged.

        Beyond the binding-gel capacity the result is an ABOVE-RANGE lower
        bound, which is what a saturated DGT honestly is.
        """
        records: list[ObservationRecord] = []
        stations = list(self._stations("bottom_water_probe"))
        if self.assumptions.dgt_at_porewater_stations:
            stations += self._stations("porewater")
        rate = self.assumptions.dgt_sampling_rate_m3_per_s
        exposure = self.config.dgt_exposure_s
        sigma_rel = self.assumptions.dgt_relative_noise
        latency = timedelta(seconds=self.config.lab_latency_s)
        deployment = 0
        for start in self.schedule(self.config.dgt_deployment_period_s, duration_s):
            end = start + timedelta(seconds=exposure)
            if self.elapsed_s(end) > duration_s:
                break
            for station in stations:
                tile_id = self._tile_for(station, scene)
                deployment += 1
                sample_id = f"DGT_{deployment:05d}"
                if station.kind == "porewater":
                    matrix = Matrix.POREWATER.value
                    getter_name = "sediment_porewater_kg_per_m3"
                else:
                    matrix = Matrix.BOTTOM_WATER.value
                    getter_name = "bottom_water_kg_per_m3"
                for element in self.assumptions.lab_elements:
                    self.reading_rng("dgt", start, station.station_id, element)
                    noise = float(self._rng.normal(0.0, sigma_rel))
                    mean_si = scene.mean_of(
                        tile_id,
                        start,
                        end,
                        lambda item, key=element, name=getter_name: float(
                            getattr(item, name).get(key, 0.0)
                        ),
                    )
                    mass_kg = rate * mean_si * exposure
                    mass_ng = max(from_si_mass(mass_kg, "ng") * (1.0 + noise), 0.0)
                    payload = self.base_payload(station, tile_id=tile_id)
                    payload.update(
                        {
                            "record_id": self.next_id(),
                            "sample_id": sample_id,
                            "observed_at_utc": format_utc(end),
                            "available_at_utc": format_utc(end + latency),
                            "sampling_start_utc": format_utc(start),
                            "sampling_end_utc": format_utc(end),
                            "parameter": element,
                            "quantity_kind": QuantityKind.ACCUMULATED_MASS.value,
                            "unit": "ng",
                            "matrix": matrix,
                            "fraction": Fraction.DGT_LABILE.value,
                            "acquisition_kind": AcquisitionKind.PASSIVE_SAMPLER.value,
                            "method_id": METHOD_IDS["dgt"],
                            "data_origin": DataOrigin.LABORATORY.value,
                            "quality_flag": int(QualityFlag.NOT_EVALUATED),
                        }
                    )
                    censored = self.censor(
                        mass_ng,
                        lod=self.assumptions.dgt_lod_ng,
                        loq=self.assumptions.dgt_loq_ng,
                        sigma_rel=sigma_rel,
                        range_top=self.assumptions.dgt_capacity_ng,
                        report_uncertainty=self.assumptions.report_uncertainty_std,
                    )
                    censored["quality_flag"] = int(QualityFlag.NOT_EVALUATED)
                    payload.update(censored)
                    payload["source_ref"] = (
                        "accumulated mass over a DGT exposure window; NOT an "
                        "instantaneous ng/L, and dgt_labile is NOT the voltammetric "
                        "labile pool. ASSUMPTION effective sampling rate="
                        f"{rate:g} m3/s (order of magnitude of D*A/dg, not a "
                        f"calibrated Rs), gel capacity={self.assumptions.dgt_capacity_ng:g} ng"
                    )
                    records.append(self.build(payload))
        return records

    # -- retrieved-media assay ---------------------------------------------

    def media_assay_record(
        self,
        batch: MediaBatch,
        element: str,
        observed_at: datetime,
        *,
        station: StationConfig | None = None,
        loading_kg_per_kg: float | None = None,
    ) -> ObservationRecord:
        """An assay of retrieved sorbent, on the mass-fraction ladder (ng/g).

        The record describes the **media batch it was taken from**.  After a
        replacement that batch is out of the water, so the record must never be
        read as the loading of the tile now in place: the operator keys on
        ``media_id``, and ``tile_id`` only says where the coupon came from.

        The conversion uses the coordinator-owned solid-loading ladder; the old
        hard-coded ``1.0e-9`` factor defeated the single-source rule.
        """
        resolved_station = station or self._assay_station(batch)
        loading = (
            float(batch.loading_kg_per_kg.get(element, 0.0))
            if loading_kg_per_kg is None
            else float(loading_kg_per_kg)
        )
        value_ng_per_g = from_si_solid_loading(loading, "ng/g")
        self.reading_rng("media_assay", observed_at, f"{batch.tile_id}|{batch.media_id}", element)
        noise = float(self._rng.normal(0.0, self.assumptions.media_assay_relative_noise))
        reported = max(value_ng_per_g * (1.0 + noise), 0.0)
        payload = self.base_payload(resolved_station, tile_id=batch.tile_id)
        payload.update(
            {
                "record_id": self.next_id(),
                "sample_id": f"MED_{batch.media_id}",
                "media_id": batch.media_id,
                "observed_at_utc": format_utc(observed_at),
                "available_at_utc": format_utc(
                    observed_at
                    + timedelta(seconds=self.assumptions.media_assay_latency_s)
                ),
                "parameter": element,
                "quantity_kind": QuantityKind.SOLID_LOADING.value,
                "unit": "ng/g",
                "matrix": Matrix.SORBENT.value,
                "fraction": Fraction.SORBED_TOTAL.value,
                "acquisition_kind": AcquisitionKind.MEDIA_ASSAY.value,
                "value": float(reported),
                "uncertainty_std": abs(
                    float(reported * self.assumptions.media_assay_relative_noise)
                ),
                "qualifier": Qualifier.QUANTIFIED.value,
                "quality_flag": int(QualityFlag.PASSED),
                "method_id": METHOD_IDS["media_assay"],
                "data_origin": DataOrigin.LABORATORY.value,
                "depth_m": 0.0,
                "vertical_datum": VerticalDatum.MAT_TOP.value,
                "source_ref": (
                    f"assay of media batch {batch.media_id!r} retrieved from tile "
                    f"{batch.tile_id!r}; mass-based ladder, never the aqueous "
                    "conversion. It reports the loading of THAT batch, not of "
                    "whichever media is in the tile now"
                ),
            }
        )
        return self.build(payload)

    def _assay_station(self, batch: MediaBatch) -> StationConfig:
        for station in self.config.stations:
            if station.tile_id == batch.tile_id:
                return station
        if self.config.stations:
            return self.config.stations[0]
        raise KeyError("no station configured for a media assay")

    def retrieved_media_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """One assay per element for every media batch retrieved during the run."""
        records: list[ObservationRecord] = []
        horizon = self.start_utc + timedelta(seconds=duration_s)
        for batch in scene.media:
            if batch.retrieved_at_utc is None or batch.retrieved_at_utc > horizon:
                continue
            for element in self.assumptions.lab_elements:
                if element not in batch.loading_kg_per_kg:
                    continue
                records.append(
                    self.media_assay_record(batch, element, batch.retrieved_at_utc)
                )
        return records

    # -- context and housekeeping ------------------------------------------

    def environmental_records(
        self, scene: ScriptedScene, duration_s: float
    ) -> list[ObservationRecord]:
        """Context and housekeeping channels.

        These constrain water or sediment conditions and instrument health only.
        They are never converted into a Pb or Hg concentration anywhere in this
        package, and ``tests/observations`` asserts that removing all of them
        leaves the metal-bearing record set unchanged.
        """
        records: list[ObservationRecord] = []
        stations = self._stations("environmental")
        sigma_rel = self.config.environmental_relative_noise
        for moment in self.schedule(self.config.environmental_period_s, duration_s):
            for station in stations:
                sample = scene.environment_at(station.station_id, moment)
                for parameter, channel in CONTEXT_CHANNELS.items():
                    if parameter not in sample.values:
                        continue
                    self.reading_rng("environment", moment, station.station_id, parameter)
                    noise = float(self._rng.normal(0.0, sigma_rel))
                    true_value = float(sample.values[parameter])
                    reported = true_value * (1.0 + noise)
                    sensor_id = f"{channel.sensor_prefix}_{station.station_id}"
                    payload = self.base_payload(station)
                    payload.update(
                        {
                            "record_id": self.next_id(),
                            "sensor_id": sensor_id,
                            "observed_at_utc": format_utc(moment),
                            "available_at_utc": format_utc(moment),
                            "parameter": parameter,
                            "quantity_kind": channel.quantity_kind.value,
                            "unit": channel.unit,
                            "matrix": channel.matrix.value,
                            "fraction": Fraction.NOT_APPLICABLE.value,
                            "acquisition_kind": AcquisitionKind.IN_SITU_SENSOR.value,
                            "method_id": METHOD_IDS[channel.method_key],
                            "calibration_id": "CAL_SIM_V1",
                            "data_origin": DataOrigin.SENSOR.value,
                            "value": float(reported),
                            "uncertainty_std": abs(float(true_value * sigma_rel)),
                            "qualifier": Qualifier.QUANTIFIED.value,
                            "quality_flag": int(QualityFlag.PASSED),
                            "source_ref": (
                                "synthetic_demo context channel; ASSUMPTION sigma_rel="
                                f"{sigma_rel}. Constrains conditions or instrument "
                                "health only, never a metal concentration"
                            ),
                        }
                    )
                    if self.in_dropout(moment) and channel.matrix is not Matrix.INSTRUMENT:
                        payload.update(self.missing("simulated sensor dropout window"))
                    records.append(self.build(payload))
        return records

    # -- entry point --------------------------------------------------------

    def generate(
        self,
        scene: ScriptedScene,
        duration_s: float,
        *,
        include_environmental: bool = True,
        include_dgt: bool = True,
        include_condition: bool = True,
    ) -> list[ObservationRecord]:
        """Generate the whole stream, sorted by availability then observation.

        ``include_condition`` pulls in the mat-condition channels.  The import is
        deliberately deferred: ``condition`` imports the record primitives from
        this module, so a module-level import here would be circular.
        """
        records: list[ObservationRecord] = []
        records.extend(self.porewater_records(scene, duration_s))
        records.extend(self.bottom_water_records(scene, duration_s))
        records.extend(self.benthic_chamber_records(scene, duration_s))
        if include_dgt:
            records.extend(self.dgt_records(scene, duration_s))
        records.extend(self.retrieved_media_records(scene, duration_s))
        if include_environmental:
            records.extend(self.environmental_records(scene, duration_s))
        if include_condition:
            from .condition import MatConditionGenerator

            condition = MatConditionGenerator(
                self.config,
                seed=self.seed + 1,
                start_utc=self.start_utc,
                fast_validation=self.fast_validation,
            )
            condition._window_start_s = self._window_start_s
            condition._window_lookback_s = self._window_lookback_s
            records.extend(condition.generate(scene, duration_s))
        records.sort(
            key=lambda record: (
                record.available_at_utc,
                record.observed_at_utc,
                record.record_id,
            )
        )
        return records

    def generate_window(
        self, scene: ScriptedScene, start_s: float, end_s: float, **include_channels
    ) -> list[ObservationRecord]:
        """Emit readings completed in ``(start_s, end_s]`` on one global clock.

        The first window includes time zero. ``scene`` must cover earlier
        exposure starts, including chamber/DGT deployments crossing the left
        boundary. Laboratory records are emitted when sampled, retaining their
        future availability time for the controller's separate time gate.
        """
        if start_s < 0.0 or end_s < start_s:
            raise ValueError("observation window must satisfy 0 <= start <= end")
        self._window_start_s = start_s
        self._window_lookback_s = max(
            self.assumptions.chamber_deployment_s, self.config.dgt_exposure_s
        )
        try:
            records = self.generate(scene, end_s, **include_channels)
        finally:
            self._window_start_s = 0.0
            self._window_lookback_s = 0.0
        return [record for record in records if (
            (self.elapsed_s(record.observed_at_utc) > start_s
             or (start_s == 0.0 and record.observed_at_utc == self.start_utc))
            and self.elapsed_s(record.observed_at_utc) <= end_s
        )]


# ---------------------------------------------------------------------------
# Scene builders
# ---------------------------------------------------------------------------

#: Default context values.  Every one is an ASSUMPTION for a demonstration.
DEFAULT_ENVIRONMENT: Mapping[str, float] = {
    Parameter.TEMPERATURE.value: 14.5,
    Parameter.SEDIMENT_TEMPERATURE.value: 12.8,
    Parameter.CONDUCTIVITY.value: 52.1,
    Parameter.SALINITY.value: 34.9,
    Parameter.PH.value: 8.05,
    Parameter.TURBIDITY.value: 8.4,
    Parameter.DISSOLVED_OXYGEN.value: 7.2,
    Parameter.REDOX_POTENTIAL.value: -185.0,
    Parameter.SULFIDE.value: 1.4,
    Parameter.CURRENT_EAST.value: 0.12,
    Parameter.CURRENT_NORTH.value: -0.004,
    Parameter.SEEPAGE_VELOCITY.value: 95.0,  # cm/yr, about 3e-8 m/s
    Parameter.BATTERY_VOLTAGE.value: 11.6,
}


def _environment_series(
    start_utc: datetime,
    duration_s: float,
    step_s: float,
    values: Mapping[str, float],
) -> list[EnvironmentSample]:
    count = int(math.floor(duration_s / step_s)) + 1
    return [
        EnvironmentSample(
            time_utc=start_utc + timedelta(seconds=index * step_s),
            values=dict(values),
        )
        for index in range(count)
    ]


def constant_mat_scene(
    start_utc: datetime,
    duration_s: float,
    *,
    step_s: float = _SECONDS_PER_DAY,
    tile_ids: Sequence[str] = ("tile_0_0", "tile_1_1", "tile_2_2"),
    sediment_porewater_kg_per_m3: Mapping[str, float] | None = None,
    bottom_water_kg_per_m3: Mapping[str, float] | None = None,
    flux_out_kg_per_m2_per_s: Mapping[str, float] | None = None,
    bare_flux_kg_per_m2_per_s: Mapping[str, float] | None = None,
    sorbed_kg_per_kg: Mapping[str, float] | None = None,
    media_id: str = "media_A0",
    environment: Mapping[str, float] | None = None,
    environment_station_id: str = "ST_ENV",
) -> ScriptedScene:
    """A flat scene: every tile in the same, unchanging state.

    Used for contract-shaped tests where the interesting thing is the record,
    not the physics.
    """
    driving = dict(sediment_porewater_kg_per_m3 or {"Pb": 1.0e-3, "Hg": 8.0e-6})
    water = dict(bottom_water_kg_per_m3 or {"Pb": 1.0e-8, "Hg": 2.0e-10})
    bare = dict(bare_flux_kg_per_m2_per_s or {"Pb": 5.3e-10, "Hg": 4.24e-12})
    flux = dict(
        flux_out_kg_per_m2_per_s
        or {element: 0.005 * value for element, value in bare.items()}
    )
    sorbed = dict(sorbed_kg_per_kg or {"Pb": 1.0e-4, "Hg": 2.0e-5})
    count = int(math.floor(duration_s / step_s)) + 1
    samples: dict[str, list[MatStateSample]] = {}
    for tile_id in tile_ids:
        series: list[MatStateSample] = []
        for index in range(count):
            moment = start_utc + timedelta(seconds=index * step_s)
            series.append(
                MatStateSample(
                    time_utc=moment,
                    sediment_porewater_kg_per_m3=dict(driving),
                    bottom_water_kg_per_m3=dict(water),
                    flux_out_kg_per_m2_per_s=dict(flux),
                    bare_flux_kg_per_m2_per_s=dict(bare),
                    mat_porewater_kg_per_m3={
                        element: 0.2 * value for element, value in driving.items()
                    },
                    sorbed_kg_per_kg=dict(sorbed),
                    media_id=media_id,
                    differential_head_pa=40.0,
                )
            )
        samples[tile_id] = series
    environment_values = dict(
        DEFAULT_ENVIRONMENT if environment is None else environment
    )
    return ScriptedScene(
        tile_samples=samples,
        environment_samples={
            environment_station_id: _environment_series(
                start_utc, duration_s, step_s, environment_values
            )
        },
        media=tuple(
            MediaBatch(
                media_id=media_id,
                tile_id=tile_id,
                installed_at_utc=start_utc,
                loading_kg_per_kg=dict(sorbed),
            )
            for tile_id in tile_ids
        ),
    )


def ramp_mat_scene(
    start_utc: datetime,
    duration_s: float,
    *,
    step_s: float = _SECONDS_PER_DAY,
    tile_ids: Sequence[str] = ("tile_0_0",),
    start_bottom_water_kg_per_m3: Mapping[str, float],
    end_bottom_water_kg_per_m3: Mapping[str, float],
    start_sediment_porewater_kg_per_m3: Mapping[str, float] | None = None,
    end_sediment_porewater_kg_per_m3: Mapping[str, float] | None = None,
    bare_flux_kg_per_m2_per_s: Mapping[str, float] | None = None,
    flux_ratio: float = 0.02,
    media_id: str = "media_A0",
    environment: Mapping[str, float] | None = None,
    environment_station_id: str = "ST_ENV",
) -> ScriptedScene:
    """A linear ramp between two states.

    Its purpose is to cross detection and range thresholds on purpose, so the
    whole censoring ladder is exercised rather than left to chance: below LOD,
    between LOD and LOQ, quantified, and above range all occur in one series.
    """
    driving_start = dict(
        start_sediment_porewater_kg_per_m3 or {"Pb": 1.0e-3, "Hg": 8.0e-6}
    )
    driving_end = dict(end_sediment_porewater_kg_per_m3 or driving_start)
    water_start = dict(start_bottom_water_kg_per_m3)
    water_end = dict(end_bottom_water_kg_per_m3)
    bare = dict(bare_flux_kg_per_m2_per_s or {"Pb": 5.3e-10, "Hg": 4.24e-12})
    count = int(math.floor(duration_s / step_s)) + 1
    elements = set(water_start) | set(water_end) | set(driving_start)

    samples: dict[str, list[MatStateSample]] = {}
    for tile_id in tile_ids:
        series: list[MatStateSample] = []
        for index in range(count):
            weight = index / max(count - 1, 1)
            moment = start_utc + timedelta(seconds=index * step_s)
            water = {
                element: (1.0 - weight) * float(water_start.get(element, 0.0))
                + weight * float(water_end.get(element, water_start.get(element, 0.0)))
                for element in elements
            }
            driving = {
                element: (1.0 - weight) * float(driving_start.get(element, 0.0))
                + weight
                * float(driving_end.get(element, driving_start.get(element, 0.0)))
                for element in elements
            }
            series.append(
                MatStateSample(
                    time_utc=moment,
                    sediment_porewater_kg_per_m3=driving,
                    bottom_water_kg_per_m3=water,
                    flux_out_kg_per_m2_per_s={
                        element: flux_ratio * value for element, value in bare.items()
                    },
                    bare_flux_kg_per_m2_per_s=dict(bare),
                    mat_porewater_kg_per_m3={
                        element: 0.2 * value for element, value in driving.items()
                    },
                    sorbed_kg_per_kg={"Pb": 1.0e-4, "Hg": 2.0e-5},
                    media_id=media_id,
                    differential_head_pa=40.0,
                )
            )
        samples[tile_id] = series
    environment_values = dict(
        DEFAULT_ENVIRONMENT if environment is None else environment
    )
    return ScriptedScene(
        tile_samples=samples,
        environment_samples={
            environment_station_id: _environment_series(
                start_utc, duration_s, step_s, environment_values
            )
        },
        media=tuple(
            MediaBatch(
                media_id=media_id, tile_id=tile_id, installed_at_utc=start_utc,
                loading_kg_per_kg={"Pb": 1.0e-4, "Hg": 2.0e-5},
            )
            for tile_id in tile_ids
        ),
        notes="linear ramp; built to cross the detection and range thresholds",
    )


@dataclass(frozen=True, slots=True)
class MediaReplacement:
    """A scheduled media replacement in one tile."""

    start_s: float
    tile_id: str
    new_media_id: str


@dataclass(frozen=True, slots=True)
class MatHistorySpec:
    """Parameters of the analytic stand-in history.

    LABELLED_STUB.  Every number here is an ASSUMPTION chosen so a multi-year
    demonstration shows loading, breakthrough, fouling and physical failure.  It
    is **not** the 1-D reactive layer: that lives on ``feat/reactive-layer``.
    When the layer timeline exists, :func:`scene_from_layer_history` replaces
    this function without changing the generator.
    """

    sediment_porewater_kg_per_m3: Mapping[str, float] = field(
        default_factory=lambda: {"Pb": 1.0e-3, "Hg": 8.0e-6}
    )
    #: Background bottom water away from the hotspot [kg m^-3].
    bottom_water_kg_per_m3: Mapping[str, float] = field(
        default_factory=lambda: {"Pb": 1.5e-8, "Hg": 3.0e-10}
    )
    #: Near-bed enrichment per unit residual flux [s m^-1], so the bottom-water
    #: channel responds to the mat state instead of sitting at background.
    #: ASSUMPTION standing in for the dilution the 2-D coastal model computes;
    #: it is not a mixing-length measurement.
    bottom_water_enrichment_s_per_m: float = 5.0e3
    #: J_bare = (v + k_film) * (C_sed - C_water), MODEL_SPEC section 3.
    seepage_velocity_m_per_s: float = 3.0e-8
    film_transfer_m_per_s: float = 5.0e-7
    #: Fresh and saturated flux ratios J_out / J_bare (MODEL_SPEC section 3:
    #: a saturated mat still attenuates as a diffusive barrier).
    fresh_flux_ratio: float = 0.005
    saturated_flux_ratio: float = 0.060
    breakthrough_s: float = 3.086 * _SECONDS_PER_YEAR
    breakthrough_width_s: float = 0.5 * _SECONDS_PER_YEAR
    #: Operating capacity per element [kg kg^-1].
    q_max_kg_per_kg: Mapping[str, float] = field(
        default_factory=lambda: {"Pb": 1.0e-3, "Hg": 4.0e-4}
    )
    #: Partition slope, used only to report an equilibrium mat porewater.
    kd_m3_per_kg: Mapping[str, float] = field(
        default_factory=lambda: {"Pb": 5.0, "Hg": 12.0}
    )
    fouling_growth_per_s: float = 5.0e-9
    edge_leakage_fraction: float = 0.02
    fouling_bypass_coupling: float = 0.35
    burial_resistance_s_per_m: float = 2.0e8
    #: Head loss across a clean and a fully fouled layer [Pa].  ASSUMPTION.
    clean_head_pa: float = 30.0
    fouled_head_pa: float = 220.0


def synthetic_mat_history(
    start_utc: datetime,
    duration_s: float,
    *,
    step_s: float = _SECONDS_PER_DAY,
    tile_ids: Sequence[str] = ("tile_0_0", "tile_1_1", "tile_2_2"),
    spec: MatHistorySpec | None = None,
    events: Sequence[DegradationEvent] = (),
    replacements: Sequence[MediaReplacement] = (),
    initial_media_id: str = "media_A0",
    environment: Mapping[str, float] | None = None,
    environment_station_id: str = "ST_ENV",
    tile_positions: Mapping[str, tuple[float, float]] | None = None,
) -> ScriptedScene:
    """A multi-year analytic stand-in for the reactive-layer timeline.

    LABELLED_STUB: this is not the 1-D layer solve.  It reproduces the shape the
    layer is documented to have (MODEL_SPEC section 3 and the refactor plan's
    probe 5): loading saturates, the flux ratio rises from about 0.5 % to about
    6 % through breakthrough, fouling grows, burial *reduces* the apparent flux,
    a displaced tile emits the bare flux, and a torn share emits the bare flux
    in proportion to the damage.

    The four degradation modes stay independent here exactly as they do in the
    model: a scheduled displacement never touches the chemistry.
    """
    resolved = spec or MatHistorySpec()
    driving = dict(resolved.sediment_porewater_kg_per_m3)
    water = dict(resolved.bottom_water_kg_per_m3)
    bare = {
        element: (resolved.seepage_velocity_m_per_s + resolved.film_transfer_m_per_s)
        * max(value - water.get(element, 0.0), 0.0)
        for element, value in driving.items()
    }
    g_top = resolved.film_transfer_m_per_s
    count = int(math.floor(duration_s / step_s)) + 1

    batches: dict[tuple[str, str], MediaBatch] = {
        (tile, initial_media_id): MediaBatch(
            media_id=initial_media_id,
            tile_id=tile,
            installed_at_utc=start_utc,
            loading_kg_per_kg={},
        )
        for tile in tile_ids
    }

    samples: dict[str, list[MatStateSample]] = {tile: [] for tile in tile_ids}
    for tile_id in tile_ids:
        tile_events = [event for event in events if event.tile_id == tile_id]
        tile_replacements = sorted(
            (item for item in replacements if item.tile_id == tile_id),
            key=lambda item: item.start_s,
        )
        loading_offset_s = 0.0
        current_media = initial_media_id
        for index in range(count):
            elapsed = index * step_s
            moment = start_utc + timedelta(seconds=elapsed)

            for item in tile_replacements:
                if elapsed >= item.start_s and current_media != item.new_media_id:
                    retired = batches[(tile_id, current_media)]
                    batches[(tile_id, current_media)] = replace(
                        retired,
                        retrieved_at_utc=moment,
                        loading_kg_per_kg=_loading_at(
                            resolved, elapsed - loading_offset_s
                        ),
                    )
                    current_media = item.new_media_id
                    loading_offset_s = elapsed
                    batches[(tile_id, current_media)] = MediaBatch(
                        media_id=current_media,
                        tile_id=tile_id,
                        installed_at_utc=moment,
                        loading_kg_per_kg={},
                    )

            age_s = elapsed - loading_offset_s
            loading = _loading_at(resolved, age_s)
            saturation = _breakthrough_fraction(resolved, age_s)
            fouling = min(1.0, resolved.fouling_growth_per_s * elapsed)
            integrity = 1.0
            burial = 0.0
            displacement = 0.0
            displaced = False
            for event in tile_events:
                if elapsed < event.start_s:
                    continue
                if event.mode == "local_damage":
                    integrity = min(integrity, max(0.0, 1.0 - event.magnitude))
                elif event.mode == "displacement":
                    if event.magnitude >= 1.0:
                        displaced = True
                        displacement = max(displacement, 5.0)
                    else:
                        displacement = max(displacement, event.magnitude)
                elif event.mode == "burial":
                    burial = max(burial, event.magnitude)
                elif event.mode == "fouling":
                    fouling = min(1.0, fouling + event.magnitude)

            ratio = resolved.fresh_flux_ratio + (
                resolved.saturated_flux_ratio - resolved.fresh_flux_ratio
            ) * saturation
            # Fouling lowers the flux through the layer but pushes flow around
            # the tile edge, so pore blockage is never a free improvement.
            layer_ratio = ratio * (1.0 - 0.3 * fouling)
            bypass = min(
                1.0,
                resolved.edge_leakage_fraction
                + resolved.fouling_bypass_coupling * fouling,
            )
            effective_ratio = (1.0 - bypass) * layer_ratio + bypass * 1.0
            effective_ratio = integrity * effective_ratio + (1.0 - integrity) * 1.0
            if displaced:
                effective_ratio = 1.0
            elif burial > 0.0:
                # Burial covers the whole footprint, edge leakage included, so
                # the resistance applies to everything leaving the tile.  This
                # is the masquerade: the apparent flux falls while the mat is
                # doing no more work than before (MODEL_SPEC section 4, mode 3).
                g_buried = 1.0 / (
                    1.0 / g_top + resolved.burial_resistance_s_per_m * burial
                )
                effective_ratio *= g_buried / g_top

            coverage = 0.0 if displaced else max(0.0, min(1.0, integrity))
            flux_out = {
                element: effective_ratio * value for element, value in bare.items()
            }
            # The water above the mat carries the residual flux, so this channel
            # responds to the mat state instead of sitting at background.
            near_bed = {
                element: water.get(element, 0.0)
                + resolved.bottom_water_enrichment_s_per_m * flux
                for element, flux in flux_out.items()
            }
            samples[tile_id].append(
                MatStateSample(
                    time_utc=moment,
                    sediment_porewater_kg_per_m3=dict(driving),
                    bottom_water_kg_per_m3=near_bed,
                    flux_out_kg_per_m2_per_s=flux_out,
                    bare_flux_kg_per_m2_per_s=dict(bare),
                    mat_porewater_kg_per_m3={
                        element: loading.get(element, 0.0)
                        / max(resolved.kd_m3_per_kg.get(element, 1.0), 1e-30)
                        for element in driving
                    },
                    sorbed_kg_per_kg=dict(loading),
                    media_id=current_media,
                    fouling_index=fouling,
                    integrity_index=integrity,
                    burial_depth_m=burial,
                    displacement_m=displacement,
                    displaced=displaced,
                    coverage_fraction=coverage,
                    differential_head_pa=(
                        resolved.clean_head_pa
                        + (resolved.fouled_head_pa - resolved.clean_head_pa) * fouling
                    ),
                    tilt_deg=2.0 if displaced else 0.5,
                    damage_class=_damage_class(integrity, displaced),
                )
            )
        # The batch still in the water at the end of the run keeps its loading.
        batches[(tile_id, current_media)] = replace(
            batches[(tile_id, current_media)],
            loading_kg_per_kg=_loading_at(resolved, (count - 1) * step_s - loading_offset_s),
        )

    environment_values = dict(
        DEFAULT_ENVIRONMENT if environment is None else environment
    )
    return ScriptedScene(
        tile_samples=samples,
        environment_samples={
            environment_station_id: _environment_series(
                start_utc, duration_s, step_s, environment_values
            )
        },
        media=tuple(batches.values()),
        tile_positions=dict(tile_positions or {}),
        notes=(
            "LABELLED_STUB analytic stand-in for the reactive-layer timeline; "
            "shape only, not a 1-D solve"
        ),
    )


def _loading_at(spec: MatHistorySpec, age_s: float) -> dict[str, float]:
    """Sorbed loading of a batch of the given age.  ASSUMPTION: 1 - exp(-t/tau)."""
    tau = max(spec.breakthrough_s / 1.2, 1.0)
    fraction = 1.0 - math.exp(-max(age_s, 0.0) / tau)
    return {
        element: fraction * value for element, value in spec.q_max_kg_per_kg.items()
    }


def _breakthrough_fraction(spec: MatHistorySpec, age_s: float) -> float:
    """Logistic breakthrough progress in ``[0, 1]``.  ASSUMPTION."""
    width = max(spec.breakthrough_width_s, 1.0)
    return 1.0 / (1.0 + math.exp(-(max(age_s, 0.0) - spec.breakthrough_s) / width))


def _damage_class(integrity: float, displaced: bool) -> str:
    if displaced:
        return "lost"
    if integrity >= 0.99:
        return "intact"
    if integrity >= 0.85:
        return "abraded"
    if integrity >= 0.5:
        return "punctured"
    return "torn"


def scene_from_layer_history(
    history: Mapping[str, Sequence[tuple[datetime, LayerStep]]],
    *,
    environment_samples: Mapping[str, Sequence[EnvironmentSample]] | None = None,
    media: Sequence[MediaBatch] = (),
    tile_positions: Mapping[str, tuple[float, float]] | None = None,
) -> ScriptedScene:
    """Build a scene from a real reactive-layer timeline.

    This is the integration seam with ``feat/reactive-layer``: it reads only
    frozen contract types (:class:`~reactive_seabed_mat.contracts.LayerStep` and
    :class:`~reactive_seabed_mat.contracts.MatTileState`), so when the layer
    branch lands the generator needs no change at all.

    A step without its :class:`~reactive_seabed_mat.contracts.SeabedExchange` is
    rejected rather than guessed: without it there is no driving concentration
    and no bottom-water concentration, and inventing them would be exactly the
    kind of silent assumption this repository is built to avoid.
    """
    tile_samples: dict[str, list[MatStateSample]] = {}
    resolved_positions = dict(tile_positions or {})
    for tile_id, series in history.items():
        samples: list[MatStateSample] = []
        for moment, step in series:
            if step.exchange is None:
                raise ValueError(
                    f"tile {tile_id!r} at {moment.isoformat()}: LayerStep without a "
                    "SeabedExchange carries no driving or bottom-water concentration; "
                    "it is rejected rather than guessed"
                )
            state = step.new_state
            resolved_positions.setdefault(tile_id, (
                state.geometry.x_m + 0.5 * state.geometry.width_m,
                state.geometry.y_m + 0.5 * state.geometry.length_m,
            ))
            samples.append(
                MatStateSample(
                    time_utc=moment,
                    sediment_porewater_kg_per_m3=dict(
                        step.exchange.sediment_porewater_kg_per_m3
                    ),
                    bottom_water_kg_per_m3=dict(step.exchange.bottom_water_kg_per_m3),
                    flux_out_kg_per_m2_per_s=dict(step.flux_out_kg_per_m2_per_s),
                    bare_flux_kg_per_m2_per_s=dict(
                        step.exchange.bare_flux_kg_per_m2_per_s
                    ),
                    mat_porewater_kg_per_m3={
                        element: float(np.mean(profile))
                        for element, profile in state.porewater_kg_per_m3.items()
                    },
                    sorbed_kg_per_kg={
                        element: float(np.mean(profile))
                        for element, profile in state.sorbed_kg_per_kg.items()
                    },
                    media_id=state.media_id,
                    fouling_index=state.fouling_index,
                    integrity_index=state.integrity_index,
                    burial_depth_m=state.burial_depth_m,
                    displacement_m=state.displacement_m,
                    displaced=state.displaced,
                    coverage_fraction=state.coverage_fraction,
                    damage_class=_damage_class(state.integrity_index, state.displaced),
                )
            )
        tile_samples[tile_id] = samples
    return ScriptedScene(
        tile_samples=tile_samples,
        environment_samples=dict(environment_samples or {}),
        media=tuple(media),
        tile_positions=resolved_positions,
        notes="scene built from a reactive-layer timeline",
    )
