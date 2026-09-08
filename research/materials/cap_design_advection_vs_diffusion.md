# Cap design: advective versus diffusive sizing

Retrieved 2026-09-08. This note backs `docs/MODEL_SPEC.md` section 3 and probe 3 in
`REFACTOR_PLAN.md`, both of which state that advection is not optional.

## Primary source actually read

* Reible, D., *In-situ management of contaminated sediments: capping and in-situ
  treatment*, short paper, NORDROCS, 2012. Author affiliation on the paper: Director,
  Center for Research in Water Resources, University of Texas at Austin.
* URL: <https://nordrocs.org/wp-content/uploads/2012/09/Session-I-onsdag-1-Reible-short-paper.pdf>
* Retrieval: `FETCHED_PDF`, four pages read directly.

### Ranking of remedial forms, verbatim

> "In general, strong sorbents mixed throughout a cap layer provides the best performance
> in sediment remedies. Less effective, although still quite effective is a layer of
> sorbent mixed within a thin layer (e.g. in a reactive core mat) as part of the cap.
> Least effective, although still providing substantial risk reduction is sorbent
> amendments mixed within a sediment layer as an in-situ treatment."

This places the thin reactive mat, which is our product, second of three on performance.
It is the single most important sentence in this note. Our case cannot be a peak
attenuation case.

### Sorbent fouling by site water, verbatim

> "The sorption of PCB congener 52 was compared on activated carbon and organophilic clay
> using slurries of clean DI water and site porewater with a site containing approximately
> 14 mg/L of dissolved organic carbon. The AC sorption in site waters was reduced
> approximately 1/2 order of magnitude by site related fouling while OC was essentially
> unaffected."

> "Many of the sorbents exhibit reduced effectiveness in the presence of dissolved organic
> matter and other porewater geochemical limitations and use of site waters and porewaters
> in the slurries are necessary to evaluate this effect."

Half an order of magnitude is a factor of about three in the partition coefficient, from
site water alone, before any long-term biofouling. Our `ReactiveMediumConfig.kd_interval`
for Pb is `(1.0, 25.0)` around a central 5.0, a factor of five up and down, which is at
least the right order of width. The relevant point for `docs/ASSUMPTIONS.md` is that the
width is justified by the literature on sorbent fouling, not by comfort.

### Transport regimes distinguishable in a cap, verbatim list

> "Effectively clean (low concentrations) in cap with a sharp increase in concentration in
> the contaminated sediment below"
>
> "Uniformly contaminated cap layer due to intermixing between sediment and cap or rapid
> underlying transport processes"
>
> "Linear decreases in concentration through a cap due to diffusion or diffusive like
> processes such as tidally controlled upwelling"
>
> "Effectively clean cap with higher concentrations in the near surface indicating
> recontamination from above"

The third item names tidally controlled upwelling as a transport process through a cap.
This is the physical justification for the Darcy velocity `v` in our layer equations and
for `HotspotScheduleEntry.seepage_velocity_m_per_s`.

The fourth item, recontamination from above, is a failure mode our model currently cannot
represent: `C_water` enters only as the top boundary of the layer, and there is no
mechanism by which contaminated material settles onto the mat and becomes a new upper
source. Recorded as a gap.

### Passive sampling for cap performance, verbatim

> "The PDMS-coated fiber is inserted into the sediment in a shielded rod and allowed to
> equilibrate for 7-28 days."

> "A particular advantage of the approach employed here is the determination of
> concentration profiles with up to 1 cm resolution."

Caution: PDMS fibres sample hydrophobic organic compounds, not metals. The metal analogue
is DGT, covered in `research/sensors/sensor_matrix.md`. Do not transfer the 1 cm profile
resolution claim to a metals measurement.

### Model references cited by that paper

Taken verbatim from its reference list, so these citations are verified as citations:

* Knox, A.S., Paller, M.H., Reible, D.D., Ma, X., Petrisor, I.G. (2008), *Sequestering
  agents for active caps: remediation of metals and organics*, Soil and Sediment
  Contamination 17:516-532.
* Lampert, D., Reible, D.D. (2009), *An analytical modeling approach for evaluation of
  capping of contaminated sediments*, Soil and Sediment Contamination 18:470-488.
* Lampert, D., Reible, D.D. (2012), *Capping for remediation of contaminated sediments*,
  chapter 12 in *Processes, Assessment and Remediation of Contaminated Sediments*,
  ed. D. Reible, Springer.
* Lampert, D.J., Sarchet, W.V., Reible, D.D. (2011), *Assessing the effectiveness of
  thin-layer sand caps for contaminated sediment management through passive sampling*,
  Environmental Science and Technology 45:8437-8443.
* The numerical model is named in the text as CAPSIM (Reible and Lampert, 2012), with
  "multilayer advection-diffusion models assuming linear sorption and constant velocities"
  for the analytical case and, for the numerical case, "consolidation, deposition and
  nonlinear sorption as well as multiple layers with bioturbation, advection, diffusion,
  colloidal transport and boundary layer mass transfer resistances".

CAPSIM is therefore a directly comparable prior model, and it already contains more
physics than our layer does (consolidation, deposition, bioturbation, colloidal
transport). Our differentiator cannot be model completeness.

## Reactive transport with metals and mercury

* Bessinger, B.A., Vlassopoulos, D., Serrano, S. and O'Day, P.A. (2012), *Reactive
  transport modeling of subaqueous sediment caps and implications for the long-term fate
  of arsenic, mercury, and methylmercury*, Aquatic Geochemistry 18(4):297-326,
  DOI 10.1007/s10498-012-9165-4.
* URL: <https://pmc.ncbi.nlm.nih.gov/articles/PMC4802735/> (`FETCHED_OK`).

Verbatim: "Methylmercury formation is predicted to occur within the upper 0.15 m of the
cap in both estuarine and freshwater scenarios." Also: "The highest dissolved
methylmercury concentrations occur in the habitat layer in estuarine environments under
conditions of advecting porewater".

Two consequences for us. First, mercury speciation in a cap is coupled to sulfide
chemistry and is not a linear-isotherm problem, so our `Kd` and `q_max` for Hg are a
strong simplification and `config.py` is right to say so. Second, the paper explicitly ties
the worst methylmercury outcome to **advecting porewater in an estuarine setting**, which
is exactly the regime our demonstrator runs in.
