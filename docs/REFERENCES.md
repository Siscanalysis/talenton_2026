# Reference register

Checked 8 September 2026, as supplied with the build packet. Full annotations
are in `docs/MESH_DEMO_BUILD_BRIEF.md`. Entries S19–S22 are explicitly
historical or incompletely retrieved product evidence. A source note supports a
bounded claim; none of them validates our device.

## Material and field evidence

| Key | Source | What it does and does not support |
|---|---|---|
| S01 | Paraskevopoulou et al. (2021), *Evaluation of Polyurea-Crosslinked Alginate Aerogels for Seawater Decontamination* — https://pmc.ncbi.nlm.nih.gov/articles/PMC8005931/ | Pb adsorption in seawater by **specific** polyurea-crosslinked alginate beads. Not a test of an ordinary alginate mesh, of our composite, or of flowing open-sea deployment. Substantial synthetic polymer content: not evidence of biodegradability. |
| S02 | Gosnell et al. (2023), *World war munitions as a source of mercury in the southwest Baltic Sea* — https://pubmed.ncbi.nlm.nih.gov/37879375/ | Sediment contamination versus a water-column target. Not evidence for a Brest hotspot. |
| S03 | den Otter et al. (2023), *Release of Ammunition-Related Compounds from a Dutch Marine Dump Site* — https://doi.org/10.3390/toxics11030238 | Supports investigating a mixture of ammunition-related contaminants. A Pb/Hg-only demo is a scope restriction, not a claim that TNT is harmless. |
| S04 | Chen et al. (2020), *Influence of sulfide, chloride and DOM on mercury adsorption by activated carbon* — https://link.springer.com/article/10.1186/s42834-020-00065-5 | Hg capture depends on water chemistry and species. Fitted parameters are not transferable to a different sulfur-functionalised biomesh. |
| S05 | USGS, *PHREEQC version 3 documentation* — https://water.usgs.gov/water-resources/software/PHREEQC/documentation/phreeqc3-html/phreeqc3-1.htm | Optional speciation module. The database and activity model must actually contain the Pb/Hg reactions and saline parameters; a Pitzer option alone is not enough. |

## Software reuse

| Key | Source | Note |
|---|---|---|
| S06 | NIST, *FiPy* — https://pages.nist.gov/fipy/en/stable/README.html | Reused transient/convection/diffusion solver. Our formulation, boundary conditions and validation remain ours. |
| S07 | *OpenDrift* — https://opendrift.github.io/ , https://github.com/OpenDrift/opendrift | MET Norway framework, GPL-2.0. Possible later adapter; not a prevalidated reactive-mesh model. |
| S08 | *open TELEMAC-MASCARET* — https://www.opentelemac.org/index.php/presentation?id=17 , licence https://www.opentelemac.org/index.php/licence | Later source of resolved local flow. Not a two-day prerequisite. |
| S25 | SciPy, `solve_ivp` — https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html | ODE solver for the reduced material model. Pin a tested release. |
| S26 | SciPy, `differential_evolution` — https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.differential_evolution.html | Optional bounded search. An optimisation result is only as credible as its model. |
| S27 | pymoo, NSGA-II — https://pymoo.org/algorithms/moo/nsga2.html | Optional multiobjective study. Keep Pb and Hg objectives separate unless a weighting is justified. |
| S28 | PyModbus — https://pymodbus.readthedocs.io/ | A client/emulator does not supply a manufacturer register map, scaling or calibration. Replay or read-only only. |
| S29 | Streamlit, `st.plotly_chart` — https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart | Local presentation component. Browser display is not a cloud requirement. |

## European data products

| Key | Source | Note |
|---|---|---|
| S09 | Copernicus Marine Toolbox — https://toolbox-docs.marine.copernicus.eu/en/stable/usage/quickoverview.html | Fetch a small reproducible subset through the supported client; cache with product/version/time/depth. |
| S10 | Copernicus Marine, IBI Ocean Physics — https://data.marine.copernicus.eu/product/IBI_ANALYSISFORECAST_PHY_005_001/services | Hourly versus daily/de-tided products differ. Candidate hourly 3D dataset `cmems_mod_ibi_phy_anfc_0.027deg-3D_PT1H-m`. Regional resolution does not establish metre-scale plume fidelity. |
| S11 | EMODnet Bathymetry — https://emodnet.ec.europa.eu/en/bathymetry | Terrain context only, at its supported resolution. No pollutant or current data. |
| S12 | EMODnet web services — https://emodnet.ec.europa.eu/en/emodnet-web-service-documentation | A rendered map service is not automatically a numerical depth raster. |
| S30 | Copernicus citation guidance — https://help.marine.copernicus.eu/en/articles/4444611-how-to-cite-copernicus-marine-products-and-services | Citation and licence obligations are not interchangeable. |

## Suppliers (see `docs/SENSOR_SUPPLIERS.md` and `docs/research/`)

| Key | Source | Status caveat |
|---|---|---|
| S13 | nke Instrumentation, MoSens — https://nke-instrumentation.com/produit/mosens/ | Modbus carrier for WiMo sensors. Configuration, register map, depth rating unconfirmed. |
| S14 | nke Instrumentation, WiMo FAQ — https://support.nke-instrumentation.com/index.php/wimo/wimo-sonde/wimo-faq/ | Documents Modbus modes. Establishes no Pb/Hg selectivity and no open SDK. |
| S15 | Aqualabo CTZN — https://www.aqualabo.fr/en/produit/digital-sensor-ctzn/ | Modbus RTU RS485 or SDI12; conductivity to 100 mS/cm. Context channel, not a metal channel. |
| S16 | Aqualabo sensor catalogue — https://www.aqualabo.fr/en/sensors-and-measuring-equipment/sensors/ | Verify each exact model; protocol and salinity rating are not shared across a range. |
| S17 | Nortek Aquadopp Gen 2 — https://www.nortekgroup.com/products/aquadopp2-500m | Current measurement. Norway is European, not EU. |
| S18 | Nortek Gen 2 release notes — https://www.nortekgroup.com/knowledge-center/wiki/aquadopp-awac-release-notes | RS422, generation-specific binary formats, NMEA option. RS422 is not an application-level message format. |
| S19 | IDRONAUT VIP leaflet — https://www.idronaut.it/wp-content/uploads/2019/06/Vip-Leaflet.pdf | Cu, Pb, Cd, Zn. **No mercury analyte.** A mercury-containing electrode is not mercury detection. Orderability unconfirmed. |
| S20 | IDRONAUT VIPPlus manual — https://www.idronaut.it/wp-content/uploads/2019/06/VIP-Windows-Leaflet.pdf ; EU SCHeMA reporting — https://cordis.europa.eu/project/id/614002/reporting | Historical capability evidence; not a verified current open protocol or a present-day quotation. |
| S21 | P S Analytical PSA 10.035 Millennium Merlin — https://psanalytical.com/products/laboratory-products/millennium-merlin-modules-and-accessories/millennium-merlin-10-025-10-035-10-045/millennium-merlin-10-035 | Laboratory Hg instrument, EPA Method 1631. Full page retrieval failed. A lead to verify, not a submersible probe. Contact: https://psanalytical.com/contact-us |
| S22 | P S Analytical PSA 10.226 Online Merlin — https://psanalytical.com/products/online-analysers/online-merlin/psa-10-226-online-merlin | Indexed description mentions sea-water applications; direct retrieval failed. Topside conditioned-sample candidate, unverified. |

## Quality control

| Key | Source | Note |
|---|---|---|
| S23 | US IOOS QARTOD — https://ioos.noaa.gov/project/qartod/ | Flags and basic range/spike/stuck checks as a baseline. Our rules are not a QARTOD certification. |
| S24 | OOI Quality Control — https://oceanobservatories.org/quality-control/ | Preserve passed / not evaluated / suspect / failed / missing instead of deleting readings. |

## User-supplied

| Key | Source | Note |
|---|---|---|
| U01 | *Writing proposal and evaluation criteria.pdf*, EU TalentOn, 28 August 2026 | Excellence, Impact, Implementation, plus Pitching. This packet is supporting material, not the written deliverable. Simulated improvement is not field validation. |
