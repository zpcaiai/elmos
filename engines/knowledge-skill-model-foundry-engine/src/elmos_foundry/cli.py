"""Command-line interface for Elmos Knowledge-Skill-Model Foundry.

Provides CLI subcommands for verification, pipeline execution, and qualification.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .domain import TenantScope
from .service import FoundryService


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Elmos Knowledge-Skill-Model Foundry CLI")
    subparsers = parser.add_subparsers(dest="command")

    # validate command
    val_parser = subparsers.add_parser("validate", help="Validate schema, skills catalog, and database tables")

    # pipeline command
    pipe_parser = subparsers.add_parser("pipeline", help="Execute a lifecycle pipeline")
    pipe_parser.add_argument("name", choices=["knowledge-to-skill", "experience-to-dataset", "train-certify-deploy", "customer-private-adapter"])
    pipe_parser.add_argument("--tenant", default="tenant-cli-001", help="Tenant ID")
    pipe_parser.add_argument("--project", default="project-cli-001", help="Project ID")

    # route command
    route_parser = subparsers.add_parser("route", help="Route query through meta-skill")
    route_parser.add_argument("meta_skill", help="Name of meta-skill")
    route_parser.add_argument("--query", default="", help="Query string")

    args = parser.parse_args(argv)
    service = FoundryService()

    if args.command == "validate":
        db_res = service.database.validate_schema_structure()
        out = {
            "status": "PASS" if db_res["valid"] else "FAIL",
            "atomicSkills": service.skills.total_atomic_skills,
            "metaSkills": service.skills.total_meta_skills,
            "tables": db_res["table_count"],
        }
        print(json.dumps(out, indent=2))
        return 0 if db_res["valid"] else 1

    elif args.command == "pipeline":
        scope = TenantScope(tenant_id=args.tenant, project_id=args.project)
        res = service.run_pipeline(args.name, {}, tenant_scope=scope)
        print(json.dumps(res, indent=2))
        return 0

    elif args.command == "route":
        matched = service.route_meta_skill(args.meta_skill, query=args.query)
        print(json.dumps({"meta_skill": args.meta_skill, "matches": matched}, indent=2))
        return 0

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
