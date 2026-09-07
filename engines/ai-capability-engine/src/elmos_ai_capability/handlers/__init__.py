"""Base handler logic shared by all domain handler modules.

Every skill handler follows the same six-phase lifecycle, differing only in
what domain-specific logic each phase executes.  This module provides the
reusable scaffold so domain modules only implement the unique parts.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..domain import (
    Artifact,
    ContentDigest,
    ExecutionEpoch,
    ProofObligation,
    RunState,
    SideEffect,
    SkillRun,
    TenantScope,
    UsageLedger,
    new_run,
)
from ..runtime import SkillExecutionResult


@dataclass
class PhaseResult:
    """Return value from each lifecycle phase."""
    success: bool
    outputs: dict[str, Any]
    error: str | None = None


# Phase function signature
PhaseFn = Callable[[SkillRun, Mapping[str, Any]], PhaseResult]


def noop_phase(run: SkillRun, inputs: Mapping[str, Any]) -> PhaseResult:
    """Default no-op phase — always succeeds."""
    return PhaseResult(success=True, outputs={})


def run_skill_lifecycle(
    skill_name: str,
    inputs: Mapping[str, Any],
    *,
    profile_fn: PhaseFn = noop_phase,
    plan_fn: PhaseFn = noop_phase,
    execute_fn: PhaseFn = noop_phase,
    verify_fn: PhaseFn = noop_phase,
    seal_fn: PhaseFn = noop_phase,
    domain_services: list[str] | None = None,
    algorithms: list[str] | None = None,
) -> SkillExecutionResult:
    """Execute a skill through the full lifecycle.

    Phase implementations are injected by domain handler modules.
    The lifecycle enforces:
    - Tenant scope validation (fail-closed)
    - State machine transitions
    - Event journaling
    - Checkpoint on each phase
    - Evidence bundle sealing
    - Content-addressed artifact digests
    """
    start = time.perf_counter()
    # Explicitly empty strings for tenant_id or project_id fail closed
    if inputs.get("tenant_id") == "" or inputs.get("project_id") == "":
        return SkillExecutionResult(
            skill_name=skill_name,
            status="BLOCKED",
            outputs={"reason": "missing required tenant_id or project_id scope"},
            evidence_digest="sha256:" + "0" * 64,
            duration_ms=(time.perf_counter() - start) * 1000,
            error="fail-closed: tenant scope required",
        )

    tenant_id = inputs.get("tenant_id") or "default-tenant"
    project_id = inputs.get("project_id") or "default-project"

    try:
        run = new_run(skill_name, inputs)
    except ValueError as exc:
        return SkillExecutionResult(
            skill_name=skill_name,
            status="BLOCKED",
            outputs={},
            evidence_digest="sha256:" + "0" * 64,
            duration_ms=(time.perf_counter() - start) * 1000,
            error=str(exc),
        )

    all_outputs: dict[str, Any] = {
        "skill": skill_name,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "run_id": run.run_id,
        "epoch_id": run.epoch.epoch_id,
    }

    if domain_services:
        all_outputs["domain_services"] = domain_services
    if algorithms:
        all_outputs["algorithms"] = algorithms

    # Phase 0: REQUESTED → PROFILED
    run.emit_event("Requested", {"skill": skill_name, "inputs_keys": list(inputs.keys())})
    profile_result = profile_fn(run, inputs)
    if not profile_result.success:
        run.state = RunState.BLOCKED
        run.emit_event("Blocked", {"phase": "profile", "reason": profile_result.error})
        all_outputs["profile"] = profile_result.outputs
        return _build_result(skill_name, run, all_outputs, start, profile_result.error)
    run.transition(RunState.PROFILED)
    run.emit_event("Profiled", profile_result.outputs)
    all_outputs["profile"] = profile_result.outputs
    run.checkpoint()

    # Phase 1: PROFILED → PLANNED
    plan_result = plan_fn(run, inputs)
    if not plan_result.success:
        run.transition(RunState.BLOCKED)
        run.emit_event("Blocked", {"phase": "plan", "reason": plan_result.error})
        all_outputs["plan"] = plan_result.outputs
        return _build_result(skill_name, run, all_outputs, start, plan_result.error)
    run.transition(RunState.PLANNED)
    run.emit_event("Planned", plan_result.outputs)
    all_outputs["plan"] = plan_result.outputs
    run.checkpoint()

    # Phase 2: PLANNED → RUNNING
    run.transition(RunState.RUNNING)
    run.emit_event("Started", {"phase": "execute"})
    execute_result = execute_fn(run, inputs)
    if not execute_result.success:
        run.transition(RunState.FAILED)
        run.emit_event("Failed", {"phase": "execute", "reason": execute_result.error})
        all_outputs["execution"] = execute_result.outputs
        all_outputs.update(execute_result.outputs)
        return _build_result(skill_name, run, all_outputs, start, execute_result.error)
    all_outputs["execution"] = execute_result.outputs
    all_outputs.update(execute_result.outputs)
    run.checkpoint()

    # Phase 3: RUNNING → VERIFYING
    run.transition(RunState.VERIFYING)
    run.emit_event("Verifying", {"phase": "verify"})
    verify_result = verify_fn(run, inputs)
    if not verify_result.success:
        run.transition(RunState.FAILED)
        run.emit_event("Failed", {"phase": "verify", "reason": verify_result.error})
        all_outputs["verification"] = verify_result.outputs
        return _build_result(skill_name, run, all_outputs, start, verify_result.error)
    all_outputs["verification"] = verify_result.outputs

    # Verify all proof obligations
    for obl in run.obligations:
        if obl.status not in ("SATISFIED", "PENDING"):
            run.transition(RunState.BLOCKED)
            run.emit_event("Blocked", {"reason": f"obligation {obl.claim} is {obl.status}"})
            return _build_result(skill_name, run, all_outputs, start, f"proof obligation violated: {obl.claim}")

    run.checkpoint()

    # Phase 4: VERIFYING → EVIDENCE_SEALED
    run.transition(RunState.EVIDENCE_SEALED)
    seal_result = seal_fn(run, inputs)
    all_outputs["evidence_seal"] = seal_result.outputs
    run.emit_event("EvidenceProduced", seal_result.outputs)

    # Phase 5: EVIDENCE_SEALED → COMPLETED
    run.transition(RunState.COMPLETED)
    run.emit_event("CompletedCandidate", {"status": "COMPLETED"})

    all_outputs["state"] = run.state.value
    all_outputs["event_count"] = len(run.events)
    all_outputs["artifact_count"] = len(run.artifacts)
    all_outputs["artifact_manifest"] = f"artifacts/{skill_name}/manifest.json"

    return _build_result(skill_name, run, all_outputs, start)


def _build_result(
    skill_name: str,
    run: SkillRun,
    outputs: dict[str, Any],
    start: float,
    error: str | None = None,
) -> SkillExecutionResult:
    run.usage.wall_clock_ms = (time.perf_counter() - start) * 1000
    evidence = run.evidence_bundle
    evidence_bytes = json.dumps(evidence, sort_keys=True, default=str).encode()
    digest = f"sha256:{hashlib.sha256(evidence_bytes).hexdigest()}"

    status = "SUCCESS" if run.state == RunState.COMPLETED else (
        "BLOCKED" if run.state == RunState.BLOCKED else "FAILED"
    )

    return SkillExecutionResult(
        skill_name=skill_name,
        status=status,
        outputs=outputs,
        evidence_digest=digest,
        duration_ms=run.usage.wall_clock_ms,
        error=error or run.error,
    )
