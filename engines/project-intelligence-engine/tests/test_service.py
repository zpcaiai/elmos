from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from elmos_project_intelligence.artifacts import ContentAddressedArtifactStore
from elmos_project_intelligence.runtime import SkillRuntimeError
from elmos_project_intelligence.service import ProjectIntelligenceService
from elmos_project_intelligence.store import (
    IdempotencyConflict,
    ProjectIntelligenceStore,
    RecordNotFound,
)


def request(
    *, tenant: str = "tenant-a", request_id: str = "run-1"
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": request_id,
        "tenant_id": tenant,
        "project_id": "project-a",
        "revision": "abc123",
        "actor_id": "actor-a",
        "purpose": "local-engineering-test",
        "inputs": {
            "files": [
                {"path": "src/app.py", "text": "class App:\n    pass\n"},
                {"path": "pyproject.toml", "text": "[project]\nname='app'\n"},
            ]
        },
    }


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="elmos-pi-service-")
        root = Path(self.temporary.name)
        self.store = ProjectIntelligenceStore(root / "state.sqlite3")
        self.artifacts = ContentAddressedArtifactStore(root / "artifacts")
        self.service = ProjectIntelligenceService(self.store, self.artifacts)

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def test_execution_persists_digest_bound_artifact_evidence_and_checkpoint(
        self,
    ) -> None:
        result = self.service.execute(
            "elmos-project-fingerprinting",
            request(),
            idempotency_key="idempotency-1",
        )
        self.assertEqual(result["state"], "LOCAL_EXECUTED")
        self.assertEqual(result["run_status"], "SUCCEEDED")
        self.assertEqual(result["evidence_state"], "COLLECTED")
        self.assertFalse(result["independent_verifier"])
        self.assertEqual(result["external_evidence"], "NOT_RUN")
        self.assertEqual(result["certification"], "NOT_CERTIFIED")
        self.assertTrue(self.artifacts.contains(result["artifact_digest"]))
        artifacts = self.store.list_artifacts("tenant-a", "project-a", "run-1")
        evidence = self.store.list_evidence("tenant-a", "project-a", "run-1")
        checkpoints = self.store.list_checkpoints("tenant-a", "project-a", "run-1")
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(evidence[0].state.value, "COLLECTED")
        self.assertIsNone(evidence[0].verifier)

    def test_exact_replay_returns_terminal_response_without_duplicate_records(
        self,
    ) -> None:
        first = self.service.execute(
            "elmos-project-fingerprinting", request(), idempotency_key="same"
        )
        second = self.service.execute(
            "elmos-project-fingerprinting", request(), idempotency_key="same"
        )
        self.assertEqual(first["result_digest"], second["result_digest"])
        self.assertEqual(second["idempotency"], "REPLAYED")
        self.assertEqual(
            len(self.store.list_artifacts("tenant-a", "project-a", "run-1")), 1
        )

    def test_idempotency_conflict_and_cross_tenant_lookup_fail_closed(self) -> None:
        self.service.execute(
            "elmos-project-fingerprinting", request(), idempotency_key="same"
        )
        changed = request(request_id="run-2")
        changed["revision"] = "different"
        with self.assertRaises(IdempotencyConflict):
            self.service.execute(
                "elmos-project-fingerprinting", changed, idempotency_key="same"
            )
        with self.assertRaises(RecordNotFound):
            self.store.get_run("tenant-b", "project-a", "run-1")

    def test_unknown_skill_is_rejected_before_persistence(self) -> None:
        with self.assertRaises(SkillRuntimeError):
            self.service.execute("elmos-unknown", request(), idempotency_key="unknown")
        with self.assertRaises(RecordNotFound):
            self.store.get_run("tenant-a", "project-a", "run-1")


if __name__ == "__main__":
    unittest.main()
