"""JSON-only, secret-free CLI for bounded local control-plane operations."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .canonical import canonical_json, require_digest, strict_json_loads
from .contracts import GateLevel, Scope, utc_now
from .errors import CommercialRuntimeError, ContractError
from .service import get_commercial_status, list_capability_kernels
from .store import ReadonlyControlPlaneStore
from .trusted_paths import PathBoundaryError, read_regular_bytes

_SECRET_KEY_FRAGMENTS = ("api_key", "credential", "password", "private_key", "secret", "token")


def _read_request(source: str) -> Mapping[str, Any]:
    if source == "-":
        document = sys.stdin.buffer.read(1_048_577)
    else:
        path = Path(source)
        if not path.is_absolute():
            raise ContractError("input JSON file path must be absolute")
        try:
            document = read_regular_bytes(path, label="CLI input JSON", maximum=1_048_576)
        except PathBoundaryError as exc:
            raise ContractError("input must be a bounded owner-only regular JSON file") from exc
    value = strict_json_loads(document)
    if not isinstance(value, Mapping):
        raise ContractError("CLI request must be a JSON object")
    return value


def _reject_secret_material(value: Any, *, path: str = "request") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            lowered = key.lower()
            if any(fragment in lowered for fragment in _SECRET_KEY_FRAGMENTS):
                raise ContractError(
                    "CLI requests must not contain secret material",
                    code="SECRET_INPUT_FORBIDDEN",
                    details={"field": f"{path}.{key}"},
                )
            _reject_secret_material(child, path=f"{path}.{key}")
    elif isinstance(value, (tuple, list)):
        for index, child in enumerate(value):
            _reject_secret_material(child, path=f"{path}[{index}]")


def _scope(value: Any) -> Scope:
    if not isinstance(value, Mapping):
        raise ContractError("scope must be an object")
    exact = {"tenant_id", "project_id", "actor_id", "revision", "environment_id"}
    if set(value) != exact:
        raise ContractError("scope fields must be exact")
    return Scope(
        tenant_id=value["tenant_id"],
        project_id=value["project_id"],
        actor_id=value["actor_id"],
        revision=value["revision"],
        environment_id=value["environment_id"],
    )
def _catalog(request: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"kernel"}
    if set(request) - allowed:
        raise ContractError("catalog request contains unknown fields")
    kernels = list_capability_kernels()
    kernel = request.get("kernel")
    if kernel is not None:
        if not isinstance(kernel, str):
            raise ContractError("catalog.kernel must be text")
        kernels = [item for item in kernels if item["kernel"] == kernel]
    status = get_commercial_status()
    return {
        "status": status["status"],
        "registry_digest": status["registry_digest"],
        "kernels": kernels,
        "external_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }


def _invoke(request: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
    _reject_secret_material(request)
    allowed = {"schema_version", "skill_id", "action", "scope", "inputs", "idempotency_key", "authority_proof"}
    unknown = set(request) - allowed
    if unknown:
        raise ContractError("invoke request contains unknown fields")
    if request.get("schema_version") != "1.0":
        raise ContractError("invoke.schema_version must be '1.0'")
    # The standalone CLI intentionally has no private signing material or
    # trusted host verifier.  A JSON authority-shaped value never gains power.
    return (
        {
            "status": "DENIED",
            "outcome": "NOT_RUN",
            "reason_code": "AUTHORITY_VERIFIER_UNAVAILABLE",
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        },
        3,
    )


def _check_store(request: Mapping[str, Any]) -> dict[str, Any]:
    if set(request) != {"database_path"} or not isinstance(request.get("database_path"), str):
        raise ContractError("check-store requires only database_path")
    path = Path(request["database_path"])
    if not path.is_absolute():
        raise ContractError("check-store database_path must be absolute")
    with ReadonlyControlPlaneStore(path) as store:
        return store.verify_all_integrity()


def _gate(request: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "gate",
        "scope",
        "subject_digest",
        "evidence",
        "obligations",
        "authorization_id",
    }
    if set(request) - allowed:
        raise ContractError("gate request contains unknown fields")
    scope = _scope(request.get("scope"))
    evidence_value = request.get("evidence", ())
    obligations_value = request.get("obligations", ())
    if not isinstance(evidence_value, (tuple, list)) or not isinstance(obligations_value, (tuple, list)):
        raise ContractError("gate evidence and obligations must be arrays")
    gate = GateLevel(request.get("gate"))
    subject_digest = require_digest(request.get("subject_digest"), "gate.subject_digest")
    return {
        "gate": gate.value,
        "passed": False,
        "status": "NOT_RUN",
        "subject_digest": subject_digest,
        "scope_digest": scope.digest,
        "evidence_ids": [],
        "candidate_evidence_count": len(evidence_value),
        "candidate_obligation_count": len(obligations_value),
        "reasons": ["TRUSTED_EVIDENCE_VERIFIER_UNAVAILABLE"],
        "evaluated_at": utc_now(),
        "external_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="elmos-commercial-expansion",
        description="Fail-closed local Commercial Capability Expansion control plane",
    )
    parser.add_argument("command", choices=("catalog", "invoke", "check-store", "gate"))
    parser.add_argument("--input", required=True, help="JSON file path, or '-' for stdin")
    args = parser.parse_args(argv)
    try:
        request = _read_request(args.input)
        if args.command == "catalog":
            response, exit_code = _catalog(request), 0
        elif args.command == "invoke":
            response, exit_code = _invoke(request)
        elif args.command == "check-store":
            response, exit_code = _check_store(request), 0
        else:
            response = _gate(request)
            exit_code = 0 if response["passed"] else 4
    except (CommercialRuntimeError, ValueError) as exc:
        code = exc.code if isinstance(exc, CommercialRuntimeError) else "INVALID_REQUEST"
        response = {
            "status": "ERROR",
            "code": code,
            "message": str(exc),
            "certification_status": "NOT_CERTIFIED",
        }
        exit_code = 2
    print(canonical_json(response))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
