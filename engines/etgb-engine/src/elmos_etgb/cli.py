"""Command line interface for the repository-owned ETGB engine."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .adapters import EXTERNAL_ADAPTERS
from .attestation import load_json_object
from .budget import estimate_machine_eta
from .candidate import freeze_candidate_file, load_spec
from .campaign import merge_release_results
from .evidence import create_deterministic_bundle
from .corpus import build_license_review_request, verify_license_reviews
from .external_harness import ExternalExecutionContext, ExternalHarnessRouter
from .orchestrator import build_plan, external_campaign_preflight, gate_profile, release_attestation_request, release_preflight, run_profile, select_cases
from .package import PACKAGE_ROOT_NAME
from .planner import build_external_canary_plan, select_plan_shard, validate_plan, validate_plan_scope
from .policy import authorize, load_document
from .registry import SkillRegistry
from .scoring import score_results
from .statistics import multi_seed_stability
from .triage import cluster_failures
from .validation import coverage_report, load_cases, validate_package, validate_results


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


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for value in values:
                handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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
    validate.add_argument("--license-reviews", type=Path)
    sub.add_parser("coverage")
    sub.add_parser("feature-coverage")
    surface_parser = sub.add_parser("surface-audit")
    surface_parser.add_argument("--surface", type=Path, required=True)
    sub.add_parser("skills")
    plan = sub.add_parser("plan")
    plan.add_argument("--changed-from")
    plan.add_argument("--history", type=Path)
    plan.add_argument("--max-cases", type=int, default=500)
    plan.add_argument("--seed", type=int, default=17)
    plan.add_argument("--shards", type=int, default=8)
    plan.add_argument("--candidate-digest")
    plan.add_argument("--profile", choices=["release", "golden"])
    plan.add_argument("--output", type=Path, required=True)
    canary_plan = sub.add_parser("canary-plan")
    canary_plan.add_argument("--candidate-digest", required=True)
    canary_plan.add_argument("--shards", type=int, default=1)
    canary_plan.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--profile", choices=["smoke", "pr", "nightly", "weekly", "release", "golden", "release-canary", "exhaustive"], required=True)
    run.add_argument("--business-line")
    run.add_argument("--priority", choices=["P0", "P1", "P2"])
    run.add_argument("--case-id")
    run.add_argument("--plan", type=Path)
    run.add_argument("--shard-id", type=int)
    run.add_argument("--limit", type=int)
    run.add_argument("--allow-unavailable", action="store_true")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--state-db", type=Path)
    run.add_argument("--artifact-root", type=Path)
    run.add_argument("--run-id")
    run.add_argument("--owner")
    run.add_argument("--resume", action="store_true")
    run.add_argument("--candidate", type=Path)
    run.add_argument("--trust-store", type=Path)
    run.add_argument("--license-reviews", type=Path)
    run.add_argument("--role-assignments", type=Path)
    run.add_argument("--production-authority", type=Path)
    run.add_argument("--harness-config", type=Path)
    run.add_argument("--tenant-id")
    run.add_argument("--project-id")
    run.add_argument("--task-id")
    run.add_argument("--environment-id")
    run.add_argument("--authority-id")
    run.add_argument("--fencing-token", type=int)
    run.add_argument("--checkpoint-digest")
    merge = sub.add_parser("merge-results")
    merge.add_argument("--plan", type=Path, required=True)
    merge.add_argument("--result", type=Path, action="append", required=True)
    merge.add_argument("--candidate-digest", required=True)
    merge.add_argument("--trust-store", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--receipt", type=Path, required=True)
    score = sub.add_parser("score")
    score.add_argument("results", type=Path)
    score.add_argument("--output", type=Path)
    score.add_argument("--expected-count", type=int)
    score.add_argument("--complete", action="store_true")
    score.add_argument("--release", action="store_true")
    score.add_argument("--trust-store", type=Path)
    score.add_argument("--license-reviews", type=Path)
    gate = sub.add_parser("gate")
    gate.add_argument("results", type=Path)
    gate.add_argument("--profile", choices=["smoke", "pr", "nightly", "weekly", "release", "golden", "exhaustive"], required=True)
    gate.add_argument("--output", type=Path)
    gate.add_argument("--external-attested", action="store_true")
    gate.add_argument("--independent-verifier")
    gate.add_argument("--attestation", type=Path)
    gate.add_argument("--trust-store", type=Path)
    gate.add_argument("--candidate-digest")
    gate.add_argument("--license-reviews", type=Path)
    gate.add_argument("--plan", type=Path)
    gate.add_argument("--role-assignments", type=Path)
    gate.add_argument("--production-authority", type=Path)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--profile", choices=["release", "golden"], default="release")
    preflight.add_argument("--results", type=Path)
    preflight.add_argument("--candidate-digest")
    preflight.add_argument("--trust-store", type=Path)
    preflight.add_argument("--license-reviews", type=Path)
    preflight.add_argument("--plan", type=Path)
    preflight.add_argument("--output", type=Path, required=True)
    review_request = sub.add_parser("corpus-review-request")
    review_request.add_argument("--output", type=Path, required=True)
    review_verify = sub.add_parser("corpus-review-verify")
    review_verify.add_argument("--records", type=Path, required=True)
    review_verify.add_argument("--trust-store", type=Path, required=True)
    review_verify.add_argument("--output", type=Path)
    attestation_request = sub.add_parser("attestation-request")
    attestation_request.add_argument("results", type=Path)
    attestation_request.add_argument("--profile", choices=["release", "golden"], default="release")
    attestation_request.add_argument("--candidate-digest", required=True)
    attestation_request.add_argument("--trust-store", type=Path)
    attestation_request.add_argument("--license-reviews", type=Path)
    attestation_request.add_argument("--plan", type=Path, required=True)
    attestation_request.add_argument("--role-assignments", type=Path, required=True)
    attestation_request.add_argument("--production-authority", type=Path, required=True)
    attestation_request.add_argument("--output", type=Path, required=True)
    harness_preflight = sub.add_parser("harness-preflight")
    harness_preflight.add_argument("--config", type=Path, required=True)
    harness_preflight.add_argument("--plan", type=Path)
    harness_preflight.add_argument("--production", action="store_true")
    harness_preflight.add_argument("--output", type=Path)
    campaign_preflight = sub.add_parser("campaign-preflight")
    campaign_preflight.add_argument("--config", type=Path, required=True)
    campaign_preflight.add_argument("--candidate", type=Path, required=True)
    campaign_preflight.add_argument("--plan", type=Path, required=True)
    campaign_preflight.add_argument("--role-assignments", type=Path, required=True)
    campaign_preflight.add_argument("--production-authority", type=Path, required=True)
    campaign_preflight.add_argument("--trust-store", type=Path, required=True)
    campaign_preflight.add_argument("--license-reviews", type=Path, required=True)
    campaign_preflight.add_argument("--tenant-id", required=True)
    campaign_preflight.add_argument("--project-id", required=True)
    campaign_preflight.add_argument("--task-id", required=True)
    campaign_preflight.add_argument("--environment-id", required=True)
    campaign_preflight.add_argument("--authority-id", required=True)
    campaign_preflight.add_argument("--owner", action="append", required=True)
    campaign_preflight.add_argument("--output", type=Path, required=True)
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
    if getattr(args, "package_root", None):
        package_root = args.package_root.resolve(strict=True)
    elif getattr(args, "extracted", None):
        package_root = args.extracted.resolve(strict=True)
    elif (repo_root / "skills" / PACKAGE_ROOT_NAME).is_dir():
        package_root = (repo_root / "skills" / PACKAGE_ROOT_NAME).resolve(strict=True)
    else:
        package_root = (repo_root / "skills/subskills" / PACKAGE_ROOT_NAME).resolve(strict=True)
    if args.command == "validate":
        archive = args.archive.resolve() if args.archive else (repo_root / "skills/subskills" / f"{PACKAGE_ROOT_NAME}.zip")
        extracted = args.extracted.resolve() if args.extracted else None
        if not archive.exists():
            archive = repo_root / "skills/subskills" / f"{PACKAGE_ROOT_NAME}.tar.gz"
        trust_store = load_json_object(args.trust_store) if getattr(args, "trust_store", None) else None
        result = validate_package(package_root, release=args.release, archive=archive if archive.exists() else None, extracted=extracted, trust_store=trust_store, license_reviews_path=args.license_reviews if args.license_reviews else None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 2
    if args.command == "coverage":
        result = coverage_report(package_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["complete"] else 2
    if args.command == "feature-coverage":
        from .features import feature_coverage_report
        result = feature_coverage_report(package_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["complete"] else 2
    if args.command == "surface-audit":
        from .discovery import load_surface, surface_coverage_report
        surface_data = load_surface(args.surface)
        result = surface_coverage_report(package_root, surface_data)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["complete"] else 2
    if args.command == "skills":
        result = SkillRegistry(package_root).describe()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "plan":
        result = build_plan(package_root, changed_from=args.changed_from, root_for_git=repo_root, history_path=args.history, max_cases=args.max_cases, seed=args.seed, shard_count=args.shards, candidate_digest=args.candidate_digest, profile=args.profile)
        _write_json(args.output, result)
        print(json.dumps({"output": str(args.output), "selected": len(result["case_ids"]), "affected": result["affected_business_lines"], "plan_digest": result["plan_digest"]}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "canary-plan":
        result = build_external_canary_plan(
            package_root,
            candidate_digest=args.candidate_digest,
            shard_count=args.shards,
        )
        _write_json(args.output, result)
        print(json.dumps({
            "output": str(args.output),
            "selected": len(result["case_ids"]),
            "required_adapters": len(result["required_adapters"]),
            "plan_digest": result["plan_digest"],
        }, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        plan_ids = None
        plan_value = None
        if args.plan:
            plan_value = load_json_object(args.plan)
            plan_errors = validate_plan_scope(package_root, plan_value) if args.profile in {"release", "golden", "release-canary"} else validate_plan(plan_value)
            if plan_errors:
                raise ValueError("invalid run plan: " + "; ".join(plan_errors))
            if plan_value.get("profile") and plan_value.get("profile") != args.profile:
                raise ValueError("run profile does not match the digest-bound plan profile")
            plan_ids = select_plan_shard(plan_value, args.shard_id) if args.shard_id is not None else set(plan_value.get("case_ids", []))
        elif args.shard_id is not None:
            raise ValueError("--shard-id requires --plan")
        case_profile = "release" if args.profile == "release-canary" else args.profile
        cases = select_cases(package_root, profile=case_profile, business_line=args.business_line, priority=args.priority, case_id=args.case_id, plan_ids=plan_ids, limit=args.limit)
        candidate = load_spec(args.candidate) if args.candidate else None
        trust_store = load_json_object(args.trust_store) if args.trust_store else None
        role_assignment = load_json_object(args.role_assignments) if args.role_assignments else None
        production_authority = load_json_object(args.production_authority) if args.production_authority else None
        external_router = None
        external_context = None
        if args.harness_config:
            required_context = {
                "--plan": args.plan,
                "--candidate": args.candidate,
                "--tenant-id": args.tenant_id,
                "--project-id": args.project_id,
                "--task-id": args.task_id,
                "--environment-id": args.environment_id,
                "--authority-id": args.authority_id,
                "--owner": args.owner,
                "--fencing-token": args.fencing_token,
                "--checkpoint-digest": args.checkpoint_digest,
            }
            if args.profile in {"release", "golden", "release-canary"}:
                required_context.update({
                    "--trust-store": args.trust_store,
                    "--license-reviews": args.license_reviews,
                    "--role-assignments": args.role_assignments,
                    "--production-authority": args.production_authority,
                })
            missing = sorted(key for key, value in required_context.items() if value is None)
            if missing:
                raise ValueError("external Harness execution requires " + ", ".join(missing))
            if not isinstance(plan_value, dict) or not isinstance(candidate, dict):
                raise ValueError("external Harness execution requires loaded plan and candidate objects")
            if plan_value.get("candidate_digest") != candidate.get("candidate_digest"):
                raise ValueError("run plan and frozen candidate digest do not match")
            external_router = ExternalHarnessRouter.load(args.harness_config)
            external_context = ExternalExecutionContext(
                tenant_id=str(args.tenant_id),
                project_id=str(args.project_id),
                task_id=str(args.task_id),
                candidate_digest=str(candidate["candidate_digest"]),
                plan_digest=str(plan_value["plan_digest"]),
                environment_id=str(args.environment_id),
                authority_id=str(args.authority_id),
                owner_id=str(args.owner),
                fencing_token=int(args.fencing_token),
                checkpoint_digest=str(args.checkpoint_digest),
            )
        results, score_value = run_profile(
            package_root,
            cases,
            profile=args.profile,
            output=args.output.resolve(),
            state_db=args.state_db.resolve() if args.state_db else None,
            artifact_root=args.artifact_root.resolve() if args.artifact_root else repo_root / ".etgb" / "evidence",
            allow_unavailable=args.allow_unavailable,
            owner=args.owner,
            run_id=args.run_id,
            resume=args.resume,
            candidate=candidate,
            external_router=external_router,
            external_context=external_context,
            trust_store=trust_store,
            license_reviews_path=args.license_reviews if args.license_reviews else None,
            plan=plan_value,
            role_assignment=role_assignment,
            production_authority=production_authority,
        )
        print(json.dumps({"selected": len(cases), "results": len(results), "output": str(args.output), "score": score_value}, ensure_ascii=False, indent=2))
        return 0 if all(result["status"] in {"passed", "unavailable", "skipped"} for result in results) and (args.allow_unavailable or all(result["status"] == "passed" for result in results)) else 2
    if args.command == "merge-results":
        plan_value = load_json_object(args.plan)
        trust_store = load_json_object(args.trust_store)
        results, receipt = merge_release_results(package_root, plan_value, args.result, candidate_digest=args.candidate_digest, trust_store=trust_store)
        _write_json(args.receipt, receipt)
        if receipt["status"] == "MERGED":
            _write_jsonl(args.output, results)
        print(json.dumps({"output": str(args.output), "receipt": str(args.receipt), **receipt}, ensure_ascii=False, indent=2))
        return 0 if receipt["status"] == "MERGED" else 2
    if args.command == "score":
        results = _read_jsonl(args.results)
        errors = validate_results(results, package_root)
        if errors:
            print(json.dumps({"valid": False, "errors": errors[:50]}, ensure_ascii=False, indent=2))
            return 2
        trust_store = load_json_object(args.trust_store) if args.trust_store else None
        result = score_results(results, package_root, expected_count=args.expected_count, complete=True if args.complete else None, corpus_release=args.release, trust_store=trust_store, license_reviews_path=args.license_reviews if args.license_reviews else None)
        if args.output:
            _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "freeze-candidate":
        result = freeze_candidate_file(args.input.resolve(), args.output.resolve())
        print(json.dumps({"output": str(args.output), "candidate_digest": result["candidate_digest"]}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "eta":
        plan = load_json_object(args.plan); ids = set(plan.get("case_ids", [])); cases = select_cases(package_root, plan_ids=ids)
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
        attestation = load_json_object(args.attestation) if args.attestation else None
        trust_store = load_json_object(args.trust_store) if args.trust_store else None
        plan_value = load_json_object(args.plan) if args.plan else None
        role_assignment = load_json_object(args.role_assignments) if args.role_assignments else None
        production_authority = load_json_object(args.production_authority) if args.production_authority else None
        result = gate_profile(package_root, results, profile=args.profile, external_attested=args.external_attested, independent_verifier=args.independent_verifier, external_attestation=attestation, trust_store=trust_store, candidate_digest=args.candidate_digest, license_reviews_path=args.license_reviews if args.license_reviews else None, plan=plan_value, role_assignment=role_assignment, production_authority=production_authority)
        if args.output:
            _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["decision"] in {"PROMOTE", "READY_FOR_EXTERNAL_GATE"} else 2
    if args.command == "preflight":
        results = _read_jsonl(args.results) if args.results else None
        trust_store = load_json_object(args.trust_store) if args.trust_store else None
        plan_value = load_json_object(args.plan) if args.plan else None
        result = release_preflight(package_root, profile=args.profile, results=results, candidate_digest=args.candidate_digest, trust_store=trust_store, license_reviews_path=args.license_reviews if args.license_reviews else None, plan=plan_value)
        _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "READY_FOR_EXTERNAL_GATE" else 2
    if args.command == "corpus-review-request":
        result = build_license_review_request(package_root)
        _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "corpus-review-verify":
        trust_store = load_json_object(args.trust_store)
        result = verify_license_reviews(package_root, release=True, trust_store=trust_store, records_path=args.records)
        if args.output:
            _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] and result["unapproved"] == 0 else 2
    if args.command == "attestation-request":
        results = _read_jsonl(args.results)
        trust_store = load_json_object(args.trust_store) if args.trust_store else None
        result = release_attestation_request(package_root, results, profile=args.profile, candidate_digest=args.candidate_digest, trust_store=trust_store, license_reviews_path=args.license_reviews if args.license_reviews else None, plan=load_json_object(args.plan), role_assignment=load_json_object(args.role_assignments), production_authority=load_json_object(args.production_authority))
        _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "READY_FOR_INDEPENDENT_VERIFICATION" else 2
    if args.command == "harness-preflight":
        plan_value = load_json_object(args.plan) if args.plan else None
        if plan_value is not None:
            plan_errors = validate_plan_scope(package_root, plan_value)
            if plan_errors:
                raise ValueError("invalid Harness preflight plan: " + "; ".join(plan_errors))
            planned_ids = set(str(value) for value in plan_value.get("case_ids", []))
        else:
            planned_ids = {str(case["id"]) for case in load_cases(package_root)}
        required_adapters = {
            str(case.get("execution", {}).get("adapter", ""))
            for case in load_cases(package_root)
            if str(case.get("id")) in planned_ids and str(case.get("execution", {}).get("adapter", "")) in EXTERNAL_ADAPTERS
        }
        production_transport = args.production or (
            plan_value is not None and plan_value.get("profile") in {"release", "golden", "release-canary"}
        )
        result = ExternalHarnessRouter.load(args.config).capability_report(
            required_adapters,
            require_production_transport=production_transport,
        )
        if args.output:
            _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "READY_FOR_EXTERNAL_EXECUTION_CONFIG" else 2
    if args.command == "campaign-preflight":
        result = external_campaign_preflight(
            package_root,
            candidate=load_spec(args.candidate),
            plan=load_json_object(args.plan),
            router=ExternalHarnessRouter.load(args.config),
            role_assignment=load_json_object(args.role_assignments),
            production_authority=load_json_object(args.production_authority),
            trust_store=load_json_object(args.trust_store),
            license_reviews_path=args.license_reviews,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            task_id=args.task_id,
            environment_id=args.environment_id,
            authority_id=args.authority_id,
            owner_ids=list(args.owner),
        )
        _write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "READY_FOR_EXTERNAL_EXECUTION" else 2
    if args.command == "bundle":
        result = create_deterministic_bundle(args.source, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "compile-requirement":
        result = SkillRegistry(package_root).dispatch("project-generation-validation", "compile_requirement", {"requirement": args.text})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return 1
