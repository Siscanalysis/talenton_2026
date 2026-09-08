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

# 1. the test suite: 434 tests, about two minutes
.venv\Scripts\python.exe -m pytest -q

# 2. a first look: one scenario, about 75 seconds
.venv\Scripts\python.exe -m reactive_seabed_mat.cli quick --out results
#    then open results\fresh_mat_quick\report\report.html in any browser

# 3. the interactive app
.venv\Scripts\streamlit.exe run app/streamlit_app.py
```

**In a hurry?** Every figure below is already committed under
[`docs/gallery/`](docs/gallery/), so you can look at the output before deciding
whether to run anything.

On Linux or macOS use `.venv/bin/python` and `.venv/bin/streamlit` instead.

```bash
# all six scenarios (several minutes), or just one
python -m reactive_seabed_mat.cli list
python -m reactive_seabed_mat.cli run displaced_section --out results
python -m reactive_seabed_mat.cli run-all --out results

# the comparison the whole project is about: no mat, calendar servicing and
# evidence-informed servicing, under identical assumptions
python -m reactive_seabed_mat.cli compare progressive_saturation --out results
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

**And a caveat we would rather state than be asked about.** 99 % is above
anything a real cap has achieved. In-situ thin-layer capping with activated
carbon in Trondheim harbour cut measured sediment-to-water fluxes by a factor of
2 to 10, that is 50 % to 90 %. Our model has uniform seepage, no bioturbation,
no consolidation and perfect mat-to-sediment contact, so its figure is an upper
bound set by the physics we chose to include. The comparison, with sources, is
in [`docs/EVIDENCE_BASE.md`](docs/EVIDENCE_BASE.md).

## The comparison the project is actually about

Six years, same seed, same forcing, same hotspot, same sampling schedule. Only
`PolicyConfig.kind` differs.

| Policy | Pb into the water | Services | Assumed cost |
|---|---|---|---|
| no mat | 642.3 kg | 0 | EUR 0 |
| fixed calendar servicing | 6.7 kg | 2 | EUR 3.73 M |
| evidence-informed servicing | 26.4 kg | 0 | EUR 0 |

The mat works. But **evidence-informed servicing under-services**: it let about
four times more lead through than a calendar and spent nothing. That is the
finding, not a defect. With chemistry on one tile out of nine, no seepage
measurement, and a capacity known only from a commissioning test, the estimated
saturation interval never narrows enough to justify sending a vessel. *The value
of evidence-informed maintenance is bounded by the monitoring programme that
feeds it.*

Every euro figure is an assumption. No supplier has been contacted.

## What is in here

| Path | Contents |
|---|---|
| `docs/MODEL_SPEC.md` | Every equation, boundary condition and acceptance rule |
| `docs/DATA_CONTRACT.md` | The observation contract and the frozen module boundary |
| `docs/ASSUMPTIONS.md` | Every default value, with its provenance label |
| `docs/LIMITATIONS.md` | What this cannot do, including where the physics works against the concept |
| `docs/EVIDENCE_BASE.md` | Every number against the measured literature, the open datasets, and the two places this model is more optimistic than reality |
| `docs/MATERIAL_KERATIN.md` | The keratin parameters, their sources and their seawater derating |
| `docs/PRIOR_ART.md` | Existing reactive caps, and what may not be claimed as novel |
| `docs/AUDIT.md`, `docs/AUDIT_DECISIONS.md` | The pre-publication audit and its decisions ledger |
| `REFACTOR_PLAN.md` | The audited plan, and the five numerical probes that settled the scheme |
| `src/reactive_seabed_mat/reactive_layer/` | The 1-D layer, the four degradation modes, service and forecasting |
| `src/reactive_seabed_mat/coastal_transport/` | The FiPy 2-D engine and the seabed source coupling |
| `src/reactive_seabed_mat/observations/` | Synthetic observations, QC, mat condition, the observation operator |
| `src/reactive_seabed_mat/estimation/` | Interval estimates of loading, attenuation and condition, from observations only |
| `src/reactive_seabed_mat/maintenance/` | The three servicing policies and the recommendations they produce |
| `docs/gallery/` | The committed output: every scenario, every map, already generated |
| `research/` | European supplier and interface evidence, materials, references |
| `research/datasets/` | Open datasets that back the numbers, how to get them, and the two gaps where nothing exists |
| `tools/build_gallery.py` | Regenerates `docs/gallery/` from scratch |
| `tests/` | Contract, layer, transport, observation, estimation, maintenance and integration tests |

**Not built yet**, and listed rather than implied: a design sweep over
footprint, thickness, loading, layout and service interval
(`docs/AUDIT.md` section G), the value-of-information experiment that section G
describes, and the optional machine-learning extension.

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
supplier has been contacted and no quotation exists.

Before publication the repository was audited the way a paper is audited before
submission: every claim checked against the code, every number recomputed, every
citation verified against the literature. It found five documented features that
did not exist, one module that could not be imported, a latent bug that would
have reported 100 % attenuation for a mat that was not there, and two places
where this model is more optimistic than the measured literature. The first
seven were fixed; the last two are written down in
[`docs/EVIDENCE_BASE.md`](docs/EVIDENCE_BASE.md) rather than tuned away. The full
report is [`docs/AUDIT.md`](docs/AUDIT.md) and the decisions ledger is
[`docs/AUDIT_DECISIONS.md`](docs/AUDIT_DECISIONS.md).
