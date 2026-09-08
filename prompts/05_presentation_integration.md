You are building the presentation layer on `feat/presentation`. Read the build brief, contract and model limits. Work in a separate worktree. The coordinator owns the final integration merge and dependency lock.

**Owned paths:** `app/`, `src/mesh_demo/reporting/`, `tests/presentation/`, `examples/presentation/`, `docs/presentation/`, `docs/handoffs/presentation.md`. Do not move core algorithms into UI callbacks or fabricate missing solver outputs.

## Deliver one small local app

Use Streamlit + Plotly unless the coordinator has documented a smaller alternative. Three pages/tabs are enough:
- **Coast / plume:** 2D field, source, mesh and station locations; current arrows and time control.
- **Mesh care:** estimated retained mass/capacity, uncertainty and service-life interval; captured/escaped mass and assumed cost comparison.
- **Evidence / decision:** observation type/fraction/age/quality, recommendation reason, sensor/supplier evidence and assumptions.

Use the shared modules or their documented result files. During parallel development use labelled fixture results; remove or visibly retain the fixture label before handoff. A 3D terrain rendering is optional only after the 2D app works, and must be labelled as visualisation rather than 3D transport.

The source/map modes must be obvious: synthetic; real geographic context with illustrative physics; imported forcing. Every main chart shows provenance, units and simulation/validation status. A real map must not imply we found a real munition hotspot. Show estimates separately from hidden truth; truth is an evaluation toggle, not an operational sensor channel.

## Presentation story

Create a five-minute script: baseline with/without mesh; loading/fouling; source change versus current reversal; sensor dropout with delayed chemistry; accepted simulated replacement and preserved mass ledger. Include a poor-performance case. Narrate what the software demonstrates and what the material/site experiments still need to establish.

Provide only a few meaningful controls: scenario, source multiplier, material loading/preload, current condition and policy. Set sensible bounds and prevent the UI from inventing scientifically meaningful probabilities. Configuration changes invalidate cached results correctly.

## Offline evidence package

Export self-contained HTML with embedded plots, scenario/config JSON, per-metal ledger, observation/estimate/action timelines and a short limitations/reference section. PNG snapshots are useful when export dependencies are available; otherwise document the limitation. Do not require a map-tile server, API token or cloud account for the presentation to run.

Show no-mesh/fixed/feedback comparisons under identical conditions, with sample and service costs explicitly assumed unless quoted. Do not imply regulatory compliance, ecological safety or field-proven savings. Source/interception/retention are different percentages.

## Acceptance

Document one start command and an offline replay command. Execute a smoke test, check chart labels/units, missing-data scenes, configuration-cache invalidation and independence from the hidden-truth store. Confirm that exports carry the same provenance and uncertainty labels as the screen. Record run commands and limitations in the handoff. Do not publish or push to a remote without user approval.
