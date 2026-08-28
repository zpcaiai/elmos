"""Tests for Durable Workflow execution and orchestration."""

from __future__ import annotations

import unittest
from elmos_ai_capability.workflows import WorkflowEngine


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = WorkflowEngine()

    def test_35_workflows_present(self) -> None:
        wfs = self.engine.list_workflows()
        self.assertEqual(len(wfs), 35)
        self.assertIn("agent-incident-containment", wfs)
        self.assertIn("formal-assurance", wfs)
        self.assertIn("zero-trust-confidential-release", wfs)

    def test_execute_incident_containment_workflow(self) -> None:
        res = self.engine.execute_workflow("agent-incident-containment")
        self.assertEqual(res.status, "COMPLETED")
        self.assertGreater(len(res.steps_executed), 0)
        self.assertTrue(res.evidence_digest.startswith("sha256:"))

    def test_validate_all_workflows(self) -> None:
        results = self.engine.validate_all_workflows()
        self.assertEqual(len(results), 35)
        for name, res in results.items():
            self.assertEqual(res.status, "COMPLETED", f"Workflow {name} did not complete")


if __name__ == "__main__":
    unittest.main()
