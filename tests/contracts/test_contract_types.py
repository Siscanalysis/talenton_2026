"""Structural tests for the frozen module boundary."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from mesh_demo import config as cfg
from mesh_demo.contracts import (
    CONTRACT_VERSION,
    ActionKind,
    ContactBatch,
    Element,
    FieldState,
    GridSpec,
    MassLedger,
    PanelGeometry,
    PanelState,
    Recommendation,
    StateOrigin,
)


def test_contract_version_is_frozen_marker():
    assert CONTRACT_VERSION.endswith("-frozen")


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
    state = FieldState(grid, datetime(2026, 9, 8, tzinfo=timezone.utc), concentration, land)
    assert state.water_mass_kg(Element.PB) == pytest.approx(3.0)
    assert state.water_mass_kg("Pb") == pytest.approx(3.0)
    assert state.origin is StateOrigin.TRUE_SIMULATED


def test_mass_ledger_invariant_arithmetic():
    ledger = MassLedger(
        element="Pb",
        initial_water_kg=0.0,
        emitted_kg=1.0,
        boundary_in_kg=0.0,
        in_water_kg=0.4,
        in_active_mesh_kg=0.1,
        in_retrieved_media_kg=0.2,
        boundary_out_kg=0.3,
    )
    assert ledger.supplied_kg == pytest.approx(1.0)
    assert ledger.accounted_kg == pytest.approx(1.0)
    assert abs(ledger.relative_imbalance) < 1e-12


def test_recommendation_cannot_disable_human_confirmation():
    kwargs = dict(
        recommendation_id="REC1",
        decision_time_utc=datetime(2026, 9, 8, tzinfo=timezone.utc),
        panel_id="panel_A",
        action=ActionKind.CONTINUE,
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


def test_panel_capacity_uses_allocated_mass_only():
    params = cfg.MaterialConfig()
    from mesh_demo.contracts import MaterialParameters

    material = MaterialParameters(
        element=Element.PB,
        kd_m3_per_kg=params.kd_m3_per_kg,
        q_max_kg_per_kg=params.q_max_kg_per_kg,
        k_rate_per_s=params.k_rate_per_s,
        allocation_fraction=params.allocation_fraction,
    )
    panel = PanelState(
        panel_id="panel_A",
        media_id="media_A0",
        installed_at_utc=datetime(2026, 9, 8, tzinfo=timezone.utc),
        sorbent_mass_kg=10.0,
        geometry=PanelGeometry(width_m=4.0, height_m=2.0, x_m=0.0, y_m=0.0),
        retained_kg={"Pb": 0.0, "Hg": 0.0},
    )
    assert panel.allocated_mass_kg(material) == pytest.approx(6.0)
    assert panel.nominal_capacity_kg(material) == pytest.approx(6.0 * 6.0e-5)


def test_material_allocation_fractions_do_not_exceed_one():
    panel = cfg.PanelConfig()
    total = sum(material.allocation_fraction for material in panel.materials)
    assert total <= 1.0 + 1e-12, "mesh capacity must not be assigned twice"


def test_contact_batch_records_its_interpretation():
    batch = ContactBatch(
        panel_id="panel_A",
        time_utc=datetime(2026, 9, 8, tzinfo=timezone.utc),
        dt_s=60.0,
        concentration_kg_per_m3={"Pb": 1e-7},
        concentration_interpretation="cell-mean dissolved, labile-equivalent",
        available_kg={"Pb": 1e-6},
        exchange_volume_m3=12.0,
        exchange_is_measured=False,
        cell_indices=(5,),
        cell_weights=(1.0,),
    )
    assert batch.exchange_is_measured is False
    assert batch.concentration_interpretation


def test_run_config_round_trip(tmp_path):
    original = cfg.default_run_config(run_id="rt", scenario="baseline")
    path = cfg.save_run_config(original, tmp_path / "config.json")
    restored = cfg.load_run_config(path)
    assert cfg.config_hash(restored) == cfg.config_hash(original)
    assert restored.n_steps == original.n_steps
    assert restored.start_datetime.tzinfo is not None


def test_config_hash_changes_with_the_configuration():
    a = cfg.default_run_config(seed=1)
    b = cfg.default_run_config(seed=2)
    assert cfg.config_hash(a) != cfg.config_hash(b)
