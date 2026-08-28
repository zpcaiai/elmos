import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from elmos_openhands.api import AuthenticatedPrincipal, AuthenticatedRuntimeGateway
from elmos_openhands.artifacts import ContentAddressedStore
from elmos_openhands.errors import ContractViolation, TenantIsolationError
from elmos_openhands.firewall import FirewallContext
from elmos_openhands.governance import RetentionController, RetentionPolicy
from elmos_openhands.ledger import EventLedger
from elmos_openhands.models import Identity, Usage
from elmos_openhands.plane import ResumableEventStream
from elmos_openhands.providers import RouteConstraints
from elmos_openhands.sandbox import DockerSandboxBackend, NetworkPolicy, SandboxSpec, SshEnterpriseSandboxBackend
from elmos_openhands.workspace import IsolationClass, LocalWorkspaceProvider, WorkspaceRequest
from elmos_openhands.workspace_api import LocalWorkspaceApi, PatchOperation, PatchSet, WorkspaceMutationStore


class FakeControlPlane:
    def __init__(self):
        self.created = []
        self.turn_request = None
        self.cancelled = []

    def create_run(self, identity, manifest):
        self.created.append((identity, manifest))

    def turn(self, request):
        self.turn_request = request
        return SimpleNamespace(status="ready", event_seq=3, checkpoint_id=None, reason=None, usage=Usage(input_tokens=1), observation=None, completion=None)

    def resume(self, identity, manifest):
        return {"run": SimpleNamespace(status="ready", manifest_hash=manifest.digest), "checkpoint": None, "projection": {}}

    def cancel(self, identity, reason):
        self.cancelled.append((identity, reason))


class FakeDockerIo:
    def snapshot_container(self, **kwargs):
        return {"digest": "sha256:" + "a" * 64}

    def restore_container(self, **kwargs):
        return {"container_id": "restored-a", "snapshot_digest": kwargs["snapshot_digest"]}


class FakeEnterpriseClient:
    def host_attestation(self, **kwargs):
        return {"host_fingerprint": "sha256:" + "f" * 64, "dedicated": True}

    def create_workspace(self, **kwargs):
        return {
            "workspace_id": "enterprise-a",
            "dedicated": True,
            "tenant_id": kwargs["tenant_id"],
            "project_id": kwargs["project_id"],
            "task_id": kwargs["task_id"],
            "run_id": kwargs["run_id"],
            "node_id": kwargs["node_id"],
            "agent_id": kwargs["agent_id"],
            "image_digest": kwargs["image_digest"],
        }

    def exec_workspace(self, **kwargs):
        return {"exit_code": 0, "stdout": b"ok", "stderr": b""}

    def snapshot_workspace(self, **kwargs):
        return {"digest": "sha256:" + "b" * 64}

    def restore_workspace(self, **kwargs):
        return {
            "workspace_id": "enterprise-b",
            "snapshot_digest": kwargs["snapshot_digest"],
            "dedicated": True,
            "tenant_id": kwargs["tenant_id"],
            "project_id": kwargs["project_id"],
            "task_id": kwargs["task_id"],
            "run_id": kwargs["run_id"],
            "node_id": kwargs["node_id"],
            "agent_id": kwargs["agent_id"],
        }

    def workspace_stats(self, **kwargs):
        return {"cpu_seconds": 1, "memory_bytes": 2, "disk_bytes": 3, "pids": 1}

    def destroy_workspace(self, **kwargs):
        return {"state": "destroyed"}


class RejectingMutationStore(WorkspaceMutationStore):
    def put(self, tenant_id, workspace_id, key, request_digest, result):
        raise RuntimeError("durable journal unavailable")


class GovernanceApiBackendTests(unittest.TestCase):
    def test_retention_export_hold_idempotent_delete_and_unknown_reconciliation(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = ContentAddressedStore(Path(temporary) / "cas")
            controller = RetentionController()
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            controller.put_policy(RetentionPolicy("policy-a", "tenant-a", 1, "browser", 0))
            first = controller.register(identity, artifacts.put("tenant-a", b"evidence-a"), record_class="browser", policy_id="policy-a", created_at_epoch=1)
            controller.place_legal_hold("tenant-a", first.object_id, actor="legal-a", reason="case open")
            self.assertEqual(controller.due("tenant-a", now=10), ())
            controller.release_legal_hold("tenant-a", first.object_id, actor="legal-a", approver="legal-b", reason="case closed")
            export = controller.export_tenant(identity, artifacts, facts=({"event": "run.completed"},), authorization_ref="export-approval")
            self.assertEqual(export.tenant_id, "tenant-a")
            receipt = controller.execute(
                "tenant-a", first.object_id, actor="retention-worker", independent_verifier_id="verifier-a",
                approval_ref="delete-approval", deleter=lambda value, policy, key: {"status": "DELETED", "receipt": key + ":provider"},
                verifier=lambda value, policy, outcome: outcome["receipt"].endswith(":provider"), now=10,
            )
            self.assertEqual(receipt.status, "DELETED")
            replay = controller.execute(
                "tenant-a", first.object_id, actor="retention-worker", independent_verifier_id="verifier-a",
                approval_ref="delete-approval", deleter=lambda value, policy, key: self.fail("idempotent deletion replay called provider"),
                verifier=lambda value, policy, outcome: True, now=10,
            )
            self.assertEqual(replay.action_id, receipt.action_id)
            with self.assertRaises(TenantIsolationError):
                controller.get("tenant-b", first.object_id)

            second = controller.register(identity, artifacts.put("tenant-a", b"evidence-b"), record_class="browser", policy_id="policy-a", created_at_epoch=1)
            controller.export_tenant(identity, artifacts, facts=(), authorization_ref="export-approval-2")
            with self.assertRaises(ContractViolation):
                controller.execute(
                    "tenant-a", second.object_id, actor="retention-worker", independent_verifier_id="verifier-a",
                    approval_ref="delete-approval-2", deleter=lambda value, policy, key: {"status": "UNKNOWN"},
                    verifier=lambda value, policy, outcome: False, now=10,
                )
            reconciled = controller.reconcile(
                "tenant-a", second.object_id, actor="reconciler", independent_verifier_id="verifier-b",
                approval_ref="delete-approval-2", provider_receipt="provider-confirmed", verifier=lambda value, policy, outcome: True,
            )
            self.assertEqual(reconciled.status, "DELETED")

            third = controller.register(identity, artifacts.put("tenant-a", b"evidence-c"), record_class="browser", policy_id="policy-a", created_at_epoch=1)
            controller.export_tenant(identity, artifacts, facts=(), authorization_ref="export-approval-3")
            with self.assertRaises(ContractViolation):
                controller.execute(
                    "tenant-a", third.object_id, actor="retention-worker", independent_verifier_id="verifier-a",
                    approval_ref="delete-approval-3", deleter=lambda value, policy, key: {"status": "DELETED", "receipt": "provider-receipt"},
                    verifier=lambda value, policy, outcome: (_ for _ in ()).throw(RuntimeError("verifier unavailable")), now=10,
                )
            self.assertEqual(controller.get("tenant-a", third.object_id).state, "deletion_unverified")
            controller.close()

    def test_authenticated_gateway_derives_scope_enforces_roles_and_uses_trusted_resolvers(self):
        ledger = EventLedger()
        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        ledger.create_run(identity, "sha256:" + "a" * 64)
        ledger.append(identity, "run.status", {"status": "ready"})
        control = FakeControlPlane()
        gateway = AuthenticatedRuntimeGateway(
            control,
            ResumableEventStream(ledger, b"k" * 32),
            firewall_context_resolver=lambda value: FirewallContext(value, frozenset({"workspace.read"})),
            route_constraints_resolver=lambda value, manifest: RouteConstraints(allowed_providers=frozenset({manifest.provider})),
        )
        principal = AuthenticatedPrincipal("user-a", "tenant-a", frozenset({"project-a"}), frozenset({"runtime.create", "runtime.turn", "runtime.read", "runtime.cancel"}), "mfa")
        payload = {
            "tenant_id": "tenant-a", "project_id": "project-a", "task_id": "task-a", "run_id": "run-a",
            "manifest": {"repo_revision": "commit-a", "policy_version": "policy-a", "provider": "native", "model": "model-a"},
        }
        gateway.create_run(principal, payload)
        result = gateway.turn(principal, payload)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(control.turn_request.identity.agent_id, "user-a")
        self.assertEqual(control.turn_request.firewall_context.identity.tenant_id, "tenant-a")
        self.assertEqual(control.turn_request.route_constraints.allowed_providers, frozenset({"native"}))
        self.assertEqual(len(gateway.event_page(principal, payload)["events"]), 1)
        with self.assertRaises(TenantIsolationError):
            gateway.event_page(AuthenticatedPrincipal("reader", "tenant-a", frozenset({"project-a"}), frozenset(), "mfa"), payload)
        with self.assertRaises(TenantIsolationError):
            gateway.create_run(principal, {**payload, "tenant_id": "tenant-b"})
        with self.assertRaises(ContractViolation):
            gateway.create_run(principal, {key: value for key, value in payload.items() if key != "manifest"})
        project_b = AuthenticatedPrincipal("reader-b", "tenant-a", frozenset({"project-b"}), frozenset({"runtime.read"}), "mfa")
        with self.assertRaises(TenantIsolationError):
            gateway.event_page(project_b, {**payload, "project_id": "project-b"})
        ledger.close()

    def test_sandbox_backends_do_not_overstate_isolation_or_snapshot_restore(self):
        docker = DockerSandboxBackend(runner=lambda command, timeout: SimpleNamespace(returncode=0, stdout="container-a", stderr=""), io_client=FakeDockerIo())
        self.assertEqual(docker.supported_isolation, frozenset({IsolationClass.L1}))
        self.assertEqual(docker.snapshot("container-a"), "sha256:" + "a" * 64)
        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        spec = SandboxSpec(identity, IsolationClass.L1, "sha256:" + "c" * 64, "local")
        self.assertEqual(docker.restore("sandbox-a", "sha256:" + "a" * 64, spec), "restored-a")
        with self.assertRaises(ContractViolation):
            NetworkPolicy("invalid", allowed_egress=("example.com",), audit_sink_ref="audit-a")
        with self.assertRaises(ContractViolation):
            NetworkPolicy("invalid", allowed_egress=("10.0.0.1/32",))

        enterprise = SshEnterpriseSandboxBackend(
            FakeEnterpriseClient(), host_id="host-a", host_fingerprint="sha256:" + "f" * 64,
            attestation_verifier=lambda attestation, fingerprint, value: attestation["host_fingerprint"] == fingerprint and value.identity.tenant_id == "tenant-a",
        )
        enterprise_spec = SandboxSpec(identity, IsolationClass.L4, "sha256:" + "d" * 64, "private")
        reference = enterprise.create("sandbox-enterprise", enterprise_spec)
        self.assertEqual(reference, "enterprise-a")
        self.assertEqual(enterprise.restore("sandbox-restored", enterprise.snapshot(reference), enterprise_spec), "enterprise-b")
        enterprise.destroy(reference)

    def test_local_patch_rolls_back_when_durable_receipt_fails_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "a.txt").write_text("before")
            artifacts = ContentAddressedStore(root / "cas")
            provider = LocalWorkspaceProvider(root / "workspaces", artifacts)
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            lease = provider.activate(provider.allocate(WorkspaceRequest(identity, source_path=str(source))))
            mutations = RejectingMutationStore()
            api = LocalWorkspaceApi(provider, lease, artifacts, mutations)
            replacement = artifacts.put("tenant-a", b"after")
            with self.assertRaises(RuntimeError):
                api.apply_patch(identity, PatchSet((PatchOperation("replace", "source/a.txt", replacement),), "patch-a"))
            self.assertEqual((Path(lease.root) / "source" / "a.txt").read_text(), "before")
            (Path(lease.root) / "source" / "link").symlink_to(Path(lease.root) / "source" / "a.txt")
            with self.assertRaises(TenantIsolationError):
                api.read_file(identity, "source/link")
            mutations.close()
            provider.destroy(lease)
            provider.close()


if __name__ == "__main__":
    unittest.main()
