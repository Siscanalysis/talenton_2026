"""A small deterministic design and maintenance comparison.

A few sorbent masses crossed with a few fixed service intervals, each run
across the parameter ensemble of ``material.sample_parameter_ensemble``, on a
scripted contact scenario that needs no map and no hardware.  The output is a
list of plain dictionaries so the presentation branch can render it without
re-running anything.

What the numbers are, and are not
---------------------------------

* ``captured_kg`` is what the reduced model of MODEL_SPEC section 4 removes
  from the contact region over the horizon, summed over service cycles.
* ``delivered_kg`` is the metal carried through the panel's *intercepted*
  frontal area over the horizon: ``c * s * A * phi * dt`` summed.  It is not
  the source's whole release, and it is not a domain-wide budget.
* ``escaped_kg = delivered_kg - captured_kg`` is therefore escape **past this
  panel within the modelled contact region**.  A domain-wide escape figure
  needs the transport branch and its boundary accounting.
* every euro figure is an ``assumption`` from ``config.CostConfig``.  No
  quotation exists.
* recovered media is metal-loaded waste with a handling cost.  This module
  books **no revenue** for it: see ``service.MEDIA_DISPOSAL_NOTE``.

The comparison deliberately includes a weak-benefit variant (slow kinetics and
poor interception).  A high capacity is not a performance claim: if the water
misses the panel, or the material takes a fortnight to approach equilibrium,
the servicing cost buys very little captured metal, and the table says so.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..config import CostConfig, PanelConfig
from ..contracts import MaterialParameters, ProvenanceLabel
from ..units import from_si_mass
from .forecast import loading_fraction
from .material import (
    ParameterEnsemble,
    build_material_map,
    sample_parameter_ensemble,
    scale_material,
    sequence_of_elements,
)
from .panel import advance_panel, build_panel_state, scripted_contact_batch
from .service import MEDIA_DISPOSAL_NOTE, RetrievedMediaLedger, replace_media

__all__ = [
    "DesignScenario",
    "DesignOption",
    "DEFAULT_SCENARIOS",
    "DEFAULT_SORBENT_MASSES_KG",
    "DEFAULT_SERVICE_INTERVALS_S",
    "WEAK_BENEFIT_YIELD_MG_PER_1000_EUR",
    "WEAK_BENEFIT_CAPTURE_FRACTION",
    "run_design_comparison",
    "design_comparison_document",
    "write_design_comparison",
]

#: Assumed thresholds used only to *label* a row as weak-benefit.  They are
#: presentation thresholds, not a standard and not a compliance limit.
WEAK_BENEFIT_YIELD_MG_PER_1000_EUR = 50.0
WEAK_BENEFIT_CAPTURE_FRACTION = 0.02

_DAY_S = 86400.0


@dataclass(frozen=True, slots=True)
class DesignScenario:
    """A scripted, deterministic contact scenario.  Every field is assumed.

    ``k_rate_scale`` and ``kd_scale`` are explicit material what-ifs: they let
    the weak-benefit variant be a stated change of the material, rather than a
    hidden tweak buried in a loop.
    """

    name: str
    concentration_kg_per_m3: Mapping[str, float]
    speed_m_per_s: float
    horizon_s: float
    dt_s: float
    interception_efficiency: float
    interception_interval: tuple[float, float]
    fouling_growth_per_s: float
    k_rate_scale: float = 1.0
    kd_scale: float = 1.0
    note: str = ""


@dataclass(frozen=True, slots=True)
class DesignOption:
    """One design point: how much sorbent, serviced how often."""

    sorbent_mass_kg: float
    #: ``None`` means "no replacement inside the horizon".
    service_interval_s: float | None


#: Baseline plume: an elevated, synthetic near-source concentration chosen so
#: the panel both saturates and runs out of supply inside a week.  20 ug/L of
#: dissolved Pb is far above open-sea background; it is a demonstration value,
#: not an observation of anywhere.
_BASELINE = DesignScenario(
    name="elevated_plume",
    concentration_kg_per_m3={"Pb": 1.0e-7, "Hg": 2.0e-9},  # assumption
    speed_m_per_s=0.12,  # assumption, matches ForcingConfig.u_mean_m_per_s
    horizon_s=7.0 * _DAY_S,
    dt_s=1800.0,
    interception_efficiency=0.45,  # assumption, PanelConfig default
    interception_interval=(0.15, 0.75),
    fouling_growth_per_s=2.5e-6,  # assumption, PanelConfig default
    note=(
        "Synthetic elevated plume. Concentrations are demonstration values, "
        "not measurements from any site."
    ),
)

#: The unfavourable case the build brief asks for: the same water, a material
#: that approaches equilibrium ~500 times more slowly, and a panel that most of
#: the flow simply misses.  Capacity is unchanged, so this is precisely the
#: "high capacity, negligible capture" outcome of MODEL_SPEC section 4.
_WEAK = DesignScenario(
    name="slow_material_poor_contact",
    concentration_kg_per_m3={"Pb": 1.0e-7, "Hg": 2.0e-9},
    speed_m_per_s=0.12,
    horizon_s=7.0 * _DAY_S,
    dt_s=1800.0,
    interception_efficiency=0.06,  # assumption: most water misses the panel
    interception_interval=(0.02, 0.12),
    fouling_growth_per_s=2.5e-6,
    k_rate_scale=0.002,  # assumption: minutes-scale kinetics become weeks-scale
    note=(
        "Deliberately unfavourable variant: same capacity, slow uptake and poor "
        "interception. Included so the comparison is not tuned to succeed."
    ),
)

DEFAULT_SCENARIOS: tuple[DesignScenario, ...] = (_BASELINE, _WEAK)

DEFAULT_SORBENT_MASSES_KG: tuple[float, ...] = (10.0, 25.0, 60.0)
DEFAULT_SERVICE_INTERVALS_S: tuple[float | None, ...] = (
    1.0 * _DAY_S,
    3.0 * _DAY_S,
    None,
)


# ---------------------------------------------------------------------------
# One deterministic trajectory
# ---------------------------------------------------------------------------

def _simulate_member(
    scenario: DesignScenario,
    option: DesignOption,
    materials: Mapping[str, MaterialParameters],
    interception_efficiency: float,
    base_panel_config: PanelConfig,
    start_utc: datetime,
    costs: CostConfig,
) -> dict[str, Any]:
    """Run one ensemble member through one design option.  Pure and repeatable."""
    elements = sequence_of_elements(materials)
    panel_config = replace(
        base_panel_config,
        sorbent_mass_kg=float(option.sorbent_mass_kg),
        interception_efficiency=float(interception_efficiency),
        interception_interval=scenario.interception_interval,
        fouling_growth_per_s=float(scenario.fouling_growth_per_s),
        preload_kg={},
        initial_fouling_fraction=0.0,
    )
    state = build_panel_state(panel_config, start_utc, materials)
    ledger = RetrievedMediaLedger()

    captured = {key: 0.0 for key in elements}
    delivered = {key: 0.0 for key in elements}
    environment = {"fouling_growth_per_s": float(scenario.fouling_growth_per_s)}

    dt_s = float(scenario.dt_s)
    horizon_s = float(scenario.horizon_s)
    n_steps = int(round(horizon_s / dt_s))
    interval = option.service_interval_s
    next_service_s = float(interval) if interval else None

    elapsed_s = 0.0
    for _ in range(n_steps):
        time_utc = start_utc + timedelta(seconds=elapsed_s)
        batch = scripted_contact_batch(
            state,
            time_utc,
            dt_s,
            scenario.concentration_kg_per_m3,
            scenario.speed_m_per_s,
            interception_efficiency=interception_efficiency,
            environment=environment,
        )
        step = advance_panel(state, batch, materials, dt_s)
        state = step.new_state
        for key in elements:
            captured[key] += float(step.uptake_kg_by_element.get(key, 0.0))
            delivered[key] += float(batch.available_kg.get(key, 0.0))
        elapsed_s += dt_s

        if (
            next_service_s is not None
            and elapsed_s >= next_service_s - 1e-9
            and elapsed_s < horizon_s - 1e-9
        ):
            state, _event = replace_media(
                state,
                start_utc + timedelta(seconds=elapsed_s),
                ledger=ledger,
                costs=costs,
            )
            next_service_s += float(interval)  # type: ignore[arg-type]

    final_fraction = {
        key: loading_fraction(
            float(state.retained_kg.get(key, 0.0)),
            state.sorbent_mass_kg,
            materials[key],
            state.fouling_fraction,
        )
        for key in elements
    }

    return {
        "captured_kg": captured,
        "delivered_kg": delivered,
        "escaped_kg": {
            key: max(0.0, delivered[key] - captured[key]) for key in elements
        },
        "replacements": ledger.service_count,
        "final_loading_fraction": final_fraction,
        "final_fouling_fraction": state.fouling_fraction,
        "retrieved_kg": dict(ledger.totals_kg),
        "active_kg": {key: float(state.retained_kg.get(key, 0.0)) for key in elements},
    }


def _percentiles(values: Sequence[float], interval_level: float) -> list[float]:
    lower = 100.0 * (1.0 - interval_level) / 2.0
    upper = 100.0 * (1.0 + interval_level) / 2.0
    array = np.asarray(values, dtype=float)
    return [float(np.percentile(array, lower)), float(np.percentile(array, upper))]


def _cost_breakdown(
    costs: CostConfig, sorbent_mass_kg: float, replacements: int
) -> dict[str, float]:
    """Assumed euro cost of one design option over the horizon.

    The first media fill is charged; the deployment visit that installs the
    panel is not, because it happens in every option including "no servicing"
    and would only add a constant.  Each replacement is charged a vessel visit,
    a fresh media fill and the handling of the retrieved, metal-loaded media.
    """
    initial_media = float(costs.sorbent_eur_per_kg) * float(sorbent_mass_kg)
    vessel = float(costs.vessel_visit_eur) * replacements
    new_media = float(costs.sorbent_eur_per_kg) * float(sorbent_mass_kg) * replacements
    handling = (
        float(costs.used_media_handling_eur_per_kg)
        * float(sorbent_mass_kg)
        * replacements
    )
    return {
        "initial_media_eur": initial_media,
        "vessel_visits_eur": vessel,
        "replacement_media_eur": new_media,
        "used_media_handling_eur": handling,
        "total_eur": initial_media + vessel + new_media + handling,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_design_comparison(
    *,
    scenarios: Sequence[DesignScenario] = DEFAULT_SCENARIOS,
    sorbent_masses_kg: Sequence[float] = DEFAULT_SORBENT_MASSES_KG,
    service_intervals_s: Sequence[float | None] = DEFAULT_SERVICE_INTERVALS_S,
    panel_config: PanelConfig | None = None,
    costs: CostConfig | None = None,
    ensemble_size: int = 16,
    seed: int = 20260908,
    interval_level: float = 0.90,
    start_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    """Deterministic design study.  Same arguments in, same rows out.

    One row per (scenario, sorbent mass, service interval).  Central values are
    ensemble medians; ``*_interval`` entries are the 5th and 95th percentiles
    at the default ``interval_level``.
    """
    base_panel = panel_config or PanelConfig()
    cost_config = costs or CostConfig()
    start = start_utc or datetime(2026, 9, 8, tzinfo=timezone.utc)
    nominal_materials = build_material_map(base_panel)

    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_materials = {
            key: scale_material(
                params,
                kd_scale=scenario.kd_scale,
                k_rate_scale=scenario.k_rate_scale,
                source_ref=(
                    f"{params.source_ref}; scenario variant {scenario.name!r} "
                    f"(k x {scenario.k_rate_scale}, Kd x {scenario.kd_scale})"
                ),
            )
            for key, params in nominal_materials.items()
        }
        ensemble: ParameterEnsemble = sample_parameter_ensemble(
            scenario_materials,
            ensemble_size,
            seed,
            interception_nominal=scenario.interception_efficiency,
            interception_interval=scenario.interception_interval,
        )
        elements = sequence_of_elements(scenario_materials)

        for mass in sorbent_masses_kg:
            for interval in service_intervals_s:
                option = DesignOption(float(mass), interval)
                member_results = [
                    _simulate_member(
                        scenario,
                        option,
                        ensemble.members[index],
                        ensemble.interception_efficiency[index],
                        base_panel,
                        start,
                        cost_config,
                    )
                    for index in range(ensemble.size)
                ]

                replacements = member_results[0]["replacements"]
                cost = _cost_breakdown(cost_config, float(mass), replacements)

                captured_median: dict[str, float] = {}
                captured_interval: dict[str, list[float]] = {}
                delivered_median: dict[str, float] = {}
                escaped_median: dict[str, float] = {}
                escaped_interval: dict[str, list[float]] = {}
                capture_fraction: dict[str, float] = {}
                loading_median: dict[str, float] = {}
                yield_mg: dict[str, float] = {}
                for key in elements:
                    captured = [result["captured_kg"][key] for result in member_results]
                    delivered = [result["delivered_kg"][key] for result in member_results]
                    escaped = [result["escaped_kg"][key] for result in member_results]
                    fractions = [
                        (
                            result["captured_kg"][key] / result["delivered_kg"][key]
                            if result["delivered_kg"][key] > 0.0
                            else 0.0
                        )
                        for result in member_results
                    ]
                    loading = [
                        result["final_loading_fraction"][key] for result in member_results
                    ]
                    captured_median[key] = float(np.median(captured))
                    captured_interval[key] = _percentiles(captured, interval_level)
                    delivered_median[key] = float(np.median(delivered))
                    escaped_median[key] = float(np.median(escaped))
                    escaped_interval[key] = _percentiles(escaped, interval_level)
                    capture_fraction[key] = float(np.median(fractions))
                    loading_median[key] = float(np.median(loading))
                    yield_mg[key] = (
                        from_si_mass(captured_median[key], "mg") / (cost["total_eur"] / 1000.0)
                        if cost["total_eur"] > 0.0
                        else 0.0
                    )

                primary = elements[0]
                weak = (
                    yield_mg[primary] < WEAK_BENEFIT_YIELD_MG_PER_1000_EUR
                    or capture_fraction[primary] < WEAK_BENEFIT_CAPTURE_FRACTION
                )
                reasons = []
                if yield_mg[primary] < WEAK_BENEFIT_YIELD_MG_PER_1000_EUR:
                    reasons.append(
                        f"{primary} yield {yield_mg[primary]:.1f} mg per 1000 EUR is "
                        f"below the assumed {WEAK_BENEFIT_YIELD_MG_PER_1000_EUR:.0f}"
                    )
                if capture_fraction[primary] < WEAK_BENEFIT_CAPTURE_FRACTION:
                    reasons.append(
                        f"{primary} capture fraction {capture_fraction[primary]:.3f} is "
                        f"below the assumed {WEAK_BENEFIT_CAPTURE_FRACTION}"
                    )

                rows.append(
                    {
                        "scenario": scenario.name,
                        "scenario_note": scenario.note,
                        "elements": list(elements),
                        "sorbent_mass_kg": float(mass),
                        "service_interval_s": (
                            None if interval is None else float(interval)
                        ),
                        "service_interval_days": (
                            None if interval is None else float(interval) / _DAY_S
                        ),
                        "horizon_s": float(scenario.horizon_s),
                        "dt_s": float(scenario.dt_s),
                        "replacements": int(replacements),
                        "ensemble_size": ensemble.size,
                        "interval_level": float(interval_level),
                        "captured_kg": captured_median,
                        "captured_kg_interval": captured_interval,
                        "delivered_kg": delivered_median,
                        "escaped_kg": escaped_median,
                        "escaped_kg_interval": escaped_interval,
                        "capture_fraction_of_delivered": capture_fraction,
                        "final_loading_fraction": loading_median,
                        "assumed_cost_eur": cost["total_eur"],
                        "assumed_cost_breakdown_eur": cost,
                        "captured_mg_per_1000_eur": yield_mg,
                        "weak_benefit": bool(weak),
                        "weak_benefit_reasons": reasons,
                        "revenue_eur": None,
                        "revenue_note": MEDIA_DISPOSAL_NOTE,
                        "escaped_definition": (
                            "delivered to the panel minus captured, inside the "
                            "modelled contact region; not a domain-wide budget"
                        ),
                        "cost_provenance": ProvenanceLabel.ASSUMPTION.value,
                        "model_provenance": ProvenanceLabel.SYNTHETIC_DEMO.value,
                    }
                )
    return rows


def design_comparison_document(
    rows: Sequence[Mapping[str, Any]],
    *,
    scenarios: Sequence[DesignScenario] = DEFAULT_SCENARIOS,
    costs: CostConfig | None = None,
    seed: int = 20260908,
) -> dict[str, Any]:
    """Wrap the rows with the assumptions they depend on, ready for JSON."""
    cost_config = costs or CostConfig()
    return {
        "kind": "micro_design_comparison",
        "model_ref": "docs/MODEL_SPEC.md section 4",
        "seed": int(seed),
        "generated_by": "mesh_demo.micro.design.run_design_comparison",
        "scenarios": [
            {
                "name": scenario.name,
                "concentration_kg_per_m3": dict(scenario.concentration_kg_per_m3),
                "speed_m_per_s": scenario.speed_m_per_s,
                "horizon_s": scenario.horizon_s,
                "dt_s": scenario.dt_s,
                "interception_efficiency": scenario.interception_efficiency,
                "interception_interval": list(scenario.interception_interval),
                "fouling_growth_per_s": scenario.fouling_growth_per_s,
                "k_rate_scale": scenario.k_rate_scale,
                "kd_scale": scenario.kd_scale,
                "note": scenario.note,
                "provenance": ProvenanceLabel.ASSUMPTION.value,
            }
            for scenario in scenarios
        ],
        "cost_assumptions_eur": {
            "vessel_visit_eur": cost_config.vessel_visit_eur,
            "sorbent_eur_per_kg": cost_config.sorbent_eur_per_kg,
            "used_media_handling_eur_per_kg": cost_config.used_media_handling_eur_per_kg,
            "provenance": ProvenanceLabel.ASSUMPTION.value,
            "note": "No dated quotation exists for any of these figures.",
        },
        "weak_benefit_thresholds": {
            "captured_mg_per_1000_eur": WEAK_BENEFIT_YIELD_MG_PER_1000_EUR,
            "capture_fraction_of_delivered": WEAK_BENEFIT_CAPTURE_FRACTION,
            "provenance": ProvenanceLabel.ASSUMPTION.value,
            "note": "Presentation thresholds only; not a standard or a limit.",
        },
        "revenue_note": MEDIA_DISPOSAL_NOTE,
        "limitations": [
            "Single-panel, single-cell scripted contact; no map and no transport "
            "solver behind these numbers.",
            "Escaped mass is escape past this panel, not a domain-wide budget.",
            "Uncertainty is the configured parameter range, not a fitted posterior.",
        ],
        "rows": [dict(row) for row in rows],
    }


def write_design_comparison(
    rows: Sequence[Mapping[str, Any]],
    path: str | Path,
    *,
    scenarios: Sequence[DesignScenario] = DEFAULT_SCENARIOS,
    costs: CostConfig | None = None,
    seed: int = 20260908,
) -> Path:
    """Write the design comparison as a single JSON document."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    document = design_comparison_document(
        rows, scenarios=scenarios, costs=costs, seed=seed
    )
    target.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
    return target
