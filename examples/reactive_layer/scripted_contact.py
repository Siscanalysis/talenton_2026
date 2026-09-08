"""Scripted contact sequence for the reduced material model.

Runs entirely offline: no map, no hardware, no network, no solver.  Two panels
see exactly the same scripted water, so every difference between them comes
from their material state:

``panel_A``
    fresh media at t = 0.
``panel_P``
    explicitly **preloaded** media (the stress-test panel of the build brief),
    so saturation is reached without inflating any uptake parameter.

The scripted sequence walks through the scenes the brief asks for:

1. ``low_contact``      almost still water and a very low concentration;
2. ``steady_plume``     ordinary contact on fresh material;
3. ``source_increase``  the concentration rises four-fold;
4. ``heavy_fouling``    the fouling growth rate rises, so access and rate fall;
5. a damage / desorption event that returns metal to the water explicitly;
6. ``after_service``    ``panel_P`` gets new media and starts capturing again.

Every number printed is a synthetic demonstration value.  None of it is a
measurement, a product specification or a validated capacity.

Run it::

    .venv\\Scripts\\python.exe examples/micro/scripted_contact.py
    .venv\\Scripts\\python.exe examples/micro/scripted_contact.py --out somewhere
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:  # let the example run from a plain checkout
    sys.path.insert(0, str(_SRC))

from reactive_seabed_mat.config import CostConfig, PanelConfig  # noqa: E402
from reactive_seabed_mat.reactive_layer import (  # noqa: E402
    RetrievedMediaLedger,
    advance_panel,
    build_material_map,
    build_panel_state,
    forecast_panel,
    release_from_damage,
    replace_media,
    scripted_contact_batch,
)
from reactive_seabed_mat.units import format_utc, from_si_aqueous_concentration, from_si_mass  # noqa: E402

HOUR_S = 3600.0
DT_S = 900.0  # assumption: a quarter-hour material step for the demonstration
START_UTC = datetime(2026, 9, 8, tzinfo=timezone.utc)

#: Fouling growth rates are assumptions chosen so the fouling scene is visible
#: within four simulated days.  They are not a measured biofouling rate.
BASE_FOULING_GROWTH_PER_S = 1.0e-6
HEAVY_FOULING_GROWTH_PER_S = 6.0e-6


@dataclass(frozen=True)
class Phase:
    """One scripted stretch of water.  Every field is an assumption."""

    name: str
    end_h: float
    speed_m_per_s: float
    concentration_kg_per_m3: Mapping[str, float]
    fouling_growth_per_s: float
    note: str


PHASES: tuple[Phase, ...] = (
    Phase(
        "low_contact",
        6.0,
        0.005,
        {"Pb": 2.0e-9, "Hg": 4.0e-11},
        BASE_FOULING_GROWTH_PER_S,
        "Almost still water and a near-background concentration: very little "
        "reaches the panel, so very little is captured.",
    ),
    Phase(
        "steady_plume",
        30.0,
        0.12,
        {"Pb": 4.0e-8, "Hg": 8.0e-10},
        BASE_FOULING_GROWTH_PER_S,
        "Ordinary contact. The fresh panel loads; the preloaded panel has "
        "little capacity left to use.",
    ),
    Phase(
        "source_increase",
        54.0,
        0.12,
        {"Pb": 1.6e-7, "Hg": 3.2e-9},
        BASE_FOULING_GROWTH_PER_S,
        "The concentration rises four-fold. More metal is delivered, so "
        "capacity is consumed faster.",
    ),
    Phase(
        "heavy_fouling",
        78.0,
        0.12,
        {"Pb": 1.6e-7, "Hg": 3.2e-9},
        HEAVY_FOULING_GROWTH_PER_S,
        "Fouling grows quickly: the rate and the accessible capacity fall, "
        "but no sorbed metal is lost.",
    ),
    Phase(
        "after_service",
        96.0,
        0.12,
        {"Pb": 1.6e-7, "Hg": 3.2e-9},
        BASE_FOULING_GROWTH_PER_S,
        "panel_P has new media: capacity is reset and capture resumes, while "
        "the retrieved metal stays in the ledger.",
    ),
)

RELEASE_AT_H = 66.0
RELEASE_FRACTION = 0.08
REPLACE_PANEL_P_AT_H = 78.0

ELEMENTS = ("Pb", "Hg")


def phase_at(elapsed_h: float) -> Phase:
    for phase in PHASES:
        if elapsed_h < phase.end_h - 1e-9:
            return phase
    return PHASES[-1]


def build_panels() -> tuple[dict[str, Any], dict[str, Any]]:
    """Fresh panel_A and explicitly preloaded panel_P, plus their materials."""
    base = PanelConfig()
    materials = build_material_map(base)

    fresh_config = replace(
        base,
        panel_id="panel_A",
        media_id="media_A0",
        preload_kg={},
        fouling_growth_per_s=BASE_FOULING_GROWTH_PER_S,
    )

    # Preload: 70 % of the Pb compartment and 40 % of the Hg compartment.  It
    # is an explicit stress test, not a measured initial condition.
    pb = materials["Pb"]
    hg = materials["Hg"]
    preload = {
        "Pb": 0.70 * base.sorbent_mass_kg * pb.allocation_fraction * pb.q_max_kg_per_kg,
        "Hg": 0.40 * base.sorbent_mass_kg * hg.allocation_fraction * hg.q_max_kg_per_kg,
    }
    preloaded_config = replace(
        base,
        panel_id="panel_P",
        media_id="media_P0",
        preload_kg=preload,
        fouling_growth_per_s=BASE_FOULING_GROWTH_PER_S,
    )

    panels = {
        "panel_A": build_panel_state(fresh_config, START_UTC, materials),
        "panel_P": build_panel_state(preloaded_config, START_UTC, materials),
    }
    return panels, materials


def run_timeline() -> dict[str, Any]:
    """Step the two panels through the scripted sequence and record everything."""
    panels, materials = build_panels()
    ledgers = {key: RetrievedMediaLedger() for key in panels}
    costs = CostConfig()

    delivered = {key: {element: 0.0 for element in ELEMENTS} for key in panels}
    captured = {key: {element: 0.0 for element in ELEMENTS} for key in panels}
    released = {key: {element: 0.0 for element in ELEMENTS} for key in panels}

    rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    n_steps = int(round(PHASES[-1].end_h * HOUR_S / DT_S))
    for index in range(n_steps):
        elapsed_s = index * DT_S
        elapsed_h = elapsed_s / HOUR_S
        phase = phase_at(elapsed_h)
        time_utc = START_UTC + timedelta(seconds=elapsed_s)

        for panel_id, state in list(panels.items()):
            batch = scripted_contact_batch(
                state,
                time_utc,
                DT_S,
                phase.concentration_kg_per_m3,
                phase.speed_m_per_s,
                environment={"fouling_growth_per_s": phase.fouling_growth_per_s},
            )
            step = advance_panel(state, batch, materials, DT_S)
            panels[panel_id] = step.new_state

            for element in ELEMENTS:
                delivered[panel_id][element] += float(batch.available_kg.get(element, 0.0))
                captured[panel_id][element] += float(
                    step.uptake_kg_by_element.get(element, 0.0)
                )

            rows.append(
                {
                    "time_utc": format_utc(time_utc),
                    "elapsed_s": elapsed_s,
                    "elapsed_h": elapsed_h,
                    "phase": phase.name,
                    "panel_id": panel_id,
                    "media_id": step.new_state.media_id,
                    "service_count": step.new_state.service_count,
                    "speed_m_per_s": phase.speed_m_per_s,
                    "concentration_kg_per_m3": dict(batch.concentration_kg_per_m3),
                    "available_kg": dict(batch.available_kg),
                    "exchange_volume_m3": batch.exchange_volume_m3,
                    "exchange_is_measured": batch.exchange_is_measured,
                    "uptake_kg": dict(step.uptake_kg_by_element),
                    "release_kg": dict(step.release_kg_by_element),
                    "retained_kg": dict(step.new_state.retained_kg),
                    "fouling_fraction": step.new_state.fouling_fraction,
                    "binding_constraint": dict(step.diagnostics["binding_constraint"]),
                    "remaining_capacity_kg": dict(
                        step.diagnostics["remaining_capacity_kg"]
                    ),
                    "loading_fraction": dict(step.diagnostics["loading_fraction_after"]),
                    "effective_q_max_kg_per_kg": dict(
                        step.diagnostics["effective_q_max_kg_per_kg"]
                    ),
                    "effective_rate_per_s": dict(step.diagnostics["effective_rate_per_s"]),
                    "corrections": list(step.diagnostics["corrections"]),
                }
            )

        next_elapsed_h = (elapsed_s + DT_S) / HOUR_S

        # Explicit damage / desorption on the preloaded panel: the mesh loses
        # exactly what the water gains, and the transport solver is told how
        # much and into which cells.
        if elapsed_h < RELEASE_AT_H <= next_elapsed_h:
            state = panels["panel_P"]
            batch = scripted_contact_batch(
                state,
                time_utc,
                0.0,
                phase.concentration_kg_per_m3,
                phase.speed_m_per_s,
            )
            step = release_from_damage(
                state,
                batch,
                released_fraction_by_element={"Pb": RELEASE_FRACTION},
                reason="assumed abrasion of the outer media layer",
            )
            panels["panel_P"] = step.new_state
            for element in ELEMENTS:
                released["panel_P"][element] += float(
                    step.release_kg_by_element.get(element, 0.0)
                )
            events.append(
                {
                    "time_utc": format_utc(time_utc),
                    "elapsed_h": elapsed_h,
                    "kind": "damage_release",
                    "panel_id": "panel_P",
                    "release_kg": dict(step.release_kg_by_element),
                    "cell_indices": list(batch.cell_indices),
                    "cell_weights": list(batch.cell_weights),
                    "note": (
                        "apply_transfers must add exactly this mass back to the "
                        "contact cells: nothing is destroyed"
                    ),
                }
            )

        if elapsed_h < REPLACE_PANEL_P_AT_H <= next_elapsed_h:
            state = panels["panel_P"]
            new_state, event = replace_media(
                state,
                time_utc,
                ledger=ledgers["panel_P"],
                costs=costs,
            )
            panels["panel_P"] = new_state
            events.append(
                {
                    "time_utc": format_utc(event.time_utc),
                    "elapsed_h": elapsed_h,
                    "kind": event.kind,
                    "panel_id": event.panel_id,
                    "old_media_id": event.old_media_id,
                    "new_media_id": event.new_media_id,
                    "retrieved_kg": dict(event.retrieved_kg),
                    "assumed_cost_eur": event.cost_eur,
                    "execution_mode": event.execution_mode,
                    "note": (
                        "Capacity resets, captured mass moves to the "
                        "retrieved-media ledger. No mass is created or destroyed."
                    ),
                }
            )

    # Conditional forecast at the end of the run, under the last phase's water.
    forecasts = {
        panel_id: forecast_panel(
            state,
            materials,
            PHASES[-1].concentration_kg_per_m3,
            ensemble_size=64,
            seed=20260908,
            time_utc=START_UTC + timedelta(seconds=n_steps * DT_S),
        ).to_dict()
        for panel_id, state in panels.items()
    }

    ledger_check = {}
    for panel_id in panels:
        per_element = {}
        for element in ELEMENTS:
            active = float(panels[panel_id].retained_kg.get(element, 0.0))
            retrieved = ledgers[panel_id].total_kg(element)
            accounted = active + retrieved + released[panel_id][element]
            per_element[element] = {
                "delivered_to_panel_kg": delivered[panel_id][element],
                "captured_kg": captured[panel_id][element],
                "escaped_past_panel_kg": (
                    delivered[panel_id][element] - captured[panel_id][element]
                ),
                "in_active_mesh_kg": active,
                "in_retrieved_media_kg": retrieved,
                "released_back_to_water_kg": released[panel_id][element],
                "captured_minus_accounted_kg": captured[panel_id][element] - accounted,
            }
        ledger_check[panel_id] = per_element

    return {
        "kind": "micro_scripted_contact_timeline",
        "model_ref": "docs/MODEL_SPEC.md section 4",
        "generated_by": "examples/micro/scripted_contact.py",
        "start_utc": format_utc(START_UTC),
        "dt_s": DT_S,
        "elements": list(ELEMENTS),
        "phases": [
            {
                "name": phase.name,
                "end_h": phase.end_h,
                "speed_m_per_s": phase.speed_m_per_s,
                "concentration_kg_per_m3": dict(phase.concentration_kg_per_m3),
                "fouling_growth_per_s": phase.fouling_growth_per_s,
                "note": phase.note,
            }
            for phase in PHASES
        ],
        "panels": {
            panel_id: {
                "media_id": state.media_id,
                "sorbent_mass_kg": state.sorbent_mass_kg,
                "service_count": state.service_count,
                "fouling_fraction": state.fouling_fraction,
                "retained_kg": dict(state.retained_kg),
            }
            for panel_id, state in panels.items()
        },
        "materials": {
            key: {
                "kd_m3_per_kg": params.kd_m3_per_kg,
                "q_max_kg_per_kg": params.q_max_kg_per_kg,
                "k_rate_per_s": params.k_rate_per_s,
                "allocation_fraction": params.allocation_fraction,
                "fouling_rate_capacity": params.fouling_rate_capacity,
                "fouling_rate_kinetics": params.fouling_rate_kinetics,
                "provenance": params.provenance.value,
                "source_ref": params.source_ref,
            }
            for key, params in materials.items()
        },
        "events": events,
        "retrieved_media_ledger": {
            panel_id: ledger.as_dict() for panel_id, ledger in ledgers.items()
        },
        "mass_check": ledger_check,
        "forecast": forecasts,
        "rows": rows,
        "limitations": [
            "Scripted contact: there is no transport solver and no map behind "
            "these concentrations.",
            "Every material parameter, schedule and euro value is an assumption.",
            "Remaining life is conditional on the assumed water persisting; it "
            "is not a measurement.",
        ],
    }


def print_timeline(document: Mapping[str, Any], every_h: float = 6.0) -> None:
    """A small, readable table.  Display units only, SI stays in the JSON."""
    print("Scripted contact sequence, reduced material model (synthetic demo)")
    print(f"start {document['start_utc']}   dt {document['dt_s']:.0f} s")
    print()
    header = (
        f"{'h':>5} {'phase':<16} {'panel':<8} {'cPb':>8} {'foul':>6} "
        f"{'Pb held':>9} {'load':>6} {'uptake':>10} {'bound':<24}"
    )
    print(header)
    print(f"{'':->5} {'':-<16} {'':-<8} {'':->8} {'':->6} {'':->9} {'':->6} "
          f"{'':->10} {'':-<24}")
    print(
        f"{'':>5} {'':<16} {'':<8} {'ng/L':>8} {'-':>6} {'mg':>9} {'-':>6} "
        f"{'ug/step':>10} {'':<24}"
    )

    step_h = document["dt_s"] / HOUR_S
    stride = max(1, int(round(every_h / step_h)))
    events_by_hour = {}
    for event in document["events"]:
        events_by_hour.setdefault(round(event["elapsed_h"], 3), []).append(event)

    printed_events: set[int] = set()
    for row in document["rows"]:
        index = int(round(row["elapsed_s"] / document["dt_s"]))
        if index % stride != 0:
            continue
        print(
            f"{row['elapsed_h']:5.1f} {row['phase']:<16} {row['panel_id']:<8} "
            f"{from_si_aqueous_concentration(row['concentration_kg_per_m3']['Pb'], 'ng/L'):8.1f} "
            f"{row['fouling_fraction']:6.3f} "
            f"{from_si_mass(row['retained_kg']['Pb'], 'mg'):9.4f} "
            f"{row['loading_fraction']['Pb']:6.3f} "
            f"{from_si_mass(row['uptake_kg']['Pb'], 'ug'):10.4f} "
            f"{row['binding_constraint']['Pb']:<24}"
        )
        for key, event_list in events_by_hour.items():
            if key <= row["elapsed_h"] + 1e-9 and id(event_list) not in printed_events:
                for event in event_list:
                    print(f"      >>> {event['elapsed_h']:.1f} h  {event['kind']}  "
                          f"{event['panel_id']}: {event['note']}")
                printed_events.add(id(event_list))

    print()
    print("Mass check per panel (kg, SI):")
    for panel_id, per_element in document["mass_check"].items():
        for element, values in per_element.items():
            print(
                f"  {panel_id} {element}: delivered {values['delivered_to_panel_kg']:.6e}"
                f"  captured {values['captured_kg']:.6e}"
                f"  escaped past panel {values['escaped_past_panel_kg']:.6e}"
            )
            print(
                f"      active {values['in_active_mesh_kg']:.6e}"
                f"  retrieved {values['in_retrieved_media_kg']:.6e}"
                f"  released back {values['released_back_to_water_kg']:.6e}"
                f"  residual {values['captured_minus_accounted_kg']:+.3e}"
            )

    print()
    print("Conditional remaining life (s), assuming the last phase persists:")
    for panel_id, forecast in document["forecast"].items():
        for element in document["elements"]:
            interval = forecast["remaining_life_s_interval"].get(element)
            never = forecast["never_reached_fraction"].get(element, 0.0)
            if interval is None:
                text = "not reached by any ensemble member under this assumption"
            else:
                text = (
                    f"[{interval[0]:.0f}, {interval[1]:.0f}] s "
                    f"({100.0 * never:.0f} % of members never reach it)"
                )
            print(f"  {panel_id} {element}: {text}")
    print()
    print("All values are synthetic demonstration values. Nothing here is a "
          "measurement or a product specification.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[2] / "results" / "examples" / "micro"),
        help="directory for the JSON timeline",
    )
    parser.add_argument(
        "--every-h",
        type=float,
        default=6.0,
        help="printing stride for the timeline table, in hours",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="write the JSON without printing the table"
    )
    args = parser.parse_args(argv)

    document = run_timeline()
    if not args.quiet:
        print_timeline(document, every_h=args.every_h)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "scripted_contact_timeline.json"
    target.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
    if not args.quiet:
        print(f"\nJSON timeline written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
