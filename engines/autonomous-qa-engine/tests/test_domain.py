from __future__ import annotations

import unittest

from elmos_autonomous_qa import domain
from elmos_autonomous_qa.contracts import ContractError, digest_json


class DomainPolicyTest(unittest.TestCase):
    def test_snapshot_digest_mismatch_is_rejected(self) -> None:
        with self.assertRaises(ContractError):
            domain.ingest_snapshot(
                {
                    "sources": [
                        {
                            "source_id": "source-1",
                            "uri": "requirements.md",
                            "kind": "requirement",
                            "required": True,
                            "content": "actual",
                            "content_hash": "0" * 64,
                        }
                    ]
                }
            )

        digest_only = domain.ingest_snapshot(
            {
                "sources": [
                    {
                        "source_id": "source-1",
                        "uri": "requirements.md",
                        "kind": "requirement",
                        "required": True,
                        "content_hash": "a" * 64,
                    }
                ]
            }
        )
        self.assertEqual("PARTIAL", digest_only["state"])
        self.assertIn(
            "source-1:CONTENT_BYTES_NOT_VERIFIED",
            digest_only["outputs"]["blockers"],
        )

    def test_ambiguous_required_requirement_stays_visible(self) -> None:
        result = domain.normalize_requirements(
            {
                "requirements": [
                    {
                        "requirement_id": "REQ-1",
                        "title": "Fast",
                        "statement": "The system is fast.",
                        "priority": "P0",
                        "required": True,
                        "source_refs": ["requirements.md:1"],
                        "acceptance_criteria": [],
                        "ambiguities": ["fast is not quantified"],
                        "status": "ambiguous",
                    }
                ]
            }
        )
        self.assertEqual(result["state"], "PARTIAL")
        self.assertEqual(result["outputs"]["blocking_requirement_ids"], ["REQ-1"])

    def test_production_data_and_environment_fail_closed(self) -> None:
        data = domain.plan_test_data(
            {
                "datasets": [
                    {
                        "dataset_id": "data-1",
                        "source": "Production",
                        "classification": "restricted",
                        "masked": True,
                    }
                ]
            }
        )
        self.assertEqual(data["state"], "BLOCKED")
        environment = domain.plan_environment({"profile": "production", "resources": ["postgres"]})
        self.assertEqual(environment["state"], "BLOCKED")
        for profile in ("production/us", "prod east"):
            with self.subTest(profile=profile):
                self.assertEqual(
                    "BLOCKED",
                    domain.plan_environment(
                        {"profile": profile, "resources": ["postgres"]}
                    )["state"],
                )

    def test_test_dsl_rejects_embedded_commands_and_materialization_traversal(self) -> None:
        case = {
            "test_case_id": "TC-1",
            "title": "adds two values",
            "test_type": "functional",
            "priority": "P0",
            "required": True,
            "requirement_refs": ["REQ-1"],
            "preconditions": [],
            "steps": [
                {
                    "step_id": "step-1",
                    "action": "invoke",
                    "input": {"left": 1, "right": 2},
                    "side_effect": False,
                }
            ],
            "oracles": [
                {
                    "oracle_id": "oracle-1",
                    "kind": "value",
                    "assertion": "result equals 3",
                }
            ],
            "evidence_requirements": ["structured-result"],
            "cleanup": [],
            "executor": {
                "adapter_key": "python",
                "capability": "unit",
                "parameters": {},
            },
        }
        valid = domain.validate_test_dsl({"test_cases": [case]})
        self.assertEqual("PARTIAL", valid["state"])
        self.assertEqual("TEST_DSL_VALIDATED_ADAPTER_UNQUALIFIED", valid["code"])
        executor = valid["outputs"]["test_cases"][0]["executor"]
        self.assertFalse(executor["caller_qualification_accepted"])
        self.assertEqual("NOT_RUN", executor["trusted_probe_receipt"])
        self.assertIn("command_plan_proposal", executor)

        caller_qualification = {
            **case,
            "executor": {**case["executor"], "qualification": {"detected": True}},
        }
        with self.assertRaises(ContractError):
            domain.validate_test_dsl({"test_cases": [caller_qualification]})

        embedded = dict(case)
        embedded["executor"] = {**case["executor"], "command": ["sh", "-c", "unsafe"]}
        with self.assertRaises(ContractError):
            domain.validate_test_dsl({"test_cases": [embedded]})

        trivial = {**case, "oracles": [{"oracle_id": "oracle-1", "kind": "value", "assertion": "true"}]}
        with self.assertRaises(ContractError):
            domain.validate_test_dsl({"test_cases": [trivial]})

        typed_bypass = {
            **case,
            "steps": [{"step_id": "step-1", "action": "invoke", "side_effect": "true"}],
        }
        with self.assertRaises(ContractError):
            domain.validate_test_dsl({"test_cases": [typed_bypass]})
        with self.assertRaises(ContractError):
            domain.plan_materialization(
                {
                    "test_cases": [{"test_case_id": "TC-1"}],
                    "adapter_key": "python",
                    "native_layout": "../../outside",
                }
            )
        materialization = domain.plan_materialization(
            {
                "test_cases": [{"test_case_id": "TC-1"}],
                "adapter_key": "python",
                "native_layout": "tests",
            }
        )
        self.assertTrue(
            materialization["outputs"]["artifacts"][0]["path"].endswith(".py")
        )

    def test_retry_classifies_flaky_without_hiding_first_failure(self) -> None:
        result = domain.classify_flaky(
            {
                "attempts": [
                    {"attempt_id": "attempt-1", "test_case_id": "TC-1", "status": "FAILED"},
                    {"attempt_id": "attempt-2", "test_case_id": "TC-1", "status": "PASSED"},
                ]
            }
        )
        profile = result["outputs"]["profiles"][0]
        self.assertEqual(profile["status"], "FLAKY_CONFIRMED")
        self.assertEqual(profile["attempts"][0], "FAILED")
        self.assertIn("TC-1", result["outputs"]["gate_blockers"])

    def test_defect_triage_requires_explicit_unexecuted_reproduction_evidence(self) -> None:
        for failure in (
            {
                "test_case_id": "TC-1",
                "fingerprint": "failure-a",
                "root_cause_confidence": 0.5,
                "reproduction_command": [],
            },
            {
                "test_case_id": "TC-1",
                "fingerprint": "failure-a",
                "reproduction_command": ["python", "-m", "pytest"],
            },
        ):
            with self.subTest(failure=failure), self.assertRaises(ContractError):
                domain.triage_defects({"failures": [failure]})
        proposal = domain.triage_defects(
            {
                "failures": [
                    {
                        "test_case_id": "TC-1",
                        "fingerprint": "failure-a",
                        "root_cause_confidence": 0.5,
                        "reproduction_command": ["python", "-m", "pytest"],
                    }
                ]
            }
        )
        self.assertEqual("PARTIAL", proposal["state"])
        self.assertEqual("NOT_RUN", proposal["outputs"]["reproduction_execution"])

    def test_caller_replay_command_remains_an_inert_descriptor(self) -> None:
        from hashlib import sha256

        result = domain.verify_evidence(
            {
                "evidence": [
                    {
                        "evidence_id": "evidence-1",
                        "content": "proof",
                        "sha256": sha256(b"proof").hexdigest(),
                        "replay_command": ["python", "-c", "do_side_effect()"],
                    }
                ]
            }
        )
        self.assertEqual("BLOCKED", result["state"])
        evidence = result["outputs"]["evidence"][0]
        self.assertNotIn("replay_argv", evidence)
        self.assertFalse(evidence["replay_execution_authorized"])

    def test_high_risk_patch_needs_independent_approvals_and_never_executes(self) -> None:
        repair_plan = {
            "defect_id": "defect-1",
            "risk_level": "R3",
            "candidate_paths": ["src/authorization.py"],
            "approval": "MULTI_ROLE_REQUIRED",
        }
        repair_plan_digest = digest_json(repair_plan)
        result = domain.validate_patch(
            {
                "diff": (
                    "--- a/src/authorization.py\n"
                    "+++ b/src/authorization.py\n"
                    "@@ -1 +1,2 @@\n"
                    " authorize()\n"
                    "+validate_authorization()\n"
                ),
                "candidate_paths": ["src/authorization.py"],
                "semantic_tags": ["authorization"],
                "repair_plan": repair_plan,
                "repair_plan_digest": repair_plan_digest,
                "isolated_worktree": True,
                "sandboxed": True,
                "approvals": [
                    {
                        "approver_id": "owner-a",
                        "role": "code-owner",
                        "repair_plan_digest": repair_plan_digest,
                    }
                ],
            }
        )
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("R3_APPROVALS_MISSING", result["outputs"]["findings"])
        self.assertFalse(result["outputs"]["execution_performed"])

        derived = domain.plan_repair(
            {
                "defect_id": "defect-2",
                "candidate_paths": ["src/authorization.py"],
                "semantic_tags": [],
            }
        )
        self.assertEqual("R3", derived["outputs"]["risk_level"])

        mismatched = dict(repair_plan)
        mismatched["candidate_paths"] = ["src/other.py"]
        with self.assertRaises(ContractError):
            domain.validate_patch(
                {
                    "diff": "--- a/src/other.py\n+++ b/src/other.py\n@@ -1 +1 @@\n-a\n+b\n",
                    "candidate_paths": ["src/authorization.py"],
                    "semantic_tags": ["authorization"],
                    "repair_plan": mismatched,
                    "repair_plan_digest": digest_json(mismatched),
                    "isolated_worktree": True,
                    "sandboxed": True,
                    "approvals": [],
                }
            )

    def test_test_healing_cannot_reduce_assertion_strength(self) -> None:
        result = domain.validate_test_heal(
            {
                "before": "assert response.status == 403\nassert response.body == 'denied'",
                "after": "assert response is not None",
                "reason": "make test pass",
            }
        )
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("ASSERTION_STRENGTH_DECREASED", result["outputs"]["findings"])
        tautology = domain.validate_test_heal(
            {
                "before": "assert response.status == 403",
                "after": "assert 1 == 1",
                "reason": "make green",
                "business_oracle_changed": False,
            }
        )
        self.assertEqual("BLOCKED", tautology["state"])
        self.assertIn("OBVIOUS_TAUTOLOGY", tautology["outputs"]["findings"])
        self.assertIn("TRUSTED_TEST_HEAL_RECEIPT_REQUIRED", tautology["outputs"]["findings"])

    def test_product_patch_always_expands_to_full_regression(self) -> None:
        from elmos_autonomous_qa.gates import analyze_impact_contract

        result = analyze_impact_contract(
            {
                "changed_paths": ["src/a.py"],
                "exact_path_to_tests": {"src/a.py": ["TC-1"]},
                "all_tests": ["TC-1", "TC-2"],
                "product_code_changed": True,
            }
        )
        self.assertTrue(result["outputs"]["full_regression_required"])
        self.assertEqual(result["outputs"]["impacted_tests"], ["TC-1", "TC-2"])

    def test_generated_ids_stay_bounded_and_bundle_plans_retain_every_artifact(self) -> None:
        long_requirement_id = "REQ-" + "a" * 120
        generated = domain.generate_profile_cases(
            {
                "requirements": [
                    {
                        "requirement_id": long_requirement_id,
                        "priority": "P0",
                        "required": True,
                        "statement": "the exact behavior is preserved",
                    }
                ]
            },
            test_type="functional",
            strategies=("happy-path",),
        )
        test_id = generated["outputs"]["test_cases"][0]["test_case_id"]
        self.assertLessEqual(len(test_id.encode("utf-8")), 128)

        evidence = {
            "artifact_id": "artifact-evidence",
            "path": "evidence/result.json",
            "sha256": "a" * 64,
            "category": "evidence",
        }
        report_artifact = {
            "artifact_id": "artifact-report",
            "path": "reports/qa.json",
            "sha256": "b" * 64,
            "category": "report",
        }
        blocked = domain.plan_bundles(
            {"artifacts": [evidence], "kinds": ["project-with-tests"]}
        )
        self.assertEqual("BLOCKED", blocked["state"])
        planned = domain.plan_bundles(
            {
                "artifacts": [evidence, report_artifact],
                "kinds": ["qa-evidence"],
            }
        )
        self.assertEqual("SUCCEEDED", planned["state"])
        self.assertEqual(
            planned["outputs"]["manifest_proposal_digest"],
            digest_json(planned["outputs"]["manifest_proposal"]),
        )

    def test_repair_output_requires_patch_bundle_and_advanced_plan_is_not_persisted(self) -> None:
        output = domain.plan_output(
            {
                "run_mode": "repair",
                "output_mode": "both",
                "adapter": "python",
                "native_layout": "tests",
            }
        )
        self.assertIn("repair-patches", output["outputs"]["required_bundles"])
        advanced = domain.plan_advanced_testing(
            {
                "invariants": ["balance is conserved"],
                "entrypoints": ["payments.create"],
                "budget_seconds": 10,
            }
        )
        target = advanced["outputs"]["fuzz_targets"][0]
        self.assertTrue(target["corpus_persistence_required"])
        self.assertFalse(target["corpus_persisted"])

    def test_lifecycle_rejects_duplicate_and_unknown_artifact_references(self) -> None:
        artifact = {
            "artifact_id": "artifact-1",
            "source_refs": ["source-1"],
            "required": False,
            "superseded": True,
        }
        with self.assertRaises(ContractError):
            domain.evaluate_lifecycle(
                {
                    "artifacts": [artifact, artifact],
                    "referenced_artifact_ids": [],
                    "legal_hold_artifact_ids": [],
                    "changed_input_refs": [],
                }
            )
        required = {**artifact, "required": True}
        lifecycle = domain.evaluate_lifecycle(
            {
                "artifacts": [required],
                "referenced_artifact_ids": [],
                "legal_hold_artifact_ids": [],
                "changed_input_refs": [],
            }
        )
        self.assertEqual([], lifecycle["outputs"]["gc_candidates"])
        with self.assertRaises(ContractError):
            domain.evaluate_lifecycle(
                {
                    "artifacts": [artifact],
                    "referenced_artifact_ids": ["artifact-missing"],
                    "legal_hold_artifact_ids": [],
                    "changed_input_refs": [],
                }
            )

    def test_not_run_required_test_never_passes_gate(self) -> None:
        result = domain.evaluate_quality_gate(
            {
                "requirements": [
                    {"requirement_id": "REQ-1", "priority": "P0", "required": True}
                ],
                "tests": [
                    {
                        "test_case_id": "TC-1",
                        "status": "NOT_RUN",
                        "required": True,
                        "requirement_refs": ["REQ-1"],
                        "risk_refs": [],
                    }
                ],
                "output": {},
                "security": {},
            }
        )
        self.assertNotEqual(result["outputs"]["decision"], "READY_FOR_EXTERNAL_GATE")
        self.assertTrue(
            any("not_run" in finding["code"] for finding in result["outputs"]["findings"])
        )
        self.assertFalse(result["outputs"]["certified"])

    def test_learning_and_governance_require_authoritative_scope(self) -> None:
        learning = domain.propose_learning(
            {"source_state": "LOCAL_EXECUTED", "rule": {"kind": "unsafe"}}
        )
        self.assertEqual(learning["state"], "BLOCKED")
        authorization = domain.authorize_action(
            {
                "resource_tenant_id": "tenant-b",
                "action": "read-evidence",
                "roles": ["admin"],
                "required_roles": ["admin"],
                "_runtime_context": {
                    "tenant_id": "tenant-a",
                    "actor_id": "actor-a",
                },
            }
        )
        self.assertEqual(authorization["state"], "BLOCKED")
        self.assertIn("TENANT_MISMATCH", authorization["outputs"]["reasons"])

        locally_matching = domain.authorize_action(
            {
                "resource_tenant_id": "tenant-a",
                "action": "read-evidence",
                "roles": ["qa-reader"],
                "required_roles": ["qa-reader"],
                "_runtime_context": {
                    "tenant_id": "tenant-a",
                    "actor_id": "actor-a",
                },
            }
        )
        self.assertEqual(locally_matching["state"], "BLOCKED")
        self.assertEqual(locally_matching["code"], "TRUSTED_POLICY_DECISION_REQUIRED")
        self.assertFalse(locally_matching["outputs"]["allowed"])

    def test_report_requires_an_untampered_local_gate_report(self) -> None:
        gate_report = {
            "decision": "BLOCKED",
            "certified": False,
            "trusted_external_receipt": "NOT_RUN",
        }
        gate_report["report_digest"] = digest_json(gate_report)
        report = domain.build_report(
            {"test_results": [], "gate_report": gate_report, "wall_clock_seconds": 1}
        )
        self.assertEqual("BLOCKED", report["state"])
        self.assertEqual(report["outputs"]["summary"]["gate_decision"], "BLOCKED")
        tampered = dict(gate_report)
        tampered["decision"] = "READY_FOR_EXTERNAL_GATE"
        with self.assertRaises(ContractError):
            domain.build_report({"test_results": [], "gate_report": tampered})


if __name__ == "__main__":
    unittest.main()
