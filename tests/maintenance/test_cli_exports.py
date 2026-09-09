"""The published evidence files preserve the actual simulation and its bounds."""
import json
import math
from dataclasses import replace

from reactive_seabed_mat.cli import _mass_into_water_kg, _write_result
from reactive_seabed_mat.observations.records import read_jsonl
from reactive_seabed_mat.results import write_json, write_jsonl_dicts
from reactive_seabed_mat.scenarios.registry import build_scenario
from reactive_seabed_mat.scenarios.run import ScenarioResult, run_mat_timeline


def test_nonfinite_json_endpoints_keep_one_sided_meaning(tmp_path):
    def reject_constant(value):
        raise AssertionError(f"non-standard JSON constant: {value}")

    path = write_json(tmp_path / "bounds.json", {"source": (2.0, math.inf)})
    payload = json.loads(path.read_text(), parse_constant=reject_constant)
    assert payload["source"] == [2.0, None]
    assert payload["_nonfinite_values"] == [{"path": "/source/1", "meaning": "unbounded_above"}]
    rows = write_jsonl_dicts(tmp_path / "bounds.jsonl", [{"flux": (math.nan, math.inf)}])
    payload = json.loads(rows.read_text(), parse_constant=reject_constant)
    assert payload["_nonfinite_values"][0]["meaning"] == "undefined"
    assert payload["_nonfinite_values"][1]["meaning"] == "unbounded_above"


def test_cli_exports_replayable_evidence_and_whole_hotspot_emission(tmp_path):
    day = 86400.0
    base = build_scenario("undersized_mat")
    config = replace(base, run_id="export_regression", duration_s=3 * day,
        observations=replace(base.observations, porewater_sample_period_s=day,
                             chamber_deployment_period_s=day, lab_latency_s=6 * 3600.0),
        policy=replace(base.policy, kind="fixed", decision_period_s=day, fixed_interval_s=2 * day))
    mat = run_mat_timeline(config)
    result = ScenarioResult(config=config, timeline=mat.timeline, windows=[],
        final_tiles=mat.final_tiles, mat_ledger=mat.mat_ledger,
        hotspot_released_kg=mat.hotspot_released_kg,
        hotspot_into_water_kg=mat.hotspot_into_water_kg, maintenance=mat)
    paths = _write_result(result, tmp_path)
    records = list(read_jsonl(paths.observations / "records.jsonl"))
    assert len(records) == mat.n_observations
    assert {record.record_id for record in records} == {record.record_id for record in mat.observations}
    estimates = [json.loads(line) for line in (paths.estimates / "history.jsonl").read_text().splitlines()]
    recommendations = [json.loads(line) for line in (paths.actions / "recommendations.jsonl").read_text().splitlines()]
    services = [json.loads(line) for line in (paths.actions / "service_events.jsonl").read_text().splitlines()]
    assert len(estimates) == len(mat.estimate_history)
    assert len(recommendations) == len(mat.recommendations)
    assert len(services) == len(mat.service_events) == 1
    assert mat.mat_ledger["Pb"].retained_in_retrieved_media_kg > 0.0
    assert _mass_into_water_kg(result, "Pb") == mat.hotspot_into_water_kg["Pb"]
    assert _mass_into_water_kg(result, "Pb") > mat.mat_ledger["Pb"].boundary_out_kg
    manifest = json.loads(paths.manifest.read_text())
    assert "observations/records.jsonl" in manifest["data_hashes"]
    assert "actions/service_events.jsonl" in manifest["data_hashes"]
    assert manifest["all_checks_passed"]
