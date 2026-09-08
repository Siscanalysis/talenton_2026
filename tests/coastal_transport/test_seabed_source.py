"""The seabed source coupling: MODEL_SPEC section 5.

These are the tests that matter most.  They check that the mat attenuates a
flux rather than intercepting a plume, that failure is spatially local, and
that every degradation mode moves its own component of the source.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from reactive_seabed_mat.config import HotspotConfig, MatLayoutConfig
from reactive_seabed_mat.contracts import Element
from reactive_seabed_mat.coastal_transport.seabed_source import (
    CONTRIBUTION_COMPONENTS,
    DEFAULT_FOULING_BYPASS_COUPLING,
    OverlappingTilesRefused,
    build_seabed_exchange,
    cell_area_weights,
    check_tile_overlaps,
    component_total,
    plan_tile_layout,
    residual_source_flux,
    residual_source_flux_detailed,
    tile_bounds,
)

from conftest import (
    START_UTC,
    STUB_FRESH_ATTENUATION,
    hotspot_bounds_m,
    make_field,
    make_forcing,
    make_grid,
    make_hotspot,
    make_tile,
    stub_layer_step,
)

PB = Element.PB.value
HG = Element.HG.value
NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def hotspot_mask(grid, hotspot) -> np.ndarray:
    mask = np.zeros(grid.n_cells, dtype=bool)
    mask[list(hotspot.cell_indices)] = True
    return mask.reshape(grid.ny, grid.nx)


def full_cover_tile(grid, hotspot, **kwargs):
    x0, y0, x1, y1 = hotspot_bounds_m(grid, hotspot)
    return make_tile("tile_full", x0, y0, x1 - x0, y1 - y0, **kwargs)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def test_cell_area_weights_are_exact_for_a_partly_covered_cell():
    grid = make_grid(nx=6, ny=4)
    tile = make_tile("t", 15.0, 10.0, 20.0, 10.0)       # x 15..35, y 10..20
    weights = cell_area_weights(grid, tile.geometry)
    assert weights.sum() == pytest.approx(2.0)          # 200 m2 over 100 m2 cells
    assert weights[1, 1] == pytest.approx(0.5)
    assert weights[1, 2] == pytest.approx(1.0)
    assert weights[1, 3] == pytest.approx(0.5)
    assert weights[0, 1] == 0.0
    assert weights[2, 2] == 0.0
    # a tile straddling a cell edge in both directions gives the product
    corner = make_tile("c", 15.0, 5.0, 20.0, 10.0)
    corner_weights = cell_area_weights(grid, corner.geometry)
    assert corner_weights[0, 1] == pytest.approx(0.25)
    assert corner_weights[0, 2] == pytest.approx(0.5)
    assert corner_weights.sum() == pytest.approx(2.0)


def test_tile_bounds_use_the_lower_left_corner_convention():
    tile = make_tile("t", 100.0, 50.0, 20.0, 30.0)
    assert tile_bounds(tile.geometry) == (100.0, 50.0, 120.0, 80.0)


def test_planned_tiles_abut_and_cover_the_designed_share():
    mat = MatLayoutConfig()
    hotspot = HotspotConfig()
    plans = plan_tile_layout(mat, hotspot)
    assert len(plans) == mat.n_tiles
    assert {p.tile_id for p in plans} >= {"tile_0_0", "tile_1_1", "tile_2_2"}
    area = sum(p.geometry.footprint_area_m2 for p in plans)
    assert area == pytest.approx(mat.coverage_fraction * hotspot.area_m2)
    check_tile_overlaps(plans, mat.overlap_m)


def test_overlapping_tiles_beyond_the_allowance_are_refused():
    a = make_tile("tile_a", 0.0, 0.0, 20.0, 20.0)
    b = make_tile("tile_b", 5.0, 5.0, 20.0, 20.0)     # 15 m by 15 m overlap
    with pytest.raises(OverlappingTilesRefused, match="overlap"):
        check_tile_overlaps([a, b], overlap_m=0.10)
    # a thin designed seam is allowed
    c = make_tile("tile_c", 19.95, 0.0, 20.0, 20.0)
    check_tile_overlaps([a, c], overlap_m=0.10)


# ---------------------------------------------------------------------------
# The coupling formula
# ---------------------------------------------------------------------------

def test_a_fully_covering_intact_mat_emits_strictly_less_than_no_mat():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    tile = full_cover_tile(grid, hotspot)
    step = stub_layer_step(tile, hotspot)
    with_mat = residual_source_flux(grid, hotspot, [tile], [step], NOW)
    no_mat = residual_source_flux(grid, hotspot, [], [], NOW)
    mat_rate = with_mat.total_rate_kg_per_s(PB, grid)
    bare_rate = no_mat.total_rate_kg_per_s(PB, grid)
    assert bare_rate > 0.0
    assert mat_rate < bare_rate
    assert mat_rate == pytest.approx(
        (1.0 - STUB_FRESH_ATTENUATION) * bare_rate, rel=1e-12
    )


def test_no_mat_emits_exactly_the_bare_flux_on_every_hotspot_cell():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    source = residual_source_flux(grid, hotspot, [], [], NOW)
    array = np.asarray(source.flux_kg_per_m2_per_s[PB])
    mask = hotspot_mask(grid, hotspot)
    bare = hotspot.bare_flux_kg_per_m2_per_s[PB]
    assert np.allclose(array[mask], bare, rtol=0, atol=0)
    assert np.all(array[~mask] == 0.0), "nothing is emitted outside the hotspot"


def test_integrity_zero_point_six_emits_zero_point_six_Jout_plus_zero_point_four_Jbare():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    tile = full_cover_tile(grid, hotspot, integrity_index=0.6)
    step = stub_layer_step(tile, hotspot)
    source = residual_source_flux(grid, hotspot, [tile], [step], NOW)
    array = np.asarray(source.flux_kg_per_m2_per_s[PB])
    mask = hotspot_mask(grid, hotspot)
    j_out = step.flux_out_kg_per_m2_per_s[PB]
    j_bare = hotspot.bare_flux_kg_per_m2_per_s[PB]
    expected = 0.6 * j_out + 0.4 * j_bare
    assert np.allclose(array[mask], expected, rtol=1e-12)
    damaged = np.asarray(source.components[PB]["damaged"])
    assert np.allclose(damaged[mask], 0.4 * j_bare, rtol=1e-12)
    assert np.all(np.asarray(source.components[PB]["displaced"]) == 0.0)


def test_a_displaced_tile_makes_exactly_its_own_cells_emit_the_bare_flux():
    """The spatially-local-failure criterion.

    Four abutting tiles, each covering four cells.  One is displaced.  Only its
    own cells return to the bare flux; every neighbouring covered cell is
    bit-for-bit unchanged.
    """
    grid = make_grid()
    hotspot = make_hotspot(grid, x0=8, y0=6, nx=4, ny=4)
    x0, y0, x1, y1 = hotspot_bounds_m(grid, hotspot)
    half_w, half_l = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    tiles = [
        make_tile(f"tile_{ix}_{iy}", x0 + ix * half_w, y0 + iy * half_l,
                  half_w, half_l)
        for iy in range(2) for ix in range(2)
    ]
    steps = [stub_layer_step(t, hotspot) for t in tiles]
    intact = residual_source_flux(grid, hotspot, tiles, steps, NOW)

    broken = list(tiles)
    broken[3] = make_tile("tile_1_1", x0 + half_w, y0 + half_l, half_w, half_l,
                          displaced=True)
    broken_steps = [stub_layer_step(t, hotspot) for t in broken]
    after = residual_source_flux(grid, hotspot, broken, broken_steps, NOW)

    before_arr = np.asarray(intact.flux_kg_per_m2_per_s[PB])
    after_arr = np.asarray(after.flux_kg_per_m2_per_s[PB])
    failed = cell_area_weights(grid, broken[3].geometry) > 0.0
    j_bare = hotspot.bare_flux_kg_per_m2_per_s[PB]

    assert np.allclose(after_arr[failed], j_bare, rtol=1e-12)
    assert np.array_equal(after_arr[~failed], before_arr[~failed]), (
        "a displaced tile must not change a single neighbouring cell"
    )
    assert np.allclose(
        np.asarray(after.components[PB]["displaced"])[failed], j_bare, rtol=1e-12
    )
    assert np.all(np.asarray(after.components[PB]["damaged"]) == 0.0), (
        "displacement is mode 3 and must not be reported as local damage"
    )


def test_coverage_fraction_0_45_leaves_55_percent_of_the_hotspot_bare():
    grid = make_grid(nx=40, ny=40)
    hotspot = make_hotspot(grid, x0=10, y0=10, nx=8, ny=8)
    x0, y0, x1, y1 = hotspot_bounds_m(grid, hotspot)
    coverage = 0.45
    scale = float(np.sqrt(coverage))
    width, length = (x1 - x0) * scale, (y1 - y0) * scale
    tile = make_tile(
        "tile_small",
        x0 + 0.5 * ((x1 - x0) - width),
        y0 + 0.5 * ((y1 - y0) - length),
        width,
        length,
    )
    step = stub_layer_step(tile, hotspot)
    source = residual_source_flux(grid, hotspot, [tile], [step], NOW)
    j_bare = hotspot.bare_flux_kg_per_m2_per_s[PB]
    hotspot_area = len(hotspot.cell_indices) * grid.cell_area_m2

    uncovered_rate = component_total(source, PB, grid, "uncovered")
    assert uncovered_rate == pytest.approx((1.0 - coverage) * hotspot_area * j_bare,
                                           rel=1e-12)
    covered_rate = component_total(source, PB, grid, "covered")
    assert covered_rate == pytest.approx(
        coverage * hotspot_area * step.flux_out_kg_per_m2_per_s[PB], rel=1e-12
    )


def test_edge_leakage_and_fouling_bypass_move_their_own_component():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    clean = full_cover_tile(grid, hotspot, edge_leakage_fraction=0.02)
    fouled = full_cover_tile(grid, hotspot, edge_leakage_fraction=0.02,
                             fouling_index=0.5)
    clean_source = residual_source_flux(
        grid, hotspot, [clean], [stub_layer_step(clean, hotspot)], NOW
    )
    fouled_source = residual_source_flux(
        grid, hotspot, [fouled], [stub_layer_step(fouled, hotspot)], NOW
    )
    clean_edge = component_total(clean_source, PB, grid, "edge_leakage")
    fouled_edge = component_total(fouled_source, PB, grid, "edge_leakage")
    assert fouled_edge > clean_edge, (
        "pore blockage must push flow around the tile edge, so fouling is never "
        "a free improvement"
    )
    expected_bypass = 0.02 + DEFAULT_FOULING_BYPASS_COUPLING * 0.5
    hotspot_area = len(hotspot.cell_indices) * grid.cell_area_m2
    assert fouled_edge == pytest.approx(
        expected_bypass * hotspot_area * hotspot.bare_flux_kg_per_m2_per_s[PB],
        rel=1e-12,
    )
    # and the total source rises, because the bypassed share emits J_bare
    assert (fouled_source.total_rate_kg_per_s(PB, grid)
            > clean_source.total_rate_kg_per_s(PB, grid))


def test_components_sum_to_the_total_everywhere():
    grid = make_grid()
    hotspot = make_hotspot(grid, porewater={PB: 1.0e-3, HG: 8.0e-6})
    x0, y0, x1, y1 = hotspot_bounds_m(grid, hotspot)
    tiles = [
        make_tile("tile_0_0", x0, y0, (x1 - x0) / 2, y1 - y0,
                  elements=(PB, HG), integrity_index=0.8,
                  edge_leakage_fraction=0.03, fouling_index=0.4),
        make_tile("tile_1_0", x0 + (x1 - x0) / 2, y0, (x1 - x0) / 4, y1 - y0,
                  elements=(PB, HG), displaced=True),
    ]
    steps = [stub_layer_step(tiles[0], hotspot)]
    source = residual_source_flux(grid, hotspot, tiles, steps, NOW)
    for name in (PB, HG):
        total = np.asarray(source.flux_kg_per_m2_per_s[name])
        parts = sum(
            np.asarray(source.components[name][key]) for key in CONTRIBUTION_COMPONENTS
        )
        assert np.allclose(parts, total, rtol=1e-12, atol=0.0)
        assert np.all(total >= 0.0)


def test_effective_cover_is_reported_so_a_map_can_show_why_a_cell_emits():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    tile = full_cover_tile(grid, hotspot, integrity_index=0.5,
                           edge_leakage_fraction=0.1)
    source = residual_source_flux(
        grid, hotspot, [tile], [stub_layer_step(tile, hotspot)], NOW
    )
    cover = np.asarray(source.components[PB]["effective_cover"])
    mask = hotspot_mask(grid, hotspot)
    assert np.allclose(cover[mask], 0.5 * (1.0 - 0.1), rtol=1e-12)
    assert np.all(cover[~mask] == 0.0)
    assert np.allclose(
        np.asarray(source.components[PB]["covered_fraction"])[mask], 0.5, rtol=1e-12
    )


def test_a_covering_tile_without_a_layer_step_is_refused():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    tile = full_cover_tile(grid, hotspot)
    with pytest.raises(KeyError, match="no LayerStep"):
        residual_source_flux(grid, hotspot, [tile], [], NOW)


def test_two_layer_steps_for_one_tile_are_refused():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    tile = full_cover_tile(grid, hotspot)
    step = stub_layer_step(tile, hotspot)
    with pytest.raises(ValueError, match="two layer steps"):
        residual_source_flux(grid, hotspot, [tile], [step, step], NOW)


def test_overlap_refusal_is_wired_into_the_detailed_entry_point():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    x0, y0, x1, y1 = hotspot_bounds_m(grid, hotspot)
    a = make_tile("tile_a", x0, y0, 30.0, 30.0)
    b = make_tile("tile_b", x0 + 5.0, y0 + 5.0, 30.0, 30.0)
    steps = [stub_layer_step(a, hotspot), stub_layer_step(b, hotspot)]
    with pytest.raises(OverlappingTilesRefused):
        residual_source_flux_detailed(
            grid, hotspot, [a, b], steps, NOW, overlap_m=0.1
        )


def test_overlapping_tiles_without_the_check_are_rescaled_and_recorded():
    """The refusal is the intended path; the rescale is the recorded fallback.

    With ``overlap_m=None`` the caller has skipped ``check_tile_overlaps``, so
    the coupling rescales every tile-derived weight by the same factor.  The
    components must still sum to the total, the source must not exceed the bare
    flux, and the correction must appear in the notes.
    """
    grid = make_grid()
    hotspot = make_hotspot(grid)
    x0, y0, x1, y1 = hotspot_bounds_m(grid, hotspot)
    a = make_tile("tile_a", x0, y0, x1 - x0, y1 - y0)
    b = make_tile("tile_b", x0, y0, x1 - x0, y1 - y0)     # laid straight on top
    steps = [stub_layer_step(a, hotspot), stub_layer_step(b, hotspot)]
    source = residual_source_flux_detailed(
        grid, hotspot, [a, b], steps, NOW, overlap_m=None
    )
    total = np.asarray(source.flux_kg_per_m2_per_s[PB])
    parts = sum(np.asarray(source.components[PB][key])
                for key in CONTRIBUTION_COMPONENTS)
    assert np.allclose(parts, total, rtol=1e-12, atol=0.0)
    mask = hotspot_mask(grid, hotspot)
    assert np.all(total[mask] <= hotspot.bare_flux_kg_per_m2_per_s[PB] * (1 + 1e-12))
    assert np.all(np.asarray(source.components[PB]["effective_cover"])[mask]
                  <= 1.0 + 1e-12)
    assert "NUMERICAL CORRECTION" in source.notes
    assert "tiles overlap" in source.notes


def test_a_negative_residual_flux_from_a_tile_is_refused():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    tile = full_cover_tile(grid, hotspot)
    step = stub_layer_step(tile, hotspot, attenuation=1.5)   # J_out < 0
    with pytest.raises(ValueError, match="negative residual flux"):
        residual_source_flux(grid, hotspot, [tile], [step], NOW)


# ---------------------------------------------------------------------------
# Driving conditions per tile
# ---------------------------------------------------------------------------

def test_build_seabed_exchange_reads_the_bottom_water_from_the_field():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    tile = full_cover_tile(grid, hotspot)
    mask = hotspot_mask(grid, hotspot)
    c = np.zeros((grid.ny, grid.nx))
    c[mask] = 2.0e-4
    field = make_field(grid, concentration={PB: c})
    forcing = make_forcing(grid, u=0.05, diffusivity_m2_per_s=0.6)
    (exchange,) = build_seabed_exchange(field, [tile], hotspot, forcing, 300.0)
    assert exchange.tile_id == tile.tile_id
    assert exchange.bottom_water_kg_per_m3[PB] == pytest.approx(2.0e-4, rel=1e-12)
    assert exchange.sediment_porewater_kg_per_m3[PB] == pytest.approx(1.0e-3)
    assert sum(exchange.cell_weights) == pytest.approx(1.0, rel=1e-12)
    assert len(exchange.cell_indices) == len(hotspot.cell_indices)


def test_a_rising_plume_reduces_the_driving_gradient():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    tile = full_cover_tile(grid, hotspot)
    forcing = make_forcing(grid, diffusivity_m2_per_s=0.6)
    clean = make_field(grid)
    mask = hotspot_mask(grid, hotspot)
    dirty_c = np.zeros((grid.ny, grid.nx))
    dirty_c[mask] = 4.0e-4
    dirty = make_field(grid, concentration={PB: dirty_c})
    (a,) = build_seabed_exchange(clean, [tile], hotspot, forcing, 300.0)
    (b,) = build_seabed_exchange(dirty, [tile], hotspot, forcing, 300.0)
    assert b.bare_flux_kg_per_m2_per_s[PB] < a.bare_flux_kg_per_m2_per_s[PB]
    transfer = hotspot.seepage_velocity_m_per_s + hotspot.film_transfer_m_per_s
    assert b.bare_flux_kg_per_m2_per_s[PB] == pytest.approx(
        transfer * (1.0e-3 - 4.0e-4), rel=1e-12
    )


def test_a_reversed_gradient_is_clamped_and_reported():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    tile = full_cover_tile(grid, hotspot)
    mask = hotspot_mask(grid, hotspot)
    c = np.zeros((grid.ny, grid.nx))
    c[mask] = 5.0e-3            # bottom water above the sediment porewater
    field = make_field(grid, concentration={PB: c})
    forcing = make_forcing(grid, diffusivity_m2_per_s=0.6)
    (exchange,) = build_seabed_exchange(field, [tile], hotspot, forcing, 300.0)
    assert exchange.bare_flux_kg_per_m2_per_s[PB] == 0.0
    assert exchange.diagnostics["bare_flux_signed_kg_per_m2_per_s"][PB] < 0.0
    assert PB in exchange.diagnostics["bare_flux_clamped_elements"]
    assert "NUMERICAL CORRECTION" in exchange.diagnostics["notes"]


def test_land_cells_are_excluded_from_the_bottom_water_average():
    grid = make_grid()
    land = np.zeros((grid.ny, grid.nx), dtype=bool)
    land[6, 8] = True
    hotspot = make_hotspot(grid)
    tile = full_cover_tile(grid, hotspot)
    mask = hotspot_mask(grid, hotspot) & ~land
    c = np.zeros((grid.ny, grid.nx))
    c[mask] = 1.0e-4
    field = make_field(grid, land_mask=land, concentration={PB: c})
    forcing = make_forcing(grid, diffusivity_m2_per_s=0.6, land_mask=land)
    (exchange,) = build_seabed_exchange(field, [tile], hotspot, forcing, 300.0)
    assert exchange.bottom_water_kg_per_m3[PB] == pytest.approx(1.0e-4, rel=1e-12)
    assert exchange.diagnostics["n_bottom_water_cells"] == len(hotspot.cell_indices) - 1


def test_exchange_records_the_film_transfer_assumption():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    tile = full_cover_tile(grid, hotspot)
    field = make_field(grid)
    slow = make_forcing(grid, u=0.01, diffusivity_m2_per_s=0.6)
    fast = make_forcing(grid, u=0.30, diffusivity_m2_per_s=0.6)
    (a,) = build_seabed_exchange(field, [tile], hotspot, slow, 300.0)
    (b,) = build_seabed_exchange(field, [tile], hotspot, fast, 300.0)
    assert a.film_transfer_m_per_s == b.film_transfer_m_per_s
    assert a.diagnostics["film_transfer_is_current_dependent"] is False
    assert b.environment["current_speed_m_per_s"] > a.environment["current_speed_m_per_s"]


def test_exchange_needs_a_positive_time_step():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    tile = full_cover_tile(grid, hotspot)
    field = make_field(grid)
    forcing = make_forcing(grid, diffusivity_m2_per_s=0.6)
    with pytest.raises(ValueError, match="dt_s"):
        build_seabed_exchange(field, [tile], hotspot, forcing, 0.0)


def test_exchange_time_is_the_field_time():
    grid = make_grid()
    hotspot = make_hotspot(grid)
    tile = full_cover_tile(grid, hotspot)
    field = make_field(grid, time_utc=START_UTC)
    forcing = make_forcing(grid, diffusivity_m2_per_s=0.6)
    (exchange,) = build_seabed_exchange(field, [tile], hotspot, forcing, 600.0)
    assert exchange.time_utc == START_UTC
    assert exchange.dt_s == 600.0
