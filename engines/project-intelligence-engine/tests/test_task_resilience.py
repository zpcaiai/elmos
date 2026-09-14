from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from elmos_project_intelligence.task_execution.task_resilience import (
    DurableTaskError,
    ResilientTaskExecutor,
)


def sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


class DurableTaskExecutorTests(unittest.TestCase):
    def test_result_replays_after_restart_without_repeating_effect(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-resilience-") as temporary:
            path = Path(temporary) / "tasks.sqlite3"
            calls = 0

            def operation():
                nonlocal calls
                calls += 1
                return {"value": 7}

            with ResilientTaskExecutor(
                path, tenant_id="tenant-a", project_id="project-a", campaign_id="campaign-a"
            ) as executor:
                first = executor.execute_idempotent("task-a", {"input": 1}, operation)
                self.assertEqual(first["status"], "EXECUTED_FRESH")
            with ResilientTaskExecutor(
                path, tenant_id="tenant-a", project_id="project-a", campaign_id="campaign-a"
            ) as executor:
                second = executor.execute_idempotent("task-a", {"input": 1}, operation)
                self.assertEqual(second["status"], "REPLAYED_FROM_DURABLE_STORE")
                self.assertFalse(second["side_effects_repeated"])
            self.assertEqual(calls, 1)

    def test_interrupted_attempt_requires_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-recovery-") as temporary:
            path = Path(temporary) / "tasks.sqlite3"
            with ResilientTaskExecutor(
                path, tenant_id="tenant-a", project_id="project-a", campaign_id="campaign-a"
            ) as executor:
                self.assertEqual(executor.begin_attempt("task-a", {"input": 1}), "CREATED")
                executor.checkpoint("task-a", {"stage": "provider-called"})
            with ResilientTaskExecutor(
                path, tenant_id="tenant-a", project_id="project-a", campaign_id="campaign-a"
            ) as executor:
                result = executor.execute_idempotent("task-a", {"input": 1}, lambda: {"bad": True})
                self.assertEqual(result["status"], "RECOVERY_REQUIRED")
                reconciled = executor.reconcile(
                    "task-a",
                    {"input": 1},
                    decision="SUCCEEDED",
                    result={"value": 7},
                    reconciliation_receipt_digest=sha("receipt"),
                )
                self.assertEqual(reconciled["status"], "RECONCILED_SUCCEEDED")

    def test_input_drift_and_cross_tenant_scope_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-isolation-") as temporary:
            path = Path(temporary) / "tasks.sqlite3"
            with ResilientTaskExecutor(
                path, tenant_id="tenant-a", project_id="project-a", campaign_id="campaign-a"
            ) as executor:
                executor.execute_idempotent("task-a", {"input": 1}, lambda: {"value": 1})
                with self.assertRaises(DurableTaskError):
                    executor.execute_idempotent("task-a", {"input": 2}, lambda: {"value": 2})
            with ResilientTaskExecutor(
                path, tenant_id="tenant-b", project_id="project-a", campaign_id="campaign-a"
            ) as executor:
                result = executor.execute_idempotent("task-a", {"input": 2}, lambda: {"value": 2})
                self.assertEqual(result["status"], "EXECUTED_FRESH")


if __name__ == "__main__":
    unittest.main()
