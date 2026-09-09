# Simulation gallery

[PDF manuscript](../../manuscript/manuscript.pdf) | [Editable LaTeX](../../manuscript/manuscript.tex) | [Interactive offline gallery](index.html)

These figures show a hypothetical hotspot with assumed material and monitoring parameters. They are computational experiments, without field calibration. The manuscript documents the current results, literature comparisons and numerical audit. Download `index.html` to use its interactive figures; GitHub displays the PNG previews below directly.

## Read the curves and balances

Whole-hotspot attenuation includes uncovered, damaged and bypass areas. Through-column attenuation and the same-discretisation non-sorbing barrier reference answer a different question. Their transient difference includes storage and source history; it is not always a positive sorption contribution. A loading plateau can represent equilibrium below nominal capacity, rather than complete exhaustion.

Source changes, scheduled physical faults and accepted services have labelled vertical markers in the timeline previews and can create bends or jumps. Remaining numerical sensitivity is documented in [TIMESCALES.md](../TIMESCALES.md) and the manuscript. A long mat-age timeline does not imply a long coastal simulation: each plume is a short window at its labelled age and tidal phase. Absolute peaks require a stated grid, time step and window.

The full-footprint column inventory and retrieved-media ledger are separate from the area-weighted hotspot emission approximation and from each coastal window's mass balance. Pb and Hg are chemically monitored; Cu is physically simulated but remains unavailable to chemical maintenance inference.

The residual-flux previews use independently scaled colour bars. Compare their printed units and limits, rather than colour alone, across scenarios. Flux-map titles identify each scenario's actual final mat age.

## Maintenance comparison

![Three servicing policies](img/policy_comparison.png)

The six-year comparison uses the same seed, forcing, source schedule and nominal monitoring configuration. Fixed and evidence-informed policies share the sample schedule; the bare reference has no mat observations. Read regenerated quantities and service events from the interactive figure or manuscript. Cost assumptions do not establish field economics. Sparse evidence can constrain recommendations, and a physical survey does not refresh stale chemical measurements.

## Scenario A: `fresh_mat`

One year with nominal full hotspot coverage and the default source.

| Residual seabed flux | Timeline |
|---|---|
| ![Fresh mat flux](img/fresh_mat_flux.png) | ![Fresh mat timeline](img/fresh_mat_timeline.png) |

## Scenario B: `progressive_saturation`

Six years with the same source and material. Inspect flux and loading together: the scenario name does not establish that every metal reaches full capacity or breakthrough.

| Residual seabed flux | Timeline |
|---|---|
| ![Progressive loading flux](img/progressive_saturation_flux.png) | ![Progressive loading timeline](img/progressive_saturation_timeline.png) |

## Scenario C: `increased_leak`

Porewater concentrations triple and seepage doubles at two years. The event changes the driving source; subsequent performance also depends on the resulting material state and observation history.

| Residual seabed flux | Timeline |
|---|---|
| ![Increased leak flux](img/increased_leak_flux.png) | ![Increased leak timeline](img/increased_leak_timeline.png) |

## Scenario D: `displaced_section`

One tile is displaced at 1.5 years and another loses part of its integrity at 2.2 years. Uncovered and damaged areas contribute bare flux. Consult the actual recommendations and service events rather than assuming every scheduled fault is immediately observed and repaired.

| Residual seabed flux | Timeline |
|---|---|
| ![Local damage flux](img/displaced_section_flux.png) | ![Local damage timeline](img/displaced_section_timeline.png) |

## Scenario E: `delayed_chemistry`

Probe dropout, drift and laboratory delay alter available evidence. The estimator can use a result only after its availability time and QC/fraction checks. Additional information need not change the selected action.

| Residual seabed flux | Timeline |
|---|---|
| ![Delayed chemistry flux](img/delayed_chemistry_flux.png) | ![Delayed chemistry timeline](img/delayed_chemistry_timeline.png) |

## Scenario F: `undersized_mat`

Nominal 45% coverage, a 2 mm core and stronger seepage. This directly tests uncovered-area emissions and reduced material inventory under the same model equations.

| Residual seabed flux | Timeline |
|---|---|
| ![Undersized mat flux](img/undersized_mat_flux.png) | ![Undersized mat timeline](img/undersized_mat_timeline.png) |

## Geographical scale

![Designated area comparison, logarithmic scale](img/deployment_scale.png)

Bar height shows area on a logarithmic scale; the labels above bars show assumed keratin mass in tonnes (t) or thousands of tonnes (kt). The Bornholm primary and extended areas are distinct entries. The chart compares assumed pilot footprints with documented designated areas. Area is not a measured contamination footprint, and arithmetic material/cost extrapolation is not a deployment recommendation. Sources and assumptions are in [DEPLOYMENT_SCALE.md](../DEPLOYMENT_SCALE.md).

## Regeneration

```bash
python tools/build_gallery.py --out docs/gallery
```

The command generates the offline page, previews and scenario outputs. Runtime depends on hardware and requested horizons. For a shorter example use `python -m reactive_seabed_mat.cli quick --out results`. The complete report build and provenance instructions are in [manuscript/README.md](../../manuscript/README.md).
