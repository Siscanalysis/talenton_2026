"""Which few hectares, and why: ranking candidate areas by what they protect.

`scale.py` establishes that only one or two hectares can realistically be
covered. This module is the consequence: if the area is fixed and small, the
question stops being *how good is the mat* and becomes **where does a hectare of
it do the most good**.

The answer proposed here is **receptor proximity**, not contaminant mass. A
tonne of lead in 90 m of water 40 km offshore reaches almost nobody. A tenth of
that, seeping under a bathing beach, a mussel farm or a municipal water intake,
reaches people and reaches them through a short, documented pathway. For a first
deployment funded by a government or a municipality, the deliverable is reduced
exposure of a named receptor, not reduced inventory.

That is a defensible priority rule and it is also a **commercially honest** one:
it points at the customer who already exists. Germany's federal Immediate Action
Programme for dumped munitions is funded at EUR 100 million and ran its first
pilot clearance in the **Bay of Lubeck**, off Haffkrug and Pelzerhaken, in
shallow water beside coastal resort towns [P1, P2]. That is a national
environment ministry, working close inshore, next to tourism and fisheries.

Three cautions, and the third is the serious one
------------------------------------------------

1. **This scoring is a transparent ranking device, not a risk assessment.** It
   has no dose-response model, no exposure duration, no toxicology, and it
   applies no regulatory threshold to declare anything safe or unsafe. It orders
   candidates; it does not certify them.
2. **The distances are illustrative.** Real siting needs bathymetry, real
   current fields, the actual receptor register and a competent authority. This
   module ranks scenarios, not sites.
3. **The contaminant may not be ours.** At the German coastal dumpsites the
   contamination measured reaching biota is *energetic compounds*, TNT, RDX and
   DNT, not heavy metals [P3, P4]. Keratin thiols bind soft metals; they do not
   bind nitroaromatics. See :data:`CONTAMINANT_MISMATCH_WARNING`. Prioritising
   coastal munitions sites on receptor grounds is right, and it points at a
   contaminant this material does not address. That has to be said before a
   proposal is written, not after.

References
----------
P1  German Federal Ministry for the Environment, Immediate Action Programme for
    dumped munitions, EUR 100 million; first pilot clearance in the Bay of
    Lubeck from 2024, concluded 2025. Four known German Baltic dumping areas:
    two in Lubeck Bay, Kolberger Heide near Kiel, one near Falshoft.
P2  GEOMAR Helmholtz Centre for Ocean Research Kiel, munitions mapping and the
    Kolberger Heide monitoring programme; planned salvage platform from end of
    2026 at roughly 2 t/day against about 300,000 t in German waters.
P3  Four-year monitoring of the Bay of Lubeck prior to remediation: TNT and six
    further energetic compounds detected in all monthly water samples at four
    locations; 1,3-dinitrobenzene, 2,4-dinitrotoluene and RDX above 1 ng/L on
    average; energetic compounds in blue mussels below 0.6 ng/g dry weight.
P4  Explosives from dumped munitions measured in dab from German coastal
    waters: parent TNT below detection, metabolites present.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

__all__ = [
    "RECEPTOR_WEIGHTS",
    "CONTAMINANT_MISMATCH_WARNING",
    "PRIORITY_NOTE",
    "GERMAN_PROGRAMME",
    "Receptor",
    "CandidateArea",
    "PILOT_CANDIDATES",
    "proximity_score",
    "priority_score",
    "rank_candidates",
    "recovery_years",
]

PRIORITY_NOTE = (
    "A transparent ranking device, not a risk assessment. No dose-response "
    "model, no exposure duration, no toxicology, and no regulatory threshold is "
    "applied anywhere. It orders candidates; it does not certify them."
)

CONTAMINANT_MISMATCH_WARNING = (
    "At the German coastal munitions dumpsites the contamination measured "
    "reaching biota is energetic compounds (TNT, RDX, DNT), not heavy metals. "
    "A keratin thiol core binds soft metals and does not bind nitroaromatics. "
    "Ranking those sites highly on receptor grounds is correct and points at a "
    "contaminant this material does not address."
)

#: How much a receptor class raises the priority of a nearby area.  These are
#: **judgement weights**, not derived from any risk model, and they are exposed
#: as data precisely so a reviewer can disagree with the numbers rather than
#: with a hidden constant.
RECEPTOR_WEIGHTS: Mapping[str, float] = {
    "bathing_water": 1.0,
    "shellfish_or_aquaculture": 1.0,
    "commercial_fishery": 0.8,
    "drinking_or_process_intake": 1.0,
    "protected_habitat": 0.7,
    "port_or_navigation": 0.4,
}


@dataclass(frozen=True, slots=True)
class Receptor:
    """Something a deployment would be protecting, and how far away it is."""

    kind: str
    distance_km: float
    name: str = ""

    def __post_init__(self) -> None:
        if self.kind not in RECEPTOR_WEIGHTS:
            raise KeyError(
                f"unknown receptor kind {self.kind!r}; known: "
                f"{sorted(RECEPTOR_WEIGHTS)}"
            )
        if self.distance_km < 0.0 or not math.isfinite(self.distance_km):
            raise ValueError(
                f"receptor distance must be finite and non-negative, got "
                f"{self.distance_km!r}"
            )


@dataclass(frozen=True, slots=True)
class CandidateArea:
    """A candidate deployment area.  Illustrative, not a proposed site."""

    name: str
    sea: str
    depth_m: float
    area_km2: float
    receptors: Sequence[Receptor] = ()
    #: Which contaminants dominate here, as documented rather than assumed.
    documented_contaminants: Sequence[str] = ()
    note: str = ""
    source: str = ""

    @property
    def addressable_by_this_material(self) -> bool:
        """Does this mat's chemistry target what is actually there?

        True only if a metal we model is among the documented contaminants.
        A site dominated by energetic compounds returns False, and the ranking
        reports that rather than quietly scoring it as a win.
        """
        targets = {"Pb", "Hg", "Cu", "heavy_metals"}
        return bool(set(self.documented_contaminants) & targets)


#: Illustrative candidates spanning the range of the argument: a deep offshore
#: dumpsite, the shallow coastal dumpsites where the funded programme actually
#: works, and a harbour of the kind where reactive capping is already deployed.
PILOT_CANDIDATES: tuple[CandidateArea, ...] = (
    CandidateArea(
        name="Bornholm Basin, primary dumpsite",
        sea="Baltic Sea",
        depth_m=90.0,
        area_km2=96.98,
        receptors=(
            Receptor("commercial_fishery", 12.0, "Baltic demersal fishery"),
            Receptor("protected_habitat", 20.0),
        ),
        documented_contaminants=("chemical_warfare_agents", "As", "heavy_metals"),
        note=(
            "The largest and best-defined dumpsite, and the furthest from "
            "anyone. Deep, offshore, no bathing water and no aquaculture."
        ),
        source="B3",
    ),
    CandidateArea(
        name="Bay of Lubeck coastal dumping areas",
        sea="Baltic Sea",
        depth_m=20.0,
        area_km2=8.0,
        receptors=(
            Receptor("bathing_water", 1.5, "Haffkrug and Pelzerhaken beaches"),
            Receptor("shellfish_or_aquaculture", 4.0),
            Receptor("commercial_fishery", 2.0),
            Receptor("port_or_navigation", 6.0),
        ),
        documented_contaminants=("TNT", "RDX", "DNT"),
        note=(
            "Where the funded German pilot clearance actually ran, in shallow "
            "water beside resort towns. The measured contamination reaching "
            "biota here is energetic compounds, NOT the metals this mat binds."
        ),
        source="P1, P3",
    ),
    CandidateArea(
        name="Kolberger Heide, Kiel Bay",
        sea="Baltic Sea",
        depth_m=12.0,
        area_km2=13.0,
        receptors=(
            Receptor("bathing_water", 3.0),
            Receptor("commercial_fishery", 1.0),
            Receptor("port_or_navigation", 2.0),
            Receptor("protected_habitat", 1.0),
        ),
        documented_contaminants=("TNT", "heavy_metals"),
        note=(
            "Shallow, close inshore, and the most thoroughly mapped munitions "
            "site in German waters after a decade of GEOMAR survey work."
        ),
        source="P1, P2",
    ),
    CandidateArea(
        name="Industrial harbour sediment, generic",
        sea="coastal",
        depth_m=8.0,
        area_km2=0.5,
        receptors=(
            Receptor("port_or_navigation", 0.1),
            Receptor("commercial_fishery", 3.0),
            Receptor("bathing_water", 2.5),
            Receptor("drinking_or_process_intake", 1.0),
        ),
        documented_contaminants=("Pb", "Hg", "Cu", "heavy_metals"),
        note=(
            "Not a munitions site at all. This is where reactive capping is "
            "already commercially deployed and where the contaminant actually "
            "matches this chemistry."
        ),
        source="E1, E2",
    ),
)

#: The funded reference customer, for scale comparisons.
GERMAN_PROGRAMME: Mapping[str, object] = {
    "name": "German federal Immediate Action Programme for dumped munitions",
    "funder": "Federal Ministry for the Environment",
    "budget_eur": 1.0e8,
    "first_pilot": "Bay of Lubeck, 2024 to 2025",
    "planned_platform_tonnes_per_day": 2.0,
    "german_waters_munitions_tonnes": 300000.0,
    "source": "P1, P2",
}


def recovery_years(
    tonnes: float = 300000.0, tonnes_per_day: float = 2.0
) -> float:
    """How long physical recovery takes at the planned rate.

    Not a criticism of recovery, which is the right answer where it is
    affordable and safe. It is the size of the gap a containment measure would
    have to cover in the meantime, and it is the strongest argument for
    containment that this project has, because it is arithmetic.
    """
    if tonnes_per_day <= 0.0:
        raise ValueError("tonnes_per_day must be positive")
    return tonnes / tonnes_per_day / 365.25


def proximity_score(distance_km: float, *, half_distance_km: float = 5.0) -> float:
    """Weight for a receptor at a given distance: 1 at zero, 0.5 at the half.

    A smooth ``1 / (1 + d/d_half)`` rather than a cliff, because a receptor at
    5.1 km is not categorically different from one at 4.9 km and a threshold
    would invite exactly that argument.
    """
    if half_distance_km <= 0.0:
        raise ValueError("half_distance_km must be positive")
    return 1.0 / (1.0 + max(0.0, float(distance_km)) / float(half_distance_km))


def priority_score(area: CandidateArea, *, half_distance_km: float = 5.0) -> float:
    """Sum of receptor weights discounted by distance.  Unitless, comparative."""
    return float(
        sum(
            RECEPTOR_WEIGHTS[receptor.kind]
            * proximity_score(receptor.distance_km, half_distance_km=half_distance_km)
            for receptor in area.receptors
        )
    )


def rank_candidates(
    candidates: Sequence[CandidateArea] = PILOT_CANDIDATES,
    *,
    half_distance_km: float = 5.0,
) -> list[dict[str, object]]:
    """Candidates ordered by receptor priority, with the mismatch flagged.

    The ``addressable`` column is deliberately separate from the score. An area
    can rank first on who it protects and still be the wrong job for this
    material, and collapsing the two into one number would hide exactly the
    finding that matters.
    """
    rows = [
        {
            "name": area.name,
            "sea": area.sea,
            "depth_m": area.depth_m,
            "area_km2": area.area_km2,
            "priority_score": priority_score(area, half_distance_km=half_distance_km),
            "nearest_receptor_km": (
                min(r.distance_km for r in area.receptors) if area.receptors else None
            ),
            "receptors": [f"{r.kind}@{r.distance_km:g}km" for r in area.receptors],
            "documented_contaminants": list(area.documented_contaminants),
            "addressable_by_this_material": area.addressable_by_this_material,
            "note": area.note,
            "source": area.source,
        }
        for area in candidates
    ]
    rows.sort(key=lambda row: row["priority_score"], reverse=True)
    return rows
