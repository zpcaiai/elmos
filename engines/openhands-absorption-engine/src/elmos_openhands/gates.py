"""Hooks, verification gates and requirement-to-evidence traceability."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .errors import ContractViolation
from .models import CompletionProposal, Identity, digest_of, utc_now

Hook = Callable[[Identity, Mapping[str, Any]], None]


@dataclass(frozen=True, slots=True)
class GateCheck:
    name: str
    required: bool = True
    status: str = "not_run"
    evidence_refs: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"pass", "fail", "skip", "error", "not_run"}:
            raise ContractViolation("invalid gate status")


@dataclass(frozen=True, slots=True)
class GateDecision:
    status: str
    checks: tuple[GateCheck, ...]
    evidence_complete: bool
    digest: str
    evaluated_at: str = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": [{"name": c.name, "required": c.required, "status": c.status, "evidence_refs": list(c.evidence_refs), "reason": c.reason} for c in self.checks],
            "evidence_complete": self.evidence_complete,
            "digest": self.digest,
            "evaluated_at": self.evaluated_at,
            "certification": "NOT_CERTIFIED",
        }


class HookRegistry:
    PHASES = (
        "pre_run", "post_run", "pre_context", "post_context", "pre_provider", "post_provider",
        "pre_tool", "post_tool", "pre_checkpoint", "post_checkpoint", "pre_completion",
        "post_completion", "on_failure", "on_cancel",
    )

    def __init__(self) -> None:
        self._hooks: dict[str, list[tuple[int, str, Hook]]] = {phase: [] for phase in self.PHASES}

    def register(self, phase: str, name: str, hook: Hook, *, order: int = 100) -> None:
        if phase not in self._hooks or not name:
            raise ContractViolation("unknown hook phase")
        if any(existing_name == name for _, existing_name, _ in self._hooks[phase]):
            raise ContractViolation("hook name is already registered in phase")
        self._hooks[phase].append((order, name, hook))
        self._hooks[phase].sort(key=lambda item: (item[0], item[1]))

    def run(self, phase: str, identity: Identity, payload: Mapping[str, Any]) -> None:
        for _, _, hook in self._hooks.get(phase, []):
            hook(identity, payload)

    def names(self, phase: str) -> tuple[str, ...]:
        return tuple(item[1] for item in self._hooks.get(phase, []))


class TraceabilityGraph:
    def __init__(self) -> None:
        self._edges: set[tuple[str, str, str]] = set()

    def link(self, requirement: str, change: str, evidence: str) -> None:
        if not requirement or not change or not evidence:
            raise ContractViolation("traceability edge requires requirement, change and evidence")
        self._edges.add((requirement, change, evidence))

    def missing_for(self, requirements: Iterable[str]) -> tuple[str, ...]:
        linked = {requirement for requirement, _, _ in self._edges}
        return tuple(sorted(set(requirements) - linked))

    def as_dict(self) -> dict[str, Any]:
        return {"edges": [{"requirement": r, "change": c, "evidence": e} for r, c, e in sorted(self._edges)]}


class CompletionGateEngine:
    """The only component allowed to convert a proposal into success."""

    DEFAULT_REQUIRED = (
        "repository_cleanliness_or_documented_diff",
        "build_or_compile",
        "unit_tests",
        "changed_scope_integration_tests",
        "lint_and_typecheck",
        "security_scan",
        "requirement_traceability",
        "evidence_pack",
    )

    def __init__(self, *, required: Iterable[str] = DEFAULT_REQUIRED, hooks: HookRegistry | None = None, evidence_verifier: Callable[[str], bool] | None = None) -> None:
        self.required = tuple(dict.fromkeys(required))
        self.hooks = hooks or HookRegistry()
        self.evidence_verifier = evidence_verifier

    def evaluate(self, identity: Identity, proposal: CompletionProposal, checks: Mapping[str, str], evidence: Mapping[str, Any], *, trace: TraceabilityGraph | None = None) -> GateDecision:
        self.hooks.run("pre_completion", identity, {"proposal": proposal, "checks": checks, "evidence": evidence})
        rows: list[GateCheck] = []
        for name in self.required:
            status = str(checks.get(name, "not_run"))
            references = tuple(str(item) for item in evidence.get(name, ())) if isinstance(evidence.get(name, ()), (tuple, list)) else ()
            rows.append(GateCheck(name, True, status, references, None if status == "pass" else "mandatory check is not passing"))
        if trace is not None:
            missing = trace.missing_for(proposal.requirement_refs)
            trace_check = GateCheck("requirement_traceability", True, "pass" if not missing else "fail", ("traceability:" + digest_of(trace.as_dict()),) if not missing else (), None if not missing else "missing: " + ",".join(missing))
            rows = [trace_check if row.name == "requirement_traceability" else row for row in rows]
        references = tuple(reference for check in rows if check.required for reference in check.evidence_refs)
        verifier = self.evidence_verifier
        evidence_complete = False
        if verifier is None:
            rows.append(GateCheck("evidence_verifier", True, "not_run", (), "independent evidence verifier is not configured"))
        else:
            evidence_complete = all(check.status == "pass" and bool(check.evidence_refs) for check in rows if check.required) and all(verifier(reference) for reference in references)
        status = "pass" if evidence_complete else "blocked"
        body = {"run_id": identity.run_id, "proposal": proposal.summary, "checks": [{"name": check.name, "status": check.status, "evidence_refs": check.evidence_refs} for check in rows], "evidence_complete": evidence_complete}
        decision = GateDecision(status, tuple(rows), evidence_complete, digest_of(body))
        self.hooks.run("post_completion", identity, decision.as_dict())
        return decision


@dataclass(frozen=True, slots=True)
class GateProfile:
    name: str
    required: tuple[str, ...]
    conditional: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    zero_tolerance: frozenset[str] = frozenset({"security_scan", "tenant_isolation", "evidence_pack"})
    max_repairs: int = 2

    def __post_init__(self) -> None:
        if not self.name or not self.required or self.max_repairs < 0 or len(self.required) != len(set(self.required)):
            raise ContractViolation("gate profile is invalid")

    def checks_for(self, change_flags: Iterable[str]) -> tuple[str, ...]:
        checks = list(self.required)
        for flag in sorted(set(change_flags)):
            checks.extend(self.conditional.get(flag, ()))
        return tuple(dict.fromkeys(checks))


DEFAULT_GATE_PROFILE = GateProfile(
    "default",
    CompletionGateEngine.DEFAULT_REQUIRED,
    {
        "ui_change": ("browser_e2e", "screenshot_or_video_evidence", "console_error_check"),
        "database_change": ("migration_forward", "migration_rollback_or_compensation", "data_compatibility"),
        "performance_sensitive": ("performance_regression",),
        "production_release": ("smoke_test", "canary_guard", "rollback_ready"),
    },
)


@dataclass(frozen=True, slots=True)
class GateExecution:
    name: str
    status: str
    evidence_refs: tuple[str, ...]
    metrics: Mapping[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"pass", "fail", "error", "not_run"}:
            raise ContractViolation("gate execution status is invalid")


class GateRunner(Protocol):
    def __call__(self, identity: Identity, proposal: CompletionProposal) -> GateExecution: ...


class VerificationExecutor:
    def __init__(self, runners: Mapping[str, GateRunner]) -> None:
        self.runners = dict(runners)

    def run(self, identity: Identity, proposal: CompletionProposal, checks: Iterable[str]) -> Mapping[str, GateExecution]:
        result: dict[str, GateExecution] = {}
        for name in checks:
            runner = self.runners.get(name)
            if runner is None:
                result[name] = GateExecution(name, "not_run", (), reason="gate runner is not configured")
                continue
            try:
                value = runner(identity, proposal)
            except Exception as error:  # noqa: BLE001 - gate errors are recorded as bounded evidence
                value = GateExecution(name, "error", (), reason=f"{type(error).__name__}: {str(error)[:300]}")
            if value.name != name:
                raise ContractViolation("gate runner returned another gate identity")
            result[name] = value
        return result


@dataclass(frozen=True, slots=True)
class GateWaiver:
    waiver_id: str
    identity: Identity
    gate_name: str
    actor: str
    reason: str
    expires_at: float
    state: str


class WaiverStore:
    def __init__(self, database: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("CREATE TABLE IF NOT EXISTS gate_waivers(waiver_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,node_id TEXT NOT NULL,agent_id TEXT,gate_name TEXT NOT NULL,actor TEXT NOT NULL,reason TEXT NOT NULL,expires_at REAL NOT NULL,state TEXT NOT NULL)")

    def close(self) -> None:
        self._connection.close()

    def create(self, identity: Identity, gate_name: str, *, actor: str, reason: str, expires_at: float, zero_tolerance: Iterable[str] = ()) -> GateWaiver:
        if gate_name in set(zero_tolerance):
            raise ContractViolation("zero-tolerance gate cannot be waived")
        if not gate_name or not actor or not reason or expires_at <= time.time():
            raise ContractViolation("gate waiver is invalid")
        waiver_id = "waiver_" + digest_of({"identity": identity.scope(), "gate": gate_name, "actor": actor, "reason": reason, "expires_at": expires_at}).split(":", 1)[1]
        self._connection.execute("INSERT INTO gate_waivers VALUES(?,?,?,?,?,?,?,?,?,?,?, 'active')", (waiver_id, *identity.scope(), identity.agent_id, gate_name, actor, reason, expires_at))
        return GateWaiver(waiver_id, identity, gate_name, actor, reason, expires_at, "active")

    def valid(self, identity: Identity, gate_name: str, *, now: float | None = None) -> GateWaiver | None:
        now = time.time() if now is None else now
        row = self._connection.execute("SELECT * FROM gate_waivers WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND node_id=? AND gate_name=? AND state='active' AND expires_at>? ORDER BY expires_at LIMIT 1", (*identity.scope(), gate_name, now)).fetchone()
        if row is None:
            return None
        return GateWaiver(row["waiver_id"], identity, row["gate_name"], row["actor"], row["reason"], float(row["expires_at"]), row["state"])

    def revoke(self, identity: Identity, waiver_id: str) -> None:
        self._connection.execute("UPDATE gate_waivers SET state='revoked' WHERE waiver_id=? AND tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND node_id=?", (waiver_id, *identity.scope()))


@dataclass(frozen=True, slots=True)
class RepairOutcome:
    attempts: int
    final_checks: Mapping[str, GateExecution]
    status: str
    escalation_reason: str | None


class BoundedRepairLoop:
    def __init__(self, profile: GateProfile) -> None:
        self.profile = profile

    def run(
        self,
        checks: Mapping[str, GateExecution],
        repair: Callable[[int, tuple[str, ...]], Mapping[str, GateExecution]],
    ) -> RepairOutcome:
        current = dict(checks)
        attempts = 0
        while attempts < self.profile.max_repairs:
            failed = tuple(sorted(name for name, result in current.items() if result.status in {"fail", "error"}))
            if not failed:
                break
            attempts += 1
            updates = repair(attempts, failed)
            if any(name not in failed for name in updates):
                raise ContractViolation("repair loop may update only failing checks")
            current.update(updates)
        failed = tuple(sorted(name for name, result in current.items() if result.status != "pass"))
        return RepairOutcome(attempts, current, "pass" if not failed else "blocked", None if not failed else "repair budget exhausted or checks remain non-passing: " + ",".join(failed))


class ProfiledCompletionGateEngine:
    def __init__(self, profile: GateProfile, *, hooks: HookRegistry | None = None, waivers: WaiverStore | None = None, evidence_verifier: Callable[[str], bool] | None = None) -> None:
        self.profile, self.hooks, self.waivers, self.evidence_verifier = profile, hooks or HookRegistry(), waivers, evidence_verifier

    def evaluate(self, identity: Identity, proposal: CompletionProposal, executions: Mapping[str, GateExecution], *, change_flags: Iterable[str], trace: TraceabilityGraph | None = None) -> GateDecision:
        required = self.profile.checks_for(change_flags)
        self.hooks.run("pre_completion", identity, {"proposal": proposal, "required": required})
        checks: list[GateCheck] = []
        for name in required:
            execution = executions.get(name, GateExecution(name, "not_run", (), reason="required gate was not executed"))
            status = execution.status
            reason = execution.reason
            waiver = None if self.waivers is None or name in self.profile.zero_tolerance else self.waivers.valid(identity, name)
            if status == "fail" and waiver is not None:
                status = "skip"
                reason = f"waived by {waiver.actor}: {waiver.reason}"
            checks.append(GateCheck(name, True, status, execution.evidence_refs, reason))
        if trace is not None and "requirement_traceability" in required:
            missing = trace.missing_for(proposal.requirement_refs)
            replacement = GateCheck("requirement_traceability", True, "pass" if not missing else "fail", ("traceability:" + digest_of(trace.as_dict()),) if not missing else (), None if not missing else "missing: " + ",".join(missing))
            checks = [replacement if item.name == "requirement_traceability" else item for item in checks]
        references = tuple(reference for item in checks for reference in item.evidence_refs)
        independently_verified = self.evidence_verifier is not None and bool(references) and all(self.evidence_verifier(reference) for reference in references)
        evidence_complete = independently_verified and all(item.status in {"pass", "skip"} and (item.status == "skip" or bool(item.evidence_refs)) for item in checks)
        status = "pass" if evidence_complete else "blocked"
        body = {"identity": identity.scope(), "proposal": proposal.summary, "profile": self.profile.name, "checks": [{"name": item.name, "status": item.status, "evidence": item.evidence_refs} for item in checks], "evidence_complete": evidence_complete}
        decision = GateDecision(status, tuple(checks), evidence_complete, digest_of(body))
        self.hooks.run("post_completion", identity, decision.as_dict())
        return decision
