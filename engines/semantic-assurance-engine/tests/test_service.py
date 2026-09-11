"""Service layer unit tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from elmos_semantic_assurance.service import SemanticAssuranceService, get_assurance_status
from elmos_semantic_assurance.registry import EXPECTED_BATCH_COUNTS

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from fixtures import make_identity, make_request_document


class TestService(unittest.TestCase):
    def setUp(self) -> None:
        self.service = SemanticAssuranceService()

    def test_status(self) -> None:
        st = self.service.status()
        self.assertEqual(st["registeredSkills"], 132)
        self.assertEqual(st["exactHandlers"], 132)
        self.assertEqual(st["implementationState"], "RUNTIME_CODE_COMPLETE")
        self.assertEqual(st["certificationStatus"], "NOT_CERTIFIED")
        self.assertEqual(st["externalEvidenceStatus"], "NOT_RUN")

    def test_get_assurance_status_helper(self) -> None:
        st = get_assurance_status()
        self.assertEqual(st["registeredSkills"], 132)

    def test_catalog_all_and_filtered(self) -> None:
        all_skills = self.service.catalog()
        self.assertEqual(len(all_skills), 132)

        for batch, expected_count in EXPECTED_BATCH_COUNTS.items():
            with self.subTest(batch=batch):
                batch_skills = self.service.catalog(batch=batch)
                self.assertEqual(len(batch_skills), expected_count)
                self.assertTrue(all(item["batch"] == batch for item in batch_skills))

    def test_catalog_invalid_batch_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported batch"):
            self.service.catalog(batch="INVALID")

    def test_prepare_route_assurance_campaign(self) -> None:
        plan = self.service.prepare_route_assurance_campaign(
            source_technology="java",
            target_technology="csharp",
            source_bytes=b"source",
            target_bytes=b"target",
        )
        self.assertEqual(plan["routeId"], "java-to-csharp")
        self.assertEqual(plan["plannedSkills"], 132)
        self.assertEqual(plan["executionStatus"], "NOT_RUN")
        self.assertEqual(plan["certificationStatus"], "NOT_CERTIFIED")
        self.assertEqual(len(plan["batchPlan"]), 9)

    def test_run_route_assurance_campaign_fails_closed(self) -> None:
        res = self.service.run_route_assurance_campaign(
            source_lang="java",
            target_lang="csharp",
            source_code="class A {}",
            target_code="class B {}",
        )
        self.assertEqual(res["readiness"], "BLOCKED")
        self.assertIn("EXACT_SCOPE_REQUIRED", res["blockers"])
        self.assertEqual(res["certificationStatus"], "NOT_CERTIFIED")


if __name__ == "__main__":
    unittest.main()
