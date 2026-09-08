# Limitations

Read this before quoting any number produced by this repository.

## What this is

A small offline simulator and presentation demonstrator. It shows a
*hypothetical* release, a prescribed current field, a finite-capacity reactive
panel, a synthetic observation stream and an uncertainty-aware maintenance
recommendation. It is a way of reasoning about a monitoring and maintenance
concept. It is not evidence that the concept works.

## What it is not

* **Not field validation.** Simulated improvement is not measured improvement
  [U01]. No part of this repository has been compared against a real deployment.
* **Not a validated material model.** The capped linear isotherm with a
  first-order approach to equilibrium is a synthetic baseline chosen because it
  is auditable, not because it is the chemistry of any real mesh. Seawater Pb
  adsorption has been demonstrated for a *particular* polyurea-crosslinked
  alginate material [S01], not for our composite, not as a mesh, and not in
  flowing open sea. Hg behaviour depends strongly on sulfide, chloride and
  dissolved organic matter [S04]; the Hg parameters here are placeholders with
  wide intervals, not transferable constants.
* **Not a validated hydrodynamic model.** The current field is prescribed and
  physically simple. It is not a calibrated coastal flow solution. TELEMAC [S08]
  or an imported Copernicus product [S09, S10] would be needed for that, and
  neither is used in the default run.
* **Not a claim about any real site.** The source is hypothetical and labelled
  as such in every export. Munitions-derived mercury has been measured in the
  Baltic [S02] and ammunition-related compounds at a Dutch dump site [S03];
  neither establishes a hotspot at Brest, and neither establishes that an
  open-water dissolved-metal mesh addresses the dominant pathway at any site.
* **Not a statement that TNT and other energetic compounds are harmless.**
  Restricting this demonstrator to Pb and Hg is a scope decision [S03].
* **Not a biodegradability claim.** No composite here has been tested. The
  material in [S01] contained substantial synthetic polymer.
* **Not a disposal route.** Metal-loaded media stay in the retrieved-media
  ledger. Nothing is returned to the sea.
* **Not an automated control system.** Every recommendation carries
  `human_confirmation_required = True` and `execution_mode = "simulation_only"`.
  No actuation path exists, and none should be added without a safety case. No
  claim is made about safe operation near munitions.

## Known modelling limitations

| Area | Limitation |
|---|---|
| Dimensionality | 2D depth-averaged with a single effective mixing depth. Stratification, near-bed structure and vertical shear are absent. A near-bed release is not resolved. |
| Mixing | One effective horizontal diffusivity lumps turbulent diffusion and unresolved shear dispersion. It is an assumption, not a measurement. |
| Interception | `phi`, the fraction of water crossing the panel's frontal area that actually contacts reactive material, is an assumption with a wide interval. It is the single largest lever on capture, and it is unmeasured. |
| Sub-grid geometry | A panel a few metres across sits inside a 10 m cell. The coupling uses area weights and a cap on how much of a cell's inventory one step may take. It does not resolve the flow around the panel. |
| Chemistry | One dissolved pool per element. No speciation, no competing ions, no particulate/dissolved exchange, no sediment interaction. PHREEQC [S05] is not used, and using it would first require checking the database actually contains the needed Pb/Hg saline-water reactions. |
| Fractions | The simulated dissolved pool is treated as the labile pool (`chi_labile = 1.0` by default, stated explicitly). Real labile and total recoverable measurements are not interchangeable, and the code refuses to merge them without an explicit operator. |
| Fouling | A single scalar reducing rate and accessible capacity. Biofouling in reality is spatially heterogeneous and time-varying, and can also change the local flow. |
| Numerics | Implicit finite volume with a power-law convection scheme. It is stable but diffusive at coarse resolution; the refinement tests state the sensitivity actually measured. Any clipping of negative concentrations is recorded in the manifest, not hidden. |

## Known evidence and estimation limitations

* The observation schedules (environmental every 10 minutes, probe every 2 hours,
  laboratory every 12 hours with a 48 hour delay) are **artificial**. They are
  not verified instrument cycle times for any product.
* Detection and quantification limits in the configuration are demonstration
  values. They are not any manufacturer's specification, and no fresh-water
  limit has been treated as sea-water performance.
* The estimator constrains only what the observations plausibly constrain:
  retained mass and its interval, given assumed parameter ranges. It does not
  identify which of saturation, a stronger source, a shifted plume, fouling or
  sensor drift occurred. When it cannot tell, it says so, and the policy is
  allowed to answer `INSUFFICIENT_EVIDENCE`.
* A two-station concentration difference is not treatment efficiency. It is
  reported only through an explicit, labelled transport interpretation.
* No environmental-compliance threshold is invented anywhere. Uncaptured Pb and
  Hg are reported as masses, separately, with no pass or fail verdict.

## Known commercial limitations

* No supplier has been contacted. No quotation exists. Every euro value in the
  configuration is an assumption, and the cost comparison is a structure for
  future real numbers, not a result.
* Supplier evidence is a documentation review with access dates and explicit
  status labels (`CURRENT_LISTING`, `HISTORICAL_EVIDENCE`, `INDEXED_LEAD_ONLY`,
  `RESEARCH_PROTOTYPE`, `NOT_SUITABLE`). A current listing is not stock, and
  historical capability evidence is not present-day orderability [S19, S20].
* No vendor register map, message format, detection limit or SDK is reproduced
  or invented. Any protocol demonstration uses our own map, labelled
  `SIMULATED_PROTOCOL` [S28].

## Reproducibility limitations

Runs are seeded and the configuration is hashed into `manifest.json` together
with the dependency lock hash. Results were produced with CPython 3.12.13,
NumPy 2.5.3, SciPy 1.18.1 and FiPy 4.0.3 on Windows 11. Different solver
versions may shift the last digits of the mass ledger; the tolerances actually
achieved are recorded in the manifest rather than assumed.
