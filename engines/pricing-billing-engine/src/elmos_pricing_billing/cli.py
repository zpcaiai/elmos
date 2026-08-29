"""Command line interface for ELMOS pricing and billing engine."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .contracts import canonical_json
from .domain import Currency, Money
from .handlers import SKILL_REGISTRY, dispatch_skill
from .service import PricingBillingService


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ELMOS Pricing and Billing CLI")
    subparsers = parser.add_subparsers(dest="command")

    # list-skills
    subparsers.add_parser("list-skills", help="List all 18 pricing and billing skills")

    # dispatch
    dispatch_parser = subparsers.add_parser("dispatch", help="Dispatch a pricing or billing skill")
    dispatch_parser.add_argument("skill_name", help="Name of skill to dispatch")
    dispatch_parser.add_argument("--tenant", default="tenant-cli-001", help="Tenant ID")
    dispatch_parser.add_argument("--org", default="org-cli-001", help="Organization ID")
    dispatch_parser.add_argument("--project", default="proj-cli-001", help="Project ID")
    dispatch_parser.add_argument("--payload", default="{}", help="JSON payload for inputs")

    args = parser.parse_args(argv)

    if args.command == "list-skills":
        skills = sorted(list(SKILL_REGISTRY.keys()))
        print(json.dumps({"skills": skills, "count": len(skills)}, indent=2))
        return 0

    elif args.command == "dispatch":
        inputs = json.loads(args.payload)
        req_data = {
            "schema_version": "1.0",
            "request_id": "req-cli-001",
            "tenant_id": args.tenant,
            "organization_id": args.org,
            "project_id": args.project,
            "actor_id": "cli-user",
            "idempotency_key": "idem-cli-001",
            "inputs": inputs,
        }
        res = dispatch_skill(args.skill_name, req_data)
        out = {
            "skill": res.skill_name,
            "status": res.status,
            "outputs": res.outputs,
            "evidence_digest": res.evidence_digest,
            "duration_ms": res.duration_ms,
        }
        print(json.dumps(out, indent=2))
        return 0 if res.status == "SUCCESS" else 1

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
