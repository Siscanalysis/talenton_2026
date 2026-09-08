# Handoff: `feat/reactive-layer`

The 1-D reactive layer through the mat thickness, the two boundary fluxes, the
attenuation derived from them, the four independent degradation modes, modular
replacement into a retrieved-media ledger, and a conditional breakthrough
forecast that is an interval or nothing at all.

Implements `docs/MODEL_SPEC.md` sections 3 and 4.

Owned paths: `src/reactive_seabed_mat/reactive_layer/`, `tests/reactive_layer/`,
`examples/reactive_layer/`, this file.

---

## 1. What changed in the package

| File | Action | Note |
|---|---|---|
| `material.py` | kept, retyped | now reads `ReactiveMediumConfig` / `MatLayoutConfig`; gained `d_eff_m2_per_s` and a diffusivity fouling factor; the ensemble samples edge leakage instead of an interception fraction |
| `column.py` | **new** | the fully implicit coupled solver, transcribed from `docs/reactive_layer_numerics_probe.py` |
| `flux.py` | **new** | `J_in`, `J_out`, `J_bare`, attenuation, the barrier floor, ensemble intervals |
| `degradation.py` | **new** | the four modes, the fouling bypass, the burial resistance, scheduled events |
| `tile.py` | **new**, replaces `panel.py` | `advance_reactive_layer` and the tile grid; `panel.py` deleted |
| `service.py` | kept, extended | `replace_tiles` for a subset of tiles; `ServiceEvent.tile_ids` is a sequence |
| `forecast.py` | adapted | the target is breakthrough of the layer, and the answer is an interval or `None` |
| `__init__.py` | rewritten | re-export facade; `design.py` deliberately excluded |
| `examples/reactive_layer/scripted_contact.py` | deleted | replaced by `scripted_layer.py` |

`design.py` was left untouched as instructed. It still imports the deleted
vertical-panel types, so it is **not** imported by `__init__.py`; importing
`reactive_seabed_mat.reactive_layer` does not drag a broken module in with it.
It moves to `optimisation/sweep.py` on `feat/optimisation`.

---

## 2. Public functions

### `tile.py`

```python
advance_reactive_layer(tile_state, exchange, material_parameters, dt_s) -> LayerStep
```
The frozen signature, unchanged, verified against
`contracts.AdvanceReactiveLayer` by `test_tile.py`. Runs one implicit column
step per element, returns the two boundary fluxes per unit area of intact
layer, and sets `LayerStep.exchange` to the exchange it was given.

```python
build_tile_states(mat_config, installed_at_utc, materials, *, hotspot=None,
                  elements=None, initial_fouling_index=0.0) -> tuple[MatTileState, ...]
build_tile_geometry(mat_config, hotspot, ix, iy) -> MatTileGeometry
tile_id_for(ix, iy) -> str                      # "tile_{ix}_{iy}"
release_from_damage(tile_state, exchange, *, released_fraction_by_element=None,
                    released_kg_per_m2_by_element=None, reason=...) -> LayerStep
scripted_exchange(tile_state, time_utc, dt_s, sediment_porewater_kg_per_m3, ...)
tile_summary(tile_state, material_parameters, *, layer_step=None, ...) -> dict
```

### `column.py`

```python
ColumnParameters, ColumnStep
build_column_parameters(geometry, params, *, n_nodes, seepage_velocity_m_per_s,
                        film_transfer_m_per_s, fouling_index=0.0)
top_conductance(params) -> float
solve_column_step(porewater, sorbed, params, dt_s, c_sed, c_water, *,
                  top_conductance_m_per_s=None, picard_iterations=6) -> ColumnStep
stored_kg_per_m2(porewater, sorbed, params) -> float
steady_state_flux_kg_per_m2_per_s(params, c_sed, c_water=0.0, *,
                                  top_conductance_m_per_s=None) -> float
```

### `flux.py`

```python
bare_flux_kg_per_m2_per_s(v, k_film, c_sed, c_water) -> float
bare_flux_from_exchange(exchange, element) -> tuple[float, str]
attenuation(j_out, j_bare) -> float | None
flux_budget(layer_step, exchange, element, *, barrier_flux=None) -> FluxBudget
ensemble_flux_interval(tile_state, exchange, materials, dt_s, ...) -> dict[str, FluxInterval]
attenuation_interval(tile_state, exchange, materials, dt_s, ...) -> dict[str, tuple | None]
```

### `degradation.py`

```python
bypass_fraction(edge_leakage_fraction, fouling_index, coupling) -> BypassFraction
buried_top_conductance(g_top, burial_depth_m, burial_resistance_s_per_m) -> float
effective_cover_fraction(coverage_fraction, bypass) -> float
tile_effective_flux_kg_per_m2_per_s(j_out, j_bare, coverage_fraction, bypass) -> float
grow_fouling(tile_state, growth_per_s, dt_s) -> MatTileState
grow_burial(tile_state, growth_m_per_s, dt_s) -> MatTileState
apply_degradation_event(tile_state, event) -> tuple[MatTileState, dict]
apply_degradation_events(tile_states, events, window_start_s, window_end_s)
saturation_state(tile_state, materials) -> dict
degradation_state(tile_state, materials, ...) -> dict      # all four, side by side
```

### `service.py`

```python
replace_tiles(tile_states, tile_ids, time_utc, *, ledger=None, ...) -> (tuple, ServiceEvent)
replace_media(tile_state, time_utc, ...) -> (MatTileState, ServiceEvent)
replacement_cost_eur(costs, *, n_tiles, media_area_m2, retrieved_media_mass_kg, ...)
RetrievedMediaLedger, next_media_id, MEDIA_DISPOSAL_NOTE
```

### `forecast.py`

```python
breakthrough_interval(...) -> dict[str, tuple[float, float] | None]
forecast_breakthrough(...) -> LayerForecast
forecast_tile(tile_state, materials, supply_flux_kg_per_m2_per_s, ...) -> LayerForecast
sorbed_kg_per_m2, loading_kg_per_kg, loading_fraction,
remaining_capacity_kg_per_m2, supply_limited_breakthrough_s, time_to_target_loading
```

### `material.py`

Unchanged names, plus `effective_d_eff_m2_per_s`. `FoulingFactors` gained
`diffusivity_factor`; `ParameterEnsemble` carries `edge_leakage_fraction` where
it used to carry `interception_efficiency`.

---

## 3. Exact run commands

```
cd "C:\Users\Artelnics\Desktop\TalentON_2026\software\worktrees\layer"
& "..\reactive-seabed-mat-demo\.venv\Scripts\python.exe" -m pytest tests/contracts -q
& "..\reactive-seabed-mat-demo\.venv\Scripts\python.exe" -m pytest tests/reactive_layer -q
& "..\reactive-seabed-mat-demo\.venv\Scripts\python.exe" examples/reactive_layer/scripted_layer.py
& "..\reactive-seabed-mat-demo\.venv\Scripts\python.exe" examples/reactive_layer/scripted_layer.py --years 1.5 --dt-hours 24 --out somewhere
```

The example takes about 30 s at its defaults (nine tiles, two elements, six
years, `dt = 12 h`, 40 nodes). `--years 1.5 --dt-hours 24` runs in about 4 s.

---

## 4. Tests actually executed, with real outcomes

```
> python -m pytest tests/contracts
88 passed in 7.94s

> python -m pytest tests/reactive_layer
67 passed in 22.24s

slowest:
  9.33s  test_refinement.py (module fixture: four multi-year marches)
  2.90s  test_degradation.py::test_fouling_lowers_the_flux_...but_is_never_a_benefit
  2.80s  test_fipy_crosscheck.py::test_pure_diffusion_matches_a_fipy_grid1d_solve
```

All 155 pass. Nothing is xfailed, skipped or deleted.

### The measured numbers the tests assert

**Time-step refinement** (`test_refinement.py`), reference parameters, 3.4 years:

| dt | breakthrough | final loading | largest backward step | relative mass residual |
|---|---|---|---|---|
| 12 h | 3.0883 yr | 0.982402 | 0 | 1.8e-14 |
| 6 h | 3.0869 yr | 0.982405 | 0 | 4.4e-13 |
| 3 h | 3.0862 yr | 0.982409 | 0 | 3.4e-14 |
| 1 h | 3.0860 yr | 0.982410 | 0 | 4.2e-12 |

Breakthrough spread over a twelvefold change of time step: 0.0023 yr, that is
0.8 days. The specification claims about 3.09 years; the solver gives 3.086 to
3.088. This is the test the scheme exists to pass: the rejected split-operator
scheme moved from 4.21 yr to 1.03 yr over the same range while conserving mass
to 1e-14.

**Mass conservation** (`test_column_conservation.py`), six years at `dt = 12 h`:
cumulative relative residual 2.8e-14 (tolerance 1e-9), worst single-step
residual 4.2e-16 of the layer capacity. No clipping occurs in the reference run,
and the test asserts that rather than assuming it.

**FiPy cross-check** (`test_fipy_crosscheck.py`): pure diffusion, 200 steps of
1 h, maximum relative difference against a `Grid1D` solve **3.5e-14**. FiPy's LU
solver does iterative refinement and stops at a default tolerance that leaves
about 2e-3 relative error on this stiff matrix, so the test sets
`LinearLUSolver(tolerance=1e-16, iterations=50)`. That is a property of the
oracle's stopping rule, not of either discretisation, and it is stated in the
test. A second test doubles the top conductance in the oracle and asserts the
comparison then **fails**, so the agreement is a real constraint.

**Attenuation** (`test_limits.py`):

| state | `J_out / J_bare` | attenuation |
|---|---|---|
| fresh, 1 yr | 8.0e-7 | 0.99999920 |
| fresh, 2 yr | 1.6e-3 | 0.99838 |
| saturated (preloaded to `q_max`) | 0.059729 | 0.940271 |
| zero capacity (`q_max = 0`) | 0.059729 | 0.940271 |

The chemical contribution of the sorbent is **0.0597**, the difference between
the fresh and the saturated value, not the 0.99999 headline. The zero-capacity
and saturated fluxes agree bit for bit, which is the honest statement of "the
sorbent contributes nothing here".

**Fouling** (`test_degradation.py`), saturated tile at steady state:

| fouling index | bypass | `J_out / J_bare` | emitted / `J_bare` |
|---|---|---|---|
| 0.00 | 0.020 | 0.0597 | 0.0785 |
| 0.25 | 0.108 | 0.0585 | 0.1597 |
| 0.50 | 0.195 | 0.0575 | 0.2413 |
| 0.75 | 0.283 | 0.0569 | 0.3233 |
| 1.00 | 0.370 | 0.0567 | 0.4057 |

Through the layer alone fouling *lowers* the flux, which is the trap. What the
footprint emits rises monotonically because the bypass grows faster than the
diffusivity benefit. Sorbed mass is unchanged at every level.

**Burial** (`test_degradation.py`): with the documented seepage velocity, 0.5 m
of sediment reduces the apparent flux by **3.9 %**; with no seepage the same
burial reduces it by **49.5 %**. The direction is what matters and the test says
so explicitly: a falling flux under a buried tile is not success.
`AmbiguityFlag.BURIAL` and `BURIAL_WARNING` are attached wherever burial is
non-zero.

**Local failure**: a displaced tile has `coverage_fraction == 0` and its
footprint emits exactly `J_bare`; a tile with `integrity_index = 0.65` emits
`0.65 J_out + 0.35 J_bare`, which for a fresh layer is 0.35 `J_bare` to 1e-6.

**Service**: single and partial replacement conserve the inventory exactly
(`==`, not `approx`). Replacing two named tiles out of nine moves exactly those
two tiles' inventory to the ledger and returns the other seven as the *same
objects*.

**Forecast**: every public entry point returns `tuple[float, float] | None`.
Tests assert the type, not only the value.

---

## 5. Assumptions made on this branch

Everything in `config.py` is already labelled an assumption. These are the ones
this branch **added**, all labelled in the code:

1. **Allocation scales both `Kd` and `q_max`.** `q` is carried per kilogram of
   *total* medium (which is what `MatTileState.retained_kg_per_m2` and
   `saturation_fraction` require), so the column uses
   `kd_column = alpha Kd` and `q_max_column = alpha q_max_eff`. Scaling both
   keeps the isotherm knee `q_max / Kd` independent of how the medium was split
   between Pb and Hg. Stated in `material.py` and `column.py`.
2. **A capacity-locked cell neither takes up nor releases.** MODEL_SPEC section
   4 says that if `q_max_eff` falls below the current load, uptake stops and `q`
   is unchanged. Implemented as a third branch alongside saturated and
   unsaturated, and locked cells are also exempt from the capacity clip: without
   that exemption, fouling pushed already-sorbed metal back into the porewater
   and out through `J_out`, which is exactly the "fouling deletes sorbed metal"
   failure the specification forbids. That was a real bug, caught by
   `test_fouling_never_reduces_sorbed_mass`.
3. **Desorption is permitted where the isotherm demands it** (`q > q_eq` with
   `q < q_max_eff`). It is conservative, it appears in `J_out`, and the count of
   desorbing cells is reported. The old panel model's
   "no spontaneous desorption" rule was a property of a bounded-transfer
   bookkeeping model and does not apply to a PDE with an explicit porewater
   phase.
4. **Mat layout.** The mat is a square of area
   `coverage_fraction * hotspot.area_m2`, centred on `(hotspot.x_m,
   hotspot.y_m)`, cut into `tiles_x * tiles_y` equal tiles.
   `MatLayoutConfig.overlap_m` is treated as a deployment tolerance and does not
   enlarge the tiles.
5. **`HotspotConfig.x_m` / `y_m` are read as the hotspot centre**, not a corner.
   See the contract request below.
6. **Defaults for the three numbers the frozen signature cannot carry**:
   `DEFAULT_BURIAL_RESISTANCE_S_PER_M = 2.0e8` and
   `DEFAULT_FOULING_BYPASS_COUPLING = 0.35`, both mirroring
   `config.DegradationConfig`. They are overridden per step through
   `SeabedExchange.environment`.
7. **Breakthrough in the forecast is a capacity proxy**: consumption of
   `DEFAULT_BREAKTHROUGH_FRACTION = 0.80` of the allocated capacity, standing in
   for the flux definition (`J_out / J_bare > 0.05`) the numerical probe uses.
   The two agree to within the width of the sorption front, and the note travels
   with the result.
8. **The one-step ensemble interval is conditional on the current profile.** A
   member with a different `Kd` would have built a different profile, so the
   interval is a one-step spread, not a full ensemble trajectory. Stated in
   `FluxInterval.notes`.
9. **Replacement resets the physical condition** (fouling, integrity, burial,
   displacement) by default, because recovering a tile and laying a fresh one
   does. `reset_physical_condition=False` isolates a single mode for a test.
10. **A tear does not spill loaded media.** `integrity_index` opens a bypass
    path; the media is still there. Physically losing loaded media is
    `release_from_damage`, an explicit event.

---

## 6. Deviation from the branch brief, stated openly

The brief asked for a test that
"zero capacity (`q_max = 0`) gives zero retention **and `J_out == J_bare`**".

The first half holds exactly and is asserted (`sorbed == 0` everywhere, not
approximately). **The second half is false for this product**, and implementing
it would have required either deleting the layer's transport resistance or
redefining `J_bare`. A layer with no chemical capacity is still 10 mm of
low-permeability medium: with the documented parameters it attenuates by 94.03 %
(`J_out / J_bare = 0.0597`). The same brief also asks, correctly, that a
saturated mat "still attenuates by roughly 94 % as a pure diffusive barrier", so
the two requirements contradict each other.

What is implemented and tested instead:

* `test_limits.py::test_zero_capacity_gives_exactly_zero_retention`: retention
  is exactly zero;
* `test_limits.py::test_zero_capacity_contributes_no_chemistry_but_still_is_a_barrier`
  shows that a zero-capacity layer passes **bit for bit** the same flux as a fully
  saturated one, which is the honest form of "the sorbent contributes nothing";
* `test_degradation.py::test_a_displaced_tile_has_coverage_fraction_zero_and_emits_the_bare_flux`
  asserts `J_out == J_bare` exactly, for the case where it is true: a seabed cell
  with no mat on it.

MODEL_SPEC section 12 states it in that form as well ("zero capacity gives zero
retention" and "`J_out == J_bare` where there is none"), so the code follows the
specification rather than the brief's compressed restatement.

---

## 7. Stubs left

One, labelled `LABELLED_STUB` in the code:

* `tile.scripted_exchange`, which builds a `SeabedExchange` from a scripted
  sediment-face concentration, standing in for
  `coastal_transport.build_seabed_exchange`. It computes `J_bare` from the same
  driving conditions the layer sees, so "with mat" and "without mat" share a
  source. Used by the example and the tests, neither of which has a map. The
  coupled runner must call the coastal branch's real function instead; the stub
  records `replace_with` in its own diagnostics.

Nothing else is stubbed. `design.py` is not a stub of mine: it is
`feat/optimisation`'s file, left untouched and not imported.

---

## 8. Requests for other branches

### To the coordinator (contract)

1. **`SeabedExchange` has nowhere to put the degradation coefficients.**
   `advance_reactive_layer` needs `burial_resistance_s_per_m` and
   `fouling_bypass_coupling`, which live in `config.DegradationConfig`, and the
   frozen signature carries no configuration object. They are currently read
   from `SeabedExchange.environment` (a `Mapping[str, float]`, so it fits) with
   documented defaults. Typed fields would be better, but nothing is blocked.
2. **`HotspotConfig.x_m` / `y_m`: centre or corner?** `build_tile_geometry`
   reads them as the centre. If `coastal_transport` reads them as a corner the
   mat will be laid off the hotspot. One sentence in the config docstring settles
   it.
3. **`LayerStep.diagnostics['clip_correction_kg']`** is populated as a
   per-element mapping in kilograms for the tile footprint, with
   `clip_correction_kg_per_m2` alongside it. MODEL_SPEC names the key but not its
   shape; if a scalar is wanted, say so.
4. `MaterialParameters.fouling_rate_capacity` defaults to `0.0` in both
   configured media, so fouling does not reduce capacity in the default run. The
   mechanism is implemented and tested with an explicitly built medium. If
   capacity loss is meant to be part of the demonstration, the config value needs
   raising; that is a modelling decision, not mine to make.

### To `feat/coastal-2d`

* `LayerStep.flux_out_kg_per_m2_per_s` is the residual flux **per unit area of
  intact layer**, not what the footprint emits. The section 5 coupling
  (`effective_cover = coverage * (1 - bypass)`) is yours. The single-tile version
  is `degradation.tile_effective_flux_kg_per_m2_per_s`, and
  `advance_reactive_layer` also records the per-tile result in
  `diagnostics['effective_flux_out_kg_per_m2_per_s']` so a cell-level
  implementation can be checked against it.
* A displaced or inactive tile returns `flux_in = flux_out = 0` and a frozen
  inventory, with `coverage_fraction = 0`. Its seabed cells emit `J_bare` through
  your coverage term, not through the layer.
* `bare_flux_from_exchange` prefers the hotspot's declared `J_bare` and reports
  which source it used. Please declare it.

### To `feat/estimation` and `feat/maintenance`

* `forecast_breakthrough` takes an **estimated** sorbed mass per unit area, not
  a `MatTileState`, so there is no path from the truth store into a
  recommendation. `forecast_tile` is the simulator-side convenience; do not use
  it in the operational loop.
* `breakthrough_s_interval` is `tuple | None` per element, and
  `never_reached_fraction` reports the share of the ensemble that never reaches
  the target. An interval alone would hide that.
* `degradation_state` returns all four modes side by side with
  `ambiguity_flags` already populated, which is the input the
  `PERFORMANCE_UNCERTAIN` rule needs.

### To `feat/optimisation`

* `design.py` is yours, still on the old types. `material.scale_material` now
  also takes `d_eff_scale`, and `sample_parameter_ensemble` takes
  `edge_leakage_nominal` / `edge_leakage_interval` / `geometry:
  MatTileGeometry` instead of the interception arguments.

---

## 9. Known limitations

* `steady_state_flux_kg_per_m2_per_s` is a **continuum** expression: it folds the
  top half cell into the layer rather than into the discrete `g_top`, so it
  agrees with the solver only to order `dz` (measured: 0.6 % at 40 nodes). It is
  a sanity oracle, not a substitute for the solver, and the test asserts the
  0.6 %, not a loose bound.
* The ensemble interval is a one-step spread from the nominal profile
  (assumption 8 above). A full ensemble trajectory would need one column per
  member marched from installation, which is affordable but has no consumer yet.
* Burial has only a few per cent of effect at the documented seepage velocity,
  because the layer's own resistance dominates the benthic film by roughly sixty
  to one. The mechanism is real and the direction is asserted; the magnitude is
  small and the test says so rather than choosing parameters that flatter it.
* The example runs nine tiles for six years in about 30 s. That is fine for a
  standalone script and would be too slow inside a design sweep over many
  layouts; tiles in an identical state could share one column solve.
