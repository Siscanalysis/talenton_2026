"""Conditional remaining-life forecasting for a loaded panel.

MODEL_SPEC section 4, "Remaining service life"::

    t = -(1/k_eff) ln( (q_target - q_eq) / (q0 - q_eq) )   if q_eq > q_target
    t = None (never reached under this assumption)         otherwise

**Remaining life is not a sensor reading.**  It is the answer to a
conditional question: *if the recent contact concentration persisted, when
would this compartment reach ``rho * q_max_eff``?*  Evaluated across the
parameter ensemble it becomes the interval reported in
``EstimateSnapshot.remaining_life_s_interval``, and the user interface has to
say what it is conditional on.

The closed form is the kinetics-and-isotherm limit.  When the available-mass
bound of MODEL_SPEC section 3 is active, real loading is slower, so the number
below is a **lower bound** on the time.  Pass ``assumed_supply_kg_per_s`` to
get the supply-limited time alongside it; that combination is reported in the
diagnostics, never silently folded into the headline interval.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

import numpy as np

from ..contracts import MaterialParameters, PanelState, ProvenanceLabel
from .material import (
    ParameterEnsemble,
    equilibrium_loading,
    fouling_factors,
    sample_parameter_ensemble,
    sequence_of_elements,
)

__all__ = [
    "PanelForecast",
    "CONDITIONAL_NOTE",
    "loading_kg_per_kg",
    "loading_fraction",
    "remaining_capacity_kg",
    "time_to_target_loading",
    "remaining_life_s",
    "remaining_life_interval",
    "forecast_loading",
    "forecast_panel",
]

CONDITIONAL_NOTE = (
    "Conditional forecast: it assumes the stated contact concentration and the "
    "current fouling state persist. It is not a measurement and not a warranty; "
    "a change of source strength or of the current field invalidates it."
)

#: Default target: ``PolicyConfig.replacement_loading_threshold`` (assumption).
DEFAULT_TARGET_LOADING_FRACTION = 0.80


# ---------------------------------------------------------------------------
# Point quantities
# ---------------------------------------------------------------------------

def loading_kg_per_kg(
    retained_kg: float, sorbent_mass_kg: float, params: MaterialParameters
) -> float:
    """``q = R_e / M_e`` [kg/kg]; zero when nothing is allocated."""
    allocated = float(sorbent_mass_kg) * float(params.allocation_fraction)
    if allocated <= 0.0:
        return 0.0
    return float(retained_kg) / allocated


def loading_fraction(
    retained_kg: float,
    sorbent_mass_kg: float,
    params: MaterialParameters,
    fouling_fraction: float = 0.0,
    *,
    use_fouling: bool = True,
) -> float:
    """Loading as a fraction of capacity, in ``[0, inf)``.

    With ``use_fouling`` (the default) the denominator is the *accessible*
    capacity ``q_max_eff``, which is what a maintenance decision cares about.
    A fouled panel can therefore report a fraction above 1: it holds more than
    its currently accessible capacity, which is exactly the state in which
    further uptake stops.  That is reported, not clipped.
    """
    factors = fouling_factors(params, fouling_fraction if use_fouling else 0.0)
    q_max_eff = params.q_max_kg_per_kg * factors.capacity_factor
    loading = loading_kg_per_kg(retained_kg, sorbent_mass_kg, params)
    if q_max_eff <= 0.0:
        return 1.0 if loading > 0.0 else 0.0
    return loading / q_max_eff


def remaining_capacity_kg(
    retained_kg: float,
    sorbent_mass_kg: float,
    params: MaterialParameters,
    fouling_fraction: float = 0.0,
) -> float:
    """``C_remaining = max(0, M_e q_max_eff - R_e)`` [kg]."""
    factors = fouling_factors(params, fouling_fraction)
    allocated = float(sorbent_mass_kg) * float(params.allocation_fraction)
    q_max_eff = params.q_max_kg_per_kg * factors.capacity_factor
    return max(0.0, allocated * q_max_eff - float(retained_kg))


def time_to_target_loading(
    q0_kg_per_kg: float,
    q_eq_kg_per_kg: float,
    k_eff_per_s: float,
    q_target_kg_per_kg: float,
) -> float | None:
    """Seconds for ``q`` to rise from ``q0`` to ``q_target``, or ``None``.

    ``None`` means "not reached under this assumption": either the equilibrium
    loading sits at or below the target, or the rate is zero.  Returns ``0.0``
    when the target has already been reached.
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


def remaining_life_s(
    params: MaterialParameters,
    retained_kg: float,
    sorbent_mass_kg: float,
    fouling_fraction: float,
    contact_concentration_kg_per_m3: float,
    target_loading_fraction: float = DEFAULT_TARGET_LOADING_FRACTION,
) -> float | None:
    """Conditional seconds until ``rho * q_max_eff`` is reached, or ``None``."""
    if not (0.0 <= target_loading_fraction <= 1.0):
        raise ValueError(
            f"target_loading_fraction must lie in [0, 1], got "
            f"{target_loading_fraction!r}"
        )
    allocated = float(sorbent_mass_kg) * float(params.allocation_fraction)
    if allocated <= 0.0:
        # No allocated sorbent: there is no loading to run out of.
        return None
    factors = fouling_factors(params, fouling_fraction)
    q_max_eff = params.q_max_kg_per_kg * factors.capacity_factor
    k_eff = params.k_rate_per_s * factors.kinetics_factor
    q0 = float(retained_kg) / allocated
    q_target = target_loading_fraction * q_max_eff
    q_eq = equilibrium_loading(
        params.kd_m3_per_kg, contact_concentration_kg_per_m3, q_max_eff
    )
    return time_to_target_loading(q0, q_eq, k_eff, q_target)


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


def remaining_life_interval(
    materials: Mapping[str, MaterialParameters],
    retained_kg: Mapping[str, float],
    sorbent_mass_kg: float,
    fouling_fraction: float,
    contact_concentration_kg_per_m3: Mapping[str, float],
    *,
    target_loading_fraction: float = DEFAULT_TARGET_LOADING_FRACTION,
    ensemble: ParameterEnsemble | None = None,
    ensemble_size: int = 64,
    seed: int = 0,
    interval_level: float = 0.90,
) -> dict[str, tuple[float, float] | None]:
    """Per-element conditional remaining-life interval, or ``None``.

    ``None`` means no ensemble member reaches the target under the assumed
    contact concentration.  When only *some* members reach it, the interval
    covers the members that do, and the share that never reach it is reported
    by :func:`forecast_loading` in ``never_reached_fraction``: an interval on
    its own would hide that.
    """
    forecast = forecast_loading(
        materials=materials,
        retained_kg=retained_kg,
        sorbent_mass_kg=sorbent_mass_kg,
        fouling_fraction=fouling_fraction,
        contact_concentration_kg_per_m3=contact_concentration_kg_per_m3,
        target_loading_fraction=target_loading_fraction,
        ensemble=ensemble,
        ensemble_size=ensemble_size,
        seed=seed,
        interval_level=interval_level,
    )
    return dict(forecast.remaining_life_s_interval)


# ---------------------------------------------------------------------------
# The object the feedback branch consumes
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PanelForecast:
    """Everything the maintenance policy needs from the material model.

    It carries no hidden event label and no truth-store reference: it is
    computed from a retained-mass estimate, the declared material priors and
    an assumed contact concentration, all of which the feedback branch already
    has.
    """

    time_utc: datetime | None
    panel_id: str | None
    elements: tuple[str, ...]
    retained_kg: Mapping[str, float]
    loading_kg_per_kg: Mapping[str, float]
    loading_fraction: Mapping[str, float]
    loading_fraction_interval: Mapping[str, tuple[float, float]]
    remaining_capacity_kg: Mapping[str, float]
    remaining_life_s_median: Mapping[str, float | None]
    remaining_life_s_interval: Mapping[str, tuple[float, float] | None]
    never_reached_fraction: Mapping[str, float]
    assumed_concentration_kg_per_m3: Mapping[str, float]
    target_loading_fraction: float
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
            "panel_id": self.panel_id,
            "elements": list(self.elements),
            "retained_kg": dict(self.retained_kg),
            "loading_kg_per_kg": dict(self.loading_kg_per_kg),
            "loading_fraction": dict(self.loading_fraction),
            "loading_fraction_interval": {
                key: list(value) for key, value in self.loading_fraction_interval.items()
            },
            "remaining_capacity_kg": dict(self.remaining_capacity_kg),
            "remaining_life_s_median": dict(self.remaining_life_s_median),
            "remaining_life_s_interval": {
                key: (None if value is None else list(value))
                for key, value in self.remaining_life_s_interval.items()
            },
            "never_reached_fraction": dict(self.never_reached_fraction),
            "assumed_concentration_kg_per_m3": dict(
                self.assumed_concentration_kg_per_m3
            ),
            "target_loading_fraction": self.target_loading_fraction,
            "interval_level": self.interval_level,
            "ensemble_size": self.ensemble_size,
            "conditional_note": self.conditional_note,
            "provenance": self.provenance,
            "diagnostics": dict(self.diagnostics or {}),
        }


def forecast_loading(
    materials: Mapping[str, MaterialParameters],
    retained_kg: Mapping[str, float],
    sorbent_mass_kg: float,
    fouling_fraction: float,
    contact_concentration_kg_per_m3: Mapping[str, float],
    *,
    target_loading_fraction: float = DEFAULT_TARGET_LOADING_FRACTION,
    ensemble: ParameterEnsemble | None = None,
    ensemble_size: int = 64,
    seed: int = 0,
    interval_level: float = 0.90,
    assumed_supply_kg_per_s: Mapping[str, float] | None = None,
    time_utc: datetime | None = None,
    panel_id: str | None = None,
) -> PanelForecast:
    """Forecast from a retained-mass estimate, without touching a panel object.

    This is the entry point the feedback branch should call: it takes an
    estimated ``retained_kg`` (which is what the estimator produces) rather
    than a simulator :class:`PanelState`, so no path leads from the hidden
    truth store into a recommendation.
    """
    if not (0.0 < interval_level < 1.0):
        raise ValueError(f"interval_level must lie in (0, 1), got {interval_level!r}")
    if ensemble is None:
        ensemble = sample_parameter_ensemble(materials, ensemble_size, seed)
    elements = tuple(sequence_of_elements(materials))

    point_loading: dict[str, float] = {}
    point_fraction: dict[str, float] = {}
    fraction_interval: dict[str, tuple[float, float]] = {}
    capacity_left: dict[str, float] = {}
    life_median: dict[str, float | None] = {}
    life_interval: dict[str, tuple[float, float] | None] = {}
    never_reached: dict[str, float] = {}
    supply_limited: dict[str, float | None] = {}

    for key in elements:
        params = materials[key]
        retained = float(retained_kg.get(key, 0.0))
        concentration = float(contact_concentration_kg_per_m3.get(key, 0.0))

        point_loading[key] = loading_kg_per_kg(retained, sorbent_mass_kg, params)
        point_fraction[key] = loading_fraction(
            retained, sorbent_mass_kg, params, fouling_fraction
        )
        capacity_left[key] = remaining_capacity_kg(
            retained, sorbent_mass_kg, params, fouling_fraction
        )

        member_fractions: list[float] = []
        member_times: list[float] = []
        never = 0
        for member in ensemble.members:
            member_params = member.get(key, params)
            member_fractions.append(
                loading_fraction(retained, sorbent_mass_kg, member_params, fouling_fraction)
            )
            time_s = remaining_life_s(
                member_params,
                retained,
                sorbent_mass_kg,
                fouling_fraction,
                concentration,
                target_loading_fraction,
            )
            if time_s is None:
                never += 1
            else:
                member_times.append(time_s)

        fraction_interval[key] = _percentiles(member_fractions, interval_level)
        never_reached[key] = never / max(1, ensemble.size)
        if member_times:
            life_interval[key] = _percentiles(member_times, interval_level)
            life_median[key] = float(np.median(np.asarray(member_times, dtype=float)))
        else:
            life_interval[key] = None
            life_median[key] = None

        if assumed_supply_kg_per_s is not None:
            rate = float(assumed_supply_kg_per_s.get(key, 0.0))
            target_capacity = target_loading_fraction * (
                float(sorbent_mass_kg)
                * params.allocation_fraction
                * params.q_max_kg_per_kg
                * fouling_factors(params, fouling_fraction).capacity_factor
            )
            deficit = max(0.0, target_capacity - retained)
            supply_limited[key] = (deficit / rate) if rate > 0.0 else None

    diagnostics: dict[str, Any] = {
        "model_ref": "docs/MODEL_SPEC.md section 4, remaining service life",
        "closed_form": "t = -(1/k_eff) ln((q_target - q_eq)/(q0 - q_eq))",
        "available_mass_bound_ignored": True,
        "available_mass_note": (
            "The closed form is the kinetics and isotherm limit. When the "
            "available-mass bound of MODEL_SPEC section 3 is active the real "
            "time is longer, so this is a lower bound on the remaining life."
        ),
        "fouling_fraction_assumed_constant": float(fouling_fraction),
        "ensemble_seed": ensemble.seed,
        "ensemble_distribution": ensemble.distribution,
        "sorbent_mass_kg": float(sorbent_mass_kg),
    }
    if assumed_supply_kg_per_s is not None:
        diagnostics["supply_limited_life_s"] = supply_limited
        diagnostics["assumed_supply_kg_per_s"] = dict(assumed_supply_kg_per_s)

    return PanelForecast(
        time_utc=time_utc,
        panel_id=panel_id,
        elements=elements,
        retained_kg={key: float(retained_kg.get(key, 0.0)) for key in elements},
        loading_kg_per_kg=point_loading,
        loading_fraction=point_fraction,
        loading_fraction_interval=fraction_interval,
        remaining_capacity_kg=capacity_left,
        remaining_life_s_median=life_median,
        remaining_life_s_interval=life_interval,
        never_reached_fraction=never_reached,
        assumed_concentration_kg_per_m3={
            key: float(contact_concentration_kg_per_m3.get(key, 0.0))
            for key in elements
        },
        target_loading_fraction=float(target_loading_fraction),
        interval_level=float(interval_level),
        ensemble_size=ensemble.size,
        diagnostics=diagnostics,
    )


def forecast_panel(
    panel_state: PanelState,
    materials: Mapping[str, MaterialParameters],
    contact_concentration_kg_per_m3: Mapping[str, float],
    *,
    target_loading_fraction: float = DEFAULT_TARGET_LOADING_FRACTION,
    ensemble: ParameterEnsemble | None = None,
    ensemble_size: int = 64,
    seed: int = 0,
    interval_level: float = 0.90,
    assumed_supply_kg_per_s: Mapping[str, float] | None = None,
    time_utc: datetime | None = None,
) -> PanelForecast:
    """:func:`forecast_loading` for a known :class:`PanelState`.

    Convenience for the simulator side and the standalone example.  The
    operator-facing loop should prefer :func:`forecast_loading` with an
    *estimated* retained mass.
    """
    return forecast_loading(
        materials=materials,
        retained_kg=panel_state.retained_kg,
        sorbent_mass_kg=panel_state.sorbent_mass_kg,
        fouling_fraction=panel_state.fouling_fraction,
        contact_concentration_kg_per_m3=contact_concentration_kg_per_m3,
        target_loading_fraction=target_loading_fraction,
        ensemble=ensemble,
        ensemble_size=ensemble_size,
        seed=seed,
        interval_level=interval_level,
        assumed_supply_kg_per_s=assumed_supply_kg_per_s,
        time_utc=time_utc if time_utc is not None else None,
        panel_id=panel_state.panel_id,
    )
