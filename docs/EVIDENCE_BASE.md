# Evidence base: what the literature supports, and where this model departs from it

Checked 8 September 2026. Companion to `docs/MATERIAL_KERATIN.md`, which covers
the reactive medium, and to `docs/PRIOR_ART.md`, which covers what is already
established practice.

This document exists because a demonstrator that quotes numbers should say where
they came from. It has two jobs:

1. Point at the real measurements and open datasets a reviewer can check.
2. Say plainly where this model's defaults sit **outside** the measured range,
   because two of them do, and both flatter the technology.

Datasets are indexed in machine-readable form at
`research/references/datasets.json`, with access notes in
`research/datasets/README.md`.

---

## 1. The two numbers that do not sit inside the measured range

### 1.1 The modelled bare flux is at the very top of the measured envelope

The default hotspot uses porewater Pb of 1.0 mg/L and a Darcy seepage of
3.0e-8 m/s, which gives a bare-sediment advective Pb flux of

```
1.0e-3 kg/m3  x  3.0e-8 m/s  =  3.0e-11 kg/m2/s  =  2592 ug/m2/d
```

Measured benthic Pb fluxes for comparison:

| Source | Setting | Pb flux |
|---|---|---|
| Rivera-Duarte and Flegal, SF Bay [E4] | contaminated estuary, **diffusive** flux from porewater gradients | 2.6e-9 to 3.1e-8 mol/m2/d, that is **0.54 to 6.4 ug/m2/d** |
| Chen et al. 2025 [E3] | mesocosm control, no cap | **0.97 to 2.50 ug/m2/d** |

So the model's bare flux is roughly **400 to 2700 times** the measured values
above. Three things should be said about that, in order of honesty:

* **It is not a like-for-like quantity.** [E4] is a *diffusive* flux computed
  from porewater gradients. This model is advection-dominated by design: it
  represents a seeping hotspot, and at a real submarine groundwater discharge
  site advection does dominate diffusion. Chamber-measured total fluxes, which
  include advection and bioirrigation, are routinely well above
  diffusion-calculated ones.
* **Even so, it is at the extreme.** 1.0 mg/L of dissolved Pb in porewater is a
  very high value. It is chosen so that a multi-year simulation shows loading,
  breakthrough and replacement inside a demonstration; a realistic site would
  saturate the mat far more slowly, and the "2.5 year replacement interval"
  would become decades.
* **It is the single most influential assumption in the model.** Service life,
  captured mass and cost per kilogram all scale with it directly.

**Consequence for reading any result here: the absolute kilogram figures are a
property of the assumed hotspot, not a prediction about any site.** The
*relative* comparisons between policies, which use the same hotspot throughout,
are the part that survives.

### 1.2 The modelled attenuation is above what field caps have achieved

The demonstrator reports 99 % attenuation for a fresh mat, falling to a plateau
near 94 %. Measured reactive caps:

| Source | Setting | Result |
|---|---|---|
| Cornelissen et al. [E1] | Trondheim harbour, in-situ thin-layer activated-carbon cap, fluxes measured with **benthic flux chambers** | sediment-to-water fluxes of PAHs and PCBs reduced by a **factor of 2 to 10**, that is 50 % to 90 % |
| Chen et al. 2025 [E3] | mesocosm, nitric-acid-modified MWCNT cap | Pb flux 0.97/2.50/1.51 to 0.76/0.59/0.25 ug/m2/d at days 15/45/90, that is **22 % to 76 %** |
| Patmont et al. 2015 [E2] | field and laboratory activated-carbon amendment | equilibrium **porewater** concentrations of PCBs, PAHs, DDT, dioxins and furans reduced by **70 % to 99 %** at 2 to 5 % AC |

The model's figure is therefore **above the whole measured field range**, and
the closest comparison ([E1], the only in-situ marine flux measurement in this
list) is the least flattering one. The gap has identifiable causes, all of them
listed in `docs/LIMITATIONS.md`: uniform seepage rather than preferential
channels, no bioturbation or bioirrigation, no consolidation, perfect contact
between mat and sediment, and no short-circuiting at seams.

Note also what [E2] measures. A 70 to 99 % reduction in *porewater
concentration* is not a 70 to 99 % reduction in *flux*, and the two are quoted
interchangeably far too often. This repository keeps concentration and flux on
separate unit ladders precisely so that substitution cannot happen silently.

**A useful presentation line, and a defensible one:** *the model's fresh-mat
attenuation should be read as an upper bound set by the physics we chose to
include, and the honest comparator for a real deployment is the factor of 2 to
10 that thin-layer capping has actually achieved in a Norwegian harbour.*

### 1.3 Seawater speciation, and the number it makes worst

The three target metals are not equally available to a sorbent, and the ranking
is the opposite of the ranking of their published capacities.

| Metal | Speciation in seawater | Consequence | `available_fraction` |
|---|---|---|---|
| Pb | PbCO3(aq) about 41 % of dissolved Pb at pH 8.2; free Pb2+ a small minority, measured an order of magnitude below equilibrium predictions [K3] | partly available | 0.25 |
| Hg | **above 99 % Hg-Cl complexes**, dominated by HgCl4(2-) [K10] | thiols still outcompete chloride, but the species is an anion approaching a negatively charged surface and four chlorides must be displaced | 0.10 |
| Cu | **above 99 % bound to strong organic ligands**, conditional stability constants around 1e15, free Cu2+ below 6 pM [K11] | a carboxyl or amino site does not obviously compete | **0.02** |

Copper has the **best** published keratin capacity of the three, 20 mg/g on wool
keratin nanofibres [K9], and is the **worst** candidate for removal from
seawater. Capacity is not availability. Over six simulated years the sorbent's
contribution to copper attenuation is **0.00 percentage points**: copper passes
through, and an inert mat of the same geometry would perform identically.

**On this evidence a keratin core is not a copper technology.** Either the
chemistry changes to something that competes with natural organic ligands, or
the copper claim is dropped.

### 1.4 The sorbent does much less of the work than the headline suggests

Reporting attenuation alone credits the chemistry with the geometry's work. The
model now reports both, per element, at six years:

| Metal | Total attenuation | Barrier only, no capacity left | Sorbent contribution |
|---|---|---|---|
| Pb | 94.53 % | 94.34 % | **0.19 pp** |
| Hg | 94.92 % | 94.34 % | **0.58 pp** |
| Cu | 94.34 % | 94.34 % | **0.00 pp** |

The barrier figure is the advective floor: the mat suppresses almost all of the
diffusive exchange and passes the seepage-driven flux, which the sorbent must
then capture. Measured against what actually *enters* the layer rather than
against the bare flux, the picture is less bleak: the mat retained 10.3 kg of Pb
out of 38.7 kg entering, about **27 %**. Both numbers are true and they answer
different questions. The first is "how much less reaches the sea"; the second is
"is the sorbent doing anything at all". Quoting only the second would be the
flattering error, and quoting only the first would understate the chemistry.

### 1.5 Capping and methylmercury: the claim to avoid

Activated-carbon capping, the closest measured analogue, reduces porewater MeHg
by 45 to 95 % and by more than 90 % at one month, **and increased sediment MeHg
in five of seven studies**, by a mechanism the literature calls unclear [K12].
In a salt-marsh field trial the effect lasted about a year.

A keratin core is a harder case than activated carbon, not an easier one:
activated carbon is refractory, whereas keratin supplies both labile organic
carbon and reduced sulfur to the sulfate-reducing bacteria that methylate
mercury. Encapsulation limits particle contact; it does not stop dissolved
organic carbon leaching downward. **No claim that this design prevents
methylation is supportable from the published record.** See
`docs/LIMITATIONS.md`.

### 1.6 The area is the problem, not the square metre

The Bornholm primary dumpsite is a circle of radius 3 nautical miles, that is
**96.98 km²**. Covering it would take about **388,000 tonnes** of keratin, a
fifth of one year's global greasy-wool clip, and tens of billions of euro of mat
material. A realistic first deployment is one to two hectares, about 0.02 % of
that dumpsite. Full analysis, with the officially designated areas and their
sources, in `docs/DEPLOYMENT_SCALE.md`.

---

## 2. Where the rest of the defaults stand

| Model quantity | Default | Status against the literature |
|---|---|---|
| Pb capacity `q_max` | 1.0 mg/g | **Below** published keratin values (4 to 33 mg/g in deionised water at pH 4 [K1, K2]), derated for seawater speciation and Ca/Mg competition. Conservative. |
| Hg capacity `q_max` | 2.5 mg/g | **Unsupported.** No verified keratin Hg capacity was found. Derived as 2 % of the 125 mg/g stoichiometric thiol ceiling implied by keratin's 4 to 8 wt% sulfur [K4]. The weakest number in the model. |
| Isotherm form | capped linear (Langmuir-like) | **Supported.** Pb biosorption on keratin biofibres fitted Langmuir [K1]. |
| Kinetics | first-order approach to equilibrium | **Approximate.** Batch data fitted pseudo-second-order with equilibrium inside 24 h [K1]. In a mat the rate is set by intraparticle transport, not batch stirring. |
| Porewater Hg | 8 ug/L | **High but not unprecedented.** Porewater MeHg in the contaminated Tagus estuary spans 0.1 to 63 ng/L [E7]; total dissolved Hg runs higher, and heavily contaminated sites reach ug/L. |
| Methylmercury fraction | 4 % of porewater Hg, as a **risk** channel | **Directionally supported.** Capping alters sediment redox and can increase MeHg production. Treated as a constraint, never as a benefit. |
| Cap thickness | 10 mm reactive layer | **Consistent** with thin-layer capping practice [E1, E2], which is centimetre-scale rather than the metre-scale of isolation caps. |
| All euro values | assumptions | **Unsupported by design.** No supplier has been contacted; no quotation exists. |
| Detection limits | demonstration values | **Not** any manufacturer's specification. See `docs/SENSOR_SUPPLIERS.md` for what was and was not verified. |

---

## 3. Open datasets a reviewer can pull

None of these is bundled with the repository: the default run is offline and
synthetic, and redistribution terms differ per product. They are listed so the
numbers above can be checked, and so a future version can be calibrated against
measurements rather than assumptions.

| Key | Dataset | What it gives this project | Access |
|---|---|---|---|
| D1 | **ICES DOME**, contaminants and effects in biota, sediment and seawater | Measured Pb and Hg in European marine sediment and water, the OSPAR CEMP and HELCOM COMBINE holdings. The realistic range our hotspot should be compared against. | https://www.ices.dk/data/data-portals/Pages/DOME.aspx  CSV download after accepting the data policy; CC BY 4.0 |
| D2 | **OSPAR CEMP assessment data and results, 2024** | The assessed levels and trends behind the OSPAR metals indicators, already quality controlled. | https://ices-library.figshare.com/articles/dataset/Data_and_results_for_the_2024_OSPAR_CEMP_assessment/27211422 |
| D3 | **OSPAR ODIMS datastreams** | OSPAR's data and information management system, including the hazardous-substances streams. | https://odims.ospar.org/en/datastreams/ |
| D4 | **EMODnet Chemistry** contaminant products | Aggregated and validated European seas data; maps for 12 MSFD-prioritised pollutants including Pb and Hg in seawater, sediment and biota. | https://emodnet.ec.europa.eu/en/chemistry |
| D5 | **HELCOM metals core indicator** (Pb, Cd, Hg) | Baltic status and trends, with the indicator methodology. | https://indicators.helcom.fi/indicator/mercury/ |
| D6 | **In situ benthic fluxes, Baltic Sea** (Hylen et al.) | 498 fluxes from three benthic chamber landers, 59 stations, 20 years. **Dissolved inorganic phosphorus only, no metals**: useful as a chamber-lander method and data-format reference, not as a metals source. | Zenodo, DOI 10.5281/zenodo.17465937, CC BY 4.0, .xlsx |
| D7 | **US EPA, Use of Amendments for In Situ Remediation at Superfund Sediment Sites** | The regulatory and performance record for activated-carbon amendment and reactive capping. | https://semspub.epa.gov/work/HQ/196704.pdf |
| D8 | **USGS SIR 2004-5298**, benthic-flux chamber development | The measurement chain behind every chamber number quoted here, including what a chamber does and does not measure. | https://pubs.usgs.gov/sir/2004/5298/pdf/SIR2004-5298.pdf |

**The gap worth naming.** No open dataset was found that gives *measured Pb or
Hg flux attenuation across a reactive cap*, which is exactly the quantity this
demonstrator predicts. The closest available evidence is [E1] for organic
contaminants and [E3] for metals in a mesocosm. Calibrating this model against
a real metal-flux measurement would require either a field trial or an
unpublished dataset, and that absence is itself a result: **the headline
quantity of this concept has not been measured in the open literature for
metals in a marine cap.**

---

## 4. Experiments that would replace an assumption with a measurement

Ordered by how much they would narrow the model. The first two are the ones
that decide whether the concept works at all.

1. **Pb and Hg isotherms for our keratin polymer in artificial seawater**, pH 8.1,
   with Ca and Mg present, at environmentally relevant concentrations. Replaces
   the single widest interval in the model. The demonstrator quantifies what
   this is worth: with only the literature interval, which spans a factor of 27,
   the estimated saturation is too wide to support any replacement decision, and
   the evidence-informed policy degenerates into monitoring. See
   `ReactiveMediumConfig.commissioned_q_max_interval`.
2. **Thiol accessibility.** What fraction of keratin's disulfides are reduced in
   the final material, and how many of the resulting thiols a hydrated Hg
   species can reach. The entire Hg case rests on this.
3. **Column breakthrough under advective flow** at a realistic Darcy velocity,
   which is what the 1-D layer model actually predicts and what no batch
   isotherm can tell you.
4. **Effective diffusivity and hydraulic conductivity of the mat structure**,
   which set `d_eff_m2_per_s` and the bypass behaviour and are currently pure
   assumptions.
5. **Seawater immersion durability** over months: biodegradation, microbial
   attack, mechanical integrity. A protein that degrades releases its bound
   metal back.
6. **Methylmercury response.** Whether a sulfur-rich organic layer over anoxic
   sediment increases MeHg production. This one can make the concept a net harm,
   so it is a stop condition rather than an optimisation.
7. **A seepage measurement at the deployment site.** The estimator currently
   assumes the seepage velocity to within a factor of six, and that assumption
   is the second-largest contributor to the width of every flux estimate.

---

## References

| Key | Source |
|---|---|
| E1 | Cornelissen, G. et al., *Remediation of Contaminated Marine Sediment Using Thin-Layer Capping with Activated Carbon: A Field Experiment in Trondheim Harbor, Norway*, Environmental Science and Technology (2011). DOI 10.1021/es2011397. In-situ marine field experiment; sediment-to-water PAH and PCB fluxes measured with benthic flux chambers; reduction by a factor of 2 to 10. See also the Grenland fjords follow-up, DOI 10.1002/ieam.1665. |
| E2 | Patmont, C. R. et al., *In situ sediment treatment using activated carbon: a demonstrated sediment cleanup technology*, Integrated Environmental Assessment and Management 11(2):195 (2015). DOI 10.1002/ieam.1589. 2 to 5 % AC reduced equilibrium porewater concentrations of PCBs, PAHs, DDT, dioxins and furans by 70 to 99 %. |
| E3 | Chen, X., Zhu, D., You, X. et al., *Effect of Nitric Acid-Modified Multi-Walled Carbon Nanotube Capping on Copper and Lead Release from Sediments*, Toxics 13(11):912 (2025). DOI 10.3390/toxics13110912. Pb release flux, control 0.97 / 2.50 / 1.51 ug/m2/d and capped 0.76 / 0.59 / 0.25 ug/m2/d at days 15 / 45 / 90. |
| E4 | Rivera-Duarte, I. and Flegal, A. R., *Benthic lead fluxes in San Francisco Bay, California, USA*, Geochimica et Cosmochimica Acta (1994). https://www.sciencedirect.com/science/article/abs/pii/0016703794900590. Fickian diffusive Pb fluxes 2.6e-9 to 3.1e-8 mol/m2/d in anoxic surface sediments. |
| E5 | US EPA, *Use of Amendments for In Situ Remediation at Superfund Sediment Sites*, OSWER directive. https://semspub.epa.gov/work/HQ/196704.pdf |
| E6 | US Navy NAVFAC EXWC, *Technology Transfer Review: Sediment Reactive Capping*. https://exwc.navfac.navy.mil/Portals/88/Documents/EXWC/Restoration/er_pdfs/r/navfac-sed-reactive-capping.pdf |
| E7 | *Mercury in contaminated sediments and pore waters enriched in sulphate (Tagus Estuary, Portugal)*. Porewater methylmercury 0.1 to 63 ng/L. |
| E8 | ICES, *DOME (Marine Environment) data portal*. https://www.ices.dk/data/data-portals/Pages/DOME.aspx. All public data CC BY 4.0. |
| E9 | EMODnet Chemistry, *Aggregated and Validated Datasets for the European Seas*, Frontiers in Marine Science 7:583657 (2020). DOI 10.3389/fmars.2020.583657. |
| E10 | HELCOM, *Metals (lead, cadmium and mercury) core indicator report* (2018). https://helcom.fi/wp-content/uploads/2019/08/Metals-HELCOM-core-indicator-2018.pdf |
| E11 | Hylen, A. et al., *In situ measured benthic fluxes of dissolved inorganic phosphorus in the Baltic Sea*. Zenodo, DOI 10.5281/zenodo.17465937, CC BY 4.0. Phosphorus only; cited as a benthic-chamber-lander method and data-structure reference. |
| E12 | USGS, *Development of a Benthic-Flux Chamber for Measurement of...*, Scientific Investigations Report 2004-5298. https://pubs.usgs.gov/sir/2004/5298/pdf/SIR2004-5298.pdf |
| K1-K8 | Keratin biosorption sources. See `docs/MATERIAL_KERATIN.md`. |
| S01-S30 | Sensor, supplier, engine and regulatory sources. See `docs/REFERENCES.md`. |

Every URL above was reachable on 8 September 2026 unless the row says
otherwise. Where a full text could not be retrieved, the row says which figure
came from an indexed summary rather than the paper itself, and no figure has
been carried into the model from a summary alone.
