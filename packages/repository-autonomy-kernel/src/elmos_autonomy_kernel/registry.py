"""Capability registry and dispatch.

Thirty-one capabilities are declared here as data.  A capability is only
callable once a module has bound a handler to it, so a declared-but-unbound
capability fails as ``NOT_APPLICABLE`` with a specific reason rather than
looking like a working feature.

Dispatch is the single choke point where timing, failure normalisation and the
success/partial/interrupted separation are enforced, so no capability can
accidentally report a partial outcome as a success.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .contracts import Observability, SkillResult, Status, require_identifier
from .errors import KernelError, not_applicable

__all__ = [
    "SkillDescriptor",
    "DESCRIPTORS",
    "register",
    "dispatch",
    "handler_for",
    "bound_skills",
    "unbound_skills",
]

Handler = Callable[[Mapping[str, Any]], Mapping[str, Any]]

_HANDLERS: dict[str, Handler] = {}


@dataclass(frozen=True, slots=True)
class SkillDescriptor:
    """Static declaration of one capability."""

    skill_id: str
    title: str
    priority: str
    capability_pack: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    invariants: tuple[str, ...]
    gates: tuple[str, ...]
    version: str = "2.0.0"
    module: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.skill_id, "skill_id")
        if self.priority not in {"P0", "P1", "P2"}:
            raise ValueError(f"unknown priority {self.priority!r}")


def _d(skill_id, title, priority, pack, inputs, outputs, invariants, gates, module, notes=""):
    return SkillDescriptor(
        skill_id=skill_id, title=title, priority=priority, capability_pack=pack,
        inputs=tuple(inputs), outputs=tuple(outputs), invariants=tuple(invariants),
        gates=tuple(gates), module=module, notes=notes,
    )


_ALL: tuple[SkillDescriptor, ...] = (
    # --- P0 ------------------------------------------------------------------
    _d("task-spec-delta-compiler", "Task Spec Delta Compiler", "P0", "P02",
       ("intent", "repository-snapshot", "prior-task-spec"),
       ("task-spec", "spec-delta", "open-questions"),
       ("a spec is versioned and content addressed",
        "an ambiguity becomes an open question, never a guess"),
       ("spec-is-deterministic", "delta-is-minimal", "ambiguity-is-surfaced"),
       "taskspec"),
    _d("durable-run-orchestrator", "Durable Run Orchestrator", "P0", "P01",
       ("task-spec", "workflow-definition", "repository-snapshot", "budget", "policy-snapshot"),
       ("run", "step-runs", "run-events", "checkpoints", "rollback-plan", "progress-snapshot"),
       ("the transcript is not execution truth",
        "the event log can rebuild current state",
        "cancellation passes a safe point",
        "PARTIAL never maps to SUCCEEDED"),
       ("state-machine-valid", "event-replay-valid", "idempotency-covered", "recovery-tested"),
       "orchestrator"),
    _d("execution-authority-kernel", "Execution Authority Kernel", "P0", "P01",
       ("environment", "workspace", "permission-profile", "policy-snapshot"),
       ("execution-authority", "authority-decision"),
       ("authority is owned by the environment, never by a conversation",
        "every write carries a fencing token"),
       ("scope-enforced", "thread-global-authority-rejected", "fencing-required-for-writes"),
       "authority"),
    _d("typed-tool-runtime", "Typed Tool Runtime", "P0", "P01",
       ("tool-descriptor", "tool-call", "execution-authority"),
       ("tool-result", "tool-events"),
       ("an unknown tool is denied, never guessed",
        "arguments are validated before any side effect"),
       ("schema-enforced", "unknown-tool-denied", "side-effects-declared"),
       "tools"),
    _d("policy-hook-kernel", "Policy Hook Kernel", "P0", "P01",
       ("policy-snapshot", "hook-point", "subject"),
       ("policy-decision", "obligations"),
       ("deny wins over every other decision",
        "an empty policy set is a deny, not an allow"),
       ("deny-precedence", "fail-closed-on-empty", "decision-is-explainable"),
       "policy"),
    _d("two-phase-secretless-sandbox", "Two-Phase Secretless Sandbox", "P0", "P01",
       ("sandbox-profile", "command", "execution-authority"),
       ("execution-result", "sandbox-evidence"),
       ("network is denied unless explicitly granted",
        "a secret never enters a prompt, log or artifact"),
       ("network-default-deny", "secret-never-materialised", "escape-attempt-denied"),
       "sandbox"),
    _d("workspace-lease-fencing", "Workspace Lease Fencing", "P0", "P01",
       ("workspace", "owner", "lease-request"),
       ("lease", "fencing-token"),
       ("a superseded owner can never write again",
        "tokens are monotonic per resource"),
       ("stale-owner-rejected", "token-monotonic", "expiry-enforced"),
       "leasing"),
    _d("artifact-evidence-protocol", "Artifact & Evidence Protocol", "P0", "P02",
       ("artifact", "producer", "claim"),
       ("evidence", "evidence-bundle", "verification-outcome"),
       ("a claim without evidence is not a claim",
        "evidence binds to the exact input digests it was produced from"),
       ("digest-verified", "binding-complete", "tamper-detected"),
       "evidence"),
    _d("repository-census", "Repository Census", "P0", "P02",
       ("repository-snapshot",),
       ("census", "language-mix", "hotspots", "risk-surface"),
       ("a census is reproducible from the snapshot alone",),
       ("deterministic", "snapshot-bound", "counts-are-defined"),
       "census"),
    _d("incremental-semantic-index", "Incremental Semantic Index", "P0", "P02",
       ("repository-snapshot", "prior-index", "change-set"),
       ("semantic-index", "index-delta"),
       ("an incremental update equals a full rebuild",),
       ("incremental-equals-full", "delta-is-minimal", "stale-entries-evicted"),
       "semindex"),
    _d("semantic-ir-compiler", "Semantic IR Compiler", "P0", "P03",
       ("source-unit", "language-profile"),
       ("semantic-ir", "rejection-reason"),
       ("what the subset cannot represent is rejected, never approximated",),
       ("subset-boundary-explicit", "round-trip-stable", "rejection-is-coded"),
       "semir"),
    _d("changegraph-vcs", "ChangeGraph VCS", "P0", "P03",
       ("repository-snapshot", "change-set"),
       ("change-graph", "conflict-report", "apply-plan"),
       ("a change graph is a DAG",
        "two changes touching one region must not silently merge"),
       ("dag-valid", "conflict-detected", "apply-is-idempotent"),
       "changegraph"),
    _d("validation-dag", "Validation DAG", "P0", "P05",
       ("validation-plan", "repository-snapshot", "budget"),
       ("validation-result", "gate-results", "coverage"),
       ("a skipped check is reported as skipped, never as passed",),
       ("dag-valid", "skip-is-visible", "budget-honoured"),
       "validation"),
    _d("independent-verification-mesh", "Independent Verification Mesh", "P0", "P04",
       ("claim", "evidence", "verifier-set"),
       ("verdicts", "consensus", "dissent"),
       ("a verifier must not verify its own output",
        "dissent is preserved, not averaged away"),
       ("independence-enforced", "dissent-recorded", "quorum-defined"),
       "vmesh"),
    _d("evidence-release-gate", "Evidence Release Gate", "P0", "P05",
       ("gate-results", "findings", "rollback-plan", "health"),
       ("acceptance-decision",),
       ("only evidence decides release",
        "an open P0/P1 finding blocks"),
       ("evidence-required", "rollback-required", "health-required"),
       "releasegate"),
    _d("contract-compatibility-engine", "Contract Compatibility Engine", "P0", "P03",
       ("baseline-surface", "candidate-surface", "compatibility-policy"),
       ("api-diff", "compatibility-decision", "deprecation-plan"),
       ("a removal is breaking until proven otherwise",),
       ("breaking-detected", "policy-applied", "plan-is-actionable"),
       "compat"),
    # --- P1 ------------------------------------------------------------------
    _d("prefix-stable-context-planner", "Prefix-Stable Context Planner", "P1", "P06",
       ("context-request", "budget"),
       ("prompt-plan", "cache-breakpoints", "eviction-report"),
       ("a stable prefix must not be reordered by later additions",),
       ("prefix-stable", "budget-honoured", "eviction-explained"),
       "contextplan"),
    _d("lazy-tool-loader", "Lazy Tool Loader", "P1", "P01",
       ("tool-catalogue", "task-profile"),
       ("loaded-tools", "deferred-tools", "load-decision"),
       ("a deferred tool is not callable until loaded",),
       ("deferred-not-callable", "selection-is-explainable", "budget-honoured"),
       "toolloader"),
    _d("model-state-continuity", "Model State Continuity", "P1", "P06",
       ("context-ledger", "compaction-policy"),
       ("checkpoint", "restored-state", "continuity-report"),
       ("a restored state must be replayable to the same decisions",),
       ("restore-equals-live", "compaction-is-lossless-for-decisions", "content-free"),
       "continuity"),
    _d("multi-agent-worktree-coordinator", "Multi-Agent Worktree Coordinator", "P1", "P04",
       ("task-dag", "workspace", "agent-pool"),
       ("waves", "path-locks", "assignment"),
       ("two agents never own overlapping paths in one wave",),
       ("no-path-overlap", "lease-per-worktree", "wave-order-respected"),
       "worktree"),
    _d("phase-aware-model-router", "Phase-Aware Model Router", "P1", "P06",
       ("task-profile", "model-registry", "routing-policy", "budget"),
       ("route-decision", "fallback-chain"),
       ("an unknown model is never routed to",),
       ("policy-applied", "fallback-defined", "cost-bounded"),
       "router"),
    _d("layered-cache-fabric", "Layered Cache Fabric", "P1", "P06",
       ("cache-key-inputs", "layer-config"),
       ("cache-key", "lookup-result", "admission-decision"),
       ("an incomplete cache key is never used",
        "a hit must be provably the same input"),
       ("key-complete", "no-false-hit", "admission-explained"),
       "cache"),
    _d("cost-eta-observability", "Cost & ETA Observability", "P1", "P06",
       ("telemetry", "budget", "plan"),
       ("cost-report", "eta", "human-equivalent"),
       ("machine wall-clock and human-equivalent effort are never mixed",
        "an unmeasured quantity is reported as unmeasured, not as zero"),
       ("units-separated", "no-silent-zero", "budget-honoured"),
       "costeta"),
    _d("tiered-security-assurance", "Tiered Security Assurance", "P1", "P05",
       ("change-set", "assurance-tier", "findings"),
       ("assurance-result", "required-controls"),
       ("a higher tier can never require fewer controls",),
       ("tier-monotonic", "controls-enforced", "waiver-is-recorded"),
       "security"),
    _d("session-time-travel", "Session Time Travel", "P1", "P01",
       ("run-events", "target-point"),
       ("restored-run", "fork", "divergence-report"),
       ("time travel never mutates the original timeline",),
       ("original-immutable", "fork-is-identified", "replay-is-exact"),
       "timetravel"),
    _d("capability-package-registry", "Capability Package Registry", "P1", "P07",
       ("package", "promotion-request", "evaluation-report"),
       ("registry-entry", "promotion-decision", "revocation"),
       ("promotion requires evidence at the tier being entered",),
       ("evidence-required", "revocation-propagates", "version-immutable"),
       "packreg"),
    # --- P2 ------------------------------------------------------------------
    _d("demonstration-to-skill", "Demonstration to Skill", "P2", "P07",
       ("demonstration-trace", "generalisation-policy"),
       ("skill-draft", "preconditions", "counterexamples"),
       ("a draft is never auto-promoted",),
       ("draft-not-promoted", "preconditions-explicit", "counterexample-required"),
       "demo2skill"),
    _d("auto-improvement-inbox-and-skill-curator", "Auto-Improvement Inbox & Skill Curator",
       "P2", "P07",
       ("incident", "telemetry", "existing-skills"),
       ("inbox-item", "curation-decision", "duplicate-report"),
       ("a duplicate proposal merges, never forks",),
       ("duplicate-detected", "decision-is-recorded", "no-auto-promotion"),
       "curator"),
    _d("agent-arena", "Agent Arena", "P2", "P07",
       ("task-set", "contestants", "scoring-policy"),
       ("match-results", "leaderboard", "anti-cheat-report"),
       ("a contestant must not see the grader's reference",),
       ("isolation-enforced", "scoring-deterministic", "cheating-detected"),
       "arena"),
    _d("repository-model-elo", "Repository Model ELO", "P2", "P07",
       ("match-results", "rating-policy"),
       ("ratings", "uncertainty", "ranking"),
       ("a rating without enough matches reports its uncertainty",),
       ("rating-converges", "uncertainty-reported", "order-independent-enough"),
       "elo"),
    _d("repository-gym-golden-routes", "Repository Gym & Golden Routes", "P2", "P07",
       ("route-definition", "repository-fixture", "acceptance"),
       ("route-run", "score", "regression-report"),
       ("a route's acceptance is fixed before the run",),
       ("acceptance-frozen", "run-reproducible", "regression-detected"),
       "gym"),
)

DESCRIPTORS: dict[str, SkillDescriptor] = {item.skill_id: item for item in _ALL}

if len(DESCRIPTORS) != 31:
    raise RuntimeError(
        f"the autonomy kernel declares exactly 31 capabilities, found {len(DESCRIPTORS)}"
    )


def register(skill_id: str) -> Callable[[Handler], Handler]:
    """Bind a handler to a declared capability."""

    if skill_id not in DESCRIPTORS:
        raise KeyError(f"unknown capability {skill_id!r}")

    def decorate(handler: Handler) -> Handler:
        if skill_id in _HANDLERS and _HANDLERS[skill_id] is not handler:
            raise RuntimeError(f"capability {skill_id!r} already has a handler")
        _HANDLERS[skill_id] = handler
        return handler

    return decorate


def handler_for(skill_id: str) -> Handler | None:
    return _HANDLERS.get(skill_id)


def bound_skills() -> tuple[str, ...]:
    return tuple(sorted(_HANDLERS))


def unbound_skills() -> tuple[str, ...]:
    return tuple(sorted(set(DESCRIPTORS) - set(_HANDLERS)))


def dispatch(skill_id: str, request: Mapping[str, Any], *,
             observability: Observability | None = None) -> SkillResult:
    """Invoke a capability and normalise its outcome.

    A handler may return outputs, raise :class:`KernelError`, or raise anything
    else.  The third case is the dangerous one: an unexpected exception is
    converted into a terminal, non-retryable failure rather than being allowed
    to look like an empty success.
    """

    descriptor = DESCRIPTORS.get(skill_id)
    if descriptor is None:
        error = KernelError(
            code="NOT_APPLICABLE",
            message=f"unknown capability {skill_id!r}",
            recommended_action="check the capability id against registry.DESCRIPTORS",
        )
        return SkillResult.failure("unknown-capability", error,
                                   status=Status.NOT_APPLICABLE)

    handler = _HANDLERS.get(skill_id)
    if handler is None:
        return SkillResult.failure(
            skill_id,
            not_applicable("declared but no handler is bound in this build", skill=skill_id),
            status=Status.NOT_APPLICABLE,
        )

    started = time.monotonic_ns()
    try:
        outputs = handler(request)
    except KernelError as exc:
        elapsed = (time.monotonic_ns() - started) // 1_000_000
        status = Status.NOT_APPLICABLE if exc.code == "NOT_APPLICABLE" else Status.FAILED
        if exc.partial:
            status = Status.PARTIAL
        elif exc.interrupted:
            status = Status.INTERRUPTED
        return SkillResult.failure(skill_id, exc, status=status,
                                   machine_wall_clock_ms=elapsed,
                                   observability=observability)
    except Exception as exc:  # noqa: BLE001 - deliberate boundary
        elapsed = (time.monotonic_ns() - started) // 1_000_000
        wrapped = KernelError(
            code="FAILED_TERMINAL",
            message=f"{skill_id} raised an unhandled {type(exc).__name__}: {exc}",
            retryable=False,
            recommended_action="treat as a kernel defect; do not retry blindly",
            details={"exception": type(exc).__name__},
        )
        return SkillResult.failure(skill_id, wrapped, machine_wall_clock_ms=elapsed,
                                   observability=observability)

    elapsed = (time.monotonic_ns() - started) // 1_000_000
    if not isinstance(outputs, Mapping):
        wrapped = KernelError(
            code="ORCHESTRATOR_INCONSISTENT",
            message=f"{skill_id} returned {type(outputs).__name__}, expected a mapping",
            recommended_action="treat as a kernel defect",
        )
        return SkillResult.failure(skill_id, wrapped, machine_wall_clock_ms=elapsed,
                                   observability=observability)

    status = Status.SUCCEEDED
    declared = outputs.get("status")
    if isinstance(declared, Status):
        status = declared
    elif isinstance(declared, str):
        status = Status(declared)
    payload = {key: value for key, value in outputs.items() if key != "status"}
    evidence = tuple(payload.pop("evidenceIds", ()) or ())
    if status is not Status.SUCCEEDED and status is not Status.PARTIAL:
        raise RuntimeError(
            f"{skill_id} declared {status} without raising a KernelError; "
            "a non-success outcome must carry a structured error"
        )
    return SkillResult(
        skill=skill_id,
        status=status,
        outputs=payload,
        evidence_ids=evidence,
        machine_wall_clock_ms=elapsed,
        observability=observability,
    )
