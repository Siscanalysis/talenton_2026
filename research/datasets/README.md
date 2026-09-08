# Datasets: what exists, how to get it, and what is missing

Machine-readable index: [`../references/datasets.json`](../references/datasets.json).
Narrative version with the numbers: [`../../docs/EVIDENCE_BASE.md`](../../docs/EVIDENCE_BASE.md).

**Nothing here is bundled with the repository.** The default run is offline and
synthetic by design, redistribution terms differ per product, and a cached copy
of a monitoring product goes stale silently. These are pointers, with enough
detail that a reviewer can check any number this project quotes.

## Why these and not others

The model needs four kinds of measurement, and they are not equally available:

| What the model needs | Availability |
|---|---|
| Contaminant concentrations in European marine sediment and water | **Good.** D1, D2, D4, D5 below. |
| Benthic flux measurement method and data structure | **Good.** D6, D8. |
| Reactive-cap performance for organic contaminants | **Adequate.** Published field trials, see `docs/EVIDENCE_BASE.md` references E1 and E2. |
| **Reactive-cap flux attenuation for metals, in the sea** | **Missing.** See GAP1. |

## Getting each one

### D1. ICES DOME
The main European holding of contaminants in biota, sediment and seawater, from
the OSPAR CEMP and HELCOM COMBINE programmes.

* Portal: <https://www.ices.dk/data/data-portals/Pages/DOME.aspx>
* Filter by year, purpose, country, monitoring programme, laboratory and area,
  accept the data policy, then download CSV. Download and functional web
  services also exist.
* Licence: CC BY 4.0 for all public data.

**Careful with this one.** DOME gives sediment *solid-phase* concentrations. The
model needs *porewater* concentrations, and converting between them requires a
partition coefficient that is itself a fitted quantity with its own uncertainty.
Do not read a sediment mg/kg as a porewater ug/L.

### D2. OSPAR CEMP assessment, 2024
Quality-controlled assessed levels and trends.

* <https://ices-library.figshare.com/articles/dataset/Data_and_results_for_the_2024_OSPAR_CEMP_assessment/27211422>
* Interactive equivalent: the OSPAR Hazardous Substances Assessment Tool,
  <https://dome.ices.dk/ohat/>

### D3. OSPAR ODIMS
<https://odims.ospar.org/en/datastreams/>

### D4. EMODnet Chemistry
Aggregated and validated European seas products, covering 12 MSFD-prioritised
pollutants including Pb and Hg in seawater, sediment and biota.

* <https://emodnet.ec.europa.eu/en/chemistry>
* Method paper: Frontiers in Marine Science 7:583657, DOI 10.3389/fmars.2020.583657

### D5. HELCOM metals core indicator
Baltic status and trends for Pb, Cd and Hg.

* <https://indicators.helcom.fi/indicator/mercury/>
* 2018 indicator report: <https://helcom.fi/wp-content/uploads/2019/08/Metals-HELCOM-core-indicator-2018.pdf>

The Baltic is where marine munitions contamination is best documented. That is
context, not a location claim: this project asserts no hotspot anywhere.

### D6. Baltic in-situ benthic fluxes (Hylen et al.)
498 fluxes from three types of benthic chamber lander, 59 stations, 20 years.

* Zenodo, DOI [10.5281/zenodo.17465937](https://doi.org/10.5281/zenodo.17465937)
* CC BY 4.0, `.xlsx`

**Phosphorus only.** It contains no trace metal fluxes and must not be cited as
a metals source. It is here as a chamber-lander method and data-structure
reference, because the demonstrator's `benthic_chamber` acquisition kind
imitates exactly this measurement.

### D7. US EPA, amendments at Superfund sediment sites
<https://semspub.epa.gov/work/HQ/196704.pdf>

The performance and regulatory record for activated-carbon amendment and
reactive capping. This is the document that makes clear why this project claims
no novelty for the basic idea.

### D8. USGS SIR 2004-5298, benthic flux chamber
<https://pubs.usgs.gov/sir/2004/5298/pdf/SIR2004-5298.pdf>

What a chamber does and does not measure. It is the basis for this repository
refusing to treat a few hours over a small enclosed area as a whole-footprint
annual flux.

## The gaps, stated as findings

### GAP1. Measured metal flux attenuation across a marine reactive cap
No open dataset was found. This is the quantity the demonstrator predicts. The
closest available evidence is organic-contaminant flux attenuation in a
Norwegian harbour field trial and Pb flux in a laboratory mesocosm with a carbon
nanotube cap, both cited in `docs/EVIDENCE_BASE.md`.

Searched: benthic flux chamber metal flux capping; reactive cap flux attenuation
metals; EMODnet and ICES holdings; Zenodo; Mendeley Data. Checked 8 September
2026.

### GAP2. Keratin biosorption in seawater
Every published keratin capacity found is deionised water at acidic pH, and no
verified keratin mercury capacity of any kind was found. This is the single
largest uncertainty in the model, and `docs/MATERIAL_KERATIN.md` section 3
records it as UNKNOWN rather than filling it from a different material.

Searched: Zenodo, Mendeley Data, CORE, AGRIS, and the keratin biosorption review
literature.

## If you add a dataset here

Add a row to `../references/datasets.json` with an `access_date` and an honest
`retrieval_status`. The vocabulary in use:

* `RECORD_FETCHED_OK`: the record page was retrieved and read.
* `PORTAL_CONFIRMED_NOT_DOWNLOADED`: the portal exists and was checked; the data
  itself was not pulled.
* `LISTING_CONFIRMED_NOT_DOWNLOADED`: the document was found in an index; the
  full text was not retrieved.
* `SEARCHED_NOT_FOUND`: looked for, not found. Record what was searched.

A status is not decoration. If a number enters the model from a source whose
full text was not read, the row must say so, and `docs/EVIDENCE_BASE.md` must
repeat it next to the number.
