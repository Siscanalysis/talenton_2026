You are the optional ML/experimental-design agent on `feat/ml-extension`. Do not start this work until the coordinator confirms that micro, transport, observations and the presentation baseline pass integration tests. Read all shared scientific/data rules.

**Owned paths:** `src/mesh_demo/ml/`, `tests/ml/`, `examples/ml/`, `docs/handoffs/ml_extension.md`. Do not modify physical equations, training-data provenance or common contracts to make ML results look better.

Choose **one** deliverable, not both:

A. A small neural-network/hybrid surrogate for material uptake or a costly simulator response. Train on explicitly simulation-generated cases unless real matched experiments are available. Use a deterministic train/validation/test split by complete scenario or material batch. Compare a simple interpolation/regression baseline, runtime and worst-case/relative errors. Test held-out parameter regimes, positivity/capacity bounds and out-of-domain warnings. Re-evaluate every optimised candidate in the original simulator. Synthetic accuracy is not experimental validation.

B. A next-experiment selector for real future material studies. Define candidate material descriptors and controllable water/flow conditions, objectives, controls, repeats and laboratory constraints. With a small sample count, use an uncertainty-aware Gaussian-process/design-of-experiments baseline rather than defaulting to a large network. Demonstrate sequential selection using labelled synthetic outcomes; do not announce a winning actual formulation. The selector must expose the measurement uncertainty and rationale for each recommendation.

No generic “AI detects pollution” classifier. No metal prediction from contextual sensors without a target-responsive measured signal. No invented access to a vendor's spectra/electrochemical data. No random time-row split that leaks neighbouring portions of the same breakthrough run into test data.

Deliver a small callable module, executed comparison tests, one presentation figure/table, provenance, and a handoff explaining whether the extension adds measurable value over the non-ML baseline. If it adds no value, report that and keep it optional.
