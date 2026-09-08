"""Uncertainty-aware estimation of mat condition from observations alone.

This package may read ``MEASURED`` records and its own previous estimates. It
may not read ``results/<run>/truth/`` or any hidden simulator state, and
``tests/contracts/test_state_separation.py`` checks that statically.

Everything here is an interval, never a point, because the evidence a real
operator has does not determine a point. Where the observations cannot separate
two explanations, the estimator reports competing weights and an ambiguity flag
instead of choosing.
"""

from __future__ import annotations

from .estimate import (  # noqa: F401
    EstimationAssumptions,
    capacity_kg_per_m2,
    estimate_tiles,
    interval_product,
    interval_quotient,
)

__all__ = [
    "EstimationAssumptions",
    "capacity_kg_per_m2",
    "estimate_tiles",
    "interval_product",
    "interval_quotient",
]
