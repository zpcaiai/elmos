#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from elmos_project_synthesis.cleanup import cleanup_acceptance_directory
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SUPPORTED_PROFILE_TARGETS
from elmos_project_synthesis.verification import verify_workspace
from elmos_project_synthesis.workspace import generate_workspace


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local PostgreSQL production-profile acceptance for one evidenced target."
    )
    parser.add_argument("--auth-mode", choices=("jwt", "oidc"), required=True)
    parser.add_argument(
        "--language",
        default="python",
        choices=sorted(SUPPORTED_PROFILE_TARGETS[("postgresql", "jwt")]),
        help="Target whose production profile carries PostgreSQL-backed evidence.",
    )
    return parser.parse_args()


MULTI_ENTITY_TARGETS = frozenset({"python", "java"})


MULTI_ENTITY_SHAPE: dict[str, Any] = {
    "entities": (
        {
            "singular": "customer",
            "plural": "customers",
            "fields": [{"name": "name", "type": "string", "required": True}],
        },
        {
            "singular": "order",
            "plural": "orders",
            "fields": [
                {"name": "customer_id", "type": "string", "required": True},
                {"name": "total", "type": "number", "required": True},
            ],
        },
    ),
    "relations": (
        {
            "source": "order",
            "target": "customer",
            "source_field": "customer_id",
            "target_field": "id",
            "kind": "many-to-one",
            "required": True,
        },
    ),
}

# Emitters that have not grown multi-entity support refuse such a request
# outright rather than dropping entities, so the acceptance uses the single
# entity shape for them instead of asserting a capability they decline.
SINGLE_ENTITY_SHAPE: dict[str, Any] = {
    "entities": (
        {
            "singular": "order",
            "plural": "orders",
            "fields": [
                {"name": "reference", "type": "string", "required": True},
                {"name": "total", "type": "number", "required": True},
            ],
        },
    ),
    "relations": (),
}


def main() -> int:
    arguments = parse_args()
    shape = (
        MULTI_ENTITY_SHAPE
        if arguments.language in MULTI_ENTITY_TARGETS
        else SINGLE_ENTITY_SHAPE
    )
    request = approve_request(
        create_draft(
            name=f"enterprise-orders-{arguments.language}-{arguments.auth_mode}",
            description="Durable authenticated and tenant-isolated order API.",
            entities=shape["entities"],
            relations=shape["relations"],
            languages=(arguments.language,),
            persistence="postgresql",
            auth_mode=arguments.auth_mode,
        ),
        actor="acceptance:production-profile",
        approved_at="2026-07-26T00:00:00+00:00",
    )
    temporary = Path(tempfile.mkdtemp(prefix="elmos-production-profile-"))
    cleanup_error: str | None = None
    try:
        workspace = temporary / "workspace"
        manifest = generate_workspace(request, workspace)
        generation_manifest_sha256 = hashlib.sha256(
            (workspace / ".elmos" / "generation-manifest.json").read_bytes()
        ).hexdigest()
        evidence = verify_workspace(workspace, use_ephemeral_runtime_ports=True)
    finally:
        cleanup_error = cleanup_acceptance_directory(
            temporary,
            expected_prefix="elmos-production-profile-",
        )
    probes = [item for item in evidence["results"] if item.get("kind") == "startup-probe"]
    result = {
        "schema_version": "1.0.0",
        "status": evidence["status"],
        "language": arguments.language,
        "auth_mode": arguments.auth_mode,
        "entity_shape": "multi-entity" if arguments.language in MULTI_ENTITY_TARGETS else "single-entity",
        "generated_file_count": manifest["file_count"],
        "request_sha256": manifest["request_sha256"],
        "approved_payload_sha256": manifest["approved_payload_sha256"],
        "generation_manifest_sha256": generation_manifest_sha256,
        "exact_toolchain_match": evidence["environment"]["exact_toolchain_match"].get(
            arguments.language,
            False,
        ),
        "startup_probes": [
            {
                "status": item["status"],
                "integration_status": item["integration_status"],
                "response": item["response"],
            }
            for item in probes
        ],
        "failures": [
            {
                "language": item["language"],
                "kind": item["kind"],
                "command": item["command"],
                "exit_code": item["exit_code"],
                "output": str(item.get("output", ""))[-4_000:],
            }
            for item in evidence["results"]
            if item.get("status") == "FAILED"
        ],
        "production_delivery_status": evidence["production_delivery_status"],
        "external_certification_status": evidence["external_certification_status"],
        "cleanup_status": "PASSED" if cleanup_error is None else "FAILED",
    }
    if cleanup_error is not None:
        result["cleanup_error"] = cleanup_error
        result["cleanup_path"] = str(temporary)
        result["status"] = "FAILED"
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
