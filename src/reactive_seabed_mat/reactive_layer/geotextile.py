"""The two permeable geotextile layers that encapsulate the reactive core.

The mat is a **geotextile / reactive core / geotextile** sandwich: the keratin
medium is held between two non-woven carrier geotextiles rather than lying loose
on the seabed. That construction is not ours and no novelty is claimed for it.
It is the established form of a reactive capping mat, sold commercially and
covered by patents; see ``docs/PRIOR_ART.md``.

What the geotextiles do to the physics, and what they do not
------------------------------------------------------------

**They do not resist flow.** A non-woven geotextile has a hydraulic
conductivity around 1.5e-3 m/s [G1], five orders of magnitude above the
seepage velocities this model uses (about 3e-8 m/s). Advection passes through
essentially unimpeded, and modelling them as a flow restriction would be wrong.

**They do add diffusive path.** Two layers of a few millimetres, at porosity
above 0.5 [G2], sit in series with the reactive core. Each contributes a
resistance ``L / (theta_g^1.5 * D_molecular)`` in s/m, using the Millington and
Quirk tortuosity ``theta^1.5``. That resistance is added to the boundary
conductances at both faces, exactly as burial already adds one at the top.

**They do not sorb.** They are treated as chemically inert. A real carrier
geotextile is polypropylene or polyester and has negligible capacity for these
metals compared with the core, so crediting it with any would be inventing
capacity.

Whether the series-resistance treatment is legitimate here is a question with a
number attached. The Peclet number across one geotextile layer is

    Pe = v L / D_eff ~ 3e-8 * 0.003 / 3.5e-10 ~ 0.26

so transport inside the geotextile is diffusion-dominated and a lumped
diffusive resistance is a reasonable approximation. It would not be at a
seepage ten times faster, and :func:`geotextile_peclet` exists so a caller can
check rather than assume.

References
----------
G1  Non-woven geotextile permittivity 0.08 to 0.40 1/s and hydraulic
    conductivity about 0.15 cm/s; ASTM D4491 permittivity range 0.02 to 2.2 1/s.
G2  Non-woven needle-punched geotextiles have porosity above 0.5 even when
    compressed; typical mass per unit area 200 to 800 g/m2, thickness a few mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "GEOTEXTILE_NOTE",
    "GeotextileLayer",
    "DEFAULT_GEOTEXTILE",
    "geotextile_resistance_s_per_m",
    "geotextile_peclet",
    "in_series",
    "encapsulated_conductances",
]

GEOTEXTILE_NOTE = (
    "The carrier geotextiles are modelled as inert diffusive resistances in "
    "series with the reactive core. They are not credited with any sorption "
    "capacity, and they do not restrict advection: their hydraulic "
    "conductivity is about five orders of magnitude above the seepage velocity."
)

#: Free-solution diffusion coefficient used for the geotextile pore fluid
#: [m^2 s^-1].  A divalent trace metal in seawater at 10 degrees C sits near
#: 5e-10; 7.0e-10 is the room-temperature end and is the *optimistic* choice,
#: so the geotextile resistance computed from it is the *smaller* one.
DEFAULT_MOLECULAR_DIFFUSIVITY_M2_PER_S = 7.0e-10


@dataclass(frozen=True, slots=True)
class GeotextileLayer:
    """One carrier geotextile.  Every value is an ``assumption`` [G1, G2]."""

    thickness_m: float = 0.003
    porosity: float = 0.55
    molecular_diffusivity_m2_per_s: float = DEFAULT_MOLECULAR_DIFFUSIVITY_M2_PER_S
    #: Saturated hydraulic conductivity [m/s].  Carried so that
    #: :func:`advection_is_unimpeded` can check the claim rather than assert it.
    hydraulic_conductivity_m_per_s: float = 1.5e-3

    def __post_init__(self) -> None:
        if self.thickness_m < 0.0 or not math.isfinite(self.thickness_m):
            raise ValueError(
                f"geotextile thickness must be finite and non-negative, "
                f"got {self.thickness_m!r}"
            )
        if not 0.0 < self.porosity <= 1.0:
            raise ValueError(
                f"geotextile porosity must be in (0, 1], got {self.porosity!r}"
            )
        if self.molecular_diffusivity_m2_per_s <= 0.0:
            raise ValueError(
                "geotextile molecular diffusivity must be positive, got "
                f"{self.molecular_diffusivity_m2_per_s!r}"
            )

    @property
    def effective_diffusivity_m2_per_s(self) -> float:
        """``D_eff = theta^1.5 D`` (Millington and Quirk tortuosity)."""
        return self.porosity**1.5 * self.molecular_diffusivity_m2_per_s

    @property
    def resistance_s_per_m(self) -> float:
        """``R = L / (theta D_eff)`` [s/m].  Zero thickness gives zero."""
        if self.thickness_m == 0.0:
            return 0.0
        return self.thickness_m / (self.porosity * self.effective_diffusivity_m2_per_s)


DEFAULT_GEOTEXTILE = GeotextileLayer()


def geotextile_resistance_s_per_m(layer: GeotextileLayer | None) -> float:
    """Diffusive resistance of one layer, or zero when there is none."""
    return 0.0 if layer is None else layer.resistance_s_per_m


def geotextile_peclet(
    layer: GeotextileLayer, seepage_velocity_m_per_s: float
) -> float:
    """``Pe = v L / D_eff`` across one geotextile layer.

    Below about 1 the lumped diffusive resistance in this module is a fair
    approximation. Well above it, the geotextile would need its own advective
    nodes and this treatment should not be used.
    """
    d_eff = layer.effective_diffusivity_m2_per_s
    if d_eff <= 0.0:
        return math.inf
    return abs(float(seepage_velocity_m_per_s)) * layer.thickness_m / d_eff


def advection_is_unimpeded(
    layer: GeotextileLayer, seepage_velocity_m_per_s: float, *, margin: float = 100.0
) -> bool:
    """Is the geotextile's conductivity far enough above the seepage to ignore?

    ``margin`` is how many times larger it must be. The design guidance for
    filtration geotextiles asks for a factor of ten against the soil; a hundred
    is used here because the claim being made is stronger, namely that the
    geotextile can be left out of the flow problem entirely.
    """
    return layer.hydraulic_conductivity_m_per_s >= margin * abs(
        float(seepage_velocity_m_per_s)
    )


def in_series(conductance_m_per_s: float, extra_resistance_s_per_m: float) -> float:
    """Add a resistance in series with a conductance.

    ``1 / (1/g + R)``. An infinite resistance gives zero conductance, and a zero
    conductance stays zero, so the caller never has to special-case a sealed
    face.
    """
    if conductance_m_per_s <= 0.0:
        return 0.0
    if extra_resistance_s_per_m <= 0.0:
        return float(conductance_m_per_s)
    if not math.isfinite(extra_resistance_s_per_m):
        return 0.0
    return 1.0 / (1.0 / float(conductance_m_per_s) + float(extra_resistance_s_per_m))


def encapsulated_conductances(
    *,
    clean_bottom_conductance_m_per_s: float,
    clean_top_conductance_m_per_s: float,
    bottom_layer: GeotextileLayer | None = DEFAULT_GEOTEXTILE,
    top_layer: GeotextileLayer | None = DEFAULT_GEOTEXTILE,
) -> tuple[float, float]:
    """Both face conductances with their carrier geotextiles in series.

    Returns ``(bottom, top)`` in m/s. Passing ``None`` for either layer models
    an unencapsulated core, which is what the earlier version of this model
    assumed, and keeps that case available for comparison rather than deleting
    it.
    """
    return (
        in_series(
            clean_bottom_conductance_m_per_s,
            geotextile_resistance_s_per_m(bottom_layer),
        ),
        in_series(
            clean_top_conductance_m_per_s, geotextile_resistance_s_per_m(top_layer)
        ),
    )
