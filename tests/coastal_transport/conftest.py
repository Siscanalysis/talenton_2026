"""Shared fixtures for the coastal-transport tests.

The reactive layer itself lives on ``feat/reactive-layer``.  Until it lands,
these tests drive the coupling with a **LABELLED_STUB**: a constant-attenuation
tile that returns ``J_out = (1 - attenuation) * J_bare``.  It exists only in
this test package.  Nothing under ``src/`` imports it, and nothing in it is a
claim about how a reactive layer behaves.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

import numpy as np
import pytest

from reactive_seabed_mat.contracts import (
    Element,
    FieldState,
    Forcing,
    GridSpec,
    LayerStep,
    MatTileGeometry,
    MatTileState,
    ProvenanceLabel,
    SeabedExchange,
    SeabedHotspot,
    StateOrigin,
)

START_UTC = datetime(2026, 9, 8, tzinfo=timezone.utc)

#: LABELLED_STUB constants.  The two numbers bracket the behaviour the refactor
#: plan records for the real layer (a fresh mat above 99 %, a saturated one about
#: 94 %, purely as a diffusive barrier).  They are stand-ins, not results.
STUB_FRESH_ATTENUATION = 0.995
STUB_SATURATED_ATTENUATION = 0.94


def make_grid(nx: int = 24, ny: int = 16, dx: float = 10.0, dy: float = 10.0,
              mixing_depth_m: float = 5.0) -> GridSpec:
    return GridSpec(nx=nx, ny=ny, dx_m=dx, dy_m=dy, mixing_depth_m=mixing_depth_m)


def make_field(
    grid: GridSpec,
    *,
    elements: Sequence[str] = (Element.PB.value,),
    land_mask: np.ndarray | None = None,
    concentration: Mapping[str, np.ndarray] | None = None,
    time_utc: datetime = START_UTC,
) -> FieldState:
    if land_mask is None:
        land_mask = np.zeros((grid.ny, grid.nx), dtype=bool)
    fields = {}
    for name in elements:
        if concentration is not None and name in concentration:
            values = np.array(concentration[name], dtype=float)
        else:
            values = np.zeros((grid.ny, grid.nx), dtype=float)
        values[land_mask] = 0.0
        fields[name] = values
    return FieldState(
        grid=grid,
        time_utc=time_utc,
        concentration_kg_per_m3=fields,
        land_mask=np.asarray(land_mask, dtype=bool),
        origin=StateOrigin.TRUE_SIMULATED,
    )


def make_forcing(
    grid: GridSpec,
    *,
    u: float = 0.0,
    v: float = 0.0,
    diffusivity_m2_per_s: float = 0.0,
    land_mask: np.ndarray | None = None,
    time_utc: datetime = START_UTC,
) -> Forcing:
    u_arr = np.full((grid.ny, grid.nx), float(u))
    v_arr = np.full((grid.ny, grid.nx), float(v))
    if land_mask is not None:
        mask = np.asarray(land_mask, dtype=bool)
        u_arr[mask] = 0.0
        v_arr[mask] = 0.0
    return Forcing(
        time_utc=time_utc,
        u_east_m_per_s=u_arr,
        v_north_m_per_s=v_arr,
        diffusivity_m2_per_s=float(diffusivity_m2_per_s),
        provenance=ProvenanceLabel.SYNTHETIC_DEMO,
        notes="test forcing",
    )


def make_hotspot(
    grid: GridSpec,
    *,
    x0: int = 8,
    y0: int = 6,
    nx: int = 4,
    ny: int = 4,
    porewater: Mapping[str, float] | None = None,
    seepage_velocity_m_per_s: float = 3.0e-8,
    film_transfer_m_per_s: float = 5.0e-7,
) -> SeabedHotspot:
    """A rectangular hotspot given in cell indices, so tests stay exact."""
    porewater = dict(porewater or {Element.PB.value: 1.0e-3})
    indices = [
        grid.cell_index(ix, iy)
        for iy in range(y0, y0 + ny)
        for ix in range(x0, x0 + nx)
    ]
    transfer = seepage_velocity_m_per_s + film_transfer_m_per_s
    return SeabedHotspot(
        hotspot_id="test_hotspot",
        cell_indices=tuple(indices),
        sediment_porewater_kg_per_m3=porewater,
        bare_flux_kg_per_m2_per_s={
            name: transfer * value for name, value in porewater.items()
        },
        seepage_velocity_m_per_s=seepage_velocity_m_per_s,
        film_transfer_m_per_s=film_transfer_m_per_s,
        label=ProvenanceLabel.SYNTHETIC_DEMO,
    )


def hotspot_bounds_m(grid: GridSpec, hotspot: SeabedHotspot) -> tuple[float, float, float, float]:
    """Outer rectangle of a hotspot built by :func:`make_hotspot`, in metres."""
    indices = np.asarray(list(hotspot.cell_indices), dtype=int)
    ix = indices % grid.nx
    iy = indices // grid.nx
    return (
        grid.origin_x_m + ix.min() * grid.dx_m,
        grid.origin_y_m + iy.min() * grid.dy_m,
        grid.origin_x_m + (ix.max() + 1) * grid.dx_m,
        grid.origin_y_m + (iy.max() + 1) * grid.dy_m,
    )


def make_tile(
    tile_id: str,
    x_m: float,
    y_m: float,
    width_m: float,
    length_m: float,
    *,
    elements: Sequence[str] = (Element.PB.value,),
    integrity_index: float = 1.0,
    fouling_index: float = 0.0,
    displaced: bool = False,
    active: bool = True,
    edge_leakage_fraction: float = 0.0,
    thickness_m: float = 0.010,
    n_nodes: int = 4,
) -> MatTileState:
    geometry = MatTileGeometry(
        width_m=width_m,
        length_m=length_m,
        thickness_m=thickness_m,
        x_m=x_m,
        y_m=y_m,
        edge_leakage_fraction=edge_leakage_fraction,
    )
    zeros = {name: np.zeros(n_nodes) for name in elements}
    return MatTileState(
        tile_id=tile_id,
        media_id="media_test",
        installed_at_utc=START_UTC,
        geometry=geometry,
        porewater_kg_per_m3=zeros,
        sorbed_kg_per_kg={name: np.zeros(n_nodes) for name in elements},
        fouling_index=fouling_index,
        integrity_index=integrity_index,
        displaced=displaced,
        active=active,
    )


def stub_layer_step(
    tile: MatTileState,
    hotspot: SeabedHotspot,
    *,
    attenuation: float = STUB_FRESH_ATTENUATION,
    bottom_water: Mapping[str, float] | None = None,
    dt_s: float = 300.0,
    time_utc: datetime = START_UTC,
) -> LayerStep:
    """LABELLED_STUB constant-attenuation tile.

    ``J_out = (1 - attenuation) * J_bare`` per element, with the bare flux taken
    from the hotspot (optionally reduced by a bottom-water concentration, so the
    plume-feedback path is exercised).  There is no chemistry here at all: it is
    a placeholder for ``feat/reactive-layer``.
    """
    names = tuple(hotspot.bare_flux_kg_per_m2_per_s)
    transfer = hotspot.seepage_velocity_m_per_s + hotspot.film_transfer_m_per_s
    bare = {}
    for name in names:
        c_sed = float(hotspot.sediment_porewater_kg_per_m3.get(name, 0.0))
        c_water = float((bottom_water or {}).get(name, 0.0))
        bare[name] = max(transfer * (c_sed - c_water), 0.0)
    j_out = {name: (1.0 - attenuation) * value for name, value in bare.items()}
    exchange = SeabedExchange(
        tile_id=tile.tile_id,
        time_utc=time_utc,
        dt_s=dt_s,
        sediment_porewater_kg_per_m3=dict(hotspot.sediment_porewater_kg_per_m3),
        bottom_water_kg_per_m3=dict(bottom_water or {name: 0.0 for name in names}),
        seepage_velocity_m_per_s=hotspot.seepage_velocity_m_per_s,
        film_transfer_m_per_s=hotspot.film_transfer_m_per_s,
        bare_flux_kg_per_m2_per_s=bare,
        cell_indices=(),
        cell_weights=(),
        diagnostics={"LABELLED_STUB": "constant-attenuation tile, tests only"},
    )
    return LayerStep(
        new_state=tile,
        flux_in_kg_per_m2_per_s=dict(bare),
        flux_out_kg_per_m2_per_s=j_out,
        retained_delta_kg_per_m2={
            name: (bare[name] - j_out[name]) * dt_s for name in names
        },
        released_kg_per_m2={name: j_out[name] * dt_s for name in names},
        exchange=exchange,
        diagnostics={"LABELLED_STUB": "constant-attenuation tile, tests only"},
    )


@pytest.fixture
def grid() -> GridSpec:
    return make_grid()


@pytest.fixture
def hotspot(grid: GridSpec) -> SeabedHotspot:
    return make_hotspot(grid)
