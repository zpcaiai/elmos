"""Registry implementations for Models, Providers, and Deployments.

Provides versioned, auditable, thread-safe configuration management and health snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
from typing import Any, Mapping

import yaml

from ..domain.contracts import (
    ExecutionLane,
    ModelDescriptor,
    ModelLifecycle,
    ProviderDeployment,
    ProviderDescriptor,
)


@dataclass(frozen=True)
class HealthSnapshot:
    deploymentId: str
    availability: float = 1.0  # 0.0 to 1.0
    p95LatencyMs: float = 500.0
    rateLimitPressure: float = 0.0  # 0.0 (none) to 1.0 (saturated)
    timeoutRate: float = 0.0
    successRate: float = 1.0
    lastProbeAt: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    circuitOpen: bool = False

    def is_healthy(self) -> bool:
        return (
            not self.circuitOpen
            and self.availability > 0.8
            and self.successRate > 0.8
            and self.rateLimitPressure < 0.95
        )


class RegistrySnapshot:
    """In-memory, versioned snapshot of models, providers, deployments, and health states."""

    def __init__(
        self,
        version: str,
        models: Mapping[str, ModelDescriptor],
        providers: Mapping[str, ProviderDescriptor],
        deployments: Mapping[str, ProviderDeployment],
        health: Mapping[str, HealthSnapshot] | None = None,
        health_version: str = "health.init.1",
    ) -> None:
        self.version = version
        self._models = dict(models)
        self._providers = dict(providers)
        self._deployments = dict(deployments)
        self._health = dict(health or {})
        self.health_version = health_version

    def get_model(self, alias: str) -> ModelDescriptor | None:
        return self._models.get(alias)

    def get_provider(self, provider_id: str) -> ProviderDescriptor | None:
        return self._providers.get(provider_id)

    def get_deployment(self, deployment_id: str) -> ProviderDeployment | None:
        return self._deployments.get(deployment_id)

    def get_deployments_for_model(self, alias: str) -> list[ProviderDeployment]:
        return [
            d for d in self._deployments.values()
            if d.modelAlias == alias and d.enabled
        ]

    def list_models(self) -> list[ModelDescriptor]:
        return list(self._models.values())

    def list_providers(self) -> list[ProviderDescriptor]:
        return list(self._providers.values())

    def list_deployments(self) -> list[ProviderDeployment]:
        return list(self._deployments.values())

    def get_health(self, deployment_id: str) -> HealthSnapshot:
        if deployment_id in self._health:
            return self._health[deployment_id]
        return HealthSnapshot(deploymentId=deployment_id)


DEFAULT_REGISTRY_YAML = """
version: "2026-09-09.1"

models:
  - alias: strategic-coding-high
    family: coding-reasoning
    lifecycle: stable
    capabilities:
      coding: 0.98
      architecture: 0.95
      refactoring: 0.98
      tool_calling: true
      structured_output: true
      streaming: true
      long_context: true
    task_benchmarks:
      LARGE_REFACTOR: 0.96
      MIGRATION_EXECUTION: 0.95

  - alias: cheap-classifier
    family: classifier
    lifecycle: stable
    capabilities:
      classification: 0.95
      structured_output: true
      streaming: false

providers:
  - id: openai-direct
    type: NATIVE
    credential_ref: secret://providers/openai/prod
    enabled: true

  - id: anthropic-direct
    type: NATIVE
    credential_ref: secret://providers/anthropic/prod
    enabled: true

  - id: litellm-prod
    type: LITELLM
    credential_ref: secret://gateways/litellm/prod
    enabled: true

  - id: openrouter
    type: OPENROUTER
    credential_ref: secret://providers/openrouter/prod
    enabled: true

deployments:
  - id: strategic-coding-high-openai-native
    model_alias: strategic-coding-high
    provider_id: openai-direct
    lane: NATIVE_DIRECT
    actual_model: "gpt-4o"
    regions: ["us"]
    retention: provider_contract
    training: false
    rate_limit_profile: openai-prod
    pricing_profile: strategic-openai-2026-09
    enabled: true

  - id: strategic-coding-high-openrouter
    model_alias: strategic-coding-high
    provider_id: openrouter
    lane: OPENROUTER
    actual_model: "anthropic/claude-3.5-sonnet"
    allowed_openrouter_providers: ["anthropic"]
    require_zdr: true
    rate_limit_profile: openrouter-prod
    pricing_profile: strategic-openrouter-2026-09
    enabled: true
"""


class DeploymentRegistry:
    """Thread-safe, versioned registry managing models, providers, deployments, and runtime health."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active_snapshot = RegistrySnapshot("0.0.0", {}, {}, {})
        self._history: dict[str, RegistrySnapshot] = {}

    @classmethod
    def create_default(cls) -> DeploymentRegistry:
        reg = cls()
        reg.load_from_yaml(DEFAULT_REGISTRY_YAML)
        return reg

    @property
    def current(self) -> RegistrySnapshot:
        with self._lock:
            return self._active_snapshot

    def load_from_yaml(self, yaml_str: str) -> RegistrySnapshot:
        data = yaml.safe_load(yaml_str)
        return self.load_from_dict(data)

    def load_from_dict(self, data: Mapping[str, Any]) -> RegistrySnapshot:
        with self._lock:
            version = str(data.get("version", datetime.now(timezone.utc).isoformat()))

            # Parse models
            models: dict[str, ModelDescriptor] = {}
            for m in data.get("models", []):
                alias = str(m["alias"])
                desc = ModelDescriptor(
                    alias=alias,
                    family=str(m.get("family", "general")),
                    lifecycle=ModelLifecycle(m.get("lifecycle", "stable")),
                    capabilities=dict(m.get("capabilities", {})),
                    modalities=tuple(m.get("modalities", ["text"])),
                    maxContextTokens=int(m.get("maxContextTokens", 128_000)),
                    maxOutputTokens=int(m.get("maxOutputTokens", 4096)),
                    reasoningProfiles=tuple(m.get("reasoningProfiles", ())),
                    supportsToolCalling=bool(m.get("capabilities", {}).get("tool_calling", True)),
                    supportsStructuredOutput=bool(m.get("capabilities", {}).get("structured_output", True)),
                    supportsStreaming=bool(m.get("capabilities", {}).get("streaming", True)),
                    taskBenchmarks=dict(m.get("task_benchmarks", {})),
                )
                models[alias] = desc

            # Parse providers
            providers: dict[str, ProviderDescriptor] = {}
            for p in data.get("providers", []):
                pid = str(p["id"])
                pdesc = ProviderDescriptor(
                    id=pid,
                    type=str(p.get("type", "NATIVE")),
                    credentialRef=str(p.get("credential_ref", f"secret://providers/{pid}")),
                    enabled=bool(p.get("enabled", True)),
                    supportedRegions=tuple(p.get("supported_regions", ("us", "eu"))),
                    zeroDataRetention=bool(p.get("zero_data_retention", False)),
                    prohibitsTraining=bool(p.get("prohibits_training", True)),
                    slaTier=str(p.get("sla_tier", "enterprise")),
                )
                providers[pid] = pdesc

            # Parse deployments
            deployments: dict[str, ProviderDeployment] = {}
            for d in data.get("deployments", []):
                did = str(d["id"])
                dep = ProviderDeployment(
                    id=did,
                    modelAlias=str(d["model_alias"]),
                    providerId=str(d["provider_id"]),
                    lane=ExecutionLane(d.get("lane", "NATIVE_DIRECT")),
                    actualModel=str(d.get("actual_model", did)),
                    enabled=bool(d.get("enabled", True)),
                    regions=tuple(d.get("regions", ("us",))),
                    retention=str(d.get("retention", "contracted")),
                    trainingAllowed=bool(d.get("training", False)),
                    rateLimitProfile=str(d.get("rate_limit_profile", "default")),
                    pricingProfile=str(d.get("pricing_profile", "default")),
                    allowedOpenRouterProviders=tuple(d.get("allowed_openrouter_providers", ())),
                    requireZdr=bool(d.get("require_zdr", False)),
                    priority=int(d.get("priority", 100)),
                    featureOverrides=dict(d.get("feature_overrides", {})),
                    priceInputPer1k=float(d.get("price_input_per_1k", 0.003)),
                    priceOutputPer1k=float(d.get("price_output_per_1k", 0.015)),
                )
                deployments[did] = dep

            # Preserve existing health where possible
            existing_health = dict(self._active_snapshot._health)
            snapshot = RegistrySnapshot(
                version=version,
                models=models,
                providers=providers,
                deployments=deployments,
                health=existing_health,
                health_version=self._active_snapshot.health_version,
            )
            self._history[version] = snapshot
            self._active_snapshot = snapshot
            return snapshot

    def rollback_to_version(self, version: str) -> RegistrySnapshot:
        with self._lock:
            if version not in self._history:
                raise ValueError(f"Version {version} not found in registry history")
            self._active_snapshot = self._history[version]
            return self._active_snapshot

    def update_health(
        self,
        deployment_id: str,
        availability: float | None = None,
        p95_latency_ms: float | None = None,
        rate_limit_pressure: float | None = None,
        timeout_rate: float | None = None,
        success_rate: float | None = None,
        circuit_open: bool | None = None,
    ) -> HealthSnapshot:
        with self._lock:
            cur_health = self._active_snapshot.get_health(deployment_id)
            new_health = HealthSnapshot(
                deploymentId=deployment_id,
                availability=cur_health.availability if availability is None else availability,
                p95LatencyMs=cur_health.p95LatencyMs if p95_latency_ms is None else p95_latency_ms,
                rateLimitPressure=cur_health.rateLimitPressure if rate_limit_pressure is None else rate_limit_pressure,
                timeoutRate=cur_health.timeoutRate if timeout_rate is None else timeout_rate,
                successRate=cur_health.successRate if success_rate is None else success_rate,
                circuitOpen=cur_health.circuitOpen if circuit_open is None else circuit_open,
                lastProbeAt=datetime.now(timezone.utc),
            )
            new_health_map = dict(self._active_snapshot._health)
            new_health_map[deployment_id] = new_health
            new_hversion = f"health.{datetime.now(timezone.utc).timestamp()}"

            self._active_snapshot = RegistrySnapshot(
                version=self._active_snapshot.version,
                models=self._active_snapshot._models,
                providers=self._active_snapshot._providers,
                deployments=self._active_snapshot._deployments,
                health=new_health_map,
                health_version=new_hversion,
            )
            return new_health


# Aliases for backwards and convenience
ModelRegistry = DeploymentRegistry
ProviderRegistry = DeploymentRegistry
