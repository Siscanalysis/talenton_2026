"""The operational path must not be able to reach the hidden simulated truth.

This is a static check over the source tree, so it keeps holding as the branches
land.  The behavioural counterpart (running the estimator with no truth data
present) lives in ``tests/feedback/``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "mesh_demo"

#: Packages that make operational recommendations.  They may read observations
#: and their own estimates, never ``truth/``.
OPERATIONAL_PACKAGES = ("feedback", "observations")

#: Modules allowed to name the truth store: the layout definition itself, and
#: the simulator that writes it.
ALLOWED_MODULES = {"results.py", "truth.py", "simulate.py", "run.py"}


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Ids of string constants that are docstrings, so prose is not flagged."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _operational_modules() -> list[Path]:
    modules: list[Path] = []
    for package in OPERATIONAL_PACKAGES:
        directory = SRC / package
        if directory.exists():
            modules.extend(
                path
                for path in directory.rglob("*.py")
                if path.name not in ALLOWED_MODULES
            )
    return modules


def test_there_is_something_to_check():
    assert SRC.exists()
    # observations/ always exists; feedback/ appears when its branch merges.
    assert _operational_modules(), "no operational modules found to check"


@pytest.mark.parametrize("module", _operational_modules(), ids=lambda p: p.name)
def test_operational_modules_never_name_the_truth_store(module: Path):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    docstrings = _docstring_nodes(tree)
    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            lowered = node.value.lower()
            if "truth" in lowered and not lowered.startswith("#"):
                offenders.append(f"line {node.lineno}: string {node.value!r}")
        if isinstance(node, ast.Attribute) and node.attr == "truth":
            offenders.append(f"line {node.lineno}: attribute access '.truth'")
        if isinstance(node, ast.ImportFrom) and node.module and "truth" in node.module:
            offenders.append(f"line {node.lineno}: import from {node.module!r}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "truth" in alias.name:
                    offenders.append(f"line {node.lineno}: import {alias.name!r}")

    assert not offenders, (
        f"{module.relative_to(SRC)} reaches for the hidden simulated truth: "
        + "; ".join(offenders)
    )


def test_run_paths_operational_view_excludes_truth(tmp_path):
    from mesh_demo.results import RunPaths

    paths = RunPaths.create(tmp_path, "run1")
    operational = paths.operational_paths()
    assert "truth" not in operational
    assert paths.truth.exists()
    assert all(
        paths.truth not in target.parents and target != paths.truth
        for target in operational.values()
    )
