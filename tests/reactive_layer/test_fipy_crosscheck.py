"""Independent cross-check of the layer solver against a FiPy ``Grid1D`` solve.

FiPy is the repository's 2-D engine.  Using it as the **oracle** for the 1-D
layer as well is a stronger position than using one solver for both: the layer
is solved by a hand-written banded implicit scheme and checked against a
mature, independent finite-volume implementation of the same discrete operator.

The case is pure diffusion (no advection, no sorption), because that is the part
both codes can express identically:

* interior faces: ``theta D (C_{i+1} - C_i) / dz`` on both sides;
* sediment face: a Dirichlet value half a cell below node 0, which is what
  ``CellVariable.constrain`` on ``facesLeft`` gives;
* water face: no diffusive face flux, and instead the benthic-film sink
  ``g_top (C_last - C_water)`` applied on the last cell, which is an implicit
  source term in FiPy.

FiPy's LU solver does iterative refinement and stops at a default tolerance that
leaves about 1e-3 relative error on this stiff matrix, so the tolerance is
tightened explicitly.  That is a property of the oracle's stopping rule, not of
either discretisation, and it is stated here rather than hidden in a loose
assertion.
"""

from __future__ import annotations

import numpy as np
import pytest

from conftest import probe_column

fipy = pytest.importorskip("fipy", reason="FiPy is the cross-check oracle")

from fipy import (  # noqa: E402
    CellVariable,
    DiffusionTerm,
    Grid1D,
    ImplicitSourceTerm,
    TransientTerm,
)
from fipy.solvers.scipy import LinearLUSolver  # noqa: E402

from reactive_seabed_mat.reactive_layer.column import (  # noqa: E402
    solve_column_step,
    top_conductance,
)

C_SED = 1.0e-3
C_WATER = 0.0
N_STEPS = 200
DT_S = 3600.0


def test_pure_diffusion_matches_a_fipy_grid1d_solve():
    params = probe_column(
        seepage_velocity_m_per_s=0.0,
        kd_m3_per_kg=0.0,
        q_max_kg_per_kg=0.0,
        k_rate_per_s=0.0,
    )
    dz = params.dz_m
    g_top = top_conductance(params)

    mesh = Grid1D(nx=params.n_nodes, dx=dz)
    fipy_c = CellVariable(mesh=mesh, value=0.0)
    fipy_c.constrain(C_SED, mesh.facesLeft)
    last_cell = CellVariable(mesh=mesh, value=0.0)
    last_cell.value[-1] = 1.0
    equation = (
        TransientTerm(coeff=params.porosity)
        == DiffusionTerm(coeff=params.porosity * params.d_eff_m2_per_s)
        - ImplicitSourceTerm(coeff=g_top / dz * last_cell)
        + g_top * C_WATER / dz * last_cell
    )
    # Direct LU with refinement driven to round-off; see the module docstring.
    solver = LinearLUSolver(tolerance=1.0e-16, iterations=50)

    concentration = np.zeros(params.n_nodes)
    sorbed = np.zeros(params.n_nodes)
    for _ in range(N_STEPS):
        step = solve_column_step(
            concentration, sorbed, params, DT_S, C_SED, C_WATER
        )
        concentration = step.porewater_kg_per_m3
        sorbed = step.sorbed_kg_per_kg
        equation.solve(var=fipy_c, dt=DT_S, solver=solver)

    reference = np.asarray(fipy_c.value, dtype=float)
    relative = np.max(
        np.abs(concentration - reference) / np.maximum(np.abs(reference), 1e-300)
    )
    assert relative < 1.0e-12, (
        f"the layer solver and FiPy disagree by {relative:.3e} relative after "
        f"{N_STEPS} steps of pure diffusion"
    )
    # A non-sorbing column must hold nothing on the solid.
    assert np.all(sorbed == 0.0)


def test_the_cross_check_would_notice_a_wrong_boundary():
    """The oracle is only worth having if it can fail.

    The same comparison with a deliberately wrong top conductance must be
    rejected, which shows the 1e-12 agreement above is a real constraint and
    not two codes agreeing about nothing.
    """
    params = probe_column(
        seepage_velocity_m_per_s=0.0,
        kd_m3_per_kg=0.0,
        q_max_kg_per_kg=0.0,
        k_rate_per_s=0.0,
    )
    dz = params.dz_m
    g_top = top_conductance(params)

    mesh = Grid1D(nx=params.n_nodes, dx=dz)
    fipy_c = CellVariable(mesh=mesh, value=0.0)
    fipy_c.constrain(C_SED, mesh.facesLeft)
    last_cell = CellVariable(mesh=mesh, value=0.0)
    last_cell.value[-1] = 1.0
    equation = (
        TransientTerm(coeff=params.porosity)
        == DiffusionTerm(coeff=params.porosity * params.d_eff_m2_per_s)
        - ImplicitSourceTerm(coeff=2.0 * g_top / dz * last_cell)
    )
    solver = LinearLUSolver(tolerance=1.0e-16, iterations=50)

    concentration = np.zeros(params.n_nodes)
    sorbed = np.zeros(params.n_nodes)
    for _ in range(40):
        step = solve_column_step(
            concentration, sorbed, params, DT_S, C_SED, C_WATER
        )
        concentration = step.porewater_kg_per_m3
        sorbed = step.sorbed_kg_per_kg
        equation.solve(var=fipy_c, dt=DT_S, solver=solver)

    reference = np.asarray(fipy_c.value, dtype=float)
    relative = np.max(
        np.abs(concentration - reference) / np.maximum(np.abs(reference), 1e-300)
    )
    assert relative > 1.0e-6, (
        "doubling the benthic-film conductance in the oracle changed nothing, "
        "so the cross-check is not actually constraining the boundary"
    )
