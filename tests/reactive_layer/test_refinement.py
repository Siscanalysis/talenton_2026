"""Time-step refinement.  This is the test the whole scheme exists to pass.

The previous split-operator layer scheme conserved mass to 1e-14 and was still
wrong: breakthrough moved from 4.21 years at ``dt = 6 h`` to 1.03 years at
``dt = 0.5 h``, and the attenuation curve swung non-monotonically by more than
the entire bare flux.  **A conserving scheme is not automatically a correct
scheme.**  So the acceptance criterion is convergence under refinement, not a
ledger check.

Expected behaviour of the fully implicit coupled scheme, from
``docs/reactive_layer_numerics_probe.py`` and ``REFACTOR_PLAN.md`` section 2:
breakthrough at about 3.09 years, stable from ``dt = 12 h`` down to ``dt = 1 h``,
final loading unchanged, and the attenuation curve monotonic while loading.

This module is the slowest in the suite (four multi-year marches).  The runs are
shared through a module-scoped fixture so each time step is marched once.
"""

from __future__ import annotations

import pytest

from conftest import probe_column, run_column

#: Time steps to refine over, in hours.
REFINEMENT_DT_HOURS = (12.0, 6.0, 3.0, 1.0)

#: Long enough to pass breakthrough at about 3.09 years and settle afterwards.
REFINEMENT_YEARS = 3.4

#: Tolerances, stated here rather than inline so a failure names the claim.
#: Breakthrough must agree across a twelvefold change of time step to better
#: than five days, and the loading to better than a tenth of a per cent.
BREAKTHROUGH_TOLERANCE_YEARS = 5.0 / 365.25
LOADING_TOLERANCE_FRACTION = 1.0e-3


@pytest.fixture(scope="module")
def refinement_runs() -> dict[float, dict]:
    params = probe_column()
    return {
        dt_hours: run_column(
            params,
            years=REFINEMENT_YEARS,
            dt_s=dt_hours * 3600.0,
            sample_years=(1.0, 2.0, 3.0),
        )
        for dt_hours in REFINEMENT_DT_HOURS
    }


def test_breakthrough_time_converges_under_refinement(refinement_runs):
    times = {
        dt_hours: run["breakthrough_years"]
        for dt_hours, run in refinement_runs.items()
    }
    assert all(value is not None for value in times.values()), (
        f"the layer failed to break through within {REFINEMENT_YEARS} years at "
        f"some time step: {times}"
    )
    spread = max(times.values()) - min(times.values())
    assert spread < BREAKTHROUGH_TOLERANCE_YEARS, (
        "breakthrough time is not converged under time-step refinement: "
        f"{ {k: round(v, 4) for k, v in times.items()} }, spread "
        f"{spread * 365.25:.2f} days"
    )
    # And it is the value the model specification and the probe report.
    for dt_hours, value in times.items():
        assert 3.05 < value < 3.13, (
            f"breakthrough at dt = {dt_hours} h is {value:.4f} yr, not the "
            "~3.09 yr the specification documents for these parameters"
        )


def test_final_loading_converges_under_refinement(refinement_runs):
    loadings = {
        dt_hours: run["loading_fraction"] for dt_hours, run in refinement_runs.items()
    }
    spread = max(loadings.values()) - min(loadings.values())
    assert spread < LOADING_TOLERANCE_FRACTION, (
        "final loading is not converged under time-step refinement: "
        f"{ {k: round(v, 6) for k, v in loadings.items()} }"
    )


def test_attenuation_curve_converges_under_refinement(refinement_runs):
    """The whole curve, not only its two end points."""
    for year in (1.0, 2.0, 3.0):
        values = [run["samples"][year] for run in refinement_runs.values()]
        spread = max(values) - min(values)
        assert spread < 2.0e-3, (
            f"J_out / J_bare at {year:.0f} yr is not converged: {values}"
        )


def test_attenuation_never_improves_while_the_layer_is_only_loading(refinement_runs):
    """Monotonicity: while the layer loads, ``J_out / J_bare`` must not fall.

    A layer that is only taking metal up cannot get better at holding it back.
    A backward step means the scheme, not the physics, is moving the answer.
    """
    for dt_hours, run in refinement_runs.items():
        assert run["largest_backward_step"] <= 1.0e-12, (
            f"at dt = {dt_hours} h the residual flux ratio fell by "
            f"{run['largest_backward_step']:.3e} while the layer was loading"
        )


def test_mass_is_conserved_at_every_refined_time_step(refinement_runs):
    """Conservation holds at each step too, which is exactly why it proves
    nothing on its own: the rejected scheme passed this and failed the tests
    above."""
    for dt_hours, run in refinement_runs.items():
        assert run["relative_residual"] < 1.0e-9, (
            f"at dt = {dt_hours} h the ledger did not close: "
            f"{run['relative_residual']:.3e}"
        )
