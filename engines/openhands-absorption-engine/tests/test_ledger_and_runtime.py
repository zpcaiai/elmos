import tempfile
import unittest
from pathlib import Path

from elmos_openhands.artifacts import ContentAddressedStore
from elmos_openhands.errors import IdempotencyConflict, LeaseLost, TenantIsolationError
from elmos_openhands.firewall import ActionFirewall, FirewallContext
from elmos_openhands.ledger import EventLedger
from elmos_openhands.models import Action, Budget, ExecutionManifest, Identity, Usage
from elmos_openhands.providers import NativeAgentAdapter, ProviderResponse
from elmos_openhands.runtime import AgentRuntime, RuntimeTurnInput
from elmos_openhands.tools import LocalWorkspaceToolExecutor, ToolGateway, ToolRegistry, ToolSpec
from elmos_openhands.workspace import LocalWorkspaceProvider, WorkspaceRequest


class LedgerAndRuntimeTests(unittest.TestCase):
    def test_append_is_idempotent_and_hash_chain_is_rebuildable(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = EventLedger(str(Path(root) / "ledger.sqlite"))
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            ledger.create_run(identity, "sha256:" + "a" * 64)
            first = ledger.append(identity, "run.status", {"status": "ready"}, idempotency_key="ready")
            second = ledger.append(identity, "run.status", {"status": "ready"}, idempotency_key="ready")
            self.assertEqual(first.event_id, second.event_id)
            self.assertEqual(first.seq, 0)
            with self.assertRaises(IdempotencyConflict):
                ledger.append(identity, "run.status", {"status": "failed"}, idempotency_key="ready")
            with self.assertRaises(IdempotencyConflict):
                ledger.append(identity, "run.status", {"status": "ready"}, idempotency_key="ready", usage=Usage(input_tokens=1))
            self.assertTrue(ledger.verify_chain(identity.tenant_id, identity.run_id))
            self.assertEqual(ledger.rebuild_projection(identity.tenant_id, identity.run_id)["status"], "ready")
            with self.assertRaises(TenantIsolationError):
                ledger.events("tenant-b", identity.run_id)

    def test_fencing_rejects_stale_worker(self):
        ledger = EventLedger()
        identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        ledger.create_run(identity, "sha256:" + "a" * 64)
        first = ledger.acquire_lease(identity, "worker-a", 30, 10)
        second = ledger.acquire_lease(identity, "worker-a", 30, 41)
        self.assertNotEqual(first.fencing_token, second.fencing_token)
        with self.assertRaises(LeaseLost):
            ledger.assert_lease(first, 41)

    def test_runtime_routes_action_through_firewall_and_records_usage(self):
        with tempfile.TemporaryDirectory() as root:
            artifacts = ContentAddressedStore(Path(root) / "cas")
            ledger = EventLedger(str(Path(root) / "ledger.sqlite"))
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            manifest = ExecutionManifest("commit-a", "policy-v1", "native", "test-model")
            workspaces = LocalWorkspaceProvider(Path(root) / "workspaces", artifacts)
            lease = workspaces.activate(workspaces.allocate(WorkspaceRequest(identity)))
            action = Action("action-a", "workspace", {"operation": "write", "path": "out/result.txt", "content": "done"}, {}, "idem-a", write_scope=(str(Path(lease.root) / "out" / "result.txt"),), required_capabilities=("workspace.write",))
            registry = ToolRegistry()
            registry.register(ToolSpec("workspace", "1.0", frozenset({"workspace.write"}), mutating=True, idempotent=True), LocalWorkspaceToolExecutor(workspaces, lease))
            gateway = ToolGateway(ledger, ActionFirewall(), registry, artifacts)
            provider = NativeAgentAdapter(decisions=[ProviderResponse(action=action, usage=Usage(input_tokens=3, output_tokens=2))])
            runtime = AgentRuntime(ledger, provider, gateway)
            runtime.register(identity, manifest)
            request = RuntimeTurnInput(identity, manifest, Budget(max_input_tokens=10, max_output_tokens=10, max_tool_calls=2), {"turn_id": "turn-a"}, firewall_context=FirewallContext(identity, frozenset({"workspace.write"}), (lease.root,)))
            result = runtime.run_turn(request)
            self.assertEqual(result.status, "ready")
            self.assertEqual(result.observation.status.value, "success")
            self.assertEqual((Path(lease.root) / "out" / "result.txt").read_text(), "done")
            self.assertTrue(ledger.verify_chain(identity.tenant_id, identity.run_id))
            self.assertEqual(len([event for event in ledger.events(identity.tenant_id, identity.run_id) if event.event_type == "tool.observed"]), 1)

    def test_tool_idempotency_key_cannot_change_action_content(self):
        with tempfile.TemporaryDirectory() as root:
            artifacts = ContentAddressedStore(Path(root) / "cas")
            ledger = EventLedger(str(Path(root) / "ledger.sqlite"))
            identity = Identity("tenant-a", "project-a", "task-a", "run-a")
            ledger.create_run(identity, "sha256:" + "a" * 64)
            workspace = LocalWorkspaceProvider(Path(root) / "workspaces", artifacts)
            lease = workspace.activate(workspace.allocate(WorkspaceRequest(identity)))
            registry = ToolRegistry()
            registry.register(ToolSpec("workspace", "1.0", frozenset({"workspace.write"}), mutating=True, idempotent=True), LocalWorkspaceToolExecutor(workspace, lease))
            gateway = ToolGateway(ledger, ActionFirewall(), registry, artifacts)
            context = FirewallContext(identity, frozenset({"workspace.write"}), (lease.root,))
            first = Action("a1", "workspace", {"operation": "write", "path": "out/a.txt", "content": "a"}, {}, "same", write_scope=(str(Path(lease.root) / "out" / "a.txt"),), required_capabilities=("workspace.write",))
            gateway.execute(identity, first, context)
            second = Action("a2", "workspace", {"operation": "write", "path": "out/a.txt", "content": "b"}, {}, "same", write_scope=(str(Path(lease.root) / "out" / "a.txt"),), required_capabilities=("workspace.write",))
            with self.assertRaises(IdempotencyConflict):
                gateway.execute(identity, second, context)


if __name__ == "__main__":
    unittest.main()
