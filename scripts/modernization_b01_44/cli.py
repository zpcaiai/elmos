#!/usr/bin/env python3
"""Command line entry point for the Batch 01-44 modernization runtime.

    python3 -m scripts.modernization_b01_44.cli packages
    python3 -m scripts.modernization_b01_44.cli run --batches 1-44 --scope svc-a
    python3 -m scripts.modernization_b01_44.cli gate --batch 9 --status certified
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Iterable

from scripts.modernization_b01_44.canonical import format_instant
from scripts.modernization_b01_44.errors import RuntimeRefusal
from scripts.modernization_b01_44.orchestrator import (
    ChainRunner,
    Platform,
    default_platform,
    standard_corpus,
)
from scripts.modernization_b01_44.packages import load_registry
from scripts.modernization_b01_44.policy import Principal


def parse_batches(spec: str) -> list[int]:
    batches: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            low, _, high = part.partition("-")
            batches.extend(range(int(low), int(high) + 1))
        else:
            batches.append(int(part))
    return sorted(set(batches))


def cmd_packages(args: argparse.Namespace) -> int:
    registry = load_registry(args.root)
    report = {
        "root": str(registry.root),
        "batches": len(registry),
        "complete": registry.complete_batches(),
        "incomplete": {str(k): list(v) for k, v in registry.incomplete_batches().items()},
        "skills": {
            str(pkg.batch): sorted({skill.name for skill in pkg.skills.values()})
            for pkg in registry
        },
        "verified_files": {str(pkg.batch): pkg.verified_files for pkg in registry},
    }
    if args.summary:
        print(f"root:     {registry.root}")
        print(f"batches:  {len(registry)}")
        print(f"complete: {len(registry.complete_batches())}/{len(registry)}")
        for pkg in registry:
            state = "ok" if pkg.complete else f"{len(pkg.problems)} problems"
            print(
                f"  b{pkg.batch:02d} {pkg.slug[:44]:<44} "
                f"skills={len({s.name for s in pkg.skills.values()}):<3} "
                f"files={pkg.verified_files:<4} {state}"
            )
        return 0 if not registry.incomplete_batches() else 1
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0 if not registry.incomplete_batches() else 1


def cmd_run(args: argparse.Namespace) -> int:
    platform = default_platform(args.root)
    now = datetime.now(timezone.utc) if args.now is None else datetime.fromisoformat(args.now)
    assets = args.assets.split(",") if args.assets else ["alpha", "beta", "gamma"]
    principal = Principal(args.principal, args.tenant, "human")
    try:
        results = ChainRunner(platform).run(
            parse_batches(args.batches),
            principal=principal,
            tenant_id=args.tenant,
            project_id=args.project,
            scope=args.scope,
            now=now,
            requested_status=args.status,
            corpus=standard_corpus(args.scope, assets=assets),
            options={"assets": assets},
        )
    except RuntimeRefusal as exc:
        json.dump({"refused": exc.as_record()}, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 1

    payload = {
        "executed_at": format_instant(now),
        "scope": args.scope,
        "batches": [
            {
                "batch": r.batch,
                "status": r.status,
                "certificate": r.certificate.as_dict() if r.certificate else None,
                "decision": r.decision.as_dict() if r.decision else None,
                "output_digest": r.output_digest,
                "evidence_refs": list(r.evidence_refs),
                "limitations": list(r.limitations),
            }
            for r in results
        ],
        "totals": {
            "batches": len(results),
            "certificates": len(platform.certificates),
            "evidence": len(platform.evidence),
            "workflows": len(platform.workflows),
        },
    }
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    platform = default_platform(args.root)
    gate = platform.gate(args.batch)
    decision = gate.evaluate(
        requested_status=args.status,
        scope=args.scope,
        evidence_refs=args.evidence or [],
        now=datetime.now(timezone.utc),
    )
    json.dump(decision.as_dict(), sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0 if decision.granted_status not in ("blocked", "revoked") else 1


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="modernization-b01-44", description=__doc__)
    parser.add_argument("--root", default=None, help="skill pack root")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pkg = sub.add_parser("packages", help="load and verify every Batch package")
    p_pkg.add_argument("--summary", action="store_true")
    p_pkg.set_defaults(func=cmd_packages)

    p_run = sub.add_parser("run", help="execute a Batch chain end to end")
    p_run.add_argument("--batches", default="1-44")
    p_run.add_argument("--tenant", default="tenant-a")
    p_run.add_argument("--project", default="proj-1")
    p_run.add_argument("--scope", default="svc-a")
    p_run.add_argument("--assets", default=None, help="comma separated asset list")
    p_run.add_argument("--principal", default="cli-user")
    p_run.add_argument("--status", default="limited")
    p_run.add_argument("--now", default=None, help="ISO-8601 instant, defaults to now")
    p_run.set_defaults(func=cmd_run)

    p_gate = sub.add_parser("gate", help="evaluate the certification gate")
    p_gate.add_argument("--batch", type=int, required=True)
    p_gate.add_argument("--scope", default="svc-a")
    p_gate.add_argument("--status", default="certified")
    p_gate.add_argument("--evidence", nargs="*")
    p_gate.set_defaults(func=cmd_gate)

    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
