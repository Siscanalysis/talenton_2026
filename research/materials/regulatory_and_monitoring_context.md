# Regulatory and monitoring context

Retrieved 2026-09-08.

## OSPAR: laying a mat on the seabed is a regulated act

* OSPAR Convention for the Protection of the Marine Environment of the North-East
  Atlantic, 1992.
* URL: <https://www.ospar.org/convention/text> (`FETCHED_OK`).

Annex II, Article 5, verbatim:

> "No placement of matter in the maritime area for a purpose other than that for which it
> was originally designed or constructed shall take place without authorisation or
> regulation by the competent authority of the relevant Contracting Party."

Article 1(g) distinguishes placement from dumping: dumping does not include "placement of
matter for a purpose other than the mere disposal thereof, provided that, if the placement
is for a purpose other than that for which the matter was originally designed or
constructed, it is in accordance with the relevant provisions of the Convention."

Consequences for this project:

1. A reactive mat laid on a seabed in the OSPAR maritime area needs authorisation from the
   competent national authority. No demonstration output may imply otherwise.
2. Retrievability is not only a maintenance feature. Under a placement regime, being able
   to remove the material again is a regulatory argument as well as an engineering one.
   That is worth stating, and it is still a hypothesis, not a permit.
3. The loaded medium, once retrieved, is a waste stream containing concentrated Pb and Hg.
   `ServiceEvent.retrieved_kg` and `CostConfig.used_media_handling_eur_per_kg` exist in the
   contract, and both are assumptions.

The London Convention and London Protocol form the parallel global regime
(<https://www.epa.gov/marine-protection-permitting/london-convention-and-london-protocol-international-treaties-prevent>,
`SEARCH_INDEX_ONLY`). Not analysed further here; recorded so nobody assumes OSPAR is the
whole picture.

## EU sediment policy

* LIFE SEDREMED, contract LIFE20 ENV/IT/000572,
  <https://life-sedremed.eu/technological-and-policy-solutions-for-the-management-of-contaminated-sediments-in-the-eu/>
  (`FETCHED_OK`).

Verbatim: "the current legal frameworks are fragmented across the EU, and Member States
address the challenges with diverging approaches". The page also records that seven pieces
of EU legislation govern the sector, that no EU-wide sediment-specific environmental
quality standards exist, and that experts agreed dredging and capping "is expensive and
cannot be applied everywhere".

Consequence: there is no single European acceptance criterion a demonstrator could be
scored against. Any threshold used in `PolicyConfig` (for example
`minimum_acceptable_attenuation = 0.70`) is a demonstration trigger and must be labelled
as one, which `config.py` already does.

## Monitoring practice for caps

Sources: ITRC *Sediment Cap* guidance chapter 7 (`FETCH_403`, search summary only) and
Reible (2012) (`FETCHED_PDF`, see `cap_design_advection_vs_diffusion.md`).

From Reible (2012), verbatim, on what porewater profiling can distinguish: effectively
clean cap over a sharp increase below; uniformly contaminated cap due to intermixing;
"Linear decreases in concentration through a cap due to diffusion or diffusive like
processes such as tidally controlled upwelling"; and "Effectively clean cap with higher
concentrations in the near surface indicating recontamination from above".

From the ITRC search summary, **not verbatim**: long-term contaminant migration through
caps occurs by advection, diffusion or dispersion of porewater, by bioturbation or by
ebullition; porewater sampling is the preferred performance monitoring method; long-term
monitoring includes bathymetry, periodic cap and sediment sampling, porewater sampling and
surface-water sampling; inspection should be frequent in the first six months after
placement because settling problems appear then.

Two consequences for the observation schedule in `config.py`:

1. `porewater_sample_period_s = 90 days` and `survey_period_s = 180 days` are consistent
   with a campaign rhythm, but the first six months after placement are, according to the
   guidance summary, the period needing the densest inspection. A uniform survey period
   does not reflect that. Recorded as a suggestion in the handoff.
2. Bathymetry appears in every monitoring list found. `AcquisitionKind.BATHYMETRIC_SURVEY`
   already exists in the contract, and it is the natural channel for burial and scour depth.

## Quality control

The repository's QARTOD-inspired flags [S23, S24] remain appropriate. Nothing retrieved
here changes that, and nothing retrieved here certifies our rules as QARTOD-compliant.
