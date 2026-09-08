"""Frozen module boundary for the marine reactive-mesh demonstrator.

Coordinator-owned.  Branch agents (``feat/mesh-care``, ``feat/coastal-2d``,
``feat/feedback``, ``feat/presentation``, ``feat/ml-extension``) import these
types and implement the functions declared at the bottom of this file.  They
must **not** edit this module; additions are proposed in the branch handoff.

The typed objects here are the exact realisation of
``contracts/DATA_CONTRACT.md`` section 2 ("Module boundary to freeze").

Three states are kept apart everywhere in the code base
(:class:`StateOrigin`):

``TRUE_SIMULATED``
    the hidden simulator state; written only under ``results/<run>/truth/``.
``MEASURED``
    observation records, with censoring, QC flags and laboratory latency.
``ESTIMATED``
    what the operator-facing estimator reconstructs from measurements alone.

The estimator and the recommendation policy may read ``MEASURED`` and their own
``ESTIMATED`` history.  They may never read ``TRUE_SIMULATED``.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Mapping, Protocol, Sequence

import numpy as np

CONTRACT_VERSION = "0.1.0-frozen"

__all__ = [
    "CONTRACT_VERSION",
    "Element",
    "StateOrigin",
    "ProvenanceLabel",
    "Parameter",
    "Matrix",
    "Fraction",
    "AcquisitionKind",
    "Qualifier",
    "QualityFlag",
    "DataOrigin",
    "ActionKind",
    "AmbiguityFlag",
    "ObservationRecord",
    "GridSpec",
    "FieldState",
    "Forcing",
    "SourceTerm",
    "TransportStep",
    "MaterialParameters",
    "PanelGeometry",
    "PanelState",
    "ContactBatch",
    "PanelStep",
    "ServiceEvent",
    "MassLedger",
    "OperatorKnownPanel",
    "ModelHistory",
    "EstimateSnapshot",
    "Recommendation",
    "ActionEvent",
    "AdvancePanel",
    "TransportStepFn",
    "BuildContacts",
    "ApplyTransfers",
    "ObservationsAvailable",
    "UpdateEstimate",
    "Recommend",
]


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Element(str, enum.Enum):
    """Target elements.  Pb is the primary channel; Hg is optional and always
    carries its own parameter set and its own allocated material mass."""

    PB = "Pb"
    HG = "Hg"


class StateOrigin(str, enum.Enum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    TRUE_SIMULATED = "true_simulated"


class ProvenanceLabel(str, enum.Enum):
    """Mandatory label for every number that reaches a chart or an export."""

    MEASUREMENT = "measurement"
    EXTERNAL_MODEL = "external_model"
    LITERATURE = "literature"
    ASSUMPTION = "assumption"
    SYNTHETIC_DEMO = "synthetic_demo"


class Parameter(str, enum.Enum):
    PB = "Pb"
    HG = "Hg"
    CURRENT_EAST = "current_east"
    CURRENT_NORTH = "current_north"
    TEMPERATURE = "temperature"
    CONDUCTIVITY = "conductivity"
    SALINITY = "salinity"
    PH = "pH"
    TURBIDITY = "turbidity"
    MESH_TILT = "mesh_tilt"
    BATTERY_VOLTAGE = "battery_voltage"


#: Parameters that carry metal-concentration information.  Everything else is
#: context / QC and must never be converted into a Pb or Hg estimate.
METAL_PARAMETERS: frozenset[Parameter] = frozenset({Parameter.PB, Parameter.HG})

#: Ordinary water-quality proxies.  Explicitly listed so the estimator can
#: assert it is not deriving chemistry from them.
CONTEXT_PARAMETERS: frozenset[Parameter] = frozenset(
    {
        Parameter.TEMPERATURE,
        Parameter.CONDUCTIVITY,
        Parameter.SALINITY,
        Parameter.PH,
        Parameter.TURBIDITY,
    }
)


class Matrix(str, enum.Enum):
    SEAWATER = "seawater"
    POREWATER = "porewater"
    SEDIMENT = "sediment"
    SORBENT = "sorbent"
    INSTRUMENT = "instrument"


class Fraction(str, enum.Enum):
    NOT_APPLICABLE = "not_applicable"
    LABILE = "labile"
    DISSOLVED_FILTERED = "dissolved_filtered"
    TOTAL_RECOVERABLE = "total_recoverable"
    DISSOLVED_INORGANIC = "dissolved_inorganic"
    METHYLMERCURY = "methylmercury"
    SORBED_TOTAL = "sorbed_total"


class AcquisitionKind(str, enum.Enum):
    IN_SITU_SENSOR = "in_situ_sensor"
    GRAB_SAMPLE = "grab_sample"
    PASSIVE_SAMPLER = "passive_sampler"
    MEDIA_ASSAY = "media_assay"
    MANUAL = "manual"


class Qualifier(str, enum.Enum):
    QUANTIFIED = "quantified"
    BELOW_LOD = "below_lod"
    BELOW_LOQ = "below_loq"
    MISSING = "missing"


class QualityFlag(enum.IntEnum):
    """QARTOD-inspired flags [S23-S24].  Not an official QARTOD certification."""

    PASSED = 1
    NOT_EVALUATED = 2
    SUSPECT = 3
    FAILED = 4
    MISSING = 9


class DataOrigin(str, enum.Enum):
    SYNTHETIC = "synthetic"
    SENSOR = "sensor"
    LABORATORY = "laboratory"
    EXTERNAL_MODEL = "external_model"
    DERIVED = "derived"


class ActionKind(str, enum.Enum):
    CONTINUE = "CONTINUE"
    REQUEST_CHEMICAL_SAMPLE = "REQUEST_CHEMICAL_SAMPLE"
    CHECK_SENSOR = "CHECK_SENSOR"
    INSPECT_MESH = "INSPECT_MESH"
    PLAN_REPLACEMENT = "PLAN_REPLACEMENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class AmbiguityFlag(str, enum.Enum):
    """Competing explanations the estimator is allowed to leave unresolved."""

    SOURCE_INCREASE = "source_increase"
    PLUME_SHIFT = "plume_shift"
    SATURATION = "saturation"
    FOULING = "fouling"
    SENSOR_DRIFT = "sensor_drift"
    SENSOR_FAILURE = "sensor_failure"
    INSUFFICIENT_DATA = "insufficient_data"


# ---------------------------------------------------------------------------
# Observation record
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ObservationRecord:
    """One measured parameter, long form.  Mirrors ``observation.schema.json``.

    ``value`` is in ``unit`` as reported; conversion to SI happens in the
    observation operator, never implicitly here.  A non-detect carries
    ``value=None`` with a finite censoring interval: it is a bound, not a zero.
    """

    record_id: str
    station_id: str
    observed_at_utc: datetime
    available_at_utc: datetime
    parameter: Parameter
    unit: str
    matrix: Matrix
    fraction: Fraction
    acquisition_kind: AcquisitionKind
    qualifier: Qualifier
    quality_flag: QualityFlag
    method_id: str
    data_origin: DataOrigin

    sensor_id: str | None = None
    sample_id: str | None = None
    media_id: str | None = None
    sampling_start_utc: datetime | None = None
    sampling_end_utc: datetime | None = None
    value: float | None = None
    uncertainty_std: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    calibration_id: str | None = None
    source_ref: str | None = None
    x_m: float | None = None
    y_m: float | None = None
    depth_m: float | None = None
    crs: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_metal(self) -> bool:
        return self.parameter in METAL_PARAMETERS

    @property
    def is_censored(self) -> bool:
        return self.qualifier in (Qualifier.BELOW_LOD, Qualifier.BELOW_LOQ)

    @property
    def carries_chemical_information(self) -> bool:
        """A missing record carries none; a non-detect carries a bound."""
        return self.is_metal and self.qualifier is not Qualifier.MISSING


# ---------------------------------------------------------------------------
# Macro (transport) side
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GridSpec:
    """Uniform metric grid.  ``crs`` is the metric computation CRS; latitude /
    longitude is a display concern only."""

    nx: int
    ny: int
    dx_m: float
    dy_m: float
    mixing_depth_m: float
    crs: str = "LOCAL_METRIC"
    origin_x_m: float = 0.0
    origin_y_m: float = 0.0

    @property
    def cell_area_m2(self) -> float:
        return self.dx_m * self.dy_m

    @property
    def cell_volume_m3(self) -> float:
        return self.dx_m * self.dy_m * self.mixing_depth_m

    @property
    def n_cells(self) -> int:
        return self.nx * self.ny

    def cell_index(self, ix: int, iy: int) -> int:
        """Flat index in row-major order, identical to FiPy ``Grid2D`` order."""
        if not (0 <= ix < self.nx and 0 <= iy < self.ny):
            raise IndexError(f"cell ({ix},{iy}) outside {self.nx}x{self.ny} grid")
        return iy * self.nx + ix

    def cell_centre_m(self, ix: int, iy: int) -> tuple[float, float]:
        return (
            self.origin_x_m + (ix + 0.5) * self.dx_m,
            self.origin_y_m + (iy + 0.5) * self.dy_m,
        )

    def nearest_cell(self, x_m: float, y_m: float) -> tuple[int, int]:
        ix = int(np.clip((x_m - self.origin_x_m) // self.dx_m, 0, self.nx - 1))
        iy = int(np.clip((y_m - self.origin_y_m) // self.dy_m, 0, self.ny - 1))
        return ix, iy


@dataclass(frozen=True, slots=True)
class FieldState:
    """Dissolved concentration field per element.

    Arrays are ``(ny, nx)`` in kg m^-3; ``arr.reshape(-1)`` is FiPy cell order.
    ``land_mask`` marks no-flux cells (``True`` = land, no water, no transport).
    """

    grid: GridSpec
    time_utc: datetime
    concentration_kg_per_m3: Mapping[str, np.ndarray]
    land_mask: np.ndarray
    origin: StateOrigin = StateOrigin.TRUE_SIMULATED

    def water_mass_kg(self, element: Element | str) -> float:
        key = element.value if isinstance(element, Element) else element
        c = self.concentration_kg_per_m3[key]
        return float(np.sum(c[~self.land_mask]) * self.grid.cell_volume_m3)

    def with_concentration(
        self, concentration: Mapping[str, np.ndarray], time_utc: datetime | None = None
    ) -> "FieldState":
        return replace(
            self,
            concentration_kg_per_m3=dict(concentration),
            time_utc=self.time_utc if time_utc is None else time_utc,
        )


@dataclass(frozen=True, slots=True)
class Forcing:
    """Depth-averaged forcing for one step.

    ``u_east_m_per_s`` / ``v_north_m_per_s`` are ``(ny, nx)`` cell-centred
    velocities.  ``provenance`` records whether they are synthetic, an external
    model product, or an assumption.
    """

    time_utc: datetime
    u_east_m_per_s: np.ndarray
    v_north_m_per_s: np.ndarray
    diffusivity_m2_per_s: float
    provenance: ProvenanceLabel = ProvenanceLabel.SYNTHETIC_DEMO
    product_ref: str | None = None
    temporal_averaging: str = "instantaneous_synthetic"
    notes: str = ""


@dataclass(frozen=True, slots=True)
class SourceTerm:
    """A hypothetical release.  ``rate_kg_per_s`` is per element."""

    source_id: str
    x_m: float
    y_m: float
    rate_kg_per_s: Mapping[str, float]
    label: ProvenanceLabel = ProvenanceLabel.SYNTHETIC_DEMO
    description: str = "hypothetical source; not a located real hotspot"


@dataclass(frozen=True, slots=True)
class TransportStep:
    new_field: FieldState
    boundary_in_kg: Mapping[str, float]
    boundary_out_kg: Mapping[str, float]
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Micro (material) side
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MaterialParameters:
    """Reduced sorbent parameters for **one** element.

    ``kd_m3_per_kg``
        partition slope of the capped linear isotherm, q_eq = Kd * c (kg/kg).
    ``q_max_kg_per_kg``
        capacity cap of the isotherm (kg metal per kg of *allocated* sorbent).
    ``k_rate_per_s``
        first-order approach-to-equilibrium rate constant.
    ``allocation_fraction``
        share of the panel's sorbent mass assigned to this element.  The sum
        over elements must not exceed 1: mesh capacity is never double-counted.
    All values are synthetic demonstration parameters unless ``provenance``
    says otherwise; literature maxima are not operating capacities [S01, S04].
    """

    element: Element
    kd_m3_per_kg: float
    q_max_kg_per_kg: float
    k_rate_per_s: float
    allocation_fraction: float
    kd_interval: tuple[float, float] | None = None
    q_max_interval: tuple[float, float] | None = None
    k_rate_interval: tuple[float, float] | None = None
    fouling_rate_capacity: float = 0.0
    fouling_rate_kinetics: float = 1.0
    provenance: ProvenanceLabel = ProvenanceLabel.SYNTHETIC_DEMO
    source_ref: str = "assumed synthetic baseline; see docs/MODEL_SPEC.md"


@dataclass(frozen=True, slots=True)
class PanelGeometry:
    """Physical footprint of one retrievable panel."""

    width_m: float
    height_m: float
    x_m: float
    y_m: float
    #: Documented, uncertain fraction of the water passing the panel's frontal
    #: area that actually contacts reactive material.  Not a claim that every
    #: molecule in a grid cell passes through the panel.
    interception_efficiency: float = 0.5
    interception_interval: tuple[float, float] | None = None

    @property
    def frontal_area_m2(self) -> float:
        return self.width_m * self.height_m


@dataclass(frozen=True, slots=True)
class PanelState:
    """Auditable per-panel state.  ``retained_kg`` never decreases silently."""

    panel_id: str
    media_id: str
    installed_at_utc: datetime
    sorbent_mass_kg: float
    geometry: PanelGeometry
    retained_kg: Mapping[str, float]
    fouling_fraction: float = 0.0
    active: bool = True
    service_count: int = 0

    def allocated_mass_kg(self, params: MaterialParameters) -> float:
        return self.sorbent_mass_kg * params.allocation_fraction

    def loading_kg_per_kg(self, params: MaterialParameters) -> float:
        allocated = self.allocated_mass_kg(params)
        if allocated <= 0.0:
            return 0.0
        return self.retained_kg.get(params.element.value, 0.0) / allocated

    def nominal_capacity_kg(self, params: MaterialParameters) -> float:
        return self.allocated_mass_kg(params) * params.q_max_kg_per_kg


@dataclass(frozen=True, slots=True)
class ContactBatch:
    """What one panel actually sees during one step.

    ``available_kg`` is the contaminant mass genuinely reachable in this step,
    already bounded by the water volume swept and by the grid-cell inventory.
    It is *not* the source's whole release.
    """

    panel_id: str
    time_utc: datetime
    dt_s: float
    concentration_kg_per_m3: Mapping[str, float]
    concentration_interpretation: str
    available_kg: Mapping[str, float]
    exchange_volume_m3: float
    exchange_is_measured: bool
    cell_indices: Sequence[int]
    cell_weights: Sequence[float]
    environment: Mapping[str, float] = field(default_factory=dict)
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PanelStep:
    new_state: PanelState
    uptake_kg_by_element: Mapping[str, float]
    release_kg_by_element: Mapping[str, float]
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    #: The batch this step answered.  ``apply_transfers`` uses its
    #: ``cell_indices`` / ``cell_weights`` to put the mass back exactly where it
    #: came from, without needing a second argument.
    contact_batch: ContactBatch | None = None


@dataclass(frozen=True, slots=True)
class ServiceEvent:
    """A simulated maintenance action that changed a panel."""

    event_id: str
    time_utc: datetime
    panel_id: str
    kind: str
    old_media_id: str | None
    new_media_id: str | None
    retrieved_kg: Mapping[str, float] = field(default_factory=dict)
    cost_eur: float = 0.0
    triggered_by_recommendation_id: str | None = None
    execution_mode: str = "simulation_only"


@dataclass(frozen=True, slots=True)
class MassLedger:
    """Per-element mass bookkeeping for a whole run.

    Invariant checked in the tests::

        initial_water + emitted + boundary_in
          == in_water + in_active_mesh + in_retrieved_media + boundary_out
             + numerical_correction

    ``numerical_correction`` records any clipping the solver had to apply.  It
    is reported, never hidden.
    """

    element: str
    initial_water_kg: float = 0.0
    emitted_kg: float = 0.0
    boundary_in_kg: float = 0.0
    in_water_kg: float = 0.0
    in_active_mesh_kg: float = 0.0
    in_retrieved_media_kg: float = 0.0
    boundary_out_kg: float = 0.0
    numerical_correction_kg: float = 0.0

    @property
    def supplied_kg(self) -> float:
        return self.initial_water_kg + self.emitted_kg + self.boundary_in_kg

    @property
    def accounted_kg(self) -> float:
        return (
            self.in_water_kg
            + self.in_active_mesh_kg
            + self.in_retrieved_media_kg
            + self.boundary_out_kg
            + self.numerical_correction_kg
        )

    @property
    def imbalance_kg(self) -> float:
        return self.accounted_kg - self.supplied_kg

    @property
    def relative_imbalance(self) -> float:
        denominator = max(abs(self.supplied_kg), 1e-30)
        return self.imbalance_kg / denominator


# ---------------------------------------------------------------------------
# Estimation and decision side
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class OperatorKnownPanel:
    """What an operator legitimately knows without measuring anything.

    Deployment paperwork, essentially: which panel, which media batch, when it
    went in, how much sorbent it holds, its geometry, and which service actions
    were actually accepted.  It carries **no** retained mass and no fouling
    state -- those are exactly what has to be estimated.
    """

    panel_id: str
    media_id: str
    installed_at_utc: datetime
    sorbent_mass_kg: float
    geometry: PanelGeometry
    accepted_service_events: Sequence[ServiceEvent] = ()


@dataclass(frozen=True, slots=True)
class ModelHistory:
    """The ``model_history`` argument of ``update_estimate``.

    It contains only operator-available information: deployment facts, the
    prior parameter ranges (assumptions, not fitted truth), and the estimator's
    own previous snapshots.  Drivers -- current speed, upstream concentration --
    are derived from the observation records themselves, so there is no path
    from the hidden simulator into this object.
    """

    panel: OperatorKnownPanel
    material_priors: Mapping[str, MaterialParameters]
    elements: Sequence[str]
    reference_time_utc: datetime
    previous_snapshots: Sequence["EstimateSnapshot"] = ()
    assumptions: Mapping[str, Any] = field(default_factory=dict)
    origin: StateOrigin = StateOrigin.ESTIMATED

    def __post_init__(self) -> None:
        if self.origin is StateOrigin.TRUE_SIMULATED:
            raise ValueError(
                "ModelHistory may never be marked as hidden simulated truth"
            )


@dataclass(frozen=True, slots=True)
class EstimateSnapshot:
    """Operator-facing state estimate.  Contains no hidden event label.

    Intervals are documented central credible intervals of the weighted
    parameter ensemble at ``interval_level`` (default 0.90, i.e. the 5th and
    95th weighted percentiles).
    """

    time_utc: datetime
    panel_id: str
    retained_kg_estimate: Mapping[str, float]
    retained_kg_interval: Mapping[str, tuple[float, float]]
    remaining_life_s_interval: Mapping[str, tuple[float, float] | None]
    data_age_s: Mapping[str, float | None]
    model_data_compatibility: float | None
    evidence_record_ids: Sequence[str]
    ambiguity_flags: Sequence[AmbiguityFlag]
    interval_level: float = 0.90
    ensemble_size: int = 0
    origin: StateOrigin = StateOrigin.ESTIMATED
    notes: str = ""
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Recommendation:
    """A recommendation for a human.  Never an actuation."""

    recommendation_id: str
    decision_time_utc: datetime
    panel_id: str
    action: ActionKind
    reason: str
    evidence_record_ids: Sequence[str]
    uncertainty_note: str
    data_age_s: float | None
    human_confirmation_required: bool = True
    execution_mode: str = "simulation_only"
    expected_cost_eur: float | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.human_confirmation_required is not True:
            raise ValueError("human_confirmation_required must stay True")
        if self.execution_mode != "simulation_only":
            raise ValueError("execution_mode must stay 'simulation_only'")


@dataclass(frozen=True, slots=True)
class ActionEvent:
    """A recommendation a (simulated) human accepted; separate from the
    recommendation itself, so duplicates cannot create repeated replacements."""

    action_event_id: str
    recommendation_id: str
    accepted_at_utc: datetime
    action: ActionKind
    panel_id: str
    accepted: bool
    cost_eur: float = 0.0
    note: str = ""


# ---------------------------------------------------------------------------
# Frozen function signatures (DATA_CONTRACT section 2)
# ---------------------------------------------------------------------------

class AdvancePanel(Protocol):
    def __call__(
        self,
        panel_state: PanelState,
        contact_batch: ContactBatch,
        material_parameters: Mapping[str, MaterialParameters],
        dt_s: float,
    ) -> PanelStep: ...


class TransportStepFn(Protocol):
    def __call__(
        self,
        field_state: FieldState,
        forcing: Forcing,
        sources: Sequence[SourceTerm],
        dt_s: float,
    ) -> TransportStep: ...


class BuildContacts(Protocol):
    def __call__(
        self,
        field_state: FieldState,
        panels: Sequence[PanelState],
        forcing: Forcing,
        dt_s: float,
    ) -> Sequence[ContactBatch]: ...


class ApplyTransfers(Protocol):
    def __call__(
        self,
        field_state: FieldState,
        panel_steps: Sequence[PanelStep],
    ) -> FieldState: ...


class ObservationsAvailable(Protocol):
    def __call__(
        self,
        records: Sequence[ObservationRecord],
        decision_time_utc: datetime,
    ) -> Sequence[ObservationRecord]: ...


class UpdateEstimate(Protocol):
    def __call__(
        self,
        previous_estimate: EstimateSnapshot | None,
        available_observations: Sequence[ObservationRecord],
        model_history: ModelHistory,
    ) -> EstimateSnapshot: ...


class Recommend(Protocol):
    def __call__(
        self,
        snapshot: EstimateSnapshot,
        policy: Any,
        previous_actions: Sequence[ActionEvent],
    ) -> Recommendation: ...
