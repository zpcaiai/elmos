"""Deterministic, fail-closed model eligibility and routing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable

from .catalog import MODEL_ALIASES
from .contracts import ContractError, FallbackPolicy, ModelMode, OptimizationProfile, Status, utc_now
from .models import ModelProfile, RegistrySnapshot, ResolvedModelSelection, RoutingTaskProfile


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    alias: str
    eligible: bool
    rejection_reasons: tuple[str, ...]
    invocation_cost: Decimal | None = None
    expected_total_cost: Decimal | None = None
    route_score: Decimal | None = None
    predicted_quality: Decimal | None = None
    predicted_success: Decimal | None = None
    cache_affinity: Decimal | None = None
    latency_ms: Decimal | None = None
    provider: str | None = None
    provider_model_id: str | None = None
    deployment_id: str | None = None
    model_revision: str | None = None
    currency: str | None = None

    def to_dict(self) -> dict[str, Any]:
        def money(value: Decimal | None) -> str | None:
            return None if value is None else format(value, "f")

        return {
            "alias": self.alias,
            "eligible": self.eligible,
            "rejection_reasons": list(self.rejection_reasons),
            "invocation_cost": money(self.invocation_cost),
            "expected_total_cost": money(self.expected_total_cost),
            "route_score": money(self.route_score),
            "predicted_quality": money(self.predicted_quality),
            "predicted_success": money(self.predicted_success),
            "cache_affinity": money(self.cache_affinity),
            "latency_ms": money(self.latency_ms),
            "provider": self.provider,
            "provider_model_id": self.provider_model_id,
            "deployment_id": self.deployment_id,
            "model_revision": self.model_revision,
            "currency": self.currency,
        }


@dataclass(frozen=True, slots=True)
class RouteDecision:
    status: Status
    chosen_model: str | None
    runner_up: str | None
    candidates: tuple[CandidateDecision, ...]
    reason: str
    registry_digest: str
    selection_mode: str
    optimization_profile: str
    currency: str
    registry_source: str
    registry_authorization_id: str
    fallback_from_model: str | None = None
    chosen_provider: str | None = None
    chosen_provider_model_id: str | None = None
    chosen_deployment_id: str | None = None
    chosen_model_revision: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "chosen_model": self.chosen_model,
            "runner_up": self.runner_up,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "reason": self.reason,
            "registry_digest": self.registry_digest,
            "selection_mode": self.selection_mode,
            "optimization_profile": self.optimization_profile,
            "currency": self.currency,
            "registry_source": self.registry_source,
            "registry_authorization_id": self.registry_authorization_id,
            "fallback_from_model": self.fallback_from_model,
            "chosen_provider": self.chosen_provider,
            "chosen_provider_model_id": self.chosen_provider_model_id,
            "chosen_deployment_id": self.chosen_deployment_id,
            "chosen_model_revision": self.chosen_model_revision,
            "provider_execution": Status.NOT_RUN.value,
            "planning_only": True,
            "certification": Status.NOT_CERTIFIED.value,
        }


def _candidate(
    model: ModelProfile,
    task: RoutingTaskProfile,
    registry: RegistrySnapshot,
    *,
    currency: str,
    now: datetime,
    excluded: frozenset[str],
) -> CandidateDecision:
    reasons = list(model.configuration_issues())
    if model.alias in excluded:
        reasons.append("model_excluded")
    if registry.observed_at is None:
        reasons.append("registry_observed_at_missing")
    elif registry.is_stale(now):
        reasons.append("registry_stale")
    minimum_tier = task.risk.minimum_tier(long_horizon=task.long_horizon)
    if model.capability_tier is not None and model.capability_tier < minimum_tier:
        reasons.append(f"risk_floor_requires_{minimum_tier.name}")
    if model.context_tokens is not None and task.prompt_tokens + task.output_tokens > model.context_tokens:
        reasons.append("context_limit_exceeded")
    if model.max_output_tokens is not None and task.output_tokens > model.max_output_tokens:
        reasons.append("output_limit_exceeded")
    unsupported = sorted(task.required_tools - model.tools)
    if unsupported:
        reasons.append("unsupported_tools:" + ",".join(unsupported))
    if task.residency not in model.allowed_residencies:
        reasons.append("residency_not_allowed")
    if task.privacy_class not in model.allowed_privacy_classes:
        reasons.append("privacy_class_not_allowed")
    if task.private_repository and model.private_repository_allowed is not True:
        reasons.append("private_repository_not_allowed")
    if model.quota_remaining is not None and model.quota_remaining < 1:
        reasons.append("quota_exhausted")
    if model.concurrency is not None and model.active_calls is not None and model.active_calls >= model.concurrency:
        reasons.append("concurrency_capacity_exhausted")
    if model.predicted_quality is not None and model.predicted_quality < task.minimum_quality:
        reasons.append("quality_floor_not_met")
    if model.predicted_success is not None and model.predicted_success <= 0:
        reasons.append("zero_success_probability")
    pricing = model.pricing
    if pricing is not None:
        if pricing.currency != currency:
            reasons.append("currency_mismatch")
        if pricing.effective_at > now:
            reasons.append("pricing_from_future")
        elif now - pricing.effective_at > timedelta(seconds=registry.max_age_seconds):
            reasons.append("pricing_stale")
    if reasons:
        return CandidateDecision(
            alias=model.alias,
            eligible=False,
            rejection_reasons=tuple(sorted(set(reasons))),
            predicted_quality=model.predicted_quality,
            predicted_success=model.predicted_success,
            cache_affinity=model.cache_affinity,
            latency_ms=model.latency_ms,
            provider=model.provider,
            provider_model_id=model.provider_model_id,
            deployment_id=model.deployment_id,
            model_revision=model.model_revision,
            currency=pricing.currency if pricing is not None else None,
        )

    assert pricing is not None
    assert model.predicted_success is not None
    assert model.predicted_quality is not None
    assert model.cache_affinity is not None
    assert model.latency_ms is not None
    uncached = task.prompt_tokens - task.cached_input_tokens
    invocation = (
        Decimal(uncached) * pricing.input_per_million
        + Decimal(task.cached_input_tokens) * pricing.cached_input_per_million
        + Decimal(task.output_tokens) * pricing.output_per_million
    ) / Decimal(1_000_000) + pricing.fixed_cost
    expected = (
        invocation
        + (Decimal("1") - model.predicted_success) * task.expected_escalation_cost
        + model.integration_risk_cost
        + task.retry_penalty
    )
    if expected > task.task_budget_remaining:
        reasons.append("task_budget_exceeded")
    if expected > task.run_budget_remaining:
        reasons.append("run_budget_exceeded")
    if reasons:
        return CandidateDecision(
            alias=model.alias,
            eligible=False,
            rejection_reasons=tuple(sorted(set(reasons))),
            invocation_cost=invocation,
            expected_total_cost=expected,
            predicted_quality=model.predicted_quality,
            predicted_success=model.predicted_success,
            cache_affinity=model.cache_affinity,
            latency_ms=model.latency_ms,
            provider=model.provider,
            provider_model_id=model.provider_model_id,
            deployment_id=model.deployment_id,
            model_revision=model.model_revision,
            currency=pricing.currency,
        )
    epsilon = Decimal("0.000000000001")
    latency_factor = max(model.latency_ms / Decimal("1000"), Decimal("1"))
    score = (model.predicted_success * model.predicted_quality * model.cache_affinity) / max(
        expected * latency_factor, epsilon
    )
    return CandidateDecision(
        alias=model.alias,
        eligible=True,
        rejection_reasons=(),
        invocation_cost=invocation,
        expected_total_cost=expected,
        route_score=score,
        predicted_quality=model.predicted_quality,
        predicted_success=model.predicted_success,
        cache_affinity=model.cache_affinity,
        latency_ms=model.latency_ms,
        provider=model.provider,
        provider_model_id=model.provider_model_id,
        deployment_id=model.deployment_id,
        model_revision=model.model_revision,
        currency=pricing.currency,
    )


def _rank(candidates: Iterable[CandidateDecision], profile: OptimizationProfile) -> list[CandidateDecision]:
    eligible = [candidate for candidate in candidates if candidate.eligible]
    if profile is OptimizationProfile.COST_PERFORMANCE:
        return sorted(eligible, key=lambda item: (-item.route_score, item.expected_total_cost, item.alias))  # type: ignore[operator]
    if profile is OptimizationProfile.LOWEST_COST:
        return sorted(eligible, key=lambda item: (item.invocation_cost, item.expected_total_cost, -item.predicted_quality, item.alias))  # type: ignore[operator]
    if profile is OptimizationProfile.MAX_QUALITY:
        return sorted(eligible, key=lambda item: (-item.predicted_quality, item.expected_total_cost, item.latency_ms, item.alias))  # type: ignore[operator]
    return sorted(eligible, key=lambda item: (item.latency_ms, item.expected_total_cost, -item.predicted_quality, item.alias))  # type: ignore[operator]


def route_model(
    task: RoutingTaskProfile,
    selection: ResolvedModelSelection,
    registry: RegistrySnapshot,
    *,
    currency: str = "USD",
    now: datetime | None = None,
    fallback_from_model: str | None = None,
    failure_class: str | None = None,
    excluded_models: Iterable[str] = (),
) -> RouteDecision:
    current = now or utc_now()
    if current.tzinfo is None or current.utcoffset() is None:
        raise ContractError("naive_timestamp", "routing time must be timezone-aware")
    current = current.astimezone(timezone.utc)
    if not isinstance(currency, str) or len(currency.strip()) != 3 or not currency.strip().isalpha():
        raise ContractError("invalid_currency", "routing currency must be a three-letter code")
    currency = currency.strip().upper()
    if selection.registry_digest != registry.digest:
        raise ContractError("selection_registry_mismatch", "resolved selection is not bound to this trusted registry snapshot")
    if fallback_from_model is not None and fallback_from_model not in registry.models:
        raise ContractError("unknown_model_alias", "fallback_from_model is not in the exact allowlist")
    excluded = frozenset(excluded_models)
    unknown_exclusions = sorted(excluded - set(registry.models))
    if unknown_exclusions:
        raise ContractError("unknown_model_alias", "excluded_models contains unknown aliases: " + ", ".join(unknown_exclusions))
    if fallback_from_model:
        excluded = excluded | {fallback_from_model}
    candidates = tuple(
        _candidate(registry.models[alias], task, registry, currency=currency, now=current, excluded=excluded)
        for alias in MODEL_ALIASES
    )

    if selection.mode is ModelMode.MANUAL and fallback_from_model is None:
        assert selection.selected_model is not None
        selected = next(item for item in candidates if item.alias == selection.selected_model)
        if selected.eligible:
            return RouteDecision(
                status=Status.PLANNED,
                chosen_model=selected.alias,
                runner_up=None,
                candidates=candidates,
                reason="manual_primary_locked",
                registry_digest=registry.digest,
                selection_mode=selection.mode.value,
                optimization_profile=selection.optimization_profile.value,
                currency=currency,
                registry_source=registry.source,
                registry_authorization_id=registry.authorization_id,
                chosen_provider=selected.provider,
                chosen_provider_model_id=selected.provider_model_id,
                chosen_deployment_id=selected.deployment_id,
                chosen_model_revision=selected.model_revision,
            )
        unconfigured = any(reason.endswith("unconfigured") or reason.endswith("missing") for reason in selected.rejection_reasons)
        return RouteDecision(
            status=Status.NOT_CONFIGURED if unconfigured else Status.BLOCKED,
            chosen_model=None,
            runner_up=None,
            candidates=candidates,
            reason="manual_model_ineligible:" + ",".join(selected.rejection_reasons),
            registry_digest=registry.digest,
            selection_mode=selection.mode.value,
            optimization_profile=selection.optimization_profile.value,
            currency=currency,
            registry_source=registry.source,
            registry_authorization_id=registry.authorization_id,
        )

    if fallback_from_model is not None:
        if selection.mode is ModelMode.MANUAL and selection.fallback_policy is FallbackPolicy.STRICT:
            return RouteDecision(
                status=Status.BLOCKED,
                chosen_model=None,
                runner_up=None,
                candidates=candidates,
                reason="model_reselection_required",
                registry_digest=registry.digest,
                selection_mode=selection.mode.value,
                optimization_profile=selection.optimization_profile.value,
                currency=currency,
                registry_source=registry.source,
                registry_authorization_id=registry.authorization_id,
                fallback_from_model=fallback_from_model,
            )
        if not failure_class:
            return RouteDecision(
                status=Status.BLOCKED,
                chosen_model=None,
                runner_up=None,
                candidates=candidates,
                reason="classified_failure_required_for_fallback",
                registry_digest=registry.digest,
                selection_mode=selection.mode.value,
                optimization_profile=selection.optimization_profile.value,
                currency=currency,
                registry_source=registry.source,
                registry_authorization_id=registry.authorization_id,
                fallback_from_model=fallback_from_model,
            )

    ranked = _rank(candidates, selection.optimization_profile)
    if not ranked:
        configured = any(not model.configuration_issues() for model in registry.models.values())
        return RouteDecision(
            status=Status.BLOCKED if configured else Status.NOT_CONFIGURED,
            chosen_model=None,
            runner_up=None,
            candidates=candidates,
            reason="no_eligible_model",
            registry_digest=registry.digest,
            selection_mode=selection.mode.value,
            optimization_profile=selection.optimization_profile.value,
            currency=currency,
            registry_source=registry.source,
            registry_authorization_id=registry.authorization_id,
            fallback_from_model=fallback_from_model,
        )
    return RouteDecision(
        status=Status.PLANNED,
        chosen_model=ranked[0].alias,
        runner_up=ranked[1].alias if len(ranked) > 1 else None,
        candidates=candidates,
        reason="smart_fallback" if fallback_from_model else "smart_ranked",
        registry_digest=registry.digest,
        selection_mode=selection.mode.value,
        optimization_profile=selection.optimization_profile.value,
        currency=currency,
        registry_source=registry.source,
        registry_authorization_id=registry.authorization_id,
        fallback_from_model=fallback_from_model,
        chosen_provider=ranked[0].provider,
        chosen_provider_model_id=ranked[0].provider_model_id,
        chosen_deployment_id=ranked[0].deployment_id,
        chosen_model_revision=ranked[0].model_revision,
    )
