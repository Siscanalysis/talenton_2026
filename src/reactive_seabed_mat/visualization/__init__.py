"""Offline figures and the self-contained HTML evidence export."""

from __future__ import annotations

from .maps import (  # noqa: F401
    SYNTHETIC_BANNER,
    attenuation_timeline,
    comparison_bar,
    mat_condition_map,
    risk_ratio_map,
    saturation_timeline,
    seabed_flux_map,
    water_concentration_map,
)
from .report import write_html_report  # noqa: F401
