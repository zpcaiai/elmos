"""Domain contracts for Elmos Router Industrial.

Defines provider-neutral, strongly typed, durable domain models for route requests,
model execution plans, route decisions, registry descriptors, and inference payloads.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Mapping, Sequence

import jsonschema


class ExecutionLane(str, Enum):
    NATIVE_DIRECT = "NATIVE_DIRECT"
    LITELLM = "LITELLM"
    OPENROUTER = "OPENROUTER"
    SELF_HOSTED = "SELF_HOSTED"


class TaskClass(str, Enum):
    REPO_ANALYSIS = "REPO_ANALYSIS"
    ARCHITECTURE_REASONING = "ARCHITECTURE_REASONING"
    CODE_GENERATION = "CODE_GENERATION"
    LARGE_REFACTOR = "LARGE_REFACTOR"
    MIGRATION_PLANNING = "MIGRATION_PLANNING"
    MIGRATION_EXECUTION = "MIGRATION_EXECUTION"
    TEST_GENERATION = "TEST_GENERATION"
    DEBUGGING = "DEBUGGING"
    SQL_TRANSLATION = "SQL_TRANSLATION"
    FORMAL_VERIFICATION = "FORMAL_VERIFICATION"
    DOCUMENTATION = "DOCUMENTATION"
    CHEAP_CLASSIFICATION = "CHEAP_CLASSIFICATION"
    EMBEDDING = "EMBEDDING"
    RERANKING = "RERANKING"


class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    SOURCE_CODE = "SOURCE_CODE"
    SECRET_BEARING = "SECRET_BEARING"
    PII = "PII"


class ModelLifecycle(str, Enum):
    EXPERIMENTAL = "experimental"
    CANARY = "canary"
    STABLE = "stable"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


@dataclass(frozen=True)
class BudgetEnvelope:
    currency: str
    maxCost: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "maxCost": float(self.maxCost),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BudgetEnvelope:
        return cls(
            currency=str(data["currency"]),
            maxCost=float(data["maxCost"]),
        )


@dataclass(frozen=True)
class VerifiedSecurityContext:
    tenantId: str
    actorId: str
    roles: tuple[str, ...] = ()
    dataClassifications: tuple[DataClassification, ...] = ()
    allowOpenRouter: bool = True
    noTrainingRequired: bool = False
    zeroDataRetentionRequired: bool = False
    regionAllowlist: tuple[str, ...] = ()

    def digest(self) -> str:
        raw = json.dumps(
            {
                "tenantId": self.tenantId,
                "actorId": self.actorId,
                "roles": sorted(self.roles),
                "dataClassifications": [c.value for c in self.dataClassifications],
                "allowOpenRouter": self.allowOpenRouter,
                "noTrainingRequired": self.noTrainingRequired,
                "zeroDataRetentionRequired": self.zeroDataRetentionRequired,
                "regionAllowlist": sorted(self.regionAllowlist),
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CapabilityLease:
    leaseId: str
    tenantId: str
    expiresAt: datetime
    allowedCapabilities: tuple[str, ...]
    maxTokenBudget: int = 1_000_000

    def digest(self) -> str:
        raw = json.dumps(
            {
                "leaseId": self.leaseId,
                "tenantId": self.tenantId,
                "expiresAt": self.expiresAt.isoformat(),
                "allowedCapabilities": sorted(self.allowedCapabilities),
                "maxTokenBudget": self.maxTokenBudget,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def is_valid(self, now: datetime | None = None) -> bool:
        check_time = now or datetime.now(timezone.utc)
        return self.expiresAt > check_time


@dataclass(frozen=True)
class InferenceMessage:
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: str | None = None
    toolCallId: str | None = None
    toolCalls: tuple[dict[str, Any], ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name is not None:
            d["name"] = self.name
        if self.toolCallId is not None:
            d["toolCallId"] = self.toolCallId
        if self.toolCalls is not None:
            d["toolCalls"] = list(self.toolCalls)
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> InferenceMessage:
        t_calls = data.get("toolCalls")
        return cls(
            role=str(data["role"]),
            content=str(data.get("content", "")),
            name=data.get("name"),
            toolCallId=data.get("toolCallId"),
            toolCalls=tuple(t_calls) if t_calls else None,
        )

@dataclass(frozen=True)
class InferenceRequest:
    messages: tuple[InferenceMessage, ...]
    maxTokens: int = 1024
    temperature: float = 0.0
    tools: tuple[dict[str, Any], ...] = ()
    responseSchema: dict[str, Any] | None = None


@dataclass(frozen=True)
class RouteRequest:
    tenantId: str
    taskId: str
    stepId: str
    attemptId: str
    taskClass: TaskClass
    dataClassification: tuple[DataClassification, ...]
    securityContextRef: str
    capabilityLeaseRef: str
    budgetEnvelope: BudgetEnvelope
    deadline: datetime
    idempotencyKey: str
    requiredCapabilities: tuple[str, ...] = ()
    preferredCapabilities: tuple[str, ...] = ()
    maxInputTokens: int = 4096
    expectedOutputTokens: int = 1024
    latencyClass: str = "normal"  # "low", "normal", "batch"
    qualityClass: str = "high"  # "highest", "high", "balanced", "fast"
    regionConstraints: tuple[str, ...] = ()
    requireToolCalling: bool = False
    requireStructuredOutput: bool = False
    preferredModels: tuple[str, ...] = ()
    deniedModels: tuple[str, ...] = ()
    deniedProviders: tuple[str, ...] = ()
    policyVersionPin: str | None = None
    tools: tuple[dict[str, Any], ...] = ()
    responseSchema: dict[str, Any] | None = None
    messages: tuple[InferenceMessage, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenantId": self.tenantId,
            "taskId": self.taskId,
            "stepId": self.stepId,
            "attemptId": self.attemptId,
            "taskClass": self.taskClass.value,
            "dataClassification": [c.value for c in self.dataClassification],
            "securityContextRef": self.securityContextRef,
            "capabilityLeaseRef": self.capabilityLeaseRef,
            "budgetEnvelope": self.budgetEnvelope.to_dict(),
            "deadline": self.deadline.isoformat(),
            "idempotencyKey": self.idempotencyKey,
            "requiredCapabilities": list(self.requiredCapabilities),
            "preferredCapabilities": list(self.preferredCapabilities),
            "maxInputTokens": self.maxInputTokens,
            "expectedOutputTokens": self.expectedOutputTokens,
            "latencyClass": self.latencyClass,
            "qualityClass": self.qualityClass,
            "regionConstraints": list(self.regionConstraints),
            "requireToolCalling": self.requireToolCalling,
            "requireStructuredOutput": self.requireStructuredOutput,
            "preferredModels": list(self.preferredModels),
            "deniedModels": list(self.deniedModels),
            "deniedProviders": list(self.deniedProviders),
            "policyVersionPin": self.policyVersionPin,
            "tools": list(self.tools),
            "responseSchema": self.responseSchema,
            "messages": [m.to_dict() for m in self.messages],
        }


@dataclass(frozen=True)
class ModelExecutionPlan:
    schemaVersion: str
    planId: str
    tenantId: str
    taskId: str
    stepId: str
    modelAlias: str
    deploymentId: str
    lane: ExecutionLane
    providerId: str
    deadlineAt: str
    policyVersion: str
    registryVersion: str
    securityContextHash: str
    capabilityLeaseHash: str
    budget: BudgetEnvelope
    fallbacks: tuple[str, ...] = ()
    modelRevision: str | None = None
    reasoningProfile: str | None = None
    requiredCapabilities: tuple[str, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schemaVersion": self.schemaVersion,
            "planId": self.planId,
            "tenantId": self.tenantId,
            "taskId": self.taskId,
            "stepId": self.stepId,
            "modelAlias": self.modelAlias,
            "deploymentId": self.deploymentId,
            "lane": self.lane.value,
            "providerId": self.providerId,
            "modelRevision": self.modelRevision,
            "reasoningProfile": self.reasoningProfile,
            "deadlineAt": self.deadlineAt,
            "policyVersion": self.policyVersion,
            "registryVersion": self.registryVersion,
            "securityContextHash": self.securityContextHash,
            "capabilityLeaseHash": self.capabilityLeaseHash,
            "budget": self.budget.to_dict(),
            "requiredCapabilities": list(self.requiredCapabilities),
            "fallbacks": list(self.fallbacks),
            "extensions": dict(self.extensions),
        }
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelExecutionPlan:
        return cls(
            schemaVersion=str(data["schemaVersion"]),
            planId=str(data["planId"]),
            tenantId=str(data["tenantId"]),
            taskId=str(data["taskId"]),
            stepId=str(data["stepId"]),
            modelAlias=str(data["modelAlias"]),
            deploymentId=str(data["deploymentId"]),
            lane=ExecutionLane(data["lane"]),
            providerId=str(data["providerId"]),
            deadlineAt=str(data["deadlineAt"]),
            policyVersion=str(data["policyVersion"]),
            registryVersion=str(data["registryVersion"]),
            securityContextHash=str(data["securityContextHash"]),
            capabilityLeaseHash=str(data["capabilityLeaseHash"]),
            budget=BudgetEnvelope.from_dict(data["budget"]),
            fallbacks=tuple(data.get("fallbacks", ())),
            modelRevision=data.get("modelRevision"),
            reasoningProfile=data.get("reasoningProfile"),
            requiredCapabilities=tuple(data.get("requiredCapabilities", ())),
            extensions=dict(data.get("extensions", {})),
        )


@dataclass(frozen=True)
class ScoreBreakdown:
    capabilityFit: float = 0.0
    taskBenchmarkQuality: float = 0.0
    reliabilityHealth: float = 0.0
    expectedLatency: float = 0.0
    estimatedCost: float = 0.0
    cacheAffinity: float = 0.0
    regionAffinity: float = 0.0
    providerDiversity: float = 0.0
    historicalSuccess: float = 0.0
    penalties: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "capabilityFit": self.capabilityFit,
            "taskBenchmarkQuality": self.taskBenchmarkQuality,
            "reliabilityHealth": self.reliabilityHealth,
            "expectedLatency": self.expectedLatency,
            "estimatedCost": self.estimatedCost,
            "cacheAffinity": self.cacheAffinity,
            "regionAffinity": self.regionAffinity,
            "providerDiversity": self.providerDiversity,
            "historicalSuccess": self.historicalSuccess,
            "penalties": self.penalties,
        }


@dataclass(frozen=True)
class CandidateEvaluation:
    deploymentId: str
    eligible: bool
    denialReasons: tuple[str, ...] = ()
    score: float | None = None
    scoreBreakdown: ScoreBreakdown | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "deploymentId": self.deploymentId,
            "eligible": self.eligible,
            "denialReasons": list(self.denialReasons),
            "score": self.score,
        }
        if self.scoreBreakdown:
            d["scoreBreakdown"] = self.scoreBreakdown.to_dict()
        return d


@dataclass(frozen=True)
class RouteDecision:
    schemaVersion: str
    decisionId: str
    selectedDeploymentId: str
    selectedLane: ExecutionLane
    policyVersion: str
    registryVersion: str
    candidates: tuple[CandidateEvaluation, ...]
    fallbackDeploymentIds: tuple[str, ...]
    decidedAt: str
    healthSnapshotVersion: str | None = None
    costSnapshotVersion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schemaVersion,
            "decisionId": self.decisionId,
            "selectedDeploymentId": self.selectedDeploymentId,
            "selectedLane": self.selectedLane.value,
            "policyVersion": self.policyVersion,
            "registryVersion": self.registryVersion,
            "healthSnapshotVersion": self.healthSnapshotVersion,
            "costSnapshotVersion": self.costSnapshotVersion,
            "fallbackDeploymentIds": list(self.fallbackDeploymentIds),
            "candidates": [c.to_dict() for c in self.candidates],
            "decidedAt": self.decidedAt,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RouteDecision:
        cands = []
        for c in data["candidates"]:
            sb = None
            if "scoreBreakdown" in c and c["scoreBreakdown"]:
                sb = ScoreBreakdown(**c["scoreBreakdown"])
            cands.append(
                CandidateEvaluation(
                    deploymentId=str(c["deploymentId"]),
                    eligible=bool(c["eligible"]),
                    denialReasons=tuple(c.get("denialReasons", ())),
                    score=c.get("score"),
                    scoreBreakdown=sb,
                )
            )
        return cls(
            schemaVersion=str(data["schemaVersion"]),
            decisionId=str(data["decisionId"]),
            selectedDeploymentId=str(data["selectedDeploymentId"]),
            selectedLane=ExecutionLane(data["selectedLane"]),
            policyVersion=str(data["policyVersion"]),
            registryVersion=str(data["registryVersion"]),
            candidates=tuple(cands),
            fallbackDeploymentIds=tuple(data.get("fallbackDeploymentIds", ())),
            decidedAt=str(data["decidedAt"]),
            healthSnapshotVersion=data.get("healthSnapshotVersion"),
            costSnapshotVersion=data.get("costSnapshotVersion"),
        )


@dataclass(frozen=True)
class ModelDescriptor:
    alias: str
    family: str
    lifecycle: ModelLifecycle
    capabilities: dict[str, Any]
    modalities: tuple[str, ...] = ("text",)
    maxContextTokens: int = 128_000
    maxOutputTokens: int = 4096
    reasoningProfiles: tuple[str, ...] = ()
    supportsToolCalling: bool = True
    supportsStructuredOutput: bool = True
    supportsStreaming: bool = True
    taskBenchmarks: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderDescriptor:
    id: str
    type: str  # NATIVE, LITELLM, OPENROUTER, SELF_HOSTED
    credentialRef: str
    enabled: bool = True
    supportedRegions: tuple[str, ...] = ("us", "eu")
    zeroDataRetention: bool = False
    prohibitsTraining: bool = True
    slaTier: str = "enterprise"


@dataclass(frozen=True)
class ProviderDeployment:
    id: str
    modelAlias: str
    providerId: str
    lane: ExecutionLane
    actualModel: str
    enabled: bool = True
    regions: tuple[str, ...] = ("us",)
    retention: str = "contracted"
    trainingAllowed: bool = False
    rateLimitProfile: str = "default"
    pricingProfile: str = "default"
    allowedOpenRouterProviders: tuple[str, ...] = ()
    requireZdr: bool = False
    priority: int = 100
    featureOverrides: dict[str, Any] = field(default_factory=dict)
    priceInputPer1k: float = 0.003
    priceOutputPer1k: float = 0.015


@dataclass(frozen=True)
class UsageReport:
    promptTokens: int
    completionTokens: int
    totalTokens: int
    reasoningTokens: int = 0
    cachedPromptTokens: int = 0
    cacheWriteTokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class InferenceResponse:
    id: str
    model: str
    content: str | None
    toolCalls: tuple[dict[str, Any], ...] | None = None
    finishReason: str = "stop"
    usage: UsageReport = field(default_factory=lambda: UsageReport(0, 0, 0))
    rawProviderResponseId: str | None = None
    rateLimitHeaders: dict[str, str] | None = None
    executionLatencyMs: float = 0.0


@dataclass(frozen=True)
class InferenceStreamChunk:
    chunkId: str
    deltaContent: str | None = None
    deltaToolCalls: tuple[dict[str, Any], ...] | None = None
    finishReason: str | None = None
    streamEpoch: int = 0
    isTerminal: bool = False


@dataclass(frozen=True)
class ReconciledUsage:
    source: str  # PROVIDER, GATEWAY, TOKENIZER_ESTIMATE
    usage: UsageReport
    estimatedCost: float
    reconciledCost: float
    currency: str = "USD"
    confidence: float = 1.0


# Schema validators
def validate_model_execution_plan(data: dict[str, Any], schema: dict[str, Any]) -> None:
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        msg = "; ".join(f"{'/'.join(map(str, err.path))}: {err.message}" for err in errors)
        raise jsonschema.ValidationError(f"ModelExecutionPlan failed validation: {msg}")


def validate_route_decision(data: dict[str, Any], schema: dict[str, Any]) -> None:
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        msg = "; ".join(f"{'/'.join(map(str, err.path))}: {err.message}" for err in errors)
        raise jsonschema.ValidationError(f"RouteDecision failed validation: {msg}")
