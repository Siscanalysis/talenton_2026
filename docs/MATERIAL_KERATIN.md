# Keratin as the reactive medium: what the literature actually supports

The candidate medium for the mat is a **keratin-based polymer**, most plausibly
derived from waste wool or feather. This document sets the model parameters from
published measurements, states exactly how far those measurements can be
carried, and derates them for seawater. Checked 8 September 2026.

**Nothing here is a measurement of our material.** Every published value below
was obtained on raw or lightly processed keratin biofibres, in deionised water,
at an acidic optimum pH, in a batch reactor. Our application is a porous mat in
seawater at pH ~8.1 under advective flow. The gap between those two situations
is the main scientific risk of the project, and it is quantified rather than
ignored.

---

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

**Literature envelope for Pb on keratin: about 4 to 33 mg/g
(4e-3 to 3.3e-2 kg/kg), in fresh water at acidic pH.**

Kinetics: biosorption fitted the **pseudo-second-order** model in almost every
metal and biosorbent combination, with equilibrium reached within 24 hours in
batch [K1]. Isotherms fitted **Langmuir**, supporting sorption at specific
sites, which is what the capped linear isotherm in `docs/MODEL_SPEC.md`
approximates.

Regeneration: Pb-loaded biofibres were eluted with EDTA or HNO3 (around 100 %
recovery for chicken feathers), but **capacity fell from 97 % to 72 % on the
second cycle** for feathers and wool, and human and dog hair lost about half
[K1]. This matters for the maintenance model: a retrieved mat is not a
like-for-like reusable asset.

## 3. Published mercury capacities: not found

**No verified Hg(II) capacity for a keratin biosorbent was found in this
check.** Keratin materials are frequently *listed* as candidate biosorbents for
mercury among other metals [K1, K5], but the searches did not return a primary
study reporting a measured Hg(II) Langmuir capacity for wool, feather or hair
keratin. This is recorded as **UNKNOWN** rather than filled with a number from a
different material.

For scale only, thiol-functionalised materials that are **not keratin** reach
78.5 mg/g (Hg-imprinted thiol mesoporous sorbent) and 1325 mg/g
(thiol-functionalised cellulose) [K7, K8]. Those figures must not be transferred
to keratin.

### A defensible ceiling from the sulfur content

Instead of borrowing a number, the model uses a **stoichiometric ceiling** from
the measured sulfur content, which is a property of keratin itself:

```
sulfur content            4 wt% (conservative end of the 4-8 wt% range [K4])
                          0.04 g S / g / 32.06 g/mol = 1.25e-3 mol S / g
all cystine reduced       1.25e-3 mol SH / g
Hg binds as Hg(SR)2       6.2e-4 mol Hg / g
                          x 200.59 g/mol = 0.125 g/g = 125 mg/g
```

**125 mg/g is a theoretical ceiling, not a capacity.** It assumes every
disulfide is reduced and every resulting thiol is sterically accessible to a
hydrated Hg species, which no real material achieves. The model therefore takes
a small accessible fraction of it, with a very wide interval, and says so.

## 4. The seawater derating, and why it is large

Every capacity in section 2 was measured at **pH 4.0 in deionised water**. Our
application is seawater. Three effects push the effective capacity down, and
they are not small:

**Speciation.** In seawater at pH 8.2, dissolved lead is dominated by the
uncharged carbonate complex **PbCO3(aq), about 41 % of total dissolved Pb**,
with about 16 % as Pb(CO3)Cl- and 5 to 10 % as chloride complexes [K3]. Free
Pb2+, the species biosorption ion-exchange chemistry actually binds, is a small
minority of the total. Measured free Pb2+ has been reported an order of
magnitude below equilibrium-model predictions [K3].

**Competition.** Seawater contains roughly 10.3 mmol/L Ca2+ and 53 mmol/L Mg2+,
five to seven orders of magnitude more than the trace Pb, competing for the same
carboxyl and amino sites. The published experiments had no such competition.

**pH.** The optimum in [K1] was pH 4.0, chosen partly to avoid hydroxide
precipitation. Seawater sits near pH 8.1. Wool keratin's isoelectric point is
acidic, so at pH 8 the surface is more negatively charged, which helps
electrostatically, but the speciation and competition effects dominate.

**For mercury the derating is different and probably smaller.** In seawater Hg
is dominated by chloride complexes, but the thiol-Hg bond is strong enough that
thiol ligands outcompete chloride. This is precisely why thiol sorbents are the
established route for Hg in saline matrices. The Hg channel is therefore modelled
with a *higher* partition coefficient and a *lower* capacity than Pb: strong
binding to a small number of sites.

## 5. The parameters the model now uses

| Parameter | Pb | Hg | Label | Basis |
|---|---|---|---|---|
| `q_max` operating capacity | 1.0e-3 kg/kg (1.0 mg/g) | 2.5e-3 kg/kg (2.5 mg/g) | assumption | Pb: about one fifth of the lowest freshwater literature value [K1], derated for section 4. Hg: 2 % of the 125 mg/g thiol ceiling. |
| `q_max` interval | 3.0e-4 to 8.0e-3 kg/kg | 2.0e-4 to 2.5e-2 kg/kg | assumption | Pb upper bound is the best freshwater result [K1], that is, the optimistic case where seawater costs nothing. Hg spans 0.16 % to 20 % of the thiol ceiling. |
| `Kd` partition slope | 3.0 m^3/kg | 30.0 m^3/kg | assumption | Derated from Langmuir behaviour [K1]; Hg an order higher for thiol affinity. |
| `Kd` interval | 0.5 to 20 m^3/kg | 2 to 300 m^3/kg | assumption | |
| `k_rate` | 4.0e-4 1/s | 2.0e-4 1/s | assumption | Order of magnitude from pseudo-second-order equilibrium within 24 h in batch [K1]. In a mat the rate is set by intraparticle transport, not by batch kinetics. |
| Bulk density | 400 kg/m^3 | | assumption | A wool-felt-like nonwoven at about 0.5 porosity; keratin solid density is near 1.3 g/cm^3. |
| Allocation | 0.6 | 0.4 | assumption | The same medium is never counted twice. |

### What these parameters imply, and it is worth saying out loud

With 4 kg/m^2 of medium at 10 mm thickness:

* **Pb capacity 2.4e-3 kg/m^2**, consumed by the modelled advective load in
  about **3 years**. Pb is what limits the service life.
* **Hg capacity 4.0e-3 kg/m^2** against a much smaller Hg load, giving a
  breakthrough time of **centuries** in the default scenario. Mercury is
  effectively a durable channel here, and the mat is not replaced because of it.

That asymmetry is a genuine result of the numbers, not a modelling artefact, and
it is a useful thing to be able to say: **for this hotspot, the mat's
replacement schedule is set by lead, while mercury capacity is not the binding
constraint.** It also means the Hg case rests almost entirely on the *unverified*
capacity assumption, which is the honest weak point.

## 6. What must be measured before any of this is a claim

1. Pb and Hg isotherms for **our** keratin polymer in **real or artificial
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
   here, and a protein that degrades releases its bound metal back.
6. Whether the mat alters sediment redox enough to promote **methylmercury**
   production. A protein-rich, sulfur-rich layer over anoxic sediment is a
   plausible substrate for sulfate-reducing bacteria, which are the main
   methylators. This is a specific and serious risk for a keratin mat, and it
   works against the concept rather than for it.

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
| K5 | *Keratin-derived bio-adsorbents for water remediation: current and future trends*, ScienceDirect. https://www.sciencedirect.com/science/article/pii/S2589014X25004918 |
| K6 | *Characterisation of reduction state of cystine linkages on wool fibre surface*, ScienceDirect. https://www.sciencedirect.com/science/article/pii/S0142941821003810 |
| K7 | Hg(II)-imprinted thiol-functionalised mesoporous sorbent, 78.5 mg/g. https://www.sciencedirect.com/science/article/abs/pii/S0039914006002074 (NOT keratin) |
| K8 | Thiol-functionalised cellulose, 1325 mg/g Hg(II). https://www.sciencedirect.com/science/article/pii/S0045653524007847 (NOT keratin) |
