# Reuse and data decisions

Decided by the coordinator on 8 September 2026 and frozen for this sprint.
Changing an engine choice requires a coordinator decision, not a branch commit.

## Chosen stack (actually installed and tested here)

| Role | Choice | Version tested | Why |
|---|---|---|---|
| Finite-volume PDE | **FiPy** | 4.0.3 | Reuse a maintained transient/convection/diffusion solver instead of writing CFD [S06]. NIST, US — chosen to limit integration risk, not presented as European. |
| Linear algebra / ODE | NumPy 2.5.3, SciPy 1.18.1 | | FiPy's default solver suite here is SciPy; the reduced material model uses closed-form exponential steps, with `solve_ivp` available for future variants [S25]. |
| Schema validation | jsonschema 4.26.0 | | Machine-readable observation contract. |
| Presentation | Streamlit 1.63.0 + Plotly 7.0.0 | | Small local app, no cloud account [S29]. |
| Tests | pytest 9.1.1 | | |
| Optional ML | scikit-learn | | Only for the optional extension, with a simpler baseline it must beat. |

Python 3.12.13 in `.venv`. Exact resolved versions: `requirements.lock.txt`.

## Deliberately not used in this sprint

* **OpenDrift** [S07] — a Lagrangian framework from MET Norway, GPL-2.0. A later
  alternative transport adapter. Particle transport is not equivalent to
  Eulerian concentration: a future adapter must preserve particle mass and state
  its concentration/contact estimator explicitly.
* **TELEMAC** [S08] — depth-averaged hydrodynamics; a later source of resolved
  local flow. Installation and calibration are not a two-day prerequisite.
* **PHREEQC** [S05] — optional speciation, only after checking that the selected
  database and activity model actually contain the needed Pb/Hg reactions and
  saline-water parameters. A Pitzer option alone is not sufficient.

Implementing FiPy, OpenDrift and TELEMAC together in the timebox is explicitly
out of scope.

## Data adapters

The default run is **fully offline and synthetic**. No account, no token, no
tile server. Three modes exist and the app never silently promotes between them:

1. `synthetic` — small channel-like domain, prescribed current field. The
   default.
2. `real_map_illustrative` — a cached geographic basemap for context, with
   physics that remain illustrative and are labelled as such. A real map must
   never imply that this project located a real munition hotspot.
3. `imported_forcing` — currents read from a cached external product, with the
   product name, version, time, depth and native resolution preserved, and its
   resolution limits printed next to every chart.

Rules for mode 3, if it is ever enabled:

* Copernicus Marine [S09, S10] distributes both hourly and daily/de-tided
  products. A de-tided or daily-mean current field **cannot** stand in for a
  tidal reversal scenario.
* Surface currents are not automatically near-bed currents. A near-bed release
  driven by a surface product must say so.
* Interpolating a ~0.027° product onto a 10 m grid does not create metre-scale
  information. The honest resolution statement stays attached to the field.
* EMODnet Bathymetry [S11, S12] gives terrain context at its supported
  resolution. A rendered map service is not a numerical depth raster, and
  bathymetry does not itself generate currents. The app states explicitly
  whether depth enters the numerical model or is visual context only.
* Citation and licence obligations are separate questions; redistribution of a
  cached product must be checked per product [S30].

The metric computational CRS (`LOCAL_METRIC`) is kept separate from any
latitude/longitude display.

## Hardware interfaces

No hardware is required, and none is emulated as if it were a vendor's. A
read-only ingestion demonstration may use an own-protocol emulator labelled
`SIMULATED_PROTOCOL` with our own register map [S28]. A vendor's RS232 / RS422 /
RS485 signal is not an HTTP or MQTT API; any such interface would come from a
separately configured gateway. No register map, detection limit or price is
invented.
