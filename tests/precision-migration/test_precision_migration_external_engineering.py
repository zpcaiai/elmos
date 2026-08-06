from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from scripts.precision_migration.external import scaffold
from scripts.precision_migration.runtime import canonical_digest
from tooling.generate_precision_migration_external_engineering_cases import build as build_cases


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "verification-packs" / "precision-migration-b01-44-runtime"
CASES = PACK / "external-engineering-qualification" / "cases.json"
RESULTS = PACK / "external-engineering-qualification" / "results.json"
CURRENT = PACK / "external-readiness" / "current.json"
DOMAIN_RESULTS = PACK / "domain-qualification" / "results.json"


class PrecisionMigrationExternalEngineeringTest(unittest.TestCase):
    def test_generated_557_by_5_case_inventory_is_exact(self) -> None:
        checked_in = json.loads(CASES.read_text(encoding="utf-8"))
        self.assertEqual(build_cases(), checked_in)
        self.assertEqual(557, checked_in["skill_count"])
        self.assertEqual(2785, checked_in["case_count"])
        self.assertFalse(checked_in["production_eligible"])
        self.assertEqual("NONE", checked_in["external_stage_effect"])
        counts = Counter(item["skill"] for item in checked_in["cases"])
        self.assertEqual({5}, set(counts.values()))
        for case in checked_in["cases"]:
            body = {key: value for key, value in case.items() if key != "case_digest"}
            self.assertEqual(canonical_digest(body), case["case_digest"])

    def test_all_2785_results_bind_fresh_handler_executions(self) -> None:
        result = json.loads(RESULTS.read_text(encoding="utf-8"))
        self.assertEqual("PASSED_LOCAL_ENGINEERING_SIMULATION", result["decision"])
        self.assertEqual(2785, result["actual_handler_invocation_count"])
        self.assertTrue(result["all_engineering_tests_passed"])
        self.assertFalse(result["production_eligible"])
        self.assertEqual(
            {"positive": 557, "negative": 557, "integration": 557, "holdout": 557, "representative": 557},
            result["test_type_summary"],
        )
        self.assertTrue(all(item["engineering_state"] == "PASS" for item in result["results"]))
        self.assertTrue(all(item["handler_invoked"] is True for item in result["results"]))
        self.assertTrue(all(item["production_eligible"] is False for item in result["results"]))
        domain = json.loads(DOMAIN_RESULTS.read_text(encoding="utf-8"))
        executed = [item for item in domain["results"] if item["test_type"] != "negative"]
        self.assertEqual(2144, len(executed))
        self.assertTrue(all("artifact_digest" not in item["evidence"] for item in executed))
        self.assertTrue(all(item["evidence"]["artifact_verified_in_fresh_execution"] for item in executed))
        self.assertTrue(all(item["evidence"]["artifact_contract_digest"].startswith("sha256:") for item in executed))

    def test_engineering_execution_cannot_promote_external_readiness(self) -> None:
        current = json.loads(CURRENT.read_text(encoding="utf-8"))
        self.assertEqual(scaffold(), current)
        result = json.loads(RESULTS.read_text(encoding="utf-8"))
        self.assertEqual("NOT_READY", result["real_external_state"]["decision"])
        self.assertEqual(0, result["real_external_state"]["verified_skill_count"])
        self.assertFalse(result["real_external_state"]["production_operation_authorized"])
        self.assertEqual("NOT_CERTIFIED", result["real_external_state"]["production_certification"])
        self.assertEqual({"NOT_RUN"}, set(result["real_external_state"]["stage_states"].values()))


if __name__ == "__main__":
    unittest.main()
