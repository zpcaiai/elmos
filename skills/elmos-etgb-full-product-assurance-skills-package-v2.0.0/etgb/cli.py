from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from etgb.budget import estimate_machine_eta
from etgb.candidate import freeze_candidate_file
from etgb.checkpoint import CheckpointStore
from etgb.coverage import coverage_report
from etgb.evidence import EvidenceStore
from etgb.discovery import load_surface, surface_coverage_report
from etgb.features import feature_coverage_report
from etgb.gates import evaluate_gate_files
from etgb.io import iter_cases, iter_jsonl, package_root, write_json, write_jsonl
from etgb.materializer import materialize
from etgb.planner import build_plan
from etgb.policy import authorize, load_document
from etgb.runner import run_cases
from etgb.scoring import score_results
from etgb.skills import audit_skills
from etgb.statistics import multi_seed_stability
from etgb.triage import cluster_failures
from etgb.validation import validate_package


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _select_cases(root: Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    plan_ids: set[str] | None = None
    if getattr(args, "plan", None):
        plan_ids = set(json.loads(Path(args.plan).read_text(encoding="utf-8"))["case_ids"])
    selected = []
    for case in iter_cases(root):
        if plan_ids is not None and case["id"] not in plan_ids:
            continue
        if getattr(args, "profile", None) and args.profile not in case["profiles"]:
            continue
        if getattr(args, "business_line", None) and case["business_line"] != args.business_line:
            continue
        if getattr(args, "priority", None) and case["priority"] != args.priority:
            continue
        if getattr(args, "case_id", None) and case["id"] != args.case_id:
            continue
        selected.append(case)
        if getattr(args, "limit", None) and len(selected) >= args.limit:
            break
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="etgb", description="Elmos ETGB benchmark and control-plane reference CLI")
    parser.add_argument("--root", type=Path, default=package_root())
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate schemas, IDs, corpus pins, Skills, and package integrity")
    p.add_argument("--release", action="store_true", help="treat unapproved corpus licenses as errors")

    sub.add_parser("coverage", help="verify 100% coverage of the declared matrix")
    p = sub.add_parser("feature-coverage", help="verify every product feature is bound to concrete cases and the correct adapter")
    p.add_argument("--output", type=Path)

    p = sub.add_parser("surface-audit", help="detect implemented routes/actions/jobs/events without governed feature bindings")
    p.add_argument("surface", type=Path)
    p.add_argument("--output", type=Path)
    sub.add_parser("materialize", help="regenerate concrete JSONL cases from matrices")
    sub.add_parser("skills-audit", help="validate Skill files, dependency graph, and manifest")

    p = sub.add_parser("run", help="execute selected cases")
    p.add_argument("--profile", choices=["smoke", "pr", "nightly", "weekly", "release", "golden", "exhaustive"])
    p.add_argument("--business-line")
    p.add_argument("--priority", choices=["P0", "P1", "P2"])
    p.add_argument("--case-id")
    p.add_argument("--plan", type=Path)
    p.add_argument("--limit", type=int)
    p.add_argument("--allow-unavailable", action="store_true")
    p.add_argument("--output", type=Path, required=True)

    p = sub.add_parser("score", help="score JSONL run results")
    p.add_argument("results", type=Path)
    p.add_argument("--output", type=Path)

    p = sub.add_parser("plan", help="create immutable risk-based affected-case plan")
    p.add_argument("--changed-from")
    p.add_argument("--history", type=Path)
    p.add_argument("--max-cases", type=int, default=500)
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--shards", type=int, default=8)
    p.add_argument("--candidate-digest")
    p.add_argument("--output", type=Path, required=True)

    p = sub.add_parser("list", help="list cases")
    p.add_argument("--profile")
    p.add_argument("--business-line")
    p.add_argument("--priority")
    p.add_argument("--case-id")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("freeze-candidate", help="freeze a release candidate and compute its immutable digest")
    p.add_argument("input", type=Path)
    p.add_argument("--output", type=Path, required=True)

    p = sub.add_parser("gate", help="evaluate release gates from a score report")
    p.add_argument("score", type=Path)
    p.add_argument("--gates", type=Path)
    p.add_argument("--waivers", type=Path)
    p.add_argument("--output", type=Path)

    p = sub.add_parser("evidence-verify", help="verify an ETGB evidence bundle")
    p.add_argument("bundle", type=Path)
    p.add_argument("--hmac-key-file", type=Path)

    p = sub.add_parser("policy-check", help="authorize a tool request against environment/attachment authority")
    p.add_argument("authority", type=Path)
    p.add_argument("request", type=Path)

    p = sub.add_parser("checkpoint-verify", help="verify checkpoint integrity and resume compatibility")
    p.add_argument("directory", type=Path)
    p.add_argument("run_id")
    p.add_argument("--candidate-digest")
    p.add_argument("--plan-digest")
    p.add_argument("--minimum-fencing-token", type=int)

    p = sub.add_parser("eta", help="estimate Elmos machine wall-clock, tokens, and credits for a plan")
    p.add_argument("plan", type=Path)
    p.add_argument("--history", type=Path)
    p.add_argument("--concurrency", type=int, default=3)
    p.add_argument("--output", type=Path)

    p = sub.add_parser("triage", help="cluster failures into stable root-cause signatures")
    p.add_argument("results", type=Path)
    p.add_argument("--output", type=Path)

    p = sub.add_parser("stability", help="calculate multi-seed stability and confidence intervals")
    p.add_argument("results", type=Path)
    p.add_argument("--minimum-seeds", type=int, default=3)
    p.add_argument("--output", type=Path)

    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    if args.command == "validate":
        result = validate_package(root, release=args.release)
        _print(result)
        return 0 if result["valid"] else 2
    if args.command == "coverage":
        result = coverage_report(root)
        _print(result)
        return 0 if result["complete"] else 2
    if args.command == "feature-coverage":
        result = feature_coverage_report(root)
        if args.output:
            write_json(args.output, result)
        _print({k: v for k, v in result.items() if k != "bindings"})
        return 0 if result["complete"] else 2
    if args.command == "surface-audit":
        result = surface_coverage_report(root, load_surface(args.surface))
        if args.output:
            write_json(args.output, result)
        _print(result)
        return 0 if result["complete"] else 2
    if args.command == "skills-audit":
        result = audit_skills(root)
        _print(result)
        return 0 if result["valid"] else 2
    if args.command == "materialize":
        _print(materialize(root))
        return 0
    if args.command == "run":
        cases = _select_cases(root, args)
        results = run_cases(cases, root, allow_unavailable=args.allow_unavailable)
        write_jsonl(args.output, results)
        _print(
            {
                "selected": len(cases),
                "output": str(args.output),
                "statuses": {
                    status: sum(1 for result in results if result["status"] == status)
                    for status in sorted({result["status"] for result in results})
                },
            }
        )
        return 0 if all(result["status"] in {"passed", "skipped", "unavailable"} for result in results) else 2
    if args.command == "score":
        results = list(iter_jsonl(args.results))
        score = score_results(results, root)
        if args.output:
            write_json(args.output, score)
        _print(score)
        return 0
    if args.command == "plan":
        plan = build_plan(
            root,
            args.changed_from,
            history_path=args.history,
            max_cases=args.max_cases,
            seed=args.seed,
            shard_count=args.shards,
            candidate_digest=args.candidate_digest,
        )
        write_json(args.output, plan)
        _print(
            {
                "output": str(args.output),
                "selected": len(plan["case_ids"]),
                "affected": plan["affected_business_lines"],
                "plan_digest": plan["plan_digest"],
            }
        )
        return 0
    if args.command == "list":
        cases = _select_cases(root, args)
        _print(
            [
                {"id": case["id"], "line": case["business_line"], "priority": case["priority"], "title": case["title"]}
                for case in cases
            ]
        )
        return 0
    if args.command == "freeze-candidate":
        frozen = freeze_candidate_file(args.input, args.output)
        _print(frozen)
        return 0
    if args.command == "gate":
        gate_path = args.gates or root / "matrices/release-gates.yaml"
        result = evaluate_gate_files(args.score, gate_path, waivers_path=args.waivers)
        if args.output:
            write_json(args.output, result)
        _print(result)
        return 0 if result["decision"] in {"PROMOTE", "PROMOTE_WITH_WAIVER"} else 2
    if args.command == "evidence-verify":
        key = args.hmac_key_file.read_bytes().strip() if args.hmac_key_file else None
        result = EvidenceStore(args.bundle, hmac_key=key).verify()
        _print(result)
        return 0 if result["valid"] else 2
    if args.command == "policy-check":
        decision = authorize(load_document(args.authority), load_document(args.request))
        _print(decision.as_dict())
        return 0 if decision.allowed else 2
    if args.command == "checkpoint-verify":
        result = CheckpointStore(args.directory).verify(
            args.run_id,
            candidate_digest=args.candidate_digest,
            plan_digest=args.plan_digest,
            minimum_fencing_token=args.minimum_fencing_token,
        )
        _print(result)
        return 0 if result["valid"] else 2
    if args.command == "eta":
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        ids = set(plan["case_ids"])
        cases = [case for case in iter_cases(root) if case["id"] in ids]
        history = list(iter_jsonl(args.history)) if args.history and args.history.exists() else []
        result = estimate_machine_eta(cases, history, concurrency=args.concurrency)
        if args.output:
            write_json(args.output, result)
        _print(result)
        return 0
    if args.command == "triage":
        result = cluster_failures(iter_jsonl(args.results))
        if args.output:
            write_json(args.output, result)
        _print(result)
        return 0
    if args.command == "stability":
        result = multi_seed_stability(iter_jsonl(args.results), minimum_seeds=args.minimum_seeds)
        if args.output:
            write_json(args.output, result)
        _print(result)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
