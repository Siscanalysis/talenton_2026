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

## Run it in five minutes

Needs **Python 3.11, 3.12 or 3.13** and nothing else: no account, no API key, no
network at run time, no map tile server. Verified from a clean clone with plain
`pip` on Windows 11 + CPython 3.12.13.

```powershell
git clone <this repository> talenton_2026
cd talenton_2026

python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.venv\Scripts\python.exe -m pip install -e . --no-deps

# 1. the test suite: 262 tests, about 90 seconds
.venv\Scripts\python.exe -m pytest -q

# 2. a first look: one scenario, about 60 seconds
.venv\Scripts\python.exe -m reactive_seabed_mat.cli quick --out results
#    then open results\fresh_mat_quick\report\report.html in any browser

# 3. the interactive app
.venv\Scripts\streamlit.exe run app/streamlit_app.py
```

On Linux or macOS use `.venv/bin/python` and `.venv/bin/streamlit` instead.

```bash
# all six scenarios (several minutes), or just one
python -m reactive_seabed_mat.cli list
python -m reactive_seabed_mat.cli run displaced_section --out results
python -m reactive_seabed_mat.cli run-all --out results
```

Each run writes a **single self-contained HTML report** with every map and
chart embedded: it opens offline, from a USB stick, with no internet.

> **Windows note.** Clone to a short path such as `C:\dev\talenton_2026`.
> Some dependencies ship deeply nested files and a very long parent path can
> trip the 260-character limit during `pip install`.

The five-minute narration is in [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md).

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

## What you will see

| View | What it shows |
|---|---|
| **Seabed residual flux** | How much Pb (or Hg) is still entering the water, per square metre, over the hotspot. A displaced or torn tile lights up here while its neighbours stay dark. |
| **Effective reactive cover** | Why each cell emits: covered, uncovered, damaged, displaced or leaking round the edge. Tile outlines are colour-coded by fault. |
| **Water concentration, with and against without** | The plume in ng/L on a shared colour scale, so the comparison is honest. |
| **Remaining fraction of the untreated plume** | Treated over untreated, 0 to 1. A model comparison, explicitly **not** a compliance assessment. |
| **Attenuation and saturation through time** | Multi-year curves. Attenuation starts above 99 % and falls to a plateau near 94 % as the medium loads. |

The plateau is worth understanding: once the chemistry is exhausted the mat is
still a **diffusive barrier**, so it keeps attenuating. The chemical
contribution of the sorbent is the difference between the two figures, not the
whole thing. The demo reports both rather than quoting the flattering one.

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
