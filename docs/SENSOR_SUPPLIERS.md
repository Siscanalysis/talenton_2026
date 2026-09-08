# European sensor and analytical-equipment shortlist

**Research snapshot: 8 September 2026.** This is a starting shortlist, not a quotation, purchase recommendation or confirmation of stock. “Listed” means a public manufacturer listing was found. Historical documents and pages that failed direct retrieval are explicitly separated. No supplier has been contacted.

France and Italy are EU-based options; Norway and the UK are European non-EU options. Exact hardware revisions, firmware and environmental ratings matter more than a generic brand name.

| Supplier / country | Candidate | Sensor utility and practical use | Published interface/software evidence | What remains to establish | Source/status |
|---|---|---|---|---|---|
| **nke Instrumentation / France, Brittany** | MoSens + selected WiMo sensors; WiMo sonde family | Environmental conditions and fouling-context channels. Regional supplier candidate for a compact monitoring assembly; not direct Pb/Hg detection | MoSens listing identifies Modbus; WiMo FAQ describes Modbus recording modes and family pages describe embedded configuration | Selected sensor parameters, electrical layer, exact register map, data/export access, marine depth rating, calibration and service interval. Do not equate an embedded web interface with a public API | [S13–S14], official listings; some support content may require access |
| **Aqualabo / France** | CTZN; exact pH/turbidity model as optional add-on | Conductivity/salinity/temperature for model context; optional pH/turbidity for contextual/QC evidence, not a metal estimate | CTZN explicitly lists Modbus RTU over RS485 or SDI12. Other sensors need their own manuals | Modbus addresses, units/scaling/endian order, pressure rating and anti-fouling requirements for the installation. IP68 alone does not identify a usable deployment depth | [S15–S16], official listings |
| **Nortek / Norway** | Aquadopp Generation 2 current meter or an appropriate profiler | Current speed/direction to interpret plume movement; choose profiler only when the vertical profile matters | Generation 2 documentation identifies RS422, NMEA option and changed binary formats; manufacturer software supports configuration/processing | Exact output messages and coordinate conventions, model/firmware, averaging, clock/time handling, integrator guide and power/cable configuration | [S17–S18], official current listings/docs |
| **IDRONAUT / Italy** | VIP, subject to current supplier confirmation | Candidate in-situ Pb channel for a defined operationally measured fraction. Archived work describes dynamic/labile-metal measurement, not universal total metals | Archived VIPPlus manual refers to RS232 and vendor software; legacy technical interface is not automatically a supported open SDK | Current orderability; supported chemical fraction, saline-matrix quantification limit, cycle time, calibration, electrode consumables, export/raw-data access and protocol manual. **No Hg analyte claim** | [S19–S20], historical manufacturer/project evidence; current availability unverified |
| **P S Analytical / UK** | PSA 10.035 Millennium Merlin | Laboratory Hg analysis of properly handled samples; a practical separate path for the initial demo | Manufacturer indexed listing connects the model to Method 1631. Full page retrieval failed; software export/API not verified | Current model, seawater method validation, matrix preparation, quantification limit, sample handling and result-export format. Not a submerged probe | [S21], official indexed lead; full-page/vendor confirmation needed |
| **P S Analytical / UK** | PSA 10.226 Online Mercury in Liquid Streams | Potential future topside/pumped-sample Hg analyser; not a compact in-water mesh sensor | Indexed manufacturer description includes sea-water applications; direct page retrieval failed. No primary-source protocol verification completed | Required conditioning/reagents/waste handling, true cycle time and detection capability; current output options; sampling-line delays. Use quote request, not guessed prices or protocols | [S22], unconfirmed shortlist lead; not minimum viable hardware |

## Minimum practical application

For the first software demonstration, emulate one environmental station, one current measurement and delayed target-specific chemistry results. For a future pilot, compare borrowing/renting a context sonde/current meter and purchasing laboratory analyses against owning specialised trace-metal analysers. Availability and cost remain questions, not numerical assumptions to present as quotations.

A simple electrical/protocol path could be: verified digital instrument → surface/logger gateway → timestamped records → common observation adapter. This is a proposed architecture. The vendor's RS485/RS422/RS232 signal is not MQTT or HTTP; any such interface would be supplied by a separately configured gateway. Do not simulate an undocumented vendor API as though it were real.

Use serial-file or CSV replay first. A read-only Modbus emulator can demonstrate ingestion without hardware; put `SIMULATED_PROTOCOL` on it, use our own register map, and do not brand the map as belonging to a manufacturer [S28].

## Research-agent output format

For every recommended exact model record: manufacturer and country; EU/non-EU; distributor versus manufacturer; parameter/analyte and chemical fraction; medium and salinity suitability; concentration/measurement range; quantification limit with units and matrix; instrument cycle versus output frequency; sampling preparation; power/depth/fouling requirements; physical link; application protocol; register/message/manual access; vendor software and export path; documented calibration; current commercial evidence/date; public price or `quote required`; source URL and limitations.

Assign one status: **CURRENT_LISTING**, **HISTORICAL_EVIDENCE**, **INDEXED_LEAD_ONLY**, **RESEARCH_PROTOTYPE**, or **NOT_SUITABLE**. Current listing still does not mean in stock. Distinguish manufacturer-claimed performance from independent validation.

## Questions to send in a future quotation request

Can the exact model quantify our chosen Pb or Hg fraction in unmodified seawater at the expected range? What preparation and analytical limit apply in that matrix? How often can valid independent results actually be obtained? Which documented digital outputs and register/message definitions can we use? Is a dated manual, example export and loan/rental trial available? What ongoing calibration, consumables, waste handling and servicing are required? What is the total installed and yearly operating cost?

Do not send enquiries automatically. The coding/research task is to assemble evidence and a draft request, not contact suppliers without permission.
