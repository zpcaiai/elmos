from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Iterator
import unittest

from elmos_proof_harness.canonical import digest_object
import elmos_proof_harness.postgres as postgres_module
from elmos_proof_harness.contracts import SecurityContext
from elmos_proof_harness.errors import AuthorizationError, ConflictError, StoreError
from elmos_proof_harness.postgres import PostgresStore, postgres_driver_readiness
from elmos_proof_harness.storage import (
    ControlPlaneStore,
    POSTGRES_DELTA_MIGRATION_NAME,
    POSTGRES_DELTA_MIGRATION_SOURCE_DIGEST,
    POSTGRES_DELTA_SCHEMA_VERSION,
    POSTGRES_MIGRATION_SOURCE_DIGEST,
    StorageStatus,
)
from elmos_proof_harness.store import SQLiteStore


class _FakeReadinessCursor:
    def __init__(self, responses: list[dict[str, Any] | None]) -> None:
        self._responses = iter(responses)
        self._current: dict[str, Any] | None = None
        self.statements: list[tuple[str, Any]] = []

    def execute(self, statement: str, parameters: Any = None) -> _FakeReadinessCursor:
        self.statements.append((statement, parameters))
        if statement.lstrip().upper().startswith("SET "):
            self._current = {}
            return self
        self._current = next(self._responses)
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self._current

    def close(self) -> None:
        return None


class _FakeReadinessConnection:
    def __init__(self, responses: list[dict[str, Any] | None]) -> None:
        self.cursor_instance = _FakeReadinessCursor(responses)

    def cursor(self) -> _FakeReadinessCursor:
        return self.cursor_instance

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


class _FakeReadinessStore(PostgresStore):
    def __init__(self, responses: list[dict[str, Any] | None]) -> None:
        self._health_context = SecurityContext(
            "health-tenant", "health-project", "health-actor"
        )
        self.fake_cursor = _FakeReadinessCursor(responses)
        self._authority_dsn = "fake-authority"
        self.fake_authority_connection = _FakeReadinessConnection(
            [
                {
                    "role_name": "authority",
                    "session_role": "authority",
                    "rolsuper": False,
                    "rolbypassrls": False,
                    "rolcreatedb": False,
                    "rolcreaterole": False,
                    "rolreplication": False,
                    "rolcanlogin": True,
                    "database_name": "proof",
                    "system_identifier": "system-a",
                    "in_recovery": False,
                    "transaction_read_only": "off",
                },
                {"exact": True},
                {"exact": True},
                {"exact": True},
                {"exact": True},
                {"exact": True},
                {"exact": True},
                {"exact": True},
                {"exact": True},
            ]
        )

    def _connect_authority(self) -> _FakeReadinessConnection:
        return self.fake_authority_connection

    @contextmanager
    def transaction(
        self, context: SecurityContext | None = None
    ) -> Iterator[_FakeReadinessCursor]:
        if context is None:
            raise AssertionError("readiness must supply its trusted health context")
        yield self.fake_cursor


def _ready_responses() -> list[dict[str, Any] | None]:
    catalog = {
        "relations": [
            [name]
            for name in (
                "runtime_assurance_migrations",
                "runtime_assurance_migration_digest_ledger",
                *postgres_module._DELTA_RELATION_NAMES,
            )
        ],
        "columns": [["tool_result_commits", 1, "tenant_id"]],
        "constraints": [["tool_result_commits", "tool_result_commits_pkey"]],
        "functions": [[name] for name in postgres_module._DELTA_CONTROL_FUNCTION_NAMES],
        "triggers": [
            [f"trigger-{index}"]
            for index in range(2 * len(postgres_module._DELTA_RELATION_NAMES))
        ],
        "indexes": [["tool_result_commits_pkey"]],
        "policies": [[name] for name in postgres_module._DELTA_RELATION_NAMES],
    }
    encoded_catalog = json.dumps(
        catalog,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    control_fingerprint = "sha256:" + hashlib.sha256(
        b"elmos.proof-harness.v3.1\0postgres-control-catalog\0" + encoded_catalog
    ).hexdigest()
    return [
        {
            "role_name": "application",
            "session_role": "application",
            "rolsuper": False,
            "rolbypassrls": False,
            "rolcreatedb": False,
            "rolcreaterole": False,
            "rolreplication": False,
            "rolcanlogin": True,
            "database_name": "proof",
            "system_identifier": "system-a",
            "in_recovery": False,
            "transaction_read_only": "off",
            "server_version_num": "170006",
            "server_version": "17.6",
        },
        {"version": 1},
        {"content_sha256": POSTGRES_MIGRATION_SOURCE_DIGEST},
        {"count": 22},
        {"count": 22},
        {"writable": False},
        {"count": 0},
        {
            "version": POSTGRES_DELTA_SCHEMA_VERSION,
            "migration_name": POSTGRES_DELTA_MIGRATION_NAME,
            "package_version": "3.1.0",
            "required_base_version": 1,
            "required_base_sha256": POSTGRES_MIGRATION_SOURCE_DIGEST,
            "control_fingerprint_sha256": control_fingerprint,
            "content_sha256": POSTGRES_DELTA_MIGRATION_SOURCE_DIGEST,
            "migration_count": 1,
            "ledger_count": 1,
        },
        {"count": len(postgres_module._DELTA_RELATION_NAMES)},
        {
            "count": len(postgres_module._DELTA_RELATION_NAMES),
            "table_count": len(postgres_module._DELTA_RELATION_NAMES),
            "exact": True,
        },
        {"catalog": catalog},
        {"exact": True},
        {"exact": True},
        {"exact": True},
        {"exact": True},
        {"count": 2, "writable": False, "owned": False},
    ]


class StorageProtocolTests(unittest.TestCase):
    def test_sqlite_implements_shared_protocol_and_receipt_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "local-engineering.sqlite3")
            self.addCleanup(store.close)
            self.assertIsInstance(store, ControlPlaneStore)
            context = SecurityContext("tenant-a", "project-a", "actor-a")
            store.register_scope(context)
            request = {"requestId": "request-1"}
            request_sha256 = digest_object(request, domain="test-control-plane-request")
            claimed, receipt = store.claim_control_plane_receipt(
                context,
                operation="invoke",
                idempotency_key="key-1",
                request_sha256=request_sha256,
                run_id="run-1",
                request=request,
            )
            self.assertTrue(claimed)
            replay, replay_receipt = store.claim_control_plane_receipt(
                context,
                operation="invoke",
                idempotency_key="key-1",
                request_sha256=request_sha256,
                run_id="run-1",
                request=request,
            )
            self.assertFalse(replay)
            self.assertEqual(receipt, replay_receipt)
            completed = store.complete_control_plane_receipt(
                context,
                operation="invoke",
                idempotency_key="key-1",
                request_sha256=request_sha256,
                response={"status": "SUCCEEDED"},
            )
            self.assertEqual(completed.response, {"status": "SUCCEEDED"})
            with self.assertRaises(ConflictError):
                store.claim_control_plane_receipt(
                    context,
                    operation="invoke",
                    idempotency_key="key-1",
                    request_sha256=digest_object(
                        {"different": True}, domain="test-control-plane-request"
                    ),
                    run_id="run-2",
                    request={"different": True},
                )
            other_actor = SecurityContext("tenant-a", "project-a", "actor-b")
            store.register_scope(other_actor)
            with self.assertRaises(AuthorizationError):
                store.get_control_plane_receipt(
                    other_actor,
                    operation="invoke",
                    idempotency_key="key-1",
                    request_sha256=request_sha256,
                )

    def test_postgres_backend_is_lazy_and_missing_dsn_fails_closed(self) -> None:
        readiness = postgres_driver_readiness()
        self.assertIn(
            readiness.status,
            {
                StorageStatus.READY,
                StorageStatus.NOT_CONFIGURED,
                StorageStatus.NOT_READY,
            },
        )
        with self.assertRaises(StoreError) as captured:
            PostgresStore.from_environment(environment={})
        self.assertEqual(captured.exception.code, "POSTGRES_NOT_CONFIGURED")

    def test_composite_v31_postgres_readiness_preserves_core_schema_version(
        self,
    ) -> None:
        store = _FakeReadinessStore(_ready_responses())

        readiness = store.readiness()

        self.assertEqual(readiness.status, StorageStatus.READY)
        self.assertEqual(readiness.schema_version, 1)
        self.assertIn("composite v3.1", readiness.reason)
        statements = store.fake_cursor.statements
        delta_ledger = next(
            item for item in statements if "runtime_assurance_migrations m" in item[0]
        )
        self.assertEqual(
            delta_ledger[1],
            (POSTGRES_DELTA_SCHEMA_VERSION, POSTGRES_DELTA_MIGRATION_NAME),
        )
        self.assertTrue(
            any(
                "relforcerowsecurity" in statement
                and "durable_event_registrations" in str(parameters)
                and "pending_tool_call_bindings" in str(parameters)
                for statement, parameters in statements
            )
        )
        self.assertTrue(
            any(
                "runtime_assurance_trusted_scope_isolation" in statement
                and "roles=ARRAY['public']::name[]" in statement
                and all(
                    binding in str(parameters)
                    for binding in (
                        "app.actor_id",
                        "app.run_id",
                        "app.execution_epoch",
                        "app.fencing_generation",
                        "app.authority_revision",
                        "app.revision_set_id",
                    )
                )
                for statement, parameters in statements
            )
        )
        self.assertTrue(
            any(
                "has_table_privilege" in statement
                and "has_any_column_privilege" in statement
                and "runtime_assurance_migration_digest_ledger" in statement
                for statement, _parameters in statements
            )
        )

    def test_composite_v31_postgres_readiness_rejects_every_delta_drift_class(
        self,
    ) -> None:
        cases: tuple[tuple[str, int, str, Any, str], ...] = (
            ("application owns a harness relation", 6, "count", 1, "must not own"),
            ("missing migration row", 7, "migration_count", 0, "ledger"),
            ("extra migration row", 7, "migration_count", 2, "ledger"),
            ("missing ledger row", 7, "ledger_count", 0, "ledger"),
            ("wrong delta version", 7, "version", 303, "ledger"),
            ("wrong delta name", 7, "migration_name", "V304__wrong.sql", "ledger"),
            ("wrong package", 7, "package_version", "3.1.1", "ledger"),
            ("wrong base version", 7, "required_base_version", 2, "ledger"),
            (
                "wrong base digest",
                7,
                "required_base_sha256",
                "sha256:" + "a" * 64,
                "ledger",
            ),
            (
                "wrong delta digest",
                7,
                "content_sha256",
                "sha256:" + "b" * 64,
                "ledger",
            ),
            (
                "wrong control fingerprint",
                7,
                "control_fingerprint_sha256",
                "sha256:" + "c" * 64,
                "ledger",
            ),
            ("missing forced RLS", 8, "count", 12, "forced RLS"),
            ("extra policy", 9, "count", 14, "policy set"),
            ("missing table policy", 9, "table_count", 12, "policy set"),
            ("policy semantics drift", 9, "exact", False, "policy set"),
            ("delta relation ACL drift", 11, "exact", False, "ACLs"),
            ("support ACL drift", 13, "exact", False, "support ACLs"),
            ("owner membership or CREATE", 14, "exact", False, "assume ownership"),
            ("missing metadata relation", 15, "count", 1, "own or write"),
            ("metadata writable", 15, "writable", True, "own or write"),
            ("metadata app-owned", 15, "owned", True, "own or write"),
        )
        for label, response_index, field, value, reason in cases:
            with self.subTest(label=label):
                responses = deepcopy(_ready_responses())
                response = responses[response_index]
                self.assertIsNotNone(response)
                assert response is not None
                response[field] = value
                readiness = _FakeReadinessStore(responses).readiness()
                self.assertEqual(readiness.status, StorageStatus.NOT_READY)
                self.assertEqual(readiness.schema_version, 1)
                self.assertIn(reason, readiness.reason)

    def test_migration_contains_production_guards(self) -> None:
        migration = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "V001__proof_harness_core.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("FORCE ROW LEVEL SECURITY", migration)
        self.assertIn("proof_harness.current_tenant_key()", migration)
        self.assertIn("proof_harness.current_project_key()", migration)
        self.assertIn("content_bytes bytea NOT NULL", migration)
        self.assertIn("runtime_evidence_immutable", migration)
        self.assertIn("external_signature_receipts", migration)
        self.assertIn(
            "attested_status <> 'CERTIFIED' OR certification_authority", migration
        )
        self.assertNotIn("object_uri text NOT NULL", migration)


if __name__ == "__main__":
    unittest.main()
