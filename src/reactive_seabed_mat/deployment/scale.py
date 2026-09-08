"""The area that would have to be covered, and what covering it would cost.

This module exists because the encouraging part of this project is measured in
square metres and the discouraging part is measured in square kilometres, and a
demonstrator that shows only the first is not honest.

The dumpsite geometries below are **officially designated areas**, published by
HELCOM and shown on the EMODnet Human Activities dumped-munitions map [B1, B2,
B3]. They are quoted to establish scale. They are not deployment proposals, this
project asserts no hotspot at any of them, and nothing here simulates, locates
or recommends handling munitions: real work near historical marine munitions
requires specialist and environmental approval.

The conclusion the arithmetic forces
------------------------------------

Covering the Bornholm primary dumpsite alone would need roughly 390,000 tonnes
of keratin, about a fifth of one year's global greasy-wool clip [B4], and would
cost tens of billions of euro in mat material at the assumed unit price. **Area
capping of a munitions dumpsite is not a plan.** What the numbers do support is
targeted covering of small, identified, high-flux patches, and the honest job of
this demonstrator is to say which patches would be worth it and how one would
know. That is a different and much smaller claim than "clean up the Baltic".

References
----------
B1  HELCOM, *Chemical Munitions Dumped in the Baltic Sea*, and the 2025
    Thematic Assessment on Hazardous Submerged Objects (Warfare Materials).
    About 40,000 t of chemical munitions containing about 15,000 t of warfare
    agents; more than 100,000 t of ammunition in total, mostly conventional.
B2  EMODnet Human Activities, dumped-munitions map,
    https://emodnet.ec.europa.eu/en/map-week-dumped-munitions-0
B3  Bornholm Basin primary dumpsite: a circle of radius 3 nautical miles, with
    a rectangular extended area around it; the extended area is close to
    1000 km2.  About 32,000 t of chemical weapons containing about 11,000 t of
    agents were dumped there in 1947.
B4  FAO: world greasy wool production about 1.76 Mt in 2022 and about 1.98 Mt
    in 2023.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

__all__ = [
    "NAUTICAL_MILE_M",
    "GLOBAL_GREASY_WOOL_TONNES_PER_YEAR",
    "DumpSite",
    "BALTIC_DUMPSITES",
    "MaterialDemand",
    "material_demand",
    "coverable_area_m2",
    "scale_table",
    "SCALE_NOTE",
]

NAUTICAL_MILE_M = 1852.0

#: FAO, 2022 [B4].  The 2023 figure is about 1.98 Mt; the smaller, older number
#: is used so the "fraction of the world clip" statements are the *larger*, less
#: flattering ones.
GLOBAL_GREASY_WOOL_TONNES_PER_YEAR = 1.76e6

SCALE_NOTE = (
    "Officially designated dumpsite areas, quoted to establish scale. Not "
    "deployment proposals and not an assertion that any of them is a hotspot "
    "for this technology. Nothing here simulates, locates or recommends "
    "handling munitions."
)


@dataclass(frozen=True, slots=True)
class DumpSite:
    """A published, officially designated area.  Coordinates are approximate."""

    name: str
    sea: str
    area_km2: float
    #: Approximate centre, WGS84, for context maps only.
    latitude_deg: float
    longitude_deg: float
    typical_depth_m: float
    munitions_tonnes: float | None
    note: str
    source: str

    @property
    def area_m2(self) -> float:
        return self.area_km2 * 1.0e6


def _circle_km2(radius_nautical_miles: float) -> float:
    radius_m = radius_nautical_miles * NAUTICAL_MILE_M
    return math.pi * radius_m**2 / 1.0e6


#: The three Baltic and one Skagerrak areas the sources name explicitly, plus
#: the extended Bornholm area.  Areas are as published where a figure exists and
#: derived from the published geometry where only that is given.
BALTIC_DUMPSITES: tuple[DumpSite, ...] = (
    DumpSite(
        name="Bornholm Basin, primary dumpsite",
        sea="Baltic Sea",
        area_km2=_circle_km2(3.0),
        latitude_deg=55.33,
        longitude_deg=15.55,
        typical_depth_m=90.0,
        munitions_tonnes=32000.0,
        note=(
            "A circle of radius 3 nautical miles. About 32,000 t of chemical "
            "weapons containing about 11,000 t of agents, dumped in 1947."
        ),
        source="B3",
    ),
    DumpSite(
        name="Bornholm Basin, extended area",
        sea="Baltic Sea",
        area_km2=1000.0,
        latitude_deg=55.33,
        longitude_deg=15.55,
        typical_depth_m=90.0,
        munitions_tonnes=None,
        note="The rectangular secondary area around the primary circle.",
        source="B3",
    ),
    DumpSite(
        name="Gotland Deep dumping area",
        sea="Baltic Sea",
        area_km2=1500.0,
        latitude_deg=57.30,
        longitude_deg=19.80,
        typical_depth_m=120.0,
        munitions_tonnes=2000.0,
        note=(
            "South-east of Gotland, one of the deep basins chosen for dumping. "
            "The area is an order-of-magnitude figure from the published extent, "
            "not an officially published polygon area."
        ),
        source="B1",
    ),
    DumpSite(
        name="Skagerrak dumping areas",
        sea="Skagerrak",
        area_km2=1300.0,
        latitude_deg=58.30,
        longitude_deg=10.30,
        typical_depth_m=400.0,
        munitions_tonnes=168000.0,
        note=(
            "Scuttled vessels loaded with munitions, in water far deeper than "
            "any capping technology has been deployed in."
        ),
        source="B1",
    ),
)


@dataclass(frozen=True, slots=True)
class MaterialDemand:
    """What covering one area would take.  Every euro figure is an assumption."""

    area_m2: float
    sorbent_tonnes: float
    mat_material_eur: float
    fraction_of_world_wool_clip: float
    vessel_days: float

    @property
    def area_km2(self) -> float:
        return self.area_m2 / 1.0e6


def material_demand(
    area_m2: float,
    *,
    sorbent_loading_kg_per_m2: float,
    mat_material_eur_per_m2: float,
    m2_per_vessel_day: float = 20000.0,
) -> MaterialDemand:
    """Sorbent mass, material cost and vessel days for a given area.

    ``m2_per_vessel_day`` is an **assumption**: two hectares a day is a
    deliberately optimistic laying rate for precision placement at 90 m depth,
    chosen so the vessel-day figure understates rather than overstates the
    difficulty. No contractor has been asked.
    """
    if area_m2 < 0.0 or not math.isfinite(area_m2):
        raise ValueError(f"area must be finite and non-negative, got {area_m2!r}")
    if m2_per_vessel_day <= 0.0:
        raise ValueError("m2_per_vessel_day must be positive")
    sorbent_kg = area_m2 * float(sorbent_loading_kg_per_m2)
    tonnes = sorbent_kg / 1000.0
    return MaterialDemand(
        area_m2=float(area_m2),
        sorbent_tonnes=tonnes,
        mat_material_eur=area_m2 * float(mat_material_eur_per_m2),
        fraction_of_world_wool_clip=tonnes / GLOBAL_GREASY_WOOL_TONNES_PER_YEAR,
        vessel_days=area_m2 / float(m2_per_vessel_day),
    )


def coverable_area_m2(budget_eur: float, *, mat_material_eur_per_m2: float) -> float:
    """The area a material budget buys.  Material only: no vessel, no survey."""
    if mat_material_eur_per_m2 <= 0.0:
        raise ValueError("mat_material_eur_per_m2 must be positive")
    return max(0.0, float(budget_eur)) / float(mat_material_eur_per_m2)


def scale_table(
    *,
    sorbent_loading_kg_per_m2: float,
    mat_material_eur_per_m2: float,
    demo_hotspot_area_m2: float,
    sites: Sequence[DumpSite] = BALTIC_DUMPSITES,
) -> list[dict[str, object]]:
    """One row per site, plus the demonstrator's own hotspot for comparison."""
    rows: list[dict[str, object]] = []
    demo = material_demand(
        demo_hotspot_area_m2,
        sorbent_loading_kg_per_m2=sorbent_loading_kg_per_m2,
        mat_material_eur_per_m2=mat_material_eur_per_m2,
    )
    rows.append(
        {
            "name": "This demonstrator's hypothetical hotspot",
            "sea": "synthetic",
            "area_km2": demo.area_km2,
            "sorbent_tonnes": demo.sorbent_tonnes,
            "mat_material_eur": demo.mat_material_eur,
            "fraction_of_world_wool_clip": demo.fraction_of_world_wool_clip,
            "vessel_days": demo.vessel_days,
            "times_larger_than_demo": 1.0,
            "note": "Abstract, not a located site.",
            "source": "synthetic_demo",
        }
    )
    for site in sites:
        demand = material_demand(
            site.area_m2,
            sorbent_loading_kg_per_m2=sorbent_loading_kg_per_m2,
            mat_material_eur_per_m2=mat_material_eur_per_m2,
        )
        rows.append(
            {
                "name": site.name,
                "sea": site.sea,
                "area_km2": site.area_km2,
                "sorbent_tonnes": demand.sorbent_tonnes,
                "mat_material_eur": demand.mat_material_eur,
                "fraction_of_world_wool_clip": demand.fraction_of_world_wool_clip,
                "vessel_days": demand.vessel_days,
                "times_larger_than_demo": (
                    site.area_m2 / demo_hotspot_area_m2
                    if demo_hotspot_area_m2 > 0
                    else math.inf
                ),
                "note": site.note,
                "source": site.source,
            }
        )
    return rows
