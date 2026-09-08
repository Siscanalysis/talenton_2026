"""Observation record I/O and validation.  Coordinator-owned.

Branch agents use these functions; they must not fork the schema.  Everything
here is deliberately strict: the point of the contract is that a censored, a
missing and a quantified result stay distinguishable all the way to the plot.
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
    Qualifier,
    QualityFlag,
)
from ..units import format_utc, parse_utc

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "contracts" / "observation.schema.json"
)

__all__ = [
    "ObservationValidationError",
    "SCHEMA_PATH",
    "load_schema",
    "record_from_dict",
    "record_to_dict",
    "validate_record_dict",
    "read_jsonl",
    "write_jsonl",
    "observations_available",
]


class ObservationValidationError(ValueError):
    """A record violates the shared observation contract."""


_SCHEMA_CACHE: dict[str, Any] = {}


def load_schema() -> Mapping[str, Any]:
    if "schema" not in _SCHEMA_CACHE:
        _SCHEMA_CACHE["schema"] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE["schema"]


# --- semantic checks that JSON Schema cannot express -----------------------

def _check_semantics(payload: Mapping[str, Any]) -> None:
    observed = parse_utc(payload["observed_at_utc"])
    available = parse_utc(payload["available_at_utc"])
    if available < observed:
        raise ObservationValidationError(
            f"{payload.get('record_id')}: available_at_utc precedes observed_at_utc; "
            "a result cannot be known before it was measured"
        )

    start = payload.get("sampling_start_utc")
    end = payload.get("sampling_end_utc")
    if (start is None) != (end is None):
        raise ObservationValidationError(
            f"{payload.get('record_id')}: sampling_start_utc and sampling_end_utc "
            "must both be present or both absent"
        )
    if start is not None and end is not None and parse_utc(end) < parse_utc(start):
        raise ObservationValidationError(
            f"{payload.get('record_id')}: sampling window ends before it starts"
        )

    qualifier = payload["qualifier"]
    if qualifier in ("below_lod", "below_loq"):
        lower, upper = payload.get("lower_bound"), payload.get("upper_bound")
        if lower is None or upper is None:
            raise ObservationValidationError(
                f"{payload.get('record_id')}: a non-detect needs a finite censoring "
                "interval; it is a bound, not a zero measurement"
            )
        if upper < lower:
            raise ObservationValidationError(
                f"{payload.get('record_id')}: censoring interval is inverted"
            )
    if qualifier == "missing":
        if payload.get("value") is not None:
            raise ObservationValidationError(
                f"{payload.get('record_id')}: a missing result carries no value"
            )
        if payload.get("quality_flag") != 9:
            raise ObservationValidationError(
                f"{payload.get('record_id')}: a missing result must carry quality_flag 9"
            )
    if qualifier == "quantified" and payload.get("value") is None:
        raise ObservationValidationError(
            f"{payload.get('record_id')}: quantified result without a value"
        )

    if payload["acquisition_kind"] == "passive_sampler" and (
        start is None or end is None
    ):
        raise ObservationValidationError(
            f"{payload.get('record_id')}: an integrated passive-sampler exposure needs "
            "sampling_start_utc and sampling_end_utc; it is not a point reading"
        )

    unc = payload.get("uncertainty_std")
    if unc is not None and unc < 0:
        raise ObservationValidationError(
            f"{payload.get('record_id')}: negative uncertainty_std"
        )


def validate_record_dict(payload: Mapping[str, Any]) -> None:
    """Validate one record against the JSON schema plus the semantic rules.

    ``jsonschema`` is used when installed; the semantic checks always run, so
    the essential contract rules hold even in a minimal environment.
    """
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
    else:
        required = load_schema()["required"]
        missing = [key for key in required if key not in payload]
        if missing:
            raise ObservationValidationError(
                f"{payload.get('record_id')}: missing required fields {missing}"
            )
    _check_semantics(payload)


_OPTIONAL_STRINGS = (
    "sensor_id",
    "sample_id",
    "media_id",
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
)


def record_from_dict(payload: Mapping[str, Any], *, validate: bool = True) -> ObservationRecord:
    """Build a typed record.  Raises rather than repairing a bad record."""
    if validate:
        validate_record_dict(payload)
    kwargs: dict[str, Any] = {
        "record_id": payload["record_id"],
        "station_id": payload["station_id"],
        "observed_at_utc": parse_utc(payload["observed_at_utc"]),
        "available_at_utc": parse_utc(payload["available_at_utc"]),
        "parameter": Parameter(payload["parameter"]),
        "unit": payload["unit"],
        "matrix": Matrix(payload["matrix"]),
        "fraction": Fraction(payload["fraction"]),
        "acquisition_kind": AcquisitionKind(payload["acquisition_kind"]),
        "qualifier": Qualifier(payload["qualifier"]),
        "quality_flag": QualityFlag(int(payload["quality_flag"])),
        "method_id": payload["method_id"],
        "data_origin": DataOrigin(payload["data_origin"]),
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
    return ObservationRecord(**kwargs)


def record_to_dict(record: ObservationRecord) -> dict[str, Any]:
    """Serialise a record in exactly the contract's field order."""
    payload = asdict(record)
    payload.pop("raw", None)
    for key in ("observed_at_utc", "available_at_utc", "sampling_start_utc", "sampling_end_utc"):
        moment = payload.get(key)
        payload[key] = None if moment is None else format_utc(moment)
    for key in (
        "parameter",
        "matrix",
        "fraction",
        "acquisition_kind",
        "qualifier",
        "data_origin",
    ):
        payload[key] = payload[key].value if hasattr(payload[key], "value") else payload[key]
    payload["quality_flag"] = int(payload["quality_flag"])
    ordered_keys = [
        "record_id", "station_id", "sensor_id", "sample_id", "media_id",
        "observed_at_utc", "available_at_utc", "sampling_start_utc", "sampling_end_utc",
        "parameter", "unit", "matrix", "fraction", "acquisition_kind",
        "value", "uncertainty_std", "qualifier", "lower_bound", "upper_bound",
        "quality_flag", "method_id", "calibration_id", "data_origin", "source_ref",
        "x_m", "y_m", "depth_m", "crs",
    ]
    return {key: payload[key] for key in ordered_keys}


def read_jsonl(path: str | Path, *, validate: bool = True) -> list[ObservationRecord]:
    """Read a JSONL observation file, preserving original IDs and flags."""
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
            except ObservationValidationError as exc:
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
    """The timestamp gate of ``contracts/DATA_CONTRACT.md`` section 2.

    Only records whose ``available_at_utc`` is at or before the decision time
    may influence a decision.  Original IDs, flags and fractions are preserved
    verbatim: this function filters, it never rewrites.
    """
    if decision_time_utc.tzinfo is None:
        raise ValueError("decision_time_utc must be timezone-aware UTC")
    return [
        record for record in records if record.available_at_utc <= decision_time_utc
    ]


def iter_jsonl_dicts(path: str | Path) -> Iterator[dict[str, Any]]:
    """Raw dictionary access, for provenance inspection and error reporting."""
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("//"):
                yield json.loads(line)
