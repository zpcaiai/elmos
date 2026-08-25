from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from elmos_spring_golden_route.canonical import parse_json_strict, validate_json_value
from elmos_spring_golden_route.cli import _strict_evidence, main
from elmos_spring_golden_route.errors import RequestValidationError

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


if __name__ == "__main__":
    unittest.main()
