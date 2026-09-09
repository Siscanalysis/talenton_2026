# Selective reactive seabed mat: demonstrator

[Read the PDF manuscript](manuscript/manuscript.pdf) | [Editable LaTeX source](manuscript/manuscript.tex) | [Figure gallery](docs/gallery/README.md)

An offline simulator of a modular, retrievable seabed cap containing a keratin-based reactive core between permeable carrier geotextiles. It models Pb, inorganic Hg and Cu transport through individual tiles, short coastal plume windows, synthetic monitoring and maintenance recommendations. The hotspot and operating parameters are assumed; these are simulated results, without field validation.

The [manuscript](manuscript/manuscript.pdf) documents the equations, assumptions, literature, numerical checks and regenerated results. The [paper traceability audit](docs/PAPER_PARAMETER_TRACEABILITY.md) explains which numbers from the supplied articles were previously considered and why laboratory uptake measurements were not substituted for seawater operating parameters. Published copper uptake on wool and mercury uptake on reduced human hair are real material-specific results; they do not validate this proposed core.

## Read the results

Open the [gallery previews](docs/gallery/README.md) on GitHub, or download and open the [interactive gallery](docs/gallery/index.html) locally. The HTML is self-contained and works offline. Each scenario has spatial flux maps and multi-year timelines; the manuscript also includes independent numerical and literature figures.

Interpret the plots using these distinctions:

- **Whole-hotspot emission** includes uncovered, damaged and bypass areas. Column attenuation describes transport through the modelled core. They are different quantities.
- **The non-sorbing barrier comparison** uses the same discrete transport geometry without reactive uptake. Its difference from the transient reactive curve includes storage and history, and need not remain positive after a source change.
- **Retained and retrieved inventories** belong to the full-footprint column ledger. Coastal windows have their own source, storage and boundary-export balance; they do not represent years of coastal transport.
- **Maintenance outcomes** depend on observation availability, QC, analytical fractions and the configured policy. Pb and Hg have chemical monitoring channels; Cu is physically simulated but unmonitored.
- **Peaks and bends** can mark source changes, damage or replacement. Numerical accuracy is established only for the cases and resolutions actually tested. See [timescale checks](docs/TIMESCALES.md), [limitations](docs/LIMITATIONS.md) and the manuscript.

## Run locally

The project declares Python 3.11?3.14 support in [pyproject.toml](pyproject.toml). Install the pinned dependencies before running offline:

```powershell
git clone https://github.com/Siscanalysis/talenton_2026.git talenton_2026
cd talenton_2026
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.venv\Scripts\python.exe -m pip install -e . --no-deps
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m reactive_seabed_mat.cli quick --out results
```

Open `results\fresh_mat_quick\report\report.html`. To use the app:

```powershell
.venv\Scripts\streamlit.exe run app/streamlit_app.py
```

On Linux or macOS use `.venv/bin/python` and `.venv/bin/streamlit`. With the environment activated:

```bash
python -m reactive_seabed_mat.cli list
python -m reactive_seabed_mat.cli run displaced_section --out results
python -m reactive_seabed_mat.cli run-all --out results
python -m reactive_seabed_mat.cli compare progressive_saturation --out results
python tools/build_gallery.py --out docs/gallery
```

Full scenario runs and gallery generation take substantially longer than the shortened `quick` run. Run exports include configuration and provenance, observations, QC, estimates, recommendations and service events. A run's saved data and manifest accompany its HTML report. See the [demonstration script](docs/DEMO_SCRIPT.md) and [manuscript build instructions](manuscript/README.md).

## Six scenarios

| Scenario | Defined experiment |
|---|---|
| `fresh_mat` | One year with nominal full hotspot coverage and the default source |
| `progressive_saturation` | Six years with the same source and material; loading can approach equilibrium below full capacity |
| `increased_leak` | At two years, porewater concentrations triple and seepage doubles |
| `displaced_section` | Local displacement at 1.5 years and partial tile damage at 2.2 years |
| `delayed_chemistry` | Probe dropout and drift with increased laboratory latency; only available evidence can affect decisions |
| `undersized_mat` | Nominal 45% coverage, a 2 mm core and stronger seepage |

The policy comparison applies no mat, fixed servicing and evidence-informed servicing to the same source schedule and observation design. Its costs are assumptions. A policy ranking in this experiment does not establish the best policy for a real site.

## Scientific documentation

| Document | Contents |
|---|---|
| [Manuscript](manuscript/manuscript.pdf) | Complete referenced report, equations, figures and current results |
| [Assumptions](docs/ASSUMPTIONS.md) | Resolved default configuration and derived quantities |
| [Model specification](docs/MODEL_SPEC.md) | Governing equations, boundaries and computational methods |
| [Data contract](docs/DATA_CONTRACT.md) | Observation units, fractions, timing and module interfaces |
| [Material evidence](docs/MATERIAL_KERATIN.md) | Keratin chemistry, capacities and transfer limits |
| [Supplied-paper audit](docs/PAPER_PARAMETER_TRACEABILITY.md) | Page-level provenance, conversions and source inconsistencies |
| [Evidence base](docs/EVIDENCE_BASE.md) | Measured comparators, datasets and calibration gaps |
| [Limitations](docs/LIMITATIONS.md) | Remaining physical, numerical, ecological and estimation limitations |
| [Timescales](docs/TIMESCALES.md) | Tested temporal, spatial, horizon and plume-window sensitivities |
| [Prior art](docs/PRIOR_ART.md) | Existing cap technologies and the limits of novelty claims |
| [Deployment scale](docs/DEPLOYMENT_SCALE.md) | Documented area geometry and assumed material/cost arithmetic |

The implementation is in [`src/reactive_seabed_mat/`](src/reactive_seabed_mat/), verification in [`tests/`](tests/), and reference registries in [`research/references/`](research/references/). Reactive caps and geotextile sorbent constructions have prior art. This repository demonstrates a modelling and monitoring workflow; it supplies neither a site design nor an experimentally validated material, ecological assessment or supplier quotation.
