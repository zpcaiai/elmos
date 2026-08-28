from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from etgb.coverage import coverage_report
from etgb.io import iter_cases, iter_jsonl, package_root, write_json, write_jsonl
from etgb.materializer import materialize
from etgb.planner import build_plan
from etgb.runner import run_cases
from etgb.scoring import score_results
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
    parser = argparse.ArgumentParser(prog="etgb", description="Elmos ETGB benchmark CLI")
    parser.add_argument("--root", type=Path, default=package_root())
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate schemas, IDs, corpus pins and package integrity")
    p.add_argument("--release", action="store_true", help="treat unapproved corpus licenses as errors")

    sub.add_parser("coverage", help="verify 100% coverage of the declared matrix")
    sub.add_parser("materialize", help="regenerate concrete JSONL cases from matrices")

    p = sub.add_parser("run", help="execute selected cases")
    p.add_argument("--profile", choices=["smoke","pr","nightly","weekly","release","golden","exhaustive"])
    p.add_argument("--business-line")
    p.add_argument("--priority", choices=["P0","P1","P2"])
    p.add_argument("--case-id")
    p.add_argument("--plan", type=Path)
    p.add_argument("--limit", type=int)
    p.add_argument("--allow-unavailable", action="store_true")
    p.add_argument("--output", type=Path, required=True)

    p = sub.add_parser("score", help="score JSONL run results")
    p.add_argument("results", type=Path)
    p.add_argument("--output", type=Path)

    p = sub.add_parser("plan", help="select affected P0 cases from changed files")
    p.add_argument("--changed-from")
    p.add_argument("--output", type=Path, required=True)

    p = sub.add_parser("list", help="list cases")
    p.add_argument("--profile")
    p.add_argument("--business-line")
    p.add_argument("--priority")
    p.add_argument("--case-id")
    p.add_argument("--limit", type=int, default=20)

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
    if args.command == "materialize":
        _print(materialize(root))
        return 0
    if args.command == "run":
        cases = _select_cases(root, args)
        results = run_cases(cases, root, allow_unavailable=args.allow_unavailable)
        write_jsonl(args.output, results)
        _print({"selected": len(cases), "output": str(args.output), "statuses": {s: sum(1 for r in results if r['status'] == s) for s in sorted({r['status'] for r in results})}})
        return 0 if all(r["status"] in {"passed","skipped","unavailable"} for r in results) else 2
    if args.command == "score":
        results = list(iter_jsonl(args.results))
        score = score_results(results, root)
        if args.output:
            write_json(args.output, score)
        _print(score)
        return 0
    if args.command == "plan":
        plan = build_plan(root, args.changed_from)
        write_json(args.output, plan)
        _print({"output": str(args.output), "selected": len(plan["case_ids"]), "affected": plan["affected_business_lines"]})
        return 0
    if args.command == "list":
        cases = _select_cases(root, args)
        _print([{"id": c["id"], "line": c["business_line"], "priority": c["priority"], "title": c["title"]} for c in cases])
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
