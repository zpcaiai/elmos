from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from elmos_project_intelligence.artifacts import ContentAddressedArtifactStore
from elmos_project_intelligence.service import ProjectIntelligenceService
from elmos_project_intelligence.store import ProjectIntelligenceStore
from elmos_project_intelligence.task_execution.task_runner import ProjectIntelligenceTaskRunner


def request() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": "task-run-1",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "revision": "abc123",
        "actor_id": "actor-a",
        "purpose": "backlog-local-execution",
        "inputs": {
            "revision": "abc123",
            "requested_skills": [],
            "dependency_edges": [],
        },
    }


class TasksExecutionTests(unittest.TestCase):
    def test_catalog_is_exact_and_all_tasks_remain_not_run_by_default(self) -> None:
        runner = ProjectIntelligenceTaskRunner()
        self.assertEqual(len(runner.tasks), 500)
        self.assertEqual(len(runner.skill_tasks), 50)
        receipts = runner.prepare_all_tasks()
        self.assertEqual(len(receipts), 500)
        self.assertEqual({item.execution_state for item in receipts.values()}, {"NOT_RUN"})
        self.assertEqual({item.acceptance_state for item in receipts.values()}, {"NOT_RUN"})
        self.assertEqual({item.certification_status for item in receipts.values()}, {"NOT_CERTIFIED"})

    def test_exact_local_handler_execution_does_not_claim_task_acceptance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-task-runner-") as temporary:
            root = Path(temporary).resolve()
            with ProjectIntelligenceStore(root / "state.sqlite3") as store:
                service = ProjectIntelligenceService(
                    store, ContentAddressedArtifactStore(root / "artifacts")
                )
                runner = ProjectIntelligenceTaskRunner(service=service)
                receipt = runner.execute_task(
                    "ELMOS-PI-00-T01",
                    request(),
                    idempotency_key="task-key-1",
                )
                self.assertEqual(receipt.execution_state, "LOCAL_EXECUTED")
                self.assertEqual(receipt.handler_state, "LOCAL_EXECUTED")
                self.assertEqual(receipt.evidence_state, "COLLECTED")
                self.assertEqual(receipt.acceptance_state, "NOT_RUN")
                self.assertEqual(receipt.external_evidence_status, "NOT_RUN")
                self.assertIn("PRODUCT_ACCEPTANCE_NOT_RUN", receipt.blockers)

    def test_request_without_trusted_service_is_blocked(self) -> None:
        runner = ProjectIntelligenceTaskRunner()
        receipt = runner.execute_task("ELMOS-PI-00-T01", request(), idempotency_key="key")
        self.assertEqual(receipt.execution_state, "BLOCKED")
        self.assertEqual(receipt.blockers, ("TRUSTED_LOCAL_SERVICE_REQUIRED",))


if __name__ == "__main__":
    unittest.main()
