# Pre-publication audit

Run on 8 September 2026 against commit `39acfb0`, before the repository was
published. The method is the one used for a paper revision, adapted to a code
repository: check every claim against the thing it claims about, verify the
citations against the real literature, and record each decision so it is not
relitigated later.

Decisions are recorded in `docs/AUDIT_DECISIONS.md`, which is authoritative.

**Baseline.** Working tree clean, 412 tests passing, `cli quick` producing a
self-contained report in about 75 seconds.

## Summary

| Severity | Count | Theme |
|---|---|---|
| High | 6 | Documented features that did not exist, one that could not be imported, and one crash they were hiding |
| Medium | 7 | Stale numbers, superseded documents, a broken link, two latent reporting bugs |
| Low | 4 | Terminology drift and tidying |
| Not a finding | 3 | Checked and cleared |

The most useful thing the audit did was not any single fix. It was that
**removing a dead feature exposed a crash** (A1 to A8): the policy knob that did
nothing was also the reason nothing ever reached the code path that failed.

Two findings were scientific rather than editorial, and both are recorded in
`docs/EVIDENCE_BASE.md` rather than fixed in code, because the honest response
is to state them, not to tune the model until they disappear.

---

## A. Claims against reality

### A1 (High, fixed) The policy comparison was documented but not implemented

`scenarios/registry.py` exported `policy_variant` and `POLICIES`, and its module
docstring stated that the none / fixed / evidence-informed comparison "is
applied on top of a scenario, which is what makes 'under identical assumptions'
true rather than merely claimed". Nothing read `config.policy`. All three
variants produced byte-identical results, and `POLICIES["none"]` claimed "no mat
deployed" while the runner always deployed one.

This is worse than a missing feature. A juror could have run the comparison the
brief asks for and been shown three identical numbers presented as a comparison.

*Fixed* by writing the two packages the frozen contracts already specified:
`estimation/` produces `EstimateSnapshot` per tile from observations alone, and
`maintenance/` turns those into `Recommendation` objects. `run_mat_timeline` now
runs the evidence loop on its own clock and applies accepted service events.
See D1 below for what the comparison actually shows.

### A2 (High, fixed) `reactive_layer/design.py` could not be imported

22 KB of pre-refactor code carrying `interception_efficiency`,
`interception_interval` and `PanelConfig` from the deleted vertical-mesh
concept. It imported `PanelConfig` from `config`, which no longer exists, and
`.panel`, which was never merged. It therefore raised `ImportError` on any
attempt to load it, and it contradicted rule 1 of `AGENTS.md`, which says the
mat attenuates a flux and computes no interception efficiency.

*Fixed* by deletion. It is in git history. The design sweep it was meant to
become is listed as open work rather than claimed.

### A3 (High, fixed) `estimation/`, `maintenance/` and `optimisation/` were empty

Each contained a single zero-byte `.gitkeep`. `README.md` described them as
"Ensemble estimator, degradation attribution, policy, costs" and "Footprint,
thickness, loading, layout and servicing sweep".

*Fixed* two different ways, on purpose: `estimation/` and `maintenance/` were
written, because the comparison depends on them; `optimisation/` was removed and
the sweep is now listed under open work. Deleting a claim is a legitimate fix,
and a cheaper one than a rushed implementation.

### A4 (High, fixed) `src/reactive_seabed_mat/{ml,feedback,reporting}/` existed and were empty

Untracked empty directories left over from the branch layout. Removed.

### A5 (High, fixed) The state-separation guard was checking a package that no longer exists

`tests/contracts/test_state_separation.py` set
`OPERATIONAL_PACKAGES = ("feedback", "observations")`. `feedback/` had been
empty since the refactor, so the guard covered only `observations/`, and its
"there is something to check" test passed on that alone. A static guard that
silently stops covering the modules it was written for is the failure mode
static guards are most prone to.

*Fixed*: the list is now `("estimation", "maintenance", "observations")` and the
sentinel test asserts that every named package is actually present.

### A6 (Medium, fixed) `README.md` linked to `docs/DEMO_SCRIPT.md`, which did not exist

A broken link on the landing page of a repository being handed to a jury.
*Fixed* by writing the file.

### A7 (Medium, fixed) The test count in the README was stale

Said 262. The merge of `feat/observations`, which had been sitting unmerged with
about 2,900 lines of tests, brought it to 412; the new maintenance tests bring
it to 434.

### A8 (High, fixed) Scenario F crashed as soon as the evidence loop existed

`undersized_mat`, the deliberately poor design, lays a **2x2** mat. The default
station list names a benthic chamber on `tile_2_2`, which a 2x2 mat does not
have, and the observation generator correctly refuses a tile that is not in the
scene. The run died with `KeyError` part-way through.

Nothing reached that path until A1 was fixed, which is the point: the dead
policy knob was also hiding a crash. Found by the gallery build, not by a test.

*Fixed* by dropping stations whose tile does not exist, which is the physical
answer, and which carries a consequence worth showing: the undersized design is
also the least monitored one. Integration tests added over every scenario.

### A9 (Medium, fixed) Two defects in the estimator written during this audit

Found by re-reading the new code rather than by a failing test.

* Loading was integrated from the mat's original deployment date, so a replaced
  tile inherited the old media's consumed capacity. The estimator would have
  recommended replacing a tile it had just watched being replaced. It now
  integrates from the latest accepted service event naming that tile, and drops
  benthic-chamber records from before it: a flux measured through the previous
  media says nothing about this one. Porewater records are kept, because the
  sediment source does not reset when a tile does.
* The cross-tile fallback said "extrapolated from another instrumented tile"
  even when the pool was also empty, putting a false statement into an
  operator-facing note.

---

## B. Numbers against the code

Every quantity quoted in the documentation was recomputed from
`default_run_config()`.

### B1 (Medium, fixed) Keratin fill time quoted as 3 years, computed as 2.5

`docs/MATERIAL_KERATIN.md` section 5 said the Pb capacity is "consumed by the
modelled advective load in about 3 years". Recomputed:

```
capacity  4.00 kg/m2 x 0.6 x 1.0e-3 kg/kg = 2.400e-03 kg/m2
load      1.0e-3 kg/m3 x 3.0e-8 m/s       = 3.000e-11 kg/m2/s
fill time                                   2.54 years
```

*Fixed* to 2.5 years. The Hg figure of "centuries" is correct: 528 years.

### B2 (Not a finding) Coverage really is 100 %

Checked because the mat ledger sees far less mass than the hotspot releases.
Nine tiles of 26.67 x 26.67 m cover exactly the 80 x 80 m hotspot. The
difference is physical, not geometric: a bare seabed loses metal by advection
*and* by diffusive exchange with clean bottom water, and the mat suppresses the
diffusive part by raising the concentration at the sediment interface. The two
fluxes are different quantities and the ledger is right to keep them apart.

### B3 (Medium, fixed) A no-mat run would have reported perfect attenuation

`_sample_point` averaged the per-tile residual fluxes with
`_mean_over_tiles([])`, which returns 0.0 for an empty list. With no tiles the
residual flux was therefore 0, and attenuation `1 - 0/bare` was reported as
**1.0**: a mat that does not exist, scoring 100 %.

Latent until the `none` policy was implemented, at which point it would have
been the first number a juror saw. *Fixed*: with no layer step the residual flux
is the bare flux, so attenuation is 0.

---

## C. Citations and evidence, web-verified

Every literature figure carried into the model was checked against the source.
Two mismatches with the measured literature were found. Neither is an error in
the arithmetic; both are the model sitting outside the range real measurements
occupy, and both flatter the technology.

### C1 (Scientific, documented not fixed) The bare flux is at the top of the measured envelope

The default hotspot gives 2592 ug/m2/d of Pb. Measured benthic Pb fluxes are
0.54 to 6.4 ug/m2/d diffusive in San Francisco Bay, and 0.97 to 2.50 ug/m2/d in
a mesocosm control. The model is advection-dominated by design and the
quantities are not strictly comparable, but 1 mg/L of dissolved porewater Pb is
an extreme value and it drives service life, captured mass and cost per
kilogram directly.

*Not changed.* A weaker source would not show loading and breakthrough inside a
demonstration. Instead `docs/EVIDENCE_BASE.md` section 1.1 states the gap, and
the conclusion that follows: the absolute kilogram figures are a property of the
assumed hotspot, and only the relative comparisons survive.

### C2 (Scientific, documented not fixed) The modelled attenuation is above every field result

The demonstrator reports 99 % for a fresh mat and about 94 % at plateau.
In-situ thin-layer activated-carbon capping in Trondheim harbour reduced
sediment-to-water fluxes by a factor of 2 to 10, that is 50 to 90 %, measured
with benthic flux chambers. A metals mesocosm with a carbon-nanotube cap
achieved 22 to 76 % on Pb flux.

*Not changed*, for the same reason, and recorded in `docs/EVIDENCE_BASE.md`
section 1.2 together with the causes: uniform seepage, no bioturbation, no
consolidation, perfect mat-sediment contact, no seam short-circuiting.

### C3 (Low, noted) A common substitution the repository is built to prevent

Activated-carbon amendment is frequently reported as reducing contamination "by
70 to 99 %". That figure is a reduction in *porewater concentration*, not in
*flux*, and the two are quoted interchangeably in secondary sources. The unit
ladders in `units.py` make the substitution impossible here, which is worth
saying because it is the most common error in this literature.

### C4 (Not a finding) No verified keratin mercury capacity exists

Re-checked. `docs/MATERIAL_KERATIN.md` already records this correctly as
UNKNOWN and derives a stoichiometric ceiling instead of borrowing a figure from
thiol-functionalised cellulose. The handling is right and is left alone.

### C5 (Medium, documented) The headline quantity has never been measured

No open dataset was found giving measured Pb or Hg flux attenuation across a
marine reactive cap. Recorded as `GAP1` in `research/references/datasets.json`.

---

## D. Incongruencies and superseded material

### D1 (Medium, fixed) Two documents described the deleted concept as the specification

`docs/MESH_DEMO_BUILD_BRIEF.md` (27 KB) and `docs/MASTER_PROMPT.md` were the
pre-refactor brief and coordination prompt. Both describe a vertical mesh
intercepting a lateral plume, which is the physics the refactor deleted, and
`MESH_DEMO_BUILD_BRIEF.md` named the coding tools its audience was expected to
use. A reader arriving at the repository could have taken either as the current
specification.

*Fixed* by removal, along with `prompts/`, which held six per-branch task
prompts for the same superseded concept. All are in git history, and
`REFACTOR_PLAN.md` documents what changed and why.

### D2 (Low, accepted) `ActionKind.REPLACE_ACTIVE_PANEL` keeps a pre-refactor name

The frozen contract enum still says PANEL. Renaming it would break
`CONTRACT_VERSION = "0.2.0-frozen-mat"`, which exists to be stable. Accepted as
a known wart, recorded here rather than silently changed. The value is unused by
the policy, which emits `PLAN_PARTIAL_REPLACEMENT`.

### D3 (Low, fixed) `reactive_layer/__init__.py` documented a file that no longer exists

Its docstring explained why `design.py` was excluded from the package. Updated
to say it was removed and why.

---

## E. What the fixes changed in the result

The comparison the brief asks for, scenario B over six years, same seed, same
forcing, same hotspot schedule, same observation schedule, only
`PolicyConfig.kind` differing:

| Policy | Pb into the water | Services | Assumed cost | Final attenuation |
|---|---|---|---|---|
| none | 642.3 kg | 0 | EUR 0 | 0 % |
| fixed | 6.7 kg | 2 | EUR 3,733,600 | 95.6 % |
| evidence informed | 26.4 kg | 0 | EUR 0 | 94.4 % |

The evidence-informed policy **under-services**: it let about four times more Pb
through than the calendar policy, and spent nothing. That is not a defect in the
policy, and it is the most useful thing the demonstrator produces. With
chemistry on one tile out of nine, no seepage measurement, and a capacity known
only from a commissioning isotherm, the estimated saturation interval never
narrows enough to justify a vessel. **The value of evidence-informed maintenance
is bounded by the monitoring programme that feeds it**, and this programme is
too thin to beat a calendar.

That result also puts a number on the laboratory work: without a commissioning
isotherm the capacity interval spans a factor of 27, and the policy cannot act
at all.

---

## F. What was checked and found sound

* Mass conservation. Every ledger closes to 1e-13 or better, and the four
  manifest checks pass. The mat ledger and the water ledger are separate
  quantities over separate clocks and are never added.
* No-lookahead. The controller reads only records whose `available_at_utc` has
  passed. Verified behaviourally as well as structurally.
* Unit handling. Six separate ladders, no cross-ladder conversion, no unit
  inferred from a parameter name.
* Censoring. A non-detect is a bound and a missing value is not a non-detect.
  Verified in the new estimation tests.
* No chemistry from proxies. No path infers Pb or Hg from turbidity,
  conductivity, salinity, temperature, pH or redox.
* Novelty. `docs/PRIOR_ART.md` is explicit that reactive caps, permeable
  reactive barriers and carbon amendments are established practice, and the
  differentiation is a hypothesis list.
* Ordnance. Nothing simulates, locates or recommends handling munitions.
* No fabricated vendor data. `research/references/evidence.json` carries 19
  supplier entries, each with an access date and a retrieval status, and records
  what is unknown as unknown.

## G. Open work, stated rather than claimed

1. `optimisation/`: a design sweep over footprint, thickness, sorbent loading,
   tile layout and service interval.
2. The value-of-information experiment implied by section E: instrument more
   tiles, measure seepage, and quantify what each buys.
3. The optional machine-learning extension, which the brief allows only after
   the baseline works and only against a documented simpler baseline.
4. Calibration against a real metal-flux measurement, which does not currently
   exist in the open literature.
