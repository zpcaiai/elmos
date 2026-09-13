"""Comprehensive test suite for MatureReleaseReadinessEngine (B45 - Skill 1491)."""

import unittest

from elmos_mature_platform.mature_release_readiness_engine import (
    MatureReleaseReadinessEngine,
)
from elmos_mature_platform.types import (
    MatureReleaseReadinessRecord,
    PillarEvaluation,
    PillarStatus,
    ReleasePillar,
)


class TestMatureReleaseReadinessComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = MatureReleaseReadinessEngine()

    def test_create_readiness_review_initial_state(self):
        review = self.engine.create_readiness_review("v5.0.0-GA", "release-lead@company.org")
        self.assertTrue(review.review_id.startswith("rrr-"))
        self.assertEqual(review.target_release, "v5.0.0-GA")
        self.assertEqual(len(review.pillars), len(ReleasePillar))
        self.assertFalse(review.ready_for_general_availability)
        self.assertEqual(review.overall_score, 0.0)

    def test_record_pillar_evaluation_updates_overall_score(self):
        review = self.engine.create_readiness_review("v5.0.0-GA", "lead")
        eval_fn = PillarEvaluation(
            pillar=ReleasePillar.FUNCTIONAL,
            status=PillarStatus.PASSED,
            score=95.0,
            lead_owner="qa-dir",
            evidence_hashes=["hash1", "hash2"],
        )
        updated = self.engine.record_pillar_evaluation(review.review_id, eval_fn)
        self.assertEqual(updated.pillars[ReleasePillar.FUNCTIONAL.value].status, PillarStatus.PASSED)
        self.assertGreater(updated.overall_score, 0.0)

    def test_evaluate_ga_rejected_when_blockers_or_unpassed_pillars(self):
        review = self.engine.create_readiness_review("v5.0.0-GA", "lead")
        # 6 pillars passed, but security has a blocker
        for p in ReleasePillar:
            if p == ReleasePillar.SECURITY:
                self.engine.record_pillar_evaluation(
                    review.review_id,
                    PillarEvaluation(pillar=p, status=PillarStatus.BLOCKED, score=60.0, blocking_issues=["Open High CVE-2026-001"]),
                )
            else:
                self.engine.record_pillar_evaluation(
                    review.review_id,
                    PillarEvaluation(pillar=p, status=PillarStatus.PASSED, score=95.0),
                )

        res = self.engine.evaluate_general_availability(review.review_id, "VP Engineering")
        self.assertFalse(res.ready_for_general_availability)
        self.assertEqual(res.sign_off_director, "")

    def test_waive_pillar_blocker_enables_ga_approval(self):
        review = self.engine.create_readiness_review("v5.0.0-GA", "lead")
        # Pass 6 pillars at 95%
        for p in ReleasePillar:
            if p == ReleasePillar.ECONOMICS:
                # Economics initially blocked due to missing telemetry feed
                self.engine.record_pillar_evaluation(
                    review.review_id,
                    PillarEvaluation(pillar=p, status=PillarStatus.BLOCKED, score=90.0, blocking_issues=["Pending finops billing stream"]),
                )
            else:
                self.engine.record_pillar_evaluation(
                    review.review_id,
                    PillarEvaluation(pillar=p, status=PillarStatus.PASSED, score=95.0),
                )

        # Before waiver: GA false
        self.assertFalse(self.engine.evaluate_general_availability(review.review_id, "CPO").ready_for_general_availability)

        # Formal signed waiver
        self.engine.waive_pillar_blocker(
            review_id=review.review_id,
            pillar=ReleasePillar.ECONOMICS,
            waiver_reason="Finops stream deferred to sprint 42 with VP Finance sign-off",
            approved_by="VP Finance",
        )

        # After waiver: GA true
        ga_approved = self.engine.evaluate_general_availability(review.review_id, "CPO")
        self.assertTrue(ga_approved.ready_for_general_availability)
        self.assertEqual(ga_approved.sign_off_director, "CPO")

    def test_get_unresolved_blockers(self):
        review = self.engine.create_readiness_review("v5.0.0", "lead")
        self.engine.record_pillar_evaluation(
            review.review_id,
            PillarEvaluation(
                pillar=ReleasePillar.PERFORMANCE,
                status=PillarStatus.BLOCKED,
                blocking_issues=["P99 latency > 200ms on 10k concurrent sessions"],
                lead_owner="perf-lead",
            ),
        )
        blockers = self.engine.get_unresolved_blockers(review.review_id)
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0]["pillar"], ReleasePillar.PERFORMANCE.value)
        self.assertIn("P99 latency", blockers[0]["blocker"])

    def test_get_readiness_scorecard(self):
        review = self.engine.create_readiness_review("v5.0.0", "lead")
        for p in ReleasePillar:
            self.engine.record_pillar_evaluation(
                review.review_id,
                PillarEvaluation(pillar=p, status=PillarStatus.PASSED, score=92.0),
            )
        self.engine.evaluate_general_availability(review.review_id, "CTO")

        card = self.engine.get_readiness_scorecard(review.review_id)
        self.assertEqual(card["target_release"], "v5.0.0")
        self.assertTrue(card["ready_for_general_availability"])
        self.assertEqual(card["sign_off_director"], "CTO")
        self.assertEqual(len(card["pillars"]), 7)


if __name__ == "__main__":
    unittest.main()
