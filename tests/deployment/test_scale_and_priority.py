"""How much area there is, and which of it is worth covering.

The tests that matter here are the ones that stop the deployment story from
being told more favourably than the evidence allows: that the ranking really
does demote the famous offshore dumpsite, and that an area can rank first on
receptor grounds while this material still cannot treat what is in it.
"""

from __future__ import annotations

import math

import pytest

from reactive_seabed_mat.config import default_run_config
from reactive_seabed_mat.deployment import (
    BALTIC_DUMPSITES,
    GERMAN_PROGRAMME,
    PILOT_CANDIDATES,
    RECEPTOR_WEIGHTS,
    CandidateArea,
    Receptor,
    coverable_area_m2,
    material_demand,
    priority_score,
    proximity_score,
    rank_candidates,
    recovery_years,
    scale_table,
)
from reactive_seabed_mat.deployment.scale import NAUTICAL_MILE_M


# ---------------------------------------------------------------------------
# Scale
# ---------------------------------------------------------------------------

def test_the_bornholm_primary_area_follows_from_its_published_geometry():
    """A 3 nautical mile circle, not a number somebody typed."""
    site = BALTIC_DUMPSITES[0]
    expected = math.pi * (3.0 * NAUTICAL_MILE_M) ** 2 / 1.0e6
    assert site.area_km2 == pytest.approx(expected)
    assert site.area_km2 == pytest.approx(96.98, abs=0.05)


def test_covering_the_primary_dumpsite_needs_an_absurd_amount_of_keratin():
    """The arithmetic that says area capping is not a plan."""
    config = default_run_config()
    demand = material_demand(
        BALTIC_DUMPSITES[0].area_m2,
        sorbent_loading_kg_per_m2=config.mat.sorbent_loading_kg_per_m2,
        mat_material_eur_per_m2=config.costs.mat_material_eur_per_m2,
    )
    assert demand.sorbent_tonnes > 3.0e5
    # More than a tenth of one year's world greasy wool clip.
    assert demand.fraction_of_world_wool_clip > 0.1
    assert demand.mat_material_eur > 1.0e10


def test_a_realistic_budget_buys_hectares_not_square_kilometres():
    config = default_run_config()
    area = coverable_area_m2(
        5.0e6, mat_material_eur_per_m2=config.costs.mat_material_eur_per_m2
    )
    assert 1.0e4 < area < 1.0e5  # between one and ten hectares


def test_the_scale_table_puts_the_demo_hotspot_first_and_dwarfs_it():
    config = default_run_config()
    rows = scale_table(
        sorbent_loading_kg_per_m2=config.mat.sorbent_loading_kg_per_m2,
        mat_material_eur_per_m2=config.costs.mat_material_eur_per_m2,
        demo_hotspot_area_m2=config.hotspot.width_m * config.hotspot.length_m,
    )
    assert rows[0]["times_larger_than_demo"] == 1.0
    assert all(row["times_larger_than_demo"] >= 1.0 for row in rows)
    assert max(row["times_larger_than_demo"] for row in rows) > 1.0e4


def test_recovery_at_the_planned_rate_takes_centuries():
    """The size of the gap a containment measure would have to cover."""
    years = recovery_years(
        float(GERMAN_PROGRAMME["german_waters_munitions_tonnes"]),
        float(GERMAN_PROGRAMME["planned_platform_tonnes_per_day"]),
    )
    assert years > 300.0
    with pytest.raises(ValueError):
        recovery_years(1000.0, 0.0)


# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------

def test_proximity_decays_smoothly_and_halves_at_the_half_distance():
    assert proximity_score(0.0) == pytest.approx(1.0)
    assert proximity_score(5.0, half_distance_km=5.0) == pytest.approx(0.5)
    assert proximity_score(50.0) < proximity_score(5.0) < proximity_score(0.5)
    with pytest.raises(ValueError):
        proximity_score(1.0, half_distance_km=0.0)


def test_an_unknown_receptor_kind_is_refused():
    """Weights are a published judgement, so the vocabulary is closed."""
    with pytest.raises(KeyError):
        Receptor("vibes", 1.0)
    with pytest.raises(ValueError):
        Receptor("bathing_water", -1.0)


def test_receptor_proximity_demotes_the_biggest_dumpsite():
    """The result that inverts the intuition the war-pollution framing invites.

    Bornholm is the largest and most famous site and it should rank LAST,
    because it is deep and far from anyone. If this ever flips, the ranking has
    stopped meaning what the deployment argument says it means.
    """
    rows = rank_candidates()
    assert rows[0]["priority_score"] > rows[-1]["priority_score"]
    assert "Bornholm" in str(rows[-1]["name"])
    assert rows[-1]["priority_score"] < 0.5 * rows[0]["priority_score"]


def test_a_nearer_receptor_outranks_a_larger_area():
    near = CandidateArea(
        name="small and close",
        sea="coastal",
        depth_m=5.0,
        area_km2=0.1,
        receptors=(Receptor("bathing_water", 0.5),),
        documented_contaminants=("Pb",),
    )
    far = CandidateArea(
        name="huge and distant",
        sea="offshore",
        depth_m=90.0,
        area_km2=1000.0,
        receptors=(Receptor("bathing_water", 50.0),),
        documented_contaminants=("Pb",),
    )
    assert priority_score(near) > priority_score(far)


def test_ranking_high_does_not_mean_this_material_can_treat_it():
    """The finding that must not be smoothed away.

    The Bay of Lubeck ranks near the top on receptors and its documented
    contamination is energetic compounds, which a keratin thiol core does not
    bind. Score and addressability are reported separately for exactly this
    reason.
    """
    rows = rank_candidates()
    lubeck = next(row for row in rows if "Lubeck" in str(row["name"]))
    assert lubeck["priority_score"] > 1.5
    assert lubeck["addressable_by_this_material"] is False
    assert set(lubeck["documented_contaminants"]) == {"TNT", "RDX", "DNT"}

    # And at least one high-ranking candidate IS addressable, or the argument
    # would have no positive case at all.
    assert any(row["addressable_by_this_material"] for row in rows[:2])


def test_every_candidate_declares_what_is_documented_there():
    for area in PILOT_CANDIDATES:
        assert area.documented_contaminants, f"{area.name} declares no contaminant"
        assert area.source, f"{area.name} cites no source"


def test_receptor_weights_are_bounded_judgements():
    assert all(0.0 < weight <= 1.0 for weight in RECEPTOR_WEIGHTS.values())
