import unittest
import datetime
from elmos_mature_platform.types import (
    PrivacyBudget,
    FederatedParticipant,
    FederatedRound,
    FederatedRoundStatus,
    PrivacyMechanism
)
from elmos_mature_platform.privacy_preserving_learning_engine import PrivacyPreservingLearningEngine

class TestPrivacyPreservingLearningEngine(unittest.TestCase):
    def setUp(self):
        self.engine = PrivacyPreservingLearningEngine()
        
    def test_create_budget(self):
        b = PrivacyBudget(budget_id="b1", tenant_id="t1", epsilon_total=5.0)
        bid = self.engine.create_budget(b)
        self.assertEqual(bid, "b1")
        self.assertEqual(self.engine.budgets["t1"].epsilon_total, 5.0)

    def test_check_budget_success(self):
        self.engine.create_budget(PrivacyBudget(budget_id="b1", tenant_id="t1", epsilon_total=10.0))
        self.assertTrue(self.engine.check_budget("t1", 2.0))

    def test_check_budget_insufficient_epsilon(self):
        self.engine.create_budget(PrivacyBudget(budget_id="b1", tenant_id="t1", epsilon_total=10.0))
        self.assertFalse(self.engine.check_budget("t1", 11.0))

    def test_check_budget_insufficient_queries(self):
        self.engine.create_budget(PrivacyBudget(budget_id="b1", tenant_id="t1", epsilon_total=10.0, queries_allowed=1, queries_used=1))
        self.assertFalse(self.engine.check_budget("t1", 1.0))

    def test_check_budget_not_found(self):
        with self.assertRaises(PermissionError):
            self.engine.check_budget("t1", 1.0)

    def test_consume_budget_success(self):
        self.engine.create_budget(PrivacyBudget(budget_id="b1", tenant_id="t1", epsilon_total=10.0))
        res = self.engine.consume_budget("t1", 3.0)
        self.assertEqual(res.epsilon_used, 3.0)
        self.assertEqual(res.queries_used, 1)

    def test_consume_budget_fails(self):
        self.engine.create_budget(PrivacyBudget(budget_id="b1", tenant_id="t1", epsilon_total=1.0))
        with self.assertRaises(ValueError):
            self.engine.consume_budget("t1", 2.0)

    def test_register_participant(self):
        p = FederatedParticipant(participant_id="p1", tenant_id="t1")
        pid = self.engine.register_participant(p)
        self.assertEqual(pid, "p1")
        self.assertIn("p1", self.engine.participants)

    def test_create_round(self):
        r = FederatedRound(round_id="r1", round_number=1)
        rid = self.engine.create_round(r)
        self.assertEqual(rid, "r1")

    def test_start_round_success(self):
        self.engine.register_participant(FederatedParticipant(participant_id="p1", tenant_id="t1"))
        self.engine.register_participant(FederatedParticipant(participant_id="p2", tenant_id="t2"))
        self.engine.create_round(FederatedRound(round_id="r1", round_number=1, participants=["p1", "p2"], min_participants=2))
        r = self.engine.start_round("r1")
        self.assertEqual(r.status, FederatedRoundStatus.TRAINING)
        self.assertIsNotNone(r.started_at)

    def test_start_round_not_enough_participants(self):
        self.engine.register_participant(FederatedParticipant(participant_id="p1", tenant_id="t1"))
        self.engine.create_round(FederatedRound(round_id="r1", round_number=1, participants=["p1"], min_participants=2))
        with self.assertRaises(ValueError):
            self.engine.start_round("r1")

    def test_start_round_inactive_participant(self):
        self.engine.register_participant(FederatedParticipant(participant_id="p1", tenant_id="t1"))
        self.engine.register_participant(FederatedParticipant(participant_id="p2", tenant_id="t2", active=False))
        self.engine.create_round(FederatedRound(round_id="r1", round_number=1, participants=["p1", "p2"], min_participants=2))
        with self.assertRaises(ValueError):
            self.engine.start_round("r1")

    def test_start_round_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.start_round("r1")

    def test_start_round_wrong_status(self):
        self.engine.register_participant(FederatedParticipant(participant_id="p1", tenant_id="t1"))
        self.engine.register_participant(FederatedParticipant(participant_id="p2", tenant_id="t2"))
        r = FederatedRound(round_id="r1", round_number=1, participants=["p1", "p2"], min_participants=2)
        r.status = FederatedRoundStatus.TRAINING
        self.engine.create_round(r)
        with self.assertRaises(ValueError):
            self.engine.start_round("r1")

    def test_submit_contribution_success(self):
        self._setup_started_round()
        p = self.engine.submit_contribution("r1", "p1", 100)
        self.assertEqual(p.contribution_count, 1)
        self.assertEqual(self.engine.round_contributions["r1"]["p1"], 100)

    def test_submit_contribution_round_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.submit_contribution("r1", "p1", 100)

    def test_submit_contribution_participant_not_found(self):
        self.engine.create_round(FederatedRound(round_id="r1", round_number=1))
        with self.assertRaises(KeyError):
            self.engine.submit_contribution("r1", "p1", 100)

    def test_submit_contribution_wrong_status(self):
        self.engine.register_participant(FederatedParticipant(participant_id="p1", tenant_id="t1"))
        self.engine.create_round(FederatedRound(round_id="r1", round_number=1, participants=["p1"]))
        with self.assertRaises(ValueError):
            self.engine.submit_contribution("r1", "p1", 100)

    def test_submit_contribution_not_in_round(self):
        self.engine.register_participant(FederatedParticipant(participant_id="p1", tenant_id="t1"))
        self.engine.register_participant(FederatedParticipant(participant_id="p2", tenant_id="t2"))
        self.engine.create_round(FederatedRound(round_id="r1", round_number=1, participants=["p1"], min_participants=1))
        self.engine.start_round("r1")
        with self.assertRaises(ValueError):
            self.engine.submit_contribution("r1", "p2", 100)

    def test_submit_contribution_inactive(self):
        self._setup_started_round()
        self.engine.participants["p1"].active = False
        with self.assertRaises(ValueError):
            self.engine.submit_contribution("r1", "p1", 100)

    def test_aggregate_round_success(self):
        self._setup_started_round()
        self.engine.create_budget(PrivacyBudget(budget_id="b1", tenant_id="t1", epsilon_total=10.0))
        self.engine.create_budget(PrivacyBudget(budget_id="b2", tenant_id="t2", epsilon_total=10.0))
        self.engine.submit_contribution("r1", "p1", 100)
        self.engine.submit_contribution("r1", "p2", 300)
        r = self.engine.aggregate_round("r1")
        self.assertEqual(r.status, FederatedRoundStatus.AGGREGATING)
        self.assertEqual(r.model_version_out, 1)
        self.assertEqual(r.aggregation_weights["p1"], 0.25)
        self.assertEqual(r.aggregation_weights["p2"], 0.75)

    def test_aggregate_round_no_contributions(self):
        self._setup_started_round()
        with self.assertRaises(ValueError):
            self.engine.aggregate_round("r1")

    def test_aggregate_round_zero_data(self):
        self._setup_started_round()
        self.engine.create_budget(PrivacyBudget(budget_id="b1", tenant_id="t1", epsilon_total=10.0))
        self.engine.submit_contribution("r1", "p1", 0)
        with self.assertRaises(ValueError):
            self.engine.aggregate_round("r1")

    def test_aggregate_round_insufficient_budget(self):
        self._setup_started_round()
        self.engine.create_budget(PrivacyBudget(budget_id="b1", tenant_id="t1", epsilon_total=0.5)) # insufficient for epsilon_spent=1.0
        self.engine.submit_contribution("r1", "p1", 100)
        with self.assertRaises(ValueError):
            self.engine.aggregate_round("r1")

    def test_complete_round_success(self):
        self._setup_started_round()
        self.engine.create_budget(PrivacyBudget(budget_id="b1", tenant_id="t1", epsilon_total=10.0))
        self.engine.create_budget(PrivacyBudget(budget_id="b2", tenant_id="t2", epsilon_total=10.0))
        self.engine.submit_contribution("r1", "p1", 100)
        self.engine.submit_contribution("r1", "p2", 300)
        self.engine.aggregate_round("r1")
        r = self.engine.complete_round("r1")
        self.assertEqual(r.status, FederatedRoundStatus.COMPLETED)
        self.assertEqual(self.engine.participants["p1"].model_version, 1)

    def test_complete_round_wrong_status(self):
        self._setup_started_round()
        with self.assertRaises(ValueError):
            self.engine.complete_round("r1")

    def test_drop_participant(self):
        self.engine.register_participant(FederatedParticipant(participant_id="p1", tenant_id="t1"))
        p = self.engine.drop_participant("r1", "p1")
        self.assertEqual(p.dropped_rounds, 1)

    def test_get_privacy_report(self):
        self.engine.create_budget(PrivacyBudget(budget_id="b1", tenant_id="t1", epsilon_total=10.0, epsilon_used=2.0, queries_allowed=10, queries_used=1))
        rep = self.engine.get_privacy_report("t1")
        self.assertEqual(rep["epsilon_remaining"], 8.0)
        self.assertEqual(rep["queries_remaining"], 9)

    def test_get_privacy_report_not_found(self):
        with self.assertRaises(PermissionError):
            self.engine.get_privacy_report("t1")

    def test_get_federation_report(self):
        self._setup_started_round()
        self.engine.create_budget(PrivacyBudget(budget_id="b1", tenant_id="t1", epsilon_total=10.0))
        self.engine.create_budget(PrivacyBudget(budget_id="b2", tenant_id="t2", epsilon_total=10.0))
        self.engine.submit_contribution("r1", "p1", 100)
        self.engine.submit_contribution("r1", "p2", 300)
        self.engine.aggregate_round("r1")
        self.engine.complete_round("r1")
        
        self.engine.drop_participant("r1", "p1")
        
        rep = self.engine.get_federation_report()
        self.assertEqual(rep["total_rounds"], 1)
        self.assertEqual(rep["completed_rounds"], 1)
        self.assertEqual(rep["total_participants"], 2)
        self.assertEqual(rep["active_participants"], 2)
        # p1: 1 contrib, 1 drop = 2
        # p2: 1 contrib, 0 drop = 1
        # total contribs = 2, total drops = 1
        # rate = 2 / 3
        self.assertAlmostEqual(rep["avg_participation_rate"], 2/3)
        self.assertEqual(rep["highest_model_version"], 1)
        
    def test_get_federation_report_empty(self):
        rep = self.engine.get_federation_report()
        self.assertEqual(rep["total_rounds"], 0)
        self.assertEqual(rep["avg_participation_rate"], 0.0)

    def _setup_started_round(self):
        self.engine.register_participant(FederatedParticipant(participant_id="p1", tenant_id="t1"))
        self.engine.register_participant(FederatedParticipant(participant_id="p2", tenant_id="t2"))
        self.engine.create_round(FederatedRound(
            round_id="r1", 
            round_number=1, 
            participants=["p1", "p2"], 
            min_participants=2,
            epsilon_spent=1.0
        ))
        self.engine.start_round("r1")

if __name__ == "__main__":
    unittest.main()
