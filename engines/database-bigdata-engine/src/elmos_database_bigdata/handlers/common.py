"""Shared pure plan compiler; individual Skills retain unique entry points."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..canonical import canonical_digest
from ..catalog import BLOCKER_DEFINITIONS, SkillContract
from ..contracts import RuntimeRequest


def compile_bounded_plan(
    contract: SkillContract,
    request: RuntimeRequest,
    installed_record: Mapping[str, Any],
    *,
    focus: Sequence[str],
) -> dict[str, Any]:
    """Compile a plan without claiming any source task was executed."""

    outputs = installed_record["source_outputs"]
    blockers = [
        {"code": code, "reason": BLOCKER_DEFINITIONS[code]}
        for code in contract.blockers
    ]
    task_ledger = [
        {
            "task_id": task_id,
            "planning_state": "NOT_RUN",
            "skill_implementation_state": "DECLARED",
            "runtime_evidence": "NOT_RUN",
            "provider_runtime_evidence": "NOT_RUN",
            "external_evidence_status": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
            "blocker_codes": list(contract.blockers),
        }
        for task_id in contract.task_ids
    ]
    artifacts = [
        {
            "declared_output": output,
            "artifact_state": "DECLARED_OUTPUT",
            "content_state": "NOT_GENERATED",
            "skill_implementation_state": "DECLARED",
            "runtime_evidence": "NOT_RUN",
            "provider_runtime_evidence": "NOT_RUN",
            "external_evidence_status": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
        }
        for output in outputs
    ]
    hard_constraints = request.inputs.get("hard_constraints")
    unknowns = request.inputs.get("unknowns")
    return {
        "state": "BLOCKED",
        "code": "DECLARED_SKILL_PLAN_SKELETON",
        "planning_state": "SKELETON_ONLY",
        "plan_skeleton_scope": "IDENTITIES_OUTPUTS_AND_EVIDENCE_GAPS_ONLY",
        "local_primitives": list(contract.local_primitives),
        "focus": list(focus),
        "input_digest": canonical_digest(request.inputs),
        "request_binding_digest": request.binding_digest(),
        "decision_policy": {
            "hard_constraints": "PRESERVED_UNEVALUATED",
            "hard_constraints_present": "hard_constraints" in request.inputs,
            "hard_constraints_digest": canonical_digest(hard_constraints),
            "unknowns": "PRESERVED_UNRESOLVED",
            "unknowns_present": "unknowns" in request.inputs,
            "unknowns_digest": canonical_digest(unknowns),
            "recommendation_state": "BLOCKED_PENDING_EXACT_EVIDENCE",
            "constraint_relaxation_performed": False,
        },
        "artifacts": artifacts,
        "task_ledger": task_ledger,
        "unresolved_evidence_gates": blockers,
        "context_assurance": "CALLER_ASSERTED_UNVERIFIED",
        "idempotency_semantics": "DIGEST_BINDING_ONLY_NO_REPLAY_STORE",
        "external_effects_performed": False,
        "skill_implementation_state": "DECLARED",
        "repository_handler_runtime_evidence": "NOT_RUN",
        "provider_runtime_evidence": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
    }


__all__ = ["compile_bounded_plan"]
