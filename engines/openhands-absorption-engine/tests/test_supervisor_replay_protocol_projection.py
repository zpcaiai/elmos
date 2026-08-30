import tempfile
import unittest
from pathlib import Path

from elmos_openhands.artifacts import ContentAddressedStore
from elmos_openhands.errors import ContractViolation, TenantIsolationError
from elmos_openhands.firewall import ActionFirewall, FirewallContext
from elmos_openhands.ledger import EventLedger
from elmos_openhands.models import Action, ActionStatus, ExecutionManifest, Identity
from elmos_openhands.projections import ProjectionEngine, ProjectionStore
from elmos_openhands.protocol import ConformanceCase, ProtocolNegotiator, ToolConformanceHarness
from elmos_openhands.replay import ResumeCoordinator
from elmos_openhands.supervisor import RunStateReconciler, RuntimeSupervisor, SupervisorStore
from elmos_openhands.tools import ToolGateway, ToolRegistry, ToolResult, ToolSpec


class ReconcileExecutor:
    name = "mutator"

    def __init__(self):
        self.executions = 0

    def execute(self, action, *, timeout_seconds):
        self.executions += 1
        return ToolResult(ActionStatus.SUCCESS, {"executed": True})

    def reconcile(self, action):
        return ToolResult(ActionStatus.SUCCESS, {"reconciled": True})


class SupervisorReplayProtocolProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.ledger = EventLedger(root / "ledger.sqlite")
        self.identity = Identity("tenant-a", "project-a", "task-a", "run-a")
        self.manifest = ExecutionManifest("git:abc", "policy-v1", "native", "model")
        self.ledger.create_run(self.identity, self.manifest.digest, "ready")
        self.artifacts = ContentAddressedStore(root / "cas")

    def tearDown(self):
        self.ledger.close()
        self.temporary.cleanup()

    def test_supervisor_stuck_deadline_and_cancel_are_durable(self):
        store = SupervisorStore()
        supervisor = RuntimeSupervisor(store, self.ledger, stuck_after_seconds=5)
        supervisor.register(self.identity, deadline_epoch=100, now=10)
        supervisor.heartbeat(self.identity, "provider", now=20)
        decisions = supervisor.sweep(now=26)
        self.assertEqual(decisions[0].decision, "stuck")
        self.assertEqual(self.ledger.run("tenant-a", "run-a").status, "blocked")
        self.assertEqual(store.get(self.identity).state, "blocked")
        store.close()

    def test_supervisor_scoped_cancellation(self):
        store = SupervisorStore()
        supervisor = RuntimeSupervisor(store, self.ledger)
        supervisor.register(self.identity, deadline_epoch=100, now=10)
        supervisor.request_cancel(self.identity, "operator-a", "requested")
        decision = supervisor.sweep(now=11)[0]
        self.assertEqual(decision.decision, "cancel")
        self.assertEqual(self.ledger.run("tenant-a", "run-a").status, "cancelled")
        store.close()

    def test_resume_falls_back_from_corrupt_latest_checkpoint(self):
        self.ledger.save_checkpoint(self.identity, event_seq=-1, manifest_hash=self.manifest.digest, state={"runtime": {"phase": "safe"}, "provider": {}})
        latest = self.ledger.save_checkpoint(self.identity, event_seq=0, manifest_hash=self.manifest.digest, state={"runtime": {"phase": "new"}, "provider": {}})
        self.ledger._connection.execute("UPDATE checkpoints SET state_json='not-json' WHERE checkpoint_id=?", (latest,))
        result = ResumeCoordinator(self.ledger).resume(self.identity, self.manifest)
        self.assertEqual(result.checkpoint.runtime_state["phase"], "safe")
        self.assertEqual(result.rejected_checkpoints, (latest,))
        with self.assertRaises(TenantIsolationError):
            ResumeCoordinator(self.ledger).resume(Identity("tenant-a", "project-b", "task-a", "run-a"), self.manifest)

    def test_resume_reconciles_unfinished_mutation_without_reexecuting(self):
        registry = ToolRegistry()
        executor = ReconcileExecutor()
        registry.register(ToolSpec("mutator", "1", frozenset({"write"}), mutating=True, reconcileable=True), executor)
        gateway = ToolGateway(self.ledger, ActionFirewall(), registry, self.artifacts)
        action = Action("action-a", "mutator", {}, {}, "idem-a", required_capabilities=("write",))
        self.ledger.append(self.identity, "action.proposed", action.as_dict(), idempotency_key="action:idem-a")
        context = FirewallContext(self.identity, frozenset({"write"}))
        result = ResumeCoordinator(self.ledger, gateway=gateway).resume(self.identity, self.manifest, firewall_context=context)
        self.assertEqual(result.reconciled_actions, ("action-a",))
        self.assertEqual(executor.executions, 0)

    def test_protocol_negotiation_and_cancellation_conformance(self):
        negotiated = ProtocolNegotiator(features=("cancellation", "reconciliation")).negotiate({"action_versions": ["1.0"], "observation_versions": ["1.0"], "provider_versions": ["1.0"], "features": ["cancellation"]})
        self.assertEqual(negotiated.features, frozenset({"cancellation"}))
        with self.assertRaises(ContractViolation):
            ProtocolNegotiator().negotiate({"action_versions": ["2.0"], "observation_versions": ["2.0"], "provider_versions": ["2.0"]})

        registry = ToolRegistry()
        executor = ReconcileExecutor()
        registry.register(ToolSpec("mutator", "1", frozenset({"write"}), mutating=True, reconcileable=True), executor)
        gateway = ToolGateway(self.ledger, ActionFirewall(), registry, self.artifacts)
        case = ConformanceCase("cancel-1", "cancellation", Action("cancel-action", "mutator", {}, {}, "cancel-idem", required_capabilities=("write",)), ActionStatus.CANCELLED)
        report = ToolConformanceHarness(registry, gateway).run(self.identity, "mutator", (case,), FirewallContext(self.identity, frozenset({"write"})))
        self.assertEqual(report.status, "pass")

    def test_projection_consumer_handles_duplicate_and_out_of_order_delivery(self):
        one = self.ledger.append(self.identity, "run.status", {"status": "running"}, idempotency_key="s1")
        two = self.ledger.append(self.identity, "context.built", {"fingerprint": "f1"}, idempotency_key="c1")
        store = ProjectionStore()
        engine = ProjectionEngine(self.ledger, store)
        engine.consume(two)
        snapshots = engine.consume(one)
        self.assertEqual(snapshots["runtime"].event_seq, 1)
        duplicate = engine.consume(one)
        self.assertEqual(duplicate["timeline"].event_seq, 1)
        self.assertTrue(all(engine.compare_rebuild(self.identity).values()))
        store.close()

    def test_reconciler_reports_unfinished_action_and_valid_chain(self):
        action = Action("a-unfinished", "mutator", {}, {}, "u1")
        self.ledger.append(self.identity, "action.proposed", action.as_dict(), idempotency_key="action:u1")
        report = RunStateReconciler(self.ledger).reconcile(self.identity)
        self.assertTrue(report.chain_valid)
        self.assertEqual(report.unfinished_actions, ("a-unfinished",))


if __name__ == "__main__":
    unittest.main()
