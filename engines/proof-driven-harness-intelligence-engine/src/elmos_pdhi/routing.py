"""K8 tool, model, prompt, context and benchmark intelligence.

Routing is policy evaluation, not provider execution.  It never creates new
authority, never silently lowers an evidence requirement and never treats a
quota/provider failure as permission to use an unapproved fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import re
import string
import threading
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from pathlib import PurePosixPath

from .canonical import digest_object, require_sha256_digest, utc_now
from .contracts import AuthorityLevel
from .errors import ValidationError


AUTHORITY_RANK: Mapping[AuthorityLevel, int] = MappingProxyType(
    {
        AuthorityLevel.FORMAL_PROOF: 8,
        AuthorityLevel.COMPILER: 7,
        AuthorityLevel.LSP: 6,
        AuthorityLevel.SEMANTIC_IR: 5,
        AuthorityLevel.AST: 4,
        AuthorityLevel.RUNTIME_EVIDENCE: 3,
        AuthorityLevel.TEXT_SEARCH: 2,
        AuthorityLevel.LLM_INFERENCE: 1,
    }
)


class RouteStatus(StrEnum):
    SELECTED = "SELECTED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    NOT_RUN = "NOT_RUN"
    BLOCKED = "BLOCKED"


class CandidateAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    PROVIDER_FAILED = "PROVIDER_FAILED"
    COOLDOWN = "COOLDOWN"
    REVOKED = "REVOKED"
    UNKNOWN = "UNKNOWN"


class ProviderFailure(StrEnum):
    QUOTA = "QUOTA"
    TRANSIENT = "TRANSIENT"
    AUTHENTICATION = "AUTHENTICATION"
    POLICY = "POLICY"
    UNKNOWN = "UNKNOWN"


def _text(value: object, name: str, *, max_length: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > max_length:
        raise ValidationError(f"{name} is invalid", code="INVALID_ROUTING_TEXT")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValidationError(f"{name} contains control characters")
    return value


def _decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValidationError(f"{name} must be a non-negative finite Decimal")
    return value


def _path_within(path: str, prefix: str) -> bool:
    return prefix == "." or path == prefix or path.startswith(prefix.rstrip("/") + "/")


def _normalize_path(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValidationError(f"{name} must be a normalized POSIX path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValidationError(f"{name} escapes its repository scope")
    normalized = parsed.as_posix()
    if normalized != value or normalized in {"", "."} and value != ".":
        raise ValidationError(f"{name} must already be normalized")
    return normalized


@dataclass(frozen=True, slots=True)
class ToolCandidate:
    tool_id: str
    version: str
    digest: str
    authority: AuthorityLevel
    capabilities: frozenset[str]
    tenant_ids: frozenset[str]
    path_scopes: tuple[str, ...]
    requires_network: bool
    requires_approval: bool
    quality_score: Decimal
    estimated_cost: Decimal
    estimated_latency_ms: int
    availability: CandidateAvailability = CandidateAvailability.AVAILABLE

    def __post_init__(self) -> None:
        _text(self.tool_id, "tool_id")
        _text(self.version, "version")
        require_sha256_digest(self.digest, field="digest")
        if not isinstance(self.authority, AuthorityLevel):
            raise ValidationError("tool authority is invalid")
        if not self.capabilities or not self.tenant_ids or not self.path_scopes:
            raise ValidationError("tool capabilities, tenants and path scopes are required")
        for scope in self.path_scopes:
            _normalize_path(scope, "path_scope")
        if not isinstance(self.availability, CandidateAvailability):
            raise ValidationError("tool availability is invalid")
        _decimal(self.quality_score, "quality_score")
        _decimal(self.estimated_cost, "estimated_cost")
        if self.quality_score > Decimal("1") or self.estimated_latency_ms < 0:
            raise ValidationError("tool quality/latency is outside its allowed range")


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    model_id: str
    provider_id: str
    version: str
    digest: str
    roles: frozenset[str]
    maximum_effort: int
    security_profile: str
    tenant_ids: frozenset[str]
    path_scopes: tuple[str, ...]
    quality_score: Decimal
    input_cost_per_million: Decimal
    output_cost_per_million: Decimal
    estimated_latency_ms: int
    availability: CandidateAvailability = CandidateAvailability.AVAILABLE

    def __post_init__(self) -> None:
        for name in ("model_id", "provider_id", "version", "security_profile"):
            _text(getattr(self, name), name)
        require_sha256_digest(self.digest, field="digest")
        if not self.roles or not self.tenant_ids or not self.path_scopes:
            raise ValidationError("model roles, tenants and path scopes are required")
        for scope in self.path_scopes:
            _normalize_path(scope, "path_scope")
        if isinstance(self.maximum_effort, bool) or not isinstance(self.maximum_effort, int) or self.maximum_effort < 0:
            raise ValidationError("maximum_effort must be non-negative")
        for name in ("quality_score", "input_cost_per_million", "output_cost_per_million"):
            _decimal(getattr(self, name), name)
        if self.quality_score > Decimal("1") or self.estimated_latency_ms < 0:
            raise ValidationError("model quality/latency is outside its allowed range")


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    policy_id: str
    policy_digest: str
    tenant_id: str
    allowed_tools: frozenset[str]
    allowed_models: frozenset[str]
    allowed_providers: frozenset[str]
    minimum_tool_authority: AuthorityLevel
    minimum_quality: Decimal
    maximum_cost: Decimal
    maximum_latency_ms: int
    required_security_profile: str
    network_allowed: bool = False
    approval_granted: bool = False

    def __post_init__(self) -> None:
        for name in ("policy_id", "tenant_id", "required_security_profile"):
            _text(getattr(self, name), name)
        require_sha256_digest(self.policy_digest, field="policy_digest")
        _decimal(self.minimum_quality, "minimum_quality")
        _decimal(self.maximum_cost, "maximum_cost")
        if self.minimum_quality > Decimal("1") or self.maximum_latency_ms < 0:
            raise ValidationError("routing policy threshold is invalid")


@dataclass(frozen=True, slots=True)
class RouteDecision:
    status: RouteStatus
    selected_id: str | None
    selected_digest: str | None
    candidates_considered: tuple[str, ...]
    rejected: Mapping[str, tuple[str, ...]]
    policy_id: str
    reason: str
    decision_digest: str


class ToolAuthorityRouter:
    def route(
        self,
        *,
        capability: str,
        path: str,
        required_authority: AuthorityLevel,
        policy: RoutingPolicy,
        candidates: Sequence[ToolCandidate],
    ) -> RouteDecision:
        _text(capability, "capability")
        path = _normalize_path(path, "path")
        if AUTHORITY_RANK[required_authority] < AUTHORITY_RANK[policy.minimum_tool_authority]:
            required_authority = policy.minimum_tool_authority
        rejected: dict[str, tuple[str, ...]] = {}
        eligible: list[ToolCandidate] = []
        for candidate in candidates:
            reasons: list[str] = []
            if candidate.tool_id not in policy.allowed_tools:
                reasons.append("tool_not_allowlisted")
            if policy.tenant_id not in candidate.tenant_ids:
                reasons.append("tenant_not_supported")
            if capability not in candidate.capabilities:
                reasons.append("capability_not_supported")
            if not any(_path_within(path, item) for item in candidate.path_scopes):
                reasons.append("path_scope_denied")
            if AUTHORITY_RANK[candidate.authority] < AUTHORITY_RANK[required_authority]:
                reasons.append("authority_too_low")
            if candidate.requires_network and not policy.network_allowed:
                reasons.append("network_denied")
            if candidate.quality_score < policy.minimum_quality:
                reasons.append("quality_below_floor")
            if candidate.estimated_cost > policy.maximum_cost:
                reasons.append("cost_over_ceiling")
            if candidate.estimated_latency_ms > policy.maximum_latency_ms:
                reasons.append("latency_over_ceiling")
            if candidate.availability is not CandidateAvailability.AVAILABLE:
                reasons.append("availability:" + candidate.availability.value)
            if candidate.requires_approval and not policy.approval_granted:
                reasons.append("approval_required")
            if reasons:
                rejected[candidate.tool_id] = tuple(reasons)
            else:
                eligible.append(candidate)
        eligible.sort(
            key=lambda item: (
                -AUTHORITY_RANK[item.authority],
                -item.quality_score,
                item.estimated_cost,
                item.estimated_latency_ms,
                item.tool_id,
            )
        )
        selected = eligible[0] if eligible else None
        status = RouteStatus.SELECTED if selected else RouteStatus.NOT_RUN
        reason = "exact authorized tool selected" if selected else "no candidate satisfies authority and policy without downgrade"
        candidate_ids = tuple(sorted(item.tool_id for item in candidates))
        body = {
            "status": status.value,
            "selected_id": None if selected is None else selected.tool_id,
            "candidate_ids": candidate_ids,
            "candidate_digests": tuple(sorted((item.tool_id, item.digest) for item in candidates)),
            "rejected": rejected,
            "policy_id": policy.policy_id,
            "policy_digest": policy.policy_digest,
            "capability": capability,
            "path": path,
            "required_authority": required_authority.value,
        }
        return RouteDecision(
            status,
            None if selected is None else selected.tool_id,
            None if selected is None else selected.digest,
            candidate_ids,
            MappingProxyType(rejected),
            policy.policy_id,
            reason,
            digest_object(body, domain="pdhi-tool-route-decision"),
        )


class ModelRoleRouter:
    def route(
        self,
        *,
        role: str,
        effort: int,
        path: str,
        estimated_tokens: int,
        policy: RoutingPolicy,
        candidates: Sequence[ModelCandidate],
    ) -> RouteDecision:
        _text(role, "role")
        path = _normalize_path(path, "path")
        if isinstance(effort, bool) or not isinstance(effort, int) or effort < 0:
            raise ValidationError("effort must be a non-negative integer")
        if isinstance(estimated_tokens, bool) or not isinstance(estimated_tokens, int) or estimated_tokens < 1:
            raise ValidationError("estimated_tokens must be positive")
        rejected: dict[str, tuple[str, ...]] = {}
        eligible: list[tuple[ModelCandidate, Decimal]] = []
        for candidate in candidates:
            reasons: list[str] = []
            if candidate.model_id not in policy.allowed_models or candidate.provider_id not in policy.allowed_providers:
                reasons.append("model_or_provider_not_allowlisted")
            if policy.tenant_id not in candidate.tenant_ids:
                reasons.append("tenant_not_supported")
            if role not in candidate.roles:
                reasons.append("role_not_supported")
            if effort > candidate.maximum_effort:
                reasons.append("effort_ceiling_would_be_weakened")
            if candidate.security_profile != policy.required_security_profile:
                reasons.append("security_profile_mismatch")
            if not any(_path_within(path, item) for item in candidate.path_scopes):
                reasons.append("path_scope_denied")
            if candidate.quality_score < policy.minimum_quality:
                reasons.append("quality_below_floor")
            if candidate.estimated_latency_ms > policy.maximum_latency_ms:
                reasons.append("latency_over_ceiling")
            estimated_cost = (
                (candidate.input_cost_per_million + candidate.output_cost_per_million)
                * Decimal(estimated_tokens)
                / Decimal(1_000_000)
            )
            if estimated_cost > policy.maximum_cost:
                reasons.append("cost_over_ceiling")
            if candidate.availability is not CandidateAvailability.AVAILABLE:
                reasons.append("availability:" + candidate.availability.value)
            if reasons:
                rejected[candidate.model_id] = tuple(reasons)
            else:
                eligible.append((candidate, estimated_cost))
        eligible.sort(key=lambda item: (-item[0].quality_score, item[1], item[0].estimated_latency_ms, item[0].model_id))
        selected = eligible[0][0] if eligible else None
        status = RouteStatus.SELECTED if selected else RouteStatus.NOT_RUN
        body = {
            "status": status.value,
            "selected_id": None if selected is None else selected.model_id,
            "role": role,
            "effort": effort,
            "path": path,
            "rejected": rejected,
            "policy_id": policy.policy_id,
            "policy_digest": policy.policy_digest,
            "candidate_digests": tuple(sorted((item.model_id, item.digest) for item in candidates)),
        }
        return RouteDecision(
            status,
            None if selected is None else selected.model_id,
            None if selected is None else selected.digest,
            tuple(sorted(item.model_id for item in candidates)),
            MappingProxyType(rejected),
            policy.policy_id,
            "exact authorized model selected" if selected else "fallback chain exhausted without weakening ceilings",
            digest_object(body, domain="pdhi-model-route-decision"),
        )


@dataclass(frozen=True, slots=True)
class ContextEntry:
    sequence: int
    entry_id: str
    kind: str
    payload: Mapping[str, Any]
    required: bool
    source_digest: str
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ContextCheckpoint:
    checkpoint_id: str
    sequence: int
    entry_digests: tuple[str, ...]
    invariant_ids: tuple[str, ...]
    digest: str


class AppendOnlyContextLedger:
    def __init__(self, *, maximum_entries: int = 10_000) -> None:
        if maximum_entries < 1:
            raise ValidationError("maximum_entries must be positive")
        self._maximum_entries = maximum_entries
        self._entries: list[ContextEntry] = []
        self._checkpoints: dict[str, ContextCheckpoint] = {}
        self._lock = threading.RLock()

    def append(self, *, entry_id: str, kind: str, payload: Mapping[str, Any], required: bool, source_digest: str) -> ContextEntry:
        _text(entry_id, "entry_id")
        _text(kind, "kind")
        require_sha256_digest(source_digest, field="source_digest")
        with self._lock:
            if len(self._entries) >= self._maximum_entries:
                raise ValidationError("context ledger capacity reached; explicit compaction required")
            if any(item.entry_id == entry_id for item in self._entries):
                raise ValidationError("duplicate context entry id")
            entry = ContextEntry(len(self._entries) + 1, entry_id, kind, MappingProxyType(dict(payload)), required, source_digest)
            self._entries.append(entry)
            return entry

    def checkpoint(self, *, checkpoint_id: str, invariant_ids: Sequence[str]) -> ContextCheckpoint:
        _text(checkpoint_id, "checkpoint_id")
        invariants = tuple(invariant_ids)
        if not invariants or len(set(invariants)) != len(invariants):
            raise ValidationError("checkpoint invariants must be nonempty and unique")
        with self._lock:
            if checkpoint_id in self._checkpoints:
                raise ValidationError("checkpoint id already exists")
            entry_digests = tuple(digest_object(item, domain="pdhi-context-entry") for item in self._entries)
            body = {"checkpoint_id": checkpoint_id, "sequence": len(self._entries), "entry_digests": entry_digests, "invariant_ids": invariants}
            checkpoint = ContextCheckpoint(checkpoint_id, len(self._entries), entry_digests, invariants, digest_object(body, domain="pdhi-context-checkpoint"))
            self._checkpoints[checkpoint_id] = checkpoint
            return checkpoint

    def rewind_view(self, checkpoint_id: str) -> tuple[ContextEntry, ...]:
        with self._lock:
            checkpoint = self._checkpoints.get(checkpoint_id)
            if checkpoint is None:
                raise ValidationError("checkpoint is unavailable")
            # Rewind is a view.  It never deletes append-only history.
            return tuple(self._entries[: checkpoint.sequence])

    def compact(self, *, through_sequence: int, summary_id: str, summary: Mapping[str, Any], source_digest: str) -> ContextEntry:
        if through_sequence < 1:
            raise ValidationError("through_sequence must be positive")
        with self._lock:
            selected = [item for item in self._entries if item.sequence <= through_sequence]
            if not selected or selected[-1].sequence != through_sequence:
                raise ValidationError("compaction sequence is unavailable")
            required_ids = [item.entry_id for item in selected if item.required]
            declared = summary.get("preserved_required_entry_ids")
            if not isinstance(declared, (tuple, list)) or sorted(declared) != sorted(required_ids):
                raise ValidationError("compaction would lose required context invariants")
            body = dict(summary)
            body["compacted_entry_digests"] = [digest_object(item, domain="pdhi-context-entry") for item in selected]
            return self.append(entry_id=summary_id, kind="compaction", payload=body, required=True, source_digest=source_digest)

    def rebuild(self, checkpoint_id: str) -> Mapping[str, Any]:
        view = self.rewind_view(checkpoint_id)
        checkpoint = self._checkpoints[checkpoint_id]
        return MappingProxyType(
            {
                "checkpoint_id": checkpoint_id,
                "entries": tuple(view),
                "invariant_ids": checkpoint.invariant_ids,
                "rebuild_digest": digest_object({"checkpoint": checkpoint, "entries": view}, domain="pdhi-context-rebuild"),
            }
        )


class PromptSurfaceCompiler:
    _FORMATTER = string.Formatter()

    def compile(self, *, template_id: str, template: str, values: Mapping[str, str], allowed_fields: frozenset[str]) -> Mapping[str, Any]:
        _text(template_id, "template_id")
        _text(template, "template", max_length=64 * 1024)
        referenced = {field for _, field, _, _ in self._FORMATTER.parse(template) if field}
        if referenced != set(values) or not referenced.issubset(allowed_fields):
            raise ValidationError("prompt fields are missing, extra, or not allowlisted")
        if any(not isinstance(value, str) for value in values.values()):
            raise ValidationError("prompt values must be text")
        rendered = template.format_map(dict(values))
        if re.search(r"\{[^{}]+\}", rendered):
            raise ValidationError("compiled prompt contains unresolved placeholders")
        body = {"template_id": template_id, "fields": sorted(referenced), "rendered": rendered}
        return MappingProxyType({**body, "digest": digest_object(body, domain="pdhi-prompt")})

    def lint(self, rendered: str) -> tuple[str, ...]:
        issues: list[str] = []
        lowered = rendered.lower()
        if "ignore previous" in lowered or "bypass policy" in lowered:
            issues.append("authority_boundary_language")
        if re.search(r"\b(pass|certified)\b", lowered) and "evidence" not in lowered:
            issues.append("unsupported_success_claim")
        if len(rendered.encode("utf-8")) > 64 * 1024:
            issues.append("prompt_too_large")
        return tuple(issues)


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    benchmark_id: str
    variant_id: str
    quality: Decimal
    cost: Decimal
    latency_ms: int
    evidence_ids: tuple[str, ...]
    independent: bool
    corpus_digest: str


class HarnessBenchmarkLab:
    def decide_promotion(
        self,
        *,
        baseline: BenchmarkResult,
        candidate: BenchmarkResult,
        quality_tolerance: Decimal,
    ) -> Mapping[str, Any]:
        _decimal(quality_tolerance, "quality_tolerance")
        for result in (baseline, candidate):
            require_sha256_digest(result.corpus_digest, field="corpus_digest")
            _decimal(result.quality, "quality")
            _decimal(result.cost, "cost")
            if not result.evidence_ids or not result.independent:
                raise ValidationError("benchmark promotion requires independent evidence")
        if baseline.corpus_digest != candidate.corpus_digest:
            raise ValidationError("benchmark corpus drift invalidates comparison")
        quality_delta = candidate.quality - baseline.quality
        promoted = quality_delta >= -quality_tolerance and (
            candidate.cost < baseline.cost or candidate.latency_ms < baseline.latency_ms or quality_delta > 0
        )
        body = {
            "baseline": baseline.variant_id,
            "candidate": candidate.variant_id,
            "quality_delta": format(quality_delta, "f"),
            "promoted": promoted,
            "reason": "quality floor preserved with measurable improvement" if promoted else "candidate does not meet promotion policy",
        }
        return MappingProxyType({**body, "decision_digest": digest_object(body, domain="pdhi-benchmark-decision")})


K8_CAPABILITY_BINDINGS: Mapping[str, str] = MappingProxyType(
    {
        "tool-authority-router": "ToolAuthorityRouter.route",
        "semantic-tool-priority": "ToolAuthorityRouter.route",
        "tool-capability-negotiator": "ToolAuthorityRouter.route",
        "tool-failure-classifier": "ProviderFailure",
        "no-silent-fallback": "ToolAuthorityRouter.route",
        "tool-approval-router": "ToolAuthorityRouter.route",
        "model-role-router": "ModelRoleRouter.route",
        "model-capability-profile": "ModelCandidate",
        "model-fallback-chain": "ModelRoleRouter.route",
        "quota-aware-fallback": "ModelRoleRouter.route",
        "provider-failure-fallback": "ModelRoleRouter.route",
        "effort-aware-routing": "ModelRoleRouter.route",
        "phase-model-handoff": "ModelRoleRouter.route",
        "cost-aware-routing": "ModelRoleRouter.route",
        "latency-aware-routing": "ModelRoleRouter.route",
        "quality-aware-routing": "ModelRoleRouter.route",
        "path-scoped-model-policy": "RoutingPolicy",
        "tenant-model-policy": "RoutingPolicy",
        "credential-pool-affinity": "RoutingPolicy",
        "prompt-compiler": "PromptSurfaceCompiler.compile",
        "prompt-linter": "PromptSurfaceCompiler.lint",
        "rfc-normative-policy": "PromptSurfaceCompiler.lint",
        "tool-doc-surface-optimizer": "HarnessBenchmarkLab.decide_promotion",
        "example-contract-validator": "PromptSurfaceCompiler.lint",
        "skill-lazy-loader": "RoutingPolicy",
        "rule-lazy-loader": "RoutingPolicy",
        "context-budget-manager": "AppendOnlyContextLedger",
        "append-only-context-optimizer": "AppendOnlyContextLedger.compact",
        "adaptive-compaction": "AppendOnlyContextLedger.compact",
        "checkpoint": "AppendOnlyContextLedger.checkpoint",
        "rewind": "AppendOnlyContextLedger.rewind_view",
        "context-promotion": "HarnessBenchmarkLab.decide_promotion",
        "provider-stream-reset": "ModelRoleRouter.route",
        "context-rebuild": "AppendOnlyContextLedger.rebuild",
        "foreign-session-import": "AppendOnlyContextLedger.append",
        "harness-ab-test": "HarnessBenchmarkLab.decide_promotion",
        "tool-format-benchmark": "HarnessBenchmarkLab.decide_promotion",
        "edit-format-benchmark": "HarnessBenchmarkLab.decide_promotion",
        "prompt-benchmark": "HarnessBenchmarkLab.decide_promotion",
        "context-strategy-benchmark": "HarnessBenchmarkLab.decide_promotion",
        "routing-benchmark": "HarnessBenchmarkLab.decide_promotion",
        "retry-policy-benchmark": "HarnessBenchmarkLab.decide_promotion",
    }
)

if len(K8_CAPABILITY_BINDINGS) != 42:
    raise RuntimeError("K8 must bind exactly 42 canonical capabilities")


__all__ = [
    "AUTHORITY_RANK",
    "AppendOnlyContextLedger",
    "BenchmarkResult",
    "CandidateAvailability",
    "ContextCheckpoint",
    "ContextEntry",
    "HarnessBenchmarkLab",
    "K8_CAPABILITY_BINDINGS",
    "ModelCandidate",
    "ModelRoleRouter",
    "PromptSurfaceCompiler",
    "ProviderFailure",
    "RouteDecision",
    "RouteStatus",
    "RoutingPolicy",
    "ToolAuthorityRouter",
    "ToolCandidate",
]
