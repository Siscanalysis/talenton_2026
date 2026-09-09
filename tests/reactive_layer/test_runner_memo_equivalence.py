"""Exact memoisation must preserve complete per-tile results and independence."""
from dataclasses import fields, is_dataclass, replace
from datetime import timedelta
from collections.abc import Mapping

import numpy as np
import pytest

from reactive_seabed_mat.config import RunConfig
from reactive_seabed_mat.coastal_transport import domain as dm, seabed_source as ss
from reactive_seabed_mat.reactive_layer import advance_reactive_layer, build_material_map, build_tile_states
from reactive_seabed_mat.scenarios import run


def assert_identical(actual, expected):
    if isinstance(expected, np.ndarray):
        assert actual.dtype == expected.dtype
        assert actual.shape == expected.shape
        assert actual.tobytes() == expected.tobytes()
    elif is_dataclass(expected):
        assert type(actual) is type(expected)
        for field in fields(expected):
            assert_identical(getattr(actual, field.name), getattr(expected, field.name))
    elif isinstance(expected, Mapping):
        assert actual.keys() == expected.keys()
        for key in expected:
            assert_identical(actual[key], expected[key])
    elif isinstance(expected, (tuple, list)):
        assert len(actual) == len(expected)
        for left, right in zip(actual, expected):
            assert_identical(left, right)
    else:
        assert actual == expected


def naive_steps(config, field, tiles, hotspot, forcing, materials, dt):
    exchanges = ss.build_seabed_exchange(field, tiles, hotspot, forcing, max(dt, config.dt_s))
    by_id = {e.tile_id: replace(e, environment={
        **e.environment, 'burial_resistance_s_per_m': config.degradation.burial_resistance_s_per_m,
        'fouling_bypass_coupling': config.degradation.fouling_bypass_coupling,
    }) for e in exchanges}
    return [advance_reactive_layer(tile, by_id[tile.tile_id], materials, dt)
            for tile in tiles if tile.tile_id in by_id]


@pytest.mark.parametrize('dt', [0.0, 21600.0])
@pytest.mark.parametrize('case', ['identical', 'metadata', 'condition', 'profiles', 'bottom_water', 'source_step', 'environment'])
def test_memo_matches_naive_complete_result_and_keeps_mutables_independent(monkeypatch, dt, case):
    config = RunConfig()
    material = build_material_map(config.mat)
    tiles = list(build_tile_states(config.mat, config.start_datetime, material, hotspot=config.hotspot))
    # Nonzero inventories exercise desorption, transport and returned profiles.
    tiles = [replace(tile, porewater_kg_per_m3={key: np.full(tile.n_nodes, 1e-6) for key in material},
                     sorbed_kg_per_kg={key: np.full(tile.n_nodes, p.q_max_kg_per_kg*p.allocation_fraction*0.3)
                                     for key, p in material.items()}) for tile in tiles]
    if case == 'metadata':
        tiles = [replace(tile, media_id=f'media_{i}', service_count=i,
                         installed_at_utc=tile.installed_at_utc-timedelta(days=i)) for i, tile in enumerate(tiles)]
    elif case == 'condition':
        tiles[1] = replace(tiles[1], fouling_index=0.3)
        tiles[2] = replace(tiles[2], burial_depth_m=0.002)
        tiles[3] = replace(tiles[3], integrity_index=0.6)
        tiles[4] = replace(tiles[4], displaced=True, displacement_m=3)
        tiles[5] = replace(tiles[5], active=False)
        tiles[6] = replace(tiles[6], geometry=replace(tiles[6].geometry, thickness_m=0.005))
        tiles[7] = replace(tiles[7], geometry=replace(tiles[7].geometry, width_m=13))
    elif case == 'profiles':
        tiles[1] = replace(tiles[1], porewater_kg_per_m3={**tiles[1].porewater_kg_per_m3,
                           'Pb': np.linspace(1e-6, 0, tiles[1].n_nodes)})
        tiles[2] = replace(tiles[2], sorbed_kg_per_kg={**tiles[2].sorbed_kg_per_kg,
                           'Pb': tiles[2].sorbed_kg_per_kg['Pb']*0.5})
    elif case == 'environment':
        config = replace(config, degradation=replace(config.degradation, fouling_bypass_coupling=0.7))
        tiles = [replace(tile, fouling_index=0.3) for tile in tiles]
    bundle = dm.build_domain(config)
    field, hotspot = bundle.field_state, bundle.hotspot
    if case == 'bottom_water':
        gradient = np.tile(np.linspace(0, 2e-7, bundle.grid.nx), (bundle.grid.ny, 1))
        field = replace(field, concentration_kg_per_m3={key: gradient.copy() for key in material})
    elif case == 'source_step':
        hotspot = replace(hotspot, sediment_porewater_kg_per_m3={key: 3*value for key, value in hotspot.sediment_porewater_kg_per_m3.items()},
                          seepage_velocity_m_per_s=2*hotspot.seepage_velocity_m_per_s)
    forcing = dm.forcing_at(config.forcing, bundle.grid, bundle.land_mask, 0, config.start_datetime)
    expected = naive_steps(config, field, tiles, hotspot, forcing, material, dt)
    called = []
    def counted(*args, **kwargs):
        called.append(args[0].tile_id)
        return advance_reactive_layer(*args, **kwargs)
    monkeypatch.setattr(run, 'advance_reactive_layer', counted)
    actual = run._layer_steps(config, field, tiles, hotspot, forcing, material, dt)
    assert_identical(actual, expected)
    if case in {'identical', 'metadata', 'source_step'}:
        assert len(called) == 1
    if case in {'condition', 'profiles', 'bottom_water'}:
        assert len(called) > 1
    for first, second in zip(actual, actual[1:]):
        for key in material:
            assert not np.shares_memory(first.new_state.porewater_kg_per_m3[key], second.new_state.porewater_kg_per_m3[key])
            assert not np.shares_memory(first.new_state.sorbed_kg_per_kg[key], second.new_state.sorbed_kg_per_kg[key])
        assert first.diagnostics is not second.diagnostics
        assert first.diagnostics['column'] is not second.diagnostics['column']
