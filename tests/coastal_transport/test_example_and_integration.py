"""The standalone example actually runs, and the known integration snags.

The second half of this module documents defects in coordinator-owned code that
this branch may not edit.  They are recorded as tests so the coordinator sees
them rather than reading about them in prose.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "coastal_transport" / "plume_demo.py"


def test_the_example_exists_where_the_handoff_says_it_does():
    assert EXAMPLE.is_file()


@pytest.mark.slow
def test_the_example_runs_offline_and_writes_both_outputs(tmp_path):
    """Runs the shipped example end to end in a subprocess.

    Short window on purpose: the point is that the whole path works without a
    map, a network or any hardware, not that a long window is affordable in a
    unit test.
    """
    result = subprocess.run(
        [sys.executable, str(EXAMPLE), "--hours", "0.5", "--dt-s", "900",
         "--out", str(tmp_path)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    assert "identical forcing arrays confirmed" in result.stdout
    assert "Nothing is subtracted from a" in result.stdout

    plot = tmp_path / "plume_demo.png"
    timeline = tmp_path / "plume_timeline.json"
    assert plot.is_file() and plot.stat().st_size > 10_000
    payload = json.loads(timeline.read_text(encoding="utf-8"))
    assert set(payload["cases"]) == {"fresh_mat", "saturated_mat", "no_mat"}
    assert payload["stub"]["LABELLED_STUB"]
    assert "does not itself generate currents" in payload["resolution_statement"]
    fresh = payload["cases"]["fresh_mat"]["ledger"]["Pb"]
    bare = payload["cases"]["no_mat"]["ledger"]["Pb"]
    assert fresh["released_from_sediment_kg"] < bare["released_from_sediment_kg"]
    for case in payload["cases"].values():
        for ledger in case["ledger"].values():
            assert abs(ledger["relative_imbalance"]) < 1e-9


# ---------------------------------------------------------------------------
# Regression: this branch found that results.ledger_to_dict still read the
# pre-refactor MassLedger field names and raised AttributeError on the frozen
# 0.2.0 contract.  It was reported in docs/handoffs/coastal_2d.md, fixed by the
# coordinator during integration, and the test now guards the fix.
# ---------------------------------------------------------------------------

def test_results_ledger_to_dict_matches_the_frozen_mass_ledger():
    from reactive_seabed_mat.contracts import MassLedger
    from reactive_seabed_mat.results import ledger_to_dict

    payload = ledger_to_dict(
        MassLedger(
            element="Pb",
            released_from_sediment_kg=1.0,
            retained_in_mat_kg=0.4,
            boundary_out_kg=0.6,
        )
    )
    assert payload["released_from_sediment_kg"] == 1.0
    assert payload["retained_in_mat_kg"] == 0.4
    assert payload["boundary_out_kg"] == 0.6
    # The pre-refactor names must be gone, not merely unused.
    for stale in ("emitted_kg", "in_active_mesh_kg", "in_retrieved_media_kg"):
        assert stale not in payload
