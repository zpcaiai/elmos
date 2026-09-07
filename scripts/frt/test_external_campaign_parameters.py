#!/usr/bin/env python3
"""Tests for exact external campaign authorization parameters."""

from __future__ import annotations

import copy
import unittest

from external_campaign_parameters import (
    CHECK_IDS,
    expected_case_contract,
    test_parameters,
    validate_campaign_parameters,
)


class ExternalCampaignParameterTests(unittest.TestCase):
    def test_every_external_check_accepts_only_its_exact_typed_fixture(self) -> None:
        for check_id in CHECK_IDS:
            with self.subTest(check_id=check_id):
                parameters = test_parameters(check_id)
                expected_cases, expected_adapters = expected_case_contract(check_id)
                self.assertEqual(parameters["case_ids"], expected_cases)
                self.assertEqual(parameters["adapter_ids"], expected_adapters)
                self.assertEqual(validate_campaign_parameters(check_id, parameters), [])

    def test_unknown_command_and_scope_fields_fail_closed_for_every_check(self) -> None:
        for check_id in CHECK_IDS:
            with self.subTest(check_id=check_id):
                parameters = test_parameters(check_id)
                parameters["command"] = "./repository-selected-command"
                parameters["authorization_scope"]["permission_override"] = "allow-all"
                failures = validate_campaign_parameters(check_id, parameters)
                self.assertTrue(any("fields must be exact" in failure for failure in failures))

    def test_plan_case_and_adapter_drift_fail_closed_for_every_check(self) -> None:
        for check_id in CHECK_IDS:
            with self.subTest(check_id=check_id):
                parameters = test_parameters(check_id)
                parameters["qualification_plan_sha256"] = "sha256:" + "0" * 64
                parameters["case_ids"] = parameters["case_ids"][:-1]
                parameters["adapter_ids"] = [*parameters["adapter_ids"], "UNDECLARED_ADAPTER"]
                failures = validate_campaign_parameters(check_id, parameters)
                self.assertTrue(any("does not bind the current plan bytes" in failure for failure in failures))
                self.assertTrue(any("case_ids must exactly equal" in failure for failure in failures))
                self.assertTrue(any("adapter_ids must exactly equal" in failure for failure in failures))

    def test_high_risk_minimums_and_human_authority_cannot_be_weakened(self) -> None:
        mutations = {
            "device_matrix": ("quality_profile_ids", []),
            "independent_holdout": ("case_count", 0),
            "formal_proof": ("bounds", {}),
            "performance": ("samples_per_workload", 1),
            "chaos_dr": ("scenario_count", 0),
            "penetration_test": ("retest_required", False),
            "production_observation": ("read_only", False),
            "customer_acceptance": ("decision_authority", "AGENT"),
        }
        for check_id, (field, weakened) in mutations.items():
            with self.subTest(check_id=check_id):
                parameters = copy.deepcopy(test_parameters(check_id))
                parameters[field] = weakened
                self.assertNotEqual(validate_campaign_parameters(check_id, parameters), [])


if __name__ == "__main__":
    unittest.main()
