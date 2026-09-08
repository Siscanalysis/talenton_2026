"""Maintenance policies: what to do, and who is allowed to decide it.

Three policies, compared under identical assumptions in
``scenarios/registry.py``:

``none``
    No mat is deployed. The bare-sediment reference case, and the only honest
    baseline for "was the mat worth it".
``fixed``
    Service on a calendar. It ignores the evidence entirely, which is exactly
    why it is worth simulating: it is what most asset programmes actually do.
``evidence_informed``
    Service when the observations and their uncertainty support it, and
    explicitly *not* when they merely permit it.

Nothing in this package actuates anything. Every
:class:`~reactive_seabed_mat.contracts.Recommendation` carries
``human_confirmation_required = True`` and
``execution_mode = "simulation_only"``, and the runner applies a recommendation
only through a separate, explicit acceptance step.
"""

from __future__ import annotations

from .policy import (  # noqa: F401
    PolicyState,
    accepted_service_tiles,
    recommend,
    saturation_interval,
)

__all__ = [
    "PolicyState",
    "accepted_service_tiles",
    "recommend",
    "saturation_interval",
]
