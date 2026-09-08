"""Per-unit-area mass conservation of the 1-D reactive layer.

``docs/MODEL_SPEC.md`` section 3::

    d/dt integral_0^L (theta C + rho_b q) dz = J_in - J_out

Conservation is necessary and **not sufficient**: the operator-split scheme this
one replaced conserved mass to 1e-14 and still diverged under refinement.  The
refinement test in ``test_refinement.py`` is the one that decides whether the
scheme is right; this one only checks the ledger closes.
"""

from __future__ import annotations

import numpy as np

from conftest import (
    PROBE_C_SED,
    PROBE_C_WATER,
    probe_column,
    run_column,
)


def test_multi_year_mass_conservation_per_unit_area():
    """Six years at dt = 12 h: what went in, minus what came out, is what is held."""
    params = probe_column()
    result = run_column(params, years=6.0, dt_s=12.0 * 3600.0)

    assert result["relative_residual"] < 1.0e-9, (
        "cumulative ledger does not close: "
        f"in={result['cumulative_in_kg_per_m2']:.6e} "
        f"out={result['cumulative_out_kg_per_m2']:.6e} "
        f"stored={result['stored_kg_per_m2']:.6e} "
        f"relative residual={result['relative_residual']:.3e}"
    )
    # The per-step balance is the stronger statement: every single step
    # telescopes exactly, so no error is being cancelled by a later one.  The
    # residual is scaled by the layer's capacity, which is the only meaningful
    # yardstick for an absolute mass in kg/m2.
    worst_relative = (
        result["worst_step_residual_kg_per_m2"] / params.capacity_kg_per_m2
    )
    assert worst_relative < 1.0e-12, (
        "a single step failed to balance: "
        f"{result['worst_step_residual_kg_per_m2']:.3e} kg/m2, "
        f"{worst_relative:.3e} of the layer capacity"
    )
    assert result["cumulative_in_kg_per_m2"] > 0.0
    assert result["stored_kg_per_m2"] > 0.0


def test_no_silent_numerical_correction_in_the_reference_run():
    """The reference run needs no clipping at all, and says so either way."""
    params = probe_column()
    result = run_column(params, years=6.0, dt_s=6.0 * 3600.0)
    assert result["clip_correction_kg_per_m2"] == 0.0
    assert result["negative_clip_kg_per_m2"] == 0.0


def test_capacity_clipping_returns_mass_to_the_porewater():
    """When clipping does happen it moves mass, it never deletes it.

    Driven deliberately hard: the layer starts within a whisker of capacity and
    sees a concentration far above the isotherm knee, so the sorbed update
    overshoots and the excess has to go somewhere.
    """
    from reactive_seabed_mat.reactive_layer.column import solve_column_step, stored_kg_per_m2

    params = probe_column(k_rate_per_s=1.0e-2)
    q_max = params.q_max_kg_per_kg
    concentration = np.full(params.n_nodes, 1.0e-2)
    sorbed = np.full(params.n_nodes, q_max * (1.0 - 1.0e-9))
    before = stored_kg_per_m2(concentration, sorbed, params)

    dt = 6.0 * 3600.0
    step = solve_column_step(
        concentration, sorbed, params, dt, PROBE_C_SED, PROBE_C_WATER
    )

    assert np.all(step.sorbed_kg_per_kg <= q_max * (1.0 + 1e-15))
    residual = step.conservation_residual_kg_per_m2(dt)
    assert abs(residual) < 1.0e-18, (
        f"clipping lost or invented mass: residual {residual:.3e} kg/m2"
    )
    assert step.stored_before_kg_per_m2 == before
    if step.clip_correction_kg_per_m2 > 0.0:
        assert any(
            entry["kind"].startswith("negative") or "clipped" in entry["kind"]
            for entry in step.diagnostics["corrections"]
        ) or step.diagnostics["clip_correction_kg_per_m2"] > 0.0


def test_zero_time_step_changes_nothing():
    from reactive_seabed_mat.reactive_layer.column import solve_column_step

    params = probe_column()
    concentration = np.linspace(1.0e-4, 0.0, params.n_nodes)
    sorbed = np.linspace(5.0e-4, 0.0, params.n_nodes)
    step = solve_column_step(
        concentration, sorbed, params, 0.0, PROBE_C_SED, PROBE_C_WATER
    )
    assert np.array_equal(step.porewater_kg_per_m3, concentration)
    assert np.array_equal(step.sorbed_kg_per_kg, sorbed)
    assert step.stored_delta_kg_per_m2 == 0.0
