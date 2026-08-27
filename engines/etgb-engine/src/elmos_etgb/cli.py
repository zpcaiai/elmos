"""Command line interface for the repository-owned ETGB engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .attestation import load_json_object
from .budget import estimate_machine_eta
from .candidate import freeze_candidate_file, load_spec
from .evidence import create_deterministic_bundle
from .orchestrator import build_plan, gate_profile, run_profile, select_cases
from .package import PACKAGE_ROOT_NAME
from .policy import authorize, load_document
from .registry import SkillRegistry
from .scoring import score_results
from .statistics import multi_seed_stability
from .triage import cluster_failures
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
    validate.add_argument("--trust-store", type=Path)
    sub.add_parser("coverage")
    skills = sub.add_parser("skills")
    plan = sub.add_parser("plan")
    plan.add_argument("--changed-from")
    plan.add_argument("--history", type=Path)
    plan.add_argument("--max-cases", type=int, default=500)
    plan.add_argument("--seed", type=int, default=17)
    plan.add_argument("--shards", type=int, default=8)
    plan.add_argument("--candidate-digest")
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
    run.add_argument("--candidate", type=Path)
    score = sub.add_parser("score")
    score.add_argument("results", type=Path)
    score.add_argument("--output", type=Path)
    score.add_argument("--expected-count", type=int)
    score.add_argument("--complete", action="store_true")
    score.add_argument("--release", action="store_true")
    score.add_argument("--trust-store", type=Path)
    gate = sub.add_parser("gate")
    gate.add_argument("results", type=Path)
    gate.add_argument("--profile", choices=["smoke", "pr", "nightly", "weekly", "release", "golden", "exhaustive"], required=True)
    gate.add_argument("--output", type=Path)
    gate.add_argument("--external-attested", action="store_true")
    gate.add_argument("--independent-verifier")
    gate.add_argument("--attestation", type=Path)
    gate.add_argument("--trust-store", type=Path)
    gate.add_argument("--candidate-digest")
    freeze = sub.add_parser("freeze-candidate")
    freeze.add_argument("input", type=Path)
    freeze.add_argument("--output", type=Path, required=True)
    eta = sub.add_parser("eta")
    eta.add_argument("plan", type=Path)
    eta.add_argument("--history", type=Path)
    eta.add_argument("--concurrency", type=int, default=3)
    eta.add_argument("--output", type=Path)
    triage = sub.add_parser("triage")
    triage.add_argument("results", type=Path)
    triage.add_argument("--output", type=Path)
    stability = sub.add_parser("stability")
    stability.add_argument("results", type=Path)
    stability.add_argument("--output", type=Path)
    materialize = sub.add_parser("materialize")
    materialize.add_argument("--output", type=Path)
    policy = sub.add_parser("authorize")
    policy.add_argument("authority", type=Path)
    policy.add_argument("request", type=Path)
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
        if not archive.exists():
            archive = repo_root / "skills/subskills" / f"{PACKAGE_ROOT_NAME}.tar.gz"
        trust_store = load_json_object(args.trust_store.resolve()) if getattr(args, "trust_store", None) else None
        result = validate_package(package_root, release=args.release, archive=archive if archive.exists() else None, extracted=extracted, trust_store=trust_store)
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
        result = build_plan(package_root, changed_from=args.changed_from, root_for_git=repo_root, history_path=args.history, max_cases=args.max_cases, seed=args.seed, shard_count=args.shards, candidate_digest=args.candidate_digest)
        _write_json(args.output, result)
        print(json.dumps({"output": str(args.output), "selected": len(result["case_ids"]), "affected": result["affected_business_lines"], "plan_digest": result["plan_digest"]}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        plan_ids = None
        if args.plan:
            plan_value = json.loads(args.plan.read_text(encoding="utf-8"))
            plan_ids = set(plan_value.get("case_ids", []))
        cases = select_cases(package_root, profile=args.profile, business_line=args.business_line, priority=args.priority, case_id=args.case_id, plan_ids=plan_ids, limit=args.limit)
        candidate = load_spec(args.candidate.resolve()) if args.candidate else None
        results, score_value = run_profile(package_root, cases, profile=args.profile, output=args.output.resolve(), state_db=args.state_db.resolve() if args.state_db else None, artifact_root=args.artifact_root.resolve() if args.artifact_root else repo_root / ".etgb" / "evidence", allow_unavailable=args.allow_unavailable, owner=args.owner, run_id=args.run_id, resume=args.resume, candidate=candidate)
        print(json.dumps({"selected": len(cases), "results": len(results), "output": str(args.output), "score": score_value}, ensure_ascii=False, indent=2))
        return 0 if all(result["status"] in {"passed", "unavailable", "skipped"} for result in results) and (args.allow_unavailable or all(result["status"] == "passed" for result in results)) else 2
    if args.command == "score":
        results = _read_jsonl(args.results)
        errors = validate_results(results, package_root)
        if errors:
            print(json.dumps({"valid": False, "errors": errors[:50]}, ensure_ascii=False, indent=2))
            return 2
        trust_store = load_json_object(args.trust_store.resolve()) if args.trust_store else None
        result = score_results(results, package_root, expected_count=args.expected_count, complete=True if args.complete else None, corpus_release=args.release, trust_store=trust_store)
        if args.output:
            _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "freeze-candidate":
        result = freeze_candidate_file(args.input.resolve(), args.output.resolve())
        print(json.dumps({"output": str(args.output), "candidate_digest": result["candidate_digest"]}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "eta":
        plan = json.loads(args.plan.read_text(encoding="utf-8")); ids = set(plan.get("case_ids", [])); cases = select_cases(package_root, plan_ids=ids)
        history = _read_jsonl(args.history) if args.history else []
        result = estimate_machine_eta(cases, history, concurrency=args.concurrency)
        if args.output: _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "triage":
        result = cluster_failures(_read_jsonl(args.results))
        if args.output: _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "stability":
        result = multi_seed_stability(_read_jsonl(args.results))
        if args.output: _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "materialize":
        from .materializer import materialize as check_materialization
        result = check_materialization(package_root)
        if args.output: _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "authorize":
        decision = authorize(load_document(args.authority.resolve()), load_document(args.request.resolve()))
        result = decision.as_dict(); print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if decision.allowed else 2
    if args.command == "gate":
        results = _read_jsonl(args.results)
        attestation = load_json_object(args.attestation.resolve()) if args.attestation else None
        trust_store = load_json_object(args.trust_store.resolve()) if args.trust_store else None
        result = gate_profile(package_root, results, profile=args.profile, external_attested=args.external_attested, independent_verifier=args.independent_verifier, external_attestation=attestation, trust_store=trust_store, candidate_digest=args.candidate_digest)
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
