"""Fluxes at the two faces of the layer, and the attenuation derived from them.

``docs/MODEL_SPEC.md`` section 3.  Four quantities, and one rule about the
fourth:

``J_in``
    what enters the layer at the sediment face [kg m^-2 s^-1].
``J_out``
    what leaves into the overlying water [kg m^-2 s^-1].  This is the residual
    flux the coastal model receives.  Nothing is ever subtracted from a
    water-column cell.
``J_bare``
    ``(v + k_film) (C_sed - C_water)``: what the same hotspot would emit with no
    mat at all, under the same driving conditions.
``attenuation``
    ``1 - J_out / J_bare``.  **Never reported without J_bare**, never a fixed
    product specification, and always accompanied by an interval when one can
    be computed.

The honest decomposition
-----------------------

A mat with no remaining chemical capacity is still a physical barrier.  With
the demonstration parameters it still attenuates by about 94 %, purely by
diffusive and advective resistance, while a fresh mat attenuates by more than
99 %.  **The chemical contribution of the sorbent is the difference between
those two numbers, not the whole of the second one.**
:class:`FluxBudget` therefore carries ``barrier_attenuation`` and
``chemical_attenuation_contribution`` next to the headline value, so the claim
cannot be quoted without its floor.

Intervals
---------

``ensemble_flux_interval`` advances the *current* profile one step for every
member of the documented parameter ensemble and reports weighted percentiles.
It is a one-step spread conditional on the profile the nominal run produced, not
a full ensemble trajectory: a member with a different ``Kd`` would have built a
different profile.  That caveat travels with the result in ``notes``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from ..contracts import (
    Element,
    LayerStep,
    MaterialParameters,
    MatTileState,
    ProvenanceLabel,
    SeabedExchange,
)
from .column import build_column_parameters, solve_column_step, top_conductance
from .degradation import (
    DEFAULT_BURIAL_RESISTANCE_S_PER_M,
    buried_top_conductance,
)
from .material import ParameterEnsemble, sample_parameter_ensemble, sequence_of_elements

__all__ = [
    "FluxBudget",
    "FluxInterval",
    "bare_flux_kg_per_m2_per_s",
    "bare_flux_from_exchange",
    "attenuation",
    "flux_budget",
    "ensemble_flux_interval",
    "attenuation_interval",
]


def bare_flux_kg_per_m2_per_s(
    seepage_velocity_m_per_s: float,
    film_transfer_m_per_s: float,
    sediment_porewater_kg_per_m3: float,
    bottom_water_kg_per_m3: float,
) -> float:
    """``J_bare = (v + k_film) (C_sed - C_water)`` [kg m^-2 s^-1].

    The uncapped reference: the same hotspot, the same seepage, the same
    benthic boundary layer, no mat.  It is what "with mat" and "without mat"
    must share for the comparison to mean anything.
    """
    driving = float(sediment_porewater_kg_per_m3) - float(bottom_water_kg_per_m3)
    return (float(seepage_velocity_m_per_s) + float(film_transfer_m_per_s)) * driving


def bare_flux_from_exchange(
    exchange: SeabedExchange, element: Element | str
) -> tuple[float, str]:
    """``(J_bare, source)`` for one element.

    The declared ``SeabedExchange.bare_flux_kg_per_m2_per_s`` wins when it is
    present, because the hotspot owns that number; otherwise it is recomputed
    from the same driving conditions the layer sees, and the source string says
    so.  A caller must never silently see one and report the other.
    """
    key = element.value if isinstance(element, Element) else str(element)
    declared = exchange.bare_flux_kg_per_m2_per_s.get(key)
    if declared is not None:
        return float(declared), "declared_by_exchange"
    return (
        bare_flux_kg_per_m2_per_s(
            exchange.seepage_velocity_m_per_s,
            exchange.film_transfer_m_per_s,
            float(exchange.sediment_porewater_kg_per_m3.get(key, 0.0)),
            float(exchange.bottom_water_kg_per_m3.get(key, 0.0)),
        ),
        "recomputed_from_driving_conditions",
    )


def attenuation(
    flux_out_kg_per_m2_per_s: float, bare_flux_kg_per_m2_per_s_value: float
) -> float | None:
    """``1 - J_out / J_bare``, or ``None`` when there is no flux to attenuate.

    ``None`` rather than 0 or 1: with no bare flux the question has no answer,
    and a chart must show a gap, not a number.
    """
    bare = float(bare_flux_kg_per_m2_per_s_value)
    if not math.isfinite(bare) or bare <= 0.0:
        return None
    return 1.0 - float(flux_out_kg_per_m2_per_s) / bare


@dataclass(frozen=True, slots=True)
class FluxBudget:
    """The four flux quantities for one element, with the honest decomposition."""

    element: str
    flux_in_kg_per_m2_per_s: float
    flux_out_kg_per_m2_per_s: float
    bare_flux_kg_per_m2_per_s: float
    bare_flux_source: str
    attenuation: float | None
    barrier_flux_kg_per_m2_per_s: float
    barrier_attenuation: float | None
    chemical_attenuation_contribution: float | None
    provenance: str = ProvenanceLabel.SYNTHETIC_DEMO.value
    notes: str = (
        "attenuation = 1 - J_out / J_bare. A mat with no remaining capacity is "
        "still a physical barrier: the chemical contribution of the sorbent is "
        "chemical_attenuation_contribution, not the whole attenuation."
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "element": self.element,
            "flux_in_kg_per_m2_per_s": self.flux_in_kg_per_m2_per_s,
            "flux_out_kg_per_m2_per_s": self.flux_out_kg_per_m2_per_s,
            "bare_flux_kg_per_m2_per_s": self.bare_flux_kg_per_m2_per_s,
            "bare_flux_source": self.bare_flux_source,
            "attenuation": self.attenuation,
            "barrier_flux_kg_per_m2_per_s": self.barrier_flux_kg_per_m2_per_s,
            "barrier_attenuation": self.barrier_attenuation,
            "chemical_attenuation_contribution": (
                self.chemical_attenuation_contribution
            ),
            "provenance": self.provenance,
            "notes": self.notes,
        }


def flux_budget(
    layer_step: LayerStep,
    exchange: SeabedExchange,
    element: Element | str,
    *,
    barrier_flux_kg_per_m2_per_s: float | None = None,
) -> FluxBudget:
    """Assemble the four fluxes for one element from a completed layer step.

    ``barrier_flux_kg_per_m2_per_s`` is the residual flux the same layer would
    pass with no remaining chemical capacity.  ``advance_reactive_layer``
    records it in ``diagnostics['barrier_flux_kg_per_m2_per_s']``; passing it
    explicitly overrides that.
    """
    key = element.value if isinstance(element, Element) else str(element)
    bare, source = bare_flux_from_exchange(exchange, key)
    flux_out = float(layer_step.flux_out_kg_per_m2_per_s.get(key, 0.0))
    flux_in = float(layer_step.flux_in_kg_per_m2_per_s.get(key, 0.0))

    if barrier_flux_kg_per_m2_per_s is None:
        recorded = layer_step.diagnostics.get("barrier_flux_kg_per_m2_per_s", {})
        barrier = float(recorded.get(key, float("nan"))) if recorded else float("nan")
    else:
        barrier = float(barrier_flux_kg_per_m2_per_s)

    barrier_att = None if math.isnan(barrier) else attenuation(barrier, bare)
    total_att = attenuation(flux_out, bare)
    chemical = (
        None
        if (total_att is None or barrier_att is None)
        else total_att - barrier_att
    )
    return FluxBudget(
        element=key,
        flux_in_kg_per_m2_per_s=flux_in,
        flux_out_kg_per_m2_per_s=flux_out,
        bare_flux_kg_per_m2_per_s=bare,
        bare_flux_source=source,
        attenuation=total_att,
        barrier_flux_kg_per_m2_per_s=barrier,
        barrier_attenuation=barrier_att,
        chemical_attenuation_contribution=chemical,
    )


# ---------------------------------------------------------------------------
# Ensemble intervals
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FluxInterval:
    """One element's residual flux and attenuation, as intervals."""

    element: str
    flux_out_interval: tuple[float, float]
    attenuation_interval: tuple[float, float] | None
    bare_flux_kg_per_m2_per_s: float
    nominal_flux_out_kg_per_m2_per_s: float
    interval_level: float
    ensemble_size: int
    members_flux_out: tuple[float, ...] = ()
    provenance: str = ProvenanceLabel.ASSUMPTION.value
    notes: str = (
        "A one-step spread conditional on the current profile, across the "
        "documented parameter ranges. It is not a full ensemble trajectory: a "
        "member with a different Kd would have built a different profile."
    )
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "element": self.element,
            "flux_out_interval": list(self.flux_out_interval),
            "attenuation_interval": (
                None
                if self.attenuation_interval is None
                else list(self.attenuation_interval)
            ),
            "bare_flux_kg_per_m2_per_s": self.bare_flux_kg_per_m2_per_s,
            "nominal_flux_out_kg_per_m2_per_s": (
                self.nominal_flux_out_kg_per_m2_per_s
            ),
            "interval_level": self.interval_level,
            "ensemble_size": self.ensemble_size,
            "provenance": self.provenance,
            "notes": self.notes,
            "diagnostics": dict(self.diagnostics or {}),
        }


def _percentiles(
    values: Sequence[float], interval_level: float
) -> tuple[float, float]:
    lower_q = 100.0 * (1.0 - interval_level) / 2.0
    upper_q = 100.0 * (1.0 + interval_level) / 2.0
    array = np.asarray(values, dtype=float)
    return (
        float(np.percentile(array, lower_q)),
        float(np.percentile(array, upper_q)),
    )


def ensemble_flux_interval(
    tile_state: MatTileState,
    exchange: SeabedExchange,
    materials: Mapping[str, MaterialParameters],
    dt_s: float,
    *,
    ensemble: ParameterEnsemble | None = None,
    ensemble_size: int = 32,
    seed: int = 0,
    interval_level: float = 0.90,
    burial_resistance_s_per_m: float = DEFAULT_BURIAL_RESISTANCE_S_PER_M,
) -> dict[str, FluxInterval]:
    """Residual-flux and attenuation intervals, per element.

    One implicit column step per ensemble member, started from the tile's
    current profile.  Member 0 of the ensemble is the nominal parameter set, so
    the nominal value always lies inside the sampled set.
    """
    if not (0.0 < interval_level < 1.0):
        raise ValueError(f"interval_level must lie in (0, 1), got {interval_level!r}")
    if ensemble is None:
        ensemble = sample_parameter_ensemble(
            materials, ensemble_size, seed, geometry=tile_state.geometry
        )

    result: dict[str, FluxInterval] = {}
    for key in sequence_of_elements(materials):
        bare, _ = bare_flux_from_exchange(exchange, key)
        member_fluxes: list[float] = []
        for member in ensemble.members:
            params = member.get(key, materials[key])
            column = build_column_parameters(
                tile_state.geometry,
                params,
                n_nodes=tile_state.n_nodes,
                seepage_velocity_m_per_s=exchange.seepage_velocity_m_per_s,
                film_transfer_m_per_s=exchange.film_transfer_m_per_s,
                fouling_index=tile_state.fouling_index,
            )
            g_top = buried_top_conductance(
                top_conductance(column),
                tile_state.burial_depth_m,
                burial_resistance_s_per_m,
            )
            step = solve_column_step(
                np.asarray(tile_state.porewater_kg_per_m3[key], dtype=float),
                np.asarray(tile_state.sorbed_kg_per_kg[key], dtype=float),
                column,
                dt_s,
                float(exchange.sediment_porewater_kg_per_m3.get(key, 0.0)),
                float(exchange.bottom_water_kg_per_m3.get(key, 0.0)),
                top_conductance_m_per_s=g_top,
            )
            member_fluxes.append(step.flux_out_kg_per_m2_per_s)

        flux_interval = _percentiles(member_fluxes, interval_level)
        if bare > 0.0:
            attenuation_range = (
                1.0 - flux_interval[1] / bare,
                1.0 - flux_interval[0] / bare,
            )
        else:
            attenuation_range = None
        result[key] = FluxInterval(
            element=key,
            flux_out_interval=flux_interval,
            attenuation_interval=attenuation_range,
            bare_flux_kg_per_m2_per_s=bare,
            nominal_flux_out_kg_per_m2_per_s=float(member_fluxes[0]),
            interval_level=float(interval_level),
            ensemble_size=ensemble.size,
            members_flux_out=tuple(float(value) for value in member_fluxes),
            diagnostics={
                "ensemble_seed": ensemble.seed,
                "ensemble_distribution": ensemble.distribution,
                "dt_s": float(dt_s),
                "fouling_index": float(tile_state.fouling_index),
                "burial_depth_m": float(tile_state.burial_depth_m),
            },
        )
    return result


def attenuation_interval(
    tile_state: MatTileState,
    exchange: SeabedExchange,
    materials: Mapping[str, MaterialParameters],
    dt_s: float,
    **kwargs: Any,
) -> dict[str, tuple[float, float] | None]:
    """Just the attenuation intervals, per element, or ``None`` per element."""
    intervals = ensemble_flux_interval(
        tile_state, exchange, materials, dt_s, **kwargs
    )
    return {key: value.attenuation_interval for key, value in intervals.items()}
