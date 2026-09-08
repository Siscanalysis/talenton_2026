# Handoff: `research/sensors`

Branch `research/sensors`, worktree
`C:\Users\Artelnics\Desktop\TalentON_2026\software\worktrees\research`.
Research snapshot **8 September 2026**. No supplier was contacted.

This branch writes **no application code and no tests**, and it does not touch `src/` or
`tests/`. It produces documents, a machine-readable evidence set, and one standalone
script that reads only its own files.

---

## 1. Deliverables

| Path | What it is |
|---|---|
| `docs/PRIOR_ART.md` | The no-novelty position, with primary sources, and the differentiation hypothesis list |
| `research/materials/` | Seven source notes backing the prior art, with verbatim quotation separated from paraphrase |
| `research/sensors/sensor_matrix.md` | Nineteen supplier and service records, fully specified |
| `research/sensors/measurement_chain.md` | Minimum pilot chain, software replay chain, what each channel constrains, what stays unobserved, four worked incompatibilities |
| `research/sensors/vendor_questions.md` | Nineteen questions tied to specific recorded gaps, plus a draft quotation request **marked NOT SENT** |
| `research/references/evidence.json` | One JSON array, nineteen supplier records, exactly the eleven contract keys |
| `research/references/prior_art.json` | Seventeen prior-art source records. **An addition beyond the requested deliverables**, kept separate so `evidence.json` keeps exactly the requested shape |
| `research/summarise_research.py` | The runnable standalone example |

### Note on `examples/`

The definition of done asks for a runnable example under `examples/<yours>/`. `examples/`
is **not** an owned path for this branch, and this branch is instructed to write no
application code. The example therefore lives at `research/summarise_research.py`, inside
an owned path, and needs no map, no network, no hardware and nothing from `src/`. If the
coordinator wants it under `examples/research/`, moving the single file is sufficient and
no import path changes.

---

## 2. Public functions

Only one module contains code.

`research/summarise_research.py`

* `check_evidence(records: list[dict]) -> list[str]`
  Returns a list of problems, empty when `evidence.json` is well formed. It checks that
  every record carries exactly the eleven contract keys
  (`supplier`, `country`, `eu_member`, `model`, `measures`, `claim`, `url`,
  `access_date`, `retrieval_status`, `status`, `notes`), that `status` is one of the five
  frozen words, that `eu_member` is a boolean agreeing with the country, that `url` is an
  http(s) URL and that `access_date` is ISO `yyyy-mm-dd`.
* `main() -> int`
  Prints the summary and returns a process exit code.

Module constants worth reusing: `REQUIRED_KEYS`, `STATUS_VOCABULARY`, `EU_MEMBERSHIP`.

---

## 3. Exact run commands

```powershell
cd "C:\Users\Artelnics\Desktop\TalentON_2026\software\worktrees\research"
& "C:\Users\Artelnics\Desktop\TalentON_2026\software\reactive-seabed-mat-demo\.venv\Scripts\python.exe" research/summarise_research.py
```

```powershell
cd "C:\Users\Artelnics\Desktop\TalentON_2026\software\worktrees\research"
& "C:\Users\Artelnics\Desktop\TalentON_2026\software\reactive-seabed-mat-demo\.venv\Scripts\python.exe" -m pytest tests/contracts -q
```

---

## 4. Tests actually executed, with real outcomes

This branch wrote no tests. Two things were run.

**Frozen contract suite, unchanged by this branch.**

```
cd "...\worktrees\research"
python -m pytest tests/contracts -q
........................................................................ [ 81%]
................                                                         [100%]
EXIT=0
```

88 test outcomes (72 dots at 81 per cent, 16 more to 100 per cent), process exit code 0.
The trailing `88 passed in Ns` summary line did not appear in the captured output on this
machine; the dot count and the exit code are what is being reported, and nothing was
inferred beyond them.

**The standalone example.**

```
Selective reactive seabed mat: research evidence summary
Branch research/sensors. Research snapshot 2026-09-08.
No supplier has been contacted. Nothing here is a quotation.

Supplier and service records : 19
Prior-art source records     : 17
Schema problems              : 0

Commercial status
  CURRENT_LISTING      15  ###############
  INDEXED_LEAD_ONLY     2  ##
  HISTORICAL_EVIDENCE   1  #
  RESEARCH_PROTOTYPE    1  #

EU member states     : 10
European non-EU      : 9

Retrieval outcome
  FETCHED_OK           16  ################
  FETCHED_PDF           2  ##
  FETCH_403             1  #

Records whose 'measures' field mentions a metal at all
(a mention is not a verified capability: read the notes)
  [HISTORICAL_EVIDENCE] Idronaut S.r.l.: VIP, Voltammetric In-situ Profiling system
  [CURRENT_LISTING    ] Metrohm AG: 884 Professional VA with Bi drop electrode, Application Bulletin 438/1
  [INDEXED_LEAD_ONLY  ] Milestone Srl: DMA-80 evo
  [INDEXED_LEAD_ONLY  ] P S Analytical Ltd: PSA 10.035 Millennium Merlin
  [CURRENT_LISTING    ] DGT Research Ltd: LSPM-NP, loaded DGT device for metals (cationic) in sediment using a Chelex binding layer
  [RESEARCH_PROTOTYPE ] University of Geneva, Tercier-Waeber group: TracMetal multichannel submersible probe / Au-GIME Hg(II) sensor

Headline finding
  No purchasable, currently confirmed continuous in-situ Pb or Hg sensor
  for seawater could be verified. The recommendation is continuous
  physical sensors plus passive and periodic chemical sampling.
  See research/sensors/measurement_chain.md.

Evidence files are well formed.
EXIT=0
```

No test was deleted, skipped or marked xfail, because none was written.

---

## 5. What the coding agents should emulate

### 5.1 `feat/observations`

1. **The metal probe channel is the weakest assumption in `config.py`.**
   `bottom_water_probe_period_s = 6 h`, `probe_relative_noise = 0.20`,
   `probe_lod_ng_per_l = 12.0`. **No instrument in the matrix was verified to deliver
   that.** Keep generating it, keep it `ProvenanceLabel.SYNTHETIC_DEMO`, and make sure a
   run can be executed with it switched off. A pilot-realistic variant is the single most
   valuable addition to the observation generator.
2. **A DGT record is an accumulated mass, not a concentration.** Emit
   `QuantityKind.ACCUMULATED_MASS` with both `sampling_start_utc` and `sampling_end_utc`
   set, `Fraction.DGT_LABILE`, `AcquisitionKind.PASSIVE_SAMPLER`. The concrete failure to
   guard against: a three-day exposure spanning one six-hour resuspension event gives the
   same accumulated mass as three steady days at one-twelfth the flux, and a point sample
   at retrieval would see neither (`measurement_chain.md` section 4.3).
3. **A chamber record without `chamber_area_m2` is meaningless.** The Unisense product
   page does not state the enclosed area (record `S-14`), which is exactly why the field
   exists. Refuse to emit or assimilate a chamber flux without it.
4. **Never merge `Fraction.LABILE` and `Fraction.DGT_LABILE`.** Record `S-09`
   (voltammetric) and record `S-13` (DGT) select different complexes and different colloid
   size ranges. Two such records from the same station on the same day are two quantities,
   not two measurements of one, and neither is a check on the other.
5. **A recovered logger is not a delayed sensor.** For a Star-Oddi class instrument
   (`S-04`) there is no in-water protocol at all: `available_at_utc` is the **recovery**
   time, potentially months after `observed_at_utc`. `ObservationConfig` currently has no
   recovery-latency parameter. See the config request below.
6. **QC channels stay QC channels.** Turbidity, salinity, conductivity, pH, redox and
   current carry no metal information. `AGENTS.md` rule 5 is confirmed by the whole
   matrix, not softened by it.

### 5.2 `feat/estimation` and `feat/maintenance`

1. **`J_bare` is unobservable under a laid mat.** Attenuation is therefore a model output
   unless an uncapped control patch exists. Either the estimator reports attenuation with
   an interval that includes the `J_bare` prior uncertainty, or it declines to report it.
   A confident attenuation number with no control patch is not defensible.
2. **Burial can masquerade as success, and only physical channels resolve it.** A
   flux-only estimator will read a buried failing mat as an improving one.
   `AmbiguityFlag.BURIAL` must be raisable from the absence of ROV or bathymetric
   evidence, not only from its presence.
3. **A media assay constrains the retrieved media, never the tile now in place.**
   `MODEL_SPEC` section 8 already says this; the sensor research confirms there is no
   alternative, because no instrument assays a tile in situ.
4. **Mode 2 (fouling) is the worst-observed mode.** `Parameter.DIFFERENTIAL_HEAD` and
   `MAT_PERMEABILITY` exist in the contract, and **no instrument in the matrix was found
   that measures a head difference across a 10 mm layer**. The estimator should be honest
   about that: fouling intervals should stay wide, and `PERFORMANCE_UNCERTAIN` is the
   right answer more often than the demonstration will make comfortable.
5. **Material parameters never narrow.** `Kd`, `q_max`, `k_rate` and `D_eff` of the medium
   in place are unobservable. If the ensemble narrows them, something has leaked.

### 5.3 `feat/presentation`

1. Every metal chart carries a provenance label, and every metal chart in the current
   configuration is `SYNTHETIC_DEMO`.
2. The prior-art position belongs in the demonstration, not in a footnote. The single
   sentence to use is at the end of `docs/PRIOR_ART.md` section 6.
3. The capacity comparison is a trap. Our assumed Pb capacity is about 83 times smaller
   than a commercial laboratory claim (record `PA03`). If that comparison is shown at all,
   it must be shown in that direction.
4. Nothing on any chart may imply an achievable continuous Pb or Hg reading.

---

## 6. Interfaces that could later be implemented

Ordered by how much of the work is already verified.

1. **File and CSV replay adapter.** Highest value, zero vendor risk. Every verified
   instrument produces a file: recovered logger memory (`S-04`), lander logger files
   (`S-14`), laboratory reports (`S-10` to `S-13`), ROV survey forms (`S-17`, `S-18`).
   A converter from a per-instrument file to the observation JSONL contract is the whole
   integration for a real pilot.
2. **Read-only Modbus RTU client, with our own register map.** Records `S-05`, `S-06`,
   `S-07` and `S-08` all speak Modbus RTU over RS-485, and **not one of their register
   maps was obtained**. Any emulator must be tagged `SIMULATED_PROTOCOL`, must use a map
   we invented, and must not be branded as belonging to a manufacturer [S28].
3. **SDI-12 adapter.** Records `S-05` and `S-07` list SDI-12. Same caveat: the command set
   is standard but the per-sensor measurement mapping was not obtained.
4. **An Ethernet-and-web-interface pattern.** Record `S-02`, the Sonardyne Origin 65, is
   the only verified subsea instrument in the matrix with Ethernet, an embedded web user
   interface, an acoustic back channel and a published SDK. If the demonstrator wants to
   show a modern subsea data path, that is the shape to imitate, and the imitation must be
   labelled as an imitation.
5. **A vendor SDK.** Record `S-17`, the Blueye X3, is the only verified vendor SDK in the
   matrix. Its licence is `unknown` and the repository was not retrieved, so nothing may
   depend on it.
6. **Two small converters worth writing properly.**
   * DGT accumulated mass to a time-averaged concentration: needs exposure duration, gel
     thickness, sampler area and a temperature-corrected diffusion coefficient. All four
     must be explicit inputs; none may be defaulted silently.
   * Benthic chamber concentration series to areal flux: needs `chamber_area_m2`, the
     enclosed volume and the incubation duration. Refuse without them.

**What must never be implemented:** an HTTP or MQTT client pretending to be a vendor
interface. No verified subsea instrument in this matrix offers one.

---

## 7. What cannot be claimed

Short list, expanded in `docs/PRIOR_ART.md` section 7.

1. That a reactive mat, a sorbent mat or a geotextile cap is new. EPA's own definition
   names activated carbon mats (record `PA01`), and CETCO has sold one since at least 2017
   (record `PA02`).
2. That activated carbon in sediment remediation is new. More than 25 field projects
   through 2013 (record `PA05`).
3. That monitoring a remediation site is new, or that sensor-informed state estimation for
   sediment contamination is new (record `PA17`).
4. That a thin mat outperforms a thick amended cap. The literature ranks it second of
   three (record `PA08`).
5. That any capacity, attenuation, breakthrough time, service interval or cost in this
   repository is a specification. All are assumptions.
6. That capping is ecologically safe. Up to 90 per cent reduction in benthic abundance and
   biomass persisting four years (record `PA07`), and a documented mechanism by which
   capping raises methylmercury (record `PA10`).
7. That a continuous in-situ Pb or Hg measurement is available. It is not
   (`sensor_matrix.md`, closing section).
8. That any euro value is a price.

---

## 8. Assumptions made in this branch

1. **Unit conversions** in `research/materials/commercial_reactive_mats.md`
   (0.8 lb/ft^2 = 3.906 kg/m^2, 1e-3 cm/s = 1e-5 m/s, 15 ft x 100 ft = 139.35 m^2,
   44 to 56 lb/ft^3 = 705 to 897 kg/m^3) are arithmetic performed here, not vendor
   statements. They use the same SI conventions as `src/reactive_seabed_mat/units.py`.
2. **Capacity comparisons** against `config.py` assume `MatLayoutConfig` defaults
   (thickness 0.010 m, bulk density 400 kg/m^3, Pb allocation 0.6 with `q_max` 1e-3,
   Hg allocation 0.4 with `q_max` 4e-4). If those defaults change, the numbers in
   `PRIOR_ART.md` section 2.2 and in `commercial_reactive_mats.md` must be recomputed.
3. **EU membership** in `summarise_research.py` is as of the snapshot date. Iceland,
   Norway and Switzerland are European non-EU; Iceland and Norway are EEA members.
4. **"Manufacturer" versus "distributor"** is assigned from each supplier's own page. No
   corporate register was checked. HUESKER's German parent attribution is reported by the
   US subsidiary's page and is not independently verified.
5. The DGT list price of GBP 73.00 is a **published list price on the manufacturer's own
   page**, not a quotation, and excludes shipping, laboratory analysis and tax. It is the
   only price in this branch.

---

## 9. Stubs left

**None.** No `LABELLED_STUB` was introduced, because this branch writes no application
code. `research/summarise_research.py` is complete and runs to exit code 0.

---

## 10. Requests to the coordinator

### 10.1 Contract requests (`contracts.py`, frozen)

**R1. Add `ProvenanceLabel.VENDOR_CLAIM`.**
A vendor-stated detection limit, capacity or accuracy is none of the six existing labels.
It is not a `MEASUREMENT` we made, it is not `LITERATURE`, it is not our `ASSUMPTION`, and
calling it `EXTERNAL_MODEL` is wrong. Nearly every number in `sensor_matrix.md` is a vendor
claim, and there is currently no honest way to label one when it reaches a chart. This is
the only contract change this branch actually needs.

**R2. Consider an ecological-impact channel separate from the four degradation modes.**
The strongest ecological evidence retrieved is not methylmercury: it is a documented 90 per
cent reduction in benthic abundance, biomass and species number under an activated-carbon
cap, persisting to four years (record `PA07`). `Fraction.METHYLMERCURY` exists;
nothing represents smothering of the benthic community. This is **not** a fifth degradation
mode of the mat (rule 6 is right to keep those four independent), it is an impact of the
mat working as intended. A wide-interval `benthic_impact` risk term alongside the
methylmercury one, available as an optimisation constraint, would close the gap.
Recorded as a discussion item, not a demand.

**Not requested, deliberately:** `chamber_area_m2`, `tile_id`, `z_in_mat_m`,
`vertical_datum`, `QuantityKind.ACCUMULATED_MASS`, `Fraction.DGT_LABILE` and
`Qualifier.ABOVE_RANGE` all already exist and all turned out to be exactly the fields the
sensor research needed. The contract is well shaped for this problem.

### 10.2 Configuration requests (`config.py`, coordinator-owned)

**R3. A recovery latency for logger-class instruments.**
`ObservationConfig` has `lab_latency_s`, `survey_latency_s` and `probe_latency_s`. A
recovered logger (`S-04`) has a latency measured in months and equal to the recovery
interval, not a fixed offset. Suggest `recovered_logger_latency_s` or, better, a
`StationConfig.recovery_interval_s` so the availability gate reflects the real thing.

**R4. A switch for the metal probe channel.**
Something like `ObservationConfig.enable_bottom_water_metal_probe: bool = True` so a
pilot-realistic run can be demonstrated with the unsupported channel off. The research
finding is that this channel corresponds to no verified instrument, and the demonstrator
should be able to show that it still works without it.

**R5. A control-patch station kind.**
`StationConfig.kind` is a free string. Adding a documented `"control_patch"` kind, sited on
cells the mat does not cover, would make `J_bare` an observed quantity in the demonstration
rather than a model constant. Scenario F (`undersized_mat`) already produces uncovered
cells and is the natural place to prototype it.

**R6. Recheck the first-six-months inspection cadence.**
`survey_period_s = 180 days` is uniform. The monitoring guidance summary says the first six
months after placement need the densest inspection because settling appears then, and the
Grenland field evidence shows up to 75 per cent of the amendment can be lost **at
placement** (record `PA07`). A denser early survey schedule would be more honest.

### 10.3 Documentation requests

**R7.** `docs/SENSOR_SUPPLIERS.md` is now superseded by
`research/sensors/sensor_matrix.md`, which contains everything it had plus verified
specifications and the two counter-examples. Suggest replacing its body with a pointer,
or deleting it. It is not an owned path for this branch, so nothing was changed.

**R8.** `docs/REFERENCES.md` entries S19 to S22 should record that on 2026-09-08 the
Idronaut domain failed TLS certificate verification on every URL and P S Analytical
returned HTTP 403 on every URL, so those leads have not improved since the previous
snapshot. Again not an owned path.

---

## 11. Open gaps, honestly

1. **The benthic chamber question is unresolved and it is the important one.** The only
   channel that measures `J_out` directly is a chamber, the verified chamber product
   carries no metal sensors, and its enclosed area is not published. Until that is closed,
   the quantity the mat is judged on has no verified instrument.
2. **`J_bare` has no observation path** without a control patch, and a control patch needs
   an authorisation nobody has.
3. **No verified continuous Pb or Hg sensor.** Stated at length in `sensor_matrix.md`.
   This is the finding, not a failure of the search.
4. **Methylmercury has no instrument in the matrix.** It needs species-specific laboratory
   analysis that was not researched.
5. **Benthic community condition has no instrument in the matrix.** It needs grab sampling
   and taxonomy.
6. **Fouling has no verified instrument.** Differential head across a 10 mm layer was not
   found in any product.
7. **Not one Modbus register map was obtained.** Every digital-protocol claim in the matrix
   is a protocol name, not an integration.
8. **Three retrieval failures worth retrying:** the ITRC sediment cap guidance
   (HTTP 403 on both ITRC hosts), the Idronaut site (TLS certificate verification failure
   on every URL), and P S Analytical (HTTP 403 on every URL). All three would upgrade
   records that are currently `INDEXED_LEAD_ONLY` or `HISTORICAL_EVIDENCE`.
9. **Two numbers used in `PRIOR_ART.md` are not verbatim-verified** and are labelled as
   such in place: the Johnson et al. (2010) methylmercury increase, and the Gilmour et al.
   (2013) porewater reduction. Both articles are behind HTTP 403.
10. **Retrieval of a laid mat is undocumented in every source found.** That is the closest
    thing this project has to a differentiator, and there is no evidence either for or
    against it. It cannot be settled by literature search; it needs a physical trial.
