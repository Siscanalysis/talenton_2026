"""Frozen module boundary for the selective reactive seabed mat demonstrator.

Coordinator-owned.  Branch agents import these types and implement the
functions declared at the bottom of this file.  They must not edit this module;
additions are proposed in the branch handoff.

The product modelled here is a **thin, modular, retrievable reactive mat** laid
on or immediately above an authorised contaminated seabed area.  It attenuates
the contaminant flux from the sediment into the overlying water.  It is not a
vertical panel intercepting a plume, and nothing in this module computes a
frontal area, a swept volume or an interception efficiency.

The chain is::

    authorised contaminated seabed hotspot
      -> contaminant flux through / near the seabed
      -> reactive mat (1-D reactive layer, per tile)
      -> residual flux into the overlying water
      -> 2-D coastal advection and diffusion

Three states are kept apart everywhere (:class:`StateOrigin`):

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

#: 0.3.0 adds copper as a third element and encapsulates the reactive core
#: between two carrier geotextiles.  Both are additive: ``Element.CU`` is a new
#: member and ``AdvanceReactiveLayer`` gained a keyword-only argument with a
#: default, so code written against 0.2 keeps working.  The version moves
#: anyway, because a reader who sees 0.2 in a manifest should not have to guess
#: whether copper was in it.
CONTRACT_VERSION = "0.3.0-core-mat"

__all__ = [
    "CONTRACT_VERSION",
    # enumerations
    "Element",
    "StateOrigin",
    "ProvenanceLabel",
    "Parameter",
    "QuantityKind",
    "Matrix",
    "VerticalDatum",
    "Fraction",
    "AcquisitionKind",
    "Qualifier",
    "QualityFlag",
    "DataOrigin",
    "ActionKind",
    "AmbiguityFlag",
    "DegradationMode",
    "METAL_PARAMETERS",
    "CONTEXT_PARAMETERS",
    "MAT_CONDITION_PARAMETERS",
    "AQUEOUS_MATRICES",
    # observation
    "ObservationRecord",
    # macro
    "GridSpec",
    "FieldState",
    "Forcing",
    "SeabedHotspot",
    "SeabedSourceField",
    "TransportStep",
    # micro
    "MaterialParameters",
    "MatTileGeometry",
    "MatTileState",
    "SeabedExchange",
    "LayerStep",
    "ServiceEvent",
    "MassLedger",
    # estimation and decision
    "OperatorKnownMat",
    "ModelHistory",
    "EstimateSnapshot",
    "Recommendation",
    "ActionEvent",
    # frozen function signatures
    "AdvanceReactiveLayer",
    "BuildSeabedExchange",
    "ResidualSourceFlux",
    "TransportStepFn",
    "ObservationsAvailable",
    "UpdateEstimate",
    "Recommend",
]


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Element(str, enum.Enum):
    """Target elements.  Pb is the primary channel; Hg and Cu each carry their
    own parameter set and their own allocated share of the medium, and the
    shares must sum to at most one so no kilogram of sorbent is spent twice.

    The three behave very differently in seawater, and the model must not treat
    them as one problem with three labels:

    * **Pb** is partly free and partly carbonate-complexed, so a fraction of it
      is available to an ion-exchange site.
    * **Hg** is above 99 per cent chloro-complexed, mostly as HgCl4(2-). It is
      not free, and an anionic complex is not what a biosorption isotherm
      measured on free Hg(2+) describes.
    * **Cu** is above 99 per cent bound to strong organic ligands, with free
      Cu(2+) in the picomolar range. It is the hardest of the three to take out
      of seawater, not the easiest, despite having the best published capacity.
    """

    PB = "Pb"
    HG = "Hg"
    CU = "Cu"


class StateOrigin(str, enum.Enum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    TRUE_SIMULATED = "true_simulated"


class ProvenanceLabel(str, enum.Enum):
    """Mandatory label for every number that reaches a chart or an export.

    Deliberately separate from :class:`DataOrigin`.  A fabricated laboratory
    record is ``DataOrigin.LABORATORY`` with ``ProvenanceLabel.SYNTHETIC_DEMO``:
    the pathway and the truth status are different questions, and the previous
    contract could not express both at once.
    """

    MEASUREMENT = "measurement"
    EXTERNAL_MODEL = "external_model"
    LITERATURE = "literature"
    ASSUMPTION = "assumption"
    FITTED = "fitted"
    SYNTHETIC_DEMO = "synthetic_demo"


class Parameter(str, enum.Enum):
    """What is measured.

    ``Pb`` and ``Hg`` stay the parameter names for a flux measurement too: a
    benthic-chamber Pb flux is still Pb, distinguished by its
    :class:`QuantityKind` and unit, not by inventing a new parameter name.
    """

    PB = "Pb"
    HG = "Hg"
    CU = "Cu"
    # water column and near-bed context
    CURRENT_EAST = "current_east"
    CURRENT_NORTH = "current_north"
    TEMPERATURE = "temperature"
    SEDIMENT_TEMPERATURE = "sediment_temperature"
    CONDUCTIVITY = "conductivity"
    SALINITY = "salinity"
    PH = "pH"
    TURBIDITY = "turbidity"
    DISSOLVED_OXYGEN = "dissolved_oxygen"
    REDOX_POTENTIAL = "redox_potential"
    SULFIDE = "sulfide"
    # interface physics
    SEEPAGE_VELOCITY = "seepage_velocity"
    DIFFERENTIAL_HEAD = "differential_head"
    MAT_PERMEABILITY = "mat_permeability"
    # mat condition
    MAT_TILT = "mat_tilt"
    MAT_DISPLACEMENT = "mat_displacement"
    MAT_UPLIFT = "mat_uplift"
    MAT_COVERAGE_FRACTION = "mat_coverage_fraction"
    MAT_DAMAGE_CLASS = "mat_damage_class"
    BURIAL_DEPTH = "burial_depth"
    SCOUR_DEPTH = "scour_depth"
    # housekeeping
    BATTERY_VOLTAGE = "battery_voltage"


#: Parameters that carry metal-concentration or metal-flux information.
METAL_PARAMETERS: frozenset[Parameter] = frozenset({Parameter.PB, Parameter.HG})

#: Ordinary water-quality and physical proxies.  Listed explicitly so the
#: estimator can assert it never derives chemistry from them.
CONTEXT_PARAMETERS: frozenset[Parameter] = frozenset(
    {
        Parameter.CURRENT_EAST,
        Parameter.CURRENT_NORTH,
        Parameter.TEMPERATURE,
        Parameter.SEDIMENT_TEMPERATURE,
        Parameter.CONDUCTIVITY,
        Parameter.SALINITY,
        Parameter.PH,
        Parameter.TURBIDITY,
        Parameter.DISSOLVED_OXYGEN,
        Parameter.REDOX_POTENTIAL,
        Parameter.SULFIDE,
        Parameter.SEEPAGE_VELOCITY,
        Parameter.DIFFERENTIAL_HEAD,
        Parameter.BATTERY_VOLTAGE,
    }
)

#: Physical condition of the mat itself.  These constrain degradation modes 3
#: and 4 (displacement and local damage); they carry no chemistry.
MAT_CONDITION_PARAMETERS: frozenset[Parameter] = frozenset(
    {
        Parameter.MAT_TILT,
        Parameter.MAT_DISPLACEMENT,
        Parameter.MAT_UPLIFT,
        Parameter.MAT_COVERAGE_FRACTION,
        Parameter.MAT_DAMAGE_CLASS,
        Parameter.BURIAL_DEPTH,
        Parameter.SCOUR_DEPTH,
        Parameter.MAT_PERMEABILITY,
    }
)


class QuantityKind(str, enum.Enum):
    """What kind of number a record carries.

    Declared, never inferred from ``(matrix, fraction, unit)``.  The observation
    operator dispatches on this.
    """

    AQUEOUS_CONCENTRATION = "aqueous_concentration"   # kg m^-3
    SOLID_LOADING = "solid_loading"                   # kg kg^-1
    ACCUMULATED_MASS = "accumulated_mass"             # kg over a window
    AREAL_FLUX = "areal_flux"                         # kg m^-2 s^-1
    LENGTH = "length"                                 # m
    VELOCITY = "velocity"                             # m s^-1
    FRACTION = "fraction"                             # dimensionless 0..1
    CATEGORICAL = "categorical"                       # a class, not a number
    CONTEXT = "context"                               # unconverted context


class Matrix(str, enum.Enum):
    """What was sampled.

    ``BOTTOM_WATER`` is distinguished from ``SEAWATER`` because a near-bed
    measurement above the cap and a mid-column one are physically different.
    ``MAT_POREWATER`` is the state variable of the 1-D layer itself.
    """

    SEAWATER = "seawater"
    BOTTOM_WATER = "bottom_water"
    POREWATER = "porewater"
    MAT_POREWATER = "mat_porewater"
    SEDIMENT = "sediment"
    SORBENT = "sorbent"
    MAT_STRUCTURE = "mat_structure"
    INSTRUMENT = "instrument"


#: Matrices representing a dissolved aqueous pool the model can assimilate.
#: ``POREWATER`` is now a primary channel: it is the driving boundary condition
#: of the reactive layer.  Demoting it to evidence was the single most damaging
#: assumption inherited from the vertical-panel concept.
AQUEOUS_MATRICES: frozenset[Matrix] = frozenset(
    {Matrix.SEAWATER, Matrix.BOTTOM_WATER, Matrix.POREWATER, Matrix.MAT_POREWATER}
)


class VerticalDatum(str, enum.Enum):
    """What ``depth_m`` is measured from.  Previously undeclared, which made a
    sediment sample at ``depth_m = 5.0`` unresolvably ambiguous."""

    SEA_SURFACE = "sea_surface"
    SEABED = "seabed"
    MAT_TOP = "mat_top"
    MAT_BASE = "mat_base"


class Fraction(str, enum.Enum):
    NOT_APPLICABLE = "not_applicable"
    LABILE = "labile"
    DGT_LABILE = "dgt_labile"
    DISSOLVED_FILTERED = "dissolved_filtered"
    TOTAL_RECOVERABLE = "total_recoverable"
    DISSOLVED_INORGANIC = "dissolved_inorganic"
    METHYLMERCURY = "methylmercury"
    SORBED_TOTAL = "sorbed_total"
    ACID_VOLATILE_SULFIDE = "acid_volatile_sulfide"
    SIMULTANEOUSLY_EXTRACTED_METAL = "simultaneously_extracted_metal"


class AcquisitionKind(str, enum.Enum):
    IN_SITU_SENSOR = "in_situ_sensor"
    GRAB_SAMPLE = "grab_sample"
    SEDIMENT_CORE = "sediment_core"
    PASSIVE_SAMPLER = "passive_sampler"
    BENTHIC_CHAMBER = "benthic_chamber"
    MEDIA_ASSAY = "media_assay"
    ROV_INSPECTION = "rov_inspection"
    DIVER_INSPECTION = "diver_inspection"
    BATHYMETRIC_SURVEY = "bathymetric_survey"
    ACOUSTIC_POSITION = "acoustic_position"
    MANUAL = "manual"


class Qualifier(str, enum.Enum):
    QUANTIFIED = "quantified"
    BELOW_LOD = "below_lod"
    BELOW_LOQ = "below_loq"
    ABOVE_RANGE = "above_range"
    CATEGORICAL = "categorical"
    MISSING = "missing"


class QualityFlag(enum.IntEnum):
    """QARTOD-inspired flags [S23-S24].  Not an official QARTOD certification."""

    PASSED = 1
    NOT_EVALUATED = 2
    SUSPECT = 3
    FAILED = 4
    MISSING = 9


class DataOrigin(str, enum.Enum):
    """The acquisition pathway.  Truth status lives in :class:`ProvenanceLabel`."""

    SENSOR = "sensor"
    LABORATORY = "laboratory"
    FIELD_SURVEY = "field_survey"
    EXTERNAL_MODEL = "external_model"
    DERIVED = "derived"
    MANUAL = "manual"


class ActionKind(str, enum.Enum):
    """What may be recommended.  Never an actuation."""

    CONTINUE_MONITORING = "CONTINUE_MONITORING"
    TAKE_CHEMICAL_SAMPLE = "TAKE_CHEMICAL_SAMPLE"
    CHECK_SENSOR = "CHECK_SENSOR"
    INSPECT_MAT = "INSPECT_MAT"
    PLAN_PARTIAL_REPLACEMENT = "PLAN_PARTIAL_REPLACEMENT"
    REPLACE_ACTIVE_PANEL = "REPLACE_ACTIVE_PANEL"
    PERFORMANCE_UNCERTAIN = "PERFORMANCE_UNCERTAIN"


class DegradationMode(str, enum.Enum):
    """The four independent ways a mat stops working.

    They are modelled and reported independently.  Reading every performance
    loss as chemical saturation is the specific failure this enumeration exists
    to prevent.
    """

    SATURATION = "saturation"          # 1: capacity consumed, breakthrough
    FOULING = "fouling"                # 2: pore blockage, permeability loss
    DISPLACEMENT = "displacement"      # 3: burial, erosion, scour, uplift, shift
    LOCAL_DAMAGE = "local_damage"      # 4: tear, puncture, lost tile


class AmbiguityFlag(str, enum.Enum):
    """Competing explanations the estimator may leave unresolved.

    ``BURIAL`` matters most: burial *reduces* the apparent flux and can
    masquerade as success.
    """

    SEDIMENT_SOURCE_INCREASE = "sediment_source_increase"
    ADVECTIVE_CHANGE = "advective_change"
    SATURATION = "saturation"
    FOULING = "fouling"
    BURIAL = "burial"
    EROSION_SCOUR = "erosion_scour"
    DISPLACEMENT_UPLIFT = "displacement_uplift"
    TEAR_PUNCTURE = "tear_puncture"
    SENSOR_DRIFT = "sensor_drift"
    SENSOR_FAILURE = "sensor_failure"
    METHYLMERCURY_RISK = "methylmercury_risk"
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
    quantity_kind: QuantityKind
    unit: str
    matrix: Matrix
    fraction: Fraction
    acquisition_kind: AcquisitionKind
    qualifier: Qualifier
    quality_flag: QualityFlag
    method_id: str
    data_origin: DataOrigin
    provenance: ProvenanceLabel

    sensor_id: str | None = None
    sample_id: str | None = None
    media_id: str | None = None
    #: Which mat tile this observation belongs to.  Without it, spatially local
    #: failure is unobservable; ``media_id`` is not a substitute, because one
    #: media batch can be laid across many tiles.
    tile_id: str | None = None
    sampling_start_utc: datetime | None = None
    sampling_end_utc: datetime | None = None
    value: float | None = None
    uncertainty_std: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    #: For ``Qualifier.CATEGORICAL``: a class from a controlled vocabulary.
    condition_class: str | None = None
    calibration_id: str | None = None
    source_ref: str | None = None
    x_m: float | None = None
    y_m: float | None = None
    depth_m: float | None = None
    vertical_datum: VerticalDatum | None = None
    #: Position within the mat thickness, for a depth-resolved layer profile.
    z_in_mat_m: float | None = None
    #: Enclosed area of a benthic flux chamber; required to interpret its flux.
    chamber_area_m2: float | None = None
    crs: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_metal(self) -> bool:
        return self.parameter in METAL_PARAMETERS

    @property
    def is_censored(self) -> bool:
        return self.qualifier in (Qualifier.BELOW_LOD, Qualifier.BELOW_LOQ)

    @property
    def is_mat_condition(self) -> bool:
        return self.parameter in MAT_CONDITION_PARAMETERS

    @property
    def carries_chemical_information(self) -> bool:
        """A missing record carries none; a non-detect carries a bound."""
        return self.is_metal and self.qualifier is not Qualifier.MISSING


# ---------------------------------------------------------------------------
# Macro (coastal transport) side
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GridSpec:
    """Uniform metric grid.  ``crs`` is the metric computation CRS; latitude and
    longitude are a display concern only."""

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
    """Dissolved concentration field per element in the overlying water.

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
class SeabedHotspot:
    """An authorised contaminated seabed area.

    Abstract by construction.  This is a contaminant hotspot, not an object:
    nothing in this repository simulates, locates or recommends the handling of
    unexploded ordnance.  Real work near historical marine munitions requires
    specialist and environmental approval.
    """

    hotspot_id: str
    #: Flat cell indices of the contaminated seabed cells.
    cell_indices: Sequence[int]
    #: Sediment porewater concentration driving the flux [kg m^-3], per element.
    sediment_porewater_kg_per_m3: Mapping[str, float]
    #: Uncapped bare-sediment areal flux [kg m^-2 s^-1], per element.  The
    #: reference against which attenuation is measured.
    bare_flux_kg_per_m2_per_s: Mapping[str, float]
    seepage_velocity_m_per_s: float
    film_transfer_m_per_s: float
    label: ProvenanceLabel = ProvenanceLabel.SYNTHETIC_DEMO
    description: str = (
        "Hypothetical authorised contaminant hotspot for a demonstration. "
        "Not a located real site, and not an ordnance object."
    )

    @property
    def n_cells(self) -> int:
        return len(self.cell_indices)


@dataclass(frozen=True, slots=True)
class SeabedSourceField:
    """The residual flux entering the water column, per element.

    This is what the reactive layer hands to the coastal model.  Arrays are
    ``(ny, nx)`` in kg m^-2 s^-1 and are zero outside the hotspot.
    ``components`` breaks the total into the covered, uncovered, damaged and
    edge-leakage contributions, so a map can show *why* a cell emits.
    """

    time_utc: datetime
    flux_kg_per_m2_per_s: Mapping[str, np.ndarray]
    components: Mapping[str, Mapping[str, np.ndarray]] = field(default_factory=dict)
    provenance: ProvenanceLabel = ProvenanceLabel.SYNTHETIC_DEMO
    notes: str = ""

    def total_rate_kg_per_s(self, element: Element | str, grid: GridSpec) -> float:
        key = element.value if isinstance(element, Element) else element
        return float(np.sum(self.flux_kg_per_m2_per_s[key]) * grid.cell_area_m2)


@dataclass(frozen=True, slots=True)
class TransportStep:
    new_field: FieldState
    boundary_in_kg: Mapping[str, float]
    boundary_out_kg: Mapping[str, float]
    released_from_seabed_kg: Mapping[str, float]
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Micro (reactive layer) side
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MaterialParameters:
    """Reduced reactive-medium parameters for **one** element.

    ``kd_m3_per_kg``
        partition slope of the capped linear isotherm, q_eq = Kd * C (kg/kg).
    ``q_max_kg_per_kg``
        operating capacity cap.  Not a literature maximum [S01, S04].
    ``k_rate_per_s``
        first-order approach-to-equilibrium rate constant.
    ``allocation_fraction``
        share of the medium assigned to this element.  The sum over elements
        must not exceed 1: capacity is never counted twice.
    ``d_eff_m2_per_s``
        effective diffusion in the layer porewater, tortuosity included.
    """

    element: Element
    kd_m3_per_kg: float
    q_max_kg_per_kg: float
    k_rate_per_s: float
    allocation_fraction: float
    d_eff_m2_per_s: float = 2.0e-10
    kd_interval: tuple[float, float] | None = None
    q_max_interval: tuple[float, float] | None = None
    k_rate_interval: tuple[float, float] | None = None
    d_eff_interval: tuple[float, float] | None = None
    #: Fraction of accessible capacity lost at full fouling.
    fouling_rate_capacity: float = 0.0
    #: Fraction of the approach rate lost at full fouling.
    fouling_rate_kinetics: float = 1.0
    #: Fraction of effective diffusivity lost at full fouling (pore blockage).
    fouling_rate_diffusivity: float = 0.6
    provenance: ProvenanceLabel = ProvenanceLabel.SYNTHETIC_DEMO
    source_ref: str = "assumed synthetic baseline; see docs/MODEL_SPEC.md"


@dataclass(frozen=True, slots=True)
class MatTileGeometry:
    """One replaceable module of the mat.

    A tile lies flat on the seabed.  It has an area and a thickness, not a
    frontal area: nothing here is swept by a lateral current.
    """

    width_m: float
    length_m: float
    thickness_m: float
    x_m: float
    y_m: float
    #: Dry bulk density of the reactive medium in the layer [kg m^-3].
    bulk_density_kg_per_m3: float = 400.0
    porosity: float = 0.5
    #: Fraction of the flux that leaks around the tile edge rather than passing
    #: through the reactive layer.  A documented, uncertain design parameter.
    edge_leakage_fraction: float = 0.02
    edge_leakage_interval: tuple[float, float] | None = None

    @property
    def footprint_area_m2(self) -> float:
        return self.width_m * self.length_m

    @property
    def sorbent_loading_kg_per_m2(self) -> float:
        """Reactive medium per unit seabed area."""
        return self.bulk_density_kg_per_m3 * self.thickness_m

    @property
    def sorbent_mass_kg(self) -> float:
        return self.sorbent_loading_kg_per_m2 * self.footprint_area_m2


@dataclass(frozen=True, slots=True)
class MatTileState:
    """Auditable per-tile state.

    The four degradation modes live in four independent fields, so a
    performance loss can be attributed rather than blamed on saturation.
    Sorbed mass never decreases silently.
    """

    tile_id: str
    media_id: str
    installed_at_utc: datetime
    geometry: MatTileGeometry
    #: Porewater concentration profile through the layer, ``(nz,)`` per element.
    porewater_kg_per_m3: Mapping[str, np.ndarray]
    #: Sorbed loading profile through the layer, ``(nz,)`` per element.
    sorbed_kg_per_kg: Mapping[str, np.ndarray]
    #: Mode 2.  0 = clean, 1 = fully fouled.
    fouling_index: float = 0.0
    #: Mode 4.  1 = intact, 0 = wholly failed.  The share of tile area still
    #: functioning; the remainder passes the bare flux straight through.
    integrity_index: float = 1.0
    #: Mode 3.  Sediment accumulated on top of the tile [m].
    burial_depth_m: float = 0.0
    #: Mode 3.  Horizontal offset from the as-laid position [m].
    displacement_m: float = 0.0
    #: Mode 3.  A displaced tile no longer covers its cells at all.
    displaced: bool = False
    active: bool = True
    service_count: int = 0

    @property
    def n_nodes(self) -> int:
        return int(next(iter(self.porewater_kg_per_m3.values())).shape[0])

    @property
    def coverage_fraction(self) -> float:
        """Share of the tile's footprint still providing a reactive layer."""
        if self.displaced or not self.active:
            return 0.0
        return max(0.0, min(1.0, self.integrity_index))

    def dz_m(self) -> float:
        return self.geometry.thickness_m / self.n_nodes

    def retained_kg_per_m2(self, element: Element | str) -> float:
        """Sorbed plus dissolved inventory per unit seabed area."""
        key = element.value if isinstance(element, Element) else element
        dz = self.dz_m()
        porewater = np.asarray(self.porewater_kg_per_m3[key], dtype=float)
        sorbed = np.asarray(self.sorbed_kg_per_kg[key], dtype=float)
        return float(
            np.sum(
                self.geometry.porosity * porewater
                + self.geometry.bulk_density_kg_per_m3 * sorbed
            )
            * dz
        )

    def retained_kg(self, element: Element | str) -> float:
        return self.retained_kg_per_m2(element) * self.geometry.footprint_area_m2

    def capacity_kg_per_m2(self, params: MaterialParameters) -> float:
        """Nominal capacity for one element, using its allocated medium."""
        return (
            self.geometry.sorbent_loading_kg_per_m2
            * params.allocation_fraction
            * params.q_max_kg_per_kg
        )

    def saturation_fraction(self, params: MaterialParameters) -> float:
        """Active-media saturation for one element, in ``[0, 1+]``."""
        capacity = self.capacity_kg_per_m2(params)
        if capacity <= 0.0:
            return 0.0
        key = params.element.value
        dz = self.dz_m()
        sorbed = np.asarray(self.sorbed_kg_per_kg[key], dtype=float)
        sorbed_kg_per_m2 = float(
            np.sum(self.geometry.bulk_density_kg_per_m3 * sorbed) * dz
        )
        return sorbed_kg_per_m2 / capacity


@dataclass(frozen=True, slots=True)
class SeabedExchange:
    """The conditions one tile sees over one step.

    Replaces the vertical-panel ``ContactBatch``.  There is no swept volume and
    no interception efficiency: the driving conditions are the sediment
    porewater beneath the tile and the bottom water above it.
    """

    tile_id: str
    time_utc: datetime
    dt_s: float
    #: Driving porewater concentration at the sediment face [kg m^-3].
    sediment_porewater_kg_per_m3: Mapping[str, float]
    #: Overlying bottom-water concentration [kg m^-3], from the coastal field.
    bottom_water_kg_per_m3: Mapping[str, float]
    #: Darcy seepage velocity through the layer [m s^-1], positive upward.
    seepage_velocity_m_per_s: float
    #: Benthic boundary-layer transfer coefficient [m s^-1].
    film_transfer_m_per_s: float
    #: Uncapped reference flux for the same conditions [kg m^-2 s^-1].
    bare_flux_kg_per_m2_per_s: Mapping[str, float]
    cell_indices: Sequence[int]
    cell_weights: Sequence[float]
    driving_is_measured: bool = False
    environment: Mapping[str, float] = field(default_factory=dict)
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LayerStep:
    """What one tile did over one step.

    Fluxes are per unit seabed area.  ``flux_out`` is the residual flux the
    coastal model receives; it is never a mass subtracted from a water cell.
    """

    new_state: MatTileState
    flux_in_kg_per_m2_per_s: Mapping[str, float]
    flux_out_kg_per_m2_per_s: Mapping[str, float]
    retained_delta_kg_per_m2: Mapping[str, float]
    released_kg_per_m2: Mapping[str, float]
    exchange: SeabedExchange | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def attenuation(self, element: Element | str, bare_flux: float) -> float | None:
        """``1 - J_out / J_bare``, or ``None`` when there is no flux to attenuate."""
        key = element.value if isinstance(element, Element) else element
        if bare_flux <= 0.0:
            return None
        return 1.0 - self.flux_out_kg_per_m2_per_s[key] / bare_flux


@dataclass(frozen=True, slots=True)
class ServiceEvent:
    """A simulated maintenance action that changed one or more tiles."""

    event_id: str
    time_utc: datetime
    tile_ids: Sequence[str]
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

    The contaminant now enters the water *from the seabed through the mat*, so
    the compartments are source-driven::

        initial_water + released_from_sediment + boundary_in
          == in_water + retained_in_mat + retained_in_retrieved_media
             + boundary_out + numerical_correction

    ``released_from_sediment_kg`` is the gross mass that left the sediment,
    whether it entered a tile or passed straight into the water where the mat is
    absent, displaced or torn.  The sediment reservoir itself is prescribed and
    not depleted, which is a documented assumption, not a conservation claim.

    ``numerical_correction_kg`` records any clipping the solvers applied.  It is
    reported, never hidden.
    """

    element: str
    initial_water_kg: float = 0.0
    released_from_sediment_kg: float = 0.0
    boundary_in_kg: float = 0.0
    in_water_kg: float = 0.0
    retained_in_mat_kg: float = 0.0
    retained_in_retrieved_media_kg: float = 0.0
    boundary_out_kg: float = 0.0
    numerical_correction_kg: float = 0.0

    @property
    def supplied_kg(self) -> float:
        return (
            self.initial_water_kg
            + self.released_from_sediment_kg
            + self.boundary_in_kg
        )

    @property
    def accounted_kg(self) -> float:
        return (
            self.in_water_kg
            + self.retained_in_mat_kg
            + self.retained_in_retrieved_media_kg
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
class OperatorKnownMat:
    """What an operator legitimately knows without measuring anything.

    Deployment paperwork: which tiles, which media batch, when they went in,
    their geometry, and which service actions were accepted.  It carries no
    loading, no fouling and no integrity: those are exactly what has to be
    estimated.
    """

    mat_id: str
    tile_ids: Sequence[str]
    media_id: str
    installed_at_utc: datetime
    geometry: MatTileGeometry
    hotspot_area_m2: float
    covered_area_m2: float
    accepted_service_events: Sequence[ServiceEvent] = ()

    @property
    def design_coverage_fraction(self) -> float:
        if self.hotspot_area_m2 <= 0.0:
            return 0.0
        return self.covered_area_m2 / self.hotspot_area_m2


@dataclass(frozen=True, slots=True)
class ModelHistory:
    """The ``model_history`` argument of ``update_estimate``.

    Operator-available information only: deployment facts, prior parameter
    ranges (assumptions, not fitted truth), and the estimator's own previous
    snapshots.  Drivers are derived from the observation records themselves, so
    there is no path from the hidden simulator into this object.
    """

    mat: OperatorKnownMat
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
    parameter ensemble at ``interval_level`` (default 0.90, the 5th and 95th
    weighted percentiles).

    Remaining life is deliberately an interval or ``None``.  A falsely precise
    remaining-life number is worse than an honest "not determined".
    """

    time_utc: datetime
    tile_id: str
    #: Sorbed loading per unit area, per element [kg m^-2].
    loading_kg_per_m2_estimate: Mapping[str, float]
    loading_kg_per_m2_interval: Mapping[str, tuple[float, float]]
    #: Remaining capacity per unit area, per element [kg m^-2].
    remaining_capacity_kg_per_m2: Mapping[str, tuple[float, float]]
    #: Residual flux leaving the mat, per element [kg m^-2 s^-1].
    residual_flux_interval: Mapping[str, tuple[float, float]]
    #: Estimated sediment-side source flux, per element [kg m^-2 s^-1].
    source_flux_interval: Mapping[str, tuple[float, float]]
    #: ``1 - J_out / J_bare`` per element, as an interval.
    attenuation_interval: Mapping[str, tuple[float, float]]
    breakthrough_s_interval: Mapping[str, tuple[float, float] | None]
    fouling_index_interval: tuple[float, float] | None
    integrity_index_interval: tuple[float, float] | None
    effective_permeability_interval: tuple[float, float] | None
    data_age_s: Mapping[str, float | None]
    model_data_compatibility: float | None
    evidence_record_ids: Sequence[str]
    ambiguity_flags: Sequence[AmbiguityFlag]
    #: Weight the evidence gives each degradation mode.  Reported side by side
    #: so no single mode is assumed.
    degradation_mode_weights: Mapping[str, float] = field(default_factory=dict)
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
    mat_id: str
    action: ActionKind
    reason: str
    evidence_record_ids: Sequence[str]
    uncertainty_note: str
    data_age_s: float | None
    target_tile_ids: Sequence[str] = ()
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
    """A recommendation a simulated human accepted.

    Separate from the recommendation itself, so duplicates cannot create
    repeated replacements.
    """

    action_event_id: str
    recommendation_id: str
    accepted_at_utc: datetime
    action: ActionKind
    mat_id: str
    accepted: bool
    target_tile_ids: Sequence[str] = ()
    cost_eur: float = 0.0
    note: str = ""


# ---------------------------------------------------------------------------
# Frozen function signatures (docs/DATA_CONTRACT.md section 2)
# ---------------------------------------------------------------------------

class AdvanceReactiveLayer(Protocol):
    """1-D reactive layer through the mat thickness, for one tile, one step.

    ``geotextile`` is the carrier layer encapsulating the reactive core on both
    faces.  Keyword-only with a default, so a caller written against contract
    0.2 keeps working; passing ``None`` recovers the unencapsulated core that
    0.2 assumed, which is how the cost of the encapsulation is measured.
    """

    def __call__(
        self,
        tile_state: MatTileState,
        exchange: SeabedExchange,
        material_parameters: Mapping[str, MaterialParameters],
        dt_s: float,
        *,
        geotextile: Any = ...,
    ) -> LayerStep: ...


class BuildSeabedExchange(Protocol):
    """Driving conditions per tile, from the hotspot and the overlying field."""

    def __call__(
        self,
        field_state: FieldState,
        tiles: Sequence[MatTileState],
        hotspot: SeabedHotspot,
        forcing: Forcing,
        dt_s: float,
    ) -> Sequence[SeabedExchange]: ...


class ResidualSourceFlux(Protocol):
    """Tile states plus hotspot to the distributed source the water receives.

    Covered area emits the tile's ``flux_out``; uncovered, displaced or torn
    area emits the bare flux; edge leakage is added on footprint boundary cells.
    """

    def __call__(
        self,
        grid: GridSpec,
        hotspot: SeabedHotspot,
        tiles: Sequence[MatTileState],
        layer_steps: Sequence[LayerStep],
        time_utc: datetime,
    ) -> SeabedSourceField: ...


class TransportStepFn(Protocol):
    def __call__(
        self,
        field_state: FieldState,
        forcing: Forcing,
        sources: SeabedSourceField,
        dt_s: float,
    ) -> TransportStep: ...


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
