"""Grid, land mask, prescribed forcing and the authorised seabed hotspot."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest

from reactive_seabed_mat.config import (
    DomainConfig,
    ForcingConfig,
    HotspotConfig,
    HotspotScheduleEntry,
    default_run_config,
)
from reactive_seabed_mat.contracts import Element, ProvenanceLabel
from reactive_seabed_mat.coastal_transport.domain import (
    TidalForcingRefused,
    assert_tide_resolving,
    bare_flux,
    build_domain,
    build_grid,
    build_hotspot,
    build_land_mask,
    forcing_at,
    forcing_signature,
    forcing_timeline,
    hotspot_area_m2,
    hotspot_cell_mask,
    hotspot_entry_at,
    initial_field_state,
    mean_velocity_at,
    tidal_factor,
)

PB = Element.PB.value
HG = Element.HG.value


# ---------------------------------------------------------------------------
# Grid and land
# ---------------------------------------------------------------------------

def test_grid_matches_the_configuration_and_the_fipy_cell_order():
    grid = build_grid(DomainConfig())
    assert (grid.nx, grid.ny) == (60, 40)
    assert grid.cell_index(3, 2) == 2 * 60 + 3
    assert grid.cell_area_m2 == 100.0
    assert grid.cell_volume_m3 == 500.0


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"nx": 0}, "at least one cell"),
        ({"dx_m": 0.0}, "strictly positive"),
        ({"mixing_depth_m": 0.0}, "mixing_depth_m"),
    ],
)
def test_a_degenerate_grid_is_refused(kwargs, message):
    with pytest.raises(ValueError, match=message):
        build_grid(replace(DomainConfig(), **kwargs))


def test_land_mask_uses_cell_centre_containment():
    domain = DomainConfig(nx=6, ny=4, dx_m=10.0, dy_m=10.0,
                          land_rectangles=((0.0, 0.0, 60.0, 10.0),))
    mask = build_land_mask(domain)
    assert mask.shape == (4, 6)
    assert mask[0].all()
    assert not mask[1:].any()


def test_land_covering_everything_is_refused():
    domain = DomainConfig(nx=4, ny=4, land_rectangles=((-1.0, -1.0, 1e6, 1e6),))
    with pytest.raises(ValueError, match="no water left"):
        build_land_mask(domain)


def test_initial_field_is_zero_and_land_holds_no_water():
    config = default_run_config()
    field = initial_field_state(config)
    for name in config.elements:
        array = np.asarray(field.concentration_kg_per_m3[name])
        assert array.shape == (config.domain.ny, config.domain.nx)
        assert not array.any()
    assert field.land_mask.any()


def test_initial_concentration_is_zeroed_on_land():
    config = default_run_config()
    grid = build_grid(config.domain)
    field = initial_field_state(
        config, initial_concentration={PB: 1.0e-6, HG: 0.0}
    )
    assert float(np.asarray(field.concentration_kg_per_m3[PB])[field.land_mask].sum()) == 0.0
    assert field.water_mass_kg(PB) == pytest.approx(
        1.0e-6 * int((~field.land_mask).sum()) * grid.cell_volume_m3
    )


def test_negative_initial_concentration_is_refused():
    config = default_run_config()
    with pytest.raises(ValueError, match="negative"):
        initial_field_state(config, initial_concentration={PB: -1.0e-9})


# ---------------------------------------------------------------------------
# Forcing
# ---------------------------------------------------------------------------

def test_steady_forcing_is_constant_and_zero_on_land():
    config = default_run_config()
    grid = build_grid(config.domain)
    land = build_land_mask(config.domain, grid)
    cfg = ForcingConfig(kind="steady", u_mean_m_per_s=0.04, v_mean_m_per_s=-0.01)
    a = forcing_at(cfg, grid, land, 0.0, config.start_datetime)
    b = forcing_at(cfg, grid, land, 1.0e5, config.start_datetime)
    assert np.array_equal(a.u_east_m_per_s, b.u_east_m_per_s)
    assert float(a.u_east_m_per_s[land].sum()) == 0.0
    assert a.u_east_m_per_s[~land][0] == pytest.approx(0.04)


def test_tidal_forcing_genuinely_reverses_sign_within_one_M2_period():
    config = default_run_config()
    grid = build_grid(config.domain)
    land = build_land_mask(config.domain, grid)
    cfg = ForcingConfig(kind="tidal", u_mean_m_per_s=0.04,
                        tidal_amplitude_m_per_s=0.18, tidal_period_s=44712.0)
    period = cfg.tidal_period_s
    samples = [mean_velocity_at(cfg, period * f / 24.0)[0] for f in range(24)]
    assert max(samples) > 0.0
    assert min(samples) < 0.0, "an M2 tide must reverse the along-channel flow"
    # peak and trough are the mean plus and minus the amplitude
    assert max(samples) == pytest.approx(0.04 + 0.18, rel=2e-2)
    assert min(samples) == pytest.approx(0.04 - 0.18, rel=2e-2)
    # and the field really is signed on the grid
    flood = forcing_at(cfg, grid, land, period * 0.25, config.start_datetime)
    ebb = forcing_at(cfg, grid, land, period * 0.75, config.start_datetime)
    assert float(flood.u_east_m_per_s[~land].mean()) > 0.0
    assert float(ebb.u_east_m_per_s[~land].mean()) < 0.0


def test_tidal_factor_is_a_unit_sinusoid():
    cfg = ForcingConfig(tidal_period_s=1000.0, tidal_phase_rad=0.0)
    assert tidal_factor(cfg, 0.0) == pytest.approx(0.0, abs=1e-12)
    assert tidal_factor(cfg, 250.0) == pytest.approx(1.0)
    assert tidal_factor(cfg, 750.0) == pytest.approx(-1.0)


def test_zero_mean_flow_still_reverses_east_to_west():
    cfg = ForcingConfig(kind="tidal", u_mean_m_per_s=0.0, v_mean_m_per_s=0.0,
                        tidal_amplitude_m_per_s=0.1, tidal_period_s=1000.0)
    assert mean_velocity_at(cfg, 250.0)[0] == pytest.approx(0.1)
    assert mean_velocity_at(cfg, 750.0)[0] == pytest.approx(-0.1)


def test_unknown_forcing_kind_is_refused():
    with pytest.raises(ValueError, match="unknown forcing kind"):
        mean_velocity_at(ForcingConfig(kind="geostrophic"), 0.0)


def test_a_daily_mean_product_is_refused_for_a_tidal_scenario():
    cfg = ForcingConfig(kind="tidal", temporal_averaging="daily_mean")
    with pytest.raises(TidalForcingRefused, match="de-tided or daily-mean"):
        assert_tide_resolving(cfg)
    assert_tide_resolving(replace(cfg, kind="steady"))


def test_a_tidal_scenario_with_no_amplitude_is_refused():
    cfg = ForcingConfig(kind="tidal", tidal_amplitude_m_per_s=0.0)
    with pytest.raises(TidalForcingRefused, match="does not reverse"):
        assert_tide_resolving(cfg)


def test_forcing_timeline_and_signature_are_identical_for_identical_settings():
    config = default_run_config()
    grid = build_grid(config.domain)
    land = build_land_mask(config.domain, grid)
    a = forcing_timeline(config.forcing, grid, land, 12, 300.0, config.start_datetime)
    b = forcing_timeline(config.forcing, grid, land, 12, 300.0, config.start_datetime)
    assert forcing_signature(a) == forcing_signature(b)
    for fa, fb in zip(a, b):
        assert np.array_equal(fa.u_east_m_per_s, fb.u_east_m_per_s)
        assert np.array_equal(fa.v_north_m_per_s, fb.v_north_m_per_s)
    changed = forcing_timeline(
        replace(config.forcing, u_mean_m_per_s=0.05), grid, land, 12, 300.0,
        config.start_datetime,
    )
    assert forcing_signature(changed) != forcing_signature(a)


def test_forcing_is_stamped_at_the_end_of_each_step():
    config = default_run_config()
    grid = build_grid(config.domain)
    land = build_land_mask(config.domain, grid)
    timeline = forcing_timeline(config.forcing, grid, land, 3, 300.0,
                                config.start_datetime)
    assert timeline[0].time_utc == config.start_datetime + timedelta(seconds=300.0)
    assert timeline[2].time_utc == config.start_datetime + timedelta(seconds=900.0)


# ---------------------------------------------------------------------------
# Hotspot
# ---------------------------------------------------------------------------

def test_hotspot_rectangle_uses_the_lower_left_corner_convention():
    """The default station list places ST_MAT_B at the centre of tile_1_1.

    That is only true if the hotspot ``x_m``/``y_m`` are its lower-left corner,
    so the convention is pinned by a test rather than by a comment.
    """
    config = default_run_config()
    grid = build_grid(config.domain)
    mask = hotspot_cell_mask(grid, config.hotspot)
    assert int(mask.sum()) == 64                     # 80 m by 80 m on a 10 m grid
    centre_x = config.hotspot.x_m + config.hotspot.width_m / 2.0
    centre_y = config.hotspot.y_m + config.hotspot.length_m / 2.0
    assert (centre_x, centre_y) == (300.0, 220.0)
    station = next(s for s in config.observations.stations if s.station_id == "ST_MAT_B")
    assert (station.x_m, station.y_m) == (centre_x, centre_y)
    assert station.tile_id == "tile_1_1"


def test_build_hotspot_computes_J_bare_from_the_schedule():
    config = default_run_config()
    hotspot = build_hotspot(config)
    entry = config.hotspot.schedule[0]
    transfer = entry.seepage_velocity_m_per_s + config.hotspot.film_transfer_m_per_s
    for name in config.elements:
        expected = transfer * entry.porewater_kg_per_m3[name]
        assert hotspot.bare_flux_kg_per_m2_per_s[name] == pytest.approx(expected,
                                                                       rel=1e-15)
    assert hotspot.n_cells == 64
    assert hotspot.seepage_velocity_m_per_s == entry.seepage_velocity_m_per_s
    assert hotspot.label is ProvenanceLabel.SYNTHETIC_DEMO
    assert "not an ordnance object" in hotspot.description
    assert "cell-centre containment" in hotspot.description


def test_the_schedule_changes_the_bare_flux_at_its_start_time():
    config = default_run_config()
    year = 365.25 * 86400.0
    schedule = (
        config.hotspot.schedule[0],
        HotspotScheduleEntry(
            start_s=2.0 * year,
            porewater_kg_per_m3={PB: 3.0e-3, HG: 2.4e-5},
            seepage_velocity_m_per_s=6.0e-8,
        ),
    )
    config = replace(config, hotspot=replace(config.hotspot, schedule=schedule))
    before = build_hotspot(config, elapsed_s=1.0 * year)
    after = build_hotspot(config, elapsed_s=2.5 * year)
    assert after.bare_flux_kg_per_m2_per_s[PB] > before.bare_flux_kg_per_m2_per_s[PB]
    assert after.seepage_velocity_m_per_s == 6.0e-8
    assert hotspot_entry_at(config.hotspot, 0.0) is schedule[0]
    assert hotspot_entry_at(config.hotspot, 3.0 * year) is schedule[1]


def test_before_the_first_schedule_entry_nothing_is_released():
    config = default_run_config()
    schedule = (HotspotScheduleEntry(
        start_s=1000.0,
        porewater_kg_per_m3={PB: 1.0e-3},
        seepage_velocity_m_per_s=3.0e-8,
    ),)
    config = replace(config, hotspot=replace(config.hotspot, schedule=schedule))
    hotspot = build_hotspot(config, elapsed_s=0.0)
    assert all(v == 0.0 for v in hotspot.bare_flux_kg_per_m2_per_s.values())
    assert "No hotspot schedule entry is active" in hotspot.description


def test_land_cells_inside_the_hotspot_are_excluded_and_declared():
    config = default_run_config()
    config = replace(
        config,
        domain=replace(config.domain,
                       land_rectangles=((0.0, 0.0, 600.0, 40.0),
                                        (255.0, 175.0, 285.0, 205.0))),
    )
    hotspot = build_hotspot(config)
    assert hotspot.n_cells < 64
    assert "are land and were excluded" in hotspot.description


def test_a_hotspot_with_no_water_cell_is_refused():
    config = default_run_config()
    config = replace(config, hotspot=replace(config.hotspot, x_m=5000.0))
    with pytest.raises(ValueError, match="covers no water cell"):
        build_hotspot(config)


def test_hotspot_area_is_the_gridded_area():
    config = default_run_config()
    bundle = build_domain(config)
    assert hotspot_area_m2(bundle.grid, bundle.hotspot) == pytest.approx(
        config.hotspot.area_m2
    )


def test_bare_flux_formula_and_its_guards():
    values = bare_flux(3.0e-8, 5.0e-7, {PB: 1.0e-3})
    assert values[PB] == pytest.approx((3.0e-8 + 5.0e-7) * 1.0e-3)
    with_water = bare_flux(3.0e-8, 5.0e-7, {PB: 1.0e-3},
                           bottom_water_kg_per_m3={PB: 4.0e-4})
    assert with_water[PB] == pytest.approx((3.0e-8 + 5.0e-7) * 6.0e-4)
    signed = bare_flux(3.0e-8, 5.0e-7, {PB: 1.0e-3},
                       bottom_water_kg_per_m3={PB: 2.0e-3}, clamp_at_zero=False)
    assert signed[PB] < 0.0
    assert bare_flux(3.0e-8, 5.0e-7, {PB: 1.0e-3},
                     bottom_water_kg_per_m3={PB: 2.0e-3})[PB] == 0.0
    with pytest.raises(ValueError, match="negative"):
        bare_flux(3.0e-8, 5.0e-7, {PB: -1.0e-3})
    with pytest.raises(ValueError, match="positive upward"):
        bare_flux(-1.0e-8, 5.0e-7, {PB: 1.0e-3})


def test_build_domain_returns_a_consistent_bundle():
    config = default_run_config()
    bundle = build_domain(config)
    assert bundle.water_cells + bundle.land_cells == bundle.grid.n_cells
    assert bundle.field_state.grid is bundle.grid
    assert np.array_equal(bundle.field_state.land_mask, bundle.land_mask)
    indices = np.asarray(bundle.hotspot.cell_indices)
    assert not bundle.land_mask.reshape(-1)[indices].any()


def test_the_M2_period_is_the_documented_twelve_hours_twenty_five_minutes():
    cfg = ForcingConfig()
    hours = cfg.tidal_period_s / 3600.0
    assert math.isclose(hours, 12.42, abs_tol=0.01)
