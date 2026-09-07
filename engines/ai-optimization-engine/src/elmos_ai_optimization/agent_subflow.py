"""Bounded agent subflow state machine for evidence teaching and repair."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .contracts import (
    ActionIntent,
    BudgetExceededError,
    ContractError,
    Receipt,
    TrustedScope,
    canonical_digest,
)


@dataclass(frozen=True)
class SubflowCheckpoint:
    run_ref: str
    graph_version: str
    step_index: int
    state: str  # 'INIT' | 'EVIDENCE_PACKED' | 'ACTION_PROPOSED' | 'DONE' | 'BLOCKED' | 'FAILED'
    state_hash: str
    evidence_refs: tuple[str, ...]
    proposed_intent: ActionIntent | None = None


class BoundedAgentSubflow:
    """Bounded, stateful subflow for guided diagnosis and repair."""

    def __init__(
        self,
        max_steps: int = 5,
        max_rounds: int = 3,
    ) -> None:
        self.max_steps = max_steps
        self.max_rounds = max_rounds
        self._checkpoints: dict[str, SubflowCheckpoint] = {}

    def init_subflow(
        self,
        run_ref: str,
        graph_version: str,
        evidence_refs: Sequence[str],
    ) -> SubflowCheckpoint:
        state_hash = canonical_digest({"run_ref": run_ref, "step": 0, "evidence": list(evidence_refs)})
        cp = SubflowCheckpoint(
            run_ref=run_ref,
            graph_version=graph_version,
            step_index=0,
            state="INIT",
            state_hash=state_hash,
            evidence_refs=tuple(evidence_refs),
            proposed_intent=None,
        )
        self._checkpoints[run_ref] = cp
        return cp

    def advance(
        self,
        scope: TrustedScope,
        run_ref: str,
        new_evidence_refs: Sequence[str] = (),
        proposed_intent: ActionIntent | None = None,
    ) -> SubflowCheckpoint:
        prev = self._checkpoints.get(run_ref)
        if prev is None:
            raise ContractError(f"Subflow checkpoint not found for run_ref: {run_ref}")

        if prev.state in {"DONE", "BLOCKED", "FAILED"}:
            return prev

        new_step = prev.step_index + 1
        if new_step > self.max_steps:
            cp = SubflowCheckpoint(
                run_ref=run_ref,
                graph_version=prev.graph_version,
                step_index=new_step,
                state="BLOCKED",
                state_hash=canonical_digest({"run_ref": run_ref, "status": "max_steps_exceeded"}),
                evidence_refs=prev.evidence_refs,
                proposed_intent=None,
            )
            self._checkpoints[run_ref] = cp
            return cp

        combined_evidence = tuple(sorted(set(prev.evidence_refs) | set(new_evidence_refs)))
        intent_dict = proposed_intent.to_dict() if proposed_intent else None
        new_state_hash = canonical_digest({
            "run_ref": run_ref,
            "step": new_step,
            "evidence": list(combined_evidence),
            "intent": intent_dict,
        })

        # No progress check: no new evidence and no new action proposed
        if combined_evidence == prev.evidence_refs and proposed_intent is None and prev.state != "INIT":
            cp = SubflowCheckpoint(
                run_ref=run_ref,
                graph_version=prev.graph_version,
                step_index=new_step,
                state="FAILED",
                state_hash=canonical_digest({"run_ref": run_ref, "status": "no_progress_detected"}),
                evidence_refs=combined_evidence,
                proposed_intent=None,
            )
            self._checkpoints[run_ref] = cp
            return cp

        next_state = "ACTION_PROPOSED" if proposed_intent else "EVIDENCE_PACKED"
        cp = SubflowCheckpoint(
            run_ref=run_ref,
            graph_version=prev.graph_version,
            step_index=new_step,
            state=next_state,
            state_hash=new_state_hash,
            evidence_refs=combined_evidence,
            proposed_intent=proposed_intent,
        )
        self._checkpoints[run_ref] = cp
        return cp

    def record_receipt(self, run_ref: str, receipt: Receipt) -> SubflowCheckpoint:
        prev = self._checkpoints.get(run_ref)
        if prev is None:
            raise ContractError(f"Subflow checkpoint not found for run_ref: {run_ref}")

        new_state = "DONE" if receipt.state == "SUCCEEDED" else "FAILED"
        cp = SubflowCheckpoint(
            run_ref=run_ref,
            graph_version=prev.graph_version,
            step_index=prev.step_index + 1,
            state=new_state,
            state_hash=canonical_digest({"run_ref": run_ref, "receipt": receipt.to_dict()}),
            evidence_refs=prev.evidence_refs,
            proposed_intent=None,
        )
        self._checkpoints[run_ref] = cp
        return cp

    def get_checkpoint(self, run_ref: str) -> SubflowCheckpoint | None:
        return self._checkpoints.get(run_ref)
