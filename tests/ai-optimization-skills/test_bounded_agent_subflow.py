from __future__ import annotations

import unittest

from elmos_ai_optimization.agent_subflow import BoundedAgentSubflow
from elmos_ai_optimization.contracts import ActionFenceError, ActionIntent, Receipt
from elmos_ai_optimization.execution import ExecutionGatewayBridge
from elmos_ai_optimization.scope import HostAuthority, ScopeResolver


class BoundedAgentSubflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = HostAuthority()
        self.authority.register_grant("t1", "r1", ["lead"], generation="gen-1")
        self.authority.create_session("t1", "lead", "tok-lead")
        self.resolver = ScopeResolver(self.authority)
        self.scope = self.resolver.resolve("t1", "lead", "tok-lead", [("r1", "snap-1")])

        self.subflow = BoundedAgentSubflow(max_steps=3, max_rounds=2)
        self.gateway = ExecutionGatewayBridge(self.authority)

    def test_subflow_lifecycle_and_no_progress_termination(self) -> None:
        cp0 = self.subflow.init_subflow("run-1", "graph-v1", ["ev-1"])
        self.assertEqual(cp0.state, "INIT")
        self.assertEqual(cp0.step_index, 0)

        # Advance with new evidence
        cp1 = self.subflow.advance(self.scope, "run-1", new_evidence_refs=["ev-2"])
        self.assertEqual(cp1.state, "EVIDENCE_PACKED")
        self.assertEqual(cp1.step_index, 1)

        # Advance with no new evidence or intent => no progress detected
        cp2 = self.subflow.advance(self.scope, "run-1")
        self.assertEqual(cp2.state, "FAILED")

    def test_max_steps_exceeded_blocks(self) -> None:
        self.subflow.init_subflow("run-2", "graph-v1", ["ev-1"])
        self.subflow.advance(self.scope, "run-2", ["ev-2"])
        self.subflow.advance(self.scope, "run-2", ["ev-3"])
        self.subflow.advance(self.scope, "run-2", ["ev-4"])
        # Next step exceeds max_steps=3
        blocked_cp = self.subflow.advance(self.scope, "run-2", ["ev-5"])
        self.assertEqual(blocked_cp.state, "BLOCKED")

    def test_action_intent_proposal_and_generation_fence(self) -> None:
        intent = ActionIntent(
            run_ref="run-3",
            logical_step="repair-fix",
            base_revision="snap-1",
            intent_digest="f" * 64,
            artifact_ref="art-1",
            budget_ref="bud-1",
            verification_plan_ref="plan-1",
        )
        action_id = self.gateway.propose(self.scope, "r1", "repair-fix", intent)
        self.assertTrue(action_id.startswith("act-"))

        # Dispatch with current generation succeeds
        receipt = self.gateway.dispatch(self.scope, action_id, "r1", "SUCCEEDED")
        self.assertEqual(receipt.state, "SUCCEEDED")

        # Propose second action
        action_id2 = self.gateway.propose(self.scope, "r1", "repair-step-2", intent)
        # Simulate repository generation bump
        self.authority.register_grant("t1", "r1", ["lead"], generation="gen-2")
        # Dispatch fails with ActionFenceError
        with self.assertRaises(ActionFenceError):
            self.gateway.dispatch(self.scope, action_id2, "r1", "SUCCEEDED")

    def test_unknown_result_reconciliation(self) -> None:
        intent = ActionIntent(
            run_ref="run-4",
            logical_step="repair-patch",
            base_revision="snap-1",
            intent_digest="e" * 64,
            artifact_ref="art-2",
            budget_ref="bud-2",
            verification_plan_ref="plan-2",
        )
        aid = self.gateway.propose(self.scope, "r1", "repair-patch", intent)
        rcpt = self.gateway.dispatch(self.scope, aid, "r1", "UNKNOWN_RESULT")
        self.assertEqual(rcpt.state, "UNKNOWN_RESULT")

        # Safe reconciliation resolves to terminal state
        reconciled = self.gateway.reconcile(aid, "SUCCEEDED")
        self.assertEqual(reconciled.state, "SUCCEEDED")


if __name__ == "__main__":
    unittest.main()
