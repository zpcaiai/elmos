"""Deterministic 4-Phase Routing Engine and Shadow Router for Elmos.

Phase A: Hard eligibility filtering through PolicyEngine.
Phase B: Multi-factor normalized scoring across quality, health, latency, and cost.
Phase C: Stable, deterministic tie-breaking.
Phase D: Constrained fallback graph generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
from typing import Any, Mapping

from ..domain.contracts import (
    CandidateEvaluation,
    CapabilityLease,
    ExecutionLane,
    ModelExecutionPlan,
    RouteDecision,
    RouteRequest,
    ScoreBreakdown,
    VerifiedSecurityContext,
)
from ..policy.engine import PolicyEngine
from ..registry.registry import DeploymentRegistry, HealthSnapshot, RegistrySnapshot


@dataclass(frozen=True)
class ShadowRouteDiff:
    routeDecisionId: str
    baselineDeploymentId: str
    shadowDeploymentId: str
    isDifferent: bool
    costDelta: float
    latencyDeltaMs: float
    policyDivergence: tuple[str, ...] = ()


class RoutingEngine:
    """Core deterministic routing engine implementing 4-phase model selection."""

    def __init__(
        self,
        registry: DeploymentRegistry,
        policy_engine: PolicyEngine,
    ) -> None:
        self.registry = registry
        self.policy_engine = policy_engine

    def route(
        self,
        request: RouteRequest,
        security_context: VerifiedSecurityContext | None = None,
        lease: CapabilityLease | None = None,
        now: datetime | None = None,
    ) -> tuple[ModelExecutionPlan, RouteDecision]:
        current_time = now or datetime.now(timezone.utc)
        snapshot: RegistrySnapshot = self.registry.current

        candidates_eval: list[CandidateEvaluation] = []
        eligible_candidates: list[tuple[str, float, ScoreBreakdown, float]] = []
        # list of tuples: (deployment_id, final_score, score_breakdown, estimated_cost)

        all_deployments = snapshot.list_deployments()
        # Sort deployments initially by ID for deterministic scan order
        all_deployments.sort(key=lambda d: d.id)

        # -------------------------------------------------------------
        # Phase A: Hard Eligibility Filtering
        # -------------------------------------------------------------
        for deployment in all_deployments:
            model = snapshot.get_model(deployment.modelAlias)
            provider = snapshot.get_provider(deployment.providerId)

            if not model or not provider:
                candidates_eval.append(
                    CandidateEvaluation(
                        deploymentId=deployment.id,
                        eligible=False,
                        denialReasons=("Model or Provider descriptor missing from registry",),
                    )
                )
                continue

            policy_res = self.policy_engine.evaluate(
                request=request,
                model=model,
                provider=provider,
                deployment=deployment,
                security_context=security_context,
                lease=lease,
                now=current_time,
            )

            if not policy_res.eligible:
                candidates_eval.append(
                    CandidateEvaluation(
                        deploymentId=deployment.id,
                        eligible=False,
                        denialReasons=policy_res.denialReasons,
                    )
                )
                continue

            # ---------------------------------------------------------
            # Phase B: Multi-Factor Normalized Scoring
            # ---------------------------------------------------------
            health: HealthSnapshot = snapshot.get_health(deployment.id)
            score, breakdown = self._score_deployment(
                request=request,
                deployment=deployment,
                model=model,
                health=health,
                estimated_cost=policy_res.estimatedCost,
            )

            candidates_eval.append(
                CandidateEvaluation(
                    deploymentId=deployment.id,
                    eligible=True,
                    score=round(score, 4),
                    scoreBreakdown=breakdown,
                )
            )
            eligible_candidates.append(
                (deployment.id, score, breakdown, policy_res.estimatedCost)
            )

        if not eligible_candidates:
            # All candidates failed hard eligibility; raise fail-closed error
            denial_summary = "; ".join(
                f"{c.deploymentId}: {','.join(c.denialReasons)}"
                for c in candidates_eval
                if not c.eligible
            )
            raise ValueError(
                f"Routing failed: no eligible deployments found for request. Reasons: {denial_summary}"
            )

        # -------------------------------------------------------------
        # Phase C: Deterministic Tie-Breaking
        # -------------------------------------------------------------
        # Ordering rule:
        # 1. Primary score (descending)
        # 2. Priority from deployment (descending)
        # 3. Projected cost (ascending)
        # 4. Health availability (descending)
        # 5. Deployment ID lexical order (ascending)
        def tie_breaker_key(
            item: tuple[str, float, ScoreBreakdown, float]
        ) -> tuple[float, int, float, float, str]:
            did, score, _, est_cost = item
            dep = snapshot.get_deployment(did)
            h = snapshot.get_health(did)
            return (
                -score,
                -dep.priority if dep else 0,
                est_cost,
                -h.availability,
                did,
            )

        eligible_candidates.sort(key=tie_breaker_key)

        selected_id = eligible_candidates[0][0]
        selected_deployment = snapshot.get_deployment(selected_id)
        if not selected_deployment:
            raise ValueError(f"Selected deployment {selected_id} not found in registry")

        # -------------------------------------------------------------
        # Phase D: Fallback Graph Generation
        # -------------------------------------------------------------
        fallback_candidates = eligible_candidates[1:]
        fallback_ids: list[str] = []

        # Enforce provider diversity when possible
        used_providers = {selected_deployment.providerId}
        deferred_same_provider: list[str] = []

        for did, _, _, _ in fallback_candidates:
            dep = snapshot.get_deployment(did)
            if not dep:
                continue
            # Respect max cross model fallbacks
            if dep.providerId not in used_providers:
                fallback_ids.append(did)
                used_providers.add(dep.providerId)
            else:
                deferred_same_provider.append(did)

        # Append deferred fallbacks up to max attempts limit
        max_fallbacks = max(0, self.policy_engine.profile.maxAttempts - 1)
        fallback_ids.extend(deferred_same_provider)
        final_fallback_ids = fallback_ids[:max_fallbacks]

        # -------------------------------------------------------------
        # Assemble RouteDecision & ModelExecutionPlan
        # -------------------------------------------------------------
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"

        sec_hash = (
            security_context.digest()
            if security_context
            else "sec_none_public"
        )
        lease_hash = lease.digest() if lease else "lease_none"

        decision = RouteDecision(
            schemaVersion="1",
            decisionId=decision_id,
            selectedDeploymentId=selected_id,
            selectedLane=selected_deployment.lane,
            policyVersion=self.policy_engine.profile.version,
            registryVersion=snapshot.version,
            healthSnapshotVersion=snapshot.health_version,
            costSnapshotVersion=snapshot.version,
            fallbackDeploymentIds=tuple(final_fallback_ids),
            candidates=tuple(candidates_eval),
            decidedAt=current_time.isoformat(),
        )

        plan = ModelExecutionPlan(
            schemaVersion="1",
            planId=plan_id,
            tenantId=request.tenantId,
            taskId=request.taskId,
            stepId=request.stepId,
            modelAlias=selected_deployment.modelAlias,
            deploymentId=selected_id,
            lane=selected_deployment.lane,
            providerId=selected_deployment.providerId,
            deadlineAt=request.deadline.isoformat(),
            policyVersion=self.policy_engine.profile.version,
            registryVersion=snapshot.version,
            securityContextHash=sec_hash,
            capabilityLeaseHash=lease_hash,
            budget=request.budgetEnvelope,
            requiredCapabilities=tuple(request.requiredCapabilities),
            fallbacks=tuple(final_fallback_ids),
            extensions=dict(selected_deployment.featureOverrides),
        )

        return plan, decision

    def _score_deployment(
        self,
        request: RouteRequest,
        deployment: Any,
        model: Any,
        health: HealthSnapshot,
        estimated_cost: float,
    ) -> tuple[float, ScoreBreakdown]:
        weights = self.policy_engine.profile.taskClassWeights.get(
            request.taskClass.value,
            {
                "quality_weight": 0.35,
                "reliability_weight": 0.25,
                "cost_weight": 0.20,
                "latency_weight": 0.10,
                "benchmark_weight": 0.10,
            },
        )

        # 1. Capability Fit
        cap_scores = []
        for cap in request.requiredCapabilities:
            val = model.capabilities.get(cap, 0.5)
            cap_scores.append(float(val) if isinstance(val, (int, float)) else 1.0)
        for cap in request.preferredCapabilities:
            val = model.capabilities.get(cap, 0.0)
            cap_scores.append(float(val) if isinstance(val, (int, float)) else (1.0 if val else 0.0))
        cap_fit = sum(cap_scores) / max(1, len(cap_scores)) if cap_scores else 1.0

        # 2. Benchmark Quality
        bm_quality = model.taskBenchmarks.get(request.taskClass.value, 0.85)

        # 3. Reliability & Health
        health_score = (
            health.availability * 0.4
            + health.successRate * 0.4
            + max(0.0, 1.0 - health.rateLimitPressure) * 0.2
        )

        # 4. Latency
        latency_score = max(0.0, 1.0 - (health.p95LatencyMs / 5000.0))

        # 5. Cost Score (lower cost gives higher score relative to max budget)
        max_cost = max(0.0001, request.budgetEnvelope.maxCost)
        cost_score = max(0.0, 1.0 - (estimated_cost / max_cost))

        # 6. Cache Affinity (Bonus if caching supported and prompt is large)
        cache_affinity = 0.0
        if model.capabilities.get("prompt_caching", False) and request.maxInputTokens > 2048:
            cache_affinity = 0.1

        # 7. Region Affinity
        region_affinity = 0.0
        if request.regionConstraints and any(r in deployment.regions for r in request.regionConstraints):
            region_affinity = 0.05

        # 8. Penalties
        penalties = 0.0
        if health.circuitOpen:
            penalties += 0.5
        if health.rateLimitPressure > 0.8:
            penalties += 0.2

        w_q = weights.get("quality_weight", 0.35)
        w_r = weights.get("reliability_weight", 0.25)
        w_c = weights.get("cost_weight", 0.20)
        w_l = weights.get("latency_weight", 0.10)
        w_bm = weights.get("benchmark_weight", 0.10)

        raw_score = (
            w_q * cap_fit
            + w_bm * bm_quality
            + w_r * health_score
            + w_l * latency_score
            + w_c * cost_score
            + cache_affinity
            + region_affinity
            - penalties
        )

        breakdown = ScoreBreakdown(
            capabilityFit=round(cap_fit, 4),
            taskBenchmarkQuality=round(bm_quality, 4),
            reliabilityHealth=round(health_score, 4),
            expectedLatency=round(latency_score, 4),
            estimatedCost=round(cost_score, 4),
            cacheAffinity=round(cache_affinity, 4),
            regionAffinity=round(region_affinity, 4),
            providerDiversity=0.0,
            historicalSuccess=round(health.successRate, 4),
            penalties=round(penalties, 4),
        )

        return max(0.0, raw_score), breakdown


class ShadowRouter:
    """Evaluates shadow decisions against baseline production routes without executing them."""

    def __init__(self, router: RoutingEngine) -> None:
        self.router = router

    def evaluate_shadow(
        self,
        request: RouteRequest,
        baseline_deployment_id: str,
        security_context: VerifiedSecurityContext | None = None,
        lease: CapabilityLease | None = None,
        now: datetime | None = None,
    ) -> ShadowRouteDiff:
        plan, decision = self.router.route(request, security_context, lease, now=now)
        shadow_id = decision.selectedDeploymentId

        diff_found = shadow_id != baseline_deployment_id
        divergence: list[str] = []
        if diff_found:
            divergence.append(f"Selected deployment differed: shadow={shadow_id}, baseline={baseline_deployment_id}")

        snap = self.router.registry.current
        base_dep = snap.get_deployment(baseline_deployment_id)
        shadow_dep = snap.get_deployment(shadow_id)

        base_cost = 0.0
        shadow_cost = 0.0
        base_latency = 0.0
        shadow_latency = 0.0

        if base_dep:
            base_cost = (request.maxInputTokens / 1000.0) * base_dep.priceInputPer1k + (request.expectedOutputTokens / 1000.0) * base_dep.priceOutputPer1k
            base_latency = snap.get_health(base_dep.id).p95LatencyMs
        if shadow_dep:
            shadow_cost = (request.maxInputTokens / 1000.0) * shadow_dep.priceInputPer1k + (request.expectedOutputTokens / 1000.0) * shadow_dep.priceOutputPer1k
            shadow_latency = snap.get_health(shadow_dep.id).p95LatencyMs

        return ShadowRouteDiff(
            routeDecisionId=decision.decisionId,
            baselineDeploymentId=baseline_deployment_id,
            shadowDeploymentId=shadow_id,
            isDifferent=diff_found,
            costDelta=round(shadow_cost - base_cost, 6),
            latencyDeltaMs=round(shadow_latency - base_latency, 2),
            policyDivergence=tuple(divergence),
        )
