from __future__ import annotations

from contextlib import redirect_stderr
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from elmos_proof_harness.storage import (
    POSTGRES_DELTA_MIGRATION_NAME,
    POSTGRES_DELTA_MIGRATION_SOURCE_DIGEST,
    POSTGRES_DELTA_SCHEMA_VERSION,
    POSTGRES_MIGRATION_SOURCE_DIGEST,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "V304__harness_runtime_assurance_delta.sql"
TOOL = ROOT / "tools" / "apply_delta_migration.py"
BASE_DIGEST = POSTGRES_MIGRATION_SOURCE_DIGEST


def _load_tool() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "apply_delta_migration", TOOL
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("delta migration applicator could not be loaded")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class _FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = list(rows)
        self.executions: list[tuple[str, object | None]] = []

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_arguments: object) -> None:
        return None

    def execute(self, sql: str, parameters: object | None = None) -> _FakeCursor:
        self.executions.append((sql, parameters))
        return self

    @property
    def rowcount(self) -> int:
        return 1

    def fetchone(self) -> tuple[object, ...] | None:
        if not self.rows:
            return None
        return self.rows.pop(0)


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *_arguments: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class _FakeDriver:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection
        self.calls: list[tuple[str, bool]] = []

    def connect(self, dsn: str, *, autocommit: bool) -> _FakeConnection:
        self.calls.append((dsn, autocommit))
        return self.connection


def _authority_row(*, can_create: bool = True) -> tuple[object, ...]:
    return (
        "proof_harness_migration_owner",
        "deployment_login",
        False,
        False,
        False,
        False,
        False,
        False,
        can_create,
        True,
    )


def _catalog_payload(tool: ModuleType) -> dict[str, list[object]]:
    relations = [
        tool.METADATA_RELATION.rsplit(".", 1)[1],
        tool.LEDGER_RELATION.rsplit(".", 1)[1],
        *(name.rsplit(".", 1)[1] for name in tool.DELTA_RELATIONS),
    ]
    return {
        "relations": [[name] for name in relations],
        "columns": [["tool_result_commits", 1, "tenant_id"]],
        "constraints": [["tool_result_commits", "tool_result_commits_pkey"]],
        "functions": [[name] for name in tool.CONTROL_FUNCTIONS],
        "triggers": [[name] for name in tool.CONTROL_TRIGGERS],
        "indexes": [[name] for name in tool.CONTROL_INDEXES],
        "policies": [[name] for name in tool.DELTA_RELATIONS],
    }


def _catalog_digest(tool: ModuleType) -> str:
    encoded = json.dumps(
        _catalog_payload(tool),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(
        b"elmos.proof-harness.v3.1\0postgres-control-catalog\0" + encoded
    ).hexdigest()


class DeltaMigrationAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = _load_tool()
        cls.sql = MIGRATION.read_text(encoding="utf-8")

    def test_migration_is_scoped_constrained_and_fail_closed(self) -> None:
        self.assertIn("PostgreSQL 17", self.sql)
        self.assertIn("runtime_assurance_migrations", self.sql)
        self.assertIn("runtime_assurance_migration_digest_ledger", self.sql)
        self.assertIn(BASE_DIGEST, self.sql)
        self.assertIn("V001__proof_harness_core.sql", self.sql)
        self.assertIn("FORCE ROW LEVEL SECURITY", self.sql)
        self.assertIn("proof_harness.current_tenant_key()", self.sql)
        self.assertIn("proof_harness.current_project_key()", self.sql)
        self.assertIn("runtime_assurance_trusted_scope_isolation", self.sql)
        self.assertIn("ON DELETE RESTRICT", self.sql)
        self.assertNotIn("ON DELETE CASCADE", self.sql)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS", self.sql)
        self.assertNotRegex(self.sql, r"(?im)^\s*(BEGIN|COMMIT|ROLLBACK)\s*;")

        relations = (
            "tool_result_commits",
            "step_execution_plans",
            "capability_leases",
            "executor_generations",
            "environment_attachments",
            "executor_replacement_effects",
            "workspace_leases",
            "durable_event_registrations",
            "durable_event_instances",
            "typed_ingress_records",
            "subagent_execution_specs",
            "runtime_assurance_invocation_receipts",
        )
        for relation in relations:
            declaration = f"CREATE TABLE proof_harness_runtime.{relation}"
            self.assertIn(declaration, self.sql)
            start = self.sql.index(declaration)
            end = self.sql.index(";", start)
            table_sql = self.sql[start:end]
            self.assertIn("tenant_id text NOT NULL", table_sql, relation)
            self.assertIn("project_id text NOT NULL", table_sql, relation)
            self.assertIn("actor_id text NOT NULL", table_sql, relation)
            self.assertIn("run_id text NOT NULL", table_sql, relation)
            self.assertIn("execution_epoch bigint NOT NULL", table_sql, relation)
            self.assertIn("fencing_generation bigint NOT NULL", table_sql, relation)
            self.assertIn("authority_revision text NOT NULL", table_sql, relation)
            self.assertIn("revision_set_id text NOT NULL", table_sql, relation)
            self.assertIn(
                "REFERENCES proof_harness_runtime.actors", table_sql, relation
            )
            self.assertIn(
                f"REVOKE ALL ON proof_harness_runtime.{relation} FROM PUBLIC",
                self.sql,
            )
            self.assertIn(f"CREATE TRIGGER {relation}_scope_guard", self.sql)
            self.assertIn(
                f"BEFORE INSERT OR UPDATE ON proof_harness_runtime.{relation}",
                self.sql,
            )
        self.assertIn(
            "authority_revision, revision_set_id, invocation_id\n  )",
            self.sql,
        )
        self.assertIn(
            "typed_ingress_records_persisted_sequence_seq",
            self.tool.SUPPORT_RELATIONS[0],
        )

    def test_relation_dependent_functions_follow_their_table(self) -> None:
        table = self.sql.index(
            "CREATE TABLE proof_harness_runtime."
            "runtime_assurance_invocation_receipts"
        )
        for function in (
            "is_live_runtime_assurance_claim",
            "assert_runtime_application_writer",
        ):
            declaration = self.sql.index(
                f"CREATE OR REPLACE FUNCTION proof_harness_runtime.{function}"
            )
            self.assertGreater(declaration, table, function)

    def test_lifecycle_and_content_guards_are_explicit(self) -> None:
        for guard in (
            "guard_tool_result_commit",
            "guard_step_execution_plan",
            "guard_capability_lease",
            "guard_executor_generation",
            "guard_environment_attachment",
            "guard_executor_replacement_effect",
            "guard_workspace_lease",
            "guard_durable_event_instance",
            "guard_subagent_execution_spec",
            "guard_runtime_assurance_invocation_receipt",
        ):
            self.assertIn(f"FUNCTION proof_harness_runtime.{guard}()", self.sql)
            self.assertIn(
                f"REVOKE EXECUTE ON FUNCTION proof_harness_runtime.{guard}()", self.sql
            )
        self.assertIn("durable_event_registrations_immutable", self.sql)
        self.assertIn("typed_ingress_records_immutable", self.sql)
        self.assertIn("subagent_execution_specs_lifecycle_guard", self.sql)
        self.assertIn("is_valid_interceptor_chain", self.sql)
        self.assertIn("is_bounded_text_array", self.sql)
        self.assertIn("^sha256:[0-9a-f]{64}$", self.sql)
        self.assertIn("invalid capability lease state transition", self.sql)
        self.assertIn("invalid executor generation state transition", self.sql)
        self.assertIn("invalid workspace lease state transition", self.sql)
        self.assertIn("capability_leases_active_invocation_idx", self.sql)
        self.assertIn("executor_generations_one_active_environment", self.sql)
        self.assertIn("workspace_leases_one_active_owner", self.sql)
        self.assertIn("typed_ingress_records_dedup_unique", self.sql)
        self.assertIn("subagent_execution_specs_budget_unique", self.sql)
        self.assertIn(
            "OLD.state = 'COMMITTED' AND NEW.state IN ('PUBLISHED', 'ABORTED')",
            self.sql,
        )
        self.assertNotIn("OLD.state = 'PUBLISHED'", self.sql)
        self.assertIn("jsonb_array_length(capability_set) >= 1", self.sql)
        self.assertIn("is_valid_workspace_scopes(write_scopes)", self.sql)
        self.assertIn(
            "OLD.state = 'RAW_CAPTURED' AND NEW.state IN ('INTERCEPTING', 'ABORTED')",
            self.sql,
        )
        self.assertIn(
            "OLD.state = 'INTERCEPTING' AND NEW.state IN ('COMMITTED', 'ABORTED')",
            self.sql,
        )
        self.assertIn("invalid subagent budget consumption transition", self.sql)
        self.assertIn("current_setting('app.authority_revision', true)", self.sql)
        self.assertIn("current_setting('app.revision_set_id', true)", self.sql)
        self.assertIn("runtime_assurance_trusted_scope_isolation", self.sql)
        for field in (
            "tenant_id",
            "project_id",
            "actor_id",
            "run_id",
            "execution_epoch",
            "fencing_generation",
            "authority_revision",
            "revision_set_id",
        ):
            self.assertIn(f"OLD.{field} IS DISTINCT FROM NEW.{field}", self.sql)
        self.assertIn("CREATE UNIQUE INDEX capability_leases_active_invocation_idx", self.sql)
        self.assertIn("workspace_leases_one_live_repository_base", self.sql)
        self.assertIn("count(DISTINCT effect.kind)", self.sql)
        self.assertIn("required_replacement_effect_kind_count <> 3", self.sql)
        self.assertIn("succeeded_replacement_effect_count <> 3", self.sql)
        self.assertIn(
            "advanced executor activation requires exactly three succeeded reconciliation effects",
            self.sql,
        )
        self.assertIn("clock_timestamp() >= OLD.wall_clock_deadline", self.sql)
        self.assertIn("octet_length(candidate ->> bounded_field.field_name)", self.sql)
        self.assertIn("octet_length(element #>> '{}')", self.sql)

    def test_detached_digest_is_exact_in_tool_and_storage(self) -> None:
        source = MIGRATION.read_bytes()
        observed = (
            "sha256:"
            + hashlib.sha256(
                b"elmos.proof-harness.v3.1\0postgres-migration-file\0" + source
            ).hexdigest()
        )
        self.assertEqual(observed, POSTGRES_DELTA_MIGRATION_SOURCE_DIGEST)
        self.assertEqual(observed, self.tool.EXPECTED_SOURCE_DIGEST)
        self.assertEqual(POSTGRES_DELTA_SCHEMA_VERSION, self.tool.SCHEMA_VERSION)
        self.assertEqual(POSTGRES_DELTA_MIGRATION_NAME, self.tool.MIGRATION_NAME)

    def test_applicator_rejects_symlinks_and_modified_bytes_before_database_access(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "source.sql"
            target.write_bytes(MIGRATION.read_bytes())
            link = root / POSTGRES_DELTA_MIGRATION_NAME
            link.symlink_to(target)
            with self.assertRaises(self.tool.MigrationRejected):
                self.tool._read_once(link)

            link.unlink()
            link.write_bytes(MIGRATION.read_bytes() + b"\n-- changed\n")
            with self.assertRaisesRegex(
                self.tool.MigrationRejected,
                "digest does not match",
            ):
                self.tool._migration_sql(link)

    def test_applicator_applies_once_under_lock_and_records_digest(self) -> None:
        rows = [
            (170000,),
            _authority_row(),
            (
                "schema_migrations",
                "migration_digest_ledger",
                "projects",
                "actors",
                "runs",
            ),
            (True,),
            (self.tool.BASE_MIGRATION_NAME, self.tool.BASE_SOURCE_DIGEST),
            (None,)
            * (2 + len(self.tool.DELTA_RELATIONS) + len(self.tool.SUPPORT_RELATIONS)),
            (True,),
            (_catalog_payload(self.tool),),
        ]
        cursor = _FakeCursor(rows)
        connection = _FakeConnection(cursor)
        driver = _FakeDriver(connection)
        with patch.object(self.tool, "_load_driver", return_value=driver):
            result = self.tool.apply(
                dsn="postgresql://credential-not-emitted",
                expected_owner_role="proof_harness_migration_owner",
                migration_path=MIGRATION,
            )
        self.assertEqual(result["status"], "APPLIED")
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertIn(
            ("SELECT pg_advisory_xact_lock(%s)", (self.tool.ADVISORY_LOCK_KEY,)),
            cursor.executions,
        )
        catalog_index = next(
            index
            for index, execution in enumerate(cursor.executions)
            if execution[0] == self.tool._CATALOG_FINGERPRINT_SQL
        )
        self.assertEqual(
            cursor.executions[catalog_index - 1],
            ("SET LOCAL search_path = pg_catalog", None),
        )
        ledger_writes = [
            execution
            for execution in cursor.executions
            if "INSERT INTO proof_harness_runtime.runtime_assurance_migration_digest_ledger"
            in execution[0]
        ]
        self.assertEqual(len(ledger_writes), 1)
        self.assertNotIn("credential-not-emitted", json.dumps(result))

    def test_applicator_replays_only_an_exact_complete_install(self) -> None:
        installed = ("present",) * (
            2 + len(self.tool.DELTA_RELATIONS) + len(self.tool.SUPPORT_RELATIONS)
        )
        rows = [
            (170000,),
            _authority_row(),
            (
                "schema_migrations",
                "migration_digest_ledger",
                "projects",
                "actors",
                "runs",
            ),
            (True,),
            (self.tool.BASE_MIGRATION_NAME, self.tool.BASE_SOURCE_DIGEST),
            installed,
            (
                self.tool.PACKAGE_VERSION,
                self.tool.BASE_SCHEMA_VERSION,
                self.tool.BASE_SOURCE_DIGEST,
                _catalog_digest(self.tool),
                self.tool.EXPECTED_SOURCE_DIGEST,
            ),
            (True,),
            (_catalog_payload(self.tool),),
        ]
        cursor = _FakeCursor(rows)
        connection = _FakeConnection(cursor)
        with patch.object(
            self.tool,
            "_load_driver",
            return_value=_FakeDriver(connection),
        ):
            result = self.tool.apply(
                dsn="postgresql://credential-not-emitted",
                expected_owner_role="proof_harness_migration_owner",
                migration_path=MIGRATION,
            )
        self.assertEqual(result["status"], "ALREADY_APPLIED")
        self.assertTrue(connection.rolled_back)
        self.assertFalse(connection.committed)
        self.assertFalse(
            any(self.sql in execution[0] for execution in cursor.executions)
        )

    def test_applicator_rejects_a_ledgered_install_with_missing_controls(self) -> None:
        installed = ("present",) * (
            2 + len(self.tool.DELTA_RELATIONS) + len(self.tool.SUPPORT_RELATIONS)
        )
        rows = [
            (170000,),
            _authority_row(),
            (
                "schema_migrations",
                "migration_digest_ledger",
                "projects",
                "actors",
                "runs",
            ),
            (True,),
            (self.tool.BASE_MIGRATION_NAME, self.tool.BASE_SOURCE_DIGEST),
            installed,
            (
                self.tool.PACKAGE_VERSION,
                self.tool.BASE_SCHEMA_VERSION,
                self.tool.BASE_SOURCE_DIGEST,
                _catalog_digest(self.tool),
                self.tool.EXPECTED_SOURCE_DIGEST,
            ),
            (False,),
        ]
        connection = _FakeConnection(_FakeCursor(rows))
        with patch.object(
            self.tool,
            "_load_driver",
            return_value=_FakeDriver(connection),
        ):
            with self.assertRaisesRegex(
                self.tool.MigrationRejected,
                "controls are incomplete",
            ):
                self.tool.apply(
                    dsn="postgresql://credential-not-emitted",
                    expected_owner_role="proof_harness_migration_owner",
                    migration_path=MIGRATION,
                )

    def test_applicator_rejects_service_roles_and_redacts_connection_failures(
        self,
    ) -> None:
        for role in (
            "proof_harness_app",
            "proof_harness_scheduler",
            "proof_harness_runtime",
            "proof_harness_worker",
        ):
            with (
                self.subTest(role=role),
                self.assertRaises(self.tool.MigrationRejected),
            ):
                self.tool._validate_owner_role(role)

        class _FailingDriver:
            @staticmethod
            def connect(_dsn: str, *, autocommit: bool) -> object:
                del autocommit
                raise RuntimeError("postgresql://user:secret@example.invalid/database")

        with patch.object(self.tool, "_load_driver", return_value=_FailingDriver()):
            with self.assertRaises(self.tool.MigrationRejected) as captured:
                self.tool.apply(
                    dsn="postgresql://user:secret@example.invalid/database",
                    expected_owner_role="proof_harness_migration_owner",
                    migration_path=MIGRATION,
                )
        self.assertNotIn("secret", str(captured.exception))
        self.assertNotIn("example.invalid", str(captured.exception))

    def test_cli_missing_dsn_fails_without_echoing_environment(self) -> None:
        stream = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(stream):
            code = self.tool.main(
                ["--expected-owner-role", "proof_harness_migration_owner"]
            )
        self.assertEqual(code, 2)
        output = json.loads(stream.getvalue())
        self.assertEqual(output["status"], "FAILED")
        self.assertEqual(output["code"], "MIGRATION_REJECTED")
        self.assertNotIn("postgresql://", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
