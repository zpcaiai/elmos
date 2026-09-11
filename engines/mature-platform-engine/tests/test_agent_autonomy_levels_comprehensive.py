import unittest
from elmos_mature_platform.types import (
    AgentAutonomyLevel,
    AutonomyReviewDecision,
    AgentAutonomyProfile
)
from elmos_mature_platform.agent_autonomy_levels_engine import AgentAutonomyLevelsEngine

class TestAgentAutonomyLevelsComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = AgentAutonomyLevelsEngine()
        
    def _create_profile(self, agent_id="agent1", tier=AgentAutonomyLevel.L1_SUGGESTION, max_tier=AgentAutonomyLevel.L3_BOUNDED_AUTONOMOUS):
        profile = AgentAutonomyProfile(
            agent_id=agent_id,
            agent_name=f"{agent_id}-name",
            current_tier=tier,
            max_permitted_tier=max_tier,
            evaluation_score=75.0,
            successful_runs=0,
            failed_runs=0,
            consecutive_successes=0,
            policy_violations=0
        )
        self.engine.register_agent(profile)
        return profile

    def test_register_agent(self):
        self._create_profile()
        profile = self.engine.get_agent_profile("agent1")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.agent_id, "agent1")
        
    def test_register_duplicate_agent_fails(self):
        self._create_profile()
        with self.assertRaises(ValueError):
            self._create_profile()

    def test_record_run_success(self):
        self._create_profile()
        p = self.engine.record_run_result("agent1", success=True)
        self.assertEqual(p.successful_runs, 1)
        self.assertEqual(p.consecutive_successes, 1)
        self.assertEqual(p.evaluation_score, 76.0)

    def test_record_run_success_cap(self):
        self._create_profile()
        self.engine.get_agent_profile("agent1").evaluation_score = 99.5
        p = self.engine.record_run_result("agent1", success=True)
        self.assertEqual(p.evaluation_score, 100.0)

    def test_record_run_failure(self):
        self._create_profile()
        p = self.engine.record_run_result("agent1", success=False)
        self.assertEqual(p.failed_runs, 1)
        self.assertEqual(p.consecutive_successes, 0)
        self.assertEqual(p.evaluation_score, 70.0)

    def test_record_run_failure_floor(self):
        self._create_profile()
        self.engine.get_agent_profile("agent1").evaluation_score = 3.0
        p = self.engine.record_run_result("agent1", success=False)
        self.assertEqual(p.evaluation_score, 0.0)

    def test_record_run_violation(self):
        self._create_profile()
        p = self.engine.record_run_result("agent1", success=True, had_policy_violation=True)
        self.assertEqual(p.policy_violations, 1)
        self.assertEqual(p.evaluation_score, 56.0) # 75 + 1 - 20

    def test_eval_missing_agent(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate_autonomy_level("unknown")
            
    def test_eval_maintained(self):
        self._create_profile()
        t = self.engine.evaluate_autonomy_level("agent1")
        self.assertEqual(t.decision, AutonomyReviewDecision.MAINTAINED)
        self.assertEqual(t.to_tier, AgentAutonomyLevel.L1_SUGGESTION)

    def test_eval_demoted_score(self):
        self._create_profile(tier=AgentAutonomyLevel.L2_SUPERVISED)
        self.engine.get_agent_profile("agent1").evaluation_score = 50.0
        t = self.engine.evaluate_autonomy_level("agent1")
        self.assertEqual(t.decision, AutonomyReviewDecision.DEMOTED)
        self.assertEqual(t.to_tier, AgentAutonomyLevel.L1_SUGGESTION)

    def test_eval_demoted_violation(self):
        self._create_profile(tier=AgentAutonomyLevel.L3_BOUNDED_AUTONOMOUS)
        self.engine.get_agent_profile("agent1").policy_violations = 1
        t = self.engine.evaluate_autonomy_level("agent1")
        self.assertEqual(t.decision, AutonomyReviewDecision.DEMOTED)
        self.assertEqual(t.to_tier, AgentAutonomyLevel.L2_SUPERVISED)

    def test_eval_demoted_many_violations(self):
        self._create_profile(tier=AgentAutonomyLevel.L3_BOUNDED_AUTONOMOUS)
        self.engine.get_agent_profile("agent1").policy_violations = 3
        t = self.engine.evaluate_autonomy_level("agent1")
        self.assertEqual(t.decision, AutonomyReviewDecision.DEMOTED)
        self.assertEqual(t.to_tier, AgentAutonomyLevel.L0_MANUAL)

    def test_eval_demoted_floor(self):
        self._create_profile(tier=AgentAutonomyLevel.L0_MANUAL)
        self.engine.get_agent_profile("agent1").policy_violations = 1
        t = self.engine.evaluate_autonomy_level("agent1")
        self.assertEqual(t.decision, AutonomyReviewDecision.DEMOTED)
        self.assertEqual(t.to_tier, AgentAutonomyLevel.L0_MANUAL)

    def test_eval_promoted(self):
        self._create_profile(tier=AgentAutonomyLevel.L1_SUGGESTION)
        p = self.engine.get_agent_profile("agent1")
        p.consecutive_successes = 10
        p.evaluation_score = 95.0
        t = self.engine.evaluate_autonomy_level("agent1")
        self.assertEqual(t.decision, AutonomyReviewDecision.PROMOTED)
        self.assertEqual(t.to_tier, AgentAutonomyLevel.L2_SUPERVISED)

    def test_eval_promoted_capped_by_max(self):
        self._create_profile(tier=AgentAutonomyLevel.L2_SUPERVISED, max_tier=AgentAutonomyLevel.L2_SUPERVISED)
        p = self.engine.get_agent_profile("agent1")
        p.consecutive_successes = 10
        p.evaluation_score = 95.0
        t = self.engine.evaluate_autonomy_level("agent1")
        self.assertEqual(t.decision, AutonomyReviewDecision.MAINTAINED)
        self.assertEqual(t.to_tier, AgentAutonomyLevel.L2_SUPERVISED)

    def test_request_elevation(self):
        self._create_profile(tier=AgentAutonomyLevel.L1_SUGGESTION, max_tier=AgentAutonomyLevel.L2_SUPERVISED)
        t = self.engine.request_tier_elevation("agent1", AgentAutonomyLevel.L4_FULL_AUTONOMOUS, "Trusted", "admin")
        self.assertEqual(t.decision, AutonomyReviewDecision.PROMOTED)
        p = self.engine.get_agent_profile("agent1")
        self.assertEqual(p.current_tier, AgentAutonomyLevel.L4_FULL_AUTONOMOUS)
        self.assertEqual(p.max_permitted_tier, AgentAutonomyLevel.L4_FULL_AUTONOMOUS)
        
    def test_request_elevation_missing(self):
        with self.assertRaises(ValueError):
            self.engine.request_tier_elevation("unknown", AgentAutonomyLevel.L4_FULL_AUTONOMOUS, "Justification", "admin")

    def test_enforce_gate_allowed(self):
        self._create_profile(tier=AgentAutonomyLevel.L3_BOUNDED_AUTONOMOUS)
        g = self.engine.enforce_action_gate("agent1", "execute_code", AgentAutonomyLevel.L2_SUPERVISED)
        self.assertTrue(g.allowed)
        self.assertFalse(g.requires_human_approval)

    def test_enforce_gate_allowed_exact(self):
        self._create_profile(tier=AgentAutonomyLevel.L3_BOUNDED_AUTONOMOUS)
        g = self.engine.enforce_action_gate("agent1", "execute_code", AgentAutonomyLevel.L3_BOUNDED_AUTONOMOUS)
        self.assertTrue(g.allowed)
        self.assertFalse(g.requires_human_approval)
        
    def test_enforce_gate_denied(self):
        self._create_profile(tier=AgentAutonomyLevel.L1_SUGGESTION)
        g = self.engine.enforce_action_gate("agent1", "execute_code", AgentAutonomyLevel.L2_SUPERVISED)
        self.assertFalse(g.allowed)
        self.assertTrue(g.requires_human_approval)
        
    def test_enforce_gate_missing(self):
        with self.assertRaises(ValueError):
            self.engine.enforce_action_gate("unk", "act", AgentAutonomyLevel.L1_SUGGESTION)

    def test_restrict_agent(self):
        self._create_profile(tier=AgentAutonomyLevel.L4_FULL_AUTONOMOUS)
        t = self.engine.restrict_agent("agent1", "Emergency", "admin")
        self.assertEqual(t.decision, AutonomyReviewDecision.RESTRICTED)
        self.assertEqual(t.to_tier, AgentAutonomyLevel.L0_MANUAL)
        p = self.engine.get_agent_profile("agent1")
        self.assertEqual(p.current_tier, AgentAutonomyLevel.L0_MANUAL)
        
    def test_restrict_missing(self):
        with self.assertRaises(ValueError):
            self.engine.restrict_agent("unk", "Bad", "admin")

    def test_transition_history(self):
        self._create_profile(tier=AgentAutonomyLevel.L2_SUPERVISED)
        self.engine.get_agent_profile("agent1").evaluation_score = 20.0
        self.engine.evaluate_autonomy_level("agent1")
        self.engine.request_tier_elevation("agent1", AgentAutonomyLevel.L3_BOUNDED_AUTONOMOUS, "Fix", "Admin")
        h = self.engine.get_transition_history("agent1")
        self.assertEqual(len(h), 2)
        
    def test_transition_history_missing(self):
        with self.assertRaises(ValueError):
            self.engine.get_transition_history("unk")

    def test_fleet_report_empty(self):
        rep = self.engine.get_fleet_autonomy_report()
        self.assertEqual(rep["total_agents"], 0)

    def test_fleet_report(self):
        self._create_profile("a1", tier=AgentAutonomyLevel.L1_SUGGESTION)
        self._create_profile("a2", tier=AgentAutonomyLevel.L1_SUGGESTION)
        p = self.engine.get_agent_profile("a1")
        p.evaluation_score = 50.0
        p.policy_violations = 2
        p2 = self.engine.get_agent_profile("a2")
        p2.evaluation_score = 100.0
        
        self.engine.request_tier_elevation("a1", AgentAutonomyLevel.L2_SUPERVISED, "up", "adm")
        self.engine.evaluate_autonomy_level("a2")
        
        rep = self.engine.get_fleet_autonomy_report()
        self.assertEqual(rep["total_agents"], 2)
        self.assertEqual(rep["average_score"], 75.0)
        self.assertEqual(rep["total_violations"], 2)
        self.assertEqual(rep["tier_breakdown"].get(AgentAutonomyLevel.L2_SUPERVISED.name), 1)
        self.assertTrue(rep["elevation_rate"] > 0)
        
    def test_record_run_result_missing(self):
        with self.assertRaises(ValueError):
            self.engine.record_run_result("unknown", True)

if __name__ == '__main__':
    unittest.main()
