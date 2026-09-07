import time
import unittest

from elmos_openhands.context import (
    ContextBenchmark,
    ContextCandidate,
    ContextRolePolicy,
    EvidenceAwareContextEngine,
    PersistentContextStore,
)
from elmos_openhands.errors import BudgetExceeded, ContractViolation, LeaseLost, TenantIsolationError
from elmos_openhands.firewall import ActionFirewall, FirewallContext
from elmos_openhands.gates import (
    BoundedRepairLoop,
    GateExecution,
    GateProfile,
    ProfiledCompletionGateEngine,
    WaiverStore,
)
from elmos_openhands.models import Action, CompletionProposal, Identity, RiskLevel
from elmos_openhands.plane import (
    DurableAdmissionController,
    DurableWorkerRegistry,
    TenantQuota,
    WorkerCapacity,
)
from elmos_openhands.policy import (
    ApprovalWorkflow,
    CompiledPolicyEngine,
    DurableKillSwitch,
    GovernedActionFirewall,
    PolicyCompiler,
    SecretTaintTracker,
)


class PlaneContextPolicyGateTests(unittest.TestCase):
    def setUp(self):
        self.identity = Identity("tenant-a", "project-a", "task-a", "run-a")

    def test_durable_worker_residency_capacity_fencing_and_recovery(self):
        registry = DurableWorkerRegistry(lease_seconds=10)
        worker = registry.register("worker-a", region="cn-east", residency=("CN",), capabilities=("python", "browser"), capacity=WorkerCapacity(1, 4, 8192), deployment_version="v1", now=10)
        assignment, selected = registry.place(self.identity, region="cn-east", residency="CN", required_capabilities=("python",), now=11)
        self.assertEqual(selected.worker_id, "worker-a")
        other = Identity("tenant-a", "project-a", "task-b", "run-b")
        with self.assertRaises(LeaseLost):
            registry.place(other, region="cn-east", residency="CN", required_capabilities=("python",), now=11)
        registry.release(self.identity, assignment)
        self.assertEqual(registry.assignments("worker-a"), 0)
        self.assertEqual(registry.recover_stale(now=21), ("worker-a",))
        with self.assertRaises(LeaseLost):
            registry.heartbeat(worker, now=21)
        registry.close()

    def test_multidimensional_admission_and_backpressure(self):
        controller = DurableAdmissionController()
        controller.set_quota("tenant-a", TenantQuota(1, 10, 1.0, 100, 100, queue_depth=1))
        active = controller.admit(self.identity, window="2026-08")
        queued = controller.admit(Identity("tenant-a", "project-a", "task-b", "run-b"), window="2026-08")
        self.assertEqual((active.state, queued.state), ("active", "queued"))
        forged = active.__class__(active.admission_id, Identity("tenant-a", "project-b", "task-a", "run-a"), active.window, active.state)
        with self.assertRaises(TenantIsolationError):
            controller.consume(forged, tokens=1)
        with self.assertRaises(BudgetExceeded):
            controller.consume(active, tokens=11)
        controller.consume(active, tokens=5, cost_micros=10)
        controller.release(active)
        self.assertEqual(controller.promote(queued).state, "active")
        controller.set_backpressure("event_bus", True)
        with self.assertRaises(ContractViolation):
            controller.admit(Identity("tenant-a", "project-a", "task-c", "run-c"), window="next")
        controller.release(queued)
        controller.close()

    def test_evidence_context_policy_conflict_security_and_benchmark(self):
        store = PersistentContextStore()
        policy = ContextRolePolicy("implementer", frozenset({"repo_graph", "tests", "requirements"}), frozenset({"dependency", "failed_test", "requirement"}), "confidential", source_weights={"tests": 2.0})
        engine = EvidenceAwareContextEngine((policy,), store)
        candidates = (
            ContextCandidate("dep-old", "tenant-a", "repo_graph", "uses old-api", 0.8, 0.4, conflict_key="dep", fact_type="dependency", observed_at_epoch=10),
            ContextCandidate("dep-new", "tenant-a", "repo_graph", "uses new-api", 0.9, 1.0, conflict_key="dep", fact_type="dependency", observed_at_epoch=20),
            ContextCandidate("failed", "tenant-a", "tests", "failed test_checkout", 0.3, 1.0, fact_type="failed_test"),
            ContextCandidate("requirement", "tenant-a", "requirements", "must preserve tenant isolation", 0.5, 1.0, fact_type="requirement"),
            ContextCandidate("restricted", "tenant-a", "tests", "restricted secret", 1.0, 1.0, "restricted", fact_type="failed_test"),
        )
        view = engine.build(self.identity, role="implementer", model="model-a", candidates=candidates, query="new api checkout", max_tokens=200, now=30)
        self.assertIn("dep-new", {item.candidate_id for item in view.candidates})
        self.assertNotIn("dep-old", {item.candidate_id for item in view.candidates})
        self.assertIn("restricted", view.dropped_candidates)
        benchmark = ContextBenchmark().evaluate(view, expected_dependencies=("dep-new",), expected_failed_tests=("failed",), stale_ids=("dep-old",))
        self.assertEqual(benchmark.status, "PASS")
        store.close()

    def test_context_unresolved_mandatory_conflict_fails_closed(self):
        store = PersistentContextStore()
        policy = ContextRolePolicy("reviewer", frozenset({"requirements"}), frozenset({"requirement"}), "internal")
        engine = EvidenceAwareContextEngine((policy,), store)
        candidates = (
            ContextCandidate("r1", "tenant-a", "requirements", "must use A", 1, 1, must_retain=True, conflict_key="choice", fact_type="requirement", observed_at_epoch=10),
            ContextCandidate("r2", "tenant-a", "requirements", "must use B", 1, 1, must_retain=True, conflict_key="choice", fact_type="requirement", observed_at_epoch=10),
        )
        with self.assertRaises(ContractViolation):
            engine.build(self.identity, role="reviewer", model="m", candidates=candidates, query="choice", max_tokens=100)
        store.close()

    def test_governed_firewall_taint_two_person_approval_and_kill_switch(self):
        approvals = ApprovalWorkflow()
        taints = SecretTaintTracker()
        switches = DurableKillSwitch()
        self.addCleanup(switches.close)
        rules = PolicyCompiler().compile({"version": "1", "rules": [{"id": "push-approval", "priority": 1, "effect": "require_approval", "tools": ["git"], "operations": ["push"], "reason": "external mutation"}]})
        firewall = GovernedActionFirewall(ActionFirewall(), CompiledPolicyEngine(rules), approvals, taints, switches)
        context = FirewallContext(self.identity, frozenset({"git.push"}), require_approval_at=RiskLevel.R4)
        action = Action("push-a", "git", {"operation": "push"}, {}, "push-idem", required_capabilities=("git.push",), risk_hint=RiskLevel.R4)
        self.assertEqual(firewall.decide(action, context).decision.decision, "require_approval")
        request = approvals.request(self.identity, action, RiskLevel.R4, requester="requester", reason="release")
        approvals.decide(self.identity, request.approval_id, actor="reviewer", decision="approve", reason="scoped")
        self.assertEqual(firewall.decide(action, context, approved_by=request.approval_id).decision.decision, "allow")
        with self.assertRaises(TenantIsolationError):
            approvals.get(Identity("tenant-a", "project-b", "task-a", "run-a"), request.approval_id)

        r6 = Action("prod-a", "cloud", {"operation": "mutate"}, {}, "prod-idem", risk_hint=RiskLevel.R6)
        window = (time.time() - 5, time.time() + 60)
        request6 = approvals.request(self.identity, r6, RiskLevel.R6, requester="requester", reason="change", change_window=window)
        approvals.decide(self.identity, request6.approval_id, actor="reviewer-a", decision="approve", reason="one")
        with self.assertRaises(ContractViolation):
            approvals.validate(self.identity, request6.approval_id, r6, RiskLevel.R6)
        approvals.decide(self.identity, request6.approval_id, actor="reviewer-b", decision="approve", reason="two")
        self.assertEqual(len(approvals.validate(self.identity, request6.approval_id, r6, RiskLevel.R6)), 2)

        taints.register(self.identity, "provider-token", "top-secret")
        leaked = Action("leak-a", "filesystem", {"operation": "write", "content": "dG9wLXNlY3JldA=="}, {}, "leak-idem")
        self.assertEqual(firewall.decide(leaked, context).decision.decision, "deny")
        self.assertEqual(taints.detect(Identity("tenant-a", "project-b", "task-a", "run-a"), leaked.args), ())
        switches.set("tenant", "tenant-a", active=True, actor="security", reason="incident")
        self.assertIn("KILL_SWITCH_ACTIVE", firewall.decide(action, context).decision.reasons[0])
        approvals.close()

    def test_profiled_gates_waivers_repairs_and_zero_tolerance(self):
        profile = GateProfile("task", ("unit_tests", "security_scan"), zero_tolerance=frozenset({"security_scan"}), max_repairs=1)
        waivers = WaiverStore()
        waivers.create(self.identity, "unit_tests", actor="owner", reason="known noncritical", expires_at=time.time() + 60, zero_tolerance=profile.zero_tolerance)
        forged = Identity("tenant-a", "project-b", "task-a", "run-a")
        self.assertIsNone(waivers.valid(forged, "unit_tests"))
        with self.assertRaises(ContractViolation):
            waivers.create(self.identity, "security_scan", actor="owner", reason="cannot", expires_at=time.time() + 60, zero_tolerance=profile.zero_tolerance)
        engine = ProfiledCompletionGateEngine(profile, waivers=waivers, evidence_verifier=lambda ref: ref.startswith("sha256:"))
        proposal = CompletionProposal("run-a", "done")
        executions = {"unit_tests": GateExecution("unit_tests", "fail", (), reason="known"), "security_scan": GateExecution("security_scan", "pass", ("sha256:" + "a" * 64,))}
        decision = engine.evaluate(self.identity, proposal, executions, change_flags=())
        self.assertEqual(decision.status, "pass")
        repaired = BoundedRepairLoop(profile).run({"unit_tests": GateExecution("unit_tests", "fail", ())}, lambda attempt, failed: {"unit_tests": GateExecution("unit_tests", "pass", ("sha256:" + "b" * 64,))})
        self.assertEqual(repaired.status, "pass")
        waivers.close()


if __name__ == "__main__":
    unittest.main()
