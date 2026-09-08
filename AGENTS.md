# AGENTS.md — how work is split in this repository

One coordinator owns the shared spine. Everything else is a branch with its own
owned paths. Agents propose changes to shared files in their handoff; they do
not edit them.

## Coordinator-owned (do not edit on a branch)

```
contracts/                        DATA_CONTRACT.md, observation.schema.json
src/mesh_demo/contracts.py        frozen dataclasses and function signatures
src/mesh_demo/units.py            SI conversions
src/mesh_demo/config.py           the single run-configuration schema
src/mesh_demo/observations/records.py   validation, JSONL I/O, the time gate
pyproject.toml, requirements.lock.txt   dependency lock
tests/contracts/                  the frozen-contract test suite
docs/MODEL_SPEC.md                equations and acceptance rules
```

The contract is frozen at `CONTRACT_VERSION = "0.1.0-frozen"`. If a branch needs
a new field, it writes the request in its handoff and keeps working against the
current types.

## Branches and owned paths

| Branch | Prompt | Owned paths |
|---|---|---|
| `feat/mesh-care` | `prompts/02_mesh_care.md` | `src/mesh_demo/micro/`, `tests/micro/`, `examples/micro/`, `docs/handoffs/mesh_care.md` |
| `feat/coastal-2d` | `prompts/03_coastal_transport.md` | `src/mesh_demo/transport/`, `src/mesh_demo/transport/geodata/`, `tests/transport/`, `examples/transport/`, `docs/handoffs/coastal_2d.md` |
| `feat/feedback` | `prompts/04_observations_feedback.md` | `src/mesh_demo/observations/` (except `records.py`), `src/mesh_demo/feedback/`, `tests/feedback/`, `examples/feedback/`, `docs/handoffs/feedback.md` |
| `feat/presentation` | `prompts/05_presentation_integration.md` | `app/`, `src/mesh_demo/reporting/`, `tests/presentation/`, `examples/presentation/`, `docs/presentation/`, `docs/handoffs/presentation.md` |
| `research/sensors` | `prompts/01_sensor_supplier_research.md` | `docs/research/`, `data/vendor_evidence/`, `docs/handoffs/research_sensors.md` |
| `feat/ml-extension` | `prompts/06_optional_ml.md` | `src/mesh_demo/ml/`, `tests/ml/`, `examples/ml/`, `docs/handoffs/ml_extension.md` |

`src/mesh_demo/scenarios/` and `src/mesh_demo/cli.py` are integration surface:
coordinator-owned, written after the branches merge.

## Non-negotiable rules

These are checked by tests, not by good intentions.

1. **Separate the three states.** Hidden simulated truth, measurements and
   estimates never share a container. `results/<run>/truth/` is off limits to
   `feedback/` and to the app's operational views.
2. **No lookahead.** A record influences a decision only at or after
   `available_at_utc`. Use `observations.records.observations_available`.
3. **Non-detect is a bound.** Never a zero, never dropped. Missing is not
   non-detect.
4. **No chemistry from proxies.** Pb/Hg are never inferred from turbidity,
   conductivity, salinity, temperature or pH.
5. **Per-element mass conservation.** Water + active mesh + retrieved media +
   boundary export, per element, always. No first-order destruction of Pb or Hg.
6. **Finite capacity, bounded transfer.** Uptake is bounded by the mass actually
   available in the contact region and by remaining capacity. The macro model
   removes exactly the kg the micro model reports, once.
7. **Explicit units.** SI internally; conversion only at the boundaries; no unit
   is inferred from a parameter name. Solid assays never use the aqueous ladder.
8. **Label every number.** `measurement`, `external_model`, `literature`,
   `assumption` or `synthetic_demo`. Euro values are assumptions unless a dated
   quotation is attached.
9. **Recommendations, not actuation.** `human_confirmation_required = True` and
   `execution_mode = "simulation_only"` are structurally enforced.
10. **Report failures.** Numerical corrections, failed checks and unresolved
    science go in the manifest and the handoff, not into a rounding.
11. **Offline by default.** No account, token, tile server or network call in
    the default run.
12. **Do not invent vendor capability.** No fabricated register map, detection
    limit, price or protocol. Unknown stays unknown.

## Working agreement

* Run `python -m pytest tests/contracts -q` before and after your changes.
* Stubs are allowed during parallel work but must be labelled
  `LABELLED_STUB` in the code and listed in the handoff.
* Each branch writes `docs/handoffs/<branch>.md`: public functions, exact run
  commands, tests actually executed with their real outcome, assumptions,
  and any dependency request.
* Commit complete, tested increments. Do not push to any remote.
