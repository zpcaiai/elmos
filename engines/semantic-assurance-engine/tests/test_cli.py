"""CLI interface unit tests."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from elmos_semantic_assurance.cli import main
from elmos_semantic_assurance.canonical import canonical_json, digest_value

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from fixtures import make_identity, make_request_document, make_scope, sha


class TestCli(unittest.TestCase):
    def test_status_command(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["status"])
        self.assertEqual(exit_code, 0)
        output = json.loads(stdout.getvalue())
        self.assertEqual(output["registeredSkills"], 132)
        self.assertEqual(output["exactHandlers"], 132)
        self.assertEqual(output["certificationStatus"], "NOT_CERTIFIED")
        self.assertEqual(output["externalEvidenceStatus"], "NOT_RUN")

    def test_catalog_command(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["catalog"])
        self.assertEqual(exit_code, 0)
        output = json.loads(stdout.getvalue())
        self.assertEqual(len(output), 132)

    def test_catalog_command_with_batch(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["catalog", "--batch", "J"])
        self.assertEqual(exit_code, 0)
        output = json.loads(stdout.getvalue())
        self.assertGreater(len(output), 0)
        self.assertTrue(all(item["batch"] == "J" for item in output))

    def test_campaign_plan_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir).resolve()
            src_file = tmp_path / "source.java"
            tgt_file = tmp_path / "target.cs"
            src_file.write_bytes(b"public class Main {}")
            tgt_file.write_bytes(b"public class Program {}")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "campaign-plan",
                    "--source-technology", "java",
                    "--target-technology", "csharp",
                    "--source", str(src_file),
                    "--target", str(tgt_file),
                    "--route-id", "java-to-csharp-test",
                ])
            self.assertEqual(exit_code, 0)
            output = json.loads(stdout.getvalue())
            self.assertEqual(output["routeId"], "java-to-csharp-test")
            self.assertEqual(output["executionStatus"], "NOT_RUN")
            self.assertEqual(output["certificationStatus"], "NOT_CERTIFIED")
            self.assertEqual(len(output["batchPlan"]), 9)

    def test_invoke_command_requires_adapter_returns_code_3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir).resolve()
            state_db = tmp_path / "state.db"
            req_file = tmp_path / "request.json"
            ident_file = tmp_path / "identity.json"

            request_doc = make_request_document()
            # Set payload for formal execution
            request_doc["payload"] = {
                "plan": {
                    "adapterId": "unconfigured-adapter",
                    "action": "bounded-operation",
                    "arguments": {},
                }
            }
            identity_doc = {
                "tenantId": "tenant-a",
                "projectId": "project-a",
                "actorId": "actor-a",
                "roles": ["semantic-assurance:execute"],
                "authorizationRef": "auth-001",
            }

            req_file.write_text(json.dumps(request_doc))
            ident_file.write_text(json.dumps(identity_doc))

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "invoke",
                    "--skill", "elmos-smt-equivalence-prover",
                    "--request", str(req_file),
                    "--identity", str(ident_file),
                    "--state-db", str(state_db),
                ])
            # REQUIRES_ADAPTER returns 3
            self.assertEqual(exit_code, 3)
            output = json.loads(stdout.getvalue())
            self.assertEqual(output["executionStatus"], "REQUIRES_ADAPTER")
            self.assertEqual(output["certificationStatus"], "NOT_CERTIFIED")

    def test_invalid_json_or_missing_file_returns_code_2(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main([
                "invoke",
                "--skill", "elmos-smt-equivalence-prover",
                "--request", "/nonexistent/path/request.json",
                "--identity", "/nonexistent/path/identity.json",
                "--state-db", "/tmp/state.db",
            ])
        self.assertEqual(exit_code, 2)
        err = json.loads(stderr.getvalue())
        self.assertIn(err["error"], ["ValueError", "StoreError"])


if __name__ == "__main__":
    unittest.main()
