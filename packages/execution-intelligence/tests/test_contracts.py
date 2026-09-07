"""The SQL schema and OpenAPI contract are shipped artifacts, so they get checked too."""
import re

import pytest
from conftest import ROOT

SQL = ROOT / "sql" / "001_execution_intelligence.sql"
OPENAPI = ROOT / "openapi" / "task-execution-api.yaml"

REQUIRED_TABLES = {
    "tenant", "run", "task", "task_attempt", "checkpoint", "run_event",
    "idempotency_key", "outbox", "artifact", "model_usage",
}


def _sql_text():
    return SQL.read_text(encoding="utf-8")


def test_every_durable_execution_table_exists():
    text = _sql_text()
    declared = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", text))
    assert REQUIRED_TABLES <= declared, REQUIRED_TABLES - declared


def test_event_sequence_is_allocated_under_the_run_row_lock():
    text = _sql_text()
    assert "append_run_event" in text
    # The UPDATE ... RETURNING on run is what makes the sequence gapless.
    assert re.search(r"UPDATE run\s+SET last_event_seq = last_event_seq \+ 1", text)
    assert "PRIMARY KEY (run_id, seq)" in text


def test_idempotency_stores_a_request_digest():
    text = _sql_text()
    assert "request_digest" in text
    assert "idempotency_key" in text


def test_artifacts_are_content_addressed_and_versioned():
    text = _sql_text()
    assert "UNIQUE (run_id, logical_name, sha256)" in text
    assert "UNIQUE (run_id, logical_name, version)" in text
    assert "char_length(sha256) = 64" in text


def test_model_usage_carries_every_declared_token_category():
    text = _sql_text()
    for column in ("input_tokens", "cached_input_tokens", "cache_write_tokens",
                   "output_tokens", "reasoning_tokens"):
        assert column in text, column


def test_calibration_input_view_exists():
    assert "CREATE OR REPLACE VIEW calibration_input" in _sql_text()


def test_sql_statements_are_balanced():
    text = _sql_text()
    assert text.count("BEGIN;") == 1
    assert text.count("COMMIT;") == 1
    # $$-quoted function bodies come in pairs
    assert text.count("$$") % 2 == 0


def test_openapi_parses_and_declares_the_reconnect_contract():
    yaml = pytest.importorskip("yaml")
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    assert spec["openapi"].startswith("3.1")

    events = spec["paths"]["/runs/{runId}/events"]["get"]
    header_names = [p.get("name") for p in events["parameters"]]
    assert "Last-Event-ID" in header_names
    assert "afterSeq" in header_names
    assert "text/event-stream" in events["responses"]["200"]["content"]

    event_schema = spec["components"]["schemas"]["RunEvent"]
    assert "seq" in event_schema["required"]
    assert event_schema["properties"]["seq"]["minimum"] == 1


def test_openapi_requires_an_idempotency_key_on_state_changing_calls():
    yaml = pytest.importorskip("yaml")
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    create = spec["paths"]["/runs"]["post"]
    refs = [p.get("$ref") for p in create["parameters"]]
    assert "#/components/parameters/IdempotencyKey" in refs
    assert spec["components"]["parameters"]["IdempotencyKey"]["required"] is True
    assert "409" in create["responses"]


def test_openapi_eta_never_folds_in_human_waits():
    yaml = pytest.importorskip("yaml")
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    eta = spec["components"]["schemas"]["EtaUpdate"]
    assert "excludes" in eta["required"]
    assert eta["properties"]["excludes"]["minItems"] == 1


def test_report_templates_expose_the_placeholders_the_renderers_fill():
    plan = (ROOT / "templates" / "TASK_EXECUTION_PLAN.md.tmpl").read_text(encoding="utf-8")
    for token in ("{{run_id}}", "{{wave_table}}", "{{critical_path}}", "{{recovery_table}}"):
        assert token in plan, token
    incident = (ROOT / "templates" / "INCIDENT_RECOVERY_REPORT.md.tmpl").read_text(encoding="utf-8")
    for token in ("{{scenario}}", "{{check_idempotency}}", "{{assertions}}", "{{failure_class}}"):
        assert token in incident, token


# ------------------------------------------------------------------ CI wiring ------

REPO_ROOT = ROOT.parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "execution-intelligence.yml"


def test_the_workflow_exists_and_is_scoped_to_this_package():
    if not (REPO_ROOT / ".github").is_dir():
        pytest.skip("not checked out inside the elmos repository")
    assert WORKFLOW.exists(), f"expected a workflow at {WORKFLOW}"

    yaml = pytest.importorskip("yaml")
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    assert spec["defaults"]["run"]["working-directory"] == "packages/execution-intelligence"
    # `on` is parsed as the boolean True by YAML 1.1; accept either spelling.
    triggers = spec.get("on", spec.get(True))
    for event in ("push", "pull_request"):
        paths = triggers[event]["paths"]
        assert any(p.startswith("packages/execution-intelligence") for p in paths), event


def test_the_workflow_runs_lint_types_and_tests():
    if not WORKFLOW.exists():
        pytest.skip("workflow not present in this checkout")
    yaml = pytest.importorskip("yaml")
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["check"]["steps"]
    joined = " ".join(str(step.get("run", "")) for step in steps)
    assert "ruff check" in joined
    assert "mypy --strict" in joined
    assert "pytest -q tests" in joined


def test_the_workflow_refuses_to_pass_on_skipped_postgres_cases():
    """A skipped conformance suite must not read as a green build."""
    if not WORKFLOW.exists():
        pytest.skip("workflow not present in this checkout")
    yaml = pytest.importorskip("yaml")
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = spec["jobs"]["check"]
    assert "postgres" in job["services"]
    joined = " ".join(str(step.get("run", "")) for step in job["steps"])
    assert "001_execution_intelligence.sql" in joined, "the DDL must be applied for real"
    assert "that is not a pass" in joined


def test_the_workflow_covers_the_interpreter_the_device_actually_runs():
    if not WORKFLOW.exists():
        pytest.skip("workflow not present in this checkout")
    yaml = pytest.importorskip("yaml")
    versions = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")
                              )["jobs"]["check"]["strategy"]["matrix"]["python-version"]
    assert "3.10" in versions, "the device VM runs 3.10; CI has to cover it"
