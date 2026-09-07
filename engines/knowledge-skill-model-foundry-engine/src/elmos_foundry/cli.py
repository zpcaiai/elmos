"""Fail-closed CLI for local Foundry catalog and preparation operations."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Mapping, Sequence

from .canonical import strict_json_loads
from .domain import TenantScope
from .kernel import KernelSecurityError
from .service import FoundryService
from .skills import CatalogValidationError, EXPECTED_PIPELINES


def _object(value: str, label: str) -> Mapping[str, Any]:
    try:
        parsed = strict_json_loads(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"{label} must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError(f"{label} must be a JSON object")
    return parsed


def _scope(service: FoundryService, args: argparse.Namespace, capability: str) -> TenantScope:
    return service.kernel.mint_context(
        tenant_id=args.tenant,
        project_id=args.project,
        actor_id=args.actor,
        environment_id=args.environment,
        workspace_digest=args.workspace_digest,
        revision_set_id=args.revision,
        purpose="foundry-local-cli-preparation",
        capabilities=(capability,),
        ttl_seconds=args.ttl_seconds,
        invocation_id=args.invocation,
        lease_id=args.lease,
    )


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    return value


def _add_scope(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--workspace-digest", required=True, help="sha256:<hex>")
    parser.add_argument("--revision", required=True, help="sha256:<hex>")
    parser.add_argument("--invocation", required=True)
    parser.add_argument("--lease", required=True)
    parser.add_argument("--ttl-seconds", type=int, default=300)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Elmos Knowledge-Skill-Model Foundry CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="Validate the exact compiled runtime catalog")

    pipe_parser = subparsers.add_parser("pipeline", help="Prepare an exact pipeline plan")
    pipe_parser.add_argument("name", choices=sorted(EXPECTED_PIPELINES))
    pipe_parser.add_argument("--params-json", required=True)
    _add_scope(pipe_parser)

    route_parser = subparsers.add_parser("route", help="Route through one exact meta Skill")
    route_parser.add_argument("meta_skill")
    route_parser.add_argument("--query", default="")
    route_parser.add_argument("--filters-json", default="{}")
    route_parser.add_argument("--candidate-limit", type=int)
    route_parser.add_argument("--activation-limit", type=int)

    skill_parser = subparsers.add_parser("skill", help="Prepare one exact atomic Skill")
    skill_parser.add_argument("skill_name")
    skill_parser.add_argument("--inputs-json", required=True)
    _add_scope(skill_parser)

    args = parser.parse_args(argv)
    try:
        service = FoundryService()
        if args.command == "validate":
            status_out = dict(service.status())
            status_out["validation_status"] = "LOCAL_STRUCTURAL_VALIDATED_SELF_ATTESTED"
            print(json.dumps(_json_ready(status_out), indent=2, sort_keys=True))
            return 0
        if args.command == "pipeline":
            pipeline_out = service.run_pipeline(
                args.name,
                _object(args.params_json, "--params-json"),
                tenant_scope=_scope(service, args, "foundry.pipeline.prepare"),
            )
            print(json.dumps(_json_ready(pipeline_out), indent=2, sort_keys=True))
            return 0 if pipeline_out["status"] == "READY_FOR_EXTERNAL_GATE" else 1
        if args.command == "route":
            route_out = service.skills.route_meta_skill_plan(
                args.meta_skill,
                args.query,
                filters=_object(args.filters_json, "--filters-json"),
                candidate_limit=args.candidate_limit,
                activation_limit=args.activation_limit,
            )
            print(json.dumps(_json_ready(route_out), indent=2, sort_keys=True))
            return 0 if route_out["status"] == "ROUTED" else 1
        inputs = dict(_object(args.inputs_json, "--inputs-json"))
        inputs["operation"] = "prepare"
        result = service.execute_skill(
            args.skill_name,
            inputs,
            tenant_scope=_scope(service, args, "foundry.skill.prepare"),
        )
        print(
            json.dumps(
                _json_ready(
                    {
                        "operation": result.operation,
                        "status": result.status,
                        "outputs": result.outputs,
                        "content_digest": result.evidence_digest,
                        "error": result.error,
                    }
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if result.status == "SUCCESS" else 1
    except (
        argparse.ArgumentTypeError,
        CatalogValidationError,
        KernelSecurityError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "execution_status": "NOT_RUN",
                    "certification_status": "NOT_CERTIFIED",
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
