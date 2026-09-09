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
| Seawater metal-flux validation for the proposed keratin core | **Not identified in this review.** See GAP1 and GAP2. |

## Getting each one

### D1. ICES DOME
The main European holding of contaminants in biota, sediment and seawater, from
the OSPAR CEMP and HELCOM COMBINE programmes.

* Portal: <https://www.ices.dk/data/data-portals/Pages/DOME.aspx>
* Filter by year, purpose, country, monitoring programme, laboratory and area,
  accept the data policy, then download CSV. Download and functional web
  services also exist.
* Licence: CC BY 4.0 for all public data.

DOME includes multiple matrices. A sediment *solid-phase* concentration cannot
be used as *porewater* concentration without a measured or fitted partition
relationship and uncertainty. Do not read sediment mg/kg as porewater ug/L.

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
reference, because it illustrates chamber exposure and reporting conventions. The
synthetic metal chamber is not calibrated to that phosphorus dataset.

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

## Gaps in the assembled evidence

Updated 9 September 2026 after inspecting the supplied keratin papers. The
[page-level traceability audit](../../docs/PAPER_PARAMETER_TRACEABILITY.md)
records the revised material evidence and limits of parameter transfer.

### GAP1. Metal-flux validation for the proposed seawater core

The assembled sources do not provide an openly accessible dataset validating
Pb/Hg/Cu flux attenuation through the final wool/feather core under representative
seawater flow. Organic-contaminant flux attenuation in a Norwegian harbour and
Pb flux in a laboratory carbon-nanotube capping study are documented comparators,
not calibration of this material. This review does not establish that no marine
metal-cap measurements exist anywhere.

The original search covered benthic flux chamber metal flux capping, reactive
cap flux attenuation metals, EMODnet and ICES holdings, Zenodo and Mendeley Data
on 8 September 2026. The supplied-paper audit adds the literature inspected on
9 September 2026; it is not a download of those monitoring datasets.

### GAP2. Final-material seawater isotherms and flow-through uptake

The earlier claim that every keratin experiment used acidic deionised water,
and that no keratin Hg capacity had been verified, is superseded. The supplied
feather-keratin/graphene-oxide study used pH 7.5 solution with NaCl and CaCl2 for
a dilute Pb removal assay. A primary paper identified through the 2026 review
reports Hg uptake on chemically reduced human hair. Treated sheep wool has
quantified Cu isotherms at pH 5. Those materials and endpoints do not validate the
proposed wool/feather core's isotherms or breakthrough in representative seawater.

Published batch results are recorded in
[paper_parameter_traceability.json](../references/paper_parameter_traceability.json).
The remaining gap is the final material, matrix, concentration, flow and
uncertainty required for operational calibration; it is not an absence of all
keratin uptake measurements.

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
