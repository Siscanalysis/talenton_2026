"""Reduced reactive-medium model: isotherm, kinetics, fouling, ensemble.

Implements the material half of ``docs/MODEL_SPEC.md`` sections 3 and 4 for
**one** element at a time.  Every equation here is the synthetic demonstration
baseline: a capped linear isotherm plus a first-order approach to equilibrium.
It is not a statement of the real chemistry of any material, and none of the
numbers below are transferred from [S01] or [S04] as validated operating
capacities.

This module survived the concept change from a vertical panel to a seabed mat
almost unaltered, because ``Kd``, ``q_eq``, ``q_max`` and ``k_rate`` describe a
sorbent, not a geometry of contact.  What changed is the configuration type it
reads (``ReactiveMediumConfig`` / ``MatLayoutConfig``), the arrival of an
effective diffusivity ``d_eff_m2_per_s`` (the 1-D layer needs one and a panel
did not), and the replacement of the interception fraction by the tile's edge
leakage fraction in the ensemble.

Allocation convention, used consistently by ``column.py`` and by the frozen
``MatTileState`` accessors: the sorbed profile ``q`` is carried **per kilogram
of total medium**, while ``allocation_fraction`` splits that medium between the
elements.  The column therefore uses

    kd_column    = allocation_fraction * kd
    q_max_column = allocation_fraction * q_max_eff

so the isotherm knee ``C* = q_max / kd`` is unchanged by the allocation, and
``rho_b * L * allocation_fraction * q_max`` is the capacity per unit area that
``MatTileState.capacity_kg_per_m2`` reports.

Provenance rule of this module: every parameter object carries a
:class:`~reactive_seabed_mat.contracts.ProvenanceLabel`.  The defaults inherited
from ``config.ReactiveMediumConfig`` are ``assumption``.

Unit rule of this module: everything is SI (kg, kg m^-3, kg kg^-1, m^2 s^-1,
s).  The two helpers at the bottom are the *only* place where a display unit is
accepted, and they delegate to ``reactive_seabed_mat.units``; no conversion
factor is re-implemented here.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from ..config import MatLayoutConfig, ReactiveMediumConfig
from ..contracts import Element, MaterialParameters, MatTileGeometry, ProvenanceLabel
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
    "effective_d_eff_m2_per_s",
    "equilibrium_loading",
    "exponential_step",
    "sample_parameter_ensemble",
    "scale_material",
    "sequence_of_elements",
    "contact_concentration_kg_per_m3",
    "solid_loading_kg_per_kg",
]


# ---------------------------------------------------------------------------
# Fouling
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FoulingFactors:
    """Multiplicative fouling factors for one element at one fouling level.

    MODEL_SPEC section 4, mode 2::

        k_eff     = k     (1 - gamma_k f)
        q_max_eff = q_max (1 - gamma_c f)
        D_eff_eff = D_eff (1 - gamma_D f)

    A configuration with ``gamma * f > 1`` would drive a factor negative, which
    is physically meaningless.  The factor is clipped into ``[0, 1]`` and the
    clipping is **recorded** in ``clipped`` and in the raw fields, never applied
    silently.

    Nothing here reduces sorbed mass.  Fouling blocks access and slows the
    approach to equilibrium; the metal already held stays held.
    """

    fouling_fraction: float
    kinetics_factor: float
    capacity_factor: float
    diffusivity_factor: float
    raw_fouling_fraction: float
    raw_kinetics_factor: float
    raw_capacity_factor: float
    raw_diffusivity_factor: float
    clipped: bool

    def as_dict(self) -> dict[str, float | bool]:
        return {
            "fouling_fraction": self.fouling_fraction,
            "kinetics_factor": self.kinetics_factor,
            "capacity_factor": self.capacity_factor,
            "diffusivity_factor": self.diffusivity_factor,
            "raw_fouling_fraction": self.raw_fouling_fraction,
            "raw_kinetics_factor": self.raw_kinetics_factor,
            "raw_capacity_factor": self.raw_capacity_factor,
            "raw_diffusivity_factor": self.raw_diffusivity_factor,
            "clipped": self.clipped,
        }


def fouling_factors(
    params: MaterialParameters, fouling_fraction: float
) -> FoulingFactors:
    """Fouling factors for ``params`` at fouling level ``fouling_fraction``."""
    raw_f = float(fouling_fraction)
    if not math.isfinite(raw_f):
        raise ValueError(f"fouling_fraction must be finite, got {fouling_fraction!r}")
    fraction = min(1.0, max(0.0, raw_f))

    raw_kinetics = 1.0 - params.fouling_rate_kinetics * fraction
    raw_capacity = 1.0 - params.fouling_rate_capacity * fraction
    raw_diffusivity = 1.0 - params.fouling_rate_diffusivity * fraction
    kinetics = min(1.0, max(0.0, raw_kinetics))
    capacity = min(1.0, max(0.0, raw_capacity))
    diffusivity = min(1.0, max(0.0, raw_diffusivity))

    clipped = (
        raw_f != fraction
        or raw_kinetics != kinetics
        or raw_capacity != capacity
        or raw_diffusivity != diffusivity
    )
    return FoulingFactors(
        fouling_fraction=fraction,
        kinetics_factor=kinetics,
        capacity_factor=capacity,
        diffusivity_factor=diffusivity,
        raw_fouling_fraction=raw_f,
        raw_kinetics_factor=raw_kinetics,
        raw_capacity_factor=raw_capacity,
        raw_diffusivity_factor=raw_diffusivity,
        clipped=bool(clipped),
    )


def effective_rate_per_s(params: MaterialParameters, fouling_fraction: float) -> float:
    """``k_eff`` [s^-1]: the fouled first-order approach rate."""
    return (
        params.k_rate_per_s * fouling_factors(params, fouling_fraction).kinetics_factor
    )


def effective_q_max_kg_per_kg(
    params: MaterialParameters, fouling_fraction: float
) -> float:
    """``q_max_eff`` [kg/kg]: the fouled accessible capacity per allocated kg."""
    return (
        params.q_max_kg_per_kg
        * fouling_factors(params, fouling_fraction).capacity_factor
    )


def effective_d_eff_m2_per_s(
    params: MaterialParameters, fouling_fraction: float
) -> float:
    """``D_eff_eff`` [m^2/s]: pore blockage lowers the effective diffusivity.

    Read on its own this looks like an improvement, because a less permeable
    layer passes less flux.  It is not free: ``degradation.bypass_fraction``
    grows with the same fouling index and pushes flow around the tile edge.
    """
    return (
        params.d_eff_m2_per_s
        * fouling_factors(params, fouling_fraction).diffusivity_factor
    )


# ---------------------------------------------------------------------------
# Isotherm and the exact exponential step
# ---------------------------------------------------------------------------

def equilibrium_loading(
    kd_m3_per_kg: float,
    concentration_kg_per_m3: float,
    q_max_eff_kg_per_kg: float,
) -> float:
    """``q_eq = min(Kd * C, q_max_eff)`` [kg/kg], never negative.

    The capped linear isotherm of MODEL_SPEC section 3.  A negative
    concentration is not physical; it is treated as zero here and the caller is
    expected to have recorded the clipping upstream (the column records its own
    clipping in ``LayerStep.diagnostics``).
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
    """Exact solution of ``dq/dt = k_eff (q_eq - q)`` over ``dt`` at constant C.

    ``q* = q_eq + (q0 - q_eq) exp(-k_eff dt)``.  Because it is the exact
    solution of the linear ODE, the update is unconditionally stable and, in
    the unbounded case, exactly time-step independent.

    The 1-D column does **not** use this form: it eliminates ``q^{n+1}``
    analytically inside the implicit transport solve instead, because splitting
    the two was measured to diverge under refinement (REFACTOR_PLAN probe 4).
    The closed form survives for the conditional forecast in ``forecast.py``,
    where the concentration really is held constant by assumption.
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


def build_material_parameters(
    medium_config: ReactiveMediumConfig,
) -> MaterialParameters:
    """Typed reactive-medium parameters for one element, from the run config.

    Validation performed here (rather than in the frozen dataclass, which is
    coordinator-owned): non-negative Kd / q_max / k / D_eff, an allocation
    fraction in ``[0, 1]``, ordered uncertainty intervals that actually contain
    the nominal value, and fouling sensitivities in ``[0, 1]``.
    """
    element = Element(medium_config.element)

    for name, value in (
        ("kd_m3_per_kg", medium_config.kd_m3_per_kg),
        ("q_max_kg_per_kg", medium_config.q_max_kg_per_kg),
        ("k_rate_per_s", medium_config.k_rate_per_s),
        ("d_eff_m2_per_s", medium_config.d_eff_m2_per_s),
    ):
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{name} must be finite and non-negative, got {value!r}")

    allocation = float(medium_config.allocation_fraction)
    if not (0.0 <= allocation <= 1.0):
        raise ValueError(
            f"allocation_fraction must lie in [0, 1], got {allocation!r}: mat "
            "capacity is never assigned twice"
        )
    for name, value in (
        ("fouling_rate_capacity", medium_config.fouling_rate_capacity),
        ("fouling_rate_kinetics", medium_config.fouling_rate_kinetics),
        ("fouling_rate_diffusivity", medium_config.fouling_rate_diffusivity),
    ):
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{name} must lie in [0, 1], got {value!r}")

    available = float(getattr(medium_config, "available_fraction", 1.0))
    if not 0.0 < available <= 1.0:
        raise ValueError(f"available_fraction must lie in (0, 1], got {available!r}")
    available_interval = _check_interval(
        "available_fraction",
        available,
        getattr(medium_config, "available_fraction_interval", (available, available)),
    )

    # Seawater speciation enters through Kd and NOT through q_max, because it
    # limits the supply of sorbable species, not the number of sites.  If only a
    # fraction f of the dissolved pool is in a form a site can bind, and that
    # form stays in rapid equilibrium with the rest, then the partition
    # coefficient measured against TOTAL dissolved concentration is f times the
    # free-ion value, while the ultimate capacity is unchanged.  Applying f to
    # q_max instead would claim the sites disappear in seawater, which is wrong:
    # they are still there, they just fill more slowly and only at a higher
    # total concentration.  For Cu, f = 0.02 makes the apparent Kd fifty times
    # smaller than any freshwater isotherm would suggest, and that is the single
    # most pessimistic number in the model.
    return MaterialParameters(
        element=element,
        kd_m3_per_kg=float(medium_config.kd_m3_per_kg) * available,
        q_max_kg_per_kg=float(medium_config.q_max_kg_per_kg),
        k_rate_per_s=float(medium_config.k_rate_per_s),
        allocation_fraction=allocation,
        d_eff_m2_per_s=float(medium_config.d_eff_m2_per_s),
        kd_interval=(
            _check_interval(
                "kd_m3_per_kg", medium_config.kd_m3_per_kg, medium_config.kd_interval
            )[0]
            * available_interval[0],
            _check_interval(
                "kd_m3_per_kg", medium_config.kd_m3_per_kg, medium_config.kd_interval
            )[1]
            * available_interval[1],
        ),
        q_max_interval=_check_interval(
            "q_max_kg_per_kg",
            medium_config.q_max_kg_per_kg,
            medium_config.q_max_interval,
        ),
        k_rate_interval=_check_interval(
            "k_rate_per_s", medium_config.k_rate_per_s, medium_config.k_rate_interval
        ),
        d_eff_interval=_check_interval(
            "d_eff_m2_per_s",
            medium_config.d_eff_m2_per_s,
            medium_config.d_eff_interval,
        ),
        fouling_rate_capacity=float(medium_config.fouling_rate_capacity),
        fouling_rate_kinetics=float(medium_config.fouling_rate_kinetics),
        fouling_rate_diffusivity=float(medium_config.fouling_rate_diffusivity),
        provenance=ProvenanceLabel(medium_config.provenance),
        source_ref=medium_config.source_ref,
    )


def validate_allocation(materials: Mapping[str, MaterialParameters]) -> float:
    """Assert the allocation fractions do not exceed 1; return their sum.

    MODEL_SPEC section 3, "Allocation between Pb and Hg": the reactive medium
    is never assigned to both metals.
    """
    total = sum(float(params.allocation_fraction) for params in materials.values())
    if total > 1.0 + 1e-12:
        raise ValueError(
            f"allocation fractions sum to {total!r} > 1: the same reactive "
            "medium would be counted for more than one element"
        )
    return total


def build_material_map(mat_config: MatLayoutConfig) -> dict[str, MaterialParameters]:
    """``{element_value: MaterialParameters}`` for one configured mat layout."""
    materials: dict[str, MaterialParameters] = {}
    for medium_config in mat_config.media:
        params = build_material_parameters(medium_config)
        key = params.element.value
        if key in materials:
            raise ValueError(
                f"element {key!r} is configured twice on mat "
                f"{mat_config.mat_id!r}; one compartment per element"
            )
        materials[key] = params
    validate_allocation(materials)
    return materials


# ---------------------------------------------------------------------------
# Parameter ensemble (the uncertainty every reported interval comes from)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ParameterEnsemble:
    """A deterministic sample of the documented uncertainty ranges.

    Member 0 is always the nominal parameter set, so a deterministic run and
    the ensemble median describe the same material.  The remaining members are
    drawn log-uniformly inside ``kd_interval`` / ``q_max_interval`` /
    ``k_rate_interval`` / ``d_eff_interval`` (they span more than an order of
    magnitude, so a log-uniform prior is the honest default) and uniformly
    inside the edge-leakage interval.

    ``edge_leakage_fraction`` is carried alongside the material parameters
    because a mat with excellent chemistry and a leaking edge performs badly,
    and the ensemble has to be able to say so.  It replaces the vertical
    panel's interception fraction, which has no meaning for a mat lying flat on
    the seabed.
    """

    members: tuple[Mapping[str, MaterialParameters], ...]
    edge_leakage_fraction: tuple[float, ...]
    seed: int
    distribution: str = "log_uniform_material_uniform_edge_leakage"
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


def _log_uniform(
    rng: np.random.Generator, low: float, high: float, size: int
) -> np.ndarray:
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
    edge_leakage_nominal: float | None = None,
    edge_leakage_interval: tuple[float, float] | None = None,
    geometry: MatTileGeometry | None = None,
) -> ParameterEnsemble:
    """Deterministic parameter ensemble used by the forecast and the intervals.

    ``geometry`` is a convenience: when given, its ``edge_leakage_fraction``
    and ``edge_leakage_interval`` are used unless overridden explicitly.
    """
    if size < 1:
        raise ValueError(f"ensemble size must be at least 1, got {size!r}")
    validate_allocation(materials)

    if geometry is not None:
        if edge_leakage_nominal is None:
            edge_leakage_nominal = geometry.edge_leakage_fraction
        if edge_leakage_interval is None:
            edge_leakage_interval = geometry.edge_leakage_interval
    if edge_leakage_nominal is None:
        edge_leakage_nominal = 0.0

    draws: dict[str, dict[str, np.ndarray]] = {}
    n = size - 1
    for key, params in materials.items():
        rng_kd = np.random.default_rng(_element_seed(seed, key, "kd"))
        rng_qmax = np.random.default_rng(_element_seed(seed, key, "q_max"))
        rng_k = np.random.default_rng(_element_seed(seed, key, "k_rate"))
        rng_d = np.random.default_rng(_element_seed(seed, key, "d_eff"))
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
            "d_eff": (
                _log_uniform(rng_d, *params.d_eff_interval, n)
                if params.d_eff_interval
                else np.full(n, params.d_eff_m2_per_s)
            ),
        }

    rng_edge = np.random.default_rng(_element_seed(seed, "__mat__", "edge_leakage"))
    if edge_leakage_interval is None:
        edge = np.full(max(0, n), float(edge_leakage_nominal))
    else:
        low, high = float(edge_leakage_interval[0]), float(edge_leakage_interval[1])
        if low > high:
            raise ValueError(
                f"edge leakage interval is inverted: {edge_leakage_interval!r}"
            )
        edge = rng_edge.uniform(low, high, size=max(0, n))

    members: list[Mapping[str, MaterialParameters]] = [dict(materials)]
    for index in range(n):
        member: dict[str, MaterialParameters] = {}
        for key, params in materials.items():
            member[key] = MaterialParameters(
                element=params.element,
                kd_m3_per_kg=float(draws[key]["kd"][index]),
                q_max_kg_per_kg=float(draws[key]["q_max"][index]),
                k_rate_per_s=float(draws[key]["k_rate"][index]),
                allocation_fraction=params.allocation_fraction,
                d_eff_m2_per_s=float(draws[key]["d_eff"][index]),
                kd_interval=params.kd_interval,
                q_max_interval=params.q_max_interval,
                k_rate_interval=params.k_rate_interval,
                d_eff_interval=params.d_eff_interval,
                fouling_rate_capacity=params.fouling_rate_capacity,
                fouling_rate_kinetics=params.fouling_rate_kinetics,
                fouling_rate_diffusivity=params.fouling_rate_diffusivity,
                provenance=params.provenance,
                source_ref=params.source_ref,
            )
        members.append(member)

    leakage = (float(edge_leakage_nominal),) + tuple(float(value) for value in edge)
    return ParameterEnsemble(
        members=tuple(members),
        edge_leakage_fraction=leakage,
        seed=int(seed),
    )


def scale_material(
    params: MaterialParameters,
    *,
    kd_scale: float = 1.0,
    q_max_scale: float = 1.0,
    k_rate_scale: float = 1.0,
    d_eff_scale: float = 1.0,
    source_ref: str | None = None,
) -> MaterialParameters:
    """A scaled variant of a parameter set, for explicit what-if variants.

    Used to build a deliberately weak medium (slow kinetics, small capacity) so
    that the weak case is a *stated* variant rather than a hidden tweak.
    Uncertainty intervals are scaled with the nominal value so the ensemble
    stays consistent with it.
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
        d_eff_m2_per_s=params.d_eff_m2_per_s * d_eff_scale,
        kd_interval=_scaled_interval(params.kd_interval, kd_scale),
        q_max_interval=_scaled_interval(params.q_max_interval, q_max_scale),
        k_rate_interval=_scaled_interval(params.k_rate_interval, k_rate_scale),
        d_eff_interval=_scaled_interval(params.d_eff_interval, d_eff_scale),
        fouling_rate_capacity=params.fouling_rate_capacity,
        fouling_rate_kinetics=params.fouling_rate_kinetics,
        fouling_rate_diffusivity=params.fouling_rate_diffusivity,
        provenance=params.provenance,
        source_ref=source_ref or params.source_ref,
    )


# ---------------------------------------------------------------------------
# The only unit boundary in this package
# ---------------------------------------------------------------------------

def contact_concentration_kg_per_m3(value: float, unit: str) -> float:
    """Display aqueous concentration -> SI, delegating to ``units``.

    Present so that no caller in ``reactive_layer/`` has an excuse to hard-code
    ``1e-9``.  A solid-loading unit raises here, exactly as it does in
    ``units``: ``ng/g`` is a mass fraction and never an aqueous concentration.
    """
    return to_si_aqueous_concentration(value, unit)


def solid_loading_kg_per_kg(value: float, unit: str) -> float:
    """Display sorbent loading (``mg/kg``, ``ng/g`` ...) -> SI kg kg^-1."""
    return to_si_solid_loading(value, unit)


def sequence_of_elements(
    materials: Mapping[str, MaterialParameters],
) -> Sequence[str]:
    """Stable element ordering for reports (Pb before Hg, then anything else)."""
    preferred = [Element.PB.value, Element.HG.value]
    ordered = [key for key in preferred if key in materials]
    ordered.extend(sorted(key for key in materials if key not in preferred))
    return tuple(ordered)
