You are the coordinating engineer for the attached `mesh_demo_agent_kit`. Build a small, science-grounded presentation demo, not a production system.

Read `MESH_DEMO_BUILD_BRIEF.md`, `AGENTS.md`, `contracts/DATA_CONTRACT.md`, `docs/MODEL_SPEC.md`, and `docs/REUSE_AND_DATA.md`. Inspect the repository before modifying it. Run the existing contract tests. The packet currently contains briefs, prompts and tested contract utilities—not a completed simulator.

Deliver one local app combining:
1. A reduced Pb mesh-loading/capture model with optional separate Hg parameters, uncertainty, fouling and replacement bookkeeping.
2. A reused 2D advection–diffusion solver showing a hypothetical source and finite-capacity mesh. Use the proposed FiPy adapter first; retain European data/model adapters as extensions.
3. An observation replay and feedback loop recommending sampling, sensor checks, inspection or replacement. It must not read hidden simulation truth or future laboratory results.
4. A presentation view and offline HTML/JSON exports comparing no mesh, fixed maintenance and evidence-informed maintenance under identical assumptions.

First produce a short implementation plan and freeze the shared interfaces. Preserve and extend the supplied observation contract rather than creating several incompatible schemas. Implement a first vertical slice before adding optional functionality.

Coordinate these independent branches using the supplied prompts and separate Git worktrees:
- `research/sensors` → `prompts/01_sensor_supplier_research.md`
- `feat/mesh-care` → `prompts/02_mesh_care.md`
- `feat/coastal-2d` → `prompts/03_coastal_transport.md`
- `feat/feedback` → `prompts/04_observations_feedback.md`
- `feat/presentation` → `prompts/05_presentation_integration.md`

Where parallel agents are unavailable, implement the same work serially, starting with the shared configuration and the micro/transport coupling. Do not merely write a plan: implement, run tests and produce the first end-to-end scenario. Only start `prompts/06_optional_ml.md` after the baseline passes integration checks.

Research agent: verify European manufacturers and exact sensor usefulness, chemical fraction, limitations, interface/protocol, software access, availability evidence and quotation needs. Do not invent a continuous mercury probe, a detector limit, or a vendor register map. Research uncertainty must not block clearly labelled synthetic replay.

Mandatory safeguards: explicit SI conversions; per-metal mass conservation; finite material capacity; no pollutant destruction; separate observed/estimated/true state; non-detect is not zero; no inference of metal concentration from ordinary water-quality proxies; no unsourced map hotspots; read-only/emulated interfaces; human-approved maintenance only. Treat daily/de-tided or surface current products according to their actual limitations.

Keep all defaults offline and the initial implementation compact. Do not add authentication, cloud deployment, Kubernetes, mobile apps or 3D physics. Pin only dependencies actually tested. Export the scenario inputs, results, provenance and limitations together. Report unsuccessful tests and unresolved science honestly.

Before handoff, demonstrate baseline, source-change, fouling/loading, sensor-failure/delayed-result and replacement scenes. Include at least one case where capture or the economic comparison is poor. Summarise what was built, exact run commands, tests executed, limitations, and remaining work. Prepare Git-ready output, but do not create or push a remote repository without my approval.
