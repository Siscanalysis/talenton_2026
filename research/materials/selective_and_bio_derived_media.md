# Selective Pb and Hg chemistry, and bio-derived media

Retrieved 2026-09-08. This note backs hypotheses H1 and H2 in `docs/PRIOR_ART.md`.
Everything here is laboratory work. None of it validates a marine reactive mat.

## The single most important caveat

Almost every sorbent paper found for Pb and Hg reports performance in fresh water, in
waste water, or in a buffered laboratory matrix at pH 5 to 6.5. Seawater is a different
problem:

* pH around 8.1, not 5,
* chloride around 0.5 mol/L, which forms strong chloro-complexes with Hg(II) and competes
  with sorption,
* calcium and magnesium at millimolar levels competing for cation-exchange sites,
* dissolved organic matter and sulfide altering speciation.

`docs/REFERENCES.md` [S04] already carries this point for activated carbon
(Chen et al. 2020, *Influence of sulfide, chloride and DOM on mercury adsorption by
activated carbon*, <https://link.springer.com/article/10.1186/s42834-020-00065-5>).
Reible (2012) makes the same point empirically for site porewater: activated carbon
sorption "was reduced approximately 1/2 order of magnitude by site related fouling" at
about 14 mg/L dissolved organic carbon
(`research/materials/cap_design_advection_vs_diffusion.md`).

**A freshwater capacity or a freshwater detection limit is not a seawater number.** This
is the same rule the sensor matrix applies to instruments, applied to materials.

## Thiol and sulfur functionalisation for mercury

Retrieval: `SEARCH_INDEX_ONLY` for all of the following. Titles, journals and the headline
capacities were obtained from search results; no article full text was retrieved. Numbers
are recorded as reported, not verified.

* Thiol-functionalised cellulose, Science of the Total Environment (2024),
  <https://www.sciencedirect.com/science/article/pii/S0045653524007847>. Reported
  Hg(II) capacity 1325 mg/g with selectivity over Co, Cu, Zn, Pb, Ca and Mg.
* Sulfur-functionalised mesoporous silica by thiol-ene click chemistry,
  <https://pubmed.ncbi.nlm.nih.gov/42250850/>. Reported distribution coefficient
  K_D = 9.72 x 10^6 mL/g in a multi-ionic system.
* Dithiol-modified mesoporous silica, Applied Nanoscience,
  <https://link.springer.com/article/10.1007/s13204-022-02531-5>. Reported 252 mg/g,
  about 90 per cent removal from a mixture containing Zn, Ni, Pb, Cd and Fe.
* Ion-imprinted thiosalicylichydrazide sorbent, Journal of Chemical Technology and
  Biotechnology (2024), <https://scijournals.onlinelibrary.wiley.com/doi/10.1002/jctb.7646>.
  Reported 350 mg/g at an optimal pH of 5.

Independent corroboration that the thiol route is real in a sediment context comes from
Gilmour et al. (2013), which used Thiol-SAMMS as one of four amendments and saw porewater
methylmercury fall by 45 to 95 per cent
(`research/materials/methylmercury_and_capping.md`).

Assessment: the chemistry is plausible and is already used by others. What is **not**
established anywhere retrieved here is performance of a thiol-functionalised medium in a
subaqueous mat, in seawater, over years, with fouling.

## Bio-derived sorbents

Retrieval: `SEARCH_INDEX_ONLY`. Reported values, not verified.

* Chitosan-modified biochar for Pb: Langmuir maximum 134 mg/g at pH 5 versus 48.2 mg/g
  unmodified, <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9082581/>.
* Alginate and chitosan gel films for Cd and Pb: 98 per cent Pb adsorption in 15 minutes
  at pH 6.5, <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11507177/>.
* Biochar from the invasive brown seaweed *Sargassum muticum* for Hg: reported
  470.53 mg/g, <https://link.springer.com/article/10.1007/s13762-024-05765-8>.

Every one of these is at pH 5 to 6.5 in a low-chloride matrix.

The repository's existing [S01] (Paraskevopoulou et al. 2021, polyurea-crosslinked
alginate aerogels, <https://pmc.ncbi.nlm.nih.gov/articles/PMC8005931/>) is the only
retrieved source describing Pb adsorption in seawater by a partly bio-derived material,
and `docs/REFERENCES.md` already records the correct caveat: it has substantial synthetic
polymer content and is not evidence of biodegradability.

## "Bio-derived" is not the same as "low impact"

This is the point most likely to be got wrong in a pitch. Powdered activated carbon is
bio-derived in the ordinary sense of the phrase, and in the Grenland fjords it reduced
benthic abundance, biomass and species number by up to 90 per cent for at least four years
(`research/materials/activated_carbon_field_evidence.md`). Any low-impact claim must be
supported by ecotoxicity and recolonisation data on the actual medium, not inferred from
its feedstock.

## Unit sanity check against `config.py`

`ReactiveMediumConfig` assumes `q_max_kg_per_kg = 1.0e-3` for Pb, which is 1 mg/g, and
`4.0e-4` for Hg, which is 0.4 mg/g. The laboratory capacities quoted above are 100 to 3000
times larger. Our operating capacity is therefore extremely conservative relative to
laboratory maxima, exactly as `config.py` claims ("deliberately far below any literature
maximum"). That claim is confirmed here.

The conservatism is a demonstration device, not a measurement, and it cuts both ways: it
makes breakthrough visible in six years, and it means every breakthrough time, service
interval and cost figure the demonstrator produces is an artefact of that choice.
