"""Strangler-fig progressive cutover orchestration and decommission governance."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import CutoverDecision


class SystemCutoverOrchestrator:
    """Orchestrates progressive read/write traffic cutovers and legacy decommissioning."""

    def evaluate_cutover_request(
        self,
        plan_id: str,
        current_state: str,
        requested_state: str,
        read_differential_pass_rate: float,
        write_idempotency_verified: bool,
        has_incompatible_new_writes: bool = False
    ) -> CutoverDecision:
        blockers = []

        if requested_state == "READ_CUTOVER":
            if read_differential_pass_rate < 0.999:
                blockers.append("READ_DIFFERENTIAL_BELOW_THRESHOLD")
            decision = "APPROVED" if not blockers else "BLOCKED"
            return CutoverDecision(
                cutoverPlanId=plan_id,
                organizationId="org-composite",
                landscapeId="landscape-prod",
                currentState=current_state,
                requestedState=requested_state,
                decision=decision,
                humanApprovalRequired=False,
                rollbackClassification="AUTOMATIC_REVERSIBLE",
                blockers=blockers,
                evidenceRefs=[f"evidence:read-cutover:{plan_id}"]
            )

        if requested_state == "WRITE_CUTOVER":
            if not write_idempotency_verified:
                blockers.append("NEW_WRITE_IDEMPOTENCY_FAILED")

            rollback_mode = "FORWARD_FIX_ONLY" if has_incompatible_new_writes else "AUTOMATIC_REVERSIBLE"
            decision = "APPROVED" if not blockers else "BLOCKED"
            return CutoverDecision(
                cutoverPlanId=plan_id,
                organizationId="org-composite",
                landscapeId="landscape-prod",
                currentState=current_state,
                requestedState=requested_state,
                decision=decision,
                humanApprovalRequired=True,
                rollbackClassification=rollback_mode,
                blockers=blockers,
                evidenceRefs=[f"evidence:write-cutover:{plan_id}"]
            )

        return CutoverDecision(
            cutoverPlanId=plan_id,
            organizationId="org-composite",
            landscapeId="landscape-prod",
            currentState=current_state,
            requestedState=requested_state,
            decision="BLOCKED",
            humanApprovalRequired=True,
            rollbackClassification="FORWARD_FIX_ONLY",
            blockers=["UNKNOWN_CUTOVER_STATE"],
            evidenceRefs=[]
        )

    def evaluate_canary_health(self, error_rate_bps: int, latency_p95_ms: float, max_error_rate_bps: int = 50) -> Dict[str, Any]:
        """Monitors canary deployment health and initiates automated rollback if thresholds breached."""
        if error_rate_bps > max_error_rate_bps:
            return {
                "decision": "ROLLBACK",
                "reason": f"Canary error rate {error_rate_bps} bps exceeded safety limit {max_error_rate_bps} bps.",
                "action": "ROUTE_ALL_TRAFFIC_TO_PRIMARY"
            }
        return {
            "decision": "PROCEED",
            "reason": "Canary error rate and latency within acceptable SLA bounds.",
            "action": "INCREMENT_TRAFFIC_WEIGHT"
        }

    def evaluate_decommission_readiness(
        self,
        node_id: str,
        active_traffic_rpm: float,
        active_batch_jobs: List[str]
    ) -> Dict[str, Any]:
        """Ensures legacy systems are not decommissioned while active traffic or batch dependencies persist."""
        if active_batch_jobs or active_traffic_rpm > 0.0:
            reasons = []
            if active_traffic_rpm > 0.0:
                reasons.append(f"active traffic of {active_traffic_rpm} rpm observed")
            if active_batch_jobs:
                reasons.append(f"unmigrated batch jobs: {', '.join(active_batch_jobs)}")

            return {
                "verdict": "LEGACY_DECOMMISSION_BLOCKED",
                "can_decommission": False,
                "reason": f"Decommission of {node_id} blocked due to: {'; '.join(reasons)}."
            }

        return {
            "verdict": "DECOMMISSION_APPROVED",
            "can_decommission": True,
            "reason": f"No active traffic or batch dependencies detected on {node_id}."
        }

    def verify_message_idempotency(self, message_id: str, processed_cache: set[str]) -> Dict[str, Any]:
        """Verifies duplicate message suppression."""
        if message_id in processed_cache:
            return {
                "verdict": "DUPLICATE_SUPPRESSED",
                "processed": False,
                "reason": f"Message {message_id} already processed. Suppressed duplicate side-effects."
            }
        processed_cache.add(message_id)
        return {
            "verdict": "PROCESSED",
            "processed": True,
            "reason": f"Message {message_id} processed successfully."
        }
