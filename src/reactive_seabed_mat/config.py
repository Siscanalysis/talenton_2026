"""Single coordinator-owned run configuration.

Every run records seed, time stepping, domain, forcing assumptions, the seabed
hotspot and its schedule, mat layout and reactive-medium parameters with their
ranges and provenance, degradation assumptions, observation schedule, noise and
detection assumptions, laboratory latency, service policy and assumed costs
(``docs/DATA_CONTRACT.md`` section 4).

Every euro value and every material parameter below is an explicit
**assumption** for a demonstration.  None is a quotation, and none is a measured
product specification.  The parameter set is the one the numerical probes in
``docs/reactive_layer_numerics_probe.py`` were run with, so the documented
breakthrough time is reproducible.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import Element, ProvenanceLabel

CONFIG_VERSION = "0.2.0"

_SECONDS_PER_DAY = 86400.0
_SECONDS_PER_YEAR = 365.25 * _SECONDS_PER_DAY

__all__ = [
    "CONFIG_VERSION",
    "DomainConfig",
    "ForcingConfig",
    "HotspotScheduleEntry",
    "HotspotConfig",
    "ReactiveMediumConfig",
    "MatLayoutConfig",
    "DegradationEvent",
    "DegradationConfig",
    "StationConfig",
    "ObservationConfig",
    "PolicyConfig",
    "CostConfig",
    "PlumeWindowConfig",
    "RunConfig",
    "default_run_config",
    "load_run_config",
    "save_run_config",
    "config_to_dict",
    "config_hash",
]


@dataclass(frozen=True, slots=True)
class DomainConfig:
    """Coastal grid for the residual plume."""

    nx: int = 60
    ny: int = 40
    dx_m: float = 10.0
    dy_m: float = 10.0
    mixing_depth_m: float = 5.0
    crs: str = "LOCAL_METRIC"
    #: Land cells: rectangles (x0, y0, x1, y1) in metres, no-flux, no water.
    land_rectangles: Sequence[tuple[float, float, float, float]] = (
        (0.0, 0.0, 600.0, 40.0),
    )
    #: synthetic | real_map_illustrative | imported_forcing.  Never promoted
    #: silently: each mode is chosen explicitly and labelled on every chart.
    mode: str = "synthetic"


@dataclass(frozen=True, slots=True)
class ForcingConfig:
    """Prescribed, physically simple current field for the overlying water.

    ``kind='steady'`` gives a constant eastward flow; ``kind='tidal'`` reverses
    it with period ``tidal_period_s``.  A de-tided or daily-mean external
    product may never be substituted for the tidal case [S10].
    """

    kind: str = "tidal"
    u_mean_m_per_s: float = 0.04
    v_mean_m_per_s: float = 0.0
    tidal_amplitude_m_per_s: float = 0.18
    tidal_period_s: float = 44712.0  # M2, 12 h 25.2 min
    tidal_phase_rad: float = 0.0
    diffusivity_m2_per_s: float = 0.6
    provenance: str = ProvenanceLabel.SYNTHETIC_DEMO.value
    product_ref: str | None = None
    temporal_averaging: str = "instantaneous_synthetic"


@dataclass(frozen=True, slots=True)
class HotspotScheduleEntry:
    """A change in the sediment-side driving conditions.

    ``porewater_kg_per_m3`` is the concentration at the sediment face and
    ``seepage_velocity_m_per_s`` the Darcy velocity through it.  Together they
    set the uncapped flux, so scenario C ("the leak rate increases") is a change
    here and nowhere else.
    """

    start_s: float
    porewater_kg_per_m3: Mapping[str, float]
    seepage_velocity_m_per_s: float


@dataclass(frozen=True, slots=True)
class HotspotConfig:
    """An authorised contaminated seabed area.

    Abstract by construction: a contaminant hotspot, never an ordnance object.
    Nothing in this repository simulates or recommends handling munitions.
    """

    hotspot_id: str = "authorised_hotspot_1"
    x_m: float = 260.0
    y_m: float = 180.0
    width_m: float = 80.0
    length_m: float = 80.0
    #: Benthic boundary-layer transfer coefficient [m/s].  With a ~1.4 mm
    #: diffusive sublayer and D ~ 7e-10 m2/s this is about 5e-7 m/s.
    film_transfer_m_per_s: float = 5.0e-7
    schedule: Sequence[HotspotScheduleEntry] = (
        HotspotScheduleEntry(
            start_s=0.0,
            # Pb 1.0 mg/L, Hg 8 ug/L, Cu 2.0 mg/L, all TOTAL DISSOLVED. These
            # are deliberately extreme: docs/EVIDENCE_BASE.md section 1.1 shows
            # the resulting bare Pb flux is hundreds of times measured benthic
            # fluxes. They are chosen so a multi-year run shows loading and
            # breakthrough, and the absolute kilograms therefore belong to the
            # assumed hotspot rather than to any site. Copper is set above lead
            # because corroding brass and copper-alloy fuzes and driving bands
            # are a documented component of dumped conventional munitions, but
            # only a small fraction of it is ever available to a sorbent: see
            # ReactiveMediumConfig.available_fraction.
            porewater_kg_per_m3={"Pb": 1.0e-3, "Hg": 8.0e-6, "Cu": 2.0e-3},
            seepage_velocity_m_per_s=3.0e-8,  # about 0.95 m/yr
        ),
    )
    label: str = ProvenanceLabel.SYNTHETIC_DEMO.value
    description: str = (
        "Hypothetical authorised contaminant hotspot for a demonstration. Not a "
        "located real site, and not an ordnance object. Real work near "
        "historical marine munitions requires specialist and environmental "
        "approval [S02, S03]."
    )

    @property
    def area_m2(self) -> float:
        return self.width_m * self.length_m


@dataclass(frozen=True, slots=True)
class ReactiveMediumConfig:
    """Reduced parameters for a **keratin-based** reactive medium, per element.

    Grounded in the published keratin biosorption literature and then derated
    for seawater.  The full derivation, the sources and the caveats are in
    ``docs/MATERIAL_KERATIN.md``; the short version:

    * Published Pb(II) Langmuir capacities for keratin biofibres are 4 to
      33 mg/g, measured **in deionised water at pH 4.0** [K1, K2].
    * In seawater at pH 8.2 free Pb2+ is a small minority of dissolved lead
      (PbCO3(aq) alone is about 41 %) and Ca and Mg outnumber it by orders of
      magnitude [K3], so the operating capacity is set well below the
      freshwater figures.
    * No verified Hg(II) capacity for a keratin biosorbent was found. The Hg
      capacity is instead a small fraction of the stoichiometric thiol ceiling
      implied by keratin's 4 to 8 wt% sulfur [K4], which is about 125 mg/g if
      every disulfide were reduced and accessible.
    * Cu(II) has the *best* published keratin capacities of the three, 20 mg/g
      on wool keratin nanofibres [K9], and is nonetheless the *hardest* of the
      three to take out of seawater, because above 99 per cent of dissolved Cu
      is held by strong organic ligands with conditional stability constants
      around 1e15 and free Cu2+ sits below 6 pM [K11]. Capacity is not
      availability, and ``available_fraction`` is where that distinction lives.

    Every value remains an ASSUMPTION about our material, not a measurement of
    it.  The intervals are wide on purpose.
    """

    element: str = Element.PB.value
    #: Derated from the Langmuir behaviour of keratin biofibres [K1].
    kd_m3_per_kg: float = 3.0
    kd_interval: tuple[float, float] = (0.5, 20.0)
    #: Operating capacity: about one fifth of the lowest freshwater literature
    #: value (4.29 mg/g, dog hair [K1]), derated for seawater speciation and
    #: Ca/Mg competition.  The interval's upper end, 8.0e-3 kg/kg, is the best
    #: published freshwater result (chicken feather, 8.02 mg/g [K1]), that is,
    #: the optimistic case in which seawater costs nothing.
    q_max_kg_per_kg: float = 1.0e-3
    q_max_interval: tuple[float, float] = (3.0e-4, 8.0e-3)
    #: What an operator would know after a commissioning isotherm on the actual
    #: batch, in artificial seawater at pH 8.1 (experiment 1 of
    #: ``docs/MATERIAL_KERATIN.md``).  ``None`` means no such test was done, and
    #: the estimator then has to fall back on the literature interval above,
    #: which spans a factor of 27 and is too wide to run a replacement policy
    #: on.  That contrast is a result worth showing, not a nuisance: it puts a
    #: number on what the laboratory work is worth.
    commissioned_q_max_interval: tuple[float, float] | None = (7.5e-4, 1.3e-3)
    #: Order of magnitude from pseudo-second-order kinetics reaching equilibrium
    #: within 24 h in batch [K1].  In a mat the rate is set by intraparticle
    #: transport, not by batch stirring, so this is uncertain.
    k_rate_per_s: float = 4.0e-4
    k_rate_interval: tuple[float, float] = (1.0e-4, 1.2e-3)
    d_eff_m2_per_s: float = 2.0e-10
    d_eff_interval: tuple[float, float] = (8.0e-11, 5.0e-10)
    #: Fraction of the DISSOLVED pool that a sorption site can actually reach in
    #: seawater, after speciation.  This is the honest home for the difference
    #: between a capacity measured on free ions in deionised water and a real
    #: seawater matrix, and it multiplies the driving concentration rather than
    #: the capacity, because speciation limits the *supply*, not the number of
    #: sites.
    #:
    #: Pb: free Pb2+ plus the weakly bound carbonate pool.  PbCO3(aq) alone is
    #: about 41 per cent of dissolved Pb at pH 8.2 [K3] and measured free Pb2+
    #: runs an order of magnitude below equilibrium predictions, so 0.25 is
    #: already generous.
    available_fraction: float = 0.25
    available_fraction_interval: tuple[float, float] = (0.05, 0.6)
    allocation_fraction: float = 0.6
    fouling_rate_capacity: float = 0.0
    fouling_rate_kinetics: float = 0.8
    fouling_rate_diffusivity: float = 0.6
    provenance: str = ProvenanceLabel.ASSUMPTION.value
    source_ref: str = (
        "keratin biosorption literature derated for seawater; "
        "see docs/MATERIAL_KERATIN.md [K1-K4]"
    )


@dataclass(frozen=True, slots=True)
class MatLayoutConfig:
    """Footprint, tiling and thickness of the reactive mat.

    These are the design variables the optimisation moves: coverage of the
    hotspot, tile size, thickness and therefore sorbent loading per square
    metre, plus overlap and the edge-leakage allowance.
    """

    mat_id: str = "mat_A"
    media_id: str = "media_A0"
    #: Tiles across x and y.  Tile size follows from the covered area.
    tiles_x: int = 3
    tiles_y: int = 3
    #: Share of the hotspot the mat is designed to cover.  Below 1 the
    #: uncovered remainder keeps emitting its bare flux, which is exactly how
    #: the poor-design scenario fails.
    coverage_fraction: float = 1.0
    thickness_m: float = 0.010
    #: A wool-felt-like keratin nonwoven at about 0.5 porosity. Keratin solid
    #: density is near 1300 kg/m^3, so a half-porous felt lands here.
    bulk_density_kg_per_m3: float = 400.0
    porosity: float = 0.5
    overlap_m: float = 0.10
    edge_leakage_fraction: float = 0.02
    edge_leakage_interval: tuple[float, float] = (0.005, 0.08)
    #: Vertical nodes through the layer for the 1-D solve.
    n_layer_nodes: int = 40
    #: Explicit preload of sorbed mass per unit area, per element [kg/m2], for a
    #: stress test.  Visible in the exported configuration; uptake parameters
    #: are never inflated to force saturation.
    preload_kg_per_m2: Mapping[str, float] = field(default_factory=dict)
    media: Sequence[ReactiveMediumConfig] = (
        ReactiveMediumConfig(),
        ReactiveMediumConfig(
            element=Element.HG.value,
            # Mercury in seawater is NOT free Hg2+: thermodynamic calculations
            # put Hg(II) at above 99 per cent Hg-Cl complexes, dominated by the
            # tetrachloride HgCl4(2-) [K10]. Two consequences, and they pull in
            # opposite directions.
            #
            # For us: thiol-Hg bonds are strong enough that thiol ligands still
            # outcompete chloride, which is why thiol sorbents are the
            # established route for Hg in saline matrices. Hence a high Kd.
            #
            # Against us: the sorbing species is an ANION approaching a surface
            # that is negatively charged at pH 8, and the site must displace
            # four chlorides before it binds. Neither cost appears in a batch
            # isotherm measured on free Hg2+, so available_fraction carries it.
            kd_m3_per_kg=30.0,
            kd_interval=(2.0, 300.0),
            # Above 99 per cent chloro-complexed [K10]. The complexes are
            # labile, so they are not permanently unavailable, but the fraction
            # a site sees at any instant is small and the exchange is slower
            # than for a free ion. 0.10 with a wide interval.
            available_fraction=0.10,
            available_fraction_interval=(0.01, 0.4),
            # 2 % of the 125 mg/g stoichiometric thiol ceiling implied by
            # keratin's 4 wt% sulfur [K4]. NO verified Hg capacity for a keratin
            # biosorbent was found, so this is the weakest number in the model
            # and the interval spans 0.16 % to 20 % of that ceiling.
            q_max_kg_per_kg=2.5e-3,
            q_max_interval=(2.0e-4, 2.5e-2),
            # No verified keratin Hg capacity exists, so there is nothing for a
            # commissioning test to confirm yet. Left as None on purpose: the
            # Hg channel must not borrow the confidence the Pb channel earned.
            commissioned_q_max_interval=None,
            k_rate_per_s=2.0e-4,
            k_rate_interval=(3.0e-5, 8.0e-4),
            allocation_fraction=0.3,
            source_ref=(
                "stoichiometric thiol ceiling from keratin sulfur content [K4], "
                "not a measured Hg capacity: none was found. Seawater Hg is "
                "above 99 per cent chloro-complexed [K10]. Hg uptake also "
                "depends strongly on sulfide, chloride and dissolved organic "
                "matter [S04]. See docs/MATERIAL_KERATIN.md section 3"
            ),
        ),
        ReactiveMediumConfig(
            element=Element.CU.value,
            # Copper has the best published keratin capacities of the three and
            # is the hardest of the three to remove from seawater. Both are
            # true, and the second matters more.
            #
            # Published: 20 mg/g on wool keratin nanofibres [K9], 27.4 mg/g on
            # keratin-modified magnetite, and 61.7 to 103.5 mg/g on keratin/PA6
            # blend nanofibres. The nanofibre figures are NOT transferable to a
            # bulk felt core: they come from a far larger specific surface area
            # than a needle-punched mat has. 3.0 mg/g is taken instead, an order
            # of magnitude below the lowest nanofibre value.
            kd_m3_per_kg=8.0,
            kd_interval=(1.0, 60.0),
            q_max_kg_per_kg=3.0e-3,
            q_max_interval=(5.0e-4, 2.0e-2),
            # A commissioning isotherm on our own batch is meaningful here,
            # because unlike Hg there IS a measured keratin Cu capacity to
            # confirm or refute.
            commissioned_q_max_interval=(2.0e-3, 4.5e-3),
            k_rate_per_s=5.0e-4,
            k_rate_interval=(1.0e-4, 1.5e-3),
            d_eff_m2_per_s=2.2e-10,
            d_eff_interval=(9.0e-11, 5.5e-10),
            # THE PESSIMISTIC NUMBER OF THE WHOLE MODEL. Above 99 per cent of
            # dissolved Cu in seawater and in pore waters is bound to strong
            # organic ligands, conditional stability constants around 1e15, with
            # free Cu2+ below 6 pM [K11]. A carboxyl or amino site on keratin
            # does not obviously outcompete a ligand that strong. 0.02 is one
            # fiftieth of the dissolved pool and the interval reaches 0.002.
            available_fraction=0.02,
            available_fraction_interval=(0.002, 0.15),
            allocation_fraction=0.1,
            source_ref=(
                "wool keratin nanofibre Cu(II) Langmuir capacity 20 mg/g [K9], "
                "derated by an order of magnitude for a bulk felt core, then "
                "limited by organic complexation: above 99 per cent of "
                "dissolved Cu in seawater is bound to strong ligands [K11]. "
                "See docs/MATERIAL_KERATIN.md section 3b"
            ),
        ),
    )

    def __post_init__(self) -> None:
        total = sum(medium.allocation_fraction for medium in self.media)
        if total > 1.0 + 1e-12:
            raise ValueError(
                "the media allocation fractions spend more sorbent than the mat "
                f"contains: {total:.3f} > 1.0. Every kilogram of keratin can be "
                "counted once."
            )

    @property
    def n_tiles(self) -> int:
        return self.tiles_x * self.tiles_y

    @property
    def sorbent_loading_kg_per_m2(self) -> float:
        return self.bulk_density_kg_per_m3 * self.thickness_m


@dataclass(frozen=True, slots=True)
class DegradationEvent:
    """A scheduled degradation of one tile.

    ``mode`` is a :class:`~reactive_seabed_mat.contracts.DegradationMode` value.
    Scheduling them explicitly keeps the four modes independent: a scenario can
    displace a tile without touching its chemistry.
    """

    start_s: float
    tile_id: str
    mode: str
    #: Meaning depends on the mode: integrity lost, burial metres, displacement
    #: metres, or fouling index added.
    magnitude: float


@dataclass(frozen=True, slots=True)
class DegradationConfig:
    """The four independent degradation modes."""

    #: Mode 2, continuous.  Reaches full fouling in about 6 years.
    fouling_growth_per_s: float = 5.0e-9
    #: Mode 3, continuous sediment accumulation on top of the mat [m/s].
    burial_growth_m_per_s: float = 0.0
    #: Extra diffusive path a buried mat must overcome, per metre of burial.
    burial_resistance_s_per_m: float = 2.0e8
    #: Mode 2 side effect: pore blockage raises the head across the layer and
    #: pushes flow around the tile edge, so fouling is never a free benefit.
    fouling_bypass_coupling: float = 0.35
    events: Sequence[DegradationEvent] = ()


@dataclass(frozen=True, slots=True)
class StationConfig:
    station_id: str
    x_m: float
    y_m: float
    depth_m: float = 0.3
    vertical_datum: str = "seabed"
    #: environmental | bottom_water_probe | porewater | chamber | survey
    kind: str = "environmental"
    tile_id: str | None = None


@dataclass(frozen=True, slots=True)
class ObservationConfig:
    """Artificial schedules, not verified instrument cycle times.

    A reactive cap is monitored on a campaign rhythm, not a plume rhythm: months
    between chemistry, not minutes.
    """

    environmental_period_s: float = 3600.0
    bottom_water_probe_period_s: float = 6.0 * 3600.0
    porewater_sample_period_s: float = 90.0 * _SECONDS_PER_DAY
    chamber_deployment_period_s: float = 180.0 * _SECONDS_PER_DAY
    survey_period_s: float = 180.0 * _SECONDS_PER_DAY
    dgt_deployment_period_s: float = 180.0 * _SECONDS_PER_DAY
    dgt_exposure_s: float = 3.0 * _SECONDS_PER_DAY
    lab_latency_s: float = 21.0 * _SECONDS_PER_DAY
    survey_latency_s: float = 1.0 * _SECONDS_PER_DAY
    probe_latency_s: float = 0.0
    probe_relative_noise: float = 0.20
    probe_lod_ng_per_l: float = 12.0
    probe_loq_ng_per_l: float = 40.0
    probe_range_top_ng_per_l: float = 5000.0
    lab_relative_noise: float = 0.08
    lab_lod_ng_per_l: float = 1.5
    lab_loq_ng_per_l: float = 5.0
    chamber_relative_noise: float = 0.35
    chamber_lod_ug_per_m2_per_d: float = 0.05
    chamber_loq_ug_per_m2_per_d: float = 0.20
    environmental_relative_noise: float = 0.02
    missing_probability: float = 0.03
    #: Simulated hard sensor dropout window, seconds from run start.
    sensor_dropout_window_s: tuple[float, float] | None = None
    sensor_drift_start_s: float | None = None
    sensor_drift_per_s: float = 0.0
    stations: Sequence[StationConfig] = (
        StationConfig("ST_MAT_A", 280.0, 200.0, kind="bottom_water_probe",
                      tile_id="tile_0_0"),
        StationConfig("ST_MAT_B", 300.0, 220.0, kind="porewater",
                      depth_m=0.01, vertical_datum="mat_base", tile_id="tile_1_1"),
        StationConfig("ST_MAT_C", 320.0, 240.0, kind="chamber",
                      depth_m=0.0, vertical_datum="mat_top", tile_id="tile_2_2"),
        StationConfig("ST_ENV", 300.0, 260.0, kind="environmental", depth_m=1.0),
        StationConfig("SURVEY_01", 300.0, 220.0, kind="survey", depth_m=0.0,
                      vertical_datum="mat_top"),
    )


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    """Maintenance policy.  ``kind='none'`` means no mat is deployed."""

    kind: str = "evidence_informed"  # none | fixed | evidence_informed
    fixed_interval_s: float = 2.0 * _SECONDS_PER_YEAR
    decision_period_s: float = 30.0 * _SECONDS_PER_DAY
    #: Which end of the estimated saturation interval a decision is taken on:
    #: ``lower`` acts only on proof, ``upper`` acts on possibility, ``mid`` is
    #: neutral between replacing too early and replacing too late.  This is a
    #: risk posture, not a physical parameter, and it belongs in the open where
    #: a reviewer can disagree with it.
    saturation_decision_bound: str = "mid"
    #: Recommend replacement when the estimated saturation lower bound passes
    #: this.  A demonstration trigger, not a regulatory or engineering standard.
    replacement_saturation_threshold: float = 0.80
    inspection_saturation_threshold: float = 0.55
    #: Attenuation below which performance is treated as lost, if the evidence
    #: supports it.
    minimum_acceptable_attenuation: float = 0.70
    #: Widest acceptable relative interval before more evidence is requested.
    max_relative_interval_width: float = 1.2
    max_data_age_s: float = 200.0 * _SECONDS_PER_DAY
    min_evidence_records: int = 3
    #: Below this coverage the mat is treated as physically compromised rather
    #: than chemically exhausted.
    minimum_coverage_fraction: float = 0.90
    #: Replace only the tiles whose evidence supports it, not the whole mat.
    allow_partial_replacement: bool = True


@dataclass(frozen=True, slots=True)
class CostConfig:
    """All euro values are ASSUMPTIONS.  No supplier has been contacted and no
    dated quotation exists [S13-S22]."""

    mat_material_eur_per_m2: float = 240.0
    deployment_vessel_day_eur: float = 6500.0
    rov_survey_eur: float = 4200.0
    benthic_chamber_deployment_eur: float = 2800.0
    porewater_sample_eur: float = 180.0
    lab_hg_sample_eur: float = 210.0
    dgt_deployment_eur: float = 260.0
    tile_replacement_eur: float = 1900.0
    used_media_handling_eur_per_kg: float = 12.0
    sensor_check_eur: float = 350.0
    provenance: str = ProvenanceLabel.ASSUMPTION.value


@dataclass(frozen=True, slots=True)
class PlumeWindowConfig:
    """How the short 2-D plume windows are run.

    A reactive cap acts over years; a coastal plume equilibrates in hours.
    Marching the 2-D field for years would be unaffordable and pointless, so the
    coastal model is run over a short window at named mat states, and the two
    ledgers are reported separately and labelled.
    """

    #: One day covers about two M2 tidal cycles, and the plume crosses the
    #: domain in roughly two hours at these currents, so the field is well past
    #: quasi-steady. A longer window costs time and shows nothing new.
    window_s: float = 1.0 * _SECONDS_PER_DAY
    dt_s: float = 600.0
    #: Times, in years from the run start, at which to render a plume. Kept
    #: short by default so a full scenario sweep stays in the minutes, not the
    #: tens of minutes; the app renders further windows on demand.
    sample_years: Sequence[float] = (0.0, 3.0)


@dataclass(frozen=True, slots=True)
class RunConfig:
    run_id: str = "demo"
    scenario: str = "fresh_mat"
    seed: int = 20260908
    start_utc: str = "2026-09-08T00:00:00Z"
    #: Mat timeline: multi-year, because that is the timescale a cap works on.
    duration_s: float = 6.0 * _SECONDS_PER_YEAR
    #: Reactive-layer step.  The refinement study in the refactor plan shows the
    #: answer is converged at 6 h and unchanged down to 0.5 h.
    dt_s: float = 6.0 * 3600.0
    domain: DomainConfig = field(default_factory=DomainConfig)
    forcing: ForcingConfig = field(default_factory=ForcingConfig)
    hotspot: HotspotConfig = field(default_factory=HotspotConfig)
    mat: MatLayoutConfig = field(default_factory=MatLayoutConfig)
    degradation: DegradationConfig = field(default_factory=DegradationConfig)
    observations: ObservationConfig = field(default_factory=ObservationConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    costs: CostConfig = field(default_factory=CostConfig)
    plume: PlumeWindowConfig = field(default_factory=PlumeWindowConfig)
    elements: Sequence[str] = (
        Element.PB.value,
        Element.HG.value,
        Element.CU.value,
    )
    transport_engine: str = "fipy"
    layer_engine: str = "scipy_banded_implicit"
    ensemble_size: int = 64
    notes: str = ""

    @property
    def start_datetime(self) -> datetime:
        return datetime.fromisoformat(self.start_utc.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )

    @property
    def n_steps(self) -> int:
        return int(round(self.duration_s / self.dt_s))

    @property
    def duration_years(self) -> float:
        return self.duration_s / _SECONDS_PER_YEAR


def default_run_config(**overrides: Any) -> RunConfig:
    return RunConfig(**overrides)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


def config_to_dict(config: RunConfig) -> dict[str, Any]:
    payload = _to_jsonable(asdict(config))
    payload["config_version"] = CONFIG_VERSION
    return payload


def save_run_config(config: RunConfig, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(config_to_dict(config), indent=2, sort_keys=True), encoding="utf-8"
    )
    return target


def load_run_config(path: str | Path) -> RunConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload.pop("config_version", None)

    payload["domain"] = DomainConfig(
        **{
            **payload["domain"],
            "land_rectangles": tuple(
                tuple(rect) for rect in payload["domain"]["land_rectangles"]
            ),
        }
    )
    payload["forcing"] = ForcingConfig(**payload["forcing"])

    hotspot = dict(payload["hotspot"])
    hotspot["schedule"] = tuple(
        HotspotScheduleEntry(
            start_s=entry["start_s"],
            porewater_kg_per_m3=dict(entry["porewater_kg_per_m3"]),
            seepage_velocity_m_per_s=entry["seepage_velocity_m_per_s"],
        )
        for entry in hotspot["schedule"]
    )
    payload["hotspot"] = HotspotConfig(**hotspot)

    mat = dict(payload["mat"])
    mat["media"] = tuple(
        ReactiveMediumConfig(
            **{
                **medium,
                "kd_interval": tuple(medium["kd_interval"]),
                "q_max_interval": tuple(medium["q_max_interval"]),
                "k_rate_interval": tuple(medium["k_rate_interval"]),
                "d_eff_interval": tuple(medium["d_eff_interval"]),
            }
        )
        for medium in mat["media"]
    )
    mat["edge_leakage_interval"] = tuple(mat["edge_leakage_interval"])
    mat["preload_kg_per_m2"] = dict(mat["preload_kg_per_m2"])
    payload["mat"] = MatLayoutConfig(**mat)

    degradation = dict(payload["degradation"])
    degradation["events"] = tuple(
        DegradationEvent(**event) for event in degradation["events"]
    )
    payload["degradation"] = DegradationConfig(**degradation)

    observations = dict(payload["observations"])
    observations["stations"] = tuple(
        StationConfig(**station) for station in observations["stations"]
    )
    window = observations.get("sensor_dropout_window_s")
    observations["sensor_dropout_window_s"] = None if window is None else tuple(window)
    payload["observations"] = ObservationConfig(**observations)

    payload["policy"] = PolicyConfig(**payload["policy"])
    payload["costs"] = CostConfig(**payload["costs"])
    plume = dict(payload["plume"])
    plume["sample_years"] = tuple(plume["sample_years"])
    payload["plume"] = PlumeWindowConfig(**plume)
    payload["elements"] = tuple(payload["elements"])
    return RunConfig(**payload)


def config_hash(config: RunConfig) -> str:
    """Stable hash of a configuration, used for cache invalidation."""
    import hashlib

    blob = json.dumps(config_to_dict(config), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]
