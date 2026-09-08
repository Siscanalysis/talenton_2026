"""A scripted multi-year life of a nine-tile reactive seabed mat.

Runs entirely offline: no map, no hardware, no network, no coastal solver.  A
scripted sediment-side porewater concentration drives nine 1-D reactive layers
through the phases the demonstrator has to be able to show:

1. ``fresh``               a new mat over a moderate hotspot;
2. ``loading``             the medium fills from the sediment face upward;
3. ``stronger_source``     the sediment-side concentration doubles;
4. ``breakthrough``        capacity is consumed and the residual flux climbs;
5. ``fouling``             pore blockage grows on every tile, and the edge
                           bypass grows with it, so it is never a benefit;
6. ``burial``              sediment settles on one tile and **lowers** its
                           apparent flux, which is not success;
7. ``local_damage``        another tile tears and passes the bare flux over the
                           torn share of its area;
8. ``partial_replacement`` the two most loaded tiles are replaced and their
                           inventory moves to the retrieved-media ledger.

Everything printed is a synthetic demonstration value.  None of it is a
measurement, a product specification or a validated capacity.

Run it::

    .venv\\Scripts\\python.exe examples/reactive_layer/scripted_layer.py
    .venv\\Scripts\\python.exe examples/reactive_layer/scripted_layer.py --out somewhere
    .venv\\Scripts\\python.exe examples/reactive_layer/scripted_layer.py --years 3 --dt-hours 24
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:  # let the example run from a plain checkout
    sys.path.insert(0, str(_SRC))

from reactive_seabed_mat.config import (  # noqa: E402
    CostConfig,
    DegradationConfig,
    DegradationEvent,
    HotspotConfig,
    MatLayoutConfig,
    RunConfig,
)
from reactive_seabed_mat.reactive_layer import (  # noqa: E402
    BURIAL_WARNING,
    RetrievedMediaLedger,
    advance_reactive_layer,
    apply_degradation_events,
    breakthrough_interval,
    build_material_map,
    build_tile_states,
    replace_tiles,
    scripted_exchange,
    sorbed_kg_per_m2,
    tile_summary,
)
from reactive_seabed_mat.units import (  # noqa: E402
    format_utc,
    from_si_areal_flux,
    from_si_mass,
)

SECONDS_PER_YEAR = 365.25 * 86400.0

#: Scripted sediment-face porewater concentration [kg m^-3], per element, from
#: a start time in seconds.  ASSUMPTIONS chosen to show loading, a stronger
#: source and breakthrough inside a six-year demonstration.
DRIVING_SCHEDULE: tuple[tuple[float, dict[str, float], str], ...] = (
    (0.0, {"Pb": 1.0e-3, "Hg": 8.0e-6}, "baseline hotspot"),
    (2.0 * SECONDS_PER_YEAR, {"Pb": 2.0e-3, "Hg": 1.2e-5}, "the seep strengthens"),
)

#: Continuous degradation, applied through the exchange environment.
#: ASSUMPTIONS mirroring ``config.DegradationConfig``.
FOULING_START_S = 3.0 * SECONDS_PER_YEAR
FOULING_GROWTH_PER_S = 5.0e-9          # full fouling in about six years
BURIAL_START_S = 3.5 * SECONDS_PER_YEAR
BURIAL_GROWTH_M_PER_S = 4.0e-9         # about 0.13 m per year
BURIED_TILE = "tile_2_0"
TORN_TILE = "tile_0_2"
REPLACEMENT_TIME_S = 4.5 * SECONDS_PER_YEAR
REPLACED_TILES = ("tile_0_0", "tile_1_0")


def driving_concentration(elapsed_s: float) -> tuple[dict[str, float], str]:
    concentration, label = DRIVING_SCHEDULE[0][1], DRIVING_SCHEDULE[0][2]
    for start_s, values, note in DRIVING_SCHEDULE:
        if elapsed_s >= start_s:
            concentration, label = values, note
    return dict(concentration), label


def phase_of(elapsed_s: float, state: dict[str, Any]) -> str:
    if state["replaced"]:
        return "partial_replacement"
    if elapsed_s >= 4.0 * SECONDS_PER_YEAR:
        return "local_damage"
    if elapsed_s >= BURIAL_START_S:
        return "burial"
    if elapsed_s >= FOULING_START_S:
        return "fouling"
    if state["broken_through"]:
        return "breakthrough"
    if elapsed_s >= 2.0 * SECONDS_PER_YEAR:
        return "stronger_source"
    if elapsed_s > 0.25 * SECONDS_PER_YEAR:
        return "loading"
    return "fresh"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", type=float, default=6.0)
    parser.add_argument("--dt-hours", type=float, default=12.0)
    parser.add_argument(
        "--report-days",
        type=float,
        default=91.0,
        help="how often a timeline row is recorded",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("results/example_reactive_layer"),
        help="directory for the JSON timeline",
    )
    args = parser.parse_args(argv)

    run_config = RunConfig(
        run_id="scripted_layer_example",
        scenario="scripted_layer_example",
        duration_s=args.years * SECONDS_PER_YEAR,
        dt_s=args.dt_hours * 3600.0,
    )
    hotspot = HotspotConfig()
    mat_config = MatLayoutConfig()
    degradation = DegradationConfig(
        events=(
            DegradationEvent(
                start_s=4.0 * SECONDS_PER_YEAR,
                tile_id=TORN_TILE,
                mode="local_damage",
                magnitude=0.35,
            ),
        )
    )
    costs = CostConfig()

    materials = build_material_map(mat_config)
    start_utc = run_config.start_datetime
    tiles = build_tile_states(mat_config, start_utc, materials, hotspot=hotspot)
    ledger = RetrievedMediaLedger()

    dt_s = run_config.dt_s
    n_steps = int(round(run_config.duration_s / dt_s))
    report_every = max(1, int(round(args.report_days * 86400.0 / dt_s)))

    tracker = {"broken_through": False, "replaced": False}
    timeline: list[dict[str, Any]] = []
    service_events: list[dict[str, Any]] = []

    print()
    print("Selective reactive seabed mat: scripted reactive-layer timeline")
    print("Synthetic demonstration. Every number below is an assumption.")
    print(
        f"{mat_config.tiles_x} x {mat_config.tiles_y} tiles, "
        f"{mat_config.thickness_m * 1000:.0f} mm thick, "
        f"{mat_config.n_layer_nodes} nodes per layer, dt = {args.dt_hours:g} h, "
        f"{args.years:g} years"
    )
    print()
    header = (
        f"{'year':>6} {'phase':>19} {'C_sed':>8} {'sat Pb':>7} {'Jout/Jb':>8} "
        f"{'emit/Jb':>8} {'foul':>5} {'burial':>7} {'integ':>6} {'held mg/m2':>11}"
    )
    print(header)
    print("-" * len(header))

    for step_index in range(n_steps):
        elapsed_s = step_index * dt_s
        time_utc = start_utc + timedelta(seconds=elapsed_s)
        concentration, source_note = driving_concentration(elapsed_s)

        tiles, applied = apply_degradation_events(
            tiles, degradation.events, elapsed_s, elapsed_s + dt_s
        )
        for record in applied:
            service_events.append(
                {"kind": "degradation_event", "elapsed_years": elapsed_s / SECONDS_PER_YEAR, **record}
            )

        if (
            not tracker["replaced"]
            and elapsed_s <= REPLACEMENT_TIME_S < elapsed_s + dt_s
        ):
            tiles, event = replace_tiles(
                tiles,
                REPLACED_TILES,
                time_utc,
                ledger=ledger,
                costs=costs,
            )
            tracker["replaced"] = True
            service_events.append(
                {
                    "kind": "partial_replacement",
                    "elapsed_years": elapsed_s / SECONDS_PER_YEAR,
                    "tile_ids": list(event.tile_ids),
                    "retrieved_kg": dict(event.retrieved_kg),
                    "new_media_id": event.new_media_id,
                    "assumed_cost_eur": event.cost_eur,
                    "execution_mode": event.execution_mode,
                }
            )

        new_tiles = []
        steps = []
        for tile in tiles:
            environment: dict[str, float] = {
                "fouling_bypass_coupling": degradation.fouling_bypass_coupling,
                "burial_resistance_s_per_m": degradation.burial_resistance_s_per_m,
            }
            if elapsed_s >= FOULING_START_S:
                environment["fouling_growth_per_s"] = FOULING_GROWTH_PER_S
            if elapsed_s >= BURIAL_START_S and tile.tile_id == BURIED_TILE:
                environment["burial_growth_m_per_s"] = BURIAL_GROWTH_M_PER_S
            exchange = scripted_exchange(
                tile,
                time_utc,
                dt_s,
                concentration,
                seepage_velocity_m_per_s=hotspot.schedule[0].seepage_velocity_m_per_s,
                film_transfer_m_per_s=hotspot.film_transfer_m_per_s,
                environment=environment,
            )
            step = advance_reactive_layer(tile, exchange, materials, dt_s)
            steps.append(step)
            new_tiles.append(step.new_state)
        tiles = tuple(new_tiles)

        bare = steps[0].diagnostics["bare_flux_kg_per_m2_per_s"]["Pb"]
        ratio = sum(
            step.flux_out_kg_per_m2_per_s["Pb"] for step in steps
        ) / (len(steps) * bare)
        if ratio > 0.05:
            tracker["broken_through"] = True

        if step_index % report_every == 0 or step_index == n_steps - 1:
            emitted = sum(
                step.diagnostics["effective_flux_out_kg_per_m2_per_s"]["Pb"]
                for step in steps
            ) / (len(steps) * bare)
            saturation = sum(
                tile.saturation_fraction(materials["Pb"]) for tile in tiles
            ) / len(tiles)
            held_kg_per_m2 = sum(sorbed_kg_per_m2(tile, "Pb") for tile in tiles) / len(
                tiles
            )
            by_id = {tile.tile_id: tile for tile in tiles}
            phase = phase_of(elapsed_s, tracker)
            row = {
                "elapsed_years": elapsed_s / SECONDS_PER_YEAR,
                "time_utc": format_utc(time_utc),
                "phase": phase,
                "source_note": source_note,
                "sediment_porewater_kg_per_m3": concentration,
                "bare_flux_kg_per_m2_per_s": bare,
                "bare_flux_ug_per_m2_per_d": from_si_areal_flux(bare, "ug/m2/d"),
                "mean_saturation_fraction_pb": saturation,
                "mean_flux_out_over_bare_pb": ratio,
                "mean_emitted_over_bare_pb": emitted,
                "mean_attenuation_pb": 1.0 - ratio,
                "mean_effective_attenuation_pb": 1.0 - emitted,
                "mean_sorbed_kg_per_m2_pb": held_kg_per_m2,
                "fouling_index": by_id[BURIED_TILE].fouling_index,
                "burial_depth_m": by_id[BURIED_TILE].burial_depth_m,
                "integrity_index_torn_tile": by_id[TORN_TILE].integrity_index,
                "retrieved_media_kg": dict(ledger.totals_kg),
            }
            timeline.append(row)
            print(
                f"{row['elapsed_years']:6.2f} {phase:>19} "
                f"{concentration['Pb'] * 1e3:8.2f} "
                f"{saturation:7.3f} {ratio:8.4f} {emitted:8.4f} "
                f"{row['fouling_index']:5.2f} {row['burial_depth_m']:7.3f} "
                f"{row['integrity_index_torn_tile']:6.2f} "
                f"{held_kg_per_m2 * 1e6:11.1f}"
            )

    print()
    print("C_sed is the sediment-face porewater concentration in mg/L.")
    print("Jout/Jb is the residual flux through the layer over the bare flux;")
    print("emit/Jb is what the whole footprint emits once the edge bypass, the")
    print("tear and displacement are counted. The two diverge as the mat fouls.")
    print()
    print(BURIAL_WARNING)
    print()

    forecast_supply = timeline[-1]["bare_flux_kg_per_m2_per_s"] * 0.06
    interval = breakthrough_interval(
        materials,
        {key: sorbed_kg_per_m2(tiles[0], key) for key in materials},
        tiles[0].geometry.sorbent_loading_kg_per_m2,
        tiles[0].fouling_index,
        {key: forecast_supply for key in materials},
        ensemble_size=64,
        seed=run_config.seed,
    )
    print("Breakthrough forecast for tile_0_0, conditional on the assumed supply:")
    for element, value in interval.items():
        if value is None:
            print(f"  {element}: not determined under this assumption")
        else:
            print(
                f"  {element}: between {value[0] / SECONDS_PER_YEAR:.2f} and "
                f"{value[1] / SECONDS_PER_YEAR:.2f} years"
            )
    print("  It is an interval or nothing at all, never a single number.")
    print()

    summaries = [tile_summary(tile, materials) for tile in tiles]
    print("Retrieved media ledger (metal removed from the sea, not destroyed):")
    for element, mass in ledger.totals_kg.items():
        print(
            f"  {element}: {from_si_mass(mass, 'g'):.1f} g "
            f"({mass:.6f} kg) over {ledger.service_count} events"
        )
    print(f"  assumed cost: EUR {ledger.assumed_cost_eur:,.0f} (an assumption)")
    print()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_config.run_id,
        "generated_by": "examples/reactive_layer/scripted_layer.py",
        "model_ref": "docs/MODEL_SPEC.md sections 3 and 4",
        "provenance": "synthetic_demo",
        "warning": BURIAL_WARNING,
        "note": (
            "Scripted offline demonstration. No map, no hardware, no network. "
            "Every parameter is an assumption; nothing here is a measurement or "
            "a product specification."
        ),
        "configuration": {
            "years": args.years,
            "dt_s": dt_s,
            "tiles_x": mat_config.tiles_x,
            "tiles_y": mat_config.tiles_y,
            "thickness_m": mat_config.thickness_m,
            "n_layer_nodes": mat_config.n_layer_nodes,
            "coverage_fraction": mat_config.coverage_fraction,
            "edge_leakage_fraction": mat_config.edge_leakage_fraction,
            "fouling_bypass_coupling": degradation.fouling_bypass_coupling,
            "burial_resistance_s_per_m": degradation.burial_resistance_s_per_m,
            "driving_schedule": [
                {"start_s": start, "porewater_kg_per_m3": values, "note": note}
                for start, values, note in DRIVING_SCHEDULE
            ],
        },
        "timeline": timeline,
        "events": service_events,
        "retrieved_media_ledger": ledger.as_dict(),
        "breakthrough_s_interval": {
            key: (None if value is None else list(value))
            for key, value in interval.items()
        },
        "final_tiles": summaries,
    }
    target = out_dir / "scripted_layer_timeline.json"
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    print(f"JSON timeline written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
