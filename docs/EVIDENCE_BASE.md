# Evidence base

Scientific revision: 9 September 2026. The [manuscript](../manuscript/manuscript.pdf), [material review](MATERIAL_KERATIN.md) and [supplied-paper audit](PAPER_PARAMETER_TRACEABILITY.md) distinguish experimental evidence from demonstration assumptions. The latter includes page numbers, source hashes, unit conversions and discrepancies in the supplied articles.

This revision supersedes earlier statements that no keratin Hg uptake had been verified, that keratin cannot remove Cu, and that the simulated attenuation exceeds every field-cap result. Those statements were broader than the evidence supports. Previously printed scenario performance tables have been replaced by links to regenerated results in the manuscript and [gallery](gallery/README.md).

## What the supplied papers contribute

The original repository cited Zubair et al.'s 2026 review as background. Git history and parameter `source_ref` records do not show numerical calibration from the supplied PDFs. The re-audit adds evidence and corrects material claims; it does not convert laboratory maxima into validated seawater defaults.

| Source and experiment | Numerical result | Appropriate use and transfer limit |
|---|---|---|
| Enkhzaya et al. (2020), Table 2, supplied PDF p. 32 [P1] | Cu Langmuir maxima 0.239, 0.817 and 0.268 mmol/g for untreated, 0.05 M Na2S-treated and 0.02 M Na2S-treated sheep wool; calculated as 15.19, 51.92 and 17.03 mg/g | Batch material screening at pH 5 and 303 K, with 48 h contact. Treatment changes the material and its yield. The reported kinetics use a different rate law; source figure/table and inventory inconsistencies preclude unqualified calibration. |
| Zubair et al. (online 2024, journal 2025), supplied PDF pp. 10 and 13 [P2] | Modified feather-keratin/graphene-oxide composite: 99.21% Pb removal from 600 ?g/L in 10 mL with 0.1 g sorbent, pH 7.5, 24 h | Calculated uptake is 0.059526 mg/g, bounded by the batch's 0.060 mg/g inventory. This is neither a maximum capacity nor mat-flux attenuation. The solution includes 0.02 M NaCl and 0.01 M CaCl2, with multiple competing metals; it is not a full seawater test. |
| Liang et al. (2023), primary publisher abstract, identified from review p. 5 [P3, P4] | Reduced human hair: reported Hg uptake 476.7 mg/g and distribution coefficient 2.6 million mL/g | A modified-hair aqueous assay, not untreated wool or feather in seawater. Full experimental methods were not retrieved in this audit. It corrects the previous absence claim but does not validate the model's Hg capacity. |

The [machine-readable traceability registry](../research/references/paper_parameter_traceability.json) distinguishes direct primary measurements, secondary leads, calculated conversions and values excluded from model fitting. Supplied copyrighted PDFs are not redistributed.

## Default capacities and chemistry

| Model quantity | Resolved default | Evidence status |
|---|---|---|
| Pb operating capacity | 1.0 mg/g | Assumed seawater derating motivated by earlier keratin biofibre studies; not fitted to the new dilute composite assay |
| Hg operating capacity | 2.5 mg/g | Assumption for the proposed core; originally linked to a conditional sulphur-site calculation, not a measured seawater isotherm |
| Cu operating capacity | 3.0 mg/g | Assumption motivated by older modified-keratin studies; new wool data support possible uptake but do not determine operating performance |
| Availability fractions, Pb / Hg / Cu | 0.25 / 0.10 / 0.02 | Effective model factors, not measured universal species fractions or kinetic accessibility |
| Isotherm and kinetics | Capped linear equilibrium, first-order relaxation | Computational approximation; batch Langmuir and pseudo-second-order fits do not identify these coefficients directly |
| Synthetic commissioning interval | Narrower configured capacity range | A hypothetical commissioning result; no commissioning experiment was performed |

The earlier 125 mg/g Hg sulphur-site calculation assumes 4 wt% sulphur, two sulphur atoms per Hg and full accessibility. It is not a universal capacity ceiling for chemically modified keratin. Published maxima from different materials and matrices must not be ranked as interchangeable sorbent performance.

Chloride, carbonate, sulphide and organic ligands can change uptake, ligand exchange and transport. The code does not solve these equilibria. In particular, strong Cu organic complexation motivates availability measurements and sensitivity analysis; it does not prove zero Cu sorption in every keratin formulation. All configuration values and inventory allocations are documented in [ASSUMPTIONS.md](ASSUMPTIONS.md).

## Prescribed source versus measured benthic flux

The default source concentrations are assumed: Pb 1.0 mg/L, inorganic Hg 8 ?g/L and Cu 2.0 mg/L. The reservoir is prescribed and never depletes. For Pb against clean overlying water, the two distinct default flux quantities are:

```text
Advective component: v Cs = 3e-8 ? 1e-3
                         = 3e-11 kg/m?/s = 2,592 ?g/m?/day
Full bare reference: (v + kb) Cs = (3e-8 + 5e-7) ? 1e-3
                               = 5.3e-10 kg/m?/s = 45,792 ?g/m?/day
```

The second expression includes the assumed bare sediment-water exchange coefficient. Comparing only the advective component with measured diffusion omits most of the denominator used in the simulated attenuation.

Rivera-Duarte and Flegal report Fickian diffusive Pb fluxes of 2.6e-9 to 3.1e-8 mol/m?/day in San Francisco Bay sediment. With a Pb molar mass of 207.2 g/mol, this is approximately 0.54?6.42 ?g/m?/day [E4]. The model's prescribed flux is much higher, but its process and site are different. The literature comparison motivates site measurements; it does not establish the true flux, service life or lifetime policy ranking at any proposed deployment.

Absolute simulated kilograms depend on assumed concentration, seepage, exchange, geometry and duration. Affinity, kinetics, loading, bypass and observation schedules also affect service outcomes. Neither linear lifetime extrapolation nor invariance of relative policy rankings follows from changing the source.

## Reactive-cap comparators have different endpoints

| Study | Measured endpoint | What it supports |
|---|---|---|
| Cornelissen et al. (2011), Trondheim harbour field trial [E1] | Benthic-chamber PAH flux reduced by a factor of 2?10, equivalent to 50?90% | Marine field evidence for that activated-carbon treatment and contaminant; not a ceiling for all cap designs or a metals result |
| Chen et al. (2025), laboratory sediment-capping study [E3] | Pb control fluxes 0.97, 2.50, 1.51 versus capped 0.76, 0.59, 0.25 ?g/m?/day at days 15, 45, 90 | Calculated reductions 21.6%, 76.4%, 83.4% for a modified carbon-nanotube cap; another material and setting |
| Patmont et al. (2015), activated-carbon treatment review [E2] | Reported equilibrium porewater concentration reductions of 70?99% for organic contaminants at 2?5% AC | Concentration and bioavailability evidence, not an equivalent flux reduction or a keratin-metal calibration |

Observed concentration reduction, batch removal, porewater availability, organism uptake and sediment-to-water flux are separate endpoints. The cited subset of studies cannot establish the maximum performance achieved by all reactive caps. Likewise, omitted processes may make the demonstrator optimistic in some settings, but do not turn it into a proven mathematical upper bound on field performance.

Within the simulation, the non-sorbing barrier reference isolates the transport geometry at steady state. Its difference from a transient reactive column also includes dissolved storage and source history. Report it alongside whole-hotspot emissions and column inventories; do not credit the entire simulated attenuation to sorption or treat a loading plateau as proof of complete exhaustion.

## Ecological evidence and the methylmercury gap

Johnson et al. found increased methylmercury beneath a cap in laboratory estuarine microcosms, without a necessarily significant cap-water-interface effect under the tested conditions [E13]. Gilmour et al.'s sediment microcosms found that activated carbon and thiol-functionalised silica at 2?7% dry mass reduced porewater methylmercury by 45?95% and uptake into a test oligochaete by 30?90% [E14]. These experiments measured different parts of formation, partitioning, transport and uptake.

They neither demonstrate that every cap increases net methylmercury exposure nor establish ecological safety of a keratin core. Leaching, biodegradation, microbial response, contaminant release and benthic effects require material- and site-specific tests. The demonstrator's separate synthetic MeHg observations do not constitute a biogeochemical or ecological prediction. See [LIMITATIONS.md](LIMITATIONS.md).

## Open data and access

The default run is offline and synthetic. The following are discovery and calibration leads, not input datasets already ingested by the simulator. Access and redistribution status are recorded individually in [datasets.json](../research/references/datasets.json) and [research/datasets/README.md](../research/datasets/README.md).

| Dataset | Relevant content and limitation |
|---|---|
| [ICES DOME](https://www.ices.dk/data/data-portals/Pages/DOME.aspx) | Marine contaminant observations in sediment, water and biota. Matrix-specific measurements cannot be substituted directly for porewater concentration. |
| [OSPAR CEMP assessment](https://ices-library.figshare.com/articles/dataset/Data_and_results_for_the_2024_OSPAR_CEMP_assessment/27211422) and [ODIMS](https://odims.ospar.org/en/datastreams/) | Assessment data and environmental data streams; check product-specific variables and access terms. |
| [EMODnet Chemistry](https://emodnet.ec.europa.eu/en/chemistry) | Aggregated European marine contaminant products; coverage and matrix depend on product. |
| [HELCOM mercury indicator](https://indicators.helcom.fi/indicator/mercury/) | Baltic status and monitoring context; no calibration of this hypothetical hotspot. |
| [Baltic benthic-flux dataset](https://doi.org/10.5281/zenodo.17465937) | Dissolved inorganic phosphorus, not Pb/Hg/Cu. Useful for chamber data structure and methods only. |
| [USGS chamber report](https://pubs.usgs.gov/sir/2004/5298/pdf/SIR2004-5298.pdf) | Benthic-flux measurement methodology; not material performance data. |
| [US EPA sediment amendment report](https://semspub.epa.gov/work/HQ/196704.pdf) | Remediation context and evidence; no validation of this proposed core. |

This review did not identify an openly accessible dataset validating the final wool/feather core's Pb/Hg/Cu flux attenuation under representative seawater flow. That is a gap in the evidence assembled here, not proof that no marine metal-cap measurements exist anywhere.

## Measurements that would replace assumptions

1. Measure isotherms, competitive uptake and uncertainty on the final material in representative seawater, including Ca/Mg, dissolved organic matter and relevant metal concentrations.
2. Determine accessible binding sites, dry and hydrated material properties, manufacturing yield and leachables. Total sulphur does not identify accessible Hg sites.
3. Run flow-through breakthrough and desorption columns across realistic seepage rates, then measure effective diffusivity, hydraulic conductivity, seams and bypass.
4. Measure porewater concentration, seepage and flux at the actual site with matched operational fractions and uncertainty.
5. Test seawater durability, fouling, burial, mechanical damage, retrievability and retained-metal release.
6. Measure methylmercury formation, net release and biological effects, alongside benthic community impacts. Reduced total dissolved Hg alone is insufficient.
7. Compare monitoring designs with documented cost assumptions and supported measurement precision. Requested additional sampling is not automatically executed by the current simulation.

## References

- **P1:** Enkhzaya, S., Shiomori, K. and Oyuntsetseg, B. (2020). *Effective adsorption of Au(III) and Cu(II) by chemically treated sheep wool and the binding mechanism*. Journal of Environmental Chemical Engineering 8, 104021. [DOI](https://doi.org/10.1016/j.jece.2020.104021).
- **P2:** Zubair, M., Roopesh, M. S. and Ullah, A. (2025; online 2024). *Green Nanoengineered Keratin Derived Bio-Adsorbent for Heavy Metals Removal from Aqueous Media*. Advanced Sustainable Systems 9, 2400491. [DOI](https://doi.org/10.1002/adsu.202400491).
- **P3:** Liang, X. et al. (2023). *Mechanochemical-assisted reduction of human hair for efficient and selective removal of aqueous Hg(II) to the ppb level*. Journal of Molecular Liquids 371, 121124. [DOI](https://doi.org/10.1016/j.molliq.2022.121124). Publisher abstract/highlights verified; full methods not retrieved.
- **P4:** Zubair, M., Rauf, Z. and Ullah, A. (2026). *Keratin-derived bio-adsorbents for water remediation: Current and future trends*. Bioresource Technology Reports 33, 102508. [DOI](https://doi.org/10.1016/j.biteb.2025.102508). Secondary review; its primary references require their own experimental context.
- **E4:** Rivera-Duarte, I. and Flegal, A. R. (1994). *Benthic lead fluxes in San Francisco Bay, California, USA*. Geochimica et Cosmochimica Acta 58, 3307?3313. [DOI](https://doi.org/10.1016/0016-7037(94)90059-0).
- **E1:** Cornelissen, G. et al. (2011). *Remediation of Contaminated Marine Sediment Using Thin-Layer Capping with Activated Carbon: A Field Experiment in Trondheim Harbor, Norway*. Environmental Science & Technology 45, 6110?6116. [DOI](https://doi.org/10.1021/es2011397).
- **E3:** Chen, X. et al. (2025). *Effect of Nitric Acid-Modified Multi-Walled Carbon Nanotube Capping on Copper and Lead Release from Sediments*. Toxics 13, 912. [DOI](https://doi.org/10.3390/toxics13110912).
- **E2:** Patmont, C. R. et al. (2015). *In situ sediment treatment using activated carbon: a demonstrated sediment cleanup technology*. Integrated Environmental Assessment and Management 11, 195?207. [DOI](https://doi.org/10.1002/ieam.1589).
- **E13:** Johnson, N. W., Reible, D. D. and Katz, L. E. (2010). *Biogeochemical Changes and Mercury Methylation beneath an In-Situ Sediment Cap*. Environmental Science & Technology 44, 7280?7286. [DOI](https://doi.org/10.1021/es100161p).
- **E14:** Gilmour, C. C. et al. (2013). *Activated Carbon Mitigates Mercury and Methylmercury Bioavailability in Contaminated Sediments*. Environmental Science & Technology 47, 13001?13010. [DOI](https://doi.org/10.1021/es4021074).
