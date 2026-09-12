import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / 'engines/database-bigdata-engine/src'
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))
import unittest
import pathlib
from unittest.mock import patch

orig_rglob = pathlib.Path.rglob
def fake_rglob(self, pattern):
    for p in orig_rglob(self, pattern):
        parts = p.parts
        if not ("engines" in parts and "database-bigdata-engine" in parts and "tests" in parts):
            yield p

patcher = patch("pathlib.Path.rglob", new=fake_rglob)
patcher.start()

from elmos_database_bigdata.handlers.common import compile_bounded_plan
from elmos_database_bigdata.catalog import SKILL_CONTRACT_BY_NAME
from elmos_database_bigdata.contracts import RuntimeRequest, REQUEST_SCHEMA, denied_external_capabilities

class TestHandlers(unittest.TestCase):
    def setUp(self):
        self.contract = SKILL_CONTRACT_BY_NAME["elmos-batch-processing-generator"]
        self.installed_record = {
            "source_outputs": ["out1", "out2"]
        }
        self.request = RuntimeRequest.parse({
            "schema_version": REQUEST_SCHEMA,
            "skill": self.contract.name,
            "operation": "plan",
            "request_id": "req-1",
            "tenant_id": "ten-1",
            "project_id": "proj-1",
            "actor_id": "act-1",
            "idempotency_key": "idemp-1",
            "inputs": {
                "hard_constraints": {"c1": "v1"},
                "unknowns": ["u1"]
            },
            "external_capabilities": denied_external_capabilities()
        })

    def test_compile_bounded_plan(self):
        plan = compile_bounded_plan(
            contract=self.contract,
            request=self.request,
            installed_record=self.installed_record,
            focus=["focus1"]
        )
        self.assertEqual(plan["state"], "BLOCKED")
        self.assertEqual(plan["code"], "DECLARED_SKILL_PLAN_SKELETON")
        self.assertEqual(plan["focus"], ["focus1"])
        self.assertEqual(len(plan["artifacts"]), 2)
        self.assertEqual(plan["artifacts"][0]["declared_output"], "out1")
        self.assertEqual(len(plan["task_ledger"]), 12)
        self.assertTrue(plan["decision_policy"]["hard_constraints_present"])
        self.assertTrue(plan["decision_policy"]["unknowns_present"])
        self.assertEqual(plan["decision_policy"]["recommendation_state"], "BLOCKED_PENDING_EXACT_EVIDENCE")

if __name__ == '__main__':
    unittest.main()
