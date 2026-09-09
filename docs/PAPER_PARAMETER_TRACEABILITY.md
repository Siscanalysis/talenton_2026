# Paper-to-parameter traceability

Audited 9 September 2026 against the three PDFs supplied by the project owner
and the simulation repository at baseline commit `158d103`. The accompanying
[machine-readable register](../research/references/paper_parameter_traceability.json)
contains source hashes, locations, original units, conversions and use decisions.
PDF page numbers below are one-based and refer to the supplied copies.
Copyrighted article files and extracted article text are not distributed here.

## What the original simulations actually used

**The supplied papers were not used to fit the simulation parameters.** The
2026 Zubair review already appeared as reference K5 in
`docs/MATERIAL_KERATIN.md`, supporting the choice of keratin. That is a
bibliographic connection, not evidence that its numerical tables were used.
Neither the Enkhzaya 2020 article nor the Zubair 2024/2025 article appears in
the baseline parameter references or their recorded history.

| Channel | Default capacity | Original numerical rationale | Relation to supplied PDFs |
|---|---:|---|---|
| Pb | 1.0 mg/g = 0.001 kg/kg | Assumed seawater derating of Zhang et al. (2019), K1; original interval 0.3 to 8.0 mg/g | No direct parameter use of the supplied Pb experiment |
| Hg | 2.5 mg/g = 0.0025 kg/kg | Assumed 2% of a conditional sulphur-site calculation; original interval 0.2 to 25 mg/g | The supplied review contains contrary evidence to the earlier literature-search statement, but it did not calibrate the default |
| Cu | 3.0 mg/g = 0.003 kg/kg | Assumed bulk-core derating of older nanofibre studies, K9; original interval 0.5 to 20 mg/g | No direct use of Enkhzaya's wool measurements |

The accompanying baseline values of `Kd`, uptake rate and available fraction
are also labelled `assumption`. The Pb and Cu commissioning intervals are
**hypothetical information available to a synthetic operator**, not completed
laboratory measurements. A numerical simulation cannot validate the chemical
assumptions that drive its results.

The trace is checkable in `src/reactive_seabed_mat/config.py`, in the conversion
to runtime parameters in `reactive_layer/material.py`, and in these commits:

- `407fb44f38bb66c6072c7316a9eeaa4899f86d31` introduced the Pb/Hg material
  values and K5 on 8 September 2026.
- `e423731a1b37689960547c608bea953fe3ad498a` introduced the Cu channel,
  geotextile core and available-fraction treatment later that day.
- History searches for `10.1016/j.jece.2020.104021` and
  `10.1002/adsu.202400491` in the scientific documentation and source produced
  no pre-audit matches. This establishes the recorded provenance, not what an
  earlier author might privately have read.

## Enkhzaya et al. (2020): treated wool and copper

Source: S. Enkhzaya, K. Shiomori and B. Oyuntsetseg, *Effective adsorption of
Au(III) and Cu(II) by chemically treated sheep wool and the binding mechanism*,
Journal of Environmental Chemical Engineering 8(5), 104021.
[DOI: 10.1016/j.jece.2020.104021](https://doi.org/10.1016/j.jece.2020.104021).
The supplied document is a 35-page journal pre-proof, including a cover page.

The Cu experiment used 10 mg of wool in 15 mL of solution, 303 K, initial pH
5, initial concentrations 1 to 100 mg/L and 48 h equilibration at 50 rpm
(section 2.4, PDF p. 5; Fig. 5, PDF p. 21). Section 2.4 describes preparation
in 1 mol/L HCl, while the Cu figure specifies pH 5 after adjustment. The final
electrolyte composition is therefore not a demonstrated seawater matrix.
The 323 K temperature in section 2.2 is the **one-hour chemical preparation**
temperature, not the adsorption temperature.

| Wool material | Table 2 Langmuir maximum (mmol Cu/g) | Converted maximum (mg Cu/g) | Langmuir K (L/mg) | Fit R² |
|---|---:|---:|---:|---:|
| Untreated SW | 0.239 | 15.1875 | 0.51 | 0.9565 |
| SW-III, 0.05 M Na2S treatment | 0.817 | 51.9171 | 0.54 | 0.9724 |
| SW-IV, 0.02 M Na2S treatment | 0.268 | 17.0303 | 1.16 | 0.9618 |

Table 2 is PDF p. 32, printed p. 31; units are defined in section 3.3.1,
PDF p. 7. Conversion uses 63.546 mg Cu/mmol. Preparation matters: the stronger
0.05 M treatment lost 44.24% of the original wool mass and produced a sheet-like
structure; 0.02 M lost 1.51% and retained fibres (Table 1, PDF p. 31; abstract).
A capacity per gram of recovered treated material is not a capacity per gram
of original wool purchased or a demonstration of a mechanically durable mat.

The low-concentration Langmuir slopes calculated as `qmax * K` are 7.7456,
28.0352 and 19.7552 m³/kg respectively. These are **derived batch slopes**,
not seawater `Kd` measurements. Their superficial numerical similarity to a
model value is not evidence of historical use.

Table 3 (PDF p. 33, printed p. 32) reports Cu pseudo-second-order `k2` values
of 0.1066, 0.0172 and 0.1451 g/(mmol min), with fitted equilibrium uptakes
0.1126, 0.2721 and 0.1216 mmol/g, respectively. A pseudo-second-order
coefficient cannot be pasted into the simulator's first-order rate in s⁻¹.
The time-series caption specifies 10 mg/L initial Cu (Fig. 6, PDF p. 22).

Two pre-proof consistency limitations must accompany any reuse:

- Fig. 5 shows the SW-IV curve approaching approximately 0.36 mmol/g,
  whereas Table 2 reports 0.268 and the text rounds it to 0.27. The table
  values above are transcribed faithfully; the disagreement is unresolved.
- At the kinetic caption's concentration, volume and sorbent mass, the entire
  initial Cu inventory is 15 mg/g, or 0.23605 mmol/g. The fitted SW-III
  equilibrium value 0.2721 mmol/g exceeds that amount. This is an inconsistency
  between the fitted asymptote and stated experimental conditions, not a
  validation target for the simulator.

This paper measures Au and Cu, not Pb or Hg. Its Au capacity must not be
reassigned to either simulated element.

## Zubair, Roopesh and Ullah: the supplied 2024/2025 composite study

Source: M. Zubair, M. S. Roopesh and A. Ullah, *Green Nanoengineered Keratin
Derived Bio-Adsorbent for Heavy Metals Removal from Aqueous Media*, Advanced
Sustainable Systems **9, 2400491 (2025)**; copyright/online publication 2024.
[DOI: 10.1002/adsu.202400491](https://doi.org/10.1002/adsu.202400491).
The filename's 2024 date and the journal's 2025 year describe the same article.

The material is chicken-feather keratin functionalised with
acrylamide-modified graphene oxide (CFK-SMGO). It is not neat keratin. The
preparation charged 2 g keratin and 1 g modified graphene oxide, reacted at
80°C for 8 h and washed and dried the product; this input ratio is not a
measured final composite composition (experimental section, PDF p. 13).

The batch conditions were 0.1 g composite in 10 mL synthetic wastewater,
containing **600 µg/L of each of eight metal(loid)s**: Pb, Cd, Ni, Co, Zn,
As, Se and Cr. Pb was measured, whereas Cu and Hg were not. The matrix was
prepared from nanopure water with **0.02 M NaCl and 0.01 M CaCl2**, giving
the stated ionic strength **0.05 M**. Thus calcium competition was tested.
This is not the complete seawater matrix: no marine Mg or dissolved-organic
ligand mixture was specified. Initial pH values were 5.5, 7.5 and 10.5,
with highest removal generally at pH 7.5 (abstract; experimental section p. 13).

Pb removal at pH 7.5 after 24 h was **99.21%** (abstract, PDF p. 1;
section 3.4, p. 9; Fig. 10, p. 10). The reported percentage is a removal
efficiency under this dose, not a Langmuir maximum. A simple batch balance
gives:

```text
initial Pb mass = 0.600 mg/L * 0.010 L = 0.00600 mg
Pb adsorbed     = 0.00600 mg * 0.9921 = 0.0059526 mg
batch uptake    = 0.0059526 mg / 0.100 g = 0.059526 mg/g
residual Pb     = 600 µg/L * (1 - 0.9921) = 4.74 µg/L
```

The mass-limited maximum at this dose is only 0.060 mg/g. Consequently, this
experiment establishes neither a 99.21 mg/g capacity nor a 0.059526 mg/g
saturation capacity. It also does not justify setting mat flux attenuation
to 99.21%. Fig. 10 separately shows much lower Pb removal for neat CFK;
the composite's result must not be credited to the protein alone.

Contact times were 1, 3, 6, 12 and 24 h, with much of the initial uptake in
the first 6 h. No Langmuir-capacity fit or model-compatible kinetic rate is
reported. The results narrative specifies 24°C, while methods specify
approximately 20°C and a 20°C kinetic shaker; retain this discrepancy instead
of selecting a temperature silently (pp. 11 and 13).

Four laboratory adsorption/desorption cycles used 10 mL of 2 M HCl for 24 h,
washing and drying at 50°C; assays were in triplicate (p. 13). This is evidence
of laboratory regeneration of that composite, not evidence that seabed mats
can be serviced or reused four times with unchanged capacity. The conclusion
on p. 12 also swaps metal names around two percentage values; the mapping used
here follows the abstract, results and Fig. 10.

## Zubair, Rauf and Ullah (2026): review and the mercury correction

Source: M. Zubair, Z. Rauf and A. Ullah, *Keratin-derived bio-adsorbents for
water remediation: Current and future trends*, Bioresource Technology Reports
33, 102508 (2026).
[DOI: 10.1016/j.biteb.2025.102508](https://doi.org/10.1016/j.biteb.2025.102508).
The baseline already cited this article as K5. It is a review, so each material
and experimental endpoint must be distinguished before importing a number.

**The earlier statement that no verified keratin-derived Hg capacity had been
found is superseded.** Page 5 cites mechanically activated, chemically reduced
human hair. The primary publisher's abstract/highlights for Liang et al.
(2023), Journal of Molecular Liquids 371, 121124, verify **476.7 mg Hg/g**,
distribution coefficient **2.6 × 10⁶ mL/g**, and reduction from 1 mg/L to
below 2 µg/L in tested samples.
[Primary DOI: 10.1016/j.molliq.2022.121124](https://doi.org/10.1016/j.molliq.2022.121124).

That Hg result is for ammonium-thioglycolate-reduced human hair. Its complete
experimental protocol and seawater applicability were not verified here.
It corrects the literature claim; it does not calibrate the proposed core.
The correct remaining unknown is **Hg uptake by the actual wool/feather core
in flowing seawater**. The model's 125 mg/g calculation is conditional on 4%
sulphur and two S atoms per Hg; it is not a universal ceiling for every
chemically modified keratin material.

The register also records the review's Pb/Cu leads: 43.3 mg Pb/g for a wool
keratin colloid; 143.2 mg Pb/g for a feather/polyacrylate/PVA network;
337.9 mg Cu/g for hydrolysed keratin/diallylamine; and 58.95 mg Cu/g for
ground wool keratin powder. These are **secondary-source leads** until the
individual primary methods are checked. Other rows give percentages, not
capacities. The review even equates 1 mol/L to 1,000,000 ppb in one Cu row,
which is not a valid element-independent conversion. Do not import that row.

Likewise, the review's 35 g/L salinity result concerns **uranium** on an
amidoxime-functionalised aerogel. It supplies no seawater Pb, Hg or Cu
calibration. Several large capacities in its selectivity discussion belong
to agave bagasse or carbon adsorbents, not keratin; those are excluded from
the keratin parameter envelope.

## Parameter decision and experiments needed

Retain the operating defaults as assumptions. None of the supplied papers
measures the joint `qmax`, low-concentration partition slope, effective rate,
diffusivity and hydraulic properties of the proposed core in seawater.
Changing one maximum while retaining all other defaults would manufacture a
material that none of these studies tested.

Paper-derived values can guide separate, clearly labelled material-screening
studies. In particular, compare untreated and sulphide-treated wool for Cu,
compare neat CFK with CFK-SMGO for Pb, and test reduced hair or deliberately
thiolated feather/wool for Hg. First reproduce each laboratory matrix; then
measure multi-ion isotherms and flow-through breakthrough for the actual core
in seawater, including Ca, Mg, chloride and organic ligands. A batch uptake
percentage and an equilibrium maximum must remain different observables.

For numerical sensitivity studies, vary capacity, affinity, availability and
rate separately and state that their uncertainty ranges are assumptions.
Such studies locate informative experiments; they cannot prove that copper
capture is impossible or establish a field service lifetime.
