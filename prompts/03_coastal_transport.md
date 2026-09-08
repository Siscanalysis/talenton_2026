You are building the macro transport module on `feat/coastal-2d`. Read the shared instructions, build brief, `docs/MODEL_SPEC.md`, `docs/REUSE_AND_DATA.md` and contract. Work in a separate worktree.

**Owned paths:** `src/mesh_demo/transport/`, `src/mesh_demo/geodata/`, `tests/transport/`, `examples/transport/`, `docs/handoffs/coastal_2d.md`. Shared contracts/configs and dependency locks are coordinator-owned.

## Minimum implementation

Wrap FiPy for a **2D advection–diffusion** equation with an explicit effective mixing depth, source kg/s, boundary conditions and a per-metal mass ledger. Do not write a new CFD solver. Use a simple verified offline channel/coastal-like domain first; physical consistency and conservation are more important than a realistic-looking coastline.

Implement the agreed `transport_step`, `build_contacts` and `apply_transfers` boundaries. Until the micro module arrives, use a labelled zero-transfer or deterministic bounded-transfer stub. Represent a mesh's true material mass, contact/exchange assumption and unresolved spatial footprint separately. Do not equate a small panel with a perfectly absorbing whole grid cell; do not duplicate capacity across cells or remove uptake both in an implicit sink and in the coupling routine.

Generate baseline, tidal/reversing-current and changed-source cases. Separate change in local concentration from change in total emitted mass. Resolve signed inlet/outlet transport when current reverses. No first-order disappearance of elemental Pb/Hg. Reject unsupported overlapping panels in the first version.

## Optional geography and EU data

Add one adapter that reads cached data and preserves metadata. Start with Copernicus/EMODnet official interfaces. Keep a strictly offline default. Discover the actual current dataset variables, depth, averaging and resolution before use. Daily/de-tided currents cannot be used as a tide-resolving input. Surface flow is not automatically near-bed flow.

Three explicit modes: synthetic domain; real map with illustrative flow/source; imported forcing with its resolution limits. Do not silently promote between them. Keep a metric simulation CRS and convert only for display. A bathymetric map does not itself generate currents; label whether depth is actually in the numerical model or merely visual context.

Do not make OpenDrift, TELEMAC or a fresh local 3D hydrodynamic installation another required engine in this sprint. Document an adapter boundary for existing outputs. A later OpenDrift particle implementation must preserve particle mass and define concentration/contact estimation explicitly; it is not equivalent to Eulerian concentration by default.

## Acceptance

Execute tests: zero-source conservation; closed-boundary mass conservation; source normalisation; known diffusion/advection benchmark; boundary export accounting; current reversal; no transfer through land; uptake limited by available inventory; time/grid refinement; identical forcing for no-mesh versus mesh scenarios. Report numerical corrections and tolerances rather than silently hiding negatives.

Deliver fields/timelines and a compact static or interactive plot for integration, scenario/config metadata and an honest resolution statement. A convincing map without a checked mass ledger is not an acceptable completion.
