import unittest
from typing import List
from elmos_mature_platform.types import (
    ExpertDomain, ExpertValidationOutcome as ValidationOutcome, ExpertValidator, ExpertReview
)
from elmos_mature_platform.independent_expert_validation_engine import IndependentExpertValidationEngine

class TestIndependentExpertValidationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = IndependentExpertValidationEngine()

    def test_register_validator(self):
        validator = ExpertValidator(validator_id="v1", name="Alice", domain=ExpertDomain.SECURITY)
        vid = self.engine.register_validator(validator)
        self.assertEqual(vid, "v1")
        self.assertEqual(len(self.engine._validators), 1)

    def test_check_conflict_of_interest_same_org(self):
        validator = ExpertValidator(validator_id="v1", name="Alice", domain=ExpertDomain.SECURITY, organization="OrgA")
        self.engine.register_validator(validator)
        self.assertTrue(self.engine.check_conflict_of_interest("v1", "OrgA"))
        self.assertFalse(self.engine.check_conflict_of_interest("v1", "OrgB"))

    def test_check_conflict_of_interest_listed_conflict(self):
        validator = ExpertValidator(
            validator_id="v1", name="Alice", domain=ExpertDomain.SECURITY, 
            organization="OrgA", conflicts_of_interest=["OrgB"]
        )
        self.engine.register_validator(validator)
        self.assertTrue(self.engine.check_conflict_of_interest("v1", "OrgB"))
        self.assertFalse(self.engine.check_conflict_of_interest("v1", "OrgC"))

    def test_check_conflict_validator_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.check_conflict_of_interest("nonexistent", "OrgA")

    def test_assign_review_success(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="Alice", domain=ExpertDomain.SECURITY))
        review = ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY)
        rid = self.engine.assign_review(review)
        self.assertEqual(rid, "r1")
        self.assertEqual(len(self.engine._reviews), 1)

    def test_assign_review_validator_not_found(self):
        review = ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY)
        with self.assertRaises(ValueError):
            self.engine.assign_review(review)

    def test_assign_review_validator_inactive(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="Alice", domain=ExpertDomain.SECURITY, active=False))
        review = ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY)
        with self.assertRaises(ValueError):
            self.engine.assign_review(review)

    def test_submit_review_success(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="Alice", domain=ExpertDomain.SECURITY))
        review = ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY)
        self.engine.assign_review(review)
        
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, ["LGTM"], 9.5, 2.0)
        self.assertEqual(review.outcome, ValidationOutcome.APPROVED)
        self.assertEqual(review.score, 9.5)
        self.assertEqual(review.review_hours, 2.0)
        self.assertTrue(review.submitted_at)

    def test_submit_review_updates_stats(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="Alice", domain=ExpertDomain.SECURITY))
        review1 = ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY)
        review2 = ExpertReview(review_id="r2", validator_id="v1", subject_id="s2", domain=ExpertDomain.SECURITY)
        self.engine.assign_review(review1)
        self.engine.assign_review(review2)
        
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, ["LGTM"], 9.0, 2.0)
        self.engine.submit_review("r2", ValidationOutcome.REJECTED, ["Bad"], 4.0, 4.0)
        
        stats = self.engine.get_validator_stats("v1")
        self.assertEqual(stats["total_reviews"], 2)
        self.assertEqual(stats["approval_rate"], 0.5)
        self.assertEqual(stats["avg_review_hours"], 3.0)

    def test_submit_review_invalid_score(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="Alice", domain=ExpertDomain.SECURITY))
        review = ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY)
        self.engine.assign_review(review)
        
        with self.assertRaises(ValueError):
            self.engine.submit_review("r1", ValidationOutcome.APPROVED, [], 11.0, 1.0)

    def test_submit_review_already_submitted(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="Alice", domain=ExpertDomain.SECURITY))
        review = ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY)
        self.engine.assign_review(review)
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, [], 9.0, 1.0)
        
        with self.assertRaises(ValueError):
            self.engine.submit_review("r1", ValidationOutcome.APPROVED, [], 9.0, 1.0)

    def test_submit_review_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.submit_review("nonexistent", ValidationOutcome.APPROVED, [], 9.0, 1.0)

    def test_get_consensus_not_enough_reviews(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="Alice", domain=ExpertDomain.SECURITY))
        review = ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY)
        self.engine.assign_review(review)
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, [], 9.0, 1.0)
        
        consensus = self.engine.get_consensus("s1")
        self.assertFalse(consensus["consensus_reached"])
        self.assertEqual(consensus["review_count"], 1)

    def test_get_consensus_success(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY))
        self.engine.register_validator(ExpertValidator(validator_id="v2", name="B", domain=ExpertDomain.SECURITY))
        self.engine.register_validator(ExpertValidator(validator_id="v3", name="C", domain=ExpertDomain.SECURITY))
        
        self.engine.assign_review(ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY))
        self.engine.assign_review(ExpertReview(review_id="r2", validator_id="v2", subject_id="s1", domain=ExpertDomain.SECURITY))
        self.engine.assign_review(ExpertReview(review_id="r3", validator_id="v3", subject_id="s1", domain=ExpertDomain.SECURITY))
        
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, ["F1"], 8.0, 1.0)
        self.engine.submit_review("r2", ValidationOutcome.APPROVED, ["F2"], 9.0, 1.0)
        self.engine.submit_review("r3", ValidationOutcome.REJECTED, ["F3"], 4.0, 1.0)
        
        consensus = self.engine.get_consensus("s1")
        self.assertTrue(consensus["consensus_reached"])
        self.assertEqual(consensus["majority_outcome"], ValidationOutcome.APPROVED)
        self.assertEqual(consensus["average_score"], 7.0)
        self.assertEqual(consensus["total_findings"], 3)
        self.assertIn("F1", consensus["all_findings"])

    def test_get_available_validators_no_exclude(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY))
        self.engine.register_validator(ExpertValidator(validator_id="v2", name="B", domain=ExpertDomain.PERFORMANCE))
        
        av = self.engine.get_available_validators(ExpertDomain.SECURITY)
        self.assertEqual(len(av), 1)
        self.assertEqual(av[0].validator_id, "v1")

    def test_get_available_validators_exclude_conflict(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY, organization="OrgA"))
        self.engine.register_validator(ExpertValidator(validator_id="v2", name="B", domain=ExpertDomain.SECURITY, organization="OrgB"))
        
        av = self.engine.get_available_validators(ExpertDomain.SECURITY, exclude_orgs=["OrgA"])
        self.assertEqual(len(av), 1)
        self.assertEqual(av[0].validator_id, "v2")

    def test_get_available_validators_inactive(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY, active=False))
        av = self.engine.get_available_validators(ExpertDomain.SECURITY)
        self.assertEqual(len(av), 0)

    def test_get_validator_stats_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_validator_stats("nonexistent")

    def test_get_pending_reviews(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY))
        self.engine.assign_review(ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY))
        self.engine.assign_review(ExpertReview(review_id="r2", validator_id="v1", subject_id="s2", domain=ExpertDomain.SECURITY))
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, [], 9.0, 1.0)
        
        pending = self.engine.get_pending_reviews()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].review_id, "r2")

    def test_get_subject_status(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY))
        self.engine.assign_review(ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY))
        
        status = self.engine.get_subject_status("s1")
        self.assertEqual(status["total_reviews"], 1)
        self.assertEqual(status["pending_reviews"], 1)
        self.assertFalse(status["consensus"]["consensus_reached"])

    def test_get_validation_report_empty(self):
        report = self.engine.get_validation_report()
        self.assertEqual(report["total_reviews"], 0)
        self.assertEqual(report["completed_reviews"], 0)
        self.assertEqual(report["average_score"], 0.0)

    def test_get_validation_report_populated(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY))
        self.engine.assign_review(ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY))
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, [], 10.0, 1.0)
        
        report = self.engine.get_validation_report()
        self.assertEqual(report["total_reviews"], 1)
        self.assertEqual(report["completed_reviews"], 1)
        self.assertEqual(report["average_score"], 10.0)
        self.assertIn(ExpertDomain.SECURITY, report["by_domain"])
        self.assertIn(ValidationOutcome.APPROVED, report["by_outcome"])

    def test_require_independent_validation_met(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY))
        self.engine.register_validator(ExpertValidator(validator_id="v2", name="B", domain=ExpertDomain.SECURITY))
        
        self.engine.assign_review(ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY, independent=True))
        self.engine.assign_review(ExpertReview(review_id="r2", validator_id="v2", subject_id="s1", domain=ExpertDomain.SECURITY, independent=True))
        
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, [], 9.0, 1.0)
        self.engine.submit_review("r2", ValidationOutcome.APPROVED, [], 9.0, 1.0)
        
        req = self.engine.require_independent_validation("s1", 2, ExpertDomain.SECURITY)
        self.assertTrue(req["requirement_met"])
        self.assertEqual(req["independent_reviews_count"], 2)

    def test_require_independent_validation_not_met_due_to_independence(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY))
        self.engine.register_validator(ExpertValidator(validator_id="v2", name="B", domain=ExpertDomain.SECURITY))
        
        self.engine.assign_review(ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY, independent=True))
        self.engine.assign_review(ExpertReview(review_id="r2", validator_id="v2", subject_id="s1", domain=ExpertDomain.SECURITY, independent=False))
        
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, [], 9.0, 1.0)
        self.engine.submit_review("r2", ValidationOutcome.APPROVED, [], 9.0, 1.0)
        
        req = self.engine.require_independent_validation("s1", 2, ExpertDomain.SECURITY)
        self.assertFalse(req["requirement_met"])
        self.assertEqual(req["independent_reviews_count"], 1)

    def test_require_independent_validation_not_met_due_to_pending(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY))
        self.engine.assign_review(ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY, independent=True))
        
        req = self.engine.require_independent_validation("s1", 1, ExpertDomain.SECURITY)
        self.assertFalse(req["requirement_met"])
        self.assertEqual(req["independent_reviews_count"], 0)

    def test_require_independent_validation_wrong_domain(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY))
        self.engine.assign_review(ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY, independent=True))
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, [], 9.0, 1.0)
        
        req = self.engine.require_independent_validation("s1", 1, ExpertDomain.PERFORMANCE)
        self.assertFalse(req["requirement_met"])

    def test_submit_review_approval_rate_calculation(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="Alice", domain=ExpertDomain.SECURITY))
        for i in range(4):
            review = ExpertReview(review_id=f"r{i}", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY)
            self.engine.assign_review(review)
        
        self.engine.submit_review("r0", ValidationOutcome.APPROVED, [], 9.0, 1.0)
        self.engine.submit_review("r1", ValidationOutcome.CONDITIONALLY_APPROVED, [], 8.0, 1.0)
        self.engine.submit_review("r2", ValidationOutcome.REJECTED, [], 4.0, 1.0)
        self.engine.submit_review("r3", ValidationOutcome.NEEDS_REWORK, [], 5.0, 1.0)
        
        stats = self.engine.get_validator_stats("v1")
        # 2 approved / 4 total completed = 0.5
        self.assertEqual(stats["approval_rate"], 0.5)

    def test_get_consensus_even_split(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY))
        self.engine.register_validator(ExpertValidator(validator_id="v2", name="B", domain=ExpertDomain.SECURITY))
        
        self.engine.assign_review(ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY))
        self.engine.assign_review(ExpertReview(review_id="r2", validator_id="v2", subject_id="s1", domain=ExpertDomain.SECURITY))
        
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, [], 9.0, 1.0)
        self.engine.submit_review("r2", ValidationOutcome.REJECTED, [], 3.0, 1.0)
        
        consensus = self.engine.get_consensus("s1")
        self.assertTrue(consensus["consensus_reached"])
        self.assertIn(consensus["majority_outcome"], [ValidationOutcome.APPROVED, ValidationOutcome.REJECTED])

    def test_get_available_validators_multiple_excludes(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY, conflicts_of_interest=["OrgA"]))
        self.engine.register_validator(ExpertValidator(validator_id="v2", name="B", domain=ExpertDomain.SECURITY, conflicts_of_interest=["OrgB"]))
        self.engine.register_validator(ExpertValidator(validator_id="v3", name="C", domain=ExpertDomain.SECURITY))
        
        av = self.engine.get_available_validators(ExpertDomain.SECURITY, exclude_orgs=["OrgA", "OrgB"])
        self.assertEqual(len(av), 1)
        self.assertEqual(av[0].validator_id, "v3")

    def test_submit_review_fractional_hours(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY))
        self.engine.assign_review(ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY))
        self.engine.assign_review(ExpertReview(review_id="r2", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY))
        
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, [], 9.0, 1.5)
        self.engine.submit_review("r2", ValidationOutcome.APPROVED, [], 9.0, 2.5)
        
        stats = self.engine.get_validator_stats("v1")
        self.assertAlmostEqual(stats["avg_review_hours"], 2.0)

    def test_get_validation_report_multiple_domains(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY))
        self.engine.register_validator(ExpertValidator(validator_id="v2", name="B", domain=ExpertDomain.PERFORMANCE))
        
        self.engine.assign_review(ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY))
        self.engine.assign_review(ExpertReview(review_id="r2", validator_id="v2", subject_id="s2", domain=ExpertDomain.PERFORMANCE))
        
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, [], 9.0, 1.0)
        self.engine.submit_review("r2", ValidationOutcome.REJECTED, [], 3.0, 1.0)
        
        report = self.engine.get_validation_report()
        self.assertEqual(report["by_domain"][ExpertDomain.SECURITY], 1)
        self.assertEqual(report["by_domain"][ExpertDomain.PERFORMANCE], 1)
        self.assertEqual(report["by_outcome"][ValidationOutcome.APPROVED], 1)
        self.assertEqual(report["by_outcome"][ValidationOutcome.REJECTED], 1)

    def test_require_independent_validation_exact_match(self):
        self.engine.register_validator(ExpertValidator(validator_id="v1", name="A", domain=ExpertDomain.SECURITY))
        self.engine.assign_review(ExpertReview(review_id="r1", validator_id="v1", subject_id="s1", domain=ExpertDomain.SECURITY, independent=True))
        self.engine.submit_review("r1", ValidationOutcome.APPROVED, [], 9.0, 1.0)
        
        req = self.engine.require_independent_validation("s1", 1, ExpertDomain.SECURITY)
        self.assertTrue(req["requirement_met"])

if __name__ == "__main__":
    unittest.main()
