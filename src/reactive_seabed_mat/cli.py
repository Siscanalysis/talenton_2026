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
from dataclasses import replace
from pathlib import Path

from .config import RunConfig, config_hash, save_run_config
from .results import ManifestBuilder, RunPaths, ledger_to_dict, write_json
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
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
