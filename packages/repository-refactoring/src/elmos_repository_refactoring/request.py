"""``RefactorRequest`` — the frozen, digest-bearing input to a refactor run.

Parsing is strict on purpose.  A request is the object every approval, plan and
evidence bundle is bound to by digest, so a field that is silently defaulted
here becomes an unauditable degree of freedom later.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .contracts import (
    ContractError,
    ExecutionMode,
    NetworkPolicy,
    RiskClass,
    canonical_json,
    decimal_value,
    integer_value,
    normalize_relative_path,
    optional_bool,
    optional_enum,
    optional_mapping,
    optional_string,
    reject_unknown_fields,
    require_enum,
    require_identifier,
    require_mapping,
    require_mapping_sequence,
    require_string,
    require_string_sequence,
    sha256_payload,
)

API_VERSION = "elmos.dev/v1"
REQUEST_KIND = "RefactorRequest"

INTENT_TYPES = (
    "structural-refactor",
    "architecture-refactor",
    "framework-upgrade",
    "language-upgrade",
    "api-migration",
    "data-schema-refactor",
    "distributed-system-refactor",
    "performance-refactor",
    "security-refactor",
    "ui-client-refactor",
    "custom",
)

REPOSITORY_ROLES = ("primary", "provider", "consumer", "shared", "generated-client")

BEHAVIOR_COMPATIBILITY = ("strict", "equivalent-for-covered-workloads", "approved-change")
PUBLIC_API_COMPATIBILITY = ("strict", "backward-compatible", "versioned-break", "approved-break")
BINARY_COMPATIBILITY = ("strict", "best-effort", "not-required")
DATABASE_STRATEGIES = ("none", "expand-contract", "maintenance-window", "approved-destructive")

#: Intent types whose *minimum* risk floor is raised regardless of how small
#: the resulting diff turns out to be.  A one-line change to an auth path is
#: still an auth change.
_INTENT_RISK_FLOOR: Mapping[str, RiskClass] = {
    "structural-refactor": RiskClass.R2,
    "architecture-refactor": RiskClass.R3,
    "framework-upgrade": RiskClass.R3,
    "language-upgrade": RiskClass.R3,
    "api-migration": RiskClass.R3,
    "data-schema-refactor": RiskClass.R4,
    "distributed-system-refactor": RiskClass.R4,
    "performance-refactor": RiskClass.R3,
    "security-refactor": RiskClass.R4,
    "ui-client-refactor": RiskClass.R2,
    "custom": RiskClass.R3,
}


def _safe_pattern(value: Any, field_name: str) -> str:
    """Validate a workspace-relative glob without collapsing its wildcards.

    ``normalize_relative_path`` is wrong for patterns because it would strip
    ``**`` semantics; the checks that matter for a pattern are the escape ones.
    """

    text = require_string(value, field_name, max_length=1024)
    if text.startswith("/") or "\\" in text or "\x00" in text:
        raise ContractError("invalid_path", f"{field_name} must be a workspace-relative POSIX glob")
    if any(segment == ".." for segment in text.split("/")):
        raise ContractError("path_escape", f"{field_name} must not contain '..' segments")
    return text.strip("/") or "**"


@dataclass(frozen=True, slots=True)
class RepositoryRef:
    uri: str
    revision: str
    sub_path: str | None = None
    role: str = "primary"
    credential_ref: str | None = None
    read_only: bool = False

    @property
    def repository_id(self) -> str:
        """Stable identity for a repository within one request."""

        name = self.uri.rstrip("/").rsplit("/", 1)[-1]
        if name.endswith(".git"):
            name = name[:-4]
        suffix = f"/{self.sub_path}" if self.sub_path else ""
        return f"{name}{suffix}" if name else self.uri

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "uri": self.uri,
            "revision": self.revision,
            "role": self.role,
            "readOnly": self.read_only,
        }
        if self.sub_path:
            payload["subPath"] = self.sub_path
        if self.credential_ref:
            payload["credentialRef"] = self.credential_ref
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> RepositoryRef:
        reject_unknown_fields(
            value,
            {"uri", "revision", "subPath", "role", "credentialRef", "readOnly"},
            "spec.repositories[]",
        )
        role = optional_string(value.get("role"), "spec.repositories[].role") or "primary"
        if role not in REPOSITORY_ROLES:
            raise ContractError("invalid_enum", "spec.repositories[].role is not a known role")
        sub_path = value.get("subPath")
        return cls(
            uri=require_string(value.get("uri"), "spec.repositories[].uri", max_length=1024),
            revision=require_string(
                value.get("revision"), "spec.repositories[].revision", min_length=7, max_length=128
            ),
            sub_path=None if sub_path is None else normalize_relative_path(sub_path, "spec.repositories[].subPath"),
            role=role,
            credential_ref=optional_string(
                value.get("credentialRef"), "spec.repositories[].credentialRef", max_length=256
            ),
            read_only=optional_bool(value.get("readOnly"), "spec.repositories[].readOnly", False),
        )


@dataclass(frozen=True, slots=True)
class RefactorIntent:
    type: str
    goals: tuple[str, ...]
    non_goals: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    context: Mapping[str, Any] = field(default_factory=dict)

    @property
    def risk_floor(self) -> RiskClass:
        return _INTENT_RISK_FLOOR[self.type]

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": self.type, "goals": list(self.goals)}
        if self.non_goals:
            payload["nonGoals"] = list(self.non_goals)
        if self.acceptance_criteria:
            payload["acceptanceCriteria"] = list(self.acceptance_criteria)
        if self.context:
            payload["context"] = dict(self.context)
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> RefactorIntent:
        reject_unknown_fields(
            value,
            {"type", "goals", "nonGoals", "acceptanceCriteria", "context"},
            "spec.intent",
        )
        intent_type = require_string(value.get("type"), "spec.intent.type", max_length=64)
        if intent_type not in INTENT_TYPES:
            raise ContractError("invalid_enum", f"spec.intent.type must be one of: {', '.join(INTENT_TYPES)}")
        goals = require_string_sequence(value.get("goals"), "spec.intent.goals", allow_empty=False, max_items=200)
        for goal in goals:
            if len(goal) < 3:
                raise ContractError("invalid_string", "spec.intent.goals[] must have at least 3 characters")
        return cls(
            type=intent_type,
            goals=goals,
            non_goals=require_string_sequence(value.get("nonGoals", ()), "spec.intent.nonGoals", max_items=200),
            acceptance_criteria=require_string_sequence(
                value.get("acceptanceCriteria", ()), "spec.intent.acceptanceCriteria", max_items=200
            ),
            context=dict(optional_mapping(value.get("context"), "spec.intent.context")),
        )


@dataclass(frozen=True, slots=True)
class RefactorConstraints:
    behavior_compatibility: str = "strict"
    public_api_compatibility: str = "backward-compatible"
    binary_compatibility: str = "best-effort"
    database_strategy: str = "none"
    maximum_changed_files: int | None = None
    maximum_changed_lines: int | None = None
    maximum_cost_usd: Decimal | None = None
    maximum_wall_clock_seconds: int | None = None
    allowed_paths: tuple[str, ...] = ()
    forbidden_paths: tuple[str, ...] = ()
    required_tests: tuple[str, ...] = ()
    performance_guardrails: Mapping[str, Any] = field(default_factory=dict)
    security_policy_ref: str | None = None
    license_policy_ref: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "behaviorCompatibility": self.behavior_compatibility,
            "publicApiCompatibility": self.public_api_compatibility,
            "binaryCompatibility": self.binary_compatibility,
            "databaseStrategy": self.database_strategy,
        }
        if self.maximum_changed_files is not None:
            payload["maximumChangedFiles"] = self.maximum_changed_files
        if self.maximum_changed_lines is not None:
            payload["maximumChangedLines"] = self.maximum_changed_lines
        if self.maximum_cost_usd is not None:
            payload["maximumCostUsd"] = str(self.maximum_cost_usd)
        if self.maximum_wall_clock_seconds is not None:
            payload["maximumWallClockSeconds"] = self.maximum_wall_clock_seconds
        if self.allowed_paths:
            payload["allowedPaths"] = list(self.allowed_paths)
        if self.forbidden_paths:
            payload["forbiddenPaths"] = list(self.forbidden_paths)
        if self.required_tests:
            payload["requiredTests"] = list(self.required_tests)
        if self.performance_guardrails:
            payload["performanceGuardrails"] = dict(self.performance_guardrails)
        if self.security_policy_ref:
            payload["securityPolicyRef"] = self.security_policy_ref
        if self.license_policy_ref:
            payload["licensePolicyRef"] = self.license_policy_ref
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any] | None) -> RefactorConstraints:
        if value is None:
            return cls()
        mapping = require_mapping(value, "spec.constraints")
        reject_unknown_fields(
            mapping,
            {
                "behaviorCompatibility",
                "publicApiCompatibility",
                "binaryCompatibility",
                "databaseStrategy",
                "maximumChangedFiles",
                "maximumChangedLines",
                "maximumCostUsd",
                "maximumWallClockSeconds",
                "allowedPaths",
                "forbiddenPaths",
                "requiredTests",
                "performanceGuardrails",
                "securityPolicyRef",
                "licensePolicyRef",
            },
            "spec.constraints",
        )

        def _choice(key: str, allowed: tuple[str, ...], default: str) -> str:
            raw = mapping.get(key)
            if raw is None:
                return default
            text = require_string(raw, f"spec.constraints.{key}", max_length=64)
            if text not in allowed:
                raise ContractError("invalid_enum", f"spec.constraints.{key} must be one of: {', '.join(allowed)}")
            return text

        max_cost = mapping.get("maximumCostUsd")
        return cls(
            behavior_compatibility=_choice("behaviorCompatibility", BEHAVIOR_COMPATIBILITY, "strict"),
            public_api_compatibility=_choice("publicApiCompatibility", PUBLIC_API_COMPATIBILITY, "backward-compatible"),
            binary_compatibility=_choice("binaryCompatibility", BINARY_COMPATIBILITY, "best-effort"),
            database_strategy=_choice("databaseStrategy", DATABASE_STRATEGIES, "none"),
            maximum_changed_files=None
            if mapping.get("maximumChangedFiles") is None
            else integer_value(mapping["maximumChangedFiles"], "spec.constraints.maximumChangedFiles", minimum=1),
            maximum_changed_lines=None
            if mapping.get("maximumChangedLines") is None
            else integer_value(mapping["maximumChangedLines"], "spec.constraints.maximumChangedLines", minimum=1),
            maximum_cost_usd=None
            if max_cost is None
            else decimal_value(max_cost, "spec.constraints.maximumCostUsd", minimum=Decimal("0")),
            maximum_wall_clock_seconds=None
            if mapping.get("maximumWallClockSeconds") is None
            else integer_value(
                mapping["maximumWallClockSeconds"], "spec.constraints.maximumWallClockSeconds", minimum=1
            ),
            allowed_paths=tuple(
                _safe_pattern(item, "spec.constraints.allowedPaths[]")
                for item in require_string_sequence(mapping.get("allowedPaths", ()), "spec.constraints.allowedPaths")
            ),
            forbidden_paths=tuple(
                _safe_pattern(item, "spec.constraints.forbiddenPaths[]")
                for item in require_string_sequence(
                    mapping.get("forbiddenPaths", ()), "spec.constraints.forbiddenPaths"
                )
            ),
            required_tests=require_string_sequence(mapping.get("requiredTests", ()), "spec.constraints.requiredTests"),
            performance_guardrails=dict(
                optional_mapping(mapping.get("performanceGuardrails"), "spec.constraints.performanceGuardrails")
            ),
            security_policy_ref=optional_string(mapping.get("securityPolicyRef"), "spec.constraints.securityPolicyRef"),
            license_policy_ref=optional_string(mapping.get("licensePolicyRef"), "spec.constraints.licensePolicyRef"),
        )


@dataclass(frozen=True, slots=True)
class RepairBudget:
    max_attempts: int = 3
    max_cost_usd: Decimal = Decimal("0")
    max_changed_files: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "maxAttempts": self.max_attempts,
            "maxCostUsd": str(self.max_cost_usd),
            "maxChangedFiles": self.max_changed_files,
        }

    @classmethod
    def from_payload(cls, value: Mapping[str, Any] | None) -> RepairBudget:
        if value is None:
            return cls()
        mapping = require_mapping(value, "spec.execution.repairBudget")
        reject_unknown_fields(mapping, {"maxAttempts", "maxCostUsd", "maxChangedFiles"}, "spec.execution.repairBudget")
        return cls(
            max_attempts=integer_value(
                mapping.get("maxAttempts", 3), "spec.execution.repairBudget.maxAttempts", minimum=0, maximum=50
            ),
            max_cost_usd=decimal_value(
                mapping.get("maxCostUsd", 0), "spec.execution.repairBudget.maxCostUsd", minimum=Decimal("0")
            ),
            max_changed_files=integer_value(
                mapping.get("maxChangedFiles", 0), "spec.execution.repairBudget.maxChangedFiles", minimum=0
            ),
        )


@dataclass(frozen=True, slots=True)
class ExecutionSpec:
    mode: ExecutionMode
    create_pull_request: bool = True
    target_branch: str | None = None
    max_parallel_shards: int = 4
    repair_budget: RepairBudget = field(default_factory=RepairBudget)
    approval_policy_ref: str | None = None
    sandbox_profile: str | None = None
    network_policy: NetworkPolicy = NetworkPolicy.DENY

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mode": self.mode.value,
            "createPullRequest": self.create_pull_request,
            "maxParallelShards": self.max_parallel_shards,
            "repairBudget": self.repair_budget.to_payload(),
            "networkPolicy": self.network_policy.value,
        }
        if self.target_branch:
            payload["targetBranch"] = self.target_branch
        if self.approval_policy_ref:
            payload["approvalPolicyRef"] = self.approval_policy_ref
        if self.sandbox_profile:
            payload["sandboxProfile"] = self.sandbox_profile
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> ExecutionSpec:
        mapping = require_mapping(value, "spec.execution")
        reject_unknown_fields(
            mapping,
            {
                "mode",
                "createPullRequest",
                "targetBranch",
                "maxParallelShards",
                "repairBudget",
                "approvalPolicyRef",
                "sandboxProfile",
                "networkPolicy",
            },
            "spec.execution",
        )
        return cls(
            mode=require_enum(mapping.get("mode"), ExecutionMode, "spec.execution.mode"),
            create_pull_request=optional_bool(
                mapping.get("createPullRequest"), "spec.execution.createPullRequest", True
            ),
            target_branch=optional_string(mapping.get("targetBranch"), "spec.execution.targetBranch", max_length=255),
            max_parallel_shards=integer_value(
                mapping.get("maxParallelShards", 4), "spec.execution.maxParallelShards", minimum=1, maximum=256
            ),
            repair_budget=RepairBudget.from_payload(mapping.get("repairBudget")),
            approval_policy_ref=optional_string(mapping.get("approvalPolicyRef"), "spec.execution.approvalPolicyRef"),
            sandbox_profile=optional_string(mapping.get("sandboxProfile"), "spec.execution.sandboxProfile"),
            network_policy=optional_enum(
                mapping.get("networkPolicy"), NetworkPolicy, "spec.execution.networkPolicy", NetworkPolicy.DENY
            ),
        )


@dataclass(frozen=True, slots=True)
class RefactorRequest:
    tenant_id: str
    project_id: str
    request_id: str | None
    labels: Mapping[str, str]
    repositories: tuple[RepositoryRef, ...]
    intent: RefactorIntent
    constraints: RefactorConstraints
    execution: ExecutionSpec

    # -- derived ---------------------------------------------------------

    @property
    def primary(self) -> RepositoryRef:
        for repository in self.repositories:
            if repository.role == "primary":
                return repository
        return self.repositories[0]

    @property
    def writable_repositories(self) -> tuple[RepositoryRef, ...]:
        return tuple(repository for repository in self.repositories if not repository.read_only)

    @property
    def risk_floor(self) -> RiskClass:
        floor = self.intent.risk_floor
        if self.constraints.database_strategy in {"maintenance-window", "approved-destructive"}:
            floor = RiskClass.max_of([floor, RiskClass.R4])
        if self.constraints.public_api_compatibility in {"versioned-break", "approved-break"}:
            floor = RiskClass.max_of([floor, RiskClass.R3])
        if len(self.repositories) > 1:
            floor = RiskClass.max_of([floor, RiskClass.R3])
        return floor

    def to_payload(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {"tenantId": self.tenant_id, "projectId": self.project_id}
        if self.request_id:
            metadata["requestId"] = self.request_id
        if self.labels:
            metadata["labels"] = dict(self.labels)
        return {
            "apiVersion": API_VERSION,
            "kind": REQUEST_KIND,
            "metadata": metadata,
            "spec": {
                "repositories": [repository.to_payload() for repository in self.repositories],
                "intent": self.intent.to_payload(),
                "constraints": self.constraints.to_payload(),
                "execution": self.execution.to_payload(),
            },
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())

    def canonical(self) -> str:
        return canonical_json(self.to_payload())

    # -- parsing ---------------------------------------------------------

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RefactorRequest:
        value = require_mapping(payload, "request")
        reject_unknown_fields(value, {"apiVersion", "kind", "metadata", "spec"}, "request")
        if value.get("apiVersion") != API_VERSION:
            raise ContractError("invalid_api_version", f"request.apiVersion must be {API_VERSION}")
        if value.get("kind") != REQUEST_KIND:
            raise ContractError("invalid_kind", f"request.kind must be {REQUEST_KIND}")

        metadata = require_mapping(value.get("metadata"), "request.metadata")
        reject_unknown_fields(metadata, {"tenantId", "projectId", "requestId", "labels"}, "request.metadata")
        labels_raw = optional_mapping(metadata.get("labels"), "request.metadata.labels")
        labels = {
            require_string(key, "request.metadata.labels key", max_length=128): require_string(
                item, "request.metadata.labels value", max_length=256
            )
            for key, item in labels_raw.items()
        }

        spec = require_mapping(value.get("spec"), "request.spec")
        reject_unknown_fields(spec, {"repositories", "intent", "constraints", "execution", "metadata"}, "request.spec")
        repository_payloads = require_mapping_sequence(
            spec.get("repositories"), "spec.repositories", allow_empty=False, max_items=1000
        )
        repositories = tuple(RepositoryRef.from_payload(item) for item in repository_payloads)
        seen: set[tuple[str, str | None]] = set()
        for repository in repositories:
            key = (repository.uri, repository.sub_path)
            if key in seen:
                raise ContractError("duplicate_repository", f"repository {repository.uri} is listed twice")
            seen.add(key)
        if sum(1 for repository in repositories if repository.role == "primary") > 1:
            raise ContractError("multiple_primary_repositories", "at most one repository may carry role 'primary'")

        request = cls(
            tenant_id=require_identifier(metadata.get("tenantId"), "request.metadata.tenantId"),
            project_id=require_identifier(metadata.get("projectId"), "request.metadata.projectId"),
            request_id=None
            if metadata.get("requestId") is None
            else require_identifier(metadata.get("requestId"), "request.metadata.requestId"),
            labels=labels,
            repositories=repositories,
            intent=RefactorIntent.from_payload(require_mapping(spec.get("intent"), "spec.intent")),
            constraints=RefactorConstraints.from_payload(spec.get("constraints")),
            execution=ExecutionSpec.from_payload(require_mapping(spec.get("execution"), "spec.execution")),
        )
        _validate_coherence(request)
        return request


def _validate_coherence(request: RefactorRequest) -> None:
    """Reject requests whose fields contradict each other.

    These are the combinations that read as plausible but cannot be honoured,
    and every one of them has to fail at intake rather than half-way through a
    run that has already written to a branch.
    """

    execution = request.execution
    constraints = request.constraints

    if execution.mode is ExecutionMode.ANALYZE_ONLY and execution.create_pull_request:
        raise ContractError(
            "incoherent_request",
            "analyze-only mode cannot create a pull request",
        )
    if execution.mode is ExecutionMode.AUTONOMOUS_LOW_RISK and request.risk_floor.rank >= RiskClass.R3.rank:
        raise ContractError(
            "autonomy_risk_conflict",
            "autonomous-low-risk mode is incompatible with this request's risk floor",
            {"risk_floor": request.risk_floor.value},
        )
    if execution.mode is ExecutionMode.FLEET_WAVE and len(request.repositories) < 2:
        raise ContractError("incoherent_request", "fleet-wave mode requires more than one repository")
    if request.intent.type == "data-schema-refactor" and constraints.database_strategy == "none":
        raise ContractError(
            "incoherent_request",
            "a data-schema-refactor intent requires an explicit databaseStrategy",
        )
    if constraints.database_strategy == "approved-destructive" and execution.mode in {
        ExecutionMode.AUTONOMOUS_LOW_RISK,
        ExecutionMode.PROPOSAL,
    }:
        raise ContractError(
            "incoherent_request",
            "approved-destructive database changes require supervised or fleet-wave execution",
        )
    if not request.writable_repositories and execution.mode.mutates_workspace:
        raise ContractError("incoherent_request", "every repository is read-only but the mode would write")
    overlap = sorted(set(constraints.allowed_paths) & set(constraints.forbidden_paths))
    if overlap:
        raise ContractError(
            "incoherent_request",
            "allowedPaths and forbiddenPaths overlap: " + ", ".join(overlap),
            {"paths": overlap},
        )


__all__ = [
    "API_VERSION",
    "BEHAVIOR_COMPATIBILITY",
    "BINARY_COMPATIBILITY",
    "DATABASE_STRATEGIES",
    "INTENT_TYPES",
    "PUBLIC_API_COMPATIBILITY",
    "REPOSITORY_ROLES",
    "REQUEST_KIND",
    "ExecutionSpec",
    "RefactorConstraints",
    "RefactorIntent",
    "RefactorRequest",
    "RepairBudget",
    "RepositoryRef",
]
