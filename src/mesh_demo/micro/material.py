"""Reduced sorbent material model: isotherm, fouling and parameter ensemble.

Implements ``docs/MODEL_SPEC.md`` section 4 for **one** element at a time.
Every equation here is the synthetic demonstration baseline agreed in the
build brief: a capped linear isotherm plus a first-order approach to
equilibrium.  It is not a statement of the real chemistry of any material,
and none of the numbers below are transferred from [S01] or [S04] as
validated operating capacities.

Provenance rule of this module: every parameter object carries a
:class:`~mesh_demo.contracts.ProvenanceLabel`.  The defaults inherited from
``config.MaterialConfig`` are ``assumption``.

Unit rule of this module: everything is SI (kg, kg m^-3, kg kg^-1, s).  The
two helpers at the bottom are the *only* place where a display unit is
accepted, and they delegate to ``mesh_demo.units``; no conversion factor is
re-implemented here.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from ..config import MaterialConfig, PanelConfig
from ..contracts import Element, MaterialParameters, PanelGeometry, ProvenanceLabel
from ..units import to_si_aqueous_concentration, to_si_solid_loading

__all__ = [
    "FoulingFactors",
    "ParameterEnsemble",
    "build_material_parameters",
    "build_material_map",
    "validate_allocation",
    "fouling_factors",
    "effective_rate_per_s",
    "effective_q_max_kg_per_kg",
    "equilibrium_loading",
    "exponential_step",
    "sample_parameter_ensemble",
    "contact_concentration_kg_per_m3",
    "solid_loading_kg_per_kg",
]


# ---------------------------------------------------------------------------
# Fouling
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FoulingFactors:
    """Multiplicative fouling factors for one element at one fouling level.

    ``k_eff = k * kinetics_factor`` and ``q_max_eff = q_max * capacity_factor``
    with ``kinetics_factor = 1 - gamma_k * f`` and
    ``capacity_factor = 1 - gamma_c * f`` (MODEL_SPEC section 4).

    A configuration with ``gamma * f > 1`` would drive a factor negative, which
    is physically meaningless.  The factor is clipped into ``[0, 1]`` and the
    clipping is **recorded** in ``clipped`` and in the raw fields, never applied
    silently.
    """

    fouling_fraction: float
    kinetics_factor: float
    capacity_factor: float
    raw_fouling_fraction: float
    raw_kinetics_factor: float
    raw_capacity_factor: float
    clipped: bool

    def as_dict(self) -> dict[str, float | bool]:
        return {
            "fouling_fraction": self.fouling_fraction,
            "kinetics_factor": self.kinetics_factor,
            "capacity_factor": self.capacity_factor,
            "raw_fouling_fraction": self.raw_fouling_fraction,
            "raw_kinetics_factor": self.raw_kinetics_factor,
            "raw_capacity_factor": self.raw_capacity_factor,
            "clipped": self.clipped,
        }


def fouling_factors(params: MaterialParameters, fouling_fraction: float) -> FoulingFactors:
    """Fouling factors for ``params`` at fouling level ``fouling_fraction``."""
    raw_f = float(fouling_fraction)
    if not math.isfinite(raw_f):
        raise ValueError(f"fouling_fraction must be finite, got {fouling_fraction!r}")
    fraction = min(1.0, max(0.0, raw_f))

    raw_kinetics = 1.0 - params.fouling_rate_kinetics * fraction
    raw_capacity = 1.0 - params.fouling_rate_capacity * fraction
    kinetics = min(1.0, max(0.0, raw_kinetics))
    capacity = min(1.0, max(0.0, raw_capacity))

    clipped = (
        raw_f != fraction
        or raw_kinetics != kinetics
        or raw_capacity != capacity
    )
    return FoulingFactors(
        fouling_fraction=fraction,
        kinetics_factor=kinetics,
        capacity_factor=capacity,
        raw_fouling_fraction=raw_f,
        raw_kinetics_factor=raw_kinetics,
        raw_capacity_factor=raw_capacity,
        clipped=bool(clipped),
    )


def effective_rate_per_s(params: MaterialParameters, fouling_fraction: float) -> float:
    """``k_eff`` [s^-1]: the fouled first-order approach rate."""
    return params.k_rate_per_s * fouling_factors(params, fouling_fraction).kinetics_factor


def effective_q_max_kg_per_kg(
    params: MaterialParameters, fouling_fraction: float
) -> float:
    """``q_max_eff`` [kg/kg]: the fouled accessible capacity per allocated kg."""
    return (
        params.q_max_kg_per_kg * fouling_factors(params, fouling_fraction).capacity_factor
    )


# ---------------------------------------------------------------------------
# Isotherm and the exact exponential step
# ---------------------------------------------------------------------------

def equilibrium_loading(
    kd_m3_per_kg: float,
    concentration_kg_per_m3: float,
    q_max_eff_kg_per_kg: float,
) -> float:
    """``q_eq = min(Kd * c, q_max_eff)`` [kg/kg], never negative.

    The capped linear isotherm of MODEL_SPEC section 4.  A negative
    concentration is not physical; it is treated as zero here and the caller is
    expected to have recorded the clipping upstream (the transport branch
    records its own clipping in ``TransportStep.diagnostics``).
    """
    concentration = max(0.0, float(concentration_kg_per_m3))
    linear = max(0.0, float(kd_m3_per_kg)) * concentration
    return min(linear, max(0.0, float(q_max_eff_kg_per_kg)))


def exponential_step(
    q0_kg_per_kg: float,
    q_eq_kg_per_kg: float,
    k_eff_per_s: float,
    dt_s: float,
) -> float:
    """Exact solution of ``dq/dt = k_eff (q_eq - q)`` over ``dt`` at constant c.

    ``q* = q_eq + (q0 - q_eq) exp(-k_eff dt)``.  Because it is the exact
    solution of the linear ODE, the update is unconditionally stable and, in
    the unbounded case, exactly time-step independent.
    """
    if dt_s < 0.0:
        raise ValueError(f"dt_s must be non-negative, got {dt_s!r}")
    k_eff = max(0.0, float(k_eff_per_s))
    if k_eff == 0.0 or dt_s == 0.0:
        return float(q0_kg_per_kg)
    # math.exp underflows smoothly to 0.0 for a large exponent; no overflow.
    decay = math.exp(-k_eff * float(dt_s))
    return float(q_eq_kg_per_kg) + (float(q0_kg_per_kg) - float(q_eq_kg_per_kg)) * decay


# ---------------------------------------------------------------------------
# Building MaterialParameters from the coordinator-owned configuration
# ---------------------------------------------------------------------------

def _check_interval(
    name: str, nominal: float, interval: tuple[float, float] | None
) -> tuple[float, float] | None:
    if interval is None:
        return None
    low, high = float(interval[0]), float(interval[1])
    if not (math.isfinite(low) and math.isfinite(high)):
        raise ValueError(f"{name} interval must be finite, got {interval!r}")
    if low > high:
        raise ValueError(f"{name} interval is inverted: {interval!r}")
    if low < 0.0:
        raise ValueError(f"{name} interval must be non-negative, got {interval!r}")
    if not (low - 1e-12 <= nominal <= high + 1e-12):
        raise ValueError(
            f"{name} nominal value {nominal!r} lies outside its declared "
            f"uncertainty interval {interval!r}; the ensemble would then not "
            "contain the value the deterministic run uses"
        )
    return (low, high)


def build_material_parameters(material_config: MaterialConfig) -> MaterialParameters:
    """Typed sorbent parameters for one element, from the run configuration.

    Validation performed here (rather than in the frozen dataclass, which is
    coordinator-owned): non-negative Kd / q_max / k, an allocation fraction in
    ``[0, 1]``, ordered uncertainty intervals that actually contain the nominal
    value, and fouling sensitivities in ``[0, 1]``.
    """
    element = Element(material_config.element)

    for name, value in (
        ("kd_m3_per_kg", material_config.kd_m3_per_kg),
        ("q_max_kg_per_kg", material_config.q_max_kg_per_kg),
        ("k_rate_per_s", material_config.k_rate_per_s),
    ):
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{name} must be finite and non-negative, got {value!r}")

    allocation = float(material_config.allocation_fraction)
    if not (0.0 <= allocation <= 1.0):
        raise ValueError(
            f"allocation_fraction must lie in [0, 1], got {allocation!r}: mesh "
            "capacity is never assigned twice"
        )
    for name, value in (
        ("fouling_rate_capacity", material_config.fouling_rate_capacity),
        ("fouling_rate_kinetics", material_config.fouling_rate_kinetics),
    ):
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{name} must lie in [0, 1], got {value!r}")

    return MaterialParameters(
        element=element,
        kd_m3_per_kg=float(material_config.kd_m3_per_kg),
        q_max_kg_per_kg=float(material_config.q_max_kg_per_kg),
        k_rate_per_s=float(material_config.k_rate_per_s),
        allocation_fraction=allocation,
        kd_interval=_check_interval(
            "kd_m3_per_kg", material_config.kd_m3_per_kg, material_config.kd_interval
        ),
        q_max_interval=_check_interval(
            "q_max_kg_per_kg",
            material_config.q_max_kg_per_kg,
            material_config.q_max_interval,
        ),
        k_rate_interval=_check_interval(
            "k_rate_per_s", material_config.k_rate_per_s, material_config.k_rate_interval
        ),
        fouling_rate_capacity=float(material_config.fouling_rate_capacity),
        fouling_rate_kinetics=float(material_config.fouling_rate_kinetics),
        provenance=ProvenanceLabel(material_config.provenance),
        source_ref=material_config.source_ref,
    )


def validate_allocation(materials: Mapping[str, MaterialParameters]) -> float:
    """Assert the allocation fractions do not exceed 1; return their sum.

    MODEL_SPEC section 4: the mesh capacity is never assigned to both metals.
    """
    total = sum(float(params.allocation_fraction) for params in materials.values())
    if total > 1.0 + 1e-12:
        raise ValueError(
            f"allocation fractions sum to {total!r} > 1: the same sorbent mass "
            "would be counted for more than one element"
        )
    return total


def build_material_map(panel_config: PanelConfig) -> dict[str, MaterialParameters]:
    """``{element_value: MaterialParameters}`` for one configured panel."""
    materials: dict[str, MaterialParameters] = {}
    for material_config in panel_config.materials:
        params = build_material_parameters(material_config)
        key = params.element.value
        if key in materials:
            raise ValueError(
                f"element {key!r} is configured twice on panel "
                f"{panel_config.panel_id!r}; one compartment per element"
            )
        materials[key] = params
    validate_allocation(materials)
    return materials


# ---------------------------------------------------------------------------
# Parameter ensemble (the uncertainty the forecast reports)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ParameterEnsemble:
    """A deterministic sample of the documented uncertainty ranges.

    Member 0 is always the nominal parameter set, so a deterministic run and
    the ensemble median describe the same material.  The remaining members are
    drawn log-uniformly inside ``kd_interval`` / ``q_max_interval`` /
    ``k_rate_interval`` (they span more than an order of magnitude, so a
    log-uniform prior is the honest default) and uniformly inside the
    interception interval.

    ``interception_efficiency`` is carried alongside the material parameters
    because MODEL_SPEC section 7 samples ``(Kd, q_max, k, phi, ...)`` jointly:
    a high-capacity material with a small contact fraction performs badly, and
    the ensemble has to be able to say so.
    """

    members: tuple[Mapping[str, MaterialParameters], ...]
    interception_efficiency: tuple[float, ...]
    seed: int
    distribution: str = "log_uniform_material_uniform_interception"
    provenance: ProvenanceLabel = ProvenanceLabel.ASSUMPTION
    notes: str = (
        "Uncertainty ranges are assumptions from the run configuration, not a "
        "fitted posterior. Member 0 is the nominal parameter set."
    )

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def elements(self) -> tuple[str, ...]:
        return tuple(self.members[0].keys()) if self.members else ()


def _element_seed(seed: int, element: str, salt: str) -> int:
    """Stable per-element stream seed (``hash()`` is salted per process)."""
    token = f"{element}|{salt}".encode("utf-8")
    return int((int(seed) + 1_000_003 * zlib.crc32(token)) % (2**32))


def _log_uniform(rng: np.random.Generator, low: float, high: float, size: int) -> np.ndarray:
    if size <= 0:
        return np.empty(0, dtype=float)
    if low <= 0.0 or high <= 0.0:
        return rng.uniform(low, high, size=size)
    return np.exp(rng.uniform(math.log(low), math.log(high), size=size))


def sample_parameter_ensemble(
    materials: Mapping[str, MaterialParameters],
    size: int,
    seed: int,
    *,
    interception_nominal: float | None = None,
    interception_interval: tuple[float, float] | None = None,
    geometry: PanelGeometry | None = None,
) -> ParameterEnsemble:
    """Deterministic parameter ensemble used by the forecast and design study.

    ``geometry`` is a convenience: when given, its ``interception_efficiency``
    and ``interception_interval`` are used unless overridden explicitly.
    """
    if size < 1:
        raise ValueError(f"ensemble size must be at least 1, got {size!r}")
    validate_allocation(materials)

    if geometry is not None:
        if interception_nominal is None:
            interception_nominal = geometry.interception_efficiency
        if interception_interval is None:
            interception_interval = geometry.interception_interval
    if interception_nominal is None:
        interception_nominal = 1.0

    draws: dict[str, dict[str, np.ndarray]] = {}
    for key, params in materials.items():
        rng_kd = np.random.default_rng(_element_seed(seed, key, "kd"))
        rng_qmax = np.random.default_rng(_element_seed(seed, key, "q_max"))
        rng_k = np.random.default_rng(_element_seed(seed, key, "k_rate"))
        n = size - 1
        draws[key] = {
            "kd": (
                _log_uniform(rng_kd, *params.kd_interval, n)
                if params.kd_interval
                else np.full(n, params.kd_m3_per_kg)
            ),
            "q_max": (
                _log_uniform(rng_qmax, *params.q_max_interval, n)
                if params.q_max_interval
                else np.full(n, params.q_max_kg_per_kg)
            ),
            "k_rate": (
                _log_uniform(rng_k, *params.k_rate_interval, n)
                if params.k_rate_interval
                else np.full(n, params.k_rate_per_s)
            ),
        }

    rng_phi = np.random.default_rng(_element_seed(seed, "__panel__", "interception"))
    if interception_interval is None:
        phi = np.full(size - 1, float(interception_nominal))
    else:
        low, high = float(interception_interval[0]), float(interception_interval[1])
        if low > high:
            raise ValueError(f"interception interval is inverted: {interception_interval!r}")
        phi = rng_phi.uniform(low, high, size=max(0, size - 1))

    members: list[Mapping[str, MaterialParameters]] = [dict(materials)]
    for index in range(size - 1):
        member: dict[str, MaterialParameters] = {}
        for key, params in materials.items():
            member[key] = MaterialParameters(
                element=params.element,
                kd_m3_per_kg=float(draws[key]["kd"][index]),
                q_max_kg_per_kg=float(draws[key]["q_max"][index]),
                k_rate_per_s=float(draws[key]["k_rate"][index]),
                allocation_fraction=params.allocation_fraction,
                kd_interval=params.kd_interval,
                q_max_interval=params.q_max_interval,
                k_rate_interval=params.k_rate_interval,
                fouling_rate_capacity=params.fouling_rate_capacity,
                fouling_rate_kinetics=params.fouling_rate_kinetics,
                provenance=params.provenance,
                source_ref=params.source_ref,
            )
        members.append(member)

    interception = (float(interception_nominal),) + tuple(float(value) for value in phi)
    return ParameterEnsemble(
        members=tuple(members),
        interception_efficiency=interception,
        seed=int(seed),
    )


def scale_material(
    params: MaterialParameters,
    *,
    kd_scale: float = 1.0,
    q_max_scale: float = 1.0,
    k_rate_scale: float = 1.0,
    source_ref: str | None = None,
) -> MaterialParameters:
    """A scaled variant of a parameter set, for explicit what-if variants.

    Used by the design comparison to build the deliberately weak material
    (slow kinetics), so that the weak case is a *stated* variant rather than a
    hidden tweak.  Uncertainty intervals are scaled with the nominal value so
    the ensemble stays consistent with it.
    """

    def _scaled_interval(
        interval: tuple[float, float] | None, scale: float
    ) -> tuple[float, float] | None:
        if interval is None:
            return None
        return (interval[0] * scale, interval[1] * scale)

    return MaterialParameters(
        element=params.element,
        kd_m3_per_kg=params.kd_m3_per_kg * kd_scale,
        q_max_kg_per_kg=params.q_max_kg_per_kg * q_max_scale,
        k_rate_per_s=params.k_rate_per_s * k_rate_scale,
        allocation_fraction=params.allocation_fraction,
        kd_interval=_scaled_interval(params.kd_interval, kd_scale),
        q_max_interval=_scaled_interval(params.q_max_interval, q_max_scale),
        k_rate_interval=_scaled_interval(params.k_rate_interval, k_rate_scale),
        fouling_rate_capacity=params.fouling_rate_capacity,
        fouling_rate_kinetics=params.fouling_rate_kinetics,
        provenance=params.provenance,
        source_ref=source_ref or params.source_ref,
    )


__all__.append("scale_material")


# ---------------------------------------------------------------------------
# The only unit boundary in this package
# ---------------------------------------------------------------------------

def contact_concentration_kg_per_m3(value: float, unit: str) -> float:
    """Display aqueous concentration -> SI, by delegation to ``mesh_demo.units``.

    Present so that no caller in ``micro/`` has an excuse to hard-code
    ``1e-9``.  A solid-loading unit raises here, exactly as it does in
    ``units``: ``ng/g`` is a mass fraction and never an aqueous concentration.
    """
    return to_si_aqueous_concentration(value, unit)


def solid_loading_kg_per_kg(value: float, unit: str) -> float:
    """Display sorbent loading (``mg/kg``, ``ng/g`` ...) -> SI kg kg^-1."""
    return to_si_solid_loading(value, unit)


def sequence_of_elements(materials: Mapping[str, MaterialParameters]) -> Sequence[str]:
    """Stable element ordering for reports (Pb before Hg, then anything else)."""
    preferred = [Element.PB.value, Element.HG.value]
    ordered = [key for key in preferred if key in materials]
    ordered.extend(sorted(key for key in materials if key not in preferred))
    return tuple(ordered)


__all__.append("sequence_of_elements")
