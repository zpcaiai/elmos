"""Typed request, policy, evidence, and result contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .canonical import canonical_digest, is_sha256_digest, strict_json_copy


class ContractError(ValueError):
    """Raised when an untrusted runtime document violates its contract."""


class ExecutionStatus(str, Enum):
    EXECUTED = "EXECUTED"
    BLOCKED = "BLOCKED"
    REQUIRES_ADAPTER = "REQUIRES_ADAPTER"
    FAILED = "FAILED"


class SkillKind(str, Enum):
    ROOT = "root"
    PACKAGE = "package"
    CHILD = "child"


_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,191}$")
CONTRACT_VERSION = "1.0"
_REQUEST_KEYS = frozenset(
    {
        "contract_version",
        "tenant_id",
        "project_id",
        "correlation_id",
        "idempotency_key",
        "policy_revision",
        "source_revision",
        "payload",
        "policy",
        "dependencies",
        "observations",
    }
)
_REQUEST_REQUIRED_KEYS = _REQUEST_KEYS - {"idempotency_key"}
_POLICY_KEYS = frozenset(
    {
        "allowed_skills",
        "allowed_actions",
        "allowed_permissions",
        "approval_required_actions",
        "approved_actions",
        "allowed_sandbox_modes",
        "allowed_providers",
        "allowed_data_classes",
        "max_nodes",
        "max_parallelism",
        "max_retries",
        "max_cost_micros",
        "min_quality_basis_points",
        "allow_global_knowledge",
    }
)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{field} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], allowed: frozenset[str], field: str) -> None:
    extras = sorted(set(value) - allowed)
    if extras:
        raise ContractError(f"{field} contains unsupported fields: {', '.join(extras)}")


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ContractError(f"{field} must be a non-empty bounded identifier")
    return value


def _bounded_text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ContractError(f"{field} must be a non-empty string of at most {maximum} characters")
    if any(ord(character) < 32 and character not in "\t\n\r" for character in value):
        raise ContractError(f"{field} contains forbidden control characters")
    return value


def _string_set(value: object, field: str, *, default: tuple[str, ...] = ()) -> frozenset[str]:
    if value is None:
        return frozenset(default)
    if not isinstance(value, list):
        raise ContractError(f"{field} must be an array")
    parsed: set[str] = set()
    for index, item in enumerate(value):
        parsed.add(_token(item, f"{field}[{index}]"))
    if len(parsed) != len(value):
        raise ContractError(f"{field} must not contain duplicates")
    return frozenset(parsed)


def _bounded_int(value: object, field: str, *, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ContractError(f"{field} must be an integer in [{minimum}, {maximum}]")
    return value


@dataclass(frozen=True)
class ScopeEnvelope:
    tenant_id: str
    project_id: str
    correlation_id: str
    policy_revision: str
    source_revision: str
    idempotency_key: str | None

    @classmethod
    def from_mapping(cls, value: object) -> "ScopeEnvelope":
        document = _mapping(value, "request")
        idempotency_key_value = document.get("idempotency_key")
        if idempotency_key_value is not None:
            idempotency_key_value = _token(idempotency_key_value, "request.idempotency_key")
        return cls(
            tenant_id=_token(document.get("tenant_id"), "request.tenant_id"),
            project_id=_token(document.get("project_id"), "request.project_id"),
            correlation_id=_token(document.get("correlation_id"), "request.correlation_id"),
            policy_revision=_token(document.get("policy_revision"), "request.policy_revision"),
            source_revision=_token(document.get("source_revision"), "request.source_revision"),
            idempotency_key=idempotency_key_value,
        )

    def as_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "correlation_id": self.correlation_id,
            "policy_revision": self.policy_revision,
            "source_revision": self.source_revision,
        }
        if self.idempotency_key is not None:
            document["idempotency_key"] = self.idempotency_key
        return document


@dataclass(frozen=True)
class ExecutionPolicy:
    allowed_skills: frozenset[str]
    allowed_actions: frozenset[str]
    allowed_permissions: frozenset[str]
    approval_required_actions: frozenset[str]
    approved_actions: frozenset[str]
    allowed_sandbox_modes: frozenset[str]
    allowed_providers: frozenset[str]
    allowed_data_classes: frozenset[str]
    max_nodes: int
    max_parallelism: int
    max_retries: int
    max_cost_micros: int
    min_quality_basis_points: int
    allow_global_knowledge: bool

    @classmethod
    def from_mapping(cls, value: object) -> "ExecutionPolicy":
        document = {} if value is None else _mapping(value, "policy")
        _exact_keys(document, _POLICY_KEYS, "policy")
        global_knowledge = document.get("allow_global_knowledge", False)
        if not isinstance(global_knowledge, bool):
            raise ContractError("policy.allow_global_knowledge must be a boolean")
        return cls(
            allowed_skills=_string_set(document.get("allowed_skills"), "policy.allowed_skills"),
            allowed_actions=_string_set(document.get("allowed_actions"), "policy.allowed_actions"),
            allowed_permissions=_string_set(
                document.get("allowed_permissions"), "policy.allowed_permissions"
            ),
            approval_required_actions=_string_set(
                document.get("approval_required_actions"), "policy.approval_required_actions"
            ),
            approved_actions=_string_set(
                document.get("approved_actions"), "policy.approved_actions"
            ),
            allowed_sandbox_modes=_string_set(
                document.get("allowed_sandbox_modes"),
                "policy.allowed_sandbox_modes",
                default=("read-only",),
            ),
            allowed_providers=_string_set(
                document.get("allowed_providers"), "policy.allowed_providers"
            ),
            allowed_data_classes=_string_set(
                document.get("allowed_data_classes"), "policy.allowed_data_classes"
            ),
            max_nodes=_bounded_int(
                document.get("max_nodes"), "policy.max_nodes", default=256, minimum=1, maximum=4096
            ),
            max_parallelism=_bounded_int(
                document.get("max_parallelism"),
                "policy.max_parallelism",
                default=4,
                minimum=1,
                maximum=64,
            ),
            max_retries=_bounded_int(
                document.get("max_retries"), "policy.max_retries", default=2, minimum=0, maximum=10
            ),
            max_cost_micros=_bounded_int(
                document.get("max_cost_micros"),
                "policy.max_cost_micros",
                default=0,
                minimum=0,
                maximum=10**15,
            ),
            min_quality_basis_points=_bounded_int(
                document.get("min_quality_basis_points"),
                "policy.min_quality_basis_points",
                default=0,
                minimum=0,
                maximum=10_000,
            ),
            allow_global_knowledge=global_knowledge,
        )


@dataclass(frozen=True)
class DependencyReceipt:
    package_id: str
    skill_name: str
    tenant_id: str
    project_id: str
    correlation_id: str
    policy_revision: str
    source_revision: str
    status: ExecutionStatus
    request_digest: str
    result_digest: str
    receipt_digest: str

    @classmethod
    def from_mapping(cls, value: object) -> "DependencyReceipt":
        document = _mapping(value, "dependency receipt")
        allowed = frozenset(
            {
                "package_id",
                "skill_name",
                "tenant_id",
                "project_id",
                "correlation_id",
                "policy_revision",
                "source_revision",
                "status",
                "request_digest",
                "result_digest",
                "receipt_digest",
            }
        )
        _exact_keys(document, allowed, "dependency receipt")
        try:
            status = ExecutionStatus(document.get("status"))
        except ValueError as exc:
            raise ContractError("dependency receipt has an invalid status") from exc
        request_digest = document.get("request_digest")
        result_digest = document.get("result_digest")
        receipt_digest = document.get("receipt_digest")
        if (
            not is_sha256_digest(request_digest)
            or not is_sha256_digest(result_digest)
            or not is_sha256_digest(receipt_digest)
        ):
            raise ContractError("dependency receipt digests must be lowercase sha256 values")
        receipt = cls(
            package_id=_token(document.get("package_id"), "dependency receipt.package_id"),
            skill_name=_token(document.get("skill_name"), "dependency receipt.skill_name"),
            tenant_id=_token(document.get("tenant_id"), "dependency receipt.tenant_id"),
            project_id=_token(document.get("project_id"), "dependency receipt.project_id"),
            correlation_id=_token(
                document.get("correlation_id"), "dependency receipt.correlation_id"
            ),
            policy_revision=_token(
                document.get("policy_revision"), "dependency receipt.policy_revision"
            ),
            source_revision=_token(
                document.get("source_revision"), "dependency receipt.source_revision"
            ),
            status=status,
            request_digest=request_digest,
            result_digest=result_digest,
            receipt_digest=receipt_digest,
        )
        if canonical_digest(receipt.body()) != receipt.receipt_digest:
            raise ContractError("dependency receipt digest does not match its canonical body")
        return receipt

    def body(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "skill_name": self.skill_name,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "correlation_id": self.correlation_id,
            "policy_revision": self.policy_revision,
            "source_revision": self.source_revision,
            "status": self.status.value,
            "request_digest": self.request_digest,
            "result_digest": self.result_digest,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.body(), "receipt_digest": self.receipt_digest}


@dataclass(frozen=True)
class ExternalObservation:
    observation_id: str
    action: str
    tenant_id: str
    project_id: str
    correlation_id: str
    policy_revision: str
    source_revision: str
    evidence_digest: str
    byte_count: int
    executor_id: str
    verifier_id: str
    authorized: bool
    verified: bool
    observation_digest: str

    @classmethod
    def from_mapping(cls, value: object) -> "ExternalObservation":
        document = _mapping(value, "external observation")
        allowed = frozenset(
            {
                "observation_id",
                "action",
                "tenant_id",
                "project_id",
                "correlation_id",
                "policy_revision",
                "source_revision",
                "evidence_digest",
                "byte_count",
                "executor_id",
                "verifier_id",
                "authorized",
                "verified",
                "observation_digest",
            }
        )
        _exact_keys(document, allowed, "external observation")
        evidence_digest = document.get("evidence_digest")
        observation_digest = document.get("observation_digest")
        if not is_sha256_digest(evidence_digest) or not is_sha256_digest(observation_digest):
            raise ContractError("external observation digests must be lowercase sha256 values")
        byte_count = _bounded_int(
            document.get("byte_count"),
            "external observation.byte_count",
            default=0,
            minimum=1,
            maximum=2**63 - 1,
        )
        authorized = document.get("authorized")
        verified = document.get("verified")
        if not isinstance(authorized, bool) or not isinstance(verified, bool):
            raise ContractError("external observation authorization flags must be booleans")
        observation = cls(
            observation_id=_token(
                document.get("observation_id"), "external observation.observation_id"
            ),
            action=_token(document.get("action"), "external observation.action"),
            tenant_id=_token(document.get("tenant_id"), "external observation.tenant_id"),
            project_id=_token(document.get("project_id"), "external observation.project_id"),
            correlation_id=_token(
                document.get("correlation_id"), "external observation.correlation_id"
            ),
            policy_revision=_token(
                document.get("policy_revision"), "external observation.policy_revision"
            ),
            source_revision=_token(
                document.get("source_revision"), "external observation.source_revision"
            ),
            evidence_digest=evidence_digest,
            byte_count=byte_count,
            executor_id=_token(document.get("executor_id"), "external observation.executor_id"),
            verifier_id=_token(document.get("verifier_id"), "external observation.verifier_id"),
            authorized=authorized,
            verified=verified,
            observation_digest=observation_digest,
        )
        if canonical_digest(observation.body()) != observation.observation_digest:
            raise ContractError("external observation digest does not match its canonical body")
        return observation

    def body(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "action": self.action,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "correlation_id": self.correlation_id,
            "policy_revision": self.policy_revision,
            "source_revision": self.source_revision,
            "evidence_digest": self.evidence_digest,
            "byte_count": self.byte_count,
            "executor_id": self.executor_id,
            "verifier_id": self.verifier_id,
            "authorized": self.authorized,
            "verified": self.verified,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.body(), "observation_digest": self.observation_digest}


@dataclass(frozen=True)
class ExecutionRequest:
    envelope: ScopeEnvelope
    payload: Mapping[str, Any]
    policy: ExecutionPolicy
    dependencies: tuple[DependencyReceipt, ...]
    observations: tuple[ExternalObservation, ...]
    request_digest: str

    @classmethod
    def from_mapping(cls, value: object) -> "ExecutionRequest":
        document = _mapping(value, "request")
        _exact_keys(document, _REQUEST_KEYS, "request")
        missing = sorted(_REQUEST_REQUIRED_KEYS - set(document))
        if missing:
            raise ContractError(f"request is missing required fields: {', '.join(missing)}")
        if document.get("contract_version") != CONTRACT_VERSION:
            raise ContractError(f"request.contract_version must be {CONTRACT_VERSION}")
        canonical_request = strict_json_copy(document, field="request")
        payload = strict_json_copy(
            _mapping(document["payload"], "request.payload"), field="request.payload"
        )
        dependency_values = document["dependencies"]
        observation_values = document["observations"]
        if not isinstance(dependency_values, list) or not isinstance(observation_values, list):
            raise ContractError("request dependencies and observations must be arrays")
        dependencies = tuple(DependencyReceipt.from_mapping(item) for item in dependency_values)
        observations = tuple(ExternalObservation.from_mapping(item) for item in observation_values)
        if len({item.package_id for item in dependencies}) != len(dependencies):
            raise ContractError("request contains duplicate dependency package receipts")
        if len({item.observation_id for item in observations}) != len(observations):
            raise ContractError("request contains duplicate external observation identifiers")
        return cls(
            envelope=ScopeEnvelope.from_mapping(document),
            payload=payload,
            policy=ExecutionPolicy.from_mapping(document["policy"]),
            dependencies=dependencies,
            observations=observations,
            request_digest=canonical_digest(canonical_request),
        )


@dataclass(frozen=True)
class ExecutionError:
    code: str
    message: str
    retryable: bool = False
    details: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "code": _token(self.code, "execution error.code"),
            "message": _bounded_text(self.message, "execution error.message"),
            "retryable": self.retryable,
        }
        if self.details is not None:
            document["details"] = strict_json_copy(self.details, field="execution error.details")
        return document


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    skill_name: str
    package_id: str
    operation: str
    envelope: ScopeEnvelope
    output: Mapping[str, Any]
    error: ExecutionError | None
    warnings: tuple[str, ...]
    retry: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...]
    registry_digest: str
    request_digest: str
    result_digest: str
    dependency_receipt: Mapping[str, Any] | None

    @classmethod
    def create(
        cls,
        *,
        status: ExecutionStatus,
        skill_name: str,
        package_id: str,
        operation: str,
        envelope: ScopeEnvelope,
        output: Mapping[str, Any] | None,
        error: ExecutionError | None,
        evidence: tuple[Mapping[str, Any], ...],
        registry_digest: str,
        request_digest: str,
        warnings: tuple[str, ...] = (),
        retry_after_ms: int | None = None,
    ) -> "ExecutionResult":
        copied_output = strict_json_copy(output or {}, field="execution result.output")
        copied_evidence = tuple(
            strict_json_copy(item, field=f"execution result.evidence[{index}]")
            for index, item in enumerate(evidence)
        )
        if len(warnings) > 128:
            raise ContractError("execution result.warnings exceeds 128 entries")
        copied_warnings = tuple(
            _bounded_text(item, f"execution result.warnings[{index}]", maximum=512)
            for index, item in enumerate(warnings)
        )
        retryable = error.retryable if error is not None else False
        if retry_after_ms is not None:
            retry_after_ms = _bounded_int(
                retry_after_ms,
                "execution result.retry.after_ms",
                default=0,
                minimum=0,
                maximum=86_400_000,
            )
        if not retryable and retry_after_ms is not None:
            raise ContractError("non-retryable execution result cannot set retry.after_ms")
        retry: dict[str, Any] = {"retryable": retryable, "after_ms": retry_after_ms}
        if not is_sha256_digest(request_digest):
            raise ContractError("execution result.request_digest must be a lowercase sha256 value")
        body: dict[str, Any] = {
            "contract_version": CONTRACT_VERSION,
            "status": status.value,
            "skill_name": _token(skill_name, "execution result.skill_name"),
            "package_id": _token(package_id, "execution result.package_id"),
            "operation": _token(operation, "execution result.operation"),
            **envelope.as_dict(),
            "output": copied_output,
            "error": None if error is None else error.as_dict(),
            "warnings": list(copied_warnings),
            "retry": retry,
            "evidence": list(copied_evidence),
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
            "registry_digest": registry_digest,
            "request_digest": request_digest,
        }
        result_digest = canonical_digest(body)
        dependency_receipt = None
        if status is ExecutionStatus.EXECUTED and package_id != "ROOT":
            dependency_receipt = make_dependency_receipt(
                package_id=package_id,
                skill_name=skill_name,
                envelope=envelope,
                request_digest=request_digest,
                result_digest=result_digest,
            )
        return cls(
            status=status,
            skill_name=skill_name,
            package_id=package_id,
            operation=operation,
            envelope=envelope,
            output=copied_output,
            error=error,
            warnings=copied_warnings,
            retry=retry,
            evidence=copied_evidence,
            registry_digest=registry_digest,
            request_digest=request_digest,
            result_digest=result_digest,
            dependency_receipt=dependency_receipt,
        )

    def body(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": self.status.value,
            "skill_name": self.skill_name,
            "package_id": self.package_id,
            "operation": self.operation,
            **self.envelope.as_dict(),
            "output": strict_json_copy(self.output, field="execution result.output"),
            "error": None if self.error is None else self.error.as_dict(),
            "warnings": list(self.warnings),
            "retry": strict_json_copy(self.retry, field="execution result.retry"),
            "evidence": [
                strict_json_copy(item, field=f"execution result.evidence[{index}]")
                for index, item in enumerate(self.evidence)
            ],
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
            "registry_digest": self.registry_digest,
            "request_digest": self.request_digest,
        }

    def as_dict(self) -> dict[str, Any]:
        document = {
            **self.body(),
            "result_digest": self.result_digest,
            "dependency_receipt": self.dependency_receipt,
        }
        if canonical_digest(self.body()) != self.result_digest:
            raise ContractError("execution result digest no longer matches its canonical body")
        return document


def make_dependency_receipt(
    *,
    package_id: str,
    skill_name: str,
    envelope: ScopeEnvelope,
    request_digest: str,
    result_digest: str,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "package_id": package_id,
        "skill_name": skill_name,
        "tenant_id": envelope.tenant_id,
        "project_id": envelope.project_id,
        "correlation_id": envelope.correlation_id,
        "policy_revision": envelope.policy_revision,
        "source_revision": envelope.source_revision,
        "status": ExecutionStatus.EXECUTED.value,
        "request_digest": request_digest,
        "result_digest": result_digest,
    }
    return {**body, "receipt_digest": canonical_digest(body)}
