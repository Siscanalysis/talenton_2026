# Build brief — a sensor-informed marine reactive-mesh demonstrator

**Audience:** Codex/Claude coding agents and a four-person project team.  
**Timebox:** two development days. **Output:** a small, runnable, repository-ready demonstration and evidence exports.  
**Target:** Pb first; Hg as a separate optional channel. **Status:** conceptual research demonstrator, not field-validated remediation.

## 1. The demonstration to build

Show a hypothetical source, moving water, a retrievable reactive mesh and a small monitoring system. Answer three practical questions:

- **Where does contamination travel, and how much reaches the mesh?**
- **How does capture change as the material loads, fouls or is replaced?**
- **Given only the available observations, should an operator sample, inspect or replace it?**

A single local app should show a 2D plume/map, material loading with an uncertainty interval, observations and a maintenance recommendation with its reason. Compare **no mesh**, **fixed servicing**, and **observation-informed servicing** using the same forcing and initial conditions. Keep the hidden simulated truth separate from the estimate displayed to an operator.

Do not build a platform, mobile app, cloud fleet service, new sensor chemistry or production control system. Do not claim automated safe operation near munitions. Here, “feedback control” means updating a model and recommending a monitoring/maintenance action; all physical actions remain human decisions.

### Scientific boundaries

The team's chemical design is a hypothesis. Seawater Pb adsorption has been demonstrated for a particular polyurea-crosslinked alginate material, not our mesh [S01]. Hg performance depends on chemical conditions [S04]. No supplier instrument or simulation establishes that a dissolved-metal capture product addresses the dominant contamination pathway at a particular wreck [S02–S03]. A focus on Pb/Hg does not imply TNT is harmless.

Every input/output needs a label: **measurement, external model, literature observation, assumption, or synthetic demo**. Do not import literature maxima as validated operating capacities. No “fully biodegradable” claim for an untested composite, and no disposal of metal-loaded material into the sea.

## 2. Branches: independent work, one shared contract

| Branch / assigned prompt | What to build | Must deliver | Priority |
|---|---|---|---|
| `research/sensors` — 01 | European vendor and interface evidence | Sensor–utility–application–protocol–supplier matrix, gaps and a minimum monitoring design | Parallel research |
| `feat/mesh-care` — 02 | Reduced material model | Uptake/loading, remaining-life intervals, replacement event, small design comparison | Essential |
| `feat/coastal-2d` — 03 | Wrapped 2D transport model | Plume, mesh contact, per-metal mass budget, scenario comparison | Essential |
| `feat/feedback` — 04 | Observation replay and decision loop | QC, delayed/censored samples, uncertainty-aware recommendations | Essential |
| `feat/presentation` — 05 | One local visual demonstrator | Interactive scenario, offline replay and HTML/PNG/JSON exports | Essential |
| `feat/ml-extension` — 06 | One optional ML experiment | Tested surrogate **or** next-experiment selector with baseline comparison | Only after integration |

Prompt 02 covers rows 1 and part of 6 of the original table; 03 covers 2 and the transport part of 7; 04 covers 3, 4 and the inference part of 7. Supplier research establishes whether row 8 is justified. Row 5 and the substantive neural-network part of row 6 are optional extensions.

One coordinator owns `contracts/`, common configuration, the dependency lock and integration. Other agents must not edit these independently. Use separate Git worktrees for parallel sessions; merge complete, tested increments, not simultaneous edits in one checkout. For four people: one handles research/assumptions, one micro + feedback, one transport, one integration/presentation. This is a proposed allocation, not an assumption about confirmed skills.

## 3. Reuse decisions: do not invent all the technology

**Default two-day path:** Python + NumPy/SciPy for material dynamics and optimisation; a thin **FiPy** wrapper for finite-volume transport; a local **Streamlit + Plotly** presentation; JSON/CSV replay before hardware connections. FiPy is US/NIST, selected to limit integration risk, not presented as European [S06, S25–S29]. Pin tested stable versions during bootstrap; do not blindly select development builds.

**European extensions:** Copernicus Marine for forcing/context, EMODnet for bathymetry, OpenDrift from MET Norway as an optional alternative transport adapter, and TELEMAC as a later source of locally resolved hydrodynamics [S07–S12]. Do not implement FiPy, OpenDrift and TELEMAC together in the timebox. Reuse existing output files from a trusted local model rather than attempting a new calibrated coastal-flow model overnight.

The first run must work offline without an account. A real-map mode is optional and must remain distinct from the synthetic physics mode. A 3D terrain rendering is a stretch goal, **not** a 3D dispersion calculation.

## 4. Be exact about the observations

### Minimum monitoring concept

| Channel | Practical role | What it does not establish | Demo treatment |
|---|---|---|---|
| Current velocity/direction | Transport forcing, flow reversal, interpretation of station order | Pollutant identity or capture | Continuous synthetic replay; candidate ADCP/current-meter adapter later |
| Temperature, conductivity/salinity; optionally pH | Environmental context, quality checks, conditioning model inputs | Pb or Hg concentration | Synthetic replay with explicit units and metadata |
| Turbidity or periodic images | Possible suspended matter, fouling or damage evidence | Dissolved-metal concentration or remaining chemical capacity | Optional health signal; no automatic conversion to metals |
| Pb-selective measurement | Constrains a defined chemical fraction at a station | Automatically total dissolved or particulate Pb | Intermittent simulated observations or lab records; fraction required |
| Hg laboratory sample | Target-specific evidence and model checking | Continuous dissolved inorganic or methylmercury monitoring unless the method measures it | Delayed sample result; separate sampling and availability times |
| Used-media assay | Supports accumulated captured-mass verification | An instantaneous water-column concentration | Optional independent measurement after retrieval |

These are a proposed monitoring design, not equipment already purchased. Supplier capability/protocol evidence and uncertainties are in `docs/SENSOR_SUPPLIERS.md` [S13–S22]. A water-condition sensor is not a Pb/Hg sensor. An Hg-bearing working electrode is not evidence of Hg measurement. A lab instrument is not automatically a submersible device.

### Required record fields

Use `contracts/DATA_CONTRACT.md` and the bundled schema: station/sample/instrument identifiers, position and depth, `observed_at_utc`, `available_at_utc`, parameter, unit, medium, chemical fraction, acquisition type, value or censoring interval, method, QC flag, uncertainty when known, and provenance. Long-form records are easiest: one measured parameter per row.

**Critical rules:** no future-result access; a below-detection result is not zero; a missing value is not a non-detect; a passive sampler is not an instantaneous measurement; labile Pb and total recoverable Pb are not interchangeable. Never fill chemical data by inferring metal concentrations from pH, conductivity or turbidity alone. Missing chemistry should widen uncertainty, not produce confident predictions.

For the demo, proposed environmental sampling can be every minute and chemistry every several hours, with a configurable lab delay. These are artificial schedules, not verified instrument cycle times. The supplied JSONL examples are **I/O edge cases, not an adsorption dataset**.

## 5. Micro model: material loading and maintenance

Use a small, auditable state per panel: mass of each sorbent compartment, retained Pb/Hg mass, effective accessible capacity, fouling state, installation/media ID and service history. Start with Pb only. Add Hg using its own parameter set and an explicitly allocated material mass; never assign the full mesh capacity to both metals.

Implement an empirical saline-water equilibrium function and an effective uptake rate. A capped linear isotherm plus a first-order approach to equilibrium is sufficient as a **synthetic baseline**; it is not a statement of the exact chemistry. Treat capacity, uptake rate, contact and reactive fraction as uncertain. Do not fit all of them from one concentration stream.

The micro model receives the contaminant mass actually available in a contact region, not the source's whole release. It returns an actual mass transfer bounded by available water mass and remaining capacity. The macro model removes exactly that mass. Fouling may reduce access/rate; it must not silently erase already retained metal.

Replacement transfers retained metal to a **retrieved-media** ledger and creates a new media ID; capacity resets but captured mass does not disappear. The optional damage/desorption scenario must transfer released mass back to water explicitly. No chemical destruction of Pb/Hg is assumed.

Expose remaining service life as a conditional interval, not a sensor reading. In a source increase, capacity depletion may accelerate; in a tidal reversal, local concentrations may change without source deterioration. Demonstrate both. Do not force “realistic” saturation into two simulated days: use time acceleration or an explicitly preloaded stress-test panel.

Detailed equations and interface are in `docs/MODEL_SPEC.md`. PHREEQC is optional future chemistry support only after database suitability is checked [S05].

## 6. Macro model: 2D transport, contact and maps

Use a 2D advection–diffusion equation, with a defined effective mixing depth. This is **not diffusion alone**: currents advect the plume. Prescribe a simple physically consistent current field for the offline example. Include land/no-flux boundaries and open-water fluxes explicitly, or use a verified simple benchmark domain first.

Wrap an existing solver. Do not code a custom CFD engine. Represent the mesh as a bounded, finite-capacity reactive contact region coupled to the micro model. Unresolved interception is a documented parameter, not a claim that every molecule in a map cell passes through a small panel. Do not remove the same mass twice through independent sink terms.

For real data: cache a small region, timestamp, depth and product version. Inspect native resolution and temporal averaging. Copernicus IBI has both hourly and de-tided products; the latter cannot stand in for tidal reversals [S10]. A near-bed release must not be driven unquestioningly by surface currents. Interpolating a coarse product onto a fine map does not create fine-scale information.

A Brest map may provide geographic context, but an invented source must be labelled **hypothetical**. Do not imply that our project has located pollution there. A visual basemap, terrain raster, measured depth and a validated hydrodynamic field are different inputs. Keep the metric computational CRS separate from latitude/longitude display [S11–S12].

For the first presentation, a small synthetic coastal/channel domain is acceptable. Optional bathymetry context must not be described as feeding the flow solver unless it actually does.

## 7. Feedback: recommendations, not autonomous intervention

Implement the loop **observe → quality check → update uncertainty → compare possible explanations → recommend → log**. Start with transparent rules and a small ensemble/grid of model parameters. Complex inverse modelling is optional.

Actions: `CONTINUE`, `REQUEST_CHEMICAL_SAMPLE`, `CHECK_SENSOR`, `INSPECT_MESH`, `PLAN_REPLACEMENT`, `INSUFFICIENT_EVIDENCE`. Every recommendation includes the supporting observation IDs, uncertainty, data age, reason and a human-confirmation flag. Simulated accepted actions can change future model states; no real actuation.

A suspected saturation event, stronger leakage, shifted plume and sensor drift may look similar. Add the option to remain ambiguous. Compare the value of an additional chemical sample with immediately recommending a replacement. Do not use the simulator's hidden event label to choose an action.

Compare fixed servicing and feedback servicing under identical uncertainty scenarios and measurement budgets, accounting for sample, visit, sorbent and used-media handling costs. All euro values are assumptions unless supplied by a dated quotation. Report uncaptured Pb and Hg separately, with no invented environmental-compliance threshold.

## 8. The five scenes for the presentation

1. **Baseline:** no mesh versus a fresh panel under identical forcing; show captured and escaped mass.
2. **Loading/fouling:** declining predicted performance and wider uncertainty; inspect versus replace.
3. **Source change versus current reversal:** similar readings, different mechanisms; show the value of current data and targeted sampling.
4. **Sensor dropout/drift and delayed chemistry:** no false “all safe” message; recommendations remain evidence-limited.
5. **Replacement:** operator accepts a simulated recommendation; active capacity resets and retrieved contaminant mass stays in the ledger.

All scenes export the scenario settings, provenance, results and limitations. Include one unfavourable case: negligible capture or no economic advantage. Do not tune all scenarios to make the product succeed.

## 9. Acceptance tests and scope cuts

**Numerics:** non-negative concentrations within a documented numerical tolerance; per-metal mass conservation; zero capacity causes zero capture; zero source/initial mass creates no metal; replacement preserves the total inventory; time-step/grid refinement check. Do not conceal numerical errors by clipping without reporting the correction.

**Observations/feedback:** quantified/non-detect/missing records stay distinct; delayed samples cannot influence past decisions; failed sensors cannot silently produce high-confidence control; different chemical fractions cannot be merged without an explicit observation model; estimator cannot access hidden truth. For open water, do not report two-station concentration differences as treatment efficiency without a transport interpretation.

**Presentation:** one documented command, offline default, bounded runtime, downloadable/self-contained HTML evidence, assumptions visible, separate true/estimated curves, reproducible seeds, and a short limitations section. CI should test numerical invariants, not only whether the app imports.

**Cut first:** 3D physics, live cloud feeds, raw hardware drivers without manuals, fancy neural networks, full multi-ion geochemistry, automated fleet maintenance. Keep the mass balance, data contract and uncertainty labelling.

## 10. Delivery and schedule

**Hours 0–3:** coordinator freezes contracts/configuration, chooses the tested solver stack and confirms each agent's owned paths.  
**Hours 3–12:** parallel micro, transport and observation slices; supplier evidence does not block a synthetic run.  
**Hours 12–24:** first coupled run, common scenario, mass-budget and no-lookahead tests.  
**Hours 24–36:** uncertainty, baseline comparisons and one map-data adapter only if core works.  
**Hours 36–48:** freeze scope, rehearse, export evidence and test offline installation/replay.

Deliver source, a tested environment lock, a simple README, provenance/reference register, small redistributable fixtures, automated checks, a five-minute demo script and generated results. GitHub-ready does not mean already published: push only after the user approves a destination. The packet supports the proposal's Excellence, Impact and Implementation sections; simulated improvement is not field validation [U01].

## Reference key

Exact URLs and support limits are in `docs/REFERENCES.md`. Principal starting points: FiPy [S06], OpenDrift [S07], TELEMAC [S08], Copernicus [S09–S10], EMODnet [S11–S12], suppliers [S13–S22], and material/field evidence [S01–S05].


---

# Evidence and software references

Checked on 8 September 2026. Official documentation and primary research are used; entries S19–S22 explicitly identify historical or incompletely retrieved product evidence. Source notes support bounded claims, not validation of our device. URLs are provided for the coding/research agents.

## S01 — Paraskevopoulou et al. (2021), Evaluation of Polyurea-Crosslinked Alginate Aerogels for Seawater Decontamination

https://pmc.ncbi.nlm.nih.gov/articles/PMC8005931/

Primary experiment. Specific polyurea-crosslinked alginate beads adsorbed Pb in seawater. This is not a test of an ordinary alginate mesh, our proposed composite, or flowing open-sea deployment. The experimental material contained substantial synthetic polymer; do not label it fully biodegradable on this evidence.

## S02 — Gosnell et al. (2023), World war munitions as a source of mercury in the southwest Baltic Sea

https://pubmed.ncbi.nlm.nih.gov/37879375/

Primary field study. Relevant to the distinction between sediment contamination and a water-column target. Establish the local, accessible contamination pathway before claiming that an open-water mesh addresses it. Not evidence for a Brest hotspot.

## S03 — den Otter et al. (2023), Release of Ammunition-Related Compounds from a Dutch Marine Dump Site

https://doi.org/10.3390/toxics11030238

Primary field study. Supports investigating a mixture of ammunition-related contaminants, not dismissing energetic compounds. A Pb/Hg-only demonstration is a deliberate scope restriction, not proof that TNT is harmless.

## S04 — Chen et al. (2020), Influence of sulfide, chloride and dissolved organic matter on mercury adsorption by activated carbon

https://link.springer.com/article/10.1186/s42834-020-00065-5

Primary adsorption study. Supports treating mercury capture as dependent on water chemistry and species. Its fitted parameters cannot be transferred automatically to a different sulfur-functionalised biomesh.

## S05 — USGS, PHREEQC version 3 documentation: abstract and model description

https://water.usgs.gov/water-resources/software/PHREEQC/documentation/phreeqc3-html/phreeqc3-1.htm

Official documentation. Supports an optional speciation module. Verify that the selected database and activity model contain the required Pb/Hg reactions and saline-water parameters; the presence of a Pitzer option alone is insufficient.

## S06 — NIST, FiPy finite-volume PDE solver

https://pages.nist.gov/fipy/en/stable/README.html

Official documentation. Reuse its transient, convection, diffusion and source terms for the small demonstration; our model formulation, boundary conditions and validation remain our responsibility.

## S07 — OpenDrift documentation and upstream repository

https://opendrift.github.io/

Official framework documentation. MET Norway ocean transport framework; potential later transport adapter, not a prevalidated heavy-metal reactive mesh model. Repository: https://github.com/OpenDrift/opendrift . The repository identifies GPL-2.0 licensing.

## S08 — open TELEMAC-MASCARET: TELEMAC-2D and licence

https://www.opentelemac.org/index.php/presentation?id=17

Official description of depth-averaged free-surface hydrodynamics. A later source of resolved local flow fields. Licence page: https://www.opentelemac.org/index.php/licence . Do not make installation and local calibration a two-day prerequisite.

## S09 — Copernicus Marine Toolbox: quick overview

https://toolbox-docs.marine.copernicus.eu/en/stable/usage/quickoverview.html

Official API documentation for metadata and subsetting. Fetch a small, reproducible subset through the supported client; preserve product/version/time/depth information and cache it for offline demonstrations.

## S10 — Copernicus Marine, IBI Ocean Physics product services

https://data.marine.copernicus.eu/product/IBI_ANALYSISFORECAST_PHY_005_001/services

Official catalogue distinguishes hourly products from daily/monthly de-tided currents. Candidate hourly 3D dataset: cmems_mod_ibi_phy_anfc_0.027deg-3D_PT1H-m. Verify available variables, depth and date before downloading. Regional resolution does not establish metre-scale plume fidelity.

## S11 — EMODnet Bathymetry

https://emodnet.ec.europa.eu/en/bathymetry

Official access to European bathymetric products. Use local terrain context only at its supported resolution; it does not supply local pollutant measurements or local current fields.

## S12 — EMODnet web-service documentation

https://emodnet.ec.europa.eu/en/emodnet-web-service-documentation

Official catalogue of discovery, visualisation and download services. A rendered map service is not automatically a numerical depth raster; inspect the selected endpoint and metadata.

## S13 — nke Instrumentation, MoSens

https://nke-instrumentation.com/produit/mosens/

French manufacturer listing: compact carrier for WiMo smart sensors with Modbus communication. Exact sensor configuration, electrical layer, register map, depth and service terms must be confirmed for the purchased version.

## S14 — nke Instrumentation, WiMo FAQ and sensor family

https://support.nke-instrumentation.com/index.php/wimo/wimo-sonde/wimo-faq/

Official FAQ documents recording and Modbus modes. Sensor family: https://nke-instrumentation.com/produit/wimo-multiparameter-sonde-new-generation/ . This does not establish Pb/Hg selectivity or an open SDK.

## S15 — Aqualabo, CTZN digital conductivity/salinity/temperature sensor

https://www.aqualabo.fr/en/produit/digital-sensor-ctzn/

French manufacturer specifies Modbus RTU RS485 or SDI12 and a conductivity range reaching 100 mS/cm. This supports an environmental-context channel, not a metal-concentration channel. Long-term depth/fouling suitability needs confirmation.

## S16 — Aqualabo sensor catalogue: pH and optical measurements

https://www.aqualabo.fr/en/sensors-and-measuring-equipment/sensors/

Manufacturer lists pH/ORP, turbidity and other water-quality sensors. Verify each exact model and manual rather than assuming every model shares a protocol or salinity rating.

## S17 — Nortek, Aquadopp Generation 2 current meter

https://www.nortekgroup.com/products/aquadopp2-500m

Norwegian manufacturer; candidate for current measurements. Norway is European but not an EU member. Choose current meter versus profiler according to the actual spatial measurement needed.

## S18 — Nortek, Generation 2 release notes

https://www.nortekgroup.com/knowledge-center/wiki/aquadopp-awac-release-notes

Official notes identify RS422, generation-specific binary formats and an NMEA option for Aquadopp. Obtain the current integrator guide; do not reuse a legacy binary parser unchecked or call RS422 an application-level message format.

## S19 — IDRONAUT, VIP manufacturer leaflet

https://www.idronaut.it/wp-content/uploads/2019/06/Vip-Leaflet.pdf

Archived manufacturer material identifies Cu, Pb, Cd and Zn in freshwater and seawater. It does not list mercury as an analyte. Current orderability and support are unconfirmed; a mercury-containing electrode must not be confused with mercury detection.

## S20 — IDRONAUT, VIPPlus manual; EU SCHeMA final reporting

https://www.idronaut.it/wp-content/uploads/2019/06/VIP-Windows-Leaflet.pdf

Legacy manual refers to RS232 and VIPPlus. Archived EU project reporting describes a marine Pb-capable VIP product: https://cordis.europa.eu/project/id/614002/reporting . This is historical capability evidence, not a verified current open protocol or present-day quotation.

## S21 — P S Analytical, PSA 10.035 Millennium Merlin

https://psanalytical.com/products/laboratory-products/millennium-merlin-modules-and-accessories/millennium-merlin-10-025-10-035-10-045/millennium-merlin-10-035

Manufacturer search listing identifies a laboratory mercury instrument developed for EPA Method 1631. Full page could not be retrieved in this check. Treat as a lead to verify, not an integration-ready selection. Official contact: https://psanalytical.com/contact-us (UK, European non-EU).

## S22 — P S Analytical, PSA 10.226 Online Mercury in Liquid Streams

https://psanalytical.com/products/online-analysers/online-merlin/psa-10-226-online-merlin

Manufacturer search listing describes aqueous/sea-water applications; direct retrieval failed. Candidate topside conditioned-sample analyser, not a verified submersible probe. Current protocols, sample conditioning, quantification limits and model availability remain vendor questions.

## S23 — US IOOS, QARTOD project

https://ioos.noaa.gov/project/qartod/

Official ocean-observation quality-control programme. Use quality flags and basic range/spike/stuck-value checks as a baseline. Our proposed metal-monitoring rules are not an official QARTOD certification.

## S24 — Ocean Observatories Initiative, Quality Control

https://oceanobservatories.org/quality-control/

Official observing-system documentation describes QC flags and human annotations. Preserve the distinction between passed, not evaluated, suspect, failed and missing rather than silently deleting inconvenient readings.

## S25 — SciPy, solve_ivp

https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html

Official ODE-solver API; suitable for the reduced material model. Pin a tested release in the implemented demo rather than copying a version number from a changing documentation site.

## S26 — SciPy, differential_evolution

https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.differential_evolution.html

Official optimisation API. Use a small enumerated design study first, or bounded search where useful; an optimisation result is only as credible as its model and constraints.

## S27 — pymoo, NSGA-II documentation

https://pymoo.org/algorithms/moo/nsga2.html

Official implementation for optional multiobjective optimisation. Compare with a simple baseline and use uncertainty scenarios; keep Pb and Hg objectives separate unless an explicit weighting is justified.

## S28 — PyModbus documentation

https://pymodbus.readthedocs.io/

Official protocol-library documentation. A reusable client or emulator does not supply the manufacturer register map, scaling, endian conventions or calibration. Restrict the demo to replay/emulation or read-only integrations.

## S29 — Streamlit, Plotly chart API

https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart

Official presentation-component documentation. Suggested lightweight local interface. Browser display is not a cloud-platform requirement.

## S30 — Copernicus Marine citation guidance

https://help.marine.copernicus.eu/en/articles/4444611-how-to-cite-copernicus-marine-products-and-services

Official guidance for acknowledgements and provenance. Verify redistribution permissions for each cached data product; citation and licence obligations are not interchangeable.

## U01 — User-supplied competition document

*Writing proposal and evaluation criteria.pdf*, EU TalentOn, 28 August 2026. The supplied template separates Excellence, Impact and Implementation, with Pitching as the fourth evaluation criterion. This software packet is supporting material, not a replacement for the five-page written deliverable. No jury weighting is inferred.
