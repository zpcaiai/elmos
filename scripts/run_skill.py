#!/usr/bin/env python3
"""ELMOS Universal Skill Execution CLI.

Provides unified discovery, inspection, and execution dispatching for all
declared and implemented Skills across the repository.

Adheres strictly to the Non-Self-Certification Contract:
- All generated receipts are marked LOCAL_EXECUTED_SELF_ATTESTED.
- External evidence remains NOT_RUN.
- External certification status remains NOT_CERTIFIED.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure proof-driven-harness-engine is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS_SRC = REPO_ROOT / "engines" / "proof-driven-harness-engine" / "src"
if str(HARNESS_SRC) not in sys.path:
    sys.path.insert(0, str(HARNESS_SRC))

from elmos_proof_harness.skill_execution_runtime import (
    ExecutionMode,
    SkillCatalog,
    SkillExecutionRuntime,
)


def cmd_list(catalog: SkillCatalog, args: argparse.Namespace) -> None:
    skills = catalog.list_skills(
        pattern=args.pattern,
        status=args.status,
        engine=args.engine,
        limit=args.limit,
    )
    print(f"Found {len(skills)} skills (total catalog: {catalog.total_count}):")
    for s in skills:
        status_tag = f"[{s.implementation_status.value}]"
        engine_tag = f"({s.bound_engine})" if s.bound_engine else ""
        print(f"  {status_tag:11} {s.name:<45} {engine_tag:<26} -> {s.path}")


def cmd_info(catalog: SkillCatalog, args: argparse.Namespace) -> None:
    skill = catalog.get_skill(args.skill_name)
    if not skill:
        print(f"Error: Skill '{args.skill_name}' not found.", file=sys.stderr)
        sys.exit(1)
    
    print(json.dumps(skill.to_dict(), indent=2, ensure_ascii=False))


def cmd_summary(catalog: SkillCatalog, args: argparse.Namespace) -> None:
    catalog.load()
    total = catalog.total_count
    status_counts = {}
    engine_counts = {}
    for s in catalog.list_skills(limit=100000):
        st = s.implementation_status.value
        status_counts[st] = status_counts.get(st, 0) + 1
        eng = s.bound_engine or "unbound"
        engine_counts[eng] = engine_counts.get(eng, 0) + 1

    summary = {
        "total_skills": total,
        "status_distribution": status_counts,
        "engine_distribution": engine_counts,
        "non_self_certification": {
            "local_grade": "LOCAL_EXECUTED_SELF_ATTESTED",
            "external_evidence": "NOT_RUN",
            "external_certification": "NOT_CERTIFIED",
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def cmd_run(runtime: SkillExecutionRuntime, args: argparse.Namespace) -> None:
    payload = {}
    if args.input_file:
        path = Path(args.input_file)
        if not path.is_file():
            print(f"Error: input file {path} not found.", file=sys.stderr)
            sys.exit(1)
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif args.input_json:
        payload = json.loads(args.input_json)

    mode = ExecutionMode.EXECUTE
    if args.dry_run:
        mode = ExecutionMode.DRY_RUN
    elif args.check_readiness:
        mode = ExecutionMode.CHECK_READINESS

    receipt = runtime.execute(args.skill_name, payload=payload, mode=mode)
    
    output_json = json.dumps(receipt.to_dict(), indent=2, ensure_ascii=False)
    print(output_json)

    if args.output:
        out_path = Path(args.output)
        receipt.save_to(out_path)
        print(f"\n[RECEIPT SAVED] -> {out_path}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ELMOS Universal Skill Execution CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List skills in catalog")
    p_list.add_argument("--pattern", "-p", help="Filter by name/description pattern")
    p_list.add_argument("--status", "-s", choices=["LOCAL", "PARTIAL", "DECLARED"], help="Filter by implementation status")
    p_list.add_argument("--engine", "-e", help="Filter by bound engine")
    p_list.add_argument("--limit", "-n", type=int, default=50, help="Max results to display")

    # info
    p_info = subparsers.add_parser("info", help="Show skill metadata")
    p_info.add_argument("skill_name", help="Name or alias of the skill")

    # summary
    subparsers.add_parser("summary", help="Show catalog summary statistics")

    # run
    p_run = subparsers.add_parser("run", help="Execute or dry-run a skill")
    p_run.add_argument("skill_name", help="Name of the skill to execute")
    p_run.add_argument("--input-json", "-j", help="JSON string of payload arguments")
    p_run.add_argument("--input-file", "-f", help="Path to JSON file containing payload")
    p_run.add_argument("--dry-run", action="store_true", help="Perform dry-run contract check")
    p_run.add_argument("--check-readiness", action="store_true", help="Perform environment readiness check")
    p_run.add_argument("--output", "-o", help="Optional path to save JSON execution receipt")

    args = parser.parse_args()

    runtime = SkillExecutionRuntime(REPO_ROOT)
    catalog = runtime.catalog

    if args.command == "list":
        cmd_list(catalog, args)
    elif args.command == "info":
        cmd_info(catalog, args)
    elif args.command == "summary":
        cmd_summary(catalog, args)
    elif args.command == "run":
        cmd_run(runtime, args)


if __name__ == "__main__":
    main()
