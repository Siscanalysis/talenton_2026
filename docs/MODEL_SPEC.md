# Model specification (coordinator-owned, frozen with the contracts)

Status: **synthetic demonstration model.** Every parameter below is an
assumption chosen so that a multi-year demonstration shows loading, breakthrough
and maintenance. None of it is a validated product specification, and none of it
is transferred from [S01] or [S04] as an operating capacity.

The product is a **selective reactive seabed mat**: a thin, modular, retrievable
reactive cap laid on or immediately above an authorised contaminated seabed
area. It attenuates the contaminant flux from the sediment into the overlying
water. Reactive caps, permeable reactive barriers and activated-carbon sediment
amendments already exist; see `docs/PRIOR_ART.md`. No novelty is claimed for
putting sorbent in a mat.

Symbols use SI internally: mass kg, aqueous concentration kg m^-3, loading
kg kg^-1, areal flux kg m^-2 s^-1, length m, time s
(`src/reactive_seabed_mat/units.py`).

---

## 1. Three separated states

| Store | Written by | Readable by |
|---|---|---|
| `results/<run>/truth/` | simulator | tests, evaluation toggle in the UI |
| `results/<run>/observations/` | observation generator | estimator, policy, UI |
| `results/<run>/estimates/` | estimator | policy, UI |

`estimation/`, `maintenance/` and `observations/` must never import from the
truth store. `tests/contracts/test_state_separation.py` enforces this
statically; `tests/estimation/` enforces it behaviourally.

---

## 2. The two scales, and the two timescales

```
authorised contaminated seabed hotspot
  -> contaminant flux through / near the seabed
  -> reactive mat: 1-D reactive layer, per tile      <- micro, section 3
  -> residual flux into the overlying water          <- coupling, section 5
  -> 2-D coastal advection and diffusion             <- macro, section 6
```

A reactive cap changes over months to years; coastal transport also varies
within a tidal cycle. This demonstrator uses separate clocks to limit cost,
with an explicit loss of continuous long-term plume feedback:

* **Mat timeline**: the whole simulated duration (1 to 6 years),
  `dt = 6 h`, cheap 1-D solves per tile. Produces loading, remaining capacity,
  attenuation, breakthrough and the maintenance decisions.
* **Plume windows**: at the mat states named by `PlumeWindowConfig.sample_years`,
  the 2-D model runs over a few tidal days with the residual flux held at that
  mat state. Produces the maps and the water-column budget.

Nothing may imply the coastal model was integrated for years. The exports label
each ledger with its own window.

The timeline integrates exactly `[0,T]`, starts with the unadvanced installed
state, and resolves source, degradation and decision boundaries. Requested
plume ages outside that interval are omitted; the actual final age is included.
Frozen plume sources are evaluated without an extra column step. A 24-hour
plume window is a transient, phase-dependent calculation, not a guaranteed
steady-state solution. See `docs/TIMESCALES.md` for regenerated checks.

---

## 3. Micro model: the 1-D reactive layer

Per tile, per element, through the layer thickness `z` in `[0, L]`:

```
theta dC/dt = d/dz(theta D_eff dC/dz) - v dC/dz - rho_b dq/dt
dq/dt       = k_eff (q_eq(C) - q),      q_eq(C) = min(Kd f_available C, q_max_eff)
```

* `C` porewater concentration in the layer [kg m^-3]
* `q` sorbed loading [kg kg^-1]
* `theta` porosity, `rho_b` dry bulk density of the medium [kg m^-3]
* `D_eff` effective diffusion including tortuosity [m^2 s^-1]
* `v` Darcy seepage velocity, positive upward [m s^-1]

Total flux at any depth:

```
J = v C - theta D_eff dC/dz          [kg m^-2 s^-1]
```

Diffusion and advective seepage are both represented. Their relative effects
depend on the material and boundary conductances; no universal breakthrough
time follows from the nominal capacity alone.

### Boundary conditions

* `z = 0`, sediment face: prescribed porewater concentration `C_sed` from the
  hotspot schedule, with advective inflow `v C_sed` and a diffusive term across
  the half cell.
* `z = L`, water face: advection out plus the benthic boundary layer in series,

```
g_top = 1 / ( dz / (2 theta D_eff) + R_upper_textile + 1 / k_film + R_burial )
J_out = v C[L] + g_top (C[L] - C_water)
```

The lower textile similarly adds series resistance at the sediment face.
`build_seabed_exchange` can sample a supplied coastal field. In the current
long-term runner that field remains clean; episodic plume windows do not feed
back into the preceding column history. This reduced coupling must not be
described as a continuously plume-aware simulation.

### The uncapped reference

```
J_bare = (v + k_film) (C_sed - C_water)
```

the flux the same hotspot would emit with no mat, under the same driving
conditions. Attenuation is then a derived, reported quantity with an interval:

```
attenuation = 1 - J_out / J_bare
```

It is never a fixed product specification, and never asserted without `J_bare`.

### Numerical scheme (settled by measurement, not by preference)

`q^{n+1}` is eliminated analytically so the sorption exchange is linear in
`C^{n+1}` and becomes a diagonal term and a source in one tridiagonal system,
solved with `scipy.linalg.solve_banded`:

```
q^{n+1} = (q^n + dt k q_eq^{n+1}) / (1 + dt k)

unsaturated (q_eq = Kd C):  rho_b (q^{n+1} - q^n)/dt = A C^{n+1} - B
    A = rho_b k Kd / (1 + dt k)      B = rho_b k q^n / (1 + dt k)
saturated  (q_eq = q_max):  rho_b (q^{n+1} - q^n)/dt = -Dsat
    Dsat = rho_b k (q_max - q^n) / (1 + dt k)
```

The branch is chosen per cell by Picard iteration. A cell already at its
effective capacity is locked (`dq/dt=0`), including under flushing. This
unvalidated constitutive discontinuity is exposed by the numerical audit.
An unconverged branch mask raises an error rather than returning a clipped
state as a successful solve. The equations above show the general eliminated
kinetic term; the implementation also includes element allocation and
availability, as documented in `manuscript/methods.tex`.

**An operator split must not be used here.** It was tried, and it diverged under
time-step refinement while conserving mass to 1e-14: breakthrough moved from
4.21 years at `dt = 6 h` to 1.03 years at `dt = 0.5 h`, with the attenuation
curve swinging by more than the whole bare flux. Mass conservation alone does
not validate a scheme, so the acceptance tests include a refinement check.

Current numerical evidence is in `docs/TIMESCALES.md` and
`manuscript/data/reactive_numerical_audit.json`. It includes independent
adaptive-ODE transients, stationary face balances and spatial refinement.
Old timing and breakthrough figures from a different parameter set are not
acceptance evidence for the current six scenarios.

FiPy remains the 2-D engine, and also the **independent cross-check oracle** for
the layer: a pure-diffusion case matches a FiPy `Grid1D` solve to 2.6e-13.

### Conservation, per unit area

```
d/dt integral_0^L (theta C + rho_b q) dz = J_in - J_out
```

Boundary fluxes are evaluated on the transport substep, at the new time level,
with the same discrete coefficients the matrix uses. Sorption moves mass inside
a cell and crosses no boundary. Capacity clipping returns the excess to the
porewater rather than deleting it, and the corrected mass is reported in
`LayerStep.diagnostics['clip_correction_kg']`.

### Allocation between Pb, Hg and Cu

`q_max` applies to the medium **allocated** to that element:

```
capacity_kg_per_m2 = rho_b * L * allocation_fraction * q_max
```

Allocations sum to at most 1. Capacity is not assigned independently in full
to each of the three metals. Default allocations are 0.6/0.3/0.1.

---

## 4. The four degradation modes, kept independent

They are separate fields on `MatTileState` and separate members of
`DegradationMode`. Reading every performance loss as chemical saturation is the
specific failure this design prevents.

**1. Saturation and breakthrough**: capacity consumed; `q -> q_max` from the
sediment face upward, and `J_out` rises toward `J_bare`.

**2. Fouling and pore blockage**: `fouling_index f` in `[0, 1]`:

```
k_eff     = k     (1 - gamma_k f)
q_max_eff = q_max (1 - gamma_c f)
D_eff_eff = D_eff (1 - gamma_D f)
```

Fouling never deletes sorbed metal. If `q_max_eff` falls below the current load,
further uptake stops and `q` is unchanged.

Lower permeability also *lowers* the flux through the layer, so pore blockage
would look like an improvement if modelled alone. It is not free: the head
across the layer rises and flow is pushed around the tile edge,

```
bypass_fraction = edge_leakage_fraction + fouling_bypass_coupling * f
```

so the bypassed share of the area emits `J_bare`.

**3. Displacement, burial, erosion, scour, uplift**: physical position.
A displaced tile has `coverage_fraction = 0`: its cells return to the bare flux
immediately. Burial adds diffusive path,

```
g_top_buried = 1 / (1/g_top + burial_resistance_s_per_m * burial_depth_m)
```

which *reduces* the apparent flux. **Burial can masquerade as success**, and the
estimator must be able to say so: `AmbiguityFlag.BURIAL` exists for this.

**4. Local damage**: `integrity_index i` in `[0, 1]`. The intact share `i`
emits the layer's `J_out`; the torn share `1 - i` emits `J_bare`. Damage is
per tile, so failure is spatially local.

---

## 5. Coupling: from tile states to a residual source flux

Per seabed cell in the hotspot:

```
covered_fraction = sum over tiles overlapping the cell of
                   (tile coverage_fraction * area weight)
bypass           = edge_leakage_fraction + fouling_bypass_coupling * f
effective_cover  = covered_fraction * (1 - bypass)

J_cell = effective_cover * J_out(tile) + (1 - effective_cover) * J_bare
```

Cells outside the mat footprint emit `J_bare`. The result is a
`SeabedSourceField` in kg m^-2 s^-1, with the covered, uncovered, damaged and
edge-leakage contributions kept separately in `components` so a map can show
*why* a cell emits.

This is the whole coupling. Nothing is subtracted from a water-column cell, and
there is no interception efficiency anywhere.

Overlapping tiles beyond the configured `overlap_m` are rejected in this
version rather than silently double-counted.

---

## 6. Macro model: 2-D advection and diffusion

For each element, over the overlying layer of effective mixing depth `H`:

```
dc/dt + div(u c) - div(D grad c) = J_seabed / H
```

`J_seabed` is the `SeabedSourceField` in kg m^-2 s^-1, so dividing by `H` gives
the volumetric source. There is no decay term: Pb and Hg are elements and are
not destroyed, only moved between ledger compartments.

Discretisation: FiPy finite volume, `TransientTerm` + `PowerLawConvectionTerm` +
`DiffusionTerm`, implicit in time [S06]. Land cells are no-flux and hold no
water; open boundaries are outflow.

Boundary accounting over one step, with `m` the dissolved mass in the water:

```
net_boundary_export = released_from_seabed - (m_after - m_before)
boundary_out = max(net_boundary_export, 0)
boundary_in  = max(-net_boundary_export, 0)
```

exact for a conservative scheme, so any numerical loss lands in `boundary_out`.
It is cross-checked by an independent exterior-face flux sum, and the difference
is reported as `closure_error_kg`. A closed domain must give `boundary_out ~ 0`;
that is the honest conservation test. Negative concentrations are clipped and
the clipped mass recorded in `clip_correction_kg`. Clipping is never silent.

---

## 7. Per-element mass ledger

```
initial_water + released_from_sediment + boundary_in
  == in_water + retained_in_mat + retained_in_retrieved_media
     + boundary_out + numerical_correction
```

The meaning of `released_from_sediment` depends on the stated control volume:
in the column ledger it is input through all full tile sediment faces; in a
plume ledger it is source mass injected into water during that window. The
separate `hotspot_released_kg` is the gross bare-reference integral, and
`hotspot_into_water_kg` is the actual area-mixed residual-source integral.
Initial column inventory, if supplied, enters the column ledger through
`boundary_in_kg` as a commissioning transfer. It is not initial coastal water.

Column inventory is not scaled by dynamic bypass. The full-column ledger and
area-mixed hotspot output therefore do not constitute a globally closed
sediment--mat--water model. The prescribed sediment reservoir is not depleted.

Replacement moves the retained inventory of the replaced tiles into the
retrieved-media ledger and issues a new `media_id`; capacity resets, captured
mass does not disappear, and nothing is returned to the sea.

Tolerance: relative imbalance below 1e-9 for the layer, below 1e-6 with open
coastal boundaries. The value achieved is written into `manifest.json` whether
it passes or not.

---

## 8. Observation operator

The monitoring contract recognises Pb and Hg chemistry. Cu is simulated but has
no implemented monitoring channel. Temperature, conductivity, salinity, pH,
turbidity, redox, sulfide and current cannot supply a metal concentration.

The runner generates readings on an experiment-wide campaign clock, retains
laboratory/survey latency, gates records by `available_at_utc`, applies QC, and
passes the resulting records to the estimator. The estimator repeats the time
gate and invokes `classify_record` before selecting evidence. Only passed,
compatible records on a deployed tile can enter its calculations. QC identity
includes station, asset, parameter, method, quantity, matrix, fraction and tile.

| Record | Operator target and current estimator use |
|---|---|
| porewater Pb, dissolved-filtered | sediment-face concentration; source-flux estimate |
| porewater Hg, dissolved-inorganic | sediment-face concentration; inorganic-Hg source estimate |
| benthic-chamber Pb, total-recoverable; Hg, dissolved-inorganic | apparent areal flux; residual-flux estimate |
| bottom-water Pb/Hg | water concentration; not converted to flux by the current estimator |
| DGT mass over a deployment window | integrated exposure; retained, not used by the current interval estimator |
| retrieved-media assay | old-media loading evidence; not assimilated as the new media's loading |
| ROV/survey/acoustic condition | local physical condition; never chemistry |
| differential head | a resolved rise from a same-unit baseline can support fouling |

Matrices and chemical fractions are explicit. MeHg never substitutes for
inorganic Hg. DGT-labile and voltammetric labile pools are not merged. The generic
operator has an optional uncertain total-recoverable-to-labile ratio, disabled
by default; the implemented estimator uses exact configured fractions.

Below-LOD/LOQ results retain finite bounds and no point value. Above-range is a
one-sided lower bound. Missing contributes no chemical evidence. A completed
sample can remain unavailable until its laboratory latency expires. Chamber
and DGT windows can cross controller decision dates without resetting their
deployment clock. Missing head or tilt in a supplied scene produces a missing
record rather than a fabricated zero.

---

## 9. Estimator

`estimate_tiles(records, known, config, now)` is deterministic interval
arithmetic. It does not run an ensemble, fit a likelihood, compute weighted
quantiles or infer a Bayesian posterior. `ensemble_size` is zero. The stored
nominal `interval_level=0.90` is metadata, not demonstrated statistical coverage.

A quantified chemical result forms `[max(value-2*sigma,0), value+2*sigma]`.
If sigma was not reported, an explicitly labelled assumption uses
`sigma=0.50*abs(value)`. Non-detect bounds are preserved. Above-range uses
`[lower,+infinity]`; no arbitrary finite upper limit is invented.

The latest compatible porewater interval is multiplied by the assumed seepage
band `[0.4,2.5]` times design seepage. Latest chamber flux provides residual
flux. Intervals widen geometrically with positive endpoints as data age grows
(default 0.35 per year), and borrowed tile chemistry receives an additional
0.50 widening factor. Attenuation is `1-residual/source`, clipped to `[0,1]`,
when the source excludes zero. Otherwise it is reported as uninformative
`[0,1]`. Thus the estimate cannot represent negative attenuation from release;
the simulated-truth flux and plots retain that possibility.

Capture bounds integrate `max(source-residual,0)` with zero-order-held chemistry.
The first sample is held backwards to installation, a stated extrapolation.
Integration resets at replacement; source history remains available, but old
condition/chamber evidence and chamber deployments straddling service are
excluded. Inventory bounds are capped by the stated capacity upper bound.
Remaining capacity subtracts loading bounds from the configured capacity band;
the loading point summary is the interval midpoint. The configured synthetic
commissioning band is used when present, otherwise the wider capacity interval.
Neither is a measurement of this finished mat.

Breakthrough is remaining capacity divided by current capture, only when the
capture lower bound is positive; otherwise it is `None`. Fouling-index and
effective-permeability intervals and model-data compatibility remain `None`.
Unobserved sources retain a legacy zero sentinel with `INSUFFICIENT_DATA`; this
is not a measured zero and does not support attenuation attribution or service.

Four degradation scores start equal and are normalised after heuristic
increments: local damage +3; resolved displacement +2; resolved fouling +2;
compatible chemistry permitting reduced attenuation with physical evidence +1
to saturation. These are relative scores, not probabilities. Only elements with
measured compatible porewater and chamber and a computable source ratio enter
the chemistry attribution; unsupported Cu and missing channels cannot imply
performance loss. Without physical evidence, ambiguous reduced attenuation can
raise source-increase and advective-change flags.

Physical attribution uses the latest observation, its uncertainty and its actual
value. Non-intact inspection classes support damage. Coverage below 0.98 or
nonzero displacement must be resolved beyond two reported standard deviations.
Burial is flagged only when the latest depth minus two standard deviations is
positive. A head rise/permeability fall requires nonoverlapping two-sigma bands
against the earliest available same-unit baseline. These thresholds are
demonstration assumptions. Burial does not establish chemical capture.

---

## 10. Policy (transparent rules, evaluated in order)

`recommend(estimates, known, config, now, elapsed_s, state)` implements three
policies. `none` deploys no mat and emits no recommendations. `fixed` replaces
all tiles at the configured interval and otherwise recommends monitoring.
`evidence_informed` evaluates each tile as follows:

1. A recent damage-class integrity band whose upper endpoint is below
   `minimum_coverage_fraction` supports inspection and partial replacement.
2. Each supported Pb/Hg porewater and chamber channel must be present and no
   older than `max_data_age_s`, with at least `min_evidence_records` chemical
   evidence IDs. Missing/stale/thin chemistry requests a chemical sample.
   Fresh physical observations cannot refresh chemical data age.
3. Saturation is loading divided by capacity as an interval. Its configured
   `lower`, `mid` or `upper` decision value is compared with the replacement
   threshold. Replacement is blocked by source-increase, advective-change or
   burial ambiguity and produces `PERFORMANCE_UNCERTAIN` with a request for
   source chemistry; otherwise affected tiles receive a partial-replacement
   recommendation.
4. Crossing the inspection saturation threshold, or an attenuation upper bound
   below `minimum_acceptable_attenuation`, supports inspection.
5. With no triggered action, continue monitoring.

The implementation does not use `max_relative_interval_width` or
`allow_partial_replacement`, issue `CHECK_SENSOR`, or compare Bayesian mode
likelihoods. The frozen vocabulary is broader than the emitted action set.
Full channel ages are in estimate snapshots; recommendation-level `data_age_s`
currently remains `None`. Recommendation records preserve their actual
evidence IDs, which can be empty for calendar or monitoring actions.

The simulated runner immediately accepts replacement recommendations and writes
a separate `ServiceEvent`; it has no pending-approval or execution-delay model.
Every recommendation still enforces `human_confirmation_required=True` and
`execution_mode="simulation_only"`. Reported incurred costs cover accepted
service events, not the complete monitoring programme. Comparisons hold source,
forcing, seed and observation schedules fixed; changing service changes later
physical state and therefore the measurements.

---

## 11. Methylmercury: a risk, never a benefit

Capping can alter sediment redox and increase methylmercury production, a risk
requiring experimental evaluation [S04]. The implemented generator emits a
separate MeHg fraction channel using a synthetic 0.04 fraction of its inorganic
Hg reading and additional noise. This is not a methylation-rate model. The
inorganic-Hg estimator excludes that channel. No redox-driven MeHg risk term,
ecological objective or optimisation constraint is implemented, and simulated
inorganic-Hg attenuation cannot establish MeHg safety.

---

## 12. Numerical acceptance

* concentrations and loadings non-negative within a reported tolerance,
  corrections logged;
* per-element mass conservation, layer and coastal, section 7;
* zero capacity gives zero retention; zero source gives no metal anywhere;
* `J_out <= J_bare` for an intact mat, and `J_out == J_bare` where there is none;
* an intact fresh mat attenuates; a saturated one attenuates less; a displaced
  tile does not attenuate at all;
* **time-step refinement**: halving `dt` must change breakthrough time and
  loading by less than the tolerance stated in the test. This test exists
  because a mass-conserving scheme was already found to be wrong;
* grid refinement for the coastal model;
* identical forcing for the no-mat and mat runs, asserted by comparing arrays.
