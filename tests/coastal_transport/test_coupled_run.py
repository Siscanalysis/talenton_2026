"""End to end: hotspot to source flux to the 2-D field, mat against no mat.

Everything here runs the *same* hotspot, the *same* grid and the *same* forcing
arrays through the coupling, so a difference between the runs can only come from
the mat.  The forcing identity is asserted array by array, not assumed.
"""

from __future__ import annotations

import numpy as np
import pytest

from reactive_seabed_mat.config import default_run_config
from reactive_seabed_mat.contracts import Element
from reactive_seabed_mat.coastal_transport.domain import (
    build_domain,
    forcing_signature,
    forcing_timeline,
)
from reactive_seabed_mat.coastal_transport.fipy_engine import (
    accumulate_ledger,
    transport_step,
)
from reactive_seabed_mat.coastal_transport.seabed_source import (
    build_seabed_exchange,
    plan_tile_layout,
    residual_source_flux_detailed,
)

from conftest import (
    STUB_FRESH_ATTENUATION,
    STUB_SATURATED_ATTENUATION,
    make_tile,
    stub_layer_step,
)

PB = Element.PB.value
HG = Element.HG.value


def _small_config():
    """A small, fast variant of the demonstration configuration."""
    from dataclasses import replace

    config = default_run_config()
    domain = replace(config.domain, nx=30, ny=20, dx_m=20.0, dy_m=20.0,
                     land_rectangles=((0.0, 0.0, 600.0, 40.0),))
    return replace(config, domain=domain)


def _tiles(config, **kwargs):
    plans = plan_tile_layout(config.mat, config.hotspot)
    return [
        make_tile(p.tile_id, p.geometry.x_m, p.geometry.y_m,
                  p.geometry.width_m, p.geometry.length_m,
                  elements=tuple(config.elements),
                  edge_leakage_fraction=config.mat.edge_leakage_fraction,
                  **kwargs)
        for p in plans
    ]


def _run(config, tiles, attenuation, n_steps=8, dt_s=600.0):
    bundle = build_domain(config)
    field = bundle.field_state
    forcings = forcing_timeline(config.forcing, bundle.grid, bundle.land_mask,
                                n_steps, dt_s, config.start_datetime)
    steps = []
    for forcing in forcings:
        exchanges = build_seabed_exchange(field, tiles, bundle.hotspot, forcing, dt_s)
        layer_steps = [
            stub_layer_step(
                tile, bundle.hotspot,
                attenuation=attenuation,
                bottom_water=dict(exchange.bottom_water_kg_per_m3),
                dt_s=dt_s,
                time_utc=field.time_utc,
            )
            for tile, exchange in zip(tiles, exchanges)
        ]
        source = residual_source_flux_detailed(
            bundle.grid, bundle.hotspot, tiles, layer_steps, field.time_utc,
            fouling_bypass_coupling=config.degradation.fouling_bypass_coupling,
            overlap_m=config.mat.overlap_m,
            elements=tuple(config.elements),
        )
        step = transport_step(field, forcing, source, dt_s)
        steps.append(step)
        field = step.new_field
    return bundle, forcings, steps, field


def test_mat_and_no_mat_runs_use_identical_forcing_arrays():
    config = _small_config()
    tiles = _tiles(config)
    _, mat_forcings, _, _ = _run(config, tiles, STUB_FRESH_ATTENUATION, n_steps=4)
    _, bare_forcings, _, _ = _run(config, [], 0.0, n_steps=4)
    assert forcing_signature(mat_forcings) == forcing_signature(bare_forcings)
    for a, b in zip(mat_forcings, bare_forcings):
        assert np.array_equal(a.u_east_m_per_s, b.u_east_m_per_s)
        assert np.array_equal(a.v_north_m_per_s, b.v_north_m_per_s)
        assert a.diffusivity_m2_per_s == b.diffusivity_m2_per_s
        assert a.time_utc == b.time_utc


def test_a_fresh_mat_releases_less_than_no_mat_under_identical_forcing():
    config = _small_config()
    tiles = _tiles(config)
    _, _, mat_steps, mat_field = _run(config, tiles, STUB_FRESH_ATTENUATION)
    _, _, bare_steps, bare_field = _run(config, [], 0.0)
    for name in (PB, HG):
        mat_released = sum(s.released_from_seabed_kg[name] for s in mat_steps)
        bare_released = sum(s.released_from_seabed_kg[name] for s in bare_steps)
        assert bare_released > 0.0
        assert mat_released < bare_released
        assert mat_field.water_mass_kg(name) < bare_field.water_mass_kg(name)


def test_a_saturated_mat_sits_between_a_fresh_mat_and_no_mat():
    config = _small_config()
    tiles = _tiles(config)
    _, _, fresh, _ = _run(config, tiles, STUB_FRESH_ATTENUATION)
    _, _, saturated, _ = _run(config, tiles, STUB_SATURATED_ATTENUATION)
    _, _, bare, _ = _run(config, [], 0.0)
    fresh_rate = sum(s.released_from_seabed_kg[PB] for s in fresh)
    saturated_rate = sum(s.released_from_seabed_kg[PB] for s in saturated)
    bare_rate = sum(s.released_from_seabed_kg[PB] for s in bare)
    assert fresh_rate < saturated_rate < bare_rate


def test_a_displaced_tile_raises_the_source_only_over_its_own_cells():
    config = _small_config()
    bundle = build_domain(config)
    intact = _tiles(config)
    broken = _tiles(config)
    broken[4] = make_tile(broken[4].tile_id, broken[4].geometry.x_m,
                          broken[4].geometry.y_m, broken[4].geometry.width_m,
                          broken[4].geometry.length_m,
                          elements=tuple(config.elements), displaced=True)

    def source_for(tiles):
        steps = [stub_layer_step(t, bundle.hotspot, attenuation=STUB_FRESH_ATTENUATION)
                 for t in tiles if t.coverage_fraction > 0.0]
        return residual_source_flux_detailed(
            bundle.grid, bundle.hotspot, tiles, steps,
            bundle.field_state.time_utc,
            elements=tuple(config.elements),
        )

    before = np.asarray(source_for(intact).flux_kg_per_m2_per_s[PB])
    after = np.asarray(source_for(broken).flux_kg_per_m2_per_s[PB])
    changed = ~np.isclose(after, before, rtol=0.0, atol=0.0)
    from reactive_seabed_mat.coastal_transport.seabed_source import cell_area_weights
    own = cell_area_weights(bundle.grid, broken[4].geometry) > 0.0
    assert changed.any()
    assert np.array_equal(changed, changed & own), (
        "a displaced tile changed a cell outside its own footprint"
    )
    assert after[changed].min() > before[changed].max()


def test_the_whole_window_conserves_mass_per_element():
    config = _small_config()
    tiles = _tiles(config)
    bundle, _, steps, field = _run(config, tiles, STUB_FRESH_ATTENUATION)
    for name in (PB, HG):
        ledger = accumulate_ledger(name, bundle.field_state, steps)
        assert ledger.supplied_kg > 0.0
        assert abs(ledger.relative_imbalance) < 1e-9, (
            f"{name}: relative imbalance {ledger.relative_imbalance:.3e}"
        )
        worst = max(abs(s.diagnostics["closure_error_kg"][name]) for s in steps)
        assert worst / ledger.supplied_kg < 1e-6


def test_nothing_is_ever_subtracted_from_a_water_cell():
    """The mat attenuates a flux; it never removes mass from the water column.

    With a mat present, the water mass can only rise while the source is
    positive: there is no path by which a tile takes contaminant back out of a
    water-column cell.
    """
    config = _small_config()
    tiles = _tiles(config)
    _, _, steps, _ = _run(config, tiles, STUB_FRESH_ATTENUATION, n_steps=6)
    previous = 0.0
    for step in steps:
        current = step.new_field.water_mass_kg(PB)
        assert current >= previous - 1e-18
        previous = current
        assert step.boundary_in_kg[PB] == pytest.approx(0.0, abs=1e-18)


def test_the_source_responds_to_the_rising_plume():
    """A rising bottom-water concentration lowers the driving gradient."""
    config = _small_config()
    tiles = _tiles(config)
    _, _, steps, _ = _run(config, tiles, STUB_FRESH_ATTENUATION, n_steps=10,
                          dt_s=1800.0)
    first = steps[0].released_from_seabed_kg[PB]
    last = steps[-1].released_from_seabed_kg[PB]
    assert last < first, (
        "the bare-flux feedback through the bottom water is not reaching the "
        "source term"
    )


def test_the_undersized_design_leaves_the_uncovered_share_bare():
    from dataclasses import replace

    config = _small_config()
    config = replace(config, mat=replace(config.mat, coverage_fraction=0.45,
                                         tiles_x=2, tiles_y=2))
    bundle = build_domain(config)
    tiles = _tiles(config)
    steps = [stub_layer_step(t, bundle.hotspot, attenuation=STUB_FRESH_ATTENUATION)
             for t in tiles]
    source = residual_source_flux_detailed(
        bundle.grid, bundle.hotspot, tiles, steps, bundle.field_state.time_utc,
        elements=tuple(config.elements),
    )
    from reactive_seabed_mat.coastal_transport.seabed_source import component_total
    hotspot_area = bundle.hotspot.n_cells * bundle.grid.cell_area_m2
    j_bare = bundle.hotspot.bare_flux_kg_per_m2_per_s[PB]
    assert component_total(source, PB, bundle.grid, "uncovered") == pytest.approx(
        0.55 * hotspot_area * j_bare, rel=1e-9
    )
