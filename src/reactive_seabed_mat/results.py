"""Run output layout, manifest and provenance.  Coordinator-owned.

Implements ``docs/DATA_CONTRACT.md`` section 5.  The layout keeps the three
states in separate directories, and the manifest records what was actually run,
including the checks that did **not** pass::

    results/<run_id>/
        manifest.json          engine, versions, hashes, assumptions, failed checks
        config.json            the exact RunConfig used
        truth/                 hidden simulated state (tests and the evaluation
                               toggle only; never the operational estimator)
        observations/          observation records as JSONL
        estimates/             estimate timeline
        actions/              recommendations and accepted action events
        ledger/                per-element mass ledger and material-state timeline
        comparison/            design comparison across policies
        report/                self-contained HTML and figures

``operational_paths`` deliberately omits ``truth/``: anything reachable by the
recommendation path uses it, so a truth read cannot happen by accident.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .config import RunConfig, config_hash, config_to_dict, save_run_config
from .contracts import CONTRACT_VERSION, MassLedger
from .units import format_utc, utc_now

__all__ = [
    "RunPaths",
    "CheckResult",
    "ManifestBuilder",
    "file_sha256",
    "write_json",
    "write_jsonl_dicts",
    "ledger_to_dict",
]

TRUTH_DIRNAME = "truth"


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    return target


def write_jsonl_dicts(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return target


def ledger_to_dict(ledger: MassLedger) -> dict[str, Any]:
    return {
        "element": ledger.element,
        "initial_water_kg": ledger.initial_water_kg,
        "released_from_sediment_kg": ledger.released_from_sediment_kg,
        "boundary_in_kg": ledger.boundary_in_kg,
        "in_water_kg": ledger.in_water_kg,
        "retained_in_mat_kg": ledger.retained_in_mat_kg,
        "retained_in_retrieved_media_kg": ledger.retained_in_retrieved_media_kg,
        "boundary_out_kg": ledger.boundary_out_kg,
        "numerical_correction_kg": ledger.numerical_correction_kg,
        "supplied_kg": ledger.supplied_kg,
        "accounted_kg": ledger.accounted_kg,
        "imbalance_kg": ledger.imbalance_kg,
        "relative_imbalance": ledger.relative_imbalance,
    }


@dataclass(frozen=True, slots=True)
class RunPaths:
    """Directory layout for one run."""

    root: Path

    @classmethod
    def create(cls, base: str | Path, run_id: str) -> "RunPaths":
        root = Path(base) / run_id
        paths = cls(root)
        for directory in (
            paths.truth,
            paths.observations,
            paths.estimates,
            paths.actions,
            paths.ledger,
            paths.comparison,
            paths.report,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return paths

    @property
    def truth(self) -> Path:
        return self.root / TRUTH_DIRNAME

    @property
    def observations(self) -> Path:
        return self.root / "observations"

    @property
    def estimates(self) -> Path:
        return self.root / "estimates"

    @property
    def actions(self) -> Path:
        return self.root / "actions"

    @property
    def ledger(self) -> Path:
        return self.root / "ledger"

    @property
    def comparison(self) -> Path:
        return self.root / "comparison"

    @property
    def report(self) -> Path:
        return self.root / "report"

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def config(self) -> Path:
        return self.root / "config.json"

    def operational_paths(self) -> dict[str, Path]:
        """Everything an operator-facing component may read.  No ``truth/``."""
        return {
            "observations": self.observations,
            "estimates": self.estimates,
            "actions": self.actions,
            "ledger": self.ledger,
            "comparison": self.comparison,
            "config": self.config,
            "manifest": self.manifest,
        }


@dataclass
class CheckResult:
    """One validation check and its real outcome, passed or not."""

    name: str
    passed: bool
    detail: str = ""
    value: float | None = None
    tolerance: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "value": self.value,
            "tolerance": self.tolerance,
        }


@dataclass
class ManifestBuilder:
    """Collects everything ``manifest.json`` must record.

    Unsuccessful checks are first-class content: ``all_checks_passed`` is a
    reported field, and a failing run still writes a manifest.
    """

    config: RunConfig
    engine: str
    repo_root: Path
    checks: list[CheckResult] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    data_hashes: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def add_check(
        self,
        name: str,
        passed: bool,
        detail: str = "",
        value: float | None = None,
        tolerance: float | None = None,
    ) -> CheckResult:
        result = CheckResult(name, passed, detail, value, tolerance)
        self.checks.append(result)
        return result

    def add_data_file(self, key: str, path: str | Path) -> None:
        self.data_hashes[key] = file_sha256(path)

    def _dependency_lock_hash(self) -> str | None:
        lock = self.repo_root / "requirements.lock.txt"
        return file_sha256(lock) if lock.exists() else None

    def _engine_versions(self) -> dict[str, str | None]:
        versions: dict[str, str | None] = {}
        for module_name in ("numpy", "scipy", "fipy", "jsonschema", "plotly", "streamlit"):
            try:
                module = __import__(module_name)
                versions[module_name] = getattr(module, "__version__", "unknown")
            except Exception:  # pragma: no cover - optional at runtime
                versions[module_name] = None
        return versions

    def build(self, run_paths: RunPaths) -> dict[str, Any]:
        failed = [check for check in self.checks if not check.passed]
        manifest = {
            "run_id": self.config.run_id,
            "scenario": self.config.scenario,
            "generated_at_utc": format_utc(utc_now()),
            "status": "conceptual research demonstrator, not field validated",
            "contract_version": CONTRACT_VERSION,
            "config_hash": config_hash(self.config),
            "seed": self.config.seed,
            "transport_engine": self.engine,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "dependency_versions": self._engine_versions(),
            "dependency_lock_sha256": self._dependency_lock_hash(),
            "data_hashes": self.data_hashes,
            "assumptions": self.assumptions,
            "checks": [check.to_dict() for check in self.checks],
            "failed_checks": [check.to_dict() for check in failed],
            "all_checks_passed": not failed,
            "state_separation": {
                "truth_dir": str(run_paths.truth.relative_to(run_paths.root)),
                "operational_dirs": sorted(run_paths.operational_paths()),
                "note": (
                    "The recommendation path never reads truth/. The evaluation "
                    "toggle in the app and the test harness may."
                ),
            },
            "limitations_ref": "docs/LIMITATIONS.md",
            "assumptions_ref": "docs/ASSUMPTIONS.md",
            "references_ref": "docs/REFERENCES.md",
        }
        manifest.update(self.extra)
        return manifest

    def write(self, run_paths: RunPaths) -> Path:
        save_run_config(self.config, run_paths.config)
        self.add_data_file("config.json", run_paths.config)
        payload = self.build(run_paths)
        payload["config"] = config_to_dict(self.config)
        return write_json(run_paths.manifest, payload)


def summarise_checks(checks: Sequence[CheckResult]) -> str:
    """Short human-readable summary, used by the CLI and the report."""
    failed = [check for check in checks if not check.passed]
    if not failed:
        return f"{len(checks)} checks, all passed"
    names = ", ".join(check.name for check in failed)
    return f"{len(checks)} checks, {len(failed)} FAILED: {names}"
