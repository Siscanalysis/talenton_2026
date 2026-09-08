# Assumption register

Every number in the default configuration, with its label and its reason.
Labels follow `contracts.ProvenanceLabel`: `measurement`, `external_model`,
`literature`, `assumption`, `synthetic_demo`.

**Nothing in this table is a measurement of our material, our site or any
product.** Where a literature source is cited, it is cited for the *shape* of
the behaviour, never as a validated operating value.

## Domain and forcing

| Quantity | Default | Label | Note |
|---|---|---|---|
| Grid | 60 x 40 cells, 10 m x 10 m | synthetic_demo | A small channel-like domain. Physical consistency matters more here than a realistic-looking coastline. |
| Effective mixing depth `H` | 5 m | assumption | Single depth-averaged layer. No stratification. |
| Land | one boundary strip | synthetic_demo | No-flux, no water volume. |
| Mean current | 0.12 m/s eastward | assumption | Plausible coastal magnitude, not a measurement. |
| Tidal amplitude | 0.18 m/s | assumption | Chosen so the flow genuinely reverses. |
| Tidal period | 44712 s | literature | M2, 12 h 25.2 min. A standard constant, not a site measurement. |
| Effective diffusivity `D` | 0.6 m^2/s | assumption | Lumps turbulent diffusion and unresolved shear dispersion. |

## Source

| Quantity | Default | Label | Note |
|---|---|---|---|
| Release rate Pb | 2.0e-7 kg/s | synthetic_demo | Hypothetical. Chosen so a plume is visible and a panel loads within a demonstration. |
| Release rate Hg | 2.0e-9 kg/s | synthetic_demo | Hypothetical, two orders below Pb. Not derived from [S02]. |
| Location | one cell in the domain | synthetic_demo | Hypothetical. Explicitly not a located real hotspot. |

## Material (per element, both channels)

| Quantity | Pb default | Hg default | Label | Note |
|---|---|---|---|---|
| `Kd` partition slope | 900 m^3/kg, interval [300, 2700] | 1500 m^3/kg, interval [200, 6000] | assumption | Slope of a capped linear isotherm. The wide Hg interval reflects that Hg uptake depends on sulfide, chloride and DOM [S04]. |
| `q_max` capacity | 6.0e-5 kg/kg, interval [2.0e-5, 1.2e-4] | 2.0e-5 kg/kg, interval [4.0e-6, 8.0e-5] | assumption | An operating cap, deliberately far below any literature maximum. Literature maxima are not validated operating capacities [S01]. |
| `k` rate constant | 4.0e-4 1/s, interval [1.0e-4, 1.2e-3] | 2.0e-4 1/s, interval [3.0e-5, 8.0e-4] | assumption | First-order approach to equilibrium. |
| Allocation fraction | 0.6 | 0.4 | assumption | Sums to 1.0. The same sorbent mass is never given to both metals. |
| Fouling effect on capacity | 0.4 | 0.4 | assumption | Fraction of accessible capacity lost at full fouling. Retained metal is never removed by fouling. |
| Fouling effect on kinetics | 0.8 | 0.8 | assumption | Fraction of rate lost at full fouling. |
| Fouling growth | 2.5e-6 1/s | | assumption | Reaches full fouling in roughly 4.6 simulated days. Chosen for the demonstration timescale. |

## Panel

| Quantity | Default | Label | Note |
|---|---|---|---|
| Frontal area | 4 m x 2 m | assumption | |
| Sorbent mass | 25 kg | assumption | |
| Interception efficiency `phi` | 0.45, interval [0.15, 0.75] | assumption | The fraction of water crossing the frontal area that actually contacts reactive material. Unmeasured, and the largest single lever on capture. |
| Cell-inventory cap `theta` | 0.5 | assumption | Numerical guard: at most half a cell's inventory may transfer in one step. |
| Labile fraction ratio `chi_labile` | 1.0 | assumption | The simulated dissolved pool is treated as the labile pool. Stated rather than hidden. |

## Observations

| Quantity | Default | Label | Note |
|---|---|---|---|
| Environmental cycle | 600 s | assumption | Artificial schedule, not a verified instrument cycle time. |
| Metal probe cycle | 7200 s | assumption | Artificial. No product is claimed to achieve this. |
| Laboratory sampling | every 43200 s | assumption | Artificial. |
| Laboratory latency | 172800 s (48 h) | assumption | A plausible turnaround, not a quoted service level. |
| Probe relative noise | 0.20 | assumption | |
| Probe LOD / LOQ | 12 / 40 ng/L | assumption | Demonstration values. Not any manufacturer's specification, and not a fresh-water limit reused as sea-water performance. |
| Laboratory relative noise | 0.08 | assumption | |
| Laboratory LOD / LOQ | 1.5 / 5.0 ng/L | assumption | Demonstration values. |
| Missing probability | 0.03 | assumption | |

## Policy

| Quantity | Default | Label | Note |
|---|---|---|---|
| Decision cycle | 3600 s | assumption | |
| Replacement loading threshold | 0.80 of effective capacity | assumption | A demonstration trigger, not a regulatory or engineering standard. |
| Inspection loading threshold | 0.55 | assumption | |
| Maximum relative interval width | 1.2 | assumption | Above this the policy asks for evidence instead of acting. |
| Maximum data age | 21600 s | assumption | |
| Minimum evidence records | 3 | assumption | |
| Fixed service interval | 604800 s (7 days) | assumption | The comparison policy. |
| Credible interval level | 0.90 (5th and 95th weighted percentiles) | assumption | Documented in every snapshot. |
| Ambiguity likelihood ratio | 3 | assumption | Below this, competing explanations are both flagged. |

## Costs

Every euro value below is an **assumption**. No supplier has been contacted and
no dated quotation exists [S13-S22]. They exist so the comparison has a
structure to hold real numbers later, and so a poor-value outcome can be shown.

| Item | Default |
|---|---|
| Vessel visit | 1800 EUR |
| Chemical sample (Pb) | 140 EUR |
| Laboratory Hg sample | 210 EUR |
| Sorbent | 55 EUR/kg |
| Used-media handling | 12 EUR/kg |
| Sensor check | 350 EUR |
| Inspection | 900 EUR |

No environmental-compliance threshold and no monetary value of avoided
contamination is assumed anywhere. Uncaptured Pb and Hg are reported as masses,
separately.

## Time acceleration

Realistic saturation is not forced into a short simulated window by inflating
uptake parameters. Where a saturated panel is needed, either the simulated
duration is extended or a panel is **explicitly preloaded** through
`PanelConfig.preload_kg`, which is visible in the exported configuration.
