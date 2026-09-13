import unittest
from dataclasses import replace
from elmos_fde_kernel import AppendOnlyLedger, LedgerVerificationError, TransformationDAG, CycleError, GateEvaluator, CoverageReport

class LedgerTests(unittest.TestCase):
    def test_append_and_verify(self):
        ledger=AppendOnlyLedger("evidence")
        ledger.append("e1", {"x":1}, "2026-08-31T00:00:00Z")
        ledger.append("e2", {"x":2}, "2026-08-31T00:00:01Z")
        self.assertTrue(ledger.verify())
        self.assertEqual(2,len(ledger.events))

    def test_duplicate_event_rejected(self):
        ledger=AppendOnlyLedger("claim"); ledger.append("e1", {})
        with self.assertRaises(ValueError): ledger.append("e1", {})

    def test_tamper_detected(self):
        ledger=AppendOnlyLedger("change"); ledger.append("e1", {"x":1}, "2026-08-31T00:00:00Z")
        ledger._events[0]=replace(ledger._events[0], payload={"x":2})
        with self.assertRaises(LedgerVerificationError): ledger.verify()

class DagTests(unittest.TestCase):
    def test_order_and_critical_path(self):
        dag=TransformationDAG([{"step_id":"a","machine_seconds":2},{"step_id":"b","depends_on":["a"],"machine_seconds":3},{"step_id":"c","depends_on":["a"],"machine_seconds":5},{"step_id":"d","depends_on":["b","c"],"machine_seconds":7}])
        self.assertEqual("a",dag.topological_order()[0]); self.assertEqual(14,dag.critical_path_seconds())

    def test_cycle_rejected(self):
        with self.assertRaises(CycleError): TransformationDAG([{"step_id":"a","depends_on":["b"]},{"step_id":"b","depends_on":["a"]}])

    def test_missing_dependency_rejected(self):
        with self.assertRaises(ValueError): TransformationDAG([{"step_id":"a","depends_on":["missing"]}])

class GateTests(unittest.TestCase):
    def test_clean_e3(self):
        d=GateEvaluator().evaluate([{"id":"x","status":"pass","material":True}],"E3",True)
        self.assertTrue(d.allowed); self.assertEqual("E3",d.recommendation)

    def test_unknown_blocks(self):
        d=GateEvaluator().evaluate([{"id":"u","status":"unknown","material":True}],"E3",True)
        self.assertFalse(d.allowed); self.assertIn("u",d.blockers)

    def test_self_approval_blocks(self):
        d=GateEvaluator().evaluate([],"E2",False)
        self.assertFalse(d.allowed); self.assertIn("producer-self-approval",d.blockers)

    def test_e4_rejected(self):
        self.assertFalse(GateEvaluator().evaluate([],"E4",True).allowed)

class CoverageTests(unittest.TestCase):
    def test_honest_complete(self):
        c=CoverageReport(observed=5,verified_absent=2)
        self.assertTrue(c.honest_complete); self.assertEqual(1.0,c.resolved_ratio)

    def test_unknown_visible(self):
        c=CoverageReport(observed=5,unknown=1)
        self.assertFalse(c.honest_complete); self.assertIn("unknown=1",c.statement())

    def test_negative_rejected(self):
        with self.assertRaises(ValueError): CoverageReport(unknown=-1)

if __name__=="__main__": unittest.main()
