You are building observation ingestion, state estimation and maintenance feedback on `feat/feedback`. Read `AGENTS.md`, the build brief, supplier notes, model specification and data contract. Work in a separate worktree.

**Owned paths:** `src/mesh_demo/observations/`, `src/mesh_demo/feedback/`, `tests/feedback/`, `examples/feedback/`, `docs/handoffs/feedback.md`. Use the supplied validation/units modules; do not fork the schema.

## Ingestion and observation model

Start with JSONL/CSV replay. Treat the supplied fixture file as I/O examples, not coherent physics data. Build a synthetic measurement generator from a model history with separate noise, sampling cycle, quantification limit, missingness and result latency. Preserve record provenance and raw records.

Implement the agreed timestamp gate: no result may influence a decision before `available_at_utc`. Compare delayed results with predictions at sampling time, not with current state. Keep `observed_at`, `available_at`, station/depth, parameter, matrix, fraction and method intact. A non-detect provides a bound; a missing observation is not a non-detect. Unknown uncertainty remains unknown.

Environmental sensors constrain water conditions or QA, not metal concentration. No Pb/Hg predictions inferred solely from turbidity/conductivity/pH. Incompatible chemical fractions require an explicit observation operator or must remain unassimilated evidence. For passive samplers, use an integration operator only when the sampler model is justified; otherwise support metadata/display without a fake point concentration.

## Quality and feedback

Use transparent range/stuck-value/spike checks and data-age rules, with meaningful flags inspired by the cited QARTOD baseline. Thresholds are configurable demo assumptions, not official heavy-metal standards. Separate sensor health from material saturation.

Implement a small ensemble/grid-based estimator or deliberately simple bounded-state update. Limit estimated quantities to what the observations plausibly constrain. Support ambiguity between stronger source, plume movement, fouling/saturation and sensor drift. Do not claim perfect diagnosis. Never load hidden truth/event labels into the estimator or policy.

Output CONTINUE, REQUEST_CHEMICAL_SAMPLE, CHECK_SENSOR, INSPECT_MESH, PLAN_REPLACEMENT or INSUFFICIENT_EVIDENCE with evidence IDs, data age, reasons, uncertainty and human-confirmation requirement. Simulate accepted actions separately; do not connect to physical actuators.

Compare one fixed policy and one evidence-informed policy under the same forcing, noise seeds and budgets. A small sensor/sampling experiment can compare fixed sample times with information-triggered sampling; include sample/visit costs and response delays. If no evidence justifies replacement, request information rather than fabricate confidence.

## Hardware optional

Only add a read-only adapter when the exact manual and message/register definitions are verified. Otherwise use a clearly labelled own-protocol emulator. Do not guess Modbus addresses or imply a vendor has an open API. Networking is not required for completion.

## Tests

Run tests for UTC and units, non-detect/missing distinction, future-result exclusion, delayed-result treatment, failed/stale sensor behaviour, chemical-fraction mismatch, no hidden-truth access, duplicate-action prevention and old-media sample handling after replacement. Include an intentionally ambiguous case. Deliver example inputs/outputs, a recommendation log, tests and handoff.
