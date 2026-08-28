#!/usr/bin/env python3
"""Run destructive integration checks against a disposable PostgreSQL 17.

This runner never accepts a DSN and therefore cannot connect to production. It
creates a private temporary cluster, applies the repository migration as a
NOLOGIN owner role, exercises the application through a NOSUPERUSER /
NOBYPASSRLS role, stops the cluster, and removes only its own temporary tree.

Usage (after installing the ``postgres`` extra)::

    PYTHONPATH=src python tests/postgres17_integration.py -v
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest

from elmos_proof_harness.canonical import digest_bytes
from elmos_proof_harness.contracts import EvidenceProducer, SecurityContext
from elmos_proof_harness.errors import (
    AuthorizationError,
    ConflictError,
    IntegrityError,
    NotFoundError,
    WorkflowError,
)
from elmos_proof_harness.evidence import EvidenceService
from elmos_proof_harness.postgres import PostgresStore
from elmos_proof_harness.workflow import RunState, WorkflowEngine


ENGINE_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ENGINE_ROOT / "migrations" / "V001__proof_harness_core.sql"


def _postgres_bin() -> Path:
    configured = os.environ.get("ELMOS_TEST_POSTGRES17_BIN")
    if configured:
        return Path(configured).resolve()
    discovered = shutil.which("initdb")
    if discovered:
        return Path(discovered).resolve().parent
    return Path("/opt/homebrew/opt/postgresql@17/bin")


PG_BIN = _postgres_bin()
APP_ROLE = "proof_harness_app_it"
OWNER_ROLE = "proof_harness_owner_it"
_DIGEST_A = "sha256:" + "a" * 64


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class DisposablePostgres17:
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="elmos-proof-harness-pg17-"))
        self.data = self.root / "data"
        self.port = _free_port()
        self.started = False

    @property
    def admin_dsn(self) -> str:
        return f"postgresql://127.0.0.1:{self.port}/postgres?sslmode=disable"

    @property
    def app_dsn(self) -> str:
        return f"postgresql://{APP_ROLE}@127.0.0.1:{self.port}/postgres?sslmode=disable"

    def _run(self, *arguments: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            arguments,
            check=True,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )

    def start(self) -> None:
        for executable in ("initdb", "pg_ctl", "psql"):
            if not (PG_BIN / executable).is_file():
                raise RuntimeError(f"PostgreSQL 17 executable is missing: {PG_BIN / executable}")
        version = self._run(str(PG_BIN / "initdb"), "--version").stdout
        if " 17." not in version:
            raise RuntimeError(f"expected PostgreSQL 17, observed {version.strip()}")
        self._run(
            str(PG_BIN / "initdb"),
            "-A",
            "trust",
            "--no-locale",
            "-E",
            "UTF8",
            "-D",
            str(self.data),
        )
        self._run(
            str(PG_BIN / "pg_ctl"),
            "-D",
            str(self.data),
            "-o",
            f"-F -p {self.port} -h 127.0.0.1",
            "-l",
            str(self.root / "postgres.log"),
            "-w",
            "start",
        )
        self.started = True
        self.psql(
            f"""
            CREATE ROLE {OWNER_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
            CREATE ROLE {APP_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
            GRANT CREATE ON DATABASE postgres TO {OWNER_ROLE};
            """
        )
        self.psql("SET ROLE " + OWNER_ROLE + ";\n" + MIGRATION.read_text(encoding="utf-8") + "\nRESET ROLE;")
        self.psql(
            f"""
            GRANT CONNECT ON DATABASE postgres TO {APP_ROLE};
            GRANT USAGE ON SCHEMA proof_harness, proof_harness_runtime TO {APP_ROLE};
            GRANT EXECUTE ON FUNCTION proof_harness.current_tenant_key(), proof_harness.current_project_key() TO {APP_ROLE};
            GRANT SELECT ON proof_harness_runtime.schema_migrations TO {APP_ROLE};
            GRANT SELECT, INSERT ON proof_harness_runtime.tenants,
              proof_harness_runtime.projects, proof_harness_runtime.actors TO {APP_ROLE};
            GRANT SELECT, INSERT, UPDATE ON proof_harness_runtime.runs,
              proof_harness_runtime.control_plane_receipts,
              proof_harness_runtime.external_effects TO {APP_ROLE};
            GRANT DELETE ON proof_harness_runtime.control_plane_receipts TO {APP_ROLE};
            GRANT SELECT, INSERT ON proof_harness_runtime.idempotency_receipts,
              proof_harness_runtime.evidence,
              proof_harness_runtime.evidence_revocations,
              proof_harness_runtime.audit_events,
              proof_harness_runtime.outbox_events,
              proof_harness_runtime.outbox_deliveries,
              proof_harness_runtime.run_checkpoints,
              proof_harness_runtime.effect_events,
              proof_harness_runtime.metric_points TO {APP_ROLE};
            """
        )

    def psql(self, sql: str) -> str:
        return self._run(
            str(PG_BIN / "psql"),
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            "127.0.0.1",
            "-p",
            str(self.port),
            "-d",
            "postgres",
            input_text=sql,
        ).stdout

    def stop(self) -> None:
        try:
            if self.started:
                self._run(str(PG_BIN / "pg_ctl"), "-D", str(self.data), "-m", "fast", "-w", "stop")
        finally:
            # ``root`` was allocated by mkdtemp in this process; no user path,
            # environment variable, glob or workspace directory is accepted.
            shutil.rmtree(self.root)


class Postgres17IntegrationTests(unittest.TestCase):
    cluster: DisposablePostgres17
    store: PostgresStore

    @classmethod
    def setUpClass(cls) -> None:
        cls.cluster = DisposablePostgres17()
        try:
            cls.cluster.start()
            cls.store = PostgresStore(cls.cluster.app_dsn)
            readiness = cls.store.readiness()
            if not readiness.ready:
                raise AssertionError(readiness)
        except Exception:
            cls.cluster.stop()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()
        cls.cluster.stop()

    def setUp(self) -> None:
        # Unique scopes make every test independent without deleting durable
        # append-only records.
        suffix = self._testMethodName
        self.context = SecurityContext(f"tenant-{suffix}", f"project-{suffix}", f"actor-{suffix}")
        self.store.register_scope(self.context)

    def test_01_missing_context_and_forced_rls(self) -> None:
        with self.assertRaisesRegex(AuthorizationError, "trusted"):
            with self.store.transaction():
                pass

        psycopg = __import__("psycopg")
        with psycopg.connect(self.cluster.app_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM proof_harness_runtime.projects")
                self.assertEqual(cursor.fetchone()[0], 0)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        "INSERT INTO proof_harness_runtime.projects(tenant_id,project_id,created_at) VALUES ('untrusted','untrusted',clock_timestamp())"
                    )

    def test_02_cross_project_and_tenant_are_invisible(self) -> None:
        created = self.store.create_run(
            self.context,
            run_id="run-isolated",
            revision_set_id=_DIGEST_A,
            idempotency_key="create-isolated",
        )
        self.assertEqual(created.actor_id, self.context.actor_id)
        same_tenant = SecurityContext(self.context.tenant_id, "project-other", "actor-other")
        other_tenant = SecurityContext("tenant-other", self.context.project_id, "actor-other")
        self.store.register_scope(same_tenant)
        self.store.register_scope(other_tenant)
        with self.assertRaises(NotFoundError):
            self.store.get_run(same_tenant, "run-isolated")
        with self.assertRaises(NotFoundError):
            self.store.get_run(other_tenant, "run-isolated")

    def test_03_idempotency_and_actor_binding(self) -> None:
        first = self.store.create_run(
            self.context,
            run_id="run-idempotent",
            revision_set_id=_DIGEST_A,
            idempotency_key="same-key",
        )
        replay = self.store.create_run(
            self.context,
            run_id="run-idempotent",
            revision_set_id=_DIGEST_A,
            idempotency_key="same-key",
        )
        self.assertEqual(first, replay)
        with self.assertRaisesRegex(ConflictError, "different request"):
            self.store.create_run(
                self.context,
                run_id="run-different",
                revision_set_id=_DIGEST_A,
                idempotency_key="same-key",
            )
        other_actor = SecurityContext(self.context.tenant_id, self.context.project_id, "actor-other")
        self.store.register_scope(other_actor)
        with self.assertRaises(AuthorizationError):
            self.store.create_run(
                other_actor,
                run_id="run-idempotent",
                revision_set_id=_DIGEST_A,
                idempotency_key="same-key",
            )
        request = {"requestId": "control-request"}
        request_digest = digest_bytes(
            json.dumps(request, sort_keys=True).encode("utf-8"),
            domain="control-request",
        )
        claimed, receipt = self.store.claim_control_plane_receipt(
            self.context,
            operation="invoke",
            idempotency_key="control-key",
            request_sha256=request_digest,
            run_id=first.run_id,
            request=request,
        )
        self.assertTrue(claimed)
        replayed, replay_receipt = self.store.claim_control_plane_receipt(
            self.context,
            operation="invoke",
            idempotency_key="control-key",
            request_sha256=request_digest,
            run_id=first.run_id,
            request=request,
        )
        self.assertFalse(replayed)
        self.assertEqual(receipt, replay_receipt)
        completed = self.store.complete_control_plane_receipt(
            self.context,
            operation="invoke",
            idempotency_key="control-key",
            request_sha256=request_digest,
            response={"status": "SUCCEEDED"},
        )
        self.assertEqual(completed.response, {"status": "SUCCEEDED"})

    def test_04_stale_fence_checkpoint_restart_and_unknown_effect(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        run = self.store.create_run(self.context, run_id="run-recover", revision_set_id=_DIGEST_A, now=base)
        run_context = self.context.for_run(run.run_id)
        lease = self.store.acquire_lease(
            run_context,
            owner_id="worker-a",
            ttl_seconds=1,
            expected_sequence=run.sequence,
            now=base,
        )
        active = run_context.for_run(run.run_id, fencing_generation=lease.fencing_generation)
        with self.assertRaisesRegex(ConflictError, "fencing generation"):
            self.store.transition_run(
                run_context,
                target_state="EXECUTING",
                expected_sequence=lease.sequence,
                lease_token=lease.token,
                now=base + timedelta(milliseconds=10),
            )
        running = self.store.transition_run(
            active,
            target_state="EXECUTING",
            expected_sequence=lease.sequence,
            lease_token=lease.token,
            now=base + timedelta(milliseconds=10),
        )
        checkpoint = self.store.append_checkpoint(
            active,
            b"exact checkpoint bytes",
            expected_sequence=running.sequence,
            lease_token=lease.token,
            checkpoint_id="checkpoint-restart",
            now=base + timedelta(milliseconds=20),
        )
        snapshot, recovery_lease, recovered_checkpoint, recovered_bytes = self.store.recover_run(
            active,
            owner_id="worker-b",
            expected_sequence=checkpoint.sequence,
            ttl_seconds=300,
            now=base + timedelta(seconds=2),
        )
        self.assertEqual(recovered_bytes, b"exact checkpoint bytes")
        self.assertEqual(recovered_checkpoint.payload_sha256, checkpoint.payload_sha256)
        recovered_context = active.for_run(
            snapshot.run_id,
            execution_epoch=snapshot.execution_epoch,
            fencing_generation=snapshot.fencing_generation,
        )
        effect = self.store.start_external_effect(
            recovered_context,
            effect_id="effect-unknown",
            provider="disposable-test-provider",
            operation="write",
            idempotency_key="effect-key",
            request={"value": 1},
            reconciliation_strategy="query-by-idempotency-key",
            lease_token=recovery_lease.token,
            now=base + timedelta(seconds=3),
        )
        replayed_effect = self.store.start_external_effect(
            recovered_context,
            effect_id="ignored-on-replay",
            provider="disposable-test-provider",
            operation="write",
            idempotency_key="effect-key",
            request={"value": 1},
            reconciliation_strategy="query-by-idempotency-key",
            lease_token=recovery_lease.token,
            now=base + timedelta(seconds=3),
        )
        self.assertEqual(effect, replayed_effect)
        unknown = self.store.reconcile_external_effect(
            recovered_context,
            effect_id=effect.effect_id,
            target_state="UNKNOWN_RESULT",
            expected_version=effect.version,
            detail={"provider_result": "timeout"},
            lease_token=recovery_lease.token,
            now=base + timedelta(seconds=4),
        )
        self.assertEqual(unknown.state, "UNKNOWN_RESULT")
        self.assertEqual(self.store.unsettled_side_effect_count(recovered_context), 1)

        # New store object proves process-local state is not needed for replay.
        restarted = PostgresStore(self.cluster.app_dsn)
        try:
            replayed_checkpoint, replayed_bytes = restarted.get_checkpoint(recovered_context, checkpoint.checkpoint_id)
            self.assertEqual(replayed_checkpoint.payload_sha256, checkpoint.payload_sha256)
            self.assertEqual(replayed_bytes, recovered_bytes)
            workflow = WorkflowEngine(restarted)
            verifying = workflow.transition(
                recovered_context,
                RunState.VERIFYING,
                expected_sequence=snapshot.sequence,
                lease_token=recovery_lease.token,
                now=base + timedelta(seconds=5),
            )
            certifying = workflow.transition(
                recovered_context,
                RunState.CERTIFYING,
                expected_sequence=verifying.sequence,
                lease_token=recovery_lease.token,
                now=base + timedelta(seconds=6),
            )
            with self.assertRaisesRegex(WorkflowError, "unsettled"):
                workflow.transition(
                    recovered_context,
                    RunState.COMPLETED,
                    expected_sequence=certifying.sequence,
                    lease_token=recovery_lease.token,
                    now=base + timedelta(seconds=7),
                )
        finally:
            restarted.close()

    def test_05_byte_bound_evidence_revocation_and_immutable_trigger(self) -> None:
        service = EvidenceService(self.store)
        record = service.record_bytes(
            self.context,
            subject_revision=_DIGEST_A,
            kind="integration",
            evidence_class="operational",
            scope="postgres17",
            content=b"exact evidence bytes",
            media_type="application/octet-stream",
            producer=EvidenceProducer(
                execution_id="pg17-integration",
                source="RUNNER",
                tool_name="postgres17-integration",
                tool_digest=digest_bytes(b"runner", domain="tool"),
                environment_revision=digest_bytes(b"postgres-17.5", domain="environment"),
            ),
            evidence_id="evidence-byte-bound",
            artifact_id="artifact-byte-bound",
            idempotency_key="evidence-key",
        )
        verified, content = service.read_verified(self.context, record.evidence_id)
        self.assertEqual(content, b"exact evidence bytes")
        tampered = replace(verified, evidence_id="evidence-tampered", content=replace(verified.content, byte_length=1))
        with self.assertRaises(IntegrityError):
            self.store.append_evidence(self.context, tampered, b"exact evidence bytes")

        # The owner has UPDATE privilege by ownership, so this reaches the
        # immutable trigger rather than merely proving the app grant is absent.
        escaped_tenant = self.context.tenant_id.replace("'", "''")
        escaped_project = self.context.project_id.replace("'", "''")
        escaped_evidence = record.evidence_id.replace("'", "''")
        with self.assertRaises(subprocess.CalledProcessError):
            self.cluster.psql(
                f"SET ROLE {OWNER_ROLE}; "
                f"SELECT set_config('app.tenant_id','{escaped_tenant}',false); "
                f"SELECT set_config('app.project_id','{escaped_project}',false); "
                f"UPDATE proof_harness_runtime.evidence SET content_bytes='tampered'::bytea "
                f"WHERE tenant_id='{escaped_tenant}' AND project_id='{escaped_project}' AND evidence_id='{escaped_evidence}';"
            )
        self.store.revoke_evidence(self.context, record.evidence_id, reason="integration revocation")
        with self.assertRaisesRegex(IntegrityError, "revoked"):
            service.verify(self.context, record.evidence_id)
        self.assertGreaterEqual(self.store.count_rows(self.context, "audit_events"), 2)
        self.assertGreaterEqual(self.store.count_rows(self.context, "outbox_events"), 2)

    def test_06_fake_certified_review_cannot_commit_and_app_role_cannot_write_it(self) -> None:
        psycopg = __import__("psycopg")
        with psycopg.connect(self.cluster.app_dsn, autocommit=True) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        "INSERT INTO proof_harness.completion_reviews(tenant_id,project_id,run_id,review_id,revision_set_digest,proof_graph_digest,evidence_root,decision,independent_verification,reviewer_identity,reviewer_execution_source,payload_digest) VALUES (%s,%s,%s,%s,%s,%s,%s,'CERTIFIED','VERIFIED','fake-reviewer','runtime-app',%s)",
                        (
                            "00000000-0000-0000-0000-000000000001",
                            "00000000-0000-0000-0000-000000000002",
                            "00000000-0000-0000-0000-000000000006",
                            "00000000-0000-0000-0000-000000000007",
                            _DIGEST_A,
                            _DIGEST_A,
                            _DIGEST_A,
                            _DIGEST_A,
                        ),
                    )

        fake_certification = f"""
        \\set VERBOSITY verbose
        BEGIN;
        SET ROLE {OWNER_ROLE};
        SELECT set_config('app.tenant_id','00000000-0000-0000-0000-000000000001',true);
        SELECT set_config('app.project_id','00000000-0000-0000-0000-000000000002',true);
        SELECT set_config('app.actor_id','certifier-negative-test',true);
        INSERT INTO proof_harness.tenant_projects(tenant_id,project_id)
          VALUES ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002');
        INSERT INTO proof_harness.goal_contracts(
          tenant_id,project_id,goal_id,contract_digest,contract_json,state,created_by
        ) VALUES (
          '00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002',
          '00000000-0000-0000-0000-000000000003','{_DIGEST_A}','{{}}'::jsonb,'FROZEN','certifier-negative-test'
        );
        INSERT INTO proof_harness.revision_sets(
          tenant_id,project_id,revision_set_id,goal_id,revision_set_digest,
          source_digest,baseline_digest,requirements_digest,policy_digest,
          workflow_digest,model_route_digest,toolchain_digest,environment_digest,
          domain_pack_digest,frozen_at
        ) VALUES (
          '00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002',
          '00000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000003',
          '{_DIGEST_A}','{_DIGEST_A}','{_DIGEST_A}','{_DIGEST_A}','{_DIGEST_A}',
          '{_DIGEST_A}','{_DIGEST_A}','{_DIGEST_A}','{_DIGEST_A}','{_DIGEST_A}',clock_timestamp()
        );
        INSERT INTO proof_harness.environment_authorities(
          tenant_id,project_id,authority_id,authority_revision,environment_id,
          execution_epoch,fencing_generation,capabilities_json,read_paths_json,
          write_paths_json,network_mode,valid_from,expires_at,issued_by
        ) VALUES (
          '00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002',
          '00000000-0000-0000-0000-000000000005','{_DIGEST_A}','pg17-negative',1,1,
          '[]'::jsonb,'[]'::jsonb,'[]'::jsonb,'DENY',clock_timestamp()-interval '1 hour',
          clock_timestamp()+interval '1 hour','certifier-negative-test'
        );
        INSERT INTO proof_harness.runs(
          tenant_id,project_id,run_id,goal_id,revision_set_id,authority_id,
          execution_epoch,fencing_generation,state
        ) VALUES (
          '00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002',
          '00000000-0000-0000-0000-000000000006','00000000-0000-0000-0000-000000000003',
          '00000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000005',
          1,1,'CERTIFYING'
        );
        INSERT INTO proof_harness.completion_reviews(
          tenant_id,project_id,run_id,review_id,revision_set_digest,proof_graph_digest,
          evidence_root,decision,independent_verification,reviewer_identity,
          reviewer_execution_source,payload_digest
        ) VALUES (
          '00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002',
          '00000000-0000-0000-0000-000000000006','00000000-0000-0000-0000-000000000007',
          '{_DIGEST_A}','{_DIGEST_A}','{_DIGEST_A}','CERTIFIED','VERIFIED',
          'fake-reviewer','self-asserted','{_DIGEST_A}'
        );
        COMMIT;
        """
        with self.assertRaises(subprocess.CalledProcessError) as rejected:
            self.cluster.psql(fake_certification)
        self.assertIn("23514", rejected.exception.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    arguments = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Postgres17IntegrationTests)
    result = unittest.TextTestRunner(verbosity=2 if arguments.verbose else 1).run(suite)
    print(
        json.dumps(
            {
                "postgres": "17",
                "driver": "psycopg[binary]==3.2.13",
                "testsRun": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
                "externalHA": "NOT_RUN",
                "backupRestore": "NOT_RUN",
                "disasterRecovery": "NOT_RUN",
            },
            sort_keys=True,
        )
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
