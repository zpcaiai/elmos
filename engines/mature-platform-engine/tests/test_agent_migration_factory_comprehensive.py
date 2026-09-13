"""Comprehensive test suite for AgentMigrationFactoryEngine (Batch 42 - Skill 1423)."""

import unittest

from elmos_mature_platform.agent_migration_factory_engine import AgentMigrationFactoryEngine
from elmos_mature_platform.types import (
    AgentMigrationTask,
    AgentTaskLifecycle,
    MigrationWavePlan,
)


class TestAgentMigrationFactoryComprehensive(unittest.TestCase):
    """Rigorous tests covering wave scheduling, task lifecycles, worktree allocations, and checkpoints."""

    def setUp(self) -> None:
        self.engine = AgentMigrationFactoryEngine()

    def test_create_wave_plan(self) -> None:
        wave = MigrationWavePlan(
            wave_id="",
            wave_number=1,
            concurrency_limit=10,
        )
        wave_id = self.engine.create_wave_plan(wave)
        self.assertTrue(wave_id.startswith("wave-"))
        self.assertEqual(wave.status, "pending")

        with self.assertRaises(ValueError):
            self.engine.create_wave_plan(
                MigrationWavePlan(wave_id="", wave_number=-1)
            )

    def test_dispatch_task_success(self) -> None:
        wave_id = self.engine.create_wave_plan(
            MigrationWavePlan(wave_id="wave-01", wave_number=1)
        )
        task = AgentMigrationTask(
            task_id="",
            project_id="proj-legacy-crm",
            wave_id=wave_id,
            agent_id="agent-java-spec-01",
            source_language="java",
            target_language="csharp",
            source_module="crm-services",
            target_module="CrmServices",
        )
        task_id = self.engine.dispatch_task(task)
        self.assertTrue(task_id.startswith("mtask-"))

        retrieved = self.engine.get_task(task_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.status, AgentTaskLifecycle.DISPATCHED)
        self.assertTrue(retrieved.assigned_worktree.startswith("/tmp/elmos_worktrees/"))

    def test_dispatch_task_missing_fields_or_wave(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.dispatch_task(
                AgentMigrationTask(
                    task_id="",
                    project_id="",
                    wave_id="non-existent",
                    agent_id="a1",
                    source_language="java",
                    target_language="go",
                    source_module="m1",
                    target_module="m2",
                )
            )

    def test_update_task_status_and_completion(self) -> None:
        wave_id = self.engine.create_wave_plan(
            MigrationWavePlan(wave_id="wave-02", wave_number=2)
        )
        task_id = self.engine.dispatch_task(
            AgentMigrationTask(
                task_id="t1",
                project_id="p1",
                wave_id=wave_id,
                agent_id="a1",
                source_language="python",
                target_language="rust",
                source_module="analytics",
                target_module="analytics_rs",
            )
        )

        t = self.engine.update_task_status(task_id, AgentTaskLifecycle.TRANSFORMING)
        self.assertEqual(t.status, AgentTaskLifecycle.TRANSFORMING)
        self.assertEqual(t.completed_at, "")

        t_comp = self.engine.update_task_status(task_id, AgentTaskLifecycle.COMPLETED)
        self.assertEqual(t_comp.status, AgentTaskLifecycle.COMPLETED)
        self.assertNotEqual(t_comp.completed_at, "")

    def test_attach_checkpoint(self) -> None:
        wave_id = self.engine.create_wave_plan(
            MigrationWavePlan(wave_id="wave-03", wave_number=3)
        )
        task_id = self.engine.dispatch_task(
            AgentMigrationTask(
                task_id="t2",
                project_id="p1",
                wave_id=wave_id,
                agent_id="a1",
                source_language="cobol",
                target_language="java",
                source_module="batch",
                target_module="batch_job",
            )
        )
        task = self.engine.attach_checkpoint(task_id, "chk-restore-point-alpha")
        self.assertEqual(task.checkpoint_id, "chk-restore-point-alpha")

        with self.assertRaises(ValueError):
            self.engine.attach_checkpoint(task_id, "")

    def test_wave_progress_and_factory_report(self) -> None:
        wave_id = self.engine.create_wave_plan(
            MigrationWavePlan(wave_id="wave-04", wave_number=4)
        )
        t1 = self.engine.dispatch_task(
            AgentMigrationTask(
                task_id="task-w4-1", project_id="p", wave_id=wave_id, agent_id="a",
                source_language="java", target_language="csharp", source_module="s1", target_module="t1"
            )
        )
        t2 = self.engine.dispatch_task(
            AgentMigrationTask(
                task_id="task-w4-2", project_id="p", wave_id=wave_id, agent_id="a",
                source_language="java", target_language="csharp", source_module="s2", target_module="t2"
            )
        )

        self.engine.update_task_status(t1, AgentTaskLifecycle.COMPLETED)
        self.engine.update_task_status(t2, AgentTaskLifecycle.FAILED, error_message="Compile error")

        prog = self.engine.get_wave_progress(wave_id)
        self.assertEqual(prog["total_tasks"], 2)
        self.assertEqual(prog["completed"], 1)
        self.assertEqual(prog["failed"], 1)
        self.assertEqual(prog["status"], "completed")

        report = self.engine.get_factory_throughput_report()
        self.assertEqual(report["total_tasks"], 2)
        self.assertEqual(report["completed_tasks"], 1)
        self.assertEqual(report["success_rate_pct"], 50.0)
        self.assertIn("java->csharp", report["language_pairs"])


if __name__ == "__main__":
    unittest.main()
