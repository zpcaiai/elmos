from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from elmos_spring_golden_route.catalog import load_catalog
from elmos_spring_golden_route.errors import (
    EvidenceValidationError,
    IdempotencyConflict,
    RunNotFound,
    StateConflict,
)
from elmos_spring_golden_route.runtime import build_registry, validate_request
from elmos_spring_golden_route.state import (
    ACTIVE,
    CANCELLED,
    PAUSED,
    LOCAL_HANDOFF_PREPARED,
    RunStore,
)

from common import REPOSITORY_ROOT, request_for


class RunStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(REPOSITORY_ROOT)
        cls.registry = build_registry(cls.catalog)
        cls.skill_name = cls.catalog.topological_order[0]

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "runs.sqlite3"
        self.store = RunStore(self.database, registry=self.registry)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _create(
        self,
        *,
        tenant_id: str = "tenant-a",
        project_id: str = "project-a",
        run_id: str = "run-a",
        idempotency_key: str = "idem-a",
        objective: str = "Produce a bounded migration blueprint",
    ):
        request = validate_request(
            request_for(
                self.skill_name,
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                idempotency_key=idempotency_key,
                objective=objective,
            )
        )
        plan = self.registry.dispatch(request)
        return request, plan, self.store.create_run(request, plan)

    def test_create_idempotent_replay_and_conflict(self) -> None:
        request, plan, created = self._create()
        self.assertEqual(created.state, ACTIVE)
        self.assertEqual(created.version, 1)
        replay = self.store.create_run(request, plan)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.request_sha256, created.request_sha256)

        other_request = validate_request(
            request_for(
                self.skill_name,
                idempotency_key=request.idempotency_key,
                objective="Different canonical content",
            )
        )
        other_plan = self.registry.dispatch(other_request)
        with self.assertRaises(IdempotencyConflict):
            self.store.create_run(other_request, other_plan)

    def test_minimal_forged_plan_and_unbound_store_cannot_create_runs(self) -> None:
        request = validate_request(request_for(self.skill_name))
        forged = {
            "decision": "DRAFT_ONLY",
            "skill_name": request.skill_name,
            "request_sha256": request.digest,
            "side_effects_performed": False,
            "domain_phase_status": {
                phase: "NOT_RUN"
                for phase in self.registry.dispatch(request)["domain_phase_status"]
            },
        }
        with self.assertRaises(StateConflict):
            self.store.create_run(request, forged)
        unbound = RunStore(Path(self.temporary.name) / "unbound.sqlite3")
        with self.assertRaises(StateConflict):
            unbound.create_run(request, self.registry.dispatch(request))

    def test_tenant_project_isolation(self) -> None:
        self._create()
        for tenant, project in (("tenant-b", "project-a"), ("tenant-a", "project-b")):
            with self.subTest(tenant=tenant, project=project), self.assertRaises(RunNotFound):
                self.store.get_run(tenant, project, "run-a")

    def test_pause_resume_cancel_optimistic_transitions_and_event_chain(self) -> None:
        self._create()
        paused = self.store.pause("tenant-a", "project-a", "run-a", actor_id="actor-b", expected_version=1)
        self.assertEqual((paused.state, paused.version), (PAUSED, 2))
        with self.assertRaises(StateConflict):
            self.store.resume("tenant-a", "project-a", "run-a", actor_id="actor-b", expected_version=1)
        resumed = self.store.resume("tenant-a", "project-a", "run-a", actor_id="actor-b", expected_version=2)
        self.assertEqual((resumed.state, resumed.version), (ACTIVE, 3))
        cancelled = self.store.cancel("tenant-a", "project-a", "run-a", actor_id="actor-c", expected_version=3)
        self.assertEqual((cancelled.state, cancelled.version), (CANCELLED, 4))
        with self.assertRaises(StateConflict):
            self.store.resume("tenant-a", "project-a", "run-a", actor_id="actor-c", expected_version=4)
        events = self.store.list_events("tenant-a", "project-a", "run-a")
        self.assertEqual([event["event_type"] for event in events], [
            "RUN_CREATED",
            "RUN_PAUSED",
            "RUN_RESUMED",
            "RUN_CANCELLED",
        ])
        for previous, current in zip(events, events[1:]):
            self.assertEqual(current["previous_sha256"], previous["event_sha256"])

    def test_event_and_evidence_tables_are_append_only(self) -> None:
        _, plan, _ = self._create()
        self.store.record_evidence(
            "tenant-a",
            "project-a",
            "run-a",
            evidence_id="evidence-catalog",
            role="catalog",
            payload={"authorization_id": "auth-a", **plan["catalog"]},
            executor_id="executor-a",
            verifier_id="verifier-a",
            authorization_id="auth-a",
        )
        with sqlite3.connect(self.database) as connection:
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("DELETE FROM run_events")
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("UPDATE evidence_records SET role = 'plan'")

    def test_readiness_is_blocked_until_exact_paused_digest_bindings_exist(self) -> None:
        _, plan, run = self._create()
        blocked = self.store.evaluate_readiness("tenant-a", "project-a", "run-a")
        self.assertEqual(blocked["decision"], "BLOCKED")
        self.assertEqual(set(blocked["missing_evidence_roles"]), {"catalog", "request", "plan"})

        with self.assertRaises(EvidenceValidationError):
            self.store.record_evidence(
                "tenant-a",
                "project-a",
                "run-a",
                evidence_id="forged",
                role="catalog",
                payload={"authorization_id": "auth-a", "source_archive_sha256": "sha256:" + "0" * 64},
                executor_id="executor-a",
                verifier_id="verifier-a",
                authorization_id="auth-a",
            )
        with self.assertRaises(EvidenceValidationError):
            self.store.record_evidence(
                "tenant-a",
                "project-a",
                "run-a",
                evidence_id="self-verified",
                role="request",
                payload={
                    "authorization_id": "auth-a",
                    "request_sha256": run.request_sha256,
                    "schema_version": "elmos.spring-golden-route.request.v1",
                },
                executor_id="same-actor",
                verifier_id="same-actor",
                authorization_id="auth-a",
            )
        with self.assertRaises(EvidenceValidationError):
            self.store.record_evidence(
                "tenant-a",
                "project-a",
                "run-a",
                evidence_id="arbitrary",
                role="claim",
                payload={"claim": "passed"},
                executor_id="executor-a",
                verifier_id="verifier-a",
                authorization_id="auth-a",
            )

        payloads = {
            "catalog": {"authorization_id": "auth-a", **plan["catalog"]},
            "request": {
                "authorization_id": "auth-a",
                "request_sha256": run.request_sha256,
                "schema_version": "elmos.spring-golden-route.request.v1",
            },
            "plan": {
                "authorization_id": "auth-a",
                "plan_sha256": run.plan_sha256,
                "decision": "DRAFT_ONLY",
            },
        }
        for role, payload in payloads.items():
            receipt = self.store.record_evidence(
                "tenant-a",
                "project-a",
                "run-a",
                evidence_id=f"evidence-{role}",
                role=role,
                payload=payload,
                executor_id=f"executor-{role}",
                verifier_id=f"verifier-{role}",
                authorization_id="auth-a",
            )
            self.assertTrue(str(receipt["payload_sha256"]).startswith("sha256:"))
            self.assertGreater(receipt["byte_count"], 0)
        still_active = self.store.evaluate_readiness("tenant-a", "project-a", "run-a")
        self.assertEqual(still_active["decision"], "BLOCKED")
        self.store.pause("tenant-a", "project-a", "run-a", actor_id="reviewer-a", expected_version=1)
        ready = self.store.evaluate_readiness("tenant-a", "project-a", "run-a")
        self.assertEqual(ready["decision"], LOCAL_HANDOFF_PREPARED)
        self.assertEqual(ready["local_evaluation_status"], "LOCAL_EXECUTED_SELF_ATTESTED")
        self.assertEqual(ready["runtime_evidence_status"], "NOT_RUN")
        self.assertEqual(ready["customer_evidence_status"], "NOT_RUN")
        self.assertEqual(ready["external_evidence_status"], "NOT_RUN")
        self.assertEqual(ready["certification"], "NOT_CERTIFIED")

    def test_stored_request_plan_and_evidence_tampering_fail_closed(self) -> None:
        self._create()
        with sqlite3.connect(self.database) as connection:
            connection.execute("UPDATE runs SET plan_json = '{\"decision\":\"CERTIFIED\"}'")
        with self.assertRaises(StateConflict):
            self.store.get_run("tenant-a", "project-a", "run-a")

        # Fresh database for evidence digest tampering because evidence rows are
        # protected by append-only triggers in ordinary operation.
        other_db = Path(self.temporary.name) / "other.sqlite3"
        other_store = RunStore(other_db, registry=self.registry)
        request = validate_request(request_for(self.skill_name, run_id="run-b", idempotency_key="idem-b"))
        plan = self.registry.dispatch(request)
        run = other_store.create_run(request, plan)
        other_store.record_evidence(
            "tenant-a",
            "project-a",
            "run-b",
            evidence_id="evidence-request",
            role="request",
            payload={
                "authorization_id": "auth-a",
                "request_sha256": run.request_sha256,
                "schema_version": "elmos.spring-golden-route.request.v1",
            },
            executor_id="executor-a",
            verifier_id="verifier-a",
            authorization_id="auth-a",
        )
        with sqlite3.connect(other_db) as connection:
            connection.execute("DROP TRIGGER evidence_records_no_update")
            connection.execute("UPDATE evidence_records SET payload_sha256 = 'sha256:deadbeef'")
        with self.assertRaises(EvidenceValidationError):
            other_store.list_evidence("tenant-a", "project-a", "run-b")


if __name__ == "__main__":
    unittest.main()
