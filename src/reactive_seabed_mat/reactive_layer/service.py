"""Media replacement, partial replacement, and the retrieved-media ledger.

``docs/MODEL_SPEC.md`` section 7::

    retrieved_ledger[e] += R_e
    R_e = 0 ; f = 0 ; media_id = new ; service_count += 1

Capacity resets; retained mass does not disappear.  The total inventory
(water + active mat + retrieved media + boundary export) is unchanged by the
event, which ``tests/reactive_layer/test_service.py`` checks to the last bit.

The mat is modular, so replacement is **per tile**.  A policy that concludes
two tiles out of nine are exhausted replaces those two and leaves the other
seven exactly as they were: ``ServiceEvent.tile_ids`` is a sequence for that
reason, and :func:`replace_tiles` moves exactly those tiles' inventory into the
ledger.

Euro values here are **assumptions** taken from ``config.CostConfig``.  No
dated quotation exists (references S13-S22).  Recovered media is metal-loaded
waste with a handling cost; this module never books revenue for it, and nothing
is ever returned to the sea.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Sequence

import numpy as np

from ..config import CostConfig
from ..contracts import MatTileState, ProvenanceLabel, ServiceEvent

__all__ = [
    "RetrievedMediaLedger",
    "next_media_id",
    "replacement_cost_eur",
    "replace_media",
    "replace_tiles",
    "MEDIA_DISPOSAL_NOTE",
]

MEDIA_DISPOSAL_NOTE = (
    "Retrieved media is metal-loaded waste. It carries a handling cost and is "
    "never valued as a saleable product, and it is never returned to the sea."
)

_TRAILING_DIGITS = re.compile(r"^(?P<stem>.*?)(?P<number>\d+)$")


def next_media_id(media_id: str) -> str:
    """Deterministic successor of a media identifier.

    ``media_A0`` -> ``media_A1``; an identifier without a trailing number gets
    ``_r1`` appended.  Deterministic on purpose: a replay of the same run must
    produce the same identifiers.
    """
    match = _TRAILING_DIGITS.match(media_id)
    if match is None:
        return f"{media_id}_r1"
    number = int(match.group("number")) + 1
    width = len(match.group("number"))
    return f"{match.group('stem')}{number:0{width}d}"


def replacement_cost_eur(
    costs: CostConfig,
    *,
    n_tiles: int,
    media_area_m2: float,
    retrieved_media_mass_kg: float,
    include_vessel_visit: bool = True,
) -> dict[str, float]:
    """Assumed cost breakdown of one replacement campaign, in euro.

    Every figure is an ``assumption`` from ``config.CostConfig``; none of them
    is a quotation.  The breakdown is returned rather than a single number so
    the presentation branch can show what was assumed.  One vessel visit
    services however many tiles were named, which is exactly why partial
    replacement is worth modelling at all.
    """
    if n_tiles < 0:
        raise ValueError(f"n_tiles must be non-negative, got {n_tiles!r}")
    for name, value in (
        ("media_area_m2", media_area_m2),
        ("retrieved_media_mass_kg", retrieved_media_mass_kg),
    ):
        if value < 0.0 or not math.isfinite(value):
            raise ValueError(f"{name} must be finite and non-negative, got {value!r}")
    vessel = float(costs.deployment_vessel_day_eur) if include_vessel_visit else 0.0
    tile_handling = float(costs.tile_replacement_eur) * int(n_tiles)
    new_media = float(costs.mat_material_eur_per_m2) * float(media_area_m2)
    handling = float(costs.used_media_handling_eur_per_kg) * float(
        retrieved_media_mass_kg
    )
    return {
        "vessel_visit_eur": vessel,
        "tile_handling_eur": tile_handling,
        "new_media_eur": new_media,
        "used_media_handling_eur": handling,
        "total_eur": vessel + tile_handling + new_media + handling,
        "provenance": ProvenanceLabel.ASSUMPTION.value,
    }


@dataclass
class RetrievedMediaLedger:
    """Accumulator for metal that has left the seabed and left the active mat.

    It is a mass store, not a report: ``totals_kg`` feeds
    ``MassLedger.retained_in_retrieved_media_kg`` directly.  Nothing here ever
    decreases, because retrieved metal does not go anywhere else in this
    demonstrator.
    """

    totals_kg: dict[str, float] = field(default_factory=dict)
    events: list[ServiceEvent] = field(default_factory=list)
    assumed_cost_eur: float = 0.0

    def record(self, event: ServiceEvent) -> "RetrievedMediaLedger":
        """Add one service event's retrieved mass to the ledger."""
        for key, value in event.retrieved_kg.items():
            amount = float(value)
            if amount < 0.0 or not math.isfinite(amount):
                raise ValueError(
                    f"retrieved mass for {key!r} must be finite and non-negative, "
                    f"got {value!r}"
                )
            self.totals_kg[key] = self.totals_kg.get(key, 0.0) + amount
        self.events.append(event)
        self.assumed_cost_eur += float(event.cost_eur)
        return self

    def total_kg(self, element: str) -> float:
        return float(self.totals_kg.get(element, 0.0))

    @property
    def total_mass_kg(self) -> float:
        return float(sum(self.totals_kg.values()))

    @property
    def service_count(self) -> int:
        return len(self.events)

    def as_dict(self) -> dict[str, Any]:
        return {
            "retrieved_kg": dict(self.totals_kg),
            "service_count": self.service_count,
            "assumed_cost_eur": self.assumed_cost_eur,
            "cost_provenance": ProvenanceLabel.ASSUMPTION.value,
            "disposal_note": MEDIA_DISPOSAL_NOTE,
            "events": [
                {
                    "event_id": event.event_id,
                    "time_utc": event.time_utc,
                    "tile_ids": list(event.tile_ids),
                    "kind": event.kind,
                    "old_media_id": event.old_media_id,
                    "new_media_id": event.new_media_id,
                    "retrieved_kg": dict(event.retrieved_kg),
                    "cost_eur": event.cost_eur,
                    "triggered_by_recommendation_id": (
                        event.triggered_by_recommendation_id
                    ),
                    "execution_mode": event.execution_mode,
                }
                for event in self.events
            ],
        }


def _fresh_profiles(state: MatTileState) -> tuple[dict[str, Any], dict[str, Any]]:
    n_nodes = state.n_nodes
    porewater = {
        key: np.zeros(n_nodes, dtype=float) for key in state.porewater_kg_per_m3
    }
    sorbed = {key: np.zeros(n_nodes, dtype=float) for key in state.sorbed_kg_per_kg}
    return porewater, sorbed


def replace_tiles(
    tile_states: Sequence[MatTileState],
    tile_ids: Sequence[str],
    time_utc: datetime,
    *,
    ledger: RetrievedMediaLedger | None = None,
    new_media_id: str | None = None,
    event_id: str | None = None,
    costs: CostConfig | None = None,
    cost_eur: float | None = None,
    triggered_by_recommendation_id: str | None = None,
    kind: str = "partial_media_replacement",
    reset_physical_condition: bool = True,
) -> tuple[tuple[MatTileState, ...], ServiceEvent]:
    """Replace the media of a **subset** of tiles.  Mass moves; it is never lost.

    Returns the full tile sequence in its original order, with the named tiles
    replaced, and the :class:`ServiceEvent` that describes the move.  Tiles that
    were not named are returned unchanged, object for object.

    ``reset_physical_condition`` also clears fouling, integrity, burial and
    displacement, which is what recovering a tile and laying a fresh one
    actually does.  Setting it to ``False`` swaps the media and leaves the
    physical condition alone, which is not a real operation but is useful for
    isolating one degradation mode in a test.
    """
    if time_utc.tzinfo is None:
        raise ValueError("time_utc must be timezone-aware UTC")
    requested = list(dict.fromkeys(str(tile_id) for tile_id in tile_ids))
    if not requested:
        raise ValueError("a replacement must name at least one tile")

    by_id = {state.tile_id: state for state in tile_states}
    unknown = [tile_id for tile_id in requested if tile_id not in by_id]
    if unknown:
        raise KeyError(
            f"replacement names unknown tiles {unknown}; known tiles: "
            f"{[state.tile_id for state in tile_states]}"
        )

    retrieved: dict[str, float] = {}
    replaced_area_m2 = 0.0
    replaced_media_mass_kg = 0.0
    old_media_ids: list[str] = []
    new_states: dict[str, MatTileState] = {}

    for tile_id in requested:
        state = by_id[tile_id]
        old_media_ids.append(state.media_id)
        media_id = new_media_id or next_media_id(state.media_id)
        if media_id == state.media_id:
            raise ValueError(
                "a replacement must create a NEW media id; "
                f"{media_id!r} equals the current one on tile {tile_id!r}"
            )
        for key in state.porewater_kg_per_m3:
            held = float(state.retained_kg(key))
            if held < 0.0 or not math.isfinite(held):
                raise ValueError(
                    f"tile {tile_id!r} holds a non-physical retained mass for "
                    f"{key!r}: {held!r}"
                )
            retrieved[key] = retrieved.get(key, 0.0) + held
        replaced_area_m2 += state.geometry.footprint_area_m2
        replaced_media_mass_kg += state.geometry.sorbent_mass_kg

        porewater, sorbed = _fresh_profiles(state)
        fields: dict[str, Any] = {
            "media_id": media_id,
            "installed_at_utc": time_utc,
            "porewater_kg_per_m3": porewater,
            "sorbed_kg_per_kg": sorbed,
            "service_count": state.service_count + 1,
        }
        if reset_physical_condition:
            fields.update(
                {
                    "fouling_index": 0.0,
                    "integrity_index": 1.0,
                    "burial_depth_m": 0.0,
                    "displacement_m": 0.0,
                    "displaced": False,
                    "active": True,
                }
            )
        new_states[tile_id] = replace(state, **fields)

    if cost_eur is None:
        breakdown = (
            replacement_cost_eur(
                costs,
                n_tiles=len(requested),
                media_area_m2=replaced_area_m2,
                retrieved_media_mass_kg=replaced_media_mass_kg,
            )
            if costs is not None
            else {"total_eur": 0.0}
        )
        resolved_cost = float(breakdown["total_eur"])
    else:
        resolved_cost = float(cost_eur)

    first = new_states[requested[0]]
    event = ServiceEvent(
        event_id=event_id
        or f"SVC-{'+'.join(requested)}-{first.service_count:03d}",
        time_utc=time_utc,
        tile_ids=tuple(requested),
        kind=kind,
        old_media_id=old_media_ids[0] if len(set(old_media_ids)) == 1 else None,
        new_media_id=first.media_id,
        retrieved_kg=retrieved,
        cost_eur=resolved_cost,
        triggered_by_recommendation_id=triggered_by_recommendation_id,
        execution_mode="simulation_only",
    )

    if ledger is not None:
        ledger.record(event)

    return (
        tuple(new_states.get(state.tile_id, state) for state in tile_states),
        event,
    )


def replace_media(
    tile_state: MatTileState,
    time_utc: datetime,
    *,
    ledger: RetrievedMediaLedger | None = None,
    new_media_id: str | None = None,
    event_id: str | None = None,
    costs: CostConfig | None = None,
    cost_eur: float | None = None,
    triggered_by_recommendation_id: str | None = None,
    kind: str = "media_replacement",
    reset_physical_condition: bool = True,
) -> tuple[MatTileState, ServiceEvent]:
    """Swap the media of **one** tile.  The single-tile case of
    :func:`replace_tiles`, kept because most call sites have one tile in hand.
    """
    states, event = replace_tiles(
        (tile_state,),
        (tile_state.tile_id,),
        time_utc,
        ledger=ledger,
        new_media_id=new_media_id,
        event_id=event_id,
        costs=costs,
        cost_eur=cost_eur,
        triggered_by_recommendation_id=triggered_by_recommendation_id,
        kind=kind,
        reset_physical_condition=reset_physical_condition,
    )
    return states[0], event
