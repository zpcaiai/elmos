#!/usr/bin/env python3
"""Integrity tests for the generated FRT external qualification plan."""

from __future__ import annotations

import copy
import unittest

from external_qualification import (
    ADAPTER_HANDLERS,
    CASE_DEFINITIONS,
    CASE_KEYS,
    PLAN_ROOT_KEYS,
    PREFLIGHT_CASE_KEYS,
    PREFLIGHT_ROOT_KEYS,
    PROFILE,
    build_preflight,
    build_local_execution,
    build_plan,
    case_blockers,
    load_json,
    validate_plan,
    validate_local_execution,
    validate_preflight,
)


class ExternalQualificationPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_plan()

    def test_generates_all_fifteen_exact_cases_and_all_nine_gate_checks(self) -> None:
        self.assertEqual(set(self.plan), PLAN_ROOT_KEYS)
        self.assertEqual(self.plan["case_count"], 15)
        self.assertEqual(len(self.plan["cases"]), 15)
        self.assertEqual(
            [case["case_id"] for case in self.plan["cases"]],
            [case["case_id"] for case in CASE_DEFINITIONS],
        )
        self.assertEqual(len({case["adapter_id"] for case in self.plan["cases"]}), 15)
        self.assertEqual(
            {case["external_check_id"] for case in self.plan["cases"]},
            set(load_json(PROFILE)["checks"]),
        )
        self.assertEqual(validate_plan(self.plan), [])

    def test_every_case_binds_the_authoritative_profile_contract(self) -> None:
        profile = load_json(PROFILE)
        for case in self.plan["cases"]:
            with self.subTest(case_id=case["case_id"]):
                self.assertEqual(set(case), CASE_KEYS)
                spec = profile["checks"][case["external_check_id"]]
                self.assertEqual(case["required_evidence_roles"], spec["required_evidence_roles"])
                self.assertEqual(case["required_metrics"], spec["required_metrics"])
                self.assertEqual(case["required_claims"], spec["required_claims"])
                self.assertEqual(case["external_state"], "NOT_RUN")
                self.assertIs(case["production_operation_authorized"], False)
                self.assertEqual(case["certification"], "NOT_CERTIFIED")

    def test_plan_contains_no_repository_selected_command_or_success_override(self) -> None:
        forbidden = {"command", "shell", "executable", "external_state_override", "certified"}

        def visit(value) -> None:
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(self.plan)

    def test_tampering_external_state_or_production_authority_fails_closed(self) -> None:
        tampered = copy.deepcopy(self.plan)
        tampered["cases"][0]["external_state"] = "PASSED"
        tampered["cases"][1]["production_operation_authorized"] = True
        failures = validate_plan(tampered)
        self.assertTrue(any("external state must remain NOT_RUN" in item for item in failures))
        self.assertTrue(any("may not authorize a production operation" in item for item in failures))

    def test_missing_browser_hvigor_and_external_authority_are_explicit_blockers(self) -> None:
        tools = {
            "browser_runtimes": {"runtimes": {
                "firefox": {"launch_available": False},
                "webkit": {"launch_available": False},
            }},
            "arkui_hvigor": {"available": False},
            "approved_visual_baselines": {"count": 0},
            "assistive_technology": {"session_executed": False},
            "physical_devices": {"manual_acceptance_executed": False},
            "customer_repositories": {"root_configured": False},
            "independent_holdout": {"non_placeholder_file_count": 0},
            "external_runner": {"configured": False},
            "production": {"observation_authorized": False, "customer_acceptance_executed": False},
        }
        by_adapter = {case["adapter_id"]: case for case in self.plan["cases"]}
        self.assertIn(
            "EXACT_FIREFOX_RUNTIME_UNAVAILABLE",
            case_blockers(by_adapter["PLAYWRIGHT_FIREFOX_DESKTOP"], tools),
        )
        self.assertIn(
            "EXACT_WEBKIT_RUNTIME_UNAVAILABLE",
            case_blockers(by_adapter["PLAYWRIGHT_WEBKIT_DESKTOP"], tools),
        )
        self.assertIn(
            "DEVECO_HVIGOR_TOOLCHAIN_UNAVAILABLE",
            case_blockers(by_adapter["ARKUI_HVIGOR_BUILD"], tools),
        )
        self.assertIn(
            "SIGNED_EXTERNAL_AUTHORIZATION_AND_INDEPENDENT_EXECUTION_REQUIRED",
            case_blockers(by_adapter["INDEPENDENT_CUSTOMER_ACCEPTANCE"], tools),
        )
        tools["browser_runtimes"]["runtimes"]["firefox"] = {
            "launch_available": True,
            "detected_version": "150.0",
        }
        tools["browser_runtimes"]["runtimes"]["webkit"] = {
            "launch_available": True,
            "detected_version": "26.4",
        }
        self.assertIn(
            "EXACT_FIREFOX_VERSION_MISMATCH",
            case_blockers(by_adapter["PLAYWRIGHT_FIREFOX_DESKTOP"], tools),
        )
        self.assertIn(
            "EXACT_WEBKIT_VERSION_MISMATCH",
            case_blockers(by_adapter["PLAYWRIGHT_WEBKIT_DESKTOP"], tools),
        )

    def test_generated_preflight_is_exact_and_keeps_every_case_not_run(self) -> None:
        preflight = build_preflight(self.plan)
        self.assertEqual(set(preflight), PREFLIGHT_ROOT_KEYS)
        self.assertEqual(validate_preflight(preflight, self.plan), [])
        self.assertEqual(preflight["external_state_counts"], {"NOT_RUN": 15})
        self.assertIs(preflight["production_operation_authorized"], False)
        self.assertEqual(preflight["production_certification"], "NOT_CERTIFIED")
        for case in preflight["cases"]:
            self.assertEqual(set(case), PREFLIGHT_CASE_KEYS)
            self.assertEqual(case["external_state"], "NOT_RUN")
            self.assertIs(case["production_operation_authorized"], False)
            self.assertEqual(case["certification"], "NOT_CERTIFIED")

    def test_preflight_tampering_is_rejected(self) -> None:
        preflight = build_preflight(self.plan)
        preflight["cases"][0]["blockers"] = []
        preflight["cases"][0]["harness_state"] = "BLOCKED_PRECONDITION"
        preflight["cases"][1]["external_state"] = "PASSED"
        preflight["tools"]["production"]["observation_authorized"] = True
        preflight["tools"]["external_runner"]["command"] = "./untrusted"
        preflight["production_operation_authorized"] = True
        failures = validate_preflight(preflight, self.plan)
        self.assertTrue(any("harness state does not match blockers" in item for item in failures))
        self.assertTrue(any("external state must remain NOT_RUN" in item for item in failures))
        self.assertTrue(any("external_runner preflight fields are not exact" in item for item in failures))
        self.assertTrue(any("may not claim production or customer authority" in item for item in failures))
        self.assertTrue(any("may not authorize production operations" in item for item in failures))

    def test_all_fifteen_adapters_execute_their_local_code_contract(self) -> None:
        preflight = build_preflight(self.plan)
        execution = build_local_execution(self.plan, preflight)
        self.assertEqual(set(ADAPTER_HANDLERS), {case["adapter_id"] for case in self.plan["cases"]})
        self.assertEqual(validate_local_execution(execution, self.plan, preflight), [])
        self.assertEqual(execution["code_contract_counts"], {"PASSED_LOCAL_TOOLING": 15})
        self.assertEqual(execution["local_execution_counts"]["REQUIRES_EXTERNAL_AUTHORITY"], 11)
        self.assertEqual(
            execution["local_execution_counts"].get("BLOCKED_TOOLCHAIN", 0)
            + execution["local_execution_counts"].get("READY_FOR_LOCAL_EXECUTION", 0),
            4,
        )
        self.assertEqual(execution["external_state_counts"], {"NOT_RUN": 15})

    def test_local_execution_cannot_promote_external_or_production_state(self) -> None:
        preflight = build_preflight(self.plan)
        execution = build_local_execution(self.plan, preflight)
        execution["cases"][0]["external_state"] = "PASSED"
        execution["cases"][1]["production_operation_authorized"] = True
        execution["production_certification"] = "CERTIFIED"
        failures = validate_local_execution(execution, self.plan, preflight)
        self.assertTrue(any("external state must remain NOT_RUN" in item for item in failures))
        self.assertTrue(any("may not authorize production" in item for item in failures))
        self.assertTrue(any("may not certify production" in item for item in failures))

    def test_local_execution_observations_are_recomputed_and_tamper_evident(self) -> None:
        plan = build_plan()
        preflight = build_preflight(plan)
        execution = build_local_execution(plan, preflight)
        execution["cases"][0]["observations"][0]["state"] = "PASSED"
        execution["cases"][0]["observations"][0]["detail"] = "fabricated launch"
        failures = validate_local_execution(execution, plan, preflight)
        self.assertTrue(
            any("observations differ from adapter output" in item for item in failures)
        )


if __name__ == "__main__":
    unittest.main()
