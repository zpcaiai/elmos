"""Fail-closed quarantine and preflight for externally supplied evidence.

This module validates bytes, scope, digests, roles, organizations, and an exact
local admission allowlist.  It deliberately contains no caller-controlled trust
shortcut: policy admission is not signature verification, independent evidence,
provider execution, production execution, approval, or certification.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifact_binding import ContentReference, read_content_reference
from .canonical import canonical_digest, strict_json_copy
from .evidence_models import (
    EvidenceContractError,
    digest,
    exact_mapping,
    token,
)


_ROLE_FIELDS = frozenset({"principal_id", "organization_id"})
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "receipt_id",
        "evidence_kind",
        "scope",
        "target_artifact_digest",
        "environment_digest",
        "corpus_digest",
        "authorization_digest",
        "replay_digest",
        "raw_evidence",
        "author",
        "executor",
        "verifier",
        "execution_state",
        "signature_state",
        "receipt_digest",
    }
)
_POLICY_FIELDS = frozenset(
    {
        "schema_version",
        "policy_id",
        "tenant_id",
        "project_id",
        "allowed_evidence_kinds",
        "allowed_receipt_digests",
        "allowed_organizations",
        "revoked_principals",
        "require_distinct_organizations",
        "trust_root_state",
    }
)
_PREFLIGHT_FIELDS = frozenset(
    {
        "schema_version",
        "scope",
        "release_digest",
        "provider_adapter",
        "independent_holdout",
        "representative_workload",
        "production_change",
    }
)
_EXTERNAL_NON_RESULTS = {
    "external_receipt_trust": "NOT_RUN",
    "independent_holdout": "NOT_RUN",
    "real_provider_execution": "NOT_RUN",
    "representative_customer_workload": "NOT_RUN",
    "production_canary": "NOT_RUN",
    "production_rollback": "NOT_RUN",
    "production_writes": "NOT_RUN",
    "external_certification": "NOT_CERTIFIED",
}


def _string_array(value: object, label: str, *, maximum: int = 4096) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise EvidenceContractError(f"{label} must be an array of at most {maximum} identifiers")
    result = tuple(token(item, f"{label}[{index}]") for index, item in enumerate(value))
    if len(set(result)) != len(result):
        raise EvidenceContractError(f"{label} contains duplicates")
    return result


def _digest_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 4096:
        raise EvidenceContractError(f"{label} must be a bounded digest array")
    result = tuple(digest(item, f"{label}[{index}]") for index, item in enumerate(value))
    if len(set(result)) != len(result):
        raise EvidenceContractError(f"{label} contains duplicates")
    return result


def _role(value: object, label: str) -> dict[str, str]:
    document = exact_mapping(value, _ROLE_FIELDS, label)
    return {
        "principal_id": token(document["principal_id"], f"{label}.principal_id"),
        "organization_id": token(document["organization_id"], f"{label}.organization_id"),
    }


def _receipt_body(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: strict_json_copy(value, field=f"receipt.{key}")
        for key, value in document.items()
        if key != "receipt_digest"
    }


def ingest_external_receipt(
    receipt: object,
    *,
    evidence_root: Path,
    policy: object,
) -> dict[str, Any]:
    """Admit an exact external receipt to local quarantine policy, never to trust."""

    document = exact_mapping(receipt, _RECEIPT_FIELDS, "external receipt")
    policy_document = exact_mapping(policy, _POLICY_FIELDS, "evidence intake policy")
    if document["schema_version"] != "1.0" or policy_document["schema_version"] != "1.0":
        raise EvidenceContractError("external receipt and policy schema_version must be 1.0")
    token(document["receipt_id"], "receipt_id")
    evidence_kind = token(document["evidence_kind"], "evidence_kind")
    receipt_digest = digest(document["receipt_digest"], "receipt_digest")
    if canonical_digest(_receipt_body(document)) != receipt_digest:
        raise EvidenceContractError("external receipt digest is stale")
    for field in (
        "target_artifact_digest",
        "environment_digest",
        "corpus_digest",
        "authorization_digest",
        "replay_digest",
    ):
        digest(document[field], field)
    if document["signature_state"] != "UNVERIFIED_CALLER_ASSERTION":
        raise EvidenceContractError("caller-controlled signature_state must remain unverified")
    execution_state = document["execution_state"]
    if execution_state not in {"PASSED", "FAILED", "UNKNOWN", "INCONCLUSIVE", "NOT_RUN"}:
        raise EvidenceContractError("external receipt execution_state is invalid")
    scope = exact_mapping(
        document["scope"],
        frozenset({"tenant_id", "project_id", "campaign_id", "policy_revision", "source_revision"}),
        "external receipt scope",
    )
    parsed_scope = {key: token(value, f"scope.{key}") for key, value in scope.items()}
    author = _role(document["author"], "author")
    executor = _role(document["executor"], "executor")
    verifier = _role(document["verifier"], "verifier")
    content = ContentReference.from_mapping(document["raw_evidence"])
    raw = read_content_reference(content, evidence_root)

    policy_id = token(policy_document["policy_id"], "policy_id")
    policy_tenant = token(policy_document["tenant_id"], "policy.tenant_id")
    policy_project = token(policy_document["project_id"], "policy.project_id")
    allowed_kinds = set(_string_array(policy_document["allowed_evidence_kinds"], "allowed_evidence_kinds"))
    allowed_receipts = set(
        _digest_array(policy_document["allowed_receipt_digests"], "allowed_receipt_digests")
    )
    allowed_orgs = set(_string_array(policy_document["allowed_organizations"], "allowed_organizations"))
    revoked = set(_string_array(policy_document["revoked_principals"], "revoked_principals"))
    distinct_orgs = policy_document["require_distinct_organizations"]
    if not isinstance(distinct_orgs, bool):
        raise EvidenceContractError("require_distinct_organizations must be boolean")
    if policy_document["trust_root_state"] != "NOT_CONFIGURED":
        raise EvidenceContractError("local intake cannot assert an external trust root")

    failures: list[str] = []
    if parsed_scope["tenant_id"] != policy_tenant or parsed_scope["project_id"] != policy_project:
        failures.append("SCOPE_MISMATCH")
    principals = {author["principal_id"], executor["principal_id"], verifier["principal_id"]}
    if len(principals) != 3:
        failures.append("ROLE_PRINCIPALS_NOT_DISTINCT")
    organizations = {author["organization_id"], executor["organization_id"], verifier["organization_id"]}
    if distinct_orgs and len(organizations) != 3:
        failures.append("ROLE_ORGANIZATIONS_NOT_DISTINCT")
    for role_name, role in (
        ("AUTHOR", author),
        ("EXECUTOR", executor),
        ("VERIFIER", verifier),
    ):
        if role["principal_id"] in revoked:
            failures.append(f"{role_name}_REVOKED")
    if not organizations <= allowed_orgs:
        failures.append("ORGANIZATION_NOT_ALLOWED")
    if evidence_kind not in allowed_kinds:
        failures.append("EVIDENCE_KIND_NOT_ALLOWED")
    if receipt_digest not in allowed_receipts:
        failures.append("RECEIPT_NOT_ALLOWLISTED")
    if execution_state != "PASSED":
        failures.append("EXECUTION_STATE_NOT_PASSED")
    status = "EXTERNAL_RECEIPT_POLICY_ADMITTED" if not failures else "EXTERNAL_RECEIPT_QUARANTINED"
    return {
        "schema_version": "1.0",
        "status": status,
        "policy_id": policy_id,
        "policy_digest": canonical_digest(strict_json_copy(policy_document, field="policy")),
        "receipt_id": document["receipt_id"],
        "receipt_digest": receipt_digest,
        "raw_evidence_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "raw_evidence_bytes": len(raw),
        "local_admission_state": "ADMITTED_UNVERIFIED" if not failures else "QUARANTINED",
        "failures": failures,
        "external_states": dict(_EXTERNAL_NON_RESULTS),
        "limitations": [
            "LOCAL_POLICY_ADMISSION_IS_NOT_SIGNATURE_VERIFICATION",
            "LOCAL_ROLE_LABELS_DO_NOT_PROVE_ORGANIZATIONAL_INDEPENDENCE",
            "EXTERNAL_EXECUTION_AND_CERTIFICATION_REMAIN_NOT_RUN",
        ],
    }


def evaluate_external_preflight(config: object) -> dict[str, Any]:
    """Validate production-shaped prerequisites without running any external action."""

    document = exact_mapping(config, _PREFLIGHT_FIELDS, "external preflight")
    canonical_input = strict_json_copy(document, field="external preflight")
    if document["schema_version"] != "1.0":
        raise EvidenceContractError("external preflight schema_version must be 1.0")
    scope = exact_mapping(
        document["scope"],
        frozenset({"tenant_id", "project_id", "campaign_id", "policy_revision", "source_revision"}),
        "external preflight scope",
    )
    parsed_scope = {key: token(value, f"scope.{key}") for key, value in scope.items()}
    release_digest = digest(document["release_digest"], "release_digest")
    provider = exact_mapping(
        document["provider_adapter"],
        frozenset(
            {
                "provider_id",
                "adapter_id",
                "adapter_registry_digest",
                "executable_digest",
                "effect_class",
                "rollback_adapter_id",
                "authorization_digest",
            }
        ),
        "provider adapter",
    )
    token(provider["provider_id"], "provider_id")
    adapter_id = token(provider["adapter_id"], "adapter_id")
    adapter_registry_digest = digest(provider["adapter_registry_digest"], "provider.adapter_registry_digest")
    executable_digest = digest(provider["executable_digest"], "provider.executable_digest")
    provider_authorization_digest = digest(provider["authorization_digest"], "provider.authorization_digest")
    if provider["effect_class"] != "REVERSIBLE":
        raise EvidenceContractError("production provider adapter must be reversible")
    rollback_adapter_id = token(provider["rollback_adapter_id"], "rollback_adapter_id")
    if adapter_id == rollback_adapter_id:
        raise EvidenceContractError("provider and rollback adapters must be distinct")

    holdout = exact_mapping(
        document["independent_holdout"],
        frozenset({"manifest_digest", "case_count", "owner", "executor", "verifier", "authorization_digest"}),
        "independent holdout",
    )
    representative = exact_mapping(
        document["representative_workload"],
        frozenset({"manifest_digest", "case_count", "customer_authorizer", "authorization_digest"}),
        "representative workload",
    )
    production = exact_mapping(
        document["production_change"],
        frozenset(
            {
                "environment",
                "pkcs11_secret_reference",
                "canary_plan_digest",
                "rollback_plan_digest",
                "authorization_digest",
            }
        ),
        "production change",
    )
    corpus_manifest_digests: dict[str, str] = {}
    corpus_authorization_digests: dict[str, str] = {}
    for item, label in ((holdout, "holdout"), (representative, "representative")):
        corpus_manifest_digests[label] = digest(item["manifest_digest"], f"{label}.manifest_digest")
        corpus_authorization_digests[label] = digest(
            item["authorization_digest"], f"{label}.authorization_digest"
        )
        count = item["case_count"]
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise EvidenceContractError(f"{label}.case_count must be positive")
    owner = _role(holdout["owner"], "holdout.owner")
    executor = _role(holdout["executor"], "holdout.executor")
    verifier = _role(holdout["verifier"], "holdout.verifier")
    customer = _role(representative["customer_authorizer"], "customer_authorizer")
    production_environment = token(production["environment"], "production.environment")
    secret_reference = production["pkcs11_secret_reference"]
    if (
        not isinstance(secret_reference, str)
        or not secret_reference.startswith("pkcs11:")
        or not 8 <= len(secret_reference) <= 2048
    ):
        raise EvidenceContractError("production secret must be an opaque pkcs11 reference")
    canary_plan_digest = digest(production["canary_plan_digest"], "production.canary_plan_digest")
    rollback_plan_digest = digest(production["rollback_plan_digest"], "production.rollback_plan_digest")
    production_authorization_digest = digest(
        production["authorization_digest"], "production.authorization_digest"
    )
    actors = {
        owner["principal_id"],
        executor["principal_id"],
        verifier["principal_id"],
        customer["principal_id"],
    }
    organizations = {
        owner["organization_id"],
        executor["organization_id"],
        verifier["organization_id"],
        customer["organization_id"],
    }
    digest_bindings = {
        "release_digest": release_digest,
        "authorization_digests": {
            "provider_adapter": provider_authorization_digest,
            "independent_holdout": corpus_authorization_digests["holdout"],
            "representative_workload": corpus_authorization_digests["representative"],
            "production_change": production_authorization_digest,
        },
        "adapter_digests": {
            "registry": adapter_registry_digest,
            "executable": executable_digest,
        },
        "corpus_manifest_digests": {
            "independent_holdout": corpus_manifest_digests["holdout"],
            "representative_workload": corpus_manifest_digests["representative"],
        },
        "canary_rollback_digests": {
            "canary_plan": canary_plan_digest,
            "rollback_plan": rollback_plan_digest,
        },
    }
    canonical_input_digest = canonical_digest(canonical_input)
    preflight_digest = canonical_digest(
        {
            "schema_version": "1.0",
            "scope": parsed_scope,
            "canonical_input_digest": canonical_input_digest,
            "digest_bindings": digest_bindings,
        }
    )
    checks = {
        "canonical_input_digest_recorded": True,
        "release_digest_format_validated": True,
        "authorization_digest_fields_validated": True,
        "adapter_digest_fields_validated": True,
        "corpus_manifest_digest_fields_validated": True,
        "canary_rollback_digest_fields_validated": True,
        "reversible_adapter_relationship_declared": True,
        "external_actor_principals_distinct": len(actors) == 4,
        "external_actor_organizations_distinct": len(organizations) == 4,
        "representative_workload_manifest_declared": representative["case_count"] > 0,
        "pkcs11_secret_reference_declared": True,
        "external_signatures_verified": False,
    }
    structurally_ready = all(value for key, value in checks.items() if key != "external_signatures_verified")
    return {
        "schema_version": "1.0",
        "status": ("STRUCTURALLY_READY_FOR_EXTERNAL_TRUST_VERIFICATION" if structurally_ready else "BLOCKED"),
        "environment": production_environment,
        "canonical_input_digest": canonical_input_digest,
        "digest_bindings": digest_bindings,
        "preflight_digest": preflight_digest,
        "checks": checks,
        "external_operations_executed": False,
        "external_states": dict(_EXTERNAL_NON_RESULTS),
        "next_required_gate": "INDEPENDENT_SIGNATURE_AND_TRUST_ROOT_VERIFICATION",
    }
