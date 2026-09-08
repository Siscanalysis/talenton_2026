"""Limiting cases, and the honest form of the attenuation claim.

MODEL_SPEC section 12: zero capacity gives zero retention; zero source gives no
metal anywhere; an intact fresh mat attenuates and a saturated one attenuates
less; ``J_out == J_bare`` where there is no mat.

One deviation from the branch brief is recorded here rather than buried in a
handoff, because it is a physical claim.  The brief asked for
"zero capacity (q_max = 0) gives zero retention **and J_out == J_bare**".  The
first half holds exactly.  The second half is false for this product: a layer
with no chemical capacity is still 10 mm of low-permeability medium, and with
the documented parameters it still attenuates by about 94 %.  ``J_out == J_bare``
is the correct statement for a seabed cell with **no mat on it** (a displaced
tile, or an uncovered part of the hotspot), and it is asserted in that form in
``test_degradation.py``.  Asserting it for a zero-capacity layer would require
either deleting the layer's transport resistance or quietly redefining
``J_bare``, and both would make the demonstrator claim something untrue.
"""

from __future__ import annotations

import numpy as np

from conftest import (
    PROBE_C_SED,
    PROBE_C_WATER,
    PROBE_J_BARE,
    probe_column,
    run_column,
)

#: Long enough for the layer to reach its transport steady state (the diffusive
#: time through 10 mm is about 6 days and the advective transit about 2 days).
SETTLE_YEARS = 0.6


def test_zero_capacity_gives_exactly_zero_retention():
    """``q_max = 0``: nothing is ever sorbed, and the porewater is all there is."""
    params = probe_column(q_max_kg_per_kg=0.0)
    result = run_column(params, years=SETTLE_YEARS, dt_s=6.0 * 3600.0)

    assert np.all(result["sorbed_kg_per_kg"] == 0.0), (
        "a layer with no capacity retained something on the solid"
    )
    # The only inventory left is the dissolved pool inside the pore space, and
    # it is tiny compared with a loaded layer's sorbed inventory.
    dissolved = result["stored_kg_per_m2"]
    assert dissolved > 0.0
    assert dissolved < 1.0e-3 * probe_column().capacity_kg_per_m2


def test_zero_capacity_contributes_no_chemistry_but_still_is_a_barrier():
    """The honest form of the "no chemical contribution" claim.

    A zero-capacity layer must pass exactly what a fully saturated layer passes:
    both have nothing left to give chemically.  It must **not** pass the bare
    flux, because the medium is still there.
    """
    zero_capacity = run_column(
        probe_column(q_max_kg_per_kg=0.0), years=SETTLE_YEARS, dt_s=6.0 * 3600.0
    )
    saturated = run_column(
        probe_column(),
        years=SETTLE_YEARS,
        dt_s=6.0 * 3600.0,
        initial_sorbed_kg_per_kg=probe_column().q_max_kg_per_kg,
    )

    assert zero_capacity["final_ratio"] == saturated["final_ratio"], (
        "a layer with no capacity and a layer with none left should pass the "
        f"same flux: {zero_capacity['final_ratio']:.9f} vs "
        f"{saturated['final_ratio']:.9f}"
    )
    assert zero_capacity["final_ratio"] < 0.1, (
        "the layer stopped being a physical barrier, which the geometry says "
        "it cannot"
    )
    assert zero_capacity["final_ratio"] > 0.0


def test_zero_source_creates_no_metal_anywhere():
    params = probe_column()
    result = run_column(
        params, years=1.0, dt_s=12.0 * 3600.0, c_sed=0.0, c_water=0.0
    )
    assert np.all(result["porewater_kg_per_m3"] == 0.0)
    assert np.all(result["sorbed_kg_per_kg"] == 0.0)
    assert result["stored_kg_per_m2"] == 0.0
    assert result["cumulative_in_kg_per_m2"] == 0.0
    assert result["cumulative_out_kg_per_m2"] == 0.0


def test_fresh_mat_attenuates_by_more_than_99_percent():
    for years in (0.25, 1.0, 2.0):
        result = run_column(probe_column(), years=years, dt_s=6.0 * 3600.0)
        attenuation = 1.0 - result["final_ratio"]
        assert attenuation > 0.99, (
            f"after {years} yr, well before breakthrough, attenuation is "
            f"{attenuation:.5f}"
        )


def test_saturated_mat_still_attenuates_as_a_pure_barrier():
    """About 94 %, and the number is asserted rather than described."""
    params = probe_column()
    saturated = run_column(
        params,
        years=SETTLE_YEARS,
        dt_s=6.0 * 3600.0,
        initial_sorbed_kg_per_kg=params.q_max_kg_per_kg,
    )
    attenuation = 1.0 - saturated["final_ratio"]
    assert 0.93 < attenuation < 0.95, (
        f"a saturated layer attenuates by {attenuation:.4f}, not the ~0.94 the "
        "specification documents"
    )
    # Sorbed mass is held, not released: a full cell neither takes up nor
    # gives back (MODEL_SPEC section 4, mode 2).
    assert np.allclose(saturated["sorbed_kg_per_kg"], params.q_max_kg_per_kg)


def test_the_chemical_contribution_is_the_difference_and_it_is_small():
    """The claim the demonstrator is allowed to make.

    Fresh attenuation is above 99 % and saturated attenuation is about 94 %, so
    the sorbent buys roughly five points of attenuation and, far more
    importantly, the *time* before the layer reaches the second number.  Quoting
    99 % as "what the sorbent does" would be wrong, and this test is what stops
    that number being quoted alone.
    """
    params = probe_column()
    fresh = run_column(params, years=1.0, dt_s=6.0 * 3600.0)
    saturated = run_column(
        params,
        years=SETTLE_YEARS,
        dt_s=6.0 * 3600.0,
        initial_sorbed_kg_per_kg=params.q_max_kg_per_kg,
    )
    fresh_attenuation = 1.0 - fresh["final_ratio"]
    barrier_attenuation = 1.0 - saturated["final_ratio"]
    chemical = fresh_attenuation - barrier_attenuation

    assert fresh_attenuation > 0.99
    assert 0.93 < barrier_attenuation < 0.95
    assert 0.04 < chemical < 0.07, (
        f"the chemical contribution is {chemical:.4f}, outside the range the "
        "documented parameters give"
    )


def test_the_analytic_barrier_flux_agrees_with_the_solver():
    """A continuum sanity check on the saturated case, to order dz.

    ``steady_state_flux_kg_per_m2_per_s`` is a closed form for a non-sorbing
    layer.  It folds the top half cell into the layer rather than into the
    discrete ``g_top``, so it agrees with the solver only to order ``dz``; that
    limitation is asserted rather than hidden behind a loose tolerance.
    """
    from reactive_seabed_mat.reactive_layer.column import (
        steady_state_flux_kg_per_m2_per_s,
    )

    params = probe_column()
    saturated = run_column(
        params,
        years=SETTLE_YEARS,
        dt_s=6.0 * 3600.0,
        initial_sorbed_kg_per_kg=params.q_max_kg_per_kg,
    )
    solver_flux = saturated["final_ratio"] * PROBE_J_BARE
    analytic = steady_state_flux_kg_per_m2_per_s(params, PROBE_C_SED, PROBE_C_WATER)
    relative = abs(solver_flux - analytic) / analytic
    assert relative < 0.02, (
        f"solver {solver_flux:.6e} vs analytic {analytic:.6e}, relative "
        f"difference {relative:.4f}"
    )
