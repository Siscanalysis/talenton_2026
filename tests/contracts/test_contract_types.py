"""Structural tests for the frozen module boundary."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from reactive_seabed_mat import config as cfg
from reactive_seabed_mat.contracts import (
    CONTRACT_VERSION,
    ActionKind,
    AmbiguityFlag,
    DegradationMode,
    Element,
    FieldState,
    GridSpec,
    MassLedger,
    MatTileGeometry,
    MatTileState,
    MaterialParameters,
    Recommendation,
    SeabedExchange,
    SeabedHotspot,
    StateOrigin,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 8, tzinfo=UTC)


def _geometry(**overrides) -> MatTileGeometry:
    kwargs = dict(
        width_m=8.0,
        length_m=8.0,
        thickness_m=0.010,
        x_m=300.0,
        y_m=220.0,
        bulk_density_kg_per_m3=400.0,
        porosity=0.5,
    )
    kwargs.update(overrides)
    return MatTileGeometry(**kwargs)


def _material(**overrides) -> MaterialParameters:
    kwargs = dict(
        element=Element.PB,
        kd_m3_per_kg=5.0,
        q_max_kg_per_kg=1.0e-3,
        k_rate_per_s=4.0e-4,
        allocation_fraction=0.6,
    )
    kwargs.update(overrides)
    return MaterialParameters(**kwargs)


def _tile(nz: int = 40, **overrides) -> MatTileState:
    kwargs = dict(
        tile_id="tile_0_0",
        media_id="media_A0",
        installed_at_utc=NOW,
        geometry=_geometry(),
        porewater_kg_per_m3={"Pb": np.zeros(nz), "Hg": np.zeros(nz)},
        sorbed_kg_per_kg={"Pb": np.zeros(nz), "Hg": np.zeros(nz)},
    )
    kwargs.update(overrides)
    return MatTileState(**kwargs)


def test_contract_version_marks_the_mat_concept():
    assert CONTRACT_VERSION == "0.2.0-frozen-mat"


def test_no_vertical_mesh_interception_concepts_remain():
    """Success criterion 1: the interception vocabulary must be gone.

    Checked against real identifiers, not prose: the module docstring is
    allowed, and required, to say that these concepts do not apply.
    """
    import ast

    import reactive_seabed_mat.contracts as contracts

    names = set(dir(contracts))
    for forbidden in (
        "PanelGeometry",
        "PanelState",
        "PanelStep",
        "ContactBatch",
        "SourceTerm",
    ):
        assert forbidden not in names, f"{forbidden} belongs to the old concept"

    tree = ast.parse(open(contracts.__file__, encoding="utf-8").read())
    banned = {
        "frontal_area_m2",
        "interception_efficiency",
        "interception_interval",
        "swept_volume_m3",
        "exchange_volume_m3",
        "available_kg",
        "uptake_kg_by_element",
        "in_active_mesh_kg",
    }
    offenders: list[str] = []
    for node in ast.walk(tree):
        # dataclass fields and annotated attributes
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in banned:
                offenders.append(f"field {node.target.id} (line {node.lineno})")
        # function parameters
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in [*node.args.args, *node.args.kwonlyargs]:
                if arg.arg in banned:
                    offenders.append(f"parameter {arg.arg} (line {node.lineno})")
        # class names
        if isinstance(node, ast.ClassDef) and node.name in banned:
            offenders.append(f"class {node.name} (line {node.lineno})")
    assert not offenders, (
        "vertical-mesh interception identifiers survive in contracts.py: "
        + "; ".join(offenders)
    )


def test_grid_indexing_matches_row_major_order():
    grid = GridSpec(nx=4, ny=3, dx_m=2.0, dy_m=5.0, mixing_depth_m=4.0)
    assert grid.cell_index(0, 0) == 0
    assert grid.cell_index(3, 2) == 11
    assert grid.n_cells == 12
    assert grid.cell_volume_m3 == pytest.approx(2.0 * 5.0 * 4.0)
    field = np.arange(12, dtype=float).reshape(3, 4)
    assert field.reshape(-1)[grid.cell_index(2, 1)] == field[1, 2]
    with pytest.raises(IndexError):
        grid.cell_index(4, 0)


def test_field_state_water_mass_excludes_land():
    grid = GridSpec(nx=2, ny=2, dx_m=1.0, dy_m=1.0, mixing_depth_m=1.0)
    land = np.array([[True, False], [False, False]])
    concentration = {"Pb": np.array([[5.0, 1.0], [1.0, 1.0]])}
    state = FieldState(grid, NOW, concentration, land)
    assert state.water_mass_kg(Element.PB) == pytest.approx(3.0)
    assert state.origin is StateOrigin.TRUE_SIMULATED


# --- mat tile geometry and state -------------------------------------------

def test_tile_geometry_is_areal_not_frontal():
    geometry = _geometry()
    assert geometry.footprint_area_m2 == pytest.approx(64.0)
    # 400 kg/m3 * 0.010 m = 4 kg of medium per square metre of seabed
    assert geometry.sorbent_loading_kg_per_m2 == pytest.approx(4.0)
    assert geometry.sorbent_mass_kg == pytest.approx(256.0)
    assert not hasattr(geometry, "frontal_area_m2")
    assert not hasattr(geometry, "interception_efficiency")


def test_thickness_drives_loading_and_therefore_capacity():
    thin = _geometry(thickness_m=0.002)
    thick = _geometry(thickness_m=0.010)
    assert thin.sorbent_loading_kg_per_m2 == pytest.approx(0.8)
    assert thick.sorbent_loading_kg_per_m2 == pytest.approx(4.0)
    material = _material()
    thin_tile = _tile(geometry=thin)
    thick_tile = _tile(geometry=thick)
    assert thick_tile.capacity_kg_per_m2(material) == pytest.approx(
        5.0 * thin_tile.capacity_kg_per_m2(material)
    )


def test_capacity_uses_the_allocated_share_only():
    tile = _tile()
    pb = _material(allocation_fraction=0.6)
    hg = _material(element=Element.HG, allocation_fraction=0.4, q_max_kg_per_kg=4.0e-4)
    # 4 kg/m2 * 0.6 * 1e-3 kg/kg
    assert tile.capacity_kg_per_m2(pb) == pytest.approx(2.4e-3)
    assert tile.capacity_kg_per_m2(hg) == pytest.approx(4.0 * 0.4 * 4.0e-4)
    assert pb.allocation_fraction + hg.allocation_fraction <= 1.0


def test_retained_mass_counts_sorbed_and_dissolved():
    nz = 10
    tile = _tile(
        nz=nz,
        sorbed_kg_per_kg={"Pb": np.full(nz, 1.0e-4), "Hg": np.zeros(nz)},
        porewater_kg_per_m3={"Pb": np.full(nz, 1.0e-3), "Hg": np.zeros(nz)},
    )
    dz = tile.dz_m()
    expected = (0.5 * 1.0e-3 + 400.0 * 1.0e-4) * nz * dz
    assert tile.retained_kg_per_m2("Pb") == pytest.approx(expected)
    assert tile.retained_kg("Pb") == pytest.approx(expected * 64.0)


def test_saturation_fraction_uses_sorbed_mass_only():
    nz = 20
    material = _material()
    tile = _tile(nz=nz, sorbed_kg_per_kg={"Pb": np.full(nz, 6.0e-4), "Hg": np.zeros(nz)})
    # sorbed per area = 400 * 6e-4 * thickness = 2.4e-3 ; capacity = 2.4e-3
    assert tile.saturation_fraction(material) == pytest.approx(1.0)


def test_the_four_degradation_modes_are_independent_fields():
    tile = _tile(
        fouling_index=0.4, integrity_index=0.7, burial_depth_m=0.05, displaced=False
    )
    assert tile.fouling_index == 0.4
    assert tile.integrity_index == 0.7
    assert tile.burial_depth_m == 0.05
    assert tile.coverage_fraction == pytest.approx(0.7)
    # A displaced tile covers nothing, whatever its chemistry says.
    assert _tile(displaced=True, integrity_index=1.0).coverage_fraction == 0.0
    assert {mode.value for mode in DegradationMode} == {
        "saturation",
        "fouling",
        "displacement",
        "local_damage",
    }


def test_ambiguity_flags_cover_every_degradation_mode():
    values = {flag.value for flag in AmbiguityFlag}
    for required in (
        "saturation",
        "fouling",
        "burial",
        "erosion_scour",
        "displacement_uplift",
        "tear_puncture",
        "sediment_source_increase",
        "advective_change",
        "methylmercury_risk",
    ):
        assert required in values
    assert "plume_shift" not in values, "a vertical-mesh flag survived"


def test_action_kinds_are_the_maintenance_vocabulary():
    values = {action.value for action in ActionKind}
    assert values == {
        "CONTINUE_MONITORING",
        "TAKE_CHEMICAL_SAMPLE",
        "CHECK_SENSOR",
        "INSPECT_MAT",
        "PLAN_PARTIAL_REPLACEMENT",
        "REPLACE_ACTIVE_PANEL",
        "PERFORMANCE_UNCERTAIN",
    }


# --- ledger ----------------------------------------------------------------

def test_mass_ledger_is_source_driven():
    ledger = MassLedger(
        element="Pb",
        released_from_sediment_kg=1.0,
        in_water_kg=0.4,
        retained_in_mat_kg=0.3,
        retained_in_retrieved_media_kg=0.2,
        boundary_out_kg=0.1,
    )
    assert ledger.supplied_kg == pytest.approx(1.0)
    assert ledger.accounted_kg == pytest.approx(1.0)
    assert abs(ledger.relative_imbalance) < 1e-12


def test_mass_ledger_detects_an_imbalance():
    ledger = MassLedger(
        element="Pb", released_from_sediment_kg=1.0, in_water_kg=0.5
    )
    assert ledger.imbalance_kg == pytest.approx(-0.5)
    assert ledger.relative_imbalance == pytest.approx(-0.5)


# --- exchange and recommendation ------------------------------------------

def test_seabed_exchange_carries_driving_conditions_not_a_swept_volume():
    exchange = SeabedExchange(
        tile_id="tile_0_0",
        time_utc=NOW,
        dt_s=21600.0,
        sediment_porewater_kg_per_m3={"Pb": 1.0e-3},
        bottom_water_kg_per_m3={"Pb": 0.0},
        seepage_velocity_m_per_s=3.0e-8,
        film_transfer_m_per_s=5.0e-7,
        bare_flux_kg_per_m2_per_s={"Pb": 5.3e-10},
        cell_indices=(5,),
        cell_weights=(1.0,),
    )
    assert exchange.driving_is_measured is False
    assert not hasattr(exchange, "exchange_volume_m3")
    assert exchange.bare_flux_kg_per_m2_per_s["Pb"] > 0.0


def test_hotspot_is_an_abstract_area_not_an_object():
    hotspot = SeabedHotspot(
        hotspot_id="h1",
        cell_indices=(1, 2, 3),
        sediment_porewater_kg_per_m3={"Pb": 1.0e-3},
        bare_flux_kg_per_m2_per_s={"Pb": 5.3e-10},
        seepage_velocity_m_per_s=3.0e-8,
        film_transfer_m_per_s=5.0e-7,
    )
    assert hotspot.n_cells == 3
    assert "ordnance" in hotspot.description.lower()


def test_recommendation_cannot_disable_human_confirmation():
    kwargs = dict(
        recommendation_id="REC1",
        decision_time_utc=NOW,
        mat_id="mat_A",
        action=ActionKind.CONTINUE_MONITORING,
        reason="no change",
        evidence_record_ids=["R0001"],
        uncertainty_note="wide",
        data_age_s=60.0,
    )
    assert Recommendation(**kwargs).human_confirmation_required is True
    with pytest.raises(ValueError):
        Recommendation(**kwargs, human_confirmation_required=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Recommendation(**{**kwargs, "execution_mode": "live"})


# --- configuration ---------------------------------------------------------

def test_media_allocations_never_exceed_the_layer():
    mat = cfg.MatLayoutConfig()
    total = sum(medium.allocation_fraction for medium in mat.media)
    assert total <= 1.0 + 1e-12, "capacity must not be assigned to both metals"


def test_run_config_round_trip(tmp_path):
    original = cfg.default_run_config(run_id="rt", scenario="fresh_mat")
    path = cfg.save_run_config(original, tmp_path / "config.json")
    restored = cfg.load_run_config(path)
    assert cfg.config_hash(restored) == cfg.config_hash(original)
    assert restored.n_steps == original.n_steps
    assert restored.start_datetime.tzinfo is not None
    assert restored.hotspot.schedule[0].porewater_kg_per_m3 == (
        original.hotspot.schedule[0].porewater_kg_per_m3
    )


def test_config_hash_changes_with_the_configuration():
    assert cfg.config_hash(cfg.default_run_config(seed=1)) != cfg.config_hash(
        cfg.default_run_config(seed=2)
    )


def test_default_timescale_is_a_capping_timescale():
    config = cfg.default_run_config()
    # A cap works over years; a plume equilibrates in hours. The mat timeline
    # must not be set to a plume timescale.
    assert config.duration_years >= 1.0
    assert config.dt_s >= 3600.0
    assert config.plume.window_s <= 7.0 * 86400.0
