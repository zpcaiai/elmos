import contextlib
import datetime as dt
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap_pre_v9_audit_events as subject


NOW = dt.datetime(2026, 8, 26, 0, 0, tzinfo=dt.timezone.utc)


def migrations():
    return tuple(
        subject.MigrationSpec(
            installed_rank=version,
            version=str(version),
            description=f"migration {version}",
            script=f"V{version}__migration_{version}.sql",
            checksum=version * 101,
            source_sha256=f"{version:064x}",
        )
        for version in range(1, 9)
    )


def history(items=None):
    source = migrations() if items is None else items
    return tuple(
        subject.HistoryRow(
            installed_rank=item.installed_rank,
            version=item.version,
            description=item.description,
            migration_type="SQL",
            script=item.script,
            checksum=item.checksum,
            success=True,
        )
        for item in source
    )


def snapshot(
    *,
    history_rows=None,
    columns=None,
    triggers=(),
    null_exists=False,
    non_system_exists=False,
):
    return subject.CatalogSnapshot(
        target_material="elmos_test\x00170000\x00127.0.0.1\x005432",
        server_version_num="170000",
        history_table_present=True,
        audit_table_present=True,
        history=history() if history_rows is None else tuple(history_rows),
        columns=(
            subject.EXPECTED_BASE_COLUMNS if columns is None else tuple(columns)
        ),
        primary_key_columns=("audit_id",),
        triggers=tuple(triggers),
        organization_null_exists=null_exists,
        organization_non_system_exists=non_system_exists,
    )


def assessment(**kwargs):
    return subject.evaluate_snapshot(snapshot(**kwargs), migrations())


class RecordingCursor:
    def __init__(self):
        self.executions = []
        self.rowcount = 0

    def execute(self, query, parameters=None):
        normalized = " ".join(query.split())
        self.executions.append((normalized, parameters))
        if normalized.startswith("UPDATE public.audit_events"):
            self.rowcount = 7

    def fetchone(self):
        raise AssertionError("catalog reads are patched in this test")

    def fetchall(self):
        raise AssertionError("catalog reads are patched in this test")

    def close(self):
        pass


class RecordingConnection:
    def __init__(self):
        self.recording_cursor = RecordingCursor()
        self.closed = False

    def cursor(self):
        return self.recording_cursor

    def close(self):
        self.closed = True


class PreV9AuditBootstrapTest(unittest.TestCase):
    def test_dry_run_is_read_only_and_returns_target_bound_confirmation(self):
        connection = RecordingConnection()
        ready = assessment()
        with patch.object(subject, "assess_database", return_value=ready):
            receipt = subject.perform(
                dsn="postgresql://redacted",
                apply=False,
                confirmation=None,
                migrations=migrations(),
                connector=lambda _dsn, _timeout: connection,
                now=lambda: NOW,
            )

        statements = [item[0] for item in connection.recording_cursor.executions]
        self.assertEqual("READY_TO_APPLY", receipt["decision"])
        self.assertEqual("ASSESS", receipt["mode"])
        self.assertIn("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY", statements)
        self.assertEqual("ROLLBACK", statements[-1])
        self.assertFalse(any(statement.startswith("ALTER TABLE") for statement in statements))
        self.assertFalse(any(statement.startswith("UPDATE ") for statement in statements))
        self.assertFalse(any("ACCESS EXCLUSIVE" in statement for statement in statements))
        self.assertFalse(receipt["production_certified"])
        self.assertEqual("NOT_CERTIFIED", receipt["certification_status"])
        self.assertRegex(receipt["target"]["fingerprint_sha256"], r"^[0-9a-f]{64}$")

    def test_apply_requires_explicit_environment_confirmation_before_connect(self):
        called = False

        def connector(_dsn, _timeout):
            nonlocal called
            called = True
            return RecordingConnection()

        with self.assertRaises(subject.BootstrapBlocked) as raised:
            subject.perform(
                dsn="postgresql://redacted",
                apply=True,
                confirmation=None,
                migrations=migrations(),
                connector=connector,
            )
        self.assertEqual("APPLY_CONFIRMATION_REQUIRED", raised.exception.code)
        self.assertFalse(called)

    def test_wrong_or_drifted_flyway_history_blocks(self):
        wrong = list(history())
        wrong[-1] = subject.HistoryRow(
            installed_rank=8,
            version="9",
            description="migration 9",
            migration_type="SQL",
            script="V9__migration_9.sql",
            checksum=909,
            success=True,
        )
        result = assessment(history_rows=wrong)
        self.assertEqual("BLOCKED", result.state)
        self.assertIn("FLYWAY_HISTORY_NOT_EXACT_V1_TO_V8", result.blockers)

        failed = list(history())
        failed[3] = subject.dataclasses.replace(failed[3], success=False)
        result = assessment(history_rows=failed)
        self.assertIn("FLYWAY_HISTORY_NOT_EXACT_V1_TO_V8", result.blockers)

    def test_preexisting_conflicting_organization_column_blocks(self):
        conflicting = subject.dataclasses.replace(
            subject._organization_column(nullable=True), maximum_length=64
        )
        result = assessment(
            columns=(*subject.EXPECTED_BASE_COLUMNS, conflicting),
            null_exists=True,
        )
        self.assertEqual("BLOCKED", result.state)
        self.assertIn("ORGANIZATION_ID_COLUMN_CONFLICT", result.blockers)

    def test_v9_append_only_trigger_blocks_before_any_write(self):
        trigger = subject.TriggerState(
            "audit_events_append_only",
            "public",
            "elmos_forbid_append_only_mutation",
            "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE",
        )
        result = assessment(triggers=(trigger,))
        self.assertEqual("BLOCKED", result.state)
        self.assertIn("V9_APPEND_ONLY_TRIGGER_PRESENT", result.blockers)

    def test_already_prepared_requires_not_null_and_only_org_system_values(self):
        prepared_columns = (
            *subject.EXPECTED_BASE_COLUMNS,
            subject._organization_column(nullable=False),
        )
        result = assessment(columns=prepared_columns)
        self.assertEqual("ALREADY_PREPARED", result.state)
        self.assertEqual((), result.blockers)

        conflict = assessment(columns=prepared_columns, non_system_exists=True)
        self.assertEqual("BLOCKED", conflict.state)
        self.assertIn("ORGANIZATION_ID_HAS_NON_SYSTEM_VALUE", conflict.blockers)

    def test_apply_uses_one_locked_transaction_and_reconciles(self):
        connection = RecordingConnection()
        ready = assessment()
        prepared = assessment(
            columns=(
                *subject.EXPECTED_BASE_COLUMNS,
                subject._organization_column(nullable=False),
            )
        )
        confirmation = subject.expected_confirmation(ready.snapshot)
        with patch.object(
            subject, "assess_database", side_effect=(ready, prepared)
        ) as assess_mock:
            receipt = subject.perform(
                dsn="postgresql://redacted",
                apply=True,
                confirmation=confirmation,
                v9_source_confirmation=subject.expected_v9_source_confirmation(
                    subject.discover_v9_source_guard()
                ),
                durable_receipt_reserved=True,
                migrations=migrations(),
                connector=lambda _dsn, _timeout: connection,
                now=lambda: NOW,
            )

        statements = [item[0] for item in connection.recording_cursor.executions]
        self.assertEqual(2, assess_mock.call_count)
        self.assertEqual("BEGIN ISOLATION LEVEL SERIALIZABLE READ WRITE", statements[0])
        advisory_index = next(
            index for index, value in enumerate(statements) if "pg_advisory_xact_lock" in value
        )
        lock_index = next(
            index for index, value in enumerate(statements) if "ACCESS EXCLUSIVE" in value
        )
        add_index = statements.index(
            "ALTER TABLE public.audit_events ADD COLUMN organization_id varchar(96)"
        )
        update_index = next(
            index for index, value in enumerate(statements) if value.startswith("UPDATE public.audit_events")
        )
        not_null_index = statements.index(
            "ALTER TABLE public.audit_events ALTER COLUMN organization_id SET NOT NULL"
        )
        self.assertLess(advisory_index, lock_index)
        self.assertLess(lock_index, add_index)
        self.assertLess(add_index, update_index)
        self.assertLess(update_index, not_null_index)
        self.assertEqual("COMMIT", statements[-1])
        self.assertEqual("APPLIED", receipt["decision"])
        self.assertEqual(7, receipt["mutation"]["rows_bound_to_org_system"])
        self.assertTrue(receipt["mutation"]["column_added"])
        self.assertFalse(receipt["mutation"]["flyway_history_modified"])
        self.assertFalse(any(statement.startswith("DELETE ") for statement in statements))
        self.assertFalse(
            any(
                statement.startswith("UPDATE public.flyway_schema_history")
                or statement.startswith("INSERT INTO public.flyway_schema_history")
                for statement in statements
            )
        )

    def test_apply_cli_requires_a_durable_receipt_before_connecting(self):
        called = False

        def connector(_dsn, _timeout):
            nonlocal called
            called = True
            return RecordingConnection()

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            exit_code = subject.main(
                ["--apply"],
                environ={
                    subject.DATABASE_URL_ENV: "postgresql://redacted",
                    subject.CONFIRMATION_ENV: subject.CONFIRMATION_PREFIX + "0" * 64,
                    subject.V9_SOURCE_CONFIRMATION_ENV: (
                        subject.V9_SOURCE_CONFIRMATION_PREFIX + "0" * 64
                    ),
                },
                connector=connector,
                now=lambda: NOW,
            )

        self.assertEqual(2, exit_code)
        self.assertFalse(called)
        self.assertEqual(
            ["APPLY_RECEIPT_REQUIRED"], json.loads(output.getvalue())["blockers"]
        )

    def test_apply_api_requires_a_reserved_receipt_before_connecting(self):
        called = False

        def connector(_dsn, _timeout):
            nonlocal called
            called = True
            return RecordingConnection()

        with self.assertRaises(subject.BootstrapBlocked) as raised:
            subject.perform(
                dsn="postgresql://redacted",
                apply=True,
                confirmation=subject.CONFIRMATION_PREFIX + "0" * 64,
                v9_source_confirmation=subject.expected_v9_source_confirmation(
                    subject.discover_v9_source_guard()
                ),
                durable_receipt_reserved=False,
                migrations=migrations(),
                connector=connector,
                now=lambda: NOW,
            )

        self.assertEqual(
            "APPLY_RECEIPT_RESERVATION_REQUIRED", raised.exception.code
        )
        self.assertFalse(called)

    def test_commit_acknowledgement_loss_preserves_unknown_outcome(self):
        class AmbiguousCommitCursor(RecordingCursor):
            def execute(self, query, parameters=None):
                normalized = " ".join(query.split())
                if normalized == "COMMIT":
                    self.executions.append((normalized, parameters))
                    raise OSError("connection lost after commit was sent")
                return super().execute(query, parameters)

        class AmbiguousCommitConnection(RecordingConnection):
            def __init__(self):
                super().__init__()
                self.recording_cursor = AmbiguousCommitCursor()

        connection = AmbiguousCommitConnection()
        ready = assessment()
        prepared = assessment(
            columns=(
                *subject.EXPECTED_BASE_COLUMNS,
                subject._organization_column(nullable=False),
            )
        )
        with patch.object(subject, "assess_database", side_effect=(ready, prepared)):
            receipt = subject.perform(
                dsn="postgresql://redacted",
                apply=True,
                confirmation=subject.expected_confirmation(ready.snapshot),
                v9_source_confirmation=subject.expected_v9_source_confirmation(
                    subject.discover_v9_source_guard()
                ),
                durable_receipt_reserved=True,
                migrations=migrations(),
                connector=lambda _dsn, _timeout: connection,
                now=lambda: NOW,
            )

        self.assertEqual("OUTCOME_UNKNOWN", receipt["decision"])
        self.assertEqual("COMMIT_SENT", receipt["mutation"]["phase"])
        self.assertTrue(receipt["mutation"]["attempted"])
        self.assertTrue(receipt["mutation"]["rollback_attempted"])
        self.assertTrue(receipt["mutation"]["rollback_acknowledged"])
        self.assertFalse(receipt["mutation"]["rollback_confirmed"])
        self.assertTrue(receipt["mutation"]["reconciliation_required"])
        self.assertFalse(receipt["production_certified"])

    def test_already_prepared_commit_acknowledgement_loss_is_not_blocked(self):
        class AmbiguousCommitCursor(RecordingCursor):
            def execute(self, query, parameters=None):
                normalized = " ".join(query.split())
                if normalized == "COMMIT":
                    self.executions.append((normalized, parameters))
                    raise OSError("connection lost after commit was sent")
                return super().execute(query, parameters)

        class AmbiguousCommitConnection(RecordingConnection):
            def __init__(self):
                super().__init__()
                self.recording_cursor = AmbiguousCommitCursor()

        connection = AmbiguousCommitConnection()
        prepared = assessment(
            columns=(
                *subject.EXPECTED_BASE_COLUMNS,
                subject._organization_column(nullable=False),
            )
        )
        with patch.object(subject, "assess_database", return_value=prepared):
            receipt = subject.perform(
                dsn="postgresql://redacted",
                apply=True,
                confirmation=subject.expected_confirmation(prepared.snapshot),
                v9_source_confirmation=subject.expected_v9_source_confirmation(
                    subject.discover_v9_source_guard()
                ),
                durable_receipt_reserved=True,
                migrations=migrations(),
                connector=lambda _dsn, _timeout: connection,
                now=lambda: NOW,
            )

        self.assertEqual("OUTCOME_UNKNOWN", receipt["decision"])
        self.assertEqual("COMMIT_SENT", receipt["mutation"]["phase"])
        self.assertFalse(receipt["mutation"]["attempted"])
        self.assertTrue(receipt["mutation"]["reconciliation_required"])

    def test_failed_rollback_after_mutation_preserves_unknown_outcome(self):
        class FailedRollbackCursor(RecordingCursor):
            def execute(self, query, parameters=None):
                normalized = " ".join(query.split())
                if normalized.startswith(
                    "ALTER TABLE public.audit_events ALTER COLUMN"
                ):
                    self.executions.append((normalized, parameters))
                    raise OSError("mutation connection failure")
                if normalized == "ROLLBACK":
                    self.executions.append((normalized, parameters))
                    raise OSError("rollback acknowledgement lost")
                return super().execute(query, parameters)

        class FailedRollbackConnection(RecordingConnection):
            def __init__(self):
                super().__init__()
                self.recording_cursor = FailedRollbackCursor()

        connection = FailedRollbackConnection()
        ready = assessment()
        with patch.object(subject, "assess_database", return_value=ready):
            receipt = subject.perform(
                dsn="postgresql://redacted",
                apply=True,
                confirmation=subject.expected_confirmation(ready.snapshot),
                v9_source_confirmation=subject.expected_v9_source_confirmation(
                    subject.discover_v9_source_guard()
                ),
                durable_receipt_reserved=True,
                migrations=migrations(),
                connector=lambda _dsn, _timeout: connection,
                now=lambda: NOW,
            )

        self.assertEqual("OUTCOME_UNKNOWN", receipt["decision"])
        self.assertEqual("MUTATION_IN_PROGRESS", receipt["mutation"]["phase"])
        self.assertTrue(receipt["mutation"]["rollback_attempted"])
        self.assertFalse(receipt["mutation"]["rollback_acknowledged"])
        self.assertFalse(receipt["mutation"]["rollback_confirmed"])
        self.assertTrue(receipt["mutation"]["reconciliation_required"])

    def test_confirmed_rollback_after_mutation_failure_is_blocked(self):
        class MutationFailureCursor(RecordingCursor):
            def execute(self, query, parameters=None):
                normalized = " ".join(query.split())
                if normalized.startswith(
                    "ALTER TABLE public.audit_events ALTER COLUMN"
                ):
                    self.executions.append((normalized, parameters))
                    raise OSError("mutation failed before commit")
                return super().execute(query, parameters)

        class MutationFailureConnection(RecordingConnection):
            def __init__(self):
                super().__init__()
                self.recording_cursor = MutationFailureCursor()

        connection = MutationFailureConnection()
        ready = assessment()
        with patch.object(subject, "assess_database", return_value=ready):
            with self.assertRaises(subject.BootstrapBlocked) as raised:
                subject.perform(
                    dsn="postgresql://redacted",
                    apply=True,
                    confirmation=subject.expected_confirmation(ready.snapshot),
                    v9_source_confirmation=subject.expected_v9_source_confirmation(
                        subject.discover_v9_source_guard()
                    ),
                    durable_receipt_reserved=True,
                    migrations=migrations(),
                    connector=lambda _dsn, _timeout: connection,
                    now=lambda: NOW,
                )

        self.assertEqual("DATABASE_OPERATION_FAILED", raised.exception.code)
        self.assertEqual(
            "ROLLBACK", connection.recording_cursor.executions[-1][0]
        )

    def test_secret_is_never_rendered_on_connection_failure(self):
        secret = "never-print-this-password"

        def failing_connector(_dsn, _timeout):
            raise RuntimeError(secret)

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            exit_code = subject.main(
                [],
                environ={
                    subject.DATABASE_URL_ENV: (
                        f"postgresql://operator:{secret}@database.example/elmos"
                    )
                },
                connector=failing_connector,
                now=lambda: NOW,
            )
        rendered = output.getvalue()
        self.assertEqual(2, exit_code)
        self.assertNotIn(secret, rendered)
        receipt = json.loads(rendered)
        self.assertEqual("BLOCKED", receipt["decision"])
        self.assertEqual(["DATABASE_OPERATION_FAILED"], receipt["blockers"])
        self.assertEqual("NOT_CERTIFIED", receipt["certification_status"])

    def test_receipt_publication_never_overwrites_an_existing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "receipt.json"
            target.write_text("existing evidence\n", encoding="utf-8")

            with self.assertRaises(subject.BootstrapBlocked) as raised:
                subject.write_receipt(target, {"decision": "READY_TO_APPLY"})

            self.assertEqual(
                "RECEIPT_PATH_ALREADY_EXISTS", raised.exception.code
            )
            self.assertEqual("existing evidence\n", target.read_text(encoding="utf-8"))

    def test_v9_guard_binds_the_trigger_before_backfill_hazard(self):
        with tempfile.TemporaryDirectory() as directory:
            migration = Path(directory) / (
                "V9__enterprise_identity_tenant_and_private_execution.sql"
            )
            trigger = (
                "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE "
                "ON audit_events"
            )
            add = (
                "EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS "
                "organization_id varchar(96)', tenant_table.tablename);"
            )
            update = (
                "EXECUTE format('UPDATE %I SET organization_id = %L WHERE "
                "organization_id IS NULL', tenant_table.tablename, 'org-system');"
            )
            not_null = (
                "EXECUTE format('ALTER TABLE %I ALTER COLUMN organization_id "
                "SET NOT NULL', tenant_table.tablename);"
            )
            migration.write_text(
                "\n".join((trigger, add, update, not_null)), encoding="utf-8"
            )

            guard = subject.discover_v9_source_guard(Path(directory))
            self.assertRegex(guard.source_sha256, r"^[0-9a-f]{64}$")
            self.assertLess(guard.trigger_offset, guard.tenant_backfill_offset)

            migration.write_text(
                "\n".join((add, update, not_null, trigger)), encoding="utf-8"
            )
            with self.assertRaises(subject.BootstrapBlocked) as raised:
                subject.discover_v9_source_guard(Path(directory))
            self.assertEqual(
                "LOCAL_V9_HAZARD_SOURCE_INVALID", raised.exception.code
            )

            migration.write_text(
                "\n".join(f"-- {marker}" for marker in (trigger, add, update, not_null)),
                encoding="utf-8",
            )
            with self.assertRaises(subject.BootstrapBlocked) as commented:
                subject.discover_v9_source_guard(Path(directory))
            self.assertEqual(
                "LOCAL_V9_HAZARD_SOURCE_INVALID", commented.exception.code
            )

    def test_apply_receipt_collision_blocks_before_database_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "receipt.json"
            target.write_text("preserve\n", encoding="utf-8")
            called = False

            def connector(_dsn, _timeout):
                nonlocal called
                called = True
                return RecordingConnection()

            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                exit_code = subject.main(
                    ["--apply", "--receipt", str(target)],
                    environ={
                        subject.DATABASE_URL_ENV: "postgresql://redacted",
                        subject.CONFIRMATION_ENV: (
                            subject.CONFIRMATION_PREFIX + "0" * 64
                        ),
                        subject.V9_SOURCE_CONFIRMATION_ENV: (
                            subject.V9_SOURCE_CONFIRMATION_PREFIX + "0" * 64
                        ),
                    },
                    connector=connector,
                    now=lambda: NOW,
                )

            self.assertEqual(2, exit_code)
            self.assertFalse(called)
            self.assertEqual("preserve\n", target.read_text(encoding="utf-8"))
            self.assertEqual(
                ["RECEIPT_PATH_ALREADY_EXISTS"],
                json.loads(output.getvalue())["blockers"],
            )

    def test_commit_result_is_preserved_when_reserved_receipt_publish_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "receipt.json"
            applied = subject._finalize_receipt(
                {
                    "schema_version": 1,
                    "operation": "PRE_V9_AUDIT_EVENTS_TENANT_BOOTSTRAP",
                    "mode": "APPLY",
                    "decision": "APPLIED",
                    "mutation": {"attempted": True},
                    "certification_status": "NOT_CERTIFIED",
                }
            )
            output = io.StringIO()
            with patch.object(subject, "perform", return_value=applied), patch.object(
                subject,
                "publish_reserved_receipt",
                side_effect=OSError("simulated receipt device failure"),
            ), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                exit_code = subject.main(
                    ["--apply", "--receipt", str(target)],
                    environ={
                        subject.DATABASE_URL_ENV: "postgresql://redacted",
                        subject.CONFIRMATION_ENV: (
                            subject.CONFIRMATION_PREFIX + "0" * 64
                        ),
                        subject.V9_SOURCE_CONFIRMATION_ENV: (
                            subject.expected_v9_source_confirmation(
                                subject.discover_v9_source_guard()
                            )
                        ),
                    },
                    now=lambda: NOW,
                )

            rendered = json.loads(output.getvalue())
            self.assertEqual(3, exit_code)
            self.assertEqual("APPLIED", rendered["decision"])
            self.assertEqual(
                "RECONCILIATION_REQUIRED",
                rendered["receipt_publication"]["status"],
            )
            pending = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual("OUTCOME_UNKNOWN", pending["decision"])
            self.assertEqual(
                "RECONCILIATION_REQUIRED_UNTIL_FINALIZED",
                pending["receipt_publication"]["status"],
            )


if __name__ == "__main__":
    unittest.main()
