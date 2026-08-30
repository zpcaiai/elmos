from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from elmos_pi_harness.models import (
    AuthoritySnapshot,
    ExecutorIdentity,
    NotFoundError,
    TextContent,
    ToolInvocation,
    ToolResult,
)
from elmos_pi_harness.postgres import PostgresConfig, PostgresMigrator, PostgresStore


def uid() -> str:
    return str(uuid.uuid4())


@unittest.skipUnless(
    os.environ.get("ELMOS_PI_POSTGRES_DSN")
    and os.environ.get("ELMOS_PI_POSTGRES_ADMIN_DSN"),
    "real PostgreSQL profile is not configured",
)
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="pi-postgres-integration-")
        cls.admin_config = PostgresConfig(os.environ["ELMOS_PI_POSTGRES_ADMIN_DSN"])
        cls.config = PostgresConfig(os.environ["ELMOS_PI_POSTGRES_DSN"])
        migration_root = Path(__file__).resolve().parents[1] / "sql"
        PostgresMigrator(cls.admin_config, migration_root).apply()
        cls.store = PostgresStore(
            cls.config, artifact_root=Path(cls.temp.name) / "artifacts"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()
        cls.temp.cleanup()

    def test_full_kernel_surface_and_rls(self) -> None:
        tenant, other_tenant, project, task = uid(), uid(), uid(), uid()
        created = self.store.create_task(
            tenant,
            project,
            "postgres integration",
            idempotency_key="create",
            task_id=task,
            actor_id="integration",
        )
        self.assertEqual(created["status"], "CREATED")
        with self.assertRaises(NotFoundError):
            self.store.get_task(other_tenant, task)
        self.store.transition_task(
            tenant, task, "QUEUED", idempotency_key="queue", actor_id="integration"
        )
        environment = self.store.create_environment(
            tenant, task, "integration", config={"database": "postgresql"}
        )
        snapshot = AuthoritySnapshot(
            uid(),
            environment["environment_id"],
            "integration-v1",
            frozenset({"repo.read"}),
        )
        snapshot_id = uid()
        self.store.create_authority_snapshot(tenant, snapshot_id, snapshot)
        executor = ExecutorIdentity("postgres-worker", 1, "registry-v1")
        self.store.register_executor(tenant, environment["environment_id"], executor)
        invocation = ToolInvocation(
            uid(),
            task,
            environment["environment_id"],
            snapshot_id,
            "repo.read",
            {"path": "README.md"},
            "pg-tool",
            1000,
            "read-only",
        )
        self.store.begin_tool_call(tenant, invocation, executor)
        self.store.mark_tool_executing(tenant, invocation.call_id, executor)
        result = ToolResult(invocation.call_id, (TextContent("ok"),))
        self.assertEqual(
            self.store.complete_tool_call(
                tenant, invocation.call_id, executor, result
            ).to_dict(),
            result.to_dict(),
        )
        artifact = self.store.put_artifact(
            tenant, task, "result.txt", b"postgres", media_type="text/plain"
        )
        self.assertEqual(
            artifact["sha256"],
            "sha256:a942b37ccfaf5a813b1432caa209a43b9d144e47ad0de1549c289c253e556cd5",
        )
        self.assertGreaterEqual(len(self.store.events(tenant, task)["items"]), 4)
        self.assertEqual(self.store.health()["backend"], "postgresql")


if __name__ == "__main__":
    unittest.main()
