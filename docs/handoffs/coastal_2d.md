# Handoff: `feat/coastal-2d`

Branch `feat/coastal-2d`, worktree
`software/worktrees/coastal`, based on `main` at `dad4707`
(`CONTRACT_VERSION = 0.2.0-frozen-mat`).

Scope delivered: `docs/MODEL_SPEC.md` section 5 (the seabed source coupling) and
section 6 (the 2-D coastal model), plus the offline geodata adapters.

Owned paths, and nothing else was touched:

```
src/reactive_seabed_mat/coastal_transport/__init__.py
src/reactive_seabed_mat/coastal_transport/domain.py          adapted
src/reactive_seabed_mat/coastal_transport/fipy_engine.py     new
src/reactive_seabed_mat/coastal_transport/seabed_source.py   new
src/reactive_seabed_mat/coastal_transport/geodata/           new
tests/coastal_transport/                                     new
examples/coastal_transport/plume_demo.py                     new
docs/handoffs/coastal_2d.md                                  this file
```

---

## 1. Public surface

### `coastal_transport.domain`

| Function | What it returns |
|---|---|
| `build_grid(domain)` | `GridSpec` from `DomainConfig`, with degenerate grids refused |
| `build_land_mask(domain, grid=None)` | `(ny, nx)` boolean, cell-centre containment |
| `initial_field_state(config, ...)` | `FieldState`, zero by default, land forced to zero |
| `tidal_factor(cfg, elapsed_s)` | signed `sin(2 pi t / T + phase)` |
| `mean_velocity_at(cfg, elapsed_s)` | `(u_east, v_north)` for `kind` `steady` or `tidal` |
| `forcing_at(cfg, grid, land, elapsed_s, start_utc)` | one `Forcing`, zero on land |
| `forcing_timeline(...)` | one `Forcing` per step, stamped at step end |
| `forcing_signature(forcings)` | stable hash, for "identical forcing" claims |
| `assert_tide_resolving(cfg)` | raises `TidalForcingRefused` for a daily or de-tided field |
| `hotspot_entry_at(cfg, elapsed_s)` | the active `HotspotScheduleEntry`, or `None` |
| `hotspot_cell_mask(grid, cfg)` | `(ny, nx)` boolean contaminated-cell mask |
| `bare_flux(v, k_film, porewater, ...)` | `J_bare = (v + k_film)(C_sed - C_water)` per element |
| **`build_hotspot(config, *, elapsed_s=0.0, ...)`** | `SeabedHotspot`: cell indices plus `J_bare` per element at that time |
| `hotspot_area_m2(grid, hotspot)` | gridded hotspot area |
| `build_domain(config)` | `DomainBundle(grid, land_mask, field_state, hotspot)` |

### `coastal_transport.seabed_source`

| Function | What it returns |
|---|---|
| **`residual_source_flux(grid, hotspot, tiles, layer_steps, time_utc)`** | `SeabedSourceField`, the frozen `ResidualSourceFlux` signature exactly |
| `residual_source_flux_detailed(..., fouling_bypass_coupling=, overlap_m=, elements=)` | the same, with the coupling parameters exposed |
| **`build_seabed_exchange(field_state, tiles, hotspot, forcing, dt_s)`** | `Sequence[SeabedExchange]`, the frozen `BuildSeabedExchange` signature exactly |
| `tile_bounds(geometry)` | `(x0, y0, x1, y1)`, the one place the corner convention lives |
| `plan_tile_layout(mat, hotspot)` / `plan_tile_layout_for(config)` | `TilePlan(tile_id, geometry)` per tile |
| `check_tile_overlaps(plans, overlap_m)` | raises `OverlappingTilesRefused` |
| `cell_area_weights(grid, geometry)` | fraction of each cell's area under a tile |
| `bypass_fraction(tile, ...)` | `edge_leakage + coupling * fouling_index`, clipped |
| `component_total(source, element, grid, component)` | one component's rate in kg s^-1 |
| `CONTRIBUTION_COMPONENTS` | `covered, uncovered, damaged, displaced, edge_leakage` |
| `DIAGNOSTIC_COMPONENTS` | `bare_reference, effective_cover, covered_fraction` |

### `coastal_transport.fipy_engine`

| Function | What it returns |
|---|---|
| **`transport_step(field_state, forcing, sources, dt_s)`** | `TransportStep`, the frozen `TransportStepFn` signature exactly |
| `mesh_bundle(grid)` | cached FiPy `Grid2D` plus the face geometry the accounting uses |
| `step_ledger(element, before, step)` | one-step `MassLedger` |
| `accumulate_ledger(element, initial, steps, ...)` | window `MassLedger` |

`TransportStep.diagnostics` carries, per element where relevant:
`closure_error_kg`, `boundary_face_export_kg`, `clip_correction_kg`,
`clipped_cells`, `min_concentration_before_clip_kg_per_m3`, `source_on_land_kg`;
and globally `engine`, `solver`, `dt_s`, `water_cells`, `land_cells`,
`open_boundary_faces`, `max_velocity_divergence_per_s`, `advective_courant`,
`diffusion_number`, `decay_term`, `notes`.

### `coastal_transport.geodata`

`GeodataMode` (`synthetic`, `real_map_illustrative`, `imported_forcing`),
`BathymetryUsage` (one member: `visual_context_only`), `ProductMetadata`,
`CachedProduct`, `SyntheticAdapter`, `RealMapIllustrativeAdapter`,
`ImportedForcingAdapter`, `adapter_for`, `resolve_mode`,
`save_cached_product`, `load_cached_product`, `forcing_from_product`,
`bathymetry_statement`; errors `NetworkAccessRefused`, `CachedProductMissing`,
`GeodataModeRefused`, and `TidalForcingRefused` re-used from `domain`.

---

## 2. Exact run commands

From the worktree root
`C:\Users\Artelnics\Desktop\TalentON_2026\software\worktrees\coastal`:

```
& "C:\Users\Artelnics\Desktop\TalentON_2026\software\reactive-seabed-mat-demo\.venv\Scripts\python.exe" -m pytest tests/coastal_transport -q
& "C:\Users\Artelnics\Desktop\TalentON_2026\software\reactive-seabed-mat-demo\.venv\Scripts\python.exe" -m pytest tests/contracts -q
& "C:\Users\Artelnics\Desktop\TalentON_2026\software\reactive-seabed-mat-demo\.venv\Scripts\python.exe" examples/coastal_transport/plume_demo.py
& "C:\Users\Artelnics\Desktop\TalentON_2026\software\reactive-seabed-mat-demo\.venv\Scripts\python.exe" examples/coastal_transport/plume_demo.py --hours 3 --dt-s 900 --out results/quick
```

The example needs no map, no network and no hardware. Default output goes to
`results/coastal_transport_plume_demo/` (`plume_demo.png` and
`plume_timeline.json`); `results/*` is already git-ignored.

---

## 3. Tests actually executed, with real outcomes

Run on 8 September 2026, Windows 11, CPython 3.12.13, FiPy 4.0.3,
NumPy 2.5.3, SciPy 1.18.1.

```
tests/coastal_transport                   106 passed, 1 xfailed
tests/contracts                            88 passed in 11.71s
tests/coastal_transport + tests/contracts 194 passed, 1 xfailed in 76.19s
examples/.../plume_demo.py                exit code 0 in 28.2 s (12 h window)
```

The one `xfail` is a defect in coordinator-owned code, not in this branch: see
section 6.

Nothing was deleted or weakened to make the suite green. Two benchmark tests
were **rewritten** after they first failed, because the first version measured
the open boundary rather than the scheme: the plume was allowed to reach the
domain edge, where the analytic result does not apply. They now run in a closed
basin with the plume many standard deviations from every wall, and they pass at
far tighter tolerances than the ones that failed.

### What each acceptance test does, and the numbers it achieved

| Requirement | Test | Measured |
|---|---|---|
| zero source and zero mass stays exactly zero | `test_zero_source_and_zero_field_stays_exactly_zero` | bit-for-bit zero |
| closed domain conserves mass | `test_closed_domain_conserves_mass_to_1e_12_relative` | relative drift over 30 steps below 1e-12; asserted, actual is at roundoff |
| source normalisation `J * A * N * dt` | `test_uniform_source_injects_J_times_A_times_N_times_dt` | equal to 1e-12 relative |
| advection benchmark, centroid travels `u t` | `test_advection_benchmark_centroid_travels_u_times_t` | 3.1e-11 relative (asserted 1e-6) |
| diffusion benchmark, variance `2 D t` | `test_diffusion_benchmark_variance_grows_as_two_D_t` | 4.7e-8 relative (asserted 1e-5) |
| boundary export accounting closes | `test_boundary_export_accounting_closes` | worst `closure_error_kg` below 1e-12 of the initial mass; typical 1e-13 relative |
| current reversal | `test_current_reversal_moves_the_centroid_back` | forward leg 1.4e-6 relative; the centroid returns to within 3e-4 m of its start |
| signed transport resolves | `test_reversal_resolves_the_sign_of_the_boundary_export` | eastward export more than 5x the westward export |
| no transport through land | `test_no_transport_through_land` | land mass exactly 0; nothing at all beyond a wall after 60 steps |
| never negative, clipping reported | `test_concentrations_never_negative_and_clipping_is_reported` | minimum stays >= 0; `clip_correction_kg` present every step |
| time-step refinement | `test_time_step_refinement_converges` | dt 200 to 100 to 50 s: mass 0.66 % then 0.44 %, centroid 2.2 % then 1.2 %, export 1.5 % then 1.0 %; each change smaller than the last |
| grid refinement | `test_grid_refinement_converges` | dx 10 to 5 to 2.5 m: mass 0.23 % then 0.075 %, centroid 0.38 % then 0.14 %, variance 1.2 % then 0.79 % |
| identical forcing, mat against no mat | `test_mat_and_no_mat_runs_use_identical_forcing_arrays` | equal signature and array-by-array equality over every step |

### The coupling tests

| Requirement | Test | Result |
|---|---|---|
| an intact fully covering mat gives a strictly smaller total source | `test_a_fully_covering_intact_mat_emits_strictly_less_than_no_mat` | equals `(1 - a) * bare` to 1e-12 |
| a displaced tile makes exactly its own cells emit `J_bare`, neighbours unchanged | `test_a_displaced_tile_makes_exactly_its_own_cells_emit_the_bare_flux` | changed cells are exactly the displaced tile's footprint; neighbouring values compared with `np.array_equal`, so bit-for-bit unchanged |
| integrity 0.6 emits `0.6 J_out + 0.4 J_bare` | `test_integrity_zero_point_six_emits_zero_point_six_Jout_plus_zero_point_four_Jbare` | to 1e-12, with the 0.4 share landing in the `damaged` component and nothing in `displaced` |
| coverage 0.45 leaves 55 % bare | `test_coverage_fraction_0_45_leaves_55_percent_of_the_hotspot_bare` and `test_the_undersized_design_leaves_the_uncovered_share_bare` | exactly 0.55 of the hotspot area, to 1e-9, because coverage uses fractional cell areas rather than cell counts |
| overlapping tiles refused | `test_overlapping_tiles_beyond_the_allowance_are_refused` | `OverlappingTilesRefused`; a thin seam within `overlap_m` is allowed |
| overlap without the check is rescaled and recorded | `test_overlapping_tiles_without_the_check_are_rescaled_and_recorded` | components still sum to the total, the source never exceeds `J_bare`, and `NUMERICAL CORRECTION` appears in the notes |
| fouling is never free | `test_edge_leakage_and_fouling_bypass_move_their_own_component` | the bypassed share rises to `edge + 0.35 f` and the total source rises with it |
| the plume feeds back | `test_a_rising_plume_reduces_the_driving_gradient`, `test_the_source_responds_to_the_rising_plume` | bottom water read from the field lowers `J_bare`, and the released rate falls over a window |
| nothing subtracted from the water | `test_nothing_is_ever_subtracted_from_a_water_cell` | water mass is monotone non-decreasing while the source is positive; `boundary_in_kg` is zero |
| whole-window per-element conservation | `test_the_whole_window_conserves_mass_per_element` | relative imbalance below 1e-9 for Pb and Hg |

### Geodata

23 tests. The ones that matter: no adapter can fetch anything
(`NetworkAccessRefused`); a missing cached file is reported and nothing is
downloaded; a `daily_mean`, `de_tided` or `monthly_mean` product is refused for
`kind='tidal'` and accepted for `kind='steady'` **with its limits printed**; a
product that does not declare tide resolution is refused; unknown metadata
fields and unknown file formats are refused rather than guessed; a gap
(non-finite value) in a product is refused rather than filled; the resolution
statement names the native resolution, says interpolation creates no
information, and says surface currents are not near-bed currents; bathymetry is
declared visual context only and `BathymetryUsage` has exactly one member. A
blunt static test also greps the whole package for `requests`, `urllib`,
`http.client`, `socket`, `ftplib`, `urlopen(` and `requests.get(` and asserts
there are none.

### Example output, default 12 h window

```
case           element    released kg  share of bare
fresh_mat      Pb       3.648702e-03         0.0249
saturated_mat  Pb       1.154687e-02         0.0788
no_mat         Pb       1.465344e-01         1.0000

largest boundary closure error over every step:  4.077e-17 kg
total clipped (reported, not hidden) mass:       0.000e+00 kg

Where the residual source comes from (kg/s, first step, Pb)
case                  covered     uncovered       damaged     displaced  edge_leakage
fresh_mat          1.6621e-08    1.0650e-21    0.0000e+00    0.0000e+00    6.7840e-08
saturated_mat      1.9945e-07    1.0650e-21    0.0000e+00    0.0000e+00    6.7840e-08
no_mat             0.0000e+00    3.3920e-06    0.0000e+00    0.0000e+00    0.0000e+00
```

The `uncovered` figure of 1.07e-21 for a fully covered hotspot is floating-point
residue from summing nine tile weights, not a real leak; it is reported as
computed rather than tidied away.

An honest finding worth carrying into the presentation: with the assumed 2 %
edge leakage, a mat whose layer attenuates 99.5 % still emits about four times
more through the **edge** than through the layer. The uncertain design
parameter, not the chemistry, sets the floor on the residual source. The example
prints this whenever it holds.

---

## 4. Findings that other branches need

**FiPy leaves an unconstrained exterior face closed to both convection and
diffusion.** Its convection term is assembled from interior faces only, so an
"open" boundary is not free: without an explicit term, a domain edge behaves as
a wall. This was measured, not assumed (a pulse advected at a boundary produced
zero export from FiPy while a hand-computed face flux said otherwise). The
engine therefore adds the open boundary itself, as an implicit sink on the
boundary cells, with the same coefficients the matrix uses. That is also what
makes the exterior-face cross-check exact rather than approximate.

**A land face has `u = 0` and `D = 0`, so FiPy's face Peclet number there is
`0/0`.** The resulting weight multiplies a zero coefficient and cannot reach the
matrix, but NumPy emits an `invalid value` warning. The solve is wrapped in
`np.errstate(invalid="ignore", divide="ignore")` and the solved field is then
checked for finiteness, so the warning is suppressed without trusting that it is
harmless.

**One equation object serves every element in a call.** The operator is
identical across elements; only the explicit source and the solution variable
change. This halves the per-step cost and is asserted bit-for-bit against
per-element solves in `test_two_elements_match_two_single_element_runs_bit_for_bit`.

**Cost.** About 0.095 s per element per step on a 60x40 grid (matrix assembly
dominates, not the linear solve; LU, GMRES and the default solver were within
5 % of each other). A 12 h window at `dt = 900 s` for three cases and two
elements is 28 s. `PlumeWindowConfig` defaults (3 days at `dt = 300 s`) would be
about 8 minutes for the same three cases, which is affordable but not
interactive; the app should use a shorter window or fewer cases.

---

## 5. Assumptions, all labelled in the code

1. **`MatTileGeometry.x_m` and `y_m` are the lower-left corner** of the tile
   footprint. The contract does not say. This convention is applied in exactly
   one function, `seabed_source.tile_bounds`, and it is the convention that
   makes the coordinator's own default station list consistent
   (`ST_MAT_B` at (300, 220) is the centre of `tile_1_1` only under this
   reading, which `test_hotspot_rectangle_uses_the_lower_left_corner_convention`
   pins down). **`feat/reactive-layer` must use the same convention.** If it
   uses centres instead, every tile is offset by half a tile and the coupling is
   silently wrong. This is the single most important cross-branch item here.
2. **`HotspotConfig.x_m`, `y_m` are likewise the lower-left corner.**
3. **The hotspot is discretised by cell-centre containment**, so the gridded
   area can differ from the configured rectangle area. The gridded area is what
   every flux is applied to and it is stated in `SeabedHotspot.description`.
   With the default configuration the two agree exactly (64 cells, 6400 m2).
4. **A reversed gradient is clamped, not modelled as deposition.** If bottom
   water exceeds the sediment porewater, `J_bare` would be negative. The
   sediment reservoir here is prescribed and never depleted, so a negative
   source would be a sink with no inventory behind it. The clamp is applied,
   the signed value is kept in
   `SeabedExchange.diagnostics['bare_flux_signed_kg_per_m2_per_s']`, and the
   clamp is named in the diagnostics notes.
5. **The film coefficient does not depend on the current.** `k_film` comes from
   the hotspot and is constant, matching `MODEL_SPEC` section 3. A stronger
   current would thin the diffusive sublayer and raise it in reality, so a
   current change does not currently change the mat's attenuation. Recorded as
   `diagnostics['film_transfer_is_current_dependent'] = False`.
6. **The water outside the domain is clean and well mixed.** Nothing advects in,
   and the diffusive exchange at an open face is with zero concentration.
   `boundary_in_kg` is therefore zero in every default run; the field exists so
   the ledger stays complete if that assumption is relaxed.
7. **A closed domain is expressed by a ring of land cells.** The frozen
   signature has no boundary flag, and a land ring exercises the same no-flux
   code path, so no extra argument was invented.
8. **The prescribed uniform current is not made divergence free after land
   masking.** Where land is not parallel to the flow, concentration piles up
   against it. Mass is still conserved exactly, because the scheme is in flux
   form; it is realism that suffers, not the ledger. The discrete divergence is
   reported as `diagnostics['max_velocity_divergence_per_s']` and named in the
   notes when it is non-zero. The default land strip is parallel to the flow.
9. **`DEFAULT_FOULING_BYPASS_COUPLING = 0.35` is duplicated** from
   `DegradationConfig` because the frozen `ResidualSourceFlux` signature carries
   no configuration. Callers that hold a `DegradationConfig` should use
   `residual_source_flux_detailed` and pass the configured value; the example
   does.
10. **Tiles abut; `overlap_m` is an allowance, not a construction parameter.**
    The planned layout has zero overlap, so nothing is double counted, and
    `check_tile_overlaps` refuses anything thicker than the allowance in both
    directions.
11. **`SeabedExchange.cell_weights` are fractions of the tile footprint**,
    normalised over the usable cells so a weighted mean is a tile average.
    `cell_area_weights` returns fractions of the **cell** area. The two are
    deliberately different quantities and both are documented at their
    definitions.
12. **The mat coverage layout is a centred rectangle** of area
    `coverage_fraction * hotspot area`. Partial cell coverage is exact, so
    `coverage_fraction = 0.45` leaves exactly 55 % of the hotspot area bare.
13. **Placeholder product names in the geodata tests** (`PLACEHOLDER_HOURLY_CURRENTS`)
    are not a claim that any vendor product was obtained, tested or is
    redistributable. No real product was downloaded and no register map, price
    or licence was invented.

---

## 6. Stubs left, marked `LABELLED_STUB` in the code

* `tests/coastal_transport/conftest.py::stub_layer_step` and
  `examples/coastal_transport/plume_demo.py::stub_layer_step`: a
  **constant-attenuation tile**, `J_out = (1 - a) * J_bare`. No chemistry, no
  capacity, no breakthrough. It exists only so the coupling and the 2-D engine
  can be exercised before `feat/reactive-layer` lands. The two attenuation
  constants (0.995 fresh, 0.940 saturated) are stand-ins chosen to bracket the
  behaviour recorded in `REFACTOR_PLAN.md`; they are assumptions, not results,
  and they are labelled as such in the example's printed output, in
  `plume_timeline.json` and on the figure.
* Nothing under `src/` imports either stub.

When `feat/reactive-layer` lands, the replacement is a one-line change in each
place: call the real `advance_reactive_layer(tile_state, exchange,
material_parameters, dt_s)` and pass its `LayerStep` straight into
`residual_source_flux`. The `SeabedExchange` objects this branch builds are
already exactly the input that function takes.

---

## 7. Requests for the coordinator

1. **Defect: `reactive_seabed_mat.results.ledger_to_dict` is stale.** It reads
   `MassLedger.emitted_kg`, `in_active_mesh_kg` and `in_retrieved_media_kg`,
   which the 0.2.0 contract renamed to `released_from_sediment_kg`,
   `retained_in_mat_kg` and `retained_in_retrieved_media_kg`. Any caller gets
   `AttributeError`. Recorded as an `xfail` in
   `tests/coastal_transport/test_example_and_integration.py::test_results_ledger_to_dict_matches_the_frozen_mass_ledger`,
   with the corrected body available to copy from
   `examples/coastal_transport/plume_demo.py::ledger_to_dict`. The example uses
   a local copy until this is fixed; please delete both once it is.
2. **Dependency: `matplotlib` is not in `pyproject.toml`** but is installed in
   the tested venv and is what the example uses for its static PNG. Either add
   it (with `requirements.lock.txt`) or say so and the example will fall back to
   a text note. It already degrades gracefully rather than crashing.
3. **Contract: state the `MatTileGeometry` anchor.** Please add one sentence to
   the docstring saying whether `x_m, y_m` is the lower-left corner or the
   centre. This branch assumes the corner (assumption 1) and
   `feat/reactive-layer` must agree.
4. **Contract: `SeabedSourceField.components` key order.** This branch uses
   `components[element][component]`, matching the key set of
   `flux_kg_per_m2_per_s`. Worth pinning in the docstring before the app reads
   it.
5. **Contract, optional: carry `fouling_bypass_coupling` on `MatTileState` or
   `MatTileGeometry`.** It is currently duplicated as a module constant
   (assumption 9) because the frozen coupling signature takes no configuration.
6. **`docs/DATA_CONTRACT.md` section 2 is stale**: it still lists
   `advance_panel`, `build_contacts` and `apply_transfers` with the old return
   types. `contracts.py` is the authority and was followed; the document was
   not.
7. **Ordering note for integration.** `residual_source_flux` reads `J_bare` from
   `LayerStep.exchange` when the layer step provides one, and falls back to
   `SeabedHotspot.bare_flux_kg_per_m2_per_s` otherwise. That is what lets a
   rising plume reduce the source. If `feat/reactive-layer` returns a
   `LayerStep` with `exchange=None`, the coupling silently uses the clean-water
   reference instead. Please have the layer branch pass the exchange through.

---

## 8. What this branch deliberately did not do

* No decay, no first-order disappearance, and no removal of mass from any
  water-column cell. There is no frontal area, no swept volume and no
  interception efficiency anywhere in the package; a source flux is refused if
  it is negative.
* No ordnance anywhere. The source is an abstract authorised hotspot and
  `SeabedHotspot.description` says so on every export.
* No network call, no account, no tile server and no basemap in any default
  path. `data/external/` is still empty.
* No 3-D hydrodynamics, no OpenDrift and no TELEMAC. The current field is
  prescribed and labelled `SYNTHETIC_DEMO`, and its honest resolution statement
  is printed by the example and written into the JSON timeline and onto the
  figure.
* No claim that the coastal model was integrated for years. Every export from
  this branch is labelled a **plume window** at one fixed mat state, with the
  mat timeline named as a separate clock.
