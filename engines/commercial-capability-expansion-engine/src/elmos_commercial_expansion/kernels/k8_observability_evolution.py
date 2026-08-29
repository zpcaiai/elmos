"""K8: Observability & Evolution Kernel for Elmos Commercial Capability Expansion."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from ..models import TaskContext, TrajectoryRecord


class ObservabilityEvolutionKernel:
    """Manages telemetry spans, trajectory dataset persistence, failure attribution, and canary promotion."""

    def __init__(self):
        self.spans: List[Dict[str, Any]] = []
        self.trajectories: Dict[str, TrajectoryRecord] = {}
        self.candidate_rules: List[Dict[str, Any]] = []
        self.canary_deployments: Dict[str, Dict[str, Any]] = {}

    def start_trace_span(
        self,
        task_id: str,
        name: str,
        kernel: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Starts an OpenTelemetry-compatible semantic span."""
        span_id = f"span-{hashlib.sha256((task_id + name + str(time.time())).encode('utf-8')).hexdigest()[:12]}"
        span = {
            "span_id": span_id,
            "task_id": task_id,
            "name": name,
            "kernel": kernel,
            "attributes": attributes or {},
            "start_time_unix_nano": int(time.time() * 1e9),
            "status": "RUNNING",
        }
        self.spans.append(span)
        return span_id

    def end_trace_span(self, span_id: str, status: str = "OK", error: Optional[str] = None) -> None:
        """Closes an active trace span."""
        for s in self.spans:
            if s["span_id"] == span_id:
                s["end_time_unix_nano"] = int(time.time() * 1e9)
                s["status"] = status
                if error:
                    s["error_message"] = error
                break

    def record_trajectory(
        self,
        task_id: str,
        steps_executed: int,
        tool_calls_count: int,
        outcome: str,
        tokens_consumed: int,
        wall_clock_ms: int,
        evidence_refs: Optional[List[str]] = None,
    ) -> TrajectoryRecord:
        """Records and versions a task execution trajectory for learning datasets."""
        traj_id = f"traj-{task_id}-{int(time.time()*1000)}"
        record = TrajectoryRecord(
            trajectory_id=traj_id,
            task_id=task_id,
            steps_executed=steps_executed,
            tool_calls_count=tool_calls_count,
            outcome=outcome,
            tokens_consumed=tokens_consumed,
            wall_clock_ms=wall_clock_ms,
            evidence_refs=evidence_refs or [],
        )
        self.trajectories[traj_id] = record
        return record

    def attribute_failure(
        self,
        trajectory: TrajectoryRecord,
        error_log: str,
        failed_step: str,
    ) -> Dict[str, Any]:
        """Attributes failure root-cause across 8 causal dimensions."""
        error_lower = error_log.lower()
        if "syntax" in error_lower or "parse" in error_lower:
            cause = "SYNTAX_PARSER_MISMATCH"
            recommendation = "Route to AST_COMPILER_API rewrite engine"
        elif "timed out" in error_lower or "timeout" in error_lower:
            cause = "EXECUTION_BUDGET_EXCEEDED"
            recommendation = "Increase timeout or shard atomic tasks"
        elif "policy" in error_lower or "denied" in error_lower:
            cause = "SECURITY_POLICY_RESTRICTION"
            recommendation = "Request human break-glass or refine policy rules"
        elif "assert" in error_lower or "mismatch" in error_lower:
            cause = "BEHAVIORAL_EQUIVALENCE_GAP"
            recommendation = "Synthesize minimal counterexample and repair rule"
        else:
            cause = "UNKNOWN_RUNTIME_EXCEPTION"
            recommendation = "Isolate in debug sandbox for diagnostic replay"

        return {
            "trajectory_id": trajectory.trajectory_id,
            "failed_step": failed_step,
            "attributed_cause": cause,
            "recommendation": recommendation,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def stage_canary_promotion(
        self,
        skill_id: str,
        new_version: str,
        traffic_weight: float = 0.10,
    ) -> Dict[str, Any]:
        """Stages a skill or rule version for progressive canary rollout."""
        canary_id = f"canary-{skill_id}-{new_version}"
        deployment = {
            "canary_id": canary_id,
            "skill_id": skill_id,
            "new_version": new_version,
            "traffic_weight": traffic_weight,
            "stage": "CANARY_EVALUATION",
            "metrics": {"invocations": 0, "success_rate": 1.0, "p95_latency_ms": 120},
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.canary_deployments[canary_id] = deployment
        return deployment
