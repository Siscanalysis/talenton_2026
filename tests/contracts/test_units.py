"""Unit-conversion contract tests (coordinator-owned).

The areal-flux and length ladders exist because flux attenuation is the whole
claim of a reactive cap, and because a burial depth reported in centimetres used
to pass every check as if it were metres.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from reactive_seabed_mat import units


def test_aqueous_ladder_round_trip():
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


def test_areal_flux_ladder():
    assert units.to_si_areal_flux(1.0, "kg/m2/s") == pytest.approx(1.0)
    assert units.to_si_areal_flux(1.0, "ng/m2/s") == pytest.approx(1e-12)
    # 1 ug/m2/d = 1e-9 kg / 86400 s
    assert units.to_si_areal_flux(1.0, "ug/m2/d") == pytest.approx(1e-9 / 86400.0)
    assert units.to_si_areal_flux(1.0, "mg/m2/yr") == pytest.approx(
        1e-6 / (365.25 * 86400.0)
    )
    value = 2.6
    si = units.to_si_areal_flux(value, "ug/m2/d")
    assert units.from_si_areal_flux(si, "ug/m2/d") == pytest.approx(value)


def test_length_ladder_distinguishes_cm_from_m():
    assert units.to_si_length(4.5, "cm") == pytest.approx(0.045)
    assert units.to_si_length(4.5, "m") == pytest.approx(4.5)
    assert units.to_si_length(4.5, "cm") != pytest.approx(units.to_si_length(4.5, "m"))
    assert units.from_si_length(0.045, "mm") == pytest.approx(45.0)


def test_velocity_ladder_distinguishes_cm_per_year_from_m_per_s():
    per_year = units.to_si_velocity(95.0, "cm/yr")
    assert per_year == pytest.approx(0.95 / (365.25 * 86400.0))
    assert units.to_si_velocity(1.0, "m/s") == pytest.approx(1.0)
    # nine orders of magnitude apart: the reason this ladder exists
    assert units.to_si_velocity(1.0, "m/s") / units.to_si_velocity(
        1.0, "cm/yr"
    ) > 1e8


def test_solid_unit_rejected_on_aqueous_ladder():
    with pytest.raises(units.UnitError):
        units.to_si_aqueous_concentration(21500.0, "ng/g")


def test_aqueous_unit_rejected_on_solid_ladder():
    with pytest.raises(units.UnitError):
        units.to_si_solid_loading(148.0, "ng/L")


@pytest.mark.parametrize(
    "from_unit,to_unit",
    [
        ("ng/L", "ng/g"),
        ("ug/m2/d", "ug/L"),
        ("cm", "kg"),
        ("m/s", "m"),
        ("mg/kg", "mg/m2/d"),
    ],
)
def test_cross_ladder_conversion_refused(from_unit, to_unit):
    with pytest.raises(units.UnitError):
        units.convert_scalar(1.0, from_unit, to_unit)


def test_within_ladder_conversion_allowed():
    assert units.convert_scalar(1.0, "cm", "mm") == pytest.approx(10.0)
    assert units.convert_scalar(1000.0, "ng/L", "ug/L") == pytest.approx(1.0)
    assert units.convert_scalar(86400.0, "ug/m2/d", "ug/m2/s") == pytest.approx(
        1.0, rel=1e-12
    )


def test_unknown_unit_is_not_guessed():
    with pytest.raises(units.UnitError):
        units.to_si_aqueous_concentration(1.0, "ppb")
    with pytest.raises(units.UnitError):
        units.to_si_areal_flux(1.0, "flux")


def test_length_is_no_longer_an_unconverted_context_unit():
    # 'm' used to sit in the context set with no conversion factor at all.
    assert "m" not in units.DIMENSIONLESS_OR_CONTEXT_UNITS
    assert "m" in units.LENGTH_UNITS
    assert "m/s" not in units.DIMENSIONLESS_OR_CONTEXT_UNITS
    assert "m/s" in units.VELOCITY_UNITS


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
