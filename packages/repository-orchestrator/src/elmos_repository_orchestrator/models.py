"""Model-selection, registry, task-profile, and pricing contracts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping

from .catalog import MODEL_ALIASES, MODEL_ALIAS_SET
from .contracts import (
    ContractError,
    FallbackPolicy,
    ModelMode,
    ModelTier,
    OptimizationProfile,
    RiskLevel,
    SelectionSource,
    VerificationPolicy,
    decimal_value,
    finite_probability,
    integer_value,
    parse_timestamp,
    require_mapping,
    require_string,
    require_string_sequence,
    sha256_payload,
    utc_now,
)


_SELECTION_FIELDS = {
    "mode",
    "selected_model",
    "optimization_profile",
    "fallback_policy",
    "verification_policy",
}
_SERVER_SELECTION_FIELDS = {
    "selection_source",
    "locked_by_user",
    "resolved_at",
    "registry_digest",
}


@dataclass(frozen=True, slots=True)
class ResolvedModelSelection:
    mode: ModelMode
    selected_model: str | None
    optimization_profile: OptimizationProfile
    fallback_policy: FallbackPolicy
    verification_policy: VerificationPolicy
    selection_source: SelectionSource
    locked_by_user: bool
    resolved_at: datetime
    registry_digest: str | None = None

    def to_payload(self) -> dict[str, Any]:
        if self.registry_digest is None:
            raise ContractError("selection_not_registry_bound", "resolved selection requires a trusted registry digest")
        return {
            "mode": self.mode.value,
            "selected_model": self.selected_model,
            "optimization_profile": self.optimization_profile.value,
            "fallback_policy": self.fallback_policy.value,
            "verification_policy": self.verification_policy.value,
            "selection_source": self.selection_source.value,
            "locked_by_user": self.locked_by_user,
            "resolved_at": self.resolved_at.isoformat().replace("+00:00", "Z"),
            "registry_digest": self.registry_digest,
        }

    def request_payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "selected_model": self.selected_model,
            "optimization_profile": self.optimization_profile.value,
            "fallback_policy": self.fallback_policy.value,
            "verification_policy": self.verification_policy.value,
        }

    def bind_registry(self, registry_digest: str) -> "ResolvedModelSelection":
        digest = require_string(registry_digest, "registry_digest")
        if not digest.startswith("sha256:") or len(digest) != 71:
            raise ContractError("invalid_registry_digest", "registry digest must be a prefixed SHA-256 digest")
        return replace(self, registry_digest=digest)


def resolve_model_selection(
    payload: Mapping[str, Any],
    *,
    source: SelectionSource | str,
    now: datetime | None = None,
) -> ResolvedModelSelection:
    value = require_mapping(payload, "model_selection")
    forged = sorted(set(value) & _SERVER_SELECTION_FIELDS)
    if forged:
        raise ContractError(
            "server_field_forgery",
            "caller may not provide server-derived field(s): " + ", ".join(forged),
        )
    unknown = sorted(set(value) - _SELECTION_FIELDS)
    if unknown:
        raise ContractError("unknown_selection_field", "unknown model-selection field(s): " + ", ".join(unknown))
    try:
        mode = ModelMode(value.get("mode", "smart"))
    except ValueError as exc:
        raise ContractError("invalid_selection_mode", "mode must be smart or manual") from exc
    selected = value.get("selected_model")
    if mode is ModelMode.MANUAL:
        if not isinstance(selected, str) or selected not in MODEL_ALIAS_SET:
            raise ContractError("manual_model_required", "manual mode requires one exact allowlisted selected_model")
    elif selected is not None:
        raise ContractError("smart_model_forbidden", "smart mode requires selected_model to be null or absent")
    try:
        profile = OptimizationProfile(value.get("optimization_profile", "cost_performance"))
    except ValueError as exc:
        raise ContractError("invalid_optimization_profile", "unsupported optimization_profile") from exc
    try:
        fallback = FallbackPolicy(value.get("fallback_policy", "strict"))
    except ValueError as exc:
        raise ContractError("invalid_fallback_policy", "unsupported fallback_policy") from exc
    try:
        verification = VerificationPolicy(value.get("verification_policy", "system_required_verifiers"))
    except ValueError as exc:
        raise ContractError("invalid_verification_policy", "unsupported verification_policy") from exc
    try:
        trusted_source = source if isinstance(source, SelectionSource) else SelectionSource(source)
    except ValueError as exc:
        raise ContractError("invalid_selection_source", "server selection source is invalid") from exc
    if now is not None and (now.tzinfo is None or now.utcoffset() is None):
        raise ContractError("naive_timestamp", "server resolution time must be timezone-aware")
    resolved_at = (now or utc_now()).astimezone(timezone.utc)
    return ResolvedModelSelection(
        mode=mode,
        selected_model=selected,
        optimization_profile=profile,
        fallback_policy=fallback,
        verification_policy=verification,
        selection_source=trusted_source,
        locked_by_user=mode is ModelMode.MANUAL,
        resolved_at=resolved_at,
    )


@dataclass(frozen=True, slots=True)
class Pricing:
    input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal
    fixed_cost: Decimal
    currency: str
    effective_at: datetime

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Pricing":
        value = require_mapping(payload, "pricing")
        unknown = sorted(
            set(value)
            - {"input_per_million", "cached_input_per_million", "output_per_million", "fixed_cost", "currency", "effective_at"}
        )
        if unknown:
            raise ContractError("unknown_pricing_field", "unknown pricing field(s): " + ", ".join(unknown))
        currency = require_string(value.get("currency"), "pricing.currency").upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ContractError("invalid_currency", "pricing.currency must be a three-letter code")
        return cls(
            input_per_million=decimal_value(value.get("input_per_million"), "pricing.input_per_million", minimum=Decimal("0")),
            cached_input_per_million=decimal_value(value.get("cached_input_per_million"), "pricing.cached_input_per_million", minimum=Decimal("0")),
            output_per_million=decimal_value(value.get("output_per_million"), "pricing.output_per_million", minimum=Decimal("0")),
            fixed_cost=decimal_value(value.get("fixed_cost", "0"), "pricing.fixed_cost", minimum=Decimal("0")),
            currency=currency,
            effective_at=parse_timestamp(value.get("effective_at"), "pricing.effective_at"),
        )


@dataclass(frozen=True, slots=True)
class ModelProfile:
    alias: str
    provider: str | None
    provider_model_id: str | None
    deployment_id: str | None
    model_revision: str | None
    enabled: bool
    available: bool | None
    capability_tier: ModelTier | None
    pricing: Pricing | None
    context_tokens: int | None
    max_output_tokens: int | None
    concurrency: int | None
    active_calls: int | None
    quota_remaining: int | None
    allowed_residencies: frozenset[str]
    allowed_privacy_classes: frozenset[str]
    private_repository_allowed: bool | None
    tools: frozenset[str] = field(default_factory=frozenset)
    predicted_success: Decimal | None = None
    predicted_quality: Decimal | None = None
    cache_affinity: Decimal | None = None
    latency_ms: Decimal | None = None
    integration_risk_cost: Decimal = Decimal("0")

    @classmethod
    def from_payload(cls, alias: str, payload: Mapping[str, Any]) -> "ModelProfile":
        if alias not in MODEL_ALIAS_SET:
            raise ContractError("unknown_model_alias", f"unknown model alias: {alias}")
        value = require_mapping(payload, f"aliases.{alias}")
        allowed = {
            "provider",
            "provider_model_id",
            "deployment_id",
            "model_revision",
            "enabled",
            "available",
            "capability_tier",
            "pricing",
            "limits",
            "active_calls",
            "quota_remaining",
            "allowed_residencies",
            "allowed_privacy_classes",
            "private_repository_allowed",
            "tools",
            "predicted_success",
            "predicted_quality",
            "cache_affinity",
            "latency_ms",
            "integration_risk_cost",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ContractError("unknown_model_profile_field", f"{alias} has unknown field(s): " + ", ".join(unknown))
        enabled = value.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ContractError("invalid_enabled", f"{alias}.enabled must be boolean")
        available = value.get("available")
        if available is not None and not isinstance(available, bool):
            raise ContractError("invalid_availability", f"{alias}.available must be boolean or null")
        provider = value.get("provider")
        provider_id = value.get("provider_model_id")
        deployment_id = value.get("deployment_id")
        model_revision = value.get("model_revision")
        provider = provider.strip() if isinstance(provider, str) and provider.strip() else None
        provider_id = provider_id.strip() if isinstance(provider_id, str) and provider_id.strip() else None
        deployment_id = deployment_id.strip() if isinstance(deployment_id, str) and deployment_id.strip() else None
        model_revision = model_revision.strip() if isinstance(model_revision, str) and model_revision.strip() else None
        pricing_value = value.get("pricing")
        pricing: Pricing | None
        pricing_required = (
            "input_per_million",
            "cached_input_per_million",
            "output_per_million",
            "currency",
            "effective_at",
        )
        if isinstance(pricing_value, Mapping) and all(pricing_value.get(key) is not None for key in pricing_required):
            pricing = Pricing.from_payload(pricing_value)
        else:
            pricing = None
        limits = value.get("limits")
        limits = limits if isinstance(limits, Mapping) else {}
        unknown_limits = sorted(set(limits) - {"context_tokens", "max_output_tokens", "concurrency"})
        if unknown_limits:
            raise ContractError("unknown_model_limit", f"{alias} has unknown limit(s): " + ", ".join(unknown_limits))

        def optional_int(key: str) -> int | None:
            item = limits.get(key)
            return None if item is None else integer_value(item, f"{alias}.limits.{key}", minimum=1)

        tier_value = value.get("capability_tier")
        tier = None if tier_value is None else ModelTier.parse(tier_value)
        tools_value = value.get("tools", [])
        tools = frozenset(require_string_sequence(tools_value, f"{alias}.tools"))
        residencies = frozenset(
            item.upper() for item in require_string_sequence(value.get("allowed_residencies", []), f"{alias}.allowed_residencies")
        )
        privacy_classes = frozenset(
            item.casefold() for item in require_string_sequence(value.get("allowed_privacy_classes", []), f"{alias}.allowed_privacy_classes")
        )
        private_allowed = value.get("private_repository_allowed")
        if private_allowed is not None and not isinstance(private_allowed, bool):
            raise ContractError("invalid_private_repo_policy", f"{alias}.private_repository_allowed must be boolean or null")
        active_value = value.get("active_calls")
        quota_value = value.get("quota_remaining")
        success_value = value.get("predicted_success")
        quality_value = value.get("predicted_quality")
        cache_affinity_value = value.get("cache_affinity")
        latency_value = value.get("latency_ms")
        integration_value = value.get("integration_risk_cost", "0")
        return cls(
            alias=alias,
            provider=provider,
            provider_model_id=provider_id,
            deployment_id=deployment_id,
            model_revision=model_revision,
            enabled=enabled,
            available=available,
            capability_tier=tier,
            pricing=pricing,
            context_tokens=optional_int("context_tokens"),
            max_output_tokens=optional_int("max_output_tokens"),
            concurrency=optional_int("concurrency"),
            active_calls=None if active_value is None else integer_value(active_value, f"{alias}.active_calls"),
            quota_remaining=None if quota_value is None else integer_value(quota_value, f"{alias}.quota_remaining"),
            allowed_residencies=residencies,
            allowed_privacy_classes=privacy_classes,
            private_repository_allowed=private_allowed,
            tools=tools,
            predicted_success=None if success_value is None else finite_probability(success_value, f"{alias}.predicted_success"),
            predicted_quality=None if quality_value is None else finite_probability(quality_value, f"{alias}.predicted_quality"),
            cache_affinity=None if cache_affinity_value is None else finite_probability(cache_affinity_value, f"{alias}.cache_affinity"),
            latency_ms=None if latency_value is None else decimal_value(latency_value, f"{alias}.latency_ms", minimum=Decimal("0.000001")),
            integration_risk_cost=decimal_value(integration_value, f"{alias}.integration_risk_cost", minimum=Decimal("0")),
        )

    def configuration_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        if not self.enabled:
            issues.append("model_disabled")
        if self.available is not True:
            issues.append("availability_unknown" if self.available is None else "model_unavailable")
        if not self.provider:
            issues.append("provider_missing")
        if not self.provider_model_id or self.provider_model_id.upper() == "SET_ME":
            issues.append("provider_model_id_unconfigured")
        if not self.deployment_id:
            issues.append("deployment_id_unconfigured")
        if not self.model_revision:
            issues.append("model_revision_unconfigured")
        if self.pricing is None:
            issues.append("pricing_unconfigured")
        if self.capability_tier is None:
            issues.append("capability_tier_unconfigured")
        if self.context_tokens is None:
            issues.append("context_limit_unconfigured")
        if self.max_output_tokens is None:
            issues.append("output_limit_unconfigured")
        if self.concurrency is None:
            issues.append("concurrency_unconfigured")
        if self.active_calls is None:
            issues.append("active_calls_unconfigured")
        if self.quota_remaining is None:
            issues.append("quota_unconfigured")
        if not self.allowed_residencies:
            issues.append("residency_policy_unconfigured")
        if not self.allowed_privacy_classes:
            issues.append("privacy_policy_unconfigured")
        if self.private_repository_allowed is None:
            issues.append("private_repository_policy_unconfigured")
        if self.predicted_success is None:
            issues.append("success_probability_unconfigured")
        if self.predicted_quality is None:
            issues.append("quality_unconfigured")
        if self.cache_affinity is None:
            issues.append("cache_affinity_unconfigured")
        if self.latency_ms is None:
            issues.append("latency_unconfigured")
        return tuple(issues)


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    models: Mapping[str, ModelProfile]
    observed_at: datetime | None
    max_age_seconds: int
    source: str
    authorization_id: str
    digest: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RegistrySnapshot":
        value = require_mapping(payload, "registry")
        unknown = sorted(set(value) - {"aliases", "observed_at", "max_age_seconds", "source", "authorization_id"})
        if unknown:
            raise ContractError("unknown_registry_field", "unknown registry field(s): " + ", ".join(unknown))
        aliases = require_mapping(value.get("aliases"), "registry.aliases")
        actual = set(aliases)
        if actual != MODEL_ALIAS_SET:
            missing = sorted(MODEL_ALIAS_SET - actual)
            extra = sorted(actual - MODEL_ALIAS_SET)
            raise ContractError("allowlist_mismatch", f"registry aliases mismatch; missing={missing}, extra={extra}")
        models = {alias: ModelProfile.from_payload(alias, aliases[alias]) for alias in MODEL_ALIASES}
        observed_value = value.get("observed_at")
        observed = None if observed_value is None else parse_timestamp(observed_value, "registry.observed_at")
        max_age = integer_value(value.get("max_age_seconds", 86400), "registry.max_age_seconds", minimum=1)
        source = require_string(value.get("source"), "registry.source")
        if source not in {"operator_registry", "control_plane_snapshot", "test_fixture"}:
            raise ContractError("invalid_registry_source", "registry.source is not an approved trusted source class")
        authorization_id = require_string(value.get("authorization_id"), "registry.authorization_id")
        canonical = {
            "aliases": aliases,
            "observed_at": observed_value,
            "max_age_seconds": max_age,
            "source": source,
            "authorization_id": authorization_id,
        }
        return cls(
            models=models,
            observed_at=observed,
            max_age_seconds=max_age,
            source=source,
            authorization_id=authorization_id,
            digest=sha256_payload(canonical),
        )

    def is_stale(self, now: datetime | None = None) -> bool:
        if self.observed_at is None:
            return True
        current = now or utc_now()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ContractError("naive_timestamp", "registry comparison time must be timezone-aware")
        current = current.astimezone(self.observed_at.tzinfo)
        return current - self.observed_at > timedelta(seconds=self.max_age_seconds) or self.observed_at > current


@dataclass(frozen=True, slots=True)
class TaskRisk:
    security: RiskLevel = RiskLevel.LOW
    data_migration: RiskLevel = RiskLevel.LOW
    concurrency: RiskLevel = RiskLevel.LOW
    public_contract: RiskLevel = RiskLevel.LOW
    blast_radius: RiskLevel = RiskLevel.LOW

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "TaskRisk":
        value = {} if payload is None else require_mapping(payload, "task.risk")
        allowed = {"security", "data_migration", "concurrency", "public_contract", "blast_radius"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ContractError("unknown_risk_field", "unknown risk field(s): " + ", ".join(unknown))
        return cls(**{key: RiskLevel.parse(value.get(key, "low"), f"risk.{key}") for key in allowed})

    def minimum_tier(self, *, long_horizon: bool = False) -> ModelTier:
        if long_horizon:
            return ModelTier.L4
        high_domains = (self.security, self.data_migration, self.concurrency, self.public_contract)
        if any(value >= RiskLevel.HIGH for value in high_domains) or self.blast_radius >= RiskLevel.CRITICAL:
            return ModelTier.L3
        if self.blast_radius >= RiskLevel.HIGH or any(value >= RiskLevel.MEDIUM for value in high_domains):
            return ModelTier.L2
        return ModelTier.L0


@dataclass(frozen=True, slots=True)
class RoutingTaskProfile:
    task_id: str
    task_class: str
    prompt_tokens: int
    cached_input_tokens: int
    output_tokens: int
    required_tools: frozenset[str]
    residency: str
    privacy_class: str
    private_repository: bool
    risk: TaskRisk
    long_horizon: bool
    minimum_quality: Decimal
    expected_escalation_cost: Decimal
    retry_penalty: Decimal
    task_budget_remaining: Decimal
    run_budget_remaining: Decimal

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RoutingTaskProfile":
        value = require_mapping(payload, "task_profile")
        allowed = {
            "task_id",
            "task_class",
            "prompt_tokens",
            "cached_input_tokens",
            "output_tokens",
            "required_tools",
            "residency",
            "privacy_class",
            "private_repository",
            "risk",
            "long_horizon",
            "minimum_quality",
            "expected_escalation_cost",
            "retry_penalty",
            "task_budget_remaining",
            "run_budget_remaining",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ContractError("unknown_task_profile_field", "unknown task profile field(s): " + ", ".join(unknown))
        prompt = integer_value(value.get("prompt_tokens"), "task_profile.prompt_tokens")
        cached = integer_value(value.get("cached_input_tokens", 0), "task_profile.cached_input_tokens")
        if cached > prompt:
            raise ContractError("invalid_cached_tokens", "cached_input_tokens cannot exceed prompt_tokens")
        long_horizon = value.get("long_horizon", False)
        if not isinstance(long_horizon, bool):
            raise ContractError("invalid_long_horizon", "long_horizon must be boolean")
        return cls(
            task_id=require_string(value.get("task_id"), "task_profile.task_id"),
            task_class=require_string(value.get("task_class", "standard"), "task_profile.task_class"),
            prompt_tokens=prompt,
            cached_input_tokens=cached,
            output_tokens=integer_value(value.get("output_tokens"), "task_profile.output_tokens"),
            required_tools=frozenset(require_string_sequence(value.get("required_tools", []), "task_profile.required_tools")),
            residency=require_string(value.get("residency"), "task_profile.residency").upper(),
            privacy_class=require_string(value.get("privacy_class"), "task_profile.privacy_class").casefold(),
            private_repository=_boolean(value.get("private_repository"), "task_profile.private_repository"),
            risk=TaskRisk.from_payload(value.get("risk")),
            long_horizon=long_horizon,
            minimum_quality=finite_probability(value.get("minimum_quality", "0"), "task_profile.minimum_quality"),
            expected_escalation_cost=decimal_value(value.get("expected_escalation_cost", "0"), "task_profile.expected_escalation_cost", minimum=Decimal("0")),
            retry_penalty=decimal_value(value.get("retry_penalty", "0"), "task_profile.retry_penalty", minimum=Decimal("0")),
            task_budget_remaining=decimal_value(value.get("task_budget_remaining"), "task_profile.task_budget_remaining", minimum=Decimal("0")),
            run_budget_remaining=decimal_value(value.get("run_budget_remaining"), "task_profile.run_budget_remaining", minimum=Decimal("0")),
        )


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError("invalid_boolean", f"{field_name} must be boolean")
    return value
