# Assumption register

Every number in the default configuration, with its label and its reason.
Labels follow `contracts.ProvenanceLabel`: `measurement`, `external_model`,
`literature`, `assumption`, `fitted`, `synthetic_demo`.

**Nothing in this table is a measurement of our material, our site or any
product.** Where a literature source is cited, it is cited for the *shape* of
the behaviour, never as a validated operating value.

The parameter set below is the one the numerical probes were run with
(`docs/reactive_layer_numerics_probe.py`), so the documented breakthrough time
is reproducible rather than asserted.

## The seabed hotspot

An **abstract authorised contaminant hotspot**. Not a located real site, and not
an ordnance object. Nothing in this repository simulates, locates or recommends
the handling of unexploded ordnance; real work near historical marine munitions
requires specialist and environmental approval [S02, S03].

| Quantity | Default | Label | Note |
|---|---|---|---|
| Footprint | 80 m x 80 m | synthetic_demo | |
| Sediment porewater Pb | 1.0e-3 kg/m^3 (1 mg/L) | assumption | A strongly contaminated porewater at a localised source. Not derived from any site measurement. |
| Sediment porewater Hg | 8.0e-6 kg/m^3 (8 ug/L) | assumption | Two orders below Pb. Not derived from [S02]. |
| Darcy seepage velocity | 3.0e-8 m/s (about 0.95 m/yr) | assumption | Tidally pumped sandy sediment. This is the term that makes a reactive cap matter: without advection a cap is only a diffusion barrier. |
| Benthic film coefficient | 5.0e-7 m/s | assumption | About a 1.4 mm diffusive sublayer at D ~ 7e-10 m^2/s. |
| Uncapped flux `J_bare` | 5.3e-10 kg/m^2/s for Pb | derived | `(v + k_film) * C_sed`, the same driving conditions as the capped case. |
| Sediment reservoir | prescribed, not depleted | assumption | The hotspot keeps emitting at the scheduled rate. Stated in the ledger, not hidden. |

## The reactive mat

| Quantity | Default | Label | Note |
|---|---|---|---|
| Thickness | 10 mm | assumption | Thin, because the architecture being demonstrated is thin and retrievable. A thick engineered cap would last far longer, and that trade is the point. |
| Bulk density of medium | 400 kg/m^3 | assumption | A light, fabric-supported reactive medium. |
| Porosity | 0.5 | assumption | |
| Sorbent loading | 4.0 kg/m^2 | derived | `bulk_density * thickness`. |
| Tiles | 3 x 3 | assumption | Modular so failure and replacement can be local. |
| Coverage of the hotspot | 1.0 (0.45 in scenario F) | assumption | Uncovered area emits the bare flux; this is how the poor design fails. |
| Tile overlap | 0.10 m | assumption | |
| Edge leakage | 0.02, interval [0.005, 0.08] | assumption | The share of flux going round the tile rather than through the layer. Unmeasured, and a significant lever. |
| Layer nodes | 40 | assumption | Numerical resolution; refinement is tested. |

## Reactive medium, per element

| Quantity | Pb | Hg | Label | Note |
|---|---|---|---|---|
| `Kd` partition slope | 5 m^3/kg, interval [1, 25] | 12 m^3/kg, interval [1, 120] | assumption | The very wide Hg interval reflects that Hg uptake depends on sulfide, chloride and dissolved organic matter [S04]. |
| `q_max` operating capacity | 1.0e-3 kg/kg, interval [3e-4, 3e-3] | 4.0e-4 kg/kg, interval [8e-5, 1.6e-3] | assumption | An operating capacity, deliberately far below any literature maximum. Literature maxima are not validated operating capacities [S01]. |
| `k_rate` | 4.0e-4 1/s | 2.0e-4 1/s | assumption | First-order approach to equilibrium. |
| `D_eff` | 2.0e-10 m^2/s, interval [8e-11, 5e-10] | same | assumption | Effective diffusion in the layer porewater, tortuosity included. |
| Allocation fraction | 0.6 | 0.4 | assumption | Sums to 1.0. The same medium is never given to both metals. |
| Fouling effect on capacity | 0.0 | 0.0 | assumption | Fouling blocks access, it does not destroy sites. |
| Fouling effect on kinetics | 0.8 | 0.8 | assumption | |
| Fouling effect on diffusivity | 0.6 | 0.6 | assumption | Pore blockage. |

Derived from these: capacity 4.0e-3 kg/m^2 of Pb, Peclet number 3 through the
layer so advection and diffusion both matter, and breakthrough at about
**3.09 years**, converged across time steps from 12 h to 0.5 h.

## Degradation

| Quantity | Default | Label | Note |
|---|---|---|---|
| Fouling growth | 5.0e-9 1/s | assumption | Full fouling in about 6 years. |
| Fouling to bypass coupling | 0.35 | assumption | Pore blockage raises the head and pushes flow round the edge, so fouling is never a free benefit. Without this term, fouling would look like an improvement. |
| Burial resistance | 2.0e8 s/m | assumption | Added diffusive path per metre of burial. Burial *reduces* apparent flux, which is exactly why it is dangerous. |
| Burial growth | 0 by default | assumption | Scenario-driven. |
| Displacement and damage | scheduled events | synthetic_demo | Per tile, so failure is local. |

## Observations

Campaign rhythm, not plume rhythm. All schedules are **artificial** and none is
a verified instrument cycle time for any product.

| Quantity | Default | Label |
|---|---|---|
| Environmental cycle | 1 h | assumption |
| Bottom-water probe cycle | 6 h | assumption |
| Porewater sampling | every 90 days | assumption |
| Benthic chamber deployment | every 180 days | assumption |
| ROV / bathymetric survey | every 180 days | assumption |
| DGT deployment / exposure | every 180 days / 3 days | assumption |
| Laboratory latency | 21 days | assumption |
| Survey latency | 1 day | assumption |
| Probe relative noise | 0.20 | assumption |
| Probe LOD / LOQ / range top | 12 / 40 / 5000 ng/L | assumption |
| Laboratory LOD / LOQ | 1.5 / 5.0 ng/L | assumption |
| Chamber relative noise | 0.35 | assumption |
| Chamber LOD / LOQ | 0.05 / 0.20 ug/m^2/d | assumption |
| Missing probability | 0.03 | assumption |

No detection limit here is any manufacturer's specification, and no fresh-water
limit has been reused as sea-water performance.

## Policy

| Quantity | Default | Label |
|---|---|---|
| Decision cycle | 30 days | assumption |
| Replacement saturation threshold | 0.80 | assumption |
| Inspection saturation threshold | 0.55 | assumption |
| Minimum acceptable attenuation | 0.70 | assumption |
| Minimum coverage fraction | 0.90 | assumption |
| Maximum relative interval width | 1.2 | assumption |
| Maximum data age | 200 days | assumption |
| Minimum evidence records | 3 | assumption |
| Fixed service interval | 2 years | assumption |
| Credible interval level | 0.90 (5th and 95th weighted percentiles) | assumption |
| Ambiguity likelihood ratio | 3 | assumption |

None of these is a regulatory or engineering standard. No
environmental-compliance threshold is invented anywhere, and uncaptured Pb and
Hg are reported as masses, separately, with no pass or fail verdict.

## Costs

Every euro value is an **assumption**. No supplier has been contacted and no
dated quotation exists [S13-S22]. They exist so the comparison has a structure
to hold real numbers later, and so a poor-value outcome can be shown.

| Item | Default |
|---|---|
| Mat material | 240 EUR/m^2 |
| Deployment vessel day | 6500 EUR |
| ROV survey | 4200 EUR |
| Benthic chamber deployment | 2800 EUR |
| Porewater sample | 180 EUR |
| Laboratory Hg sample | 210 EUR |
| DGT deployment | 260 EUR |
| Tile replacement | 1900 EUR |
| Used-media handling | 12 EUR/kg |
| Sensor check | 350 EUR |

No monetary value of avoided contamination is assumed anywhere.

## Time acceleration

Saturation is never forced into a short window by inflating uptake parameters.
Scenario B reaches breakthrough by simulating six years at the same chemistry as
scenario A. Where a preloaded layer is used it goes through
`MatLayoutConfig.preload_kg_per_m2`, which is visible in the exported
configuration.

## The honest reading of the attenuation numbers

A **fresh** mat attenuates by more than 99 %. A **saturated** mat still
attenuates by roughly 94 %, purely as a diffusive barrier, because the extra
path resistance remains after the chemistry is exhausted. The chemical
contribution of the sorbent is the difference between those two figures, not the
whole attenuation. The demonstration reports both.
