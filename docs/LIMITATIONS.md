# Limitations

Updated 9 September 2026. Read together with the [manuscript](../manuscript/manuscript.pdf), [assumptions](ASSUMPTIONS.md), [evidence base](EVIDENCE_BASE.md) and [paper traceability audit](PAPER_PARAMETER_TRACEABILITY.md).

## Scope and validation status

This is an offline simulator of a hypothetical reactive seabed cap and a synthetic monitoring/maintenance workflow. It models Pb, inorganic Hg and Cu transport; the default chemical monitoring supports Pb and Hg. No simulated result has been validated against a deployment of the proposed keratin core. Existing caps and geotextile sorbent constructions are documented in [PRIOR_ART.md](PRIOR_ART.md).

The materials literature includes real uptake measurements on particular keratin formulations, including Cu on treated wool and Hg on reduced human hair. Those experiments do not calibrate the final wool/feather core in flowing seawater. A literature-supported mechanism, an assumed capacity and a fitted operational model are different levels of evidence.

The source does not locate contamination, simulate munitions or address their handling. TNT and other energetic compounds are outside the simulated chemical scope. Designated-area maps provide context rather than a measured Pb/Hg/Cu footprint or deployment recommendation. Recommendations have `human_confirmation_required = True` and `execution_mode = "simulation_only"`; there is no physical actuation.

## Physical and numerical limitations

| Area | Remaining limitation |
|---|---|
| Source reservoir | Porewater concentrations and seepage are prescribed. The source never depletes, and sediment reactions do not respond to capping. |
| Layer geometry | Each tile has a 1-D vertical column. Preferential paths, lateral flow, seam geometry, heterogeneous contact and sediment consolidation are unresolved. |
| Chemistry | Independent dissolved Pb/Hg/Cu pools with capped linear equilibrium and first-order relaxation. No explicit multi-metal competition, speciation, precipitation, particulate exchange, pH feedback or microbial chemistry. |
| Material allocation | Fixed per-element allocation avoids counting the same dry mass repeatedly, but is not a mechanistic shared-site competitive isotherm. Bulk density and porosity are independent assumptions. |
| Full-capacity rule | A cell at its effective sorption capacity stops exchanging sorbed mass under the retained locking rule. This can produce a finite difference from a nearly full cell during flushing; reversible desorption of exhausted material is not validated. |
| Fouling and burial | Scalar resistance, accessibility and bypass changes approximate complex biological and hydraulic processes. Lower flux under burial does not prove successful treatment. |
| Damaged-area coupling | Whole-hotspot emission mixes full-column flux with uncovered, damaged and bypass fractions. Columns continue to evolve over their full represented footprint. This area approximation is not a fully coupled heterogeneous sediment/mat flow solution. |
| Separate mass balances | Initial sorbed inventory, new column input, residual output, remaining media and retrieved media form a column ledger. Coastal windows have separate source/storage/export ledgers. Area-mixed hotspot emission is not a term that closes a single shared sediment/mat/water budget. |
| Coastal hydrodynamics | Prescribed currents and 2-D depth-averaged transport with effective mixing depth/diffusivity. No stratification, resolved near-bed boundary layer or calibrated coastal flow solution. |
| Two timescales | The mat evolves over years; the coastal model runs short windows at valid captured mat ages. Window phase and duration affect peaks and inventories. These windows are not a multi-year coastal trajectory and do not feed water concentrations back to the long column run. |
| Numerical error | Implicit layer and coastal schemes still have truncation error. Independent temporal and spatial studies test specified cases, not every possible parameter combination. Stable or mass-conserving output is not sufficient evidence of accuracy. |
| Interpolation and events | Column steps end at exact scheduled boundaries; source changes, damage and service can produce jumps. Monitoring histories use the documented sample-hold convention, including the first available state before a window's first sample. Fine transient structure below the recorded cadence is unresolved. |

The revised barrier reference uses the same discrete boundary fluxes as the layer. Its difference from transient reactive attenuation includes storage and history, so it need not stay positive after forcing changes. A plateau can reflect finite-affinity equilibrium below capacity. The historical approximately 3.09-year breakthrough is a separate numerical test fixture, not the default scenario's service life.

The [numerical audit data](../results/numerical-audit/reactive_numerical_audit.json), [timescale studies](TIMESCALES.md) and manuscript give the errors and sensitivities actually measured. A convergent benchmark does not establish a precise field prediction, and a phase-dependent plume peak must not be described as horizon-independent.

## Monitoring and inference limitations

- Observation schedules, detection limits and noise are synthetic choices, not verified instrument performance. The hypothetical commissioning capacity interval was not obtained from a laboratory test.
- The estimator uses available, compatible, QC-passed observations for known tiles. Default Pb porewater is dissolved filtered and Pb chamber output is total recoverable; mapping these operational fractions to the same simulated dissolved pool remains an observation-model approximation.
- Inorganic Hg and MeHg are separate analytical channels. The MeHg values do not constrain the inorganic Hg loading estimate. Cu has no default chemical observations and cannot support a chemical maintenance decision.
- A missing measurement is not zero. Legacy estimate fields can carry `(0, 0)` as an unavailable-source sentinel alongside `INSUFFICIENT_DATA`; that flag is authoritative. Such zeros are not measured absence or certainty.
- Above-range measurements preserve an unbounded upper interval. Finite loading bounds may come from the assumed capacity ceiling. Strict JSON uses `null` with `_nonfinite_values` path metadata for non-finite endpoints; `null` alone must not be interpreted as a measured zero.
- Missing reported chemical uncertainty uses an explicit assumed relative standard uncertainty of 0.50. Interval widening and attribution weights are heuristics rather than calibrated confidence probabilities. Estimated attenuation is clipped to [0,1], so it cannot describe net-release negative attenuation even when truth plots can. Fouling, permeability and compatibility estimates remain unavailable; channel ages are in snapshots while recommendation-level `data_age_s` remains null.
- Numeric condition anomalies require a resolved two-standard-uncertainty deviation and reported uncertainty. Categorical damage has separate rules. The coupled timeline has no calibrated head or tilt proxy, so those fields are unavailable; stable zeros or a record's mere presence do not establish failure.
- Current-media loading, chamber and condition inference excludes outgoing-media observations at replacement. Porewater history is retained as source evidence. A physical survey does not refresh missing or stale Pb/Hg chemistry.
- Only compatible measured source and chamber channels with a computable ratio enter attenuation attribution. Several physical and chemical changes remain observationally confounded despite these gates.
- A chamber samples a limited area over a finite exposure. Its default synthetic reading represents the column, whereas the displayed hotspot source includes area losses and bypass. Scaling chamber data to footprint-wide yearly emission requires additional assumptions.
- Campaign schedules remain fixed. A recommendation for additional sampling is recorded but does not launch an adaptive measurement campaign. Cost calculations cover only the implemented categories and omit parts of real monitoring and mobilisation economics.

## Ecological response is not predicted

A synthetic MeHg channel does not simulate Hg methylation, demethylation, microbial response, redox, toxicity or biological uptake. Lower total Hg flux alone does not establish ecological benefit.

Laboratory estuarine microcosms showed increased methylmercury beneath a cap without a necessarily significant increase at the cap-water interface [Johnson et al., 2010](https://doi.org/10.1021/es100161p). Other sediment microcosms showed lower porewater MeHg and test-organism uptake after activated-carbon or thiol-silica amendment [Gilmour et al., 2013](https://doi.org/10.1021/es4021074). Neither result transfers directly to this keratin core.

Leachables, degradation products and changes to sediment chemistry could affect net methylmercury release; the direction and magnitude must be measured. Encapsulation does not prove that dissolved products cannot move through a permeable carrier. No experiment here establishes that keratin increases methylation, prevents it or is environmentally benign.

Benthic impacts also require assessment independently of chemical removal. A Grenland field study reported impaired benthic community function 49 months after powdered activated-carbon capping [Raymond et al., 2021](https://doi.org/10.1007/s11356-020-11607-0). That is a material- and setting-specific trade-off, not a prediction for keratin. Durability, retained-metal release, net MeHg transport and biological endpoints belong in validation before any ecological performance claim.

## Commercial and reproducibility limits

No supplier has been contacted and no quotation exists. Prices, pilot scale, logistics and decision thresholds are assumptions. A documented supplier capability is not a quotation, current stock or proof of suitability in seawater. Protocol demonstrations use the project's own simulated interface, not an invented vendor register map.

Seeded runs, configuration hashes, dependency provenance and saved evidence records support reproduction of this implementation. They do not remove uncertainty in the model or validate field performance. Tests establish the specific contracts, numerical checks and cases exercised; broad physical and numerical generalisation requires additional evidence. The accompanying manuscript and generated manifests record the revision and checks used for the published outputs.
