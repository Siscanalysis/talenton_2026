# AGENTS.md: how work is split in this repository

One coordinator owns the shared spine. Everything else is a branch with its own
owned paths. Agents propose changes to shared files in their handoff; they do
not edit them.

## Coordinator-owned (do not edit on a branch)

```
src/reactive_seabed_mat/contracts.py            frozen dataclasses and signatures
src/reactive_seabed_mat/units.py                SI conversions and unit ladders
src/reactive_seabed_mat/config.py               the single run-configuration schema
src/reactive_seabed_mat/results.py              run layout, manifest, state separation
src/reactive_seabed_mat/schemas/                observation.schema.json
src/reactive_seabed_mat/observations/records.py validation, JSONL I/O, the time gate
src/reactive_seabed_mat/scenarios/registry.py   scenarios A to F
pyproject.toml, requirements.lock.txt           dependency lock
tests/contracts/                                the frozen-contract test suite
docs/MODEL_SPEC.md, docs/DATA_CONTRACT.md       equations and the contract
REFACTOR_PLAN.md                                the audited plan
```

The contract is frozen at `CONTRACT_VERSION = "0.2.0-frozen-mat"`. If a branch
needs a new field, it writes the request in its handoff and keeps working
against the current types.

## Branches and owned paths

| Branch | What it builds | Owned paths |
|---|---|---|
| `feat/reactive-layer` | the 1-D reactive layer, tile state, the four degradation modes, service, forecasting | `src/reactive_seabed_mat/reactive_layer/`, `tests/reactive_layer/`, `examples/reactive_layer/`, `docs/handoffs/reactive_layer.md` |
| `feat/coastal-2d` | the FiPy 2-D engine, the seabed source coupling, geodata adapters | `src/reactive_seabed_mat/coastal_transport/`, `tests/coastal_transport/`, `examples/coastal_transport/`, `docs/handoffs/coastal_2d.md` |
| `feat/observations` | the synthetic observation generator, QC, mat condition, the observation operator | `src/reactive_seabed_mat/observations/` except `records.py`, `tests/observations/`, `examples/observations/`, `docs/handoffs/observations.md` (**merged**) |
| `feat/estimation` | the estimator and the maintenance policy | `src/reactive_seabed_mat/estimation/`, `src/reactive_seabed_mat/maintenance/`, `tests/maintenance/` (**merged**) |
| `feat/optimisation` | the design sweep over footprint, thickness, loading, layout and servicing | `src/reactive_seabed_mat/optimisation/`, `tests/optimisation/`, `docs/handoffs/optimisation.md` (**not started**; see `docs/AUDIT.md` section G) |
| `feat/presentation` | the local app and the offline evidence exports | `app/`, `src/reactive_seabed_mat/visualization/`, `tests/presentation/`, `docs/presentation/`, `docs/handoffs/presentation.md` |
| `research/sensors` | European supplier and interface evidence, prior art | `research/`, `docs/handoffs/research_sensors.md`, `docs/PRIOR_ART.md` |
| `feat/ml-extension` | one optional ML experiment, only after integration | `src/reactive_seabed_mat/ml/`, `tests/ml/`, `docs/handoffs/ml_extension.md` |

`src/reactive_seabed_mat/scenarios/run.py` and `cli.py` are integration surface:
coordinator-owned, written after the branches merge.

## Non-negotiable rules

These are checked by tests, not by good intentions.

1. **The mat attenuates a flux; it does not intercept a plume.** No frontal
   area, no swept volume, no interception efficiency, and nothing is subtracted
   from a water-column cell.
2. **Separate the three states.** Hidden simulated truth, measurements and
   estimates never share a container. `results/<run>/truth/` is off limits to
   `estimation/`, `maintenance/` and the app's operational views.
3. **No lookahead.** A record influences a decision only at or after
   `available_at_utc`. Use `observations.records.observations_available`.
4. **Non-detect is a bound.** Never a zero, never dropped. Missing is not
   non-detect. Above-range is a lower bound.
5. **No chemistry from proxies.** Pb and Hg are never inferred from turbidity,
   conductivity, salinity, temperature, pH, redox or current.
6. **The four degradation modes stay independent.** Saturation, fouling,
   displacement and local damage are modelled and reported separately. Burial
   reduces apparent flux and must never be read as success.
7. **Failure can be local.** Every condition observation carries a `tile_id`,
   and a failed tile affects its own cells only.
8. **Per-element mass conservation.** Released from sediment equals water plus
   active mat plus retrieved media plus boundary export, per element, always.
9. **Explicit units.** SI internally; conversion only at the boundaries; no unit
   is inferred from a parameter name. A flux uses the flux ladder, a length the
   length ladder.
10. **A conserving scheme is not automatically a correct scheme.** Numerical
    changes need a refinement test, not only a ledger check.
11. **Label every number.** `measurement`, `external_model`, `literature`,
    `assumption`, `fitted` or `synthetic_demo`. Euro values are assumptions
    unless a dated quotation is attached.
12. **Recommendations, not actuation.** `human_confirmation_required = True` and
    `execution_mode = "simulation_only"` are structurally enforced.
13. **No novelty claims.** Reactive caps and carbon amendments already exist.
    Differentiation is a hypothesis list, not a result.
14. **No ordnance handling.** The source is an abstract authorised contaminant
    hotspot. Nothing simulates, locates or recommends handling munitions.
15. **Offline by default.** No account, token, tile server or network call in
    the default run.
16. **Do not invent vendor capability.** No fabricated register map, detection
    limit, price or protocol. Unknown stays unknown.

## Working agreement

* Run `python -m pytest tests/contracts -q` before and after your changes.
* Stubs are allowed during parallel work but must be labelled `LABELLED_STUB`
  in the code and listed in the handoff.
* Each branch writes `docs/handoffs/<branch>.md`: public functions, exact run
  commands, tests actually executed with their real outcome, assumptions, and
  any dependency or contract request.
* British English in prose. No em-dashes.
* Commit complete, tested increments.
* Before publishing anything, run the audit in `docs/AUDIT.md` again: check every
  documented feature against the code, recompute every quoted number, and verify
  every citation. The first pass found five features that did not exist and a
  latent bug that reported 100 % attenuation for a mat that was not there.
  Decisions go in `docs/AUDIT_DECISIONS.md`, which is authoritative.
