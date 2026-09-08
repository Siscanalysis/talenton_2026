# Measurement chains: a minimum pilot, and a software-demo replay

**Research snapshot: 8 September 2026.** Record identifiers `S-01` to `S-19` refer to
`research/sensors/sensor_matrix.md`. Nothing here is a purchase recommendation, and every
euro figure in this repository remains an assumption.

Two chains are described, and they are **not** the same chain at different fidelities.
The pilot chain is what could actually be assembled from verified European suppliers. The
replay chain is what the demonstrator runs, offline, with no hardware. Confusing them is
the failure this document exists to prevent.

---

## 1. Minimum pilot measurement chain

Six instrument or sampler classes, chosen because each one constrains a state that nothing
else constrains. Everything else in the matrix is an alternative or an upgrade.

| # | Purpose | Candidate | Cadence | Latency to a decision |
|---|---|---|---|---|
| P1 | Near-bed hydrodynamics | Nortek Aquadopp 500 m Gen 2 (**S-01**) | continuous, 1 Hz burst to hourly average | minutes if cabled, otherwise until recovery |
| P2 | Water-column context and QC | Aqualabo CTZN + PHEHT + NTU (**S-05**, **S-06**, **S-07**) on an nke MoSens carrier (**S-08**) | hourly | minutes to hours |
| P3 | Time-integrated labile lead in porewater and bottom water | DGT Research LSPM-NP (**S-13**) | campaign, days of exposure every few months | weeks (laboratory) |
| P4 | Discrete porewater chemistry at the sediment face and inside the layer | Rhizon CSS (**S-15**) plus accredited laboratory analysis | campaign, every few months | weeks (laboratory) |
| P5 | Direct areal flux across the sediment-water interface | Unisense MiniChamber Lander (**S-14**) with timed water sub-samples for laboratory Pb and Hg | campaign, twice a year | weeks (laboratory) |
| P6 | Physical condition of the mat, per tile | ROV survey (**S-17** owned, or **S-18** contracted) plus bathymetry | campaign, twice a year, and more often in the first six months | one to a few days |

Plus one non-instrument channel that no sensor can replace:

| # | Purpose | Method | Cadence |
|---|---|---|---|
| P7 | Retained inventory in the medium | Assay of the **retrieved** media at every service event, total Pb and Hg on the solid (**S-11** is a candidate technique) | at each replacement only |

### The control patch, which is not optional

`attenuation = 1 - J_out / J_bare` cannot be computed without `J_bare`, and once a mat is
laid, `J_bare` at the covered cells is unmeasurable forever. A pilot must therefore include
an **uncapped control patch of the same hotspot**, instrumented identically (at minimum
P3, P4 and P5), or every attenuation number is a model output and not a measurement.
`MODEL_SPEC` section 3 already says attenuation "is never asserted without `J_bare`";
this is the field consequence of that sentence.

### Physical and electrical path

```
subsea instrument  --RS485 Modbus RTU / RS422 / SDI-12-->  subsea junction or logger
      |                                                          |
      |                                              (cable, or recovered memory)
      v                                                          v
 recovered loggers (S-04)  ------------------------------>  surface gateway / PC
                                                                 |
                                                    timestamped records, one file per
                                                    instrument, in vendor format
                                                                 |
                                                      converter to the observation
                                                      JSONL contract
                                                                 |
                                              src/reactive_seabed_mat/observations/records.py
```

**None of the verified subsea instruments speaks HTTP, MQTT or any REST API.** The
protocols verified in this snapshot are RS-422 (S-01), RS232 and Ethernet with an embedded
web interface (S-02, the one exception, and it is a 4100 m ADCP), RS-232 and AiCaP CANbus
(S-03), a PC cable after recovery (S-04), Modbus RTU over RS-485 and SDI-12 (S-05, S-06,
S-07, S-08), and RS-232 for guest devices on a lander logger (S-14). Any web interface in
the architecture is something the integrator builds on the surface side, not something a
vendor supplies subsea.

---

## 2. Software-demo replay chain

This is what the demonstrator runs. It needs no map, no network and no hardware
(`AGENTS.md` rule 15).

```
scenarios/registry.py                 a RunConfig, seed fixed
      |
      v
simulator  -->  results/<run>/truth/          hidden state, off limits to estimation
      |
      v
observation generator  -->  results/<run>/observations/*.jsonl
      |                      censoring, QC flags, laboratory latency, missing records
      v
observations/records.py  observations_available(records, decision_time_utc)
      |                      the no-lookahead gate
      v
estimation/  -->  results/<run>/estimates/
      |
      v
maintenance/  -->  Recommendation, human_confirmation_required = True
```

Rules for the replay chain, all of which follow from the sensor research:

1. Every generated metal record carries `ProvenanceLabel.SYNTHETIC_DEMO`. Not one of them
   corresponds to a verified instrument.
2. Any file-based or Modbus-emulated ingestion demonstration is marked
   `SIMULATED_PROTOCOL`, uses **our own** register map, and is never branded as belonging
   to a manufacturer [S28].
3. The replay chain must be able to run with the six-hourly metal probe **switched off**,
   because that channel is the least defensible assumption in the configuration
   (`sensor_matrix.md`, closing section). A pilot-realistic variant of scenario E is the
   natural place to demonstrate this.
4. Timestamps: `available_at_utc = observed_at_utc + lab_latency_s` for laboratory
   records, and for a recovered logger such as **S-04** `available_at_utc` is the
   **recovery** time, which can be months after the observation. The current
   `ObservationConfig` has no recovery-latency parameter; see the handoff.

---

## 3. What each channel actually constrains

The four blocks below are the whole point of this document. A channel appears in exactly
one block.

### 3.1 Channels that constrain the SOURCE FLUX

The source is `C_sed`, the porewater concentration at the sediment face, together with the
seepage velocity `v` and the film coefficient `k_film`. These set `J_bare` and drive the
layer.

| Channel | Constrains | Strength | Caveat |
|---|---|---|---|
| Rhizon porewater at the sediment face, laboratory Pb and Hg (**S-15**) | `C_sed` directly | strong | dissolved-filtered fraction; trace-metal blanks unproven for the sampler |
| DGT in the sediment beneath the mat (**S-13**) | a time-integrated labile pool related to `C_sed` | moderate | DGT-labile, a different pool; Pb only in the verified product |
| Differential head across the layer, plus a seepage estimate | `v`, hence the advective part of `J_bare` | weak to moderate | no verified instrument in this matrix measures seepage velocity directly |
| Benthic chamber on the **uncapped control patch** (**S-14**) | `J_bare` directly | strong | needs a control patch, and chamber artefacts suppress advection |

Without a control patch, `J_bare` is **not observed at all** and every attenuation figure
is model-derived. This is the single largest observability gap in the pilot design.

### 3.2 Channels that constrain the RESIDUAL FLUX

`J_out`, the quantity the mat is judged on.

| Channel | Constrains | Strength | Caveat |
|---|---|---|---|
| Benthic chamber over a tile, with timed water sub-samples (**S-14**) | `J_out` **directly**, as `QuantityKind.AREAL_FLUX` | strong, and unique | the chamber changes local hydrodynamics; enclosing an advection-driven interface can suppress the flux being measured; the enclosed area must be recorded (`chamber_area_m2`) or the number is meaningless |
| Bottom-water Pb and Hg immediately above the mat (**S-04** position, laboratory analysis) | `C_water`, hence `J_out` through the film relation | weak | the coastal field dilutes and advects; two tiles apart may be indistinguishable |
| Mat-porewater sampling inside the layer (**S-15** with a `z_in_mat_m` position) | the layer profile `C(z)`, hence the gradient at the top face | moderate | disturbs the layer; a repeat sample is not the same sample |

### 3.3 Channels that constrain MAT CONDITION, modes 3 and 4

Displacement, burial, scour, uplift, tear, puncture, lost tile.

| Channel | Constrains | Strength | Caveat |
|---|---|---|---|
| ROV visual survey (**S-17**, **S-18**) | `MAT_COVERAGE_FRACTION`, `MAT_DAMAGE_CLASS`, `MAT_TILT`, `MAT_DISPLACEMENT` | strong for what is visible | cannot see through sediment; a fully buried tile looks like no tile |
| Bathymetric survey (**S-18**) | `BURIAL_DEPTH`, `SCOUR_DEPTH` | moderate | resolution against a mat 10 mm thick is the whole question, and it was not established |
| Acoustic positioning of a tile transponder (**S-16**) | `MAT_DISPLACEMENT` | unknown at the required precision | accuracy is a percentage of slant range, dominated in shallow water by sound speed and multipath |
| Pressure and temperature logger on a tile (**S-04**) | gross depth change, hence uplift or major burial | weak but very cheap | recovered data only |

**Burial deserves its own warning.** Burial *reduces* the apparent flux
(`MODEL_SPEC` section 4, `g_top_buried`). A flux-only monitoring programme would read a
buried, failing mat as an improving one. `AmbiguityFlag.BURIAL` exists for this, and the
only channels that can resolve it are the physical ones in this block. **A pilot without
an ROV or bathymetry cannot tell success from burial.**

### 3.4 Channels that only support condition monitoring and QC

These carry no chemistry and no mat state. They exist to explain, to bound and to
disqualify other records.

* Current speed and direction (**S-01**, **S-02**, **S-03**): sets the coastal transport,
  explains resuspension, and provides the erosion context for mode 3.
* Temperature and sediment temperature (**S-04**, and the temperature channel of
  **S-05**, **S-06**): rate context, and a sensor-health check.
* Conductivity and salinity (**S-05**): matrix context; a salinity excursion invalidates a
  chemical result rather than producing one.
* pH and redox (**S-06**): the drivers of the methylmercury risk term
  (`MODEL_SPEC` section 11) and of sorption chemistry. **Redox in sediment is
  operationally defined and poorly reproducible; treat it as an indicator, not a
  measurement.**
* Turbidity and suspended solids (**S-07**): resuspension events, and QC for any water
  sample taken during one.
* Battery voltage: sensor health only.

`AGENTS.md` rule 5 applies to this whole block without exception. Removing every one of
these records must leave the metal estimate unchanged, and `tests/estimation/` is required
to assert it.

### 3.5 States that stay UNOBSERVED

Honest list. Nothing in the verified matrix constrains any of these.

| Unobserved state | Why | Consequence |
|---|---|---|
| `Kd`, `q_max`, `k_rate`, `D_eff` of the medium **in place** | No in-situ method exists. Laboratory isotherms on fresh medium are not the aged, fouled, in-place material | These stay priors in `ModelHistory.material_priors`; their intervals never narrow from field data |
| Sorbed loading `q(z)` of the tile **currently in place** | The only assay is of media already retrieved, which by definition is no longer in place | `MODEL_SPEC` section 8 is right: a media assay constrains the **old** media. Loading of the live tile is inferred, never measured |
| `J_bare` under a laid mat | Physically unmeasurable once covered | Requires a control patch, or attenuation is model output |
| Edge leakage fraction and fouling bypass coupling | No instrument measures flow around a tile edge | Pure assumption, `edge_leakage_interval` in `config.py` |
| Fouling index `f` | Inferable only from a permeability or differential-head change, and no verified instrument in this matrix measures differential head across a 10 mm layer | Mode 2 is the weakest-observed of the four modes |
| Methylmercury fraction | No instrument in the matrix measures MeHg. It needs species-specific laboratory analysis (distillation and GC-CVAFS or equivalent), which was not researched | The MeHg risk term stays a wide interval driven by redox, exactly as `MODEL_SPEC` section 11 specifies |
| Benthic community condition under and around the mat | No instrument in the matrix. It needs grab sampling and taxonomy | The strongest ecological harm in the retrieved literature (`docs/PRIOR_ART.md` section 4) is invisible to this monitoring design |
| Sediment reservoir depletion | Prescribed and not depleted by assumption (`MODEL_SPEC` section 7) | A documented assumption, not a conservation claim |

---

## 4. Incompatibility examples, worked

These four are the specific mistakes the observation operator must refuse to make.

### 4.1 Labile versus total recoverable

A voltammetric probe (**S-09**) reports the **dynamic or labile** fraction: the metal that
dissociates and diffuses to the electrode on the timescale of the measurement. An
accredited laboratory reporting "total recoverable Pb" reports what an acid digestion
releases, including colloid-bound and particle-associated metal.

In a turbid bottom-water sample these can differ by an order of magnitude, and the
difference is dominated by particles, not by chemistry.

*Rule:* `MODEL_SPEC` section 8 already forbids assimilating a `total_recoverable` record
against a `labile` model state unless a documented, uncertain ratio operator is switched
on, default off. That is correct. The failure mode it prevents is a laboratory
total-recoverable value being read as a rising porewater source when what actually rose
was the turbidity.

### 4.2 DGT-labile versus voltammetric labile

Both are called "labile" in ordinary speech, and they are different pools. A DGT
(**S-13**) integrates the metal that diffuses through a defined gel of defined thickness
over days, with a defined diffusion coefficient; a voltammetric probe (**S-09**) measures
what is electrochemically available at the electrode over seconds to minutes behind a
different membrane. The two operational definitions select different complexes and
different colloid size ranges.

*Rule:* `Fraction.DGT_LABILE` and `Fraction.LABILE` are distinct members of the contract
enumeration and are never merged. A DGT-labile Pb and a voltammetric labile Pb from the
same station on the same day are two different quantities, not two measurements of one
quantity, and neither is a check on the other.

### 4.3 Integrated passive exposure versus a point reading

A DGT deployed for three days reports an **accumulated mass** over that window.
Converting it to an average concentration requires the exposure duration, the gel
thickness, the sampler area and the temperature-corrected diffusion coefficient. It is not
a reading at the moment of retrieval, and it carries no information about **when** inside
the window the metal arrived.

Concretely: a three-day DGT exposure that spans a single six-hour resuspension event
reports the same accumulated mass as three days of a steady flux one-twelfth as large.
A point sample taken at retrieval would see neither.

*Rule:* such a record is `QuantityKind.ACCUMULATED_MASS`, with
`sampling_start_utc` and `sampling_end_utc` both set, and the observation operator
compares it against the model's integral over that same window. `MODEL_SPEC` section 8
already says "a time-integrated labile pool, never a point ng/L". Enforce it in the
likelihood, not only in the documentation.

### 4.4 A benthic chamber flux versus a water-column concentration

A chamber (**S-14**) reports `QuantityKind.AREAL_FLUX` in kg m^-2 s^-1 across the patch it
encloses. A bottom-water sample reports `QuantityKind.AQUEOUS_CONCENTRATION` in kg m^-3 at
one point in a field that is being advected and diluted by the tidal current.

They are not convertible without the whole coastal transport model, the mixing depth and
the local velocity, which is precisely the model under test. Dividing a concentration by a
depth and a time to "get a flux" fabricates the answer.

Worse, they can disagree honestly and both be right: a chamber over an intact tile can
read a low `J_out` while the bottom water above it reads high, because the water is
carrying the plume from the uncovered cells three tiles away.

*Rule:* the chamber constrains `J_out` for the tile it sits on, and only that tile. The
bottom-water record constrains `C_water`, which is the layer's top boundary condition, and
only that. `ObservationRecord.chamber_area_m2` is mandatory for the first and meaningless
for the second, and `tile_id` distinguishes which tile either belongs to.

---

## 5. What a pilot could and could not demonstrate

**Could:** that the residual areal flux over a capped patch is lower than over an adjacent
uncapped control patch, by a factor with an honest confidence interval, at a handful of
times over a few years; that coverage and physical integrity can be tracked; that the
retained inventory in retrieved media closes a mass balance to some stated tolerance.

**Could not, with this instrument set:** a continuous flux time series; a real-time metal
reading; the loading of the tile currently in place; the methylmercury outcome; the
benthic-community outcome; or any distinction between the four degradation modes without
the physical condition channels.

That is the honest scope, and it is smaller than the demonstrator's output implies. Every
export from this repository should say so.
