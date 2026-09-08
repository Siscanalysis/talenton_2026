# Selective reactive seabed mat: demonstrator

An offline, science-grounded **presentation demo** of a thin, modular,
retrievable reactive mat laid over an authorised contaminated seabed area. The
mat attenuates the Pb (and optionally Hg) flux from the sediment into the
overlying water. The demonstrator simulates that flux, the four ways the mat
degrades, the observations an operator would actually have, and the maintenance
recommendation those observations support.

```
authorised contaminated seabed hotspot
  -> contaminant flux through / near the seabed
  -> reactive mat (1-D reactive layer, per tile)
  -> residual flux into the overlying water
  -> 2-D coastal advection and diffusion
```

**This is not a field-validated remediation system, and the basic idea is not
new.** Reactive caps, permeable reactive barriers and activated-carbon sediment
amendments already exist and are commercially deployed. See
[`docs/PRIOR_ART.md`](docs/PRIOR_ART.md) for what is established practice and
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) before quoting any number from
here.

---

## Install and run

```powershell
# Windows PowerShell, from this directory
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.lock.txt
uv pip install --python .venv\Scripts\python.exe -e . --no-deps

# tests
.venv\Scripts\python.exe -m pytest -q

# scenarios A to F, offline, no account and no network
.venv\Scripts\python.exe -m reactive_seabed_mat.cli run-all --out results

# the local app
.venv\Scripts\streamlit.exe run app/streamlit_app.py
```

Exact commands, timings and the five-minute narration are in
[`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md).

## The six scenarios

| | Scenario | What it shows |
|---|---|---|
| A | `fresh_mat` | A fresh, fully covering mat against the same hotspot with no mat, under identical forcing |
| B | `progressive_saturation` | Six years at the same chemistry: the medium loads, attenuation falls, the layer breaks through |
| C | `increased_leak` | The porewater concentration triples and the seepage doubles. The mat is unchanged, so this is a stronger source, not a failing cap |
| D | `displaced_section` | One tile displaced, another punctured. Those cells return to the bare flux; their neighbours keep working |
| E | `delayed_chemistry` | Probe dropout and drift while laboratory chemistry is in transit. The late result changes the decision when it arrives, and not before |
| F | `undersized_mat` | A deliberately poor design: 45 % coverage, 2 mm thick, over a stronger seep. Poor capture, bad cost per kilogram |

Scenario F exists because a demonstration that always succeeds is not evidence.

## What is in here

| Path | Contents |
|---|---|
| `docs/MODEL_SPEC.md` | Every equation, boundary condition and acceptance rule |
| `docs/DATA_CONTRACT.md` | The observation contract and the frozen module boundary |
| `docs/ASSUMPTIONS.md` | Every default value, with its provenance label |
| `docs/LIMITATIONS.md` | What this cannot do, including where the physics works against the concept |
| `docs/PRIOR_ART.md` | Existing reactive caps, and what may not be claimed as novel |
| `REFACTOR_PLAN.md` | The audited plan, and the five numerical probes that settled the scheme |
| `src/reactive_seabed_mat/reactive_layer/` | The 1-D layer, the four degradation modes, service and forecasting |
| `src/reactive_seabed_mat/coastal_transport/` | The FiPy 2-D engine and the seabed source coupling |
| `src/reactive_seabed_mat/observations/` | Synthetic observations, QC, the observation operator |
| `src/reactive_seabed_mat/estimation/`, `maintenance/` | Ensemble estimator, degradation attribution, policy, costs |
| `src/reactive_seabed_mat/optimisation/` | Footprint, thickness, loading, layout and servicing sweep |
| `research/` | European supplier and interface evidence, materials, references |
| `tests/` | Contract, layer, transport, observation, estimation and integration tests |

## The rules the code is built to keep

The mat attenuates a flux; it does not intercept a plume, and nothing is ever
subtracted from a water-column cell. Hidden simulated truth, measurements and
estimates are separate stores. A result cannot influence a decision before
`available_at_utc`. A non-detect is a bound, not a zero; a missing value is not
a non-detect. Pb and Hg are never inferred from turbidity, conductivity or pH.
The four degradation modes stay independent, and burial reduces the apparent
flux rather than proving success. Failure can be local: everything is per tile.
Mass is conserved per element across sediment, mat, retrieved media, water and
boundary export. No recommendation ever actuates anything.

Full list: [`AGENTS.md`](AGENTS.md).

## One thing worth knowing about the numerics

The first reactive-layer scheme conserved mass to one part in 10^14 and was
still wrong: refining the time step moved the predicted breakthrough from
4.2 years to 1.0 years. **Mass conservation alone does not validate a scheme.**
The layer now uses a fully implicit coupled solve, verified converged from a
12 hour step down to 30 minutes, and cross-checked against an independent FiPy
solve. Every numerical result here carries a refinement test as well as a ledger
test.

## Status

Every material parameter, schedule and euro value is a labelled assumption. No
supplier has been contacted and no quotation exists. Nothing has been pushed to
any remote.
