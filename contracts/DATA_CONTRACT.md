# Shared contract v0.1

The observation format and units below are supplied now. Common model/result dataclasses must be frozen by the coordinator before parallel implementation. Keep functions plain and local: no web-service interface is necessary.

## 1. Observation records

One JSON object per line, one parameter per record. `observation.schema.json` supplies the machine-readable shape. `data/examples/observations.jsonl` contains **synthetic format/edge-case fixtures only**, not coherent sensor measurements or a dataset for fitting adsorption.

| Field | Meaning |
|---|---|
| `record_id`, `station_id` | Stable unique record and station identifiers |
| `sensor_id`, `sample_id`, `media_id` | Nullable hardware, collected sample and relevant material-installation identifiers |
| `observed_at_utc` | Sampling/measurement timestamp, ISO 8601 UTC ending in Z |
| `available_at_utc` | Earliest time the controller can access the result; never earlier than sampling |
| `sampling_start_utc`, `sampling_end_utc` | Required for integrated passive-sampler exposure; otherwise null |
| `parameter` | `Pb`, `Hg`, `current_east`, `current_north`, `temperature`, `conductivity`, `salinity`, `pH`, `turbidity`, `mesh_tilt`, `battery_voltage` |
| `unit` | Explicit supported display unit; no automatic inference |
| `matrix` | `seawater`, `porewater`, `sediment`, `sorbent`, `instrument` |
| `fraction` | `not_applicable`, `labile`, `dissolved_filtered`, `total_recoverable`, `dissolved_inorganic`, `methylmercury`, `sorbed_total` |
| `acquisition_kind` | `in_situ_sensor`, `grab_sample`, `passive_sampler`, `media_assay`, `manual` |
| `value`, `uncertainty_std` | Number or null; uncertainty in the same unit, null when unknown |
| `qualifier` | `quantified`, `below_lod`, `below_loq`, `missing` |
| `lower_bound`, `upper_bound` | Censoring interval; non-detect is not a zero measurement |
| `quality_flag` | 1 passed, 2 not evaluated, 3 suspect, 4 failed, 9 missing [S23–S24] |
| `method_id`, `calibration_id` | Method definition and calibration reference; calibration may be null |
| `data_origin`, `source_ref` | `synthetic`, `sensor`, `laboratory`, `external_model`, `derived`; provenance reference |
| `x_m`, `y_m`, `depth_m`, `crs` | Metric horizontal coordinates and positive-down depth; declared CRS |

`salinity` uses unit `1` for practical salinity in the fixture. Record the scale/method in `method_id`; do not silently mix practical salinity with absolute salinity in g/kg. pH is dimensionless but its measurement scale must also be specified in a real method record. Conductivity examples use mS/cm. Turbidity examples use NTU; a future FTU channel requires explicit contract extension, not a silent relabelling.

The `Pb`/`Hg` name identifies the element; `matrix`, `fraction` and method determine what the number means. The schema allows sediment/media records for evidence, but the first aqueous adapter must reject them as water concentration inputs. For solid assays use ng/g or mg/kg with a separate mass-based conversion; never use the aqueous conversion.

For a raw passive sampler, an accumulated mass and sampling rate may be the correct observable. The first release may store its metadata and defer quantitative assimilation until a sampler-specific observation operator and schema extension exist. Do not force raw passive-sampler mass into ng/L.

### Censoring

- `quantified`: a finite value, no censoring interval.
- `below_lod`/`below_loq`: this minimal canonical format stores `value: null` and a finite interval. A reported estimated value can be retained in raw provenance; do not silently assimilate it as an exact value.
- `missing`: `value: null`, no interval, quality flag 9. A missing result contains no chemical information.

The supplied validation utility checks these essentials, but future vendor ingestion must also validate model-specific metadata, ranges, messages and methods.

## 2. Module boundary to freeze

Use dataclasses or similarly explicit typed objects, not unstructured dictionaries passed everywhere. The coordinator implements their exact definitions and fixture factories on main first.

```
advance_panel(panel_state, contact_batch, material_parameters, dt_s)
    -> PanelStep(new_state, uptake_kg_by_element, release_kg_by_element, diagnostics)

transport_step(field_state, forcing, sources, dt_s)
    -> TransportStep(new_field, boundary_in_kg, boundary_out_kg, diagnostics)

build_contacts(field_state, panels, forcing, dt_s)
    -> contact_batches

apply_transfers(field_state, panel_steps)
    -> new_field                       # exactly one subtraction/addition per transfer

observations_available(records, decision_time_utc)
    -> records                         # preserves original IDs, flags and fractions

update_estimate(previous_estimate, available_observations, model_history)
    -> EstimateSnapshot

recommend(snapshot, policy, previous_actions)
    -> Recommendation
```

`ContactBatch` includes panel ID, timestamp, total/accessible concentration interpretation, available mass per element, assumed/measured contact exchange, environment and allocating grid-cell IDs/weights. `PanelState` includes media ID, material allocation, retained kg, capacity kg and fouling. All model transfers are in kg, never displayed ng/L.

The independent micro branch can use a scripted contact sequence. The macro branch can use a zero-uptake stub. The observation branch can use a scripted model-history fixture. Such stubs must be labelled and replaced during integration.

## 3. Snapshot and action shape

A snapshot contains estimated retained mass and uncertainty, remaining-life interval or null, model-data compatibility, data age, evidence IDs and ambiguity flags. It does not contain actual hidden event labels. Confidence levels/quantiles must be documented.

A recommendation contains UTC decision time, action enum, human-readable reason, evidence record IDs, uncertainty/rationale, `human_confirmation_required: true`, and `execution_mode: simulation_only`. An accepted simulated action has a separate action-event record. Duplicate recommendations must not create repeated replacements.

## 4. Configuration and provenance

Each run records seed, simulation interval/time step, domain dimensions/CRS/depth, current/diffusion assumptions, source kg/s schedule, panel geometry/material allocations, parameter ranges and provenance, observation schedule/noise/detection assumptions, laboratory latency, service policy and assumed costs. Use one coordinator-owned config schema.

Mark illustrative fields explicitly. Do not fabricate a reference for an assumed number. A plot combining a real map, model currents and synthetic metal data must show all three origins.

## 5. Result contract

Emit `manifest.json`, per-element mass ledger, material-state timeline, observation records, estimate timeline, action timeline, design comparison and a self-contained presentation report. A result manifest records implemented engine/version, dependency lock hash, data hashes, assumptions and all unsuccessful validation checks. The UI can consume these files without re-running a costly optimiser.

Keep `truth/` output separate from `observations/` and `estimates/`. The test harness may compare them; the operational recommendation function may not load `truth/`.
