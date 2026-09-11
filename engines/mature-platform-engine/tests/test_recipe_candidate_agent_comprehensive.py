"""Comprehensive test suite for RecipeCandidateAgentEngine (Batch 42 - Skill 1431)."""

import unittest

from elmos_mature_platform.recipe_candidate_agent_engine import (
    RecipeCandidateAgentEngine,
)
from elmos_mature_platform.types import (
    RecipeCandidateStatus,
    SynthesizedRecipeCandidate,
)


class TestRecipeCandidateAgentComprehensive(unittest.TestCase):
    """Rigorous tests covering pattern synthesis, occurrence mining, confidence scoring, approval, and rejection."""

    def setUp(self) -> None:
        self.engine = RecipeCandidateAgentEngine()

    def test_register_candidate_success(self) -> None:
        cand = SynthesizedRecipeCandidate(
            candidate_id="",
            name="Spring MVC @RequestMapping to @GetMapping",
            source_pattern='@RequestMapping(method = RequestMethod.GET, value = "$PATH")',
            target_transformation='@GetMapping("$PATH")',
        )
        cid = self.engine.register_candidate(cand)
        self.assertTrue(cid.startswith("rcand-"))

        retrieved = self.engine.get_candidate(cid)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.status, RecipeCandidateStatus.DISCOVERED)
        self.assertEqual(retrieved.confidence_score, 0.5)

    def test_register_candidate_missing_fields(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.register_candidate(
                SynthesizedRecipeCandidate(
                    candidate_id="",
                    name="",
                    source_pattern="",
                    target_transformation="",
                )
            )

    def test_record_pattern_occurrence_and_confidence_growth(self) -> None:
        cid = self.engine.register_candidate(
            SynthesizedRecipeCandidate(
                candidate_id="cand-01",
                name="Var to Explicit Type",
                source_pattern="var x = ...",
                target_transformation="Type x = ...",
            )
        )

        for _ in range(3):
            self.engine.record_pattern_occurrence(cid)

        cand = self.engine.get_candidate(cid)
        self.assertEqual(cand.occurrence_count, 4)
        self.assertAlmostEqual(cand.confidence_score, 0.7)
        self.assertEqual(cand.status, RecipeCandidateStatus.DISCOVERED)

        # 5th occurrence transitions status to SYNTHESIZED
        self.engine.record_pattern_occurrence(cid)
        self.assertEqual(cand.status, RecipeCandidateStatus.SYNTHESIZED)

    def test_approve_candidate(self) -> None:
        cid = self.engine.register_candidate(
            SynthesizedRecipeCandidate(
                candidate_id="cand-02",
                name="Replace StringBuffer with StringBuilder",
                source_pattern="new StringBuffer()",
                target_transformation="new StringBuilder()",
            )
        )

        with self.assertRaises(ValueError):
            self.engine.approve_candidate(cid, approver="")

        cand = self.engine.approve_candidate(cid, approver="lead-dev@company.com")
        self.assertEqual(cand.status, RecipeCandidateStatus.APPROVED)
        self.assertEqual(cand.approver, "lead-dev@company.com")

    def test_reject_candidate(self) -> None:
        cid = self.engine.register_candidate(
            SynthesizedRecipeCandidate(
                candidate_id="cand-03",
                name="Dangerous Unchecked Cast",
                source_pattern="(Target) obj",
                target_transformation="obj",
            )
        )

        cand = self.engine.reject_candidate(cid, reason="Causes ClassCastException in downstream services")
        self.assertEqual(cand.status, RecipeCandidateStatus.REJECTED)

    def test_filter_by_status_and_report(self) -> None:
        c1 = self.engine.register_candidate(
            SynthesizedRecipeCandidate(candidate_id="c1", name="n1", source_pattern="p1", target_transformation="t1")
        )
        c2 = self.engine.register_candidate(
            SynthesizedRecipeCandidate(candidate_id="c2", name="n2", source_pattern="p2", target_transformation="t2")
        )
        self.engine.approve_candidate(c1, "approver-1")

        approved = self.engine.get_candidates_by_status(RecipeCandidateStatus.APPROVED)
        self.assertEqual(len(approved), 1)

        rep = self.engine.get_recipe_candidate_report()
        self.assertEqual(rep["total_candidates"], 2)
        self.assertIn("approved", rep["by_status"])
        self.assertIn("discovered", rep["by_status"])


if __name__ == "__main__":
    unittest.main()
