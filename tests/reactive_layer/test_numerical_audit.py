"""Independent transport/sorption oracles and discontinuity classification.

These checks complement conservation: a closed ledger cannot detect an
incorrect equation or a numerically smeared concentration history.
"""

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from conftest import probe_column
from reactive_seabed_mat.reactive_layer.column import (
    bottom_conductance,
    discrete_steady_state_flux_kg_per_m2_per_s,
    solve_column_step,
    steady_state_flux_kg_per_m2_per_s,
    top_conductance,
)


def _face_fluxes(c, params, c_sed, c_water, g_bot, g_top):
    """Assemble physical face fluxes independently of the banded matrix."""
    flux = np.empty(params.n_nodes + 1)
    v = params.seepage_velocity_m_per_s
    flux[0] = v * c_sed + g_bot * (c_sed - c[0])
    flux[1:-1] = v * c[:-1] - params.porosity * params.d_eff_m2_per_s * np.diff(c) / params.dz_m
    flux[-1] = v * c[-1] + g_top * (c[-1] - c_water)
    return flux


@pytest.mark.parametrize("n_nodes", [1, 5, 40])
@pytest.mark.parametrize("velocity", [0.0, 3.0e-8])
def test_discrete_barrier_matches_independent_face_balance(n_nodes, velocity):
    p = probe_column(n_nodes=n_nodes, seepage_velocity_m_per_s=velocity, q_max_kg_per_kg=0.0)
    g_bot, g_top = 0.3 * bottom_conductance(p), 0.2 * top_conductance(p)
    c_sed, c_water = 1.0e-3, 2.0e-4

    def rate(c):
        return -np.diff(_face_fluxes(c, p, c_sed, c_water, g_bot, g_top)) / p.dz_m

    source = rate(np.zeros(n_nodes))
    matrix = np.column_stack([rate(row) - source for row in np.eye(n_nodes)])
    stationary = np.linalg.solve(matrix, -source)
    fluxes = _face_fluxes(stationary, p, c_sed, c_water, g_bot, g_top)
    reported = discrete_steady_state_flux_kg_per_m2_per_s(
        p, c_sed, c_water, top_conductance_m_per_s=g_top, bottom_conductance_m_per_s=g_bot
    )
    np.testing.assert_allclose(fluxes, reported, rtol=2e-11, atol=1e-24)
    # A stationary control must remain stationary under the actual integrator.
    step = solve_column_step(stationary, np.zeros(n_nodes), p, 21600.0, c_sed, c_water,
                             top_conductance_m_per_s=g_top, bottom_conductance_m_per_s=g_bot)
    np.testing.assert_allclose(step.porewater_kg_per_m3, stationary, rtol=2e-11)
    assert step.flux_out_kg_per_m2_per_s == pytest.approx(reported, rel=2e-11)


def test_barrier_spatial_refinement_converges_to_continuum():
    exact = steady_state_flux_kg_per_m2_per_s(probe_column(), 1.0e-3)
    errors = []
    for nodes in (20, 40, 80, 160):
        flux = discrete_steady_state_flux_kg_per_m2_per_s(probe_column(n_nodes=nodes), 1.0e-3)
        errors.append(abs(flux / exact - 1.0))
    assert all(fine < 0.6 * coarse for coarse, fine in zip(errors, errors[1:])), errors
    assert errors[-1] < 0.003


def test_nonlinear_transient_converges_to_independent_bdf_integration():
    # Deliberately small capacity advances the sorption front during a short
    # check; these are test parameters, not revised material assumptions.
    p = probe_column(n_nodes=8, q_max_kg_per_kg=1e-5)
    n = p.n_nodes
    g_bot, g_top = bottom_conductance(p), top_conductance(p)
    duration = 14.0 * 86400.0

    def rate(t, state):
        c, q = state[:n], state[n:]
        # The same stated constitutive law; the spatial divergence and coupled
        # evolution are integrated independently with adaptive BDF, not the
        # production branch elimination or backward-Euler matrix assembly.
        dq = p.k_rate_per_s * (np.minimum(p.kd_m3_per_kg * c, p.q_max_kg_per_kg) - q)
        dq[q >= p.q_max_kg_per_kg] = 0.0
        flux = _face_fluxes(c, p, 1e-3, 0.0, g_bot, g_top)
        dc = (-np.diff(flux) / p.dz_m - p.bulk_density_kg_per_m3 * dq) / p.porosity
        return np.concatenate([dc, dq])

    marks = np.arange(1, 15) * 86400.0
    reference = solve_ivp(rate, (0, duration), np.zeros(2*n), method="BDF",
                          t_eval=marks, rtol=2e-9, atol=1e-14)
    assert reference.success, reference.message
    errors = []
    for dt in (21600.0, 10800.0, 5400.0):
        c, q = np.zeros(n), np.zeros(n)
        snapshots = []
        for index in range(int(duration / dt)):
            step = solve_column_step(c, q, p, dt, 1e-3, 0.0)
            assert step.picard_converged
            assert step.clip_correction_kg_per_m2 == 0.0
            assert step.negative_clip_kg_per_m2 == 0.0
            c, q = step.porewater_kg_per_m3, step.sorbed_kg_per_kg
            if (index + 1) % int(86400 / dt) == 0:
                snapshots.append(np.concatenate([c / 1e-3, q / p.q_max_kg_per_kg]))
        scaled_reference = reference.y / np.concatenate([np.full(n, 1e-3), np.full(n, p.q_max_kg_per_kg)])[:, None]
        errors.append(float(np.max(np.abs(np.array(snapshots).T - scaled_reference))))
    assert all(fine < 0.7 * coarse for coarse, fine in zip(errors, errors[1:])), errors
    assert errors[-1] < 0.06, errors


def test_capacity_lock_is_a_documented_discontinuous_modelling_assumption():
    # A clean-water flush desorbs a cell just below capacity, whereas exactly
    # full cells are held. This finite jump is in the law, not a plotting bug.
    p = probe_column(n_nodes=1)
    held = solve_column_step(np.zeros(1), np.array([p.q_max_kg_per_kg]), p, 21600, 0, 0)
    below = solve_column_step(np.zeros(1), np.array([p.q_max_kg_per_kg * (1-1e-10)]), p, 21600, 0, 0)
    assert held.sorbed_kg_per_kg[0] == p.q_max_kg_per_kg
    assert held.flux_out_kg_per_m2_per_s == 0.0
    assert below.sorbed_kg_per_kg[0] < p.q_max_kg_per_kg * (1-1e-10)
    assert below.flux_out_kg_per_m2_per_s > 0.0
    assert abs(below.conservation_residual_kg_per_m2(21600)) < 1e-17


def test_unconverged_sorption_is_refused_instead_of_corrected_by_clipping():
    p = probe_column()
    with pytest.raises(RuntimeError, match="sorption branches did not converge"):
        solve_column_step(np.zeros(p.n_nodes), np.zeros(p.n_nodes), p,
                          10.0 * 86400, 1e-3, 0, picard_iterations=1)


def test_source_step_changes_ratio_without_an_instantaneous_inventory_jump():
    p = probe_column(n_nodes=8, q_max_kg_per_kg=0.0)
    c, q = np.zeros(p.n_nodes), np.zeros(p.n_nodes)
    for _ in range(56):
        step = solve_column_step(c, q, p, 21600, 1e-3, 0)
        c, q = step.porewater_kg_per_m3, step.sorbed_kg_per_kg
    old = solve_column_step(c, q, p, 0, 1e-3, 0)
    new = solve_column_step(c, q, p, 0, 1e-4, 0)
    assert new.flux_out_kg_per_m2_per_s == old.flux_out_kg_per_m2_per_s
    np.testing.assert_array_equal(new.porewater_kg_per_m3, old.porewater_kg_per_m3)
    old_ratio = old.flux_out_kg_per_m2_per_s / ((p.seepage_velocity_m_per_s + p.film_transfer_m_per_s) * 1e-3)
    new_ratio = new.flux_out_kg_per_m2_per_s / ((p.seepage_velocity_m_per_s + p.film_transfer_m_per_s) * 1e-4)
    assert new_ratio == pytest.approx(10 * old_ratio)
    # The outgoing concentration has memory; the reference denominator has
    # stepped immediately. A bump in an attenuation ratio is expected here.


def test_continuum_oracle_keeps_advection_and_handles_high_peclet_number():
    p = probe_column()
    assert steady_state_flux_kg_per_m2_per_s(p, 1e-3, 1e-3) == pytest.approx(p.seepage_velocity_m_per_s * 1e-3)
    from dataclasses import replace
    for diffusivity in (1e-20, 0.0):
        pure_advection = replace(p, d_eff_m2_per_s=diffusivity)
        assert steady_state_flux_kg_per_m2_per_s(pure_advection, 1e-3) == pytest.approx(p.seepage_velocity_m_per_s * 1e-3)
