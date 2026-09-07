"""Typed deterministic receipts for bounded local evidence campaigns."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .canonical import CanonicalValueError, canonical_digest, is_sha256_digest, strict_json_copy


EVIDENCE_CONTRACT_VERSION = "1.0"
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,191}$")
_CAMPAIGN_TYPES = frozenset({"local-holdout", "provider-contract-simulation", "production-like-rehearsal"})
_EVIDENCE_STATES = {
    "local-holdout": "LOCAL_HOLDOUT_EXECUTED_SELF_ATTESTED",
    "provider-contract-simulation": "LOCAL_PROVIDER_CONTRACT_SIMULATED_SELF_ATTESTED",
    "production-like-rehearsal": "LOCAL_PRODUCTION_LIKE_REHEARSAL_SELF_ATTESTED",
}
_CASE_RESULT_COMMON_FIELDS = frozenset({"case_id", "status"})
_CASE_RESULT_STATUSES = frozenset({"PASSED", "BLOCKED", "FAILED"})
_LOCAL_RESULT_FIELDS = frozenset(
    {
        "case_id",
        "status",
        "case_digest",
        "request_digest",
        "observed_status",
        "observed_error_code",
        "observed_result_digest",
    }
)
_LOCAL_OVERLAP_FIELDS = frozenset({"case_id", "status", "overlap"})
_PROVIDER_RESULT_FIELDS = frozenset(
    {
        "case_id",
        "status",
        "case_digest",
        "provider_request_digest",
        "provider_response_digest",
        "simulated_provider_state",
        "mapped_error",
        "bounded_runtime_state",
        "bounded_runtime_error",
        "runtime_request_digest",
        "runtime_result_digest",
        "skill_registry_digest",
        "capability_registry_digest",
        "public_method_registry_digest",
        "provider_calls_executed",
    }
)
_REHEARSAL_RESULT_FIELDS = frozenset(
    {
        "case_id",
        "status",
        "initial_state_digest",
        "canary_state_digest",
        "rollback_state_digest",
        "event_set_digest",
        "error_basis_points",
        "uncertain_outcome",
        "control_decision",
        "rollback_complete",
        "network_calls_executed",
        "provider_calls_executed",
        "production_writes_executed",
    }
)
_REPLAY_FIELDS = frozenset({"operation", "campaign_type", "manifest_digest", "expected_execution_digest"})
EXTERNAL_STATES = {
    "archive_scripts_executed": False,
    "independent_holdout": "NOT_RUN",
    "provider_execution": "NOT_RUN",
    "production_canary": "NOT_RUN",
    "production_deployment": "NOT_RUN",
    "production_writes": "NOT_RUN",
    "independent_verification": "NOT_RUN",
    "external_certification": "NOT_CERTIFIED",
}


class EvidenceContractError(ValueError):
    """Raised when a campaign or receipt violates the evidence contract."""


def exact_mapping(value: object, expected: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceContractError(f"{label} must be an object")
    if any(not isinstance(key, str) or not key for key in value):
        raise EvidenceContractError(f"{label} fields must be non-empty strings")
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise EvidenceContractError(f"{label} fields differ: missing={missing} extra={extra}")
    return value


def token(value: object, label: str) -> str:
    if not isinstance(value, str) or _TOKEN.fullmatch(value) is None:
        raise EvidenceContractError(f"{label} must be a bounded identifier")
    return value


def digest(value: object, label: str) -> str:
    if not is_sha256_digest(value):
        raise EvidenceContractError(f"{label} must be lowercase sha256")
    return value


def bounded_json_copy(value: object, label: str) -> Any:
    """Copy untrusted JSON while normalizing canonical failures to contract errors."""

    try:
        return strict_json_copy(value, field=label)
    except CanonicalValueError as exc:
        raise EvidenceContractError(str(exc)) from exc


def _optional_token(value: object, label: str) -> str | None:
    return None if value is None else token(value, label)


def validated_case_results(
    value: object,
    campaign_type: str,
) -> tuple[Mapping[str, Any], ...]:
    """Validate exact fail-closed result variants for one campaign type."""

    if not isinstance(value, (list, tuple)) or not value:
        raise EvidenceContractError("campaign receipt case_results must be a non-empty array")
    copied = bounded_json_copy(list(value), "case_results")
    results: list[Mapping[str, Any]] = []
    for index, item in enumerate(copied):
        label = f"case_results[{index}]"
        if not isinstance(item, Mapping):
            raise EvidenceContractError(f"{label} must be an object")
        actual = frozenset(item)
        missing = sorted(_CASE_RESULT_COMMON_FIELDS - actual)
        if missing:
            raise EvidenceContractError(f"{label} is missing common fields: {missing}")
        token(item["case_id"], f"{label}.case_id")
        if not isinstance(item["status"], str) or item["status"] not in _CASE_RESULT_STATUSES:
            raise EvidenceContractError(f"{label}.status is invalid")
        fields = frozenset(item)
        if campaign_type == "local-holdout" and fields == _LOCAL_OVERLAP_FIELDS:
            if item["case_id"] != "corpus-separation" or item["status"] != "BLOCKED":
                raise EvidenceContractError(f"{label} corpus overlap result is invalid")
            overlaps = item["overlap"]
            if not isinstance(overlaps, list) or not overlaps:
                raise EvidenceContractError(f"{label}.overlap must be a non-empty array")
            for overlap_index, overlap in enumerate(overlaps):
                digest(overlap, f"{label}.overlap[{overlap_index}]")
        elif campaign_type == "local-holdout" and fields == _LOCAL_RESULT_FIELDS:
            if item["status"] not in {"PASSED", "FAILED"}:
                raise EvidenceContractError(f"{label}.status is invalid for a holdout case")
            for field in ("case_digest", "request_digest", "observed_result_digest"):
                digest(item[field], f"{label}.{field}")
            if item["observed_status"] not in {
                "EXECUTED",
                "BLOCKED",
                "REQUIRES_ADAPTER",
                "FAILED",
            }:
                raise EvidenceContractError(f"{label}.observed_status is invalid")
            _optional_token(item["observed_error_code"], f"{label}.observed_error_code")
        elif campaign_type == "provider-contract-simulation" and fields == _PROVIDER_RESULT_FIELDS:
            if item["status"] not in {"PASSED", "FAILED"}:
                raise EvidenceContractError(f"{label}.status is invalid for a provider fixture")
            for field in (
                "case_digest",
                "provider_request_digest",
                "provider_response_digest",
                "runtime_request_digest",
                "runtime_result_digest",
                "skill_registry_digest",
                "capability_registry_digest",
                "public_method_registry_digest",
            ):
                digest(item[field], f"{label}.{field}")
            if item["simulated_provider_state"] not in {
                "SUCCEEDED",
                "FAILED",
                "UNKNOWN",
                "TIMEOUT",
            }:
                raise EvidenceContractError(f"{label}.simulated_provider_state is invalid")
            if item["bounded_runtime_state"] not in {
                "EXECUTED",
                "BLOCKED",
                "REQUIRES_ADAPTER",
                "FAILED",
            }:
                raise EvidenceContractError(f"{label}.bounded_runtime_state is invalid")
            _optional_token(item["mapped_error"], f"{label}.mapped_error")
            _optional_token(item["bounded_runtime_error"], f"{label}.bounded_runtime_error")
            if item["provider_calls_executed"] is not False:
                raise EvidenceContractError(f"{label} cannot claim provider execution")
        elif campaign_type == "production-like-rehearsal" and fields == _REHEARSAL_RESULT_FIELDS:
            if item["case_id"] != "canary-rehearsal" or item["status"] not in {
                "PASSED",
                "BLOCKED",
            }:
                raise EvidenceContractError(f"{label} rehearsal identity or status is invalid")
            for field in (
                "initial_state_digest",
                "canary_state_digest",
                "rollback_state_digest",
                "event_set_digest",
            ):
                digest(item[field], f"{label}.{field}")
            basis_points = item["error_basis_points"]
            if (
                isinstance(basis_points, bool)
                or not isinstance(basis_points, int)
                or not 0 <= basis_points <= 10_000
            ):
                raise EvidenceContractError(f"{label}.error_basis_points is invalid")
            for field in ("uncertain_outcome", "rollback_complete"):
                if not isinstance(item[field], bool):
                    raise EvidenceContractError(f"{label}.{field} must be boolean")
            if item["control_decision"] not in {"PROMOTE", "ROLLBACK"}:
                raise EvidenceContractError(f"{label}.control_decision is invalid")
            if item["network_calls_executed"] is not False:
                raise EvidenceContractError(f"{label} cannot claim network execution")
            if item["provider_calls_executed"] is not False:
                raise EvidenceContractError(f"{label} cannot claim provider execution")
            if item["production_writes_executed"] != 0:
                raise EvidenceContractError(f"{label} cannot claim production writes")
        else:
            raise EvidenceContractError(f"{label} fields do not match campaign type {campaign_type}")
        results.append(item)
    return tuple(results)


def validate_campaign_result_status(
    campaign_status: str,
    case_results: tuple[Mapping[str, Any], ...],
) -> None:
    """Require a unique ordered case ledger and derive its exact top-level status."""

    identities = [str(item["case_id"]) for item in case_results]
    if len(identities) != len(set(identities)):
        raise EvidenceContractError("campaign receipt case_results contain duplicate case_id values")
    if identities != sorted(identities):
        raise EvidenceContractError("campaign receipt case_results must be sorted by case_id")
    statuses = {str(item["status"]) for item in case_results}
    if "FAILED" in statuses:
        derived = "FAILED"
    elif "BLOCKED" in statuses:
        derived = "BLOCKED"
    else:
        derived = "PASSED"
    if campaign_status != derived:
        raise EvidenceContractError(
            f"campaign receipt status {campaign_status} contradicts derived case status {derived}"
        )


@dataclass(frozen=True)
class CampaignScope:
    tenant_id: str
    project_id: str
    campaign_id: str
    policy_revision: str
    source_revision: str

    @classmethod
    def from_mapping(cls, value: object) -> "CampaignScope":
        document = exact_mapping(
            value,
            frozenset({"tenant_id", "project_id", "campaign_id", "policy_revision", "source_revision"}),
            "campaign scope",
        )
        return cls(
            tenant_id=token(document["tenant_id"], "scope.tenant_id"),
            project_id=token(document["project_id"], "scope.project_id"),
            campaign_id=token(document["campaign_id"], "scope.campaign_id"),
            policy_revision=token(document["policy_revision"], "scope.policy_revision"),
            source_revision=token(document["source_revision"], "scope.source_revision"),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "campaign_id": self.campaign_id,
            "policy_revision": self.policy_revision,
            "source_revision": self.source_revision,
        }


@dataclass(frozen=True)
class CampaignReceipt:
    campaign_type: str
    scope: CampaignScope
    target_artifact_digest: str
    environment_digest: str
    corpus_digest: str
    runtime_binding_digest: str
    manifest_digest: str
    status: str
    evidence_state: str
    case_results: tuple[Mapping[str, Any], ...]
    execution_digest: str
    replay: Mapping[str, Any]
    external_states: Mapping[str, Any]
    limitations: tuple[str, ...]
    receipt_digest: str

    @classmethod
    def create(
        cls,
        *,
        campaign_type: str,
        scope: CampaignScope,
        target_artifact_digest: str,
        environment_digest: str,
        corpus_digest: str,
        runtime_binding_digest: str,
        manifest_digest: str,
        status: str,
        case_results: tuple[Mapping[str, Any], ...],
        limitations: tuple[str, ...],
    ) -> "CampaignReceipt":
        if campaign_type not in _CAMPAIGN_TYPES:
            raise EvidenceContractError("campaign_type is unsupported")
        if status not in {"PASSED", "BLOCKED", "FAILED"}:
            raise EvidenceContractError("campaign status is invalid")
        copied_results = validated_case_results(case_results, campaign_type)
        validate_campaign_result_status(status, copied_results)
        copied_limitations = tuple(
            token(item, f"limitations[{index}]") for index, item in enumerate(limitations)
        )
        target = digest(target_artifact_digest, "target_artifact_digest")
        environment = digest(environment_digest, "environment_digest")
        corpus = digest(corpus_digest, "corpus_digest")
        runtime_binding = digest(runtime_binding_digest, "runtime_binding_digest")
        manifest = digest(manifest_digest, "manifest_digest")
        execution = canonical_digest(
            {
                "runtime_binding_digest": runtime_binding,
                "case_results": list(copied_results),
            }
        )
        replay = {
            "operation": "campaign-replay",
            "campaign_type": campaign_type,
            "manifest_digest": manifest,
            "expected_execution_digest": execution,
        }
        body = {
            "schema_version": EVIDENCE_CONTRACT_VERSION,
            "campaign_type": campaign_type,
            "scope": scope.as_dict(),
            "target_artifact_digest": target,
            "environment_digest": environment,
            "corpus_digest": corpus,
            "runtime_binding_digest": runtime_binding,
            "manifest_digest": manifest,
            "status": status,
            "evidence_state": _EVIDENCE_STATES[campaign_type],
            "case_results": list(copied_results),
            "execution_digest": execution,
            "replay": replay,
            "external_states": dict(EXTERNAL_STATES),
            "limitations": list(copied_limitations),
        }
        return cls(
            campaign_type=campaign_type,
            scope=scope,
            target_artifact_digest=target,
            environment_digest=environment,
            corpus_digest=corpus,
            runtime_binding_digest=runtime_binding,
            manifest_digest=manifest,
            status=status,
            evidence_state=_EVIDENCE_STATES[campaign_type],
            case_results=copied_results,
            execution_digest=execution,
            replay=replay,
            external_states=dict(EXTERNAL_STATES),
            limitations=copied_limitations,
            receipt_digest=canonical_digest(body),
        )

    @classmethod
    def from_mapping(cls, value: object) -> "CampaignReceipt":
        fields = frozenset(
            {
                "schema_version",
                "campaign_type",
                "scope",
                "target_artifact_digest",
                "environment_digest",
                "corpus_digest",
                "runtime_binding_digest",
                "manifest_digest",
                "status",
                "evidence_state",
                "case_results",
                "execution_digest",
                "replay",
                "external_states",
                "limitations",
                "receipt_digest",
            }
        )
        document = exact_mapping(bounded_json_copy(value, "campaign receipt"), fields, "campaign receipt")
        if document["schema_version"] != EVIDENCE_CONTRACT_VERSION:
            raise EvidenceContractError("campaign receipt schema_version must be 1.0")
        campaign_type = document["campaign_type"]
        if not isinstance(campaign_type, str) or campaign_type not in _CAMPAIGN_TYPES:
            raise EvidenceContractError("campaign receipt type is unsupported")
        status = document["status"]
        if not isinstance(status, str) or status not in {"PASSED", "BLOCKED", "FAILED"}:
            raise EvidenceContractError("campaign receipt status is invalid")
        if document["evidence_state"] != _EVIDENCE_STATES[campaign_type]:
            raise EvidenceContractError("campaign receipt evidence_state is invalid")
        cases = document["case_results"]
        limitations = document["limitations"]
        if not isinstance(cases, list) or not isinstance(limitations, list):
            raise EvidenceContractError("campaign receipt cases and limitations must be arrays")
        parsed_cases = validated_case_results(cases, campaign_type)
        validate_campaign_result_status(status, parsed_cases)
        if not limitations:
            raise EvidenceContractError("campaign receipt limitations must be a non-empty array")
        parsed_limitations = tuple(
            token(item, f"limitations[{index}]") for index, item in enumerate(limitations)
        )
        if len(set(parsed_limitations)) != len(parsed_limitations):
            raise EvidenceContractError("campaign receipt limitations must be unique")
        if document["external_states"] != EXTERNAL_STATES:
            raise EvidenceContractError("campaign receipt external states cannot be promoted locally")
        target_artifact_digest = digest(document["target_artifact_digest"], "target_artifact_digest")
        environment_digest = digest(document["environment_digest"], "environment_digest")
        corpus_digest = digest(document["corpus_digest"], "corpus_digest")
        runtime_binding_digest = digest(document["runtime_binding_digest"], "runtime_binding_digest")
        manifest_digest = digest(document["manifest_digest"], "manifest_digest")
        execution_digest = digest(document["execution_digest"], "execution_digest")
        replay = exact_mapping(document["replay"], _REPLAY_FIELDS, "campaign receipt replay")
        if replay["operation"] != "campaign-replay":
            raise EvidenceContractError("campaign receipt replay operation is invalid")
        if replay["campaign_type"] != campaign_type:
            raise EvidenceContractError("campaign receipt replay campaign_type is not cross-linked")
        replay_manifest_digest = digest(replay["manifest_digest"], "replay.manifest_digest")
        if replay_manifest_digest != manifest_digest:
            raise EvidenceContractError("campaign receipt replay manifest_digest is not cross-linked")
        replay_execution_digest = digest(
            replay["expected_execution_digest"], "replay.expected_execution_digest"
        )
        if replay_execution_digest != execution_digest:
            raise EvidenceContractError(
                "campaign receipt replay expected_execution_digest is not cross-linked"
            )
        parsed = cls(
            campaign_type=campaign_type,
            scope=CampaignScope.from_mapping(document["scope"]),
            target_artifact_digest=target_artifact_digest,
            environment_digest=environment_digest,
            corpus_digest=corpus_digest,
            runtime_binding_digest=runtime_binding_digest,
            manifest_digest=manifest_digest,
            status=status,
            evidence_state=document["evidence_state"],
            case_results=parsed_cases,
            execution_digest=execution_digest,
            replay=replay,
            external_states=bounded_json_copy(document["external_states"], "external_states"),
            limitations=parsed_limitations,
            receipt_digest=digest(document["receipt_digest"], "receipt_digest"),
        )
        if (
            canonical_digest(
                {
                    "runtime_binding_digest": parsed.runtime_binding_digest,
                    "case_results": list(parsed.case_results),
                }
            )
            != parsed.execution_digest
        ):
            raise EvidenceContractError("campaign receipt execution digest is stale")
        body = parsed.as_dict()
        body.pop("receipt_digest")
        if canonical_digest(body) != parsed.receipt_digest:
            raise EvidenceContractError("campaign receipt digest is stale")
        return parsed

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EVIDENCE_CONTRACT_VERSION,
            "campaign_type": self.campaign_type,
            "scope": self.scope.as_dict(),
            "target_artifact_digest": self.target_artifact_digest,
            "environment_digest": self.environment_digest,
            "corpus_digest": self.corpus_digest,
            "runtime_binding_digest": self.runtime_binding_digest,
            "manifest_digest": self.manifest_digest,
            "status": self.status,
            "evidence_state": self.evidence_state,
            "case_results": list(self.case_results),
            "execution_digest": self.execution_digest,
            "replay": dict(self.replay),
            "external_states": dict(self.external_states),
            "limitations": list(self.limitations),
            "receipt_digest": self.receipt_digest,
        }
