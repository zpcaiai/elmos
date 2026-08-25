from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from elmos_project_intelligence.contracts import (
    CreateRunRequest,
    IdempotencyDisposition,
)
from elmos_project_intelligence.store import (
    IdempotencyConflict,
    ProjectIntelligenceStore,
)


ENGINE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ENGINE_ROOT / "src"


def _canonical_line(value: object) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def _request() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": "request-a",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "revision": "abc123",
        "inputs": {
            "revision": "abc123",
            "files": [
                {
                    "path": "src/app.py",
                    "text": "def main():\n    return 'ready'\n",
                },
                {
                    "path": "pyproject.toml",
                    "text": "[project]\nname='fixture'\n",
                },
            ],
        },
    }


class CliBoundaryTests(unittest.TestCase):
    def _invoke(
        self,
        *arguments: str,
        stdin: str = "",
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        existing_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            str(SOURCE_ROOT)
            if not existing_path
            else str(SOURCE_ROOT) + os.pathsep + existing_path
        )
        return subprocess.run(
            [sys.executable, "-m", "elmos_project_intelligence.cli", *arguments],
            cwd=ENGINE_ROOT,
            env=environment,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

    def test_manifest_and_dispatch_emit_deterministic_canonical_json(self) -> None:
        first_manifest = self._invoke("manifest")
        second_manifest = self._invoke("manifest")
        self.assertEqual(first_manifest.returncode, 0, first_manifest.stderr)
        self.assertEqual(second_manifest.returncode, 0, second_manifest.stderr)
        self.assertEqual(first_manifest.stderr, "")
        self.assertEqual(first_manifest.stdout, second_manifest.stdout)
        manifest = json.loads(first_manifest.stdout)
        self.assertEqual(first_manifest.stdout, _canonical_line(manifest))
        self.assertEqual(manifest["counts"]["skills"], 50)
        self.assertEqual(manifest["external_evidence"], "NOT_RUN")
        self.assertEqual(manifest["certification"], "NOT_CERTIFIED")

        request_json = _canonical_line(_request())
        first_dispatch = self._invoke(
            "dispatch",
            "--skill",
            "elmos-project-fingerprinting",
            "--request",
            "-",
            stdin=request_json,
        )
        second_dispatch = self._invoke(
            "dispatch",
            "--skill",
            "elmos-project-fingerprinting",
            "--request",
            "-",
            stdin=request_json,
        )
        self.assertEqual(first_dispatch.returncode, 0, first_dispatch.stderr)
        self.assertEqual(second_dispatch.returncode, 0, second_dispatch.stderr)
        self.assertEqual(first_dispatch.stderr, "")
        self.assertEqual(first_dispatch.stdout, second_dispatch.stdout)
        result = json.loads(first_dispatch.stdout)
        self.assertEqual(first_dispatch.stdout, _canonical_line(result))
        self.assertEqual(result["code"], "REVISION_FINGERPRINTED")
        self.assertEqual(result["state"], "LOCAL_EXECUTED")
        self.assertFalse(result["external_effects_performed"])
        self.assertEqual(result["external_evidence"], "NOT_RUN")
        self.assertEqual(result["certification"], "NOT_CERTIFIED")

    def test_unknown_skill_is_rejected_without_fallback_dispatch(self) -> None:
        completed = self._invoke(
            "dispatch",
            "--skill",
            "elmos-unknown-capability",
            "--request",
            "-",
            stdin=_canonical_line(_request()),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stderr, "")
        result = json.loads(completed.stdout)
        self.assertEqual(completed.stdout, _canonical_line(result))
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["code"], "CLI_REQUEST_REJECTED")
        self.assertEqual(result["error"]["type"], "SkillRuntimeError")
        self.assertIn("unknown Project Intelligence Skill", result["error"]["message"])
        self.assertFalse(result["external_effects_performed"])
        self.assertEqual(result["external_evidence"], "NOT_RUN")
        self.assertEqual(result["certification"], "NOT_CERTIFIED")

    def test_duplicate_json_key_is_rejected_before_handler_execution(self) -> None:
        duplicate_request = (
            '{"schema_version":"1.0","request_id":"one","request_id":"two",'
            '"tenant_id":"tenant-a","project_id":"project-a",'
            '"revision":"abc123","inputs":{}}\n'
        )
        completed = self._invoke(
            "dispatch",
            "--skill",
            "elmos-project-fingerprinting",
            "--request",
            "-",
            stdin=duplicate_request,
        )
        self.assertEqual(completed.returncode, 2)
        result = json.loads(completed.stdout)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["code"], "CLI_REQUEST_REJECTED")
        self.assertIn("duplicate JSON key", result["error"]["message"])
        self.assertFalse(result["external_effects_performed"])


class ServiceRestartBoundaryTests(unittest.TestCase):
    def test_idempotency_binding_and_events_survive_store_restart(self) -> None:
        # The current CLI is intentionally stateless. Persistence is exercised
        # at the SQLite-backed service boundary used by long-running callers.
        with TemporaryDirectory() as temporary:
            database = Path(temporary) / "project-intelligence.sqlite3"
            original = CreateRunRequest(
                tenant_id="tenant-a",
                project_id="project-a",
                run_id="run-original",
                operation="fingerprint",
                idempotency_key="request-a",
                request={"revision": "abc123"},
            )
            with ProjectIntelligenceStore(database) as store:
                store.register_project("tenant-a", "project-a")
                created = store.create_run(original)
                self.assertEqual(created.disposition, IdempotencyDisposition.CREATED)

            with ProjectIntelligenceStore(database) as restarted:
                replayed = restarted.create_run(
                    CreateRunRequest(
                        tenant_id="tenant-a",
                        project_id="project-a",
                        run_id="run-must-not-replace-original",
                        operation="fingerprint",
                        idempotency_key="request-a",
                        request={"revision": "abc123"},
                    )
                )
                self.assertEqual(replayed.disposition, IdempotencyDisposition.REPLAYED)
                self.assertEqual(replayed.run.run_id, "run-original")
                self.assertEqual(
                    restarted.get_run("tenant-a", "project-a", "run-original").run_id,
                    "run-original",
                )
                events = restarted.list_events("tenant-a", "project-a", "run-original")
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].event_type, "run.created")
                with self.assertRaises(IdempotencyConflict):
                    restarted.create_run(
                        CreateRunRequest(
                            tenant_id="tenant-a",
                            project_id="project-a",
                            run_id="run-conflict",
                            operation="fingerprint",
                            idempotency_key="request-a",
                            request={"revision": "different"},
                        )
                    )


if __name__ == "__main__":
    unittest.main()
