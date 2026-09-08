"""Conditional breakthrough forecasting for a loaded reactive layer.

What changed from the panel model this file replaces: the target is no longer
"when does this panel reach 80 % of its loading?" but **when does the layer
break through?**, that is, when is its allocated capacity consumed so that the
sorption front reaches the water face and the residual flux climbs toward the
bare-barrier value.

Two estimates, and neither is a measurement
-------------------------------------------

``supply limited``
    ``t = remaining_capacity_per_m2 / J_in``.  The layer cannot load faster than
    metal is delivered to it, so this is the estimate that matters for a cap
    driven by a seepage flux.  It is the headline number.
``kinetics limited``
    ``t = -(1/k_eff) ln((q_target - q_eq)/(q0 - q_eq))``, the closed form of
    ``dq/dt = k_eff (q_eq - q)`` at a held concentration.  It is a *lower*
    bound: it ignores the fact that the metal has to arrive.  Reported in the
    diagnostics, never folded into the headline.

**The result is an interval or ``None``, never a bare number.**  A falsely
precise remaining-life figure is worse than an honest "not determined", and the
type signature enforces that rather than a convention: every public function
here returns ``tuple[float, float] | None`` or a mapping of them.

``None`` means "not reached under this assumption": either no member of the
parameter ensemble consumes its capacity under the assumed supply, or there is
no supply at all.  When only *some* members reach it, the interval covers the
members that do and ``never_reached_fraction`` reports the share that do not.
An interval on its own would hide that.

Breakthrough is defined here as consumption of a stated share of the allocated
capacity, which is a proxy for the flux definition used by the numerical probe
(``J_out / J_bare`` crossing 5 %).  The two agree to within the width of the
sorption front; the note travels with the result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

import numpy as np

from ..contracts import MaterialParameters, MatTileState, ProvenanceLabel
from .material import (
    ParameterEnsemble,
    equilibrium_loading,
    fouling_factors,
    sample_parameter_ensemble,
    sequence_of_elements,
)

__all__ = [
    "CONDITIONAL_NOTE",
    "DEFAULT_BREAKTHROUGH_FRACTION",
    "LayerForecast",
    "sorbed_kg_per_m2",
    "loading_kg_per_kg",
    "loading_fraction",
    "remaining_capacity_kg_per_m2",
    "time_to_target_loading",
    "supply_limited_breakthrough_s",
    "forecast_breakthrough",
    "forecast_tile",
    "breakthrough_interval",
]

CONDITIONAL_NOTE = (
    "Conditional forecast: it assumes the stated supply flux, fouling state and "
    "driving concentration persist. It is not a measurement and not a warranty; "
    "a change of source strength, of the seepage velocity or of the mat's "
    "physical condition invalidates it."
)

#: Share of the allocated capacity whose consumption counts as breakthrough.
#: ASSUMPTION, matching ``PolicyConfig.replacement_saturation_threshold``.
DEFAULT_BREAKTHROUGH_FRACTION = 0.80


# ---------------------------------------------------------------------------
# Point quantities, all per unit seabed area
# ---------------------------------------------------------------------------

def sorbed_kg_per_m2(tile_state: MatTileState, element: str) -> float:
    """Sorbed inventory per unit seabed area [kg m^-2], porewater excluded.

    ``MatTileState.retained_kg_per_m2`` includes the dissolved pool; a capacity
    question is about the sorbed pool alone, so it is computed here.
    """
    if element not in tile_state.sorbed_kg_per_kg:
        return 0.0
    sorbed = np.asarray(tile_state.sorbed_kg_per_kg[element], dtype=float)
    return float(
        np.sum(tile_state.geometry.bulk_density_kg_per_m3 * sorbed)
        * tile_state.dz_m()
    )


def loading_kg_per_kg(
    sorbed_kg_per_m2_value: float,
    sorbent_loading_kg_per_m2: float,
    params: MaterialParameters,
) -> float:
    """``q`` per kilogram of **allocated** medium [kg/kg]; 0 when none is."""
    allocated = float(sorbent_loading_kg_per_m2) * float(params.allocation_fraction)
    if allocated <= 0.0:
        return 0.0
    return float(sorbed_kg_per_m2_value) / allocated


def loading_fraction(
    sorbed_kg_per_m2_value: float,
    sorbent_loading_kg_per_m2: float,
    params: MaterialParameters,
    fouling_index: float = 0.0,
    *,
    use_fouling: bool = True,
) -> float:
    """Loading as a fraction of capacity, in ``[0, inf)``.

    With ``use_fouling`` (the default) the denominator is the *accessible*
    capacity ``q_max_eff``, which is what a maintenance decision cares about.
    A fouled layer can therefore report a fraction above 1: it holds more than
    its currently accessible capacity, which is exactly the state in which
    further uptake stops.  That is reported, not clipped.
    """
    factors = fouling_factors(params, fouling_index if use_fouling else 0.0)
    q_max_eff = params.q_max_kg_per_kg * factors.capacity_factor
    loading = loading_kg_per_kg(
        sorbed_kg_per_m2_value, sorbent_loading_kg_per_m2, params
    )
    if q_max_eff <= 0.0:
        return 1.0 if loading > 0.0 else 0.0
    return loading / q_max_eff


def remaining_capacity_kg_per_m2(
    sorbed_kg_per_m2_value: float,
    sorbent_loading_kg_per_m2: float,
    params: MaterialParameters,
    fouling_index: float = 0.0,
) -> float:
    """``max(0, rho_b L alpha q_max_eff - sorbed)`` [kg m^-2]."""
    factors = fouling_factors(params, fouling_index)
    allocated = float(sorbent_loading_kg_per_m2) * float(params.allocation_fraction)
    q_max_eff = params.q_max_kg_per_kg * factors.capacity_factor
    return max(0.0, allocated * q_max_eff - float(sorbed_kg_per_m2_value))


def time_to_target_loading(
    q0_kg_per_kg: float,
    q_eq_kg_per_kg: float,
    k_eff_per_s: float,
    q_target_kg_per_kg: float,
) -> float | None:
    """Seconds for ``q`` to rise from ``q0`` to ``q_target``, or ``None``.

    The kinetics-limited bound.  ``None`` means "not reached under this
    assumption": either the equilibrium loading sits at or below the target, or
    the rate is zero.  Returns ``0.0`` when the target has already been reached.
    """
    q0 = float(q0_kg_per_kg)
    q_eq = float(q_eq_kg_per_kg)
    q_target = float(q_target_kg_per_kg)
    k_eff = float(k_eff_per_s)

    if q0 >= q_target:
        return 0.0
    if k_eff <= 0.0:
        return None
    if q_eq <= q_target:
        return None
    ratio = (q_target - q_eq) / (q0 - q_eq)
    if not (0.0 < ratio <= 1.0):
        # q0 < q_target < q_eq guarantees 0 < ratio < 1; anything else is a
        # numerical edge, reported as "not reached" rather than guessed at.
        return None
    return -math.log(ratio) / k_eff


def supply_limited_breakthrough_s(
    params: MaterialParameters,
    sorbed_kg_per_m2_value: float,
    sorbent_loading_kg_per_m2: float,
    fouling_index: float,
    supply_flux_kg_per_m2_per_s: float,
    breakthrough_fraction: float = DEFAULT_BREAKTHROUGH_FRACTION,
) -> float | None:
    """Seconds until ``breakthrough_fraction`` of the capacity is consumed.

    ``None`` when nothing is being delivered: with no supply the capacity is
    never consumed, and saying "never under this assumption" is the honest
    answer.  ``0.0`` when the target share is already consumed.
    """
    if not (0.0 < breakthrough_fraction <= 1.0):
        raise ValueError(
            f"breakthrough_fraction must lie in (0, 1], got "
            f"{breakthrough_fraction!r}"
        )
    factors = fouling_factors(params, fouling_index)
    allocated = float(sorbent_loading_kg_per_m2) * float(params.allocation_fraction)
    capacity = allocated * params.q_max_kg_per_kg * factors.capacity_factor
    if capacity <= 0.0:
        # No capacity at all: the layer is a physical barrier only. There is no
        # chemical service life left to run down, so breakthrough is now, not
        # "never": returning None here would read as reassurance.
        return 0.0
    target = breakthrough_fraction * capacity
    deficit = target - float(sorbed_kg_per_m2_value)
    if deficit <= 0.0:
        return 0.0
    supply = float(supply_flux_kg_per_m2_per_s)
    if not math.isfinite(supply) or supply <= 0.0:
        return None
    return deficit / supply


# ---------------------------------------------------------------------------
# Ensemble interval
# ---------------------------------------------------------------------------

def _percentiles(values: Sequence[float], interval_level: float) -> tuple[float, float]:
    lower_q = 100.0 * (1.0 - interval_level) / 2.0
    upper_q = 100.0 * (1.0 + interval_level) / 2.0
    array = np.asarray(values, dtype=float)
    return (
        float(np.percentile(array, lower_q)),
        float(np.percentile(array, upper_q)),
    )


@dataclass(frozen=True, slots=True)
class LayerForecast:
    """Everything the maintenance policy needs from the layer's chemistry.

    It carries no hidden event label and no truth-store reference: it is
    computed from a sorbed-mass estimate, the declared material priors and an
    assumed supply flux, all of which the estimation branch already has.
    """

    time_utc: datetime | None
    tile_id: str | None
    elements: tuple[str, ...]
    sorbed_kg_per_m2: Mapping[str, float]
    loading_fraction: Mapping[str, float]
    loading_fraction_interval: Mapping[str, tuple[float, float]]
    remaining_capacity_kg_per_m2: Mapping[str, float]
    remaining_capacity_interval: Mapping[str, tuple[float, float]]
    breakthrough_s_interval: Mapping[str, tuple[float, float] | None]
    never_reached_fraction: Mapping[str, float]
    assumed_supply_flux_kg_per_m2_per_s: Mapping[str, float]
    breakthrough_fraction: float
    interval_level: float
    ensemble_size: int
    conditional_note: str = CONDITIONAL_NOTE
    provenance: str = ProvenanceLabel.ASSUMPTION.value
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready view (SI units; timestamps as ISO-8601 UTC strings)."""
        from ..units import format_utc

        return {
            "time_utc": None if self.time_utc is None else format_utc(self.time_utc),
            "tile_id": self.tile_id,
            "elements": list(self.elements),
            "sorbed_kg_per_m2": dict(self.sorbed_kg_per_m2),
            "loading_fraction": dict(self.loading_fraction),
            "loading_fraction_interval": {
                key: list(value)
                for key, value in self.loading_fraction_interval.items()
            },
            "remaining_capacity_kg_per_m2": dict(self.remaining_capacity_kg_per_m2),
            "remaining_capacity_interval": {
                key: list(value)
                for key, value in self.remaining_capacity_interval.items()
            },
            "breakthrough_s_interval": {
                key: (None if value is None else list(value))
                for key, value in self.breakthrough_s_interval.items()
            },
            "never_reached_fraction": dict(self.never_reached_fraction),
            "assumed_supply_flux_kg_per_m2_per_s": dict(
                self.assumed_supply_flux_kg_per_m2_per_s
            ),
            "breakthrough_fraction": self.breakthrough_fraction,
            "interval_level": self.interval_level,
            "ensemble_size": self.ensemble_size,
            "conditional_note": self.conditional_note,
            "provenance": self.provenance,
            "diagnostics": dict(self.diagnostics or {}),
        }


def forecast_breakthrough(
    materials: Mapping[str, MaterialParameters],
    sorbed_kg_per_m2_by_element: Mapping[str, float],
    sorbent_loading_kg_per_m2: float,
    fouling_index: float,
    supply_flux_kg_per_m2_per_s: Mapping[str, float],
    *,
    breakthrough_fraction: float = DEFAULT_BREAKTHROUGH_FRACTION,
    driving_concentration_kg_per_m3: Mapping[str, float] | None = None,
    ensemble: ParameterEnsemble | None = None,
    ensemble_size: int = 64,
    seed: int = 0,
    interval_level: float = 0.90,
    time_utc: datetime | None = None,
    tile_id: str | None = None,
) -> LayerForecast:
    """Forecast from a sorbed-mass estimate, without touching a tile object.

    This is the entry point the estimation branch should call: it takes an
    *estimated* sorbed mass per unit area rather than a simulator
    :class:`MatTileState`, so no path leads from the hidden truth store into a
    recommendation.
    """
    if not (0.0 < interval_level < 1.0):
        raise ValueError(f"interval_level must lie in (0, 1), got {interval_level!r}")
    if ensemble is None:
        ensemble = sample_parameter_ensemble(materials, ensemble_size, seed)
    elements = tuple(sequence_of_elements(materials))

    point_fraction: dict[str, float] = {}
    fraction_interval: dict[str, tuple[float, float]] = {}
    point_capacity: dict[str, float] = {}
    capacity_interval: dict[str, tuple[float, float]] = {}
    breakthrough: dict[str, tuple[float, float] | None] = {}
    never_reached: dict[str, float] = {}
    kinetic_bound: dict[str, tuple[float, float] | None] = {}

    for key in elements:
        params = materials[key]
        sorbed = float(sorbed_kg_per_m2_by_element.get(key, 0.0))
        supply = float(supply_flux_kg_per_m2_per_s.get(key, 0.0))
        concentration = float(
            (driving_concentration_kg_per_m3 or {}).get(key, 0.0)
        )

        point_fraction[key] = loading_fraction(
            sorbed, sorbent_loading_kg_per_m2, params, fouling_index
        )
        point_capacity[key] = remaining_capacity_kg_per_m2(
            sorbed, sorbent_loading_kg_per_m2, params, fouling_index
        )

        member_fractions: list[float] = []
        member_capacities: list[float] = []
        member_times: list[float] = []
        member_kinetic: list[float] = []
        never = 0
        for member in ensemble.members:
            member_params = member.get(key, params)
            member_fractions.append(
                loading_fraction(
                    sorbed, sorbent_loading_kg_per_m2, member_params, fouling_index
                )
            )
            member_capacities.append(
                remaining_capacity_kg_per_m2(
                    sorbed, sorbent_loading_kg_per_m2, member_params, fouling_index
                )
            )
            time_s = supply_limited_breakthrough_s(
                member_params,
                sorbed,
                sorbent_loading_kg_per_m2,
                fouling_index,
                supply,
                breakthrough_fraction,
            )
            if time_s is None:
                never += 1
            else:
                member_times.append(time_s)

            if driving_concentration_kg_per_m3 is not None:
                factors = fouling_factors(member_params, fouling_index)
                q_max_eff = member_params.q_max_kg_per_kg * factors.capacity_factor
                k_eff = member_params.k_rate_per_s * factors.kinetics_factor
                q0 = loading_kg_per_kg(
                    sorbed, sorbent_loading_kg_per_m2, member_params
                )
                q_eq = equilibrium_loading(
                    member_params.kd_m3_per_kg, concentration, q_max_eff
                )
                kinetic = time_to_target_loading(
                    q0, q_eq, k_eff, breakthrough_fraction * q_max_eff
                )
                if kinetic is not None:
                    member_kinetic.append(kinetic)

        fraction_interval[key] = _percentiles(member_fractions, interval_level)
        capacity_interval[key] = _percentiles(member_capacities, interval_level)
        never_reached[key] = never / max(1, ensemble.size)
        breakthrough[key] = (
            _percentiles(member_times, interval_level) if member_times else None
        )
        kinetic_bound[key] = (
            _percentiles(member_kinetic, interval_level) if member_kinetic else None
        )

    diagnostics: dict[str, Any] = {
        "model_ref": "docs/MODEL_SPEC.md section 3, capacity and breakthrough",
        "headline_estimate": "supply_limited",
        "supply_limited_form": "t = (target_capacity - sorbed) / J_in",
        "kinetics_limited_form": "t = -(1/k_eff) ln((q_target - q_eq)/(q0 - q_eq))",
        "kinetics_limited_s_interval": {
            key: (None if value is None else list(value))
            for key, value in kinetic_bound.items()
        },
        "kinetics_limited_note": (
            "A lower bound only: it assumes the metal has already arrived. The "
            "supply-limited estimate is the headline for a cap driven by a "
            "seepage flux."
        ),
        "breakthrough_definition": (
            "consumption of breakthrough_fraction of the allocated capacity, a "
            "proxy for J_out / J_bare crossing 5 % in the numerical probe; the "
            "two agree to within the width of the sorption front"
        ),
        "fouling_index_assumed_constant": float(fouling_index),
        "ensemble_seed": ensemble.seed,
        "ensemble_distribution": ensemble.distribution,
        "sorbent_loading_kg_per_m2": float(sorbent_loading_kg_per_m2),
    }

    return LayerForecast(
        time_utc=time_utc,
        tile_id=tile_id,
        elements=elements,
        sorbed_kg_per_m2={
            key: float(sorbed_kg_per_m2_by_element.get(key, 0.0)) for key in elements
        },
        loading_fraction=point_fraction,
        loading_fraction_interval=fraction_interval,
        remaining_capacity_kg_per_m2=point_capacity,
        remaining_capacity_interval=capacity_interval,
        breakthrough_s_interval=breakthrough,
        never_reached_fraction=never_reached,
        assumed_supply_flux_kg_per_m2_per_s={
            key: float(supply_flux_kg_per_m2_per_s.get(key, 0.0)) for key in elements
        },
        breakthrough_fraction=float(breakthrough_fraction),
        interval_level=float(interval_level),
        ensemble_size=ensemble.size,
        diagnostics=diagnostics,
    )


def forecast_tile(
    tile_state: MatTileState,
    materials: Mapping[str, MaterialParameters],
    supply_flux_kg_per_m2_per_s: Mapping[str, float],
    **kwargs: Any,
) -> LayerForecast:
    """:func:`forecast_breakthrough` for a known :class:`MatTileState`.

    Convenience for the simulator side and the standalone example.  The
    operator-facing loop should prefer :func:`forecast_breakthrough` with an
    *estimated* sorbed mass.
    """
    kwargs.setdefault("tile_id", tile_state.tile_id)
    return forecast_breakthrough(
        materials,
        {key: sorbed_kg_per_m2(tile_state, key) for key in materials},
        tile_state.geometry.sorbent_loading_kg_per_m2,
        tile_state.fouling_index,
        supply_flux_kg_per_m2_per_s,
        **kwargs,
    )


def breakthrough_interval(
    materials: Mapping[str, MaterialParameters],
    sorbed_kg_per_m2_by_element: Mapping[str, float],
    sorbent_loading_kg_per_m2: float,
    fouling_index: float,
    supply_flux_kg_per_m2_per_s: Mapping[str, float],
    **kwargs: Any,
) -> dict[str, tuple[float, float] | None]:
    """Per-element breakthrough interval, or ``None``.  Never a bare number.

    ``None`` means no ensemble member consumes its capacity under the assumed
    supply.  When only some members do, the interval covers those members and
    :func:`forecast_breakthrough` reports the rest in ``never_reached_fraction``.
    """
    forecast = forecast_breakthrough(
        materials,
        sorbed_kg_per_m2_by_element,
        sorbent_loading_kg_per_m2,
        fouling_index,
        supply_flux_kg_per_m2_per_s,
        **kwargs,
    )
    return dict(forecast.breakthrough_s_interval)
