"""Reduced material and maintenance model (``feat/mesh-care``).

Implements ``docs/MODEL_SPEC.md`` section 4: a capped linear isotherm with a
first-order approach to equilibrium, finite allocated capacity per element,
fouling that blocks access without erasing sorbed metal, explicit release
events, media replacement into a retrieved-media ledger, a conditional
remaining-life forecast and a small deterministic design comparison.

Every number produced here is a synthetic demonstration value unless the
caller supplies something better.  Literature capacities from [S01] and [S04]
are **not** operating specifications of this mesh.

Typical use, without a map and without hardware::

    from datetime import datetime, timezone
    from mesh_demo.config import PanelConfig
    from mesh_demo.micro import (
        advance_panel, build_material_map, build_panel_state,
        scripted_contact_batch,
    )

    panel_config = PanelConfig()
    materials = build_material_map(panel_config)
    state = build_panel_state(
        panel_config, datetime(2026, 9, 8, tzinfo=timezone.utc), materials
    )
    batch = scripted_contact_batch(
        state, state.installed_at_utc, 600.0, {"Pb": 1e-7}, speed_m_per_s=0.12
    )
    step = advance_panel(state, batch, materials, 600.0)
    step.uptake_kg_by_element["Pb"]  # the kg the macro model removes, once
"""

from __future__ import annotations

from .design import (
    DEFAULT_SCENARIOS,
    DEFAULT_SERVICE_INTERVALS_S,
    DEFAULT_SORBENT_MASSES_KG,
    WEAK_BENEFIT_CAPTURE_FRACTION,
    WEAK_BENEFIT_YIELD_MG_PER_1000_EUR,
    DesignOption,
    DesignScenario,
    design_comparison_document,
    run_design_comparison,
    write_design_comparison,
)
from .forecast import (
    CONDITIONAL_NOTE,
    DEFAULT_TARGET_LOADING_FRACTION,
    PanelForecast,
    forecast_loading,
    forecast_panel,
    loading_fraction,
    loading_kg_per_kg,
    remaining_capacity_kg,
    remaining_life_interval,
    remaining_life_s,
    time_to_target_loading,
)
from .material import (
    FoulingFactors,
    ParameterEnsemble,
    build_material_map,
    build_material_parameters,
    contact_concentration_kg_per_m3,
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
from .panel import (
    BINDING_CONSTRAINTS,
    advance_panel,
    build_panel_geometry,
    build_panel_state,
    grow_fouling,
    panel_summary,
    release_from_damage,
    scripted_contact_batch,
)
from .service import (
    MEDIA_DISPOSAL_NOTE,
    RetrievedMediaLedger,
    next_media_id,
    replace_media,
    replacement_cost_eur,
)

__all__ = [
    # material
    "FoulingFactors",
    "ParameterEnsemble",
    "build_material_map",
    "build_material_parameters",
    "contact_concentration_kg_per_m3",
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
    # panel
    "BINDING_CONSTRAINTS",
    "advance_panel",
    "build_panel_geometry",
    "build_panel_state",
    "grow_fouling",
    "panel_summary",
    "release_from_damage",
    "scripted_contact_batch",
    # service
    "MEDIA_DISPOSAL_NOTE",
    "RetrievedMediaLedger",
    "next_media_id",
    "replace_media",
    "replacement_cost_eur",
    # forecast
    "CONDITIONAL_NOTE",
    "DEFAULT_TARGET_LOADING_FRACTION",
    "PanelForecast",
    "forecast_loading",
    "forecast_panel",
    "loading_fraction",
    "loading_kg_per_kg",
    "remaining_capacity_kg",
    "remaining_life_interval",
    "remaining_life_s",
    "time_to_target_loading",
    # design
    "DEFAULT_SCENARIOS",
    "DEFAULT_SERVICE_INTERVALS_S",
    "DEFAULT_SORBENT_MASSES_KG",
    "DesignOption",
    "DesignScenario",
    "WEAK_BENEFIT_CAPTURE_FRACTION",
    "WEAK_BENEFIT_YIELD_MG_PER_1000_EUR",
    "design_comparison_document",
    "run_design_comparison",
    "write_design_comparison",
]
