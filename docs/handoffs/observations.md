# Handoff: `feat/observations`

Branch `feat/observations`, worktree `software/worktrees/obs`.
Implements `docs/MODEL_SPEC.md` section 8: the synthetic observation generator,
the mat-condition channels, quality control and the observation operator.

Owned paths: `src/reactive_seabed_mat/observations/` except `records.py`,
`tests/observations/`, `examples/observations/`, this file.
No coordinator-owned file was edited.

---

## 1. What changed, and why

The inherited stack (`generator.py`, `qc.py`, `operator.py`, about 1 950 lines)
did not import at all: `Parameter.MESH_TILT` no longer exists. The audit was
right that it contained no vertical-mesh physics, only a vocabulary and a
geometry, so it was adapted rather than rewritten. What it got wrong about the
mat concept was structural:

| Inherited assumption | Now |
|---|---|
| only `seawater` is assimilable; porewater is rejected evidence | porewater, mat porewater, bottom water and seawater are all assimilable, and each names the model state it constrains |
| the primary evidence is an upstream/downstream water-column pair | the primary evidence is porewater at the sediment face, bottom water above the mat, and a benthic-chamber areal flux |
| there is no areal-flux channel at all | `quantity_kind = areal_flux` in ug/m2/d, with the enclosed area and the deployment window, is the only channel that measures what the mat is judged on |
| one `labile` fraction | `labile` and `dgt_labile` are different pools and are never merged, in either direction, with or without a ratio operator |
| mat condition does not exist | a whole module: damage class, coverage, burial, scour, displacement, tilt, differential head, all per tile |
| the operator infers a quantity from `(matrix, fraction, unit)` | it dispatches on the declared `quantity_kind` |
| `data_origin = synthetic` mixes pathway with truth status | pathway in `data_origin`, truth status in `provenance`; every generated record is `synthetic_demo` |

---

## 2. Modules and public functions

### `observations/generator.py` (adapted)

Synthetic measurement generation from a scripted model history.

* `ObservationGenerator(config, *, seed, start_utc, assumptions=None, fast_validation=True)`
  * `.porewater_records(scene, duration_s)` sediment-face chemistry in ug/L,
    the driving boundary condition, plus the methylmercury risk channel
  * `.bottom_water_records(scene, duration_s)` in-situ probe in ng/L above the
    mat, carrying dropout, drift, missingness and the stuck-value window
  * `.benthic_chamber_records(scene, duration_s)` areal flux in ug/m2/d with
    `chamber_area_m2` and a deployment window
  * `.dgt_records(scene, duration_s)` accumulated mass in ng over an exposure
    window, `fraction = dgt_labile`, above-range when the gel saturates
  * `.media_assay_record(batch, element, observed_at, ...)` and
    `.retrieved_media_records(scene, duration_s)` in ng/g
  * `.environmental_records(scene, duration_s)` context and housekeeping
  * `.generate(scene, duration_s, *, include_environmental, include_dgt, include_condition)`
* `SyntheticRecordFactory` shared primitives: `next_id`, `schedule`,
  `base_payload`, `censor`, `missing`, `build`
* `CachedRecordValidator` / `CACHED_VALIDATOR` (see section 6)
* Types: `MatStateSample`, `EnvironmentSample`, `MediaBatch`, `ScriptedScene`,
  `GeneratorAssumptions`, `MatHistorySpec`, `MediaReplacement`, `ContextChannel`
* Scene builders: `constant_mat_scene`, `ramp_mat_scene`,
  `synthetic_mat_history` (LABELLED_STUB), `scene_from_layer_history`
* Tables: `CONTEXT_CHANNELS`, `CONTEXT_UNITS`, `METHOD_IDS`, `DEFAULT_ENVIRONMENT`

### `observations/condition.py` (new)

Mat-condition channels. They constrain degradation modes 2, 3 and 4 and carry
no chemistry.

* `MatConditionGenerator(config, *, seed, start_utc, assumptions=None, fast_validation=True)`
  * `.damage_class_records` ROV or diver inspection, a class from a controlled
    vocabulary, `qualifier = categorical`
  * `.coverage_records` bathymetric survey, a fraction in [0, 1]
  * `.burial_records` bathymetric survey, cm on the length ladder
  * `.scour_records`, `.displacement_records`, `.tilt_records`
  * `.differential_head_records` the channel that separates fouling from
    saturation
  * `.generate(scene, duration_s)`
* `MAT_DAMAGE_CLASSES`, `DAMAGE_CLASS_SEVERITY`, `DAMAGE_CLASS_INTEGRITY_BAND`,
  `CONDITION_MODE`, `CONDITION_METHOD_IDS`, `ConditionAssumptions`
* `damage_class_from_integrity(integrity, displaced)`,
  `integrity_band_for_class(condition_class)`

A class is a class: `value` is `None`, the class is in `condition_class`, and
`DAMAGE_CLASS_INTEGRITY_BAND` says what integrity **interval** it implies so no
downstream code can average two inspections into a fictitious 2.5.

### `observations/qc.py` (adapted)

* `run_qc(records, *, thresholds=DEMO_THRESHOLDS, now_utc=None) -> QCReport`
* `gross_range_check`, `spike_check`, `stuck_value_check`, `vocabulary_check`
* `apply_qc_flags(records, report)`
* `band_keys(record)`, `asset_key(record)`, `channel_key(record)`
* `QCThresholds`, `DEMO_THRESHOLDS`, `QCOutcome`, `AssetHealth`
  (`SensorHealth` is an alias), `QCReport`, `STUCK_REASON_TEMPLATE`

### `observations/operator.py` (adapted)

* `classify_record(record, config=None, *, qc_report=None) -> ObservationUse`
* `build_assimilation_set(records, config=None, *, qc_report=None) -> AssimilationSet`
* `ModelQuantity`: `AQUEOUS_CONCENTRATION`, `SOLID_LOADING`, `ACCUMULATED_MASS`,
  `AREAL_FLUX`, `MAT_COVERAGE_FRACTION`, `BURIAL_DEPTH`, `SCOUR_DEPTH`,
  `MAT_DISPLACEMENT`, `MAT_TILT`, `MAT_DAMAGE_CLASS`, `MAT_PERMEABILITY`,
  `DIFFERENTIAL_HEAD`, `CONTEXT`, `NONE`
* `OperatorConfig`, `FractionRatioOperator`, `ObservationUse`, `AssimilationSet`
* `NEVER_MERGED_FRACTIONS`, `UNMERGEABLE_FRACTIONS`, `never_merged(a, b)`

`ObservationUse` gained `tile_id`, `si_unit`, `is_one_sided`,
`condition_evidence`, `degradation_mode`, `model_target`, `carries_chemistry`
and `condition_class`, so a consumer never has to re-derive what a record meant.

---

## 3. Exact run commands

From the worktree root
`C:\Users\Artelnics\Desktop\TalentON_2026\software\worktrees\obs`:

```
& "C:\Users\Artelnics\Desktop\TalentON_2026\software\reactive-seabed-mat-demo\.venv\Scripts\python.exe" -m pytest tests/observations -q
& "C:\Users\Artelnics\Desktop\TalentON_2026\software\reactive-seabed-mat-demo\.venv\Scripts\python.exe" -m pytest tests/contracts -q
& "C:\Users\Artelnics\Desktop\TalentON_2026\software\reactive-seabed-mat-demo\.venv\Scripts\python.exe" examples\observations\replay_demo.py
```

The example needs no map, no hardware and no network. It writes
`results/observations_demo/generated_observations.jsonl` and
`results/observations_demo/replay_summary.json`, both gitignored.

---

## 4. Tests actually executed, with their real outcome

There were **no tests at all** for these 1 950 lines before this branch.

```
tests/observations             149 passed in 74.24s
tests/contracts                 89 passed in  8.68s
tests/contracts + observations 238 passed in 90.49s
```

Per file:

| File | Tests | Outcome |
|---|---|---|
| `tests/observations/test_generator.py` | 49 | all pass |
| `tests/observations/test_condition.py` | 19 | all pass |
| `tests/observations/test_qc.py` | 26 | all pass |
| `tests/observations/test_qc_regressions.py` | 11 | all pass |
| `tests/observations/test_operator.py` | 44 | all pass |
| total | 149 | all pass |

Nothing is skipped, nothing is `xfail`, and no test was deleted or weakened to
get a green run. Two tests did fail during development and were fixed by
changing the code, not the assertion: the burial history was only attenuating
the layer term while edge leakage bypassed it (burial covers the whole
footprint, so it now applies to the bypass as well), and porewater was not
assimilable because the operator expected one fraction for every matrix.

**One honest correction to the brief.** `tests/contracts` reports **89**
passed, not 88. `test_state_separation.py` parametrises over every module in
`observations/`, so adding `condition.py` added one parametrised case. It
passes: the new module does not name the truth store.

### The required cases, and where each lives

| Required | Test |
|---|---|
| every generated record validates via `record_from_dict` | `test_every_generated_record_validates_through_the_public_entry_point`, `test_every_condition_record_validates_against_the_frozen_schema` |
| the six qualifiers stay distinct | `test_every_qualifier_stays_distinct_in_one_stream`, `test_the_six_qualifiers_carry_different_payload_shapes`, `test_a_ramp_crosses_the_thresholds_in_order` |
| a chamber record without area or window is rejected | `test_a_chamber_record_without_area_or_window_is_rejected_by_the_contract` (schema), `test_a_chamber_record_without_area_is_refused_by_the_operator_too`, `..._without_a_window_...` (operator) |
| a DGT record is never a point concentration | `test_a_dgt_record_is_never_converted_into_a_point_concentration`, `test_a_record_claiming_a_passive_sampler_gave_a_point_concentration_is_refused` |
| porewater is assimilable, sediment is not a water concentration | `test_porewater_is_assimilable_and_names_the_state_it_constrains`, `test_mat_porewater_is_assimilable_against_the_layer_state`, `test_sediment_is_not_accepted_as_a_water_concentration` |
| labile and dgt_labile are never merged | `test_labile_and_dgt_labile_are_never_merged`, `..._with_a_filtered_porewater_state_either`, `..._even_with_the_ratio_operator_on` |
| a media assay after a replacement names the old media | `test_a_media_assay_after_a_replacement_describes_the_old_media`, `test_a_generated_replacement_assay_describes_the_retired_batch` |
| condition records carry a tile_id and are not chemistry | `test_every_condition_record_carries_a_tile_id`, `test_condition_records_carry_no_chemistry`, `test_condition_records_are_condition_evidence_and_carry_no_chemistry`, `test_a_condition_record_without_a_tile_cannot_support_a_local_decision` |
| removing context leaves the metal set unchanged | `test_removing_every_context_record_leaves_the_metal_set_unchanged`, `test_removing_context_also_leaves_the_qc_flags_of_metal_records_unchanged` |
| the three QC defects, each with a discriminating regression test | `tests/observations/test_qc_regressions.py`, all 11 |
| burial is available and is not improved performance | `test_a_burial_observation_is_condition_evidence_for_mode_three`, `test_burial_never_enters_the_chemistry_set`, `test_a_buried_tile_shows_a_lower_flux_with_the_condition_evidence_beside_it` |

---

## 5. The three audited QC defects

Each is fixed, and each regression test carries the **inherited algorithm**
beside the fixed one (`_inherited_sensor_health` in
`test_qc_regressions.py`) and asserts that the old one misses the case. A
regression test that only exercises the new code proves nothing.

**(a) the data-age check was skipped for the sensor that needed it.**
`_sensor_health` did `continue` on a missing record before updating
`last_seen`, so a sensor whose readings were *all* missing kept
`last_seen = None` and the age check never ran. Health now tracks
`last_observed_at_utc` (any contact) and `last_usable_at_utc` (information)
separately, runs the age check on the second, and marks an asset with no usable
reading at all as `stale` by definition.
Discriminating assertion: `old["SIM_PBPROBE_A"]["stale"] is False` after 30 days
of nothing but missing records.

**(b) stuck detection matched prose.** It tested
`"stuck value" in reason`, so rewording the message disabled it silently.
`QCOutcome` now carries `failed_checks: frozenset[str]` and the health summary
reads that. The regression test monkeypatches `STUCK_REASON_TEMPLATE` to text
without the old substring and asserts the detection survives; the paired test
shows the inherited version reports `stuck = False` while the same records are
still individually failed, which is what made the defect subtle.

**(c) records with `sensor_id = None` never entered the summary.** That is
every laboratory, chamber, DGT, media-assay and survey record. Health is now
computed per **asset** through `asset_key`: the sensor when there is one, else
the tile, else the station. `QCReport.sensor_health` still exists and still
contains only instruments, so nothing downstream breaks.
Discriminating assertion: six identical porewater results produce
`old == {}` while the fixed summary reports `stuck` and `failed` on
`tile:tile_1_1`.

### Other QC changes, all deliberate

* **Thresholds are keyed by a band key** `parameter|quantity_kind|matrix`, with
  fallbacks. One band per parameter cannot work: porewater Pb beneath the mat
  and bottom-water Pb above it differ by five orders of magnitude, and a single
  band either passes everything or fails everything.
* **The spike test gained a relative allowance**, `max(absolute, relative *
  |neighbour mean|)`. With a 20 % relative-noise probe an absolute threshold
  flagged 1 816 of 5 845 readings (31 %) as suspect. It now flags 17 (0.3 %),
  and a real excursion at low concentration is still caught.
* **Step channels are deliberately not spike-tested**: `mat_displacement`,
  `mat_coverage_fraction`, `burial_depth`, `scour_depth`. A tile can genuinely
  move, tear or be buried between two surveys, and flagging that step as
  suspect would push the evidence of failure out of the likelihood, which is the
  opposite of what QC is for.
* **A vocabulary check** was added, so an invented damage class fails rather
  than propagating.
* **The aggregate flag is the worst result among the checks that could run.**
  Previously a single inapplicable test demoted every record to `NOT_EVALUATED`,
  so flag 1 was unreachable. `NOT_EVALUATED` is now reserved for a record no
  check applied to.
* **Per-band data-age limits.** A benthic chamber deployed twice a year is not a
  broken sensor. The asset limit is the largest among the channels it reports.

---

## 6. Contract requests

**CR-1 (performance, blocking for a multi-year demonstration).**
`records.validate_record_dict` calls `jsonschema.validate(instance, schema)`,
which re-checks the schema against its own metaschema on **every** call.
Measured on this machine against `observation.schema.json`:

| path | per record |
|---|---|
| `jsonschema.validate(instance, schema)` | 38.7 ms |
| pre-built `Draft202012Validator(schema).validate(instance)` | 0.57 ms |

A four-year stream is about 11 000 records, so this is seven minutes against
six seconds, and it decides whether the demonstration can be run at all.
Requested change: build the validator once in `records.py`, for example

```python
_VALIDATOR_CACHE: dict[str, Any] = {}

def _validator():
    if "v" not in _VALIDATOR_CACHE:
        import jsonschema
        _VALIDATOR_CACHE["v"] = jsonschema.Draft202012Validator(load_schema())
    return _VALIDATOR_CACHE["v"]
```

Until then this branch uses `generator.CachedRecordValidator`, which runs the
coordinator's own required-key, enum and semantic checks in the coordinator's
own order over the coordinator's own schema object, and falls back to the public
path if the module changes shape.
`test_cached_validator_rejects_exactly_what_the_public_one_rejects` (16
malformed payloads) is what makes that safe. **Delete
`CachedRecordValidator` when CR-1 lands**; it imports two private helpers from
`records.py` and should not outlive the defect.

**CR-2 (config).** `DegradationEvent.mode` is documented as a
`DegradationMode` value, but mode 3 covers burial, lateral displacement, uplift
and scour, which need different magnitudes and different observables. This
branch accepts the extra mode string `"burial"` in `synthetic_mat_history`.
Requested: either a `sub_mode` field or the explicit event kinds
`burial` / `displacement` / `uplift` / `scour`.

**CR-3 (config, minor).** `ObservationConfig` has no station kind and no period
for a DGT deployment. DGTs are currently attached to the `porewater` and
`bottom_water_probe` stations, which is defensible but implicit. A
`kind = "passive_sampler"` station would make it explicit.

**CR-4 (documentation).** `docs/DATA_CONTRACT.md` is still at v0.1 and
describes the vertical-panel contract: `mesh_tilt`, `data_origin: synthetic`,
five matrices, four qualifiers, and the `advance_panel` / `apply_transfers`
signatures. `docs/MODEL_SPEC.md` and `observation.schema.json` are the ones this
branch implements. The stale document should be rewritten or marked superseded
before anyone reads it as current.

---

## 7. Assumptions

Every number this branch produces is `ProvenanceLabel.SYNTHETIC_DEMO`, and every
parameter that shapes it is an assumption. None is a vendor specification, a
validated calibration or a measured ratio. The ones that matter:

**Generator** (`GeneratorAssumptions`)
* `chi_labile = 1.0`: the simulated dissolved pool *is* the labile pool. Stated
  rather than hidden.
* `total_recoverable_ratio = 1.6`, `hg_dissolved_inorganic_ratio = 1.0`. A real
  ratio is site, particle-load and method dependent and is not a constant.
* `methylmercury_fraction = 0.04` of the porewater Hg. A **risk** channel:
  capping alters sediment redox and can increase MeHg production.
* `chamber_area_m2 = 0.196` (a 0.5 m chamber), `chamber_deployment_s = 24 h`.
* `dgt_sampling_rate_m3_per_s = 2.8e-10`, the order of magnitude of `D*A/dg` for
  a standard open-pore disc, **not** a calibrated `Rs`.
* `dgt_capacity_ng = 5.0e4`, the order of magnitude of a Chelex binding disc. A
  sediment-face deployment genuinely exhausts it, and the honest report of that
  is an above-range lower bound.
* `dgt_lod_ng = 0.2`, `dgt_loq_ng = 0.6`, `dgt_relative_noise = 0.15`.
* `sample_loss_probability = 0.02` for a lost or voided laboratory sample.
* `probe_elements = ("Pb",)`: a Pb-selective voltammetric probe is not a mercury
  sensor.

**Condition** (`ConditionAssumptions`)
* `misclassification_probability = 0.10`: an inspection class is a judgement,
  not a measurement.
* `survey_abort_probability = 0.04` (weather, vessel). An aborted leg is
  `missing`, never a zero.
* Survey noise: coverage 0.03, burial 10 mm, scour 10 mm, displacement 0.25 m,
  tilt 0.8 deg, differential head 8 %.
* `differential_head_period_s = 1 day`: one daily aggregate per tile. Pore
  blockage evolves over months.
* `DAMAGE_CLASS_INTEGRITY_BAND`: the integrity interval each class implies.

**Scene stub** (`MatHistorySpec`, LABELLED_STUB)
* `fresh_flux_ratio = 0.005`, `saturated_flux_ratio = 0.060`,
  `breakthrough_s = 3.086 yr`, from the numbers `MODEL_SPEC` section 3 and the
  refactor plan's probe 5 record.
* `bottom_water_enrichment_s_per_m = 5.0e3`: near-bed enrichment per unit
  residual flux, standing in for the dilution the 2-D coastal model computes.
  Without it the bottom-water channel sits at background and says nothing.
* `burial_resistance_s_per_m = 2.0e8` (from `DegradationConfig`),
  `edge_leakage_fraction = 0.02`, `fouling_bypass_coupling = 0.35`,
  `clean_head_pa = 30`, `fouled_head_pa = 220`.

**QC** (`DEMO_THRESHOLDS`) every band, spike limit, tolerance and age limit is a
demonstration assumption, not a heavy-metal quality standard and not a QARTOD
certification.

One consequence is worth stating rather than hiding: with 2 % edge leakage, a
**fresh** mat in this history attenuates about 97.5 %, not 99.5 %, because the
bypass term dominates the residual flux of an intact layer. As fouling grows the
bypass grows with it, so most of the modelled performance loss over four years
is mode 2 acting through the edge, not mode 1 in the medium.

---

## 8. Stubs left (`LABELLED_STUB` in the code)

* `generator.synthetic_mat_history` / `MatHistorySpec`: an analytic stand-in for
  the reactive-layer timeline. It reproduces the documented shape (loading,
  breakthrough, fouling with bypass, burial resistance, displacement, tearing)
  but it is **not** a 1-D solve. `generator.scene_from_layer_history` is the
  real seam: it consumes `Sequence[tuple[datetime, LayerStep]]` per tile using
  only frozen contract types, and refuses a `LayerStep` whose `SeabedExchange`
  is `None` rather than inventing a driving concentration. When
  `feat/reactive-layer` lands, swap the builder and nothing else changes.
* `generator.CachedRecordValidator`: delete when CR-1 lands.

Not stubs, but gaps a later branch may want to fill:

* No `mat_permeability` records are generated. The operator classifies them
  (mode 2) if another branch produces them; `MatStateSample.permeability_m2`
  exists and is unused.
* No `acid_volatile_sulfide` or `simultaneously_extracted_metal` records are
  generated. Both fractions exist in the contract, and `never_merged` already
  refuses to relate them to anything.
* The tile positions in a scene default to the survey station's position when
  `ScriptedScene.tile_positions` is empty, so condition records for different
  tiles can share coordinates. The `tile_id` is what carries the attribution.

---

## 9. What the next branch needs from here

`feat/estimation` should read:

* `build_assimilation_set(records, config, qc_report=report)` and use only
  `AssimilationSet.assimilable`. `evidence_only` uses are display and data-age
  material.
* `ObservationUse.model_target` to route an aqueous record to the right state:
  `sediment_face_porewater`, `mat_layer_porewater` or `bottom_water`.
* `ObservationUse.is_censored` and `is_one_sided`. A below-LOD record is a
  two-sided interval, an above-range record is a lower bound with **no** upper
  bound, and a missing record is not in `assimilable` at all.
* `ObservationUse.degradation_mode` for the per-mode likelihood, and
  `AssimilationSet.for_mode` / `.for_tile`.
* `QCReport.asset_health` for the `CHECK_SENSOR` rule, including
  `AssetHealth.stale`, which is set both when the data age exceeds the limit and
  when there is no usable reading at all.
* For burial: `ModelQuantity.BURIAL_DEPTH` with
  `diagnostics["burial_masquerades_as_success"] = True`. A falling chamber flux
  next to a rising burial depth must raise `AmbiguityFlag.BURIAL`, not report an
  improvement.
