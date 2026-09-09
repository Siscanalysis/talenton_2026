# Shared contract v0.2 (seabed reactive mat)

Supersedes contract v0.1, which was written for a vertical reactive mesh
intercepting a plume. The changes are recorded in `REFACTOR_PLAN.md`.

The realisation of this document is
`src/reactive_seabed_mat/contracts.py` (`CONTRACT_VERSION = "0.2.0-frozen-mat"`)
and `src/reactive_seabed_mat/schemas/observation.schema.json`. Where this prose
and the code disagree, the code is the contract and the prose is the bug.

## 1. Observation records

One JSON object per line, one parameter per record.
`data/synthetic/observations.jsonl` contains **synthetic format and edge-case
fixtures only**, not coherent measurements and not a dataset for fitting
sorption.

| Field | Meaning |
|---|---|
| `record_id`, `station_id` | Stable unique record and station identifiers |
| `sensor_id`, `sample_id`, `media_id` | Nullable hardware, collected sample and media-batch identifiers |
| `tile_id` | Nullable mat tile. **Required for spatially local failure to be observable.** `media_id` is not a substitute: one media batch can be laid across many tiles |
| `observed_at_utc` | Sampling or measurement timestamp, ISO 8601 UTC ending in Z |
| `available_at_utc` | Earliest time the controller may use the result; never earlier than sampling |
| `sampling_start_utc`, `sampling_end_utc` | Required for an integrated passive-sampler exposure and for a benthic-chamber deployment; otherwise null |
| `parameter` | The measured quantity, including the mat-condition channels |
| `quantity_kind` | **Declared, never inferred**: `aqueous_concentration`, `solid_loading`, `accumulated_mass`, `areal_flux`, `length`, `velocity`, `fraction`, `categorical`, `context` |
| `unit` | Explicit supported unit from the ladder that `quantity_kind` implies |
| `matrix` | `seawater`, `bottom_water`, `porewater`, `mat_porewater`, `sediment`, `sorbent`, `mat_structure`, `instrument` |
| `fraction` | Operationally defined analytical fraction, including `dgt_labile` |
| `acquisition_kind` | How it was obtained, including `benthic_chamber`, `rov_inspection`, `bathymetric_survey`, `acoustic_position`, `sediment_core` |
| `value`, `uncertainty_std` | Number or null; uncertainty in the same unit, null when unknown |
| `qualifier` | `quantified`, `below_lod`, `below_loq`, `above_range`, `categorical`, `missing` |
| `lower_bound`, `upper_bound` | Censoring interval. A non-detect is a bound, not a zero measurement |
| `condition_class` | Controlled-vocabulary class for a categorical condition record |
| `quality_flag` | 1 passed, 2 not evaluated, 3 suspect, 4 failed, 9 missing [S23-S24] |
| `method_id`, `calibration_id` | Method definition and calibration reference |
| `data_origin` | **The acquisition pathway only**: `sensor`, `laboratory`, `field_survey`, `external_model`, `derived`, `manual` |
| `provenance` | **The truth status**: `measurement`, `external_model`, `literature`, `assumption`, `fitted`, `synthetic_demo` |
| `source_ref` | Provenance reference |
| `x_m`, `y_m`, `depth_m`, `vertical_datum`, `crs` | Metric coordinates, positive-down depth, **the datum that depth is measured from**, declared CRS |
| `z_in_mat_m` | Position within the reactive-layer thickness, for a depth-resolved profile |
| `chamber_area_m2` | Enclosed area of a benthic flux chamber; required to interpret its flux |

`data_origin` and `provenance` are separate on purpose. A fabricated laboratory
record is `data_origin: laboratory` with `provenance: synthetic_demo`. The
previous contract could not express both at once, and its fixture therefore
labelled invented numbers as laboratory results.

`depth_m` without a `vertical_datum` is rejected. In the previous contract a
sediment sample at `depth_m: 5.0` was unresolvably ambiguous between the water
column and below the sediment surface.

### Units

Six ladders, and no conversion between them:

| Ladder | SI | Examples |
|---|---|---|
| aqueous concentration | kg m^-3 | ng/L, ug/L, mg/L |
| solid loading | kg kg^-1 | ng/g, mg/kg |
| mass | kg | ng, ug, mg, g |
| **areal flux** | kg m^-2 s^-1 | ng/m2/s, ug/m2/d, mg/m2/yr |
| **length** | m | m, cm, mm |
| **velocity** | m s^-1 | m/s, m/d, cm/yr |

The last three are new in v0.2. Flux attenuation is the whole claim of a
reactive cap and no flux value could previously be converted or range-checked;
`m` sat among the unconverted context units, so a burial depth in centimetres
would have passed every check as if it were metres; and a seepage velocity in
cm/yr differs from m/s by nine orders of magnitude.

`ng/g` is a mass fraction and must never be pushed through the aqueous
conversion. For solid assays use ng/g or mg/kg with the mass-based ladder.

`salinity` uses unit `1` for practical salinity; record the scale in
`method_id` and do not mix practical salinity with absolute salinity in g/kg.
Turbidity examples use NTU; an FTU channel requires an explicit contract
extension, not a silent relabelling.

### Censoring

* `quantified`: a finite value, no censoring interval.
* `below_lod` / `below_loq`: `value: null` and a finite interval. A reported
  estimated value belongs in `source_ref` or the laboratory's own file, not in a
  field that the schema drops.
* `above_range`: `value: null` and a lower bound only.
* `categorical`: `value: null`, a `condition_class`, and
  `quantity_kind: categorical`.
* `missing`: `value: null`, no interval, quality flag 9. A missing result
  contains no chemical information at all.

### What each channel constrains

Only `Pb` and `Hg` records carry chemical information. Never infer a metal
concentration from turbidity, conductivity, salinity, temperature, pH, redox or
current.

| Channel | Constrains |
|---|---|
| porewater Pb/Hg at the sediment face | the driving condition `C_sed` |
| bottom-water Pb/Hg above the mat | `C_water`; the current estimator does not convert concentration to flux |
| benthic-chamber areal flux | `J_out` directly, the quantity the mat is judged on |
| DGT accumulated mass over a window | a time-integrated labile pool, never a point ng/L |
| retrieved-media assay | the loading of the **old** media, not the tile now in place |
| ROV, survey and acoustic records | mat condition, degradation modes 3 and 4, per tile |
| differential head | pore blockage, separating fouling from saturation |
| environmental sensors | water conditions and QC only |

A `total_recoverable` record is not assimilated against a `labile` model state
unless an explicit, documented, uncertain ratio operator is switched on; by
default such records are unassimilated evidence. `dgt_labile` and `labile` are
different operationally defined pools and are never merged.

## 2. Module boundary

Compatibility signatures are declared as Protocols in `contracts.py`:

```
advance_reactive_layer(tile_state, exchange, material_parameters, dt_s)
    -> LayerStep(new_state, flux_in, flux_out, retained_delta, released, ...)

build_seabed_exchange(field_state, tiles, hotspot, forcing, dt_s)
    -> Sequence[SeabedExchange]

residual_source_flux(grid, hotspot, tiles, layer_steps, time_utc)
    -> SeabedSourceField          # the distributed source the water receives

transport_step(field_state, forcing, sources, dt_s)
    -> TransportStep(new_field, boundary_in_kg, boundary_out_kg,
                     released_from_seabed_kg, diagnostics)

observations_available(records, decision_time_utc)
    -> records                    # preserves original IDs, flags and fractions

update_estimate(previous_estimate, available_observations, model_history)
    -> EstimateSnapshot

recommend(snapshot, policy, previous_actions)
    -> Recommendation
```

The last two are reserved compatibility protocols, not the implementations used
by the current runner. Its implemented evidence-loop interfaces are:

```
ObservationGenerator.generate_window(scene, start_s, end_s, **include_channels)
    -> list[ObservationRecord]

estimate_tiles(records, known, config, now, *, assumptions=None)
    -> dict[str, EstimateSnapshot]

recommend(estimates, known, config, now, elapsed_s, state)
    -> list[Recommendation]
```

Window generation uses the experiment-wide origin and preserves laboratory
availability separately from sampling completion. QC runs before estimation;
the estimator also checks availability and the observation classifier. Exact
quantity, matrix and fraction matching excludes MeHg from inorganic-Hg estimates.
The current estimator uses interval arithmetic, not an ensemble likelihood.

The coupling direction is the opposite of v0.1. The reactive layer is the
**source-term generator** for the coastal model. Nothing is subtracted from a
water-column cell, and there is no `apply_transfers`.

`SeabedExchange` carries the sediment-side porewater, the bottom-water
concentration, the seepage velocity, the film coefficient and the uncapped
reference flux. `MatTileState` carries the layer profiles plus four independent
degradation fields: `fouling_index`, `integrity_index`, `burial_depth_m` and
`displaced`. All model transfers are in kg or kg m^-2 s^-1, never a displayed
ng/L.

## 3. Snapshot and action shape

A snapshot has fields for loading, remaining capacity, residual/source flux,
attenuation, breakthrough, physical condition, channel age, evidence IDs and
ambiguity. Current fouling, effective-permeability and model-data-compatibility
fields remain `None`. Four degradation weights are normalised heuristic scores,
not Bayesian probabilities. `ensemble_size=0`; nominal `interval_level=0.90` does
not establish statistical coverage. There is no hidden event label.

Above-range endpoints remain unbounded internally. JSON exports encode
nonfinite endpoints as null and attach `_nonfinite_values` metadata with JSON
Pointer paths and their unbounded direction (or `undefined` for NaN). For a
top-level JSON list the metadata is in a `.numeric_metadata.json` sidecar.
Unobserved source/loading zero sentinels require their insufficient-data flag
and cannot be interpreted as measured zero or positive service evidence.

Remaining life and breakthrough are intervals or `None`. A falsely precise
remaining-life number is worse than an honest "not determined".

A recommendation contains a UTC decision time, an action from
`CONTINUE_MONITORING`, `TAKE_CHEMICAL_SAMPLE`, `CHECK_SENSOR`, `INSPECT_MAT`,
`PLAN_PARTIAL_REPLACEMENT`, `REPLACE_ACTIVE_PANEL`, `PERFORMANCE_UNCERTAIN`; a
human-readable reason; evidence record IDs; the target tile IDs; an uncertainty
note; `human_confirmation_required: true`; and
`execution_mode: simulation_only`. The current policy emits a subset of that
vocabulary and leaves recommendation-level data age `None`; per-channel ages are
in the snapshots. The runner immediately accepts replacement recommendations,
deduplicates target tiles within each decision batch and records `ServiceEvent`.
The frozen `ActionEvent` type is not the runner's current acceptance mechanism.

## 4. Configuration and provenance

One coordinator-owned schema, `config.RunConfig`. Each run records seed, time
stepping, domain, forcing, the hotspot and its schedule, mat layout and
reactive-medium parameters with ranges and provenance, degradation assumptions,
observation schedule, noise and detection assumptions, laboratory latency,
service policy, assumed costs and the plume-window settings.

Mark illustrative fields explicitly. Do not fabricate a reference for an assumed
number. A plot combining a real map, model currents and synthetic metal data
must show all three origins.

## 5. Result contract

Emit `manifest.json`, a per-element mass ledger, a mat-state timeline,
observation records, an estimate timeline, an action timeline, the design
comparison and a self-contained presentation report. The manifest records the
implemented engines and versions, the dependency lock hash, data hashes,
assumptions and **all unsuccessful validation checks**, including the numerical
tolerances actually achieved. The CLI exports replayable observations, estimates,
recommendations and accepted service events and hashes them in the manifest.
Offline reports are standalone artifacts. The Streamlit app runs and caches the
simulation directly when its controls change; it is not an output-file viewer.

Keep `truth/` output separate from `observations/` and `estimates/`. The test
harness may compare them; the operational recommendation path may not load
`truth/`.

Because the mat and the plume run on different clocks, their ledgers are
reported separately and each is labelled with its own window. Nothing may imply
the coastal model was integrated for the whole mat timeline.
