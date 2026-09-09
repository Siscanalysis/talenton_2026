# TalentON 2026: reactive seabed mat manuscript

[Open the PDF report](manuscript.pdf) | [Editable main LaTeX file](manuscript.tex) | [Bibliography](references.bib)

The manuscript documents the scientific revision of the reactive seabed mat demonstrator: all six regenerated scenarios, the three-policy comparison, material evidence, assumptions, equations, synthetic monitoring, numerical verification, deployment scale and remaining limitations. It distinguishes whole-hotspot emission from column attenuation and keeps the full-column and coastal-window mass ledgers explicit. The results are synthetic, without field validation.

The supplied keratin papers were inspected for numerical parameter provenance. Their measurements and transfer limits are documented in the report and the included [page-level audit](data/paper_parameter_traceability.md), with [machine-readable values and article hashes](data/paper_parameter_traceability.json). No copyrighted source articles are included.

## Editable files and data

| Path | Contents |
|---|---|
| `manuscript.tex`, section `.tex` files | Main document and editable scientific narrative |
| `references.bib`, `manuscript.bbl` | Bibliography source and compiled reference list |
| `figures/` | Locally generated vector PDF figures and PNG previews |
| `data/scenario_summary.json` | Regenerated configurations, timelines, inventories, windows and evidence summaries for six scenarios |
| `data/policy_summary.json` | The regenerated no-mat, fixed and evidence-informed comparison |
| `data/gallery_plots.json`, `data/gallery_tables.json` | Plot traces and tables extracted from the regenerated offline gallery |
| `data/` numerical audit JSON files | Independent reactive-layer and timescale/coastal refinement results copied by the numerical renderer |
| `verification/scenario_audit.json` | Per-run checks of exact horizons, valid snapshot ages, unique observation IDs, source-map/timeline agreement and separate ledger residuals |
| `verification/` | Test, manuscript and PDF-build verification records |
| `provenance.json` | Scientific source inventory, revision provenance and file hashes |
| `build.ps1` | LaTeX/BibTeX build script |

The repository's source, tests and scientific documentation are the evidential corpus. Internal prompts, agent instructions, handoffs and development narratives are excluded from the manuscript's source discussion. The baseline commit `158d103ec9deafe86d9ea142c0e292df456a3c59` is retained for historical traceability; current results belong to the published scientific revision, not the unmodified baseline.

Full run exports are generated under `results/revision/`, including the observation/QC/estimate/recommendation/service records and manifests. The portable JSON summaries and figures above support review without loading a private runtime cache.

## Rebuild the PDF from included data

With `pdflatex` and `bibtex` available on PATH, run from the repository root:

```powershell
.\manuscript\build.ps1
```

The script performs pdfLaTeX, BibTeX and two further pdfLaTeX passes. It stops if a build step fails. A working MiKTeX or TeX Live installation is required; the document does not fetch remote maps or images.

To redraw the main figures from the included JSON after installing the repository dependencies:

```powershell
python manuscript/make_figures.py
.\manuscript\build.ps1
```

## Regenerate simulations, audit data and manuscript results

Run the following from the repository root with its Python environment activated. These are full computations and take longer than the shortened CLI `quick` example. The worker count can be adjusted to the machine.

```powershell
python tools/build_gallery.py --out docs/gallery --workers 2
python tools/export_manuscript_data.py
python manuscript/extract_gallery.py .
python manuscript/make_figures.py
python tools/render_manuscript_tables.py
python tools/revision_numerics.py --output results/numerical-audit
python tools/benchmark_layer_memo.py --days 30
python tools/timescale_check.py --out docs/TIMESCALES.md --data-dir results/timescale-audit --workers 2
python tools/render_numerical_results.py --output manuscript
python -m pytest -q
.\manuscript\build.ps1
```

The gallery builder uses source/configuration fingerprints and a local `.revision_cache/gallery/` cache. `export_manuscript_data.py` consumes only that locally generated cache and its `docs/gallery/cache_manifest.json`; the compressed Python objects are build intermediates, not the published data interchange format. A full gallery build supplies all scenarios and comparison variants required by the export.

`render_manuscript_tables.py` writes the abstract and scenario/policy result sections directly from regenerated JSON. `render_numerical_results.py` writes `numerical_results.tex` and copies the independent numerical figures/data into the manuscript. These generated sections should be refreshed together after numerical changes. Review captions, surrounding interpretation, configuration provenance and the built PDF whenever results change.

The saved verification records state the tests and errors actually checked. Passing them establishes the stated implementation behaviour and numerical accuracy in the tested cases. It does not validate seawater capacities, ecological benefits or a real deployment's service policy.
