from __future__ import annotations
import unittest
from elmos_formal_assurance.cache import proof_cache_key
from elmos_formal_assurance.models import AssuranceLevel, Criticality, ProofObligation
from elmos_formal_assurance.planner import topological_order, estimate_machine_wall_clock_seconds, PlanError

BASE = {
    "formula_hash":"a"*64,"semantic_profile_hash":"b"*64,"semantic_model_hash":"c"*64,
    "assumption_hash":"d"*64,"tcb_hash":"e"*64,"engine":"z3","engine_version":"1",
    "engine_digest":"f"*64,"engine_options":{"timeout":10},"bound":{},
    "source_hash":"1"*64,"target_hash":"2"*64,
}

def o(oid, deps=(), kind="STATE_INVARIANT", criticality=Criticality.P0):
    return ProofObligation(oid, criticality, kind, AssuranceLevel.A2_SOLVER_PROVED, dependencies=deps)

class CachePlannerTests(unittest.TestCase):
    def test_cache_key_is_stable(self):
        self.assertEqual(proof_cache_key(BASE), proof_cache_key(dict(reversed(list(BASE.items())))))

    def test_every_cache_dimension_changes_key(self):
        original = proof_cache_key(BASE)
        for key in BASE:
            changed = dict(BASE)
            changed[key] = {"x":1} if isinstance(BASE[key], dict) else str(BASE[key]) + "-changed"
            self.assertNotEqual(original, proof_cache_key(changed), key)

    def test_missing_cache_dimension_fails(self):
        changed = dict(BASE)
        del changed["assumption_hash"]
        with self.assertRaises(ValueError):
            proof_cache_key(changed)

    def test_topological_order(self):
        self.assertEqual(["a","b","c"], topological_order([o("c",("b",)),o("a"),o("b",("a",))]))

    def test_unknown_dependency_fails(self):
        with self.assertRaises(PlanError):
            topological_order([o("a",("missing",))])

    def test_cycle_fails(self):
        with self.assertRaises(PlanError):
            topological_order([o("a",("b",)),o("b",("a",))])

    def test_estimate_reports_machine_wall_clock(self):
        estimate = estimate_machine_wall_clock_seconds([o("a"),o("b"),o("c")], max_parallel=2)
        self.assertEqual(270, estimate)

    def test_empty_plan_estimate(self):
        self.assertEqual(0, estimate_machine_wall_clock_seconds([]))

if __name__ == "__main__":
    unittest.main()
