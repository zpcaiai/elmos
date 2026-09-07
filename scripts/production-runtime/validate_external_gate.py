#!/usr/bin/env python3
"""Validate the external-gate plan without contacting any external system."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from external_gate_contract import ContractError, load_object, preflight, validate_plan


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=ROOT / "docs/production-runtime/EXTERNAL-GATE-PLAN.json")
    parser.add_argument("--strict-ready", action="store_true", help="fail unless every external binding is executable")
    args = parser.parse_args()
    plan_path = args.plan if args.plan.is_absolute() else ROOT / args.plan
    try:
        plan = load_object(plan_path)
        validate_plan(plan, ROOT)
        blockers = preflight(plan, ROOT)
        result = {
            "status": "READY_FOR_EXTERNAL_GATE" if not blockers else "EXTERNAL_GATE_BLOCKED",
            "plan": str(plan_path),
            "source_archive_sha256": plan["package"]["archive_sha256"],
            "external_status": {operation: "NOT_RUN" for operation in plan["operations"]},
            "production_certification": "NOT_CERTIFIED",
            "blockers": blockers,
        }
    except (ContractError, OSError, ValueError, KeyError) as exc:
        print(f"production-runtime external gate plan: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict_ready and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
