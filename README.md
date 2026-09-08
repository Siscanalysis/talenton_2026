# Marine reactive-mesh demonstrator

A small, offline, science-grounded **presentation demo** of a sensor-informed
retrievable reactive mesh: a hypothetical Pb (and optional Hg) source in moving
water, a finite-capacity mesh that loads, fouls and gets replaced, an
observation stream with censoring and laboratory delay, and an uncertainty-aware
maintenance recommendation.

**This is not a field-validated remediation system.** It is a conceptual
research demonstrator. See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) before
quoting any number from it.

---

## Install and run

```powershell
# Windows PowerShell, from this directory
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.lock.txt
uv pip install --python .venv\Scripts\python.exe -e . --no-deps

# tests
.venv\Scripts\python.exe -m pytest -q

# the five demonstration scenes plus the poor-performance case, offline
.venv\Scripts\python.exe -m mesh_demo.cli run-all --out results

# the local app (no account, no tile server, no network)
.venv\Scripts\streamlit.exe run app/streamlit_app.py
```

Exact commands, timings and the five-minute narration are in
[`docs/presentation/DEMO_SCRIPT.md`](docs/presentation/DEMO_SCRIPT.md).

## What is in here

| Path | Contents |
|---|---|
| `contracts/` | The shared data contract and the observation JSON schema |
| `docs/MODEL_SPEC.md` | Every equation, bound and acceptance rule |
| `docs/REUSE_AND_DATA.md` | Which solver stack was chosen, and what was deliberately not used |
| `docs/REFERENCES.md` | Reference register S01–S30, U01 |
| `docs/research/` | European supplier / interface evidence matrix |
| `src/mesh_demo/` | The model: `micro/`, `transport/`, `observations/`, `feedback/`, `reporting/`, `scenarios/` |
| `app/` | The Streamlit presentation app |
| `tests/` | Contract, micro, transport, feedback, presentation and integration tests |
| `results/` | Generated run outputs (git-ignored) |

## The rules the code is built to keep

Hidden simulated truth, measurements and estimates are separate stores. A
result cannot influence a decision before `available_at_utc`. A non-detect is a
bound, not a zero; a missing value is not a non-detect. Pb and Hg are never
inferred from turbidity, conductivity or pH. Mass is conserved per element
across water, active mesh, retrieved media and boundary export, and no
recommendation ever actuates anything.

Full list: [`AGENTS.md`](AGENTS.md).

## Status

Working demonstrator. Every material parameter, schedule and euro value is a
labelled assumption; no supplier has been contacted and no quotation exists.
