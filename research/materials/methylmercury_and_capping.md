# Capping, mercury methylation and ecological safety

Retrieved 2026-09-08. This note backs `docs/MODEL_SPEC.md` section 11 and hypothesis H2
in `docs/PRIOR_ART.md`.

The short version: **the literature points both ways, and the honest position is that
methylmercury is a validation constraint requiring site-specific measurement, never an
automatic benefit of capping.**

## Evidence that capping can increase methylmercury

* Johnson, N.W., Reible, D.D. and Katz, L.E. (2010), *Biogeochemical Changes and Mercury
  Methylation beneath an In-Situ Sediment Cap*, Environmental Science and Technology
  44(19):7280-7286, DOI 10.1021/es100161p.
* URLs attempted: <https://pubs.acs.org/doi/abs/10.1021/es100161p> (`FETCH_403`) and
  <https://repositories.lib.utexas.edu/items/b7756134-4ae5-4b7a-95a3-abd4991261e4>
  (`FETCH_403`).
* Retrieval: `SEARCH_INDEX_ONLY`. The bibliographic record is verified. The following is
  a search-index paraphrase and is **not verbatim**:
  * anoxic laboratory microcosms of estuarine sediment,
  * increased methylmercury of up to about 50 per cent beneath a sediment cap,
  * in a zone 2 to 3 cm higher than in uncapped sediment,
  * concurrent with an upward extension of anaerobic bacterial activity beneath the cap.

Use in this repository: cite the mechanism (a cap shifts the redox boundary upward and can
extend the methylating zone), and mark the percentage and the depth shift as unverified
until the article is obtained. Do not put these numbers on a chart.

## Evidence that sorbent amendment can decrease porewater methylmercury

* Gilmour, C.C., Riedel, G.S., Riedel, G., Kwon, S., Landis, R., Brown, S.S.,
  Menzie, C.A. and Ghosh, U. (2013), *Activated Carbon Mitigates Mercury and
  Methylmercury Bioavailability in Contaminated Sediments*, Environmental Science and
  Technology 47(22), DOI 10.1021/es4021074.
* URLs: <https://pubs.acs.org/doi/abs/10.1021/es4021074>,
  <https://pubmed.ncbi.nlm.nih.gov/24156748/>.
* Retrieval: `SEARCH_INDEX_ONLY`. Paraphrase, **not verbatim**: four amendments were
  tested in 2 L sediment and water microcosms with 14-day bioaccumulation assays, using
  Hg-contaminated sediment from two freshwater and two estuarine sites. The amendments
  were an activated carbon, CETCO Organoclay MRM, Thiol-SAMMS (a thiol-functionalised
  mesoporous silica) and AMBERSEP GT74 (an ion-exchange resin). Activated carbon and
  Thiol-SAMMS, added at 2 to 7 per cent of sediment dry weight, reduced porewater
  methylmercury by 45 to 95 per cent relative to unamended controls.

Two observations that matter. First, this is amendment mixed **into** sediment, not a mat
laid **on** it, so the geometry differs from ours. Second, the doses are 2 to 7 per cent
of sediment dry weight, which is a bulk treatment of the biologically active layer, not a
thin overlying layer.

## Evidence from modelling

* Bessinger et al. (2012), Aquatic Geochemistry 18(4):297-326,
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC4802735/> (`FETCHED_OK`).

Verbatim: "Methylmercury formation is predicted to occur within the upper 0.15 m of the
cap in both estuarine and freshwater scenarios." And: "Mercury and methylmercury
concentrations are predicted to remain below water and sediment quality criteria levels in
both estuarine and freshwater systems once sulfide concentrations increase after the first
5-10 years because of precipitation of insoluble mercury sulfide."

Note the timescale in the second quotation. The favourable outcome is predicted to arrive
after five to ten years of sulfide build-up. Our demonstrator runs for one to six years,
which sits entirely inside the unfavourable window.

## Commercial recognition of the problem

AquaBlok lists "Methylation Inhibitors" among the amendments deliverable by AquaGate+
(<https://www.aquablok.com/remediation/products/aquagate>, `FETCHED_OK`). A vendor selling
a methylation inhibitor is evidence that methylmercury generation under an amendment is a
recognised operational problem, not a hypothetical objection.

## The wider ecological constraint

Methylmercury is not the only ecological risk, and in the retrieved European field
evidence it is not the largest one. Raymond et al. (2020) report that thin-layer capping
with powdered activated carbon "strongly reduced the benthic species diversity, abundance,
and biomass by up to 90%", that "particle reworking and bioirrigation of the sediment were
also reduced", and that the effects persisted to 49 months
(<https://pmc.ncbi.nlm.nih.gov/articles/PMC7969561/>, `FETCHED_OK`).

## What this means for the repository

1. `MODEL_SPEC` section 11 is correctly framed: methylmercury is a wide-interval risk
   term and a constraint in the optimisation, never a benefit.
2. The risk term should be driven by redox and sulfide under the mat, and its interval
   should stay wide because the primary quantitative evidence is unverified and points in
   both directions.
3. **A second ecological constraint is missing.** Nothing in the current contracts
   represents smothering of benthic fauna by the mat itself, and the strongest retrieved
   field evidence is precisely about that. This is a contract-level gap, recorded in
   `docs/handoffs/research_sensors.md` as a request rather than acted on here.
4. Any claim about ecological safety, in either direction, requires site-specific
   measurement of methylmercury and of benthic community metrics. Neither is obtainable
   from the physical and chemical sensor set in `research/sensors/sensor_matrix.md`.
