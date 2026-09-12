import unittest
from elmos_ai_optimization.execution import ExecutionGatewayBridge
from elmos_ai_optimization.scope import HostAuthority
from elmos_ai_optimization.contracts import TrustedScope, ActionIntent, ActionFenceError, ContractError, RevisionBinding, Receipt

class TestExecution(unittest.TestCase):
    def setUp(self):
        self.auth = HostAuthority()
        self.gateway = ExecutionGatewayBridge(self.auth)
        self.auth.register_grant("t1", "r1", ["p1"], "gen-1")
        self.scope = TrustedScope("t1", "p1", 1, "sec_ref", (RevisionBinding("r1", "s1", "gen-1"),))
        self.intent = ActionIntent("run1", "step1", "base_rev", "digest", "artifact", "budget", "plan")

    def test_compute_action_id(self):
        action_id = self.gateway.compute_action_id("t1", "r1", "step1", self.intent, "gen-1")
        self.assertTrue(action_id.startswith("act-"))
        self.assertEqual(len(action_id), 4 + 24)

    def test_propose_happy_path(self):
        action_id = self.gateway.propose(self.scope, "r1", "step1", self.intent)
        self.assertIn(action_id, self.gateway._actions)
        self.assertEqual(self.gateway._actions[action_id][1], "PROPOSED")

    def test_propose_permission_denied(self):
        scope_p2 = TrustedScope("t1", "p2", 1, "sec_ref", (RevisionBinding("r1", "s1", "gen-1"),))
        with self.assertRaises(ActionFenceError):
            self.gateway.propose(scope_p2, "r1", "step1", self.intent)
            
        with self.assertRaises(ActionFenceError):
            self.gateway.propose(self.scope, "r_unknown", "step1", self.intent)

    def test_propose_idempotent(self):
        action_id1 = self.gateway.propose(self.scope, "r1", "step1", self.intent)
        action_id2 = self.gateway.propose(self.scope, "r1", "step1", self.intent)
        self.assertEqual(action_id1, action_id2)

    def test_dispatch_happy_path(self):
        action_id = self.gateway.propose(self.scope, "r1", "step1", self.intent)
        receipt = self.gateway.dispatch(self.scope, action_id, "r1", "SUCCEEDED")
        self.assertEqual(receipt.state, "SUCCEEDED")
        self.assertEqual(receipt.action_id, action_id)

    def test_dispatch_unknown_action(self):
        with self.assertRaises(ContractError):
            self.gateway.dispatch(self.scope, "act_unknown", "r1")

    def test_dispatch_idempotent_replay(self):
        action_id = self.gateway.propose(self.scope, "r1", "step1", self.intent)
        receipt1 = self.gateway.dispatch(self.scope, action_id, "r1", "SUCCEEDED")
        receipt2 = self.gateway.dispatch(self.scope, action_id, "r1", "FAILED") # Replay
        self.assertEqual(receipt2.state, "SUCCEEDED") # Original receipt
        self.assertEqual(receipt1, receipt2)

    def test_dispatch_generation_fencing(self):
        action_id = self.gateway.propose(self.scope, "r1", "step1", self.intent)
        # Change generation
        self.auth.register_grant("t1", "r1", ["p1"], "gen-2")
        
        with self.assertRaises(ActionFenceError):
            self.gateway.dispatch(self.scope, action_id, "r1")
            
        # Check action is recorded as FAILED
        _, status, receipt = self.gateway._actions[action_id]
        self.assertEqual(status, "FAILED")
        self.assertEqual(receipt.state, "FAILED")
        self.assertIn("fence-violation", receipt.receipt_ref)

    def test_dispatch_repo_not_found(self):
        action_id = self.gateway.propose(self.scope, "r1", "step1", self.intent)
        self.auth._grants.pop(("t1", "r1")) # simulate repo deletion
        with self.assertRaises(ActionFenceError):
            self.gateway.dispatch(self.scope, action_id, "r1")

    def test_dispatch_invalid_outcome(self):
        action_id = self.gateway.propose(self.scope, "r1", "step1", self.intent)
        with self.assertRaises(ContractError):
            self.gateway.dispatch(self.scope, action_id, "r1", "INVALID")

    def test_reconcile_happy_path(self):
        action_id = self.gateway.propose(self.scope, "r1", "step1", self.intent)
        self.gateway.dispatch(self.scope, action_id, "r1", "UNKNOWN_RESULT")
        
        receipt = self.gateway.reconcile(action_id, "SUCCEEDED")
        self.assertEqual(receipt.state, "SUCCEEDED")

    def test_reconcile_already_resolved(self):
        action_id = self.gateway.propose(self.scope, "r1", "step1", self.intent)
        self.gateway.dispatch(self.scope, action_id, "r1", "SUCCEEDED")
        
        receipt = self.gateway.reconcile(action_id, "FAILED")
        self.assertEqual(receipt.state, "SUCCEEDED") # Keeps original

    def test_reconcile_unknown_action(self):
        with self.assertRaises(ContractError):
            self.gateway.reconcile("act_unknown", "SUCCEEDED")

    def test_reconcile_invalid_state(self):
        action_id = self.gateway.propose(self.scope, "r1", "step1", self.intent)
        self.gateway.dispatch(self.scope, action_id, "r1", "UNKNOWN_RESULT")
        with self.assertRaises(ContractError):
            self.gateway.reconcile(action_id, "UNKNOWN_RESULT")

if __name__ == '__main__':
    unittest.main()
