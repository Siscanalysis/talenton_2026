"""The 1-D reactive layer and the four degradation modes (``feat/reactive-layer``).

Implements ``docs/MODEL_SPEC.md`` sections 3 and 4: a fully implicit coupled
transport-and-sorption solve through the thickness of one mat tile, the two
boundary fluxes it produces, the attenuation derived from them, the four
independent ways a mat stops working, modular replacement into a
retrieved-media ledger, and a conditional breakthrough forecast that is an
interval or nothing at all.

The mat **attenuates a flux**.  There is no frontal area, no swept volume, no
interception efficiency, and nothing here is ever subtracted from a
water-column cell.

Every number produced by this package is a synthetic demonstration value unless
the caller supplies something better.  Literature capacities from [S01] and
[S04] are not operating specifications of this mat.

Typical use, without a map and without hardware::

    from datetime import datetime, timezone
    from reactive_seabed_mat.config import HotspotConfig, MatLayoutConfig
    from reactive_seabed_mat.reactive_layer import (
        advance_reactive_layer, build_material_map, build_tile_states,
        scripted_exchange,
    )

    mat = MatLayoutConfig()
    materials = build_material_map(mat)
    tiles = build_tile_states(
        mat, datetime(2026, 9, 8, tzinfo=timezone.utc), materials,
        hotspot=HotspotConfig(),
    )
    exchange = scripted_exchange(
        tiles[0], tiles[0].installed_at_utc, 21600.0,
        {"Pb": 1.0e-3, "Hg": 8.0e-6},
    )
    step = advance_reactive_layer(tiles[0], exchange, materials, 21600.0)
    step.flux_out_kg_per_m2_per_s["Pb"]     # the residual flux, kg m^-2 s^-1
    step.attenuation("Pb", exchange.bare_flux_kg_per_m2_per_s["Pb"])

A ``design.py`` used to sit here, carried over from the vertical-panel concept.
It computed an interception efficiency over a frontal area, which is not what
this mat does, and it could no longer be imported at all.  It was removed rather
than ported; the design sweep is listed as open work in ``README.md``.
"""

from __future__ import annotations

from .column import (
    DEFAULT_PICARD_ITERATIONS,
    ColumnParameters,
    ColumnStep,
    build_column_parameters,
    solve_column_step,
    steady_state_flux_kg_per_m2_per_s,
    stored_kg_per_m2,
    top_conductance,
)
from .degradation import (
    BURIAL_WARNING,
    DEFAULT_BURIAL_RESISTANCE_S_PER_M,
    DEFAULT_FOULING_BYPASS_COUPLING,
    BypassFraction,
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
from .flux import (
    FluxBudget,
    FluxInterval,
    attenuation,
    attenuation_interval,
    bare_flux_from_exchange,
    bare_flux_kg_per_m2_per_s,
    ensemble_flux_interval,
    flux_budget,
)
from .forecast import (
    CONDITIONAL_NOTE,
    DEFAULT_BREAKTHROUGH_FRACTION,
    LayerForecast,
    breakthrough_interval,
    forecast_breakthrough,
    forecast_tile,
    loading_fraction,
    loading_kg_per_kg,
    remaining_capacity_kg_per_m2,
    sorbed_kg_per_m2,
    supply_limited_breakthrough_s,
    time_to_target_loading,
)
from .material import (
    FoulingFactors,
    ParameterEnsemble,
    build_material_map,
    build_material_parameters,
    contact_concentration_kg_per_m3,
    effective_d_eff_m2_per_s,
    effective_q_max_kg_per_kg,
    effective_rate_per_s,
    equilibrium_loading,
    exponential_step,
    fouling_factors,
    sample_parameter_ensemble,
    scale_material,
    sequence_of_elements,
    solid_loading_kg_per_kg,
    validate_allocation,
)
from .service import (
    MEDIA_DISPOSAL_NOTE,
    RetrievedMediaLedger,
    next_media_id,
    replace_media,
    replace_tiles,
    replacement_cost_eur,
)
from .tile import (
    LAYER_STATUS,
    advance_reactive_layer,
    build_tile_geometry,
    build_tile_states,
    release_from_damage,
    scripted_exchange,
    tile_id_for,
    tile_summary,
)

__all__ = [
    # column
    "ColumnParameters",
    "ColumnStep",
    "DEFAULT_PICARD_ITERATIONS",
    "build_column_parameters",
    "solve_column_step",
    "steady_state_flux_kg_per_m2_per_s",
    "stored_kg_per_m2",
    "top_conductance",
    # flux
    "FluxBudget",
    "FluxInterval",
    "attenuation",
    "attenuation_interval",
    "bare_flux_from_exchange",
    "bare_flux_kg_per_m2_per_s",
    "ensemble_flux_interval",
    "flux_budget",
    # degradation
    "BURIAL_WARNING",
    "BypassFraction",
    "DEFAULT_BURIAL_RESISTANCE_S_PER_M",
    "DEFAULT_FOULING_BYPASS_COUPLING",
    "apply_degradation_event",
    "apply_degradation_events",
    "buried_top_conductance",
    "bypass_fraction",
    "degradation_state",
    "effective_cover_fraction",
    "grow_burial",
    "grow_fouling",
    "saturation_state",
    "tile_effective_flux_kg_per_m2_per_s",
    # material
    "FoulingFactors",
    "ParameterEnsemble",
    "build_material_map",
    "build_material_parameters",
    "contact_concentration_kg_per_m3",
    "effective_d_eff_m2_per_s",
    "effective_q_max_kg_per_kg",
    "effective_rate_per_s",
    "equilibrium_loading",
    "exponential_step",
    "fouling_factors",
    "sample_parameter_ensemble",
    "scale_material",
    "sequence_of_elements",
    "solid_loading_kg_per_kg",
    "validate_allocation",
    # tile
    "LAYER_STATUS",
    "advance_reactive_layer",
    "build_tile_geometry",
    "build_tile_states",
    "release_from_damage",
    "scripted_exchange",
    "tile_id_for",
    "tile_summary",
    # service
    "MEDIA_DISPOSAL_NOTE",
    "RetrievedMediaLedger",
    "next_media_id",
    "replace_media",
    "replace_tiles",
    "replacement_cost_eur",
    # forecast
    "CONDITIONAL_NOTE",
    "DEFAULT_BREAKTHROUGH_FRACTION",
    "LayerForecast",
    "breakthrough_interval",
    "forecast_breakthrough",
    "forecast_tile",
    "loading_fraction",
    "loading_kg_per_kg",
    "remaining_capacity_kg_per_m2",
    "sorbed_kg_per_m2",
    "supply_limited_breakthrough_s",
    "time_to_target_loading",
]
