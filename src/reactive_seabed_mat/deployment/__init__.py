"""How much seabed there is to cover, and what that would take.

Separate from the physics on purpose. The 1-D layer and the 2-D plume answer
"does a square metre of mat work". This package answers "how many square metres
are there", and the two answers point in opposite directions.

Nothing here locates a deployment. The dumpsite geometries are published,
officially designated areas cited to establish **scale**; the demonstrator's own
hotspot stays an abstract authorised contaminant hotspot, and no part of this
repository simulates, locates or recommends handling munitions.
"""

from __future__ import annotations

from .scale import (  # noqa: F401
    BALTIC_DUMPSITES,
    DumpSite,
    MaterialDemand,
    coverable_area_m2,
    material_demand,
    scale_table,
)
from .priority import (  # noqa: F401
    CONTAMINANT_MISMATCH_WARNING,
    GERMAN_PROGRAMME,
    PILOT_CANDIDATES,
    PRIORITY_NOTE,
    RECEPTOR_WEIGHTS,
    CandidateArea,
    Receptor,
    priority_score,
    proximity_score,
    rank_candidates,
    recovery_years,
)

__all__ = [
    "BALTIC_DUMPSITES",
    "DumpSite",
    "MaterialDemand",
    "coverable_area_m2",
    "material_demand",
    "scale_table",
    "CONTAMINANT_MISMATCH_WARNING",
    "GERMAN_PROGRAMME",
    "PILOT_CANDIDATES",
    "PRIORITY_NOTE",
    "RECEPTOR_WEIGHTS",
    "CandidateArea",
    "Receptor",
    "priority_score",
    "proximity_score",
    "rank_candidates",
    "recovery_years",
]
