"""Estimate each tile's condition from the observations an operator would hold.

Implements ``docs/MODEL_SPEC.md`` section 8 against the frozen
:class:`~reactive_seabed_mat.contracts.EstimateSnapshot`.

The one rule that shapes every function here: **a number is only as good as the
channel that carried it.** So

* a residual flux comes from a benthic chamber, never from a bottom-water
  concentration, because a concentration is not a flux;
* a source flux comes from a porewater chemistry result and an *assumed* seepage
  interval, and the assumption's width stays in the answer;
* attenuation is the quotient of those two intervals, so an unmeasured source
  makes the attenuation unknown rather than optimistic;
* loading is the time integral of what the mat is inferred to have captured,
  which means a long gap in the evidence widens the interval rather than
  narrowing it.

Falling residual flux has at least six causes, and several of them are not the
mat working: the sediment source may have weakened, the seepage may have slowed,
the mat may be buried, or the chamber may have been deployed on a different
patch. :func:`estimate_tiles` therefore attributes across
:class:`~reactive_seabed_mat.contracts.DegradationMode` with explicit weights
and refuses to concentrate them when the channels that would separate the modes
were not observed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from ..config import RunConfig
from ..contracts import (
    AmbiguityFlag,
    DegradationMode,
    EstimateSnapshot,
    Matrix,
    ObservationRecord,
    OperatorKnownMat,
    Parameter,
    QualityFlag,
    QuantityKind,
    Qualifier,
    StateOrigin,
)
from ..observations.condition import CONDITION_MODE, integrity_band_for_class
from ..units import to_si_areal_flux, to_si_aqueous_concentration

__all__ = [
    "EstimationAssumptions",
    "capacity_kg_per_m2",
    "estimate_tiles",
    "interval_product",
    "interval_quotient",
]


def capacity_kg_per_m2(medium, sorbent_loading_kg_per_m2: float) -> tuple[float, float]:
    """The capacity interval an operator is entitled to use, per unit area.

    A commissioning isotherm on the actual batch is evidence about the material,
    so it supersedes the literature interval. Without one the only honest
    capacity is the literature range, which for keratin spans a factor of 27 and
    is too wide to support a replacement decision. Both the estimator and the
    policy must answer this question the same way, which is why it lives in one
    function rather than being written out twice.
    """
    band = medium.commissioned_q_max_interval or medium.q_max_interval
    loading = sorbent_loading_kg_per_m2 * medium.allocation_fraction
    return (loading * band[0], loading * band[1])

#: A decision may rest on a passed record.  ``NOT_EVALUATED`` is deliberately
#: excluded: an unchecked value is not a good value, and treating it as one is
#: how a drifting probe ends up driving a replacement.
_USABLE_FLAGS = (QualityFlag.PASSED,)

#: Widths applied when a quantity rests on an assumption rather than a
#: measurement.  Deliberately generous: an operator who has not measured the
#: seepage does not know it to better than a factor of a few.
_SEEPAGE_WIDTH = (0.4, 2.5)


@dataclass(frozen=True, slots=True)
class EstimationAssumptions:
    """What the operator is allowed to assume, and how loosely.

    Every field is an ``assumption`` in the provenance sense. None of them is a
    measurement of the deployed mat, and the intervals are wide because that is
    the honest width, not because wide intervals are safe.
    """

    #: Multiplicative band on the design seepage velocity. The operator knows
    #: the design value; the seabed does not.
    seepage_band: tuple[float, float] = _SEEPAGE_WIDTH
    #: Widening applied per year of gap between the newest usable record for a
    #: quantity and the decision time. Old evidence is weaker evidence.
    staleness_widening_per_year: float = 0.35
    #: Below this many usable chemistry records the estimate is treated as
    #: evidence-limited whatever its nominal width.
    min_records_for_trend: int = 3
    #: Fraction of the interval width below which two explanations are treated
    #: as indistinguishable rather than ranked.
    indistinguishable_margin: float = 0.15
    #: Extra widening applied when a tile's chemistry is borrowed from another
    #: tile.  A mat of nine tiles carries chemistry on one or two of them, so
    #: most tiles are judged by extrapolation.  This is a stated convention for
    #: that extrapolation, not a measurement of tile-to-tile variability, which
    #: nobody here has made.  Half a log-width: doubling it instead turns an
    #: already wide interval into an uninformative one, and an uninformative
    #: interval presented as an estimate is worse than reporting "unknown".
    cross_tile_widening: float = 0.5
    interval_level: float = 0.9


# ---------------------------------------------------------------------------
# Interval arithmetic.  Endpoint arithmetic is exact for these monotone
# combinations and avoids pretending to a distribution nobody measured.
# ---------------------------------------------------------------------------

def interval_product(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    """Product of two intervals, by endpoints."""
    candidates = (a[0] * b[0], a[0] * b[1], a[1] * b[0], a[1] * b[1])
    return (min(candidates), max(candidates))


def interval_quotient(
    a: tuple[float, float], b: tuple[float, float]
) -> tuple[float, float] | None:
    """Quotient of two intervals, or ``None`` when the divisor spans zero.

    Returning ``None`` rather than an infinite bound is deliberate: a ratio
    against an unknown-sign denominator is not a wide answer, it is no answer.
    """
    if b[0] <= 0.0 <= b[1]:
        return None
    candidates = (a[0] / b[0], a[0] / b[1], a[1] / b[0], a[1] / b[1])
    return (min(candidates), max(candidates))


def _widen(interval: tuple[float, float], factor: float) -> tuple[float, float]:
    """Widen an interval by ``factor`` (0 leaves it alone).

    Geometric, not arithmetic, whenever both endpoints are positive: a
    concentration or a flux is known to within a *factor*, so widening it about
    the geometric mean keeps the answer positive. Widening a
    ``(1e-11, 9e-11)`` flux arithmetically pushes the lower bound below zero,
    and a flux interval that reaches zero destroys every quotient downstream:
    attenuation stops being computable and no breakthrough can be forecast.
    Arithmetic widening is kept only for intervals that already touch zero,
    where there is no ratio to preserve.
    """
    if factor <= 0.0:
        return interval
    low, high = interval
    if low > 0.0 and high > 0.0:
        geometric_mean = math.sqrt(low * high)
        spread = (high / low) ** (0.5 * (1.0 + factor))
        return (geometric_mean / spread, geometric_mean * spread)
    mid = 0.5 * (low + high)
    half = 0.5 * (high - low) * (1.0 + factor)
    return (mid - half, mid + half)


def _clip(interval: tuple[float, float], low: float, high: float) -> tuple[float, float]:
    return (min(max(interval[0], low), high), min(max(interval[1], low), high))


# ---------------------------------------------------------------------------
# Record selection
# ---------------------------------------------------------------------------

def _usable(record: ObservationRecord) -> bool:
    """Records a decision may rest on.

    A non-detect is kept: it is a bound, and a bound is evidence. A missing
    value is dropped, because it carries no bound at all. That asymmetry is the
    whole point of the qualifier ladder.
    """
    if record.quality_flag not in _USABLE_FLAGS:
        return False
    if record.qualifier is Qualifier.MISSING:
        return False
    return True


def _value_interval_si(record: ObservationRecord) -> tuple[float, float] | None:
    """One record as an SI interval, honouring the censoring ladder.

    ``quantified``   -> value +/- k*sigma
    ``below_lod``    -> [0, LOD]
    ``below_loq``    -> [LOD, LOQ] when both are carried, else [0, LOQ]
    ``above_range``  -> [top, 3*top], an explicit lower bound with an admitted
                        arbitrary upper one, never a point
    """
    if record.quantity_kind is QuantityKind.AQUEOUS_CONCENTRATION:
        convert = to_si_aqueous_concentration
    elif record.quantity_kind is QuantityKind.AREAL_FLUX:
        convert = to_si_areal_flux
    else:
        return None

    lower = record.lower_bound
    upper = record.upper_bound
    if record.qualifier is Qualifier.QUANTIFIED and record.value is not None:
        sigma = record.uncertainty_std or 0.0
        return (
            convert(max(record.value - 2.0 * sigma, 0.0), record.unit),
            convert(record.value + 2.0 * sigma, record.unit),
        )
    if record.qualifier in (Qualifier.BELOW_LOD, Qualifier.BELOW_LOQ):
        top = upper if upper is not None else record.value
        if top is None:
            return None
        bottom = lower if lower is not None else 0.0
        return (convert(bottom, record.unit), convert(top, record.unit))
    if record.qualifier is Qualifier.ABOVE_RANGE:
        bottom = lower if lower is not None else record.value
        if bottom is None:
            return None
        # No upper bound exists.  Three times the top of range is an admitted
        # convention, recorded in the notes rather than hidden in a constant.
        return (convert(bottom, record.unit), convert(3.0 * bottom, record.unit))
    return None


def _by_tile(records: Iterable[ObservationRecord]) -> dict[str, list[ObservationRecord]]:
    grouped: dict[str, list[ObservationRecord]] = {}
    for record in records:
        if record.tile_id:
            grouped.setdefault(record.tile_id, []).append(record)
    return grouped


def _select(
    records: Sequence[ObservationRecord],
    *,
    element: str | None = None,
    quantity: QuantityKind | None = None,
    matrix: Matrix | None = None,
    parameter: Parameter | None = None,
) -> list[ObservationRecord]:
    out = []
    for record in records:
        if not _usable(record):
            continue
        if quantity is not None and record.quantity_kind is not quantity:
            continue
        if matrix is not None and record.matrix is not matrix:
            continue
        if parameter is not None and record.parameter is not parameter:
            continue
        if element is not None and record.parameter.value != element:
            continue
        out.append(record)
    return sorted(out, key=lambda r: r.observed_at_utc)


def _media_installed_at(known: OperatorKnownMat, tile_id: str) -> datetime:
    """When this tile's current media went in.

    The operator knows this without any simulator access: it is the latest
    service event they accepted that named this tile, or the original deployment
    if there has not been one.
    """
    latest = known.installed_at_utc
    for event in known.accepted_service_events:
        if tile_id in event.tile_ids and event.time_utc > latest:
            latest = event.time_utc
    return latest


def _own_or_pooled(
    own: Sequence[ObservationRecord],
    pooled: Sequence[ObservationRecord],
    **criteria,
) -> tuple[list[ObservationRecord], bool]:
    """This tile's records for a channel, or the mat's if it has none.

    The second element says whether the answer was borrowed, so the caller can
    widen the interval and say so rather than presenting an extrapolation as a
    measurement of this tile.
    """
    mine = _select(own, **criteria)
    if mine:
        return mine, False
    borrowed = _select(pooled, **criteria)
    # Borrowed only if something was actually borrowed. With no records anywhere
    # the answer is "no evidence", and saying "extrapolated from another
    # instrumented tile" would be a false statement in an operator-facing note.
    return borrowed, bool(borrowed)


def _age_s(records: Sequence[ObservationRecord], now: datetime) -> float | None:
    if not records:
        return None
    return (now - max(r.observed_at_utc for r in records)).total_seconds()


def _staleness_factor(age_s: float | None, assumptions: EstimationAssumptions) -> float:
    if age_s is None:
        return 0.0
    return assumptions.staleness_widening_per_year * max(age_s, 0.0) / (365.25 * 86400.0)


# ---------------------------------------------------------------------------
# The estimate
# ---------------------------------------------------------------------------

def estimate_tiles(
    records: Sequence[ObservationRecord],
    known: OperatorKnownMat,
    config: RunConfig,
    now: datetime,
    *,
    assumptions: EstimationAssumptions | None = None,
) -> dict[str, EstimateSnapshot]:
    """One :class:`EstimateSnapshot` per tile, from observations only.

    ``records`` must already be time-gated with
    :func:`~reactive_seabed_mat.observations.records.observations_available`;
    this function does not look at ``available_at_utc`` again, and passing it
    future records is a caller bug that no assertion here can catch.
    """
    assumptions = assumptions or EstimationAssumptions()
    grouped = _by_tile(records)
    elements = [str(element) for element in config.elements]
    media_by_element = {medium.element: medium for medium in config.mat.media}
    loading_kg_per_m2 = config.mat.sorbent_loading_kg_per_m2
    design_seepage = config.hotspot.schedule[0].seepage_velocity_m_per_s

    # A nine-tile mat carries chemistry on one or two tiles. Every other tile is
    # judged by extrapolation from those, which is what a real programme does
    # and what section "Known evidence and estimation limitations" of
    # docs/LIMITATIONS.md warns about. The pool makes that extrapolation
    # explicit and widens the interval for it, rather than leaving most tiles
    # with no estimate at all.
    pooled = [record for record in records if _usable(record)]

    snapshots: dict[str, EstimateSnapshot] = {}
    for tile_id in known.tile_ids:
        tile_records = grouped.get(tile_id, [])
        snapshots[tile_id] = _estimate_one_tile(
            tile_id=tile_id,
            records=tile_records,
            pooled=pooled,
            known=known,
            elements=elements,
            media_by_element=media_by_element,
            loading_kg_per_m2=loading_kg_per_m2,
            design_seepage_m_per_s=design_seepage,
            now=now,
            assumptions=assumptions,
        )
    return snapshots


def _estimate_one_tile(
    *,
    tile_id: str,
    records: Sequence[ObservationRecord],
    pooled: Sequence[ObservationRecord],
    known: OperatorKnownMat,
    elements: Sequence[str],
    media_by_element: Mapping[str, Any],
    loading_kg_per_m2: float,
    design_seepage_m_per_s: float,
    now: datetime,
    assumptions: EstimationAssumptions,
) -> EstimateSnapshot:
    notes: list[str] = []
    flags: list[AmbiguityFlag] = []
    evidence_ids: list[str] = []
    data_age: dict[str, float | None] = {}

    seepage_interval = (
        design_seepage_m_per_s * assumptions.seepage_band[0],
        design_seepage_m_per_s * assumptions.seepage_band[1],
    )

    loading_estimate: dict[str, float] = {}
    loading_interval: dict[str, tuple[float, float]] = {}
    remaining_interval: dict[str, tuple[float, float]] = {}
    residual_interval: dict[str, tuple[float, float]] = {}
    source_interval: dict[str, tuple[float, float]] = {}
    attenuation_interval: dict[str, tuple[float, float]] = {}
    breakthrough: dict[str, tuple[float, float] | None] = {}

    # Loading accumulates on the CURRENT media, not since the mat was first
    # laid. A replaced tile starts empty, and integrating from the original
    # deployment would have the estimator recommend replacing a tile it had just
    # watched being replaced.
    installed = _media_installed_at(known, tile_id)
    elapsed_s = max((now - installed).total_seconds(), 0.0)

    for element in elements:
        chamber, chamber_borrowed = _own_or_pooled(
            records, pooled, element=element, quantity=QuantityKind.AREAL_FLUX
        )
        porewater, porewater_borrowed = _own_or_pooled(
            records,
            pooled,
            element=element,
            quantity=QuantityKind.AQUEOUS_CONCENTRATION,
            matrix=Matrix.POREWATER,
        )
        borrow_widening = assumptions.cross_tile_widening
        if chamber_borrowed or porewater_borrowed:
            notes.append(
                f"{element}: chemistry for this tile is extrapolated from "
                "another instrumented tile, and the interval is widened for it."
            )
        chamber_age = _age_s(chamber, now)
        porewater_age = _age_s(porewater, now)
        data_age[f"{element}|areal_flux"] = chamber_age
        data_age[f"{element}|porewater"] = porewater_age
        evidence_ids.extend(record.record_id for record in chamber[-4:])
        evidence_ids.extend(record.record_id for record in porewater[-4:])

        # --- the source side ------------------------------------------------
        pore_interval = _latest_interval(porewater)
        if pore_interval is None:
            notes.append(
                f"{element}: no usable porewater chemistry on this tile, so the "
                "source flux rests entirely on the design assumption."
            )
            flags.append(AmbiguityFlag.INSUFFICIENT_DATA)
            pore_interval = (0.0, 0.0)
            source = (0.0, 0.0)
        else:
            source = interval_product(pore_interval, seepage_interval)
            source = _widen(
                source,
                _staleness_factor(porewater_age, assumptions)
                + (borrow_widening if porewater_borrowed else 0.0),
            )
            source = _clip(source, 0.0, math.inf)

        # --- the residual side ----------------------------------------------
        chamber_interval = _latest_interval(chamber)
        if chamber_interval is None:
            # Without a flux measurement the only defensible statement is that
            # the mat emits somewhere between nothing and the whole source.
            residual = (0.0, source[1])
            notes.append(
                f"{element}: no usable benthic-chamber flux on this tile. The "
                "residual flux is bounded by the source, not measured."
            )
            flags.append(AmbiguityFlag.INSUFFICIENT_DATA)
        else:
            residual = _widen(
                chamber_interval,
                _staleness_factor(chamber_age, assumptions)
                + (borrow_widening if chamber_borrowed else 0.0),
            )
            residual = _clip(residual, 0.0, math.inf)

        residual_interval[element] = residual
        source_interval[element] = source

        # --- attenuation ----------------------------------------------------
        ratio = interval_quotient(residual, source)
        if ratio is None:
            attenuation_interval[element] = (0.0, 1.0)
            notes.append(
                f"{element}: the source flux interval includes zero, so "
                "attenuation is not computable from this evidence."
            )
        else:
            attenuation_interval[element] = _clip(
                (1.0 - ratio[1], 1.0 - ratio[0]), 0.0, 1.0
            )

        # --- loading and remaining capacity ---------------------------------
        captured = (
            max(source[0] - residual[1], 0.0),
            max(source[1] - residual[0], 0.0),
        )
        # Loading is the time integral of capture, so it is integrated over the
        # measurement history rather than by holding today's rate over the whole
        # service life. That distinction matters: today's residual flux is the
        # largest it has ever been, and projecting it backwards would say the
        # mat captured almost nothing since installation.
        loading_interval[element] = _integrate_capture(
            porewater_series=[
                (record.observed_at_utc, interval)
                for record, interval in _series(porewater)
            ],
            chamber_series=[
                (record.observed_at_utc, interval)
                for record, interval in _series(chamber)
            ],
            seepage_interval=seepage_interval,
            installed=installed,
            now=now,
            fallback=captured,
            widening=(
                _staleness_factor(porewater_age, assumptions)
                + (borrow_widening if porewater_borrowed else 0.0)
            ),
        )
        loading_estimate[element] = 0.5 * (
            loading_interval[element][0] + loading_interval[element][1]
        )

        medium = media_by_element.get(element)
        if medium is None:
            remaining_interval[element] = (0.0, 0.0)
            breakthrough[element] = None
            continue
        capacity = capacity_kg_per_m2(medium, loading_kg_per_m2)
        remaining_interval[element] = _clip(
            (
                capacity[0] - loading_interval[element][1],
                capacity[1] - loading_interval[element][0],
            ),
            0.0,
            math.inf,
        )

        # --- breakthrough -----------------------------------------------------
        if captured[0] <= 0.0:
            # Capture indistinguishable from zero: a forecast would be a
            # division by an unknown, so there is no forecast.
            breakthrough[element] = None
            notes.append(
                f"{element}: the inferred capture rate includes zero, so no "
                "breakthrough time is forecast."
            )
        else:
            breakthrough[element] = (
                remaining_interval[element][0] / captured[1],
                remaining_interval[element][1] / captured[0],
            )

    integrity, coverage_seen, condition_ids, condition_modes = _condition_from_records(
        records
    )
    evidence_ids.extend(condition_ids)
    data_age["condition"] = _age_s(
        _select(records, quantity=QuantityKind.CATEGORICAL), now
    )

    weights, mode_flags, mode_notes = _attribute(
        integrity=integrity,
        coverage_seen=coverage_seen,
        condition_modes=condition_modes,
        attenuation_interval=attenuation_interval,
        source_interval=source_interval,
        records=records,
        assumptions=assumptions,
    )
    flags.extend(mode_flags)
    notes.extend(mode_notes)

    return EstimateSnapshot(
        time_utc=now,
        tile_id=tile_id,
        loading_kg_per_m2_estimate=loading_estimate,
        loading_kg_per_m2_interval=loading_interval,
        remaining_capacity_kg_per_m2=remaining_interval,
        residual_flux_interval=residual_interval,
        source_flux_interval=source_interval,
        attenuation_interval=attenuation_interval,
        breakthrough_s_interval=breakthrough,
        fouling_index_interval=None,
        integrity_index_interval=integrity,
        effective_permeability_interval=None,
        data_age_s=data_age,
        model_data_compatibility=None,
        evidence_record_ids=tuple(dict.fromkeys(evidence_ids)),
        ambiguity_flags=tuple(dict.fromkeys(flags)),
        degradation_mode_weights=weights,
        interval_level=assumptions.interval_level,
        ensemble_size=0,
        origin=StateOrigin.ESTIMATED,
        notes=" ".join(notes),
        diagnostics={
            "seepage_interval_m_per_s": list(seepage_interval),
            "elapsed_since_install_s": elapsed_s,
            "n_records_considered": len(records),
            "above_range_convention": (
                "an above-range result is treated as [top, 3*top]: the lower "
                "bound is real, the upper bound is an admitted convention"
            ),
        },
    )


def _series(
    records: Sequence[ObservationRecord],
) -> list[tuple[ObservationRecord, tuple[float, float]]]:
    """Every record in a channel that yields an SI interval, in time order."""
    out = []
    for record in records:
        interval = _value_interval_si(record)
        if interval is not None:
            out.append((record, interval))
    return out


def _integrate_capture(
    *,
    porewater_series: Sequence[tuple[datetime, tuple[float, float]]],
    chamber_series: Sequence[tuple[datetime, tuple[float, float]]],
    seepage_interval: tuple[float, float],
    installed: datetime,
    now: datetime,
    fallback: tuple[float, float],
    widening: float,
) -> tuple[float, float]:
    """Time-integrate the captured flux interval over the measurement history.

    Zero-order hold on both channels: a measurement stands until the next one
    replaces it, which is what a campaign-interval monitoring programme
    actually gives you. The first measurement is held *backwards* to
    installation, which is a stated convention and not a measurement. It is the
    same convention every operator uses when the first survey happens some
    months after deployment, and it is the reason the interval carries a note
    rather than a smaller number.
    """
    elapsed_s = max((now - installed).total_seconds(), 0.0)
    if not porewater_series:
        return _clip((fallback[0] * elapsed_s, fallback[1] * elapsed_s), 0.0, math.inf)

    # A flux measured through the previous media says nothing about this one, so
    # chamber records from before the replacement are dropped. The porewater
    # series is kept whole: the sediment source does not reset when a tile does.
    chamber_series = [
        (time, interval) for time, interval in chamber_series if time >= installed
    ]

    times = sorted(
        {time for time, _ in porewater_series} | {time for time, _ in chamber_series}
    )
    edges = [installed] + [t for t in times if installed < t < now] + [now]

    total_low = 0.0
    total_high = 0.0
    for start, end in zip(edges[:-1], edges[1:]):
        span = (end - start).total_seconds()
        if span <= 0.0:
            continue
        pore = _held(porewater_series, start)
        if pore is None:
            continue
        source = _widen(interval_product(pore, seepage_interval), widening)
        source = _clip(source, 0.0, math.inf)
        chamber = _held(chamber_series, start)
        # No flux measurement standing over this stretch means the residual is
        # bounded only by the source, so the capture lower bound is zero there.
        residual = _clip(chamber, 0.0, math.inf) if chamber else (0.0, source[1])
        total_low += max(source[0] - residual[1], 0.0) * span
        total_high += max(source[1] - residual[0], 0.0) * span
    return (total_low, total_high)


def _held(
    series: Sequence[tuple[datetime, tuple[float, float]]], when: datetime
) -> tuple[float, float] | None:
    """The value standing at ``when`` under a zero-order hold.

    Before the first sample the first sample is held backwards, which is the
    convention documented in :func:`_integrate_capture`.
    """
    if not series:
        return None
    standing = series[0][1]
    for time, interval in series:
        if time > when:
            break
        standing = interval
    return standing


def _latest_interval(
    records: Sequence[ObservationRecord],
) -> tuple[float, float] | None:
    """The most recent usable record as an SI interval.

    The most recent, not an average: averaging a censored result with a
    quantified one silently converts a bound into a number.
    """
    for record in reversed(records):
        interval = _value_interval_si(record)
        if interval is not None:
            return interval
    return None


def _condition_from_records(
    records: Sequence[ObservationRecord],
) -> tuple[tuple[float, float] | None, bool, list[str], set[DegradationMode]]:
    """Integrity band, whether coverage was surveyed, and the modes observed."""
    integrity: tuple[float, float] | None = None
    coverage_seen = False
    ids: list[str] = []
    modes: set[DegradationMode] = set()

    for record in sorted(records, key=lambda r: r.observed_at_utc):
        if not _usable(record):
            continue
        mode = CONDITION_MODE.get(record.parameter.value)
        if mode is not None:
            modes.add(mode)
            ids.append(record.record_id)
        if record.condition_class is not None:
            integrity = integrity_band_for_class(record.condition_class)
            ids.append(record.record_id)
        if record.parameter.value == "mat_coverage_fraction":
            coverage_seen = True
    return integrity, coverage_seen, ids, modes


def _attribute(
    *,
    integrity: tuple[float, float] | None,
    coverage_seen: bool,
    condition_modes: set[DegradationMode],
    attenuation_interval: Mapping[str, tuple[float, float]],
    source_interval: Mapping[str, tuple[float, float]],
    records: Sequence[ObservationRecord],
    assumptions: EstimationAssumptions,
) -> tuple[dict[str, float], list[AmbiguityFlag], list[str]]:
    """Split the blame for lost performance across the four degradation modes.

    The honest default is a flat split. Weight moves away from flat only when a
    channel was actually observed that distinguishes one mode from another: a
    damage class separates local damage, a coverage or displacement survey
    separates displacement, a differential-head or permeability reading
    separates fouling. Chemistry alone cannot separate saturation from a
    stronger source, which is why
    :attr:`AmbiguityFlag.SEDIMENT_SOURCE_INCREASE` is raised whenever the
    chemistry moved and no physical survey accompanied it.
    """
    modes = [mode.value for mode in DegradationMode]
    weights = {mode: 1.0 for mode in modes}
    flags: list[AmbiguityFlag] = []
    notes: list[str] = []

    worst_attenuation = min(
        (interval[0] for interval in attenuation_interval.values()), default=1.0
    )
    performance_lost = worst_attenuation < 0.9

    if integrity is not None and integrity[1] < 0.9:
        weights[DegradationMode.LOCAL_DAMAGE.value] += 3.0
        flags.append(AmbiguityFlag.TEAR_PUNCTURE)
        notes.append(
            "A damage class worse than intact was observed, so local damage "
            "carries weight that the chemistry alone could not assign."
        )
    if DegradationMode.DISPLACEMENT in condition_modes:
        weights[DegradationMode.DISPLACEMENT.value] += 2.0
        flags.append(AmbiguityFlag.DISPLACEMENT_UPLIFT)
    if DegradationMode.FOULING in condition_modes:
        weights[DegradationMode.FOULING.value] += 2.0
        flags.append(AmbiguityFlag.FOULING)

    burial = [
        record
        for record in records
        if _usable(record) and record.parameter.value == "burial_depth"
    ]
    if burial:
        flags.append(AmbiguityFlag.BURIAL)
        notes.append(
            "Burial was surveyed. A buried mat emits less because the path is "
            "longer, not because the chemistry is working, so a fall in "
            "measured flux here is not evidence of capture."
        )

    if performance_lost and not condition_modes and integrity is None:
        # Chemistry says something changed and nothing physical was inspected.
        # Saturation is the *convenient* reading, so it is precisely the one
        # that must not be assumed.
        flags.append(AmbiguityFlag.SEDIMENT_SOURCE_INCREASE)
        flags.append(AmbiguityFlag.ADVECTIVE_CHANGE)
        notes.append(
            "Performance fell with no physical survey to accompany it. "
            "Saturation, a stronger sediment source and a faster seepage all "
            "produce this signature, and the available evidence does not "
            "separate them."
        )
    elif performance_lost:
        weights[DegradationMode.SATURATION.value] += 1.0

    if any(interval[1] <= 0.0 for interval in source_interval.values()):
        flags.append(AmbiguityFlag.INSUFFICIENT_DATA)

    total = sum(weights.values())
    return ({mode: value / total for mode, value in weights.items()}, flags, notes)
