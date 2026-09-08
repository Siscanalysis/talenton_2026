"""Numerical acceptance tests for the 2-D coastal engine.

``docs/MODEL_SPEC.md`` sections 6 and 12.  Every tolerance below is stated in
the assertion, not hidden in a helper, because a conserving scheme is not
automatically a correct scheme: the refinement checks matter as much as the
ledger checks.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from reactive_seabed_mat.contracts import Element, SeabedSourceField
from reactive_seabed_mat.coastal_transport.fipy_engine import (
    accumulate_ledger,
    step_ledger,
    transport_step,
)

from conftest import make_field, make_forcing, make_grid

PB = Element.PB.value
HG = Element.HG.value
START = datetime(2026, 9, 8, tzinfo=timezone.utc)


def zero_source(grid, elements=(PB,), time_utc=START) -> SeabedSourceField:
    return SeabedSourceField(
        time_utc=time_utc,
        flux_kg_per_m2_per_s={
            name: np.zeros((grid.ny, grid.nx)) for name in elements
        },
    )


def uniform_source(grid, flux, cells, elements=(PB,), time_utc=START) -> SeabedSourceField:
    """A uniform areal flux over the listed ``(ix, iy)`` cells."""
    arrays = {}
    for name in elements:
        array = np.zeros((grid.ny, grid.nx))
        for ix, iy in cells:
            array[iy, ix] = flux
        arrays[name] = array
    return SeabedSourceField(time_utc=time_utc, flux_kg_per_m2_per_s=arrays)


def centroid_x(field, element=PB) -> float:
    grid = field.grid
    c = np.asarray(field.concentration_kg_per_m3[element])
    total = c.sum()
    assert total > 0.0
    x = grid.origin_x_m + (np.arange(grid.nx) + 0.5) * grid.dx_m
    return float((c.sum(axis=0) * x).sum() / total)


def variance_x(field, element=PB) -> float:
    grid = field.grid
    c = np.asarray(field.concentration_kg_per_m3[element])
    weights = c.sum(axis=0)
    total = weights.sum()
    x = grid.origin_x_m + (np.arange(grid.nx) + 0.5) * grid.dx_m
    mean = float((weights * x).sum() / total)
    return float((weights * (x - mean) ** 2).sum() / total)


# ---------------------------------------------------------------------------
# 1. Nothing from nothing
# ---------------------------------------------------------------------------

def test_zero_source_and_zero_field_stays_exactly_zero():
    grid = make_grid()
    field = make_field(grid)
    forcing = make_forcing(grid, u=0.07, v=0.03, diffusivity_m2_per_s=0.6)
    step = transport_step(field, forcing, zero_source(grid), 300.0)
    result = np.asarray(step.new_field.concentration_kg_per_m3[PB])
    assert np.array_equal(result, np.zeros_like(result))
    assert step.released_from_seabed_kg[PB] == 0.0
    assert step.boundary_out_kg[PB] == 0.0
    assert step.boundary_in_kg[PB] == 0.0
    assert step.diagnostics["clip_correction_kg"][PB] == 0.0


# ---------------------------------------------------------------------------
# 2. Closed domain conserves mass
# ---------------------------------------------------------------------------

def test_closed_domain_conserves_mass_to_1e_12_relative():
    """A land ring makes every water face interior, so nothing can leave."""
    grid = make_grid(nx=20, ny=16)
    land = np.zeros((grid.ny, grid.nx), dtype=bool)
    land[0, :] = land[-1, :] = True
    land[:, 0] = land[:, -1] = True
    c0 = np.zeros((grid.ny, grid.nx))
    c0[8, 6] = 1.0e-3
    field = make_field(grid, land_mask=land, concentration={PB: c0})
    forcing = make_forcing(grid, u=0.05, v=0.02, diffusivity_m2_per_s=0.6,
                           land_mask=land)
    source = zero_source(grid)
    start_mass = field.water_mass_kg(PB)
    steps = []
    for _ in range(30):
        step = transport_step(field, forcing, source, 300.0)
        steps.append(step)
        field = step.new_field
    end_mass = field.water_mass_kg(PB)
    assert abs(end_mass - start_mass) / start_mass < 1e-12
    assert sum(s.boundary_out_kg[PB] for s in steps) / start_mass < 1e-12
    ledger = accumulate_ledger(PB, make_field(grid, land_mask=land,
                                              concentration={PB: c0}), steps)
    assert abs(ledger.relative_imbalance) < 1e-12
    # nothing may sit on a land cell
    assert float(np.asarray(field.concentration_kg_per_m3[PB])[land].sum()) == 0.0


# ---------------------------------------------------------------------------
# 3. Source normalisation
# ---------------------------------------------------------------------------

def test_uniform_source_injects_J_times_A_times_N_times_dt():
    grid = make_grid(nx=20, ny=16)
    land = np.zeros((grid.ny, grid.nx), dtype=bool)
    land[0, :] = land[-1, :] = True
    land[:, 0] = land[:, -1] = True
    field = make_field(grid, land_mask=land)
    forcing = make_forcing(grid, u=0.0, v=0.0, diffusivity_m2_per_s=0.3,
                           land_mask=land)
    cells = [(ix, iy) for iy in range(7, 10) for ix in range(8, 11)]
    flux = 4.0e-10
    source = uniform_source(grid, flux, cells)
    dt, n_steps = 300.0, 24
    for _ in range(n_steps):
        field = transport_step(field, forcing, source, dt).new_field
    expected = flux * len(cells) * grid.cell_area_m2 * n_steps * dt
    got = field.water_mass_kg(PB)
    assert got == pytest.approx(expected, rel=1e-12)


def test_source_on_a_land_cell_is_reported_not_released():
    grid = make_grid(nx=12, ny=10)
    land = np.zeros((grid.ny, grid.nx), dtype=bool)
    land[2, 3] = True
    field = make_field(grid, land_mask=land)
    forcing = make_forcing(grid, diffusivity_m2_per_s=0.1, land_mask=land)
    source = uniform_source(grid, 1.0e-9, [(3, 2)])
    step = transport_step(field, forcing, source, 300.0)
    assert step.released_from_seabed_kg[PB] == 0.0
    assert step.diagnostics["source_on_land_kg"][PB] > 0.0
    assert "source flux was supplied on land" in step.diagnostics["notes"]


# ---------------------------------------------------------------------------
# 4. Known benchmarks
#
# Both benchmarks are run in a CLOSED basin (a ring of land cells) with the
# plume kept many standard deviations from every wall.  The analytic results
# hold for an unbounded domain, so any wall contact would be measuring the
# boundary rather than the scheme.  Under those conditions the finite-volume
# discretisation reproduces both moments essentially exactly, which is why the
# tolerances below are so tight: a looser tolerance here would hide a real
# scheme error rather than allow for one.
# ---------------------------------------------------------------------------

def land_ring(grid) -> np.ndarray:
    land = np.zeros((grid.ny, grid.nx), dtype=bool)
    land[0, :] = land[-1, :] = True
    land[:, 0] = land[:, -1] = True
    return land


def test_advection_benchmark_centroid_travels_u_times_t():
    grid = make_grid(nx=100, ny=14)
    land = land_ring(grid)
    c0 = np.zeros((grid.ny, grid.nx))
    c0[7, 30] = 1.0e-3
    field = make_field(grid, land_mask=land, concentration={PB: c0})
    u = 0.05
    forcing = make_forcing(grid, u=u, diffusivity_m2_per_s=0.5, land_mask=land)
    x0 = centroid_x(field)
    dt, n_steps = 100.0, 30
    for _ in range(n_steps):
        field = transport_step(field, forcing, zero_source(grid), dt).new_field
    travelled = centroid_x(field) - x0
    # measured 3.1e-11 relative on this configuration
    assert travelled == pytest.approx(u * dt * n_steps, rel=1e-6)
    # the plume must still be far from the walls, or the benchmark is void
    assert np.sqrt(variance_x(field)) < 0.25 * grid.nx * grid.dx_m


def test_diffusion_benchmark_variance_grows_as_two_D_t():
    grid = make_grid(nx=60, ny=60)
    land = land_ring(grid)
    c0 = np.zeros((grid.ny, grid.nx))
    c0[30, 30] = 1.0e-3
    field = make_field(grid, land_mask=land, concentration={PB: c0})
    diffusivity = 0.6
    forcing = make_forcing(grid, diffusivity_m2_per_s=diffusivity, land_mask=land)
    dt, n_steps = 100.0, 13
    for _ in range(n_steps):
        field = transport_step(field, forcing, zero_source(grid), dt).new_field
    elapsed = dt * n_steps
    # measured 4.7e-8 relative on this configuration
    assert variance_x(field) == pytest.approx(2.0 * diffusivity * elapsed, rel=1e-5)


# ---------------------------------------------------------------------------
# 5. Boundary export accounting
# ---------------------------------------------------------------------------

def test_boundary_export_accounting_closes():
    grid = make_grid(nx=24, ny=16)
    c0 = np.zeros((grid.ny, grid.nx))
    c0[8, 4] = 2.0e-3
    field = make_field(grid, concentration={PB: c0})
    forcing = make_forcing(grid, u=0.08, v=0.01, diffusivity_m2_per_s=0.6)
    start_mass = field.water_mass_kg(PB)
    exported = 0.0
    worst_closure = 0.0
    for _ in range(60):
        step = transport_step(field, forcing, zero_source(grid), 300.0)
        exported += step.boundary_out_kg[PB]
        worst_closure = max(
            worst_closure, abs(step.diagnostics["closure_error_kg"][PB])
        )
        field = step.new_field
    assert exported > 0.3 * start_mass, "the plume should genuinely leave"
    assert worst_closure / start_mass < 1e-12
    assert field.water_mass_kg(PB) + exported == pytest.approx(start_mass, rel=1e-12)


def test_closure_error_is_reported_per_element():
    grid = make_grid(nx=16, ny=12)
    field = make_field(grid, elements=(PB, HG))
    forcing = make_forcing(grid, u=0.05, diffusivity_m2_per_s=0.4)
    source = uniform_source(grid, 5.0e-10, [(6, 6)], elements=(PB, HG))
    step = transport_step(field, forcing, source, 300.0)
    assert set(step.diagnostics["closure_error_kg"]) == {PB, HG}
    assert set(step.diagnostics["clip_correction_kg"]) == {PB, HG}


# ---------------------------------------------------------------------------
# 6. Current reversal
# ---------------------------------------------------------------------------

def test_current_reversal_moves_the_centroid_back():
    grid = make_grid(nx=100, ny=14)
    land = land_ring(grid)
    c0 = np.zeros((grid.ny, grid.nx))
    c0[7, 50] = 1.0e-3
    field = make_field(grid, land_mask=land, concentration={PB: c0})
    source = zero_source(grid)
    dt, u = 100.0, 0.05
    x_start = centroid_x(field)
    forward = make_forcing(grid, u=u, diffusivity_m2_per_s=0.5, land_mask=land)
    for _ in range(30):
        field = transport_step(field, forward, source, dt).new_field
    x_forward = centroid_x(field)
    backward = make_forcing(grid, u=-u, diffusivity_m2_per_s=0.5, land_mask=land)
    for _ in range(30):
        field = transport_step(field, backward, source, dt).new_field
    x_back = centroid_x(field)
    assert x_forward - x_start == pytest.approx(u * dt * 30, rel=1e-4)
    assert x_back < x_forward
    # measured 3e-4 m of residual offset on this configuration
    assert x_back == pytest.approx(x_start, abs=0.05 * grid.dx_m)


def test_reversal_resolves_the_sign_of_the_boundary_export():
    """The same plume near the east boundary, run east and then run west.

    Signed transport must be resolved: the eastward current pushes the plume
    out, the westward current carries it back into the domain.
    """
    exported = {}
    for u in (0.08, -0.08):
        grid = make_grid(nx=40, ny=14)
        land = np.zeros((grid.ny, grid.nx), dtype=bool)
        land[0, :] = land[-1, :] = True
        c0 = np.zeros((grid.ny, grid.nx))
        c0[7, 34] = 1.0e-3
        field = make_field(grid, land_mask=land, concentration={PB: c0})
        forcing = make_forcing(grid, u=u, diffusivity_m2_per_s=0.05,
                               land_mask=land)
        total = 0.0
        for _ in range(15):
            step = transport_step(field, forcing, zero_source(grid), 200.0)
            total += step.boundary_out_kg[PB]
            field = step.new_field
        exported[u] = total
    assert exported[0.08] > 5.0 * exported[-0.08]


# ---------------------------------------------------------------------------
# 7. Land
# ---------------------------------------------------------------------------

def test_no_transport_through_land():
    grid = make_grid(nx=24, ny=12)
    land = np.zeros((grid.ny, grid.nx), dtype=bool)
    land[:, 12] = True          # a wall right across the channel
    c0 = np.zeros((grid.ny, grid.nx))
    c0[6, 6] = 1.0e-3
    field = make_field(grid, land_mask=land, concentration={PB: c0})
    forcing = make_forcing(grid, u=0.10, diffusivity_m2_per_s=1.0, land_mask=land)
    for _ in range(60):
        field = transport_step(field, forcing, zero_source(grid), 300.0).new_field
    c = np.asarray(field.concentration_kg_per_m3[PB])
    assert float(c[land].sum()) == 0.0
    assert float(c[:, 13:].sum()) == 0.0, "nothing may appear beyond the wall"
    assert float(c[:, :12].sum()) > 0.0


def test_non_zero_concentration_on_land_is_refused():
    grid = make_grid(nx=8, ny=8)
    land = np.zeros((grid.ny, grid.nx), dtype=bool)
    land[0, :] = True
    field = make_field(grid, land_mask=land)
    # bypass the helper's masking on purpose
    field.concentration_kg_per_m3[PB][0, 3] = 1.0e-6
    forcing = make_forcing(grid, diffusivity_m2_per_s=0.1, land_mask=land)
    with pytest.raises(ValueError, match="non-zero on a land cell"):
        transport_step(field, forcing, zero_source(grid), 300.0)


# ---------------------------------------------------------------------------
# 8. Negativity and clipping
# ---------------------------------------------------------------------------

def test_concentrations_never_negative_and_clipping_is_reported():
    """A sharp front at a high cell Peclet number is where undershoot lives."""
    grid = make_grid(nx=30, ny=8)
    c0 = np.zeros((grid.ny, grid.nx))
    c0[:, 4:7] = 1.0e-3
    field = make_field(grid, concentration={PB: c0})
    forcing = make_forcing(grid, u=0.5, diffusivity_m2_per_s=1.0e-4)
    total_clip = 0.0
    for _ in range(40):
        step = transport_step(field, forcing, zero_source(grid), 20.0)
        field = step.new_field
        total_clip += step.diagnostics["clip_correction_kg"][PB]
        c = np.asarray(field.concentration_kg_per_m3[PB])
        assert c.min() >= 0.0
        assert "clip_correction_kg" in step.diagnostics
    # whether or not this configuration actually undershoots, the correction is
    # a number the caller can read rather than something hidden
    assert total_clip >= 0.0
    assert isinstance(step.diagnostics["clipped_cells"][PB], int)


# ---------------------------------------------------------------------------
# 9. Refinement
# ---------------------------------------------------------------------------

def _run_open(grid, dt, n_steps, diffusivity=0.6, u=0.05):
    """An open-boundary run with a seabed source: the production configuration."""
    c0 = np.zeros((grid.ny, grid.nx))
    c0[grid.ny // 2, grid.nx // 4] = 1.0e-3
    field = make_field(grid, concentration={PB: c0})
    forcing = make_forcing(grid, u=u, diffusivity_m2_per_s=diffusivity)
    source = uniform_source(
        grid, 2.0e-10,
        [(ix, iy) for iy in range(grid.ny // 2 - 1, grid.ny // 2 + 2)
         for ix in range(grid.nx // 4 - 1, grid.nx // 4 + 2)],
    )
    exported = 0.0
    for _ in range(n_steps):
        step = transport_step(field, forcing, source, dt)
        exported += step.boundary_out_kg[PB]
        field = step.new_field
    return field, exported


def _gaussian(grid, x0, y0, sigma, peak=1.0e-3):
    xs = grid.origin_x_m + (np.arange(grid.nx) + 0.5) * grid.dx_m
    ys = grid.origin_y_m + (np.arange(grid.ny) + 0.5) * grid.dy_m
    xx, yy = np.meshgrid(xs, ys)
    return peak * np.exp(-((xx - x0) ** 2 + (yy - y0) ** 2) / (2.0 * sigma ** 2))


def test_time_step_refinement_converges():
    """Halving dt must move the answer less each time, and by less than the
    tolerance stated here.

    Implicit Euler is first order in time, so a change of a few per cent per
    halving is the expected behaviour, not a defect.  What would be a defect is
    a change that fails to shrink, which is exactly how the operator-split
    reactive-layer scheme was caught (REFACTOR_PLAN probe 4).  Measured on this
    configuration: mass 0.66 %, 0.44 %; centroid 2.2 %, 1.2 %; export 1.5 %,
    1.0 % for dt 200 to 100 to 50.
    """
    grid = make_grid(nx=32, ny=16)
    window = 2400.0
    results = {}
    for dt in (200.0, 100.0, 50.0):
        field, exported = _run_open(grid, dt, int(window / dt))
        results[dt] = (field.water_mass_kg(PB), centroid_x(field), exported)
    coarse, medium, fine = results[200.0], results[100.0], results[50.0]
    tolerances = {0: ("water mass", 1.0e-2), 1: ("centroid", 2.5e-2),
                  2: ("boundary export", 2.0e-2)}
    for index, (label, tolerance) in tolerances.items():
        first = abs(medium[index] - coarse[index]) / abs(coarse[index])
        second = abs(fine[index] - medium[index]) / abs(medium[index])
        assert second < tolerance, f"{label} still moves by {second:.3e} at dt=50"
        assert second < first, f"{label} refinement did not converge: {first:.3e} -> {second:.3e}"


def test_grid_refinement_converges():
    """Halving dx over the same physical basin, closed so nothing leaves.

    The initial Gaussian is sampled at cell centres, so the discrete starting
    mass itself differs slightly between grids; that is an initial-condition
    artefact and is included in the tolerance rather than corrected away.
    Measured: mass 0.23 %, 0.075 %; centroid 0.38 %, 0.14 %; variance 1.2 %,
    0.79 % for dx 10 m to 5 m to 2.5 m.
    """
    from reactive_seabed_mat.contracts import GridSpec

    results = {}
    for nx, ny, dx in ((32, 16, 10.0), (64, 32, 5.0), (128, 64, 2.5)):
        grid = GridSpec(nx=nx, ny=ny, dx_m=dx, dy_m=dx, mixing_depth_m=5.0)
        land = land_ring(grid)
        c0 = _gaussian(grid, 100.0, 80.0, 25.0)
        c0[land] = 0.0
        field = make_field(grid, land_mask=land, concentration={PB: c0})
        forcing = make_forcing(grid, u=0.05, diffusivity_m2_per_s=0.6,
                               land_mask=land)
        for _ in range(24):
            field = transport_step(field, forcing, zero_source(grid), 100.0).new_field
        results[dx] = (field.water_mass_kg(PB), centroid_x(field), variance_x(field))
    coarse, medium, fine = results[10.0], results[5.0], results[2.5]
    tolerances = {0: ("water mass", 1.0e-2), 1: ("centroid", 1.0e-2),
                  2: ("variance", 3.0e-2)}
    for index, (label, tolerance) in tolerances.items():
        first = abs(medium[index] - coarse[index]) / abs(coarse[index])
        second = abs(fine[index] - medium[index]) / abs(medium[index])
        assert second < tolerance, f"{label} still moves by {second:.3e} at dx=2.5 m"
        assert second < first, f"{label} refinement did not converge: {first:.3e} -> {second:.3e}"


# ---------------------------------------------------------------------------
# 10. Engine mechanics
# ---------------------------------------------------------------------------

def test_two_elements_match_two_single_element_runs_bit_for_bit():
    """The shared equation object must not couple the elements."""
    grid = make_grid(nx=16, ny=12)
    c_pb = np.zeros((grid.ny, grid.nx))
    c_pb[6, 4] = 1.0e-3
    c_hg = np.zeros((grid.ny, grid.nx))
    c_hg[6, 9] = 5.0e-6
    forcing = make_forcing(grid, u=0.05, v=0.01, diffusivity_m2_per_s=0.5)
    source_arrays = {
        PB: np.zeros((grid.ny, grid.nx)),
        HG: np.zeros((grid.ny, grid.nx)),
    }
    source_arrays[PB][6, 4] = 3.0e-10
    source_arrays[HG][6, 9] = 1.0e-12
    both = transport_step(
        make_field(grid, elements=(PB, HG), concentration={PB: c_pb, HG: c_hg}),
        forcing,
        SeabedSourceField(time_utc=START, flux_kg_per_m2_per_s=source_arrays),
        300.0,
    )
    for name, c0 in ((PB, c_pb), (HG, c_hg)):
        alone = transport_step(
            make_field(grid, elements=(name,), concentration={name: c0}),
            forcing,
            SeabedSourceField(
                time_utc=START,
                flux_kg_per_m2_per_s={name: source_arrays[name]},
            ),
            300.0,
        )
        assert np.array_equal(
            np.asarray(both.new_field.concentration_kg_per_m3[name]),
            np.asarray(alone.new_field.concentration_kg_per_m3[name]),
        )


def test_source_element_absent_from_the_field_is_refused():
    grid = make_grid(nx=8, ny=8)
    field = make_field(grid, elements=(PB,))
    forcing = make_forcing(grid, diffusivity_m2_per_s=0.1)
    source = uniform_source(grid, 1.0e-10, [(3, 3)], elements=(PB, HG))
    with pytest.raises(KeyError, match="does not"):
        transport_step(field, forcing, source, 300.0)


def test_negative_source_flux_is_refused():
    grid = make_grid(nx=8, ny=8)
    field = make_field(grid)
    forcing = make_forcing(grid, diffusivity_m2_per_s=0.1)
    source = uniform_source(grid, -1.0e-10, [(3, 3)])
    with pytest.raises(ValueError, match="negative"):
        transport_step(field, forcing, source, 300.0)


def test_no_decay_term_anywhere():
    """With no source, no flow and a closed domain, mass is exactly preserved."""
    grid = make_grid(nx=12, ny=10)
    land = np.zeros((grid.ny, grid.nx), dtype=bool)
    land[0, :] = land[-1, :] = True
    land[:, 0] = land[:, -1] = True
    c0 = np.full((grid.ny, grid.nx), 1.0e-6)
    field = make_field(grid, land_mask=land, concentration={PB: c0})
    forcing = make_forcing(grid, diffusivity_m2_per_s=0.8, land_mask=land)
    start = field.water_mass_kg(PB)
    for _ in range(50):
        field = transport_step(field, forcing, zero_source(grid), 600.0).new_field
    assert field.water_mass_kg(PB) == pytest.approx(start, rel=1e-13)


def test_step_ledger_balances():
    grid = make_grid(nx=16, ny=12)
    field = make_field(grid)
    forcing = make_forcing(grid, u=0.06, diffusivity_m2_per_s=0.5)
    source = uniform_source(grid, 8.0e-10, [(6, 6), (7, 6)])
    step = transport_step(field, forcing, source, 300.0)
    ledger = step_ledger(PB, field, step)
    assert ledger.supplied_kg > 0.0
    assert abs(ledger.relative_imbalance) < 1e-12


def test_dt_must_be_positive():
    grid = make_grid(nx=8, ny=8)
    field = make_field(grid)
    forcing = make_forcing(grid, diffusivity_m2_per_s=0.1)
    with pytest.raises(ValueError, match="dt_s"):
        transport_step(field, forcing, zero_source(grid), 0.0)
