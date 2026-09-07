#!/usr/bin/env python3
"""Fail-closed preflight for authorized external Precision Migration work.

This command validates the code-owned boundary before any native toolchain,
customer workload, HSM, Canary, rollback, or certification actor is allowed to
run.  It never invokes an external adapter and never converts configuration
availability into execution or certification evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.precision_migration.external import (
    ExternalProfileRegistry,
    STAGES,
    validate_canary_plan,
    validate_external_corpus,
    validate_rollback_plan,
)
from scripts.precision_migration.production_runtime import (
    PRODUCTION_STAGES,
    ProductionRuntimeError,
    TrustedAdapterRegistry,
)
from scripts.precision_migration.trust import (
    TrustStore,
    configured_roots,
    read_regular_file_once,
    utc_now,
    verify_content_reference,
)


MAX_PREFLIGHT_FILE_BYTES = 64 * 1024 * 1024
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
REQUIRED_ROLES = (
    "external-campaign-authorizer",
    "native-verifier",
    "independent-verifier",
    "customer-workload-verifier",
    "customer-workload-authorizer",
    "production-change-approver",
    "production-hsm-attestor",
    "production-controller",
    "rollback-controller",
    "external-certifier",
    "external-adapter-admin",
    "external-execution-authorizer",
)
CONFIGURATION = {
    "environment": "ELMOS_PRECISION_ENVIRONMENT",
    "independent_verifier_trust_store": "ELMOS_PRECISION_INDEPENDENT_TRUST_STORE",
    "external_adapter_registry": "ELMOS_PRECISION_EXTERNAL_ADAPTER_REGISTRY",
    "evidence_roots": "ELMOS_PRECISION_EVIDENCE_ROOTS",
    "hsm_provider": "ELMOS_PRECISION_HSM_PROVIDER",
    "hsm_key_reference": "ELMOS_PRECISION_HSM_KEY_REFERENCE",
    "customer_workload_manifest": "ELMOS_PRECISION_CUSTOMER_WORKLOAD_MANIFEST",
    "canary_plan": "ELMOS_PRECISION_CANARY_PLAN",
    "rollback_plan": "ELMOS_PRECISION_ROLLBACK_PLAN",
    "production_authorization": "ELMOS_PRECISION_PRODUCTION_AUTHORIZATION",
}
HSM_PIN_ENV = "ELMOS_PRECISION_HSM_PIN"


class ExternalPreflightError(ValueError):
    pass


def _required_text(config: dict[str, Any], name: str) -> str:
    value = config.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ExternalPreflightError(f"{CONFIGURATION[name]} is not configured")
    return value.strip()


def _roots(config: dict[str, Any]) -> tuple[Path, ...]:
    value = _required_text(config, "evidence_roots")
    candidates = [Path(item) for item in value.split(os.pathsep) if item]
    if not candidates:
        raise ExternalPreflightError("ELMOS_PRECISION_EVIDENCE_ROOTS contains no roots")
    return configured_roots(candidates)


def _within(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _content_reference(path_value: str, roots: tuple[Path, ...], label: str) -> dict[str, Any]:
    supplied = Path(path_value).expanduser()
    if supplied.is_symlink():
        raise ExternalPreflightError(f"{label} must not be a symlink")
    try:
        resolved = supplied.resolve(strict=True)
    except OSError as exc:
        raise ExternalPreflightError(f"{label} is unavailable: {exc}") from exc
    if not _within(resolved, roots):
        raise ExternalPreflightError(f"{label} escapes the approved evidence roots")
    try:
        content = read_regular_file_once(supplied, max_bytes=MAX_PREFLIGHT_FILE_BYTES, label=label)
    except (OSError, ValueError) as exc:
        raise ExternalPreflightError(str(exc)) from exc
    return {
        "uri": resolved.as_uri(),
        "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "media_type": "application/json",
    }


def _json_reference(path_value: str, roots: tuple[Path, ...], label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    reference = _content_reference(path_value, roots, label)
    observed = verify_content_reference(reference, roots)
    try:
        payload = json.loads(
            read_regular_file_once(
                Path(observed["resolved_path"]),
                max_bytes=MAX_PREFLIGHT_FILE_BYTES,
                label=label,
            ).decode("utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ExternalPreflightError(f"{label} must be valid bounded UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExternalPreflightError(f"{label} JSON root must be an object")
    return payload, observed


def _valid_role_keys(trust: TrustStore, now: datetime) -> dict[str, set[str]]:
    role_keys: dict[str, set[str]] = {role: set() for role in REQUIRED_ROLES}
    for key in trust.keys.values():
        if key.not_before <= now < key.not_after:
            for role in key.roles:
                if role in role_keys:
                    role_keys[role].add(key.public_key_digest)
    missing = [role for role, values in role_keys.items() if not values]
    if missing:
        raise ExternalPreflightError(f"trust store lacks current non-revoked keys for roles: {missing}")
    owners: dict[str, set[str]] = {}
    for role, digests in role_keys.items():
        for digest in digests:
            owners.setdefault(digest, set()).add(role)
    shared = sorted("/".join(sorted(roles)) for roles in owners.values() if len(roles) > 1)
    if shared:
        raise ExternalPreflightError(f"independent external roles share key material: {shared}")
    return role_keys


def _validate_hsm(config: dict[str, Any], secret_names: set[str]) -> dict[str, Any]:
    provider = _required_text(config, "hsm_provider").lower()
    if provider != "pkcs11":
        raise ExternalPreflightError("production HSM provider must be pkcs11")
    reference = _required_text(config, "hsm_key_reference")
    lowered = reference.lower()
    if not lowered.startswith("pkcs11:") or "type=private" not in lowered:
        raise ExternalPreflightError("HSM key reference must be a PKCS#11 private-key URI")
    if "pin-" in lowered or "pin=" in lowered or "secret=" in lowered:
        raise ExternalPreflightError("HSM key reference must not embed a PIN or secret")
    if HSM_PIN_ENV not in secret_names:
        raise ExternalPreflightError(f"{HSM_PIN_ENV} secret reference is not configured")
    return {
        "state": "VALIDATED_NOT_EXECUTED",
        "provider": provider,
        "key_reference_digest": "sha256:" + hashlib.sha256(reference.encode("utf-8")).hexdigest(),
        "pin_secret_configured": True,
        "secret_value_recorded": False,
    }


def _validate_adapters(
    registry: TrustedAdapterRegistry,
    canary: dict[str, Any],
) -> dict[str, Any]:
    stage_counts = {
        stage: sum(adapter.stage == stage for adapter in registry.adapters.values())
        for stage in (*STAGES, *PRODUCTION_STAGES)
    }
    missing = [stage for stage, count in stage_counts.items() if count == 0]
    if missing:
        raise ExternalPreflightError(f"signed adapter registry lacks stages: {missing}")
    canary_adapter = registry.adapters.get(canary["canary_adapter_id"])
    rollback_adapter = registry.adapters.get(canary["rollback_adapter_id"])
    if (
        canary_adapter is None
        or canary_adapter.stage != "authorized_canary"
        or canary_adapter.effect_class != "reversible"
        or canary_adapter.compensation_adapter != canary["rollback_adapter_id"]
    ):
        raise ExternalPreflightError("Canary plan is not bound to a reversible signed adapter")
    if rollback_adapter is None or rollback_adapter.stage != "verified_rollback":
        raise ExternalPreflightError("rollback plan is not bound to a signed rollback adapter")
    hsm_adapters = [item for item in registry.adapters.values() if item.stage == "production_hsm"]
    if not any(item.effect_class == "approval-required" and HSM_PIN_ENV in item.environment_allowlist for item in hsm_adapters):
        raise ExternalPreflightError("production HSM adapter must require approval and an allowlisted PIN reference")
    return {
        "state": "VALIDATED_NOT_EXECUTED",
        "registry_id": registry.registry_id,
        "registry_digest": registry.digest,
        "stage_counts": stage_counts,
        "canary_adapter_id": canary_adapter.adapter_id,
        "rollback_adapter_id": rollback_adapter.adapter_id,
    }


def _validate_authorization(
    payload: dict[str, Any],
    trust: TrustStore,
    *,
    environment: str,
    now: datetime,
) -> dict[str, Any]:
    fields = {
        "record_type", "record_id", "actor_id", "campaign_id", "release_digest",
        "environment", "decision", "issued_at", "expires_at",
    }
    authorization = payload.get("payload") if isinstance(payload, dict) else None
    if not isinstance(authorization, dict) or set(authorization) != fields:
        raise ExternalPreflightError("production authorization payload fields are invalid")
    if not isinstance(authorization.get("actor_id"), str) or not authorization["actor_id"]:
        raise ExternalPreflightError("production authorization actor_id is required")
    if not isinstance(authorization.get("campaign_id"), str) or not authorization["campaign_id"]:
        raise ExternalPreflightError("production authorization campaign_id is required")
    if DIGEST.fullmatch(str(authorization.get("release_digest"))) is None:
        raise ExternalPreflightError("production authorization release_digest is invalid")
    try:
        verified = trust.verify_envelope(
            payload,
            required_role="production-change-approver",
            bindings={
                "record_type": "PRECISION_PRODUCTION_CHANGE_AUTHORIZATION",
                "environment": environment,
                "decision": "APPROVED",
            },
            now=now,
        )
    except ValueError as exc:
        raise ExternalPreflightError(f"production authorization failed verification: {exc}") from exc
    return {
        "state": "VALIDATED_NOT_EXECUTED",
        "record_id": verified["record_id"],
        "key_id": verified["key_id"],
        "campaign_id": authorization["campaign_id"],
        "release_digest": authorization["release_digest"],
        "authorization_digest": verified["payload_digest"],
    }


def evaluate_preflight(
    config: dict[str, Any],
    *,
    secret_names: set[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate all code-owned prerequisites without running external work."""
    checks: dict[str, Any] = {}
    failures: list[str] = []
    observed_now = (now or utc_now()).astimezone(timezone.utc)
    secrets = secret_names or set()

    def capture(name: str, action: Any) -> Any:
        try:
            value = action()
            checks[name] = value
            return value
        except (ExternalPreflightError, ProductionRuntimeError, OSError, ValueError, KeyError) as exc:
            message = str(exc)
            checks[name] = {"state": "BLOCKED", "reason": message}
            failures.append(f"{name}: {message}")
            return None

    environment = capture(
        "environment",
        lambda: {
            "state": "VALIDATED_NOT_EXECUTED",
            "value": _required_text(config, "environment"),
        },
    )
    roots = capture(
        "evidence_roots",
        lambda: {
            "state": "VALIDATED_NOT_EXECUTED",
            "roots": [str(item) for item in _roots(config)],
        },
    )
    root_values = tuple(Path(item) for item in roots["roots"]) if roots else ()
    trust = capture(
        "independent_verifier_trust_store",
        lambda: TrustStore.load(Path(_required_text(config, "independent_verifier_trust_store"))),
    )
    if isinstance(trust, TrustStore):
        role_keys = capture("independent_role_keys", lambda: _valid_role_keys(trust, observed_now))
        checks["independent_verifier_trust_store"] = {
            "state": "VALIDATED_NOT_EXECUTED",
            "trust_store_digest": trust.digest,
            "key_count": len(trust.keys),
        }
        if role_keys is not None:
            checks["independent_role_keys"] = {
                "state": "VALIDATED_NOT_EXECUTED",
                "role_count": len(role_keys),
                "distinct_key_material_count": len(set().union(*role_keys.values())),
            }

    capture("production_hsm", lambda: _validate_hsm(config, secrets))
    if root_values:
        capture(
            "representative_customer_workload",
            lambda: validate_external_corpus(
                "representative",
                _content_reference(
                    _required_text(config, "customer_workload_manifest"),
                    root_values,
                    "customer workload manifest",
                ),
                evidence_roots=root_values,
            ),
        )
    else:
        checks["representative_customer_workload"] = {"state": "BLOCKED", "reason": "evidence roots are invalid"}
        failures.append("representative_customer_workload: evidence roots are invalid")

    canary = None
    rollback = None
    if root_values and environment:
        canary_pair = capture(
            "canary_plan",
            lambda: _json_reference(_required_text(config, "canary_plan"), root_values, "Canary plan"),
        )
        if canary_pair:
            canary = capture(
                "canary_plan",
                lambda: validate_canary_plan(canary_pair[0], environment=environment["value"]),
            )
            if canary:
                checks["canary_plan"] = {
                    "state": "VALIDATED_NOT_EXECUTED",
                    **canary,
                    "content_digest": canary_pair[1]["digest"],
                }
        rollback_pair = capture(
            "rollback_plan",
            lambda: _json_reference(_required_text(config, "rollback_plan"), root_values, "rollback plan"),
        )
        if rollback_pair and canary:
            rollback = capture(
                "rollback_plan",
                lambda: validate_rollback_plan(
                    rollback_pair[0],
                    environment=environment["value"],
                    expected_adapter_id=canary["rollback_adapter_id"],
                ),
            )
            if rollback:
                checks["rollback_plan"] = {
                    "state": "VALIDATED_NOT_EXECUTED",
                    **rollback,
                    "content_digest": rollback_pair[1]["digest"],
                }
        elif rollback_pair:
            checks["rollback_plan"] = {
                "state": "BLOCKED",
                "reason": "Canary plan validation must pass before rollback validation",
            }
            failures.append("rollback_plan: Canary plan validation did not pass")

    registry = None
    if isinstance(trust, TrustStore):
        registry = capture(
            "external_adapter_registry",
            lambda: TrustedAdapterRegistry.load(
                Path(_required_text(config, "external_adapter_registry")),
                trust,
                ExternalProfileRegistry.load(),
            ),
        )
    if isinstance(registry, TrustedAdapterRegistry) and canary:
        capture("external_adapter_registry", lambda: _validate_adapters(registry, canary))
    elif isinstance(registry, TrustedAdapterRegistry):
        checks["external_adapter_registry"] = {
            "state": "BLOCKED",
            "reason": "Canary plan validation must pass before adapter-plan validation",
        }
        failures.append("external_adapter_registry: Canary plan validation did not pass")

    if root_values and isinstance(trust, TrustStore) and environment:
        authorization_pair = capture(
            "production_authorization",
            lambda: _json_reference(
                _required_text(config, "production_authorization"),
                root_values,
                "production authorization",
            ),
        )
        if authorization_pair:
            authorization = capture(
                "production_authorization",
                lambda: _validate_authorization(
                    authorization_pair[0], trust, environment=environment["value"], now=observed_now
                ),
            )
            if authorization:
                checks["production_authorization"] = {
                    **authorization,
                    "content_digest": authorization_pair[1]["digest"],
                }

    # Ensure a partial branch above cannot accidentally appear ready.
    required_checks = {
        "environment", "evidence_roots", "independent_verifier_trust_store",
        "independent_role_keys", "production_hsm", "representative_customer_workload",
        "canary_plan", "rollback_plan", "external_adapter_registry", "production_authorization",
    }
    missing_checks = sorted(required_checks - set(checks))
    for name in missing_checks:
        checks[name] = {"state": "BLOCKED", "reason": "prerequisite validation did not run"}
        failures.append(f"{name}: prerequisite validation did not run")
    ready = not failures and all(
        isinstance(checks[name], dict) and checks[name].get("state") == "VALIDATED_NOT_EXECUTED"
        for name in required_checks
    )
    return {
        "schema_version": 2,
        "namespace": "precision-migration-b01-44",
        "status": "READY_FOR_AUTHORIZED_EXTERNAL_EXECUTION" if ready else "BLOCKED",
        "checks": checks,
        "failures": failures,
        "profile_count": 557,
        "external_operations_executed": False,
        "native_source_execution": "NOT_RUN",
        "native_target_execution": "NOT_RUN",
        "independent_holdout": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "hsm_signing": "NOT_RUN",
        "customer_workload": "NOT_RUN",
        "canary": "NOT_RUN",
        "rollback": "NOT_RUN",
        "production_evidence": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
    }


def _environment_config() -> dict[str, Any]:
    return {name: os.environ.get(variable, "") for name, variable in CONFIGURATION.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_preflight(_environment_config(), secret_names=set(os.environ))
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "READY_FOR_AUTHORIZED_EXTERNAL_EXECUTION" else 3


if __name__ == "__main__":
    raise SystemExit(main())
