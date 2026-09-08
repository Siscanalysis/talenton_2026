You are building the material and maintenance-simulation module on `feat/mesh-care`. Read `AGENTS.md`, the build brief, `docs/MODEL_SPEC.md` and the common contract. Work in your own Git worktree.

**Owned paths:** `src/mesh_demo/micro/`, `tests/micro/`, `examples/micro/`, `docs/handoffs/mesh_care.md`. Common dataclasses/configuration and dependency locks belong to the coordinator; propose additions rather than silently changing them.

## Build

Implement `advance_panel` using the agreed typed inputs/outputs. Start with Pb in one explicitly allocated material compartment. Add optional Hg as an independent compartment only after Pb tests pass. Implement effective adsorption/loading kinetics, finite capacity, uncertainty ranges and a fouling factor. Use the documented reduced model or a justified equivalent. Reuse SciPy/NumPy; do not attempt molecular simulation or invent seawater selectivity constants.

Expose retained mass, conditional remaining capacity, capture per time step and predicted service-life range. Neither saturation nor life is an instrument reading. A high-capacity material can still perform poorly because uptake is slow or water misses it. Keep effective contact separate from intrinsic material parameters.

The actual transfer must be bounded by available contact mass and remaining material capacity. Its kg value is the only uptake passed to the macro solver. Preserve all mass when replacing material: move old retained inventory into a retrieved-media ledger, create a new media ID, then reset only the new active inventory. Fouling must not delete already sorbed metal. Optional desorption/damage must return explicit released kg for the transport solver.

Provide a standalone example using a scripted contact sequence, without needing a map or hardware. Scenarios: low/no contact; fresh material; explicitly preloaded material; source/concentration increase; reduced transfer due to fouling; replacement. Treat all numerical values as synthetic unless the exact supporting experiment is supplied. Literature parameters are not our product specifications.

Add a small deterministic design/maintenance comparison: a few sorbent masses and fixed intervals across an uncertainty ensemble. Show assumed cost and per-element capture/escape, including a case where benefit is weak. Do not estimate profits from selling contaminated media. Keep recommendation logic itself in the feedback branch; provide forecasting functions it can call.

## Tests and deliverables

Test units; zero available mass; zero remaining capacity; nonnegative and bounded inventory; consistent service bookkeeping; time-step refinement; separate Pb/Hg material allocation; and mass returned exactly to the coupled model. Include a manufactured/analytical first-order case if using that model. Do not repair invalid physics only with unexplained clipping.

Deliver callable code, tests actually executed, an offline example and simple machine-readable timelines for UI consumption. Write the handoff with public functions, run commands, actual test outcomes, assumptions, fit/calibration needs and dependency proposals. A tiny, correct module is better than an elaborate unverified model.
