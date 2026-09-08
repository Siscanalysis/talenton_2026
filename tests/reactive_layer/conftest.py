"""Shared fixtures for the reactive-layer suite.

The parameter set below is the one ``docs/reactive_layer_numerics_probe.py`` was
measured with, and the one ``config.py`` documents, so the breakthrough time
these tests assert is the breakthrough time the repository claims.  Every value
is an ASSUMPTION for a synthetic demonstration.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pytest

from reactive_seabed_mat.reactive_layer.column import (
    ColumnParameters,
    solve_column_step,
    stored_kg_per_m2,
)

SECONDS_PER_YEAR = 365.25 * 86400.0

#: The probe's reference column: 10 mm of medium, 40 nodes, porosity 0.5,
#: bulk density 400 kg/m3, D_eff 2e-10 m2/s, Darcy velocity 3e-8 m/s
#: (about 0.95 m/yr), benthic film 5e-7 m/s, Kd 5 m3/kg, operating capacity
#: 1e-3 kg/kg, rate 4e-4 /s.  ASSUMPTIONS, all of them.
PROBE_COLUMN_KWARGS: dict[str, Any] = {
    "thickness_m": 0.010,
    "n_nodes": 40,
    "porosity": 0.5,
    "bulk_density_kg_per_m3": 400.0,
    "d_eff_m2_per_s": 2.0e-10,
    "seepage_velocity_m_per_s": 3.0e-8,
    "film_transfer_m_per_s": 5.0e-7,
    "kd_m3_per_kg": 5.0,
    "q_max_kg_per_kg": 1.0e-3,
    "k_rate_per_s": 4.0e-4,
}

#: Driving conditions: 1 mg/L of Pb in the sediment porewater, clean bottom
#: water.  ASSUMPTIONS.
PROBE_C_SED = 1.0e-3
PROBE_C_WATER = 0.0

#: ``J_bare = (v + k_film)(C_sed - C_water)``, the uncapped reference.
PROBE_J_BARE = (
    PROBE_COLUMN_KWARGS["seepage_velocity_m_per_s"]
    + PROBE_COLUMN_KWARGS["film_transfer_m_per_s"]
) * (PROBE_C_SED - PROBE_C_WATER)

#: ``J_out / J_bare`` above which the layer counts as broken through.  The
#: numerical probe's definition, kept so the numbers are comparable.
BREAKTHROUGH_RATIO = 0.05


def probe_column(**overrides: Any) -> ColumnParameters:
    """The reference column, with any keyword overridden."""
    return ColumnParameters(**{**PROBE_COLUMN_KWARGS, **overrides})


def run_column(
    params: ColumnParameters,
    years: float,
    dt_s: float,
    *,
    c_sed: float = PROBE_C_SED,
    c_water: float = PROBE_C_WATER,
    initial_sorbed_kg_per_kg: float = 0.0,
    initial_porewater_kg_per_m3: float = 0.0,
    top_conductance_m_per_s: float | None = None,
    sample_years: tuple[float, ...] = (),
) -> dict[str, Any]:
    """March the 1-D column and return the diagnostics the tests assert on.

    Deliberately a plain loop over :func:`solve_column_step` rather than a
    convenience wrapper: the tests must exercise the solver the model uses, not
    a test-only shortcut.
    """
    n_steps = int(round(years * SECONDS_PER_YEAR / dt_s))
    concentration = np.full(params.n_nodes, float(initial_porewater_kg_per_m3))
    sorbed = np.full(params.n_nodes, float(initial_sorbed_kg_per_kg))

    cumulative_in = 0.0
    cumulative_out = 0.0
    clip_total = 0.0
    negative_clip_total = 0.0
    worst_step_residual = 0.0
    breakthrough_years: float | None = None
    previous_ratio = 0.0
    largest_backward_step = 0.0
    samples: dict[float, float] = {}
    ratio = 0.0

    for index in range(n_steps):
        step = solve_column_step(
            concentration,
            sorbed,
            params,
            dt_s,
            c_sed,
            c_water,
            top_conductance_m_per_s=top_conductance_m_per_s,
        )
        concentration = step.porewater_kg_per_m3
        sorbed = step.sorbed_kg_per_kg
        cumulative_in += step.flux_in_kg_per_m2_per_s * dt_s
        cumulative_out += step.flux_out_kg_per_m2_per_s * dt_s
        clip_total += step.clip_correction_kg_per_m2
        negative_clip_total += step.negative_clip_kg_per_m2
        worst_step_residual = max(
            worst_step_residual, abs(step.conservation_residual_kg_per_m2(dt_s))
        )

        bare = (
            params.seepage_velocity_m_per_s + params.film_transfer_m_per_s
        ) * (c_sed - c_water)
        ratio = step.flux_out_kg_per_m2_per_s / bare if bare > 0.0 else 0.0
        largest_backward_step = max(largest_backward_step, previous_ratio - ratio)
        previous_ratio = ratio
        if breakthrough_years is None and ratio > BREAKTHROUGH_RATIO:
            breakthrough_years = (index + 1) * dt_s / SECONDS_PER_YEAR
        elapsed_years = (index + 1) * dt_s / SECONDS_PER_YEAR
        for mark in sample_years:
            if mark not in samples and elapsed_years >= mark:
                samples[mark] = ratio

    stored = stored_kg_per_m2(concentration, sorbed, params)
    residual = cumulative_in - cumulative_out - stored + negative_clip_total
    return {
        "porewater_kg_per_m3": concentration,
        "sorbed_kg_per_kg": sorbed,
        "stored_kg_per_m2": stored,
        "cumulative_in_kg_per_m2": cumulative_in,
        "cumulative_out_kg_per_m2": cumulative_out,
        "clip_correction_kg_per_m2": clip_total,
        "negative_clip_kg_per_m2": negative_clip_total,
        "cumulative_residual_kg_per_m2": residual,
        "relative_residual": abs(residual) / max(cumulative_in, 1e-30),
        "worst_step_residual_kg_per_m2": worst_step_residual,
        "breakthrough_years": breakthrough_years,
        "largest_backward_step": largest_backward_step,
        "final_ratio": ratio,
        "loading_fraction": stored / params.capacity_kg_per_m2
        if params.capacity_kg_per_m2 > 0.0
        else 0.0,
        "samples": samples,
        "n_steps": n_steps,
    }


@pytest.fixture(scope="session")
def start_utc() -> datetime:
    return datetime(2026, 9, 8, tzinfo=timezone.utc)


@pytest.fixture()
def mat_config():
    from reactive_seabed_mat.config import MatLayoutConfig

    return MatLayoutConfig()


@pytest.fixture()
def hotspot_config():
    from reactive_seabed_mat.config import HotspotConfig

    return HotspotConfig()


@pytest.fixture()
def materials(mat_config):
    from reactive_seabed_mat.reactive_layer import build_material_map

    return build_material_map(mat_config)


@pytest.fixture()
def tiles(mat_config, hotspot_config, materials, start_utc):
    from reactive_seabed_mat.reactive_layer import build_tile_states

    return build_tile_states(
        mat_config, start_utc, materials, hotspot=hotspot_config
    )


@pytest.fixture()
def saturated_tiles(mat_config, hotspot_config, materials, start_utc):
    """A mat preloaded to the full allocated Pb capacity of every tile.

    Saturation is reached by an explicit preload, never by inflating an uptake
    parameter: ``MatLayoutConfig.preload_kg_per_m2`` is visible in the exported
    configuration.
    """
    from reactive_seabed_mat.reactive_layer import build_material_map, build_tile_states

    capacity_kg_per_m2 = (
        mat_config.bulk_density_kg_per_m3
        * mat_config.thickness_m
        * materials["Pb"].allocation_fraction
        * materials["Pb"].q_max_kg_per_kg
    )
    loaded = replace(
        mat_config, preload_kg_per_m2={"Pb": capacity_kg_per_m2}
    )
    return build_tile_states(
        loaded, start_utc, build_material_map(loaded), hotspot=hotspot_config
    )
