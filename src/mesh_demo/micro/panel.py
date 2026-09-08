"""Panel state advance: the bounded transfer of MODEL_SPEC section 4.

``advance_panel`` is the frozen signature of ``contracts/DATA_CONTRACT.md``
section 2.  It is the **only** place where metal moves from water to mesh, and
the kg it reports is exactly the kg the macro model must remove, once.  The
batch it answered is echoed back in ``PanelStep.contact_batch`` so
``apply_transfers`` can put the mass back in the right cells with the right
weights without a second argument.

Nothing here destroys metal.  Fouling reduces access and rate; it never
reduces ``retained_kg``.  A desorption or damage event returns an explicit
``release_kg_by_element`` that the transport branch adds back to the water.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime
from typing import Any, Mapping, Sequence

from ..config import PanelConfig
from ..contracts import (
    ContactBatch,
    MaterialParameters,
    PanelGeometry,
    PanelState,
    PanelStep,
    ProvenanceLabel,
)
from .material import (
    equilibrium_loading,
    exponential_step,
    fouling_factors,
    sequence_of_elements,
    validate_allocation,
)

__all__ = [
    "BINDING_CONSTRAINTS",
    "build_panel_geometry",
    "build_panel_state",
    "advance_panel",
    "grow_fouling",
    "release_from_damage",
    "scripted_contact_batch",
    "panel_summary",
]

#: The labels ``PanelStep.diagnostics['binding_constraint']`` can carry.
#: ``kinetics``, ``available_mass`` and ``capacity`` are the three of
#: MODEL_SPEC section 4.  ``no_spontaneous_desorption`` records the lower clip
#: at zero: the isotherm wanted to give metal back, and the model refuses to do
#: that implicitly (release is an explicit event, see ``release_from_damage``).
#: ``inactive_panel`` records a panel that is switched off.
BINDING_CONSTRAINTS = (
    "kinetics",
    "available_mass",
    "capacity",
    "no_spontaneous_desorption",
    "inactive_panel",
)

#: Relative slack used when deciding which of two nearly equal bounds was the
#: active one.  It only affects the diagnostic label, never the transferred kg.
_LABEL_TOLERANCE = 1e-12


# ---------------------------------------------------------------------------
# Construction from the coordinator-owned configuration
# ---------------------------------------------------------------------------

def build_panel_geometry(panel_config: PanelConfig) -> PanelGeometry:
    """Typed geometry for one configured panel."""
    if panel_config.width_m <= 0.0 or panel_config.height_m <= 0.0:
        raise ValueError(
            f"panel {panel_config.panel_id!r} must have a positive frontal area"
        )
    phi = float(panel_config.interception_efficiency)
    if not (0.0 <= phi <= 1.0):
        raise ValueError(
            f"interception_efficiency must lie in [0, 1], got {phi!r}; it is a "
            "documented, uncertain contact fraction, not a gain"
        )
    return PanelGeometry(
        width_m=float(panel_config.width_m),
        height_m=float(panel_config.height_m),
        x_m=float(panel_config.x_m),
        y_m=float(panel_config.y_m),
        interception_efficiency=phi,
        interception_interval=(
            None
            if panel_config.interception_interval is None
            else (
                float(panel_config.interception_interval[0]),
                float(panel_config.interception_interval[1]),
            )
        ),
    )


def build_panel_state(
    panel_config: PanelConfig,
    installed_at_utc: datetime,
    materials: Mapping[str, MaterialParameters],
    *,
    elements: Sequence[str] | None = None,
) -> PanelState:
    """Initial panel state, including any explicit ``preload_kg``.

    ``preload_kg`` is the stress-test entry point of the build brief: a panel
    that is already part-loaded when the demonstration starts, so saturation
    can be shown without inflating the uptake parameters.  A preload above the
    nominal capacity of its compartment is rejected rather than silently
    clipped.
    """
    if installed_at_utc.tzinfo is None:
        raise ValueError("installed_at_utc must be timezone-aware UTC")
    if panel_config.sorbent_mass_kg < 0.0:
        raise ValueError(
            f"sorbent_mass_kg must be non-negative, got {panel_config.sorbent_mass_kg!r}"
        )
    validate_allocation(materials)

    keys = list(elements) if elements is not None else list(materials)
    for key in panel_config.preload_kg:
        if key not in keys:
            keys.append(key)

    retained: dict[str, float] = {key: 0.0 for key in keys}
    for key, value in panel_config.preload_kg.items():
        preload = float(value)
        if preload < 0.0 or not math.isfinite(preload):
            raise ValueError(f"preload_kg[{key!r}] must be finite and non-negative")
        params = materials.get(key)
        if params is not None:
            allocated = panel_config.sorbent_mass_kg * params.allocation_fraction
            capacity = allocated * params.q_max_kg_per_kg
            if preload > capacity * (1.0 + 1e-12):
                raise ValueError(
                    f"preload_kg[{key!r}] = {preload!r} kg exceeds the nominal "
                    f"capacity {capacity!r} kg of its allocated compartment"
                )
        retained[key] = preload

    fouling = float(panel_config.initial_fouling_fraction)
    if not (0.0 <= fouling <= 1.0):
        raise ValueError(
            f"initial_fouling_fraction must lie in [0, 1], got {fouling!r}"
        )

    return PanelState(
        panel_id=panel_config.panel_id,
        media_id=panel_config.media_id,
        installed_at_utc=installed_at_utc,
        sorbent_mass_kg=float(panel_config.sorbent_mass_kg),
        geometry=build_panel_geometry(panel_config),
        retained_kg=retained,
        fouling_fraction=fouling,
        active=True,
        service_count=0,
    )


# ---------------------------------------------------------------------------
# Fouling growth
# ---------------------------------------------------------------------------

def grow_fouling(
    panel_state: PanelState, fouling_growth_per_s: float, dt_s: float
) -> PanelState:
    """``f <- min(1, f + growth * dt)`` (MODEL_SPEC section 4).

    Retained mass is untouched: fouling blocks access, it does not dissolve
    what is already sorbed.
    """
    if fouling_growth_per_s < 0.0:
        raise ValueError(
            f"fouling_growth_per_s must be non-negative, got {fouling_growth_per_s!r}"
        )
    if dt_s < 0.0:
        raise ValueError(f"dt_s must be non-negative, got {dt_s!r}")
    fouling = min(1.0, panel_state.fouling_fraction + fouling_growth_per_s * dt_s)
    return replace(panel_state, fouling_fraction=float(fouling))


# ---------------------------------------------------------------------------
# The frozen advance
# ---------------------------------------------------------------------------

def advance_panel(
    panel_state: PanelState,
    contact_batch: ContactBatch,
    material_parameters: Mapping[str, MaterialParameters],
    dt_s: float,
) -> PanelStep:
    """Advance one panel over ``dt_s`` against one contact batch.

    Exactly MODEL_SPEC section 4, per element ``e``::

        M_e         = M * alpha_e
        q           = R_e / M_e
        k_eff       = k_e * (1 - gamma_k f)
        q_max_eff   = q_max_e * (1 - gamma_c f)
        q_eq        = min(Kd_e * c_e, q_max_eff)
        q*          = q_eq + (q - q_eq) exp(-k_eff dt)
        dm_desired  = M_e (q* - q)
        C_remaining = max(0, M_e q_max_eff - R_e)
        dm          = clip(dm_desired, 0, min(m_avail,e, C_remaining))

    ``uptake_kg_by_element`` is the transfer the macro model must remove from
    the contact cells, once.  ``release_kg_by_element`` is zero here: the
    isotherm never gives metal back implicitly (see ``release_from_damage``).

    Fouling growth is applied *after* the uptake, and only when the batch
    carries ``environment['fouling_growth_per_s']``; otherwise the caller owns
    fouling and must call :func:`grow_fouling`.  The choice is recorded in the
    diagnostics.
    """
    if dt_s < 0.0:
        raise ValueError(f"dt_s must be non-negative, got {dt_s!r}")
    if contact_batch.panel_id != panel_state.panel_id:
        raise ValueError(
            f"contact batch is for panel {contact_batch.panel_id!r} but the state "
            f"is panel {panel_state.panel_id!r}"
        )
    validate_allocation(material_parameters)

    elements = sequence_of_elements(material_parameters)
    corrections: list[dict[str, Any]] = []

    uptake: dict[str, float] = {}
    release: dict[str, float] = {key: 0.0 for key in elements}
    new_retained: dict[str, float] = dict(panel_state.retained_kg)

    binding: dict[str, str] = {}
    desired: dict[str, float] = {}
    reduction: dict[str, float] = {}
    available: dict[str, float] = {}
    remaining_capacity: dict[str, float] = {}
    loading_before: dict[str, float] = {}
    loading_after: dict[str, float] = {}
    q_eq_by_element: dict[str, float] = {}
    q_max_eff_by_element: dict[str, float] = {}
    k_eff_by_element: dict[str, float] = {}
    loading_fraction_after: dict[str, float] = {}
    fouling_by_element: dict[str, dict[str, float | bool]] = {}
    missing_from_batch: list[str] = []

    for key in elements:
        params = material_parameters[key]
        allocated = panel_state.sorbent_mass_kg * params.allocation_fraction
        retained = float(panel_state.retained_kg.get(key, 0.0))
        if retained < 0.0:
            corrections.append(
                {
                    "kind": "negative_retained_mass_clipped",
                    "element": key,
                    "value_kg": retained,
                }
            )
            retained = 0.0

        factors = fouling_factors(params, panel_state.fouling_fraction)
        fouling_by_element[key] = factors.as_dict()
        if factors.clipped:
            corrections.append(
                {
                    "kind": "fouling_factor_clipped",
                    "element": key,
                    "raw_kinetics_factor": factors.raw_kinetics_factor,
                    "raw_capacity_factor": factors.raw_capacity_factor,
                }
            )

        k_eff = params.k_rate_per_s * factors.kinetics_factor
        q_max_eff = params.q_max_kg_per_kg * factors.capacity_factor
        k_eff_by_element[key] = k_eff
        q_max_eff_by_element[key] = q_max_eff

        if key not in contact_batch.available_kg:
            missing_from_batch.append(key)
        m_avail = float(contact_batch.available_kg.get(key, 0.0))
        if m_avail < 0.0:
            corrections.append(
                {"kind": "negative_available_mass_clipped", "element": key,
                 "value_kg": m_avail}
            )
            m_avail = 0.0
        available[key] = m_avail

        concentration = float(contact_batch.concentration_kg_per_m3.get(key, 0.0))
        q_before = retained / allocated if allocated > 0.0 else 0.0
        q_eq = equilibrium_loading(params.kd_m3_per_kg, concentration, q_max_eff)
        q_star = exponential_step(q_before, q_eq, k_eff, dt_s)

        dm_desired = allocated * (q_star - q_before)
        capacity_left = max(0.0, allocated * q_max_eff - retained)
        cap = min(m_avail, capacity_left)

        if not panel_state.active:
            dm = 0.0
            label = "inactive_panel"
        elif dm_desired <= 0.0:
            dm = 0.0
            label = "no_spontaneous_desorption"
        else:
            dm = min(dm_desired, cap)
            if dm_desired <= cap * (1.0 + _LABEL_TOLERANCE):
                label = "kinetics"
            elif m_avail <= capacity_left:
                label = "available_mass"
            else:
                label = "capacity"

        if not math.isfinite(dm):
            corrections.append(
                {"kind": "non_finite_transfer_replaced_by_zero", "element": key,
                 "desired_kg": dm_desired}
            )
            dm = 0.0
        dm = max(0.0, dm)

        retained_after = retained + dm
        new_retained[key] = retained_after

        uptake[key] = dm
        desired[key] = dm_desired
        reduction[key] = dm_desired - dm
        binding[key] = label
        remaining_capacity[key] = max(0.0, allocated * q_max_eff - retained_after)
        loading_before[key] = q_before
        loading_after[key] = retained_after / allocated if allocated > 0.0 else 0.0
        q_eq_by_element[key] = q_eq
        loading_fraction_after[key] = (
            loading_after[key] / q_max_eff if q_max_eff > 0.0 else (
                1.0 if retained_after > 0.0 else 0.0
            )
        )

    fouling_before = panel_state.fouling_fraction
    growth = contact_batch.environment.get("fouling_growth_per_s")
    if growth is None:
        fouling_after = fouling_before
        fouling_source = "not_applied_caller_owns_fouling"
    else:
        fouling_after = min(1.0, fouling_before + float(growth) * float(dt_s))
        fouling_source = "contact_batch.environment['fouling_growth_per_s']"

    new_state = replace(
        panel_state,
        retained_kg=new_retained,
        fouling_fraction=float(fouling_after),
    )

    diagnostics: dict[str, Any] = {
        "model": "capped_linear_isotherm_first_order",
        "model_ref": "docs/MODEL_SPEC.md section 4",
        "dt_s": float(dt_s),
        "time_utc": contact_batch.time_utc,
        "panel_active": bool(panel_state.active),
        "binding_constraint": binding,
        "desired_transfer_kg": desired,
        "actual_transfer_kg": dict(uptake),
        "transfer_reduction_kg": reduction,
        "available_kg": available,
        "remaining_capacity_kg": remaining_capacity,
        "loading_kg_per_kg_before": loading_before,
        "loading_kg_per_kg_after": loading_after,
        "loading_fraction_after": loading_fraction_after,
        "equilibrium_loading_kg_per_kg": q_eq_by_element,
        "effective_q_max_kg_per_kg": q_max_eff_by_element,
        "effective_rate_per_s": k_eff_by_element,
        "fouling_fraction_before": float(fouling_before),
        "fouling_fraction_after": float(fouling_after),
        "fouling_growth_source": fouling_source,
        "fouling_factors": fouling_by_element,
        "missing_from_contact_batch": tuple(missing_from_batch),
        "corrections": tuple(corrections),
        "exchange_is_measured": bool(contact_batch.exchange_is_measured),
        "provenance": ProvenanceLabel.SYNTHETIC_DEMO.value,
    }

    return PanelStep(
        new_state=new_state,
        uptake_kg_by_element=uptake,
        release_kg_by_element=release,
        diagnostics=diagnostics,
        contact_batch=contact_batch,
    )


# ---------------------------------------------------------------------------
# Desorption / damage
# ---------------------------------------------------------------------------

def release_from_damage(
    panel_state: PanelState,
    contact_batch: ContactBatch,
    *,
    released_fraction_by_element: Mapping[str, float] | None = None,
    released_kg_by_element: Mapping[str, float] | None = None,
    reason: str = "assumed damage or desorption event",
) -> PanelStep:
    """An explicit release event: metal leaves the mesh and returns to water.

    Exactly one of ``released_fraction_by_element`` (share of the currently
    retained mass) or ``released_kg_by_element`` (absolute kg) must be given.
    The returned ``release_kg_by_element`` is what ``apply_transfers`` adds
    back to the contact cells, so nothing is destroyed: the mesh loses exactly
    what the water gains.

    A request above the retained mass is clipped to the retained mass, and the
    clipping is recorded in ``diagnostics['corrections']``.
    """
    if (released_fraction_by_element is None) == (released_kg_by_element is None):
        raise ValueError(
            "give exactly one of released_fraction_by_element or "
            "released_kg_by_element"
        )
    if contact_batch.panel_id != panel_state.panel_id:
        raise ValueError(
            f"contact batch is for panel {contact_batch.panel_id!r} but the state "
            f"is panel {panel_state.panel_id!r}"
        )

    corrections: list[dict[str, Any]] = []
    release: dict[str, float] = {}
    new_retained = dict(panel_state.retained_kg)

    if released_fraction_by_element is not None:
        requested = {
            key: float(panel_state.retained_kg.get(key, 0.0)) * float(fraction)
            for key, fraction in released_fraction_by_element.items()
        }
        for key, fraction in released_fraction_by_element.items():
            if not (0.0 <= float(fraction) <= 1.0):
                raise ValueError(
                    f"released fraction for {key!r} must lie in [0, 1], got {fraction!r}"
                )
    else:
        assert released_kg_by_element is not None
        requested = {key: float(value) for key, value in released_kg_by_element.items()}

    for key, value in requested.items():
        if value < 0.0 or not math.isfinite(value):
            raise ValueError(f"released mass for {key!r} must be finite and non-negative")
        retained = float(panel_state.retained_kg.get(key, 0.0))
        actual = min(value, retained)
        if actual < value:
            corrections.append(
                {
                    "kind": "release_clipped_to_retained_mass",
                    "element": key,
                    "requested_kg": value,
                    "released_kg": actual,
                }
            )
        release[key] = actual
        new_retained[key] = retained - actual

    uptake = {key: 0.0 for key in new_retained}
    new_state = replace(panel_state, retained_kg=new_retained)

    diagnostics: dict[str, Any] = {
        "model": "explicit_release_event",
        "model_ref": "docs/MODEL_SPEC.md section 4, optional desorption / damage",
        "reason": reason,
        "time_utc": contact_batch.time_utc,
        "released_kg": dict(release),
        "retained_kg_before": dict(panel_state.retained_kg),
        "retained_kg_after": dict(new_retained),
        "corrections": tuple(corrections),
        "provenance": ProvenanceLabel.SYNTHETIC_DEMO.value,
    }
    return PanelStep(
        new_state=new_state,
        uptake_kg_by_element=uptake,
        release_kg_by_element=release,
        diagnostics=diagnostics,
        contact_batch=contact_batch,
    )


# ---------------------------------------------------------------------------
# LABELLED_STUB: scripted contact, standing in for transport.build_contacts
# ---------------------------------------------------------------------------

def scripted_contact_batch(
    panel_state: PanelState,
    time_utc: datetime,
    dt_s: float,
    concentration_kg_per_m3: Mapping[str, float],
    speed_m_per_s: float,
    *,
    cell_inventory_kg: Mapping[str, float] | None = None,
    theta: float = 0.5,
    cell_indices: Sequence[int] = (0,),
    cell_weights: Sequence[float] = (1.0,),
    interception_efficiency: float | None = None,
    environment: Mapping[str, float] | None = None,
    concentration_interpretation: str = (
        "scripted contact concentration, dissolved / labile-equivalent, "
        "synthetic demonstration"
    ),
) -> ContactBatch:
    """LABELLED_STUB: a scripted :class:`ContactBatch` for offline micro runs.

    This is the micro branch's stand-in for ``transport.build_contacts``
    (``contracts/DATA_CONTRACT.md`` section 2 explicitly allows it).  It
    implements MODEL_SPEC section 3 for a single-cell contact region::

        V_sw        = s * A * phi * dt
        m_avail,e   = min(c_e * V_sw, theta * cell_inventory_e)

    At integration the coupled runner must call the transport branch's
    ``build_contacts`` instead; this helper stays for the standalone example,
    the design study and the tests, none of which have a map.

    ``cell_inventory_kg=None`` means "do not apply the inventory bound", which
    is only honest for a scripted scenario with no grid behind it; the choice
    is recorded in ``diagnostics``.
    """
    if dt_s < 0.0:
        raise ValueError(f"dt_s must be non-negative, got {dt_s!r}")
    if speed_m_per_s < 0.0:
        raise ValueError(f"speed_m_per_s must be non-negative, got {speed_m_per_s!r}")
    if not (0.0 <= theta <= 1.0):
        raise ValueError(f"theta must lie in [0, 1], got {theta!r}")
    if len(cell_indices) != len(cell_weights):
        raise ValueError("cell_indices and cell_weights must have the same length")
    weight_sum = sum(float(weight) for weight in cell_weights)
    if abs(weight_sum - 1.0) > 1e-9:
        raise ValueError(f"cell_weights must sum to 1, they sum to {weight_sum!r}")
    if time_utc.tzinfo is None:
        raise ValueError("time_utc must be timezone-aware UTC")

    phi = (
        panel_state.geometry.interception_efficiency
        if interception_efficiency is None
        else float(interception_efficiency)
    )
    if not (0.0 <= phi <= 1.0):
        raise ValueError(f"interception_efficiency must lie in [0, 1], got {phi!r}")

    area = panel_state.geometry.frontal_area_m2
    swept_volume = float(speed_m_per_s) * area * phi * float(dt_s)

    available: dict[str, float] = {}
    inventory_bound_active: dict[str, bool] = {}
    for key, concentration in concentration_kg_per_m3.items():
        swept_mass = max(0.0, float(concentration)) * swept_volume
        if cell_inventory_kg is None:
            available[key] = swept_mass
            inventory_bound_active[key] = False
        else:
            inventory_bound = theta * max(0.0, float(cell_inventory_kg.get(key, 0.0)))
            available[key] = min(swept_mass, inventory_bound)
            inventory_bound_active[key] = inventory_bound < swept_mass

    return ContactBatch(
        panel_id=panel_state.panel_id,
        time_utc=time_utc,
        dt_s=float(dt_s),
        concentration_kg_per_m3={
            key: float(value) for key, value in concentration_kg_per_m3.items()
        },
        concentration_interpretation=concentration_interpretation,
        available_kg=available,
        exchange_volume_m3=swept_volume,
        exchange_is_measured=False,
        cell_indices=tuple(int(index) for index in cell_indices),
        cell_weights=tuple(float(weight) for weight in cell_weights),
        environment=dict(environment or {}),
        diagnostics={
            "source": "LABELLED_STUB mesh_demo.micro.panel.scripted_contact_batch",
            "replace_with": "mesh_demo.transport.build_contacts",
            "speed_m_per_s": float(speed_m_per_s),
            "frontal_area_m2": area,
            "interception_efficiency": phi,
            "theta_cell_inventory_share": float(theta),
            "cell_inventory_bound_applied": cell_inventory_kg is not None,
            "cell_inventory_bound_active": inventory_bound_active,
            "provenance": ProvenanceLabel.SYNTHETIC_DEMO.value,
        },
    )


# ---------------------------------------------------------------------------
# Reporting helper
# ---------------------------------------------------------------------------

def panel_summary(
    panel_state: PanelState, material_parameters: Mapping[str, MaterialParameters]
) -> dict[str, Any]:
    """A small JSON-ready summary of a panel state (SI units throughout)."""
    elements = sequence_of_elements(material_parameters)
    retained: dict[str, float] = {}
    allocated: dict[str, float] = {}
    capacity_nominal: dict[str, float] = {}
    capacity_effective: dict[str, float] = {}
    loading: dict[str, float] = {}
    loading_fraction: dict[str, float] = {}
    for key in elements:
        params = material_parameters[key]
        mass = panel_state.sorbent_mass_kg * params.allocation_fraction
        q_max_eff = (
            params.q_max_kg_per_kg
            * fouling_factors(params, panel_state.fouling_fraction).capacity_factor
        )
        retained_kg = float(panel_state.retained_kg.get(key, 0.0))
        retained[key] = retained_kg
        allocated[key] = mass
        capacity_nominal[key] = mass * params.q_max_kg_per_kg
        capacity_effective[key] = mass * q_max_eff
        loading[key] = retained_kg / mass if mass > 0.0 else 0.0
        loading_fraction[key] = (
            loading[key] / q_max_eff if q_max_eff > 0.0 else (
                1.0 if retained_kg > 0.0 else 0.0
            )
        )
    return {
        "panel_id": panel_state.panel_id,
        "media_id": panel_state.media_id,
        "service_count": panel_state.service_count,
        "active": panel_state.active,
        "sorbent_mass_kg": panel_state.sorbent_mass_kg,
        "fouling_fraction": panel_state.fouling_fraction,
        "retained_kg": retained,
        "allocated_sorbent_kg": allocated,
        "nominal_capacity_kg": capacity_nominal,
        "effective_capacity_kg": capacity_effective,
        "loading_kg_per_kg": loading,
        "loading_fraction_of_effective_capacity": loading_fraction,
    }
