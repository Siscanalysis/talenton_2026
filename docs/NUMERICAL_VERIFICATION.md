# Reproducing the revised numerical audit

Run these commands from the repository root in the project environment. The
plotting tools also need Matplotlib, which is present in the manuscript build
environment. Each script imports this checkout's `src` explicitly.

```powershell
python -m pytest tests/reactive_layer -q
python tools/revision_numerics.py --output results/numerical-audit
python tools/benchmark_layer_memo.py --days 30
python tools/timescale_check.py --out docs/TIMESCALES.md --workers 2
python tools/render_numerical_results.py --output manuscript
```

`revision_numerics.py` exports the independent nonlinear BDF comparison,
stationary spatial refinement, exact discrete barrier comparison and a source
step example into `results/numerical-audit/reactive_numerical_audit.json`, PDF
and PNG. The accelerated verification capacity is not a new material
calibration. Its errors quantify a particular problem; conservation alone does
not establish convergence, and changing forcing can legitimately produce bumps.

`timescale_check.py` regenerates all temporal, horizon, plume-window, decision
cadence and coastal discretisation results. Independent tasks use two worker
processes by default. JSON caches are keyed by source files, script,
configuration and task; a source change creates a new key. The final artifact
records whether the source changed during its execution. Exact horizon samples
come from one continuous longest trajectory. The 24-hour coastal audit compares
600/300/150-second steps at 10 m and 20/10/5-m grids at 150 s. Tidal window
length, numerical time step and physical service age are different studies.

`render_numerical_results.py` reads completed JSON, writes
`manuscript/numerical_results.tex`, and copies the three new figures and audit
data into the manuscript package. Values and captions therefore refer to
generated results instead of rounded or stale historical tables.

## Exact reuse of equivalent tile calculations

The runner solves each distinct vertical state once within an individual
advance call. Matching requires exact profile bytes and all inputs consumed by
the reactive layer, including geometry dimensions, condition, boundary
concentrations, seepage, film and relevant environment coefficients. No rounded
keys or approximate profile matching are used. Tile position and media identity
are preserved in each target's returned state and exchange; arrays and
diagnostic mappings are copied so tiles remain independently mutable.

Fourteen dedicated regression cases compare every field against independent
per-tile advancement, with exact array bytes, at zero and six-hour steps. Cases
include identity-only differences, service metadata, changed source, nonuniform
bottom water, unequal profiles, fouling, burial, damage, displacement, geometry
differences and nondefault bypass coupling. All 14 passed. Nine identical tiles
invoke the physical advance once, while physically different tiles remain
separate. This changes computational repetition, not a model law.

`benchmark_layer_memo.py` additionally checks the entire `MatTimelineResult`
over 30 days, recursively including observations, recommendations, estimates,
inventories, source totals and captured states. Its JSON records source and
configuration hashes, machine/Python details and the timings. A first paired
check gave 5.49 s with reuse versus 11.76 s without (2.14x); the recorded repeat
under concurrent workload gave 6.62 s versus 7.75 s (1.17x), with complete
bitwise-equivalent output. These local timings are workload dependent. The
reduction from nine equivalent solver invocations to one is not a claim of
ninefold end-to-end speedup.

## Scientific limits retained

The capacity-lock rule has a finite discontinuity at accessible capacity and is
an unvalidated material assumption. The exact discrete barrier isolates a
numerical reference consistently, but its difference from transient attenuation
still includes dissolved storage and forcing history. A conservative source
ledger and a conservative column ledger use different control volumes. A small
mass residual cannot certify a coastal peak concentration, a keratin uptake law,
or a maintenance decision.
