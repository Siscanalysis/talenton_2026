# European sensor, sampler and service matrix for a seabed reactive mat

**Research snapshot: 8 September 2026.** Every record carries the URL that was used and
the date it was retrieved. No supplier has been contacted. Nothing here is a quotation, a
purchase recommendation or a confirmation of stock.

Nineteen records are given. The brief's target of eight to twelve is exceeded because the
brief names twelve distinct measurement categories, and because a manufacturer and a
distributor of the same category are different records. A **minimum viable pilot set of
six** is identified in `research/sensors/measurement_chain.md`; the rest are alternatives
and rejected options, kept because knowing why something was rejected is worth as much as
knowing what was chosen.

## Rules applied to every record

* A mercury-film or mercury-plated working electrode used to measure lead is **not**
  evidence of mercury measurement. This trap is live in the trace-metal literature and is
  called out explicitly in record **S-09**.
* A fresh-water or tap-water limit of detection is **not** sea-water performance. Record
  **S-10** contains a published table in which the vendor's own sea-water lead result is
  blank.
* A serial link is not an application programming interface. RS232, RS422, RS485, Modbus
  RTU and SDI-12 are physical and link layers. None of them is HTTP, MQTT or a REST API.
* Historical evidence is not current orderability. Records **S-09**, **S-11** and **S-12**
  are marked accordingly.
* "Unknown" is written as the word `unknown`. No detection limit, register map, price,
  protocol or SDK has been inferred, interpolated or invented.

## Status vocabulary

Exactly one per record: `CURRENT_LISTING`, `HISTORICAL_EVIDENCE`, `INDEXED_LEAD_ONLY`,
`RESEARCH_PROTOTYPE`, `NOT_SUITABLE`. A current listing still does not mean in stock.

## Retrieval vocabulary

`FETCHED_OK`, `FETCHED_PDF`, `FETCH_403`, `FETCH_TLS_FAIL`, `SEARCH_INDEX_ONLY`.

---

## Summary

| ID | Supplier | Country | EU | Mfr/Dist | Model or service | Category | Status | Suitability for this application |
|---|---|---|---|---|---|---|---|---|
| S-01 | Nortek AS | Norway | non-EU | manufacturer | Aquadopp 500 m, Generation 2 | current meter | CURRENT_LISTING | VERIFIED for near-bed currents |
| S-02 | Sonardyne | United Kingdom | non-EU | manufacturer | Origin 65 ADCP (Type 8323) | seabed ADCP | CURRENT_LISTING | UNKNOWN: 62.5 kHz suits deep profiling, not a 5 m coastal column |
| S-03 | Aanderaa Data Instruments AS | Norway | non-EU | manufacturer | DCPS 5400 / DCS 4520 family | current sensor | CURRENT_LISTING | UNKNOWN: accuracy not published on the page retrieved |
| S-04 | Star-Oddi Ltd | Iceland | non-EU (EEA) | manufacturer | DST centi-TD | temperature and depth logger | CURRENT_LISTING | VERIFIED for recorded temperature; no telemetry |
| S-05 | Aqualabo | France | EU | manufacturer | Digital sensor CTZN | conductivity, salinity, temperature | CURRENT_LISTING | UNKNOWN: 5 bar class, depth rating unpublished |
| S-06 | Aqualabo | France | EU | manufacturer | Digital sensor PHEHT | pH, redox, temperature | CURRENT_LISTING | UNKNOWN: seawater pH accuracy not published |
| S-07 | Aqualabo | France | EU | manufacturer | NTU Sensor | turbidity, suspended solids | CURRENT_LISTING | UNKNOWN: no marine depth rating published |
| S-08 | nke Instrumentation | France | EU | manufacturer | MoSens | Modbus sensor carrier and logger | CURRENT_LISTING | UNKNOWN: depth rating and register map not published |
| S-09 | Idronaut S.r.l. | Italy | EU | manufacturer | VIP (Voltammetric In-situ Profiling system) | in-situ Pb, Cd, Cu, Zn | HISTORICAL_EVIDENCE | UNKNOWN: site unreachable on 2026-09-08; **no Hg analyte** |
| S-10 | Metrohm AG | Switzerland | non-EU | manufacturer | 884 Professional VA with Bi drop electrode | laboratory Pb and Cd by ASV | CURRENT_LISTING | NOT SUITABLE as published for seawater Pb: see the blank cell |
| S-11 | Milestone Srl | Italy | EU | manufacturer | DMA-80 evo | laboratory total Hg | INDEXED_LEAD_ONLY | UNKNOWN: manufacturer pages unreachable |
| S-12 | P S Analytical Ltd | United Kingdom | non-EU | manufacturer | PSA 10.035 Millennium Merlin | laboratory total Hg by AFS | INDEXED_LEAD_ONLY | UNKNOWN: every route returned HTTP 403 |
| S-13 | DGT Research Ltd | United Kingdom | non-EU | manufacturer | LSPM-NP sediment DGT, Chelex binding layer | DGT-labile Pb in porewater | CURRENT_LISTING | VERIFIED as a time-integrated porewater channel |
| S-14 | Unisense A/S | Denmark | EU | manufacturer | MiniChamber Lander System | benthic chamber incubation | CURRENT_LISTING | UNKNOWN for metal flux: sensor set is O2, H2, N2O, pH, H2S |
| S-15 | Rhizosphere Research Products | Netherlands | EU | manufacturer | Rhizon CSS | porewater extraction from cores | CURRENT_LISTING | VERIFIED as a porewater sampling method |
| S-16 | Exail | France | EU | manufacturer | Gaps M5 USBL | acoustic positioning and telemetry | CURRENT_LISTING | UNKNOWN: accuracy is a percentage of slant range |
| S-17 | Blueye Robotics AS | Norway | non-EU | manufacturer | Blueye X3 | ROV visual inspection | CURRENT_LISTING | VERIFIED for visual condition, not for chemistry |
| S-18 | Subsea Tech | France | EU | manufacturer and service provider | ROV inspection and survey services | inspection service | CURRENT_LISTING | UNKNOWN: no sediment-cap reference retrieved |
| S-19 | University of Geneva (Tercier-Waeber group) | Switzerland | non-EU | research group | TracMetal / Au-GIME Hg(II) sensor | in-situ Hg(II), As, Cd, Pb, Cu, Zn | RESEARCH_PROTOTYPE | NOT a purchasable product |

---

# Full records

## Current meters and ADCPs

### S-01 Nortek Aquadopp 500 m, Generation 2

* **Supplier** Nortek AS. **Country** Norway, **European non-EU**. **Manufacturer.**
* **Exact model** Aquadopp 500 m, Generation 2.
* **What it actually measures** Single-point water velocity by acoustic Doppler, plus
  temperature, compass heading, tilt and pressure. Optional PUV-based directional waves.
* **Analyte and fraction** Not a chemical instrument. `Parameter.CURRENT_EAST`,
  `CURRENT_NORTH`, `TEMPERATURE`; `QuantityKind.VELOCITY` and `CONTEXT`.
* **Published range and accuracy** Velocity range "User-selectable 1.0 to 5.0 m/s";
  accuracy "+/-1% of measured value +/-0.5 cm/s"; precision "Typ. 1 cm/s"; cell size
  0.75 m, single point. Temperature -4 to +40 degC at +/-0.1 degC. Compass under 2 deg.
  Tilt 0.2 deg for tilt under 30 deg. Pressure 0.5 per cent of full scale. Maximum
  sampling rate 1 Hz.
* **Marine and submersible suitability** Yes. Depth rating 500 m.
* **Deployment duration** Battery packs of 50 Wh alkaline, 165 Wh lithium or 76 Wh
  lithium-ion, one to three packs. Endurance in hours or months: `unknown`, it depends on
  the sampling scheme and no duty-cycle table was retrieved.
* **Physical interface** Cabled or self-recording; 16 GB internal memory.
* **Application protocol** "RS-422 (inquire for RS-232)", 9600 baud to 1.2 Mbaud. No HTTP,
  no MQTT, no REST. Message formats: `unknown` from this page; a separate Nortek
  integrator manual exists and was not retrieved.
* **SDK or software** Nortek Deployment Software, Storm 2 post-processing, online data
  display. A programmatic SDK: `unknown`.
* **Power** 9 to 24 VDC input, maximum peak current 4.5 A.
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://www.nortekgroup.com/products/aquadopp2-500m>, retrieved
  2026-09-08, `FETCHED_OK`.
* **Limitations** A single-point meter gives one velocity at one height, not the near-bed
  shear that actually drives scour and resuspension over a mat. A 500 m depth rating is
  far beyond a coastal hotspot and is paid for.
* **Suitability for this application** **VERIFIED** for the `Forcing` channel: it measures
  what `Parameter.CURRENT_EAST` and `CURRENT_NORTH` mean. It constrains no chemistry.

### S-02 Sonardyne Origin 65 ADCP (Type 8323)

* **Supplier** Sonardyne. **Country** United Kingdom, **European non-EU**.
  **Manufacturer.**
* **Exact model** Origin 65 ADCP, Type 8323.
* **What it actually measures** Current profiles by acoustic Doppler; integrates
  pressure-inverted-echosounder measurements for time of flight and sound velocity.
* **Published specification** 62.5 kHz operating frequency; "800+ m (depending on water
  environment)" profiling range; "4,100 m depth rating"; output formats "PD0, A gram,
  B gram; simultaneous output".
* **Marine and submersible suitability** Yes, seabed-mounted, free-fall deployment and
  recovery.
* **Deployment duration** "504 Ah dual battery" lithium primary; the page gives
  "6 weeks/2 year" for full-rate and scheduled operation respectively.
* **Physical interface** Seabed frame; "RS232, Ethernet and acoustic modem"; integrated
  LMF 14 to 19 kHz acoustic modem and integrated acoustic release.
* **Application protocol** RS232 and **Ethernet**. It carries an embedded web user
  interface, Origin Portal, and supports "Edge computing with customizable apps via
  Software Development Kit".
* **SDK or software** Origin Portal (embedded web UI), Origin Scheduler, Origin Viewer,
  Origin Topside for remote acoustic configuration, plus the named SDK.
* **Power** Internal lithium primary battery, 504 Ah dual pack.
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://www.sonardyne.com/product/origin-65-adcp/>, retrieved 2026-09-08,
  `FETCHED_OK`.
* **Limitations** 62.5 kHz is a long-range, coarse-cell configuration. In the
  demonstrator's 5 m mixing depth it would resolve almost nothing. The instrument is sized
  for a different problem.
* **Suitability for this application** **UNKNOWN**, and probably poor on frequency
  grounds. Recorded because it is the clearest verified example of a seabed instrument
  with Ethernet, an embedded web interface, an acoustic back channel and a published SDK.
  That combination is what `docs/handoffs/research_sensors.md` proposes the software
  branches emulate.

### S-03 Aanderaa DCPS 5400 and DCS 4520 family

* **Supplier** Aanderaa Data Instruments AS, part of Xylem. **Country** Norway,
  **European non-EU**. **Manufacturer.**
* **Exact models** Doppler Current Profiler Sensor 5400 / 5400R (300 m), 5400P (with
  integrated pressure), 5402 / 5402R (4500 m), 5403 / 5403R (6000 m); Doppler Current
  Sensor 4420, 4520, 4830, 4930 and their R variants; in-line ZPulse 5800 family.
* **What it actually measures** Current speed and direction, sea temperature; acoustic
  waves on the 5400P; built-in compass and tilt sensor with "integrated compensation for
  tilting and movement".
* **Published range** DCS speed range "0 to 300 cm/s". Accuracy figures are **not** given
  on the page retrieved: `unknown`.
* **Marine and submersible suitability** Yes; depth ratings by model as listed above.
* **Deployment duration** `unknown` from the page retrieved.
* **Application protocol** "serial or AiCap bus" for the DCPS; RS-232, AiCaP CANbus and
  RS-422 options depending on model. AiCaP is a proprietary CANbus protocol. No HTTP,
  MQTT or REST.
* **SDK or software** `unknown` from the page retrieved.
* **Power** `unknown` from the page retrieved.
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://www.aanderaa.com/stand-alone-current-sensor>, retrieved
  2026-09-08, `FETCHED_OK`. A separate operating manual, TD 304, exists at
  <https://www.aanderaa.com/media/pdfs/td304-manual-dcps.pdf> and was not retrieved.
* **Limitations** The landing page is a family overview. Every number needed for a
  purchase decision is in the per-model manual, which was not read.
* **Suitability for this application** **UNKNOWN** until the manual is read.

## Temperature

### S-04 Star-Oddi DST centi-TD

* **Supplier** Star-Oddi Ltd, Skeidaras 12, 210 Gardabaer. **Country** Iceland,
  **European non-EU** (European Economic Area). **Manufacturer.**
* **Exact model** DST centi-TD.
* **What it actually measures** Temperature and pressure (depth). Nothing else.
* **Published specification, verbatim from the data sheet** Size 15 mm x 46 mm (max
  diameter 17 mm); housing alumina (ceramic); weight 19 g in air, 12 g in water; data
  resolution 12 bits; temperature range -2 to +40 degC; temperature resolution
  0.032 degC; temperature accuracy +/-0.1 degC; temperature response time constant (63 per
  cent) reached in 20 s; standard depth ranges 0.1 to 50 m, 0.1 to 100 m, 1 to 270 m,
  5 to 800 m, 5 to 1500 m, 10 to 3000 m; depth resolution 0.03 per cent of selected range;
  depth accuracy +/-0.6 per cent of selected range; memory non-volatile EEPROM, 174,000
  measurements, optionally 524,068; minimum measuring interval 0.1 s; burst option 10 Hz;
  up to 7 different intervals.
* **Marine and submersible suitability** Yes: "Easy to mount on subsea gear, fishing nets,
  and moorings for short or long-term studies in oceans, lakes and boreholes."
* **Deployment duration** Battery life is stated elsewhere as up to 9 years at a 10 minute
  interval (`SEARCH_INDEX_ONLY`; the data sheet pages read do not carry that figure, so it
  is recorded as reported and unverified).
* **Physical interface** Sealed capsule; no connector in the water. Required accessories:
  "PC Communication Cable, SeaStar Windows software"; optional polyurethane or stainless
  steel protective housing.
* **Application protocol** **None in the water.** Data are read out over a PC cable after
  recovery. There is no serial telemetry, no Modbus, no SDI-12 and no API.
* **SDK or software** SeaStar for Windows. A programmatic SDK: `unknown`.
* **Power** Internal battery, not user-specified on the sheet read.
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://www.star-oddi.com/media/1/dst-centi-td.pdf>, retrieved 2026-09-08,
  `FETCHED_PDF`, two pages read.
* **Limitations** Recovered-data only. Nothing it records can inform a decision until
  someone lifts it. In the contract's terms, `available_at_utc` equals the recovery time,
  not the observation time, and the availability gate in `observations/records.py` must be
  fed accordingly.
* **Suitability for this application** **VERIFIED** as a cheap, redundant, per-tile
  temperature and depth record. It is exactly the right instrument for `SEDIMENT_TEMPERATURE`
  and for detecting a gross depth change, and exactly the wrong one for anything needing a
  timely answer.

## Salinity, conductivity, pH and turbidity

### S-05 Aqualabo Digital sensor CTZN

* **Supplier** Aqualabo, Champigny-sur-Marne. **Country** France, **EU**.
  **Manufacturer.**
* **Exact model** Digital sensor CTZN.
* **What it actually measures** Conductivity, salinity and temperature, by "an inductive
  method with ring-type coils".
* **Analyte and fraction** Not a chemical analyte in the contract's sense.
  `Parameter.CONDUCTIVITY`, `SALINITY`, `TEMPERATURE`; `QuantityKind.CONTEXT`.
* **Published range** Conductivity "Ranges from 0 to 100 mS/cm". Accuracy: `unknown` from
  the page retrieved.
* **Marine and submersible suitability** 100 mS/cm covers full-strength seawater at about
  53 mS/cm with headroom. IP68. **A pressure or depth rating was not published on the page
  retrieved: `unknown`.** IP68 is not a deployment depth.
* **Deployment duration** `unknown`. The inductive cell is described as fouling-resistant
  and consumable-free, which is a maintenance advantage but not a duration.
* **Physical interface** Cabled digital sensor.
* **Application protocol** "Modbus RS-485 and SDI12 digital communication". Register map:
  `unknown`. No HTTP, MQTT or REST.
* **SDK or software** `unknown`.
* **Power** `unknown` from the page retrieved.
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://www.aqualabo.fr/en/produit/digital-sensor-ctzn/>, retrieved
  2026-09-08, `FETCHED_OK`.
* **Limitations** Everything needed for an integration (register addresses, scaling, byte
  order, pressure rating, cable length limits) is in a manual that was not retrieved.
* **Suitability for this application** **UNKNOWN** pending the depth rating. As a
  context and QC channel the measurement itself is right.

### S-06 Aqualabo Digital sensor PHEHT

* **Supplier** Aqualabo. **Country** France, **EU**. **Manufacturer.**
* **Exact model** Digital sensor PHEHT (also sold as a PHEHT and PHT monobloc).
* **What it actually measures** pH, redox potential (ORP) and temperature.
* **Published range** pH 0.00 to 14.00; redox -1000 to +1000 mV; temperature 0 to
  +50.00 degC. Accuracy: not published on the manufacturer page retrieved; `unknown`.
  Third-party listings state RS485 Modbus or SDI-12, 5 to 12 V supply, maximum 5 bar and
  IP68; those figures are `SEARCH_INDEX_ONLY` and are recorded as reported.
* **Marine and submersible suitability** Partial. A 5 bar rating, if confirmed, is about
  40 m of water, which is adequate for a coastal hotspot. **Seawater pH measurement is a
  known hard problem**: a glass electrode in seawater needs a total-scale calibration and
  drifts. No seawater accuracy statement was found.
* **Deployment duration** `unknown`. The reference is described as long-life with a
  changeable Plastogel cartridge, so it is a consumable.
* **Application protocol** Modbus RTU over RS-485, and SDI-12 per third-party listings.
  Register map: `unknown`.
* **SDK or software** `unknown`. Calibration and history are stored in the sensor.
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://www.aqualabo.fr/en/produit/digital-sensor-pheht/>, retrieved
  2026-09-08, `FETCHED_OK`.
* **Limitations** pH and redox are the two channels the methylmercury risk term in
  `MODEL_SPEC` section 11 would most like to have, and they are also the two hardest to
  keep trustworthy on a multi-year seabed deployment. Redox in particular is an
  operationally defined, poorly reproducible quantity in sediment.
* **Suitability for this application** **UNKNOWN**. Usable as a context and QC channel.
  It must never be used to infer a metal concentration (`AGENTS.md` rule 5).

### S-07 Aqualabo NTU Sensor

* **Supplier** Aqualabo. **Country** France, **EU**. **Manufacturer.**
* **Exact model** NTU Sensor. A lower-range sibling, LowTuS, also exists.
* **What it actually measures** Turbidity by "90 degree infrared light-scattering
  nephelometry", suspended solids, and medium temperature.
* **Published range** Turbidity 0 to 4000 NTU across four auto-selected ranges; suspended
  solids 0 to 4500 mg/L. Accuracy: `unknown` from the page retrieved. ISO 7027 compliance
  is stated in third-party listings only (`SEARCH_INDEX_ONLY`).
* **Marine and submersible suitability** IP68 stated. Pressure or depth rating:
  `unknown`. An optional HYDROCLEAN automatic cleaning system is offered, which matters on
  a multi-month benthic deployment.
* **Application protocol** Modbus RTU over RS485, and SDI-12. Register map: `unknown`.
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://www.aqualabo.fr/en/produit/ntu-sensor/>, retrieved 2026-09-08,
  `FETCHED_OK`.
* **Limitations** Turbidity is a resuspension and QC channel only. It carries no metal
  information whatever. It is also the channel most likely to be misread as a
  contamination signal by a non-specialist audience, which is precisely why
  `AGENTS.md` rule 5 exists.
* **Suitability for this application** **UNKNOWN** pending a depth rating; the measurement
  itself is right for detecting resuspension events over a mat.

## Sensor carrier and logger

### S-08 nke Instrumentation MoSens

* **Supplier** nke Instrumentation, 6 rue Gutenberg, ZI Kerandre, 56700 Hennebont.
  **Country** France, **EU**. **Manufacturer.** ISO 9001:2015 stated on the page.
* **Exact model** MoSens.
* **What it actually measures** Nothing by itself. It is a compact carrier for the
  manufacturer's WiMo smart sensors, with tool-free connection and calibration values
  retained in the sensor.
* **Application protocol** "Modbus communication". Which registers, which function codes,
  which framing: `unknown`. The user manual is "available on request".
* **Power** "9-16 VDC power input" with "very low power consumption".
* **Marine and submersible suitability** Depth rating not stated on the page: `unknown`.
* **Deployment duration** `unknown`.
* **SDK or software** `unknown`. An embedded configuration interface is not a public API.
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://nke-instrumentation.com/produit/mosens/>, retrieved 2026-09-08,
  `FETCHED_OK`.
* **Limitations** Which WiMo sensors are available, and their individual ranges and
  ratings, were not established. A carrier is only as good as the sensors on it.
* **Suitability for this application** **UNKNOWN**. It is the most plausible French
  aggregation point for the physical channels, and it is the record with the largest gap
  between "looks right" and "verified".

## Lead

### S-09 Idronaut VIP, Voltammetric In-situ Profiling system

* **Supplier** Idronaut S.r.l., Brugherio, Milan area. **Country** Italy, **EU**.
  **Manufacturer.**
* **Exact model** VIP; a VIPPlus variant is referenced in the repository's existing
  reference register.
* **What it actually measures** Anodic stripping voltammetry at a mercury-plated
  iridium-based gel-integrated microelectrode array, protected by an antifouling agarose
  gel membrane. The leaflet recorded in `docs/REFERENCES.md` [S19] lists the analytes as
  **Cu, Pb, Cd and Zn**.
* **THE TRAP, STATED EXPLICITLY** The mercury in this instrument is the **working
  electrode material**, not the analyte. A mercury-film electrode used to measure lead is
  not a mercury sensor. Any document that lists this instrument under "mercury" is
  reading the electrode, not the measurement.
* **Analyte and fraction** Pb, Cd, Cu, Zn as the **dynamic or labile** fraction, an
  operationally defined pool. In the contract this is `Fraction.LABILE`, and it is
  **not** interchangeable with `Fraction.DGT_LABILE` or with
  `Fraction.TOTAL_RECOVERABLE`.
* **Published range or limit** `unknown`. No detection limit in any matrix was verified
  during this snapshot.
* **Marine and submersible suitability** A peer-reviewed review states that
  "The VIP/TracMetal provides nice analytical performances in seawater or estuarine
  conditions due to the high salinity, constant pHs and small NOM concentrations", and
  that VIP "has been developed by Geneva University and commercialized by Idronaut for
  more than two decades" (Pinheiro and Rotureau 2023, `FETCHED_OK`). Depth: profiling to
  500 m per `SEARCH_INDEX_ONLY` sources.
* **Deployment duration** `unknown`. See S-19 for a published limit on the related
  TracMetal probe.
* **Application protocol** RS232 with vendor software, per the archived leaflet recorded
  in `docs/REFERENCES.md` [S20]. Not verified in this snapshot.
* **Commercial status** `HISTORICAL_EVIDENCE`. **The manufacturer's own domain could not
  be reached on 2026-09-08.** `https://www.idronaut.it/`,
  `https://www.idronaut.it/research-projects/` and the VIP leaflet PDF at
  `https://www.idronaut.it/wp-content/uploads/2019/06/Vip-Leaflet.pdf` all failed with a
  TLS certificate verification error (`FETCH_TLS_FAIL`). Current orderability is therefore
  **not established**.
* **Evidence** Pinheiro, J.P. and Rotureau, E. (2023), *Molecules* 28(6):2831,
  DOI 10.3390/molecules28062831, <https://pmc.ncbi.nlm.nih.gov/articles/PMC10056914/>,
  retrieved 2026-09-08, `FETCHED_OK`. Manufacturer URLs as above, all `FETCH_TLS_FAIL`.
* **Limitations** No mercury analyte. Unknown detection limit. Unknown current
  availability. Consumables and electrode maintenance unknown. A gel membrane on a benthic
  deployment for months is an unanswered question.
* **Suitability for this application** **UNKNOWN.** It is the only instrument in this
  matrix that could in principle give an in-situ, near-real-time lead number in seawater,
  and not one of the numbers needed to plan a deployment could be verified.

### S-10 Metrohm 884 Professional VA with bismuth drop electrode

* **Supplier** Metrohm AG, Herisau. **Country** Switzerland, **European non-EU**.
  **Manufacturer.**
* **Exact model** 884 Professional VA (2.884.0110, manual for MME), with electrode
  equipment 6.5339.080 including the Bi drop electrode 6.0346.000, Ag/AgCl reference
  6.0728.120 and glassy carbon auxiliary 6.1247.000; `viva 2.1` software 6.6065.21X.
  Method: Application Bulletin 438/1, version 202103.
* **What it actually measures** Cadmium and lead by anodic stripping voltammetry in an
  acetate buffer at pH 4.6, quantified by two standard additions.
* **Analyte and fraction** Free ionic Cd and Pb released under the method conditions. Not
  a total-recoverable determination unless the optional UV digestion is applied.
* **Published limits, verbatim** "The limit of detection is 0.1 microgram/L for Cd and
  0.5 microgram/L for Pb." Working range "beta(Cd) = 0.1-15 microgram/L and beta(Pb) =
  0.5-15 microgram/L" with a 60 s deposition time.
* **THE SECOND TRAP, STATED EXPLICITLY** The bulletin lists "Tap water, mineral water, and
  sea water" as samples, and it says "This method is best suited for tap water and mineral
  water samples." Its own results table reports, for lead:

  | Sample | beta(Pb2+) microgram/L | RSD | Recovery |
  |---|---|---|---|
  | Tap water spiked 2 microgram/L Pb | 2.3 | 3% | 111% |
  | Mineral water spiked 2 microgram/L Pb | 1.92 | 2% | 96% |
  | Sea water | < LOD | | |
  | **Sea water spiked 2 microgram/L Pb** | **-** | **-** | **-** |

  The spiked sea-water lead row is **blank in the manufacturer's own bulletin**. Spiked
  sea-water cadmium recovered at 82 per cent, the worst of the three matrices. A published
  0.5 microgram/L lead detection limit is therefore emphatically not a sea-water figure,
  and this is the cleanest available proof of that rule.
* **Marine and submersible suitability** **None.** It is a benchtop laboratory system.
  10 mL of sample plus 1 mL of supporting electrolyte, 5 minutes of purging, standard
  additions, an optional 90 minute UV digestion at 90 degC for organic-rich samples.
* **Deployment duration** Not applicable.
* **Application protocol** Laboratory instrument driven by `viva` software over a PC link.
  No field protocol. Export format: `unknown`.
* **Commercial status** `CURRENT_LISTING` for the instrument family.
* **Evidence** <https://www.metrohm.com/content/dam/metrohm/shared/documents/application-bulletins/AB-438_1.pdf>,
  retrieved 2026-09-08, `FETCHED_PDF`, four pages read. Product page
  <https://www.metrohm.com/en/products/voltammetry/professional-va.html>,
  `SEARCH_INDEX_ONLY`.
* **Limitations** As published, the method does not deliver a validated sea-water lead
  result. Other Metrohm methods exist (scTRACE Gold with a silver film, screen-printed
  electrodes) and were not evaluated.
* **Suitability for this application** **NOT SUITABLE as published** for sea-water lead.
  Suitable as a laboratory Pb route only if a sea-water-validated Metrohm method is
  obtained, or if analysis is contracted to an accredited laboratory using ICP-MS with a
  matrix-matched method.

## Mercury

### S-11 Milestone DMA-80 evo direct mercury analyser

* **Supplier** Milestone Srl. **Country** Italy, **EU**. **Manufacturer.**
* **Exact model** DMA-80 evo.
* **What it actually measures** Total mercury by thermal decomposition, gold amalgamation
  and atomic absorption with a double-beam spectrophotometer. No sample preparation and no
  chemical addition.
* **Analyte and fraction** Total Hg. In contract terms `Fraction.TOTAL_RECOVERABLE` at
  best, and in practice total mercury in the mass introduced. **It is not a
  methylmercury method** and it is not a dissolved-fraction method.
* **Published limits** Compliance with EPA method 7473, ASTM D-6722-01 and D-7623-10.
  Detection capability described as "ppt level"; a detection limit "as low as 0.0003 ng"
  with a range to 30,000 ng appears in `SEARCH_INDEX_ONLY` sources. Because a mass
  detection limit converts to a concentration only through the sample size, the
  concentration limit in a sea-water matrix is `unknown`.
* **Marine and submersible suitability** **None.** Laboratory bench instrument.
* **Analysis time** About 5 to 6 minutes per sample.
* **Application protocol** Laboratory instrument, PC-controlled. Export format and any
  API: `unknown`.
* **Commercial status** `INDEXED_LEAD_ONLY`. **Both manufacturer routes failed on
  2026-09-08**: `https://www.milestonesci.com/direct-mercury-analyzer/` returned HTTP 403
  and `https://www.milestonesrl.com/products/mercury-determination/dma-80-evo` and
  `https://www.milestonesrl.com/en/products/mercury-determination/dma-80-evo` failed TLS
  certificate verification.
* **Evidence** Third-party equipment directory
  <https://www.azom.com/equipment-details.aspx?EquipID=9242>, retrieved 2026-09-08,
  `FETCHED_OK`, which reproduces manufacturer information. This is a directory listing,
  not the manufacturer's own page.
* **Limitations** Sea-water total mercury at ambient levels is typically sub-ng/L and
  needs preconcentration; a direct thermal method is normally applied to solids and to
  concentrated liquids. Whether the DMA-80 evo can reach ambient sea-water levels without
  preconcentration is `unknown` and should be assumed to be no.
* **Suitability for this application** **UNKNOWN**. Plausible for the retrieved-media
  assay channel (`Matrix.SORBENT`, `QuantityKind.SOLID_LOADING`), where the sample is a
  loaded solid and the mercury is concentrated. Not established for water samples.

### S-12 P S Analytical PSA 10.035 Millennium Merlin

* **Supplier** P S Analytical Ltd, Orpington, Kent. **Country** United Kingdom,
  **European non-EU**. **Manufacturer.**
* **Exact model** PSA 10.035 Millennium Merlin; siblings 10.025 and 10.045; an on-line
  variant PSA 10.226 Online Merlin also exists.
* **What it actually measures** Total mercury by vapour generation and atomic fluorescence
  spectrometry, with an on-board gold pre-concentration trap on the 10.035.
* **Analyte and fraction** Total Hg in a prepared water sample.
* **Published limits** `SEARCH_INDEX_ONLY`: developed for EPA Method 1631, "typically used
  for water samples where a detection limit below 0.05ppt is required", with "routine
  detection limits of 0.01ppt" achievable. **The matrix in which those limits apply is not
  established, and Method 1631 is written for water including sea water but requires
  specified clean-hands sampling, preservation and oxidation.** Treat the numbers as
  vendor-reported and matrix-unspecified.
* **Marine and submersible suitability** **None.** Laboratory bench instrument.
* **Application protocol** `unknown`. Export format and API `unknown`.
* **Commercial status** `INDEXED_LEAD_ONLY`. Every retrieval route attempted on
  2026-09-08 returned HTTP 403:
  `https://www.psanalytical.com/products/millenniummerlin1631.html`,
  `http://psanalytical.com/elements/hg`, and the deep product URL recorded in
  `docs/REFERENCES.md` [S21]. This repeats the failure already noted in that register, so
  the situation has not improved since the previous snapshot.
* **Evidence** Search-index summaries only, retrieved 2026-09-08.
* **Limitations** Nothing about this instrument has been verified from a retrievable
  primary page during this snapshot. Sample handling for ultra-trace mercury dominates the
  achievable limit far more than the instrument does.
* **Suitability for this application** **UNKNOWN**. Retained as the strongest lead for a
  laboratory total-mercury route, and as a live example of why "historical evidence is not
  current orderability" is a rule and not a slogan.

### S-19 TracMetal and the Au-GIME Hg(II) sensor

* **Supplier** University of Geneva, Tercier-Waeber group. **Country** Switzerland,
  **European non-EU**. **Research group**, not a manufacturer or distributor.
* **Exact system** TracMetal, a submersible multichannel probe integrating Hg-plated and
  gold-nanofilament gel-integrated microelectrode arrays in a three-channel flow cell with
  a multichannel peristaltic pump. The mercury sensing chemistry is described in
  Tercier-Waeber et al. (2021), *In Situ Voltammetric Sensor of Potentially Bioavailable
  Inorganic Mercury in Marine Aquatic Systems Based on Gel-Integrated Nanostructured
  Gold-Based Microelectrode Arrays*, ACS Sensors 6(3):925-937,
  DOI 10.1021/acssensors.0c02111.
* **What it actually measures** In-situ voltammetric determination of the **potentially
  bioavailable** fraction of Hg(II), As(III), Cd(II), Pb(II), Cu(II) and Zn(II).
* **Important distinction** Here mercury **is** the analyte, on the gold channel. The
  Hg-plated channel is still an electrode for the other metals. Both roles coexist in the
  same instrument, which is exactly why the electrode-versus-analyte confusion persists in
  this field.
* **Published limits** `unknown` from the sources retrieved.
* **Marine and submersible suitability** Deployed in Arcachon Bay on the French Atlantic
  coast (`SEARCH_INDEX_ONLY`).
* **Deployment duration** A 2024 review reports that underwater in-situ continuous
  operation of such analysers "has not exceeded 10 days" (`SEARCH_INDEX_ONLY`, see
  limitations).
* **Application protocol** `unknown`.
* **Commercial status** `RESEARCH_PROTOTYPE`. **It cannot be ordered.** No supplier,
  price, lead time or support arrangement was found.
* **Evidence** Pinheiro and Rotureau (2023), *Molecules* 28(6):2831,
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC10056914/>, `FETCHED_OK`;
  *Review of Underwater In Situ Voltammetry Analyzers for Trace Metals*, Chemosensors
  12(8):158 (2024), <https://www.mdpi.com/2227-9040/12/8/158>, `FETCH_403` on 2026-09-08,
  so its statements are `SEARCH_INDEX_ONLY`; ACS Sensors page
  <https://pubs.acs.org/doi/10.1021/acssensors.0c02111>, not retrieved.
* **Limitations** A research instrument, a ten-day operational ceiling as reported, a
  pumped flow cell with a peristaltic pump on a benthic deployment, and no commercial
  support path.
* **Suitability for this application** **NOT a purchasable option.** Recorded because it
  is the only verified evidence that in-situ dissolved Hg(II) measurement in seawater is
  physically possible at all, and because it is the correct citation to use if anyone asks
  whether a continuous mercury sensor exists.

## Passive and DGT-type metal monitoring

### S-13 DGT Research LSPM-NP sediment DGT device

* **Supplier** DGT Research Ltd, Summer Cottage, Cockerham Road, Bay Horse, Lancaster
  LA2 0HF. **Country** United Kingdom, **European non-EU**. **Manufacturer.**
* **Exact model** LSPM-NP, "For metals (cationic) in sediments using a Chelex BL". A
  solution variant LSNM-NP exists for waters.
* **What it actually measures** Time-integrated accumulation of cationic metals onto a
  Chelex binding layer behind a 0.8 mm APA diffusive gel and a polyethersulphone filter
  membrane. The device measures an **accumulated mass over an exposure window**, not a
  concentration at an instant.
* **Analyte and fraction** "up to 30 metals, including Cd, Co, Cu, Fe, Mn, Ni, Pb, Zn".
  The fraction is **DGT-labile**, which is `Fraction.DGT_LABILE` in the contract and is
  operationally different from voltammetric `Fraction.LABILE` and from
  `Fraction.TOTAL_RECOVERABLE`. `AGENTS.md` and `MODEL_SPEC` section 8 already forbid
  merging them, and this record is the reason.
* **Mercury** Not listed among the metals on this product page. A DGT for mercury requires
  a different binding layer. Whether DGT Research currently sells one was **not
  established**: `unknown`.
* **Published limits** `unknown`. A DGT limit of detection depends on the exposure time,
  the diffusion coefficient, the gel area and the analytical method used on the eluate, so
  there is no single device figure.
* **Marine and submersible suitability** Designed for deployment in sediment. Salinity
  suitability for Chelex-based DGT in seawater is a known research topic and was not
  verified here: `unknown` at the vendor level.
* **Deployment duration** Not stated on the product page: `unknown`. Typical published
  sediment deployments are of the order of days, which is consistent with
  `ObservationConfig.dgt_exposure_s = 3 days`.
* **Physical interface** A passive plastic device. No cable, no power, no protocol.
* **Application protocol** **None.** It is chemistry, not electronics.
* **Laboratory chain required** Yes: retrieval, elution and instrumental analysis, in
  practice ICP-MS. This is the source of `ObservationConfig.lab_latency_s`.
* **Price** £73.00 listed on the product page on 2026-09-08. Recorded because it is a
  published list price on the manufacturer's own page, not a quotation. It carries no
  shipping, no analysis and no VAT.
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://www.dgtresearch.com/product/lspm-loaded-dgt-device-for-metals-a-in-sediment/>,
  retrieved 2026-09-08, `FETCHED_OK`. Detailed user guide referenced at
  <https://www.dgtresearch.com/detailed-user-guides/cations-oxyanions-FeO-guide-A2-2020.pdf>,
  not retrieved.
* **Limitations** Integrated, not instantaneous. Lead only among our two elements. Needs a
  laboratory. Gives a bound-free number but on a different pool from every other channel.
* **Suitability for this application** **VERIFIED** as the time-integrated porewater lead
  channel that `MODEL_SPEC` section 8 already describes, provided the estimator treats it
  as `QuantityKind.ACCUMULATED_MASS` over `sampling_start_utc` to `sampling_end_utc` and
  never as a point ng/L.

## Benthic flux chambers and landers

### S-14 Unisense MiniChamber Lander System

* **Supplier** Unisense A/S. **Country** Denmark, **EU**. **Manufacturer.**
* **Exact model** MiniChamber Lander System. Siblings: DeepSea Lander System, MiniProfiler
  MP4/8, Eddy Covariance System.
* **What it actually measures** In-situ benthic chamber incubation: a lid closes over an
  enclosed patch of seabed and microsensors in the lid record the change in the enclosed
  water. Sensors named: O2, H2, N2O, pH and H2S.
* **Analyte and fraction** **Not metals.** The listed microsensor set contains no Pb and
  no Hg channel. A metal flux from such a chamber would require water sub-samples drawn
  during the incubation and analysed in a laboratory, which is a different workflow from
  the electrode set that is sold with it.
* **Published specification** "Continuous deployment down to 300 m, optionally deep-sea
  deployment down to 6,000 m". Chamber enclosed area and volume: **not stated on the page
  retrieved**, and without an area a chamber cannot produce an areal flux. That is exactly
  why `ObservationRecord.chamber_area_m2` exists in the contract.
* **Deployment duration** `unknown`.
* **Physical interface** Lander frame with a "Powerful Field DataLogger", "Ready for
  optodes and RS-232 devices".
* **Application protocol** RS-232 for guest devices; the logger is programmed "via an easy
  and intuitive PC software interface". A public API: `unknown`.
* **Power** `unknown`.
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://unisense.com/products/minichamber-lander-system/>, retrieved
  2026-09-08, `FETCHED_OK`. Related: <https://unisense.com/products/deepsea-lander-system/>,
  and KC Denmark lander frames at
  <https://www.kc-denmark.dk/products/autonomus-benthic-lander/lander-frames/rectangular-lander.aspx>,
  neither retrieved in detail.
* **Limitations** A chamber measures the flux of the patch it encloses, which on a tiled
  mat means one tile at most and probably less. It changes the hydrodynamics of the patch
  it encloses, which is a known chamber artefact and matters here because our layer is
  advection-driven: enclosing the water can suppress the very seepage the flux depends on.
* **Suitability for this application** **UNKNOWN for metals as sold.** The
  `AcquisitionKind.BENTHIC_CHAMBER` channel in the contract is the only one that measures
  `J_out` directly, so this is the most valuable record in the matrix and also the one
  with the largest unresolved gap. Establishing whether a chamber plus timed water
  sub-sampling plus laboratory Pb and Hg can give a defensible areal flux over a reactive
  mat is the single highest-value question in `vendor_questions.md`.

## Sediment porewater samplers

### S-15 Rhizosphere Research Products Rhizon CSS

* **Supplier** Rhizosphere Research Products. **Country** Netherlands, **EU**.
  **Manufacturer** (the page carries the company's own copyright; the site does not state
  a town, so the address is `unknown` from the page retrieved).
* **Exact models** Standard Rhizon types SMS, MOM, CSS and Flex; also MacroRhizon
  (4.5 mm, female luer lock) and MicroRhizon (1.2 mm outer diameter, 8 mm membrane,
  0.15 micrometre pore size, steam-sterilisable).
* **What it actually measures** Nothing. It extracts porewater through a hydrophilic
  microporous polymer tube under vacuum, for laboratory analysis.
* **Published specification** Standard Rhizons: outer diameter 2.5 mm; membrane length
  5 cm or 10 cm; pore sizes 0.15 and 0.60 micrometres. Application: "sampling pore water
  in pots, vessels, cylinders or columns filled with settled soil, or in undisturbed cores
  and sediments".
* **Analyte and fraction** Whatever the laboratory measures on the filtrate. Operationally
  this is a filtered dissolved fraction whose cut-off is the membrane pore size, so it maps
  to `Fraction.DISSOLVED_FILTERED`, **not** to `Fraction.LABILE` or
  `Fraction.DGT_LABILE`.
* **Marine and submersible suitability** Used routinely on marine sediment cores. In-situ
  seabed deployment through a mat: `unknown`.
* **Deployment duration** Instantaneous extraction, not an integrated sampler.
* **Application protocol** **None.**
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://www.rhizosphere.com/rhizons/rhizon-samplers/>, retrieved
  2026-09-08, `FETCHED_OK`. A widely used community description of the core-sampling
  variant is at <https://www.sedgeochem.uni-bremen.de/rhizon.html>, not retrieved.
* **Limitations** Trace-metal work through a polymer tube needs blank control: adsorption
  and leaching artefacts for metals are documented for Rhizon-type samplers in the
  literature and were **not** evaluated here. Do not assume clean trace-metal performance.
* **Suitability for this application** **VERIFIED** as a porewater extraction method for
  `Matrix.POREWATER` and `Matrix.MAT_POREWATER`, subject to a trace-metal blank study.
  This is the channel that constrains `C_sed`, the driving boundary condition of the whole
  layer model.

## Acoustic positioning

### S-16 Exail Gaps M5

* **Supplier** Exail. **Country** France, **EU**. **Manufacturer.**
* **Exact model** Gaps M5. Family members Gaps M3 and Gaps M7.
* **What it actually measures** Ultra-short-baseline acoustic position of a transponder
  relative to the transceiver, with an embedded Phins fibre-optic-gyroscope inertial
  system, plus acoustic telemetry.
* **Published specification** Operating range 995 m or 4,000 m variants; absolute accuracy
  "0.06% of slant range (CEP50)"; 200 degree aperture with above-horizontal tracking;
  "true calibration-free operation"; third-party transponder compatible.
* **Marine suitability** Yes, vessel- or ROV-mounted transceiver with subsea transponders.
* **Deployment duration** Not a permanent installation in the intended use.
* **Application protocol** `unknown` from the page retrieved. Positioning output formats
  are typically serial and Ethernet in this class, but that was not verified.
* **SDK or software** `unknown`.
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://www.exail.com/product-range/ultra-short-baseline-usbl-solutions>,
  retrieved 2026-09-08, `FETCHED_OK`. Third-party datasheets exist and were not used.
* **Limitations** Accuracy is a percentage of slant range, so at a 20 m coastal deployment
  0.06 per cent is a very small number and the practical accuracy will be dominated by
  sound-speed error, multipath off the seabed and transponder mounting, none of which is
  captured by the headline figure. `Parameter.MAT_DISPLACEMENT` needs centimetres to
  decimetres of certainty on a tile, and whether a USBL delivers that over a flat seabed
  is `unknown`.
* **Suitability for this application** **UNKNOWN.** It is the right class of instrument
  for `AcquisitionKind.ACOUSTIC_POSITION` and the wrong scale of problem statement.
  A short-baseline or a simple mechanical tell-tale may serve better and was not
  researched.

## ROV and inspection

### S-17 Blueye X3

* **Supplier** Blueye Robotics AS, Trondheim. **Country** Norway, **European non-EU**.
  **Manufacturer.**
* **Exact model** Blueye X3. A higher-specification X3 Ultra also exists.
* **What it actually measures** Visual inspection. HD tilt camera, 1920 x 1080, mechanical
  tilt -30 to +30 degrees, 115 degree vertical field of view. Onboard depth sensor
  (0 to 30 bar), temperature sensor, and a 3-axis IMU.
* **Analyte and fraction** None. This instrument produces `Qualifier.CATEGORICAL`
  condition classes and lengths, never chemistry.
* **Published specification** Depth rating "305 m / 1000 feet"; operational in "up to 2
  knots current"; endurance about 2 h standard or 5 h with the high-capacity battery;
  tether up to 300 m with 100 kg breaking strength.
* **Physical interface** Three guest ports supporting Ethernet, RS232, I2C, PWM and UART.
  Optional Water Linked DVL A50 and acoustic positioning add-ons.
* **Application protocol** Surface unit with WiFi to an iOS or Android application; guest
  ports as above.
* **SDK or software** **A published SDK exists.** The manufacturer names "The Blueye SDK";
  a Python SDK is maintained publicly on GitHub according to `SEARCH_INDEX_ONLY` sources,
  supporting custom payload control and mission scripting. The repository URL was not
  retrieved and the licence is `unknown`.
* **Power** Battery, rechargeable; specific capacity not recorded here.
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://www.blueyerobotics.com/rov/x3>, retrieved 2026-09-08,
  `FETCHED_OK`.
* **Limitations** Two knots is about 1.03 m/s. The demonstrator's tidal forcing peaks at
  `u_mean 0.04 + tidal_amplitude 0.18 = 0.22 m/s`, so the vehicle is not current-limited
  in this scenario, but visibility over a disturbed seabed will limit it long before
  current does. A visual survey cannot see burial depth under sediment, cannot see
  saturation, and cannot see fouling inside the layer.
* **Suitability for this application** **VERIFIED** for
  `AcquisitionKind.ROV_INSPECTION` producing `MAT_COVERAGE_FRACTION`,
  `MAT_DAMAGE_CLASS`, `MAT_TILT`, `MAT_DISPLACEMENT` and, with a probe or a scale bar,
  `BURIAL_DEPTH`. **Never** for chemistry.

### S-18 Subsea Tech ROV inspection and survey services

* **Supplier** Subsea Tech, Marseille. **Country** France, **EU**. **Manufacturer of
  ROVs and USVs, and a service provider**; the page states the company designs and
  manufactures its own equipment and operates it on client sites.
* **Exact service** Site Services: underwater inspection and measurement with ROVs on
  submerged infrastructure, 3D photogrammetry and modelling, bathymetric surveys with
  unmanned surface vessels, equipment rental and operator training.
* **Equipment named** Observation and inspection class ROVs Mini TORTUGA and TORTUGA
  (standard and XP4 versions); remotely operated catamarans Catarob, AirCAT, Cat-Surveyor
  and SeaCAT; multibeam and side-scan sonars, thickness measurement sensors and HD cameras.
* **Track record stated** "over 20 years of operations in France and internationally",
  "more than 180 missions completed", "over 80 public and private clients".
* **What it measures** Position, geometry and visual condition. No chemistry.
* **Commercial status** `CURRENT_LISTING`.
* **Evidence** <https://www.subsea-tech.com/prestations-services/>, retrieved 2026-09-08,
  `FETCHED_OK`. Company site <https://www.subsea-tech.com/>.
* **Limitations** No reference to sediment remediation, capping or contaminated-site work
  was found on the page retrieved. Day rates, mobilisation costs and availability:
  `unknown`. `CostConfig.rov_survey_eur = 4200.0` in this repository remains an
  **assumption** and no quotation exists.
* **Suitability for this application** **UNKNOWN.** It is the right kind of French
  supplier for a periodic condition survey, and nothing about a contaminated-sediment
  deployment has been established.

---

## The finding that matters most

**No practical, purchasable, continuous in-situ mercury sensor for seawater could be
verified. No purchasable, currently confirmed continuous in-situ lead sensor could be
verified either.**

* The only commercial in-situ lead instrument found, the Idronaut VIP (**S-09**), has an
  unreachable manufacturer website, no verified detection limit, and **no mercury
  analyte**: its mercury is the electrode.
* The only verified in-situ seawater mercury measurement, TracMetal / Au-GIME (**S-19**),
  is a university research system with a reported ten-day continuous-operation ceiling and
  no commercial path.
* The best-documented laboratory lead method retrieved (**S-10**) has a **blank cell**
  where its own sea-water spike recovery should be.
* The two laboratory mercury instruments (**S-11**, **S-12**) could not be confirmed from
  any retrievable manufacturer page on 2026-09-08.

### Therefore, the recommendation

**Continuous physical sensors plus passive and periodic chemical sampling.**

1. Continuous, telemetered or logged: current, temperature, conductivity and salinity, pH
   and redox, turbidity, differential head across the layer, and battery voltage. These
   are `CONTEXT_PARAMETERS` in the contract, they constrain conditions and QC, and
   `AGENTS.md` rule 5 forbids deriving chemistry from any of them.
2. Time-integrated chemistry: DGT for lead in porewater and in bottom water (**S-13**),
   read as `QuantityKind.ACCUMULATED_MASS` over a declared window.
3. Periodic discrete chemistry: Rhizon porewater extraction (**S-15**) and bottom-water
   grabs, analysed in an accredited laboratory by a sea-water-validated method, with a
   laboratory latency of weeks.
4. Periodic direct flux: benthic chamber incubation (**S-14**) with timed water
   sub-samples for laboratory Pb and Hg, subject to the open question in that record.
5. Periodic physical condition: ROV survey (**S-17**, **S-18**) plus bathymetry, giving
   coverage, damage class, tilt, displacement, burial and scour.
6. Retrieved-media assay at every service event: total Pb and Hg on the recovered medium
   (**S-11** as a candidate), which is the only channel that closes the mass ledger.

This is not a fallback. Given the evidence retrieved, it is the correct architecture, and
the demonstrator's observation schedule in `config.py` already has approximately the right
shape: hourly context, six-hourly bottom-water probe, ninety-day porewater, one-hundred-and-eighty-day
chamber, survey and DGT, and a twenty-one-day laboratory latency.

### What the demonstrator must therefore not do

Simulate a continuous, low-latency, in-water Pb or Hg reading and present it as
representative of an achievable pilot. `ObservationConfig.bottom_water_probe_period_s` is
six hours with a 20 per cent relative noise and a 12 ng/L limit of detection. **No
instrument in this matrix was verified to deliver that.** It is a `SYNTHETIC_DEMO`
channel, it must be labelled as one everywhere it appears, and the honest reading of this
research is that the six-hourly metal probe is the most optimistic assumption in the whole
configuration.
