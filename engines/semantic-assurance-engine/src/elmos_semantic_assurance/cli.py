"""Fail-closed CLI for semantic-assurance planning and exact invocation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .adapters import AdapterSet
from .contracts import TrustedIdentity
from .service import SemanticAssuranceService
from .store import SemanticAssuranceStore

_MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


def _strict_object(path_text: str, label: str) -> dict[str, Any]:
    path = Path(path_text)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} must be a regular non-symlink file")
    raw = path.read_bytes()
    if len(raw) > _MAX_DOCUMENT_BYTES:
        raise ValueError(f"{label} exceeds {_MAX_DOCUMENT_BYTES} bytes")

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"{label} contains duplicate key {key!r}")
            value[key] = item
        return value

    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return document


def _identity(document: dict[str, Any]) -> TrustedIdentity:
    allowed = {"tenantId", "projectId", "actorId", "roles", "authorizationRef"}
    extra = sorted(set(document) - allowed)
    if extra:
        raise ValueError(f"identity contains unsupported fields: {extra}")
    roles = document.get("roles", [])
    if not isinstance(roles, list):
        raise ValueError("identity.roles must be an array")
    tenant_id = document.get("tenantId")
    if not isinstance(tenant_id, str):
        raise ValueError("identity.tenantId must be a string")
    project_id = document.get("projectId")
    if not isinstance(project_id, str):
        raise ValueError("identity.projectId must be a string")
    actor_id = document.get("actorId")
    if not isinstance(actor_id, str):
        raise ValueError("identity.actorId must be a string")
    authorization_ref = document.get("authorizationRef")
    if authorization_ref is not None and not isinstance(authorization_ref, str):
        raise ValueError("identity.authorizationRef must be a string or null")
    return TrustedIdentity(
        tenant_id=tenant_id,
        project_id=project_id,
        actor_id=actor_id,
        roles=tuple(roles),
        authorization_ref=authorization_ref,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-semantic-assurance")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="show fail-closed implementation status")
    catalog = commands.add_parser("catalog", help="list exact registered Skills")
    catalog.add_argument("--batch", choices=list("JKLMNOPQR"))
    plan = commands.add_parser("campaign-plan", help="prepare a non-executing route plan")
    plan.add_argument("--source-technology", required=True)
    plan.add_argument("--target-technology", required=True)
    plan.add_argument("--source", required=True)
    plan.add_argument("--target", required=True)
    plan.add_argument("--route-id")
    invoke = commands.add_parser("invoke", help="invoke one exact Skill")
    invoke.add_argument("--skill", required=True)
    invoke.add_argument("--request", required=True)
    invoke.add_argument("--identity", required=True)
    invoke.add_argument("--state-db", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result: dict[str, Any] | list[dict[str, Any]]
        if args.command == "invoke":
            store = SemanticAssuranceStore(args.state_db)
            service = SemanticAssuranceService(store=store, adapters=AdapterSet())
            result = service.dispatch(
                args.skill,
                _strict_object(args.request, "request"),
                _identity(_strict_object(args.identity, "identity")),
            )
        else:
            service = SemanticAssuranceService()
            if args.command == "status":
                result = service.status()
            elif args.command == "catalog":
                result = service.catalog(batch=args.batch)
            else:
                result = service.prepare_route_assurance_campaign(
                    source_technology=args.source_technology,
                    target_technology=args.target_technology,
                    source_bytes=Path(args.source).read_bytes(),
                    target_bytes=Path(args.target).read_bytes(),
                    route_id=args.route_id,
                )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        if isinstance(result, dict) and result.get("executionStatus") in {
            "BLOCKED",
            "FAILED",
            "REQUIRES_ADAPTER",
        }:
            return 3
        return 0
    except (KeyError, OSError, PermissionError, RuntimeError, ValueError) as exc:
        print(
            json.dumps({"error": type(exc).__name__, "message": str(exc)}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
