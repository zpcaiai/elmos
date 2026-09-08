"""Five bounded Skill Evaluation handlers for the 05-skill-foundry-runtime pack.

Each handler performs deterministic, repository-owned evaluation of a specific
skill-quality dimension: efficiency, output conformance, process compliance,
robustness, and trigger accuracy.  They share the same typed input envelope as
the other runtime handlers (runbook, experience episodes, task contract,
semantic IR, policy context) and produce the canonical four-section output
(skill package, activation rules, workflow DAG, evidence bundle).

No handler calls a provider, trains a model, mutates a repository, or claims
independent evidence.  Every evaluation is a local deterministic computation
over caller-supplied, digest-bound measurements and scenarios.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from .canonical import (
    canonical_digest,
    canonical_value,
    require_identifier,
    validate_digest,
)
from .domain import TenantScope
from .local_semantics import (
    CatalogView,
    LocalHandler,
    _exact_mapping,
    _number,
    _response,
    _sequence,
    _text,
)
from .store import FoundryStore


EVALUATION_SEMANTIC_SKILLS = frozenset({
    "skill-efficiency-evaluation",
    "skill-output-evaluation",
    "skill-process-evaluation",
    "skill-robustness-evaluation",
    "skill-trigger-evaluation",
})

_EVALUATION_INPUTS = {"runbook", "experience episodes", "task contract", "semantic IR", "policy context"}
_ROBUSTNESS_CATEGORIES = frozenset({
    "boundary-input", "version-change", "tool-failure",
    "concurrency", "recovery", "malicious-content",
})
_TRIGGER_CATEGORIES = frozenset({
    "should-trigger", "should-not-trigger",
    "ambiguous-intent", "typo", "multi-intent",
})


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return int(value)


def _strings(value: Any, label: str, *, minimum: int = 0, maximum: int = 256) -> list[str]:
    items = [require_identifier(item, label) for item in _sequence(
        value, label, minimum=minimum, maximum=maximum,
    )]
    if len(items) != len(set(items)):
        raise ValueError(f"{label} contains duplicate entries")
    return items


def _values(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    values = _exact_mapping(payload.get("inputs"), "inputs", _EVALUATION_INPUTS)
    canonical_value(values)
    return values


def _runbook(values: Mapping[str, Any]) -> tuple[str, str]:
    book = _exact_mapping(values["runbook"], "runbook", {"evaluation_id", "mode"})
    evaluation_id = require_identifier(book["evaluation_id"], "evaluation_id")
    mode = book["mode"]
    if mode not in {"evaluate", "dry-run"}:
        raise ValueError("runbook mode must be evaluate or dry-run")
    return evaluation_id, mode


def _episodes(values: Mapping[str, Any]) -> list[str]:
    envelope = _exact_mapping(values["experience episodes"], "experience episodes", {"episode_ids"})
    return _strings(envelope["episode_ids"], "episode_ids", minimum=0, maximum=64)


def _policy(values: Mapping[str, Any], scope: TenantScope) -> Mapping[str, Any]:
    policy = _exact_mapping(values["policy context"], "policy context", {"purpose", "effect_class"})
    if policy["purpose"] != scope.purpose:
        raise ValueError("evaluation purpose differs from the trusted scope")
    if policy["effect_class"] != "LOCAL_DETERMINISTIC":
        raise ValueError("evaluation does not authorize external effects")
    return policy


def _scope_binding(scope: TenantScope) -> Mapping[str, str]:
    return {key: str(getattr(scope, key)) for key in (
        "tenant_id", "project_id", "actor_id", "environment_id", "workspace_digest",
        "revision_set_id", "purpose",
    )}


def _evaluation_outputs(
    skill: str,
    values: Mapping[str, Any],
    scope: TenantScope,
    catalog: CatalogView,
    primary: Mapping[str, Any],
) -> Mapping[str, Any]:
    binding = _scope_binding(scope)
    return {
        "skill package": primary,
        "activation rules": {
            "effect_class": "LOCAL_DETERMINISTIC",
            "scope": binding,
            "mode": "evaluate",
        },
        "workflow DAG": {
            "skill": skill,
            "steps": ["validate-preconditions", "evaluate", "aggregate-evidence"],
            "dependencies": list(catalog.atomic_skills[skill]["dependencies"]),
        },
        "evidence bundle": {
            "input_digest": canonical_digest(values),
            "catalog_digest": catalog.content_sha256,
            "evidence_state": "COLLECTED_SELF_ATTESTED",
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
            "independent_verification": "NOT_RUN",
        },
    }


def _ratio(actual: float, budget: float) -> float:
    if budget <= 0:
        return 0.0 if actual <= 0 else float("inf")
    return actual / budget


class EvaluationSemantics:
    """Repository-owned deterministic evaluation handlers."""

    def __init__(self, catalog: CatalogView, store: FoundryStore | None) -> None:
        self.catalog = catalog
        self.store = store

    # -- skill-efficiency-evaluation ----------------------------------------

    def skill_efficiency_evaluation(
        self, skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str,
    ) -> Mapping[str, Any]:
        values = _values(payload)
        evaluation_id, mode = _runbook(values)
        _episodes(values)
        _policy(values, scope)
        task = _exact_mapping(values["task contract"], "task contract", {"purpose", "budget", "measurements"})
        if task["purpose"] != scope.purpose:
            raise ValueError("efficiency evaluation purpose differs from the trusted scope")
        budget = _exact_mapping(task["budget"], "budget", {
            "max_tokens", "max_tool_calls", "max_wall_clock_seconds", "max_cost_units",
        })
        measurements = _exact_mapping(task["measurements"], "measurements", {
            "token_count", "tool_call_count", "retry_count",
            "wall_clock_seconds", "cache_hit_ratio", "cost_units",
        })
        max_tokens = _integer(budget["max_tokens"], "budget.max_tokens", 1, 10_000_000)
        max_tool_calls = _integer(budget["max_tool_calls"], "budget.max_tool_calls", 1, 100_000)
        max_wall = _integer(budget["max_wall_clock_seconds"], "budget.max_wall_clock_seconds", 1, 86400)
        max_cost = _number(budget["max_cost_units"], "budget.max_cost_units")
        if max_cost <= 0:
            raise ValueError("budget.max_cost_units must be positive")
        token_count = _integer(measurements["token_count"], "measurements.token_count", 0, 10_000_000)
        tool_calls = _integer(measurements["tool_call_count"], "measurements.tool_call_count", 0, 100_000)
        retries = _integer(measurements["retry_count"], "measurements.retry_count", 0, 10_000)
        wall = _number(measurements["wall_clock_seconds"], "measurements.wall_clock_seconds")
        if wall < 0:
            raise ValueError("measurements.wall_clock_seconds must be non-negative")
        cache_ratio = _number(measurements["cache_hit_ratio"], "measurements.cache_hit_ratio")
        if not 0.0 <= cache_ratio <= 1.0:
            raise ValueError("measurements.cache_hit_ratio must be in [0,1]")
        cost = _number(measurements["cost_units"], "measurements.cost_units")
        if cost < 0:
            raise ValueError("measurements.cost_units must be non-negative")
        ir = _exact_mapping(values["semantic IR"], "semantic IR", {"efficiency_targets"})
        targets = _strings(ir["efficiency_targets"], "efficiency_targets", minimum=1, maximum=32)
        ratios = {
            "token_utilization": _ratio(float(token_count), float(max_tokens)),
            "tool_call_utilization": _ratio(float(tool_calls), float(max_tool_calls)),
            "wall_clock_utilization": _ratio(wall, float(max_wall)),
            "cost_utilization": _ratio(cost, max_cost),
        }
        overages = sorted(
            key for key, ratio in ratios.items() if ratio > 1.0
        )
        efficiency_score = max(0.0, 1.0 - max(ratios.values())) if ratios else 0.0
        decision = "PASS" if not overages and retries <= max_tool_calls else "BLOCKED"
        primary = {
            "schema_version": "elmos.foundry.efficiency-evaluation.v1",
            "evaluation_id": evaluation_id,
            "mode": mode,
            "targets": targets,
            "budget": canonical_value(task["budget"]),
            "measurements": canonical_value(task["measurements"]),
            "utilization_ratios": ratios,
            "efficiency_score": round(efficiency_score, 6),
            "cache_hit_ratio": cache_ratio,
            "retry_count": retries,
            "overage_reasons": overages,
            "decision": decision,
            "content_digest": canonical_digest({
                "evaluation_id": evaluation_id, "measurements": measurements, "budget": budget,
            }),
        }
        return _response(_evaluation_outputs(skill, values, scope, self.catalog, primary))

    # -- skill-output-evaluation --------------------------------------------

    def skill_output_evaluation(
        self, skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str,
    ) -> Mapping[str, Any]:
        values = _values(payload)
        evaluation_id, mode = _runbook(values)
        _episodes(values)
        _policy(values, scope)
        task = _exact_mapping(values["task contract"], "task contract", {
            "purpose", "acceptance_criteria", "artifacts",
        })
        if task["purpose"] != scope.purpose:
            raise ValueError("output evaluation purpose differs from the trusted scope")
        criteria_raw = _sequence(task["acceptance_criteria"], "acceptance_criteria", maximum=256)
        criteria: list[Mapping[str, Any]] = []
        criterion_ids: set[str] = set()
        for index, raw in enumerate(criteria_raw):
            entry = _exact_mapping(raw, f"acceptance_criteria[{index}]", {
                "criterion_id", "required", "validator",
            })
            cid = require_identifier(entry["criterion_id"], f"acceptance_criteria[{index}].criterion_id")
            if cid in criterion_ids:
                raise ValueError(f"duplicate criterion_id: {cid}")
            criterion_ids.add(cid)
            if not isinstance(entry["required"], bool):
                raise ValueError(f"acceptance_criteria[{index}].required must be boolean")
            validator = _text(entry["validator"], f"acceptance_criteria[{index}].validator", maximum=128)
            criteria.append({"criterion_id": cid, "required": entry["required"], "validator": validator})
        artifacts_raw = _sequence(task["artifacts"], "artifacts", minimum=0, maximum=256)
        artifacts: list[Mapping[str, Any]] = []
        artifact_ids: set[str] = set()
        for index, raw in enumerate(artifacts_raw):
            entry = _exact_mapping(raw, f"artifacts[{index}]", {
                "artifact_id", "content_digest", "artifact_type", "satisfies",
            })
            aid = require_identifier(entry["artifact_id"], f"artifacts[{index}].artifact_id")
            if aid in artifact_ids:
                raise ValueError(f"duplicate artifact_id: {aid}")
            artifact_ids.add(aid)
            validate_digest(entry["content_digest"], f"artifacts[{index}].content_digest")
            atype = require_identifier(entry["artifact_type"], f"artifacts[{index}].artifact_type")
            satisfies = _strings(entry["satisfies"], f"artifacts[{index}].satisfies", minimum=0, maximum=64)
            unknown = sorted(set(satisfies) - criterion_ids)
            if unknown:
                raise ValueError(f"artifacts[{index}] references unknown criteria: {unknown}")
            artifacts.append({
                "artifact_id": aid,
                "content_digest": entry["content_digest"],
                "artifact_type": atype,
                "satisfies": satisfies,
            })
        ir = _exact_mapping(values["semantic IR"], "semantic IR", {"output_targets"})
        targets = _strings(ir["output_targets"], "output_targets", minimum=1, maximum=32)
        satisfied: set[str] = set()
        for artifact in artifacts:
            satisfied.update(artifact["satisfies"])
        results: list[Mapping[str, Any]] = []
        passed = 0
        failed_required = 0
        failed_optional = 0
        for entry in criteria:
            met = entry["criterion_id"] in satisfied
            status = "PASS" if met else ("FAIL_REQUIRED" if entry["required"] else "FAIL_OPTIONAL")
            if met:
                passed += 1
            elif entry["required"]:
                failed_required += 1
            else:
                failed_optional += 1
            results.append({
                "criterion_id": entry["criterion_id"],
                "required": entry["required"],
                "status": status,
            })
        decision = "PASS" if failed_required == 0 else "BLOCKED"
        primary = {
            "schema_version": "elmos.foundry.output-evaluation.v1",
            "evaluation_id": evaluation_id,
            "mode": mode,
            "targets": targets,
            "criterion_count": len(criteria),
            "artifact_count": len(artifacts),
            "results": results,
            "passed": passed,
            "failed_required": failed_required,
            "failed_optional": failed_optional,
            "decision": decision,
            "content_digest": canonical_digest({
                "evaluation_id": evaluation_id, "results": results, "artifacts": artifacts,
            }),
        }
        return _response(_evaluation_outputs(skill, values, scope, self.catalog, primary))

    # -- skill-process-evaluation -------------------------------------------

    def skill_process_evaluation(
        self, skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str,
    ) -> Mapping[str, Any]:
        values = _values(payload)
        evaluation_id, mode = _runbook(values)
        _episodes(values)
        _policy(values, scope)
        task = _exact_mapping(values["task contract"], "task contract", {
            "purpose", "prescribed_steps", "executed_steps", "approvals",
        })
        if task["purpose"] != scope.purpose:
            raise ValueError("process evaluation purpose differs from the trusted scope")
        prescribed = _strings(task["prescribed_steps"], "prescribed_steps", minimum=1, maximum=128)
        prescribed_set = set(prescribed)
        approvals = _exact_mapping(task["approvals"], "approvals", {"required", "obtained"})
        required_approvals = _strings(approvals["required"], "approvals.required", minimum=0, maximum=64)
        obtained_approvals = set(_strings(approvals["obtained"], "approvals.obtained", minimum=0, maximum=64))
        missing_approvals = sorted(set(required_approvals) - obtained_approvals)
        executed_raw = _sequence(task["executed_steps"], "executed_steps", maximum=256)
        executed: list[Mapping[str, Any]] = []
        executed_names: set[str] = set()
        for index, raw in enumerate(executed_raw):
            entry = _exact_mapping(raw, f"executed_steps[{index}]", {
                "step", "tool", "approved", "validated",
            })
            step_name = require_identifier(entry["step"], f"executed_steps[{index}].step")
            if step_name in executed_names:
                raise ValueError(f"duplicate executed step: {step_name}")
            if step_name not in prescribed_set:
                raise ValueError(f"executed step not in prescribed steps: {step_name}")
            executed_names.add(step_name)
            tool = require_identifier(entry["tool"], f"executed_steps[{index}].tool")
            if not isinstance(entry["approved"], bool):
                raise ValueError(f"executed_steps[{index}].approved must be boolean")
            if not isinstance(entry["validated"], bool):
                raise ValueError(f"executed_steps[{index}].validated must be boolean")
            executed.append({
                "step": step_name, "tool": tool,
                "approved": entry["approved"], "validated": entry["validated"],
            })
        ir = _exact_mapping(values["semantic IR"], "semantic IR", {"process_targets"})
        targets = _strings(ir["process_targets"], "process_targets", minimum=1, maximum=32)
        skipped = sorted(prescribed_set - executed_names)
        deviations: list[str] = []
        for entry in executed:
            if not entry["approved"]:
                deviations.append(f"unapproved-step:{entry['step']}")
            if not entry["validated"]:
                deviations.append(f"unvalidated-step:{entry['step']}")
        deviations.extend(f"skipped-step:{step}" for step in skipped)
        deviations.extend(f"missing-approval:{name}" for name in missing_approvals)
        decision = "PASS" if not deviations else "BLOCKED"
        primary = {
            "schema_version": "elmos.foundry.process-evaluation.v1",
            "evaluation_id": evaluation_id,
            "mode": mode,
            "targets": targets,
            "prescribed_steps": prescribed,
            "executed_steps": [e["step"] for e in executed],
            "skipped_steps": skipped,
            "missing_approvals": missing_approvals,
            "deviations": deviations,
            "decision": decision,
            "content_digest": canonical_digest({
                "evaluation_id": evaluation_id, "executed": executed,
                "prescribed": prescribed, "approvals": approvals,
            }),
        }
        return _response(_evaluation_outputs(skill, values, scope, self.catalog, primary))

    # -- skill-robustness-evaluation ----------------------------------------

    def skill_robustness_evaluation(
        self, skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str,
    ) -> Mapping[str, Any]:
        values = _values(payload)
        evaluation_id, mode = _runbook(values)
        _episodes(values)
        _policy(values, scope)
        task = _exact_mapping(values["task contract"], "task contract", {
            "purpose", "robustness_scenarios",
        })
        if task["purpose"] != scope.purpose:
            raise ValueError("robustness evaluation purpose differs from the trusted scope")
        scenarios_raw = _sequence(task["robustness_scenarios"], "robustness_scenarios", minimum=1, maximum=256)
        scenarios: list[Mapping[str, Any]] = []
        scenario_ids: set[str] = set()
        category_counts: Counter[str] = Counter()
        for index, raw in enumerate(scenarios_raw):
            entry = _exact_mapping(raw, f"robustness_scenarios[{index}]", {
                "scenario_id", "category", "input_digest", "expected_outcome", "actual_outcome",
            })
            sid = require_identifier(entry["scenario_id"], f"robustness_scenarios[{index}].scenario_id")
            if sid in scenario_ids:
                raise ValueError(f"duplicate scenario_id: {sid}")
            scenario_ids.add(sid)
            category = entry["category"]
            if category not in _ROBUSTNESS_CATEGORIES:
                raise ValueError(
                    f"robustness_scenarios[{index}].category must be one of {sorted(_ROBUSTNESS_CATEGORIES)}"
                )
            validate_digest(entry["input_digest"], f"robustness_scenarios[{index}].input_digest")
            expected = entry["expected_outcome"]
            actual = entry["actual_outcome"]
            if expected not in {"pass", "fail"}:
                raise ValueError(f"robustness_scenarios[{index}].expected_outcome must be pass or fail")
            if actual not in {"pass", "fail", "error"}:
                raise ValueError(
                    f"robustness_scenarios[{index}].actual_outcome must be pass, fail, or error"
                )
            category_counts[category] += 1
            matched = expected == actual if actual != "error" else False
            scenarios.append({
                "scenario_id": sid,
                "category": category,
                "input_digest": entry["input_digest"],
                "expected_outcome": expected,
                "actual_outcome": actual,
                "matched": matched,
            })
        ir = _exact_mapping(values["semantic IR"], "semantic IR", {"robustness_targets"})
        targets = _strings(ir["robustness_targets"], "robustness_targets", minimum=1, maximum=32)
        missing_categories = sorted(_ROBUSTNESS_CATEGORIES - set(category_counts))
        passed = sum(1 for s in scenarios if s["matched"])
        failed = len(scenarios) - passed
        decision = "PASS" if failed == 0 and not missing_categories else "BLOCKED"
        primary = {
            "schema_version": "elmos.foundry.robustness-evaluation.v1",
            "evaluation_id": evaluation_id,
            "mode": mode,
            "targets": targets,
            "scenario_count": len(scenarios),
            "passed": passed,
            "failed": failed,
            "category_coverage": dict(sorted(category_counts.items())),
            "missing_categories": missing_categories,
            "scenarios": scenarios,
            "decision": decision,
            "content_digest": canonical_digest({
                "evaluation_id": evaluation_id, "scenarios": scenarios,
            }),
        }
        return _response(_evaluation_outputs(skill, values, scope, self.catalog, primary))

    # -- skill-trigger-evaluation -------------------------------------------

    def skill_trigger_evaluation(
        self, skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str,
    ) -> Mapping[str, Any]:
        values = _values(payload)
        evaluation_id, mode = _runbook(values)
        _episodes(values)
        _policy(values, scope)
        task = _exact_mapping(values["task contract"], "task contract", {
            "purpose", "trigger_scenarios",
        })
        if task["purpose"] != scope.purpose:
            raise ValueError("trigger evaluation purpose differs from the trusted scope")
        scenarios_raw = _sequence(task["trigger_scenarios"], "trigger_scenarios", minimum=1, maximum=256)
        scenarios: list[Mapping[str, Any]] = []
        scenario_ids: set[str] = set()
        category_counts: Counter[str] = Counter()
        for index, raw in enumerate(scenarios_raw):
            entry = _exact_mapping(raw, f"trigger_scenarios[{index}]", {
                "scenario_id", "category", "query", "expected_skills", "actual_skills",
            })
            sid = require_identifier(entry["scenario_id"], f"trigger_scenarios[{index}].scenario_id")
            if sid in scenario_ids:
                raise ValueError(f"duplicate scenario_id: {sid}")
            scenario_ids.add(sid)
            category = entry["category"]
            if category not in _TRIGGER_CATEGORIES:
                raise ValueError(
                    f"trigger_scenarios[{index}].category must be one of {sorted(_TRIGGER_CATEGORIES)}"
                )
            query = _text(entry["query"], f"trigger_scenarios[{index}].query", maximum=512)
            expected = _strings(entry["expected_skills"], f"trigger_scenarios[{index}].expected_skills",
                                minimum=0, maximum=16)
            actual = _strings(entry["actual_skills"], f"trigger_scenarios[{index}].actual_skills",
                              minimum=0, maximum=16)
            category_counts[category] += 1
            expected_set = set(expected)
            actual_set = set(actual)
            if category == "should-trigger":
                correct = expected_set.issubset(actual_set) and bool(expected_set)
            elif category == "should-not-trigger":
                correct = len(actual_set) == 0
            else:
                correct = expected_set == actual_set
            false_positives = sorted(actual_set - expected_set)
            false_negatives = sorted(expected_set - actual_set)
            scenarios.append({
                "scenario_id": sid,
                "category": category,
                "query": query,
                "expected_skills": expected,
                "actual_skills": actual,
                "correct": correct,
                "false_positives": false_positives,
                "false_negatives": false_negatives,
            })
        ir = _exact_mapping(values["semantic IR"], "semantic IR", {"trigger_targets"})
        targets = _strings(ir["trigger_targets"], "trigger_targets", minimum=1, maximum=32)
        missing_categories = sorted(_TRIGGER_CATEGORIES - set(category_counts))
        passed = sum(1 for s in scenarios if s["correct"])
        failed = len(scenarios) - passed
        total_fp = sum(len(s["false_positives"]) for s in scenarios)
        total_fn = sum(len(s["false_negatives"]) for s in scenarios)
        decision = "PASS" if failed == 0 and not missing_categories else "BLOCKED"
        primary = {
            "schema_version": "elmos.foundry.trigger-evaluation.v1",
            "evaluation_id": evaluation_id,
            "mode": mode,
            "targets": targets,
            "scenario_count": len(scenarios),
            "passed": passed,
            "failed": failed,
            "false_positives": total_fp,
            "false_negatives": total_fn,
            "category_coverage": dict(sorted(category_counts.items())),
            "missing_categories": missing_categories,
            "scenarios": scenarios,
            "decision": decision,
            "content_digest": canonical_digest({
                "evaluation_id": evaluation_id, "scenarios": scenarios,
            }),
        }
        return _response(_evaluation_outputs(skill, values, scope, self.catalog, primary))


def build_evaluation_handlers(
    catalog: CatalogView, store: FoundryStore | None,
) -> dict[str, LocalHandler]:
    missing = EVALUATION_SEMANTIC_SKILLS - set(catalog.atomic_skills)
    if missing:
        raise ValueError(f"evaluation semantic Skills absent from the exact catalog: {sorted(missing)}")
    semantics = EvaluationSemantics(catalog, store)
    return {
        "skill-efficiency-evaluation": semantics.skill_efficiency_evaluation,
        "skill-output-evaluation": semantics.skill_output_evaluation,
        "skill-process-evaluation": semantics.skill_process_evaluation,
        "skill-robustness-evaluation": semantics.skill_robustness_evaluation,
        "skill-trigger-evaluation": semantics.skill_trigger_evaluation,
    }
