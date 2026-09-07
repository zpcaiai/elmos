"""Skill 10 — service boundaries, message semantics and failure policy.

What this module refuses to pretend
-----------------------------------

A repository snapshot shows the *code*, not the traffic.  Three consequences
are wired into the types here rather than left to a caller's discretion:

* a call site found statically proves the edge *can* happen, never how often
  or under what load, so every :class:`ServiceEdge` carries ``evidence`` and
  the plan reports ``traces_supplied`` — with no traces, hot-path claims are
  ``UNKNOWN``, not "low risk";
* an *absent* retry, timeout or idempotency key is a finding, not a default:
  :func:`audit_call_policies` reports the missing control as a violation
  because "we did not find a timeout" and "there is no timeout" are the same
  thing for a caller that hangs;
* two services reading the same table is coupling whether or not anybody
  wrote it down — :func:`shared_datastores` derives it from the code and
  refuses to let a service-boundary plan claim independence without it.

The plan is a *proposal*.  Nothing here deploys, publishes, or drains: the
outputs are a boundary plan, an event-migration plan, a resilience test
matrix and a runbook, each addressed by digest so an approval can bind to it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .contracts import ContractError, EntityKind, RiskClass, sha256_payload
from .expressions import UNKNOWN, UnknownType
from .index import SemanticIndex
from .workspace import WorkspaceSnapshot


class EdgeKind(StrEnum):
    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"
    DATA_SHARED = "data-shared"


class SplitStrategy(StrEnum):
    BRANCH_BY_ABSTRACTION = "branch-by-abstraction"
    STRANGLER_FIG = "strangler-fig"
    #: Only legitimate when the two sides are already independent.
    DIRECT_EXTRACTION = "direct-extraction"


class WritePattern(StrEnum):
    LOCAL_TRANSACTION = "local-transaction"
    OUTBOX = "transactional-outbox"
    SAGA = "saga-with-compensation"
    TWO_PHASE = "two-phase-commit"


#: Call shapes that cross a process boundary.  Matching one of these is what
#: makes a line "not a local call" for the purposes of the invariant.
_REMOTE_CALL = (
    re.compile(r"\b(?:requests|httpx|aiohttp|axios|fetch)\s*\.\s*(?:get|post|put|patch|delete)\b", re.IGNORECASE),
    re.compile(r"\bhttp(?:s)?://", re.IGNORECASE),
    re.compile(r"\b(?:grpc|Stub|Channel)\b"),
    re.compile(r"\bRestTemplate|WebClient|OkHttpClient|HttpClient\b"),
)
_ASYNC_PUBLISH = (
    re.compile(r"\b(?:publish|produce|send_event|emit|enqueue)\s*\(", re.IGNORECASE),
    re.compile(r"\b(?:kafka|rabbit|sqs|sns|pubsub|nats|kinesis)\b", re.IGNORECASE),
)
_SUBSCRIBE = re.compile(r"\b(?:subscribe|consume|on_message|listener|@KafkaListener)\b", re.IGNORECASE)

#: Start of a new callable in the languages this audit covers.  The retry
#: window is bounded by these, because a ``retry`` four lines below a call may
#: belong to a completely different function.
_BLOCK_START = re.compile(
    r"^\s*(?:async\s+)?(?:def|func|fn|function|public|private|protected|internal|sub)\b"
)

_TIMEOUT = re.compile(r"\btimeout\s*[=:]", re.IGNORECASE)
_RETRY = re.compile(r"\b(?:retry|retries|max_attempts|backoff)\b", re.IGNORECASE)
_BACKOFF = re.compile(r"\b(?:backoff|jitter|exponential)\b", re.IGNORECASE)
#: An explicit ceiling, in any shape that actually bounds a retry: a named
#: limit, a bounded loop, or a decorator argument.
_MAX_ATTEMPTS = re.compile(
    r"\b(?:max_attempts|max_retries|max_tries|retries|stop_after_attempt|attempts)\s*[=:(]\s*\d+"
    r"|\bfor\s+\w+\s+in\s+range\s*\(\s*\d+",
    re.IGNORECASE,
)
_IDEMPOTENCY = re.compile(r"\b(?:idempot\w*|dedup\w*|Idempotency-Key)\b", re.IGNORECASE)

_TABLE_REFERENCE = re.compile(
    r"\b(?:from|join|into|update)\s+([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)",
    re.IGNORECASE,
)
_SQL_NOISE = frozenset({"select", "where", "values", "set", "table", "dual"})


def _enclosing_block(lines: Sequence[str], number: int, *, limit: int = 40) -> str:
    """The callable containing line ``number`` (1-based), bounded both ways.

    A fixed +/-N line window is wrong here: it reads a retry loop belonging to
    the *next* function as though it guarded this call, and reports a control
    as present or absent on evidence from unrelated code.  Walking out to the
    nearest block boundary keeps every finding attributable to the code that
    actually produced it.
    """

    index = number - 1
    start = index
    while start > 0 and not _BLOCK_START.match(lines[start]):
        if index - start >= limit:
            break
        start -= 1
    end = index + 1
    while end < len(lines) and not _BLOCK_START.match(lines[end]):
        if end - index >= limit:
            break
        end += 1
    return "\n".join(lines[start:end])


@dataclass(frozen=True, slots=True)
class ServiceNode:
    name: str
    root: str
    paths: tuple[str, ...]
    owners: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {"name": self.name, "root": self.root, "fileCount": len(self.paths), "owners": list(self.owners)}


@dataclass(frozen=True, slots=True)
class ServiceEdge:
    source: str
    target: str
    kind: EdgeKind
    evidence: tuple[str, ...]
    #: Populated only from supplied traces; static analysis cannot fill it in.
    observed_calls: int | None = None

    @property
    def hot(self) -> bool | UnknownType:
        if self.observed_calls is None:
            return UNKNOWN
        return self.observed_calls > 0

    def to_payload(self) -> dict[str, Any]:
        hot = self.hot
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "evidence": list(self.evidence[:8]),
            "observedCalls": self.observed_calls,
            "hot": None if isinstance(hot, UnknownType) else hot,
        }


@dataclass(frozen=True, slots=True)
class CallPolicyFinding:
    path: str
    line: int
    control: str
    detail: str
    blocking: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "control": self.control,
            "detail": self.detail,
            "blocking": self.blocking,
        }


@dataclass(frozen=True, slots=True)
class EventContractPlan:
    event: str
    path: str
    version_field: str
    ordering_key: str
    idempotency_key: str
    dedupe_window: str
    retry_policy: Mapping[str, Any]
    dead_letter: str
    replay_safe: bool
    notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "path": self.path,
            "versionField": self.version_field,
            "orderingKey": self.ordering_key,
            "idempotencyKey": self.idempotency_key,
            "dedupeWindow": self.dedupe_window,
            "retryPolicy": dict(self.retry_policy),
            "deadLetter": self.dead_letter,
            "replaySafe": self.replay_safe,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class ResilienceTest:
    name: str
    fault: str
    target: str
    expectation: str
    #: Whether the pure core can decide this without an executor.  Every entry
    #: here is ``False``: fault injection is by definition an executed test.
    decidable_offline: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fault": self.fault,
            "target": self.target,
            "expectation": self.expectation,
            "decidableOffline": self.decidable_offline,
            "status": "not-run",
        }


@dataclass(frozen=True, slots=True)
class BoundaryStep:
    step_id: str
    title: str
    strategy: SplitStrategy
    detail: str
    reversible: bool
    gate: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "stepId": self.step_id,
            "title": self.title,
            "strategy": self.strategy.value,
            "detail": self.detail,
            "reversible": self.reversible,
            "gate": self.gate,
        }


@dataclass(frozen=True, slots=True)
class DistributedPlan:
    services: tuple[ServiceNode, ...]
    edges: tuple[ServiceEdge, ...]
    shared_stores: tuple[Mapping[str, Any], ...]
    boundary_steps: tuple[BoundaryStep, ...]
    events: tuple[EventContractPlan, ...]
    policy_findings: tuple[CallPolicyFinding, ...]
    resilience_tests: tuple[ResilienceTest, ...]
    runbook: tuple[Mapping[str, str], ...]
    write_pattern: WritePattern
    write_pattern_reason: str
    risk_class: RiskClass
    traces_supplied: bool
    reasons: tuple[str, ...] = ()
    blocked_reason: str = ""

    @property
    def executable(self) -> bool:
        return not self.blocked_reason

    @property
    def blocking_findings(self) -> tuple[CallPolicyFinding, ...]:
        return tuple(item for item in self.policy_findings if item.blocking)

    def to_payload(self) -> dict[str, Any]:
        return {
            "services": [item.to_payload() for item in self.services],
            "edges": [item.to_payload() for item in self.edges],
            "sharedDatastores": [dict(item) for item in self.shared_stores],
            "boundarySteps": [item.to_payload() for item in self.boundary_steps],
            "eventMigrationPlan": [item.to_payload() for item in self.events],
            "callPolicyFindings": [item.to_payload() for item in self.policy_findings],
            "resilienceTests": [item.to_payload() for item in self.resilience_tests],
            "operationalRunbook": [dict(item) for item in self.runbook],
            "writePattern": self.write_pattern.value,
            "writePatternReason": self.write_pattern_reason,
            "riskClass": self.risk_class.value,
            "tracesSupplied": self.traces_supplied,
            "hotPathKnowledge": "observed" if self.traces_supplied else "unknown",
            "reasons": list(self.reasons),
            "executable": self.executable,
            "blockedReason": self.blocked_reason,
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

_SERVICE_ROOTS = ("services/", "apps/", "cmd/", "packages/")


def discover_services(
    snapshot: WorkspaceSnapshot,
    *,
    declared: Sequence[Mapping[str, Any]] = (),
    owners: Mapping[str, Sequence[str]] | None = None,
) -> tuple[ServiceNode, ...]:
    """Group files into services, from a declaration when one exists.

    A declared portfolio always wins: guessing service boundaries from
    directory names is a convenience for repositories that never wrote them
    down, and it is reported as such by the caller.
    """

    ownership = {key: tuple(value) for key, value in (owners or {}).items()}
    if declared:
        nodes: list[ServiceNode] = []
        for entry in declared:
            name = str(entry.get("name", "")).strip()
            root = str(entry.get("root", "")).strip().strip("/")
            if not name or not root:
                raise ContractError(
                    "invalid_service_declaration",
                    "each declared service needs a non-empty 'name' and 'root'",
                    {"entry": dict(entry)},
                )
            paths = tuple(record.path for record in snapshot if record.path.startswith(f"{root}/"))
            nodes.append(
                ServiceNode(name=name, root=root, paths=paths, owners=ownership.get(name, ()))
            )
        return tuple(sorted(nodes, key=lambda item: item.name))

    grouped: dict[str, list[str]] = {}
    for record in snapshot:
        for prefix in _SERVICE_ROOTS:
            if record.path.startswith(prefix):
                remainder = record.path[len(prefix) :]
                head = remainder.split("/", 1)[0]
                if head and "/" in remainder:
                    grouped.setdefault(f"{prefix}{head}", []).append(record.path)
                break
    return tuple(
        ServiceNode(
            name=root.rstrip("/").split("/")[-1],
            root=root,
            paths=tuple(sorted(paths)),
            owners=ownership.get(root.rstrip("/").split("/")[-1], ()),
        )
        for root, paths in sorted(grouped.items())
    )


def _service_of(services: Sequence[ServiceNode], path: str) -> str:
    for node in services:
        if path.startswith(f"{node.root}/"):
            return node.name
    return ""


def build_service_graph(
    snapshot: WorkspaceSnapshot,
    services: Sequence[ServiceNode],
    *,
    traces: Sequence[Mapping[str, Any]] = (),
) -> tuple[ServiceEdge, ...]:
    """Synchronous, asynchronous and data-sharing edges between services."""

    observed: dict[tuple[str, str], int] = {}
    for entry in traces:
        key = (str(entry.get("source", "")), str(entry.get("target", "")))
        if key[0] and key[1]:
            observed[key] = observed.get(key, 0) + int(entry.get("calls", 1))

    publishers: dict[str, set[str]] = {}
    subscribers: dict[str, set[str]] = {}
    evidence: dict[tuple[str, str, EdgeKind], list[str]] = {}

    for record in snapshot:
        text = record.text
        if text is None:
            #: Unreadable file: it may hold the busiest call site in the
            #: repository.  It is not evidence of absence.
            continue
        service = _service_of(services, record.path)
        if not service:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in _REMOTE_CALL):
                target = _target_service(line, services, service)
                if target and target != service:
                    evidence.setdefault((service, target, EdgeKind.SYNCHRONOUS), []).append(
                        f"{record.path}:{number}"
                    )
            if any(pattern.search(line) for pattern in _ASYNC_PUBLISH):
                topic = _topic_of(line)
                if topic:
                    publishers.setdefault(topic, set()).add(service)
                    evidence.setdefault((service, f"topic:{topic}", EdgeKind.ASYNCHRONOUS), []).append(
                        f"{record.path}:{number}"
                    )
            if _SUBSCRIBE.search(line):
                topic = _topic_of(line)
                if topic:
                    subscribers.setdefault(topic, set()).add(service)

    edges: list[ServiceEdge] = []
    for (source, target, kind), lines in sorted(evidence.items(), key=lambda item: item[0][:2]):
        if kind is EdgeKind.ASYNCHRONOUS:
            topic = target.removeprefix("topic:")
            for consumer in sorted(subscribers.get(topic, set()) - {source}):
                edges.append(
                    ServiceEdge(
                        source=source,
                        target=consumer,
                        kind=EdgeKind.ASYNCHRONOUS,
                        evidence=tuple(sorted(lines)),
                        observed_calls=observed.get((source, consumer)),
                    )
                )
            if not subscribers.get(topic):
                edges.append(
                    ServiceEdge(
                        source=source,
                        target=target,
                        kind=EdgeKind.ASYNCHRONOUS,
                        evidence=tuple(sorted(lines)),
                        observed_calls=None,
                    )
                )
            continue
        edges.append(
            ServiceEdge(
                source=source,
                target=target,
                kind=kind,
                evidence=tuple(sorted(lines)),
                observed_calls=observed.get((source, target)),
            )
        )
    return tuple(edges)


def _target_service(line: str, services: Sequence[ServiceNode], source: str) -> str:
    for node in services:
        if node.name == source:
            continue
        #: Whole-token match only: a service called "user" must not claim every
        #: line that happens to mention "username".
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(node.name)}(?![A-Za-z0-9_])", line, re.IGNORECASE):
            return node.name
    return ""


def _topic_name(identifier: str) -> str:
    """A queue name, not an entity id: drop the path and normalise separators."""

    tail = identifier.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    cleaned = re.sub(r"[^A-Za-z0-9]+", ".", tail).strip(".").lower()
    return cleaned or "unnamed.event"


_TOPIC = re.compile(r"[\"']([A-Za-z][\w.\-]{2,})[\"']")


def _topic_of(line: str) -> str:
    match = _TOPIC.search(line)
    return match.group(1) if match else ""


def shared_datastores(
    snapshot: WorkspaceSnapshot,
    services: Sequence[ServiceNode],
) -> tuple[Mapping[str, Any], ...]:
    """Tables touched by more than one service: coupling, whether declared or not."""

    touched: dict[str, dict[str, set[str]]] = {}
    for record in snapshot:
        text = record.text
        if text is None:
            continue
        service = _service_of(services, record.path)
        if not service:
            continue
        for match in _TABLE_REFERENCE.finditer(text):
            table = match.group(1).lower()
            if table in _SQL_NOISE or table.isdigit():
                continue
            touched.setdefault(table, {}).setdefault(service, set()).add(record.path)

    shared: list[Mapping[str, Any]] = []
    for table, owners in sorted(touched.items()):
        if len(owners) < 2:
            continue
        shared.append(
            {
                "table": table,
                "services": sorted(owners),
                "paths": sorted({path for paths in owners.values() for path in paths})[:12],
                "detail": (
                    "more than one service reaches this table directly; extracting either side "
                    "without an ownership decision leaves them coupled through the database"
                ),
            }
        )
    return tuple(shared)


# ---------------------------------------------------------------------------
# Call-policy audit
# ---------------------------------------------------------------------------


def audit_call_policies(snapshot: WorkspaceSnapshot) -> tuple[CallPolicyFinding, ...]:
    """Every remote call needs a timeout, a bounded retry and an idempotency key."""

    findings: list[CallPolicyFinding] = []
    for record in snapshot:
        text = record.text
        if text is None:
            continue
        lines = text.splitlines()
        for number, line in enumerate(lines, start=1):
            if not any(pattern.search(line) for pattern in _REMOTE_CALL):
                continue
            window = _enclosing_block(lines, number)
            if not _TIMEOUT.search(window):
                findings.append(
                    CallPolicyFinding(
                        path=record.path,
                        line=number,
                        control="timeout",
                        detail=(
                            "a remote call with no timeout in view; the absence of a timeout is "
                            "indistinguishable from an unbounded wait for the caller"
                        ),
                    )
                )
            if _RETRY.search(window):
                if _MAX_ATTEMPTS.search(window) is None:
                    findings.append(
                        CallPolicyFinding(
                            path=record.path,
                            line=number,
                            control="retry-bound",
                            detail="retry logic with no visible attempt ceiling",
                        )
                    )
                if not _BACKOFF.search(window):
                    findings.append(
                        CallPolicyFinding(
                            path=record.path,
                            line=number,
                            control="retry-backoff",
                            detail="retry with no backoff or jitter amplifies an outage into a stampede",
                        )
                    )
                if not _IDEMPOTENCY.search(window):
                    findings.append(
                        CallPolicyFinding(
                            path=record.path,
                            line=number,
                            control="retry-idempotency",
                            detail=(
                                "a retried call with no idempotency key can duplicate a side effect; "
                                "the retry is only safe if the callee deduplicates"
                            ),
                        )
                    )
    return tuple(findings)


# ---------------------------------------------------------------------------
# Event and boundary planning
# ---------------------------------------------------------------------------


def plan_event_migration(
    index: SemanticIndex,
    *,
    dedupe_window: str = "24h",
    max_attempts: int = 5,
) -> tuple[EventContractPlan, ...]:
    """Give every event contract explicit version, ordering and replay semantics."""

    if max_attempts < 1:
        raise ContractError("invalid_retry_bound", "max_attempts must be at least 1")
    plans: list[EventContractPlan] = []
    for entity in index.of_kind(EntityKind.EVENT_CONTRACT):
        plans.append(
            EventContractPlan(
                event=entity.qualified_name or entity.name,
                path=entity.path,
                version_field="schema_version",
                ordering_key="aggregate_id",
                idempotency_key="event_id",
                dedupe_window=dedupe_window,
                retry_policy={
                    "maxAttempts": max_attempts,
                    "backoff": "exponential",
                    "jitter": "full",
                    "timeoutSeconds": 30,
                },
                dead_letter=f"{_topic_name(entity.qualified_name or entity.name)}.dlq",
                replay_safe=True,
                notes=(
                    "consumers must treat event_id as the deduplication key before applying any effect",
                    "replay is only safe while every handler is keyed on event_id; adding an "
                    "unkeyed handler silently breaks it",
                ),
            )
        )
    return tuple(plans)


def choose_write_pattern(
    edges: Sequence[ServiceEdge],
    shared: Sequence[Mapping[str, Any]],
) -> tuple[WritePattern, str]:
    """Pick the cross-service write pattern from the shape of the graph."""

    if shared:
        return (
            WritePattern.LOCAL_TRANSACTION,
            "writes still share a datastore, so a local transaction remains correct — and the "
            "coupling must be resolved before any distributed pattern is introduced",
        )
    asynchronous = [edge for edge in edges if edge.kind is EdgeKind.ASYNCHRONOUS]
    synchronous = [edge for edge in edges if edge.kind is EdgeKind.SYNCHRONOUS]
    if asynchronous and synchronous:
        return (
            WritePattern.SAGA,
            "a write spans services over both synchronous and asynchronous edges; each step needs "
            "an explicit compensating action because there is no shared commit point",
        )
    if asynchronous:
        return (
            WritePattern.OUTBOX,
            "state change and event publication must commit together; an outbox row written in the "
            "same transaction is the only way to keep them from diverging",
        )
    return (
        WritePattern.LOCAL_TRANSACTION,
        "no cross-service write was found; nothing justifies a distributed transaction",
    )


def plan_boundary(
    services: Sequence[ServiceNode],
    shared: Sequence[Mapping[str, Any]],
    target: str,
) -> tuple[BoundaryStep, ...]:
    """Branch-by-abstraction then strangler; never a direct cut over shared data."""

    steps: list[BoundaryStep] = [
        BoundaryStep(
            step_id="boundary-0-seam",
            title=f"Introduce an abstraction seam in front of '{target}'",
            strategy=SplitStrategy.BRANCH_BY_ABSTRACTION,
            detail=(
                "every caller goes through one interface, still backed by the existing "
                "implementation; no behaviour changes and the change is a pure refactor"
            ),
            reversible=True,
            gate="changed-target-tests",
        ),
        BoundaryStep(
            step_id="boundary-1-implementation",
            title="Add the remote-backed implementation behind the seam",
            strategy=SplitStrategy.BRANCH_BY_ABSTRACTION,
            detail="both implementations exist; selection is a runtime flag, defaulting to the old one",
            reversible=True,
            gate="full-tests",
        ),
    ]
    if shared:
        steps.append(
            BoundaryStep(
                step_id="boundary-2-data-ownership",
                title="Resolve shared-table ownership before routing traffic",
                strategy=SplitStrategy.STRANGLER_FIG,
                detail=(
                    f"{len(shared)} table(s) are reached by more than one service; assign a single "
                    "writer and give the others a read path through its API or a replica"
                ),
                reversible=True,
                gate="human-approval",
            )
        )
    steps.append(
        BoundaryStep(
            step_id=f"boundary-{len(steps)}-strangle",
            title="Move traffic to the remote implementation in a canary ladder",
            strategy=SplitStrategy.STRANGLER_FIG,
            detail="the flag moves 1 → 5 → 25 → 50 → 100 with the old implementation still deployed",
            reversible=True,
            gate="canary-guardrails",
        )
    )
    steps.append(
        BoundaryStep(
            step_id=f"boundary-{len(steps)}-cleanup",
            title="Remove the old implementation",
            strategy=SplitStrategy.STRANGLER_FIG,
            detail="only after the old path has served zero traffic for a full retention window",
            reversible=False,
            gate="old-path-usage-zero",
        )
    )
    return tuple(steps)


def resilience_matrix(edges: Sequence[ServiceEdge]) -> tuple[ResilienceTest, ...]:
    """Fault injection per edge — none of it decidable without an executor."""

    tests: list[ResilienceTest] = []
    for edge in edges:
        label = f"{edge.source}->{edge.target}[{edge.kind.value}]"
        tests.append(
            ResilienceTest(
                name=f"latency:{label}",
                fault="inject p99 latency at the callee",
                target=label,
                expectation="the caller times out and degrades; it does not exhaust its own pool",
            )
        )
        tests.append(
            ResilienceTest(
                name=f"partition:{label}",
                fault="drop all traffic on this edge",
                target=label,
                expectation="the caller fails fast with a defined fallback; no unbounded queue growth",
            )
        )
        if edge.kind is EdgeKind.ASYNCHRONOUS:
            tests.extend(
                (
                    ResilienceTest(
                        name=f"duplicate:{label}",
                        fault="redeliver every message once",
                        target=label,
                        expectation="the effect is applied exactly once, keyed on event_id",
                    ),
                    ResilienceTest(
                        name=f"reorder:{label}",
                        fault="deliver messages in reverse order within one ordering key",
                        target=label,
                        expectation="the final state matches the highest version, not the last arrival",
                    ),
                    ResilienceTest(
                        name=f"replay:{label}",
                        fault="replay the retention window from the beginning",
                        target=label,
                        expectation="no external side effect is repeated",
                    ),
                )
            )
        else:
            tests.append(
                ResilienceTest(
                    name=f"degrade:{label}",
                    fault="return 5xx from the callee for a sustained window",
                    target=label,
                    expectation="the circuit opens; the caller sheds load rather than retrying forever",
                )
            )
    return tuple(tests)


def build_runbook(
    plan_target: str,
    events: Sequence[EventContractPlan],
    write_pattern: WritePattern,
) -> tuple[Mapping[str, str], ...]:
    entries: list[Mapping[str, str]] = [
        {
            "situation": "the new path errors above the guardrail",
            "action": f"flip the '{plan_target}' selector flag back to the in-process implementation",
            "reversible": "yes — both implementations are deployed",
        },
        {
            "situation": "the outbox or queue backs up",
            "action": "stop producers first, drain consumers, and only then resume; never truncate the queue",
            "reversible": "yes",
        },
        {
            "situation": "duplicate side effects are observed",
            "action": (
                "stop the consumer, confirm the handler keys on event_id, and reconcile from the "
                "side-effect ledger before resuming"
            ),
            "reversible": "partially — already-emitted effects need compensation, not deletion",
        },
    ]
    if write_pattern is WritePattern.SAGA:
        entries.append(
            {
                "situation": "a saga step fails after earlier steps committed",
                "action": "run the compensating actions in reverse order, each with its idempotency key",
                "reversible": "by compensation only; there is no rollback across services",
            }
        )
    for event in events[:5]:
        entries.append(
            {
                "situation": f"'{event.event}' lands in {event.dead_letter}",
                "action": (
                    "inspect, fix forward, and replay from the DLQ; the handler is keyed on "
                    f"{event.idempotency_key}, so replay does not duplicate"
                ),
                "reversible": "yes",
            }
        )
    return tuple(entries)


def plan_distributed_refactor(
    snapshot: WorkspaceSnapshot,
    index: SemanticIndex,
    *,
    target: str,
    declared_services: Sequence[Mapping[str, Any]] = (),
    owners: Mapping[str, Sequence[str]] | None = None,
    traces: Sequence[Mapping[str, Any]] = (),
) -> DistributedPlan:
    """Assemble the boundary, event, resilience and runbook outputs for one target."""

    services = discover_services(snapshot, declared=declared_services, owners=owners)
    reasons: list[str] = []
    blocked = ""
    if not services:
        blocked = (
            "no service boundary could be established; declare the portfolio explicitly rather than "
            "letting a directory-name guess drive a critical-risk refactor"
        )
    elif not declared_services:
        reasons.append(
            f"{len(services)} service(s) were inferred from directory layout, not declared; "
            "the boundary plan is only as good as that guess"
        )
    edges = build_service_graph(snapshot, services, traces=traces)
    shared = shared_datastores(snapshot, services)
    findings = audit_call_policies(snapshot)
    events = plan_event_migration(index)
    pattern, pattern_reason = choose_write_pattern(edges, shared)
    steps = plan_boundary(services, shared, target)
    tests = resilience_matrix(edges)
    runbook = build_runbook(target, events, pattern)

    if not traces:
        reasons.append(
            "no runtime traces were supplied; call frequency and hot paths are UNKNOWN and no "
            "step may be justified by 'this edge is cold'"
        )
    if shared:
        reasons.append(
            f"{len(shared)} datastore(s) are shared across services; ownership must be assigned "
            "before extraction, not after"
        )
    blocking = [item for item in findings if item.blocking]
    if blocking and not blocked:
        blocked = (
            f"{len(blocking)} remote call site(s) lack a timeout, a retry bound, backoff or an "
            "idempotency key; a service split multiplies every one of those into an outage"
        )
    risk = RiskClass.R4 if (shared or blocking) else RiskClass.R3
    return DistributedPlan(
        services=services,
        edges=edges,
        shared_stores=shared,
        boundary_steps=steps,
        events=events,
        policy_findings=findings,
        resilience_tests=tests,
        runbook=runbook,
        write_pattern=pattern,
        write_pattern_reason=pattern_reason,
        risk_class=risk,
        traces_supplied=bool(traces),
        reasons=tuple(reasons),
        blocked_reason=blocked,
    )


__all__ = [
    "BoundaryStep",
    "CallPolicyFinding",
    "DistributedPlan",
    "EdgeKind",
    "EventContractPlan",
    "ResilienceTest",
    "ServiceEdge",
    "ServiceNode",
    "SplitStrategy",
    "WritePattern",
    "audit_call_policies",
    "build_runbook",
    "build_service_graph",
    "choose_write_pattern",
    "discover_services",
    "plan_boundary",
    "plan_distributed_refactor",
    "plan_event_migration",
    "resilience_matrix",
    "shared_datastores",
]
