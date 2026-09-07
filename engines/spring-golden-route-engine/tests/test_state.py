from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from elmos_spring_golden_route.canonical import canonical_json, sha256_digest
from elmos_spring_golden_route.catalog import load_catalog
from elmos_spring_golden_route.errors import (
    EvidenceValidationError,
    IdempotencyConflict,
    RunNotFound,
    SchemaMigrationRequired,
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

    @staticmethod
    def _rewrite_plan_and_creation_event(database: Path, tampered_plan: dict[str, object]) -> None:
        plan_json = canonical_json(tampered_plan)
        plan_sha256 = sha256_digest(plan_json.encode("utf-8"))
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.row_factory = sqlite3.Row
            connection.execute(
                "UPDATE runs SET plan_json = ?, plan_sha256 = ?",
                (plan_json, plan_sha256),
            )
            connection.execute("DROP TRIGGER run_events_no_update")
            row = connection.execute("SELECT * FROM run_events ORDER BY sequence LIMIT 1").fetchone()
            payload = json.loads(str(row["payload_json"]))
            payload["plan_sha256"] = plan_sha256
            body = RunStore._event_body(
                tenant_id=row["tenant_id"],
                project_id=row["project_id"],
                run_id=row["run_id"],
                event_type=row["event_type"],
                actor_id=row["actor_id"],
                from_state=row["from_state"],
                to_state=row["to_state"],
                run_version=row["run_version"],
                occurred_at=row["occurred_at"],
                previous_sha256=row["previous_sha256"],
                payload=payload,
            )
            connection.execute(
                "UPDATE run_events SET payload_json = ?, event_sha256 = ? WHERE sequence = ?",
                (
                    canonical_json(payload),
                    sha256_digest(canonical_json(body).encode("utf-8")),
                    row["sequence"],
                ),
            )

    @staticmethod
    def _rewrite_schema_object(
        database: Path,
        *,
        object_type: str,
        name: str,
        old: str,
        new: str,
    ) -> None:
        with closing(sqlite3.connect(database)) as connection, connection:
            schema_version = int(connection.execute("PRAGMA schema_version").fetchone()[0])
            row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = ? AND name = ?",
                (object_type, name),
            ).fetchone()
            if row is None or not isinstance(row[0], str) or old not in row[0]:
                raise AssertionError(f"schema fixture {object_type}:{name} is not rewriteable")
            connection.execute("PRAGMA writable_schema = ON")
            connection.execute(
                "UPDATE sqlite_master SET sql = ? WHERE type = ? AND name = ?",
                (row[0].replace(old, new, 1), object_type, name),
            )
            connection.execute(f"PRAGMA schema_version = {schema_version + 1}")
            connection.execute("PRAGMA writable_schema = OFF")

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

    def test_unbound_store_cannot_read_transition_or_evaluate_runs(self) -> None:
        self._create()
        unbound = RunStore(self.database, create=False)
        operations = {
            "get": lambda: unbound.get_run("tenant-a", "project-a", "run-a"),
            "transition": lambda: unbound.pause(
                "tenant-a", "project-a", "run-a", actor_id="actor-b", expected_version=1
            ),
            "evaluate": lambda: unbound.evaluate_readiness("tenant-a", "project-a", "run-a"),
        }
        for name, operation in operations.items():
            with self.subTest(operation=name), self.assertRaises(StateConflict):
                operation()
        current = self.store.get_run("tenant-a", "project-a", "run-a")
        self.assertEqual((current.state, current.version), (ACTIVE, 1))

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
            payload={
                "authorization_id": "auth-a", "executor_id": "executor-a",
                "verifier_id": "verifier-a", **plan["catalog"],
            },
            executor_id="executor-a",
            verifier_id="verifier-a",
            authorization_id="auth-a",
        )
        with closing(sqlite3.connect(self.database)) as connection, connection:
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
            "catalog": {
                "authorization_id": "auth-a", "executor_id": "executor-catalog",
                "verifier_id": "verifier-catalog", **plan["catalog"],
            },
            "request": {
                "authorization_id": "auth-a",
                "executor_id": "executor-request",
                "verifier_id": "verifier-request",
                "request_sha256": run.request_sha256,
                "schema_version": "elmos.spring-golden-route.request.v1",
            },
            "plan": {
                "authorization_id": "auth-a",
                "executor_id": "executor-plan",
                "verifier_id": "verifier-plan",
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
        self.assertEqual(ready["decision"], "BLOCKED")
        self.assertEqual(ready["local_handoff_status"], LOCAL_HANDOFF_PREPARED)
        self.assertEqual(ready["local_evaluation_status"], "LOCAL_EXECUTED_SELF_ATTESTED")
        self.assertEqual(ready["authorization_verification_status"], "NOT_RUN")
        self.assertEqual(ready["runtime_evidence_status"], "NOT_RUN")
        self.assertEqual(ready["customer_evidence_status"], "NOT_RUN")
        self.assertEqual(ready["external_evidence_status"], "NOT_RUN")
        self.assertEqual(ready["certification"], "NOT_CERTIFIED")

    def test_stored_request_plan_and_evidence_tampering_fail_closed(self) -> None:
        self._create()
        with closing(sqlite3.connect(self.database)) as connection, connection:
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
                "executor_id": "executor-a",
                "verifier_id": "verifier-a",
                "request_sha256": run.request_sha256,
                "schema_version": "elmos.spring-golden-route.request.v1",
            },
            executor_id="executor-a",
            verifier_id="verifier-a",
            authorization_id="auth-a",
        )
        with closing(sqlite3.connect(other_db)) as connection, connection:
            connection.execute("DROP TRIGGER evidence_records_no_update")
            connection.execute("UPDATE evidence_records SET payload_sha256 = 'sha256:deadbeef'")
        with self.assertRaises(EvidenceValidationError):
            other_store.list_evidence("tenant-a", "project-a", "run-b")

    def test_schema_version_is_explicit_and_legacy_databases_require_reviewed_migration(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
            metadata = connection.execute(
                "SELECT schema_id, version, schema_sha256 FROM engine_schema"
            ).fetchone()
        self.assertEqual(metadata[0], "elmos.spring-golden-route.run-store")
        self.assertEqual(metadata[1], 1)
        self.assertTrue(str(metadata[2]).startswith("sha256:"))
        RunStore(self.database, create=False)

        legacy = Path(self.temporary.name) / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy)) as connection, connection:
            connection.execute("CREATE TABLE legacy_state (value TEXT)")
        with self.assertRaises(SchemaMigrationRequired):
            RunStore(legacy)
        with closing(sqlite3.connect(legacy)) as connection, connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        self.assertEqual(tables, {"legacy_state"})

    def test_schema_validation_rejects_constraint_fk_trigger_and_index_drift(self) -> None:
        table_drift = Path(self.temporary.name) / "table-drift.sqlite3"
        RunStore(table_drift)
        self._rewrite_schema_object(
            table_drift,
            object_type="table",
            name="runs",
            old="version INTEGER NOT NULL CHECK (version >= 1)",
            new="version INTEGER NOT NULL",
        )
        with self.assertRaises(SchemaMigrationRequired):
            RunStore(table_drift, create=False)

        foreign_key_drift = Path(self.temporary.name) / "foreign-key-drift.sqlite3"
        RunStore(foreign_key_drift)
        self._rewrite_schema_object(
            foreign_key_drift,
            object_type="table",
            name="run_events",
            old=(
                ",\n            FOREIGN KEY (tenant_id, project_id, run_id)\n"
                "                REFERENCES runs (tenant_id, project_id, run_id)"
            ),
            new="",
        )
        with self.assertRaises(SchemaMigrationRequired):
            RunStore(foreign_key_drift, create=False)

        trigger_drift = Path(self.temporary.name) / "trigger-drift.sqlite3"
        RunStore(trigger_drift)
        with closing(sqlite3.connect(trigger_drift)) as connection, connection:
            connection.execute("DROP TRIGGER run_events_no_update")
            connection.execute(
                """
                CREATE TRIGGER run_events_no_update
                BEFORE UPDATE ON run_events
                BEGIN
                    SELECT 1;
                END
                """
            )
        with self.assertRaises(SchemaMigrationRequired):
            RunStore(trigger_drift, create=False)

        index_drift = Path(self.temporary.name) / "index-drift.sqlite3"
        RunStore(index_drift)
        with closing(sqlite3.connect(index_drift)) as connection, connection:
            connection.execute("CREATE INDEX runs_skill_name_idx ON runs (skill_name)")
        with self.assertRaises(SchemaMigrationRequired):
            RunStore(index_drift, create=False)

    def test_rehashed_row_scope_task_skill_and_idempotency_rewrites_fail_closed(self) -> None:
        attacks = {
            "tenant_id": "tenant-z",
            "project_id": "project-z",
            "run_id": "run-z",
            "task_id": "task-z",
            "skill_name": self.catalog.topological_order[1],
            "idempotency_key": "idem-z",
        }
        for index, (field, replacement) in enumerate(attacks.items()):
            with self.subTest(field=field):
                database = Path(self.temporary.name) / f"row-tamper-{index}.sqlite3"
                store = RunStore(database, registry=self.registry)
                original = validate_request(
                    request_for(
                        self.skill_name,
                        run_id=f"run-{index}",
                        task_id=f"task-{index}",
                        idempotency_key=f"idem-{index}",
                    )
                )
                store.create_run(original, self.registry.dispatch(original))
                rewritten = original.as_dict()
                rewritten[field] = replacement
                rewritten_request = validate_request(rewritten)
                rewritten_plan = self.registry.dispatch(rewritten_request)
                plan_json = canonical_json(rewritten_plan)
                with closing(sqlite3.connect(database)) as connection, connection:
                    connection.execute(
                        """
                        UPDATE runs SET tenant_id = ?, project_id = ?, run_id = ?, task_id = ?,
                            skill_name = ?, idempotency_key = ?, request_sha256 = ?, request_json = ?,
                            plan_sha256 = ?, plan_json = ?
                        """,
                        (
                            rewritten_request.tenant_id,
                            rewritten_request.project_id,
                            rewritten_request.run_id,
                            rewritten_request.task_id,
                            rewritten_request.skill_name,
                            rewritten_request.idempotency_key,
                            rewritten_request.digest,
                            rewritten_request.canonical.decode("utf-8"),
                            sha256_digest(plan_json.encode("utf-8")),
                            plan_json,
                        ),
                    )
                reopened = RunStore(database, registry=self.registry, create=False)
                with self.assertRaises(StateConflict):
                    reopened.get_run(
                        rewritten_request.tenant_id,
                        rewritten_request.project_id,
                        rewritten_request.run_id,
                    )

    def test_rehashed_plan_binding_and_creation_event_rewrites_fail_closed(self) -> None:
        request, plan, _ = self._create()
        tampered_plan = dict(plan)
        tampered_plan["skill_name"] = self.catalog.topological_order[1]
        plan_json = canonical_json(tampered_plan)
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(
                "UPDATE runs SET plan_json = ?, plan_sha256 = ?",
                (plan_json, sha256_digest(plan_json.encode("utf-8"))),
            )
        with self.assertRaises(StateConflict):
            self.store.get_run("tenant-a", "project-a", "run-a")

        event_db = Path(self.temporary.name) / "event-tamper.sqlite3"
        event_store = RunStore(event_db, registry=self.registry)
        event_request = validate_request(request_for(self.skill_name, run_id="event-run", idempotency_key="event-idem"))
        event_run = event_store.create_run(event_request, self.registry.dispatch(event_request))
        with closing(sqlite3.connect(event_db)) as connection, connection:
            connection.execute("DROP TRIGGER run_events_no_update")
            row = connection.execute("SELECT * FROM run_events").fetchone()
            payload = {
                "idempotency_key": "forged-idempotency",
                "request_sha256": event_run.request_sha256,
                "plan_sha256": event_run.plan_sha256,
            }
            body = RunStore._event_body(
                tenant_id=row[1], project_id=row[2], run_id=row[3], event_type=row[4],
                actor_id=row[5], from_state=row[6], to_state=row[7], run_version=row[8],
                occurred_at=row[9], previous_sha256=row[10], payload=payload,
            )
            connection.execute(
                "UPDATE run_events SET payload_json = ?, event_sha256 = ?",
                (canonical_json(payload), sha256_digest(canonical_json(body).encode("utf-8"))),
            )
        with self.assertRaises(StateConflict):
            event_store.get_run("tenant-a", "project-a", "event-run")
        with self.assertRaises(StateConflict):
            event_store.pause(
                "tenant-a", "project-a", "event-run", actor_id="actor-b", expected_version=1
            )
        with closing(sqlite3.connect(event_db)) as connection:
            state, version = connection.execute("SELECT state, version FROM runs").fetchone()
            event_count = connection.execute("SELECT COUNT(*) FROM run_events").fetchone()[0]
        self.assertEqual((state, version, event_count), (ACTIVE, 1, 1))

    def test_rehashed_full_plan_semantic_tampering_blocks_get_evaluate_and_transition(self) -> None:
        def replace(field: str, value: object):
            return lambda plan: plan.__setitem__(field, value)

        def mutate_source(plan: dict[str, object]) -> None:
            plan["source"]["version"] = "9.9.9"

        def mutate_target(plan: dict[str, object]) -> None:
            plan["target"]["version"] = "9.9.9"

        def mutate_dependencies(plan: dict[str, object]) -> None:
            plan["dependencies"].append(
                {
                    "skill_name": "rich-type-attribution",
                    "dependency_kinds": ["declared"],
                    "status": "NOT_RUN",
                }
            )

        def mutate_outputs(plan: dict[str, object]) -> None:
            plan["output_blueprints"].append(
                {
                    "name": "forged.json",
                    "media_type": "application/json",
                    "materialized": False,
                    "status": "NOT_RUN",
                    "producer": "EXTERNAL_ADAPTER_REQUIRED",
                }
            )

        def mutate_catalog_digest(plan: dict[str, object]) -> None:
            plan["catalog"]["compiled_contracts_sha256"] = "sha256:" + "0" * 64

        def mutate_batch_dependencies(plan: dict[str, object]) -> None:
            plan["batch_dependencies"].append({"batch": "F01", "status": "NOT_RUN"})

        attacks = {
            "source_id": replace("source_id", "FOUNDATION-01-forged-source"),
            "objective": replace("objective", "Forged migration objective"),
            "source": mutate_source,
            "target": mutate_target,
            "dependencies": mutate_dependencies,
            "output_blueprints": mutate_outputs,
            "source_contract_sha256": replace("source_contract_sha256", "sha256:" + "0" * 64),
            "catalog.compiled_contracts_sha256": mutate_catalog_digest,
            "batch": replace("batch", "F02"),
            "batch_dependencies": mutate_batch_dependencies,
        }
        for index, (field, mutate) in enumerate(attacks.items()):
            with self.subTest(field=field):
                database = Path(self.temporary.name) / f"full-plan-tamper-{index}.sqlite3"
                store = RunStore(database, registry=self.registry)
                request = validate_request(
                    request_for(
                        self.skill_name,
                        run_id=f"tamper-run-{index}",
                        task_id=f"tamper-task-{index}",
                        idempotency_key=f"tamper-idem-{index}",
                    )
                )
                plan = self.registry.dispatch(request)
                store.create_run(request, plan)
                tampered_plan = copy.deepcopy(plan)
                mutate(tampered_plan)
                self._rewrite_plan_and_creation_event(database, tampered_plan)

                operations = {
                    "get": lambda: store.get_run("tenant-a", "project-a", request.run_id),
                    "evaluate": lambda: store.evaluate_readiness("tenant-a", "project-a", request.run_id),
                    "transition": lambda: store.pause(
                        "tenant-a", "project-a", request.run_id,
                        actor_id="actor-b", expected_version=1,
                    ),
                }
                for operation_name, operation in operations.items():
                    with self.subTest(field=field, operation=operation_name), self.assertRaises(StateConflict):
                        operation()
                with closing(sqlite3.connect(database)) as connection:
                    state, version = connection.execute("SELECT state, version FROM runs").fetchone()
                    event_count = connection.execute("SELECT COUNT(*) FROM run_events").fetchone()[0]
                self.assertEqual((state, version, event_count), (ACTIVE, 1, 1))

    def test_rehashed_evidence_role_authorization_and_scope_rewrites_fail_closed(self) -> None:
        request, _, run = self._create()
        payload = {
            "authorization_id": "auth-a",
            "executor_id": "executor-a",
            "verifier_id": "verifier-a",
            "request_sha256": run.request_sha256,
            "schema_version": "elmos.spring-golden-route.request.v1",
        }
        self.store.record_evidence(
            "tenant-a", "project-a", "run-a",
            evidence_id="evidence-request", role="request", payload=payload,
            executor_id="executor-a", verifier_id="verifier-a", authorization_id="auth-a",
        )
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("DROP TRIGGER evidence_records_no_update")
            forged_payload = {
                "authorization_id": "auth-z",
                "executor_id": "executor-a",
                "verifier_id": "verifier-a",
                "request_sha256": request.digest,
                "schema_version": "elmos.spring-golden-route.request.v1",
            }
            forged_json = canonical_json(forged_payload)
            connection.execute(
                """
                UPDATE evidence_records SET role = 'plan', authorization_id = 'auth-z',
                    payload_json = ?, payload_sha256 = ?, byte_count = ?
                """,
                (forged_json, sha256_digest(forged_json.encode("utf-8")), len(forged_json.encode("utf-8"))),
            )
        with self.assertRaises(EvidenceValidationError):
            self.store.list_evidence("tenant-a", "project-a", "run-a")

        scope_db = Path(self.temporary.name) / "evidence-scope.sqlite3"
        scope_store = RunStore(scope_db, registry=self.registry)
        scope_request = validate_request(request_for(self.skill_name, run_id="scope-run", idempotency_key="scope-idem"))
        scope_run = scope_store.create_run(scope_request, self.registry.dispatch(scope_request))
        scope_store.record_evidence(
            "tenant-a", "project-a", "scope-run",
            evidence_id="evidence-request", role="request",
            payload={
                "authorization_id": "auth-a", "executor_id": "executor-a",
                "verifier_id": "verifier-a", "request_sha256": scope_run.request_sha256,
                "schema_version": "elmos.spring-golden-route.request.v1",
            },
            executor_id="executor-a", verifier_id="verifier-a", authorization_id="auth-a",
        )
        with closing(sqlite3.connect(scope_db)) as connection, connection:
            connection.execute("DROP TRIGGER evidence_records_no_update")
            connection.execute("UPDATE evidence_records SET run_id = 'moved-run'")
        with self.assertRaises(EvidenceValidationError):
            scope_store.list_evidence("tenant-a", "project-a", "scope-run")


if __name__ == "__main__":
    unittest.main()
