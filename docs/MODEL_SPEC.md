# Model specification (coordinator-owned, frozen with the contracts)

Status: **synthetic demonstration model.** Every parameter below is an
assumption chosen so that a short demonstration shows loading, saturation and
maintenance. None of it is a validated product specification, and none of it is
transferred from [S01] or [S04] as an operating capacity.

Symbols use SI internally: mass kg, aqueous concentration kg m^-3, loading
kg kg^-1, length m, time s (see `src/reactive_seabed_mat/units.py`).

---

## 1. Three separated states

| Store | Written by | Readable by |
|---|---|---|
| `results/<run>/truth/` | simulator | tests, evaluation toggle in the UI |
| `results/<run>/observations/` | observation generator | estimator, policy, UI |
| `results/<run>/estimates/` | estimator | policy, UI |

`src/reactive_seabed_mat/feedback/` and the estimator must never import from the truth
store. `tests/feedback/test_no_hidden_truth.py` enforces this by static import
inspection and by running the estimator with the truth directory removed.

---

## 2. Macro model: 2D advection–diffusion

For each element `e` with dissolved concentration `c_e(x, y, t)` [kg m^-3] over
a depth-averaged layer of effective mixing depth `H` [m]:

```
dc_e/dt + div(u c_e) - div(D grad c_e) = S_e / (dx dy H)
```

* `u = (u_east, v_north)` [m s^-1], prescribed, depth-averaged.
* `D` [m^2 s^-1] is a single effective horizontal mixing coefficient. It lumps
  turbulent diffusion and unresolved shear dispersion; it is an assumption.
* `S_e` [kg s^-1] is the hypothetical source, applied to one cell.
* There is **no** first-order decay term. Pb and Hg are elements: they are not
  destroyed, only moved between the ledger compartments of section 5.

Discretisation: FiPy finite volume, `TransientTerm` + `PowerLawConvectionTerm`
+ `DiffusionTerm`, implicit in time [S06]. We supply the formulation, boundary
conditions and validation; FiPy supplies the solver.

**Boundaries.** Land cells are no-flux: convection and diffusion coefficients
are zeroed on land faces, and land cells carry no water volume. Open-water
boundaries are outflow (`faceGrad` constrained to zero) so mass may leave.

**Panel uptake is not a PDE sink term.** It is applied exactly once, explicitly,
in `apply_transfers`, after `transport_step`. Implementing it a second time as
an implicit sink would remove the same mass twice.

**Boundary accounting.** Over one step, with `m` the total dissolved mass in the
water:

```
net_boundary_export = emitted - (m_after - m_before)
boundary_out = max(net_boundary_export, 0)
boundary_in  = max(-net_boundary_export, 0)
```

This identity is exact for a conservative scheme, so any numerical loss lands in
`boundary_out`. It is therefore cross-checked two ways, both reported in
`TransportStep.diagnostics`:

1. an independent exterior-face flux sum (`face_flux_export_kg`), and
2. `closure_error_kg = net_boundary_export - face_flux_export_kg`.

A **closed** domain (all boundaries no-flux) must give `boundary_out ≈ 0`; that
is the honest conservation test, and its tolerance is stated in the test.

Negative concentrations produced by the scheme are clipped to zero **and the
clipped mass is recorded** in `diagnostics['clip_correction_kg']`, which flows
into `MassLedger.numerical_correction_kg`. Clipping is never silent.

---

## 3. Contact model: what the panel actually sees

A panel of frontal area `A = w * h` [m^2] sits in one or more grid cells. Over a
step of length `dt`, with local speed `s = |u|`:

```
swept_volume   V_sw = s * A * phi * dt
cell_inventory m_cell,e = c_e * dx * dy * H     (per covered water cell)
available_kg   m_avail,e = min( c_e * V_sw , theta * sum_cells m_cell,e )
```

* `phi` = `PanelGeometry.interception_efficiency` — the **documented, uncertain**
  fraction of the water crossing the panel's frontal area that actually contacts
  reactive material. It is not a claim that every molecule in a map cell passes
  through a small panel. Default 0.45, interval [0.15, 0.75], assumption.
* `theta` = 0.5, the largest share of a cell's inventory removable in one step.
  It keeps the explicit coupling stable and makes "remove more than exists"
  structurally impossible.
* `exchange_is_measured = False`: the exchange volume is assumed, not measured.

`build_contacts` returns one `ContactBatch` per panel with `cell_indices` and
area `cell_weights` summing to 1; `apply_transfers` subtracts the actual uptake
from those cells with those weights, and adds any release back the same way —
exactly one subtraction/addition per transfer.

Overlapping panels are rejected in this version.

---

## 4. Micro model: capped linear isotherm, first-order approach

Per panel and per element `e`, with sorbent mass `M` [kg] and allocation
fraction `alpha_e` (the allocations must sum to at most 1 — mesh capacity is
never assigned to both metals):

```
M_e   = M * alpha_e                       allocated sorbent mass
q     = R_e / M_e                         current loading [kg/kg]
```

Fouling `f in [0, 1]` reduces access and rate but never erases sorbed metal:

```
k_eff     = k_e * (1 - gamma_k * f)       gamma_k = fouling_rate_kinetics
q_max_eff = q_max_e * (1 - gamma_c * f)   gamma_c = fouling_rate_capacity
```

Capped linear isotherm and first-order approach to equilibrium, with the
contact concentration `c_e` held constant over the step (exact exponential
update, so the step is stable at any `dt`):

```
q_eq = min(Kd_e * c_e, q_max_eff)
q*   = q_eq + (q - q_eq) * exp(-k_eff * dt)
```

The desired transfer is then bounded, in this order, by the mass that is
actually there and by the capacity that is actually left:

```
dm_desired  = M_e * (q* - q)
C_remaining = max(0, M_e * q_max_eff - R_e)
dm          = clip( dm_desired , 0 , min(m_avail,e , C_remaining) )
```

* `q_max_e = 0` (or `alpha_e = 0`) gives `dm = 0`. Zero capacity, zero capture.
* `m_avail = 0` gives `dm = 0`. No water, no capture.
* If fouling pushes `q_max_eff * M_e` below `R_e`, then `C_remaining = 0`: the
  panel stops taking up metal, and `R_e` is unchanged. Fouling never deletes
  retained mass.
* `PanelStep.diagnostics['binding_constraint']` records which bound was active
  (`kinetics`, `available_mass`, `capacity`), and by how much the desired
  transfer was reduced.

A high-capacity material can still perform badly: `q_max` large with `k_eff`
small, or `phi` small, gives negligible capture. That is the poor-performance
scene, and it is a real outcome of these equations, not a special case.

**Analytical check.** With `m_avail -> inf`, `C_remaining -> inf` and constant
`c`, the update reduces to `q(t) = q_eq + (q0 - q_eq) exp(-k t)`, which
`tests/micro/test_analytical_first_order.py` compares against directly.

**Fouling growth.** `f <- min(1, f + fouling_growth_per_s * dt)`; reset to 0 on
replacement.

**Optional desorption / damage.** An explicit event returns
`release_kg_by_element > 0`; `R_e` decreases by exactly that amount and
`apply_transfers` adds exactly that mass back to the water cells. Nothing is
destroyed.

**Replacement.**

```
retrieved_ledger[e] += R_e
R_e = 0 ; f = 0 ; media_id = new ; service_count += 1
```

Total inventory (water + active + retrieved + exported) is unchanged by the
event. Capacity resets; captured mass does not disappear.

**Remaining service life** is a conditional interval, not a sensor reading.
Assuming the recent contact concentration persists, the time to reach a target
loading `q_target = rho * q_max_eff` follows from the same exponential:

```
t = -(1/k_eff) * ln( (q_target - q_eq) / (q0 - q_eq) )    if q_eq > q_target
t = None (never reached under this assumption)            otherwise
```

Evaluated across the parameter ensemble this yields the interval reported in
`EstimateSnapshot.remaining_life_s_interval`. It is conditional on the assumed
future forcing, and the UI must say so.

---

## 5. Per-element mass ledger

```
initial_water + emitted + boundary_in
  == in_water + in_active_mesh + in_retrieved_media + boundary_out
     + numerical_correction
```

Checked per element after every run (`tests/integration/`). Tolerance:
relative imbalance below 1e-9 for a closed domain, below 1e-6 with open
boundaries; the actual value is written into `manifest.json` whether it passes
or not.

---

## 6. Observation operator

Only `Pb` and `Hg` records carry chemical information. Temperature,
conductivity, salinity, pH and turbidity constrain water conditions or QC only;
`tests/feedback/` asserts that removing every context record leaves the metal
estimate unchanged.

For an in-situ metal probe at station `k`, matrix `seawater`, fraction `labile`:

```
value_reported = c_true,labile(x_k, y_k, t) * (1 + drift(t)) * (1 + eps),
    eps ~ N(0, sigma_rel)
```

with `c_true,labile = chi_labile * c_true,dissolved`, `chi_labile` an explicit
assumed fraction ratio (default 1.0 for the demo, i.e. the simulated dissolved
pool *is* the labile pool, stated rather than hidden).

* below LOD: `value = null`, `qualifier = below_lod`, interval `[0, LOD]`.
* below LOQ: `value = null`, `qualifier = below_loq`, interval `[LOD, LOQ]`.
* dropout window: `qualifier = missing`, `quality_flag = 9`, no interval.
* laboratory records: `available_at_utc = observed_at_utc + lab_latency_s`.

A `total_recoverable` record is **not** assimilated against a `labile` model
state unless an explicit observation operator with a documented, uncertain ratio
is switched on. By default such records are retained as *unassimilated
evidence*, visible in the UI, contributing to data age but not to the
likelihood.

Passive-sampler records store accumulated mass in `ng` with an exposure window.
The first release displays them and records their metadata; it does not force
them into ng/L.

---

## 7. Estimator (ensemble, importance-weighted)

Members `j = 1..N` sample `(Kd, q_max, k, phi, c_bias)` from the configured
intervals with the run seed. Each member integrates the **reduced** panel model
of section 4, driven only by observed quantities: measured current speed and
the measured upstream metal concentration. No member sees the truth store.

Likelihood of member `j` given the available records:

* quantified: `N(value | c_pred, sigma)`, `sigma` from `uncertainty_std` when
  present, otherwise from the configured relative noise (recorded as an
  assumption).
* censored: `Phi((upper - c_pred)/sigma) - Phi((lower - c_pred)/sigma)` — the
  bound is used as a bound.
* missing: contributes nothing. Missing chemistry widens the interval; it never
  produces a confident prediction.
* `quality_flag in {3, 4}`: excluded from the likelihood, kept as sensor-health
  evidence.

Weights `w_j ∝ L_j`, normalised. Reported estimates are the weighted median and
the weighted 5th/95th percentiles (`interval_level = 0.90`, documented in the
snapshot).

**Downstream comparison.** A two-station concentration difference is never
reported as treatment efficiency. The estimator relates the two stations through
an explicit reduced transport interpretation (advective travel time and the
capture fraction implied by section 3); the UI labels this as a model-based
interpretation, not a measurement.

**Ambiguity.** Hypotheses `{saturation, source_increase, plume_shift, fouling,
sensor_drift}` are scored by the same weighted likelihood restricted to members
consistent with each. When the best two are within a likelihood ratio of 3, both
flags are raised and the policy is allowed to answer `INSUFFICIENT_EVIDENCE`.

---

## 8. Policy (transparent rules, evaluated in order)

1. Sensor health failed / stuck / stale beyond `max_data_age_s` → `CHECK_SENSOR`.
2. Fewer than `min_evidence_records` usable metal records, or none within
   `max_data_age_s` → `REQUEST_CHEMICAL_SAMPLE`, or `INSUFFICIENT_EVIDENCE` when
   a sample is already pending.
3. Relative interval width above `max_relative_interval_width` →
   `REQUEST_CHEMICAL_SAMPLE`.
4. Lower bound of estimated loading ≥ `replacement_loading_threshold` →
   `PLAN_REPLACEMENT`.
5. Median loading ≥ `inspection_loading_threshold`, or a fouling/ambiguity flag
   → `INSPECT_MESH`.
6. Otherwise → `CONTINUE`.

A `PLAN_REPLACEMENT` is suppressed while an accepted replacement for the same
`media_id` is pending: duplicate recommendations cannot create repeated
replacements. Every recommendation carries evidence IDs, data age, uncertainty,
`human_confirmation_required = True` and `execution_mode = "simulation_only"`.

The `fixed` policy ignores the evidence and replaces every
`fixed_interval_s`. The `none` policy runs the identical forcing with no panel.
All three are compared with the same seed, same forcing and same measurement
budget.

---

## 9. Numerical acceptance

* concentrations ≥ 0 within a reported tolerance, corrections logged;
* per-element mass conservation (section 5);
* zero capacity → zero capture; zero source and zero initial mass → no metal;
* replacement preserves total inventory;
* time-step halving and grid refinement change the captured mass by less than
  the tolerance stated in the test;
* identical forcing for the no-mesh and mesh scenarios (asserted by comparing
  the forcing hash).
