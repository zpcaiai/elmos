from __future__ import annotations

import contextlib
import copy
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from elmos_spring_golden_route.canonical import (
    canonical_json,
    parse_json_strict,
    sha256_digest,
    validate_json_value,
)
from elmos_spring_golden_route.catalog import load_catalog
from elmos_spring_golden_route.cli import _read, _strict_evidence, main
from elmos_spring_golden_route.errors import RequestValidationError
from elmos_spring_golden_route.runtime import build_registry, validate_request
from elmos_spring_golden_route.state import RunStore

from common import REPOSITORY_ROOT, request_for


class CanonicalAndCliTests(unittest.TestCase):
    def test_depth_item_nonfinite_float_and_unsupported_bounds(self) -> None:
        nested: object = "leaf"
        for _ in range(14):
            nested = [nested]
        with self.assertRaises(RequestValidationError):
            validate_json_value(nested)
        with self.assertRaises(RequestValidationError):
            validate_json_value([0] * 2_049)
        with self.assertRaises(RequestValidationError):
            parse_json_strict('{"value":NaN}')
        with self.assertRaises(RequestValidationError):
            parse_json_strict('{"value":1.5}')
        with self.assertRaises(RequestValidationError):
            validate_json_value({"unsupported": {1, 2}})

    def test_duplicate_keys_and_lone_surrogates_fail_typed(self) -> None:
        with self.assertRaises(RequestValidationError):
            parse_json_strict('{"key":1,"key":2}')
        with self.assertRaises(RequestValidationError):
            parse_json_strict('"\\ud800"')
        with self.assertRaises(RequestValidationError):
            parse_json_strict('{"\\ud800":1}')

    def test_forbidden_cli_operation_emits_structured_error_without_traceback(self) -> None:
        request = request_for("lossless-semantic-ir", operation="execute")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "request.json"
            path.write_text(json.dumps(request), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(
                    [
                        "invoke",
                        "--repo-root",
                        str(REPOSITORY_ROOT),
                        "--request",
                        str(path),
                    ]
                )
        self.assertEqual(result, 2)
        response = json.loads(output.getvalue())
        self.assertEqual(response["decision"], "BLOCKED")
        self.assertEqual(response["error"], "EXTERNAL_ADAPTER_REQUIRED")
        self.assertEqual(response["certification"], "NOT_CERTIFIED")
        self.assertNotIn("Traceback", output.getvalue())

    def test_non_create_cli_does_not_create_missing_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "missing.sqlite3"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(
                    [
                        "get-run",
                        "--database",
                        str(database),
                        "--tenant",
                        "tenant-a",
                        "--project",
                        "project-a",
                        "--run",
                        "run-a",
                    ]
                )
            self.assertEqual(result, 2)
            self.assertFalse(database.exists())
            self.assertEqual(json.loads(output.getvalue())["error"], "RUN_NOT_FOUND")

    def test_non_create_cli_loads_registry_and_rejects_coherently_rehashed_plan(self) -> None:
        registry = build_registry(load_catalog(REPOSITORY_ROOT))
        request = validate_request(request_for("lossless-semantic-ir"))
        plan = registry.dispatch(request)
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "runs.sqlite3"
            RunStore(database, registry=registry).create_run(request, plan)
            tampered_plan = copy.deepcopy(plan)
            tampered_plan["objective"] = "Coherently rehashed forged objective"
            plan_json = canonical_json(tampered_plan)
            plan_sha256 = sha256_digest(plan_json.encode("utf-8"))
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.row_factory = sqlite3.Row
                connection.execute(
                    "UPDATE runs SET plan_json = ?, plan_sha256 = ?",
                    (plan_json, plan_sha256),
                )
                trigger_sql = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'run_events_no_update'"
                ).fetchone()[0]
                connection.execute("DROP TRIGGER run_events_no_update")
                row = connection.execute("SELECT * FROM run_events").fetchone()
                payload = json.loads(str(row["payload_json"]))
                payload["plan_sha256"] = plan_sha256
                body = RunStore._event_body(
                    tenant_id=row["tenant_id"], project_id=row["project_id"], run_id=row["run_id"],
                    event_type=row["event_type"], actor_id=row["actor_id"],
                    from_state=row["from_state"], to_state=row["to_state"],
                    run_version=row["run_version"], occurred_at=row["occurred_at"],
                    previous_sha256=row["previous_sha256"], payload=payload,
                )
                connection.execute(
                    "UPDATE run_events SET payload_json = ?, event_sha256 = ?",
                    (
                        canonical_json(payload),
                        sha256_digest(canonical_json(body).encode("utf-8")),
                    ),
                )
                connection.execute(str(trigger_sql))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(
                    [
                        "get-run",
                        "--repo-root",
                        str(REPOSITORY_ROOT),
                        "--database",
                        str(database),
                        "--tenant",
                        "tenant-a",
                        "--project",
                        "project-a",
                        "--run",
                        "run-a",
                    ]
                )
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output.getvalue())["error"], "STATE_CONFLICT")

    def test_evidence_identifiers_are_not_coerced_from_numbers(self) -> None:
        evidence = {
            "evidence_id": 123,
            "role": "request",
            "payload": {"value": "bounded"},
            "executor_id": "executor-a",
            "verifier_id": "verifier-a",
            "authorization_id": "auth-a",
        }
        with self.assertRaises(RequestValidationError):
            _strict_evidence(json.dumps(evidence).encode("utf-8"))

    def test_cli_file_is_rejected_before_unbounded_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            oversized = Path(temporary) / "oversized.json"
            oversized.write_bytes(b" " * 65_537)
            with self.assertRaises(RequestValidationError):
                _read(str(oversized))


if __name__ == "__main__":
    unittest.main()
