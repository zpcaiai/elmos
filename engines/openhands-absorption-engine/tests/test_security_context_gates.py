import unittest

from elmos_openhands.context import ContextCandidate, ContextEngine
from elmos_openhands.errors import ContractViolation, TenantIsolationError
from elmos_openhands.firewall import ActionFirewall, FirewallContext
from elmos_openhands.gates import CompletionGateEngine, HookRegistry, TraceabilityGraph
from elmos_openhands.models import Action, CompletionProposal, Identity, RiskLevel


class SecurityContextGateTests(unittest.TestCase):
    def setUp(self):
        self.identity = Identity("tenant-a", "project-a", "task-a", "run-a")

    def test_firewall_denies_traversal_secret_and_destructive_command(self):
        firewall = ActionFirewall()
        context = FirewallContext(self.identity, frozenset({"shell.exec"}), ("/tmp/workspace",), secret_values=("secret-value",))
        traversal = Action("a1", "shell", {"operation": "shell", "command": ["cat", "../../secret-value"]}, {}, "i1", read_scope=("/tmp/workspace/../../secret",), required_capabilities=("shell.exec",))
        self.assertEqual(firewall.decide(traversal, context).decision.decision, "deny")
        destructive = Action("a2", "shell", {"operation": "shell", "command": "rm -rf /"}, {}, "i2", required_capabilities=("shell.exec",))
        self.assertEqual(firewall.decide(destructive, context).decision.decision, "deny")
        injected = Action("a3", "shell", {"operation": "shell", "command": ["echo", "secret-value"]}, {}, "i3", required_capabilities=("shell.exec",))
        self.assertEqual(firewall.decide(injected, context).decision.decision, "deny")
        unscoped_path = Action("a4", "filesystem", {"operation": "read", "path": "/etc/passwd"}, {}, "i4")
        self.assertEqual(firewall.decide(unscoped_path, FirewallContext(self.identity)).decision.decision, "deny")

    def test_high_risk_requires_scoped_approval(self):
        firewall = ActionFirewall()
        context = FirewallContext(self.identity, frozenset({"git.push"}), ("/tmp/workspace",))
        action = Action("a1", "git", {"operation": "push"}, {}, "i1", risk_hint=RiskLevel.R4, required_capabilities=("git.push",))
        self.assertEqual(firewall.decide(action, context).decision.decision, "require_approval")
        self.assertEqual(firewall.decide(action, context, approved_by="reviewer-1").decision.decision, "allow")

    def test_context_retains_mandatory_facts_and_is_tenant_scoped(self):
        engine = ContextEngine()
        candidates = [
            ContextCandidate("failure", "tenant-a", "test", "failed test must remain visible", relevance=0.5),
            ContextCandidate("nice", "tenant-a", "docs", "optional background", relevance=0.9),
        ]
        view = engine.build(self.identity, "debugger", candidates, max_tokens=9)
        self.assertEqual(view.candidates[0].candidate_id, "failure")
        self.assertIn("nice", view.dropped_candidates)
        with self.assertRaises(TenantIsolationError):
            engine.build(self.identity, "debugger", [ContextCandidate("other", "tenant-b", "docs", "x")], max_tokens=20)
        with self.assertRaises(ContractViolation):
            engine.build(self.identity, "debugger", [candidates[0]], max_tokens=1)

    def test_completion_gate_cannot_be_bypassed_by_agent_text(self):
        hooks = HookRegistry()
        order = []
        hooks.register("pre_completion", "first", lambda *_: order.append("first"), order=2)
        hooks.register("pre_completion", "zero", lambda *_: order.append("zero"), order=1)
        gates = CompletionGateEngine(required=("build_or_compile", "unit_tests"), hooks=hooks, evidence_verifier=lambda reference: reference.startswith(("artifact-", "traceability:")))
        proposal = CompletionProposal(self.identity.run_id, "done", provider_text="all tests passed")
        blocked = gates.evaluate(self.identity, proposal, {"build_or_compile": "fail", "unit_tests": "pass"}, {"build_or_compile": ["sha256:x"]})
        self.assertEqual(blocked.status, "blocked")
        self.assertFalse(blocked.evidence_complete)
        self.assertEqual(order, ["zero", "first"])
        trace = TraceabilityGraph()
        trace.link("REQ-1", "change-1", "evidence-1")
        passed = gates.evaluate(self.identity, CompletionProposal(self.identity.run_id, "done", requirement_refs=("REQ-1",)), {"build_or_compile": "pass", "unit_tests": "pass"}, {"build_or_compile": ["artifact-1"], "unit_tests": ["artifact-2"]}, trace=trace)
        self.assertEqual(passed.status, "pass")

        unverified = CompletionGateEngine(required=("build_or_compile",), evidence_verifier=None).evaluate(self.identity, proposal, {"build_or_compile": "pass"}, {"build_or_compile": ["artifact-1"]})
        self.assertEqual(unverified.status, "blocked")


if __name__ == "__main__":
    unittest.main()
