# Five-minute demonstration

Written to be read aloud. Every number below comes from a run you can reproduce,
and the commands are in the order you would actually type them.

Before you start, have this ready:

```powershell
.venv\Scripts\python.exe -m reactive_seabed_mat.cli quick --out results
```

Open `results\fresh_mat_quick\report\report.html` in a browser. It is one file,
it works offline, and it is the whole demonstration if the laptop misbehaves.

---

## 0:00 to 0:40 The problem, and what this is not

> An authorised contaminated seabed area leaks lead and mercury into the water
> above it. A reactive seabed mat is a thin, modular, retrievable cap laid over
> that area: contaminant passes through a sorbent layer instead of straight into
> the sea.
>
> Two things before anything else. **This is not a new idea.** Reactive caps,
> permeable reactive barriers and activated-carbon sediment amendments are
> deployed practice, and we claim no novelty for any of them. And **this is a
> simulation, not a field trial.** No supplier has been contacted, no quotation
> exists, and every material parameter is a literature value derated for
> seawater rather than a measurement of our material.
>
> What is ours is the question underneath: **a cap that consumes itself needs to
> be maintained, and you cannot maintain what you cannot see.** That is what this
> demonstrator is about.

Show the banner at the top of the report. It says all of this on the page.

## 0:40 to 1:40 The material, and the one honest asymmetry

Open the **Reactive medium** table in the report.

> The candidate is a keratin-based polymer, from waste wool or feather. Published
> lead capacities for keratin biofibres are 4 to 33 mg/g. For scale, the same
> paper measures activated carbon at 6.7 mg/g, so keratin is comparable, not
> miraculous.
>
> Those numbers are all from deionised water at pH 4. In seawater at pH 8.2,
> carbonate complexes dominate dissolved lead and free Pb2+ is a minority
> species, while calcium and magnesium outnumber the trace metal by orders of
> magnitude. So we run the model at 1.0 mg/g, well below the lowest published
> figure.
>
> For mercury there is a harder answer: **we could not find a verified keratin
> mercury capacity anywhere.** Rather than borrow a number from a different
> material, the model uses a stoichiometric ceiling from keratin's own 4 to 8
> weight per cent sulfur. It is the weakest number in the model and the report
> says so.
>
> Here is what the numbers then imply, and it is not what we expected. Against
> this hotspot, **lead fills the mat in about two and a half years. Mercury
> capacity would last about five hundred.** The replacement schedule is set by
> lead. Mercury is not the binding constraint, which also means the mercury case
> rests almost entirely on that unverified capacity.

## 1:40 to 2:40 What the mat does, and what it does not

Scroll to **Seabed residual flux** and **Effective reactive cover**.

> This is the flux still entering the water, per square metre. Green tiles are
> intact, amber torn, red displaced, blue buried.
>
> Next to it, the plume with and without the mat, on a shared colour scale so
> the comparison is honest.
>
> The model reports about 99 per cent attenuation for a fresh mat, falling to a
> plateau near 94 per cent as the medium loads. **Two caveats, and I would rather
> you heard them from me.**
>
> First, that plateau. Once the chemistry is exhausted the mat is still a
> physical diffusive barrier, so it keeps attenuating. The sorbent's chemical
> contribution is the *difference* between those two figures, not the whole
> thing.
>
> Second, and more important: **99 per cent is above anything a real cap has
> achieved.** In-situ thin-layer capping in Trondheim harbour reduced measured
> sediment-to-water fluxes by a factor of two to ten, so 50 to 90 per cent. Our
> model has uniform seepage, no bioturbation, no consolidation and perfect
> contact. The honest reading is that our figure is an upper bound set by the
> physics we chose to include. That comparison is written down in
> `docs/EVIDENCE_BASE.md`, not buried.

## 2:40 to 3:40 It degrades in four independent ways

Switch to the app if it is running, or scroll to the timeline charts.

```powershell
.venv\Scripts\streamlit.exe run app/streamlit_app.py
```

> A cap does not simply fill up. It saturates, it fouls, it gets buried or swept
> off, and it tears. The model keeps those four apart because **they need
> different responses and they look the same in a single flux number.**
>
> Scenario D displaces one tile and punctures another. Those cells go straight
> back to the bare-sediment flux while their neighbours keep working. Failure is
> local, so the response should be local: replace two tiles out of nine, not the
> mat.
>
> And one that works against us. **Burial reduces the measured flux.** A buried
> mat looks like a working mat. If your monitoring programme is only flux
> measurements, burial reads as success. The model raises a flag for it instead.

## 3:40 to 4:40 The comparison that matters, and it does not flatter us

Open the **Maintenance** tab, or run:

```powershell
.venv\Scripts\python.exe -m reactive_seabed_mat.cli compare progressive_saturation --out results
```

Six years, same seed, same forcing, same hotspot, same sampling. Only the policy
differs.

| Policy | Pb into the water | Services | Assumed cost |
|---|---|---|---|
| no mat | 642.3 kg | 0 | EUR 0 |
| fixed calendar servicing | 6.7 kg | 2 | EUR 3.73 M |
| evidence-informed servicing | 26.4 kg | 0 | EUR 0 |

> The mat works: 642 kilograms down to single figures.
>
> But look at the third row. **Evidence-informed servicing let four times more
> lead through than a calendar, and spent nothing.** It under-serviced. That is
> not a bug we are about to fix, it is the finding.
>
> With chemistry on one tile out of nine, no seepage measurement, and a capacity
> known only from a commissioning test, the estimated saturation never narrows
> enough to justify sending a vessel. **The value of evidence-informed
> maintenance is bounded by the monitoring programme that feeds it.**
>
> And that gives us a number for what the laboratory work is worth. Without a
> commissioning isotherm on our own material, the capacity interval spans a
> factor of twenty-seven and the policy cannot act at all. That single experiment
> is what turns this from monitoring into maintenance.

If someone asks why the policy did not just replace the mat anyway: it also
declines to replace when the same falling attenuation could be a stronger
sediment source. New media does not fix a source that grew.

## 4:40 to 5:00 What would change our minds

> Six experiments would replace assumptions with measurements, and they are
> listed in `docs/MATERIAL_KERATIN.md`. The first is the isotherm in real
> seawater. The one that could stop the project is the sixth: **a sulfur-rich,
> biodegradable protein layer over anoxic sediment is a plausible substrate for
> the bacteria that make methylmercury.** Capping can increase methylmercury
> production. We model that as a risk channel, never as a benefit, and if it
> turns out to be real then this material is the wrong material.
>
> Everything on screen is reproducible from a clean clone: 430 tests, one
> command, no network. The audit that found the problems in our own code is in
> `docs/AUDIT.md`, including the two places where our model is more optimistic
> than the measured literature.

---

## If a question goes somewhere awkward

**"Is 99 per cent realistic?"** No, and we say so on the page. Real caps achieve
a factor of two to ten. Our model omits preferential flow, bioturbation and
consolidation, all of which make real caps worse.

**"Where did the porewater concentration come from?"** It is an assumption, and
it is an aggressive one: about 400 times measured benthic lead fluxes. It is
chosen so a six-year run shows loading and breakthrough. The absolute kilograms
belong to the assumed hotspot; the comparisons between policies are the part
that transfers.

**"Has anyone measured a keratin mat in seawater?"** Not that we could find.
Neither a seawater keratin isotherm nor a measured metal flux attenuation across
a marine reactive cap exists in the open literature. Both gaps are recorded in
`research/references/datasets.json`.

**"What about the munitions?"** Out of scope by design. The source is an
abstract authorised contaminant hotspot. Nothing here simulates, locates or
recommends handling unexploded ordnance, and real deployment near historical
marine munitions needs specialist and environmental approval.

**"Can it be automated?"** No, and deliberately. Every recommendation carries
`human_confirmation_required = True` and `execution_mode = "simulation_only"`.
There is no actuation path and none should be added without a safety case.
