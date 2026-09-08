# Prior art: reactive caps, reactive mats and in-situ sediment treatment

**Research snapshot: 8 September 2026.** Every claim below carries a primary-source
URL and the date it was retrieved. Where retrieval failed, that is stated instead of
being hidden. Supporting notes and full quotations are in `research/materials/`;
machine-readable records are in `research/references/prior_art.json`.

This document exists to stop the project claiming things that are not ours to claim.
It is written before the demonstration is built, not after, and rule 13 of
`AGENTS.md` depends on it.

---

## 1. The headline finding

**Reactive caps, permeable reactive barriers, activated-carbon sediment amendments and
reactive geotextile mats are established, commercially sold, field-deployed technology.**
They have been described in national regulatory guidance for decades, they have been
applied at more than twenty-five field sites across three countries as of 2013, and at
least three manufacturers sell a geotextile mat with sorbent encapsulated inside it.

The United States Environmental Protection Agency defines the object of this project in
its own guidance:

> "In a reactive cap, the isolation layer includes an amendment (such as organoclay or
> activated carbon mats) that binds or sequesters contaminants exiting the sediment pore
> water, thereby preventing contaminant release to surface water."
>
> EPA 542-F-15-009, April 2015, *Climate Change Adaptation Technical Fact Sheet:
> Contaminated Sediment Remedies*, page 1.
> <https://www.epa.gov/sites/default/files/2018-08/documents/contaminated_sediments.pdf>
> (retrieved 2026-09-08)

The phrase "activated carbon mats" appears in that definition. The concept is not new,
and the mat form is not new.

---

## 2. No novelty may be claimed for any of the following

Each item is followed by the evidence that retires it.

### 2.0 The name "Reactive Core Mat" is taken, and it is taken by exactly this

**Decided, 8 September 2026: we do not use that name.** This project is called a
**selective reactive seabed mat**, which is a plain description of what it is:
a mat, laid on the seabed, whose core is reactive, and whose selectivity is the
hypothesis under test. The package identifier `reactive_seabed_mat` and the
repository name follow from it. The name is deliberately generic, and being
generic is the point: it describes a class of thing rather than claiming a
product.

REACTIVE CORE MAT is CETCO's product name for "a patented permeable composite
mat that encapsulates active material(s) between two layers of adhered,
non-woven carrier geotextiles". That is not merely a similar idea to the
geotextile / reactive core / geotextile construction this project has adopted:
it is a word-for-word description of it, sold under that name since at least
2017, and covered by a patent family that includes US 6,284,681 B1,
US 2002/0151241 A1, US 7,670,082, US 8,042,696 ("Contaminant-reactive
geocomposite mat"), US 8,262,318 and US 11,998,891 ("Geotextile sediment cap
with active media"). Retrieved 2026-09-08.

Two separate consequences, and they should not be confused with each other:

1. **The architecture is fine to use, and using it is a strength.** It is proven,
   manufacturable and field-deployed. This project has never claimed novelty for
   it and section 6 says so explicitly.
2. **The name is not fine to adopt.** Publishing a project called "Reactive Core
   Mat" would put a third party's product name on our work, and a jury or a
   patent attorney would notice before we did.

This repository therefore describes the construction generically, as a
*geotextile-encapsulated reactive core*, and never as a Reactive Core Mat. Every
occurrence of that phrase in this repository attributes it to CETCO, and a test
would be the right way to keep it that way if the name ever starts drifting into
our own prose.

**What would actually be ours, if anything is:** the reactive medium. CETCO's
product carries organoclay, HUESKER's carries a cation adsorber or zeolite.
Neither is a keratin biosorbent, and a waste-derived, sulfur-bearing protein core
is a genuinely different filling for a well-known envelope. That is a materials
claim, it is unproven, and section 6 lists what would have to be measured before
it could be made.

### 2.1 Putting sorbent in a mat

CETCO (Minerals Technologies Inc.) sells **REACTIVE CORE MAT with ORGANOCLAY**, described
on its own technical data sheet as "a permeable composite of geotextiles and granular
Organoclay". The sheet is dated May 2017 and gives measured physical properties:

| Property | Value | Test method |
|---|---|---|
| Organoclay mass per area | 0.8 lb/ft^2 (about 3.9 kg/m^2) | CETCO test method |
| Hydraulic conductivity | 1 x 10^-3 cm/s minimum (1 x 10^-5 m/s) | ASTM D4491 |
| Mat grab strength | 90 lbs MARV | ASTM D4632 |
| Packaging | 15 ft by 100 ft rolls (about 139 m^2) | - |

Stated application: "In situ subaqueous cap for contaminated sediments or post-dredge
residual sediments". Stated benefit: "Reactive cap allows for thinner cap thickness than
a traditional sand cap".
<https://www.mineralstech.com/docs/default-source/performance-materials-documents/cetco/water-and-remediation/technical-data-sheets/tds---reactive-core-mat-with-organoclay.pdf?sfvrsn=876d65e2_9>
(retrieved 2026-09-08)

**This matters numerically for us.** `config.py` assumes a 10 mm layer at a bulk density
of 400 kg/m^3, which is 4.0 kg/m^2 of reactive medium. A product sold since at least 2017
carries about 3.9 kg/m^2. Our "thin mat" is not thinner than the commercial state of the
art; it is the same areal loading.

### 2.2 A geotextile reactive cap

HUESKER sells the **Tektoseal Active** family of "multi-layer composite materials that
feature two outer woven or nonwoven geotextile layers and an internal active layer",
in variants for organic pollutants, oils and petrochemicals, PFAS and heavy metals. The
heavy-metals variant uses a cation adsorber, or zeolite for lightly contaminated cases,
and the listed applications include "Isolation of contaminated sediments" including
underwater applications. The page states a laboratory binding capacity of "more than
200,000 mg of metals and radionuclides per m^2".
<https://www.huesker.us/geosynthetics/products/composites/tektoseal-active-product-family/tektoseal-active-for-heavy-metals/>
(retrieved 2026-09-08)

**This matters numerically for us too, in the other direction.** 200,000 mg/m^2 is
0.2 kg/m^2. Our demonstration assumes an operating capacity of 2.4 x 10^-3 kg/m^2 for Pb
(4.0 kg/m^2 of medium, allocation 0.6, `q_max` 1e-3 kg/kg). Our assumed capacity is
roughly a hundred times smaller than a commercial laboratory claim. That is deliberate:
a low assumed capacity is what makes breakthrough visible inside a six-year demonstration.
It must never be presented as a product specification, and the comparison must never be
inverted into a performance claim.

The retrieved page belongs to HUESKER Inc. (Charlotte, North Carolina). The page states
that group headquarters are in Germany. The German parent entity page was not retrieved,
so "HUESKER Synthetic GmbH, Germany" is recorded here as reported by the US subsidiary
and not as independently verified.

### 2.3 Activated carbon in sediment remediation

Patmont et al. (2015) report:

> "Through 2013, however, more than 25 field-scale demonstrations or full-scale projects
> spanning a range of environmental conditions were completed or underway in the United
> States, Norway, and the Netherlands."
>
> Patmont, C.R. et al. (2015), *In situ sediment treatment using activated carbon: a
> demonstrated sediment cleanup technology*, Integrated Environmental Assessment and
> Management 11(2):195-207.
> <https://pmc.ncbi.nlm.nih.gov/articles/PMC4409844/> (retrieved 2026-09-08)

The same paper names the proprietary delivery products already on the market, including
SediMite and AquaGate. AquaBlok Ltd. (Swanton, Ohio) currently lists **AquaGate+** with
amendments including powdered activated carbon, organoclay, clinoptilolite, zero-valent
iron, manganese oxides, iron oxide, sulfur compounds, attapulgite, REMBIND and, notably,
"Methylation Inhibitors".
<https://www.aquablok.com/remediation/products/aquagate> (retrieved 2026-09-08)

Large-scale European field application exists. In the Grenland fjords, Norway, activated
carbon mixed with clay at a 1:10 dry-weight ratio was applied over "three test fields
(100 x 100 m)" at 30 m depth and "one test field (200 x 200 m)" at 95 m depth, achieving
cap thicknesses of "11 +/- 6 and 12 +/- 3 mm" after one month.
Samuelsson, G.S. et al. (2017), Environmental Science and Pollution Research
24(16):14218-14233, <https://pmc.ncbi.nlm.nih.gov/articles/PMC5486621/>
(retrieved 2026-09-08)

### 2.4 Monitoring a remediation site

Long-term monitoring of sediment caps is a documented practice with its own guidance and
its own instrument set: bathymetry, cap coring, porewater sampling, passive samplers and
surface-water sampling. Reible (2012) describes profiling passive samplers inserted into
the sediment "in a shielded rod and allowed to equilibrate for 7-28 days", giving
concentration profiles "with up to 1 cm resolution", and lists the cap conditions that
such profiling can distinguish, including intermixing, recontamination from above, and
"diffusive like processes such as tidally controlled upwelling".
Reible, D., *In-situ management of contaminated sediments: capping and in-situ
treatment*, NORDROCS, 2012.
<https://nordrocs.org/wp-content/uploads/2012/09/Session-I-onsdag-1-Reible-short-paper.pdf>
(retrieved 2026-09-08)

### 2.5 Modelling a cap with advection, diffusion and sorption

The governing equations in `docs/MODEL_SPEC.md` section 3 are the standard ones. Analytical
and numerical cap models predating this project include Lampert and Reible (2009),
*An analytical modeling approach for evaluation of capping of contaminated sediments*,
Soil and Sediment Contamination 18:470-488, and CAPSIM (Reible and Lampert, 2012), both
cited in the NORDROCS paper above. Bessinger et al. (2012) published a reactive-transport
cap model specifically for arsenic, mercury and methylmercury.
<https://pmc.ncbi.nlm.nih.gov/articles/PMC4802735/> (retrieved 2026-09-08)

We are re-implementing a known model class. The implementation, the degradation
bookkeeping and the honesty discipline are ours; the physics is not.

### 2.6 Sensor-informed state estimation for contaminated sediment

A 2026 systematic review in *Science of the Total Environment* covers "Intelligent
sediment-groundwater digital twin: A systematic review, meta-analysis, and reference
architecture for reliable metal pollution risk assessment" (PII S0048969726006170,
PMID 42361392). The publisher page returned HTTP 403 and the PubMed page returned only a
cookie notice on 2026-09-08, so only the existence and identity of the review are
verified here, not its contents. Data assimilation applied to contaminant fate models is
an active, published field. We may not present it as new.

---

## 3. A finding that constrains the concept directly

Reible (2012) ranks the options, and the thin mat is the middle one:

> "In general, strong sorbents mixed throughout a cap layer provides the best performance
> in sediment remedies. Less effective, although still quite effective is a layer of
> sorbent mixed within a thin layer (e.g. in a reactive core mat) as part of the cap.
> Least effective, although still providing substantial risk reduction is sorbent
> amendments mixed within a sediment layer as an in-situ treatment."

A thin reactive mat is therefore already known to be less effective than a thick
sorbent-amended cap. Any argument for the mat must be made on retrievability,
modularity, material quantity and servicing, not on peak attenuation. The refactor plan
already says the same thing in its own words, and the two agree.

Two further field findings sharpen the point:

* **Amendment loss is real and large.** In the Grenland fjords application, "AC particles
  did not settle as expected and up to 75% were lost to surrounding areas due to lateral
  advection". Raymond, C. et al. (2020), Environmental Science and Pollution Research
  28(13):16181-16197, <https://pmc.ncbi.nlm.nih.gov/articles/PMC7969561/>
  (retrieved 2026-09-08). This is degradation mode 3 in `MODEL_SPEC` section 4,
  observed in the field at a scale of hundreds of metres.
* **Fouling of the sorbent is real and measurable.** Reible (2012) reports that for
  PCB congener 52 at a site with about 14 mg/L dissolved organic carbon, "The AC sorption
  in site waters was reduced approximately 1/2 order of magnitude by site related fouling
  while OC was essentially unaffected." That is degradation mode 2, and it is
  sorbent-specific.

---

## 4. Capping and mercury methylation: a risk, not a benefit

The literature is **not** unanimous, and the demonstrator must represent both directions.

**Capping can increase methylmercury.** Johnson, N.W., Reible, D.D. and Katz, L.E. (2010),
*Biogeochemical Changes and Mercury Methylation beneath an In-Situ Sediment Cap*,
Environmental Science and Technology 44(19):7280-7286, DOI 10.1021/es100161p. The
publisher page returned HTTP 403 on 2026-09-08 and the University of Texas repository
record also returned HTTP 403, so the following is recorded from search-index summaries
and is **not verbatim-verified**: increased methylmercury of up to about 50 per cent was
observed beneath a sediment cap in a zone 2 to 3 cm higher than in uncapped sediment,
concurrent with an upward extension of anaerobic bacterial activity. Treat the
mechanism as established and the numbers as unverified until the article is obtained.

**Sorbent amendment can decrease porewater methylmercury.** Gilmour, C.C. et al. (2013),
*Activated Carbon Mitigates Mercury and Methylmercury Bioavailability in Contaminated
Sediments*, Environmental Science and Technology 47(22), DOI 10.1021/es4021074. Activated
carbon and a thiol-functionalised mesoporous silica added at 2 to 7 per cent of sediment
dry weight reduced porewater methylmercury by 45 to 95 per cent relative to unamended
controls. Publisher page not retrieved directly; recorded from the PubMed and Semantic
Scholar index entries on 2026-09-08.

**Modelling predicts methylation inside the cap itself.** Bessinger et al. (2012):
"Methylmercury formation is predicted to occur within the upper 0.15 m of the cap in both
estuarine and freshwater scenarios."
<https://pmc.ncbi.nlm.nih.gov/articles/PMC4802735/> (retrieved 2026-09-08)

**Ecological harm from the amendment itself is documented.** In the Grenland fjords the
activated-carbon cap "strongly reduced the benthic species diversity, abundance, and
biomass by up to 90%", "Vital functions in the benthic ecosystem such as particle
reworking and bioirrigation of the sediment were also reduced", and "Much of the initial
effects observed after 1 and 14 months were still present after 49 months, indicating
that the effects are long-lasting". The authors conclude: "These long-lasting negative
ecological effects should be carefully considered before decisions are made on sediment
remediation with powdered AC, especially in large areas, since important ecosystem
functions can be impaired."
Raymond, C. et al. (2020), <https://pmc.ncbi.nlm.nih.gov/articles/PMC7969561/>
(retrieved 2026-09-08)

**Consequence for this repository.** `MODEL_SPEC` section 11 is correct to treat
methylmercury as a wide-interval risk term and an ecological constraint in the
optimisation, never as a benefit. Beyond methylmercury, the benthic-community effect
above means the mat must also be judged on what it does to the seabed it covers. That is
a second ecological constraint, and it is currently not modelled at all. It is recorded
here as an open gap rather than quietly ignored.

---

## 5. Regulatory context

Placing a mat on the seabed in the North-East Atlantic is a regulated act. OSPAR
Convention Annex II, Article 5:

> "No placement of matter in the maritime area for a purpose other than that for which it
> was originally designed or constructed shall take place without authorisation or
> regulation by the competent authority of the relevant Contracting Party."

<https://www.ospar.org/convention/text> (retrieved 2026-09-08)

The EU LIFE SEDREMED project (LIFE20 ENV/IT/000572) records that "the current legal
frameworks are fragmented across the EU, and Member States address the challenges with
diverging approaches", that no EU-wide sediment-specific environmental quality standards
exist, and that experts agreed dredging and capping "is expensive and cannot be applied
everywhere".
<https://life-sedremed.eu/technological-and-policy-solutions-for-the-management-of-contaminated-sediments-in-the-eu/>
(retrieved 2026-09-08)

The demonstrator's hotspot is an abstract authorised area for exactly this reason
(`AGENTS.md` rule 14). Nothing here simulates, locates or recommends the handling of
munitions.

---

## 6. Possible differentiation: a HYPOTHESIS LIST, explicitly unproven

None of the following is a result. Each is a hypothesis, with the state of evidence and
what would be needed to test it. None of them is demonstrated by this repository, and the
simulation cannot demonstrate any of them because the simulation assumes them.

| # | Hypothesis | Current evidence | Status | What would test it |
|---|---|---|---|---|
| H1 | Selective Pb and Hg chemistry that works in saline conditions | Thiol- and sulfur-functionalised sorbents show high Hg selectivity in laboratory water, usually at pH 5 to 6.5 and in low-chloride matrices. Hg uptake by activated carbon is known to depend strongly on sulfide, chloride and dissolved organic matter [S04]. Alginate-based Pb sorption in seawater is reported for one specific polyurea-crosslinked material [S01]. | **UNPROVEN in seawater at pH 8 with about 0.5 M chloride** | Isotherms and kinetics in real site porewater and real seawater, with competing ions and DOM present, using the actual candidate medium |
| H2 | Bio-derived or low-impact active material | Biochar, chitosan and alginate sorbents for Pb and Hg are widely published, almost always in fresh or waste water. [S01] is a polyurea-crosslinked alginate, which is substantially synthetic polymer and is not evidence of biodegradability. | **UNPROVEN**, and "bio-derived" must not be read as "low impact": the Grenland fjords result shows a bio-derived carbon amendment causing up to 90 per cent loss of benthic abundance | Life-cycle and ecotoxicity testing of the actual medium, plus a benthic-recolonisation study |
| H3 | Thin, retrievable, modular architecture | Thin reactive mats exist commercially (section 2.1). Retrieval and replacement of a laid subaqueous mat is not documented in any source retrieved here. Reible (2012) ranks the thin-mat form below a thick amended cap on performance. | **PARTLY NOVEL AT BEST.** The thin mat is prior art; the *retrieval and re-lay* operation is the part with no evidence either way | A physical retrieval trial: lifting forces, sediment disturbance during lifting, resuspension release, and whether the retrieved medium can be handled as a waste stream |
| H4 | Application to localised release associated with historical marine munitions | Munition-related metal release to sediment is documented [S02, S03]. No source retrieved here applies a reactive cap to such a site. | **UNPROVEN**, and out of scope for any hands-on work: rule 14 forbids ordnance handling anywhere in this repository | Would require specialist and environmental approval and is not a software question |
| H5 | Site-specific simulation | Cap models with advection, diffusion and sorption predate this project (section 2.5). | **NOT NOVEL.** The contribution, if any, is the coupling of a per-tile layer model to a 2-D coastal source term with a per-element ledger | Comparison against CAPSIM or an equivalent published model on the same case |
| H6 | Sensor-informed state estimation | Data assimilation for sediment and groundwater contamination is a reviewed field as of 2026 (section 2.6). | **NOT NOVEL as a class.** What is arguably specific here is estimating four degradation modes side by side and refusing to collapse them into saturation | A field data set with independent ground truth on which the estimator can be scored |
| H7 | Predictive maintenance | Cap monitoring and maintenance guidance exists. Evidence-triggered partial replacement of mat tiles is not documented in any source retrieved here. | **UNPROVEN**, and untestable in simulation because the simulator supplies the truth the policy is scored against | A multi-year instrumented pilot with a real replacement decision and its outcome |
| H8 | Optimisation of material quantity and servicing | Cap thickness design is standard practice. Joint optimisation over footprint, thickness, loading, layout and service interval under an explicit methylmercury and ecological constraint was not found in the sources retrieved. | **UNPROVEN**, and the optimum is only as credible as the assumed capacity, which is a synthetic number | Calibrated capacity and fouling parameters from real media, plus real cost data |

### The one-sentence version for any slide or abstract

Reactive caps, activated-carbon amendments and reactive geotextile mats already exist and
are commercially deployed; this project claims no novelty for any of them, and its
possible differentiation is a list of unproven hypotheses about selectivity in seawater,
retrievability, and evidence-driven servicing.

---

## 7. What this repository must never say

* That a reactive mat, a sorbent mat or a geotextile cap is new.
* That activated carbon in sediment remediation is new.
* That monitoring a remediation site is new.
* That any attenuation, capacity or breakthrough number produced by the demonstrator is a
  product specification. Every one of them is an assumption chosen to make a
  demonstration legible (`config.py`, `docs/ASSUMPTIONS.md`).
* That capping is ecologically safe. The retrieved evidence includes a documented 90 per
  cent reduction in benthic abundance and biomass persisting for four years, and a
  documented mechanism by which capping raises methylmercury.
* That a euro value in this repository is a price. No supplier has been contacted and no
  quotation exists.
