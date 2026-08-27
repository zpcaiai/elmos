"""Hooks, verification gates and requirement-to-evidence traceability."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

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
    def __init__(self) -> None:
        self._hooks: dict[str, list[tuple[int, str, Hook]]] = {"pre_tool": [], "post_tool": [], "pre_completion": [], "post_completion": []}

    def register(self, phase: str, name: str, hook: Hook, *, order: int = 100) -> None:
        if phase not in self._hooks or not name:
            raise ContractViolation("unknown hook phase")
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
