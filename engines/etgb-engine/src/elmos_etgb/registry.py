"""Exact ten-Skill registry and narrow operation dispatch."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from .campaigns import metamorphic_relation, mutation_summary, property_campaign
from .contracts import compile_requirement, validate_domain_case
from .corpus import verify_lock
from .oracles import compare_json, compare_trace
from .orchestrator import build_plan, gate_profile, run_profile, select_cases
from .scoring import score_results
from .validation import coverage_report, load_cases, validate_package, validate_results


@dataclass(frozen=True)
class SkillDescriptor:
    name: str
    description: str
    dependencies: tuple[str, ...]


class SkillRegistry:
    def __init__(self, package_root: Path) -> None:
        self.package_root = package_root.resolve(strict=True)
        manifest = yaml.safe_load((self.package_root / "skills/manifest.yaml").read_text(encoding="utf-8"))
        self._skills = {
            item["name"]: SkillDescriptor(item["name"], item.get("description", ""), tuple(item.get("depends_on", [])))
            for item in manifest.get("skills", [])
        }
        self._operations: dict[str, tuple[str, ...]] = {
            "etgb-orchestrator": ("plan", "run", "score", "gate"),
            "test-case-authoring": ("validate", "coverage", "materialized"),
            "spring-modernization-validation": ("validate_case", "capability"),
            "repository-translation-validation": ("validate_case", "capability"),
            "project-generation-validation": ("compile_requirement", "validate_case", "capability"),
            "sql-dialect-routine-validation": ("validate_case", "capability"),
            "differential-oracle-engine": ("compare_json", "compare_trace"),
            "metamorphic-fuzz-mutation": ("property_campaign", "metamorphic", "mutation_summary"),
            "corpus-governance": ("verify",),
            "release-certification": ("gate",),
        }

    @property
    def skills(self) -> tuple[SkillDescriptor, ...]:
        return tuple(self._skills[name] for name in sorted(self._skills))

    def describe(self) -> list[dict[str, Any]]:
        return [{"name": skill.name, "description": skill.description, "depends_on": list(skill.dependencies), "operations": list(self._operations.get(skill.name, ())), "runtime_state": "BOUND"} for skill in self.skills]

    def dispatch(self, skill: str, operation: str, payload: Mapping[str, Any] | None = None) -> Any:
        if skill not in self._skills:
            raise KeyError(f"unknown ETGB skill: {skill}")
        if operation not in self._operations.get(skill, ()):
            raise ValueError(f"operation '{operation}' is not allowed for {skill}")
        payload = dict(payload or {})
        if operation == "validate":
            return validate_package(self.package_root, release=bool(payload.get("release")))
        if operation == "coverage":
            return coverage_report(self.package_root)
        if operation == "materialized":
            return {"case_count": sum(1 for _ in load_cases(self.package_root)), "coverage": coverage_report(self.package_root)}
        if operation == "verify":
            return verify_lock(self.package_root, release=bool(payload.get("release")))
        if operation == "compile_requirement":
            return compile_requirement(payload.get("requirement", ""), contract_id=str(payload.get("contract_id", "REQ-ETGB")))
        if operation == "validate_case":
            case = payload.get("case")
            if not isinstance(case, Mapping):
                raise ValueError("case must be an object")
            errors = validate_domain_case(case)
            return {"valid": not errors, "errors": errors}
        if operation == "capability":
            return {"skill": skill, "status": "EXTERNAL_ADAPTER_REQUIRED", "claimable": False, "reason": "real source/target runtime evidence is not provided by the offline package"}
        if operation == "compare_json":
            return compare_json(payload.get("left"), payload.get("right"), ignore_paths=payload.get("ignore_paths", []), unordered_paths=payload.get("unordered_paths", []), absolute_tolerance=float(payload.get("absolute_tolerance", 0.0)), relative_tolerance=float(payload.get("relative_tolerance", 0.0)))
        if operation == "compare_trace":
            return compare_trace(list(payload.get("left", [])), list(payload.get("right", [])), happens_before=payload.get("happens_before", []))
        if operation == "property_campaign":
            return {"status": "requires_callable", "claimable": False, "reason": "callables cannot cross the JSON dispatch boundary"}
        if operation == "metamorphic":
            return metamorphic_relation(str(payload.get("name", "unnamed")), payload.get("left"), payload.get("right"), relation=lambda left, right: left == right)
        if operation == "mutation_summary":
            return mutation_summary(list(payload.get("mutants", [])), [bool(value) for value in payload.get("killed", [])])
        if operation == "plan":
            repo_root = Path(str(payload.get("repo_root", self.package_root.parents[2])))
            return build_plan(self.package_root, changed_from=payload.get("changed_from"), root_for_git=repo_root)
        if operation == "run":
            profile = str(payload.get("profile", "smoke"))
            output_value = payload.get("output")
            if not output_value:
                raise ValueError("run requires an explicit output path")
            plan_ids = set(str(case_id) for case_id in payload.get("case_ids", [])) or None
            cases = select_cases(
                self.package_root,
                profile=profile,
                business_line=payload.get("business_line"),
                priority=payload.get("priority"),
                case_id=payload.get("case_id"),
                plan_ids=plan_ids,
                limit=int(payload["limit"]) if payload.get("limit") is not None else None,
            )
            results, score = run_profile(
                self.package_root,
                cases,
                profile=profile,
                output=Path(str(output_value)).resolve(),
                state_db=Path(str(payload["state_db"])).resolve() if payload.get("state_db") else None,
                artifact_root=Path(str(payload["artifact_root"])).resolve() if payload.get("artifact_root") else None,
                allow_unavailable=bool(payload.get("allow_unavailable")),
                owner=payload.get("owner"),
                run_id=payload.get("run_id"),
                resume=bool(payload.get("resume")),
            )
            return {"selected": len(cases), "results": results, "score": score}
        if operation == "score":
            results = payload.get("results")
            if results is None and payload.get("results_path"):
                results = [json.loads(line) for line in Path(str(payload["results_path"])).read_text(encoding="utf-8").splitlines() if line.strip()]
            if not isinstance(results, list) or not all(isinstance(result, Mapping) for result in results):
                raise ValueError("score requires a results list or results_path")
            result_list = [dict(result) for result in results]
            errors = validate_results(result_list, self.package_root)
            if errors:
                raise ValueError(f"invalid results: {errors[:3]}")
            return score_results(result_list, self.package_root, expected_count=int(payload["expected_count"]) if payload.get("expected_count") is not None else None, complete=bool(payload["complete"]) if "complete" in payload else None)
        if operation == "gate":
            results = payload.get("results")
            if results is None and payload.get("results_path"):
                results = [json.loads(line) for line in Path(str(payload["results_path"])).read_text(encoding="utf-8").splitlines() if line.strip()]
            if not isinstance(results, list) or not all(isinstance(result, Mapping) for result in results):
                raise ValueError("gate requires a results list or results_path")
            return gate_profile(self.package_root, [dict(result) for result in results], profile=str(payload.get("profile", "release")), external_attested=bool(payload.get("external_attested")), independent_verifier=payload.get("independent_verifier"))
        raise AssertionError(operation)
