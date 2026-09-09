"""Turn estimates into recommendations, without ever touching simulator truth.

Implements ``docs/MODEL_SPEC.md`` section 9 against the frozen
:class:`~reactive_seabed_mat.contracts.Recommendation`.

The interesting rule is negative. A tile is recommended for replacement only
when the evidence supports *saturation specifically*. When the same falling
attenuation could equally be a stronger sediment source or a faster seepage, the
policy asks for chemistry instead of steel, because replacing a mat does not fix
a source that grew. That is the whole reason the estimator reports competing
weights rather than a single cause: a policy that reads only the headline number
would service the mat and watch the flux stay high.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Sequence

from ..config import RunConfig
from ..contracts import (
    ActionKind,
    AmbiguityFlag,
    EstimateSnapshot,
    METAL_PARAMETERS,
    OperatorKnownMat,
    Recommendation,
)
from ..estimation import capacity_kg_per_m2

__all__ = [
    "PolicyState",
    "accepted_service_tiles",
    "recommend",
    "saturation_interval",
]

_SIMULATION_ONLY = "simulation_only"

#: Ambiguity flags that mean "this could be the source, not the mat". A
#: replacement decision may not be taken while one of these stands unresolved.
_SOURCE_SIDE_FLAGS = (
    AmbiguityFlag.SEDIMENT_SOURCE_INCREASE,
    AmbiguityFlag.ADVECTIVE_CHANGE,
    AmbiguityFlag.BURIAL,
)


@dataclass
class PolicyState:
    """What the policy is allowed to remember between decisions.

    Only its own past decisions and the service events a human accepted. It
    never accumulates simulator state, which is why this is a small object.
    """

    last_service_s: float = 0.0
    n_recommendations: int = 0
    accepted_events: list[str] = field(default_factory=list)

    def next_id(self, kind: str, elapsed_s: float) -> str:
        self.n_recommendations += 1
        return f"REC-{kind}-{self.n_recommendations:04d}-{int(elapsed_s)}"


def saturation_interval(
    snapshot: EstimateSnapshot, config: RunConfig, element: str
) -> tuple[float, float] | None:
    """Estimated fraction of capacity consumed, as an interval.

    ``None`` when the medium is unknown or the assumed capacity is zero, which
    is a configuration problem rather than a wide answer.
    """
    medium = next(
        (m for m in config.mat.media if m.element == element), None
    )
    if medium is None:
        return None
    # The same capacity rule the estimator used, from the same function: a
    # policy that judged saturation against a different capacity than the
    # estimate was built on would be comparing two different quantities.
    capacity = capacity_kg_per_m2(medium, config.mat.sorbent_loading_kg_per_m2)
    if capacity[1] <= 0.0:
        return None
    held = snapshot.loading_kg_per_m2_interval.get(element)
    if held is None:
        return None
    # Low saturation pairs the low load with the generous capacity, and the
    # high saturation pairs the high load with the stingy capacity.
    low = held[0] / capacity[1]
    high = held[1] / capacity[0] if capacity[0] > 0.0 else 1.0
    return (max(low, 0.0), min(high, 1.0))


def _decision_value(interval: tuple[float, float], bound: str) -> float:
    """Reduce an interval to the one number the threshold is compared against.

    Which end you pick is a risk posture and it changes the answer, so it is a
    named configuration field rather than a hidden convention:

    ``lower``  act only when the evidence proves the threshold is passed. Safe
               against wasted servicing, and with a capacity known only to a
               factor of 27 it never fires at all.
    ``upper``  act as soon as the evidence permits it. Safe against uncontrolled
               release, and it services a mat that may be almost fresh.
    ``mid``    neutral between those two errors. The default, because neither
               error is obviously the worse one here.
    """
    if bound == "lower":
        return interval[0]
    if bound == "upper":
        return interval[1]
    if bound == "mid":
        return 0.5 * (interval[0] + interval[1])
    raise KeyError(
        f"unknown saturation_decision_bound {bound!r}; use lower, mid or upper"
    )


def recommend(
    estimates: Mapping[str, EstimateSnapshot],
    known: OperatorKnownMat,
    config: RunConfig,
    now: datetime,
    elapsed_s: float,
    state: PolicyState,
) -> list[Recommendation]:
    """Recommendations for this decision time, under the configured policy."""
    kind = config.policy.kind
    if kind == "none":
        return []
    if kind == "fixed":
        return _fixed(known, config, now, elapsed_s, state)
    if kind == "evidence_informed":
        return _evidence_informed(estimates, known, config, now, elapsed_s, state)
    raise KeyError(f"unknown policy kind {kind!r}")


def _make(
    *,
    state: PolicyState,
    tag: str,
    now: datetime,
    elapsed_s: float,
    known: OperatorKnownMat,
    action: ActionKind,
    reason: str,
    uncertainty_note: str,
    tiles: Sequence[str] = (),
    evidence: Sequence[str] = (),
    data_age_s: float | None = None,
    cost_eur: float | None = None,
    diagnostics: Mapping[str, object] | None = None,
) -> Recommendation:
    return Recommendation(
        recommendation_id=state.next_id(tag, elapsed_s),
        decision_time_utc=now,
        mat_id=known.mat_id,
        action=action,
        reason=reason,
        evidence_record_ids=tuple(evidence),
        uncertainty_note=uncertainty_note,
        data_age_s=data_age_s,
        target_tile_ids=tuple(tiles),
        human_confirmation_required=True,
        execution_mode=_SIMULATION_ONLY,
        expected_cost_eur=cost_eur,
        diagnostics=dict(diagnostics or {}),
    )


def _fixed(
    known: OperatorKnownMat,
    config: RunConfig,
    now: datetime,
    elapsed_s: float,
    state: PolicyState,
) -> list[Recommendation]:
    """Calendar servicing.  Deliberately blind to every observation."""
    due = elapsed_s - state.last_service_s >= config.policy.fixed_interval_s
    if not due:
        return [
            _make(
                state=state,
                tag="FIX",
                now=now,
                elapsed_s=elapsed_s,
                known=known,
                action=ActionKind.CONTINUE_MONITORING,
                reason=(
                    "Fixed-interval policy: the next service is not due. No "
                    "observation was consulted."
                ),
                uncertainty_note=(
                    "This policy ignores evidence by construction, so it "
                    "carries no uncertainty statement about mat condition."
                ),
            )
        ]
    return [
        _make(
            state=state,
            tag="FIX",
            now=now,
            elapsed_s=elapsed_s,
            known=known,
            action=ActionKind.PLAN_PARTIAL_REPLACEMENT,
            reason=(
                f"Fixed-interval policy: {config.policy.fixed_interval_s / (365.25 * 86400.0):.1f} "
                "years since the last service, so every tile is replaced "
                "whatever its condition."
            ),
            uncertainty_note=(
                "No condition evidence was used. Some tiles may be replaced "
                "with capacity left, and a failed tile may wait for the next "
                "calendar date."
            ),
            tiles=tuple(known.tile_ids),
            cost_eur=_assumed_cost(config, len(known.tile_ids), known),
            diagnostics={"policy": "fixed", "evidence_used": False},
        )
    ]


def _evidence_informed(
    estimates: Mapping[str, EstimateSnapshot],
    known: OperatorKnownMat,
    config: RunConfig,
    now: datetime,
    elapsed_s: float,
    state: PolicyState,
) -> list[Recommendation]:
    policy = config.policy
    out: list[Recommendation] = []

    replace_tiles: list[str] = []
    inspect_tiles: list[str] = []
    sample_tiles: list[str] = []
    blocked: list[tuple[str, str]] = []

    for tile_id, snapshot in estimates.items():
        evidence = tuple(snapshot.evidence_record_ids)
        # Physical failure first: a torn or displaced tile is not a chemistry
        # problem and no amount of capacity will fix it.
        integrity = snapshot.integrity_index_interval
        condition_age = snapshot.data_age_s.get("condition")
        if (integrity is not None and integrity[1] < policy.minimum_coverage_fraction
                and condition_age is not None and condition_age <= policy.max_data_age_s):
            inspect_tiles.append(tile_id)
            replace_tiles.append(tile_id)
            continue

        # Every required chemistry channel must be recent. A fresh ROV visit
        # or a Pb sample cannot refresh an old or missing Hg chamber result.
        monitored = [element for element in config.elements
                     if element in {parameter.value for parameter in METAL_PARAMETERS}]
        ages = [snapshot.data_age_s.get(f"{element}|{channel}")
                for element in monitored for channel in ("areal_flux", "porewater")]
        stale = not monitored or any(age is None or age > policy.max_data_age_s for age in ages)
        thin = snapshot.diagnostics.get("chemistry_record_count", len(evidence)) < policy.min_evidence_records
        if stale or thin:
            sample_tiles.append(tile_id)
            continue

        source_side = [
            flag for flag in snapshot.ambiguity_flags if flag in _SOURCE_SIDE_FLAGS
        ]

        worst_saturation = 0.0
        for element in monitored:
            interval = saturation_interval(snapshot, config, str(element))
            if interval is not None:
                worst_saturation = max(
                    worst_saturation,
                    _decision_value(interval, config.policy.saturation_decision_bound),
                )

        lost = any(
            snapshot.attenuation_interval.get(str(element), (1.0, 1.0))[1]
            < policy.minimum_acceptable_attenuation
            for element in monitored
        )

        if worst_saturation >= policy.replacement_saturation_threshold:
            if source_side:
                # The decisive case. Capacity looks consumed, but the same
                # evidence is consistent with a source that grew, and swapping
                # media would not touch that. Ask for the measurement that
                # separates them.
                blocked.append(
                    (
                        tile_id,
                        ", ".join(flag.value for flag in source_side),
                    )
                )
                sample_tiles.append(tile_id)
            else:
                replace_tiles.append(tile_id)
        elif worst_saturation >= policy.inspection_saturation_threshold or lost:
            inspect_tiles.append(tile_id)

    if replace_tiles:
        out.append(
            _make(
                state=state,
                tag="REPL",
                now=now,
                elapsed_s=elapsed_s,
                known=known,
                action=ActionKind.PLAN_PARTIAL_REPLACEMENT,
                reason=(
                    "The estimated consumed capacity, or the observed damage "
                    f"class, supports replacing {len(replace_tiles)} of "
                    f"{len(known.tile_ids)} tiles. The rest are left in place."
                ),
                uncertainty_note=(
                    "Saturation is an interval derived from the commissioned "
                    "capacity and an assumed seepage band, and most tiles "
                    "borrow their chemistry from an instrumented neighbour. "
                    f"The decision was taken on the "
                    f"'{config.policy.saturation_decision_bound}' end of that "
                    "interval, which is a risk posture and not a measurement."
                ),
                tiles=tuple(replace_tiles),
                evidence=tuple(
                    rid
                    for tile in replace_tiles
                    for rid in estimates[tile].evidence_record_ids
                ),
                cost_eur=_assumed_cost(config, len(replace_tiles), known),
                diagnostics={"policy": "evidence_informed", "evidence_used": True},
            )
        )
    if inspect_tiles:
        out.append(
            _make(
                state=state,
                tag="INSP",
                now=now,
                elapsed_s=elapsed_s,
                known=known,
                action=ActionKind.INSPECT_MAT,
                reason=(
                    "Observed condition or estimated chemical performance "
                    "supports inspecting the selected tiles. Any replacement "
                    "recommendation is recorded separately."
                ),
                uncertainty_note=(
                    "An inspection narrows the physical modes. It does not "
                    "measure capacity."
                ),
                tiles=tuple(inspect_tiles),
                cost_eur=float(config.costs.rov_survey_eur),
                diagnostics={"policy": "evidence_informed"},
            )
        )
    if sample_tiles:
        out.append(
            _make(
                state=state,
                tag="SAMP",
                now=now,
                elapsed_s=elapsed_s,
                known=known,
                action=(
                    ActionKind.PERFORMANCE_UNCERTAIN
                    if blocked
                    else ActionKind.TAKE_CHEMICAL_SAMPLE
                ),
                reason=(
                    (
                        "Replacement is NOT recommended: the evidence is "
                        "equally consistent with the sediment source or the "
                        "seepage having changed ("
                        + "; ".join(f"{tile}: {why}" for tile, why in blocked)
                        + "). New media would not address that, so porewater "
                        "chemistry is requested first."
                    )
                    if blocked
                    else (
                        "The evidence for these tiles is too old or too thin to "
                        "support any decision."
                    )
                ),
                uncertainty_note=(
                    "Acting on an ambiguous signal is how a monitoring "
                    "programme ends up replacing a working mat."
                ),
                tiles=tuple(dict.fromkeys(sample_tiles)),
                cost_eur=float(config.costs.porewater_sample_eur)
                * len(set(sample_tiles)),
                diagnostics={
                    "policy": "evidence_informed",
                    "blocked_by_ambiguity": [tile for tile, _ in blocked],
                },
            )
        )
    if not out:
        out.append(
            _make(
                state=state,
                tag="MON",
                now=now,
                elapsed_s=elapsed_s,
                known=known,
                action=ActionKind.CONTINUE_MONITORING,
                reason="No tile crossed a decision threshold on this evidence.",
                uncertainty_note=(
                    "Continuing to monitor is a decision, and it is the right "
                    "one only while the intervals stay narrow enough to notice "
                    "a change."
                ),
            )
        )
    return out


def _assumed_cost(config: RunConfig, n_tiles: int, known: OperatorKnownMat) -> float:
    """Assumed euro cost of one servicing campaign.  Never a quotation."""
    geometry = known.geometry
    area = geometry.width_m * geometry.length_m * n_tiles
    media_mass = area * geometry.thickness_m * geometry.bulk_density_kg_per_m3
    costs = config.costs
    return float(
        costs.deployment_vessel_day_eur
        + costs.tile_replacement_eur * n_tiles
        + costs.mat_material_eur_per_m2 * area
        + costs.used_media_handling_eur_per_kg * media_mass
    )


def accepted_service_tiles(
    recommendations: Sequence[Recommendation],
) -> tuple[str, ...]:
    """Tiles a human accepted for replacement.

    In this demonstrator acceptance is automatic and total, which is a
    *simplification and is labelled as one*: it models an operator who follows
    the recommendation exactly. It is not a claim that recommendations are
    executed without review, and the recommendation still carries
    ``human_confirmation_required = True`` in every export.
    """
    tiles: list[str] = []
    for recommendation in recommendations:
        if recommendation.action in (
            ActionKind.PLAN_PARTIAL_REPLACEMENT,
            ActionKind.REPLACE_ACTIVE_PANEL,
        ):
            tiles.extend(recommendation.target_tile_ids)
    return tuple(dict.fromkeys(tiles))
