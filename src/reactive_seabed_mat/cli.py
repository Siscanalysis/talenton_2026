"""Command line entry point.  Offline, no account, no network.

    python -m reactive_seabed_mat.cli list
    python -m reactive_seabed_mat.cli run fresh_mat --out results
    python -m reactive_seabed_mat.cli run-all --out results
    python -m reactive_seabed_mat.cli quick --out results
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

from .config import RunConfig, config_hash, save_run_config
from .results import ManifestBuilder, RunPaths, ledger_to_dict, write_json, write_jsonl_dicts
from .observations.records import write_jsonl, observations_available
from .observations.qc import run_qc
from .scenarios import registry
from .scenarios.run import run_scenario
from .visualization.report import write_html_report

__all__ = ["main"]

_SECONDS_PER_YEAR = 365.25 * 86400.0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_result(result, base: Path) -> RunPaths:
    config: RunConfig = result.config
    paths = RunPaths.create(base, config.run_id)

    write_json(
        paths.ledger / "mat_mass_ledger.json",
        {
            "note": (
                "The mat ledger is the reactive layer's own control volume: "
                "released_from_sediment_kg is what entered through the tiles' "
                "sediment face, boundary_out_kg is the residual flux that left "
                "into the water. hotspot_released_kg is the separate gross mass "
                "leaving the whole hotspot, including area no tile covers."
            ),
            "hotspot_released_kg": dict(result.hotspot_released_kg),
            "hotspot_into_water_kg": dict(result.hotspot_into_water_kg),
            "layer_budget": {
                element: ledger_to_dict(ledger)
                for element, ledger in result.mat_ledger.items()
            },
        },
    )
    write_json(
        paths.ledger / "mat_timeline.json",
        [point.to_dict() for point in result.timeline],
    )
    write_json(
        paths.comparison / "plume_windows.json",
        [
            {
                "label": window.label,
                "elapsed_years": window.elapsed_years,
                "window_s": window.window_s,
                "with_mat": {
                    element: ledger_to_dict(ledger)
                    for element, ledger in window.ledger_with_mat.items()
                },
                "without_mat": {
                    element: ledger_to_dict(ledger)
                    for element, ledger in window.ledger_without_mat.items()
                },
                "peak_kg_per_m3": {
                    element: {
                        "with_mat": window.peak_concentration(element),
                        "without_mat": window.peak_concentration(element, with_mat=False),
                    }
                    for element in config.elements
                },
            }
            for window in result.windows
        ],
    )
    maintenance = result.maintenance
    if maintenance is not None:
        write_jsonl(paths.observations / "records.jsonl", maintenance.observations)
        write_jsonl_dicts(paths.estimates / "history.jsonl",
                         (asdict(estimate) for estimate in maintenance.estimate_history))
        write_json(paths.estimates / "final.json",
                   {tile: asdict(estimate) for tile, estimate in maintenance.final_estimates.items()})
        write_jsonl_dicts(paths.actions / "recommendations.jsonl",
                         (asdict(rec) for rec in maintenance.recommendations))
        write_jsonl_dicts(paths.actions / "service_events.jsonl",
                         (asdict(event) for event in maintenance.service_events))
        if result.timeline:
            final_time = result.timeline[-1].time_utc
            qc = run_qc(list(observations_available(maintenance.observations, final_time)), now_utc=final_time)
            write_json(paths.observations / "final_qc.json", asdict(qc))
        write_json(
            paths.comparison / "recommendations.json",
            {
                "policy": config.policy.kind,
                "saturation_decision_bound": config.policy.saturation_decision_bound,
                "note": (
                    "Recommendations are advisory. Every one carries "
                    "human_confirmation_required = True and "
                    "execution_mode = 'simulation_only'; nothing here actuates "
                    "anything. Acceptance in this demonstrator is automatic and "
                    "total, which models an operator who follows the "
                    "recommendation exactly."
                ),
                "n_observations_generated": maintenance.n_observations,
                "assumed_service_cost_eur": maintenance.assumed_service_cost_eur,
                "retrieved_kg": dict(maintenance.retrieved_kg),
                "service_events": [
                    {
                        "event_id": event.event_id,
                        "time_utc": str(event.time_utc),
                        "tile_ids": list(event.tile_ids),
                        "retrieved_kg": dict(event.retrieved_kg),
                        "cost_eur": event.cost_eur,
                        "triggered_by": event.triggered_by_recommendation_id,
                        "execution_mode": event.execution_mode,
                    }
                    for event in maintenance.service_events
                ],
                "recommendations": [
                    {
                        "recommendation_id": rec.recommendation_id,
                        "decision_time_utc": str(rec.decision_time_utc),
                        "action": rec.action.value,
                        "reason": rec.reason,
                        "uncertainty_note": rec.uncertainty_note,
                        "target_tile_ids": list(rec.target_tile_ids),
                        "n_evidence_records": len(rec.evidence_record_ids),
                        "evidence_record_ids": list(rec.evidence_record_ids),
                        "data_age_s": rec.data_age_s,
                        "diagnostics": dict(rec.diagnostics),
                        "expected_cost_eur": rec.expected_cost_eur,
                        "human_confirmation_required": rec.human_confirmation_required,
                        "execution_mode": rec.execution_mode,
                    }
                    for rec in maintenance.recommendations
                ],
            },
        )

    write_json(
        paths.truth / "final_tiles.json",
        [
            {
                "tile_id": tile.tile_id,
                "media_id": tile.media_id,
                "fouling_index": tile.fouling_index,
                "integrity_index": tile.integrity_index,
                "burial_depth_m": tile.burial_depth_m,
                "displaced": tile.displaced,
                "coverage_fraction": tile.coverage_fraction,
                "retained_kg": {
                    element: tile.retained_kg(element) for element in config.elements
                },
            }
            for tile in result.final_tiles
        ],
    )

    report = write_html_report(result, paths.report / "report.html")

    manifest = ManifestBuilder(
        config=config, engine=config.transport_engine, repo_root=_repo_root()
    )
    manifest.assumptions.append(
        "Reactive-medium parameters are keratin literature values derated for "
        "seawater; see docs/MATERIAL_KERATIN.md. They are not measurements of "
        "our material."
    )
    manifest.assumptions.append(
        "The mat timeline and the plume windows run on separate clocks and "
        "their ledgers are reported separately."
    )
    manifest.assumptions.extend([
        "Evidence-informed decisions use compatible Pb/Hg chemistry. Cu is simulated but has no observation channel and is not evidence-controlled.",
        "Missing hydraulic-head and tilt models emit missing observations; no zero-valued physical condition is fabricated.",
        "Nonfinite interval endpoints are JSON null with _nonfinite_values path metadata identifying unbounded directions.",
    ])
    for element, ledger in result.mat_ledger.items():
        manifest.add_check(
            f"mat_mass_balance_{element}",
            abs(ledger.relative_imbalance) < 1e-6,
            detail="mat ledger relative imbalance",
            value=abs(ledger.relative_imbalance),
            tolerance=1e-6,
        )
    for window in result.windows:
        for element, ledger in window.ledger_with_mat.items():
            manifest.add_check(
                f"water_mass_balance_{element}_{window.label.replace(' ', '')}",
                abs(ledger.relative_imbalance) < 1e-6,
                detail="water-column ledger relative imbalance",
                value=abs(ledger.relative_imbalance),
                tolerance=1e-6,
            )
    manifest.add_data_file("report.html", report)
    for directory in (paths.observations, paths.estimates, paths.actions, paths.ledger, paths.comparison):
        for artifact in sorted(directory.iterdir()):
            if artifact.is_file():
                manifest.add_data_file(artifact.relative_to(paths.root).as_posix(), artifact)
    manifest.write(paths)
    return paths


def _run_one(name: str, base: Path, *, quick: bool) -> None:
    config = registry.build_scenario(name)
    if quick:
        config = replace(
            config,
            run_id=f"{config.run_id}_quick",
            duration_s=min(config.duration_s, 1.5 * _SECONDS_PER_YEAR),
            plume=replace(config.plume, sample_years=(0.0,)),
        )
    letter = registry.scenario_letter(name)
    print(f"[{letter}] {name}: {config.duration_years:.1f} simulated years, "
          f"config {config_hash(config)}")
    started = time.perf_counter()
    result = run_scenario(config)
    paths = _write_result(result, base)
    elapsed = time.perf_counter() - started

    final = result.timeline[-1] if result.timeline else None
    if final is not None:
        primary = config.elements[0]
        print(
            f"     attenuation({primary}) {final.attenuation[primary]:.4f}"
            f" | saturation {final.saturation[primary]:.3f}"
            f" | coverage {final.mean_coverage:.2f}"
        )
    print(f"     wrote {paths.root} in {elapsed:.1f} s")


def _mass_into_water_kg(result, element: str) -> float:
    """Mass entering the overlying water over the timeline, per element.

    One quantity for all three policies, which is the only way the comparison
    means anything. With no mat it is the whole hotspot release; with a mat it
    is what left the reactive layer, plus whatever the tiles never covered.
    """
    return float(result.hotspot_into_water_kg.get(element, 0.0))


def _compare_policies(scenario: str, base: Path, *, quick: bool) -> None:
    """Run one scenario under all three policies under identical assumptions."""
    config = registry.build_scenario(scenario)
    if quick:
        config = replace(
            config,
            duration_s=min(config.duration_s, 3.0 * _SECONDS_PER_YEAR),
            plume=replace(config.plume, sample_years=(0.0,)),
        )
    element = config.elements[0]
    rows = []

    for policy in registry.POLICIES:
        variant = registry.policy_variant(config, policy)
        print(f"[{policy}] {scenario}: {variant.duration_years:.1f} yr")
        started = time.perf_counter()
        result = run_scenario(variant)
        paths = _write_result(result, base)
        maintenance = result.maintenance
        row = {
            "policy": policy,
            "description": registry.POLICIES[policy],
            "run_id": variant.run_id,
            f"{element}_into_water_kg": _mass_into_water_kg(result, element),
            f"{element}_retained_kg": (
                result.mat_ledger[element].retained_in_mat_kg
                + result.mat_ledger[element].retained_in_retrieved_media_kg
                if element in result.mat_ledger
                else 0.0
            ),
            f"{element}_active_mat_kg": result.mat_ledger[element].retained_in_mat_kg,
            f"{element}_retrieved_media_kg": result.mat_ledger[element].retained_in_retrieved_media_kg,
            "final_attenuation": (
                result.timeline[-1].attenuation.get(element) if result.timeline else None
            ),
            "n_service_events": len(maintenance.service_events) if maintenance else 0,
            "assumed_service_cost_eur": (
                maintenance.assumed_service_cost_eur if maintenance else 0.0
            ),
            "n_recommendations": len(maintenance.recommendations) if maintenance else 0,
            "output": str(paths.root),
        }
        retained = row[f"{element}_retained_kg"]
        row["assumed_eur_per_kg_retained"] = (
            row["assumed_service_cost_eur"] / retained if retained > 0 else None
        )
        rows.append(row)
        print(
            f"     {element} into water {row[f'{element}_into_water_kg']:.4g} kg"
            f" | services {row['n_service_events']}"
            f" | assumed cost EUR {row['assumed_service_cost_eur']:,.0f}"
            f" | {time.perf_counter() - started:.0f} s"
        )

    target = base / f"{scenario}_policy_comparison.json"
    write_json(
        target,
        {
            "scenario": scenario,
            "element": element,
            "identical_assumptions": (
                "Same seed, same forcing, same hotspot schedule, same "
                "observation schedule. Only PolicyConfig.kind differs."
            ),
            "cost_note": (
                "Every euro value is an assumption from CostConfig. No supplier "
                "has been contacted and no quotation exists."
            ),
            "comparison_note": (
                "Mass into water is the same quantity in all three rows: the "
                "whole hotspot release under 'none', and the integrated mat residual "
                "plus release through uncovered or displaced area under the other two. "
                "Retained mass includes active media and separately recorded retrieved media."
            ),
            "rows": rows,
        },
    )
    print(f"     wrote {target}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reactive-seabed-mat-demo",
        description=(
            "Offline demonstrator for a selective reactive seabed mat. "
            "Synthetic data, assumed parameters, not field validated."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list the scenarios")

    run_parser = sub.add_parser("run", help="run one scenario")
    run_parser.add_argument("scenario", choices=registry.list_scenarios())
    run_parser.add_argument("--out", default="results")
    run_parser.add_argument("--quick", action="store_true",
                            help="shorter timeline and one plume window")

    all_parser = sub.add_parser("run-all", help="run every scenario")
    all_parser.add_argument("--out", default="results")
    all_parser.add_argument("--quick", action="store_true")

    quick_parser = sub.add_parser(
        "quick", help="one short scenario, for a first look (about a minute)"
    )
    quick_parser.add_argument("--out", default="results")

    compare_parser = sub.add_parser(
        "compare",
        help="one scenario under no mat, fixed servicing and evidence-informed "
             "servicing, under identical assumptions",
    )
    compare_parser.add_argument(
        "scenario", nargs="?", default="progressive_saturation",
        choices=registry.list_scenarios(),
    )
    compare_parser.add_argument("--out", default="results")
    compare_parser.add_argument(
        "--quick", action="store_true", help="cap the timeline at three years"
    )

    args = parser.parse_args(argv)

    if args.command == "list":
        for name in registry.list_scenarios():
            letter = registry.scenario_letter(name)
            print(f"{letter}  {name:24s} {registry.scenario_description(name)}")
        return 0

    base = Path(args.out)
    if args.command == "quick":
        _run_one("fresh_mat", base, quick=True)
        return 0
    if args.command == "run":
        _run_one(args.scenario, base, quick=args.quick)
        return 0
    if args.command == "run-all":
        for name in registry.list_scenarios():
            _run_one(name, base, quick=args.quick)
        return 0
    if args.command == "compare":
        _compare_policies(args.scenario, base, quick=args.quick)
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
