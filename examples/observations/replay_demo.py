"""Replay the observation stack end to end, with no map and no hardware.

What it does, in order:

1. reads the coordinator's edge-case fixture
   ``data/synthetic/observations.jsonl`` and reports what each record is;
2. generates a four-year synthetic stream on the campaign rhythm of
   ``ObservationConfig``: porewater at the sediment face, bottom water above the
   mat, benthic-chamber areal fluxes, DGT exposures, a retrieved-media assay,
   context channels, and the mat-condition channels;
3. runs the QARTOD-inspired quality control over both;
4. runs the observation operator and prints the inventory by channel, by
   decision and by degradation mode;
5. applies the availability gate at three decision times, so the effect of
   laboratory latency is visible;
6. writes ``results/observations_demo/`` : the generated stream as JSONL and a
   JSON summary of everything printed.

Run it from the repository root::

    .venv\\Scripts\\python.exe examples\\observations\\replay_demo.py

Nothing here touches the network, a results/truth directory or any hardware.
Every number is ``synthetic_demo`` or an explicit ``assumption``.

The mat state in step 2 comes from ``synthetic_mat_history``, a LABELLED_STUB
analytic stand-in for the reactive-layer timeline.  When ``feat/reactive-layer``
lands, ``scene_from_layer_history`` replaces it and nothing else changes.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from reactive_seabed_mat.config import DegradationEvent, ObservationConfig  # noqa: E402
from reactive_seabed_mat.contracts import (  # noqa: E402
    DegradationMode,
    METAL_PARAMETERS,
    Qualifier,
)
from reactive_seabed_mat.observations import generator as gen  # noqa: E402
from reactive_seabed_mat.observations import operator as op  # noqa: E402
from reactive_seabed_mat.observations import qc  # noqa: E402
from reactive_seabed_mat.observations import records as obs  # noqa: E402
from reactive_seabed_mat.units import format_utc, from_si_areal_flux  # noqa: E402

DAY = 86400.0
YEAR = 365.25 * DAY
START = datetime(2026, 9, 8, tzinfo=timezone.utc)
DURATION_S = 4.0 * YEAR

FIXTURE = REPOSITORY_ROOT / "data" / "synthetic" / "observations.jsonl"
OUTPUT_DIR = REPOSITORY_ROOT / "results" / "observations_demo"


def _rule(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def _table(rows, headers) -> None:
    widths = [len(header) for header in headers]
    rendered = [[str(cell) for cell in row] for row in rows]
    for row in rendered:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row)]
    print("  ".join(header.ljust(width) for header, width in zip(headers, widths)))
    print("  ".join("-" * width for width in widths))
    for row in rendered:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)))


def replay_fixture() -> dict:
    """Step 1: the coordinator's edge-case fixture."""
    _rule("1. Fixture replay: data/synthetic/observations.jsonl")
    records = obs.read_jsonl(FIXTURE)
    uses = op.build_assimilation_set(records)
    rows = []
    for record, use in zip(records, uses.uses):
        rows.append(
            (
                record.record_id,
                record.parameter.value,
                record.quantity_kind.value,
                record.matrix.value,
                record.qualifier.value,
                record.tile_id or "-",
                use.decision.value,
                use.model_quantity.value,
            )
        )
    _table(
        rows,
        ("id", "parameter", "kind", "matrix", "qualifier", "tile", "decision",
         "model quantity"),
    )
    return {
        "n_records": len(records),
        "decisions": dict(Counter(use.decision.value for use in uses.uses)),
        "assimilable": len(uses.assimilable),
    }


def generate_stream() -> tuple[list, dict]:
    """Step 2: a four-year stream on the campaign rhythm."""
    _rule("2. Generated stream: four years on the campaign rhythm")
    config = ObservationConfig(
        # A demonstration decimation: the context channels are hourly in the
        # configuration, which would be 10^5 records over four years and would
        # say nothing new.  Everything else keeps its configured rhythm.
        environmental_period_s=30.0 * DAY,
    )
    events = (
        DegradationEvent(start_s=1.5 * YEAR, tile_id="tile_0_0",
                         mode="displacement", magnitude=1.0),
        DegradationEvent(start_s=2.2 * YEAR, tile_id="tile_1_1",
                         mode="local_damage", magnitude=0.35),
        DegradationEvent(start_s=1.0 * YEAR, tile_id="tile_2_2",
                         mode="burial", magnitude=0.045),
    )
    scene = gen.synthetic_mat_history(
        START,
        DURATION_S,
        events=events,
        replacements=(
            gen.MediaReplacement(
                start_s=3.0 * YEAR, tile_id="tile_1_1", new_media_id="media_B1"
            ),
        ),
    )
    generator = gen.ObservationGenerator(config, seed=20260908, start_utc=START)
    records = generator.generate(scene, DURATION_S)

    print(f"records generated : {len(records)}")
    print(f"first available   : {format_utc(records[0].available_at_utc)}")
    print(f"last available    : {format_utc(records[-1].available_at_utc)}")
    print()
    print("Each failure is placed on the tile whose station can observe it:")
    print("  tile_0_0  bottom-water probe  displaced at 1.5 yr")
    print("  tile_1_1  porewater station   torn at 2.2 yr, media replaced at 3.0 yr")
    print("  tile_2_2  benthic chamber     buried at 1.0 yr")
    return records, {
        "n_records": len(records),
        "duration_years": DURATION_S / YEAR,
        "scene_notes": scene.notes,
    }


def inventory_by_channel(records) -> dict:
    _rule("3. Inventory by channel")
    counter = Counter(
        (
            record.parameter.value,
            record.quantity_kind.value,
            record.matrix.value,
            record.acquisition_kind.value,
        )
        for record in records
    )
    rows = [
        (parameter, kind, matrix, acquisition, count)
        for (parameter, kind, matrix, acquisition), count in sorted(counter.items())
    ]
    _table(rows, ("parameter", "quantity kind", "matrix", "acquisition", "n"))
    return {"|".join(key): value for key, value in counter.items()}


def inventory_by_qualifier(records) -> dict:
    _rule("4. Inventory by censoring qualifier")
    counter = Counter(record.qualifier.value for record in records)
    _table(sorted(counter.items()), ("qualifier", "n"))
    print()
    print("A non-detect is a bound, an above-range result is a lower bound, and a")
    print("missing result is neither: it carries no information at all.")
    return dict(counter)


#: The demonstration decimates the hourly context channels to one reading a
#: month (step 2).  A data-age limit of six hours would then report those
#: channels as stale, which would be an artefact of the decimation reported as a
#: finding.  The limit is therefore declared to match the rhythm actually used.
CONTEXT_AGE_LIMIT_S = 45.0 * DAY
DEMO_AGE_LIMITS = dict(qc.DEMO_THRESHOLDS.max_data_age)
DEMO_AGE_LIMITS.update(
    {
        parameter: CONTEXT_AGE_LIMIT_S
        for parameter in (
            "temperature", "sediment_temperature", "conductivity", "salinity",
            "pH", "turbidity", "dissolved_oxygen", "redox_potential", "sulfide",
            "current_east", "current_north", "seepage_velocity", "battery_voltage",
        )
    }
)
DEMO_THRESHOLDS = replace(qc.DEMO_THRESHOLDS, max_data_age=DEMO_AGE_LIMITS)


def run_quality_control(records) -> tuple[qc.QCReport, dict]:
    _rule("5. Quality control")
    now = START + timedelta(seconds=DURATION_S)
    report = qc.run_qc(records, now_utc=now, thresholds=DEMO_THRESHOLDS)
    flags = Counter(int(outcome.flag) for outcome in report.outcomes.values())
    _table(sorted(flags.items()), ("quality flag", "n"))
    failed_checks = Counter()
    for outcome in report.outcomes.values():
        for name in outcome.failed_checks:
            failed_checks[name] += 1
    print()
    _table(sorted(failed_checks.items()) or [("none", 0)], ("failed check", "n"))
    print()
    rows = []
    for key, health in sorted(report.asset_health.items()):
        rows.append(
            (
                key,
                health.n_records,
                f"{health.missing_fraction:.2f}",
                "yes" if health.failed else "no",
                "yes" if health.stuck else "no",
                "yes" if health.stale else "no",
                "yes" if health.healthy else "no",
            )
        )
    _table(rows, ("asset", "n", "missing", "failed", "stuck", "stale", "healthy"))
    print()
    print("Health covers every asset, including the laboratory, chamber, DGT,")
    print("assay and survey records that carry no sensor_id at all.  The context")
    print("channels use a 45-day age limit because this demonstration decimates")
    print("them to a monthly rhythm; reporting them stale against a six-hour")
    print("limit would be an artefact of the decimation, not a finding.")
    return report, {
        "flags": {str(key): value for key, value in flags.items()},
        "failed_checks": dict(failed_checks),
        "assets": {
            key: {
                "kind": health.asset_kind,
                "n_records": health.n_records,
                "missing_fraction": health.missing_fraction,
                "failed": health.failed,
                "stuck": health.stuck,
                "stale": health.stale,
                "healthy": health.healthy,
            }
            for key, health in report.asset_health.items()
        },
    }


def run_operator(records, report) -> tuple[op.AssimilationSet, dict]:
    _rule("6. Observation operator")
    config = op.OperatorConfig(
        active_media_id="media_A0",
        active_media_id_by_tile={"tile_1_1": "media_B1"},
    )
    uses = op.build_assimilation_set(records, config, qc_report=report)

    decisions = Counter(use.decision.value for use in uses.uses)
    _table(sorted(decisions.items()), ("decision", "n"))
    print()
    quantities = Counter(use.model_quantity.value for use in uses.uses)
    _table(sorted(quantities.items()), ("model quantity", "n"))
    print()
    modes = Counter(
        use.degradation_mode.value for use in uses.uses if use.degradation_mode
    )
    _table(sorted(modes.items()) or [("none", 0)], ("degradation mode constrained", "n"))
    print()
    print(f"chemistry-bearing uses : {len(uses.chemistry)}")
    print(f"condition uses         : {len(uses.condition)}")
    print(f"health evidence        : {len(uses.sensor_health_evidence)}")
    return uses, {
        "decisions": dict(decisions),
        "model_quantities": dict(quantities),
        "degradation_modes": dict(modes),
    }


def context_independence(records) -> dict:
    _rule("7. Removing every context record leaves the metal set unchanged")
    metal_only = [r for r in records if r.parameter in METAL_PARAMETERS]
    full = op.build_assimilation_set(records)
    reduced = op.build_assimilation_set(metal_only)

    def signature(assimilation_set):
        return [
            (use.record_id, use.decision.value, use.model_quantity.value, use.value_si)
            for use in assimilation_set.uses
            if use.carries_chemistry or use.element is not None
        ]

    identical = signature(full) == signature(reduced)
    print(f"records in the full stream  : {len(records)}")
    print(f"records after removing context: {len(metal_only)}")
    print(f"metal-bearing uses unchanged  : {identical}")
    print()
    print("No chemistry is ever derived from temperature, salinity, pH, turbidity,")
    print("oxygen, redox, sulfide or a current measurement.")
    return {
        "n_full": len(records),
        "n_metal_only": len(metal_only),
        "metal_uses_unchanged": identical,
    }


def burial_is_not_success(records, uses) -> dict:
    _rule("8. Burial reduces the apparent flux, and is reported as mode 3")
    fluxes = sorted(
        (use.observed_at_utc, use.value_si)
        for use in uses.uses
        if use.model_quantity is op.ModelQuantity.AREAL_FLUX
        and use.tile_id == "tile_2_2"
        and use.element == "Pb"
        and use.value_si is not None
    )
    rows = [
        (
            format_utc(moment),
            f"{(moment - START).total_seconds() / YEAR:.2f}",
            f"{from_si_areal_flux(value, 'ug/m2/d'):.1f}",
        )
        for moment, value in fluxes
    ]
    _table(rows, ("chamber deployment", "years", "flux ug/m2/d"))

    burial = [
        use
        for use in uses.for_tile("tile_2_2")
        if use.model_quantity is op.ModelQuantity.BURIAL_DEPTH
        and use.value_si is not None
    ]
    print()
    print(f"burial observations on tile_2_2 : {len(burial)}")
    if burial:
        last = burial[-1]
        print(f"latest burial depth              : {last.value_si:.3f} m")
        print(f"degradation mode constrained     : {last.degradation_mode.value}")
        print(f"carries chemistry                : {last.carries_chemistry}")
        print(f"masquerade warning recorded      : "
              f"{last.diagnostics.get('burial_masquerades_as_success')}")
    print()
    print("The chamber flux on this tile falls after burial.  That is not success:")
    print("the mat is doing no more work, the path out has simply got longer, and")
    print("the burial channel is what makes the difference observable.")
    return {
        "chamber_flux_ug_per_m2_per_d": [
            from_si_areal_flux(value, "ug/m2/d") for _, value in fluxes
        ],
        "n_burial_observations": len(burial),
        "latest_burial_depth_m": burial[-1].value_si if burial else None,
    }


def availability_gate(records) -> dict:
    _rule("9. The availability gate: no result influences a decision early")
    rows = []
    summary = {}
    for years in (0.5, 2.0, 4.0):
        moment = START + timedelta(seconds=years * YEAR)
        visible = obs.observations_available(records, moment)
        observed_but_not_available = sum(
            1 for record in records
            if record.observed_at_utc <= moment < record.available_at_utc
        )
        rows.append(
            (f"{years:.1f} yr", format_utc(moment), len(visible), observed_but_not_available)
        )
        summary[f"{years:.1f}_yr"] = {
            "visible": len(visible),
            "in_transit": observed_but_not_available,
        }
    _table(rows, ("decision time", "utc", "visible records", "still in transit"))
    return summary


def write_outputs(records, payload) -> None:
    _rule("10. Outputs")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stream_path = obs.write_jsonl(OUTPUT_DIR / "generated_observations.jsonl", records)
    summary_path = OUTPUT_DIR / "replay_summary.json"
    summary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    print(f"stream  : {stream_path}")
    print(f"summary : {summary_path}")


def main() -> int:
    print("Selective reactive seabed mat: observation replay")
    print("=" * 48)
    print("All values are synthetic_demo or explicit assumptions.  No network, no")
    print("hardware, no map, and no access to any simulated truth store.")

    payload: dict = {}
    payload["fixture"] = replay_fixture()
    records, generated = generate_stream()
    payload["generated"] = generated
    payload["by_channel"] = inventory_by_channel(records)
    payload["by_qualifier"] = inventory_by_qualifier(records)
    report, qc_summary = run_quality_control(records)
    payload["quality_control"] = qc_summary
    uses, operator_summary = run_operator(records, report)
    payload["operator"] = operator_summary
    payload["context_independence"] = context_independence(records)
    payload["burial"] = burial_is_not_success(records, uses)
    payload["availability_gate"] = availability_gate(records)
    write_outputs(records, payload)

    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
