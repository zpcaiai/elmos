import json

import pytest
from conftest import PRICING_PATH, PROJECT_PATH, TASKS_PATH

from elmos_execution_intelligence.cli import main


def _small_profile(tmp_path):
    project = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    project["simulation"] = {"runs": 150, "seed": 5}
    path = tmp_path / "project.json"
    path.write_text(json.dumps(project), encoding="utf-8")
    return path


def test_validate_passes_on_the_shipped_elmos_profile():
    assert main(["validate", "--project", str(PROJECT_PATH), "--tasks", str(TASKS_PATH),
                 "--pricing", str(PRICING_PATH)]) == 0


def test_validate_returns_blocked_exit_code_on_bad_input(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"project_id": "x"}), encoding="utf-8")
    code = main(["validate", "--project", str(broken), "--tasks", str(TASKS_PATH), "--pricing", str(PRICING_PATH)])
    assert code == 3


def test_missing_file_returns_error_exit_code(tmp_path):
    assert main(["validate", "--project", str(tmp_path / "nope.json"), "--tasks", str(TASKS_PATH),
                 "--pricing", str(PRICING_PATH)]) == 2


def test_forecast_writes_every_declared_artifact(tmp_path):
    output = tmp_path / "out"
    code = main(["forecast", "--project", str(_small_profile(tmp_path)), "--tasks", str(TASKS_PATH),
                 "--pricing", str(PRICING_PATH), "--output", str(output)])
    assert code == 0
    for name in ("project-forecast.json", "TOKEN_BUDGET.md", "task-token-estimates.csv",
                 "SYSTEM_RUNTIME_ESTIMATE.md", "HUMAN_EFFORT_ESTIMATE.md", "SYSTEM_VS_HUMAN_COMPARISON.md"):
        assert (output / name).exists(), name
    forecast = json.loads((output / "project-forecast.json").read_text(encoding="utf-8"))
    assert forecast["tokens"]["total"]["p90"] >= forecast["tokens"]["total"]["p50"]
    expected_tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"]
    assert len(forecast["task_tokens"]) == len(expected_tasks)


def test_forecast_folds_in_a_static_scan(tmp_path):
    scan_output = tmp_path / "scan.json"
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.md").write_text("hello " * 500, encoding="utf-8")
    assert main(["scan-tokens", str(source), "--output", str(scan_output)]) == 0

    output = tmp_path / "out2"
    assert main(["forecast", "--project", str(_small_profile(tmp_path)), "--tasks", str(TASKS_PATH),
                 "--pricing", str(PRICING_PATH), "--static-scan", str(scan_output),
                 "--output", str(output)]) == 0
    budget = (output / "TOKEN_BUDGET.md").read_text(encoding="utf-8")
    assert "静态语料扫描" in budget


def test_calibrate_writes_the_full_calibration_bundle(tmp_path):
    history = tmp_path / "history.jsonl"
    history.write_text(json.dumps({
        "task_type": "t", "complexity": "c", "model": "m", "estimated_minutes": 10, "actual_minutes": 20,
        "estimated_total_tokens": 100, "actual_total_tokens": 300}) + "\n", encoding="utf-8")
    out = tmp_path / "cal"
    assert main(["calibrate", "--history", str(history), "--output", str(out)]) == 0
    for name in ("calibration.json", "estimator-profiles.json", "forecast-accuracy-report.md"):
        assert (out / name).exists(), name
    calibration = json.loads((out / "calibration.json").read_text(encoding="utf-8"))
    assert calibration["global"]["runtime_multiplier"]["p50"] == 2.0
    report = (out / "forecast-accuracy-report.md").read_text(encoding="utf-8")
    assert "低估" in report


def test_forecast_emits_every_declared_split_artifact(tmp_path):
    output = tmp_path / "out3"
    assert main(["forecast", "--project", str(_small_profile(tmp_path)), "--tasks", str(TASKS_PATH),
                 "--pricing", str(PRICING_PATH), "--output", str(output)]) == 0
    for name in ("token-forecast.json", "cost-forecast.json", "autonomous-runtime.json",
                 "human-effort.json", "time-comparison.json", "MODEL_COST_COMPARISON.md"):
        assert (output / name).exists(), name

    token = json.loads((output / "token-forecast.json").read_text(encoding="utf-8"))
    assert token["artifact"] == "token-forecast"
    assert token["totals"]["category_sum_equals_total"] is True

    runtime = json.loads((output / "autonomous-runtime.json").read_text(encoding="utf-8"))
    assert runtime["scope"] == "machine-autonomous execution only"
    assert runtime["excludes"]

    cost = json.loads((output / "cost-forecast.json").read_text(encoding="utf-8"))
    assert cost["cross_currency_comparison"] is None


def test_forecast_self_checks_artifacts_against_schemas(tmp_path):
    output = tmp_path / "out4"
    assert main(["forecast", "--project", str(_small_profile(tmp_path)), "--tasks", str(TASKS_PATH),
                 "--pricing", str(PRICING_PATH), "--output", str(output)]) == 0
    assert main(["validate-schemas", str(output)]) == 0


def test_validate_schemas_reports_a_corrupted_artifact(tmp_path):
    output = tmp_path / "out5"
    assert main(["forecast", "--project", str(_small_profile(tmp_path)), "--tasks", str(TASKS_PATH),
                 "--pricing", str(PRICING_PATH), "--output", str(output)]) == 0
    corrupted = json.loads((output / "token-forecast.json").read_text(encoding="utf-8"))
    del corrupted["totals"]
    (output / "token-forecast.json").write_text(json.dumps(corrupted), encoding="utf-8")
    assert main(["validate-schemas", str(output)]) == 3


def test_validate_schemas_blocks_on_an_empty_directory(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    assert main(["validate-schemas", str(empty)]) == 3


def test_apply_calibration_rewrites_durations_and_tokens(tmp_path):
    history = tmp_path / "history.jsonl"
    history.write_text("\n".join(json.dumps({
        "task_type": "verification", "complexity": "high", "model": "m",
        "estimated_minutes": 10, "actual_minutes": 20,
        "estimated_total_tokens": 100, "actual_total_tokens": 200}) for _ in range(6)) + "\n", encoding="utf-8")
    cal = tmp_path / "cal"
    assert main(["calibrate", "--history", str(history), "--output", str(cal)]) == 0

    out = tmp_path / "task-dag.calibrated.json"
    assert main(["apply-calibration", "--tasks", str(TASKS_PATH),
                 "--profiles", str(cal / "estimator-profiles.json"), "--output", str(out)]) == 0

    before = json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"]
    after = json.loads(out.read_text(encoding="utf-8"))
    assert after["calibrated"] is True
    for original, updated in zip(before, after["tasks"], strict=True):
        assert updated["system"]["most_likely_minutes"] == pytest.approx(
            original["system"]["most_likely_minutes"] * 2.0)
        assert updated["system"]["calibration"]["basis"] in {"global", "group"}
    # the source document must not be mutated in place
    assert json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"][0]["system"]["most_likely_minutes"] == \
        before[0]["system"]["most_likely_minutes"]


def test_calibrated_dag_still_validates_and_forecasts(tmp_path):
    history = tmp_path / "history.jsonl"
    history.write_text(json.dumps({
        "task_type": "t", "complexity": "c", "model": "m", "estimated_minutes": 10, "actual_minutes": 11,
        "estimated_total_tokens": 100, "actual_total_tokens": 110}) + "\n", encoding="utf-8")
    cal = tmp_path / "cal2"
    assert main(["calibrate", "--history", str(history), "--output", str(cal)]) == 0
    dag = tmp_path / "dag.json"
    assert main(["apply-calibration", "--tasks", str(TASKS_PATH),
                 "--profiles", str(cal / "estimator-profiles.json"), "--output", str(dag)]) == 0
    assert main(["forecast", "--project", str(_small_profile(tmp_path)), "--tasks", str(dag),
                 "--pricing", str(PRICING_PATH), "--output", str(tmp_path / "out6")]) == 0


def test_full_loop_from_scope_to_certification(tmp_path):
    """scope -> decompose -> forecast -> execute -> telemetry -> calibrate -> certify."""
    repo = tmp_path / "repo"
    (repo / "routes").mkdir(parents=True)
    langs = ["java", "python", "kotlin"]
    routes = [f"{a}-to-{b}" for a in langs for b in langs if a != b]
    (repo / "routes" / "inventory.json").write_text(json.dumps({
        "route_count": len(routes), "routes": routes,
        "languages": {name: ({"analyzer_status": "PENDING_ANALYZER"} if name == "kotlin" else {"version": "1"})
                      for name in langs},
        "route_sets": {},
    }), encoding="utf-8")
    for name in routes:
        (repo / "routes" / name).mkdir()
    (repo / "a.py").write_text("x = 1\n" * 20, encoding="utf-8")

    work = tmp_path / "work"
    assert main(["audit-scope", str(repo), "--output", str(work), "--project-id", "loop"]) == 0
    assert main(["decompose", "--scope", str(work / "scope-baseline.json"),
                 "--output", str(work), "--dag-id", "loop-dag"]) == 0

    profile = json.loads((work / "project-profile.seed.json").read_text(encoding="utf-8"))
    profile["simulation"] = {"runs": 150, "seed": 5}
    profile_path = work / "project.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    dag_path = work / "task-dag.json"

    assert main(["forecast", "--project", str(profile_path), "--tasks", str(dag_path),
                 "--pricing", str(PRICING_PATH), "--output", str(work)]) == 0
    assert main(["plan", "--project", str(profile_path), "--tasks", str(dag_path),
                 "--output", str(work)]) == 0
    assert main(["route", "--tasks", str(dag_path), "--pricing", str(PRICING_PATH),
                 "--output", str(work)]) == 0

    store = tmp_path / "run.db"
    assert main(["execute", "--project", str(profile_path), "--tasks", str(dag_path),
                 "--store", str(store), "--output", str(work), "--seed", "9"]) == 0
    run_id = json.loads((work / "run-summary.json").read_text(encoding="utf-8"))["run_id"]

    assert main(["events", "--store", str(store), "--run-id", run_id, "--after", "0", "--limit", "5"]) == 0
    assert main(["eta", "--store", str(store), "--run-id", run_id,
                 "--output", str(work / "recovery-eta-update.json")]) == 0
    telemetry = work / "telemetry.jsonl"
    assert main(["export-telemetry", "--store", str(store), "--run-id", run_id,
                 "--output", str(telemetry)]) == 0
    assert main(["calibrate", "--history", str(telemetry), "--output", str(work)]) == 0
    assert main(["apply-calibration", "--tasks", str(dag_path),
                 "--profiles", str(work / "estimator-profiles.json"),
                 "--output", str(work / "task-dag.calibrated.json")]) == 0
    assert main(["chaos", "--project", str(profile_path), "--output", str(work)]) == 0

    # Every emitted JSON artifact must satisfy its schema.
    assert main(["validate-schemas", str(work)]) == 0

    # Certification honestly refuses: the seeded profile's confidence is below the bar.
    assert main(["certify", "--evidence", str(work), "--min-calibration-samples", "1"]) == 1
    report = json.loads((work / "production-readiness.json").read_text(encoding="utf-8"))
    assert report["decision"] in {"block", "not_certified"}
    assert any(gate["id"] == "forecast-confidence" and gate["status"] == "FAIL"
               for gate in report["gates"])


def test_execute_produces_telemetry_calibrate_can_consume(tmp_path):
    store = tmp_path / "run.db"
    out = tmp_path / "out"
    assert main(["execute", "--project", str(_small_profile(tmp_path)), "--tasks", str(TASKS_PATH),
                 "--store", str(store), "--output", str(out), "--seed", "1"]) == 0
    rows = [json.loads(line) for line in (out / "telemetry.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len(json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"])
    assert main(["calibrate", "--history", str(out / "telemetry.jsonl"), "--output", str(out)]) == 0


def test_chaos_exit_code_reflects_partial_coverage(tmp_path):
    out = tmp_path / "chaos"
    assert main(["chaos", "--project", str(PROJECT_PATH), "--scenario", "orchestrator-restart",
                 "--output", str(out)]) == 1
    report = json.loads((out / "chaos-test-report.json").read_text(encoding="utf-8"))
    assert report["scenarios_not_run"]


def test_export_telemetry_blocks_on_an_empty_run(tmp_path):
    from elmos_execution_intelligence.durable import DurableStore

    store_path = tmp_path / "empty.db"
    store = DurableStore(str(store_path))
    run_id = store.create_run(json.loads(PROJECT_PATH.read_text(encoding="utf-8")),
                              json.loads(TASKS_PATH.read_text(encoding="utf-8")))
    store.close()
    assert main(["export-telemetry", "--store", str(store_path), "--run-id", run_id,
                 "--output", str(tmp_path / "t.jsonl")]) == 3


def test_calibrate_prints_no_data_instead_of_crashing_on_a_runtime_only_history(tmp_path, capsys):
    history = tmp_path / "runtime-only.jsonl"
    history.write_text(json.dumps({
        "task_type": "verification", "complexity": "high", "model": "m",
        "estimated_minutes": 10, "actual_minutes": 4}) + "\n", encoding="utf-8")
    out = tmp_path / "cal"
    assert main(["calibrate", "--history", str(history), "--output", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "no data (not inferred)" in printed
    calibration = json.loads((out / "calibration.json").read_text(encoding="utf-8"))
    assert calibration["global"]["token_multiplier"] is None


def test_ingest_telemetry_refuses_a_task_that_is_not_in_the_dag(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("1 failed, 83 passed in 4759.49s (1:19:19)\n", encoding="utf-8")
    assert main(["ingest-telemetry", "--tasks", str(TASKS_PATH), "--task-id", "no-such-task",
                 "--pytest-log", str(log), "--unit-count", "156",
                 "--output", str(tmp_path / "out")]) == 3


def test_ingest_telemetry_then_calibrate_runs_end_to_end(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("1 failed, 83 passed in 4759.49s (1:19:19)\n", encoding="utf-8")
    out = tmp_path / "real"
    assert main(["ingest-telemetry", "--tasks", str(TASKS_PATH), "--task-id", "matrix-small",
                 "--pytest-log", str(log), "--unit-count", "156",
                 "--caveat", "older suite", "--output", str(out)]) == 0
    assert main(["calibrate", "--history", str(out / "telemetry-real.jsonl"), "--output", str(out)]) == 0
    calibration = json.loads((out / "calibration.json").read_text(encoding="utf-8"))
    assert calibration["runtime_samples"] == 1
    assert calibration["token_samples"] == 0
    assert main(["validate-schemas", str(out)]) == 0
