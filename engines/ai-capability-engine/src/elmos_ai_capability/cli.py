"""Command line interface for AI Capability Enhancement engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .service import AICapabilityService


def main() -> int:
    parser = argparse.ArgumentParser(description="Elmos AI Capability Enhancement CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # 1. validate
    v = sub.add_parser("validate", help="Validate all engine components")
    v.add_argument("--json", action="store_true", help="Output JSON results")

    # 2. execute-skill
    s = sub.add_parser("execute-skill", help="Execute an individual skill")
    s.add_argument("skill_name", help="Name of the skill to execute")
    s.add_argument("--input", help="Path to input JSON file")

    # 3. golden-route
    g = sub.add_parser("golden-route", help="Execute a golden route")
    g.add_argument("route_name", help="Name of the golden route")

    # 4. workflow
    w = sub.add_parser("workflow", help="Execute a workflow")
    w.add_argument("workflow_name", help="Name of the workflow")

    args = parser.parse_args()
    service = AICapabilityService()

    if args.command == "validate":
        routes = service.golden_routes.validate_all_routes()
        wfs = service.workflows.validate_all_workflows()
        migs = service.validate_database_migrations()
        pols = service.policies.validate_all_policies()
        summary = {
            "status": "PASS",
            "goldenRoutesCount": len(routes),
            "workflowsCount": len(wfs),
            "migrationsCount": len(migs),
            "policiesCount": len(pols),
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"Validation successful: {len(routes)} routes, {len(wfs)} workflows, {len(migs)} migrations, {len(pols)} policies validated.")
        return 0

    elif args.command == "execute-skill":
        inputs = {}
        if args.input:
            inputs = json.loads(Path(args.input).read_text(encoding="utf-8"))
        res = service.run_skill(args.skill_name, inputs)
        print(json.dumps(res.__dict__, indent=2))
        return 0 if res.status == "SUCCESS" else 1

    elif args.command == "golden-route":
        res = service.run_golden_route(args.route_name)
        print(json.dumps(res.__dict__, indent=2))
        return 0 if res.status == "QUALIFIED" else 1

    elif args.command == "workflow":
        res = service.run_workflow(args.workflow_name)
        print(json.dumps(res.__dict__, indent=2))
        return 0 if res.status == "COMPLETED" else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
