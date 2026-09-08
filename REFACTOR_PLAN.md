# Refactor plan: vertical reactive mesh to selective reactive seabed mat

Status of this document: the audited plan agreed before the refactor is
executed. It records what survives, what is renamed, what changes physically,
and what is genuinely new. Written after inspecting the existing repository, not
from the brief alone.

Project name: **reactive-seabed-mat-demo**. Python package: `reactive_seabed_mat`.

---

## 1. What actually exists right now

The repository at `software/mesh_demo` is at commit `5993dd1` on `main`, with a
frozen-contract baseline plus three merged work-in-progress branches. Nothing
has been pushed anywhere.

| Area | Lines | Origin | State |
|---|---|---|---|
| `src/mesh_demo/contracts.py` | 700 | coordinator | frozen types, all seven boundary functions |
| `src/mesh_demo/units.py` | 210 | coordinator | SI ladders, tested |
| `src/mesh_demo/config.py` | 330 | coordinator | one run-config schema, tested |
| `src/mesh_demo/observations/records.py` | 300 | coordinator | schema validation, JSONL I/O, availability gate |
| `src/mesh_demo/results.py` | 280 | coordinator | run layout, manifest, state separation |
| `src/mesh_demo/scenarios/registry.py` | 260 | coordinator | seven scenes as config variations |
| `src/mesh_demo/micro/` | 2 490 | `feat/mesh-care` | sorption chemistry, panel step, service, forecast, design sweep |
| `src/mesh_demo/transport/domain.py` | 419 | `feat/coastal-2d` | grid, land mask, forcing, sources |
| `src/mesh_demo/observations/{generator,operator,qc}.py` | 1 946 | `feat/feedback` | synthetic observations, QC, observation operator |
| `tests/contracts/` | 48 tests | coordinator | all passing |

Two branch tasks never started: the FiPy solver itself (`transport/fipy_engine.py`,
`transport/coupling.py`) and the whole `feedback/` package. That is fortunate:
the two modules that would have been most invalidated by the concept change were
never written.

**Verdict: roughly 70 % of the written code survives.** The sorption chemistry,
the whole observation stack, the contracts spine and the configuration machinery
are concept-neutral. What must change is the *geometry of contact* and
everything downstream of it.

---

## 2. The concept change, precisely

Old chain:

```
source -> water-column plume -> vertical mesh panel intercepts a swept volume -> capture
```

New chain:

```
authorised contaminated seabed hotspot
  -> contaminant flux through / near the seabed
  -> reactive mat (thin reactive cap, modular tiles)
  -> residual flux into the overlying water
  -> 2-D coastal advection and diffusion
```

The single most important consequence: **the mat no longer removes mass from
water-column cells.** It sits between the sediment and the water and *attenuates
a boundary flux*. The 2-D model's source term stops being a point release and
becomes a spatially distributed seabed flux whose local value depends on the
local mat state.

That inverts the coupling direction. In the old design the macro model handed
the micro model a contact batch and got back an uptake to subtract. In the new
design the micro model is the *source term generator* for the macro model.

### Physical assumptions that must be deleted

1. **Frontal area swept by a lateral current.** `PanelGeometry.frontal_area_m2`,
   the swept volume `V_sw = s * A * phi * dt`, and the speed dependence of
   contact all disappear. Current speed no longer controls how much contaminant
   reaches the reactive material; it controls what happens to the residual flux
   *after* it leaves the mat.
2. **Interception efficiency `phi`.** The concept of "the fraction of water
   crossing the panel that touches reactive material" has no meaning for a mat
   lying on the seabed. Its replacement is **coverage**: the fraction of the
   hotspot area actually capped by intact mat, plus an explicit **edge and
   bypass leakage** term.
3. **`theta`, the cap on how much of a water cell's inventory one step may
   take.** It existed only to keep an explicit water-column removal stable. The
   flux formulation needs no such guard.
4. **`apply_transfers` subtracting uptake from water cells.** Replaced by a
   source term that is already reduced at the seabed.
5. **Upstream/downstream station pairs as the primary evidence.** Still useful,
   but the primary evidence for a cap is *porewater and near-bed* chemistry plus
   mat-condition inspection, not a two-station water-column difference.

### What replaces them

A 1-D reactive layer through the mat thickness `z in [0, L]`, per tile, per
element:

```
dC/dt   = D_eff d2C/dz2 - v dC/dz - (rho_b / theta_p) dq/dt
dq/dt   = k_eff * (q_eq(C) - q),        q_eq(C) = min(Kd * C, q_max_eff)
```

with `C` the porewater concentration in the mat [kg m^-3], `q` the sorbed
loading [kg kg^-1], `rho_b` the dry bulk density of the reactive medium
[kg m^-3], `theta_p` the porosity, `D_eff` the effective diffusion coefficient
including tortuosity, and `v` the optional porewater Darcy velocity.

Boundary conditions:

* `z = 0` (sediment side): a prescribed contaminant supply. Either a fixed
  porewater concentration `C_sed` or a prescribed bare-sediment flux `J_bare`.
  The demo uses `C_sed` and derives `J_bare` from the same driving gradient with
  no mat present, so "with mat" and "without mat" are genuinely the same source.
* `z = L` (water side): the overlying water is treated as well mixed by the
  coastal model, giving a mass-transfer condition
  `J_out = k_film * (C(L) - C_water)`.

Outputs, which are the whole point of this layer:

```
J_in       kg m^-2 s^-1   flux entering the mat at the sediment face
J_out      kg m^-2 s^-1   residual flux leaving into the water   <- macro source
retained   kg m^-2        stored in the layer (sorbed + porewater)
capacity   kg m^-2        remaining, per element
breakthrough                predicted service window, as an interval
```

Conservation per unit area, checked in the tests:

```
d/dt (integral over z of (theta_p * C + rho_b * q)) = J_in - J_out
```

Attenuation is then a *derived, honest* quantity:

```
attenuation = 1 - J_out / J_bare
```

reported with its uncertainty, never as a fixed product specification.

### Numerical approach, verified before committing to it

Four probes were run before writing any repository code. They changed the
design twice, so they are recorded here rather than summarised.

**Probe 1: FiPy for the 1-D layer: rejected on cost.** A `Grid1D` layer needs
thousands of steps per tile over a multi-year timeline. FiPy's per-solve
overhead made an 8-year run exceed seven minutes and time out. The reuse
decision already assigns *material dynamics* to NumPy/SciPy and *finite-volume
transport* to FiPy [S06, S25]; a 1-D reactive layer is material dynamics.

**Probe 2: SciPy banded implicit solve: 0.67 s for 6 simulated years**, and it
matches a FiPy `Grid1D` solve of the same pure-diffusion case to a maximum
relative difference of 2.6e-13. FiPy is therefore kept as the 2-D engine *and*
as the independent cross-check oracle for the layer, which is a stronger
position than using one solver for both.

**Probe 3: advection is not optional.** With `D_eff = 2e-10` and a 5 cm layer,
a purely diffusive cap already attenuates by a factor of ~2500 and would take
millennia to saturate: the sorbent would be irrelevant. Porewater advection
(seepage and tidal pumping) is what a reactive cap is actually designed
against, so the Darcy velocity `v` is a first-class term. Probe 3 also exposed
a flux-accounting error: boundary fluxes must be evaluated on the transport
substep at the new time level, with the same discrete coefficients the matrix
uses, because sorption moves mass inside a cell and crosses no boundary.

**Probe 4: the operator split is wrong here, and mass conservation did not
reveal it.** With `rho_b * Kd / theta ~ 6000`, a split sorption substep drains
the porewater completely every step. Refining the time step made the answer
*worse*, not better: breakthrough moved from 4.21 years at `dt = 6 h` to 1.03
years at `dt = 0.5 h`, with the attenuation curve swinging non-monotonically by
more than the entire bare flux. Throughout, mass was conserved to 1e-14. **A
conservative scheme can still be a wrong scheme**, and the repository's tests
must therefore include a refinement check, not only a ledger check.

**Probe 5: fully implicit coupled solve: adopted.** Eliminating `q^{n+1}`
analytically makes the sorption exchange linear in `C^{n+1}`, so it becomes a
diagonal term and a source in the same tridiagonal system:

```
q^{n+1} = (q^n + dt k q_eq^{n+1}) / (1 + dt k)

unsaturated (q_eq = Kd C):  rho_b (q^{n+1} - q^n)/dt = A C^{n+1} - B
    A = rho_b k Kd / (1 + dt k)      B = rho_b k q^n / (1 + dt k)
saturated  (q_eq = q_max):  rho_b (q^{n+1} - q^n)/dt = -Dsat
    Dsat = rho_b k (q_max - q^n) / (1 + dt k)
```

with the saturated/unsaturated branch chosen per cell by Picard iteration.
Measured behaviour across `dt` from 12 h down to 0.5 h:

| dt | breakthrough | largest backward step | mass error | final loading |
|---|---|---|---|---|
| 12 h | 3.088 yr | 0 | 1.1e-13 | 98.3 % |
| 6 h | 3.087 yr | 0 | 7.9e-13 | 98.3 % |
| 3 h | 3.086 yr | 0 | 1.3e-13 | 98.3 % |
| 1 h | 3.086 yr | 0 | 6.1e-12 | 98.3 % |
| 0.5 h | 3.086 yr | 0 | 6.0e-12 | 98.3 % |

Converged, monotonic while loading, conservative. `dt = 6 h` costs 1.8 s for
eight simulated years, so a multi-year timeline per tile is affordable.

Capacity clipping returns the excess to the porewater rather than deleting it,
and the corrected mass is reported.

### Two timescales, stated honestly

A reactive cap works over months to years; a coastal plume equilibrates in
hours. Marching the 2-D field for years would be both unaffordable and
pointless. The architecture therefore separates them:

* **Mat timeline**: multi-year, `dt = 6 h`, cheap 1-D solves per tile. Produces
  loading, remaining capacity, attenuation, breakthrough and the maintenance
  decisions.
* **Plume windows**: for a set of mat states named by each scenario, the 2-D
  coastal model is run over a short window (a few tidal days) with the residual
  flux held at that mat state. Produces the maps and the water-column budget.

The two ledgers are reported separately and labelled, so nothing implies the
coastal model was integrated for years.

### Parameters that make the demonstration honest

The probe fixed a self-consistent parameter set (all assumptions):
thickness 10 mm, porosity 0.5, bulk density 400 kg/m^3, `D_eff` 2e-10 m^2/s,
Darcy velocity 3e-8 m/s (about 0.95 m/yr), benthic film 5e-7 m/s, sediment
porewater 1 mg/L, `Kd` 5 m^3/kg, operating capacity 1e-3 kg/kg. This gives
4 kg/m^2 of medium, 4e-3 kg/m^2 of capacity, breakthrough at 3.1 years, and a
Peclet number of 3 through the layer so advection and diffusion both matter.

One consequence must be stated in the demonstration rather than hidden: a
**saturated** mat still attenuates by about 94 %, purely as a diffusive
barrier, while a **fresh** mat attenuates by more than 99 %. The chemical
contribution of the sorbent is the difference between those two numbers, not
the whole attenuation. A thin retrievable mat also buys a shorter service life
than a thick engineered cap, which is precisely why predictive maintenance and
retrievability are the things worth demonstrating.

### Macro coupling

```
for each seabed cell in the contaminated hotspot:
    if covered by an intact tile:  S_cell = J_out(tile) * cell_area
    if uncovered / displaced:      S_cell = J_bare      * cell_area
    if locally damaged (fraction 1 - integrity):
        S_cell = integrity * J_out * area + (1 - integrity) * J_bare * area
    plus an edge-leakage term on footprint boundary cells
```

This makes local failure genuinely local, which is what scenario D needs, and it
makes the poor-design scenario F fall out naturally: a mat that is too small
leaves hotspot cells uncovered and their bare flux dominates the plume.

---

## 3. Terminology map

Applied to user-facing text and identifiers. **Not** applied mechanically:
scientific quantities whose names remain correct keep them.

| Old | New (user-facing) | New (code) |
|---|---|---|
| mesh | reactive mat, mat | `mat` |
| mesh model | reactive-layer model | `reactive_layer` |
| mesh size | mat footprint, area | `footprint_area_m2` |
| mesh thickness | reactive-layer thickness | `thickness_m` |
| mesh loading | sorbent loading | `sorbent_loading_kg_per_m2` |
| mesh saturation | active-media saturation | `saturation_fraction` |
| mesh health | mat condition, integrity | `integrity_index` |
| mesh maintenance | mat maintenance | `maintenance` |
| mesh placement | mat footprint, deployment layout | `layout`, `tiles` |
| mesh capture efficiency | contaminant-flux attenuation | `flux_attenuation` |
| mesh breakthrough | reactive-layer breakthrough | `breakthrough` |
| panel | tile (a replaceable module of the mat) | `tile` |
| `mesh_tilt` observation | mat tilt | `mat_tilt` |
| `PanelState` | mat tile state | `MatTileState` |
| `ContactBatch` | seabed exchange conditions | `SeabedExchange` |
| capture, captured mass | retained mass, attenuated flux | `retained_kg` |

**Names deliberately kept**, because they remain technically correct: `Kd`
(partition coefficient), `q_max` (capacity), `q_eq` (equilibrium loading),
`k_rate_per_s` (first-order rate), `fouling_fraction`, `Element`, `MassLedger`,
every observation-contract field, every unit function, `Forcing`, `GridSpec`,
`FieldState`, `Recommendation`, `EstimateSnapshot`.

---

## 4. Module and API map

### Repository structure

```
reactive-seabed-mat-demo/
    src/reactive_seabed_mat/          (was src/mesh_demo/)
        contracts.py                  frozen types            ADAPT
        units.py                      SI ladders              KEEP
        config.py                     run configuration       ADAPT
        results.py                    run layout, manifest    KEEP
        reactive_layer/               (was micro/)
            material.py               isotherm, kinetics      KEEP
            column.py                 1-D FiPy layer          NEW
            flux.py                   J_in, J_out, attenuation NEW
            tile.py                   tile state, degradation (was panel.py) REWRITE
            service.py                replacement, retrieved ledger  KEEP
            forecast.py               breakthrough intervals  ADAPT
        coastal_transport/            (was transport/)
            domain.py                 grid, land, forcing     ADAPT
            fipy_engine.py            2-D solver              NEW
            seabed_source.py          mat state -> source flux NEW
            geodata/                  Copernicus/EMODnet adapters NEW
        observations/
            records.py                schema, gate            KEEP
            generator.py              synthetic observations  ADAPT
            operator.py               assimilation rules      ADAPT
            qc.py                     QARTOD-style checks     KEEP
            condition.py              mat-condition channels  NEW
        estimation/                   (was feedback/estimator) NEW
        maintenance/                  (was feedback/policy)    NEW
        optimisation/                 design sweep (from micro/design.py) ADAPT
        scenarios/                    registry + coupled run  ADAPT
        visualization/                (was reporting/)         NEW
    research/
        sensors/                      (was docs/research/)
        materials/                    prior art, reactive caps NEW
        references/                   evidence JSON
    data/synthetic/   (was data/examples/)
    data/external/                    cached products, empty by default
    docs/  MODEL_SPEC.md  DATA_CONTRACT.md  ASSUMPTIONS.md  REFERENCES.md
           LIMITATIONS.md  DEMO_SCRIPT.md  PRIOR_ART.md
    tests/  app/
```

`src/` layout is kept rather than a bare top-level package: it prevents
accidental imports of an uninstalled tree, and it is what makes the per-worktree
`conftest.py` isolation work. This is the only deliberate deviation from the
suggested structure.

### Frozen boundary functions, old to new

| Old | New | Note |
|---|---|---|
| `advance_panel(panel_state, contact_batch, material_parameters, dt_s)` | `advance_reactive_layer(layer_state, exchange, material_parameters, dt_s)` | REWRITE: 1-D column, returns fluxes not an uptake |
| `build_contacts(field_state, panels, forcing, dt_s)` | `build_seabed_exchange(field_state, tiles, hotspot, forcing, dt_s)` | REWRITE: near-bed water concentration and film transfer, no swept volume |
| `apply_transfers(field_state, panel_steps)` | `residual_source_flux(tiles, hotspot, layer_steps)` | REWRITE: produces `SourceTerm`s instead of subtracting from cells |
| `transport_step(field_state, forcing, sources, dt_s)` | unchanged | the 2-D equation is the same, only its source term changes |
| `observations_available(records, decision_time_utc)` | unchanged | |
| `update_estimate(previous_estimate, available_observations, model_history)` | unchanged signature | estimated quantities change |
| `recommend(snapshot, policy, previous_actions)` | unchanged signature | action enum changes |

### Type changes in `contracts.py`

| Type | Disposition |
|---|---|
| `Element`, `Parameter`, `Matrix`, `Fraction`, `AcquisitionKind`, `Qualifier`, `QualityFlag`, `DataOrigin`, `StateOrigin`, `ProvenanceLabel` | KEEP; add enum members (below) |
| `ObservationRecord`, `GridSpec`, `FieldState`, `Forcing`, `TransportStep` | KEEP |
| `SourceTerm` | ADAPT: gains an area-distributed form (`flux_kg_per_m2_per_s` over cells) |
| `MaterialParameters` | KEEP, add `rho_bulk_kg_per_m3`, `porosity`, `d_eff_m2_per_s`, `tortuosity` |
| `PanelGeometry` | REWRITE as `MatTileGeometry`: `x_m, y_m, width_m, length_m, thickness_m, sorbent_loading_kg_per_m2`; `frontal_area_m2` and `interception_efficiency` deleted |
| `PanelState` | REWRITE as `MatTileState`: adds `fouling_index`, `integrity_index`, `effective_permeability`, `burial_depth_m`, `displaced`, per-element `loading` and `remaining_capacity`, and the 1-D profiles |
| `ContactBatch` | REWRITE as `SeabedExchange`: sediment-side driving concentration, water-side concentration, film coefficient, cell ids and weights; `exchange_volume_m3`, swept volume and `interception` deleted |
| `PanelStep` | REWRITE as `LayerStep`: `flux_in_kg_per_m2_per_s`, `flux_out_kg_per_m2_per_s`, `retained_kg_by_element`, `released_kg_by_element`, new profiles, diagnostics |
| `ServiceEvent` | KEEP, add `tile_id` and partial-replacement kinds |
| `MassLedger` | ADAPT: compartments become source-driven (below) |
| `EstimateSnapshot` | ADAPT: estimated quantities become loading, remaining capacity, fouling, integrity, effective permeability, estimated source flux, attenuation |
| `Recommendation`, `ActionEvent`, `ModelHistory`, `OperatorKnownPanel` | KEEP, rename `OperatorKnownPanel` to `OperatorKnownMat` |
| `ActionKind` | REWRITE, see below |

New `ActionKind`:

```
CONTINUE_MONITORING        (was CONTINUE)
TAKE_CHEMICAL_SAMPLE       (was REQUEST_CHEMICAL_SAMPLE)
CHECK_SENSOR               (kept)
INSPECT_MAT                (was INSPECT_MESH)
PLAN_PARTIAL_REPLACEMENT   (new: a subset of tiles)
REPLACE_ACTIVE_PANEL       (new: one tile now)
PERFORMANCE_UNCERTAIN      (was INSUFFICIENT_EVIDENCE)
```

New `AmbiguityFlag` members: `BURIAL`, `EROSION_OR_DISPLACEMENT`,
`LOCAL_DAMAGE`, `PERMEABILITY_LOSS`, `METHYLMERCURY_RISK`.

New `Parameter` members: `mat_tilt` (renamed from `mesh_tilt`),
`mat_displacement_m`, `burial_depth_m`, `visual_damage_index`,
`differential_head_m`.

New `AcquisitionKind` member: `rov_inspection`.

New `Matrix` usage: `porewater` becomes a first-class assimilation matrix rather
than a rejected one, since porewater is now the most informative chemistry.

### Mass ledger compartments

Old (water-column removal):

```
initial_water + emitted + boundary_in
  == in_water + in_active_mesh + in_retrieved_media + boundary_out + correction
```

New (seabed source through a cap):

```
released_from_sediment + boundary_in
  == retained_in_mat + retained_in_retrieved_media
     + in_water + boundary_out + correction
```

where `released_from_sediment` is the gross flux that left the sediment into the
mat or directly into the water where the mat is absent. The sediment reservoir
itself is prescribed, not depleted: that is an explicit, documented assumption.

---

## 5. File-by-file disposition

| Path | Action | Note |
|---|---|---|
| `src/mesh_demo/units.py` | `git mv`, no edit | fully concept-neutral |
| `src/mesh_demo/results.py` | `git mv`, path strings only | run layout unchanged |
| `src/mesh_demo/observations/records.py` | `git mv`, add enum members | contract fields unchanged |
| `src/mesh_demo/observations/qc.py` | `git mv`, add condition-channel ranges | range/spike/stuck checks are generic |
| `src/mesh_demo/observations/generator.py` | `git mv` + ADAPT | must emit porewater, DGT and mat-condition records; station geometry becomes seabed-relative |
| `src/mesh_demo/observations/operator.py` | `git mv` + ADAPT | porewater becomes assimilable; add the condition channels; keep the fraction-mismatch refusal |
| `src/mesh_demo/micro/material.py` | `git mv` to `reactive_layer/material.py` | KEEP. Isotherm, kinetics, fouling factors and the parameter ensemble are exactly what the 1-D layer needs |
| `src/mesh_demo/micro/service.py` | `git mv` to `reactive_layer/service.py` | KEEP, plus partial replacement of a tile subset |
| `src/mesh_demo/micro/forecast.py` | `git mv` + ADAPT | the exponential time-to-target logic survives; the target becomes breakthrough of the layer, not loading of a panel |
| `src/mesh_demo/micro/design.py` | `git mv` to `optimisation/sweep.py` + ADAPT | the sweep, ensemble and cost machinery survive; the design variables change to footprint, thickness, loading, tile layout, overlap, service interval |
| `src/mesh_demo/micro/panel.py` | REWRITE as `reactive_layer/tile.py` | `advance_panel` is vertical interception. `build_panel_state`, `grow_fouling`, `release_from_damage` and `panel_summary` are salvageable with edits |
| `examples/micro/scripted_contact.py` | REWRITE as `examples/reactive_layer/scripted_flux.py` | scripted contact becomes a scripted sediment-side driving concentration |
| `src/mesh_demo/transport/domain.py` | `git mv` + ADAPT | grid, land mask and forcing survive. Point source becomes an area hotspot |
| `src/mesh_demo/scenarios/registry.py` | ADAPT | the seven old scenes become the six required scenarios A to F |
| `src/mesh_demo/contracts.py`, `config.py` | ADAPT in place | per the tables above |
| `tests/contracts/` | ADAPT | 48 tests: the unit, observation, gate, state-separation and config tests survive; the panel-capacity and scene tests change |
| `docs/MODEL_SPEC.md` | REWRITE sections 3 and 4, keep 1, 2, 5 to 9 | |
| `docs/LIMITATIONS.md`, `ASSUMPTIONS.md` | ADAPT | new interception-free assumption set, plus methylmercury risk |
| `docs/REFERENCES.md`, `SENSOR_SUPPLIERS.md` | KEEP, extend | reactive-cap prior art and DGT suppliers are additions |

---

## 5b. What the audit found that the brief did not predict

The observation stack contains **no vertical-mesh physics at all**: not one line
computes a frontal area, a swept volume or an interception efficiency. Those
live only in `contracts.py`, `config.py` and `MODEL_SPEC` section 3. What the
observation stack bakes in instead is a *vocabulary and a geometry*, and that is
what must change.

### Blocking gaps in the contract

1. **There is no areal-flux unit ladder.** Flux attenuation is now the entire
   claim of the product, and no flux value can currently be converted,
   validated or range-checked. Add `ng/m2/s`, `ug/m2/d`, `mg/m2/d` to
   `kg m^-2 s^-1`.
2. **There is no length ladder.** `m` sits in the dimensionless/context set with
   no conversion factor, so a burial depth reported in centimetres would pass
   every check as if it were metres. Add `m`, `cm`, `mm`.
3. **There is no `tile_id`.** Without it, spatially local mat failure is
   unobservable. `media_id` is not a substitute: one media batch can be laid
   across many tiles. This is the single most important field addition.
4. **`depth_m` has no vertical datum.** Add `vertical_datum`
   (`sea_surface` / `seabed` / `mat_top` / `mat_base`) and `z_in_mat_m` for a
   depth-resolved profile through the layer.
5. **The operator accepts only `seawater` as assimilable.** Porewater at the
   sediment/mat interface is the driving boundary condition of the whole model,
   and today it is discarded as evidence-only. This is the most damaging single
   assumption in the stack.
6. Add `quantity_kind` (`aqueous_concentration` / `solid_loading` /
   `accumulated_mass` / `areal_flux` / `length` / `fraction` / `categorical` /
   `context`) so the operator dispatches on a declared kind rather than
   inferring one from `(matrix, fraction, unit)`, plus `chamber_area_m2` and
   `condition_class`.

### Enumeration changes, as named members

* `Matrix`: add `bottom_water`, `mat_porewater`, `mat_structure`. All five
  existing members keep their meanings; `porewater` and `sediment` change role
  from rejected evidence to primary channels.
* `Parameter`: rename `mesh_tilt` to `mat_tilt`; add `burial_depth`,
  `scour_depth`, `mat_displacement`, `mat_uplift`, `mat_coverage_fraction`,
  `mat_damage_class`, `differential_head`, `mat_permeability`,
  `seepage_velocity`, `sediment_temperature`, `dissolved_oxygen`,
  `redox_potential`, `sulfide`. `Pb` and `Hg` stay the parameter names for the
  flux channel: a benthic-chamber flux is still Pb, distinguished by its unit
  and quantity kind, not by a new parameter name.
* `AcquisitionKind`: add `rov_inspection`, `bathymetric_survey`,
  `acoustic_position`, `sediment_core`, `benthic_chamber`. The last is the only
  kind that directly measures the quantity the mat is judged on.
* `Fraction`: add `dgt_labile` (a DGT-labile pool is operationally different
  from a voltammetric labile pool, and both are currently called `labile`),
  `acid_volatile_sulfide` and `simultaneously_extracted_metal`.
* `Qualifier`: add `above_range`; the ladder is currently one-sided and an
  over-range flux has no qualifier. Add `categorical` so a damage class can be a
  valid record at all.
* `DataOrigin`: add `field_survey`, since an ROV survey is neither a sensor
  stream nor a laboratory result.
* `AmbiguityFlag`: remove `plume_shift`; rename `source_increase` to
  `sediment_source_increase`; add `burial`, `erosion_scour`,
  `displacement_uplift`, `tear_puncture`, `advective_change`. Without these,
  every non-saturation failure collapses into "saturation", which is exactly
  what the brief forbids. `burial` matters most: it *reduces* apparent flux and
  can masquerade as success.

### Defects to fix while refactoring

Found by the audit in already-committed code, including the coordinator's own:

* `records.py read_jsonl` catches only `ObservationValidationError`, but
  `record_from_dict` raises bare `ValueError` from every enum constructor and
  `UnitError` from `parse_utc`, so a bad enum escapes without file/line context.
* `records.py validate_record_dict` without `jsonschema` checks only that
  required keys exist: no enum membership and none of the four conditional
  rules. The docstring's claim that the essential rules still hold is overstated.
* `SCHEMA_PATH` resolves outside `src/`, and `pyproject.toml` packages only
  `src/`, so `load_schema()` fails on any installed non-checkout deployment.
  The schema must move inside the package.
* `DATA_CONTRACT` says a non-detect's reported value "can be retained in raw
  provenance", but the schema sets `additionalProperties: false` and
  `record_to_dict` drops `.raw`. The promise is unimplementable as written.
* `data_origin` mixes a truth-status label (`synthetic`) with acquisition
  pathways (`sensor`, `laboratory`), and fixture records are fabricated numbers
  labelled `laboratory`. In a repository whose discipline is provenance honesty
  this must be split: `acquisition_kind` already carries the pathway.
* `qc.py _sensor_health` never updates `last_seen` for missing records, so the
  data-age check is skipped for exactly the sensor that needs it most.
* `qc.py` detects a stuck sensor by substring-matching prose inside a reason
  string; rewording the message silently disables the check.
* `qc.py` never sees records with `sensor_id = None`, which is every
  laboratory, passive-sampler, media-assay and future survey record.
* `generator.py` hard-codes the solid-loading factor `1.0e-9` instead of calling
  the coordinator-owned `from_si_solid_loading`, defeating the single-source
  rule; several numbers there carry no provenance label.
* `mesh_demo.cli:main` is declared in `pyproject.toml` but does not exist.
* Roughly 1 950 of the observation stack's 2 226 lines have no consumer and no
  test. They are correct-looking but unexercised, and must be wired up and
  tested during the refactor rather than trusted.

## 6. Genuinely new work

1. `reactive_layer/column.py`: the 1-D FiPy layer.
2. `reactive_layer/flux.py`: `J_in`, `J_out`, `J_bare`, attenuation with intervals.
3. `reactive_layer/degradation.py`: the four independent modes, kept independent.
4. `coastal_transport/fipy_engine.py`: the 2-D solver (never written).
5. `coastal_transport/seabed_source.py`: the tile-state to source-flux map.
6. `estimation/` and `maintenance/`: never written; now estimate a richer state
   (loading, fouling, integrity, permeability, source flux) and must be able to
   answer `PERFORMANCE_UNCERTAIN` rather than blame saturation for everything.
7. `optimisation/`: footprint, thickness, loading, layout, overlap, service
   interval, against the listed objectives and constraints.
8. `visualization/` and `app/`: the Streamlit demo.
9. `docs/PRIOR_ART.md`: reactive caps, activated-carbon amendments and
   permeable reactive barriers already exist. No novelty is claimed for putting
   sorbent in a mat. Differentiation is stated as a hypothesis list.
10. Methylmercury risk: capping alters sediment redox and can *increase* MeHg
    production. Modelled as an explicit, wide-interval risk term and an
    ecological constraint in the optimisation, never as a benefit.

---

## 7. Compatibility risks

| Risk | Handling |
|---|---|
| The 48 passing contract tests are the safety net; a wholesale rename could silently break them | Rename in one commit with `git mv` only, run the suite, then change physics in separate commits |
| `PanelState` and `ContactBatch` are referenced by ~2 500 lines of merged branch code | Rewrite the types first, then fix call sites file by file, with the test suite run after each |
| Two Python packages installed editable (`mesh_demo`) while renaming to `reactive_seabed_mat` | Uninstall and reinstall editable after the rename; the per-worktree `conftest.py` keeps worktrees honest |
| The `.venv` holds absolute paths, so renaming the repository directory breaks it | Recreate the venv from `requirements.lock.txt`, which is pinned and tested |
| Existing worktrees point at the old directory | Remove all worktrees before the directory rename, recreate afterwards |
| 1-D layer plus 2-D field per tile per element could get slow | Tiles share one column solve per distinct state class; the demo grid stays small; runtime is asserted in a test |
| Sorption operator splitting can violate conservation if written carelessly | Mass moved between `C` and `q` is computed as one explicit difference and asserted per step |
| Fouling could accidentally look like a benefit, since lower permeability means lower flux | An explicit bypass and edge-leakage term grows with fouling, so pore blockage is not free |
| Renaming `capture` to `attenuation` everywhere could rename correct science | Only interception-specific names change; the keep-list in section 3 is enforced by review |

---

## 8. Order of work

1. **Rename only.** `git mv` the package and directories, fix imports, run the
   48 tests. No behaviour change in this commit.
2. **Contracts.** Rewrite the geometry and state types, the action enum, the
   ledger compartments, the new enum members. Update the contract tests.
3. **Reactive layer.** `column.py`, `flux.py`, `degradation.py`, rewritten
   `tile.py`, with conservation and breakthrough tests.
4. **Coastal transport.** `fipy_engine.py` and `seabed_source.py`, with the
   numerical acceptance tests.
5. **Observations.** Condition channels, porewater and DGT.
6. **Estimation and maintenance.** Richer state, four degradation modes kept
   apart, the new action set.
7. **Scenarios A to F**, the coupled run, and the mass-balance integration test.
8. **Optimisation**, then **visualisation and the app**, then the demo script.
9. **Research**: sensors refreshed with DGT and mat-condition instruments;
   materials and prior art.

Steps 3 to 6 are independent once step 2 lands, and go back onto parallel
branches. Steps 1 and 2 are coordinator work and are done first, serially.

---

## 9. Success criteria, and where each is demonstrated

| Criterion | Where |
|---|---|
| 1 no vertical-mesh interception physics | `PanelGeometry`, swept volume and `phi` deleted; a test asserts the identifiers are gone |
| 2 mat attenuates contaminant flux | `flux.py` reports `J_in`, `J_out`, attenuation, with a test that `J_out < J_bare` for an intact mat and `J_out == J_bare` for no mat |
| 3 finite capacity and breakthrough | `column.py` capacity test and a breakthrough-curve test |
| 4 loading affects later performance | scenario B: attenuation falls as loading rises, asserted |
| 5 failure can be spatially local | scenario D: one tile displaced, its cells return to bare flux while neighbours do not |
| 6 transport responds to residual flux | `seabed_source.py` feeds the 2-D source; scenarios A and F differ only through it |
| 7 realistic observation delays and QC | existing observation stack, extended; gate tests already pass |
| 8 evidence and uncertainty drive maintenance | `maintenance/`, with the ambiguity test that a shared symptom does not become a confident saturation call |
| 9 mass conserved | ledger invariant test per element, per scenario |
| 10 traceable or visibly labelled numbers | `ProvenanceLabel` on every parameter, manifest export, `docs/ASSUMPTIONS.md` |
