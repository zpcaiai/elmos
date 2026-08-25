"""Fail-closed HTTP service helpers for the cache-parity supplement.

The transport-independent service in this module deliberately separates raw
request material from durable metadata.  Prompt source is accepted only long
enough to compile a deterministic layout; the repository receives the
content-free manifest.  Benchmark endpoints evaluate caller-supplied
measurements and evidence references and never execute providers or invent
missing observations.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol, TypeVar, cast

from .affinity import (
    AffinityAuthorizationContext,
    AffinityAuthorizationResolver,
    AffinityCandidate,
    AffinityDecision,
    AffinityRequest,
    AttestedAffinityRegistry,
    RoutingReason,
    TargetHealth,
    route_affinity,
)
from .canonical import digest_of, require_digest
from .clock import Clock
from .context_ledger import ContextEventType, ContextLedgerEvent, RepositoryContextLedger
from .db import MetadataStore
from .environment_cache import RestoreEstimate
from .environment_service import EnvironmentSnapshotService
from .errors import (
    ContractViolation,
    CorruptObject,
    NotFound,
    PermissionDenied,
    RemoteUnavailable,
    SecretDetected,
)
from .miss_diagnostics import (
    CacheCohort,
    CacheLayer,
    CacheOutcome,
    CacheOutcomeEvent,
    CacheOutcomeReason,
    FirstDifference,
    IdentityDimension,
    ReasonFamily,
)
from .parity import (
    MANDATORY_METRICS,
    EvidenceBinding,
    ParityDecision,
    ParityReport,
    ParityThresholds,
    ScenarioResult,
    ScenarioStatus,
    evaluate_parity,
)
from .parity_evidence import EvidenceVerification
from .prompt_cache import (
    CompiledPrompt,
    PromptCacheController,
    PromptCompiler,
    PromptIdentity,
    PromptProvider,
    PromptRequestClass,
    PromptSegment,
    ProviderCacheMode,
    ProviderCacheReason,
    SegmentStability,
)
from .prompt_tools import VolatilityCode, assert_cache_safe_prefix, lint_stable_segments

PARITY_API_SCHEMA_VERSION = "1.2.0"
MAX_PROMPT_SEGMENTS = 256
MAX_PROMPT_SEGMENT_BYTES = 1 * 1024 * 1024
MAX_PROMPT_TOTAL_BYTES = 4 * 1024 * 1024

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}$")
_COHORT = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_SENSITIVE_MARKERS = (
    "api_key",
    "credential",
    "password",
    "private_key",
    "raw",
    "secret",
)
_RAW_MATERIAL_FIELDS = frozenset(
    {
        "body",
        "content",
        "messages",
        "prompt",
        "prompt_text",
        "source",
        "source_code",
        "source_text",
        "value",
    }
)
_ENVIRONMENT_QUERY_FIELDS = frozenset(
    {
        "projectId",
        "trustNamespace",
        "transferMs",
        "decompressionMs",
        "verificationMs",
        "rebuildMs",
        "minimumSavingsMs",
        "maximumRestoreRatio",
    }
)

_TEnum = TypeVar("_TEnum", bound=Enum)


class ParityRepository(Protocol):
    """Persistent, tenant/project-scoped metadata contract used by the API."""

    def put_prompt_manifest(
        self,
        tenant_id: str,
        project_id: str,
        manifest_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def get_prompt_manifest(
        self,
        tenant_id: str,
        project_id: str,
        manifest_id: str,
    ) -> dict[str, Any] | None: ...

    def put_provider_usage(
        self,
        tenant_id: str,
        project_id: str,
        observation_id: str,
        prompt_manifest_digest: str,
        usage: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def put_cache_outcome(
        self,
        tenant_id: str,
        project_id: str,
        request_id: str,
        event_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def get_environment_snapshot(
        self, tenant_id: str, project_id: str, snapshot_key: str
    ) -> dict[str, Any] | None: ...

    def get_environment_snapshot_state(
        self, tenant_id: str, project_id: str, snapshot_key: str
    ) -> dict[str, Any] | None: ...

    def put_affinity_decision(
        self,
        tenant_id: str,
        project_id: str,
        request_id: str,
        decision_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def list_cache_outcomes(
        self, tenant_id: str, project_id: str, request_id: str
    ) -> tuple[dict[str, Any], ...]: ...

    def put_parity_report(
        self,
        tenant_id: str,
        project_id: str,
        report_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def get_parity_report(
        self, tenant_id: str, project_id: str, report_id: str
    ) -> dict[str, Any] | None: ...


class ParityEvidenceVerifier(Protocol):
    def verify_scenario(
        self,
        scenario_id: str,
        evidence_digests: Sequence[str],
        binding: EvidenceBinding,
        metrics: Mapping[str, float | int],
        cohorts: Mapping[str, Mapping[str, float | int]],
        *,
        tenant_id: str,
        project_id: str,
        report_id: str,
    ) -> EvidenceVerification: ...


@dataclass(frozen=True)
class PromptCompilation:
    project_id: str
    compiled: CompiledPrompt
    manifest: dict[str, Any]
    response: dict[str, Any]


@dataclass(frozen=True)
class AffinityEvaluation:
    project_id: str
    request_id: str
    decision_id: str
    decision: AffinityDecision
    document: dict[str, Any]


@dataclass(frozen=True)
class ServiceResult:
    status: int
    body: dict[str, Any]


def tenant_project_scope_digest(tenant_id: str, project_id: str) -> str:
    """Return the only tenant scope digest accepted by public parsers."""

    return digest_of(
        {
            "tenant_id": _identifier(tenant_id, "tenant_id"),
            "project_id": _identifier(project_id, "project_id"),
        }
    )


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field} must be a bounded identifier", field=field)
    return value


def _text(value: Any, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ContractViolation(f"{field} must be non-blank and at most {maximum} characters")
    return value


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{field} must be an object", field=field)
    return cast(Mapping[str, Any], value)


def _strict_object(
    value: Any,
    field: str,
    *,
    allowed: frozenset[str],
    required: frozenset[str] = frozenset(),
) -> Mapping[str, Any]:
    document = _mapping(value, field)
    unknown = sorted(set(document) - allowed)
    missing = sorted(required - set(document))
    if unknown or missing:
        raise ContractViolation(
            f"{field} has an invalid shape", field=field, unknown=unknown, missing=missing
        )
    return document


def _sequence(value: Any, field: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ContractViolation(f"{field} must be an array", field=field)
    return value


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractViolation(f"{field} must be an integer >= {minimum}", field=field)
    return cast(int, value)


def _number(value: Any, field: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractViolation(f"{field} must be numeric", field=field)
    result = float(value)
    if result < minimum or result != result or result in {float("inf"), float("-inf")}:
        raise ContractViolation(f"{field} must be finite and >= {minimum}", field=field)
    return result


def _enum(enum_type: type[_TEnum], value: Any, field: str) -> _TEnum:
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must use the closed vocabulary", field=field)
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ContractViolation(
            f"{field} must use the closed vocabulary", field=field, value=value
        ) from exc


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be a sha256 digest", field=field)
    return require_digest(value)


def _optional_digest(value: Any, field: str) -> str | None:
    return None if value is None else _digest(value, field)


def _iso_timestamp(value: Any, field: str) -> str:
    text = _text(value, field, maximum=128)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractViolation(f"{field} must be an ISO-8601 timestamp", field=field) from exc
    if parsed.tzinfo is None:
        raise ContractViolation(f"{field} must include a timezone", field=field)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _assert_content_free(value: Any, field: str = "document") -> None:
    """Reject raw source/prompt/secret-shaped telemetry recursively."""

    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            if not isinstance(raw_key, str):
                raise ContractViolation("telemetry keys must be text", field=field)
            key = raw_key.casefold()
            if key in _RAW_MATERIAL_FIELDS:
                raise SecretDetected("raw material cannot enter persistent telemetry", field=f"{field}.{raw_key}")
            if any(marker in key for marker in _SENSITIVE_MARKERS) and not key.endswith(
                ("_digest", "_digests", "_ref", "_refs", "_reference", "_references")
            ):
                raise SecretDetected(
                    "secret-shaped field cannot enter persistent telemetry",
                    field=f"{field}.{raw_key}",
                )
            _assert_content_free(nested, f"{field}.{raw_key}")
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for index, nested in enumerate(value):
            _assert_content_free(nested, f"{field}[{index}]")
    elif isinstance(value, str) and len(value) > 4096:
        raise ContractViolation("telemetry strings must be bounded", field=field)
    elif not isinstance(value, str | int | float | bool | type(None)):
        raise ContractViolation("telemetry value is not JSON-safe", field=field)


def _project(payload: Mapping[str, Any]) -> str:
    if "project_id" not in payload:
        raise ContractViolation("project_id is required", field="project_id")
    return _identifier(payload["project_id"], "project_id")


def compile_prompt_prefix_payload(
    tenant_id: str, payload: Mapping[str, Any]
) -> PromptCompilation:
    """Compile raw prompt input while returning only content-free documents."""

    body = _strict_object(
        payload,
        "prompt compilation",
        allowed=frozenset(
            {"project_id", "identity", "segments", "volatility_approvals"}
        ),
        required=frozenset({"project_id", "identity", "segments"}),
    )
    project_id = _project(body)
    scope_digest = tenant_project_scope_digest(tenant_id, project_id)
    identity_data = _strict_object(
        body["identity"],
        "identity",
        allowed=frozenset(
            {
                "tenant_scope_digest",
                "provider",
                "provider_namespace_digest",
                "model",
                "effort_profile",
                "tool_schema_digest",
                "compatibility_digest",
            }
        ),
        required=frozenset(
            {
                "provider",
                "provider_namespace_digest",
                "model",
                "effort_profile",
                "tool_schema_digest",
                "compatibility_digest",
            }
        ),
    )
    claimed_scope = identity_data.get("tenant_scope_digest")
    if claimed_scope is not None and _digest(claimed_scope, "tenant_scope_digest") != scope_digest:
        raise ContractViolation("tenant scope digest does not match the authenticated scope")
    identity = PromptIdentity(
        tenant_scope_digest=scope_digest,
        provider=_enum(PromptProvider, identity_data["provider"], "provider"),
        provider_namespace_digest=_digest(
            identity_data["provider_namespace_digest"], "provider_namespace_digest"
        ),
        model=_identifier(identity_data["model"], "model"),
        effort_profile=_identifier(identity_data["effort_profile"], "effort_profile"),
        tool_schema_digest=_digest(identity_data["tool_schema_digest"], "tool_schema_digest"),
        compatibility_digest=_digest(
            identity_data["compatibility_digest"], "compatibility_digest"
        ),
    )
    supplied_segments = _sequence(body["segments"], "segments")
    if len(supplied_segments) > MAX_PROMPT_SEGMENTS:
        raise ContractViolation(
            "prompt contains too many segments",
            maximum=MAX_PROMPT_SEGMENTS,
        )
    segments: list[PromptSegment] = []
    total_prompt_bytes = 0
    for index, raw_segment in enumerate(supplied_segments):
        segment = _strict_object(
            raw_segment,
            f"segments[{index}]",
            allowed=frozenset({"segment_id", "stability", "ordinal", "content"}),
            required=frozenset({"segment_id", "stability", "ordinal", "content"}),
        )
        content = segment["content"]
        if not isinstance(content, str):
            raise ContractViolation("prompt segment content must be text", field=f"segments[{index}].content")
        content_bytes = len(content.encode("utf-8"))
        if content_bytes > MAX_PROMPT_SEGMENT_BYTES:
            raise ContractViolation(
                "prompt segment exceeds the byte limit",
                field=f"segments[{index}].content",
                maximum=MAX_PROMPT_SEGMENT_BYTES,
            )
        total_prompt_bytes += content_bytes
        if total_prompt_bytes > MAX_PROMPT_TOTAL_BYTES:
            raise ContractViolation(
                "prompt exceeds the total byte limit",
                maximum=MAX_PROMPT_TOTAL_BYTES,
            )
        segments.append(
            PromptSegment(
                segment_id=_identifier(segment["segment_id"], "segment_id"),
                stability=_enum(SegmentStability, segment["stability"], "stability"),
                ordinal=_integer(segment["ordinal"], "ordinal"),
                content=content,
            )
        )
    compiled = PromptCompiler().compile(identity, segments)
    approvals: set[tuple[str, VolatilityCode]] = set()
    for index, raw_approval in enumerate(
        _sequence(body.get("volatility_approvals", ()), "volatility_approvals")
    ):
        approval = _strict_object(
            raw_approval,
            f"volatility_approvals[{index}]",
            allowed=frozenset({"segment_id", "code"}),
            required=frozenset({"segment_id", "code"}),
        )
        approvals.add(
            (
                _identifier(approval["segment_id"], "segment_id"),
                _enum(VolatilityCode, approval["code"], "code"),
            )
        )
    exact_approvals = frozenset(approvals)
    assert_cache_safe_prefix(compiled, approved=exact_approvals)
    lint_findings = lint_stable_segments(compiled, approved=exact_approvals)
    stability = {
        SegmentStability.STABLE: "PROJECT_STABLE",
        SegmentStability.APPEND_ONLY: "SESSION_APPEND_ONLY",
        SegmentStability.VOLATILE: "TURN_VOLATILE",
    }
    manifest: dict[str, Any] = {
        "schema_version": PARITY_API_SCHEMA_VERSION,
        "manifest_id": compiled.cache_key,
        "provider_namespace": identity.provider_namespace_digest,
        "compatibility_group": identity.compatibility_digest,
        "provider": identity.provider.value,
        "model": identity.model,
        "effort": identity.effort_profile,
        "tool_schema_digest": identity.tool_schema_digest,
        "stable_prefix_digest": compiled.stable_prefix_digest,
        "breakpoint_after_segment_ids": [
            item.segment_id for item in (*compiled.stable_segments, *compiled.append_segments)
        ],
        "segments": [
            {
                "segment_id": item.segment_id,
                "stability_class": stability[item.stability],
                "digest": item.content_digest,
                "byte_length": len(item.content.encode("utf-8")),
            }
            for item in compiled.segments
        ],
    }
    response: dict[str, Any] = {
        "project_id": project_id,
        "manifest": manifest,
        "provider_plan": {
            "provider": identity.provider.value,
            "model": identity.model,
            "effort_profile": identity.effort_profile,
            "cache_key": compiled.cache_key,
            "stable_prefix_digest": compiled.stable_prefix_digest,
            "append_prefix_digest": compiled.append_prefix_digest,
            "full_prompt_digest": compiled.full_prompt_digest,
            "stable_segments": compiled.stable_count,
            "append_segments": compiled.append_count,
            "volatile_segments": len(compiled.volatile_segments),
        },
        "telemetry": compiled.telemetry(),
        "lint_findings": [finding.to_dict() for finding in lint_findings],
        "volatility_approvals": [
            {"segment_id": segment_id, "code": code.value}
            for segment_id, code in sorted(exact_approvals, key=lambda item: (item[0], item[1].value))
        ],
    }
    _assert_content_free(manifest, "prompt manifest")
    _assert_content_free(response, "prompt response")
    return PromptCompilation(project_id, compiled, manifest, response)


def _parse_affinity_candidate(
    value: Any,
    *,
    index: int,
    default_tenant_scope: str,
) -> AffinityCandidate:
    candidate = _strict_object(
        value,
        f"candidates[{index}]",
        allowed=frozenset(
            {
                "target_id",
                "tenant_scope_digest",
                "authorization_scope_digest",
                "authorized",
                "trust_namespace",
                "provider",
                "model",
                "effort_profile",
                "tool_schema_digest",
                "prefix_compatibility_digest",
                "platform_digest",
                "available_capacity",
                "health",
                "prompt_cache_value_ms",
                "environment_value_ms",
                "artifact_value_ms",
                "dag_next_use_value_ms",
                "queue_delay_ms",
                "transfer_cost_ms",
                "failure_penalty_ms",
                "fairness_debt_ms",
            }
        ),
        required=frozenset(
            {
                "target_id",
                "authorization_scope_digest",
                "authorized",
                "trust_namespace",
                "provider",
                "model",
                "effort_profile",
                "tool_schema_digest",
                "prefix_compatibility_digest",
                "platform_digest",
                "available_capacity",
                "health",
            }
        ),
    )
    authorized = candidate["authorized"]
    if not isinstance(authorized, bool):
        raise ContractViolation("authorized must be boolean", field=f"candidates[{index}].authorized")
    return AffinityCandidate(
        target_id=_identifier(candidate["target_id"], "target_id"),
        tenant_scope_digest=_digest(
            candidate.get("tenant_scope_digest", default_tenant_scope), "tenant_scope_digest"
        ),
        authorization_scope_digest=_digest(
            candidate["authorization_scope_digest"], "authorization_scope_digest"
        ),
        authorized=authorized,
        trust_namespace=_identifier(candidate["trust_namespace"], "trust_namespace"),
        provider=_enum(PromptProvider, candidate["provider"], "provider"),
        model=_identifier(candidate["model"], "model"),
        effort_profile=_identifier(candidate["effort_profile"], "effort_profile"),
        tool_schema_digest=_digest(candidate["tool_schema_digest"], "tool_schema_digest"),
        prefix_compatibility_digest=_digest(
            candidate["prefix_compatibility_digest"], "prefix_compatibility_digest"
        ),
        platform_digest=_digest(candidate["platform_digest"], "platform_digest"),
        available_capacity=_integer(candidate["available_capacity"], "available_capacity"),
        health=_enum(TargetHealth, candidate["health"], "health"),
        prompt_cache_value_ms=_number(
            candidate.get("prompt_cache_value_ms", 0), "prompt_cache_value_ms"
        ),
        environment_value_ms=_number(
            candidate.get("environment_value_ms", 0), "environment_value_ms"
        ),
        artifact_value_ms=_number(
            candidate.get("artifact_value_ms", 0), "artifact_value_ms"
        ),
        dag_next_use_value_ms=_number(
            candidate.get("dag_next_use_value_ms", 0), "dag_next_use_value_ms"
        ),
        queue_delay_ms=_number(candidate.get("queue_delay_ms", 0), "queue_delay_ms"),
        transfer_cost_ms=_number(candidate.get("transfer_cost_ms", 0), "transfer_cost_ms"),
        failure_penalty_ms=_number(
            candidate.get("failure_penalty_ms", 0), "failure_penalty_ms"
        ),
        fairness_debt_ms=_number(candidate.get("fairness_debt_ms", 0), "fairness_debt_ms"),
    )


def _affinity_request_from_payload(
    tenant_id: str,
    payload: Mapping[str, Any],
    *,
    trusted_authorization_scope_digest: str,
) -> tuple[str, str, AffinityRequest]:
    body = _strict_object(
        payload,
        "affinity request",
        allowed=frozenset({"project_id", "request_id", "request"}),
        required=frozenset({"project_id", "request_id", "request"}),
    )
    project_id = _project(body)
    request_id = _identifier(body["request_id"], "request_id")
    scope_digest = tenant_project_scope_digest(tenant_id, project_id)
    request_data = _strict_object(
        body["request"],
        "request",
        allowed=frozenset(
            {
                "tenant_scope_digest",
                "authorization_scope_digest",
                "trust_namespace",
                "provider",
                "model",
                "effort_profile",
                "tool_schema_digest",
                "prefix_compatibility_digest",
                "platform_digest",
                "required_capacity",
            }
        ),
        required=frozenset(
            {
                "trust_namespace",
                "provider",
                "model",
                "effort_profile",
                "tool_schema_digest",
                "prefix_compatibility_digest",
                "platform_digest",
                "required_capacity",
            }
        ),
    )
    claimed_scope = request_data.get("tenant_scope_digest")
    if claimed_scope is not None and _digest(claimed_scope, "tenant_scope_digest") != scope_digest:
        raise ContractViolation("tenant scope digest does not match the authenticated scope")
    trusted_authorization_scope_digest = _digest(
        trusted_authorization_scope_digest,
        "trusted_authorization_scope_digest",
    )
    claimed_authorization = request_data.get("authorization_scope_digest")
    if (
        claimed_authorization is not None
        and _digest(claimed_authorization, "authorization_scope_digest")
        != trusted_authorization_scope_digest
    ):
        raise ContractViolation(
            "claimed authorization scope does not match the authenticated principal"
        )
    request = AffinityRequest(
        tenant_scope_digest=scope_digest,
        authorization_scope_digest=trusted_authorization_scope_digest,
        trust_namespace=_identifier(request_data["trust_namespace"], "trust_namespace"),
        provider=_enum(PromptProvider, request_data["provider"], "provider"),
        model=_identifier(request_data["model"], "model"),
        effort_profile=_identifier(request_data["effort_profile"], "effort_profile"),
        tool_schema_digest=_digest(request_data["tool_schema_digest"], "tool_schema_digest"),
        prefix_compatibility_digest=_digest(
            request_data["prefix_compatibility_digest"], "prefix_compatibility_digest"
        ),
        platform_digest=_digest(request_data["platform_digest"], "platform_digest"),
        required_capacity=_integer(request_data["required_capacity"], "required_capacity", minimum=1),
    )
    return project_id, request_id, request


def decide_cache_affinity_payload(
    tenant_id: str,
    payload: Mapping[str, Any],
    *,
    trusted_candidates: Sequence[AffinityCandidate],
    trusted_authorization_scope_digest: str,
) -> AffinityEvaluation:
    """Rank only server-registry candidates under a server-resolved scope."""

    project_id, request_id, request = _affinity_request_from_payload(
        tenant_id,
        payload,
        trusted_authorization_scope_digest=trusted_authorization_scope_digest,
    )
    scope_digest = request.tenant_scope_digest
    candidates = tuple(trusted_candidates)
    if any(not isinstance(candidate, AffinityCandidate) for candidate in candidates):
        raise ContractViolation("affinity registry returned an invalid candidate type")
    for candidate in candidates:
        if (
            candidate.tenant_scope_digest != scope_digest
            or candidate.authorization_scope_digest
            != trusted_authorization_scope_digest
            or not candidate.authorized
        ):
            raise ContractViolation(
                "affinity registry returned an unauthorized or cross-scope candidate",
                target_id=candidate.target_id,
            )
    decision = route_affinity(request, candidates)
    scores = {item.target_id: item for item in decision.scores}
    candidate_documents: list[dict[str, Any]] = []
    for candidate in candidates:
        score = scores.get(candidate.target_id)
        compatible = not candidate.hard_rejections(request)
        candidate_documents.append(
            {
                "target_id": candidate.target_id,
                "compatible": compatible,
                "score": 0.0 if score is None else score.total_ms,
                "prompt_value_ms": candidate.prompt_cache_value_ms,
                "environment_value_ms": candidate.environment_value_ms,
                "artifact_value_ms": candidate.artifact_value_ms,
                "queue_penalty_ms": candidate.queue_delay_ms,
                "transfer_penalty_ms": candidate.transfer_cost_ms,
                "fairness_penalty": candidate.fairness_debt_ms,
            }
        )
    reason_code = {
        RoutingReason.PREFIX_LOCAL: "PREFIX_LOCAL",
        RoutingReason.ENVIRONMENT_LOCAL: "ENV_LOCAL",
        RoutingReason.ARTIFACT_LOCAL: "ARTIFACT_LOCAL",
        RoutingReason.DAG_LOCAL: "DAG_NEXT_USE",
        RoutingReason.BALANCED_SCORE: None,
        RoutingReason.NO_COMPATIBLE_TARGET: "NO_COMPATIBLE_TARGET",
    }[decision.reason]
    decision_id = "affinity_" + digest_of(
        {"request_id": request_id, "decision": decision.to_dict()}
    ).removeprefix("sha256:")
    document: dict[str, Any] = {
        "schema_version": PARITY_API_SCHEMA_VERSION,
        "decision_id": decision_id,
        "affinity_key": decision.affinity_key,
        "request_id": request_id,
        "selected_target": decision.selected_target or "",
        "candidates": candidate_documents,
        "reason_codes": [] if reason_code is None else [reason_code],
    }
    _assert_content_free(document, "affinity decision")
    return AffinityEvaluation(project_id, request_id, decision_id, decision, document)


def _numeric_metrics(value: Any, field: str) -> dict[str, float | int]:
    document = _mapping(value, field)
    unknown = sorted(set(document) - set(MANDATORY_METRICS))
    if unknown:
        raise ContractViolation("parity metrics contain unknown fields", field=field, unknown=unknown)
    result: dict[str, float | int] = {}
    count_metrics = {
        "redundant_validated_rerun_calls",
        "false_hits",
        "cross_tenant_hits",
        "corrupt_executions",
        "under_validated_publications",
    }
    for name, raw in document.items():
        if name in count_metrics:
            result[name] = _integer(raw, f"{field}.{name}")
            continue
        measured = _number(raw, f"{field}.{name}")
        if measured > 1.0:
            raise ContractViolation(
                "parity ratio metrics cannot exceed one", field=f"{field}.{name}"
            )
        result[name] = measured
    return result


def _scenario_detail(value: Any) -> dict[str, Any]:
    detail = _strict_object(
        value,
        "detail",
        allowed=frozenset(
            {
                "authorization_digest",
                "cohort",
                "environment_digest",
                "evidence_role_digests",
                "evidence_state",
                "measurement_window_digest",
                "metrics",
                "repeat_count",
                "replay_digest",
                "sample_count",
                "workload_digest",
            }
        ),
    )
    normalized = dict(detail)
    for name in (
        "authorization_digest",
        "environment_digest",
        "measurement_window_digest",
        "replay_digest",
        "workload_digest",
    ):
        if name in normalized:
            normalized[name] = _digest(normalized[name], name)
    if "evidence_role_digests" in normalized:
        normalized["evidence_role_digests"] = [
            _digest(item, "evidence_role_digests")
            for item in _sequence(normalized["evidence_role_digests"], "evidence_role_digests")
        ]
    for name in ("repeat_count", "sample_count"):
        if name in normalized:
            normalized[name] = _integer(normalized[name], name)
    if "cohort" in normalized:
        cohort = normalized["cohort"]
        if not isinstance(cohort, str) or not _COHORT.fullmatch(cohort):
            raise ContractViolation("scenario detail cohort is invalid")
    if "evidence_state" in normalized:
        state = normalized["evidence_state"]
        if state not in {"PRESENT", "MISSING", "UNVERIFIED"}:
            raise ContractViolation("scenario evidence_state is invalid")
    if "metrics" in normalized:
        metrics = _mapping(normalized["metrics"], "detail.metrics")
        normalized["metrics"] = {
            name: _number(metric, f"detail.metrics.{name}")
            for name, metric in metrics.items()
        }
    _assert_content_free(normalized, "scenario detail")
    return normalized


def _evidence_binding(value: Any) -> EvidenceBinding:
    binding_input = _strict_object(
        value,
        "binding",
        allowed=frozenset(
            {
                "source_digest",
                "configuration_digest",
                "provider_profiles_digest",
                "corpus_digest",
                "platform_digest",
                "generated_at",
                "executor_identity",
                "verifier_identity",
                "tenant_scope_digest",
                "authorization_digest",
            }
        ),
        required=frozenset(
            {
                "source_digest",
                "configuration_digest",
                "provider_profiles_digest",
                "corpus_digest",
                "platform_digest",
                "generated_at",
                "executor_identity",
                "verifier_identity",
            }
        ),
    )
    return EvidenceBinding(
        source_digest=_digest(binding_input["source_digest"], "source_digest"),
        configuration_digest=_digest(
            binding_input["configuration_digest"], "configuration_digest"
        ),
        provider_profiles_digest=_digest(
            binding_input["provider_profiles_digest"], "provider_profiles_digest"
        ),
        corpus_digest=_digest(binding_input["corpus_digest"], "corpus_digest"),
        platform_digest=_digest(binding_input["platform_digest"], "platform_digest"),
        generated_at=_iso_timestamp(binding_input["generated_at"], "generated_at"),
        executor_identity=_identifier(
            binding_input["executor_identity"], "executor_identity"
        ),
        verifier_identity=_identifier(
            binding_input["verifier_identity"], "verifier_identity"
        ),
        tenant_scope_digest=(
            _digest(binding_input["tenant_scope_digest"], "tenant_scope_digest")
            if "tenant_scope_digest" in binding_input
            else None
        ),
        authorization_digest=(
            _digest(binding_input["authorization_digest"], "authorization_digest")
            if "authorization_digest" in binding_input
            else None
        ),
    )


def evaluate_cache_parity_payload(
    tenant_id: str,
    payload: Mapping[str, Any],
    *,
    evidence_verifier: ParityEvidenceVerifier | None = None,
) -> ParityReport:
    """Evaluate only supplied measurements; absent or missing evidence is NOT_RUN."""

    body = _strict_object(
        payload,
        "parity run",
        allowed=frozenset(
            {"project_id", "report_id", "metrics", "cohorts", "scenarios", "binding", "thresholds"}
        ),
        required=frozenset(
            {"project_id", "report_id", "metrics", "cohorts", "scenarios", "binding"}
        ),
    )
    project_id = _project(body)
    # Derivation is intentional even though the current report binding has no
    # tenant field: it validates the authenticated scope before persistence.
    tenant_project_scope_digest(tenant_id, project_id)
    report_id = _identifier(body["report_id"], "report_id")
    metrics = _numeric_metrics(body["metrics"], "metrics")
    cohort_input = _mapping(body["cohorts"], "cohorts")
    cohorts: dict[str, dict[str, float | int]] = {}
    for cohort, values in cohort_input.items():
        if not _COHORT.fullmatch(cohort):
            raise ContractViolation("cohort name is not bounded", cohort=cohort)
        cohorts[cohort] = _numeric_metrics(values, f"cohorts.{cohort}")

    binding = _evidence_binding(body["binding"])

    scenario_results: list[ScenarioResult] = []
    claimed_execution_manifests: set[str] = set()
    for index, raw_scenario in enumerate(_sequence(body["scenarios"], "scenarios")):
        scenario = _strict_object(
            raw_scenario,
            f"scenarios[{index}]",
            allowed=frozenset({"scenario_id", "status", "evidence_digests", "detail"}),
            required=frozenset({"scenario_id", "status"}),
        )
        status = _enum(ScenarioStatus, scenario["status"], "status")
        evidence = tuple(
            _digest(item, "evidence_digest")
            for item in _sequence(scenario.get("evidence_digests", ()), "evidence_digests")
        )
        detail = _scenario_detail(scenario.get("detail", {}))
        if status is ScenarioStatus.PASS:
            verification = (
                EvidenceVerification(False, "EVIDENCE_VERIFIER_UNAVAILABLE")
                if evidence_verifier is None
                else evidence_verifier.verify_scenario(
                    _identifier(scenario["scenario_id"], "scenario_id"),
                    evidence,
                    binding,
                    metrics,
                    cohorts,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    report_id=report_id,
                )
            )
            execution_manifest = verification.execution_manifest_digest
            if (
                not verification.valid
                or execution_manifest is None
                or execution_manifest in claimed_execution_manifests
            ):
                status = ScenarioStatus.NOT_RUN
                detail = {
                    **detail,
                    "evidence_state": "UNVERIFIED",
                    "evidence_failure_code": (
                        "EXECUTION_MANIFEST_REUSED"
                        if execution_manifest in claimed_execution_manifests
                        else verification.reason_code
                    ),
                }
            else:
                claimed_execution_manifests.add(execution_manifest)
                detail = {
                    **detail,
                    "evidence_state": "PRESENT",
                    "execution_manifest_digest": execution_manifest,
                }
        scenario_results.append(
            ScenarioResult(
                scenario_id=_identifier(scenario["scenario_id"], "scenario_id"),
                status=status,
                evidence_digests=evidence,
                detail=detail,
            )
        )

    thresholds: ParityThresholds | None = None
    if "thresholds" in body:
        defaults = asdict(ParityThresholds())
        supplied = _strict_object(
            body["thresholds"],
            "thresholds",
            allowed=frozenset(defaults),
        )
        maximum_thresholds = {
            "unexpected_full_prefix_miss",
            "unnecessary_invalidation",
        }
        zero_tolerance_thresholds = {
            "redundant_validated_rerun_calls",
            "false_hits",
            "cross_tenant_hits",
            "corrupt_executions",
            "under_validated_publications",
        }
        normalized_supplied: dict[str, float | int] = {}
        for name, value in supplied.items():
            default = defaults[name]
            if isinstance(default, int):
                normalized: float | int = _integer(value, f"thresholds.{name}")
            else:
                normalized = _number(value, f"thresholds.{name}")
            if name in zero_tolerance_thresholds and normalized != 0:
                raise ContractViolation("zero-tolerance parity threshold cannot be weakened")
            if name in maximum_thresholds and normalized > default:
                raise ContractViolation(
                    "maximum parity threshold cannot be weakened",
                    threshold=name,
                )
            if (
                name not in maximum_thresholds
                and name not in zero_tolerance_thresholds
                and normalized < default
            ):
                raise ContractViolation(
                    "minimum parity threshold cannot be weakened",
                    threshold=name,
                )
            normalized_supplied[name] = normalized
        defaults.update(normalized_supplied)
        try:
            thresholds = ParityThresholds(**defaults)
        except TypeError as exc:
            raise ContractViolation("parity thresholds have invalid types") from exc
    return evaluate_parity(
        report_id=report_id,
        metrics=metrics,
        cohorts=cohorts,
        scenarios=scenario_results,
        binding=binding,
        thresholds=thresholds,
    )


_LEDGER_PAYLOAD_FIELDS: dict[ContextEventType, frozenset[str]] = {
    ContextEventType.SNAPSHOT_BOUND: frozenset({"snapshot_digest"}),
    ContextEventType.FILE_READ: frozenset({"logical_path", "content_digest"}),
    ContextEventType.SYMBOL_READ: frozenset(
        {"logical_path", "symbol_digest", "content_digest", "source_event_id"}
    ),
    ContextEventType.SUMMARY_WRITTEN: frozenset(
        {"summary_digest", "source_event_ids", "token_count"}
    ),
    ContextEventType.CONTENT_CHANGED: frozenset({"logical_path", "content_digest"}),
    ContextEventType.CONTEXT_STALE: frozenset({"logical_path", "content_digest"}),
    ContextEventType.CONTENT_REREAD: frozenset({"logical_path", "content_digest"}),
    ContextEventType.TOOL_OBSERVED: frozenset(
        {"tool", "result_digest", "status", "duration_ms"}
    ),
    ContextEventType.VALIDATION_OBSERVED: frozenset(
        {"validation_level", "result_digest", "status", "suite_id"}
    ),
    ContextEventType.CONTEXT_CHECKPOINT: frozenset(
        {"checkpoint_id", "checkpoint_digest", "source_event_ids", "ledger_sequence"}
    ),
    ContextEventType.COMPACTION_COMPLETED: frozenset(
        {
            "checkpoint_id",
            "checkpoint_digest",
            "source_event_ids",
            "previous_checkpoint_id",
            "tokens_before",
            "tokens_after",
        }
    ),
    ContextEventType.COMPACTION_ROLLBACK: frozenset(
        {"checkpoint_id", "checkpoint_digest", "rollback_event_ids"}
    ),
}


def _safe_ledger_payload(event_type: ContextEventType, value: Any) -> dict[str, Any]:
    document = _strict_object(
        value,
        "context event payload",
        allowed=_LEDGER_PAYLOAD_FIELDS[event_type],
    )
    normalized = dict(document)
    for name, raw in tuple(normalized.items()):
        if name.endswith("_digest"):
            normalized[name] = _digest(raw, name)
        elif name.endswith("_event_ids"):
            normalized[name] = [
                _identifier(item, name) for item in _sequence(raw, name)
            ]
        elif name.endswith("_event_id") or name.endswith("_id"):
            normalized[name] = _identifier(raw, name)
        elif name in {
            "duration_ms",
            "ledger_sequence",
            "token_count",
            "tokens_after",
            "tokens_before",
        }:
            normalized[name] = _integer(raw, name)
        elif name == "logical_path":
            normalized[name] = _text(raw, name, maximum=2048)
        else:
            normalized[name] = _identifier(raw, name)
    _assert_content_free(normalized, "context event payload")
    return normalized


def _context_event_document(event: ContextLedgerEvent) -> dict[str, Any]:
    document = {
        "schema_version": PARITY_API_SCHEMA_VERSION,
        "stream_id": event.stream_id,
        "sequence": event.sequence,
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "occurred_at": datetime.fromtimestamp(event.occurred_at, UTC).isoformat().replace(
            "+00:00", "Z"
        ),
        "repository_snapshot_digest": event.repository_snapshot_digest,
        "subject_ref": event.subject_ref,
        "payload_digest": event.payload_digest,
        "previous_event_digest": event.previous_event_digest,
        "event_digest": event.event_digest,
        "supersedes_event_id": event.supersedes_event_id,
        "tenant_scope": digest_of(
            {"tenant_id": event.tenant_id, "project_id": event.project_id}
        ),
        "branch_lineage": event.branch_lineage,
    }
    _assert_content_free(document, "context event response")
    return document


def _reason_remediation(family: ReasonFamily) -> str:
    return {
        ReasonFamily.HIT: "NONE",
        ReasonFamily.COLD: "WARM_EXPECTED_ENTRY",
        ReasonFamily.IDENTITY_CHANGED: "REVIEW_FIRST_DIFFERENCE",
        ReasonFamily.TTL_OR_RETENTION: "REBUILD_OR_REFRESH_WITHIN_POLICY",
        ReasonFamily.PLACEMENT: "REBALANCE_COMPATIBLE_SHARD",
        ReasonFamily.CAPACITY_POLICY: "REVIEW_CAPACITY_AND_BYPASS_POLICY",
        ReasonFamily.RESTORE: "REBUILD_AND_RECORD_RESTORE_FAILURE",
        ReasonFamily.SECURITY: "DENY_AND_REAUTHORIZE_EXACT_SCOPE",
        ReasonFamily.CORRUPTION: "QUARANTINE_AND_RECOMPUTE",
        ReasonFamily.ECONOMIC_BYPASS: "RECOMPUTE_AS_SELECTED",
        ReasonFamily.UNSUPPORTED: "DISABLE_UNSUPPORTED_CACHE_PATH",
        ReasonFamily.BACKEND: "RETRY_WITH_BOUNDED_FALLBACK",
        ReasonFamily.UNKNOWN: "INVESTIGATE_AND_CONSUME_UNEXPECTED_MISS_BUDGET",
    }[family]


_EXTERNAL_LAYER = {
    "PROMPT": CacheLayer.PROVIDER_PROMPT,
    "ACTION": CacheLayer.ACTION,
    "CAS_LOCAL": CacheLayer.CAS,
    "CAS_REMOTE": CacheLayer.CAS,
    "CONTEXT": CacheLayer.CONTEXT,
    "ENVIRONMENT": CacheLayer.ENVIRONMENT,
    "NATIVE_BUILD": CacheLayer.NATIVE_BUILD,
    "CHECKPOINT": CacheLayer.STAGING,
    "COORDINATOR": CacheLayer.COORDINATOR,
}


def _validated_outcome(document: Mapping[str, Any]) -> CacheOutcomeEvent:
    layer_value = document.get("layer")
    if not isinstance(layer_value, str) or layer_value not in _EXTERNAL_LAYER:
        raise CorruptObject("stored cache outcome has an unknown layer")
    difference: FirstDifference | None = None
    if document.get("first_difference") is not None:
        raw = _strict_object(
            document["first_difference"],
            "first_difference",
            allowed=frozenset({"dimension", "previous_digest", "current_digest", "reason"}),
            required=frozenset({"dimension", "previous_digest", "current_digest", "reason"}),
        )
        difference = FirstDifference(
            dimension=_enum(IdentityDimension, raw["dimension"], "dimension"),
            previous_digest=_digest(raw["previous_digest"], "previous_digest"),
            current_digest=_digest(raw["current_digest"], "current_digest"),
            reason=_enum(CacheOutcomeReason, raw["reason"], "reason"),
        )
    eligible = document.get("eligible")
    if not isinstance(eligible, bool):
        raise CorruptObject("stored cache outcome has a non-boolean eligibility")
    try:
        return CacheOutcomeEvent(
            layer=_EXTERNAL_LAYER[layer_value],
            outcome=_enum(CacheOutcome, document.get("outcome"), "outcome"),
            reason=_enum(CacheOutcomeReason, document.get("reason_code"), "reason_code"),
            eligible=eligible,
            cohort=_enum(CacheCohort, document.get("cohort", "default"), "cohort"),
            first_difference=difference,
        )
    except ContractViolation as exc:
        raise CorruptObject("stored cache outcome failed semantic validation") from exc


def _provider_outcome(
    reason: ProviderCacheReason,
) -> tuple[CacheOutcome, CacheOutcomeReason]:
    """Map the provider vocabulary into the shared diagnostic taxonomy."""

    mapping = {
        ProviderCacheReason.HIT: (
            CacheOutcome.HIT,
            CacheOutcomeReason.PROMPT_PREFIX_REUSED,
        ),
        ProviderCacheReason.COLD_PREFIX: (
            CacheOutcome.NECESSARY_MISS,
            CacheOutcomeReason.COLD_NO_ENTRY,
        ),
        ProviderCacheReason.MODEL_CHANGED: (
            CacheOutcome.NECESSARY_MISS,
            CacheOutcomeReason.MODEL_CHANGED,
        ),
        ProviderCacheReason.EFFORT_CHANGED: (
            CacheOutcome.NECESSARY_MISS,
            CacheOutcomeReason.EFFORT_CHANGED,
        ),
        ProviderCacheReason.TOOL_SCHEMA_CHANGED: (
            CacheOutcome.NECESSARY_MISS,
            CacheOutcomeReason.TOOL_SCHEMA_CHANGED,
        ),
        ProviderCacheReason.PREFIX_CHANGED: (
            CacheOutcome.NECESSARY_MISS,
            CacheOutcomeReason.PROMPT_SEGMENT_CHANGED,
        ),
        ProviderCacheReason.TTL_EXPIRED: (
            CacheOutcome.NECESSARY_MISS,
            CacheOutcomeReason.TTL_EXPIRED,
        ),
        ProviderCacheReason.WRONG_REPLICA: (
            CacheOutcome.UNEXPECTED_MISS,
            CacheOutcomeReason.WRONG_SHARD,
        ),
        ProviderCacheReason.PROVIDER_UNSUPPORTED: (
            CacheOutcome.BYPASS,
            CacheOutcomeReason.PROVIDER_UNSUPPORTED,
        ),
        ProviderCacheReason.PROVIDER_OUTAGE: (
            CacheOutcome.LOOKUP_ERROR,
            CacheOutcomeReason.BACKEND_UNAVAILABLE,
        ),
        ProviderCacheReason.UNKNOWN: (
            CacheOutcome.UNEXPECTED_MISS,
            CacheOutcomeReason.UNKNOWN_MISS,
        ),
    }
    return mapping[reason]


class ParityApiService:
    """Transport-independent implementation of all seven supplement operations."""

    def __init__(
        self,
        *,
        tenant_id: str,
        store: MetadataStore,
        repository: ParityRepository | None,
        clock: Clock,
        evidence_verifier: ParityEvidenceVerifier | None = None,
        affinity_registry: AttestedAffinityRegistry | None = None,
        affinity_authorizer: AffinityAuthorizationResolver | None = None,
        environment_service: EnvironmentSnapshotService | None = None,
        prompt_cache_controller: PromptCacheController | None = None,
    ) -> None:
        self.tenant_id = _identifier(tenant_id, "tenant_id")
        self.store = store
        self.repository = repository
        self.clock = clock
        self.evidence_verifier = evidence_verifier
        self.affinity_registry = affinity_registry
        self.affinity_authorizer = affinity_authorizer
        self.environment_service = environment_service
        # Provider profiles, kill switches and circuit-breaker state belong to
        # trusted runtime composition.  Request bodies can select only values
        # already admitted by this controller; they cannot register adapters.
        self.prompt_cache_controller = prompt_cache_controller

    def _repository(self) -> ParityRepository:
        if self.repository is None:
            raise RemoteUnavailable("cache parity metadata repository is unavailable")
        return self.repository

    def compile_prompt_prefix(self, payload: Mapping[str, Any]) -> ServiceResult:
        compilation = compile_prompt_prefix_payload(self.tenant_id, payload)
        self._repository().put_prompt_manifest(
            self.tenant_id,
            compilation.project_id,
            str(compilation.manifest["manifest_id"]),
            compilation.manifest,
        )
        return ServiceResult(200, compilation.response)

    def prepare_provider_prompt(self, payload: Mapping[str, Any]) -> ServiceResult:
        """Compile and map one request through a server-owned provider profile.

        The returned provider payload intentionally contains the prompt and is
        therefore never persisted by this service.  Durable state receives
        only the content-free prefix manifest and normalized usage records.
        """

        body = _strict_object(
            payload,
            "provider prompt preparation",
            allowed=frozenset(
                {
                    "project_id",
                    "identity",
                    "segments",
                    "volatility_approvals",
                    "request_class",
                    "cache_mode",
                    "ttl_class",
                }
            ),
            required=frozenset(
                {"project_id", "identity", "segments", "request_class"}
            ),
        )
        controller = self.prompt_cache_controller
        if controller is None:
            raise RemoteUnavailable("provider prompt cache controller is unavailable")
        compilation_payload = {
            key: body[key]
            for key in (
                "project_id",
                "identity",
                "segments",
                "volatility_approvals",
            )
            if key in body
        }
        compilation = compile_prompt_prefix_payload(
            self.tenant_id,
            compilation_payload,
        )
        request_class = _enum(
            PromptRequestClass,
            body["request_class"],
            "request_class",
        )
        cache_mode = (
            None
            if body.get("cache_mode") is None
            else _enum(ProviderCacheMode, body["cache_mode"], "cache_mode")
        )
        ttl_class = (
            None
            if body.get("ttl_class") is None
            else _identifier(body["ttl_class"], "ttl_class")
        )
        provider_request, reason = controller.prepare(
            compilation.compiled,
            request_class,
            cache_mode=cache_mode,
            ttl_class=ttl_class,
        )
        self._repository().put_prompt_manifest(
            self.tenant_id,
            compilation.project_id,
            str(compilation.manifest["manifest_id"]),
            compilation.manifest,
        )
        return ServiceResult(
            200,
            {
                "project_id": compilation.project_id,
                "manifest": compilation.manifest,
                "provider_request": {
                    **provider_request.telemetry(),
                    "payload": dict(provider_request.payload),
                },
                "reason_code": reason.value,
                "provider_execution_performed": False,
            },
        )

    def record_provider_usage(self, payload: Mapping[str, Any]) -> ServiceResult:
        """Normalize provider counters and persist one retry-stable outcome."""

        body = _strict_object(
            payload,
            "provider cache usage",
            allowed=frozenset(
                {
                    "project_id",
                    "prompt_manifest_id",
                    "provider",
                    "request_id",
                    "reason_code",
                    "usage",
                }
            ),
            required=frozenset(
                {
                    "project_id",
                    "prompt_manifest_id",
                    "provider",
                    "request_id",
                    "reason_code",
                    "usage",
                }
            ),
        )
        controller = self.prompt_cache_controller
        if controller is None:
            raise RemoteUnavailable("provider prompt cache controller is unavailable")
        project_id = _project(body)
        manifest_id = _digest(body["prompt_manifest_id"], "prompt_manifest_id")
        provider = _enum(PromptProvider, body["provider"], "provider")
        request_id = _digest(body["request_id"], "request_id")
        reason = _enum(ProviderCacheReason, body["reason_code"], "reason_code")
        manifest = self._repository().get_prompt_manifest(
            self.tenant_id,
            project_id,
            manifest_id,
        )
        if manifest is None:
            raise NotFound("prompt prefix manifest does not exist", manifest_id=manifest_id)
        if manifest.get("provider") != provider.value:
            raise ContractViolation("provider usage does not match the prompt manifest")
        adapter = controller.registry.adapter(provider)
        normalized = adapter.normalize_usage(_mapping(body["usage"], "usage"))
        if (normalized.cache_read_tokens > 0) != (reason is ProviderCacheReason.HIT):
            raise ContractViolation(
                "provider reason and cache-read counters do not agree",
                reason_code=reason.value,
                cache_read_tokens=normalized.cache_read_tokens,
            )
        manifest_digest = digest_of(manifest)
        observation_id = digest_of(
            {
                "tenant_id": self.tenant_id,
                "project_id": project_id,
                "request_id": request_id,
                "prompt_manifest_digest": manifest_digest,
                "provider": provider.value,
            }
        )
        usage_document = self._repository().put_provider_usage(
            self.tenant_id,
            project_id,
            observation_id,
            manifest_digest,
            normalized.telemetry(),
        )
        outcome, outcome_reason = _provider_outcome(reason)
        event_id = "cache_event_" + digest_of(
            {
                "request_id": request_id,
                "observation_id": observation_id,
                "reason_code": outcome_reason.value,
            }
        ).removeprefix("sha256:")
        outcome_document = {
            "schema_version": PARITY_API_SCHEMA_VERSION,
            "event_id": event_id,
            "request_id": request_id,
            "layer": "PROMPT",
            "outcome": outcome.value,
            "reason_code": outcome_reason.value,
            "eligible": reason
            not in {ProviderCacheReason.PROVIDER_UNSUPPORTED, ProviderCacheReason.PROVIDER_OUTAGE},
            "occurred_at": datetime.fromtimestamp(self.clock.now(), tz=UTC).isoformat(),
        }
        self._repository().put_cache_outcome(
            self.tenant_id,
            project_id,
            request_id,
            event_id,
            outcome_document,
        )
        if reason is ProviderCacheReason.PROVIDER_OUTAGE:
            controller.record_provider_failure(provider)
        else:
            controller.record_provider_success(provider)
        return ServiceResult(
            201,
            {
                "project_id": project_id,
                "observation": usage_document,
                "outcome": outcome_document,
                "provider_execution_performed": False,
            },
        )

    def append_context_event(
        self, stream_id: str, payload: Mapping[str, Any], idempotency_key: str
    ) -> ServiceResult:
        body = _strict_object(
            payload,
            "context append",
            allowed=frozenset(
                {
                    "project_id",
                    "branch_lineage",
                    "repository_snapshot_digest",
                    "event_type",
                    "payload",
                    "expected_sequence",
                    "expected_head_digest",
                    "subject_ref",
                    "supersedes_event_id",
                }
            ),
            required=frozenset(
                {
                    "project_id",
                    "branch_lineage",
                    "repository_snapshot_digest",
                    "event_type",
                    "payload",
                }
            ),
        )
        project_id = _project(body)
        kind = _enum(ContextEventType, body["event_type"], "event_type")
        safe_payload = _safe_ledger_payload(kind, body["payload"])
        ledger = RepositoryContextLedger(
            self.store,
            self.tenant_id,
            project_id,
            _text(stream_id, "stream_id", maximum=256),
            _text(body["branch_lineage"], "branch_lineage"),
            _digest(body["repository_snapshot_digest"], "repository_snapshot_digest"),
        )
        before = ledger.position().sequence
        expected_sequence = body.get("expected_sequence")
        event = ledger.append(
            kind,
            safe_payload,
            idempotency_key=_text(idempotency_key, "idempotency_key", maximum=256),
            expected_sequence=(
                None
                if expected_sequence is None
                else _integer(expected_sequence, "expected_sequence")
            ),
            expected_head_digest=_optional_digest(
                body.get("expected_head_digest"), "expected_head_digest"
            ),
            subject_ref=(
                None
                if body.get("subject_ref") is None
                else _text(body["subject_ref"], "subject_ref", maximum=1024)
            ),
            supersedes_event_id=(
                None
                if body.get("supersedes_event_id") is None
                else _identifier(body["supersedes_event_id"], "supersedes_event_id")
            ),
        )
        return ServiceResult(200 if event.sequence <= before else 201, _context_event_document(event))

    def lookup_environment_snapshot(
        self, snapshot_key: str, query: Mapping[str, str]
    ) -> ServiceResult:
        unknown = sorted(set(query) - _ENVIRONMENT_QUERY_FIELDS)
        if unknown:
            raise ContractViolation(
                "environment lookup query has unknown fields",
                unknown=unknown,
            )
        key = _digest(
            snapshot_key if snapshot_key.startswith("sha256:") else f"sha256:{snapshot_key}",
            "snapshotKey",
        )
        project_id = _identifier(query.get("projectId"), "projectId")
        trust_namespace = _identifier(query.get("trustNamespace"), "trustNamespace")
        estimate = RestoreEstimate(
            transfer_ms=_query_number(query, "transferMs"),
            decompression_ms=_query_number(query, "decompressionMs"),
            verification_ms=_query_number(query, "verificationMs"),
            rebuild_ms=_query_number(query, "rebuildMs"),
            minimum_savings_ms=_query_number(query, "minimumSavingsMs", default=0.0),
            maximum_restore_ratio=_query_number(query, "maximumRestoreRatio", default=1.0),
        )
        if self.environment_service is None:
            raise RemoteUnavailable("environment snapshot verification service is unavailable")
        inspection = self.environment_service.inspect(
            self.tenant_id,
            project_id,
            trust_namespace,
            key,
            estimate,
        )
        return ServiceResult(
            200,
            {
                "project_id": project_id,
                "manifest_digest": inspection.manifest_digest,
                "verified": True,
                "verified_layer_digests": list(inspection.verified_layer_digests),
                "manifest": dict(inspection.manifest),
                "restore_decision": inspection.decision.to_dict(),
                "execution_performed": False,
            },
        )

    def decide_affinity(
        self,
        payload: Mapping[str, Any],
        *,
        principal_digest: str,
    ) -> ServiceResult:
        if self.affinity_registry is None:
            raise RemoteUnavailable(
                "server-side attested affinity registry is unavailable"
            )
        if self.affinity_authorizer is None:
            raise RemoteUnavailable(
                "server-side affinity authorization resolver is unavailable"
            )
        project_id = _project(payload)
        request_id = _identifier(payload.get("request_id"), "request_id")
        authenticated_principal = _digest(principal_digest, "principal_digest")
        authorization = self.affinity_authorizer.resolve(
            authenticated_principal,
            self.tenant_id,
            project_id,
            request_id,
        )
        if not isinstance(authorization, AffinityAuthorizationContext):
            raise ContractViolation("affinity authorization resolver returned an invalid type")
        if (
            authorization.principal_digest != authenticated_principal
            or authorization.tenant_id != self.tenant_id
            or authorization.project_id != project_id
        ):
            raise PermissionDenied("affinity authorization scope mismatch")
        if not authorization.allowed:
            raise PermissionDenied("affinity routing is not authorized for this principal")
        _, _, request = _affinity_request_from_payload(
            self.tenant_id,
            payload,
            trusted_authorization_scope_digest=authorization.authorization_scope_digest,
        )
        trusted_candidates = self.affinity_registry.candidates(
            self.tenant_id,
            project_id,
            request,
            self.clock.now(),
        )
        evaluation = decide_cache_affinity_payload(
            self.tenant_id,
            payload,
            trusted_candidates=trusted_candidates,
            trusted_authorization_scope_digest=authorization.authorization_scope_digest,
        )
        # The canonical decision is intentionally time-free.  An ambiguous
        # retry after the repository commit must reconstruct identical bytes.
        document = evaluation.document
        self._repository().put_affinity_decision(
            self.tenant_id,
            evaluation.project_id,
            evaluation.request_id,
            evaluation.decision_id,
            document,
        )
        return ServiceResult(200, document)

    def explain_cache_outcome(self, request_id: str, query: Mapping[str, str]) -> ServiceResult:
        normalized_request = _identifier(request_id, "requestId")
        project_id = _identifier(query.get("projectId"), "projectId")
        documents = self._repository().list_cache_outcomes(
            self.tenant_id, project_id, normalized_request
        )
        if not documents:
            raise NotFound("cache outcome does not exist", request_id=normalized_request)
        outcomes: list[dict[str, Any]] = []
        remediations: set[str] = set()
        first_differences: list[dict[str, str]] = []
        nodes: list[dict[str, str]] = []
        edges: list[dict[str, str]] = []
        for document in documents:
            _assert_content_free(document, "cache outcome")
            event = _validated_outcome(document)
            diagnostic = event.diagnostic()
            event_id = _identifier(document.get("event_id"), "event_id")
            outcomes.append(
                {
                    "event_id": event_id,
                    "occurred_at": _iso_timestamp(
                        document.get("occurred_at"), "occurred_at"
                    ),
                    **diagnostic,
                }
            )
            remediations.add(_reason_remediation(event.family))
            if event.first_difference is not None:
                first_differences.append(event.first_difference.to_dict())
            nodes.append({"id": event_id, "reason": event.reason.value})
            edges.append(
                {"from": normalized_request, "to": event_id, "relation": "OBSERVED_OUTCOME"}
            )
        return ServiceResult(
            200,
            {
                "project_id": project_id,
                "request_id": normalized_request,
                "outcomes": outcomes,
                "first_differences": first_differences,
                "causal_invalidation_graph": {
                    "root": normalized_request,
                    "nodes": nodes,
                    "edges": edges,
                    "claim": "OBSERVED_ONLY",
                },
                "remediation_codes": sorted(remediations),
            },
        )

    def start_parity_run(self, payload: Mapping[str, Any]) -> ServiceResult:
        report = evaluate_cache_parity_payload(
            self.tenant_id,
            payload,
            evidence_verifier=self.evidence_verifier,
        )
        project_id = _project(payload)
        document = report.to_dict()
        _assert_content_free(document, "parity report")
        self._repository().put_parity_report(
            self.tenant_id, project_id, report.report_id, document
        )
        return ServiceResult(
            202,
            {
                "project_id": project_id,
                "decision": report.decision.value,
                "report": document,
                "provider_execution_performed": False,
                "certified": False,
            },
        )

    def get_parity_report(self, report_id: str, query: Mapping[str, str]) -> ServiceResult:
        normalized_report = _identifier(report_id, "reportId")
        project_id = _identifier(query.get("projectId"), "projectId")
        document = self._repository().get_parity_report(
            self.tenant_id, project_id, normalized_report
        )
        if document is None:
            raise NotFound("cache parity report does not exist", report_id=normalized_report)
        _assert_content_free(document, "parity report")
        decision = _enum(ParityDecision, document.get("decision"), "decision")
        if decision is ParityDecision.READY_FOR_EXTERNAL_GATE and not document.get(
            "mandatory_pass", False
        ):
            raise CorruptObject("parity report decision contradicts mandatory_pass")
        return ServiceResult(
            200,
            {
                "project_id": project_id,
                "decision": decision.value,
                "report": document,
                "certified": False,
            },
        )


def _query_number(
    query: Mapping[str, str], name: str, *, default: float | None = None
) -> float:
    raw = query.get(name)
    if raw is None:
        if default is None:
            raise ContractViolation(f"{name} is required", field=name)
        return default
    try:
        parsed = float(raw)
    except ValueError as exc:
        raise ContractViolation(f"{name} must be numeric", field=name) from exc
    return _number(parsed, name)


__all__ = [
    "AffinityEvaluation",
    "ParityApiService",
    "ParityRepository",
    "PromptCompilation",
    "ServiceResult",
    "compile_prompt_prefix_payload",
    "decide_cache_affinity_payload",
    "evaluate_cache_parity_payload",
    "tenant_project_scope_digest",
]
