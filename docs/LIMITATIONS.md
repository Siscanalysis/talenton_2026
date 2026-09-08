# Limitations

Read this before quoting any number produced by this repository.

## What this is

A small offline simulator and presentation demonstrator for a **selective
reactive seabed mat**: a thin, modular, retrievable reactive cap over an
authorised contaminated seabed area. It shows a hypothetical hotspot, a
flux-attenuating reactive layer, four independent degradation modes, a synthetic
observation stream and an uncertainty-aware maintenance recommendation. It is a
way of reasoning about a monitoring and maintenance concept. It is not evidence
that the concept works.

## What it is not

* **Not novel in its basic idea.** Reactive caps, permeable reactive barriers,
  activated-carbon sediment amendments and reactive geotextile mats already
  exist and are commercially deployed. No novelty is claimed for putting sorbent
  in a mat, for a geotextile reactive cap, for activated carbon in sediment
  remediation, or for monitoring a remediation site. See `docs/PRIOR_ART.md`.
  The possible differentiation, listed there, is a hypothesis list, not a
  result.
* **Not field validation.** Simulated improvement is not measured improvement
  [U01]. No part of this repository has been compared against a real deployment.
* **Not a validated material model.** The capped linear isotherm with a
  first-order approach to equilibrium is a synthetic baseline chosen because it
  is auditable, not because it is the chemistry of any real medium. Seawater Pb
  adsorption has been demonstrated for a *particular* polyurea-crosslinked
  alginate material [S01], not for our composite, not as a mat, and not under
  advective flux. Hg behaviour depends strongly on sulfide, chloride and
  dissolved organic matter [S04]; the Hg parameters here are placeholders with
  deliberately wide intervals.
* **Not a validated hydrodynamic model.** The overlying current field is
  prescribed and physically simple. It is not a calibrated coastal flow
  solution.
* **Not a claim about any real site.** The hotspot is hypothetical and labelled
  as such in every export. Munitions-derived mercury has been measured in the
  Baltic [S02] and ammunition-related compounds at a Dutch dump site [S03];
  neither establishes a hotspot at any particular location.
* **Not a statement that TNT and other energetic compounds are harmless.**
  Restricting this demonstrator to Pb and Hg is a scope decision [S03].
* **Not an ordnance study.** The source is an abstract authorised contaminant
  hotspot. Nothing here simulates, locates or recommends the physical handling
  of unexploded ordnance. Real deployment near historical marine munitions
  requires specialist and environmental approval.
* **Not a biodegradability claim.** No composite here has been tested. The
  material in [S01] contained substantial synthetic polymer.
* **Not a disposal route.** Metal-loaded media stay in the retrieved-media
  ledger. Nothing is returned to the sea.
* **Not an automated control system.** Every recommendation carries
  `human_confirmation_required = True` and `execution_mode = "simulation_only"`.
  No actuation path exists and none should be added without a safety case.

## Ecological limitation that works against the concept

Capping alters sediment redox conditions and can **increase** methylmercury
production. This is a recognised risk of in-situ capping and amendment, not a
detail. Ecological safety is therefore a validation constraint in this
demonstrator, not an automatic benefit of treatment: the methylmercury channel
is reported alongside the Pb and Hg attenuation and is treated as a risk. A cap
that reduces total Hg flux while raising MeHg production could be a net harm,
and the demonstrator is built so that outcome can be seen rather than hidden.

### The evidence does not support a claim that this design prevents methylation

It is tempting to argue that encapsulating the keratin between two geotextiles
keeps the sulfur away from the sediment and therefore stops methylation. The
published record does not support that, and it points the other way on the part
that matters most.

**What activated-carbon capping actually does to mercury**, which is the closest
measured analogue:

* Porewater MeHg **falls**, substantially. Field amendment at 2 to 7 % dry
  weight reduced porewater MeHg by 45 to 95 %, and by more than 90 % at one
  month.
* Sediment MeHg **rose in five of seven studies**, apparently by shifting the
  balance between MeHg production and degradation. The mechanism is stated in
  the literature as unclear.
* The effect **fades**. In a salt-marsh field trial the impact on porewater MeHg
  and on MeHg partitioning was significant for only about the first year.

So a sorbent cap reliably reduces the *mobile* pool and may simultaneously
increase the *sediment* inventory, and its effect is not durable. Three separate
reasons not to claim prevention.

**Why a keratin core is a harder case than activated carbon, not an easier one.**
Methylation is carried out largely by sulfate-reducing bacteria, which need
labile organic carbon and sulfur. Activated carbon supplies neither: it is
refractory. A keratin core supplies both. It is a biodegradable protein that is
4 to 8 wt% sulfur, and the disulfides we would deliberately reduce to thiols to
bind mercury are exactly the sulfur species those organisms use. Encapsulation
limits particle contact; it does not stop dissolved organic carbon and reduced
sulfur from leaching downward into the sediment beneath.

**What can honestly be said.** Seawater mercury is above 99 % chloro-complexed,
and those complexes are reported to resist reduction and methylation more than
free Hg(II) does, so a mat that holds mercury as a thiolate rather than
releasing it to porewater is *plausibly* better than doing nothing. Plausibly is
the correct word. Until the experiment in `docs/MATERIAL_KERATIN.md` section 6
item 6 is done, on this material, in this configuration, **methylmercury is a
stop condition for the project and not a feature of it.** If a keratin core
raises net MeHg production, keratin is the wrong core and the envelope should be
filled with something else.

## Known modelling limitations

| Area | Limitation |
|---|---|
| Layer dimensionality | 1-D vertical per tile. Lateral flow within the layer, preferential channels and finger flow are absent. Real caps fail through preferential pathways that a 1-D model cannot represent. |
| Advection | A single prescribed Darcy velocity. Real seepage is heterogeneous, tidally modulated, and often concentrated in a few percent of the area. Uniform seepage is the optimistic case. |
| Sediment reservoir | Prescribed and never depleted. The model cannot show a source exhausting itself. |
| Consolidation and settlement | Not modelled. A mat laid on soft sediment settles, and its thickness and contact change. |
| Bioturbation and bioirrigation | Not modelled. Both can short-circuit a thin cap. |
| Chemistry | One dissolved pool per element, a capped linear isotherm, no competition between Pb and Hg for sites, no speciation, no particulate exchange. Competitive adsorption is a stated future need, not a feature. PHREEQC [S05] is not used, and using it would first require checking the database contains the needed saline-water Pb/Hg reactions. |
| Fractions | The simulated dissolved pool is treated as the labile pool, stated explicitly. Labile, DGT-labile and total recoverable are operationally different and the code refuses to merge them. |
| Fouling | A single scalar per tile driving rate, capacity and diffusivity, plus a bypass coupling. Real biofouling is heterogeneous and can alter the local flow field. |
| Edge effects | A single edge-leakage fraction. Real edge and seam behaviour is a geometry problem this model does not resolve. |
| Coastal model | 2-D depth-averaged with one effective mixing depth and one effective diffusivity. No stratification, no near-bed structure. |
| Two timescales | The mat is integrated for years; the coastal plume only for short windows at named mat states. The two ledgers are separate and labelled. Nothing implies the coastal model was run for years. |
| Numerics | The layer scheme is fully implicit and converged under refinement; the coastal scheme is stable but diffusive at coarse resolution. Both report their clipping corrections. The refinement tests state the sensitivity actually measured. |

## A methodological warning this project learned the hard way

The first reactive-layer scheme conserved mass to one part in 10^14 and was
still wrong: refining the time step moved the predicted breakthrough from
4.2 years to 1.0 years and made the attenuation curve oscillate. **Mass
conservation alone does not validate a numerical scheme.** Every numerical
result in this repository is therefore backed by a refinement test as well as a
ledger test, and both are reported in the manifest.

## Known evidence and estimation limitations

* Observation schedules are artificial. They are not verified instrument cycle
  times for any product.
* Detection and quantification limits are demonstration values. They are not any
  manufacturer's specification, and no fresh-water limit has been treated as
  sea-water performance.
* The estimator constrains only what the observations plausibly constrain. It
  does not reliably identify which of saturation, fouling, burial, displacement,
  local damage, a stronger sediment source or a change in seepage velocity
  occurred: several of them produce the same change in a single flux number.
  When it cannot tell, it reports competing weights and says so.
* Burial reduces the measured flux and can look like success. This is
  represented explicitly, but it also means a monitoring programme built only on
  flux measurements can be actively misled.
* A benthic chamber measures a small enclosed area for a few hours. Scaling that
  to a whole footprint over a year is an extrapolation, not a measurement.
* No environmental-compliance threshold is invented anywhere.

## Known commercial limitations

* No supplier has been contacted. No quotation exists. Every euro value is an
  assumption, and the cost comparison is a structure for future real numbers,
  not a result.
* Supplier evidence is a documentation review with access dates and explicit
  status labels. A current listing is not stock, and historical capability
  evidence is not present-day orderability.
* No vendor register map, message format, detection limit or SDK is reproduced
  or invented. Any protocol demonstration uses our own map, labelled
  `SIMULATED_PROTOCOL` [S28].

## Reproducibility

Runs are seeded and the configuration is hashed into `manifest.json` together
with the dependency lock hash. Results were produced with CPython 3.12.13,
NumPy 2.5.3, SciPy 1.18.1 and FiPy 4.0.3 on Windows 11. The tolerances actually
achieved are recorded in the manifest rather than assumed.
