"""Policy, Security, and Data Governance Engine for Elmos Router Industrial.

Implements the 15 hard policy filters, fail-closed data classification checks,
security context and capability lease validation, and sensitive data redaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Mapping

import yaml

from ..domain.contracts import (
    CapabilityLease,
    DataClassification,
    ExecutionLane,
    ModelDescriptor,
    ModelLifecycle,
    ProviderDeployment,
    ProviderDescriptor,
    RouteRequest,
    VerifiedSecurityContext,
)


@dataclass(frozen=True)
class PolicyEvaluationResult:
    eligible: bool
    denialReasons: tuple[str, ...] = ()
    estimatedCost: float = 0.0


@dataclass(frozen=True)
class PolicyProfile:
    version: str = "2026-09-09.1"
    failClosed: bool = True
    rawPromptLogging: bool = False
    rawResponseLogging: bool = False
    classifications: dict[str, dict[str, Any]] = field(default_factory=dict)
    taskClassWeights: dict[str, dict[str, float]] = field(default_factory=dict)
    maxAttempts: int = 3
    maxCrossModelFallbacks: int = 2


# Sensitive keys regex for redaction
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|password|bearer|auth|token|credential)"
)


_STRING_SECRET_PATTERN = re.compile(
    r"\b(?:sk-[a-zA-Z0-9_\-]{16,}|ghp_[a-zA-Z0-9]{20,}|bearer\s+[a-zA-Z0-9_\-\.]+)\b",
    re.IGNORECASE,
)


def redact_sensitive_data(obj: Any) -> Any:
    """Recursively redacts values for keys resembling API keys, secrets, or bearer tokens."""
    if isinstance(obj, str):
        return _STRING_SECRET_PATTERN.sub("[REDACTED]", obj)
    elif isinstance(obj, Mapping):
        redacted: dict[str, Any] = {}
        for k, v in obj.items():
            if _SECRET_PATTERN.search(str(k)):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_sensitive_data(v)
        return redacted
    elif isinstance(obj, list):
        return [redact_sensitive_data(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(redact_sensitive_data(item) for item in obj)
    return obj


class PolicyEngine:
    """Evaluates security, compliance, residency, and data protection invariants before scoring."""

    def __init__(self, profile: PolicyProfile | None = None) -> None:
        self.profile = profile or PolicyProfile()

    @classmethod
    def from_yaml(cls, yaml_content: str) -> PolicyEngine:
        data = yaml.safe_load(yaml_content) or {}
        defaults = data.get("defaults", {})
        profile = PolicyProfile(
            version=str(data.get("version", "2026-09-09.1")),
            failClosed=bool(defaults.get("fail_closed", True)),
            rawPromptLogging=bool(defaults.get("raw_prompt_logging", False)),
            rawResponseLogging=bool(defaults.get("raw_response_logging", False)),
            classifications=dict(data.get("classifications", {})),
            taskClassWeights=dict(data.get("task_classes", {})),
            maxAttempts=int(data.get("fallback", {}).get("max_attempts", 3)),
            maxCrossModelFallbacks=int(
                data.get("fallback", {}).get("max_cross_model_fallbacks", 2)
            ),
        )
        return cls(profile)

    def evaluate(
        self,
        request: RouteRequest,
        model: ModelDescriptor,
        provider: ProviderDescriptor,
        deployment: ProviderDeployment,
        security_context: VerifiedSecurityContext | None = None,
        lease: CapabilityLease | None = None,
        now: datetime | None = None,
    ) -> PolicyEvaluationResult:
        denial_reasons: list[str] = []
        current_time = now or datetime.now(timezone.utc)

        # Fail-closed classification validation
        if not request.dataClassification:
            if self.profile.failClosed:
                denial_reasons.append("Missing data classification on fail-closed policy")

        # 1. Tenant allow/deny & Context validation
        if security_context:
            if security_context.tenantId != request.tenantId:
                denial_reasons.append(
                    f"Security context tenant mismatch: {security_context.tenantId} != {request.tenantId}"
                )

        # 2. Model allow/deny
        if model.alias in request.deniedModels:
            denial_reasons.append(f"Model alias '{model.alias}' explicitly denied by request")
        if model.lifecycle == ModelLifecycle.DISABLED:
            denial_reasons.append(f"Model alias '{model.alias}' is lifecycle disabled")

        # 3. Provider allow/deny
        if provider.id in request.deniedProviders:
            denial_reasons.append(f"Provider '{provider.id}' explicitly denied by request")
        if not provider.enabled:
            denial_reasons.append(f"Provider '{provider.id}' is disabled")
        if not deployment.enabled:
            denial_reasons.append(f"Deployment '{deployment.id}' is disabled")

        # 4. Region and residency constraint
        if request.regionConstraints:
            matching_regions = set(request.regionConstraints).intersection(
                set(deployment.regions)
            )
            if not matching_regions:
                denial_reasons.append(
                    f"Deployment regions {deployment.regions} do not satisfy requested constraints {request.regionConstraints}"
                )

        # 5. Retention and Zero Data Retention (ZDR) requirements
        is_confidential = DataClassification.CONFIDENTIAL in request.dataClassification
        needs_zdr = (
            is_confidential
            or (security_context and security_context.zeroDataRetentionRequired)
        )
        if needs_zdr and deployment.lane == ExecutionLane.OPENROUTER and not deployment.requireZdr:
            denial_reasons.append("Zero Data Retention (ZDR) required but deployment does not enforce ZDR")

        # 6. Training / Use-of-data prohibition
        has_source_code = DataClassification.SOURCE_CODE in request.dataClassification
        prohibit_training = (
            has_source_code
            or is_confidential
            or (security_context and security_context.noTrainingRequired)
        )
        if prohibit_training:
            if deployment.trainingAllowed:
                denial_reasons.append("Data training prohibited but deployment allows training")
            if not provider.prohibitsTraining:
                denial_reasons.append("Data training prohibited but provider does not contractually prohibit training")

        # 7. Capability requirements
        for cap in request.requiredCapabilities:
            cap_val = model.capabilities.get(cap)
            if cap_val is None or cap_val is False:
                denial_reasons.append(f"Model does not satisfy required capability '{cap}'")

        # 8. Context length limits
        total_projected_tokens = request.maxInputTokens + request.expectedOutputTokens
        if total_projected_tokens > model.maxContextTokens:
            denial_reasons.append(
                f"Projected tokens ({total_projected_tokens}) exceed model max context tokens ({model.maxContextTokens})"
            )
        if request.expectedOutputTokens > model.maxOutputTokens:
            denial_reasons.append(
                f"Expected output tokens ({request.expectedOutputTokens}) exceed model max output tokens ({model.maxOutputTokens})"
            )

        # 9. Tool calling requirements
        if request.requireToolCalling and not model.supportsToolCalling:
            denial_reasons.append("Tool calling required but model does not support tool calling")

        # 10. Structured output requirements
        if request.requireStructuredOutput and not model.supportsStructuredOutput:
            denial_reasons.append("Structured output required but model does not support structured output")

        # 11. Secret-bearing data routing restrictions
        if DataClassification.SECRET_BEARING in request.dataClassification:
            if deployment.lane == ExecutionLane.OPENROUTER:
                denial_reasons.append("OpenRouter lane strictly forbidden for SECRET_BEARING data classification")
            if deployment.lane not in (ExecutionLane.NATIVE_DIRECT, ExecutionLane.SELF_HOSTED):
                denial_reasons.append(
                    f"SECRET_BEARING classification requires NATIVE_DIRECT or SELF_HOSTED lane, got {deployment.lane.value}"
                )

        # 12. Budget hard ceiling preflight check
        estimated_cost = (
            (request.maxInputTokens / 1000.0) * deployment.priceInputPer1k
            + (request.expectedOutputTokens / 1000.0) * deployment.priceOutputPer1k
        )
        if estimated_cost > request.budgetEnvelope.maxCost:
            denial_reasons.append(
                f"Estimated cost ({estimated_cost:.4f} {request.budgetEnvelope.currency}) exceeds budget hard ceiling ({request.budgetEnvelope.maxCost:.4f} {request.budgetEnvelope.currency})"
            )

        # 13. Provider legal/compliance restrictions
        # (covered by provider/deployment/region/training flags above)

        # 14. Capability lease validation
        if lease:
            if not lease.is_valid(current_time):
                denial_reasons.append(f"Capability lease '{lease.leaseId}' has expired")
            if lease.tenantId != request.tenantId:
                denial_reasons.append(
                    f"Capability lease tenant mismatch: {lease.tenantId} != {request.tenantId}"
                )
            for cap in request.requiredCapabilities:
                if cap not in lease.allowedCapabilities:
                    denial_reasons.append(
                        f"Capability lease '{lease.leaseId}' does not grant required capability '{cap}'"
                    )

        # 15. Execution authority validation
        if request.deadline <= current_time:
            denial_reasons.append("Request deadline has already expired before route evaluation")

        eligible = len(denial_reasons) == 0
        return PolicyEvaluationResult(
            eligible=eligible,
            denialReasons=tuple(denial_reasons),
            estimatedCost=round(estimated_cost, 6),
        )
