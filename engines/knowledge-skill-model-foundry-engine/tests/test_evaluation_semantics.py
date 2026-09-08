"""Focused positive and negative acceptance cases for the five Skill Evaluation handlers."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest

from elmos_foundry.adapters import AdapterRegistry
from elmos_foundry.canonical import canonical_digest
from elmos_foundry.domain import TenantScope
from elmos_foundry.evaluation_semantics import (
    EVALUATION_SEMANTIC_SKILLS,
    build_evaluation_handlers,
)
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.store import FoundryStore


SOURCE_INPUTS = {
    "skill-efficiency-evaluation": (
        "runbook", "experience episodes", "task contract", "semantic IR", "policy context",
    ),
    "skill-output-evaluation": (
        "runbook", "experience episodes", "task contract", "semantic IR", "policy context",
    ),
    "skill-process-evaluation": (
        "runbook", "experience episodes", "task contract", "semantic IR", "policy context",
    ),
    "skill-robustness-evaluation": (
        "runbook", "experience episodes", "task contract", "semantic IR", "policy context",
    ),
    "skill-trigger-evaluation": (
        "runbook", "experience episodes", "task contract", "semantic IR", "policy context",
    ),
}

EXPECTED_OUTPUTS = {
    "skill-efficiency-evaluation": {"skill package", "activation rules", "workflow DAG", "evidence bundle"},
    "skill-output-evaluation": {"skill package", "activation rules", "workflow DAG", "evidence bundle"},
    "skill-process-evaluation": {"skill package", "activation rules", "workflow DAG", "evidence bundle"},
    "skill-robustness-evaluation": {"skill package", "activation rules", "workflow DAG", "evidence bundle"},
    "skill-trigger-evaluation": {"skill package", "activation rules", "workflow DAG", "evidence bundle"},
}


def _base_inputs(scope: TenantScope) -> dict[str, Any]:
    return {
        "runbook": {"evaluation_id": "eval-acceptance", "mode": "evaluate"},
        "experience episodes": {"episode_ids": ["episode-eval-1"]},
        "policy context": {"purpose": scope.purpose, "effect_class": "LOCAL_DETERMINISTIC"},
    }


def _efficiency_inputs(scope: TenantScope) -> dict[str, Any]:
    inputs = _base_inputs(scope)
    inputs["task contract"] = {
        "purpose": scope.purpose,
        "budget": {
            "max_tokens": 10_000, "max_tool_calls": 100,
            "max_wall_clock_seconds": 3600, "max_cost_units": 50.0,
        },
        "measurements": {
            "token_count": 5_000, "tool_call_count": 20, "retry_count": 2,
            "wall_clock_seconds": 1200.0, "cache_hit_ratio": 0.5, "cost_units": 12.5,
        },
    }
    inputs["semantic IR"] = {"efficiency_targets": ["token-efficiency"]}
    return inputs


def _output_inputs(scope: TenantScope) -> dict[str, Any]:
    inputs = _base_inputs(scope)
    inputs["task contract"] = {
        "purpose": scope.purpose,
        "acceptance_criteria": [
            {"criterion_id": "crit-a", "required": True, "validator": "digest-match"},
            {"criterion_id": "crit-b", "required": False, "validator": "schema-check"},
        ],
        "artifacts": [
            {"artifact_id": "art-a", "content_digest": canonical_digest("content-a"),
             "artifact_type": "code", "satisfies": ["crit-a"]},
        ],
    }
    inputs["semantic IR"] = {"output_targets": ["contract-conformance"]}
    return inputs


def _process_inputs(scope: TenantScope) -> dict[str, Any]:
    inputs = _base_inputs(scope)
    inputs["task contract"] = {
        "purpose": scope.purpose,
        "prescribed_steps": ["step-1", "step-2", "step-3"],
        "executed_steps": [
            {"step": "step-1", "tool": "skill.registry", "approved": True, "validated": True},
            {"step": "step-2", "tool": "sandbox.run", "approved": True, "validated": True},
            {"step": "step-3", "tool": "eval.run", "approved": True, "validated": True},
        ],
        "approvals": {"required": ["approver-lead"], "obtained": ["approver-lead"]},
    }
    inputs["semantic IR"] = {"process_targets": ["step-compliance"]}
    return inputs


def _robustness_inputs(scope: TenantScope) -> dict[str, Any]:
    inputs = _base_inputs(scope)
    scenarios = []
    for cat in ("boundary-input", "version-change", "tool-failure",
                "concurrency", "recovery", "malicious-content"):
        scenarios.append({
            "scenario_id": f"scenario-{cat}",
            "category": cat,
            "input_digest": canonical_digest(f"input-{cat}"),
            "expected_outcome": "pass",
            "actual_outcome": "pass",
        })
    inputs["task contract"] = {"purpose": scope.purpose, "robustness_scenarios": scenarios}
    inputs["semantic IR"] = {"robustness_targets": ["boundary-coverage"]}
    return inputs


def _trigger_inputs(scope: TenantScope) -> dict[str, Any]:
    inputs = _base_inputs(scope)
    scenarios = [
        {"scenario_id": "s-should-trigger", "category": "should-trigger",
         "query": "evaluate skill efficiency", "expected_skills": ["skill-efficiency-evaluation"],
         "actual_skills": ["skill-efficiency-evaluation"]},
        {"scenario_id": "s-should-not-trigger", "category": "should-not-trigger",
         "query": "what time is it", "expected_skills": [], "actual_skills": []},
        {"scenario_id": "s-ambiguous", "category": "ambiguous-intent",
         "query": "check output", "expected_skills": ["skill-output-evaluation"],
         "actual_skills": ["skill-output-evaluation"]},
        {"scenario_id": "s-typo", "category": "typo",
         "query": "efficency evaluaton", "expected_skills": ["skill-efficiency-evaluation"],
         "actual_skills": ["skill-efficiency-evaluation"]},
        {"scenario_id": "s-multi-intent", "category": "multi-intent",
         "query": "evaluate output and process",
         "expected_skills": ["skill-output-evaluation", "skill-process-evaluation"],
         "actual_skills": ["skill-output-evaluation", "skill-process-evaluation"]},
    ]
    inputs["task contract"] = {"purpose": scope.purpose, "trigger_scenarios": scenarios}
    inputs["semantic IR"] = {"trigger_targets": ["trigger-accuracy"]}
    return inputs


FIXTURES = {
    "skill-efficiency-evaluation": _efficiency_inputs,
    "skill-output-evaluation": _output_inputs,
    "skill-process-evaluation": _process_inputs,
    "skill-robustness-evaluation": _robustness_inputs,
    "skill-trigger-evaluation": _trigger_inputs,
}


def fixture_inputs(skill: str, scope: TenantScope) -> dict[str, Any]:
    return FIXTURES[skill](scope)


class EvaluationSemanticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="foundry-eval-semantics-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.sqlite3"
        self.kernel = ExecutionKernel()
        self.store = FoundryStore(self.path, context_verifier=self.kernel.require_context)
        self.addCleanup(self.store.close)
        self.scope = self._mint_scope()
        self.catalog = SimpleNamespace(
            content_sha256="a" * 64,
            discovery={"candidate_limit": 16, "activation_limit": 8},
            atomic_skills={name: {"dependencies": ["typed-skill-contract", "policy-contract", "evidence-contract"]}
                           for name in EVALUATION_SEMANTIC_SKILLS},
            meta_skills={},
        )
        self.handlers = build_evaluation_handlers(self.catalog, self.store)

    def _mint_scope(self, **changes: Any) -> TenantScope:
        values = {
            "tenant_id": "tenant-eval", "project_id": "project-eval", "actor_id": "actor-eval",
            "environment_id": "environment-local", "workspace_digest": "sha256:" + "a" * 64,
            "revision_set_id": "sha256:" + "b" * 64, "purpose": "evaluation-acceptance",
            "capabilities": ("foundry.adapter.execute", "foundry.store.read", "foundry.store.write"),
            "ttl_seconds": 600,
        }
        values.update(changes)
        return self.kernel.mint_context(**values)

    def invoke(self, name: str, inputs: dict[str, Any] | None = None, scope: TenantScope | None = None) -> Any:
        actual_scope = scope or self.scope
        self.kernel.require_context(actual_scope, "foundry.adapter.execute")
        payload = {
            "operation": "local-semantic-execute",
            "inputs": fixture_inputs(name, actual_scope) if inputs is None else inputs,
        }
        AdapterRegistry._validate_adapter_payload(payload=payload, required_inputs=SOURCE_INPUTS[name])
        return self.handlers[name](
            name, payload, actual_scope, actual_scope.invocation_id,
        )

    # -- shared acceptance --------------------------------------------------

    def test_exact_handlers_and_source_output_shapes(self) -> None:
        self.assertEqual(EVALUATION_SEMANTIC_SKILLS, set(self.handlers))
        for name in sorted(self.handlers):
            result = self.invoke(name)
            with self.subTest(skill=name):
                self.assertEqual(EXPECTED_OUTPUTS[name], set(result["outputs"]))
                self.assertEqual("SUCCEEDED", result["status"])
                self.assertEqual("NOT_RUN", result["external_evidence_status"])
                self.assertEqual("NOT_CERTIFIED", result["certification_status"])
                self.assertEqual("NOT_RUN", result["outputs"]["evidence bundle"]["independent_verification"])

    def test_required_outer_inputs_are_nonempty_at_the_public_guard(self) -> None:
        for name, required in SOURCE_INPUTS.items():
            for input_name in required:
                for empty in (None, "", [], {}):
                    inputs = fixture_inputs(name, self.scope)
                    inputs[input_name] = empty
                    with self.subTest(skill=name, input=input_name, empty=empty):
                        with self.assertRaisesRegex(ValueError, "missing required inputs"):
                            self.invoke(name, inputs)

    def test_purpose_mismatch_with_scope_fails_closed(self) -> None:
        for name in sorted(self.handlers):
            inputs = fixture_inputs(name, self.scope)
            inputs["task contract"]["purpose"] = "wrong-purpose"
            with self.subTest(skill=name):
                with self.assertRaisesRegex(ValueError, "purpose differs from the trusted scope"):
                    self.invoke(name, inputs)

    def test_external_effect_class_is_rejected(self) -> None:
        for name in sorted(self.handlers):
            inputs = fixture_inputs(name, self.scope)
            inputs["policy context"]["effect_class"] = "EXTERNAL_MUTATION"
            with self.subTest(skill=name):
                with self.assertRaisesRegex(ValueError, "external effects"):
                    self.invoke(name, inputs)

    def test_invalid_runbook_mode_fails_closed(self) -> None:
        for name in sorted(self.handlers):
            inputs = fixture_inputs(name, self.scope)
            inputs["runbook"]["mode"] = "execute"
            with self.subTest(skill=name):
                with self.assertRaisesRegex(ValueError, "mode must be"):
                    self.invoke(name, inputs)

    def test_dry_run_mode_is_accepted(self) -> None:
        for name in sorted(self.handlers):
            inputs = fixture_inputs(name, self.scope)
            inputs["runbook"]["mode"] = "dry-run"
            with self.subTest(skill=name):
                result = self.invoke(name, inputs)
                self.assertEqual("SUCCEEDED", result["status"])
                self.assertEqual("dry-run", result["outputs"]["skill package"]["mode"])

    def test_scope_binding_preserves_tenant_and_project(self) -> None:
        for name in sorted(self.handlers):
            with self.subTest(skill=name):
                result = self.invoke(name)
                binding = result["outputs"]["activation rules"]["scope"]
                self.assertEqual(self.scope.tenant_id, binding["tenant_id"])
                self.assertEqual(self.scope.project_id, binding["project_id"])

    # -- efficiency-specific -----------------------------------------------

    def test_efficiency_pass_when_within_budget(self) -> None:
        primary = self.invoke("skill-efficiency-evaluation")["outputs"]["skill package"]
        self.assertEqual("PASS", primary["decision"])
        self.assertEqual([], primary["overage_reasons"])
        self.assertGreater(primary["efficiency_score"], 0.0)
        self.assertLess(primary["efficiency_score"], 1.0)

    def test_efficiency_blocks_when_token_budget_exceeded(self) -> None:
        inputs = _efficiency_inputs(self.scope)
        inputs["task contract"]["measurements"]["token_count"] = 20_000
        primary = self.invoke("skill-efficiency-evaluation", inputs)["outputs"]["skill package"]
        self.assertEqual("BLOCKED", primary["decision"])
        self.assertIn("token_utilization", primary["overage_reasons"])

    def test_efficiency_blocks_when_cost_exceeds_budget(self) -> None:
        inputs = _efficiency_inputs(self.scope)
        inputs["task contract"]["measurements"]["cost_units"] = 100.0
        primary = self.invoke("skill-efficiency-evaluation", inputs)["outputs"]["skill package"]
        self.assertEqual("BLOCKED", primary["decision"])
        self.assertIn("cost_utilization", primary["overage_reasons"])

    def test_efficiency_rejects_invalid_cache_ratio(self) -> None:
        inputs = _efficiency_inputs(self.scope)
        inputs["task contract"]["measurements"]["cache_hit_ratio"] = 1.5
        with self.assertRaisesRegex(ValueError, "cache_hit_ratio must be in"):
            self.invoke("skill-efficiency-evaluation", inputs)

    def test_efficiency_rejects_negative_wall_clock(self) -> None:
        inputs = _efficiency_inputs(self.scope)
        inputs["task contract"]["measurements"]["wall_clock_seconds"] = -1.0
        with self.assertRaisesRegex(ValueError, "wall_clock_seconds must be non-negative"):
            self.invoke("skill-efficiency-evaluation", inputs)

    # -- output-specific ----------------------------------------------------

    def test_output_pass_when_required_criteria_satisfied(self) -> None:
        primary = self.invoke("skill-output-evaluation")["outputs"]["skill package"]
        self.assertEqual("PASS", primary["decision"])
        self.assertEqual(1, primary["passed"])
        self.assertEqual(0, primary["failed_required"])
        self.assertEqual(1, primary["failed_optional"])

    def test_output_blocks_when_required_criterion_unsatisfied(self) -> None:
        inputs = _output_inputs(self.scope)
        inputs["task contract"]["artifacts"] = []
        primary = self.invoke("skill-output-evaluation", inputs)["outputs"]["skill package"]
        self.assertEqual("BLOCKED", primary["decision"])
        self.assertEqual(1, primary["failed_required"])

    def test_output_rejects_duplicate_criterion_id(self) -> None:
        inputs = _output_inputs(self.scope)
        inputs["task contract"]["acceptance_criteria"].append(
            {"criterion_id": "crit-a", "required": True, "validator": "duplicate"}
        )
        with self.assertRaisesRegex(ValueError, "duplicate criterion_id"):
            self.invoke("skill-output-evaluation", inputs)

    def test_output_rejects_artifact_referencing_unknown_criterion(self) -> None:
        inputs = _output_inputs(self.scope)
        inputs["task contract"]["artifacts"][0]["satisfies"] = ["unknown-criterion"]
        with self.assertRaisesRegex(ValueError, "unknown criteria"):
            self.invoke("skill-output-evaluation", inputs)

    def test_output_rejects_invalid_digest(self) -> None:
        inputs = _output_inputs(self.scope)
        inputs["task contract"]["artifacts"][0]["content_digest"] = "not-a-digest"
        with self.assertRaisesRegex(ValueError, "must use sha256"):
            self.invoke("skill-output-evaluation", inputs)

    # -- process-specific ---------------------------------------------------

    def test_process_pass_when_all_steps_compliant(self) -> None:
        primary = self.invoke("skill-process-evaluation")["outputs"]["skill package"]
        self.assertEqual("PASS", primary["decision"])
        self.assertEqual([], primary["deviations"])
        self.assertEqual([], primary["skipped_steps"])

    def test_process_blocks_when_step_skipped(self) -> None:
        inputs = _process_inputs(self.scope)
        inputs["task contract"]["executed_steps"] = inputs["task contract"]["executed_steps"][:2]
        primary = self.invoke("skill-process-evaluation", inputs)["outputs"]["skill package"]
        self.assertEqual("BLOCKED", primary["decision"])
        self.assertIn("step-3", primary["skipped_steps"])
        self.assertTrue(any("skipped-step" in d for d in primary["deviations"]))

    def test_process_blocks_when_unapproved_step(self) -> None:
        inputs = _process_inputs(self.scope)
        inputs["task contract"]["executed_steps"][1]["approved"] = False
        primary = self.invoke("skill-process-evaluation", inputs)["outputs"]["skill package"]
        self.assertEqual("BLOCKED", primary["decision"])
        self.assertIn("unapproved-step:step-2", primary["deviations"])

    def test_process_blocks_when_missing_approval(self) -> None:
        inputs = _process_inputs(self.scope)
        inputs["task contract"]["approvals"]["obtained"] = []
        primary = self.invoke("skill-process-evaluation", inputs)["outputs"]["skill package"]
        self.assertEqual("BLOCKED", primary["decision"])
        self.assertIn("missing-approval:approver-lead", primary["deviations"])

    def test_process_rejects_executed_step_not_in_prescribed(self) -> None:
        inputs = _process_inputs(self.scope)
        inputs["task contract"]["executed_steps"].append(
            {"step": "step-unknown", "tool": "tool", "approved": True, "validated": True}
        )
        with self.assertRaisesRegex(ValueError, "not in prescribed steps"):
            self.invoke("skill-process-evaluation", inputs)

    def test_process_rejects_duplicate_executed_step(self) -> None:
        inputs = _process_inputs(self.scope)
        inputs["task contract"]["executed_steps"].append(
            deepcopy(inputs["task contract"]["executed_steps"][0])
        )
        with self.assertRaisesRegex(ValueError, "duplicate executed step"):
            self.invoke("skill-process-evaluation", inputs)

    # -- robustness-specific ------------------------------------------------

    def test_robustness_pass_when_all_scenarios_match(self) -> None:
        primary = self.invoke("skill-robustness-evaluation")["outputs"]["skill package"]
        self.assertEqual("PASS", primary["decision"])
        self.assertEqual(6, primary["scenario_count"])
        self.assertEqual(6, primary["passed"])
        self.assertEqual(0, primary["failed"])
        self.assertEqual([], primary["missing_categories"])

    def test_robustness_blocks_when_scenario_fails(self) -> None:
        inputs = _robustness_inputs(self.scope)
        inputs["task contract"]["robustness_scenarios"][0]["actual_outcome"] = "fail"
        primary = self.invoke("skill-robustness-evaluation", inputs)["outputs"]["skill package"]
        self.assertEqual("BLOCKED", primary["decision"])
        self.assertEqual(1, primary["failed"])

    def test_robustness_blocks_when_category_missing(self) -> None:
        inputs = _robustness_inputs(self.scope)
        inputs["task contract"]["robustness_scenarios"] = inputs["task contract"]["robustness_scenarios"][:5]
        primary = self.invoke("skill-robustness-evaluation", inputs)["outputs"]["skill package"]
        self.assertEqual("BLOCKED", primary["decision"])
        self.assertEqual(1, len(primary["missing_categories"]))

    def test_robustness_rejects_invalid_category(self) -> None:
        inputs = _robustness_inputs(self.scope)
        inputs["task contract"]["robustness_scenarios"][0]["category"] = "unknown-category"
        with self.assertRaisesRegex(ValueError, "category must be one of"):
            self.invoke("skill-robustness-evaluation", inputs)

    def test_robustness_rejects_invalid_outcome(self) -> None:
        inputs = _robustness_inputs(self.scope)
        inputs["task contract"]["robustness_scenarios"][0]["actual_outcome"] = "maybe"
        with self.assertRaisesRegex(ValueError, "actual_outcome must be"):
            self.invoke("skill-robustness-evaluation", inputs)

    def test_robustness_rejects_duplicate_scenario_id(self) -> None:
        inputs = _robustness_inputs(self.scope)
        inputs["task contract"]["robustness_scenarios"].append(
            deepcopy(inputs["task contract"]["robustness_scenarios"][0])
        )
        with self.assertRaisesRegex(ValueError, "duplicate scenario_id"):
            self.invoke("skill-robustness-evaluation", inputs)

    # -- trigger-specific ---------------------------------------------------

    def test_trigger_pass_when_all_scenarios_correct(self) -> None:
        primary = self.invoke("skill-trigger-evaluation")["outputs"]["skill package"]
        self.assertEqual("PASS", primary["decision"])
        self.assertEqual(5, primary["scenario_count"])
        self.assertEqual(5, primary["passed"])
        self.assertEqual(0, primary["failed"])
        self.assertEqual(0, primary["false_positives"])
        self.assertEqual(0, primary["false_negatives"])
        self.assertEqual([], primary["missing_categories"])

    def test_trigger_blocks_when_should_trigger_misfires(self) -> None:
        inputs = _trigger_inputs(self.scope)
        inputs["task contract"]["trigger_scenarios"][0]["actual_skills"] = []
        primary = self.invoke("skill-trigger-evaluation", inputs)["outputs"]["skill package"]
        self.assertEqual("BLOCKED", primary["decision"])
        self.assertEqual(1, primary["failed"])
        self.assertGreater(primary["false_negatives"], 0)

    def test_trigger_blocks_when_should_not_trigger_fires(self) -> None:
        inputs = _trigger_inputs(self.scope)
        inputs["task contract"]["trigger_scenarios"][1]["actual_skills"] = ["skill-efficiency-evaluation"]
        primary = self.invoke("skill-trigger-evaluation", inputs)["outputs"]["skill package"]
        self.assertEqual("BLOCKED", primary["decision"])
        self.assertGreater(primary["false_positives"], 0)

    def test_trigger_blocks_when_category_missing(self) -> None:
        inputs = _trigger_inputs(self.scope)
        inputs["task contract"]["trigger_scenarios"] = inputs["task contract"]["trigger_scenarios"][:4]
        primary = self.invoke("skill-trigger-evaluation", inputs)["outputs"]["skill package"]
        self.assertEqual("BLOCKED", primary["decision"])
        self.assertEqual(1, len(primary["missing_categories"]))

    def test_trigger_rejects_invalid_category(self) -> None:
        inputs = _trigger_inputs(self.scope)
        inputs["task contract"]["trigger_scenarios"][0]["category"] = "unknown-category"
        with self.assertRaisesRegex(ValueError, "category must be one of"):
            self.invoke("skill-trigger-evaluation", inputs)

    def test_trigger_rejects_duplicate_scenario_id(self) -> None:
        inputs = _trigger_inputs(self.scope)
        inputs["task contract"]["trigger_scenarios"].append(
            deepcopy(inputs["task contract"]["trigger_scenarios"][0])
        )
        with self.assertRaisesRegex(ValueError, "duplicate scenario_id"):
            self.invoke("skill-trigger-evaluation", inputs)

    # -- determinism --------------------------------------------------------

    def test_results_are_deterministic_across_invocations(self) -> None:
        for name in sorted(self.handlers):
            first = self.invoke(name)
            second = self.invoke(name)
            with self.subTest(skill=name):
                self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
