"""Observation record I/O and validation.  Coordinator-owned.

Branch agents use these functions; they must not fork the schema.  Everything
here is deliberately strict: the point of the contract is that a censored, a
missing, a categorical and a quantified result stay distinguishable all the way
to the plot.

The validator does not depend on ``jsonschema`` being installed.  When it is
absent the same rules are enforced in Python, including enum membership and the
conditional rules, so the guarantee does not quietly weaken in a minimal
environment.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from ..contracts import (
    AcquisitionKind,
    DataOrigin,
    Fraction,
    Matrix,
    ObservationRecord,
    Parameter,
    ProvenanceLabel,
    Qualifier,
    QualityFlag,
    QuantityKind,
    VerticalDatum,
)
from ..units import (
    AQUEOUS_CONCENTRATION_UNITS,
    AREAL_FLUX_UNITS,
    DIMENSIONLESS_OR_CONTEXT_UNITS,
    LENGTH_UNITS,
    MASS_UNITS,
    SOLID_LOADING_UNITS,
    VELOCITY_UNITS,
    UnitError,
    format_utc,
    parse_utc,
)

#: Packaged inside the distribution, so ``load_schema`` works from an installed
#: wheel and not only from a source checkout.
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "schemas" / "observation.schema.json"
)

__all__ = [
    "ObservationValidationError",
    "SCHEMA_PATH",
    "UNITS_FOR_QUANTITY_KIND",
    "load_schema",
    "record_from_dict",
    "record_to_dict",
    "validate_record_dict",
    "read_jsonl",
    "write_jsonl",
    "iter_jsonl_dicts",
    "observations_available",
]


class ObservationValidationError(ValueError):
    """A record violates the shared observation contract."""


_SCHEMA_CACHE: dict[str, Any] = {}


def load_schema() -> Mapping[str, Any]:
    if "schema" not in _SCHEMA_CACHE:
        _SCHEMA_CACHE["schema"] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE["schema"]


#: Which unit ladder each declared quantity kind is allowed to use.  This is the
#: check that stops a burial depth in centimetres being read as metres, and a
#: flux in ug/m2/d being read as kg/m2/s.
UNITS_FOR_QUANTITY_KIND: dict[QuantityKind, frozenset[str]] = {
    QuantityKind.AQUEOUS_CONCENTRATION: frozenset(AQUEOUS_CONCENTRATION_UNITS),
    QuantityKind.SOLID_LOADING: frozenset(SOLID_LOADING_UNITS),
    QuantityKind.ACCUMULATED_MASS: frozenset(MASS_UNITS),
    QuantityKind.AREAL_FLUX: frozenset(AREAL_FLUX_UNITS),
    QuantityKind.LENGTH: frozenset(LENGTH_UNITS),
    QuantityKind.VELOCITY: frozenset(VELOCITY_UNITS),
    QuantityKind.FRACTION: frozenset({"1"}),
    QuantityKind.CATEGORICAL: frozenset({"class"}),
    QuantityKind.CONTEXT: DIMENSIONLESS_OR_CONTEXT_UNITS,
}

_ENUM_FIELDS: tuple[tuple[str, type], ...] = (
    ("parameter", Parameter),
    ("quantity_kind", QuantityKind),
    ("matrix", Matrix),
    ("fraction", Fraction),
    ("acquisition_kind", AcquisitionKind),
    ("qualifier", Qualifier),
    ("data_origin", DataOrigin),
    ("provenance", ProvenanceLabel),
)


def _check_enums(payload: Mapping[str, Any]) -> None:
    record_id = payload.get("record_id")
    for key, enum_type in _ENUM_FIELDS:
        raw = payload.get(key)
        try:
            enum_type(raw)
        except ValueError:
            allowed = sorted(member.value for member in enum_type)
            raise ObservationValidationError(
                f"{record_id}: {key}={raw!r} is not one of {allowed}"
            ) from None
    flag = payload.get("quality_flag")
    if not isinstance(flag, int) or isinstance(flag, bool):
        raise ObservationValidationError(
            f"{record_id}: quality_flag must be an integer, got {flag!r}"
        )
    try:
        QualityFlag(flag)
    except ValueError:
        raise ObservationValidationError(
            f"{record_id}: quality_flag={flag!r} is not one of "
            f"{sorted(int(member) for member in QualityFlag)}"
        ) from None
    datum = payload.get("vertical_datum")
    if datum is not None:
        try:
            VerticalDatum(datum)
        except ValueError:
            raise ObservationValidationError(
                f"{record_id}: vertical_datum={datum!r} is not one of "
                f"{sorted(member.value for member in VerticalDatum)}"
            ) from None


def _check_semantics(payload: Mapping[str, Any]) -> None:
    record_id = payload.get("record_id")

    observed = parse_utc(payload["observed_at_utc"])
    available = parse_utc(payload["available_at_utc"])
    if available < observed:
        raise ObservationValidationError(
            f"{record_id}: available_at_utc precedes observed_at_utc; "
            "a result cannot be known before it was measured"
        )

    start = payload.get("sampling_start_utc")
    end = payload.get("sampling_end_utc")
    if (start is None) != (end is None):
        raise ObservationValidationError(
            f"{record_id}: sampling_start_utc and sampling_end_utc must both be "
            "present or both absent"
        )
    if start is not None and end is not None and parse_utc(end) < parse_utc(start):
        raise ObservationValidationError(
            f"{record_id}: sampling window ends before it starts"
        )

    qualifier = payload["qualifier"]
    value = payload.get("value")
    lower, upper = payload.get("lower_bound"), payload.get("upper_bound")

    if qualifier == "quantified":
        if value is None:
            raise ObservationValidationError(
                f"{record_id}: quantified result without a value"
            )
        if lower is not None or upper is not None:
            raise ObservationValidationError(
                f"{record_id}: a quantified result carries no censoring interval"
            )
    elif qualifier in ("below_lod", "below_loq"):
        if value is not None:
            raise ObservationValidationError(
                f"{record_id}: a non-detect carries no exact value; it is a bound"
            )
        if lower is None or upper is None:
            raise ObservationValidationError(
                f"{record_id}: a non-detect needs a finite censoring interval; "
                "it is a bound, not a zero measurement"
            )
        if upper < lower:
            raise ObservationValidationError(
                f"{record_id}: censoring interval is inverted"
            )
    elif qualifier == "above_range":
        if value is not None or lower is None or upper is not None:
            raise ObservationValidationError(
                f"{record_id}: an above-range result carries a lower bound only"
            )
    elif qualifier == "categorical":
        if value is not None:
            raise ObservationValidationError(
                f"{record_id}: a categorical result carries a class, not a value"
            )
        if not payload.get("condition_class"):
            raise ObservationValidationError(
                f"{record_id}: a categorical result needs a condition_class"
            )
        if payload.get("quantity_kind") != QuantityKind.CATEGORICAL.value:
            raise ObservationValidationError(
                f"{record_id}: a categorical result needs quantity_kind "
                f"{QuantityKind.CATEGORICAL.value!r}"
            )
    elif qualifier == "missing":
        if value is not None:
            raise ObservationValidationError(
                f"{record_id}: a missing result carries no value"
            )
        if lower is not None or upper is not None:
            raise ObservationValidationError(
                f"{record_id}: a missing result is not a non-detect and carries "
                "no interval"
            )
        if int(payload.get("quality_flag", -1)) != int(QualityFlag.MISSING):
            raise ObservationValidationError(
                f"{record_id}: a missing result must carry quality_flag "
                f"{int(QualityFlag.MISSING)}"
            )

    acquisition = payload["acquisition_kind"]
    if acquisition == AcquisitionKind.PASSIVE_SAMPLER.value and (
        start is None or end is None
    ):
        raise ObservationValidationError(
            f"{record_id}: an integrated passive-sampler exposure needs "
            "sampling_start_utc and sampling_end_utc; it is not a point reading"
        )
    if acquisition == AcquisitionKind.BENTHIC_CHAMBER.value:
        if start is None or end is None:
            raise ObservationValidationError(
                f"{record_id}: a benthic-chamber flux needs a deployment window"
            )
        area = payload.get("chamber_area_m2")
        if area is None or area <= 0:
            raise ObservationValidationError(
                f"{record_id}: a benthic-chamber flux needs a positive "
                "chamber_area_m2 to be interpretable"
            )

    kind = QuantityKind(payload["quantity_kind"])
    allowed_units = UNITS_FOR_QUANTITY_KIND[kind]
    if payload["unit"] not in allowed_units:
        raise ObservationValidationError(
            f"{record_id}: unit {payload['unit']!r} is not valid for "
            f"quantity_kind {kind.value!r}; allowed: {sorted(allowed_units)}"
        )

    if payload.get("depth_m") is not None and payload.get("vertical_datum") is None:
        raise ObservationValidationError(
            f"{record_id}: depth_m without a vertical_datum is ambiguous; "
            "declare sea_surface, seabed, mat_top or mat_base"
        )

    z_in_mat = payload.get("z_in_mat_m")
    if z_in_mat is not None and z_in_mat < 0:
        raise ObservationValidationError(
            f"{record_id}: z_in_mat_m must be a positive depth into the layer"
        )

    unc = payload.get("uncertainty_std")
    if unc is not None and unc < 0:
        raise ObservationValidationError(
            f"{record_id}: negative uncertainty_std"
        )


def validate_record_dict(payload: Mapping[str, Any]) -> None:
    """Validate one record against the JSON schema plus the semantic rules.

    ``jsonschema`` is used when installed.  The enum and semantic checks always
    run, so the essential contract rules hold in a minimal environment too.
    """
    required = load_schema()["required"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise ObservationValidationError(
            f"{payload.get('record_id')}: missing required fields {missing}"
        )

    try:
        import jsonschema  # type: ignore
    except ModuleNotFoundError:  # pragma: no cover - environment dependent
        jsonschema = None  # type: ignore

    if jsonschema is not None:
        try:
            jsonschema.validate(instance=dict(payload), schema=load_schema())
        except jsonschema.ValidationError as exc:  # type: ignore[attr-defined]
            raise ObservationValidationError(
                f"{payload.get('record_id')}: schema violation: {exc.message}"
            ) from exc

    _check_enums(payload)
    _check_semantics(payload)


_OPTIONAL_STRINGS = (
    "sensor_id",
    "sample_id",
    "media_id",
    "tile_id",
    "condition_class",
    "calibration_id",
    "source_ref",
    "crs",
)
_OPTIONAL_FLOATS = (
    "value",
    "uncertainty_std",
    "lower_bound",
    "upper_bound",
    "x_m",
    "y_m",
    "depth_m",
    "z_in_mat_m",
    "chamber_area_m2",
)

#: Serialisation order, matching ``docs/DATA_CONTRACT.md`` section 1.
ORDERED_KEYS = (
    "record_id", "station_id", "sensor_id", "sample_id", "media_id", "tile_id",
    "observed_at_utc", "available_at_utc", "sampling_start_utc", "sampling_end_utc",
    "parameter", "quantity_kind", "unit", "matrix", "fraction", "acquisition_kind",
    "value", "uncertainty_std", "qualifier", "lower_bound", "upper_bound",
    "condition_class", "quality_flag", "method_id", "calibration_id",
    "data_origin", "provenance", "source_ref",
    "x_m", "y_m", "depth_m", "vertical_datum", "z_in_mat_m", "chamber_area_m2",
    "crs",
)


def record_from_dict(payload: Mapping[str, Any], *, validate: bool = True) -> ObservationRecord:
    """Build a typed record.  Raises rather than repairing a bad record."""
    if validate:
        validate_record_dict(payload)
    try:
        kwargs: dict[str, Any] = {
            "record_id": payload["record_id"],
            "station_id": payload["station_id"],
            "observed_at_utc": parse_utc(payload["observed_at_utc"]),
            "available_at_utc": parse_utc(payload["available_at_utc"]),
            "parameter": Parameter(payload["parameter"]),
            "quantity_kind": QuantityKind(payload["quantity_kind"]),
            "unit": payload["unit"],
            "matrix": Matrix(payload["matrix"]),
            "fraction": Fraction(payload["fraction"]),
            "acquisition_kind": AcquisitionKind(payload["acquisition_kind"]),
            "qualifier": Qualifier(payload["qualifier"]),
            "quality_flag": QualityFlag(int(payload["quality_flag"])),
            "method_id": payload["method_id"],
            "data_origin": DataOrigin(payload["data_origin"]),
            "provenance": ProvenanceLabel(payload["provenance"]),
            "raw": dict(payload),
        }
        for key in _OPTIONAL_STRINGS:
            kwargs[key] = payload.get(key)
        for key in _OPTIONAL_FLOATS:
            raw_value = payload.get(key)
            kwargs[key] = None if raw_value is None else float(raw_value)
        for key in ("sampling_start_utc", "sampling_end_utc"):
            raw_value = payload.get(key)
            kwargs[key] = None if raw_value is None else parse_utc(raw_value)
        datum = payload.get("vertical_datum")
        kwargs["vertical_datum"] = None if datum is None else VerticalDatum(datum)
    except (ValueError, KeyError, TypeError, UnitError) as exc:
        if isinstance(exc, ObservationValidationError):
            raise
        raise ObservationValidationError(
            f"{payload.get('record_id')}: cannot build record: {exc}"
        ) from exc
    return ObservationRecord(**kwargs)


def record_to_dict(record: ObservationRecord) -> dict[str, Any]:
    """Serialise a record in exactly the contract's field order.

    ``raw`` is deliberately not serialised: the schema sets
    ``additionalProperties: false``, so a round trip could not carry it.  A
    reported value behind a non-detect belongs in ``source_ref`` or in the
    laboratory's own file, not in a field that silently disappears on write.
    """
    payload = asdict(record)
    payload.pop("raw", None)
    for key in (
        "observed_at_utc",
        "available_at_utc",
        "sampling_start_utc",
        "sampling_end_utc",
    ):
        moment = payload.get(key)
        payload[key] = None if moment is None else format_utc(moment)
    for key in (
        "parameter",
        "quantity_kind",
        "matrix",
        "fraction",
        "acquisition_kind",
        "qualifier",
        "data_origin",
        "provenance",
        "vertical_datum",
    ):
        member = payload.get(key)
        payload[key] = member.value if hasattr(member, "value") else member
    payload["quality_flag"] = int(payload["quality_flag"])
    return {key: payload[key] for key in ORDERED_KEYS}


def read_jsonl(path: str | Path, *, validate: bool = True) -> list[ObservationRecord]:
    """Read a JSONL observation file, preserving original IDs and flags.

    Every failure is reported with its file and line, including the ones raised
    by an enum constructor or by timestamp parsing rather than by the schema.
    """
    records: list[ObservationRecord] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ObservationValidationError(
                    f"{path}:{line_number}: not valid JSON: {exc}"
                ) from exc
            try:
                records.append(record_from_dict(payload, validate=validate))
            except (ObservationValidationError, ValueError, UnitError) as exc:
                raise ObservationValidationError(f"{path}:{line_number}: {exc}") from exc
    return records


def write_jsonl(path: str | Path, records: Iterable[ObservationRecord]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record_to_dict(record), ensure_ascii=False) + "\n")
    return target


def observations_available(
    records: Sequence[ObservationRecord], decision_time_utc: datetime
) -> list[ObservationRecord]:
    """The timestamp gate of ``docs/DATA_CONTRACT.md`` section 2.

    Only records whose ``available_at_utc`` is at or before the decision time
    may influence a decision.  Original IDs, flags and fractions are preserved
    verbatim: this function filters, it never rewrites.
    """
    if decision_time_utc.tzinfo is None:
        raise ValueError("decision_time_utc must be timezone-aware UTC")
    return [record for record in records if record.available_at_utc <= decision_time_utc]


def iter_jsonl_dicts(path: str | Path) -> Iterator[dict[str, Any]]:
    """Raw dictionary access, for provenance inspection and error reporting."""
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("//"):
                yield json.loads(line)
