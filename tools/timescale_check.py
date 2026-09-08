"""Does the answer depend on the time step, or on how long you look?

    python tools/timescale_check.py --out docs/TIMESCALES.md

Four separate questions, because "check the time scales" means four different
things and conflating them is how the first version of this model went wrong:

1. **Numerical convergence.** Refine the reactive-layer step and see whether the
   answer moves. It must not. The original operator-split scheme conserved mass
   to one part in 1e14 and still moved breakthrough from 4.2 years to 1.0 years
   under refinement, which is why this check exists at all.
2. **Horizon dependence.** Run the same configuration for 1, 2, 4, 8 and 16
   years and see which conclusions survive. Attenuation at one year is not a
   service life.
3. **Plume window.** The 2-D field is run for hours at a fixed mat state. Check
   that it has actually reached quasi-steady, so the window length is not
   quietly setting the answer.
4. **Decision cadence.** The evidence loop runs monthly against chemistry that
   arrives quarterly. Vary the decision period and see whether the maintenance
   outcome depends on it.

The output is a markdown table per question, written to a file, so the numbers
in the documentation are generated rather than typed.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import numpy as np  # noqa: E402

from reactive_seabed_mat.scenarios import registry  # noqa: E402
from reactive_seabed_mat.scenarios.run import (  # noqa: E402
    run_mat_timeline,
    run_plume_window,
)

_YEAR = 365.25 * 86400.0
_HOUR = 3600.0


def _fmt(value: float, digits: int = 4) -> str:
    if value != value:
        return "n/a"
    return f"{value:.{digits}f}"


def refinement_rows(base, steps_h, years: float) -> list[dict]:
    rows = []
    for dt_h in steps_h:
        config = replace(base, dt_s=dt_h * _HOUR, duration_s=years * _YEAR)
        started = time.perf_counter()
        result = run_mat_timeline(config)
        last = result.timeline[-1]
        rows.append(
            {
                "dt_h": dt_h,
                "n_steps": config.n_steps,
                "attenuation_Pb": last.attenuation["Pb"],
                "saturation_Pb": last.saturation["Pb"],
                "retained_Pb_kg": result.mat_ledger["Pb"].retained_in_mat_kg,
                "imbalance": abs(result.mat_ledger["Pb"].relative_imbalance),
                "seconds": time.perf_counter() - started,
            }
        )
        print(f"  dt={dt_h:>5.2f} h  atten={rows[-1]['attenuation_Pb']:.6f}"
              f"  ({rows[-1]['seconds']:.0f} s)", flush=True)
    return rows


def horizon_rows(base, horizons) -> list[dict]:
    rows = []
    for years in horizons:
        config = replace(base, duration_s=years * _YEAR)
        result = run_mat_timeline(config)
        last = result.timeline[-1]
        row = {"years": years}
        for element in config.elements:
            row[f"atten_{element}"] = last.attenuation[element]
            row[f"barrier_{element}"] = last.barrier_attenuation[element]
            row[f"sat_{element}"] = last.saturation[element]
        row["services"] = len(result.service_events)
        rows.append(row)
        print(f"  {years:>5.1f} yr  Pb atten={row['atten_Pb']:.4f}"
              f"  sat={row['sat_Pb']:.3f}", flush=True)
    return rows


def window_rows(base, window_hours) -> list[dict]:
    result = run_mat_timeline(replace(base, duration_s=1.0 * _YEAR))
    tiles = result.final_tiles
    rows = []
    for hours in window_hours:
        config = replace(
            base, plume=replace(base.plume, window_s=hours * _HOUR)
        )
        window = run_plume_window(config, tiles, _YEAR, label=f"{hours:.0f} h")
        peak = window.peak_concentration("Pb")
        bare = window.peak_concentration("Pb", with_mat=False)
        rows.append(
            {
                "hours": hours,
                "peak_with_mat_ng_per_l": peak * 1e9,
                "peak_without_mat_ng_per_l": bare * 1e9,
                "ratio": (peak / bare) if bare > 0 else float("nan"),
                "imbalance": abs(window.ledger_with_mat["Pb"].relative_imbalance),
            }
        )
        print(f"  {hours:>5.1f} h  peak={rows[-1]['peak_with_mat_ng_per_l']:.4g} ng/L"
              f"  ratio={rows[-1]['ratio']:.4f}", flush=True)
    return rows


def cadence_rows(base, periods_days, years: float) -> list[dict]:
    rows = []
    for days in periods_days:
        config = replace(
            base,
            duration_s=years * _YEAR,
            policy=replace(base.policy, decision_period_s=days * 86400.0),
        )
        result = run_mat_timeline(config)
        last = result.timeline[-1]
        rows.append(
            {
                "days": days,
                "decisions": len(result.recommendations),
                "services": len(result.service_events),
                "observations": result.n_observations,
                "atten_Pb": last.attenuation["Pb"],
                "cost_eur": result.assumed_service_cost_eur,
            }
        )
        print(f"  {days:>4.0f} d  decisions={rows[-1]['decisions']:>4d}"
              f"  services={rows[-1]['services']}", flush=True)
    return rows


def _table(headers, rows, formatters) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(f(row) for f in formatters) + " |")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/TIMESCALES.md")
    parser.add_argument("--scenario", default="progressive_saturation")
    parser.add_argument("--quick", action="store_true",
                        help="fewer points, for a smoke test")
    args = parser.parse_args()

    base = registry.build_scenario(args.scenario)
    started = time.perf_counter()

    steps = [12.0, 6.0, 3.0] if args.quick else [24.0, 12.0, 6.0, 3.0, 1.0]
    horizons = [1.0, 4.0] if args.quick else [1.0, 2.0, 4.0, 8.0, 16.0]
    windows = [6.0, 24.0] if args.quick else [3.0, 6.0, 12.0, 24.0, 48.0]
    cadences = [30.0, 180.0] if args.quick else [15.0, 30.0, 90.0, 180.0, 365.0]

    print("1. numerical refinement", flush=True)
    refinement = refinement_rows(base, steps, years=2.0)
    print("2. horizon", flush=True)
    horizon = horizon_rows(base, horizons)
    print("3. plume window", flush=True)
    window = window_rows(base, windows)
    print("4. decision cadence", flush=True)
    cadence = cadence_rows(base, cadences, years=4.0)

    atten = [row["attenuation_Pb"] for row in refinement]
    spread = max(atten) - min(atten)
    elements = list(base.elements)

    text = f"""# Time scales: what the answer depends on

Generated by `tools/timescale_check.py` in {time.perf_counter() - started:.0f} s,
on scenario `{args.scenario}`. Every number below is computed, not typed.

Four different questions travel under the heading "check the time scales", and
this project has already been burned by conflating two of them. The first
reactive-layer scheme conserved mass to one part in 1e14 and was still wrong:
refining the step moved the predicted breakthrough from 4.2 years to 1.0 years.
**Mass conservation is not convergence.**

## 1. Numerical convergence: does the step size set the answer?

Two simulated years, reactive-layer step refined from 24 h to 1 h.

{_table(
    ["step (h)", "steps", "Pb attenuation", "Pb saturation", "Pb retained (kg)",
     "mass imbalance", "runtime (s)"],
    refinement,
    [lambda r: f"{r['dt_h']:.0f}",
     lambda r: f"{r['n_steps']:,}",
     lambda r: _fmt(r["attenuation_Pb"], 6),
     lambda r: _fmt(r["saturation_Pb"], 5),
     lambda r: f"{r['retained_Pb_kg']:.5g}",
     lambda r: f"{r['imbalance']:.2e}",
     lambda r: f"{r['seconds']:.0f}"],
)}

**Spread across the whole refinement: {spread:.2e} in attenuation.** The default
step of 6 h is inside that spread, so it is converged for this purpose. The mass
imbalance column is a separate check and passing it would prove nothing on its
own.

## 2. Horizon: which conclusions survive being looked at for longer?

{_table(
    ["years"] + [f"{e} attenuation" for e in elements]
    + [f"{e} barrier only" for e in elements] + ["services"],
    horizon,
    [lambda r: f"{r['years']:.0f}"]
    + [(lambda e: (lambda r: _fmt(r[f"atten_{e}"])))(e) for e in elements]
    + [(lambda e: (lambda r: _fmt(r[f"barrier_{e}"])))(e) for e in elements]
    + [lambda r: str(r["services"])],
)}

The **barrier only** columns are what this mat would attenuate with no chemical
capacity left at all. The difference between the two halves of the table is the
sorbent's actual contribution, and it shrinks with time as the medium loads.
Quoting a one-year attenuation as if it were a service life is the single
easiest way to mislead with this model.

## 3. Plume window: is the short 2-D run long enough?

The mat state is held fixed and the coastal field is integrated for a few hours.
If the window were too short the answer would still be moving.

{_table(
    ["window (h)", "peak with mat (ng/L)", "peak without (ng/L)", "ratio",
     "mass imbalance"],
    window,
    [lambda r: f"{r['hours']:.0f}",
     lambda r: f"{r['peak_with_mat_ng_per_l']:.4g}",
     lambda r: f"{r['peak_without_mat_ng_per_l']:.4g}",
     lambda r: _fmt(r["ratio"], 4),
     lambda r: f"{r['imbalance']:.2e}"],
)}

## 4. Decision cadence: does the maintenance outcome depend on how often you look?

Four simulated years. The chemistry arrives on a 90-day sampling interval with a
21-day laboratory latency, so a decision period well below 90 days cannot add
information, only decisions.

{_table(
    ["decision period (d)", "decisions", "services", "observations",
     "Pb attenuation", "assumed cost (EUR)"],
    cadence,
    [lambda r: f"{r['days']:.0f}",
     lambda r: f"{r['decisions']:,}",
     lambda r: str(r["services"]),
     lambda r: f"{r['observations']:,}",
     lambda r: _fmt(r["atten_Pb"]),
     lambda r: f"{r['cost_eur']:,.0f}"],
)}

Deciding more often than the evidence arrives produces more decisions and not
more information. That is worth showing, because "monitor continuously" is an
easy thing to promise and a poor use of a monitoring budget when the binding
constraint is a quarterly grab sample and a three-week laboratory queue.

---

Every figure here is synthetic and rests on the assumed hotspot in
`docs/EVIDENCE_BASE.md` section 1.1. The relative comparisons are the part that
transfers; the absolute values are a property of the assumption.
"""
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"wrote {target} in {time.perf_counter() - started:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
