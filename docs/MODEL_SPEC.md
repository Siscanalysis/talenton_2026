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

A reactive cap works over months to years; a coastal plume equilibrates in
hours. Marching the 2-D field for years would be unaffordable and would say
nothing. The two scales are therefore run on their own clocks and reported with
their own ledgers:

* **Mat timeline** — the whole simulated duration (1 to 6 years),
  `dt = 6 h`, cheap 1-D solves per tile. Produces loading, remaining capacity,
  attenuation, breakthrough and the maintenance decisions.
* **Plume windows** — at the mat states named by `PlumeWindowConfig.sample_years`,
  the 2-D model runs over a few tidal days with the residual flux held at that
  mat state. Produces the maps and the water-column budget.

Nothing may imply the coastal model was integrated for years. The exports label
each ledger with its own window.

---

## 3. Micro model: the 1-D reactive layer

Per tile, per element, through the layer thickness `z` in `[0, L]`:

```
theta dC/dt = d/dz(theta D_eff dC/dz) - v dC/dz - rho_b dq/dt
dq/dt       = k_eff (q_eq(C) - q),      q_eq(C) = min(Kd C, q_max_eff)
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

**Advection is not optional.** With `D_eff = 2e-10` and a 5 cm layer, a purely
diffusive cap attenuates by a factor of about 2500 and would take millennia to
saturate: the sorbent would be irrelevant. A reactive cap is designed against
*advective* flux, so `v` is a first-class term.

### Boundary conditions

* `z = 0`, sediment face: prescribed porewater concentration `C_sed` from the
  hotspot schedule, with advective inflow `v C_sed` and a diffusive term across
  the half cell.
* `z = L`, water face: advection out plus the benthic boundary layer in series,

```
g_top = 1 / ( dz / (2 theta D_eff) + 1 / k_film )
J_out = v C[L] + g_top (C[L] - C_water)
```

`C_water` is the bottom-water concentration taken from the coastal field, so a
rising plume genuinely reduces the driving gradient.

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

The saturated branch is chosen per cell by Picard iteration.

**An operator split must not be used here.** It was tried, and it diverged under
time-step refinement while conserving mass to 1e-14: breakthrough moved from
4.21 years at `dt = 6 h` to 1.03 years at `dt = 0.5 h`, with the attenuation
curve swinging by more than the whole bare flux. Mass conservation alone does
not validate a scheme, so the acceptance tests include a refinement check.

The implicit scheme converges: breakthrough 3.086 to 3.088 years across `dt`
from 12 h to 0.5 h, monotonic while loading, mass conserved to 1e-12, and
1.8 s for eight simulated years.

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

### Allocation between Pb and Hg

`q_max` applies to the medium **allocated** to that element:

```
capacity_kg_per_m2 = rho_b * L * allocation_fraction * q_max
```

Allocations sum to at most 1. Capacity is never assigned to both metals.

---

## 4. The four degradation modes, kept independent

They are separate fields on `MatTileState` and separate members of
`DegradationMode`. Reading every performance loss as chemical saturation is the
specific failure this design prevents.

**1. Saturation and breakthrough** — capacity consumed; `q -> q_max` from the
sediment face upward, and `J_out` rises toward `J_bare`.

**2. Fouling and pore blockage** — `fouling_index f` in `[0, 1]`:

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

**3. Displacement, burial, erosion, scour, uplift** — physical position.
A displaced tile has `coverage_fraction = 0`: its cells return to the bare flux
immediately. Burial adds diffusive path,

```
g_top_buried = 1 / (1/g_top + burial_resistance_s_per_m * burial_depth_m)
```

which *reduces* the apparent flux. **Burial can masquerade as success**, and the
estimator must be able to say so: `AmbiguityFlag.BURIAL` exists for this.

**4. Local damage** — `integrity_index i` in `[0, 1]`. The intact share `i`
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

`released_from_sediment` is the gross mass that left the sediment, whether it
entered a tile or passed straight into the water. The sediment reservoir is
prescribed and not depleted: a documented assumption, not a conservation claim.

Replacement moves the retained inventory of the replaced tiles into the
retrieved-media ledger and issues a new `media_id`; capacity resets, captured
mass does not disappear, and nothing is returned to the sea.

Tolerance: relative imbalance below 1e-9 for the layer, below 1e-6 with open
coastal boundaries. The value achieved is written into `manifest.json` whether
it passes or not.

---

## 8. Observation operator

Only `Pb` and `Hg` records carry chemical information. Temperature,
conductivity, salinity, pH, turbidity, redox and sulfide constrain conditions or
QC only. Removing every context record must leave the metal estimate unchanged,
and `tests/estimation/` asserts it.

Assimilable aqueous matrices are `porewater`, `mat_porewater`, `bottom_water`
and `seawater`. **Porewater is now a primary channel**: it is the driving
boundary condition of the layer.

| Record | Constrains |
|---|---|
| porewater Pb/Hg at the sediment face | `C_sed`, the driving condition |
| bottom-water Pb/Hg above the mat | `C_water` and the residual flux |
| benthic-chamber areal flux | `J_out` directly, the quantity the mat is judged on |
| DGT accumulated mass over a window | a time-integrated labile pool, never a point ng/L |
| retrieved-media assay | the loading of the **old** media, not the tile now in place |
| ROV / survey condition records | modes 3 and 4, per tile, never chemistry |
| differential head | mode 2, separating fouling from saturation |

A `total_recoverable` record is not assimilated against a `labile` model state
unless an explicit, documented, uncertain ratio operator is switched on. Default
off: such records are retained as unassimilated evidence. `dgt_labile` and
`labile` are different operationally defined pools and are never merged.

Censoring: below LOD/LOQ gives `value = null` with a finite interval;
`above_range` gives a lower bound only; `missing` gives nothing at all and
widens the interval. Laboratory records carry
`available_at_utc = observed_at_utc + lab_latency_s`.

---

## 9. Estimator

Members sample `(Kd, q_max, k, D_eff, edge leakage, C_sed bias)` from the
configured intervals with the run seed, and integrate the reduced layer model
driven only by observed quantities. No member sees the truth store.

Likelihood: Gaussian for quantified records; for censored records the normal CDF
over the interval, so a bound is used as a bound; missing records contribute
nothing; `quality_flag` 3 and 4 are excluded from the likelihood but kept as
sensor-health evidence. Weights are normalised likelihoods; reported values are
the weighted median and the weighted 5th and 95th percentiles.

Estimated quantities are limited to what the observations plausibly constrain:
loading, remaining capacity, residual flux, source flux, attenuation, fouling,
integrity, effective permeability, and a breakthrough interval.

**Remaining life is an interval or `None`.** A falsely precise remaining-life
number is worse than an honest "not determined".

Degradation-mode attribution: the same weighted likelihood is evaluated per
mode, and `EstimateSnapshot.degradation_mode_weights` reports all four side by
side. When the best two explanations are within a likelihood ratio of 3, both
ambiguity flags are raised and the policy may answer `PERFORMANCE_UNCERTAIN`.

---

## 10. Policy (transparent rules, evaluated in order)

1. Sensor failed, stuck or stale beyond `max_data_age_s` -> `CHECK_SENSOR`.
2. Condition evidence shows coverage below `minimum_coverage_fraction`, or a
   damage class worse than intact -> `INSPECT_MAT`, then
   `PLAN_PARTIAL_REPLACEMENT` for the affected tiles only.
3. Fewer than `min_evidence_records` usable metal records, or none within
   `max_data_age_s` -> `TAKE_CHEMICAL_SAMPLE`.
4. Relative interval width above `max_relative_interval_width`, or two competing
   degradation modes within the ambiguity ratio -> `PERFORMANCE_UNCERTAIN`.
5. Lower bound of saturation at or above `replacement_saturation_threshold`, or
   upper bound of attenuation below `minimum_acceptable_attenuation`
   -> `REPLACE_ACTIVE_PANEL` (or `PLAN_PARTIAL_REPLACEMENT` when only some tiles
   qualify and `allow_partial_replacement` is set).
6. Median saturation at or above `inspection_saturation_threshold` -> `INSPECT_MAT`.
7. Otherwise -> `CONTINUE_MONITORING`.

A replacement is suppressed while an accepted one for the same tiles is pending.
Every recommendation carries evidence IDs, data age, uncertainty,
`human_confirmation_required = True` and `execution_mode = "simulation_only"`.

The `fixed` policy replaces on `fixed_interval_s` regardless of evidence. The
`none` policy runs the identical hotspot with no mat. All three are compared
with the same seed, forcing, hotspot schedule and measurement budget.

---

## 11. Methylmercury: a risk, never a benefit

Capping alters sediment redox and can **increase** methylmercury production. The
demonstrator therefore carries a `methylmercury` fraction channel and an
explicit, wide-interval risk term driven by the redox conditions under the mat,
reported alongside the Pb and Hg attenuation, and available as an ecological
constraint in the optimisation. Ecological safety is a validation constraint
here, not an automatic benefit of capping [S04].

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
