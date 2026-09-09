# Keratin as the reactive medium: what the literature actually supports

The candidate medium is a **keratin-based polymer**, potentially derived from
waste wool or feathers. Published experiments motivate material screening;
the operating parameters remain assumptions about a core that has not been
tested in seawater. Checked 9 September 2026.

**Literature correction, 9 September 2026.** The three supplied papers were
checked against the parameter history. The 2026 review was already cited as
K5, but its numerical tables were not used to calibrate the simulations.
A primary paper on reduced human hair reports Hg uptake, correcting the
previous incomplete search. The newly inspected Pb composite includes calcium
competition and must not be described as salt-free or as neat keratin.
See [the source-by-source audit](PAPER_PARAMETER_TRACEABILITY.md) for page
locations, conversions and experimental discrepancies. Defaults are unchanged.

**Nothing here is a measurement of our material.** The cited materials include
raw fibres, chemically treated wool, nanofibres and composites. Their matrices,
pH, concentration, dosage and contact times differ. The proposed application
is a porous mat in seawater under flow; no supplied paper establishes its
capacity, hydraulic properties or field service life.

## 1. Why keratin is a reasonable candidate

Keratin carries carboxyl, hydroxyl, amino and, importantly, **sulfur-bearing**
functional groups, which act as binding sites for heavy metal ions through
coordination and chelation [K1, K5]. Wool keratin is a high-sulfur protein at
**4 to 8 wt% sulfur**, with cystine making up **7 to 20 % of amino acid
residues** [K4]. The disulfide bonds can be reduced to free thiol (-SH) groups
under basic or reducing conditions [K6].

That thiol chemistry is the reason to look at keratin for **mercury**
specifically: Hg(II) has an exceptionally high affinity for thiol sulfur, and
thiol-functionalised sorbents are the established route for Hg capture. It is
also the reason keratin is a *bio-derived* candidate rather than another
activated carbon: the selectivity is intrinsic to the protein.

## 2. Published lead capacities

Primary source [K1], Zhang, Carrillo, Lopez-Mesas and Palet (2019), *Textile
Research Journal* 89(7):1153-1165, DOI 10.1177/0040517518764008. Langmuir
maximum biosorption capacities for Pb(II) at 22 +/- 1 C, **pH 4.0**, in
**deionised water**, from a multiple-metal solution of eight ions:

| Keratin biofibre | Langmuir q_max | Converted (Pb, 207.2 g/mol) |
|---|---|---|
| Chicken feathers | 3.87e-5 mol/g | **8.02 mg/g** = 8.0e-3 kg/kg |
| Degreased wool | 3.40e-5 mol/g | **7.04 mg/g** = 7.0e-3 kg/kg |
| Human hair | 2.43e-5 mol/g | 5.03 mg/g |
| Dog hair | 2.07e-5 mol/g | 4.29 mg/g |

The same paper reports, for comparison at the same basis: activated carbon
3.22e-5 mol/g (6.67 mg/g) and bentonite 3.13e-5 mol/g (6.49 mg/g), so the
keratin biofibres are **comparable to activated carbon**, not dramatically
better. It cites Kong et al. for a keratin/hide-waste biosorbent at
1.06e-4 to 1.56e-4 mol/g, that is **22 to 32 mg/g**.

A separate study on brut keratin powder from sheep horn reports a monolayer
Pb(II) capacity of **33.33 mg/g at 298 K** [K2].

**Selected older Pb biofibre/powder results: about 4 to 33 mg/g
(4e-3 to 3.3e-2 kg/kg), principally freshwater batch conditions.**
This is the subset that motivated the original default, not the complete
capacity envelope for all modified keratin composites in the supplied review.

Kinetics: biosorption fitted the **pseudo-second-order** model in almost every
metal and biosorbent combination, with equilibrium reached within 24 hours in
batch [K1]. Isotherms fitted **Langmuir**, supporting sorption at specific
sites. The capped linear law in `docs/MODEL_SPEC.md` is a computational
approximation, not a fitted version of those experimental Langmuir curves.

Regeneration: Pb-loaded biofibres were eluted with EDTA or HNO3 (around 100 %
recovery for chicken feathers), but **capacity fell from 97 % to 72 % on the
second cycle** for feathers and wool, and human and dog hair lost about half
[K1]. This matters for the maintenance model: a retrieved mat is not a
like-for-like reusable asset.

## 3. Published mercury evidence and the remaining material gap

The earlier statement that no verified keratin-derived Hg capacity had been
found is superseded. The supplied review [K5, p. 5] cites Liang et al. [K15]:
mechanically activated human hair reduced with ammonium thioglycolate has a
reported **476.7 mg/g Hg uptake** in the primary publisher's highlights.
This is a particular modified material; it does not validate the proposed
wool/feather core in seawater. Full primary experimental methods were not
retrieved in this audit.

The remaining unknown is **Hg capacity and kinetics for the actual core under
flowing seawater conditions**. The model retains 2.5 mg/g as an assumption,
without presenting it as a fit to [K15].

### The conditional sulphur-site calculation used by the default

The original calculation assumes a 4 wt% sulphur content [K4], full conversion
to accessible sites and two sulphur atoms per captured Hg:

```text
0.04 g S/g / 32.06 g/mol / 2 * 200.59 g Hg/mol
    = 0.125 g Hg/g = approximately 125 mg/g
```

This is an **idealised bound for those assumptions**, not a universal ceiling
for chemically modified keratin. The material, binding stoichiometry and final
sulphur content must be measured. Taking 2% of this value gives the assumed
2.5 mg/g; that accessibility fraction has not been measured either.

## 3b. Copper and lead: material form and experimental endpoint matter

Published Cu results from the original evidence chain include 20 mg/g on wool
keratin nanofibres and 27.4 mg/g on keratin-modified magnetite [K9]. The supplied
Enkhzaya study [K13, Table 2] adds a more directly relevant wool comparison:

| Material | Langmuir maximum, mg Cu/g | Test context |
|---|---:|---|
| Untreated sheep wool | 15.19 | pH 5, 303 K, batch, 48 h |
| 0.05 M Na2S-treated wool | 51.92 | same conditions; 44.24% preparation mass loss |
| 0.02 M Na2S-treated wool | 17.03 | same conditions; 1.51% preparation mass loss |

The source uses 10 mg material in 15 mL and 1 to 100 mg/L initial Cu. It does
not test a marine mat. Its pre-proof contains figure/table and kinetic-inventory
discrepancies recorded in the traceability audit, so the fits should not be
silently reused as validation data. The simulator's 3 mg/g Cu capacity and
0.02 available fraction remain separate assumptions. Strong organic Cu
complexation in measured porewaters [K11] motivates testing low availability;
it does not prove that all keratin chemistries fail to remove Cu from seawater.

The supplied Zubair composite [K14] is feather keratin with
acrylamide-functionalised graphene oxide, **not neat keratin**. It removed
99.21% of Pb after 24 h at pH 7.5, with 600 micrograms/L initial Pb and 0.1 g
composite in 10 mL. Its matrix contains 0.02 M NaCl and 0.01 M CaCl2, at ionic
strength 0.05 M. It includes calcium competition but is not complete seawater.

The batch balance gives **0.059526 mg Pb/g** captured at that dose. This is
neither a Langmuir maximum nor a 99.21% mat-flux attenuation. No Cu or Hg was
tested. Four acid-regeneration cycles concern that composite in the laboratory;
they do not establish equivalent regeneration of a deployed core [K14].

## 3c. Mercury speciation is not a fixed free-ion percentage

Chloride complexes can dominate Hg(II) in saline oxic water [K10], while
organic ligands and sulphide change binding and availability in other settings.
The frequently quoted fraction above 99% chloride-complexed is not a universal
porewater composition. Thiol groups can exchange ligands with Hg complexes,
so neither free-ion concentration nor the need to displace chloride directly
sets the amount accessible over a mat's contact time.

The model's `available_fraction = 0.10` and interval 0.01 to 0.4 for Hg are
assumptions. Its 30 m^3/kg partition slope is also assumed. Experiments on
activated carbon show that chloride, sulphide and dissolved organic matter
can change uptake [S04 in `REFERENCES.md`], but they do not calibrate keratin.
The updated human-hair evidence [K15] strengthens the material-screening
rationale without resolving seawater-core transport or speciation.

## 4. Why freshwater evidence does not set operating seawater parameters

Zhang's biofibre Pb values [K1] were measured at pH 4 in deionised water.
Other cited materials and matrices differ, including the salt-containing
pH-7.5 composite assay [K14]. The earlier blanket description of every keratin
experiment as salt-free and acidic is therefore incorrect.

Pb carbonate/chloride complexes, organic ligands and abundant competing ions
all matter. Typical seawater Ca and Mg concentrations are about 10.3 and
53 mmol/L, respectively. The new composite experiment includes 10 mmol/L Ca,
but not the complete marine major-ion or organic-ligand matrix. More negative
surface charge at higher pH can favour cation binding while speciation and
competition act differently. These mechanisms do not supply a unique derating
factor from batch capacity to seawater capacity.

The operating capacities, partition slopes and available fractions below
remain deliberately explicit assumptions. They must be varied separately in
sensitivity work and ultimately measured together for a defined material.
An assumed low value is not necessarily conservative for every model outcome:
reducing uptake also changes breakthrough, retrieval and the estimator's
uncertainty. The simulation cannot confirm its own chemical parameter choices.

## 5. Parameters used in the model

All values below have provenance `assumption`. They are screening parameters,
not measured seawater estimates or confidence intervals.

| Parameter | Pb | Hg | Cu |
|---|---:|---:|---:|
| Operating `q_max`, kg/kg | 0.001 | 0.0025 | 0.003 |
| `q_max` interval, kg/kg | 0.0003 to 0.008 | 0.0002 to 0.025 | 0.0005 to 0.020 |
| `Kd`, m^3/kg | 3 | 30 | 8 |
| `Kd` interval, m^3/kg | 0.5 to 20 | 2 to 300 | 1 to 60 |
| First-order `k_rate`, 1/s | 0.0004 | 0.0002 | 0.0005 |
| Available fraction | 0.25 | 0.10 | 0.02 |
| Sorbent allocation | 0.60 | 0.30 | 0.10 |

The bulk density is assumed to be 400 kg/m^3 and thickness 0.010 m, giving
4 kg/m^2 of core. Porosity 0.5 is a separate assumption; it is not obtained by
combining that bulk density with a 1300 kg/m^3 solid density. Those quantities
need joint measurement for the finished composite.

The allocated nominal inventories are 0.0024 kg Pb/m^2, 0.0030 kg Hg/m^2 and
0.0012 kg Cu/m^2. Dividing these by an assumed advective input gives a
capacity-to-load ratio, **not a breakthrough or replacement prediction**.
Finite affinity, reversible uptake, porewater storage, bypass and the selected
service policy also determine the time response. In particular, a simulation
may reach a low-occupancy steady state before exhausting nominal capacity.

The Pb and Cu `commissioned_q_max_interval` values represent hypothetical
information for a synthetic operator. No commissioning experiment was
performed. Hg has no commissioned range in the default scenario, but that
software choice does not imply that Hg commissioning is scientifically
impossible or that no keratin-derived Hg literature exists.

## 6. What must be measured before any of this is a claim

1. Pb, Hg and Cu isotherms for **our** keratin polymer in **real or artificial
   seawater** at pH 8.1, with Ca and Mg present. This is the single most
   important experiment.
2. Whether the disulfides are reduced in the final material, and what fraction
   of thiols is accessible. The entire Hg case depends on it.
3. Capacity retention after the first regeneration cycle, given the 97 % to 72 %
   drop observed for feathers and wool [K1].
4. Effective diffusivity and hydraulic conductivity of the actual mat structure,
   which set `D_eff` and the advective flux and are currently pure assumptions.
5. Whether a keratin mat survives months of seawater immersion at all:
   biodegradation, microbial attack and mechanical integrity are unaddressed
   here. Degradation can change capacity, leaching and retained-metal release;
   the released fraction and its fate must be measured.
6. Whether the final material changes **methylmercury** formation, degradation
   and net release. Leachables and altered sediment chemistry could affect
   microbial processes, but their direction and magnitude cannot be inferred
   from total sulphur or protein content alone. Measure net transport and
   biological effects alongside total Hg removal.

Point 6 deserves emphasis: adding a biodegradable, sulfur-rich organic layer on
top of contaminated anoxic sediment is not obviously ecologically neutral. See
`docs/LIMITATIONS.md`.

---

## References

| Key | Source |
|---|---|
| K1 | Zhang, H., Carrillo, F., Lopez-Mesas, M., Palet, C. (2019), *Valorization of keratin biofibers for removing heavy metals from aqueous solutions*, Textile Research Journal 89(7):1153-1165. DOI 10.1177/0040517518764008. Open copy: https://upcommons.upc.edu/handle/2117/116153 |
| K2 | *Modeling isotherm and mechanism adsorption of heavy metals from water using brut keratin powder prepared from Algerian sheep horns*, ScienceDirect. https://www.sciencedirect.com/science/article/pii/S1944398624081219 (Pb monolayer capacity 33.33 mg/g at 298 K; figure taken from the indexed summary, full text not retrieved in this check) |
| K3 | Lead speciation in seawater: PbCO3(aq) about 41 % of dissolved Pb at pH 8.2, free Pb2+ a small minority. https://doi.org/10.3390/w17101470 and https://nap.nationalacademies.org/read/24898/chapter/5 |
| K4 | Wool keratin sulfur content 4 to 8 wt%, cystine 7 to 20 % of residues. https://ift.onlinelibrary.wiley.com/doi/10.1111/1541-4337.13087 ; NIST, *Role of cystine in the structure of the fibrous protein, wool*, https://nvlpubs.nist.gov/nistpubs/jres/27/jresv27n1p89_A1b.pdf |
| K5 | Zubair, M., Rauf, Z., Ullah, A. (2026), *Keratin-derived bio-adsorbents for water remediation: Current and future trends*, Bioresource Technology Reports 33, 102508. https://doi.org/10.1016/j.biteb.2025.102508. Supplied full review inspected; its numerical tables did not calibrate the original defaults. |
| K6 | *Characterisation of reduction state of cystine linkages on wool fibre surface*, ScienceDirect. https://www.sciencedirect.com/science/article/pii/S0142941821003810 |
| K7 | Hg(II)-imprinted thiol-functionalised mesoporous sorbent, 78.5 mg/g. https://www.sciencedirect.com/science/article/abs/pii/S0039914006002074 (NOT keratin) |
| K8 | Thiol-functionalised cellulose, 1325 mg/g Hg(II). https://www.sciencedirect.com/science/article/pii/S0045653524007847 (NOT keratin) |
| K9 | Aluigi et al. (2012), *Wool Keratin Nanofibres for Copper(II) Adsorption*, https://doi.org/10.1166/jbmb.2012.1204: pure wool-keratin nanofibres, 20 mg/g Cu uptake in batch at pH 6. The distinct keratin/PA6 blend study, https://www.sciencedirect.com/science/article/abs/pii/S0014305711002394, reports 61.7 / 90 / 103.5 mg/g at 50 / 70 / 90 wt% keratin; these are different materials. Zhang et al. (2021), https://doi.org/10.3390/nano11051068: wool-keratin-modified magnetite, 27.4 mg/g at pH 5 and 293 K after 90 min (primary paper conclusions). None is a bulk felt core or a seawater-core calibration. |
| K10 | Mercury speciation depends on chloride, sulphide, dissolved organic matter and redox. *Mercury in Marine and Oceanic Waters, a Review*, Water Air Soil Pollut (2016), DOI 10.1007/s11270-016-3060-3, https://pmc.ncbi.nlm.nih.gov/articles/PMC5013138/. The frequently quoted chloride fraction is not a universal value for organic-rich reducing porewater or a measured sorbent-accessible fraction. |
| K11 | Paul et al. (2021), *Copper-binding ligands in deep-sea pore waters of the Pacific Ocean*, Scientific Reports, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8446087/. More than 99% organically complexed Cu and free Cu below 6 pM in eight of nine fitted samples; strong ligand conditional constants around 1e15. These sample-specific results do not identify the model's 0.02 availability factor. See also https://www.nature.com/articles/s43247-022-00597-1. |
| K12 | Gilmour et al. (2013), *Activated Carbon Mitigates Mercury and Methylmercury Bioavailability in Contaminated Sediments*, https://doi.org/10.1021/es4021074: sediment microcosms with activated carbon/thiol-silica amendments at 2?7% dry mass; porewater MeHg reduced 45?95% and test-organism uptake 30?90%. Johnson et al. (2010), https://doi.org/10.1021/es100161p: increased MeHg beneath a cap in laboratory estuarine microcosms, without a necessarily significant cap-water-interface effect. Neither validates keratin ecological behaviour. |
| K13 | Enkhzaya, S., Shiomori, K., Oyuntsetseg, B. (2020), *Effective adsorption of Au(III) and Cu(II) by chemically treated sheep wool and the binding mechanism*, Journal of Environmental Chemical Engineering 8(5), 104021. https://doi.org/10.1016/j.jece.2020.104021. Supplied pre-proof Tables 1 to 3 and methods inspected; see traceability audit for discrepancies. |
| K14 | Zubair, M., Roopesh, M. S., Ullah, A. (2025; online 2024), *Green Nanoengineered Keratin Derived Bio-Adsorbent for Heavy Metals Removal from Aqueous Media*, Advanced Sustainable Systems 9, 2400491. https://doi.org/10.1002/adsu.202400491. Supplied full article; CFK-SMGO composite, Pb batch percentage rather than capacity maximum. |
| K15 | Liang, X. et al. (2023), *Mechanochemical-assisted reduction of human hair for efficient and selective removal of aqueous Hg(II) to the ppb level*, Journal of Molecular Liquids 371, 121124. https://doi.org/10.1016/j.molliq.2022.121124. Primary publisher abstract/highlights verified; full methods and marine-core transfer not verified. |
