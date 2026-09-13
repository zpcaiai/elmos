import unittest
from elmos_ai_optimization.agent_subflow import BoundedAgentSubflow, SubflowCheckpoint
from elmos_ai_optimization.contracts import TrustedScope, RevisionBinding, ActionIntent, Receipt, ContractError

class TestAgentSubflow(unittest.TestCase):
    def setUp(self):
        self.subflow = BoundedAgentSubflow(max_steps=3, max_rounds=2)
        self.scope = TrustedScope("t1", "p1", 1, "sec_ref", (RevisionBinding("r1", "s1", "g1"),))

    def test_init_subflow(self):
        cp = self.subflow.init_subflow("run1", "v1", ["ev1"])
        self.assertEqual(cp.state, "INIT")
        self.assertEqual(cp.step_index, 0)
        self.assertEqual(cp.run_ref, "run1")
        self.assertEqual(cp.evidence_refs, ("ev1",))
        self.assertIsNone(cp.proposed_intent)

    def test_advance_evidence_packed(self):
        self.subflow.init_subflow("run1", "v1", ["ev1"])
        cp = self.subflow.advance(self.scope, "run1", ["ev2"])
        self.assertEqual(cp.state, "EVIDENCE_PACKED")
        self.assertEqual(cp.step_index, 1)
        self.assertEqual(set(cp.evidence_refs), {"ev1", "ev2"})

    def test_advance_action_proposed(self):
        self.subflow.init_subflow("run1", "v1", ["ev1"])
        intent = ActionIntent("run1", "step1", "base_rev", "digest", "artifact", "budget", "plan")
        cp = self.subflow.advance(self.scope, "run1", [], proposed_intent=intent)
        self.assertEqual(cp.state, "ACTION_PROPOSED")
        self.assertEqual(cp.step_index, 1)
        self.assertIsNotNone(cp.proposed_intent)

    def test_advance_not_found(self):
        with self.assertRaises(ContractError):
            self.subflow.advance(self.scope, "run_unknown", [])

    def test_advance_max_steps(self):
        self.subflow.init_subflow("run1", "v1", ["ev1"])
        self.subflow.advance(self.scope, "run1", ["ev2"]) # step 1
        self.subflow.advance(self.scope, "run1", ["ev3"]) # step 2
        self.subflow.advance(self.scope, "run1", ["ev4"]) # step 3
        cp = self.subflow.advance(self.scope, "run1", ["ev5"]) # step 4 -> exceeds max 3
        self.assertEqual(cp.state, "BLOCKED")

    def test_advance_terminal_state(self):
        self.subflow.init_subflow("run1", "v1", ["ev1"])
        self.subflow.advance(self.scope, "run1", ["ev2"]) # step 1
        self.subflow.advance(self.scope, "run1", ["ev3"]) # step 2
        self.subflow.advance(self.scope, "run1", ["ev4"]) # step 3
        cp1 = self.subflow.advance(self.scope, "run1", ["ev5"]) # step 4 -> BLOCKED
        
        # Advance again from terminal state should return same state
        cp2 = self.subflow.advance(self.scope, "run1", ["ev6"])
        self.assertEqual(cp2.state, "BLOCKED")
        self.assertEqual(cp2.step_index, 4)

    def test_advance_no_progress(self):
        self.subflow.init_subflow("run1", "v1", ["ev1"])
        self.subflow.advance(self.scope, "run1", ["ev2"]) # step 1
        # Advance again with no new evidence and no intent
        cp = self.subflow.advance(self.scope, "run1", [])
        self.assertEqual(cp.state, "FAILED")

    def test_record_receipt_succeeded(self):
        self.subflow.init_subflow("run1", "v1", ["ev1"])
        intent = ActionIntent("run1", "step1", "base_rev", "digest", "artifact", "budget", "plan")
        self.subflow.advance(self.scope, "run1", [], proposed_intent=intent)
        
        receipt = Receipt("action_id", "SUCCEEDED", "receipt_ref")
        cp = self.subflow.record_receipt("run1", receipt)
        self.assertEqual(cp.state, "DONE")
        
    def test_record_receipt_failed(self):
        self.subflow.init_subflow("run1", "v1", ["ev1"])
        intent = ActionIntent("run1", "step1", "base_rev", "digest", "artifact", "budget", "plan")
        self.subflow.advance(self.scope, "run1", [], proposed_intent=intent)
        
        receipt = Receipt("action_id", "FAILED")
        cp = self.subflow.record_receipt("run1", receipt)
        self.assertEqual(cp.state, "FAILED")

    def test_record_receipt_not_found(self):
        receipt = Receipt("action_id", "SUCCEEDED")
        with self.assertRaises(ContractError):
            self.subflow.record_receipt("run_unknown", receipt)

    def test_get_checkpoint(self):
        self.subflow.init_subflow("run1", "v1", ["ev1"])
        cp = self.subflow.get_checkpoint("run1")
        self.assertIsNotNone(cp)
        self.assertEqual(cp.state, "INIT")
        
        self.assertIsNone(self.subflow.get_checkpoint("run_unknown"))

if __name__ == '__main__':
    unittest.main()
