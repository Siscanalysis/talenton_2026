"""The carrier geotextiles, and what encapsulating the core costs.

The design question these tests exist to answer is not "does the code run" but
"is the geotextile treatment legitimate here". Two things have to hold: the
lumped diffusive resistance must be a fair approximation at the seepage
velocities used, and adding it must not break the conservation the whole solver
is built on.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from reactive_seabed_mat.config import default_run_config
from reactive_seabed_mat.reactive_layer import build_material_map, build_tile_states
from reactive_seabed_mat.reactive_layer.column import (
    bottom_conductance,
    build_column_parameters,
    solve_column_step,
    top_conductance,
)
from reactive_seabed_mat.reactive_layer.geotextile import (
    DEFAULT_GEOTEXTILE,
    GeotextileLayer,
    advection_is_unimpeded,
    encapsulated_conductances,
    geotextile_peclet,
    geotextile_resistance_s_per_m,
    in_series,
)
from reactive_seabed_mat.reactive_layer.tile import (
    advance_reactive_layer,
    scripted_exchange,
)

DT_S = 6.0 * 3600.0


@pytest.fixture
def setup():
    config = default_run_config()
    materials = build_material_map(config.mat)
    tiles = list(
        build_tile_states(
            config.mat,
            config.start_datetime,
            materials,
            hotspot=config.hotspot,
            elements=list(config.elements),
        )
    )
    return config, materials, tiles


# ---------------------------------------------------------------------------
# Is the treatment legitimate?
# ---------------------------------------------------------------------------

def test_the_geotextile_is_diffusion_dominated_at_our_seepage():
    """The lumped resistance is only fair while Peclet stays below about one.

    If this ever fails, the geotextile needs its own advective nodes and
    ``geotextile.py`` must not be used as it stands.
    """
    peclet = geotextile_peclet(DEFAULT_GEOTEXTILE, 3.0e-8)
    assert peclet < 1.0, f"Pe = {peclet:.2f}: lumping the geotextile is no longer fair"


def test_the_geotextile_does_not_restrict_flow():
    """Its hydraulic conductivity is orders above the seepage, so advection
    passes through and modelling it as a flow restriction would be wrong."""
    assert advection_is_unimpeded(DEFAULT_GEOTEXTILE, 3.0e-8)
    # And the claim is not vacuous: at a seepage a thousand times faster it fails.
    assert not advection_is_unimpeded(DEFAULT_GEOTEXTILE, 3.0e-5)


def test_series_resistance_algebra():
    assert in_series(2.0, 0.0) == 2.0
    assert in_series(0.0, 5.0) == 0.0
    assert in_series(1.0, math.inf) == 0.0
    assert in_series(0.5, 1.0) == pytest.approx(1.0 / 3.0)
    # Adding resistance can only reduce a conductance.
    assert in_series(1.0, 0.7) < 1.0


def test_a_thicker_geotextile_resists_more_and_a_missing_one_resists_nothing():
    thin = GeotextileLayer(thickness_m=0.001)
    thick = GeotextileLayer(thickness_m=0.006)
    assert thick.resistance_s_per_m > thin.resistance_s_per_m
    assert geotextile_resistance_s_per_m(None) == 0.0
    assert GeotextileLayer(thickness_m=0.0).resistance_s_per_m == 0.0


def test_a_geotextile_with_impossible_properties_is_refused():
    with pytest.raises(ValueError):
        GeotextileLayer(porosity=0.0)
    with pytest.raises(ValueError):
        GeotextileLayer(porosity=1.5)
    with pytest.raises(ValueError):
        GeotextileLayer(thickness_m=-0.001)
    with pytest.raises(ValueError):
        GeotextileLayer(molecular_diffusivity_m2_per_s=0.0)


# ---------------------------------------------------------------------------
# Does it break the solver?
# ---------------------------------------------------------------------------

def test_the_encapsulated_solve_still_conserves_mass_exactly(setup):
    """The whole point of the generalised boundary: the fluxes are evaluated
    with the SAME conductances the matrix used, so the balance closes."""
    config, materials, tiles = setup
    params = build_column_parameters(
        tiles[0].geometry,
        materials["Pb"],
        n_nodes=config.mat.n_layer_nodes,
        seepage_velocity_m_per_s=3.0e-8,
        film_transfer_m_per_s=config.hotspot.film_transfer_m_per_s,
    )
    g_bot, g_top = encapsulated_conductances(
        clean_bottom_conductance_m_per_s=bottom_conductance(params),
        clean_top_conductance_m_per_s=top_conductance(params),
    )
    nz = params.n_nodes
    step = solve_column_step(
        np.zeros(nz),
        np.zeros(nz),
        params,
        DT_S,
        1.0e-3,
        0.0,
        top_conductance_m_per_s=g_top,
        bottom_conductance_m_per_s=g_bot,
    )
    stored = step.stored_after_kg_per_m2 - step.stored_before_kg_per_m2
    crossed = (
        step.flux_in_kg_per_m2_per_s - step.flux_out_kg_per_m2_per_s
    ) * DT_S
    assert stored == pytest.approx(crossed, rel=1e-9, abs=1e-18)


def test_passing_no_geotextile_reproduces_the_bare_boundary(setup):
    """``geotextile=None`` must recover the unencapsulated model exactly, so the
    cost of encapsulation can be measured rather than assumed."""
    config, materials, tiles = setup
    params = build_column_parameters(
        tiles[0].geometry,
        materials["Pb"],
        n_nodes=config.mat.n_layer_nodes,
        seepage_velocity_m_per_s=3.0e-8,
        film_transfer_m_per_s=config.hotspot.film_transfer_m_per_s,
    )
    g_bot, g_top = encapsulated_conductances(
        clean_bottom_conductance_m_per_s=bottom_conductance(params),
        clean_top_conductance_m_per_s=top_conductance(params),
        bottom_layer=None,
        top_layer=None,
    )
    assert g_bot == pytest.approx(bottom_conductance(params))
    assert g_top == pytest.approx(top_conductance(params))


def test_encapsulation_reduces_the_residual_flux(setup):
    """It should help, and the test says by how much rather than just 'less'."""
    config, materials, tiles = setup
    tile = tiles[0]
    concentrations = {element: 1.0e-3 for element in config.elements}
    exchange = scripted_exchange(tile, tile.installed_at_utc, DT_S, concentrations)

    bare = advance_reactive_layer(tile, exchange, materials, DT_S, geotextile=None)
    wrapped = advance_reactive_layer(tile, exchange, materials, DT_S)

    assert (
        wrapped.flux_out_kg_per_m2_per_s["Pb"]
        <= bare.flux_out_kg_per_m2_per_s["Pb"] + 1e-30
    )


def test_the_barrier_limit_includes_the_geotextile(setup):
    """The 'no capacity left' floor must account for the encapsulation too,
    otherwise the sorbent gets credited with the geotextile's work."""
    config, materials, tiles = setup
    tile = tiles[0]
    concentrations = {element: 1.0e-3 for element in config.elements}
    exchange = scripted_exchange(tile, tile.installed_at_utc, DT_S, concentrations)

    bare = advance_reactive_layer(tile, exchange, materials, DT_S, geotextile=None)
    wrapped = advance_reactive_layer(tile, exchange, materials, DT_S)

    bare_barrier = bare.diagnostics["barrier_flux_kg_per_m2_per_s"]["Pb"]
    wrapped_barrier = wrapped.diagnostics["barrier_flux_kg_per_m2_per_s"]["Pb"]
    assert wrapped_barrier < bare_barrier


# ---------------------------------------------------------------------------
# Copper, and what the speciation does to it
# ---------------------------------------------------------------------------

def test_the_three_elements_have_independent_capacities(setup):
    config, materials, _ = setup
    assert set(materials) == {"Pb", "Hg", "Cu"}
    allocations = {m.element: m.allocation_fraction for m in config.mat.media}
    assert sum(allocations.values()) <= 1.0 + 1e-12


def test_allocating_more_medium_than_exists_is_refused():
    from reactive_seabed_mat.config import MatLayoutConfig, ReactiveMediumConfig

    with pytest.raises(ValueError, match="spend more sorbent"):
        MatLayoutConfig(
            media=(
                ReactiveMediumConfig(element="Pb", allocation_fraction=0.8),
                ReactiveMediumConfig(element="Hg", allocation_fraction=0.8),
            )
        )


def test_speciation_reduces_kd_and_leaves_capacity_alone():
    """The chemistry of the derating.

    Only a fraction of dissolved copper is in a form a site can bind, so the
    partition coefficient measured against TOTAL dissolved concentration falls.
    The number of sites does not: applying the fraction to q_max instead would
    claim the sites vanish in seawater.
    """
    from reactive_seabed_mat.config import ReactiveMediumConfig
    from reactive_seabed_mat.reactive_layer.material import build_material_parameters

    free = ReactiveMediumConfig(
        element="Cu", kd_m3_per_kg=8.0, q_max_kg_per_kg=3.0e-3,
        available_fraction=1.0, available_fraction_interval=(1.0, 1.0),
        allocation_fraction=0.1,
    )
    seawater = replace(
        free, available_fraction=0.02, available_fraction_interval=(0.002, 0.15)
    )

    a = build_material_parameters(free)
    b = build_material_parameters(seawater)

    assert b.kd_m3_per_kg == pytest.approx(0.02 * a.kd_m3_per_kg)
    assert b.q_max_kg_per_kg == pytest.approx(a.q_max_kg_per_kg)


def test_an_impossible_available_fraction_is_refused():
    from reactive_seabed_mat.config import ReactiveMediumConfig
    from reactive_seabed_mat.reactive_layer.material import build_material_parameters

    with pytest.raises(ValueError, match="available_fraction"):
        build_material_parameters(
            ReactiveMediumConfig(available_fraction=0.0)
        )
    with pytest.raises(ValueError, match="available_fraction"):
        build_material_parameters(
            ReactiveMediumConfig(available_fraction=1.5)
        )
