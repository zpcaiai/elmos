from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from elmos_autonomous_qa.api import QaApi, TrustedIdentity
from elmos_autonomous_qa.control_plane import QaControlPlane
from elmos_autonomous_qa.skill_runtime import dispatch_skill
from elmos_autonomous_qa.trusted_services import TrustedProjectRoots


class TrustedSkillServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "pyproject.toml").write_text(
            "[project]\nname='demo'\nversion='1.0'\n", encoding="utf-8"
        )
        (self.project / "app.py").write_text(
            "def application():\n    return 'ok'\n", encoding="utf-8"
        )
        self.database = self.root / "qa.sqlite3"
        self.api = QaApi(
            QaControlPlane(self.database),
            project_roots={("tenant-a", "project-a"): self.project},
        )
        self.identity = TrustedIdentity(
            tenant_id="tenant-a",
            actor_id="actor-a",
            roles=frozenset({"qa:read", "qa:write"}),
            project_ids=frozenset({"project-a"}),
        )

    def execute(self, source_id: str, inputs: dict, *, key: str | None = None):
        body = {"project_id": "project-a", "inputs": inputs}
        if key is not None:
            body["idempotency_key"] = key
        return self.api.handle(
            "POST",
            f"/api/v1/qa/skills/{source_id}:execute",
            body,
            self.identity,
        )

    def test_00_exact_skill_api_binds_durable_create_transition_and_observation(self) -> None:
        created = self.execute(
            "00-qa-control-plane",
            {
                "operation": "create",
                "run_id": "run-service",
                "mode": "verify",
                "payload": {"snapshot_id": "snapshot-1"},
            },
            key="create-service",
        )
        self.assertEqual(200, created.status)
        self.assertTrue(created.body["outputs"]["persisted"])
        self.assertEqual("created", created.body["outputs"]["run"]["status"])

        started = self.execute(
            "00-qa-control-plane",
            {
                "operation": "transition",
                "run_id": "run-service",
                "action": "start",
                "details": {},
            },
            key="start-service",
        )
        self.assertEqual("running", started.body["outputs"]["run"]["status"])

        heartbeat = self.execute(
            "00-qa-control-plane",
            {
                "operation": "heartbeat",
                "run_id": "run-service",
                "payload": {"worker_id": "worker-a", "lease_epoch": 1},
            },
            key="heartbeat-service",
        )
        self.assertEqual(200, heartbeat.status)
        reopened = QaControlPlane(self.database)
        events = reopened.list_events(tenant_id="tenant-a", run_id="run-service")
        self.assertIn(
            "run.observation.worker-heartbeat", {event.kind for event in events}
        )

    def test_00_generic_dispatch_never_accepts_a_caller_database_or_claims_persistence(self) -> None:
        result = dispatch_skill(
            "00-qa-control-plane",
            {
                "schema_version": "1.0",
                "request_id": "request-plan",
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "actor_id": "actor-a",
                "idempotency_key": "create-plan",
                "inputs": {
                    "operation": "create",
                    "run_id": "run-plan",
                    "mode": "verify",
                    "payload": {},
                },
            },
        )
        self.assertEqual("PARTIAL", result["state"])
        self.assertFalse(result["outputs"]["persisted"])
        self.assertFalse(result["outputs"]["caller_database_path_accepted"])

    def test_01_exact_skill_uses_only_trusted_root_and_reports_snapshot_omissions(self) -> None:
        response = self.execute(
            "01-project-context-ingestion",
            {"operation": "snapshot", "required_paths": ["app.py"]},
        )
        self.assertEqual(200, response.status)
        outputs = response.body["outputs"]
        self.assertEqual("LOCAL_EXECUTED", outputs["trusted_project_binding"])
        self.assertFalse(outputs["caller_project_root_accepted"])
        self.assertIn("app.py", outputs["entrypoints"])
        self.assertIn("python", outputs["build_systems"])
        location = next(
            item for item in outputs["source_locations"] if item["path"] == "app.py"
        )
        self.assertFalse(location["content_exposed"])
        self.assertRegex(location["sha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual("NOT_RUN", outputs["build_command_execution"])

    def test_01_unbound_project_and_caller_path_are_rejected(self) -> None:
        unbound = QaApi(QaControlPlane(self.root / "unbound.sqlite3"))
        response = unbound.handle(
            "POST",
            "/api/v1/qa/skills/01-project-context-ingestion:execute",
            {"project_id": "project-a", "inputs": {"operation": "snapshot"}},
            self.identity,
        )
        self.assertEqual(422, response.status)
        caller_path = self.execute(
            "01-project-context-ingestion",
            {"operation": "snapshot", "project_root": str(self.root)},
        )
        self.assertEqual(422, caller_path.status)

    def test_project_root_registry_requires_exact_absolute_scoped_bindings(self) -> None:
        with self.assertRaises(ValueError):
            TrustedProjectRoots({("tenant-a", "project-a"): Path("relative")})
        registry = TrustedProjectRoots(
            {("tenant-a", "project-a"): self.project}
        )
        self.assertEqual(
            self.project,
            registry.root_for(tenant_id="tenant-a", project_id="project-a"),
        )
        with self.assertRaises(Exception):
            registry.root_for(tenant_id="tenant-b", project_id="project-a")


if __name__ == "__main__":
    unittest.main()
