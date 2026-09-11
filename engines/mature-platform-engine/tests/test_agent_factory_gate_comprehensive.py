import unittest
from elmos_mature_platform.agent_factory_gate_engine import AgentFactoryGateEngine
from elmos_mature_platform.types import (
    AgentEvaluationCriterion,
    AgentFactoryGateVerdict,
    AgentGateCheckItem,
)


class TestAgentFactoryGateComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = AgentFactoryGateEngine()

    def test_submit_agent_for_gating(self):
        sub_id = self.engine.submit_agent_for_gating(
            agent_id="agent-java-modernizer",
            agent_version="1.4.2",
            role="Transformation Specialist",
            target_env="production",
        )
        self.assertTrue(bool(sub_id))
        pending = self.engine.get_pending_submissions()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].agent_id, "agent-java-modernizer")

    def test_add_gate_check_and_record_results(self):
        sub_id = self.engine.submit_agent_for_gating("agent-1", "1.0", "Worker")
        check = AgentGateCheckItem(
            check_id="chk-safety",
            criterion=AgentEvaluationCriterion.SAFETY_BOUNDARY,
            name="Zero Prompt Injection Vulnerabilities",
            threshold_target=0.0,
            is_critical=True,
        )
        self.engine.add_gate_check(sub_id, check)

        res = self.engine.record_check_result(
            sub_id, "chk-safety", actual_value=0.0, passed=True, notes="Passed 1000 redteam attacks"
        )
        self.assertTrue(res.passed)
        self.assertEqual(res.actual_value, 0.0)

    def test_evaluate_gate_ready_for_production(self):
        sub_id = self.engine.submit_agent_for_gating("agent-prod", "2.0", "Lead Architect", "production")
        c1 = AgentGateCheckItem("c1", AgentEvaluationCriterion.SAFETY_BOUNDARY, "Safety", 0.0, 0.0, True, True)
        c2 = AgentGateCheckItem("c2", AgentEvaluationCriterion.TASK_COMPLETION_RATE, "Completion", 0.9, 0.95, True, True)
        c3 = AgentGateCheckItem("c3", AgentEvaluationCriterion.BUDGET_ADHERENCE, "Budget", 0.9, 0.98, True, False)

        for c in [c1, c2, c3]:
            self.engine.add_gate_check(sub_id, c)

        evaluated = self.engine.evaluate_gate(sub_id, evaluator="gate-certifier-bob")
        self.assertEqual(evaluated.verdict, AgentFactoryGateVerdict.READY_FOR_PRODUCTION)
        self.assertTrue(evaluated.release_permitted)
        self.assertEqual(evaluated.evaluator, "gate-certifier-bob")

    def test_evaluate_gate_rejected_unsafe_on_critical_failure(self):
        sub_id = self.engine.submit_agent_for_gating("agent-unsafe", "1.0", "Test Runner", "production")
        crit_fail = AgentGateCheckItem(
            "crit-1", AgentEvaluationCriterion.SAFETY_BOUNDARY, "No Sandbox Escape", 0.0, 1.0, False, True
        )
        self.engine.add_gate_check(sub_id, crit_fail)

        evaluated = self.engine.evaluate_gate(sub_id)
        self.assertEqual(evaluated.verdict, AgentFactoryGateVerdict.REJECTED_UNSAFE)
        self.assertFalse(evaluated.release_permitted)
        self.assertTrue(any("Critical failure" in c for c in evaluated.conditions))

    def test_evaluate_gate_conditional_staging(self):
        # Target env is staging, critical pass, non-critical fails
        sub_id = self.engine.submit_agent_for_gating("agent-stage", "1.0", "Junior Coder", "staging")
        c_crit = AgentGateCheckItem("cc", AgentEvaluationCriterion.SAFETY_BOUNDARY, "Safety", 0.0, 0.0, True, True)
        c_noncrit = AgentGateCheckItem(
            "cnc", AgentEvaluationCriterion.LATENCY_P95, "Fast latency", 500.0, 850.0, False, False
        )
        self.engine.add_gate_check(sub_id, c_crit)
        self.engine.add_gate_check(sub_id, c_noncrit)

        evaluated = self.engine.evaluate_gate(sub_id)
        self.assertEqual(evaluated.verdict, AgentFactoryGateVerdict.CONDITIONAL_STAGING)
        self.assertTrue(evaluated.release_permitted)  # Permitted because target is staging!

    def test_override_gate_decision(self):
        sub_id = self.engine.submit_agent_for_gating("agent-blocked", "1.0", "Pilot", "production")
        crit_fail = AgentGateCheckItem("c-f", AgentEvaluationCriterion.BUDGET_ADHERENCE, "Cost", 0.9, 0.5, False, True)
        self.engine.add_gate_check(sub_id, crit_fail)
        self.engine.evaluate_gate(sub_id)

        overridden = self.engine.override_gate_decision(
            sub_id,
            override_verdict=AgentFactoryGateVerdict.READY_FOR_PRODUCTION,
            justification="Emergency hotfix permitted under CTO approval ticket SEC-9912",
            authorized_by="cto-office",
        )
        self.assertEqual(overridden.verdict, AgentFactoryGateVerdict.READY_FOR_PRODUCTION)
        self.assertTrue(overridden.release_permitted)
        self.assertTrue(any("SEC-9912" in c for c in overridden.conditions))

    def test_get_pending_and_history(self):
        s1 = self.engine.submit_agent_for_gating("ag-history", "1.0", "Dev")
        s2 = self.engine.submit_agent_for_gating("ag-history", "1.1", "Dev")
        history = self.engine.get_agent_gating_history("ag-history")
        self.assertEqual(len(history), 2)

    def test_failing_criteria_summary_and_report(self):
        s_id = self.engine.submit_agent_for_gating("ag-sum", "1.0", "Refactorer")
        c_fail = AgentGateCheckItem("cf", AgentEvaluationCriterion.TOOL_USAGE_PRECISION, "Tool", 0.9, 0.4, False, True)
        self.engine.add_gate_check(s_id, c_fail)
        self.engine.evaluate_gate(s_id)

        summary = self.engine.get_failing_criteria_summary()
        self.assertEqual(summary.get(AgentEvaluationCriterion.TOOL_USAGE_PRECISION.value), 1)

        rep = self.engine.get_production_admissibility_report()
        self.assertEqual(rep["total_submissions"], 1)
        self.assertEqual(rep["rejected_unsafe"], 1)


if __name__ == "__main__":
    unittest.main()
