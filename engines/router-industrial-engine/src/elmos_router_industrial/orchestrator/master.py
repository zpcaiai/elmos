"""Master Orchestrator for Elmos Router Industrial.

Implements Skill 00: Coordinates end-to-end execution flow, feature flags,
coexistence with legacy systems, preflight reservation, multi-phase routing,
resilient retry/fallback, exactly-once CAS commit, cost ledgering, and telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any, Callable, Mapping, Sequence
import uuid

from ..accounting.accounting import (
    AccountingEvent,
    BudgetManager,
    CostLedger,
    RateLimiter,
    UsageReconciler,
)
from ..adapters.litellm_gateway import LiteLLMGatewayAdapter
from ..adapters.native_anthropic import NativeAnthropicAdapter
from ..adapters.native_openai import NativeOpenAIAdapter
from ..adapters.openrouter import OpenRouterAdapter
from ..adapters.self_hosted import SelfHostedAdapter
from ..domain.contracts import (
    CapabilityLease,
    ExecutionLane,
    InferenceResponse,
    InferenceStreamChunk,
    ModelExecutionPlan,
    RouteDecision,
    RouteRequest,
    VerifiedSecurityContext,
)
from ..domain.errors import ErrorTaxonomyClass, ProviderError
from ..observability.observability import (
    HealthTracker,
    MetricsCollector,
    TelemetryTracer,
)
from ..policy.engine import PolicyEngine
from ..registry.registry import DeploymentRegistry
from ..resilience.resilience import (
    CircuitBreakerRegistry,
    CommitCoordinator,
    CommittedResult,
    RetryManager,
    StreamEpochCoordinator,
)
from ..router.engine import RoutingEngine, ShadowRouter
from ..spi.adapter import ProviderAdapter


@dataclass
class OrchestratorFeatureFlags:
    router_v2_enabled: bool = True
    shadow_route_enabled: bool = False
    native_lane_enabled: bool = True
    openrouter_fallback_enabled: bool = True


class MasterOrchestrator:
    """Production-grade master orchestrator for Elmos model intelligence and routing."""

    def __init__(
        self,
        registry: DeploymentRegistry | None = None,
        policy_engine: PolicyEngine | None = None,
        routing_engine: RoutingEngine | None = None,
        budget_manager: BudgetManager | None = None,
        rate_limiter: RateLimiter | None = None,
        cost_ledger: CostLedger | None = None,
        commit_coordinator: CommitCoordinator | None = None,
        circuit_registry: CircuitBreakerRegistry | None = None,
        retry_manager: RetryManager | None = None,
        tracer: TelemetryTracer | None = None,
        metrics: MetricsCollector | None = None,
        health_tracker: HealthTracker | None = None,
        feature_flags: OrchestratorFeatureFlags | None = None,
        legacy_router_fallback: Callable[[RouteRequest], InferenceResponse] | None = None,
    ) -> None:
        self.registry = registry or DeploymentRegistry.create_default()
        self.policy_engine = policy_engine or PolicyEngine()
        self.routing_engine = routing_engine or RoutingEngine(self.registry, self.policy_engine)
        self.shadow_router = ShadowRouter(self.routing_engine)

        self.budget_manager = budget_manager or BudgetManager()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.cost_ledger = cost_ledger or CostLedger()
        self.commit_coordinator = commit_coordinator or CommitCoordinator()
        self.circuit_registry = circuit_registry or CircuitBreakerRegistry()
        self.retry_manager = retry_manager or RetryManager()
        self.stream_epoch_coord = StreamEpochCoordinator()

        self.tracer = tracer or TelemetryTracer()
        self.metrics = metrics or MetricsCollector()
        self.health_tracker = health_tracker or HealthTracker()
        self.flags = feature_flags or OrchestratorFeatureFlags()
        self.legacy_fallback = legacy_router_fallback

        # Register provider adapters
        self._adapters: dict[str, ProviderAdapter] = {}
        self.register_adapter(NativeOpenAIAdapter())
        self.register_adapter(NativeAnthropicAdapter())
        self.register_adapter(LiteLLMGatewayAdapter())
        self.register_adapter(OpenRouterAdapter())
        self.register_adapter(SelfHostedAdapter())

    def register_adapter(self, adapter: ProviderAdapter) -> None:
        self._adapters[adapter.adapter_id] = adapter

    def execute_inference(
        self,
        request: RouteRequest,
        security_context: VerifiedSecurityContext | None = None,
        lease: CapabilityLease | None = None,
    ) -> CommittedResult:
        trace_id = f"tr_{request.taskId}_{request.stepId}"
        self.metrics.increment("router.requests.total")

        # 1. Check feature flag: if router v2 disabled, fall back to legacy route
        if not self.flags.router_v2_enabled:
            if not self.legacy_fallback:
                raise ProviderError(
                    taxonomyClass=ErrorTaxonomyClass.POLICY_DENIED,
                    message="Router v2 is disabled and no legacy fallback is configured",
                )
            resp = self.legacy_fallback(request)
            return self.commit_coordinator.commit(
                task_id=request.taskId,
                step_id=request.stepId,
                attempt_id=request.attemptId,
                idempotency_key=request.idempotencyKey,
                response=resp,
            )

        # 2. Check Idempotent Pre-Commit (avoid duplicate execution)
        existing = self.commit_coordinator.get_committed(request.taskId, request.stepId)
        if existing:
            self.metrics.increment("router.commits.idempotent_hit")
            return existing

        # 3. Route Evaluation Span
        with self.tracer.start_span("elmos.route.evaluate", trace_id, {"tenant": request.tenantId}):
            plan, decision = self.routing_engine.route(request, security_context, lease)

        # Optional Shadow Routing
        if self.flags.shadow_route_enabled:
            try:
                self.shadow_router.evaluate_shadow(request, decision.selectedDeploymentId, security_context, lease)
            except Exception:
                pass  # shadow evaluation must never fail the primary route

        # 4. Budget Preflight Check & Reservation
        res_id = f"res_{uuid.uuid4().hex[:8]}"
        est_cost = (request.maxInputTokens / 1000.0) * 0.003 + (request.expectedOutputTokens / 1000.0) * 0.015
        if not self.budget_manager.reserve(request.tenantId, request.taskId, est_cost, res_id):
            self.metrics.increment("router.budget.denied")
            raise ProviderError(
                taxonomyClass=ErrorTaxonomyClass.BUDGET_DENIED,
                message=f"Budget exceeded for tenant {request.tenantId} or task {request.taskId}",
                deploymentId=decision.selectedDeploymentId,
            )

        # 5. Rate Limiting Admission
        if not self.rate_limiter.try_acquire(request.tenantId, decision.selectedDeploymentId, request.maxInputTokens):
            self.budget_manager.settle(request.tenantId, request.taskId, 0.0, res_id)
            self.metrics.increment("router.ratelimit.throttled")
            raise ProviderError(
                taxonomyClass=ErrorTaxonomyClass.RATE_LIMIT,
                message=f"Rate limit or concurrency ceiling reached for deployment {decision.selectedDeploymentId}",
                deploymentId=decision.selectedDeploymentId,
            )

        # 6. Resilient Provider Invocation with Fallback Chain
        deployments_to_try = [decision.selectedDeploymentId] + list(decision.fallbackDeploymentIds)
        last_error: Exception | None = None
        successful_response: InferenceResponse | None = None
        executed_deployment_id = decision.selectedDeploymentId
        executed_plan = plan

        try:
            for dep_id in deployments_to_try:
                executed_deployment_id = dep_id
                snapshot = self.registry.current
                dep = snapshot.get_deployment(dep_id)
                if not dep:
                    continue

                breaker = self.circuit_registry.get_breaker(dep.providerId, dep.id)
                if not breaker.allow_request():
                    self.metrics.increment("router.circuit_breaker.rejected")
                    continue

                # Find adapter for lane
                adapter = self._resolve_adapter_for_deployment(dep.lane, dep.providerId)
                if not adapter:
                    continue

                # Update plan with active deployment
                active_plan = ModelExecutionPlan(
                    schemaVersion=plan.schemaVersion,
                    planId=plan.planId,
                    tenantId=plan.tenantId,
                    taskId=plan.taskId,
                    stepId=plan.stepId,
                    modelAlias=dep.modelAlias,
                    deploymentId=dep.id,
                    lane=dep.lane,
                    providerId=dep.providerId,
                    deadlineAt=plan.deadlineAt,
                    policyVersion=plan.policyVersion,
                    registryVersion=plan.registryVersion,
                    securityContextHash=plan.securityContextHash,
                    capabilityLeaseHash=plan.capabilityLeaseHash,
                    budget=plan.budget,
                    fallbacks=plan.fallbacks,
                    extensions=dict(dep.featureOverrides),
                )
                executed_plan = active_plan

                # Attempt execution with retries
                max_retries = 2
                for attempt in range(max_retries + 1):
                    try:
                        with self.tracer.start_span(
                            "elmos.provider.invoke",
                            trace_id,
                            {
                                "deploymentId": dep.id,
                                "providerId": dep.providerId,
                                "attempt": attempt,
                                "promptHash": self.tracer.hash_prompt(
                                    request.messages[0].content if request.messages else ""
                                ),
                            },
                        ):
                            resp = adapter.execute(request, active_plan, security_context)
                            breaker.record_success()
                            self.health_tracker.record_outcome(dep.id, True, resp.executionLatencyMs)
                            successful_response = resp
                            break
                    except ProviderError as pe:
                        breaker.record_failure()
                        self.health_tracker.record_outcome(dep.id, False, 5000.0)
                        last_error = pe
                        if pe.is_retryable(deadline=request.deadline, retries_remaining=max_retries - attempt):
                            backoff = self.retry_manager.compute_backoff(attempt + 1, pe.retryAfterSeconds, request.deadline)
                            if backoff is not None:
                                time.sleep(min(backoff, 0.05))  # bounded for execution efficiency
                                continue
                        # Non-retryable or retries exhausted; check fallback eligibility
                        if pe.is_fallback_eligible():
                            break  # advance to next deployment in fallback chain
                        raise pe
                    except Exception as ex:
                        breaker.record_failure()
                        self.health_tracker.record_outcome(dep.id, False, 5000.0)
                        last_error = ex
                        break

                if successful_response:
                    break

            if not successful_response:
                raise last_error or ProviderError(
                    taxonomyClass=ErrorTaxonomyClass.PROVIDER_5XX,
                    message="All eligible provider deployments and fallbacks failed",
                )

            # 7. Usage Reconciliation & Budget Settlement
            reconciled = UsageReconciler.reconcile(successful_response.usage, None, request)
            self.budget_manager.settle(request.tenantId, request.taskId, reconciled.reconciledCost, res_id)

            # 8. Append Accounting Event to Cost Ledger
            event = AccountingEvent(
                eventId=f"acct_{uuid.uuid4().hex[:8]}",
                taskId=request.taskId,
                stepId=request.stepId,
                attemptId=request.attemptId,
                tenantId=request.tenantId,
                modelAlias=executed_plan.modelAlias,
                deploymentId=executed_deployment_id,
                providerId=executed_plan.providerId,
                promptTokens=reconciled.usage.promptTokens,
                completionTokens=reconciled.usage.completionTokens,
                totalTokens=reconciled.usage.totalTokens,
                reasoningTokens=reconciled.usage.reasoningTokens,
                cachedTokens=reconciled.usage.cachedPromptTokens,
                estimatedCost=reconciled.estimatedCost,
                reconciledCost=reconciled.reconciledCost,
                currency=reconciled.currency,
                recordedAt=datetime.now(timezone.utc),
                pricingVersion=self.policy_engine.profile.version,
            )
            self.cost_ledger.append(event)

            # 9. Idempotent Result Commit (CAS)
            committed_record = self.commit_coordinator.commit(
                task_id=request.taskId,
                step_id=request.stepId,
                attempt_id=request.attemptId,
                idempotency_key=request.idempotencyKey,
                response=successful_response,
            )
            self.metrics.increment("router.commits.success")
            return committed_record

        finally:
            self.rate_limiter.release(request.tenantId, executed_deployment_id)

    def _resolve_adapter_for_deployment(self, lane: ExecutionLane, provider_id: str) -> ProviderAdapter | None:
        if lane == ExecutionLane.LITELLM:
            return self._adapters.get("litellm-gateway")
        elif lane == ExecutionLane.OPENROUTER:
            return self._adapters.get("openrouter")
        elif lane == ExecutionLane.SELF_HOSTED:
            return self._adapters.get("self-hosted")
        elif lane == ExecutionLane.NATIVE_DIRECT:
            if "anthropic" in provider_id.lower():
                return self._adapters.get("native-anthropic")
            return self._adapters.get("native-openai")
        return None


def main() -> None:
    print("Elmos Router Industrial Engine CLI v1.0.0")
