You are the supplier and software-reuse research agent for a two-day marine reactive-mesh demo. Work on `research/sensors` in your own worktree. Read `AGENTS.md`, the build brief, the data contract, `docs/SENSOR_SUPPLIERS.md` and `docs/REFERENCES.md`.

**Owned paths:** `docs/research/`, `data/vendor_evidence/` (metadata only, no restricted manuals), `docs/handoffs/research_sensors.md`. Suggest shared-doc edits in your handoff; do not change model contracts or dependencies.

## Task

Search European businesses actually offering the instrumentation or analytical service needed for a Pb/Hg mesh experiment. Prefer France/EU when suitability is comparable; include Norway/UK/Switzerland as European non-EU and distinguish manufacturers from distributors. Start with the supplied leads but verify them afresh. Historical evidence is not current orderability.

Output a compact **sensor → utility → practical application → software interface/protocol → business** matrix with primary-source citations and access dates. Target 5–8 relevant exact models/services, not a long product list. Required categories: current measurement; conductivity/salinity/temperature; optional pH/turbidity; Pb-capable chemical measurement; a realistic Hg laboratory/topside path. A viable outcome may be “no suitably documented submersible Hg option identified.” Do not invent one.

For each: specify analyte/fraction, medium/salinity evidence, measurement range, quantification limit and matrix, independent measurement cycle versus streaming frequency, sample conditioning, depth/power/fouling/calibration, physical interface, application protocol, documented register/message access, SDK/export/software restrictions, availability status and quote requirement. Unknowns stay unknown. Verify any numerical sensitivity against actual expected site ranges; do not use a fresh-water LOD as established sea-water performance.

Separate RS232/RS422/RS485, Modbus RTU, SDI12, NMEA, proprietary files and any surface-gateway API. Do not call a physical serial link an HTTP API. Do not transfer protocol details between revisions or product lines. A mercury-film electrode used to measure Pb is not evidence that it measures mercury.

Recommend a **minimum pilot measurement chain** and a **software-demo replay chain**. The latter can use synthetic observations and delayed lab records. Explain which fields can update transport, which can constrain capture, which only support condition monitoring and which states remain unobserved. Include two real incompatibility examples: labile versus total metals; passive integrated exposure versus a point reading.

Briefly assess reuse candidates in `docs/REUSE_AND_DATA.md`. Do not change the agreed FiPy-first build without coordinator approval. Verify relevant upstream/data licences and whether an official API/manual is actually accessible. No contact with suppliers and no purchases.

## Deliverables

Write `docs/research/sensor_matrix.md`, `measurement_chain.md`, and `vendor_questions.md`; a small evidence JSON with URL/date/status/claim; and a handoff. Use statuses CURRENT_LISTING, HISTORICAL_EVIDENCE, INDEXED_LEAD_ONLY, RESEARCH_PROTOTYPE or NOT_SUITABLE. Provide a draft quotation-request paragraph but do not send it.

Stop expanding the search when the minimum measurement plan and main gaps are clear. The end result must tell the coding agents which data to emulate, which interfaces could later be implemented, and what cannot yet be claimed—not merely name attractive sensors.
