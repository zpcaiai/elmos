"""Signed separation-of-duties and production-authority verification.

The repository consumes public, expiring governance records.  It never creates
approvals, loads signing keys, or treats a caller-provided role label as
authority.  Release execution and promotion bind the same records to the exact
candidate, plan, tenant, project, campaign, environment, and executor set.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .adapters import EXTERNAL_ADAPTERS
from .attestation import verify_signed_record
from .canonical import digest_json


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
ROLE_NAMES = (
    "release_owner",
    "code_owner",
    "harness_administrator",
    "harness_executor",
    "corpus_license_reviewer",
    "qa_reviewer",
    "security_reviewer",
    "independent_approver",
    "independent_verifier",
    "production_environment_owner",
    "external_certification_authority",
)
REQUIRED_SEPARATION = (
    ("harness_executor", "independent_verifier"),
    ("release_owner", "independent_approver"),
    ("corpus_license_reviewer", "harness_executor"),
    ("production_environment_owner", "independent_verifier"),
)
_ROLE_PAYLOAD_FIELDS = frozenset(
    {
        "schema_version",
        "candidate_digest",
        "plan_digest",
        "tenant_id",
        "project_id",
        "task_id",
        "status",
        "roles",
    }
)
_AUTHORITY_PAYLOAD_FIELDS = frozenset(
    {
        "schema_version",
        "candidate_digest",
        "plan_digest",
        "tenant_id",
        "project_id",
        "task_id",
        "environment_id",
        "authority_id",
        "status",
        "authorized_executor_ids",
        "allowed_effects",
        "cleanup_required",
        "rollback_required",
    }
)
_ALLOWED_EFFECTS = frozenset(
    {
        "external-case-execution",
        "evidence-publication",
        "artifact-retention",
        "cleanup",
        "rollback",
    }
)


def _identifier(value: Any, *, field: str, errors: list[str]) -> str:
    text = str(value) if isinstance(value, str) else ""
    if not _IDENTIFIER.fullmatch(text):
        errors.append(f"{field} must be a bounded identifier")
    return text


def _principals(value: Any, *, field: str, errors: list[str]) -> set[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not values:
        errors.append(f"{field} must contain at least one principal")
        return set()
    principals: set[str] = set()
    for index, item in enumerate(values):
        principal = _identifier(item, field=f"{field}[{index}]", errors=errors)
        if principal:
            principals.add(principal)
    if len(principals) != len(values):
        errors.append(f"{field} principals must be unique")
    return principals


def _binding_errors(
    payload: Mapping[str, Any],
    *,
    candidate_digest: str,
    plan_digest: str,
    tenant_id: str,
    project_id: str,
    task_id: str,
) -> list[str]:
    expected = {
        "candidate_digest": candidate_digest,
        "plan_digest": plan_digest,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "task_id": task_id,
    }
    errors: list[str] = []
    for field, value in expected.items():
        if payload.get(field) != value:
            errors.append(f"governance binding mismatch: {field}")
    if not _DIGEST.fullmatch(str(payload.get("candidate_digest", ""))):
        errors.append("governance candidate_digest must be sha256:<64 hex>")
    if not _DIGEST.fullmatch(str(payload.get("plan_digest", ""))):
        errors.append("governance plan_digest must be sha256:<64 hex>")
    return errors


def verify_role_assignment(
    record: Mapping[str, Any],
    trust_store: Mapping[str, Any],
    *,
    candidate_digest: str,
    plan_digest: str,
    tenant_id: str,
    project_id: str,
    task_id: str,
    executor_ids: Iterable[str] = (),
    owner_ids: Iterable[str] = (),
    verifier_id: str | None = None,
) -> dict[str, Any]:
    verification = verify_signed_record(record, trust_store, record_type="role-assignment")
    errors = list(verification.get("errors", []))
    payload = record.get("payload")
    normalized: dict[str, list[str]] = {}
    if not isinstance(payload, Mapping):
        errors.append("role-assignment payload must be an object")
    else:
        if set(payload) != _ROLE_PAYLOAD_FIELDS:
            errors.append("role-assignment payload fields do not match schema v1")
        if payload.get("schema_version") != "1.0" or payload.get("status") != "approved":
            errors.append("role-assignment must be schema 1.0 with approved status")
        errors.extend(
            _binding_errors(
                payload,
                candidate_digest=candidate_digest,
                plan_digest=plan_digest,
                tenant_id=tenant_id,
                project_id=project_id,
                task_id=task_id,
            )
        )
        roles = payload.get("roles")
        if not isinstance(roles, Mapping) or set(roles) != set(ROLE_NAMES):
            errors.append("role-assignment roles must contain the exact required role set")
        else:
            role_sets = {
                role: _principals(roles[role], field=f"roles.{role}", errors=errors)
                for role in ROLE_NAMES
            }
            normalized = {role: sorted(values) for role, values in role_sets.items()}
            for left, right in REQUIRED_SEPARATION:
                overlap = sorted(role_sets[left] & role_sets[right])
                if overlap:
                    errors.append(f"role separation violated: {left}/{right}: {overlap}")
            required_executors = set(executor_ids) | set(owner_ids)
            missing_executors = sorted(required_executors - role_sets["harness_executor"])
            if missing_executors:
                errors.append(f"executors absent from harness_executor role: {missing_executors}")
            if verifier_id and verifier_id not in role_sets["independent_verifier"]:
                errors.append("supplied verifier is absent from independent_verifier role")
            if record.get("issuer_id") not in role_sets["independent_approver"]:
                errors.append("role-assignment issuer must be an assigned independent approver")
    return {
        "valid": not errors,
        "status": "VERIFIED" if not errors else "BLOCKED",
        "record_type": "role-assignment",
        "record_digest": digest_json(record),
        "issuer_id": record.get("issuer_id"),
        "roles": normalized,
        "errors": errors,
        "signature_verification": verification,
    }


def verify_production_authority(
    record: Mapping[str, Any],
    trust_store: Mapping[str, Any],
    *,
    candidate_digest: str,
    plan_digest: str,
    tenant_id: str,
    project_id: str,
    task_id: str,
    environment_id: str,
    authority_id: str,
    executor_ids: Iterable[str] = (),
    owner_ids: Iterable[str] = (),
    production_environment_owners: Iterable[str] = (),
) -> dict[str, Any]:
    verification = verify_signed_record(record, trust_store, record_type="production-authorization")
    errors = list(verification.get("errors", []))
    payload = record.get("payload")
    authorized: set[str] = set()
    effects: set[str] = set()
    if not isinstance(payload, Mapping):
        errors.append("production-authorization payload must be an object")
    else:
        if set(payload) != _AUTHORITY_PAYLOAD_FIELDS:
            errors.append("production-authorization payload fields do not match schema v1")
        if payload.get("schema_version") != "1.0" or payload.get("status") != "approved":
            errors.append("production-authorization must be schema 1.0 with approved status")
        errors.extend(
            _binding_errors(
                payload,
                candidate_digest=candidate_digest,
                plan_digest=plan_digest,
                tenant_id=tenant_id,
                project_id=project_id,
                task_id=task_id,
            )
        )
        if payload.get("environment_id") != environment_id:
            errors.append("governance binding mismatch: environment_id")
        if payload.get("authority_id") != authority_id:
            errors.append("governance binding mismatch: authority_id")
        authorized = _principals(
            payload.get("authorized_executor_ids"),
            field="authorized_executor_ids",
            errors=errors,
        )
        required_executors = set(executor_ids) | set(owner_ids)
        missing = sorted(required_executors - authorized)
        if missing:
            errors.append(f"executors absent from production authorization: {missing}")
        raw_effects = payload.get("allowed_effects")
        if not isinstance(raw_effects, list) or not raw_effects or any(not isinstance(item, str) for item in raw_effects):
            errors.append("allowed_effects must be a non-empty string array")
        else:
            effects = set(raw_effects)
            if len(effects) != len(raw_effects):
                errors.append("allowed_effects must be unique")
            unknown = sorted(effects - _ALLOWED_EFFECTS)
            if unknown:
                errors.append(f"unsupported production effects: {unknown}")
            if "external-case-execution" not in effects:
                errors.append("production authorization does not allow external-case-execution")
        if payload.get("cleanup_required") is not True or payload.get("rollback_required") is not True:
            errors.append("production authorization must require cleanup and rollback")
        owners = set(production_environment_owners)
        if owners and record.get("issuer_id") not in owners:
            errors.append("production-authorization issuer must be an assigned production environment owner")
    return {
        "valid": not errors,
        "status": "VERIFIED" if not errors else "BLOCKED",
        "record_type": "production-authorization",
        "record_digest": digest_json(record),
        "issuer_id": record.get("issuer_id"),
        "authorized_executor_ids": sorted(authorized),
        "allowed_effects": sorted(effects),
        "errors": errors,
        "signature_verification": verification,
    }


def verify_release_governance(
    *,
    role_assignment: Mapping[str, Any] | None,
    production_authority: Mapping[str, Any] | None,
    trust_store: Mapping[str, Any],
    candidate_digest: str,
    plan_digest: str,
    tenant_id: str,
    project_id: str,
    task_id: str,
    environment_id: str,
    authority_id: str,
    executor_ids: Iterable[str] = (),
    owner_ids: Iterable[str] = (),
    verifier_id: str | None = None,
) -> dict[str, Any]:
    if role_assignment is None:
        role_result = {"valid": False, "status": "BLOCKED", "errors": ["signed role-assignment record is required"]}
    else:
        role_result = verify_role_assignment(
            role_assignment,
            trust_store,
            candidate_digest=candidate_digest,
            plan_digest=plan_digest,
            tenant_id=tenant_id,
            project_id=project_id,
            task_id=task_id,
            executor_ids=executor_ids,
            owner_ids=owner_ids,
            verifier_id=verifier_id,
        )
    environment_owners = role_result.get("roles", {}).get("production_environment_owner", [])
    if production_authority is None:
        authority_result = {"valid": False, "status": "BLOCKED", "errors": ["signed production-authorization record is required"]}
    else:
        authority_result = verify_production_authority(
            production_authority,
            trust_store,
            candidate_digest=candidate_digest,
            plan_digest=plan_digest,
            tenant_id=tenant_id,
            project_id=project_id,
            task_id=task_id,
            environment_id=environment_id,
            authority_id=authority_id,
            executor_ids=executor_ids,
            owner_ids=owner_ids,
            production_environment_owners=environment_owners,
        )
    errors = [
        *(f"role-assignment: {error}" for error in role_result.get("errors", [])),
        *(f"production-authorization: {error}" for error in authority_result.get("errors", [])),
    ]
    result = {
        "schema_version": "1.0",
        "valid": bool(role_result.get("valid")) and bool(authority_result.get("valid")),
        "status": "VERIFIED" if not errors else "BLOCKED",
        "role_assignment": role_result,
        "production_authority": authority_result,
        "errors": errors,
        "certification_status": "NOT_CERTIFIED",
    }
    result["governance_digest"] = digest_json(result)
    return result


def campaign_context_from_results(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Recover one immutable campaign context and all executor identities."""

    stable_fields = (
        "candidate_digest",
        "plan_digest",
        "tenant_id",
        "project_id",
        "task_id",
        "environment_id",
        "authority_id",
    )
    values = {field: set() for field in stable_fields}
    owner_ids: set[str] = set()
    executor_ids: set[str] = set()
    errors: list[str] = []
    count = 0
    for index, result in enumerate(results, 1):
        count += 1
        evidence = result.get("evidence")
        binding = evidence.get("campaign_binding") if isinstance(evidence, Mapping) else None
        if not isinstance(binding, Mapping):
            errors.append(f"result {index} campaign binding is missing")
            continue
        for field in stable_fields:
            value = binding.get(field)
            if isinstance(value, str) and value:
                values[field].add(value)
            else:
                errors.append(f"result {index} campaign binding is missing {field}")
        owner = binding.get("owner_id")
        if isinstance(owner, str) and owner:
            owner_ids.add(owner)
        else:
            errors.append(f"result {index} campaign binding is missing owner_id")
        adapter = evidence.get("adapter") if isinstance(evidence, Mapping) else None
        signed = evidence.get("signed_response") if isinstance(evidence, Mapping) else None
        if adapter in EXTERNAL_ADAPTERS:
            if not isinstance(signed, Mapping) or not isinstance(signed.get("issuer_id"), str):
                errors.append(f"result {index} external executor identity is missing")
            else:
                executor_ids.add(str(signed["issuer_id"]))
    context: dict[str, Any] = {}
    for field, observed in values.items():
        if len(observed) != 1:
            errors.append(f"campaign results must contain one {field}; observed {len(observed)}")
        else:
            context[field] = next(iter(observed))
    context.update(
        {
            "result_count": count,
            "owner_ids": sorted(owner_ids),
            "executor_ids": sorted(executor_ids),
            "valid": not errors,
            "errors": errors,
        }
    )
    return context
