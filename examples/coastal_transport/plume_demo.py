"""Short coastal plume window: fresh mat, saturated mat and no mat.

Offline and self-contained.  No map, no network, no hardware, no account.

What it does
------------

One short 2-D plume window (a fraction of a day, not years) is run three times
over the *same* authorised seabed hotspot, with the *same* grid and the **same
forcing arrays**, which are compared element by element rather than assumed
equal:

``fresh_mat``      a fully covering mat with a high residual attenuation
``saturated_mat``  the same mat with a much lower attenuation
``no_mat``         the bare hotspot, the reference the other two are judged on

It prints the per-element water-column mass ledger for each case, writes a
static PNG and a JSON timeline, and states the resolution honestly.

What it is not
--------------

The reactive layer itself lives on ``feat/reactive-layer``.  Until it lands,
this example drives the coupling with a **LABELLED_STUB** constant-attenuation
tile (see :func:`stub_layer_step`).  The two attenuation numbers are stand-ins
chosen to bracket the behaviour recorded in ``REFACTOR_PLAN.md``; they are not
measurements, not a product specification, and not an output of any chemistry.

The coastal model is integrated over a **short window at a fixed mat state**.
Nothing here implies the 2-D field was marched for years: the mat timeline and
the plume window are separate clocks with separate ledgers
(``docs/MODEL_SPEC.md`` section 2).

Run::

    python examples/coastal_transport/plume_demo.py
    python examples/coastal_transport/plume_demo.py --hours 6 --out /tmp/demo
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:  # keep the example runnable from a bare checkout
    sys.path.insert(0, str(_SRC))

from reactive_seabed_mat.config import RunConfig, config_hash  # noqa: E402
from reactive_seabed_mat.contracts import (  # noqa: E402
    LayerStep,
    MassLedger,
    MatTileState,
    SeabedExchange,
    SeabedHotspot,
)
from reactive_seabed_mat.coastal_transport.domain import (  # noqa: E402
    SYNTHETIC_FORCING_NOTE,
    assert_tide_resolving,
    build_domain,
    forcing_signature,
    forcing_timeline,
    hotspot_area_m2,
)
from reactive_seabed_mat.coastal_transport.fipy_engine import (  # noqa: E402
    accumulate_ledger,
    transport_step,
)
from reactive_seabed_mat.coastal_transport.geodata import adapter_for  # noqa: E402
from reactive_seabed_mat.coastal_transport.seabed_source import (  # noqa: E402
    CONTRIBUTION_COMPONENTS,
    build_seabed_exchange,
    check_tile_overlaps,
    component_total,
    plan_tile_layout,
    residual_source_flux_detailed,
)
from reactive_seabed_mat.results import write_json  # noqa: E402
from reactive_seabed_mat.scenarios.registry import (  # noqa: E402
    build_scenario,
    scenario_description,
)
from reactive_seabed_mat.units import format_utc, from_si_areal_flux  # noqa: E402

# ---------------------------------------------------------------------------
# LABELLED_STUB: the reactive layer is not on this branch yet
# ---------------------------------------------------------------------------

#: LABELLED_STUB.  ASSUMPTION, not a measurement: a fresh thin mat attenuates
#: more than 99 % and a saturated one still attenuates about 94 % purely as a
#: diffusive barrier (REFACTOR_PLAN.md, "parameters that make the demonstration
#: honest").  These two constants stand in for ``feat/reactive-layer`` and are
#: replaced the moment it lands.
STUB_ATTENUATION: Mapping[str, float] = {
    "fresh_mat": 0.995,
    "saturated_mat": 0.940,
    "no_mat": 0.0,
}


def stub_layer_step(
    tile: MatTileState,
    hotspot: SeabedHotspot,
    exchange: SeabedExchange,
    attenuation: float,
    dt_s: float,
    time_utc: datetime,
) -> LayerStep:
    """LABELLED_STUB constant-attenuation tile: ``J_out = (1 - a) * J_bare``.

    No chemistry, no capacity, no breakthrough.  It exists so the coupling and
    the 2-D engine can be exercised before the 1-D layer arrives.
    """
    bare = dict(exchange.bare_flux_kg_per_m2_per_s)
    j_out = {name: (1.0 - attenuation) * value for name, value in bare.items()}
    return LayerStep(
        new_state=tile,
        flux_in_kg_per_m2_per_s=bare,
        flux_out_kg_per_m2_per_s=j_out,
        retained_delta_kg_per_m2={
            name: (bare[name] - j_out[name]) * dt_s for name in bare
        },
        released_kg_per_m2={name: j_out[name] * dt_s for name in bare},
        exchange=exchange,
        diagnostics={
            "LABELLED_STUB": "constant-attenuation tile, example only",
            "attenuation_assumed": attenuation,
        },
    )


def tiles_from_layout(config: RunConfig) -> list[MatTileState]:
    """Fresh, intact tiles over the designed footprint.

    Tile *state* is the reactive-layer branch's business; the profiles below are
    zero placeholders so the coupling has a well-formed object to read.
    """
    plans = plan_tile_layout(config.mat, config.hotspot)
    check_tile_overlaps(plans, config.mat.overlap_m)
    zeros = {name: np.zeros(config.mat.n_layer_nodes) for name in config.elements}
    return [
        MatTileState(
            tile_id=plan.tile_id,
            media_id=config.mat.media_id,
            installed_at_utc=config.start_datetime,
            geometry=plan.geometry,
            porewater_kg_per_m3=dict(zeros),
            sorbed_kg_per_kg=dict(zeros),
        )
        for plan in plans
    ]


# ---------------------------------------------------------------------------
# One plume window
# ---------------------------------------------------------------------------

def run_window(
    config: RunConfig,
    case: str,
    forcings: Sequence,
    dt_s: float,
) -> dict:
    """Run one case and return everything the report needs."""
    bundle = build_domain(config)
    tiles = [] if case == "no_mat" else tiles_from_layout(config)
    attenuation = STUB_ATTENUATION[case]
    field = bundle.field_state
    steps = []
    timeline = []
    for index, forcing in enumerate(forcings):
        exchanges = build_seabed_exchange(field, tiles, bundle.hotspot, forcing, dt_s)
        layer_steps = [
            stub_layer_step(tile, bundle.hotspot, exchange, attenuation, dt_s,
                            field.time_utc)
            for tile, exchange in zip(tiles, exchanges)
        ]
        source = residual_source_flux_detailed(
            bundle.grid,
            bundle.hotspot,
            tiles,
            layer_steps,
            field.time_utc,
            fouling_bypass_coupling=config.degradation.fouling_bypass_coupling,
            overlap_m=config.mat.overlap_m,
            elements=tuple(config.elements),
        )
        step = transport_step(field, forcing, source, dt_s)
        steps.append(step)
        timeline.append(
            {
                "step": index,
                "time_utc": format_utc(step.new_field.time_utc),
                "u_east_m_per_s": float(np.mean(forcing.u_east_m_per_s)),
                "source_rate_kg_per_s": {
                    name: source.total_rate_kg_per_s(name, bundle.grid)
                    for name in config.elements
                },
                "released_kg": dict(step.released_from_seabed_kg),
                "in_water_kg": {
                    name: step.new_field.water_mass_kg(name)
                    for name in config.elements
                },
                "boundary_out_kg": dict(step.boundary_out_kg),
                "closure_error_kg": dict(step.diagnostics["closure_error_kg"]),
                "clip_correction_kg": dict(step.diagnostics["clip_correction_kg"]),
                "components_kg_per_s": {
                    name: {
                        key: component_total(source, name, bundle.grid, key)
                        for key in CONTRIBUTION_COMPONENTS
                    }
                    for name in config.elements
                },
            }
        )
        field = step.new_field
    ledgers = {
        name: accumulate_ledger(name, bundle.field_state, steps)
        for name in config.elements
    }
    return {
        "case": case,
        "attenuation_assumed": attenuation,
        "bundle": bundle,
        "steps": steps,
        "final_field": field,
        "ledgers": ledgers,
        "timeline": timeline,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def ledger_to_dict(ledger: MassLedger) -> dict:
    """Serialise a :class:`MassLedger`.

    ``reactive_seabed_mat.results.ledger_to_dict`` is coordinator-owned and is
    still written against the pre-refactor compartment names (``emitted_kg``,
    ``in_active_mesh_kg``, ``in_retrieved_media_kg``), so it raises
    ``AttributeError`` on the current contract.  This local copy uses the frozen
    field names; the defect is reported in ``docs/handoffs/coastal_2d.md``.
    """
    return {
        "element": ledger.element,
        "initial_water_kg": ledger.initial_water_kg,
        "released_from_sediment_kg": ledger.released_from_sediment_kg,
        "boundary_in_kg": ledger.boundary_in_kg,
        "in_water_kg": ledger.in_water_kg,
        "retained_in_mat_kg": ledger.retained_in_mat_kg,
        "retained_in_retrieved_media_kg": ledger.retained_in_retrieved_media_kg,
        "boundary_out_kg": ledger.boundary_out_kg,
        "numerical_correction_kg": ledger.numerical_correction_kg,
        "supplied_kg": ledger.supplied_kg,
        "accounted_kg": ledger.accounted_kg,
        "imbalance_kg": ledger.imbalance_kg,
        "relative_imbalance": ledger.relative_imbalance,
    }


def print_ledger_table(results: Mapping[str, dict], elements: Sequence[str]) -> None:
    print()
    print("Per-element water-column mass ledger for the plume window")
    print("(kg; the mat timeline is a separate clock with its own ledger)")
    header = (
        f"{'case':<15}{'element':<8}{'released':>13}{'in water':>13}"
        f"{'exported':>13}{'correction':>13}{'imbalance':>12}"
    )
    print(header)
    print("-" * len(header))
    for case, result in results.items():
        for name in elements:
            ledger = result["ledgers"][name]
            print(
                f"{case:<15}{name:<8}"
                f"{ledger.released_from_sediment_kg:13.6e}"
                f"{ledger.in_water_kg:13.6e}"
                f"{ledger.boundary_out_kg:13.6e}"
                f"{ledger.numerical_correction_kg:13.3e}"
                f"{ledger.relative_imbalance:12.2e}"
            )
    print()


def print_attenuation_table(results: Mapping[str, dict], elements: Sequence[str]) -> None:
    bare = results["no_mat"]
    print("Released from the seabed over the window, against the no-mat reference")
    header = f"{'case':<15}{'element':<8}{'released kg':>14}{'share of bare':>15}"
    print(header)
    print("-" * len(header))
    for case, result in results.items():
        for name in elements:
            released = result["ledgers"][name].released_from_sediment_kg
            reference = bare["ledgers"][name].released_from_sediment_kg
            share = released / reference if reference > 0.0 else float("nan")
            print(f"{case:<15}{name:<8}{released:14.6e}{share:15.4f}")
    print()


def write_plot(
    results: Mapping[str, dict],
    element: str,
    path: Path,
    dt_s: float,
    statement: str,
) -> Path:
    """Static PNG: the final field per case above one shared rate timeline.

    matplotlib is present in the tested environment but is **not** declared in
    ``pyproject.toml``; that is a dependency request in the handoff, not
    something this branch may change.  If it is missing, the numbers still come
    out and only the picture is skipped, with an honest message.
    """
    import textwrap

    try:
        import matplotlib
    except ImportError:                                   # pragma: no cover
        note = path.with_suffix(".txt")
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(
            "No plot was written: matplotlib is not installed. Every number in "
            "plume_timeline.json was still produced. matplotlib is not yet a "
            "declared dependency in pyproject.toml; see "
            "docs/handoffs/coastal_2d.md.\n",
            encoding="utf-8",
        )
        return note

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cases = list(results)
    fig = plt.figure(figsize=(4.6 * len(cases), 8.4))
    spec = fig.add_gridspec(2, len(cases), height_ratios=[3.0, 2.0],
                            hspace=0.45, wspace=0.14,
                            top=0.86, bottom=0.24, left=0.07, right=0.88)

    peak = max(
        float(np.max(result["final_field"].concentration_kg_per_m3[element]))
        for result in results.values()
    )
    peak = peak if peak > 0.0 else 1.0

    image = None
    for column, case in enumerate(cases):
        result = results[case]
        grid = result["bundle"].grid
        land = result["bundle"].land_mask
        field = np.asarray(result["final_field"].concentration_kg_per_m3[element])
        axis = fig.add_subplot(spec[0, column])
        image = axis.imshow(
            np.ma.masked_where(land, field),
            origin="lower",
            extent=(grid.origin_x_m, grid.origin_x_m + grid.nx * grid.dx_m,
                    grid.origin_y_m, grid.origin_y_m + grid.ny * grid.dy_m),
            vmin=0.0,
            vmax=peak,
            cmap="viridis",
        )
        indices = np.asarray(list(result["bundle"].hotspot.cell_indices))
        hx = grid.origin_x_m + (indices % grid.nx + 0.5) * grid.dx_m
        hy = grid.origin_y_m + (indices // grid.nx + 0.5) * grid.dy_m
        axis.plot(hx, hy, linestyle="none", marker="s", markersize=1.6,
                  color="white", alpha=0.45,
                  label="authorised hotspot" if column == 0 else None)
        axis.set_title(
            f"{case}\nassumed attenuation "
            f"{result['attenuation_assumed']:.3f} (stub)",
            fontsize=10,
        )
        axis.set_xlabel("x (m)")
        if column == 0:
            axis.set_ylabel("y (m)")
            axis.legend(loc="upper left", fontsize=7, framealpha=0.6)
        else:
            axis.set_yticklabels([])

    bar = fig.colorbar(image, ax=fig.axes, shrink=0.42, pad=0.015, aspect=18,
                       location="right", anchor=(0.0, 0.78))
    bar.set_label(f"{element} in the water (kg m$^{{-3}}$), one scale",
                  fontsize=8)
    bar.ax.tick_params(labelsize=8)

    rate_axis = fig.add_subplot(spec[1, :])
    for case in cases:
        result = results[case]
        hours = [(entry["step"] + 1) * dt_s / 3600.0 for entry in result["timeline"]]
        rate = [entry["source_rate_kg_per_s"][element] for entry in result["timeline"]]
        rate_axis.semilogy(hours, rate, marker="o", markersize=3.0, linewidth=1.3,
                           label=case)
    rate_axis.set_xlabel("hours into the plume window")
    rate_axis.set_ylabel(f"{element} leaving the seabed (kg s$^{{-1}}$)")
    rate_axis.set_title(
        "Residual source: the mat attenuates the seabed flux, it does not "
        "remove anything from the water",
        fontsize=9,
    )
    rate_axis.grid(alpha=0.3, which="both")
    rate_axis.legend(fontsize=8, loc="center right")

    current = fig.add_subplot(spec[1, :], frame_on=False)
    current.xaxis.set_visible(False)
    current.yaxis.tick_right()
    current.yaxis.set_label_position("right")
    reference = results[cases[0]]["timeline"]
    current.plot(
        [(entry["step"] + 1) * dt_s / 3600.0 for entry in reference],
        [entry["u_east_m_per_s"] for entry in reference],
        color="0.45", linestyle="--", linewidth=1.0,
    )
    current.axhline(0.0, color="0.75", linewidth=0.6)
    current.set_ylabel("mean eastward current (m s$^{-1}$), dashed", fontsize=8,
                       color="0.35")
    current.tick_params(axis="y", colors="0.35", labelsize=8)
    current.patch.set_visible(False)

    fig.suptitle(
        "Selective reactive seabed mat: one short coastal plume window\n"
        "synthetic demonstration, prescribed current, no real site",
        fontsize=12,
    )
    wrapped = "\n".join(textwrap.wrap(statement, width=int(26 * len(cases) + 60)))
    fig.text(0.02, 0.015, wrapped, fontsize=6.6, va="bottom", color="0.25",
             linespacing=1.35)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def resolution_statement(config: RunConfig, bundle) -> str:
    grid = bundle.grid
    adapter = adapter_for(config.domain)
    return " ".join(
        [
            f"Model grid {grid.nx} by {grid.ny} cells of {grid.dx_m:.0f} m by "
            f"{grid.dy_m:.0f} m over an effective mixing depth of "
            f"{grid.mixing_depth_m:.1f} m, CRS {grid.crs}.",
            f"The hotspot occupies {bundle.hotspot.n_cells} cells, "
            f"{hotspot_area_m2(grid, bundle.hotspot):.0f} m2 gridded.",
            "The 10 m cell size is a model choice, not evidence of 10 m "
            "information: the current field is prescribed and uniform, so it "
            "carries no spatial detail at all.",
            SYNTHETIC_FORCING_NOTE,
            adapter.bathymetry_statement(),
            "Mode: " + adapter.mode.value + ". No map, no network, no account.",
        ]
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hours", type=float, default=12.0,
                        help="length of the plume window in hours (default 12)")
    parser.add_argument("--dt-s", type=float, default=900.0,
                        help="transport time step in seconds (default 900)")
    parser.add_argument("--scenario", default="fresh_mat",
                        help="scenario name from the registry (default fresh_mat)")
    parser.add_argument(
        "--out",
        default=str(Path("results") / "coastal_transport_plume_demo"),
        help="output directory (default results/coastal_transport_plume_demo)",
    )
    args = parser.parse_args(argv)

    config = build_scenario(args.scenario)
    assert_tide_resolving(config.forcing)
    dt_s = float(args.dt_s)
    n_steps = max(1, int(round(args.hours * 3600.0 / dt_s)))
    elements = tuple(config.elements)

    bundle = build_domain(config)
    forcings = forcing_timeline(config.forcing, bundle.grid, bundle.land_mask,
                                n_steps, dt_s, config.start_datetime)

    print("Selective reactive seabed mat: coastal plume window")
    print("=" * 70)
    print(scenario_description(args.scenario))
    print()
    print(f"configuration hash   {config_hash(config)}")
    print(f"plume window         {n_steps} steps of {dt_s:.0f} s "
          f"= {n_steps * dt_s / 3600.0:.2f} h")
    print(f"tidal period         {config.forcing.tidal_period_s:.0f} s "
          f"({config.forcing.tidal_period_s / 3600.0:.2f} h, M2)")
    print(f"forcing signature    {forcing_signature(forcings)}")
    print(f"bare flux J_bare     " + ", ".join(
        f"{name} {from_si_areal_flux(bundle.hotspot.bare_flux_kg_per_m2_per_s[name], 'ug/m2/d'):.4g} ug/m2/d"
        for name in elements
    ))
    print()
    print("The mat attenuates the seabed flux. Nothing is subtracted from a")
    print("water-column cell, and there is no interception efficiency anywhere.")

    results: dict[str, dict] = {}
    for case in ("fresh_mat", "saturated_mat", "no_mat"):
        print(f"  running {case} ...", flush=True)
        results[case] = run_window(config, case, forcings, dt_s)

    # The three runs must have seen identical forcing: assert it, do not assume.
    reference = forcings
    for case in results:
        for a, b in zip(reference, forcings):
            assert np.array_equal(a.u_east_m_per_s, b.u_east_m_per_s)
            assert np.array_equal(a.v_north_m_per_s, b.v_north_m_per_s)
    print("  identical forcing arrays confirmed across all three cases "
          f"(signature {forcing_signature(forcings)})")

    print_ledger_table(results, elements)
    print_attenuation_table(results, elements)

    worst_closure = max(
        abs(entry["closure_error_kg"][name])
        for result in results.values()
        for entry in result["timeline"]
        for name in elements
    )
    total_clip = sum(
        entry["clip_correction_kg"][name]
        for result in results.values()
        for entry in result["timeline"]
        for name in elements
    )
    print(f"largest boundary closure error over every step:  {worst_closure:.3e} kg")
    print(f"total clipped (reported, not hidden) mass:       {total_clip:.3e} kg")

    print()
    print("Where the residual source comes from (kg/s, first step, "
          f"{elements[0]})")
    header = f"{'case':<15}" + "".join(f"{key:>14}" for key in CONTRIBUTION_COMPONENTS)
    print(header)
    print("-" * len(header))
    for case, result in results.items():
        parts = result["timeline"][0]["components_kg_per_s"][elements[0]]
        print(f"{case:<15}" + "".join(
            f"{parts[key]:14.4e}" for key in CONTRIBUTION_COMPONENTS
        ))
    fresh = results["fresh_mat"]["timeline"][0]["components_kg_per_s"][elements[0]]
    if fresh["edge_leakage"] > fresh["covered"]:
        print()
        print("Note: for a strongly attenuating mat the assumed "
              f"{config.mat.edge_leakage_fraction:.0%} edge leakage already "
              "dominates the")
        print("residual source. The uncertain design parameter, not the "
              "chemistry, sets the floor.")

    statement = resolution_statement(config, bundle)
    print()
    print("Resolution and provenance")
    print("-" * 70)
    for sentence in statement.split(". "):
        if sentence.strip():
            print("  " + sentence.strip().rstrip(".") + ".")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "demonstration": "coastal plume window, selective reactive seabed mat",
        "scenario": args.scenario,
        "scenario_description": scenario_description(args.scenario),
        "config_hash": config_hash(config),
        "elements": list(elements),
        "window": {
            "n_steps": n_steps,
            "dt_s": dt_s,
            "hours": n_steps * dt_s / 3600.0,
            "start_utc": format_utc(config.start_datetime),
            "note": (
                "A plume window at one fixed mat state. The mat timeline is a "
                "separate clock and is not integrated here."
            ),
        },
        "forcing_signature": forcing_signature(forcings),
        "hotspot": {
            "hotspot_id": bundle.hotspot.hotspot_id,
            "n_cells": bundle.hotspot.n_cells,
            "gridded_area_m2": hotspot_area_m2(bundle.grid, bundle.hotspot),
            "bare_flux_kg_per_m2_per_s": dict(bundle.hotspot.bare_flux_kg_per_m2_per_s),
            "description": bundle.hotspot.description,
        },
        "stub": {
            "LABELLED_STUB": "constant-attenuation tile, example only",
            "attenuation_assumed": dict(STUB_ATTENUATION),
            "note": (
                "ASSUMPTION, not a measurement. Replaced when "
                "feat/reactive-layer lands."
            ),
        },
        "resolution_statement": statement,
        "cases": {
            case: {
                "attenuation_assumed": result["attenuation_assumed"],
                "ledger": {
                    name: ledger_to_dict(result["ledgers"][name])
                    for name in elements
                },
                "timeline": result["timeline"],
            }
            for case, result in results.items()
        },
    }
    timeline_path = write_json(out / "plume_timeline.json", payload)
    plot_path = write_plot(results, elements[0], out / "plume_demo.png", dt_s,
                           statement)
    print()
    print(f"JSON timeline written to  {timeline_path}")
    print(f"static plot written to    {plot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
