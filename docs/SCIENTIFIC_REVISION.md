# Scientific revision, 9 September 2026

This revision follows a comparison with the three user-supplied keratin papers
and an investigation of anomalous plot behaviour. The manuscript and all
scenario/policy figures are regenerated from the revised implementation.

## Literature and parameter traceability

[PAPER_PARAMETER_TRACEABILITY.md](PAPER_PARAMETER_TRACEABILITY.md) and its
[machine-readable register](../research/references/paper_parameter_traceability.json)
record article identifiers, file hashes, page locations, experimental conditions,
unit conversions and numerical inconsistencies. The supplied article PDFs are
not redistributed.

The model's Pb/Hg/Cu operating capacities remain 1/2.5/3 mg/g. They are assumed
settings, not fitted values from the supplied papers. In particular:

- Enkhzaya et al. report Cu batch isotherms for treated sheep wool. The register
  distinguishes raw wool and different treatments and flags inconsistent
  reported values and a kinetic mass-balance discrepancy.
- The Zubair composite study reports 99.21% Pb removal at a low initial loading.
  The corresponding batch uptake is 0.059526 mg/g, not a fitted maximum capacity
  and not the performance of neat keratin.
- The 2026 review points to Liang et al.'s 476.7 mg/g laboratory Hg uptake by
  chemically modified human hair. This supersedes the blanket claim that no
  keratin-derived mercury capacity had been found. It does not establish a
  finished wool/feather mat capacity in seawater.

## Corrected implementation and reporting

| Finding | Correction and verification |
|---|---|
| Tile coordinates interpreted as centres in one component and lower-left corners in another | One lower-left convention; rectangular hotspot aspect ratio preserved; exact area-overlap regression checks |
| Raw column averages presented as hotspot attenuation | Timeline uses the same footprint, condition and bypass weights as the spatial source; final source-map equality audited for every run and element |
| Displaced tiles appeared to improve attenuation | Missing cover emits the bare source; a real-column integration test verifies an exact-time downward attenuation jump |
| Simulation advanced before recording t=0 and ran one extra step | Unadvanced initial state; integration exactly over [0,T], including partial last intervals and exact event/decision boundaries |
| Requested plume ages outside the simulated horizon silently used final tiles | Only valid ages are captured, and the actual final age is included |
| Plume source advanced a captured column again | Zero-duration instantaneous flux diagnostic holds inventory unchanged |
| Maps drew final conditions around earlier snapshots | Each plume window stores and draws its own tile states |
| Approximate continuum barrier differed from the discrete column | Exact stationary discrete operator for the diagnostic; independent continuum/grid and face-balance checks retained |
| Conditional ensemble path bypassed textile/inactive-tile behaviour | Ensemble samples use the actual tile advance path; nominal-member equivalence tested |
| Nonconverged Picard branch masks could return a clipped but wrong state | Fail explicitly with an actionable solver error; independent adaptive-ODE transient check and step refinement |
| Observation generator reset its start time and random stream every decision | One experiment-wide schedule with deterministic per-record draws, completed-exposure windows and partition invariance |
| Quality-control flags and analytical fractions not fully used by the controller | Gate on arrival, apply QC, and select compatible parameter/matrix/fraction/quantity records |
| Zero burial or absent Cu treated as evidence of a failure | Require resolved physical anomalies and measured compatible chemical pairs; unobserved Cu does not drive attribution |
| Missing head/tilt physics emitted normal-condition values | Emit missing observations when the simulator provides no such model |
| Retired-media or cross-replacement samples contaminated a new estimate | Filter current-media evidence by the service boundary and exposure interval |
| Above-range intervals invented a finite upper bound | Standalone interval reconstruction preserves the open upper bound; strict JSON uses null and explicit nonfinite-path metadata. The separate coupled-QC limitation below remains |
| Policy comparison used different emission quantities | Every policy integrates the actual whole-hotspot residual source; active and retrieved column inventories remain distinct |
| Outputs omitted observation/estimate/action histories | Export the full histories, final QC and hashes alongside configurations, ledgers and reports |
| Static plots clipped low attenuation or used wrong tile outlines | Correct geometry and ranges, common paired concentration scales, exact event jumps and actual-age labels |

## Verification artefacts

- `manuscript/verification/test_results.txt`: complete final test-suite output.
- `manuscript/verification/scenario_audit.json`: regenerated scenario/policy
  budget closure, source-map agreement, ages and observation-ID checks.
- `manuscript/data/reactive_numerical_audit.json`: independent nonlinear ODE,
  stationary/grid and capacity-lock comparisons.
- `manuscript/data/timescale_audit.json`: mat-step, horizon, campaign-cadence,
  tidal-window and coastal-resolution studies.
- `docs/gallery/cache_manifest.json`: scientific source fingerprint and run
  configuration hashes; `manuscript/provenance.json` identifies the source
  revision and delivered scientific artefacts.

## Remaining interpretation limits

Abrupt source changes, physical damage and replacement cause real scenario
discontinuities. Coastal endpoint maxima vary with tidal phase. The numerical
studies quantify resolution dependence; a non-monotone window-length curve is
not by itself a solver defect.

The exactly capacity-locked branch remains an explicit, unvalidated law: unlike
an almost-full cell, it does not desorb on flushing. The numerical comparison
shows this discontinuity rather than treating it as experimental evidence.

The column ledger uses full tile volumes, while long-term hotspot emission is
mixed by coverage and bypass. Individually closed column and plume ledgers do
not establish a globally closed, coupled sediment--mat--water inventory. The
long-term columns see clean bottom water; short plume windows start clean and
hold the source fixed. No finite sediment depletion or long-term plume feedback
is solved.

Material coefficients, accessible fractions, monitoring errors, degradation,
costs and deployment scores remain assumptions. The current Pb/Hg estimator is
interval arithmetic with heuristic attribution, not a calibrated Bayesian
ensemble. Cu is unobserved. Recommendations to obtain more evidence do not
adapt the future campaign schedule. These limits remain explicit in the report.

The final saved-record audit also identifies a remaining censoring/QC interface
limitation. Records preserve their detection bounds, and standalone interval
arithmetic supports them, but scalar QC has no applicable range or spike check
for generated bounds without values. With no applied check, an input passed
flag becomes `NOT_EVALUATED` (2), which the coupled estimator's passed-only gate
excludes. In fresh-mat scenario A, the day-1 Hg chamber result is below LOD
([0, 0.05] micrograms/m2/day) and the day-181 result is below LOQ
([0.05, 0.20]); both raw flags are 1 and processed flags are 2. The quantified
day-361 result arrives on day 382, after the one-year horizon. The final Hg
chamber age is consequently unavailable and its attenuation interval is [0,1];
the run records twelve sampling recommendations and no service. These are the
reported results of the current conservative gate, not evidence of validated
assimilation of censoring intervals. The limitation is documented without
changing the frozen scientific implementation or regenerating different results.
