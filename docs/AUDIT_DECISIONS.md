# Audit decisions ledger

Authoritative. A decision recorded here is settled: do not reopen it without
adding a dated supersession row saying what changed and why.

Vocabulary: **implement** (change the code), **document** (state it rather than
change it), **remove** (delete the claim instead of building it), **accept**
(a known wart, left deliberately), **verify** (already correct, confirmed).

| ID | Finding | Decision | Status | Date | Rationale |
|---|---|---|---|---|---|
| A1 | The none / fixed / evidence-informed policy comparison was documented and exported but nothing read `config.policy` | implement | done | 2026-09-08 | The brief's headline comparison. Shipping a dead knob that returns three identical results labelled as a comparison is worse than not shipping one. Written against the frozen contracts, which already specified `EstimateSnapshot` and `Recommendation`. |
| A2 | `reactive_layer/design.py` raised `ImportError` and carried `interception_efficiency` from the deleted concept | remove | done | 2026-09-08 | Dead, unreachable and contradicts rule 1. Recoverable from git history. Porting it would have meant porting the wrong physics. |
| A3 | `estimation/`, `maintenance/`, `optimisation/` held only a zero-byte `.gitkeep` while the README described their contents | implement (first two), remove (third) | done | 2026-09-08 | The comparison depends on the first two. The design sweep is real work that deserves doing properly, so the claim was deleted and the item listed as open rather than rushed. |
| A4 | Empty untracked `ml/`, `feedback/`, `reporting/` directories | remove | done | 2026-09-08 | Branch-layout residue. |
| A5 | The state-separation guard listed a package that no longer exists, so it covered one package instead of three | implement | done | 2026-09-08 | A static guard that stops covering what it was written for fails silently. The sentinel test now asserts every named package is present. |
| A6 | `README.md` linked to a `docs/DEMO_SCRIPT.md` that did not exist | implement | done | 2026-09-08 | A broken link on the landing page. Writing it was cheaper than removing the link, and the demo needs a narration anyway. |
| A7 | README said 262 tests | implement | done | 2026-09-08 | Stale after the observations merge. |
| B1 | Keratin Pb fill time quoted as 3 years, recomputed as 2.54 | implement | done | 2026-09-08 | Recompute, then write down what the code says. |
| B2 | The mat ledger sees far less mass than the hotspot releases; suspected a coverage bug | verify | closed | 2026-09-08 | Not a bug. Coverage is exactly 100 %. The difference is the mat suppressing the diffusive exchange term, which is physical. Recorded so it is not re-investigated. |
| B3 | With no tiles, `_mean_over_tiles([])` returned 0.0 and a non-existent mat scored 100 % attenuation | implement | done | 2026-09-08 | Latent until the `none` policy existed, at which point it would have been the first number a juror saw. With no layer step the residual flux is the bare flux. |
| C1 | The default bare Pb flux, 2592 ug/m2/d, is 400 to 2700 times measured benthic Pb fluxes | document | done | 2026-09-08 | A weaker source shows no loading or breakthrough inside a demonstration, so the default stays. `docs/EVIDENCE_BASE.md` section 1.1 states the gap and draws the conclusion: the absolute kilogram figures belong to the assumed hotspot, and only the relative comparisons survive. Tuning the model until the mismatch disappeared would have hidden it. |
| C2 | Modelled attenuation of 94 to 99 % is above every measured field cap (Trondheim, factor 2 to 10) | document | done | 2026-09-08 | Same reasoning. The causes are known and already listed in `LIMITATIONS.md`. The honest comparator is named in `EVIDENCE_BASE.md` section 1.2 so the presentation cannot quote 99 % as a field expectation. |
| C3 | Secondary sources quote activated-carbon "70 to 99 % reduction" as if concentration and flux were interchangeable | document | done | 2026-09-08 | The unit ladders already prevent the substitution in code. Worth naming because it is the most common error in this literature. |
| C4 | No verified keratin Hg capacity exists | verify | closed | 2026-09-08 | `MATERIAL_KERATIN.md` already records it as UNKNOWN and derives a stoichiometric ceiling rather than borrowing a number from a different material. Correct as it stands. |
| C5 | No open dataset gives measured Pb or Hg flux attenuation across a marine reactive cap | document | done | 2026-09-08 | Recorded as `GAP1` in `research/references/datasets.json`. The absence is a finding: the headline quantity of the concept is unmeasured in the open literature for metals. |
| D1 | `docs/MESH_DEMO_BUILD_BRIEF.md`, `docs/MASTER_PROMPT.md` and `prompts/` described the deleted vertical-mesh concept as the specification | remove | done | 2026-09-08 | A reader could have taken either as current. Both are in git history and `REFACTOR_PLAN.md` records the change. `MESH_DEMO_BUILD_BRIEF.md` also named the tooling its audience was expected to use, which does not belong in a published repository. |
| D2 | `ActionKind.REPLACE_ACTIVE_PANEL` keeps a pre-refactor name in the frozen contract | accept | closed | 2026-09-08 | Renaming breaks `CONTRACT_VERSION = "0.2.0-frozen-mat"`, which exists to be stable. Unused by the policy. Recorded rather than silently changed. |
| D3 | `reactive_layer/__init__.py` documented why it excluded a file that no longer exists | implement | done | 2026-09-08 | Docstring updated when the file was removed. |
| E1 | The evidence-informed policy under-services relative to the calendar policy | document | done | 2026-09-08 | Not tuned away. It is the most useful result the demonstrator produces: the value of evidence-informed maintenance is bounded by the monitoring programme feeding it, and this one is too thin to beat a calendar. Reported in `AUDIT.md` section E, in the report and in the app. |
| E2 | The estimator's saturation interval is dominated by the assumed capacity, not by the observations | implement + document | done | 2026-09-08 | Added `ReactiveMediumConfig.commissioned_q_max_interval` so a commissioning isotherm on the real batch can narrow it, and a test that shows the narrowing. This turns "we need lab work" into a quantified statement. Hg is left uncommissioned because no verified capacity exists to confirm. |
| E3 | Which end of the saturation interval a decision is taken on changes the decision | implement | done | 2026-09-08 | Made explicit as `PolicyConfig.saturation_decision_bound` (lower / mid / upper) with the trade-off documented, rather than left as a hidden convention. Default `mid`: neither replacing too early nor too late is obviously the worse error here. |
| E4 | Arithmetic interval widening drove positive fluxes negative, destroying every downstream quotient | implement | done | 2026-09-08 | Switched to geometric widening for positive intervals. A flux is known to within a factor, not a difference. Guarded by a regression test. |
| E5 | Nine tiles carry chemistry on one or two, so most tiles had no estimate at all | implement | done | 2026-09-08 | Pool chemistry across the mat, widen for the extrapolation, and say so in the notes. This is what a real monitoring programme does and what `LIMITATIONS.md` already warned about. |

## Supersessions

None yet. Add a dated row here before changing any decision above.
