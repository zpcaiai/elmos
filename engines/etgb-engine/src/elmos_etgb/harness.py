"""Production adapter contract and durable local reference harness."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .budget import BudgetLedger
from .canonical import digest_json
from .checkpoint import CheckpointStore
from .evidence import EvidenceStore
from .policy import authorize
from .state import JsonRunStateStore, RunState


@dataclass
class PhaseResult:
    status: str
    outputs: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Path] = field(default_factory=list)
    side_effects: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    message: str | None = None


class HarnessAdapter(Protocol):
    def prepare(self, context: dict[str, Any]) -> PhaseResult: ...
    def baseline(self, context: dict[str, Any]) -> PhaseResult: ...
    def transform_or_generate(self, context: dict[str, Any]) -> PhaseResult: ...
    def build(self, context: dict[str, Any]) -> PhaseResult: ...
    def validate(self, context: dict[str, Any]) -> PhaseResult: ...
    def score(self, context: dict[str, Any]) -> PhaseResult: ...
    def publish(self, context: dict[str, Any]) -> PhaseResult: ...
    def compensate(self, context: dict[str, Any]) -> PhaseResult: ...
    def cleanup(self, context: dict[str, Any]) -> PhaseResult: ...


def phase_plan(context: dict[str, Any]) -> list[tuple[RunState, str, RunState]]:
    work = RunState.GENERATING if context.get("business_line") == "project-generation" else RunState.TRANSFORMING
    return [(RunState.PLANNED, "prepare", RunState.PREPARING), (RunState.PREPARING, "baseline", RunState.BASELINING), (RunState.BASELINING, "transform_or_generate", work), (work, "build", RunState.BUILDING), (RunState.BUILDING, "validate", RunState.VALIDATING), (RunState.VALIDATING, "score", RunState.SCORING), (RunState.SCORING, "publish", RunState.PUBLISHING)]


class HarnessRuntime:
    """Reference orchestration enforcing ownership, evidence, budget and CAS."""

    def __init__(self, *, state_store: JsonRunStateStore, checkpoint_store: CheckpointStore, budget_ledger: BudgetLedger, evidence_store: EvidenceStore):
        self.state_store = state_store; self.checkpoint_store = checkpoint_store; self.budget_ledger = budget_ledger; self.evidence_store = evidence_store

    def execute(self, *, run_id: str, adapter: HarnessAdapter, context: dict[str, Any], authority: dict[str, Any], owner_id: str, fencing_token: int) -> dict[str, Any]:
        run = self.state_store.load(run_id)
        if run.get("fencing_token") != fencing_token or run.get("owner_id") != owner_id: raise PermissionError("runtime ownership/fencing mismatch")
        context = {**context, "run_id": run_id, "owner_id": owner_id, "fencing_token": fencing_token}; records: list[dict[str, Any]] = []
        try:
            for expected, method_name, target in phase_plan(context):
                current = self.state_store.load(run_id)
                if RunState(current["state"]) == expected:
                    current = self.state_store.transition(run_id=run_id, expected_state=expected, target_state=target, owner_id=owner_id, fencing_token=fencing_token, expected_revision=current["revision"], reason=f"enter {method_name}")
                elif RunState(current["state"]) != target:
                    raise RuntimeError(f"unexpected run state before {method_name}: {current['state']}")
                decision = authorize(authority, {"environment_id": authority.get("environment_id"), "authority_id": authority.get("authority_id"), "owner_id": owner_id, "tenant_id": authority.get("tenant_id"), "action": f"harness.{method_name}", "fencing_token": fencing_token})
                if not decision.allowed: raise PermissionError(decision.reason)
                started = time.perf_counter(); result = getattr(adapter, method_name)(context); duration_ms = int((time.perf_counter() - started) * 1000)
                if result.status != "passed": raise RuntimeError(result.message or f"phase failed: {method_name}")
                usage = {"input_tokens": int(result.usage.get("input_tokens", 0)), "output_tokens": int(result.usage.get("output_tokens", 0)), "credit_usd": float(result.usage.get("credit_usd", 0.0)), "wall_clock_ms": int(result.usage.get("wall_clock_ms", duration_ms))}
                self.budget_ledger.consume(run_id=run_id, idempotency_key=f"{run_id}:{method_name}:{current['revision']}", phase=method_name, **usage)
                artifacts = []
                for artifact_path in result.artifacts:
                    artifact = self.evidence_store.add_file(artifact_path, logical_name=f"phases/{method_name}/{artifact_path.name}", producer_environment=str(authority["environment_id"]), redact=artifact_path.suffix.lower() in {".txt", ".log", ".json", ".yaml", ".yml"})
                    artifacts.append({"logical_name": artifact["logical_name"], "sha256": artifact["sha256"]})
                checkpoint = self.checkpoint_store.save(run_id=run_id, phase=target.value, candidate_digest=run["candidate_digest"], plan_digest=run["plan_digest"], environment_digest=authority.get("digest") or digest_json(authority), fencing_token=fencing_token, artifacts=artifacts, side_effects=result.side_effects, resume_payload=result.outputs)
                latest = self.state_store.load(run_id)
                self.state_store.record_checkpoint(run_id=run_id, checkpoint_digest=checkpoint["checkpoint_digest"], owner_id=owner_id, fencing_token=fencing_token, expected_revision=latest["revision"], phase=method_name)
                records.append({"phase": method_name, "state": target.value, "duration_ms": duration_ms, "usage": usage, "checkpoint_digest": checkpoint["checkpoint_digest"], "outputs_digest": digest_json(result.outputs)})
                context[method_name] = result.outputs
            current = self.state_store.load(run_id)
            current = self.state_store.transition(run_id=run_id, expected_state=RunState.PUBLISHING, target_state=RunState.COMPLETED, owner_id=owner_id, fencing_token=fencing_token, expected_revision=current["revision"], reason="all phases completed")
            self.evidence_store.add_json(logical_name="run/phase-records.json", value=records, producer_environment=str(authority["environment_id"]))
            self.evidence_store.seal({"run_id": run_id, "tenant_id": authority["tenant_id"], "candidate_digest": run["candidate_digest"], "plan_digest": run["plan_digest"], "final_state": current["state"]})
            self.budget_ledger.close(run_id)
            return {"status": "COMPLETED", "phases": records, "evidence": self.evidence_store.verify()}
        except Exception as exc:
            current = self.state_store.load(run_id); state = RunState(current["state"])
            if state not in {RunState.COMPLETED, RunState.CANCELLED, RunState.FAILED, RunState.BLOCKED}:
                try:
                    self.state_store.transition(run_id=run_id, expected_state=state, target_state=RunState.FAILED, owner_id=owner_id, fencing_token=fencing_token, expected_revision=current["revision"], reason=f"runtime failure: {type(exc).__name__}")
                except Exception: pass
            try: adapter.compensate(context)
            finally: adapter.cleanup(context)
            raise
