"""Command line interface for the repository-owned ETGB engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .evidence import create_deterministic_bundle
from .gates import evaluate_gate
from .orchestrator import build_plan, run_profile, select_cases
from .package import PACKAGE_ROOT_NAME
from .registry import SkillRegistry
from .scoring import score_results
from .validation import coverage_report, validate_package, validate_results


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"result at line {number} is not an object")
                results.append(value)
    return results


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elmos-etgb")
    parser.add_argument("--package-root", type=Path, help="immutable extracted ETGB source package")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--release", action="store_true")
    validate.add_argument("--archive", type=Path)
    validate.add_argument("--extracted", type=Path)
    sub.add_parser("coverage")
    skills = sub.add_parser("skills")
    plan = sub.add_parser("plan")
    plan.add_argument("--changed-from")
    plan.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--profile", choices=["smoke", "pr", "nightly", "weekly", "release", "golden", "exhaustive"], required=True)
    run.add_argument("--business-line")
    run.add_argument("--priority", choices=["P0", "P1", "P2"])
    run.add_argument("--case-id")
    run.add_argument("--plan", type=Path)
    run.add_argument("--limit", type=int)
    run.add_argument("--allow-unavailable", action="store_true")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--state-db", type=Path)
    run.add_argument("--artifact-root", type=Path)
    run.add_argument("--run-id")
    run.add_argument("--owner")
    run.add_argument("--resume", action="store_true")
    score = sub.add_parser("score")
    score.add_argument("results", type=Path)
    score.add_argument("--output", type=Path)
    score.add_argument("--expected-count", type=int)
    score.add_argument("--complete", action="store_true")
    gate = sub.add_parser("gate")
    gate.add_argument("results", type=Path)
    gate.add_argument("--profile", choices=["smoke", "pr", "nightly", "weekly", "release", "golden", "exhaustive"], required=True)
    gate.add_argument("--output", type=Path)
    gate.add_argument("--external-attested", action="store_true")
    gate.add_argument("--independent-verifier")
    bundle = sub.add_parser("bundle")
    bundle.add_argument("--source", type=Path, required=True)
    bundle.add_argument("--output", type=Path, required=True)
    requirement = sub.add_parser("compile-requirement")
    requirement.add_argument("text")

    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    package_root = (args.package_root or repo_root / "skills/subskills" / PACKAGE_ROOT_NAME).resolve(strict=True)
    if args.command == "validate":
        archive = args.archive.resolve() if args.archive else repo_root / "skills/subskills" / f"{PACKAGE_ROOT_NAME}.zip"
        extracted = args.extracted.resolve() if args.extracted else None
        result = validate_package(package_root, release=args.release, archive=archive if archive.exists() else None, extracted=extracted)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 2
    if args.command == "coverage":
        result = coverage_report(package_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["complete"] else 2
    if args.command == "skills":
        result = SkillRegistry(package_root).describe()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "plan":
        result = build_plan(package_root, changed_from=args.changed_from, root_for_git=repo_root)
        _write_json(args.output, result)
        print(json.dumps({"output": str(args.output), "selected": len(result["case_ids"]), "affected": result["affected_business_lines"], "plan_digest": result["plan_digest"]}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        plan_ids = None
        if args.plan:
            plan_value = json.loads(args.plan.read_text(encoding="utf-8"))
            plan_ids = set(plan_value.get("case_ids", []))
        cases = select_cases(package_root, profile=args.profile, business_line=args.business_line, priority=args.priority, case_id=args.case_id, plan_ids=plan_ids, limit=args.limit)
        results, score_value = run_profile(package_root, cases, profile=args.profile, output=args.output.resolve(), state_db=args.state_db.resolve() if args.state_db else None, artifact_root=args.artifact_root.resolve() if args.artifact_root else repo_root / ".etgb" / "evidence", allow_unavailable=args.allow_unavailable, owner=args.owner, run_id=args.run_id, resume=args.resume)
        print(json.dumps({"selected": len(cases), "results": len(results), "output": str(args.output), "score": score_value}, ensure_ascii=False, indent=2))
        return 0 if all(result["status"] in {"passed", "unavailable", "skipped"} for result in results) and (args.allow_unavailable or all(result["status"] == "passed" for result in results)) else 2
    if args.command == "score":
        results = _read_jsonl(args.results)
        errors = validate_results(results, package_root)
        if errors:
            print(json.dumps({"valid": False, "errors": errors[:50]}, ensure_ascii=False, indent=2))
            return 2
        result = score_results(results, package_root, expected_count=args.expected_count, complete=True if args.complete else None)
        if args.output:
            _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "gate":
        results = _read_jsonl(args.results)
        validation = validate_package(package_root, release=args.profile in {"release", "golden"})
        score_value = score_results(results, package_root, expected_count=len(results), complete=not any(result.get("status") in {"unavailable", "skipped"} for result in results))
        result = evaluate_gate(score=score_value, validation=validation, coverage=coverage_report(package_root), profile=args.profile, external_attested=args.external_attested, independent_verifier=args.independent_verifier)
        if args.output:
            _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["decision"] in {"PROMOTE", "READY_FOR_EXTERNAL_GATE"} else 2
    if args.command == "bundle":
        result = create_deterministic_bundle(args.source, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "compile-requirement":
        result = SkillRegistry(package_root).dispatch("project-generation-validation", "compile_requirement", {"requirement": args.text})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return 1
