"""Single coordinator-owned run configuration.

Every run records seed, time stepping, domain, forcing assumptions, source
schedule, panel geometry and material allocation, parameter ranges and their
provenance, observation schedule / noise / detection assumptions, laboratory
latency, service policy and assumed costs (``docs/DATA_CONTRACT.md``
section 4).

Every euro value and every material parameter in the defaults below is an
explicit **assumption** for a demonstration, not a quotation and not a measured
product specification.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import Element, ProvenanceLabel

CONFIG_VERSION = "0.1.0"

__all__ = [
    "CONFIG_VERSION",
    "DomainConfig",
    "ForcingConfig",
    "SourceScheduleEntry",
    "SourceConfig",
    "MaterialConfig",
    "PanelConfig",
    "StationConfig",
    "ObservationConfig",
    "PolicyConfig",
    "CostConfig",
    "RunConfig",
    "default_run_config",
    "load_run_config",
    "save_run_config",
    "config_hash",
]


@dataclass(frozen=True, slots=True)
class DomainConfig:
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
    mode: str = "synthetic"  # synthetic | real_map_illustrative | imported_forcing


@dataclass(frozen=True, slots=True)
class ForcingConfig:
    """Prescribed, physically simple current field.

    ``kind='steady'`` gives a constant eastward flow; ``kind='tidal'`` reverses
    it with period ``tidal_period_s``.  A de-tided or daily-mean external
    product may never be substituted for the tidal case [S10].
    """

    kind: str = "steady"  # steady | tidal
    u_mean_m_per_s: float = 0.12
    v_mean_m_per_s: float = 0.0
    tidal_amplitude_m_per_s: float = 0.18
    tidal_period_s: float = 44712.0  # M2, 12 h 25.2 min
    tidal_phase_rad: float = 0.0
    diffusivity_m2_per_s: float = 0.6
    provenance: str = ProvenanceLabel.SYNTHETIC_DEMO.value
    product_ref: str | None = None
    temporal_averaging: str = "instantaneous_synthetic"


@dataclass(frozen=True, slots=True)
class SourceScheduleEntry:
    """Piecewise-constant release rate, per element, in kg/s."""

    start_s: float
    rate_kg_per_s: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class SourceConfig:
    source_id: str = "hypothetical_source_1"
    x_m: float = 80.0
    y_m: float = 220.0
    schedule: Sequence[SourceScheduleEntry] = (
        SourceScheduleEntry(0.0, {"Pb": 2.0e-7, "Hg": 2.0e-9}),
    )
    label: str = ProvenanceLabel.SYNTHETIC_DEMO.value
    description: str = (
        "Hypothetical release for a demonstration. Not a located real hotspot; "
        "no claim about any particular wreck or site [S02-S03]."
    )


@dataclass(frozen=True, slots=True)
class MaterialConfig:
    """Reduced sorbent parameters per element, with uncertainty ranges.

    Values are a synthetic baseline chosen so a two-day demonstration shows
    loading and saturation.  They are not transferred from [S01]/[S04] as
    validated operating capacities.
    """

    element: str = Element.PB.value
    kd_m3_per_kg: float = 900.0
    kd_interval: tuple[float, float] = (300.0, 2700.0)
    q_max_kg_per_kg: float = 6.0e-5
    q_max_interval: tuple[float, float] = (2.0e-5, 1.2e-4)
    k_rate_per_s: float = 4.0e-4
    k_rate_interval: tuple[float, float] = (1.0e-4, 1.2e-3)
    allocation_fraction: float = 0.6
    fouling_rate_capacity: float = 0.4
    fouling_rate_kinetics: float = 0.8
    provenance: str = ProvenanceLabel.ASSUMPTION.value
    source_ref: str = "synthetic baseline, docs/MODEL_SPEC.md section 3"


@dataclass(frozen=True, slots=True)
class PanelConfig:
    panel_id: str = "panel_A"
    media_id: str = "media_A0"
    x_m: float = 300.0
    y_m: float = 220.0
    width_m: float = 4.0
    height_m: float = 2.0
    sorbent_mass_kg: float = 25.0
    interception_efficiency: float = 0.45
    interception_interval: tuple[float, float] = (0.15, 0.75)
    initial_fouling_fraction: float = 0.0
    #: Preloaded retained mass per element (kg), for an explicit stress test.
    preload_kg: Mapping[str, float] = field(default_factory=dict)
    materials: Sequence[MaterialConfig] = (
        MaterialConfig(),
        MaterialConfig(
            element=Element.HG.value,
            kd_m3_per_kg=1500.0,
            kd_interval=(200.0, 6000.0),
            q_max_kg_per_kg=2.0e-5,
            q_max_interval=(4.0e-6, 8.0e-5),
            k_rate_per_s=2.0e-4,
            k_rate_interval=(3.0e-5, 8.0e-4),
            allocation_fraction=0.4,
            source_ref=(
                "synthetic baseline; Hg uptake is strongly chemistry dependent [S04] "
                "and is not transferable from a different sorbent"
            ),
        ),
    )
    fouling_growth_per_s: float = 2.5e-6


@dataclass(frozen=True, slots=True)
class StationConfig:
    station_id: str
    x_m: float
    y_m: float
    depth_m: float = 3.0
    kind: str = "environmental"  # environmental | metal_probe | reference


@dataclass(frozen=True, slots=True)
class ObservationConfig:
    """Artificial schedules, not verified instrument cycle times."""

    environmental_period_s: float = 600.0
    metal_probe_period_s: float = 7200.0
    lab_sample_period_s: float = 43200.0
    lab_latency_s: float = 172800.0
    metal_probe_latency_s: float = 0.0
    metal_probe_relative_noise: float = 0.20
    metal_probe_lod_ng_per_l: float = 12.0
    metal_probe_loq_ng_per_l: float = 40.0
    lab_relative_noise: float = 0.08
    lab_lod_ng_per_l: float = 1.5
    lab_loq_ng_per_l: float = 5.0
    environmental_relative_noise: float = 0.02
    missing_probability: float = 0.03
    #: Simulated hard sensor dropout window, seconds from run start.
    sensor_dropout_window_s: tuple[float, float] | None = None
    sensor_drift_start_s: float | None = None
    sensor_drift_per_s: float = 0.0
    stations: Sequence[StationConfig] = (
        StationConfig("ST_UP", 200.0, 220.0, kind="metal_probe"),
        StationConfig("ST_DOWN", 400.0, 220.0, kind="metal_probe"),
        StationConfig("ST_ENV", 300.0, 250.0, kind="environmental"),
    )


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    """Maintenance policy.  ``kind='none'`` = no mesh at all."""

    kind: str = "evidence_informed"  # none | fixed | evidence_informed
    fixed_interval_s: float = 604800.0
    decision_period_s: float = 3600.0
    #: Recommend replacement when the estimated remaining capacity fraction is
    #: below this, with enough evidence.  Demo assumption, not a standard.
    replacement_loading_threshold: float = 0.80
    #: Widest acceptable relative interval before more evidence is requested.
    max_relative_interval_width: float = 1.2
    max_data_age_s: float = 21600.0
    min_evidence_records: int = 3
    inspection_loading_threshold: float = 0.55


@dataclass(frozen=True, slots=True)
class CostConfig:
    """All euro values are ASSUMPTIONS. No dated quotation exists [S13-S22]."""

    vessel_visit_eur: float = 1800.0
    chemical_sample_eur: float = 140.0
    lab_hg_sample_eur: float = 210.0
    sorbent_eur_per_kg: float = 55.0
    used_media_handling_eur_per_kg: float = 12.0
    sensor_check_eur: float = 350.0
    inspection_eur: float = 900.0
    provenance: str = ProvenanceLabel.ASSUMPTION.value


@dataclass(frozen=True, slots=True)
class RunConfig:
    run_id: str = "demo"
    scenario: str = "baseline"
    seed: int = 20260908
    start_utc: str = "2026-09-08T00:00:00Z"
    duration_s: float = 259200.0  # 3 simulated days
    dt_s: float = 60.0
    #: Simulated seconds per wall-clock scene; used only for display pacing.
    time_acceleration_note: str = (
        "Saturation is reached by accelerating time or by preloading a panel, "
        "never by inflating uptake parameters."
    )
    domain: DomainConfig = field(default_factory=DomainConfig)
    forcing: ForcingConfig = field(default_factory=ForcingConfig)
    source: SourceConfig = field(default_factory=SourceConfig)
    panels: Sequence[PanelConfig] = field(default_factory=lambda: (PanelConfig(),))
    observations: ObservationConfig = field(default_factory=ObservationConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    costs: CostConfig = field(default_factory=CostConfig)
    elements: Sequence[str] = (Element.PB.value, Element.HG.value)
    transport_engine: str = "fipy"
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


def _rebuild(cls: Any, payload: Mapping[str, Any]) -> Any:
    return cls(**payload)


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
    source = dict(payload["source"])
    source["schedule"] = tuple(
        SourceScheduleEntry(entry["start_s"], dict(entry["rate_kg_per_s"]))
        for entry in source["schedule"]
    )
    payload["source"] = SourceConfig(**source)
    panels = []
    for panel in payload["panels"]:
        panel = dict(panel)
        panel["materials"] = tuple(
            MaterialConfig(
                **{
                    **material,
                    "kd_interval": tuple(material["kd_interval"]),
                    "q_max_interval": tuple(material["q_max_interval"]),
                    "k_rate_interval": tuple(material["k_rate_interval"]),
                }
            )
            for material in panel["materials"]
        )
        panel["interception_interval"] = tuple(panel["interception_interval"])
        panel["preload_kg"] = dict(panel["preload_kg"])
        panels.append(PanelConfig(**panel))
    payload["panels"] = tuple(panels)
    observations = dict(payload["observations"])
    observations["stations"] = tuple(
        StationConfig(**station) for station in observations["stations"]
    )
    window = observations.get("sensor_dropout_window_s")
    observations["sensor_dropout_window_s"] = None if window is None else tuple(window)
    payload["observations"] = ObservationConfig(**observations)
    payload["policy"] = PolicyConfig(**payload["policy"])
    payload["costs"] = CostConfig(**payload["costs"])
    payload["elements"] = tuple(payload["elements"])
    return RunConfig(**payload)


def config_hash(config: RunConfig) -> str:
    """Stable hash of a configuration, used for cache invalidation."""
    import hashlib

    blob = json.dumps(config_to_dict(config), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]
