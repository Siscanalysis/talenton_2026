"""Explicit SI unit handling for the mesh demonstrator.

Coordinator-owned module (see ``AGENTS.md``).  Branch agents import from here;
they must not re-implement conversions locally.

Internal convention, used by every model transfer in this repository:

======================  ===========================
Quantity                Internal SI unit
======================  ===========================
mass                    kg
aqueous concentration   kg m^-3
solid loading           kg kg^-1 (mass fraction)
length                  m
area                    m^2
volume                  m^3
time                    s
velocity                m s^-1
diffusivity             m^2 s^-1
======================  ===========================

Display units (``ng/L``, ``ug/L``, ``mg/kg`` ...) exist only at the I/O and
presentation boundaries.  There is deliberately **no** inference of a unit from
a parameter name: an unknown unit string raises instead of guessing.

The aqueous and the mass-based (solid / sorbent) ladders are kept apart on
purpose.  ``ng/g`` is a mass fraction and must never be pushed through the
aqueous conversion (``docs/DATA_CONTRACT.md`` section 1).
"""

from __future__ import annotations

from datetime import datetime, timezone

__all__ = [
    "UnitError",
    "AQUEOUS_CONCENTRATION_UNITS",
    "SOLID_LOADING_UNITS",
    "MASS_UNITS",
    "AREAL_FLUX_UNITS",
    "LENGTH_UNITS",
    "VELOCITY_UNITS",
    "to_si_areal_flux",
    "from_si_areal_flux",
    "to_si_length",
    "from_si_length",
    "to_si_velocity",
    "from_si_velocity",
    "to_si_aqueous_concentration",
    "from_si_aqueous_concentration",
    "to_si_solid_loading",
    "from_si_solid_loading",
    "to_si_mass",
    "from_si_mass",
    "convert_scalar",
    "utc_now",
    "parse_utc",
    "format_utc",
]


class UnitError(ValueError):
    """Raised when a unit is unknown, or used on the wrong physical ladder."""


# --- aqueous concentration: factor to kg m^-3 ------------------------------
# 1 ng/L = 1e-12 kg / 1e-3 m^3 = 1e-9 kg m^-3
AQUEOUS_CONCENTRATION_UNITS: dict[str, float] = {
    "ng/L": 1.0e-9,
    "ug/L": 1.0e-6,
    "mg/L": 1.0e-3,
    "g/L": 1.0e0,
    "kg/m3": 1.0,
    "ng/m3": 1.0e-12,
    "ug/m3": 1.0e-9,
    "mg/m3": 1.0e-6,
}

# --- solid / sorbent loading: factor to kg kg^-1 ---------------------------
# 1 ng/g = 1e-9 g / 1 g = 1e-9 kg kg^-1
SOLID_LOADING_UNITS: dict[str, float] = {
    "ng/g": 1.0e-9,
    "ug/g": 1.0e-6,
    "mg/kg": 1.0e-6,
    "ug/kg": 1.0e-9,
    "mg/g": 1.0e-3,
    "g/kg": 1.0e-3,
    "kg/kg": 1.0,
}

# --- mass: factor to kg ----------------------------------------------------
MASS_UNITS: dict[str, float] = {
    "ng": 1.0e-12,
    "ug": 1.0e-9,
    "mg": 1.0e-6,
    "g": 1.0e-3,
    "kg": 1.0,
}

# --- areal flux: factor to kg m^-2 s^-1 ------------------------------------
# The quantity the mat is judged on.  Without this ladder no flux value could
# be converted, validated or range-checked, and flux attenuation is the whole
# claim of a reactive cap.
_SECONDS_PER_DAY = 86400.0
_SECONDS_PER_YEAR = 365.25 * _SECONDS_PER_DAY

AREAL_FLUX_UNITS: dict[str, float] = {
    "kg/m2/s": 1.0,
    "g/m2/s": 1.0e-3,
    "mg/m2/s": 1.0e-6,
    "ug/m2/s": 1.0e-9,
    "ng/m2/s": 1.0e-12,
    "kg/m2/d": 1.0 / _SECONDS_PER_DAY,
    "g/m2/d": 1.0e-3 / _SECONDS_PER_DAY,
    "mg/m2/d": 1.0e-6 / _SECONDS_PER_DAY,
    "ug/m2/d": 1.0e-9 / _SECONDS_PER_DAY,
    "ng/m2/d": 1.0e-12 / _SECONDS_PER_DAY,
    "mg/m2/yr": 1.0e-6 / _SECONDS_PER_YEAR,
    "ug/m2/yr": 1.0e-9 / _SECONDS_PER_YEAR,
}

# --- length: factor to m ---------------------------------------------------
# ``m`` used to sit among the unconverted context units, so a burial depth
# reported in centimetres would have passed every check as if it were metres.
LENGTH_UNITS: dict[str, float] = {
    "m": 1.0,
    "cm": 1.0e-2,
    "mm": 1.0e-3,
    "um": 1.0e-6,
    "km": 1.0e3,
}

# --- velocity: factor to m s^-1 --------------------------------------------
# Seepage and Darcy velocities are habitually reported in cm/yr or m/yr, which
# differ from m/s by nine orders of magnitude.
VELOCITY_UNITS: dict[str, float] = {
    "m/s": 1.0,
    "cm/s": 1.0e-2,
    "mm/s": 1.0e-3,
    "m/d": 1.0 / _SECONDS_PER_DAY,
    "cm/d": 1.0e-2 / _SECONDS_PER_DAY,
    "m/yr": 1.0 / _SECONDS_PER_YEAR,
    "cm/yr": 1.0e-2 / _SECONDS_PER_YEAR,
    "mm/yr": 1.0e-3 / _SECONDS_PER_YEAR,
}

# --- units that carry no conversion (context / QC channels) ----------------
DIMENSIONLESS_OR_CONTEXT_UNITS: frozenset[str] = frozenset(
    {
        "1",  # practical salinity, dimensionless ratios, coverage fractions
        "degC",
        "mS/cm",
        "NTU",
        "pH",
        "V",
        "mV",  # redox potential
        "Pa",  # differential pressure across the layer
        "deg",
        "m2",  # permeability
        "class",  # categorical condition classes
    }
)


def _lookup(unit: str, table: dict[str, float], ladder: str) -> float:
    try:
        return table[unit]
    except KeyError:
        raise UnitError(
            f"unit {unit!r} is not a supported {ladder} unit; "
            f"supported: {sorted(table)}. No unit is inferred automatically."
        ) from None


def to_si_aqueous_concentration(value: float, unit: str) -> float:
    """Aqueous concentration -> kg m^-3."""
    if unit in SOLID_LOADING_UNITS and unit not in AQUEOUS_CONCENTRATION_UNITS:
        raise UnitError(
            f"{unit!r} is a mass-fraction (solid) unit; it cannot be converted to an "
            "aqueous concentration. Use to_si_solid_loading and a separate "
            "mass-based interpretation."
        )
    return value * _lookup(unit, AQUEOUS_CONCENTRATION_UNITS, "aqueous concentration")


def from_si_aqueous_concentration(value_si: float, unit: str) -> float:
    """kg m^-3 -> requested display unit."""
    return value_si / _lookup(unit, AQUEOUS_CONCENTRATION_UNITS, "aqueous concentration")


def to_si_solid_loading(value: float, unit: str) -> float:
    """Solid / sorbent loading -> kg kg^-1."""
    if unit in AQUEOUS_CONCENTRATION_UNITS and unit not in SOLID_LOADING_UNITS:
        raise UnitError(
            f"{unit!r} is a volumetric (aqueous) unit; it cannot be read as a solid "
            "loading. Solid assays use ng/g or mg/kg."
        )
    return value * _lookup(unit, SOLID_LOADING_UNITS, "solid loading")


def from_si_solid_loading(value_si: float, unit: str) -> float:
    """kg kg^-1 -> requested display unit."""
    return value_si / _lookup(unit, SOLID_LOADING_UNITS, "solid loading")


def to_si_mass(value: float, unit: str) -> float:
    """Mass -> kg."""
    return value * _lookup(unit, MASS_UNITS, "mass")


def from_si_mass(value_si: float, unit: str) -> float:
    """kg -> requested display unit."""
    return value_si / _lookup(unit, MASS_UNITS, "mass")


def to_si_areal_flux(value: float, unit: str) -> float:
    """Areal contaminant flux -> kg m^-2 s^-1."""
    return value * _lookup(unit, AREAL_FLUX_UNITS, "areal flux")


def from_si_areal_flux(value_si: float, unit: str) -> float:
    """kg m^-2 s^-1 -> requested display unit."""
    return value_si / _lookup(unit, AREAL_FLUX_UNITS, "areal flux")


def to_si_length(value: float, unit: str) -> float:
    """Length -> m."""
    return value * _lookup(unit, LENGTH_UNITS, "length")


def from_si_length(value_si: float, unit: str) -> float:
    """m -> requested display unit."""
    return value_si / _lookup(unit, LENGTH_UNITS, "length")


def to_si_velocity(value: float, unit: str) -> float:
    """Velocity -> m s^-1."""
    return value * _lookup(unit, VELOCITY_UNITS, "velocity")


def from_si_velocity(value_si: float, unit: str) -> float:
    """m s^-1 -> requested display unit."""
    return value_si / _lookup(unit, VELOCITY_UNITS, "velocity")


def convert_scalar(value: float, from_unit: str, to_unit: str) -> float:
    """Convert within one ladder.  Cross-ladder conversion is an error."""
    for table, ladder in (
        (AQUEOUS_CONCENTRATION_UNITS, "aqueous concentration"),
        (SOLID_LOADING_UNITS, "solid loading"),
        (MASS_UNITS, "mass"),
        (AREAL_FLUX_UNITS, "areal flux"),
        (LENGTH_UNITS, "length"),
        (VELOCITY_UNITS, "velocity"),
    ):
        if from_unit in table and to_unit in table:
            return value * table[from_unit] / table[to_unit]
    raise UnitError(
        f"cannot convert {from_unit!r} -> {to_unit!r}: not on a common physical "
        "ladder (aqueous concentration / solid loading / mass / areal flux / "
        "length / velocity)."
    )


# --- time ------------------------------------------------------------------

def utc_now() -> datetime:
    """Timezone-aware current UTC time (used only for provenance stamps)."""
    return datetime.now(timezone.utc)


def parse_utc(text: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp ending in ``Z``.

    The contract requires an explicit ``Z``; a naive or offset timestamp is
    rejected rather than silently assumed to be UTC.
    """
    if not isinstance(text, str) or not text.endswith("Z"):
        raise UnitError(
            f"timestamp {text!r} must be ISO-8601 UTC ending in 'Z' "
            "(docs/DATA_CONTRACT.md section 1)"
        )
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def format_utc(moment: datetime) -> str:
    """Format a timezone-aware datetime as ``...Z``."""
    if moment.tzinfo is None:
        raise UnitError("refusing to format a naive datetime as UTC")
    moment = moment.astimezone(timezone.utc)
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")
