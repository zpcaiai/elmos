from __future__ import annotations

import asyncio
import hashlib
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from elmos_pi_harness.acceptance import (
    AcceptanceCase,
    AcceptanceRunner,
    accept_customer_signoff,
)
from elmos_pi_harness.artifacts import S3ArtifactBackend, S3ArtifactConfig
from elmos_pi_harness.canonical import digest, digest_bytes, utc_now
from elmos_pi_harness.deployment import (
    DeploymentController,
    DeploymentManifest,
    validate_production_configuration,
)
from elmos_pi_harness.disaster_recovery import (
    BackupObject,
    DisasterRecoveryOrchestrator,
    PostgresBackupConfig,
    PostgresLogicalBackupAdapter,
)
from elmos_pi_harness.identity import (
    CertificateIdentity,
    MTLSAuthenticator,
    OIDCAuthenticator,
    OIDCConfig,
    bind_oidc_and_mtls,
)
from elmos_pi_harness.independent_verifier import (
    EvidenceStatement,
    IndependentVerifierSigner,
    TrustedVerifier,
    VerificationReceiptRegistry,
    VerifierTrustStore,
    external_gate_decision,
)
from elmos_pi_harness.models import (
    AuthoritySnapshot,
    ConflictError,
    ExecutorIdentity,
    PolicyDeniedError,
    StaleGenerationError,
    TaskState,
)
from elmos_pi_harness.persistence import DurableStore
from elmos_pi_harness.postgres import (
    PostgresConfig,
    PostgresMigrator,
    _translate_kernel_sql,
)
from elmos_pi_harness.production import ApprovalGrant, ExactTarget, OperationState
from elmos_pi_harness.provider import (
    NativeProviderResult,
    ProviderControlPlane,
    ProviderOperationJournal,
    ProviderOutcomeUnknown,
)
from elmos_pi_harness.qualification import implementation_inventory
from elmos_pi_harness.temporal import TaskWorkflowInput, TemporalConfig, TemporalGateway
from elmos_pi_harness.temporal_activities import TemporalTaskActivity


def uid() -> str:
    return str(uuid.uuid4())


def when(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat().replace("+00:00", "Z")


def target(environment: str = "staging") -> ExactTarget:
    return ExactTarget(
        "aws",
        "cloudformation",
        "2010-05-15",
        "ap-southeast-1",
        "123456789012",
        environment,
    )


def approval(
    operation_id: str,
    request_digest: str,
    exact_target: ExactTarget,
    action: str,
    *,
    approver: str = "approver",
) -> ApprovalGrant:
    return ApprovalGrant(
        uid(),
        operation_id,
        request_digest,
        digest(exact_target.to_dict()),
        approver,
        when(timedelta(hours=1)),
        action,
    )


class FakeJWTDecoder:
    def __init__(self, claims):
        self.claims = claims

    def decode(self, _token):
        return self.claims


class FakeCertificateDecoder:
    def __init__(self, identity):
        self.identity = identity

    def decode(self, _certificate):
        return self.identity


class IdentityTests(unittest.TestCase):
    def test_oidc_and_mtls_bind_same_tenant_and_reject_spoofing(self) -> None:
        tenant = uid()
        now = int(datetime.now(timezone.utc).timestamp())
        config = OIDCConfig(
            "https://id.example.test", "pi-api", "https://id.example.test/jwks"
        )
        oidc = OIDCAuthenticator(
            config,
            FakeJWTDecoder(
                {
                    "iss": config.issuer,
                    "aud": [config.audience],
                    "sub": "user-1",
                    "preferred_username": "alice",
                    "tenant_id": tenant,
                    "project_ids": [uid()],
                    "iat": now,
                    "exp": now + 300,
                }
            ),
        )
        oidc_principal = oidc.authenticate("signed-token")
        certificate = CertificateIdentity(
            f"spiffe://mesh.example/tenant/{tenant}/workload/runner-1",
            datetime.now(timezone.utc) - timedelta(minutes=1),
            datetime.now(timezone.utc) + timedelta(minutes=5),
            10,
            "a" * 64,
        )
        mtls = MTLSAuthenticator(
            "mesh.example",
            decoder=FakeCertificateDecoder(certificate),
            revocation_checker=lambda _serial, _fingerprint: False,
        ).authenticate(b"der", transport_chain_verified=True)
        combined = bind_oidc_and_mtls(oidc_principal, mtls)
        self.assertEqual(combined.authentication_methods, frozenset({"oidc", "mtls"}))
        other = CertificateIdentity(
            f"spiffe://mesh.example/tenant/{uid()}/workload/runner-1",
            certificate.not_before,
            certificate.not_after,
            11,
            "b" * 64,
        )
        with self.assertRaises(PolicyDeniedError):
            bind_oidc_and_mtls(
                oidc_principal,
                MTLSAuthenticator(
                    "mesh.example",
                    decoder=FakeCertificateDecoder(other),
                    revocation_checker=lambda _serial, _fingerprint: False,
                ).authenticate(b"der", transport_chain_verified=True),
            )

    def test_expired_or_unverified_mtls_fails_closed(self) -> None:
        identity = CertificateIdentity(
            f"spiffe://mesh.example/tenant/{uid()}/workload/runner",
            datetime.now(timezone.utc) - timedelta(hours=2),
            datetime.now(timezone.utc) - timedelta(hours=1),
            1,
            "a" * 64,
        )
        authenticator = MTLSAuthenticator(
            "mesh.example",
            decoder=FakeCertificateDecoder(identity),
            revocation_checker=lambda _serial, _fingerprint: False,
        )
        with self.assertRaises(PolicyDeniedError):
            authenticator.authenticate(b"der", transport_chain_verified=True)
        with self.assertRaises(PolicyDeniedError):
            authenticator.authenticate(b"der", transport_chain_verified=False)

    def test_oidc_without_project_binding_fails_closed(self) -> None:
        tenant = uid()
        now = int(datetime.now(timezone.utc).timestamp())
        config = OIDCConfig(
            "https://id.example.test", "pi-api", "https://id.example.test/jwks"
        )
        authenticator = OIDCAuthenticator(
            config,
            FakeJWTDecoder(
                {
                    "iss": config.issuer,
                    "aud": config.audience,
                    "sub": "user-1",
                    "tenant_id": tenant,
                    "iat": now,
                    "exp": now + 300,
                }
            ),
        )
        with self.assertRaises(PolicyDeniedError):
            authenticator.authenticate("signed-token")


class FakeProvider:
    def __init__(self, exact_target: ExactTarget, outcome: str = "success") -> None:
        self.target = exact_target
        self.outcome = outcome

    def plan(self, action, request):
        return {
            "valid": True,
            "policy_denials": [],
            "action": action,
            "request_digest": digest(dict(request)),
        }

    def apply(self, operation_id, action, request):
        if self.outcome == "unknown":
            raise ProviderOutcomeUnknown("timeout after submit")
        return NativeProviderResult(
            OperationState.SUCCEEDED,
            "native-1",
            {"status": "complete", "operation_id": operation_id},
        )

    def observe(self, native_id, action):
        return NativeProviderResult(
            OperationState.SUCCEEDED, native_id, {"status": "complete"}
        )

    def recover(self, operation_id, action, request, plan):
        return NativeProviderResult(
            OperationState.SUCCEEDED,
            "native-recovered-1",
            {"status": "recovered", "operation_id": operation_id},
        )

    def rollback(self, native_id, action, request):
        if self.outcome == "terminal_unknown":
            return NativeProviderResult(
                OperationState.UNKNOWN, native_id, {"status": "rollback-submitted"}
            )
        return NativeProviderResult(
            OperationState.SUCCEEDED, native_id, {"status": "rolled-back"}
        )

    def destroy(self, native_id, action, request):
        return NativeProviderResult(
            OperationState.SUCCEEDED, native_id, {"status": "destroyed"}
        )


class ProviderTests(unittest.TestCase):
    def test_approval_is_digest_bound_and_success_is_replayable(self) -> None:
        journal = ProviderOperationJournal()
        plane = ProviderControlPlane(journal, {"aws": FakeProvider(target())})
        tenant, operation = uid(), uid()
        prepared = plane.prepare(
            operation_id=operation,
            tenant_id=tenant,
            actor_id="requester",
            adapter_name="aws",
            action="execute_change_set",
            request={"change_set": "one"},
        )
        journal.approve(
            tenant,
            operation,
            approval(
                operation, prepared["request_digest"], target(), "execute_change_set"
            ),
            actor_id="approver",
        )
        result = plane.execute(tenant, operation, "aws", actor_id="requester")
        self.assertEqual(result["state"], "SUCCEEDED")
        self.assertGreaterEqual(len(journal.events(tenant, operation)), 4)
        with self.assertRaises(ConflictError):
            plane.execute(tenant, operation, "aws", actor_id="requester")
        journal.close()

    def test_unknown_provider_result_requires_reconciliation_and_no_retry(self) -> None:
        journal = ProviderOperationJournal()
        plane = ProviderControlPlane(
            journal, {"aws": FakeProvider(target(), "unknown")}
        )
        tenant, operation = uid(), uid()
        prepared = plane.prepare(
            operation_id=operation,
            tenant_id=tenant,
            actor_id="requester",
            adapter_name="aws",
            action="execute_change_set",
            request={"change_set": "one"},
        )
        journal.approve(
            tenant,
            operation,
            approval(
                operation, prepared["request_digest"], target(), "execute_change_set"
            ),
            actor_id="approver",
        )
        result = plane.execute(tenant, operation, "aws", actor_id="requester")
        self.assertEqual(result["state"], "RECONCILIATION_REQUIRED")
        self.assertTrue(result["reconciliation_required"])
        with self.assertRaises(ConflictError):
            plane.execute(tenant, operation, "aws", actor_id="requester")
        reconciled = plane.reconcile(tenant, operation, "aws", actor_id="reconciler")
        self.assertEqual(
            (reconciled["state"], reconciled["provider_native_id"]),
            ("SUCCEEDED", "native-recovered-1"),
        )
        journal.close()

    def test_unknown_rollback_is_persisted_then_reconciled(self) -> None:
        journal = ProviderOperationJournal()
        adapter = FakeProvider(target(), "terminal_unknown")
        plane = ProviderControlPlane(journal, {"aws": adapter})
        tenant, operation = uid(), uid()
        prepared = plane.prepare(
            operation_id=operation,
            tenant_id=tenant,
            actor_id="requester",
            adapter_name="aws",
            action="execute_change_set",
            request={"change_set": "one"},
        )
        journal.approve(
            tenant,
            operation,
            approval(
                operation,
                prepared["request_digest"],
                target(),
                "execute_change_set",
            ),
            actor_id="approver",
        )
        self.assertEqual(
            plane.execute(tenant, operation, "aws", actor_id="requester")["state"],
            "SUCCEEDED",
        )
        pending = plane.rollback(tenant, operation, "aws", actor_id="requester")
        self.assertEqual(
            (pending["state"], pending["pending_terminal_state"]),
            ("RECONCILIATION_REQUIRED", "ROLLED_BACK"),
        )
        reconciled = plane.reconcile(tenant, operation, "aws", actor_id="reconciler")
        self.assertEqual(reconciled["state"], "ROLLED_BACK")
        journal.close()


class FakeWorkflowHandle:
    def __init__(self):
        self.signals = []
        self.first_execution_run_id = "run-1"

    async def signal(self, signal, arg=None):
        self.signals.append((signal, arg))

    async def cancel(self):
        self.signals.append(("cancel", None))

    async def result(self):
        return {"status": "SUCCEEDED"}

    async def describe(self):
        return {"status": "RUNNING"}


class FakeTemporalClient:
    def __init__(self):
        self.handle = FakeWorkflowHandle()
        self.started = None

    async def start_workflow(self, workflow, arg, **kwargs):
        self.started = (workflow, arg, kwargs)
        return self.handle

    def get_workflow_handle(self, workflow_id, *, run_id=None):
        return self.handle


class TemporalTests(unittest.TestCase):
    def test_workflow_identity_signals_and_request_digest_are_bound(self) -> None:
        client = FakeTemporalClient()
        config = TemporalConfig(
            "temporal.example:7233",
            "pi-staging",
            "pi-v51",
            "5.1.0+1",
            "worker-a",
            "temporal.example",
            Path("/tmp/ca"),
            Path("/tmp/cert"),
            Path("/tmp/key"),
        )
        gateway = TemporalGateway(client, config)
        request = {"objective": "run"}
        value = TaskWorkflowInput(
            uid(),
            uid(),
            uid(),
            uid(),
            uid(),
            uid(),
            "executor-a",
            2,
            request,
            digest(request),
        )

        async def exercise():
            created = await gateway.start_task(value)
            await gateway.pause(created["workflow_id"], reason="operator")
            await gateway.resume(created["workflow_id"], expected_executor_generation=2)
            return created

        created = asyncio.run(exercise())
        self.assertEqual(created["state"], "SUBMITTED")
        self.assertEqual(client.handle.signals, [("pause", "operator"), ("resume", 2)])
        with self.assertRaises(ValueError):
            TaskWorkflowInput(
                uid(),
                uid(),
                uid(),
                uid(),
                uid(),
                uid(),
                "executor-a",
                0,
                request,
                "sha256:" + "0" * 64,
            )

    def test_activity_fences_executor_and_replays_persisted_result(self) -> None:
        tenant, project, task_id, execution_id = uid(), uid(), uid(), uid()
        request = {"objective": "execute with durable evidence"}
        store = DurableStore()
        store.create_task(
            tenant,
            project,
            request["objective"],
            idempotency_key="create",
            request_payload=request,
            task_id=task_id,
        )
        store.transition_task(
            tenant,
            task_id,
            TaskState.QUEUED,
            idempotency_key="queue",
            actor_id="scheduler",
        )
        environment = store.create_environment(tenant, execution_id, "sandbox")
        authority_id = uid()
        store.create_authority_snapshot(
            tenant,
            authority_id,
            AuthoritySnapshot(
                uid(),
                environment["environment_id"],
                "policy-v1",
                frozenset({"tool.execute"}),
            ),
        )
        identity = ExecutorIdentity("executor-a", 2)
        store.register_executor(tenant, environment["environment_id"], identity)
        value = TaskWorkflowInput(
            tenant,
            project,
            task_id,
            execution_id,
            environment["environment_id"],
            authority_id,
            identity.executor_id,
            identity.generation,
            request,
            digest(request),
        )

        class Backend:
            calls = 0

            async def execute(self, received, *, idempotency_key, heartbeat):
                self.calls += 1
                heartbeat({"phase": "BACKEND"})
                return {
                    "status": "VERIFYING",
                    "task_id": received.task_id,
                    "request_digest": received.request_digest,
                    "executor_id": received.executor_id,
                    "executor_generation": received.executor_generation,
                    "evidence_digest": "sha256:" + "a" * 64,
                }

        backend = Backend()
        heartbeats = []
        service = TemporalTaskActivity(store, backend, actor_id="temporal-worker")
        first = asyncio.run(
            service.execute(value.to_dict(), heartbeat=heartbeats.append)
        )
        second = asyncio.run(
            service.execute(value.to_dict(), heartbeat=heartbeats.append)
        )
        self.assertEqual((first["replayed"], second["replayed"]), (False, True))
        self.assertEqual(backend.calls, 1)
        self.assertEqual(store.get_task(tenant, task_id)["status"], "VERIFYING")
        self.assertGreaterEqual(len(heartbeats), 3)

        store.register_executor(
            tenant,
            environment["environment_id"],
            ExecutorIdentity("executor-b", 3),
        )
        with self.assertRaises(StaleGenerationError):
            asyncio.run(service.execute(value.to_dict()))
        store.close()

    def test_control_activity_durably_pauses_resumes_and_cancels(self) -> None:
        tenant, project, task_id, execution_id = uid(), uid(), uid(), uid()
        request = {"objective": "durable controls"}
        store = DurableStore()
        store.create_task(
            tenant,
            project,
            request["objective"],
            idempotency_key="create-control",
            request_payload=request,
            task_id=task_id,
        )
        store.transition_task(
            tenant,
            task_id,
            TaskState.QUEUED,
            idempotency_key="queue-control",
            actor_id="scheduler",
        )
        environment = store.create_environment(tenant, execution_id, "sandbox")
        authority_id = uid()
        store.create_authority_snapshot(
            tenant,
            authority_id,
            AuthoritySnapshot(
                uid(),
                environment["environment_id"],
                "policy-v1",
                frozenset({"tool.execute"}),
            ),
        )
        identity = ExecutorIdentity("executor-a", 2)
        store.register_executor(tenant, environment["environment_id"], identity)
        store.transition_task(
            tenant,
            task_id,
            TaskState.RUNNING,
            idempotency_key="run-control",
            actor_id="temporal-worker",
        )
        value = TaskWorkflowInput(
            tenant,
            project,
            task_id,
            execution_id,
            environment["environment_id"],
            authority_id,
            identity.executor_id,
            identity.generation,
            request,
            digest(request),
        )
        service = TemporalTaskActivity(store, object(), actor_id="temporal-worker")
        paused = asyncio.run(
            service.control(
                {"value": value.to_dict(), "action": "PAUSE", "control_sequence": 1}
            )
        )
        resumed = asyncio.run(
            service.control(
                {"value": value.to_dict(), "action": "RESUME", "control_sequence": 2}
            )
        )
        self.assertEqual((paused["status"], resumed["status"]), ("PAUSED", "RUNNING"))
        asyncio.run(
            service.control(
                {"value": value.to_dict(), "action": "PAUSE", "control_sequence": 3}
            )
        )
        store.register_executor(
            tenant,
            environment["environment_id"],
            ExecutorIdentity("executor-b", 3),
        )
        with self.assertRaises(StaleGenerationError):
            asyncio.run(
                service.control(
                    {
                        "value": value.to_dict(),
                        "action": "RESUME",
                        "control_sequence": 4,
                    }
                )
            )
        cancelled = asyncio.run(
            service.control(
                {"value": value.to_dict(), "action": "CANCEL", "control_sequence": 5}
            )
        )
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertEqual(store.get_task(tenant, task_id)["status"], "CANCELLED")
        store.close()


class FakeEd25519:
    @staticmethod
    def sign_with_private_key(private_key, payload):
        return hashlib.sha256(private_key + payload).digest()

    @staticmethod
    def verify(public_key, signature, payload):
        if signature != hashlib.sha256(public_key + payload).digest():
            raise ValueError("bad signature")


class VerifierTests(unittest.TestCase):
    def statement(self, scope="postgresql", subject="sha256:" + "a" * 64):
        return EvidenceStatement(
            uid(),
            scope,
            "producer",
            "engineering.example",
            subject,
            "sha256:" + "b" * 64,
            ("sha256:" + "c" * 64,),
            "AUTH-1",
            "runner-1",
            when(timedelta(minutes=-2)),
            when(timedelta(minutes=-1)),
            "PASS",
        )

    def trust(self):
        trusted = TrustedVerifier(
            "verifier",
            "audit.example",
            "key-1",
            b"k" * 32,
            when(timedelta(hours=-1)),
            when(timedelta(hours=1)),
            allowed_scopes=frozenset(
                {"postgresql", "external_gate_acceptance:P1-G07"}
            ),
        )
        return VerifierTrustStore([trusted], backend=FakeEd25519())

    def sign(self, statement):
        signer = IndependentVerifierSigner(
            verifier_id="verifier",
            trust_domain="audit.example",
            key_id="key-1",
            private_key=b"k" * 32,
            backend=FakeEd25519(),
        )
        return signer.sign(
            statement,
            receipt_id=uid(),
            verdict="VERIFIED",
            issued_at=when(timedelta(minutes=-1)),
            expires_at=when(timedelta(hours=1)),
        )

    def test_signed_receipt_rejects_tamper_and_registry_is_idempotent(self) -> None:
        statement = self.statement()
        receipt = self.sign(statement)
        verified = self.trust().verify(
            receipt, expected_subject_digest=statement.subject_digest
        )
        registry = VerificationReceiptRegistry()
        first = registry.accept(receipt, verified)
        second = registry.accept(receipt, verified)
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        with self.assertRaises(PolicyDeniedError):
            self.trust().verify(receipt, expected_subject_digest="sha256:" + "d" * 64)
        registry.close()
        self.assertFalse(
            external_gate_decision([first], {"postgresql", "temporal"})["certified"]
        )


class FakeBackupAdapter:
    component = "postgresql"

    def capture(self, destination, *, authorization_id):
        path = destination / "backup.age"
        path.write_bytes(b"age-encryption.org/v1\nfixture")
        return (
            BackupObject(
                self.component,
                "database",
                path,
                digest_bytes(path.read_bytes()),
                path.stat().st_size,
                utc_now(),
                True,
                "kms://key-1",
            ),
        )

    def restore(self, objects, target, *, authorization_id):
        return {
            "status": "PASS",
            "evidence_digest": digest(
                {"objects": len(objects), "target": target.to_dict()}
            ),
        }


class DisasterRecoveryTests(unittest.TestCase):
    def test_corrupt_backup_is_rejected_and_isolated_restore_measures_objectives(
        self,
    ) -> None:
        orchestrator = DisasterRecoveryOrchestrator([FakeBackupAdapter()])
        with tempfile.TemporaryDirectory(prefix="pi-dr-") as root:
            destination = Path(root).resolve() / "backup"
            manifest = orchestrator.capture(
                backup_id=uid(),
                source=target("source"),
                destination=destination,
                authorization_id="AUTH-1",
            )
            restore_target = target("dr-rehearsal")
            request = {
                "backup_id": manifest.backup_id,
                "manifest_digest": manifest.to_dict()["manifest_digest"],
            }
            restore_operation_id = uid()
            grant = approval(
                restore_operation_id, digest(request), restore_target, "dr_restore"
            )
            result = orchestrator.rehearse_restore(
                manifest,
                restore_operation_id=restore_operation_id,
                target=restore_target,
                grant=grant,
                actor_id="operator",
                verifiers=[
                    lambda _target: {
                        "status": "PASS",
                        "evidence_digest": "sha256:" + "e" * 64,
                    }
                ],
                maximum_rpo_seconds=60,
                maximum_rto_seconds=60,
            )
            self.assertEqual(result["status"], "PASS")
            manifest.objects[0].path.write_bytes(b"tampered")
            with self.assertRaises(ConflictError):
                orchestrator.rehearse_restore(
                    manifest,
                    restore_operation_id=restore_operation_id,
                    target=restore_target,
                    grant=grant,
                    actor_id="operator",
                    verifiers=[],
                    maximum_rpo_seconds=60,
                    maximum_rto_seconds=60,
                )

    def test_postgres_restore_is_bound_to_exact_target_and_private_identity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-dr-config-") as temporary:
            root = Path(temporary).resolve()
            identity = root / "age.key"
            identity.write_text("AGE-SECRET-KEY-TEST", encoding="utf-8")
            identity.chmod(0o600)
            services = root / "pg_service.conf"
            services.write_text("[source]\n[restore]\n", encoding="utf-8")
            services.chmod(0o600)
            approved_target = target("dr-rehearsal")
            executable_digest = digest_bytes(Path("/usr/bin/true").read_bytes())
            service_digest = digest_bytes(services.read_bytes())
            config = PostgresBackupConfig(
                source_service="source",
                restore_service="restore",
                pg_dump=Path("/usr/bin/true"),
                pg_restore=Path("/usr/bin/true"),
                age_binary=Path("/usr/bin/true"),
                age_recipient="age1testrecipient",
                age_identity=identity,
                pg_service_file=services,
                restore_target_digest=digest(approved_target.to_dict()),
                pg_dump_digest=executable_digest,
                pg_restore_digest=executable_digest,
                age_binary_digest=executable_digest,
                pg_service_file_digest=service_digest,
                key_reference="secret://age/dr-key",
            )
            encrypted = root / "backup.age"
            encrypted.write_bytes(b"age-encryption.org/v1\nfixture")
            backup = BackupObject(
                "postgresql",
                "database",
                encrypted,
                digest_bytes(encrypted.read_bytes()),
                encrypted.stat().st_size,
                utc_now(),
                True,
                config.key_reference,
            )
            adapter = object.__new__(PostgresLogicalBackupAdapter)
            adapter.config = config
            with self.assertRaises(PolicyDeniedError):
                adapter.restore(
                    (backup,),
                    target("different-dr-target"),
                    authorization_id="AUTH-RESTORE",
                )

            identity.chmod(0o644)
            with self.assertRaises(PolicyDeniedError):
                PostgresBackupConfig(
                    source_service="source",
                    restore_service="restore",
                    pg_dump=Path("/usr/bin/true"),
                    pg_restore=Path("/usr/bin/true"),
                    age_binary=Path("/usr/bin/true"),
                    age_recipient="age1testrecipient",
                    age_identity=identity,
                    pg_service_file=services,
                    restore_target_digest=digest(approved_target.to_dict()),
                    pg_dump_digest=executable_digest,
                    pg_restore_digest=executable_digest,
                    age_binary_digest=executable_digest,
                    pg_service_file_digest=service_digest,
                    key_reference="secret://age/dr-key",
                )


class FakeDeploymentAdapter:
    def __init__(self):
        self.target = target("production")

    def deploy_canary(self, manifest, *, idempotency_key):
        return {
            "status": "SUCCEEDED",
            "native_release_id": "release-native-1",
            "raw_evidence_digest": "sha256:" + "1" * 64,
        }

    def observe(self, native_release_id, required_slos):
        return {
            "status": "SUCCEEDED",
            "metrics": {"availability_min": 1.0, "error_rate_max": 0.001},
            "raw_evidence_digest": "sha256:" + "2" * 64,
        }

    def promote(self, native_release_id, *, idempotency_key):
        return {"status": "SUCCEEDED", "raw_evidence_digest": "sha256:" + "3" * 64}

    def rollback(self, native_release_id, rollback_artifact_digest, *, idempotency_key):
        return {"status": "SUCCEEDED", "raw_evidence_digest": "sha256:" + "4" * 64}

    def reconcile(self, release_id, native_release_id, expected_state):
        return {
            "state": expected_state,
            "native_release_id": native_release_id,
            "raw_evidence_digest": "sha256:" + "5" * 64,
        }


class UnknownCanaryDeploymentAdapter(FakeDeploymentAdapter):
    def deploy_canary(self, manifest, *, idempotency_key):
        return {"status": "UNKNOWN", "submission_token": idempotency_key}

    def reconcile(self, release_id, native_release_id, expected_state):
        return {
            "state": expected_state,
            "native_release_id": "release-recovered-1",
            "raw_evidence_digest": "sha256:" + "6" * 64,
        }


class CrashCanaryDeploymentAdapter(FakeDeploymentAdapter):
    def deploy_canary(self, manifest, *, idempotency_key):
        raise KeyboardInterrupt("simulated process termination")


class UnknownPromotionDeploymentAdapter(FakeDeploymentAdapter):
    def promote(self, native_release_id, *, idempotency_key):
        raise TimeoutError("provider response lost")


class AcceptanceAndDeploymentTests(VerifierTests):
    def test_uat_requires_external_customer_signoff(self) -> None:
        run = AcceptanceRunner().run(
            run_id=uid(),
            tenant_id=uid(),
            target=target(),
            cases=[
                AcceptanceCase("UAT-1", "create task", "operator", {"created": True})
            ],
            executor=lambda _case: {
                "actual_outcome": {"created": True},
                "evidence_digest": "sha256:" + "a" * 64,
            },
            authorization_id="AUTH-UAT",
            executor_id="customer-uat-runner",
            producer_trust_domain="engineering.example",
        )
        statement = EvidenceStatement(
            uid(),
            "external_gate_acceptance:P1-G07",
            run["executor_id"],
            run["producer_trust_domain"],
            run["result_digest"],
            run["environment_digest"],
            tuple(item["evidence_digest"] for item in run["results"]),
            run["authorization_id"],
            run["executor_id"],
            run["started_at"],
            run["completed_at"],
            "PASS",
        )
        signer = IndependentVerifierSigner(
            verifier_id="verifier",
            trust_domain="audit.example",
            key_id="key-1",
            private_key=b"k" * 32,
            backend=FakeEd25519(),
        )
        receipt = signer.sign(
            statement,
            receipt_id=uid(),
            verdict="VERIFIED",
            issued_at=run["completed_at"],
            expires_at=when(timedelta(hours=1)),
        )
        accepted = accept_customer_signoff(
            run,
            receipt,
            self.trust(),
            implementation_trust_domain="engineering.example",
            customer_authority_id="verifier",
            customer_trust_domain="audit.example",
        )
        self.assertEqual(accepted["status"], "ACCEPTED")
        self.assertFalse(accepted["certified"])
        tampered = dict(run)
        tampered["authorization_id"] = "AUTH-TAMPERED"
        with self.assertRaises(PolicyDeniedError):
            accept_customer_signoff(
                tampered,
                receipt,
                self.trust(),
                implementation_trust_domain="engineering.example",
                customer_authority_id="verifier",
                customer_trust_domain="audit.example",
            )

    def test_canary_observation_and_promotion_are_separate_approved_steps(self) -> None:
        adapter = FakeDeploymentAdapter()
        manifest = DeploymentManifest(
            uid(),
            "sha256:" + "a" * 64,
            "sha256:" + "b" * 64,
            "sha256:" + "c" * 64,
            "sha256:" + "d" * 64,
            "sha256:" + "e" * 64,
            "5.1.0+1",
            adapter.target,
            "sha256:" + "f" * 64,
            {"availability_min": 0.999, "error_rate_max": 0.01},
        )
        controller = DeploymentController(adapter)
        tenant = uid()
        started = controller.start_canary(
            tenant_id=tenant,
            actor_id="release-operator",
            manifest=manifest,
            approval=approval(
                manifest.release_id,
                manifest.manifest_digest,
                adapter.target,
                "deploy_canary",
            ),
        )
        self.assertEqual(started["state"], "CANARY")
        self.assertEqual(
            controller.observe_canary(tenant, manifest.release_id, actor_id="observer")[
                "state"
            ],
            "CANARY_PASS",
        )
        promoted = controller.promote(
            tenant,
            manifest.release_id,
            approval(
                manifest.release_id,
                manifest.manifest_digest,
                adapter.target,
                "promote_release",
                approver="release-approver",
            ),
            actor_id="release-operator",
        )
        self.assertEqual(promoted["state"], "PROMOTED")
        self.assertFalse(promoted["certified"])
        controller.close()

    def test_production_config_rejects_static_token_and_public_network(self) -> None:
        bad = validate_production_configuration(
            {
                "database_backend": "sqlite",
                "static_api_token_enabled": True,
                "tls_mode": "server",
                "allow_public_ingress": True,
                "default_network_egress": "allow",
            }
        )
        self.assertFalse(bad["valid"])
        self.assertIn("static_api_token_must_be_disabled", bad["policy_denials"])
        exact_store = {
            "bucket": "pi-harness-production",
            "region": "ap-southeast-1",
            "account_id": "123456789012",
            "kms_key_arn": "arn:aws:kms:ap-southeast-1:123456789012:key/key-1",
            "public_access": False,
        }
        valid = validate_production_configuration(
            {
                "postgres_dsn_reference": "aws-secretsmanager://pi-harness/postgres",
                "temporal_target": {
                    "endpoint": "temporal.internal:7233",
                    "namespace": "pi-production",
                    "server_version": "1.31.2",
                    "mtls": True,
                },
                "oidc_issuer": "https://idp.example.test/",
                "oidc_audience": "pi-harness",
                "mtls_trust_domain": "mesh.example",
                "artifact_store": exact_store,
                "immutable_evidence_store": exact_store
                | {
                    "object_lock": True,
                    "versioning": True,
                    "retention_mode": "COMPLIANCE",
                    "retention_days": 365,
                },
                "cloud_provider": "aws",
                "region": "ap-southeast-1",
                "account_id": "123456789012",
                "backup_policy_id": "backup-policy-v1",
                "verifier_trust_store": "trust-store-v1",
                "slo_profile": "slo-v1",
                "private_endpoints": ["s3", "kms", "secretsmanager", "temporal"],
                "database_backend": "postgresql",
                "static_api_token_enabled": False,
                "tls_mode": "mutual",
                "allow_public_ingress": False,
                "default_network_egress": "deny",
                "secrets_inline": False,
            }
        )
        self.assertTrue(valid["valid"])
        self.assertFalse(valid["certified"])

    def test_unknown_canary_requires_reconciliation_before_observation(self) -> None:
        adapter = UnknownCanaryDeploymentAdapter()
        manifest = DeploymentManifest(
            uid(),
            "sha256:" + "a" * 64,
            "sha256:" + "b" * 64,
            "sha256:" + "c" * 64,
            "sha256:" + "d" * 64,
            "sha256:" + "e" * 64,
            "5.1.0+1",
            adapter.target,
            "sha256:" + "f" * 64,
            {"availability_min": 0.999},
        )
        tenant = uid()
        controller = DeploymentController(adapter)
        pending = controller.start_canary(
            tenant_id=tenant,
            actor_id="release-operator",
            manifest=manifest,
            approval=approval(
                manifest.release_id,
                manifest.manifest_digest,
                adapter.target,
                "deploy_canary",
            ),
        )
        self.assertEqual(pending["state"], "RECONCILIATION_REQUIRED")
        with self.assertRaises(ConflictError):
            controller.observe_canary(tenant, manifest.release_id, actor_id="observer")
        reconciled = controller.reconcile(
            tenant, manifest.release_id, actor_id="reconciler"
        )
        self.assertEqual(
            (reconciled["state"], reconciled["native_release_id"]),
            ("CANARY", "release-recovered-1"),
        )
        controller.close()

    def test_release_identity_is_tenant_bound_and_slo_contract_is_strict(self) -> None:
        adapter = FakeDeploymentAdapter()
        manifest = DeploymentManifest(
            uid(),
            "sha256:" + "a" * 64,
            "sha256:" + "b" * 64,
            "sha256:" + "c" * 64,
            "sha256:" + "d" * 64,
            "sha256:" + "e" * 64,
            "5.1.0+tenant",
            adapter.target,
            "sha256:" + "f" * 64,
            {"availability_min": 0.999},
        )
        controller = DeploymentController(adapter)
        tenant = uid()
        controller.start_canary(
            tenant_id=tenant,
            actor_id="release-operator",
            manifest=manifest,
            approval=approval(
                manifest.release_id,
                manifest.manifest_digest,
                adapter.target,
                "deploy_canary",
            ),
        )
        with self.assertRaises(ConflictError):
            controller.start_canary(
                tenant_id=uid(),
                actor_id="release-operator",
                manifest=manifest,
                approval=approval(
                    manifest.release_id,
                    manifest.manifest_digest,
                    adapter.target,
                    "deploy_canary",
                ),
            )
        with self.assertRaises(ValueError):
            DeploymentManifest(
                uid(),
                "sha256:" + "a" * 64,
                "sha256:" + "b" * 64,
                "sha256:" + "c" * 64,
                "sha256:" + "d" * 64,
                "sha256:" + "e" * 64,
                "5.1.0+invalid-slo",
                adapter.target,
                "sha256:" + "f" * 64,
                {"availability": float("nan")},
            )
        controller.close()

    def test_crashed_submission_and_unknown_promotion_require_reconciliation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-deploy-") as temporary:
            journal = Path(temporary).resolve() / "deployment.db"
            crash_adapter = CrashCanaryDeploymentAdapter()
            manifest = DeploymentManifest(
                uid(),
                "sha256:" + "a" * 64,
                "sha256:" + "b" * 64,
                "sha256:" + "c" * 64,
                "sha256:" + "d" * 64,
                "sha256:" + "e" * 64,
                "5.1.0+crash",
                crash_adapter.target,
                "sha256:" + "f" * 64,
                {"availability_min": 0.999},
            )
            tenant = uid()
            controller = DeploymentController(crash_adapter, str(journal))
            with self.assertRaises(KeyboardInterrupt):
                controller.start_canary(
                    tenant_id=tenant,
                    actor_id="release-operator",
                    manifest=manifest,
                    approval=approval(
                        manifest.release_id,
                        manifest.manifest_digest,
                        crash_adapter.target,
                        "deploy_canary",
                    ),
                )
            self.assertEqual(
                controller.get(tenant, manifest.release_id)["state"],
                "SUBMITTING_CANARY",
            )
            controller.close()

            recovered = DeploymentController(
                UnknownCanaryDeploymentAdapter(), str(journal)
            )
            self.assertEqual(
                recovered.reconcile(
                    tenant, manifest.release_id, actor_id="reconciler"
                )["state"],
                "CANARY",
            )
            recovered.close()

        adapter = UnknownPromotionDeploymentAdapter()
        manifest = DeploymentManifest(
            uid(),
            "sha256:" + "1" * 64,
            "sha256:" + "2" * 64,
            "sha256:" + "3" * 64,
            "sha256:" + "4" * 64,
            "sha256:" + "5" * 64,
            "5.1.0+promotion",
            adapter.target,
            "sha256:" + "6" * 64,
            {"availability_min": 0.999},
        )
        tenant = uid()
        controller = DeploymentController(adapter)
        controller.start_canary(
            tenant_id=tenant,
            actor_id="release-operator",
            manifest=manifest,
            approval=approval(
                manifest.release_id,
                manifest.manifest_digest,
                adapter.target,
                "deploy_canary",
            ),
        )
        controller.observe_canary(tenant, manifest.release_id, actor_id="observer")
        unknown = controller.promote(
            tenant,
            manifest.release_id,
            approval(
                manifest.release_id,
                manifest.manifest_digest,
                adapter.target,
                "promote_release",
            ),
            actor_id="release-operator",
        )
        self.assertEqual(unknown["state"], "RECONCILIATION_REQUIRED")
        self.assertEqual(unknown["pending_state"], "PROMOTED")
        self.assertEqual(
            controller.reconcile(
                tenant, manifest.release_id, actor_id="reconciler"
            )["state"],
            "PROMOTED",
        )
        controller.close()


class PostgresAndArtifactTests(unittest.TestCase):
    def test_postgres_profile_and_fixed_sql_translation(self) -> None:
        config = PostgresConfig("service=pi_staging")
        self.assertEqual(config.required_server_major, 16)
        translated = _translate_kernel_sql(
            "SELECT payload_json FROM task_event WHERE tenant_id=? AND task_id=?"
        )
        self.assertEqual(
            translated,
            "SELECT payload FROM pi_task_event WHERE tenant_id=%s AND task_id=%s",
        )
        with tempfile.TemporaryDirectory(prefix="pi-migrations-") as root:
            path = Path(root) / "001_one.sql"
            path.write_text("SELECT 1;", encoding="utf-8")
            records = PostgresMigrator(config, Path(root)).discover()
            self.assertEqual(
                (records[0].version, records[0].sha256),
                ("001", digest_bytes(b"SELECT 1;")),
            )

    def test_s3_backend_requires_account_region_encryption_and_verifies_content(
        self,
    ) -> None:
        class STS:
            def get_caller_identity(self):
                return {"Account": "123456789012"}

        class NotFound(Exception):
            def __init__(self):
                self.response = {"Error": {"Code": "404"}}

        class S3:
            def __init__(self):
                self.objects = {}

            def get_bucket_location(self, **_kwargs):
                return {"LocationConstraint": "ap-southeast-1"}

            def get_public_access_block(self, **_kwargs):
                return {
                    "PublicAccessBlockConfiguration": {
                        name: True
                        for name in (
                            "BlockPublicAcls",
                            "IgnorePublicAcls",
                            "BlockPublicPolicy",
                            "RestrictPublicBuckets",
                        )
                    }
                }

            def get_bucket_encryption(self, **_kwargs):
                return {
                    "ServerSideEncryptionConfiguration": {
                        "Rules": [
                            {
                                "ApplyServerSideEncryptionByDefault": {
                                    "KMSMasterKeyID": "arn:aws:kms:ap-southeast-1:123456789012:key/key-1"
                                }
                            }
                        ]
                    }
                }

            def head_object(self, Bucket, Key):
                if Key not in self.objects:
                    raise NotFound()
                value = self.objects[Key]
                return {
                    "ContentLength": len(value),
                    "Metadata": {"sha256": digest_bytes(value)},
                }

            def put_object(self, Bucket, Key, Body, **_kwargs):
                self.objects[Key] = Body

            def get_object(self, Bucket, Key):
                class Body:
                    def __init__(self, value):
                        self.value = value

                    def read(self):
                        return self.value

                return {"Body": Body(self.objects[Key])}

        config = S3ArtifactConfig(
            "pi-artifacts",
            "ap-southeast-1",
            "123456789012",
            "arn:aws:kms:ap-southeast-1:123456789012:key/key-1",
        )
        backend = S3ArtifactBackend(config, s3_client=S3(), sts_client=STS())
        content = b"artifact"
        tenant = uid()
        uri = backend.put(tenant, digest_bytes(content), content, {})
        self.assertTrue(uri.startswith("s3://pi-artifacts/"))
        self.assertEqual(backend.get(tenant, digest_bytes(content)), content)


class QualificationTests(unittest.TestCase):
    def test_all_code_surfaces_exist_but_external_evidence_is_not_fabricated(
        self,
    ) -> None:
        inventory = implementation_inventory()
        self.assertEqual(inventory["implementation_status"], "CODE_COMPLETE")
        self.assertEqual(inventory["external_evidence"], "NOT_RUN")
        self.assertEqual(inventory["certification"], "NOT_CERTIFIED")
        self.assertFalse(inventory["certified"])
        self.assertEqual(len(inventory["gaps"]), 8)


if __name__ == "__main__":
    unittest.main()
