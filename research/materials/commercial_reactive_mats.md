# Commercial reactive mat and composite capping products

Retrieved 2026-09-08. These are products a customer can buy today. They are the reason
`AGENTS.md` rule 13 exists.

## CETCO REACTIVE CORE MAT with ORGANOCLAY

* Manufacturer: CETCO, part of Minerals Technologies Inc. Plant location given on the
  data sheet: 92 Highway 37, Lovell, Wyoming, USA. **Not a European manufacturer**,
  although a CETCO Europe entity is listed on third-party directories that were not
  retrieved.
* Document: technical data sheet, form `TDS_RCM_ORGANOCLAY_AM_EN_201705_V2`, updated
  May 2017.
* URL: <https://www.mineralstech.com/docs/default-source/performance-materials-documents/cetco/water-and-remediation/technical-data-sheets/tds---reactive-core-mat-with-organoclay.pdf?sfvrsn=876d65e2_9>
* Retrieval: `FETCHED_PDF`, page 1 read directly.
* Note: the CETCO sediment-capping landing page
  <https://www.mineralstech.com/business-segments/performance-materials/cetco/environmental-products/products/sediment-capping-technologies>
  returned empty content on 2026-09-08 and is therefore not cited.

Verbatim from the data sheet:

> "ORGANOCLAY REACTIVE CORE MAT is a permeable composite of geotextiles and granular
> Organoclay that reliably adsorbs NAPL and low solubility organics from water."

> "Reactive cap allows for thinner cap thickness than a traditional sand cap"

> "provides a reactive material that treats contaminants carried by advective/diffusive
> flow"

> "In situ subaqueous cap for contaminated sediments or post-dredge residual sediments"

> "REACTIVE CORE MAT is designed to provide a simple method of placing active materials
> into subaqueous sediment caps."

Measured physical properties, verbatim from the testing table:

| Property | Test method | Result |
|---|---|---|
| Organoclay bulk density range | ASTM D7481 | 44 to 56 lbs/ft^3 |
| Oil adsorption capacity | CETCO test method | 0.5 lb of oil per lb of Organoclay, min |
| Quaternary amine content | ASTM D7626 | 25 to 33% quaternary amine loading |
| Organoclay mass per area (finished mat) | CETCO test method | 0.8 lb/ft^2 |
| Mat grab strength | ASTM D4632 | 90 lbs. MARV |
| Hydraulic conductivity | ASTM D4491 | 1 x 10^-3 cm/sec minimum |

Packaging, verbatim: "15' by 100' rolls, packaged on 4" PVC core tubes wrapped with
polyethylene plastic packaging."

Unit conversions performed here, using the SI ladders in `src/reactive_seabed_mat/units.py`
conventions (assumption label: derived arithmetic, not a vendor statement):

* 0.8 lb/ft^2 = 0.362874 kg / 0.09290304 m^2 = **3.906 kg/m^2** of organoclay.
* 1 x 10^-3 cm/s = **1 x 10^-5 m/s** hydraulic conductivity.
* 15 ft x 100 ft = 4.572 m x 30.48 m = **139.35 m^2** per roll.
* 44 to 56 lb/ft^3 = **705 to 897 kg/m^3** granular bulk density.

Comparison with `config.py` (stated so that the demonstrator cannot be read as a leap
beyond the market): our `MatLayoutConfig` assumes `thickness_m = 0.010` and
`bulk_density_kg_per_m3 = 400`, giving 4.0 kg/m^2 of medium. The commercial mat carries
3.906 kg/m^2. The demonstrator's areal loading is the commercial state of the art, not an
advance on it. Our assumed bulk density is roughly half the granular organoclay density,
which is consistent with a mat in which the medium is dispersed in a fibre matrix rather
than packed, but it is an assumption and is labelled as one in `config.py`.

The data sheet says nothing about retrieval, replacement or servicing of a laid mat.
Absence of a statement is not evidence that it cannot be done, and it is not evidence
that it can.

## HUESKER Tektoseal Active

* Manufacturer group: HUESKER. Page retrieved belongs to HUESKER Inc., Charlotte, North
  Carolina, USA; the page states group headquarters are in Germany. The German parent
  page was not retrieved, so the German attribution is **reported, not verified**.
* URLs retrieved (`FETCHED_OK`):
  * <https://www.huesker.us/geosynthetics/products/composites/tektoseal-active-product-family/tektoseal-active-for-organic-pollutants/>
  * <https://www.huesker.us/geosynthetics/products/composites/tektoseal-active-product-family/tektoseal-active-for-heavy-metals/>

Family variants named on the site: Tektoseal Active for PFAS, for Heavy Metals, for
Organic Pollutants, for Oils and Petrochemicals.

Construction: "multi-layer composite materials that feature two outer woven or nonwoven
geotextile layers and an internal active layer" (this phrasing appears in third-party
trade coverage and is consistent with the manufacturer pages; treat as reported).

Active materials named on the manufacturer pages:

* Organic pollutants variant: "High-performance textiles combined with special activated
  carbon"; also organoclay, described as "Chemical treatment of the base material
  bentonite makes it an oliophilic pollutant adsorber".
* Heavy-metals variant: a cation adsorber as the primary active substance, with zeolite
  offered for lightly contaminated applications.

Stated applications include "Securing of contaminated soils on land and sediments under
water" and, on the heavy-metals page, isolation of contaminated sediments including
underwater applications.

Capacity claim, heavy-metals variant: the page states the material can bind "more than
200,000 mg of metals and radionuclides per m^2", attributed to laboratory studies.

Conversion: 200,000 mg/m^2 = **0.2 kg/m^2**.

Comparison with `config.py`: our Pb capacity is
`4.0 kg/m^2 * allocation 0.6 * q_max 1e-3 kg/kg = 2.4e-3 kg/m^2`; our Hg capacity is
`4.0 * 0.4 * 4e-4 = 6.4e-4 kg/m^2`. The commercial laboratory claim is about 83 times our
Pb assumption and about 310 times our Hg assumption. Our numbers are deliberately small so
that breakthrough happens inside a six-year demonstration. **This must never be reported
as a comparison in our favour.**

A third-party trade page also mentions a variant "Tektoseal Active AC 3400" said to
contain 3400 g/m^2 of activated carbon. That page was not retrieved and the number is
recorded here as `SEARCH_INDEX_ONLY` and unverified.

## AquaBlok AquaGate+

* Manufacturer: AquaBlok, Ltd., Swanton, Ohio, USA. Not European.
* URL: <https://www.aquablok.com/remediation/products/aquagate>
* Retrieval: `FETCHED_OK`.

Verbatim: "AquaGate+ delivers powdered amendments in a thin coating around an inner core,
allowing movement of water through the matrix for treatment, while limiting the migration
of contaminants."

Amendments listed on the page: powdered activated carbon, organoclay, clinoptilolite,
zero-valent iron, manganese oxides, iron oxide, sulfur compounds, organic carbon,
microbes, attapulgite, aluminium sulfate, EHC-M, PROVECT-IRM, REMBIND, and "Methylation
Inhibitors". The page adds: "AquaGate+ products are not limited to the use of the above
examples. Other amendments may be available to address your project."

Two points matter for us. First, a granular composite is a competing delivery form to a
mat and is already sold with the same amendments. Second, a commercial vendor already
sells a methylation-inhibitor amendment, which confirms that methylmercury under a cap is
a recognised industry problem rather than a theoretical concern raised only here.
