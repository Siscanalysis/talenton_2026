"""Media replacement and the retrieved-media ledger.

MODEL_SPEC section 4, "Replacement"::

    retrieved_ledger[e] += R_e
    R_e = 0 ; f = 0 ; media_id = new ; service_count += 1

Capacity resets; captured mass does not disappear.  The total inventory
(water + active mesh + retrieved media + boundary export) is unchanged by the
event, which is what ``tests/micro/test_service.py`` checks to the last bit.

Euro values here are **assumptions** taken from ``config.CostConfig``.  No
dated quotation exists (build brief, references S13-S22).  Recovered media is
metal-loaded waste with a handling cost; this module never books revenue for
it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Mapping

from ..config import CostConfig
from ..contracts import PanelState, ProvenanceLabel, ServiceEvent

__all__ = [
    "RetrievedMediaLedger",
    "next_media_id",
    "replacement_cost_eur",
    "replace_media",
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
    sorbent_mass_kg: float,
    *,
    include_vessel_visit: bool = True,
) -> dict[str, float]:
    """Assumed cost breakdown of one media replacement, in euro.

    Every figure is an ``assumption`` from ``config.CostConfig``; none of them
    is a quotation.  The breakdown is returned rather than a single number so
    the presentation branch can show what was assumed.
    """
    if sorbent_mass_kg < 0.0:
        raise ValueError(f"sorbent_mass_kg must be non-negative, got {sorbent_mass_kg!r}")
    vessel = float(costs.vessel_visit_eur) if include_vessel_visit else 0.0
    new_media = float(costs.sorbent_eur_per_kg) * float(sorbent_mass_kg)
    handling = float(costs.used_media_handling_eur_per_kg) * float(sorbent_mass_kg)
    return {
        "vessel_visit_eur": vessel,
        "new_sorbent_eur": new_media,
        "used_media_handling_eur": handling,
        "total_eur": vessel + new_media + handling,
    }


@dataclass
class RetrievedMediaLedger:
    """Accumulator for metal that has left the water and left the active mesh.

    It is a mass store, not a report: ``totals_kg`` feeds
    ``MassLedger.in_retrieved_media_kg`` directly.  Nothing here ever
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
                    "panel_id": event.panel_id,
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


def replace_media(
    panel_state: PanelState,
    time_utc: datetime,
    *,
    ledger: RetrievedMediaLedger | None = None,
    new_media_id: str | None = None,
    event_id: str | None = None,
    costs: CostConfig | None = None,
    cost_eur: float | None = None,
    triggered_by_recommendation_id: str | None = None,
    kind: str = "media_replacement",
    new_sorbent_mass_kg: float | None = None,
) -> tuple[PanelState, ServiceEvent]:
    """Swap the media of one panel.  Mass moves; it is never destroyed.

    Returns the new :class:`PanelState` and the :class:`ServiceEvent` that
    describes the move.  When a ``ledger`` is given the event is recorded in it
    immediately, so ``ledger.totals_kg`` plus the new (zero) active inventory
    equals the old active inventory, exactly.

    ``new_sorbent_mass_kg`` allows a refill with a different media mass, which
    the design study uses; it does not change the retrieved mass.
    """
    if time_utc.tzinfo is None:
        raise ValueError("time_utc must be timezone-aware UTC")

    retrieved = {
        key: float(value) for key, value in panel_state.retained_kg.items()
    }
    for key, value in retrieved.items():
        if value < 0.0 or not math.isfinite(value):
            raise ValueError(
                f"panel {panel_state.panel_id!r} holds a non-physical retained "
                f"mass for {key!r}: {value!r}"
            )

    media_id = new_media_id or next_media_id(panel_state.media_id)
    if media_id == panel_state.media_id:
        raise ValueError(
            "a replacement must create a NEW media id; "
            f"{media_id!r} equals the current one"
        )

    sorbent_mass = (
        panel_state.sorbent_mass_kg
        if new_sorbent_mass_kg is None
        else float(new_sorbent_mass_kg)
    )
    if sorbent_mass < 0.0:
        raise ValueError(f"new_sorbent_mass_kg must be non-negative, got {sorbent_mass!r}")

    new_state = replace(
        panel_state,
        media_id=media_id,
        installed_at_utc=time_utc,
        sorbent_mass_kg=sorbent_mass,
        retained_kg={key: 0.0 for key in panel_state.retained_kg},
        fouling_fraction=0.0,
        service_count=panel_state.service_count + 1,
    )

    if cost_eur is None:
        breakdown = (
            replacement_cost_eur(costs, sorbent_mass)
            if costs is not None
            else {"total_eur": 0.0}
        )
        resolved_cost = float(breakdown["total_eur"])
    else:
        resolved_cost = float(cost_eur)

    event = ServiceEvent(
        event_id=event_id
        or f"SVC-{panel_state.panel_id}-{new_state.service_count:03d}",
        time_utc=time_utc,
        panel_id=panel_state.panel_id,
        kind=kind,
        old_media_id=panel_state.media_id,
        new_media_id=media_id,
        retrieved_kg=retrieved,
        cost_eur=resolved_cost,
        triggered_by_recommendation_id=triggered_by_recommendation_id,
        execution_mode="simulation_only",
    )

    if ledger is not None:
        ledger.record(event)

    return new_state, event
