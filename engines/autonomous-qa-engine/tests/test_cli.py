from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from elmos_autonomous_qa.cli import main


class CliTests(unittest.TestCase):
    def invoke(self, *arguments: str) -> tuple[int, dict[str, object]]:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(arguments)
        return code, json.loads(output.getvalue())

    def test_lists_all_exact_skill_bindings(self) -> None:
        code, payload = self.invoke("skills")
        self.assertEqual(0, code)
        self.assertEqual(40, len(payload["skills"]))
        self.assertEqual("NOT_RUN", payload["external_evidence"])
        self.assertEqual("NOT_CERTIFIED", payload["certification"])

    def test_dispatches_a_skill_from_strict_json(self) -> None:
        request = {
            "schema_version": "1.0",
            "request_id": "request-1",
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "actor_id": "actor-1",
            "inputs": {
                "requirements": [
                    {
                        "requirement_id": "REQ-1",
                        "title": "Addition",
                        "statement": "The sum equals the two inputs.",
                        "priority": "P0",
                        "required": True,
                        "source_refs": ["requirements.md:1"],
                        "acceptance_criteria": ["One plus two equals three."],
                    }
                ]
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(json.dumps(request), encoding="utf-8")
            code, payload = self.invoke(
                "execute", "02-spec-normalization", "--request", str(path)
            )
        self.assertEqual(0, code)
        self.assertEqual("SUCCEEDED", payload["state"])
        self.assertEqual("NOT_CERTIFIED", payload["certification"])

    def test_execute_refuses_mutating_skill_without_trusted_scope_binder(self) -> None:
        request = {
            "schema_version": "1.0",
            "request_id": "request-1",
            "tenant_id": "forged-tenant",
            "project_id": "forged-project",
            "idempotency_key": "key-1",
            "inputs": {"mode": "plan-only", "snapshot_ref": "a" * 64},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(json.dumps(request), encoding="utf-8")
            code, payload = self.invoke(
                "execute", "00-qa-control-plane", "--request", str(path)
            )
        self.assertEqual(2, code)
        self.assertEqual("AUTONOMOUS_QA_CLI_REJECTED", payload["code"])

    def test_partial_skill_and_incomplete_snapshot_return_nonzero(self) -> None:
        request = {
            "schema_version": "1.0",
            "request_id": "request-partial",
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "actor_id": "forged-actor",
            "inputs": {
                "requirements": [
                    {
                        "requirement_id": "REQ-1",
                        "title": "Requirement",
                        "statement": "Behavior is preserved",
                        "priority": "P0",
                        "required": True,
                    }
                ]
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "request.json"
            path.write_text(json.dumps(request), encoding="utf-8")
            code, payload = self.invoke(
                "execute", "06-functional-test-generation", "--request", str(path)
            )
            self.assertEqual(3, code)
            self.assertEqual("PARTIAL", payload["state"])

            request["inputs"] = {
                "resource_tenant_id": "tenant-1",
                "action": "read-evidence",
                "roles": ["qa-reader"],
                "required_roles": ["qa-reader"],
            }
            path.write_text(json.dumps(request), encoding="utf-8")
            identity_code, identity_result = self.invoke(
                "execute", "35-governance-approval-audit", "--request", str(path)
            )
            self.assertEqual(3, identity_code)
            self.assertEqual(
                f"local-uid-{os.getuid()}", identity_result["outputs"]["actor_id"]
            )

            snapshot_code, snapshot = self.invoke(
                "snapshot", str(root), "--required", "missing.file"
            )
            self.assertEqual(3, snapshot_code)
            self.assertFalse(snapshot["complete"])

    def test_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
            code, payload = self.invoke("execute", "00-qa-control-plane", "--request", str(path))
        self.assertEqual(2, code)
        self.assertEqual("AUTONOMOUS_QA_CLI_REJECTED", payload["code"])

    def test_run_commands_keep_tenants_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "qa.sqlite3"
            payload = root / "payload.json"
            payload.write_text("{}", encoding="utf-8")
            create_code, created = self.invoke(
                "run-create",
                "--database",
                str(database),
                "--tenant",
                "tenant-a",
                "--run-id",
                "run-1",
                "--idempotency-key",
                "create-1",
                "--project",
                "project-1",
                "--mode",
                "verify",
                "--payload",
                str(payload),
            )
            get_code, blocked = self.invoke(
                "run-get",
                "--database",
                str(database),
                "--tenant",
                "tenant-b",
                "--run-id",
                "run-1",
            )
        self.assertEqual(0, create_code)
        self.assertEqual("run-1", created["run_id"])
        self.assertEqual(2, get_code)
        self.assertEqual("AUTONOMOUS_QA_CLI_REJECTED", blocked["code"])

    def test_privileged_evidence_and_approval_commands_are_not_exposed(self) -> None:
        for command in ("evidence-register", "evidence-revoke"):
            with self.subTest(command=command), self.assertRaises(SystemExit):
                main((command,))
        with self.assertRaises(SystemExit):
            main(
                (
                    "run-transition",
                    "--database",
                    "qa.sqlite3",
                    "--tenant",
                    "tenant-a",
                    "--run-id",
                    "run-a",
                    "--idempotency-key",
                    "key-a",
                    "approve",
                )
            )

    def test_json_input_refuses_symlinks_and_oversized_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "request.json"
            target.write_text("{}", encoding="utf-8")
            link = root / "request-link.json"
            link.symlink_to(target)
            code, payload = self.invoke(
                "execute", "00-qa-control-plane", "--request", str(link)
            )
            self.assertEqual(2, code)
            self.assertEqual("AUTONOMOUS_QA_CLI_REJECTED", payload["code"])

            oversized = root / "oversized.json"
            with oversized.open("wb") as stream:
                stream.truncate(16 * 1024 * 1024 + 1)
            code, payload = self.invoke(
                "execute", "00-qa-control-plane", "--request", str(oversized)
            )
            self.assertEqual(2, code)
            self.assertEqual("AUTONOMOUS_QA_CLI_REJECTED", payload["code"])

    def test_deep_json_is_a_bounded_cli_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request_path = Path(directory) / "deep.json"
            request_path.write_text(
                '{"child":' * 2_000 + 'null' + '}' * 2_000,
                encoding="utf-8",
            )
            code, payload = self.invoke(
                "execute",
                "02-spec-normalization",
                "--request",
                str(request_path),
            )
            self.assertEqual(2, code)
            self.assertEqual("AUTONOMOUS_QA_CLI_REJECTED", payload["code"])

    def test_snapshot_cli_cannot_broaden_repository_limits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code, payload = self.invoke(
                "snapshot", directory, "--max-files", "50001"
            )
        self.assertEqual(2, code)
        self.assertEqual("AUTONOMOUS_QA_CLI_REJECTED", payload["code"])


if __name__ == "__main__":
    unittest.main()
