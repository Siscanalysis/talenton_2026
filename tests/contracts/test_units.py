"""Unit-conversion contract tests (coordinator-owned)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mesh_demo import units


def test_aqueous_ladder_round_trip():
    # 1 ng/L == 1e-9 kg m^-3 exactly.
    assert units.to_si_aqueous_concentration(1.0, "ng/L") == pytest.approx(1e-9)
    assert units.to_si_aqueous_concentration(1.0, "ug/L") == pytest.approx(1e-6)
    assert units.to_si_aqueous_concentration(1.0, "mg/L") == pytest.approx(1e-3)
    value = 137.5
    si = units.to_si_aqueous_concentration(value, "ng/L")
    assert units.from_si_aqueous_concentration(si, "ng/L") == pytest.approx(value)


def test_solid_ladder_round_trip():
    assert units.to_si_solid_loading(1.0, "ng/g") == pytest.approx(1e-9)
    assert units.to_si_solid_loading(1.0, "mg/kg") == pytest.approx(1e-6)
    value = 21500.0
    si = units.to_si_solid_loading(value, "ng/g")
    assert units.from_si_solid_loading(si, "ng/g") == pytest.approx(value)


def test_solid_unit_rejected_on_aqueous_ladder():
    with pytest.raises(units.UnitError):
        units.to_si_aqueous_concentration(21500.0, "ng/g")


def test_aqueous_unit_rejected_on_solid_ladder():
    with pytest.raises(units.UnitError):
        units.to_si_solid_loading(148.0, "ng/L")


def test_cross_ladder_conversion_refused():
    with pytest.raises(units.UnitError):
        units.convert_scalar(1.0, "ng/L", "ng/g")


def test_unknown_unit_is_not_guessed():
    with pytest.raises(units.UnitError):
        units.to_si_aqueous_concentration(1.0, "ppb")


def test_mass_ladder():
    assert units.to_si_mass(1.0, "ng") == pytest.approx(1e-12)
    assert units.from_si_mass(1e-6, "mg") == pytest.approx(1.0)


def test_timestamps_require_explicit_utc():
    with pytest.raises(units.UnitError):
        units.parse_utc("2026-09-08T06:00:00")
    with pytest.raises(units.UnitError):
        units.parse_utc("2026-09-08T06:00:00+02:00")
    parsed = units.parse_utc("2026-09-08T06:00:00Z")
    assert parsed == datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc)
    assert units.format_utc(parsed) == "2026-09-08T06:00:00Z"


def test_naive_datetime_is_not_stamped_as_utc():
    with pytest.raises(units.UnitError):
        units.format_utc(datetime(2026, 9, 8, 6, 0))
