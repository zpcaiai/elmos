import hashlib
import tempfile
import time
import unittest
from pathlib import Path

from elmos_openhands.artifacts import ContentAddressedStore
from elmos_openhands.errors import (
    ContractViolation,
    CorruptState,
    IdempotencyConflict,
    LeaseLost,
    TenantIsolationError,
)
from elmos_openhands.ledger import EventLedger
from elmos_openhands.models import Identity
from elmos_openhands.persistence import S3ContentAddressedStore, TransactionalOutboxDispatcher
from elmos_openhands.postgres import PostgresEventLedger
from elmos_openhands.sandbox import (
    InMemorySecretBroker,
    KubernetesSandboxBackend,
    MountSpec,
    NetworkPolicy,
    ProductionSandboxProvider,
    SandboxExecRequest,
    SandboxExecResult,
    SandboxQuotas,
    SandboxSpec,
    SandboxStats,
)
from elmos_openhands.workspace import IsolationClass, LocalWorkspaceProvider, WorkspaceRequest
from elmos_openhands.workspace_api import (
    FileRange,
    GitOperation,
    LocalWorkspaceApi,
    PatchOperation,
    PatchSet,
    WorkspaceMutationStore,
)


class FakeS3:
    def __init__(self):
        self.objects = {}

    def head_bucket(self, **kwargs):
        return {}

    def get_bucket_versioning(self, **kwargs):
        return {"Status": "Enabled"}

    def head_object(self, **kwargs):
        if kwargs["Key"] not in self.objects:
            raise KeyError(kwargs["Key"])
        return self.objects[kwargs["Key"]][1]

    def put_object(self, **kwargs):
        self.objects[kwargs["Key"]] = (kwargs["Body"], {"Metadata": kwargs["Metadata"]})
        return {"ChecksumSHA256": kwargs["ChecksumSHA256"]}

    def get_object(self, **kwargs):
        data, metadata = self.objects[kwargs["Key"]]
        return {"Body": data, **metadata}


class CapturingPublisher:
    def __init__(self, fail=False):
        self.fail = fail
        self.messages = []

    def publish(self, subject, payload, *, message_key, headers):
        if self.fail:
            raise RuntimeError("bus unavailable")
        self.messages.append((subject, payload, message_key, dict(headers)))


class _Scope:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FakePostgresCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 1
        self.current = None

    def execute(self, query, params=()):
        normalized = " ".join(query.split())
        self.connection.statements.append((normalized, tuple(params)))
        if normalized.startswith("SELECT * FROM oh_execution_runs"):
            self.current = {
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "task_id": "task-a",
                "run_id": "run-a",
                "node_id": "root",
                "status": "queued",
                "manifest_hash": "sha256:" + "a" * 64,
                "created_at": "2026-08-28T00:00:00Z",
            }
        elif normalized.startswith("SELECT manifest_hash FROM oh_execution_runs"):
            self.current = {"manifest_hash": "sha256:" + "a" * 64}
        elif normalized.startswith("SELECT 1 FROM oh_execution_runs"):
            self.current = {"exists": 1}
        elif normalized.startswith(("SELECT * FROM oh_execution_events", "SELECT seq,digest FROM oh_execution_events")):
            self.current = None
        else:
            self.current = None

    def executemany(self, query, params):
        for item in params:
            self.execute(query, item)

    def fetchone(self):
        return self.current

    def fetchall(self):
        return []


class FakePostgresConnection:
    def __init__(self):
        self.statements = []
        self.closed = False
        self.transactions = 0

    def transaction(self):
        self.transactions += 1
        return _Scope(self)

    def cursor(self):
        return _Scope(FakePostgresCursor(self))

    def close(self):
        self.closed = True


class FakeSandboxBackend:
    name = "fake-l4"
    supported_isolation = frozenset({IsolationClass.L4})

    def __init__(self):
        self.destroyed = []
        self.files = {}
        self.executions = 0
        self.restores = 0
        self.fail_restore_once = False

    def create(self, sandbox_id, spec):
        return "backend-" + sandbox_id

    def exec(self, backend_ref, request, secrets):
        self.executions += 1
        now = time.time()
        leaked = b"" if not secrets else b":" + next(iter(secrets.values())).encode()
        return SandboxExecResult(0, b"ok:" + str(len(secrets)).encode() + leaked, b"", now, now + 0.1)

    def snapshot(self, backend_ref):
        return "sha256:" + "a" * 64

    def restore(self, sandbox_id, snapshot_ref, spec):
        self.restores += 1
        if self.fail_restore_once:
            self.fail_restore_once = False
            raise RuntimeError("restore outcome unknown")
        return "restored-" + sandbox_id

    def stats(self, backend_ref):
        return SandboxStats(1.0, 1024, 2048, 2, time.time())

    def destroy(self, backend_ref):
        self.destroyed.append(backend_ref)

    def read_file(self, backend_ref, path, start, length):
        data = self.files[(backend_ref, path)]
        return data[start:] if length is None else data[start : start + length]

    def write_file(self, backend_ref, path, data, expected_digest, idempotency_key):
        previous = self.files.get((backend_ref, path))
        previous_digest = None if previous is None else "sha256:" + hashlib.sha256(previous).hexdigest()
        if expected_digest is not None and expected_digest != previous_digest:
            raise ContractViolation("CAS mismatch")
        self.files[(backend_ref, path)] = data
        return {"previous_digest": previous_digest, "digest": "sha256:" + hashlib.sha256(data).hexdigest(), "size_bytes": len(data), "changed": previous != data}

    def apply_patch(self, backend_ref, operations, idempotency_key):
        return {"changed_paths": [item["path"] for item in operations], "before_digest": "sha256:" + "1" * 64, "after_digest": "sha256:" + "2" * 64, "receipt_digest": "sha256:" + "3" * 64}

    def git(self, backend_ref, operation, args, idempotency_key):
        return {"exit_code": 0, "stdout": "ok", "stderr": "", "head_before": "a", "head_after": "b", "changed": True}

    def expose_port(self, backend_ref, spec):
        return {"endpoint_id": "endpoint-a", "url": "https://sandbox.invalid", "expires_at": time.time() + 60, "auth_reference": "lease-a"}


class FakeKubernetesClient:
    def __init__(self):
        self.pod = None
        self.network_policy = None
        self.exec_request = None

    def resolve_namespaced_sandbox_mounts(self, **kwargs):
        mount = kwargs["mounts"][0]
        return {
            "volumes": [{"name": "approved", "persistentVolumeClaim": {"claimName": "tenant-pvc"}}],
            "volume_mounts": [{"name": "approved", "mountPath": mount["target"], "readOnly": mount["read_only"]}],
        }

    def create_namespaced_pod(self, **kwargs):
        self.pod = kwargs["body"]

    def apply_namespaced_network_policy(self, **kwargs):
        self.network_policy = kwargs["body"]

    def exec_namespaced_pod(self, **kwargs):
        self.exec_request = kwargs
        return {"exit_code": 0, "stdout": b"ok", "stderr": b""}

    def restore_namespaced_pod(self, **kwargs):
        return {"pod_name": kwargs["name"], "snapshot_digest": kwargs["snapshot_digest"], "network_policy_attached": True}

    def delete_namespaced_pod(self, **kwargs):
        return None


class PersistenceSandboxWorkspaceTests(unittest.TestCase):
    def test_postgres_adapter_binds_rls_and_atomically_appends_outbox(self):
        connection = FakePostgresConnection()
        ledger = PostgresEventLedger(connection)
        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        manifest_hash = "sha256:" + "a" * 64

        run = ledger.create_run(identity, manifest_hash)
        event = ledger.append(identity, "run.status", {"status": "running"}, idempotency_key="status-a")
        checkpoint_id = ledger.save_checkpoint(
            identity,
            event_seq=event.seq,
            manifest_hash=manifest_hash,
            state={"status": "running"},
        )

        self.assertEqual(run.identity, identity)
        self.assertEqual(event.seq, 0)
        self.assertEqual(event.digest, event.computed_digest())
        self.assertTrue(checkpoint_id.startswith("checkpoint_"))
        statements = connection.statements
        tenant_bindings = [params for sql, params in statements if "set_config('elmos.tenant_id'" in sql]
        self.assertEqual(tenant_bindings, [("tenant-a",)] * 3)
        self.assertTrue(any("pg_advisory_xact_lock" in sql for sql, _ in statements))
        self.assertTrue(any(sql.startswith("INSERT INTO oh_execution_events") for sql, _ in statements))
        self.assertTrue(any(sql.startswith("INSERT INTO oh_execution_outbox") for sql, _ in statements))
        self.assertTrue(any(sql.startswith("INSERT INTO oh_checkpoints") for sql, _ in statements))
        self.assertEqual(connection.transactions, 3)
        ledger.close()
        self.assertTrue(connection.closed)

    def test_s3_cas_is_tenant_scoped_encrypted_and_digest_verified(self):
        client = FakeS3()
        store = S3ContentAddressedStore("bucket-a", client=client, kms_key_id="kms-key")
        ref = store.put("tenant-a", b"payload", kind="evidence")
        self.assertEqual(store.get("tenant-a", ref), b"payload")
        request_metadata = next(iter(client.objects.values()))[1]["Metadata"]
        self.assertEqual(request_metadata["tenant-id"], "tenant-a")
        with self.assertRaises(TenantIsolationError):
            store.get("tenant-b", ref)
        key = next(iter(client.objects))
        client.objects[key] = (b"tampered", client.objects[key][1])
        with self.assertRaises(CorruptState):
            store.get("tenant-a", ref)

    def test_outbox_is_marked_only_after_broker_ack(self):
        ledger = EventLedger()
        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        ledger.create_run(identity, "sha256:" + "a" * 64)
        ledger.append(identity, "run.status", {"status": "running"}, idempotency_key="status")
        with self.assertRaises(RuntimeError):
            TransactionalOutboxDispatcher(ledger, CapturingPublisher(fail=True)).dispatch_once()
        self.assertEqual(len(ledger.pending_outbox()), 1)
        publisher = CapturingPublisher()
        self.assertEqual(TransactionalOutboxDispatcher(ledger, publisher).dispatch_once(), 1)
        self.assertEqual(len(ledger.pending_outbox()), 0)
        self.assertEqual(publisher.messages[0][3]["tenant-id"], "tenant-a")
        ledger.close()

    def test_production_sandbox_fencing_secret_revocation_and_idempotency(self):
        backend = FakeSandboxBackend()
        broker = InMemorySecretBroker({("tenant-a", "provider-token"): "secret"})
        provider = ProductionSandboxProvider(backend, secret_broker=broker, lease_seconds=10)
        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        spec = SandboxSpec(identity, IsolationClass.L4, "sha256:" + "b" * 64, "cn-east", SandboxQuotas(output_bytes=100), NetworkPolicy("deny"))
        handle = provider.create(spec, idempotency_key="create-a", now=10)
        self.assertEqual(provider.create(spec, idempotency_key="create-a", now=11).sandbox_id, handle.sandbox_id)
        lease = broker.issue(identity, "provider-token", "sandbox-exec", ttl_seconds=30)
        request = SandboxExecRequest(("true",), "exec-a", secret_leases=(lease.lease_id,))
        result = provider.exec(handle, request, now=11)
        self.assertEqual(result.stdout, b"ok:1:[REDACTED_SECRET]")
        self.assertEqual(provider.exec(handle, request, now=12).digest, result.digest)
        self.assertEqual(backend.executions, 1)
        with self.assertRaises(LeaseLost):
            broker.resolve(identity, lease.lease_id, purpose="sandbox-exec", now=12)
        with self.assertRaises(IdempotencyConflict):
            provider.exec(handle, SandboxExecRequest(("false",), "exec-a"), now=12)
        forged = Identity("tenant-b", "project-a", "task-a", "run-a")
        with self.assertRaises(TenantIsolationError):
            provider.stats(handle.__class__(handle.sandbox_id, forged, handle.backend, handle.backend_ref, handle.region, handle.isolation_class, handle.image_digest, handle.state, handle.fencing_token, handle.expires_at, handle.spec_digest))
        forged_project = Identity("tenant-a", "project-b", "task-a", "run-a")
        forged_handle = handle.__class__(handle.sandbox_id, forged_project, handle.backend, handle.backend_ref, handle.region, handle.isolation_class, handle.image_digest, handle.state, handle.fencing_token, handle.expires_at, handle.spec_digest)
        with self.assertRaises(TenantIsolationError):
            provider.stats(forged_handle)
        with self.assertRaises(TenantIsolationError):
            provider.destroy(forged_handle)
        scoped_lease = broker.issue(identity, "provider-token", "sandbox-exec", ttl_seconds=30)
        with self.assertRaises(TenantIsolationError):
            broker.resolve(forged_project, scoped_lease.lease_id, purpose="sandbox-exec", now=12)
        broker.revoke(identity, scoped_lease.lease_id)
        snapshot = "sha256:" + "d" * 64
        restored = provider.restore(spec, snapshot, idempotency_key="restore-a", now=12)
        self.assertEqual(provider.restore(spec, snapshot, idempotency_key="restore-a", now=13).sandbox_id, restored.sandbox_id)
        self.assertEqual(backend.restores, 1)
        backend.fail_restore_once = True
        unknown_snapshot = "sha256:" + "e" * 64
        with self.assertRaises(RuntimeError):
            provider.restore(spec, unknown_snapshot, idempotency_key="restore-unknown", now=13)
        with self.assertRaises(LeaseLost):
            provider.restore(spec, unknown_snapshot, idempotency_key="restore-unknown", now=13)
        reconciled = provider.reconcile_restore(
            spec,
            unknown_snapshot,
            idempotency_key="restore-unknown",
            resolver=lambda sandbox_id, snapshot_ref, resolved_spec, key: {"status": "absent", "sandbox_id": sandbox_id, "snapshot_ref": snapshot_ref, "spec_digest": resolved_spec.image_digest, "idempotency_key": key},
            verifier=lambda outcome, evidence: outcome["status"] == "absent" and evidence.startswith("sha256:"),
            executor_id="sandbox-reconciler-a",
            verifier_id="sandbox-verifier-b",
            evidence_ref="sha256:" + "f" * 64,
            now=14,
        )
        self.assertEqual(backend.restores, 3)
        provider.destroy(reconciled)
        provider.destroy(restored)
        provider.destroy(handle)
        provider.close()

    def test_kubernetes_backend_scopes_network_mounts_secrets_and_restore_attestation(self):
        client = FakeKubernetesClient()
        backend = KubernetesSandboxBackend(client)
        identity = Identity("tenant-a", "project-a", "task-a", "run-k8s")
        spec = SandboxSpec(
            identity,
            IsolationClass.L3,
            "sha256:" + "e" * 64,
            "cn-east",
            mounts=(MountSpec("/approved/source", "/workspace/source"),),
        )
        reference = backend.create("sandbox-k8s", spec)
        self.assertEqual(reference, "sandbox-k8s")
        labels = client.pod["metadata"]["labels"]
        selector = client.network_policy["spec"]["podSelector"]["matchLabels"]
        self.assertEqual(labels["sandbox-id"], "sandbox-k8s")
        self.assertEqual(selector["sandbox-id"], "sandbox-k8s")
        self.assertNotIn("hostPath", client.pod["spec"]["volumes"][0])
        backend.exec(reference, SandboxExecRequest(("true",), "exec-k8s"), {"lease-a": "secret-a"})
        self.assertEqual(client.exec_request["env"], {})
        self.assertEqual(client.exec_request["secret_values"], {"lease-a": "secret-a"})
        snapshot = "sha256:" + "f" * 64
        self.assertEqual(backend.restore("sandbox-restored", snapshot, spec), "sandbox-restored")

    def test_sandbox_reaper_destroys_expired_lease(self):
        backend = FakeSandboxBackend()
        provider = ProductionSandboxProvider(backend, lease_seconds=5)
        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        handle = provider.create(SandboxSpec(identity, IsolationClass.L4, "sha256:" + "c" * 64, "local"), idempotency_key="create", now=10)
        self.assertEqual(provider.reap_expired(now=16), (handle.sandbox_id,))
        self.assertTrue(backend.destroyed)
        provider.close()

    def test_local_workspace_api_compare_swap_patch_and_range(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source-repo"
            source.mkdir()
            (source / "initial.txt").write_text("initial")
            artifacts = ContentAddressedStore(root / "cas")
            provider = LocalWorkspaceProvider(root / "workspaces", artifacts)
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            lease = provider.activate(provider.allocate(WorkspaceRequest(identity, source_path=str(source))))
            mutations = WorkspaceMutationStore()
            api = LocalWorkspaceApi(provider, lease, artifacts, mutations)
            content = artifacts.put("tenant-a", b"hello world")
            written = api.write_file(identity, "source/new.txt", content, idempotency_key="write-a")
            self.assertTrue(written.changed)
            self.assertEqual(artifacts.get("tenant-a", api.read_file(identity, "source/new.txt", FileRange(6, 5))), b"world")
            replacement = artifacts.put("tenant-a", b"updated")
            patch = PatchSet((PatchOperation("replace", "source/new.txt", replacement, written.digest),), "patch-a")
            result = api.apply_patch(identity, patch)
            self.assertEqual(result.changed_paths, ("source/new.txt",))
            with self.assertRaises(ContractViolation):
                api.write_file(identity, "source/new.txt", content, idempotency_key="write-b", expected_digest="sha256:" + "0" * 64)
            with self.assertRaises(ContractViolation):
                api.read_file(identity, "../outside")
            with self.assertRaises(ContractViolation):
                GitOperation("push", ("https://attacker.invalid/repo", "main"), "push-a")
            with self.assertRaises(ContractViolation):
                GitOperation("diff", ("--no-index", "/etc/passwd"))
            with self.assertRaises(ContractViolation):
                GitOperation("status", ("--repo=https://attacker.invalid/repo",), "repo-escape")
            forged_identity = Identity("tenant-a", "project-b", "task-a", "run-a")
            forged_lease = lease.__class__(lease.workspace_id, forged_identity, lease.root, lease.state, lease.fencing_token, lease.expires_at, lease.isolation_class, lease.image_digest)
            with self.assertRaises(TenantIsolationError):
                provider.release(forged_lease)
            with self.assertRaises(TenantIsolationError):
                provider.destroy(forged_lease)
            provider.destroy(lease)
            provider.close()
            mutations.close()


if __name__ == "__main__":
    unittest.main()
