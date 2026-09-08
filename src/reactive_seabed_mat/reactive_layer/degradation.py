"""The four independent degradation modes of ``docs/MODEL_SPEC.md`` section 4.

They are four separate mechanisms with four separate state fields on
:class:`~reactive_seabed_mat.contracts.MatTileState`, and this module keeps them
apart on purpose.  Reading every performance loss as chemical saturation is the
specific failure the design exists to prevent.

======  ===================  ==============================================
Mode    State field          What it does here
======  ===================  ==============================================
1       (the profiles)       saturation falls out of the chemistry in
                             ``column.py``; nothing is applied here
2       ``fouling_index``    lowers ``k``, ``q_max`` and ``D_eff``, and
                             raises the edge bypass so it is never free
3       ``burial_depth_m``   adds diffusive resistance above the layer, so
                             it **reduces** the apparent flux
3       ``displaced``        coverage drops to zero: bare flux immediately
4       ``integrity_index``  the torn share emits the bare flux
======  ===================  ==============================================

Two of these deserve a warning rather than a docstring.

**Fouling is not an improvement.**  Pore blockage lowers ``D_eff`` and would
lower the residual flux if it were modelled alone.  The head across the layer
rises and flow is pushed around the tile edge instead::

    bypass_fraction = edge_leakage_fraction + fouling_bypass_coupling * f

and the bypassed share of the footprint emits ``J_bare``.  With the configured
coupling the bypass term dominates the diffusivity term at every fouling level,
so fouling always makes the tile worse.  ``tests/reactive_layer/`` asserts that.

**Burial masquerades as success.**  Sediment settling on the mat adds a
diffusive path::

    g_top_buried = 1 / (1 / g_top + burial_resistance_s_per_m * burial_depth_m)

which lowers ``J_out``.  A monitoring system that reads a falling flux as a
working mat is wrong: the mat may be doing nothing at all under a blanket of
mud.  :data:`BURIAL_WARNING` is attached to every buried tile summary, and
``AmbiguityFlag.BURIAL`` exists in the contract for exactly this.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from ..config import DegradationEvent
from ..contracts import (
    AmbiguityFlag,
    DegradationMode,
    MaterialParameters,
    MatTileState,
    ProvenanceLabel,
)
from .material import fouling_factors, sequence_of_elements

__all__ = [
    "BURIAL_WARNING",
    "DEFAULT_BURIAL_RESISTANCE_S_PER_M",
    "DEFAULT_FOULING_BYPASS_COUPLING",
    "BypassFraction",
    "bypass_fraction",
    "buried_top_conductance",
    "effective_cover_fraction",
    "tile_effective_flux_kg_per_m2_per_s",
    "grow_fouling",
    "grow_burial",
    "apply_degradation_event",
    "apply_degradation_events",
    "degradation_state",
    "saturation_state",
]

BURIAL_WARNING = (
    "Burial reduces the apparent residual flux by adding diffusive resistance "
    "above the layer. A lower measured flux under a buried tile is not "
    "evidence that the mat is working; AmbiguityFlag.BURIAL must be raised."
)

#: Extra diffusive path a buried mat must overcome, per metre of burial
#: [s m^-1].  ASSUMPTION, mirroring ``config.DegradationConfig``; the frozen
#: ``advance_reactive_layer`` signature carries no configuration object, so this
#: is the default when ``SeabedExchange.environment`` does not override it.
DEFAULT_BURIAL_RESISTANCE_S_PER_M = 2.0e8

#: How strongly pore blockage pushes flow around the tile edge.  ASSUMPTION,
#: mirroring ``config.DegradationConfig.fouling_bypass_coupling``.
DEFAULT_FOULING_BYPASS_COUPLING = 0.35


# ---------------------------------------------------------------------------
# Mode 2: fouling, and the bypass that stops it looking like a benefit
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BypassFraction:
    """The share of a tile's footprint that flow takes around the layer."""

    value: float
    edge_leakage_fraction: float
    fouling_index: float
    fouling_bypass_coupling: float
    raw_value: float
    clipped: bool

    def as_dict(self) -> dict[str, float | bool]:
        return {
            "bypass_fraction": self.value,
            "edge_leakage_fraction": self.edge_leakage_fraction,
            "fouling_index": self.fouling_index,
            "fouling_bypass_coupling": self.fouling_bypass_coupling,
            "raw_bypass_fraction": self.raw_value,
            "clipped": self.clipped,
        }


def bypass_fraction(
    edge_leakage_fraction: float,
    fouling_index: float,
    fouling_bypass_coupling: float = DEFAULT_FOULING_BYPASS_COUPLING,
) -> BypassFraction:
    """``bypass = edge_leakage + coupling * f``, clipped into ``[0, 1]``.

    Clipping is recorded, never silent.  A value of 1 means the whole footprint
    is bypassed, which is a design failure and is reported as such.
    """
    for name, value in (
        ("edge_leakage_fraction", edge_leakage_fraction),
        ("fouling_index", fouling_index),
        ("fouling_bypass_coupling", fouling_bypass_coupling),
    ):
        if not math.isfinite(float(value)):
            raise ValueError(f"{name} must be finite, got {value!r}")
    fouling = min(1.0, max(0.0, float(fouling_index)))
    raw = float(edge_leakage_fraction) + float(fouling_bypass_coupling) * fouling
    value = min(1.0, max(0.0, raw))
    return BypassFraction(
        value=value,
        edge_leakage_fraction=float(edge_leakage_fraction),
        fouling_index=fouling,
        fouling_bypass_coupling=float(fouling_bypass_coupling),
        raw_value=raw,
        clipped=raw != value,
    )


# ---------------------------------------------------------------------------
# Mode 3: burial adds resistance; displacement removes the tile
# ---------------------------------------------------------------------------

def buried_top_conductance(
    top_conductance_m_per_s: float,
    burial_depth_m: float,
    burial_resistance_s_per_m: float = DEFAULT_BURIAL_RESISTANCE_S_PER_M,
) -> float:
    """``1 / (1/g_top + R d)`` [m s^-1].  Never larger than ``g_top``.

    See :data:`BURIAL_WARNING`.  This reduces the flux the mat emits, and that
    reduction is a **failure to observe**, not a success.
    """
    depth = max(0.0, float(burial_depth_m))
    if depth == 0.0:
        return float(top_conductance_m_per_s)
    if top_conductance_m_per_s <= 0.0:
        return 0.0
    resistance = 1.0 / float(top_conductance_m_per_s) + max(
        0.0, float(burial_resistance_s_per_m)
    ) * depth
    if not math.isfinite(resistance) or resistance <= 0.0:
        return 0.0
    return 1.0 / resistance


# ---------------------------------------------------------------------------
# Combining modes 2, 3 and 4 into what one tile's footprint emits
# ---------------------------------------------------------------------------

def effective_cover_fraction(
    coverage_fraction: float, bypass: float
) -> float:
    """``covered * (1 - bypass)`` (MODEL_SPEC section 5), clipped to ``[0, 1]``.

    ``coverage_fraction`` already folds in displacement (0 when displaced) and
    local damage (the integrity index).  The cell-level version, which weights
    several tiles over one seabed cell, belongs to ``coastal_transport`` and is
    not duplicated here; this is the single-tile case the layer tests need.
    """
    value = float(coverage_fraction) * (1.0 - float(bypass))
    return min(1.0, max(0.0, value))


def tile_effective_flux_kg_per_m2_per_s(
    flux_out_kg_per_m2_per_s: float,
    bare_flux_kg_per_m2_per_s: float,
    coverage_fraction: float,
    bypass: float,
) -> float:
    """What one tile's whole footprint emits, modes 2, 3 and 4 combined::

        effective_cover = coverage * (1 - bypass)
        J = effective_cover * J_out + (1 - effective_cover) * J_bare

    A displaced tile has ``coverage = 0`` and emits ``J_bare`` exactly.  A tile
    with ``integrity_index = 0.65`` and no bypass emits
    ``0.65 J_out + 0.35 J_bare``.
    """
    cover = effective_cover_fraction(coverage_fraction, bypass)
    return cover * float(flux_out_kg_per_m2_per_s) + (1.0 - cover) * float(
        bare_flux_kg_per_m2_per_s
    )


# ---------------------------------------------------------------------------
# Continuous growth
# ---------------------------------------------------------------------------

def grow_fouling(
    tile_state: MatTileState, fouling_growth_per_s: float, dt_s: float
) -> MatTileState:
    """``f <- min(1, f + growth dt)``.

    Retained mass is untouched: fouling blocks access, it does not dissolve
    what is already sorbed.
    """
    if fouling_growth_per_s < 0.0:
        raise ValueError(
            f"fouling_growth_per_s must be non-negative, got {fouling_growth_per_s!r}"
        )
    if dt_s < 0.0:
        raise ValueError(f"dt_s must be non-negative, got {dt_s!r}")
    fouling = min(
        1.0, float(tile_state.fouling_index) + float(fouling_growth_per_s) * float(dt_s)
    )
    return replace(tile_state, fouling_index=float(fouling))


def grow_burial(
    tile_state: MatTileState, burial_growth_m_per_s: float, dt_s: float
) -> MatTileState:
    """``d <- d + growth dt`` [m].  See :data:`BURIAL_WARNING`."""
    if burial_growth_m_per_s < 0.0:
        raise ValueError(
            f"burial_growth_m_per_s must be non-negative, got "
            f"{burial_growth_m_per_s!r}"
        )
    if dt_s < 0.0:
        raise ValueError(f"dt_s must be non-negative, got {dt_s!r}")
    depth = float(tile_state.burial_depth_m) + float(burial_growth_m_per_s) * float(
        dt_s
    )
    return replace(tile_state, burial_depth_m=float(depth))


# ---------------------------------------------------------------------------
# Scheduled events (config.DegradationConfig.events)
# ---------------------------------------------------------------------------

def apply_degradation_event(
    tile_state: MatTileState, event: DegradationEvent
) -> tuple[MatTileState, dict[str, Any]]:
    """Apply one scheduled :class:`~reactive_seabed_mat.config.DegradationEvent`.

    ``magnitude`` means what the mode says it means, and nothing else:

    ``saturation``
        rejected.  Saturation is a consequence of the chemistry, not an event
        that can be imposed; use ``MatLayoutConfig.preload_kg_per_m2`` to start
        a tile part-loaded instead.
    ``fouling``
        fouling index **added**, clipped into ``[0, 1]``.
    ``displacement``
        magnitude >= 1 displaces the tile outright; a smaller magnitude is a
        horizontal offset in metres and leaves the tile in place.
    ``local_damage``
        the share of tile area lost, subtracted from ``integrity_index``.

    Burial is scheduled through ``DegradationConfig.burial_growth_m_per_s`` or
    through a ``displacement`` event with ``mode='displacement'``; a dedicated
    burial event is expressed as a ``displacement`` event only when the config
    says so, so this function also accepts the literal mode string ``burial``
    for a burial depth in metres.
    """
    if event.tile_id != tile_state.tile_id:
        raise ValueError(
            f"event targets tile {event.tile_id!r} but the state is tile "
            f"{tile_state.tile_id!r}"
        )
    magnitude = float(event.magnitude)
    if not math.isfinite(magnitude) or magnitude < 0.0:
        raise ValueError(
            f"degradation magnitude must be finite and non-negative, got "
            f"{event.magnitude!r}"
        )

    mode = str(event.mode)
    record: dict[str, Any] = {
        "tile_id": tile_state.tile_id,
        "mode": mode,
        "start_s": float(event.start_s),
        "magnitude": magnitude,
    }

    if mode == DegradationMode.SATURATION.value:
        raise ValueError(
            "saturation is not a schedulable event: it is the consequence of "
            "the chemistry in column.py. Use MatLayoutConfig.preload_kg_per_m2 "
            "to start a tile part-loaded."
        )
    if mode == DegradationMode.FOULING.value:
        before = float(tile_state.fouling_index)
        after = min(1.0, max(0.0, before + magnitude))
        record.update({"fouling_index_before": before, "fouling_index_after": after})
        return replace(tile_state, fouling_index=after), record
    if mode == DegradationMode.DISPLACEMENT.value:
        if magnitude >= 1.0:
            record.update(
                {
                    "displaced": True,
                    "coverage_fraction_after": 0.0,
                    "note": "the tile no longer covers its footprint at all",
                }
            )
            return (
                replace(
                    tile_state,
                    displaced=True,
                    displacement_m=float(tile_state.displacement_m) + magnitude,
                ),
                record,
            )
        record.update(
            {
                "displaced": False,
                "displacement_m_after": float(tile_state.displacement_m) + magnitude,
                "note": "a partial offset; the tile still covers its footprint",
            }
        )
        return (
            replace(
                tile_state,
                displacement_m=float(tile_state.displacement_m) + magnitude,
            ),
            record,
        )
    if mode == "burial":
        before = float(tile_state.burial_depth_m)
        record.update(
            {
                "burial_depth_m_before": before,
                "burial_depth_m_after": before + magnitude,
                "warning": BURIAL_WARNING,
            }
        )
        return replace(tile_state, burial_depth_m=before + magnitude), record
    if mode == DegradationMode.LOCAL_DAMAGE.value:
        before = float(tile_state.integrity_index)
        after = min(1.0, max(0.0, before - magnitude))
        record.update({"integrity_index_before": before, "integrity_index_after": after})
        return replace(tile_state, integrity_index=after), record

    raise ValueError(
        f"unknown degradation mode {event.mode!r}; known: "
        f"{[member.value for member in DegradationMode]} plus 'burial'"
    )


def apply_degradation_events(
    tile_states: Sequence[MatTileState],
    events: Iterable[DegradationEvent],
    window_start_s: float,
    window_end_s: float,
) -> tuple[tuple[MatTileState, ...], tuple[dict[str, Any], ...]]:
    """Apply every event whose ``start_s`` falls in ``[start, end)``.

    The window is half open so a stepped run applies each event exactly once.
    Events for unknown tiles are an error rather than a silent no-op: a
    scenario that names a tile which does not exist is a configuration bug.
    """
    if window_end_s < window_start_s:
        raise ValueError(
            f"window is inverted: [{window_start_s!r}, {window_end_s!r})"
        )
    by_id = {state.tile_id: state for state in tile_states}
    order = [state.tile_id for state in tile_states]
    applied: list[dict[str, Any]] = []
    for event in events:
        if not (window_start_s <= float(event.start_s) < window_end_s):
            continue
        if event.tile_id not in by_id:
            raise KeyError(
                f"degradation event targets unknown tile {event.tile_id!r}; "
                f"known tiles: {order}"
            )
        new_state, record = apply_degradation_event(by_id[event.tile_id], event)
        by_id[event.tile_id] = new_state
        applied.append(record)
    return tuple(by_id[tile_id] for tile_id in order), tuple(applied)


# ---------------------------------------------------------------------------
# Reporting the four modes side by side
# ---------------------------------------------------------------------------

def saturation_state(
    tile_state: MatTileState, materials: Mapping[str, MaterialParameters]
) -> dict[str, dict[str, float]]:
    """Mode 1, per element: loading, capacity and saturation fraction.

    Nothing is applied: saturation is what the chemistry did, read back out.
    """
    result: dict[str, dict[str, float]] = {}
    dz = tile_state.dz_m()
    rho_b = tile_state.geometry.bulk_density_kg_per_m3
    for key in sequence_of_elements(materials):
        params = materials[key]
        factors = fouling_factors(params, tile_state.fouling_index)
        nominal = tile_state.capacity_kg_per_m2(params)
        sorbed = np.asarray(
            tile_state.sorbed_kg_per_kg.get(key, np.zeros(tile_state.n_nodes)),
            dtype=float,
        )
        # Computed from the profile, not from the saturation fraction: with
        # q_max = 0 the fraction is defined as 0 and would hide any mass held.
        sorbed_kg_per_m2 = float(np.sum(rho_b * sorbed) * dz)
        result[key] = {
            "sorbed_kg_per_m2": sorbed_kg_per_m2,
            "nominal_capacity_kg_per_m2": float(nominal),
            "accessible_capacity_kg_per_m2": float(nominal * factors.capacity_factor),
            "saturation_fraction": float(tile_state.saturation_fraction(params)),
            "retained_kg_per_m2": float(tile_state.retained_kg_per_m2(key))
            if key in tile_state.porewater_kg_per_m3
            else 0.0,
        }
    return result


def degradation_state(
    tile_state: MatTileState,
    materials: Mapping[str, MaterialParameters],
    *,
    fouling_bypass_coupling: float = DEFAULT_FOULING_BYPASS_COUPLING,
    burial_resistance_s_per_m: float = DEFAULT_BURIAL_RESISTANCE_S_PER_M,
) -> dict[str, Any]:
    """All four modes reported side by side, with no mode allowed to stand in
    for another.

    The returned mapping is JSON ready and carries ``ambiguity_flags`` so a
    consumer cannot present a buried tile's low flux as success without seeing
    ``AmbiguityFlag.BURIAL`` next to it.
    """
    bypass = bypass_fraction(
        tile_state.geometry.edge_leakage_fraction,
        tile_state.fouling_index,
        fouling_bypass_coupling,
    )
    flags: list[str] = []
    if tile_state.burial_depth_m > 0.0:
        flags.append(AmbiguityFlag.BURIAL.value)
    if tile_state.displaced or tile_state.displacement_m > 0.0:
        flags.append(AmbiguityFlag.DISPLACEMENT_UPLIFT.value)
    if tile_state.integrity_index < 1.0:
        flags.append(AmbiguityFlag.TEAR_PUNCTURE.value)
    if tile_state.fouling_index > 0.0:
        flags.append(AmbiguityFlag.FOULING.value)
    if any(
        entry["saturation_fraction"] > 0.0
        for entry in saturation_state(tile_state, materials).values()
    ):
        flags.append(AmbiguityFlag.SATURATION.value)

    return {
        "tile_id": tile_state.tile_id,
        "media_id": tile_state.media_id,
        DegradationMode.SATURATION.value: saturation_state(tile_state, materials),
        DegradationMode.FOULING.value: {
            "fouling_index": float(tile_state.fouling_index),
            **bypass.as_dict(),
            "factors": {
                key: fouling_factors(
                    materials[key], tile_state.fouling_index
                ).as_dict()
                for key in sequence_of_elements(materials)
            },
        },
        DegradationMode.DISPLACEMENT.value: {
            "displaced": bool(tile_state.displaced),
            "displacement_m": float(tile_state.displacement_m),
            "burial_depth_m": float(tile_state.burial_depth_m),
            "burial_resistance_s_per_m": float(burial_resistance_s_per_m),
            "warning": BURIAL_WARNING if tile_state.burial_depth_m > 0.0 else "",
        },
        DegradationMode.LOCAL_DAMAGE.value: {
            "integrity_index": float(tile_state.integrity_index),
            "bare_flux_share_of_footprint": 1.0
            - effective_cover_fraction(tile_state.coverage_fraction, bypass.value),
        },
        "coverage_fraction": float(tile_state.coverage_fraction),
        "effective_cover_fraction": effective_cover_fraction(
            tile_state.coverage_fraction, bypass.value
        ),
        "ambiguity_flags": tuple(flags),
        "modes_are_independent": True,
        "provenance": ProvenanceLabel.SYNTHETIC_DEMO.value,
    }
