"""One replaceable module of the mat: state, the frozen advance, reporting.

``advance_reactive_layer`` is the frozen signature of ``docs/DATA_CONTRACT.md``
section 2 and the entry point for the whole micro model.  It runs the 1-D
reactive layer of ``column.py`` through the tile's thickness, once per element,
and reports the two boundary fluxes.

What changed from the vertical-panel model this file replaces
-------------------------------------------------------------

The old ``advance_panel`` computed a bounded transfer out of a swept volume and
returned an uptake in kilograms that the macro model then subtracted from a
water-column cell.  None of that survives: there is no frontal area, no swept
volume, no interception efficiency, and **nothing is ever subtracted from a
water cell**.  A tile lies flat on the seabed and attenuates a boundary flux.

What was worth keeping is the bookkeeping discipline: every correction is
recorded, every binding constraint is named, the exchange that was answered is
echoed back on the step, and release is an explicit event rather than an
implicit consequence.  All four are still here.

Where the parameters that the frozen signature cannot carry come from
---------------------------------------------------------------------

``advance_reactive_layer`` takes no configuration object, but the layer needs
three numbers that live in ``config.DegradationConfig``.  They are read from
``SeabedExchange.environment`` when present and otherwise fall back to the
documented defaults in ``degradation.py``:

``burial_resistance_s_per_m``
    extra diffusive resistance per metre of burial.
``fouling_bypass_coupling``
    how strongly pore blockage pushes flow around the tile edge.
``fouling_growth_per_s`` / ``burial_growth_m_per_s``
    continuous growth applied **after** the transport step, and only when the
    exchange carries them.  Otherwise the caller owns degradation and calls
    ``grow_fouling`` / ``grow_burial`` itself.  Which of the two happened is
    recorded in the diagnostics.

This is listed in ``docs/handoffs/reactive_layer.md`` as a contract request.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime
from typing import Any, Mapping, Sequence

import numpy as np

from ..config import HotspotConfig, MatLayoutConfig
from ..contracts import (
    LayerStep,
    MaterialParameters,
    MatTileGeometry,
    MatTileState,
    ProvenanceLabel,
    SeabedExchange,
)
from .column import (
    bottom_conductance,
    build_column_parameters,
    solve_column_step,
    steady_state_flux_kg_per_m2_per_s,
    top_conductance,
)
from .geotextile import (
    DEFAULT_GEOTEXTILE,
    GeotextileLayer,
    encapsulated_conductances,
    geotextile_resistance_s_per_m,
)
from .degradation import (
    BURIAL_WARNING,
    DEFAULT_BURIAL_RESISTANCE_S_PER_M,
    DEFAULT_FOULING_BYPASS_COUPLING,
    apply_degradation_event,
    apply_degradation_events,
    buried_top_conductance,
    bypass_fraction,
    degradation_state,
    effective_cover_fraction,
    grow_burial,
    grow_fouling,
    saturation_state,
    tile_effective_flux_kg_per_m2_per_s,
)
from .flux import attenuation, bare_flux_from_exchange, flux_budget
from .material import (
    fouling_factors,
    sequence_of_elements,
    validate_allocation,
)

__all__ = [
    "LAYER_STATUS",
    "tile_id_for",
    "build_tile_geometry",
    "build_tile_states",
    "advance_reactive_layer",
    "release_from_damage",
    "scripted_exchange",
    "tile_summary",
    "grow_fouling",
    "grow_burial",
    "apply_degradation_event",
    "apply_degradation_events",
]

#: The values ``LayerStep.diagnostics['layer_status']`` can carry.
#:
#: ``loading``
#:     the layer is taking metal up; this is the ordinary case.
#: ``capacity_locked``
#:     every cell is at or above its accessible capacity, so uptake has
#:     stopped.  Sorbed metal is held, not released.
#: ``desorbing``
#:     at least one cell is giving metal back to its porewater because the
#:     capped isotherm sits below the current load.  Conservative, visible in
#:     ``flux_out``, and never silent.
#: ``out_of_service``
#:     the tile is displaced or switched off; the layer processes nothing and
#:     its footprint emits the bare flux through the coverage term.
#: ``no_source``
#:     nothing is driving the layer.
LAYER_STATUS = (
    "loading",
    "capacity_locked",
    "desorbing",
    "out_of_service",
    "no_source",
)


def tile_id_for(ix: int, iy: int) -> str:
    """``tile_{ix}_{iy}``, the identifier the whole repository uses."""
    return f"tile_{int(ix)}_{int(iy)}"


# ---------------------------------------------------------------------------
# Construction from the coordinator-owned configuration
# ---------------------------------------------------------------------------

def build_tile_geometry(
    mat_config: MatLayoutConfig,
    hotspot: HotspotConfig,
    ix: int,
    iy: int,
) -> MatTileGeometry:
    """Geometry of one tile of a square mat centred on the hotspot.

    ASSUMPTION, stated because the configuration does not settle it: the mat is
    a square of area ``coverage_fraction * hotspot.area_m2``, laid centred on
    ``(hotspot.x_m, hotspot.y_m)``, and ``HotspotConfig.x_m / y_m`` are read as
    the **centre** of the hotspot.  ``MatLayoutConfig.overlap_m`` is a
    deployment tolerance and is not used to enlarge the tiles here; overlapping
    tiles are rejected downstream rather than double counted.
    """
    if mat_config.tiles_x < 1 or mat_config.tiles_y < 1:
        raise ValueError(
            f"a mat needs at least one tile in each direction, got "
            f"{mat_config.tiles_x!r} x {mat_config.tiles_y!r}"
        )
    coverage = float(mat_config.coverage_fraction)
    if not (0.0 < coverage <= 1.0):
        raise ValueError(
            f"coverage_fraction must lie in (0, 1], got {coverage!r}"
        )
    if mat_config.thickness_m <= 0.0:
        raise ValueError(
            f"thickness_m must be strictly positive, got {mat_config.thickness_m!r}"
        )

    mat_side_m = math.sqrt(coverage * hotspot.area_m2)
    width = mat_side_m / mat_config.tiles_x
    length = mat_side_m / mat_config.tiles_y
    origin_x = float(hotspot.x_m) - 0.5 * mat_side_m
    origin_y = float(hotspot.y_m) - 0.5 * mat_side_m
    return MatTileGeometry(
        width_m=width,
        length_m=length,
        thickness_m=float(mat_config.thickness_m),
        x_m=origin_x + (ix + 0.5) * width,
        y_m=origin_y + (iy + 0.5) * length,
        bulk_density_kg_per_m3=float(mat_config.bulk_density_kg_per_m3),
        porosity=float(mat_config.porosity),
        edge_leakage_fraction=float(mat_config.edge_leakage_fraction),
        edge_leakage_interval=(
            None
            if mat_config.edge_leakage_interval is None
            else (
                float(mat_config.edge_leakage_interval[0]),
                float(mat_config.edge_leakage_interval[1]),
            )
        ),
    )


def build_tile_states(
    mat_config: MatLayoutConfig,
    installed_at_utc: datetime,
    materials: Mapping[str, MaterialParameters],
    *,
    hotspot: HotspotConfig | None = None,
    elements: Sequence[str] | None = None,
    initial_fouling_index: float = 0.0,
) -> tuple[MatTileState, ...]:
    """The ``tiles_x * tiles_y`` initial tile states of one mat.

    Identifiers are ``tile_{ix}_{iy}`` with ``ix`` across and ``iy`` along, so
    ``scenarios/registry.py`` can name ``tile_2_0`` and mean a specific module.

    ``MatLayoutConfig.preload_kg_per_m2`` is the stress-test entry point: a mat
    that is already part loaded when the demonstration starts, so saturation can
    be shown without inflating any uptake parameter.  It is laid down as a
    uniform sorbed profile, and a preload above the allocated capacity is
    rejected rather than silently clipped.
    """
    if installed_at_utc.tzinfo is None:
        raise ValueError("installed_at_utc must be timezone-aware UTC")
    if mat_config.n_layer_nodes < 1:
        raise ValueError(
            f"n_layer_nodes must be at least 1, got {mat_config.n_layer_nodes!r}"
        )
    if not (0.0 <= float(initial_fouling_index) <= 1.0):
        raise ValueError(
            f"initial_fouling_index must lie in [0, 1], got "
            f"{initial_fouling_index!r}"
        )
    validate_allocation(materials)
    hotspot = HotspotConfig() if hotspot is None else hotspot

    keys = list(elements) if elements is not None else list(materials)
    for key in mat_config.preload_kg_per_m2:
        if key not in keys:
            keys.append(key)

    n_nodes = int(mat_config.n_layer_nodes)
    sorbent_loading = (
        float(mat_config.bulk_density_kg_per_m3) * float(mat_config.thickness_m)
    )

    sorbed_profile: dict[str, np.ndarray] = {}
    for key in keys:
        preload = float(mat_config.preload_kg_per_m2.get(key, 0.0))
        if preload < 0.0 or not math.isfinite(preload):
            raise ValueError(
                f"preload_kg_per_m2[{key!r}] must be finite and non-negative, "
                f"got {preload!r}"
            )
        params = materials.get(key)
        if params is not None and preload > 0.0:
            capacity = sorbent_loading * params.allocation_fraction * params.q_max_kg_per_kg
            if preload > capacity * (1.0 + 1e-12):
                raise ValueError(
                    f"preload_kg_per_m2[{key!r}] = {preload!r} kg/m2 exceeds the "
                    f"allocated capacity {capacity!r} kg/m2 of its compartment"
                )
        loading = 0.0 if sorbent_loading <= 0.0 else preload / sorbent_loading
        sorbed_profile[key] = np.full(n_nodes, loading, dtype=float)

    states: list[MatTileState] = []
    for iy in range(int(mat_config.tiles_y)):
        for ix in range(int(mat_config.tiles_x)):
            states.append(
                MatTileState(
                    tile_id=tile_id_for(ix, iy),
                    media_id=mat_config.media_id,
                    installed_at_utc=installed_at_utc,
                    geometry=build_tile_geometry(mat_config, hotspot, ix, iy),
                    porewater_kg_per_m3={
                        key: np.zeros(n_nodes, dtype=float) for key in keys
                    },
                    sorbed_kg_per_kg={
                        key: sorbed_profile[key].copy() for key in keys
                    },
                    fouling_index=float(initial_fouling_index),
                    integrity_index=1.0,
                    burial_depth_m=0.0,
                    displacement_m=0.0,
                    displaced=False,
                    active=True,
                    service_count=0,
                )
            )
    return tuple(states)


# ---------------------------------------------------------------------------
# The frozen advance
# ---------------------------------------------------------------------------

def advance_reactive_layer(
    tile_state: MatTileState,
    exchange: SeabedExchange,
    material_parameters: Mapping[str, MaterialParameters],
    dt_s: float,
    *,
    geotextile: "GeotextileLayer | None" = DEFAULT_GEOTEXTILE,
) -> LayerStep:
    """Advance one tile's 1-D reactive layer over ``dt_s``.

    The reactive core is encapsulated between two carrier geotextiles, which
    enter as inert diffusive resistances in series at both faces. Passing
    ``geotextile=None`` removes them and recovers the bare-core model, which is
    kept so the cost of the encapsulation can be measured rather than assumed.

    Exactly MODEL_SPEC section 3, per element, solved fully implicitly with the
    sorption exchange eliminated analytically (see ``column.py`` for why an
    operator split is forbidden here).

    Returns a :class:`~reactive_seabed_mat.contracts.LayerStep` whose
    ``flux_out_kg_per_m2_per_s`` is the residual flux **per unit area of intact
    layer**.  What the tile's whole footprint emits, once local damage, burial,
    displacement and the fouling bypass are taken into account, is reported
    separately in ``diagnostics['effective_flux_out_kg_per_m2_per_s']``, because
    a covered square metre and a torn square metre are different things and the
    contract keeps them apart.

    Per element, over the step::

        retained_delta = (J_in - J_out) dt

    to round-off.  ``released_kg_per_m2`` is zero here: metal leaves the layer
    through ``J_out`` and nowhere else.  An explicit release (a tear that spills
    media) is :func:`release_from_damage`.
    """
    if dt_s < 0.0:
        raise ValueError(f"dt_s must be non-negative, got {dt_s!r}")
    if exchange.tile_id != tile_state.tile_id:
        raise ValueError(
            f"exchange is for tile {exchange.tile_id!r} but the state is tile "
            f"{tile_state.tile_id!r}"
        )
    validate_allocation(material_parameters)

    environment = dict(exchange.environment or {})
    burial_resistance = float(
        environment.get("burial_resistance_s_per_m", DEFAULT_BURIAL_RESISTANCE_S_PER_M)
    )
    bypass_coupling = float(
        environment.get("fouling_bypass_coupling", DEFAULT_FOULING_BYPASS_COUPLING)
    )
    elements = sequence_of_elements(material_parameters)
    n_nodes = tile_state.n_nodes
    out_of_service = tile_state.displaced or not tile_state.active

    corrections: list[dict[str, Any]] = []
    missing_profiles: list[str] = []

    new_porewater: dict[str, np.ndarray] = dict(tile_state.porewater_kg_per_m3)
    new_sorbed: dict[str, np.ndarray] = dict(tile_state.sorbed_kg_per_kg)
    flux_in: dict[str, float] = {}
    flux_out: dict[str, float] = {}
    retained_delta: dict[str, float] = {}
    released: dict[str, float] = {}
    bare_flux: dict[str, float] = {}
    bare_flux_source: dict[str, str] = {}
    barrier_flux: dict[str, float] = {}
    attenuation_by_element: dict[str, float | None] = {}
    effective_flux: dict[str, float] = {}
    clip_per_m2: dict[str, float] = {}
    clip_kg: dict[str, float] = {}
    negative_clip_per_m2: dict[str, float] = {}
    conservation_residual: dict[str, float] = {}
    column_diagnostics: dict[str, dict[str, Any]] = {}
    picard_converged = True

    bypass = bypass_fraction(
        tile_state.geometry.edge_leakage_fraction,
        tile_state.fouling_index,
        bypass_coupling,
    )
    cover = effective_cover_fraction(tile_state.coverage_fraction, bypass.value)

    status_flags: set[str] = set()

    for key in elements:
        params = material_parameters[key]
        column = build_column_parameters(
            tile_state.geometry,
            params,
            n_nodes=n_nodes,
            seepage_velocity_m_per_s=exchange.seepage_velocity_m_per_s,
            film_transfer_m_per_s=exchange.film_transfer_m_per_s,
            fouling_index=tile_state.fouling_index,
        )
        clean_g_top = top_conductance(column)
        buried_g_top = buried_top_conductance(
            clean_g_top, tile_state.burial_depth_m, burial_resistance
        )
        # The carrier geotextiles sit outside everything else: sediment, bottom
        # geotextile, reactive core, top geotextile, burial, benthic film. They
        # are added last so the order of the series matches the order of the
        # physical layers.
        g_bot, g_top = encapsulated_conductances(
            clean_bottom_conductance_m_per_s=bottom_conductance(column),
            clean_top_conductance_m_per_s=buried_g_top,
            bottom_layer=geotextile,
            top_layer=geotextile,
        )

        if key in tile_state.porewater_kg_per_m3:
            porewater = np.asarray(tile_state.porewater_kg_per_m3[key], dtype=float)
        else:
            missing_profiles.append(key)
            porewater = np.zeros(n_nodes, dtype=float)
        if key in tile_state.sorbed_kg_per_kg:
            sorbed = np.asarray(tile_state.sorbed_kg_per_kg[key], dtype=float)
        else:
            if key not in missing_profiles:
                missing_profiles.append(key)
            sorbed = np.zeros(n_nodes, dtype=float)

        c_sed = float(exchange.sediment_porewater_kg_per_m3.get(key, 0.0))
        c_water = float(exchange.bottom_water_kg_per_m3.get(key, 0.0))
        declared_bare, source = bare_flux_from_exchange(exchange, key)
        bare_flux[key] = declared_bare
        bare_flux_source[key] = source

        # The barrier limit: what this mat would do with no chemical capacity
        # left at all. Reported per element because the difference between it
        # and the actual attenuation IS the sorbent's contribution, and for a
        # strongly complexed metal like copper that difference is close to zero.
        barrier_flux[key] = steady_state_flux_kg_per_m2_per_s(
            column,
            c_sed,
            c_water,
            top_conductance_m_per_s=g_top,
            bottom_resistance_s_per_m=geotextile_resistance_s_per_m(geotextile),
        )

        if out_of_service:
            # The tile is off its footprint or switched off: the layer sees
            # nothing, holds what it holds, and the seabed it used to cover
            # emits the bare flux through the coverage term instead.
            new_porewater[key] = porewater
            new_sorbed[key] = sorbed
            flux_in[key] = 0.0
            flux_out[key] = 0.0
            retained_delta[key] = 0.0
            released[key] = 0.0
            clip_per_m2[key] = 0.0
            clip_kg[key] = 0.0
            negative_clip_per_m2[key] = 0.0
            conservation_residual[key] = 0.0
            attenuation_by_element[key] = attenuation(0.0, declared_bare)
            effective_flux[key] = tile_effective_flux_kg_per_m2_per_s(
                0.0, declared_bare, tile_state.coverage_fraction, bypass.value
            )
            column_diagnostics[key] = {
                "skipped": True,
                "reason": "tile displaced or inactive",
                "top_conductance_m_per_s": g_top,
            }
            status_flags.add("out_of_service")
            continue

        step = solve_column_step(
            porewater,
            sorbed,
            column,
            dt_s,
            c_sed,
            c_water,
            top_conductance_m_per_s=g_top,
            bottom_conductance_m_per_s=g_bot,
        )
        picard_converged = picard_converged and step.picard_converged

        new_porewater[key] = step.porewater_kg_per_m3
        new_sorbed[key] = step.sorbed_kg_per_kg
        flux_in[key] = step.flux_in_kg_per_m2_per_s
        flux_out[key] = step.flux_out_kg_per_m2_per_s
        retained_delta[key] = step.stored_delta_kg_per_m2
        released[key] = 0.0
        clip_per_m2[key] = step.clip_correction_kg_per_m2
        clip_kg[key] = (
            step.clip_correction_kg_per_m2 * tile_state.geometry.footprint_area_m2
        )
        negative_clip_per_m2[key] = step.negative_clip_kg_per_m2
        conservation_residual[key] = step.conservation_residual_kg_per_m2(dt_s)
        attenuation_by_element[key] = attenuation(
            step.flux_out_kg_per_m2_per_s, declared_bare
        )
        effective_flux[key] = tile_effective_flux_kg_per_m2_per_s(
            step.flux_out_kg_per_m2_per_s,
            declared_bare,
            tile_state.coverage_fraction,
            bypass.value,
        )
        column_diagnostics[key] = dict(step.diagnostics)

        if step.clip_correction_kg_per_m2 > 0.0:
            corrections.append(
                {
                    "kind": "sorbed_capacity_clipped_excess_returned_to_porewater",
                    "element": key,
                    "mass_kg_per_m2": step.clip_correction_kg_per_m2,
                }
            )
        if step.negative_clip_kg_per_m2 > 0.0:
            corrections.append(
                {
                    "kind": "negative_porewater_clipped_to_zero",
                    "element": key,
                    "mass_kg_per_m2": step.negative_clip_kg_per_m2,
                }
            )
        if not step.picard_converged:
            corrections.append(
                {
                    "kind": "picard_branch_mask_did_not_settle",
                    "element": key,
                    "iterations": step.picard_iterations,
                    "note": (
                        "the saturated / unsaturated mask was still moving; the "
                        "sorbed update used the mask the matrix used, so mass is "
                        "still conserved exactly"
                    ),
                }
            )

        if c_sed <= 0.0 and c_water <= 0.0:
            status_flags.add("no_source")
        if int(step.diagnostics.get("desorbing_cells", 0)) > 0:
            status_flags.add("desorbing")
        if int(step.diagnostics.get("locked_cells", 0)) >= n_nodes:
            status_flags.add("capacity_locked")

    if not status_flags:
        status_flags.add("loading")
    layer_status = tuple(sorted(status_flags))

    # Continuous degradation is applied after the transport step, and only when
    # the exchange carries a growth rate.  Otherwise the caller owns it.
    fouling_before = float(tile_state.fouling_index)
    fouling_growth = environment.get("fouling_growth_per_s")
    if fouling_growth is None:
        fouling_after = fouling_before
        fouling_source = "not_applied_caller_owns_fouling"
    else:
        fouling_after = min(1.0, fouling_before + float(fouling_growth) * float(dt_s))
        fouling_source = "SeabedExchange.environment['fouling_growth_per_s']"

    burial_before = float(tile_state.burial_depth_m)
    burial_growth = environment.get("burial_growth_m_per_s")
    if burial_growth is None:
        burial_after = burial_before
        burial_source = "not_applied_caller_owns_burial"
    else:
        burial_after = burial_before + float(burial_growth) * float(dt_s)
        burial_source = "SeabedExchange.environment['burial_growth_m_per_s']"

    new_state = replace(
        tile_state,
        porewater_kg_per_m3=new_porewater,
        sorbed_kg_per_kg=new_sorbed,
        fouling_index=float(fouling_after),
        burial_depth_m=float(burial_after),
    )

    diagnostics: dict[str, Any] = {
        "model_ref": "docs/MODEL_SPEC.md sections 3 and 4",
        "solver": "scipy_banded_implicit",
        "operator_split": False,
        "dt_s": float(dt_s),
        "time_utc": exchange.time_utc,
        "tile_id": tile_state.tile_id,
        "media_id": tile_state.media_id,
        "layer_status": layer_status,
        "out_of_service": bool(out_of_service),
        "n_nodes": n_nodes,
        "dz_m": tile_state.dz_m(),
        "bare_flux_kg_per_m2_per_s": bare_flux,
        "bare_flux_source": bare_flux_source,
        "barrier_flux_kg_per_m2_per_s": barrier_flux,
        "attenuation": attenuation_by_element,
        "effective_flux_out_kg_per_m2_per_s": effective_flux,
        "coverage_fraction": float(tile_state.coverage_fraction),
        "effective_cover_fraction": cover,
        "integrity_index": float(tile_state.integrity_index),
        "displaced": bool(tile_state.displaced),
        "burial_depth_m": burial_after,
        "burial_resistance_s_per_m": burial_resistance,
        "burial_warning": BURIAL_WARNING if burial_after > 0.0 else "",
        **bypass.as_dict(),
        "fouling_index_before": fouling_before,
        "fouling_index_after": float(fouling_after),
        "fouling_growth_source": fouling_source,
        "burial_depth_m_before": burial_before,
        "burial_growth_source": burial_source,
        "fouling_factors": {
            key: fouling_factors(material_parameters[key], fouling_before).as_dict()
            for key in elements
        },
        "clip_correction_kg": clip_kg,
        "clip_correction_kg_per_m2": clip_per_m2,
        "negative_clip_kg_per_m2": negative_clip_per_m2,
        "conservation_residual_kg_per_m2": conservation_residual,
        "picard_converged": bool(picard_converged),
        "missing_profiles": tuple(missing_profiles),
        "corrections": tuple(corrections),
        "column": column_diagnostics,
        "saturation": saturation_state(new_state, material_parameters),
        "driving_is_measured": bool(exchange.driving_is_measured),
        "provenance": ProvenanceLabel.SYNTHETIC_DEMO.value,
    }

    return LayerStep(
        new_state=new_state,
        flux_in_kg_per_m2_per_s=flux_in,
        flux_out_kg_per_m2_per_s=flux_out,
        retained_delta_kg_per_m2=retained_delta,
        released_kg_per_m2=released,
        exchange=exchange,
        diagnostics=diagnostics,
    )


# ---------------------------------------------------------------------------
# Explicit release
# ---------------------------------------------------------------------------

def release_from_damage(
    tile_state: MatTileState,
    exchange: SeabedExchange,
    *,
    released_fraction_by_element: Mapping[str, float] | None = None,
    released_kg_per_m2_by_element: Mapping[str, float] | None = None,
    reason: str = "assumed damage event that spilled loaded media",
) -> LayerStep:
    """An explicit release event: sorbed metal leaves the layer.

    The ordinary advance never does this.  A tear that merely opens a bypass
    path does not liberate sorbed metal either: the media is still there, it is
    simply no longer in the flow path, which is what ``integrity_index``
    expresses.  Physically spilling loaded media is a different, rarer event,
    and it has to be stated, which is what this function is for.

    Exactly one of ``released_fraction_by_element`` (share of the currently
    sorbed mass) or ``released_kg_per_m2_by_element`` (absolute kg per unit
    area) must be given.  A request above what is held is clipped to what is
    held, and the clipping is recorded.
    """
    if (released_fraction_by_element is None) == (
        released_kg_per_m2_by_element is None
    ):
        raise ValueError(
            "give exactly one of released_fraction_by_element or "
            "released_kg_per_m2_by_element"
        )
    if exchange.tile_id != tile_state.tile_id:
        raise ValueError(
            f"exchange is for tile {exchange.tile_id!r} but the state is tile "
            f"{tile_state.tile_id!r}"
        )

    dz = tile_state.dz_m()
    rho_b = tile_state.geometry.bulk_density_kg_per_m3
    corrections: list[dict[str, Any]] = []
    released: dict[str, float] = {}
    new_sorbed: dict[str, np.ndarray] = dict(tile_state.sorbed_kg_per_kg)
    retained_delta: dict[str, float] = {}

    if released_fraction_by_element is not None:
        keys = list(released_fraction_by_element)
    else:
        keys = list(released_kg_per_m2_by_element or {})

    for key in keys:
        sorbed = np.asarray(tile_state.sorbed_kg_per_kg[key], dtype=float)
        held = float(np.sum(rho_b * sorbed) * dz)
        if released_fraction_by_element is not None:
            fraction = float(released_fraction_by_element[key])
            if not (0.0 <= fraction <= 1.0):
                raise ValueError(
                    f"released fraction for {key!r} must lie in [0, 1], got "
                    f"{fraction!r}"
                )
            requested = held * fraction
        else:
            requested = float((released_kg_per_m2_by_element or {})[key])
            if requested < 0.0 or not math.isfinite(requested):
                raise ValueError(
                    f"released mass for {key!r} must be finite and non-negative"
                )
        actual = min(requested, held)
        if actual < requested:
            corrections.append(
                {
                    "kind": "release_clipped_to_sorbed_mass",
                    "element": key,
                    "requested_kg_per_m2": requested,
                    "released_kg_per_m2": actual,
                }
            )
        scale = 0.0 if held <= 0.0 else (held - actual) / held
        new_sorbed[key] = sorbed * scale
        released[key] = actual
        retained_delta[key] = -actual

    new_state = replace(tile_state, sorbed_kg_per_kg=new_sorbed)
    zero = {key: 0.0 for key in released}
    diagnostics: dict[str, Any] = {
        "model_ref": "docs/MODEL_SPEC.md section 4, explicit release",
        "reason": reason,
        "time_utc": exchange.time_utc,
        "released_kg_per_m2": dict(released),
        "released_kg": {
            key: value * tile_state.geometry.footprint_area_m2
            for key, value in released.items()
        },
        "corrections": tuple(corrections),
        "note": (
            "The released mass leaves the layer inventory. A caller that also "
            "keeps a water ledger must add exactly this mass to it: nothing is "
            "destroyed here."
        ),
        "provenance": ProvenanceLabel.SYNTHETIC_DEMO.value,
    }
    return LayerStep(
        new_state=new_state,
        flux_in_kg_per_m2_per_s=dict(zero),
        flux_out_kg_per_m2_per_s=dict(zero),
        retained_delta_kg_per_m2=retained_delta,
        released_kg_per_m2=released,
        exchange=exchange,
        diagnostics=diagnostics,
    )


# ---------------------------------------------------------------------------
# LABELLED_STUB: scripted exchange, standing in for build_seabed_exchange
# ---------------------------------------------------------------------------

def scripted_exchange(
    tile_state: MatTileState,
    time_utc: datetime,
    dt_s: float,
    sediment_porewater_kg_per_m3: Mapping[str, float],
    *,
    bottom_water_kg_per_m3: Mapping[str, float] | None = None,
    seepage_velocity_m_per_s: float = 3.0e-8,
    film_transfer_m_per_s: float = 5.0e-7,
    cell_indices: Sequence[int] = (0,),
    cell_weights: Sequence[float] = (1.0,),
    environment: Mapping[str, float] | None = None,
    diagnostics: Mapping[str, Any] | None = None,
) -> SeabedExchange:
    """LABELLED_STUB: a scripted :class:`SeabedExchange` for offline runs.

    This is the reactive-layer branch's stand-in for
    ``coastal_transport.build_seabed_exchange``, which owns the real thing.  It
    computes the uncapped reference flux from the same driving conditions the
    layer sees, so "with mat" and "without mat" genuinely share a source.

    Defaults are the demonstration baseline of ``config.HotspotConfig``
    (seepage 3e-8 m/s, benthic film 5e-7 m/s), both ASSUMPTIONS.
    """
    if dt_s < 0.0:
        raise ValueError(f"dt_s must be non-negative, got {dt_s!r}")
    if time_utc.tzinfo is None:
        raise ValueError("time_utc must be timezone-aware UTC")
    if len(cell_indices) != len(cell_weights):
        raise ValueError("cell_indices and cell_weights must have the same length")
    weight_sum = sum(float(weight) for weight in cell_weights)
    if abs(weight_sum - 1.0) > 1e-9:
        raise ValueError(f"cell_weights must sum to 1, they sum to {weight_sum!r}")

    water = dict(bottom_water_kg_per_m3 or {})
    sediment = {key: float(value) for key, value in sediment_porewater_kg_per_m3.items()}
    bare = {
        key: (float(seepage_velocity_m_per_s) + float(film_transfer_m_per_s))
        * (value - float(water.get(key, 0.0)))
        for key, value in sediment.items()
    }
    return SeabedExchange(
        tile_id=tile_state.tile_id,
        time_utc=time_utc,
        dt_s=float(dt_s),
        sediment_porewater_kg_per_m3=sediment,
        bottom_water_kg_per_m3={key: float(water.get(key, 0.0)) for key in sediment},
        seepage_velocity_m_per_s=float(seepage_velocity_m_per_s),
        film_transfer_m_per_s=float(film_transfer_m_per_s),
        bare_flux_kg_per_m2_per_s=bare,
        cell_indices=tuple(int(index) for index in cell_indices),
        cell_weights=tuple(float(weight) for weight in cell_weights),
        driving_is_measured=False,
        environment=dict(environment or {}),
        diagnostics={
            "source": (
                "LABELLED_STUB reactive_seabed_mat.reactive_layer.tile."
                "scripted_exchange"
            ),
            "replace_with": (
                "reactive_seabed_mat.coastal_transport.build_seabed_exchange"
            ),
            "provenance": ProvenanceLabel.SYNTHETIC_DEMO.value,
            **dict(diagnostics or {}),
        },
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def tile_summary(
    tile_state: MatTileState,
    material_parameters: Mapping[str, MaterialParameters],
    *,
    layer_step: LayerStep | None = None,
    fouling_bypass_coupling: float = DEFAULT_FOULING_BYPASS_COUPLING,
    burial_resistance_s_per_m: float = DEFAULT_BURIAL_RESISTANCE_S_PER_M,
) -> dict[str, Any]:
    """A JSON-ready summary of one tile (SI units throughout).

    Carries the four degradation modes side by side, never collapsed into a
    single health number, and the flux budget when a step is supplied.
    """
    elements = sequence_of_elements(material_parameters)
    summary: dict[str, Any] = {
        "tile_id": tile_state.tile_id,
        "media_id": tile_state.media_id,
        "installed_at_utc": tile_state.installed_at_utc,
        "service_count": tile_state.service_count,
        "active": bool(tile_state.active),
        "geometry": {
            "width_m": tile_state.geometry.width_m,
            "length_m": tile_state.geometry.length_m,
            "thickness_m": tile_state.geometry.thickness_m,
            "x_m": tile_state.geometry.x_m,
            "y_m": tile_state.geometry.y_m,
            "footprint_area_m2": tile_state.geometry.footprint_area_m2,
            "sorbent_loading_kg_per_m2": (
                tile_state.geometry.sorbent_loading_kg_per_m2
            ),
            "sorbent_mass_kg": tile_state.geometry.sorbent_mass_kg,
            "porosity": tile_state.geometry.porosity,
            "bulk_density_kg_per_m3": tile_state.geometry.bulk_density_kg_per_m3,
        },
        "retained_kg_per_m2": {
            key: tile_state.retained_kg_per_m2(key)
            for key in elements
            if key in tile_state.porewater_kg_per_m3
        },
        "retained_kg": {
            key: tile_state.retained_kg(key)
            for key in elements
            if key in tile_state.porewater_kg_per_m3
        },
        "capacity_kg_per_m2": {
            key: tile_state.capacity_kg_per_m2(material_parameters[key])
            for key in elements
        },
        "saturation_fraction": {
            key: tile_state.saturation_fraction(material_parameters[key])
            for key in elements
        },
        "degradation": degradation_state(
            tile_state,
            material_parameters,
            fouling_bypass_coupling=fouling_bypass_coupling,
            burial_resistance_s_per_m=burial_resistance_s_per_m,
        ),
        "provenance": ProvenanceLabel.SYNTHETIC_DEMO.value,
    }
    if layer_step is not None and layer_step.exchange is not None:
        summary["flux"] = {
            key: flux_budget(layer_step, layer_step.exchange, key).as_dict()
            for key in elements
        }
        summary["effective_flux_out_kg_per_m2_per_s"] = dict(
            layer_step.diagnostics.get("effective_flux_out_kg_per_m2_per_s", {})
        )
        summary["layer_status"] = layer_step.diagnostics.get("layer_status", ())
    return summary
