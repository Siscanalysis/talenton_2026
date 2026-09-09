# Five-minute demonstration

Use the [PDF manuscript](../manuscript/manuscript.pdf) for the complete evidence and the [gallery](gallery/README.md) for regenerated figures. Read numerical values from the current report being shown; this script deliberately does not duplicate run-dependent performance tables.

Prepare a short run:

```powershell
.venv\Scripts\python.exe -m reactive_seabed_mat.cli quick --out results
```

Open `results\fresh_mat_quick\report\report.html`, or open the committed `docs\gallery\index.html` for all six full scenarios. A shortened quick run and a full scenario have different horizons.

## 0:00?0:45: The question

> We model a thin, retrievable cap over a hypothetical contaminated seabed hotspot. Each tile contains a reactive core between two permeable carriers. The model follows lead, inorganic mercury and copper through the core, then calculates short coastal transport windows. It also asks what maintenance decisions could be supported by delayed and imperfect observations.
>
> Reactive caps already exist. This simulation evaluates an assumed keratin-core design and monitoring workflow. The proposed material has not been tested in a seawater mat.

Show the scenario, simulation horizon and synthetic-data label.

## 0:45?1:35: What the papers establish

> The supplied review was already cited as background. Its experimental numbers and the two other supplied papers did not calibrate the original simulation. We traced their values and units in the new report.
>
> Treated sheep wool has measured copper adsorption. A modified feather-keratin/graphene-oxide composite removed lead in a dilute, salt-containing batch. A primary study cited by the review reports mercury uptake on chemically reduced human hair. These findings correct the earlier blanket statements about copper and mercury.
>
> They are different materials and tests. A percentage removed from a small batch is not the maximum capacity, and a maximum batch capacity is not the operating capacity in a flowing seawater mat. Our Pb, Hg and Cu defaults remain labelled assumptions until that transfer is measured.

Show the paper traceability table and its experimental conditions. The [page-level audit](PAPER_PARAMETER_TRACEABILITY.md) records both usable values and inconsistencies in the source papers.

## 1:35?2:30: Reading the maps and curves

Show scenario A's residual-flux map and timeline.

> The spatial map includes uncovered and bypass flow. Its whole-hotspot attenuation differs from attenuation through an individual column. The comparison curve is the same geometry with no sorption. The separation of the curves reflects reactive transport and transient storage; it is not an isolated laboratory measurement of the sorbent.
>
> In scenario B we extend the same source to six years. A loading plateau does not necessarily mean every site is filled: finite affinity can bring the material to equilibrium below its nominal capacity. We use the plotted inventories and fluxes to distinguish these outcomes.

For a plume surface, explain that height represents concentration, not water depth. The coastal calculation lasts for a short window at the labelled mat age, rather than for the entire multi-year timeline.

## 2:30?3:30: Bends, failures and uncertain evidence

Show scenarios C and D, then E.

> Scenario C changes the source at two years. Scenario D introduces displacement and partial damage at specified times. Abrupt changes at these events can be expected. Replacement also changes inventories discontinuously. Unexplained oscillation or a result that moves substantially with numerical resolution needs a separate numerical check.
>
> The revised code aligns geometry and timestamps, preserves exact campaign schedules and checks the numerical solution against independent benchmarks. The report lists what remains sensitive, including coastal grid and time resolution and a retained modelling discontinuity at exactly full capacity.
>
> Decisions see records only after completion, availability and QC checks. A non-detect is an interval, and an above-range reading has an unbounded upper limit. Physical survey readings are evaluated by their values and uncertainty. Missing copper chemistry is reported as unknown and cannot be used as evidence of chemical failure.

Show the observation timestamps and evidence identifiers for a recommendation. A delayed measurement can change the information available without necessarily changing the selected action.

## 3:30?4:20: Maintenance comparison

Open the comparison figure, or run:

```powershell
.venv\Scripts\python.exe -m reactive_seabed_mat.cli compare progressive_saturation --out results
```

> These policies share a hypothetical source and monitoring design. Compare whole-hotspot emission, full-column retained and retrieved inventories, services and the assumed cost separately. The mass columns have different control volumes and should not be added into an invented global balance.
>
> Sparse or stale chemistry can prevent the evidence-informed policy from supporting a chemical replacement decision. Resolved physical damage can support a different response. Every action shown is a simulation recommendation, and additional sampling recommendations do not automatically launch a new campaign in the present model.

Read actual event counts and quantities from the displayed regenerated result. The economic comparison uses assumed prices and covers the cost categories listed in that result, not a supplier quotation or complete deployment business case.

## 4:20?5:00: What would validate the design

Show scenario F's smaller coverage and the deployment-scale chart.

> Coverage is a design input, and its uncovered area continues emitting. Regional designated dumping areas give geographical scale; they do not establish a measured metal hotspot or a deployment priority. A pilot area and its target contaminants would need site-specific evidence.
>
> The next useful experiments are seawater isotherms and flow-through columns on the final material, followed by durability, hydraulic and ecological tests. Mercury methylation needs its own assessment: the model does not simulate the relevant microbiology, and a synthetic methylmercury channel cannot validate ecological safety.
>
> The manuscript, editable LaTeX, figures and computational provenance are included with the scripts so those assumptions and checks can be reviewed together.
