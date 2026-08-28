"""Proof-obligation DAG and conservative result application.

An obligation closes only when the result and the *actual resolved evidence
records* agree on tenant/project, subject revision, scope, assumptions,
evidence classes, tool and environment, and the proof status meets the declared
minimum.  Error, timeout, unknown, unsupported, monitored and waived outcomes
never close an obligation.  Rejected high-status claims do not inflate state.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Iterable

from .contracts import (
    NON_CLOSING_PROOF_STATUSES,
    EvidenceClass,
    EvidenceRecord,
    ProofDecision,
    ProofObligation,
    ProofResult,
    ProofStatus,
    SecurityContext,
    Severity,
    proof_status_meets,
    utc_now,
)
from .errors import ConflictError, ProofError
from .evidence import EvidenceService


ProofGraphError = ProofError


class EdgeKind(StrEnum):
    DEPENDS_ON = "depends_on"
    REFINES = "refines"
    DISCHARGES_ASSUMPTION = "discharges_assumption"
    SHARES_EVIDENCE = "shares_evidence"
    INVALIDATES = "invalidates"


@dataclass(frozen=True, slots=True)
class ProofEdge:
    obligation_id: str
    dependency_id: str
    kind: EdgeKind = EdgeKind.DEPENDS_ON


class ProofObligationGraph:
    """In-memory deterministic DAG; durable callers journal results in Store."""

    def __init__(
        self,
        obligations: Iterable[ProofObligation],
        dependencies: Iterable[ProofEdge | tuple[str, str] | tuple[str, str, EdgeKind | str]] = (),
    ) -> None:
        items = tuple(obligations)
        self._obligations = {item.obligation_id: item for item in items}
        if not items:
            raise ProofGraphError("at least one proof obligation is required")
        if len(items) != len(self._obligations):
            raise ProofGraphError("proof obligation ids must be unique")
        scope = {(item.tenant_id, item.project_id, item.graph_id, item.goal_id) for item in items}
        if len(scope) != 1:
            raise ProofGraphError("all obligations must share an exact tenant/project/graph/goal scope")
        for item in items:
            if item.status not in {ProofStatus.PENDING, ProofStatus.READY, ProofStatus.RUNNING, ProofStatus.BLOCKED}:
                raise ProofGraphError("pre-closed obligations are not accepted without result evidence", code="STATUS_INFLATION")
        self._scope = next(iter(scope))
        self._dependencies: dict[str, set[str]] = defaultdict(set)
        self._dependents: dict[str, set[str]] = defaultdict(set)
        self._edges: list[ProofEdge] = []
        for raw in dependencies:
            edge = self._coerce_edge(raw)
            if edge.obligation_id not in self._obligations or edge.dependency_id not in self._obligations:
                raise ProofGraphError(
                    "proof edge references an unknown obligation",
                    details={"obligation_id": edge.obligation_id, "dependency_id": edge.dependency_id},
                )
            if edge.obligation_id == edge.dependency_id:
                raise ProofGraphError("proof obligation cannot depend on itself", code="PROOF_GRAPH_CYCLE")
            if any(
                existing.obligation_id == edge.obligation_id
                and existing.dependency_id == edge.dependency_id
                and existing.kind is edge.kind
                for existing in self._edges
            ):
                raise ProofGraphError("duplicate proof edge")
            self._edges.append(edge)
            self._dependencies[edge.obligation_id].add(edge.dependency_id)
            self._dependents[edge.dependency_id].add(edge.obligation_id)
        self._assert_acyclic()
        self._closed: set[str] = set()
        self._result_ids: set[str] = set()
        self._decisions: list[ProofDecision] = []

    @staticmethod
    def _coerce_edge(raw: ProofEdge | tuple[str, str] | tuple[str, str, EdgeKind | str]) -> ProofEdge:
        if isinstance(raw, ProofEdge):
            return raw
        if len(raw) == 2:
            return ProofEdge(raw[0], raw[1])
        return ProofEdge(raw[0], raw[1], EdgeKind(raw[2]))

    @property
    def obligations(self) -> tuple[ProofObligation, ...]:
        return tuple(self._obligations[key] for key in sorted(self._obligations))

    @property
    def edges(self) -> tuple[ProofEdge, ...]:
        return tuple(self._edges)

    @property
    def decisions(self) -> tuple[ProofDecision, ...]:
        return tuple(self._decisions)

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        """Evidence actually resolved while applying graph results.

        The graph digest must bind the evidence that discharged each result;
        otherwise a caller could seal an unrelated evidence bundle after the
        graph had already been closed.
        """

        return tuple(sorted({evidence_id for decision in self._decisions for evidence_id in decision.evidence_ids}))

    @property
    def tenant_id(self) -> str:
        return self._scope[0]

    @property
    def project_id(self) -> str:
        return self._scope[1]

    @property
    def graph_id(self) -> str:
        return self._scope[2]

    @property
    def goal_id(self) -> str:
        return self._scope[3]

    def _assert_acyclic(self) -> None:
        indegree = {key: len(self._dependencies[key]) for key in self._obligations}
        queue = deque(sorted(key for key, degree in indegree.items() if degree == 0))
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for dependent in sorted(self._dependents[node]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    queue.append(dependent)
        if visited != len(self._obligations):
            raise ProofGraphError("proof obligation graph contains a cycle", code="PROOF_GRAPH_CYCLE")

    def ready(self) -> tuple[ProofObligation, ...]:
        return tuple(
            item
            for item in self.obligations
            if item.status in {ProofStatus.PENDING, ProofStatus.READY, ProofStatus.BLOCKED}
            and self._dependencies[item.obligation_id].issubset(self._closed)
        )

    def apply_result(
        self,
        result: ProofResult,
        evidence: EvidenceService,
        context: SecurityContext,
        *,
        expected_sequence: int | None = None,
        now: datetime | None = None,
    ) -> ProofDecision:
        if result.result_id in self._result_ids:
            raise ConflictError("proof result id already applied", code="PROOF_RESULT_REPLAY")
        obligation = self._obligations.get(result.obligation_id)
        if obligation is None:
            raise ProofGraphError("proof result references an unknown obligation")
        if expected_sequence is not None and obligation.sequence != expected_sequence:
            raise ConflictError(
                "proof obligation sequence conflict",
                details={"expected": expected_sequence, "actual": obligation.sequence},
            )
        current_time = now or utc_now()
        if (context.tenant_id, context.project_id) != (obligation.tenant_id, obligation.project_id):
            raise ProofGraphError("evidence resolver context does not match graph scope")
        if context.actor_id != result.actor_id:
            raise ProofGraphError(
                "proof result actor does not match authenticated context",
                code="PROOF_ACTOR_MISMATCH",
            )
        # Resolution performs an actual BLOB read, byte-length check, digest
        # verification, freshness check and revocation check.  Callers cannot
        # close an obligation by supplying metadata-only evidence records.
        records = evidence.fresh_records(context, result.evidence_ids, now=current_time)
        reasons = self._validate_binding(obligation, result, records, now=current_time)
        closing_reasons = list(reasons)
        if result.error_code is not None:
            closing_reasons.append("result reports an execution error")
        if not proof_status_meets(result.status, obligation.required_minimum_status):
            closing_reasons.append("proof status does not meet the required minimum")
        if obligation.severity is Severity.CRITICAL and result.status is ProofStatus.BOUNDED_NO_COUNTEREXAMPLE:
            closing_reasons.append("bounded search cannot close a critical obligation")
        if obligation.open_world and result.status is ProofStatus.RUNTIME_MONITORED:
            closing_reasons.append("runtime monitoring is not a proof closure")
        if result.status is ProofStatus.PROVED_CERTIFIED:
            # The local graph has no asymmetric trust adapter.  Producer and
            # result booleans therefore cannot manufacture a certified proof
            # state; a future external-proof adapter must supply a separately
            # verified, durable receipt before this status can close locally.
            closing_reasons.append("certified proof status requires external cryptographic verification")
            if not result.independent_verifier:
                closing_reasons.append("certified proof result lacks an independent verifier")
            if not any(record.producer.independent for record in records):
                closing_reasons.append("certified proof evidence is not independently produced")
        closed = not closing_reasons
        envelope_valid = not reasons
        applied_status = obligation.status
        if closed:
            applied_status = result.status
            self._closed.add(obligation.obligation_id)
        elif envelope_valid and result.status in NON_CLOSING_PROOF_STATUSES:
            # Preserve legitimate refuted/unknown/unsupported outcomes without
            # turning them into success.  A later refutation invalidates a
            # previously closed obligation.
            applied_status = result.status
            self._closed.discard(obligation.obligation_id)
        updated = replace(obligation, status=applied_status, sequence=obligation.sequence + 1)
        self._obligations[obligation.obligation_id] = updated
        self._result_ids.add(result.result_id)
        decision = ProofDecision(
            obligation_id=obligation.obligation_id,
            result_id=result.result_id,
            accepted=envelope_valid,
            closed=closed,
            applied_status=applied_status,
            reasons=tuple(dict.fromkeys(closing_reasons)),
            evidence_ids=tuple(record.evidence_id for record in records),
        )
        self._decisions.append(decision)
        return decision

    @staticmethod
    def _validate_binding(
        obligation: ProofObligation,
        result: ProofResult,
        records: tuple[EvidenceRecord, ...],
        *,
        now: datetime,
    ) -> list[str]:
        reasons: list[str] = []
        if (result.tenant_id, result.project_id) != (obligation.tenant_id, obligation.project_id):
            reasons.append("tenant or project binding mismatch")
        if result.subject_revision != obligation.subject_revision:
            reasons.append("subject revision mismatch")
        if result.scope != obligation.scope:
            reasons.append("proof scope mismatch")
        if tuple(result.assumptions) != tuple(obligation.assumptions):
            reasons.append("assumptions do not exactly match the approved set")
        if not records:
            reasons.append("resolved evidence is empty")
            return reasons
        record_ids = tuple(record.evidence_id for record in records)
        if len(set(record_ids)) != len(record_ids) or set(record_ids) != set(result.evidence_ids):
            reasons.append("resolved evidence ids do not match the result")
        actual_classes = frozenset(record.evidence_class for record in records)
        if actual_classes != result.evidence_classes:
            reasons.append("claimed evidence classes do not match resolved evidence")
        if not actual_classes or not actual_classes.issubset(obligation.accepted_evidence_classes):
            reasons.append("one or more evidence classes are not approved")
        if obligation.accepted_tool_digests and result.tool.digest not in obligation.accepted_tool_digests:
            reasons.append("proof tool digest is not approved")
        if obligation.accepted_environment_revisions and result.environment_revision not in obligation.accepted_environment_revisions:
            reasons.append("proof environment revision is not approved")
        for record in records:
            if (record.tenant_id, record.project_id) != (obligation.tenant_id, obligation.project_id):
                reasons.append("evidence tenant or project mismatch")
            if record.subject_revision != obligation.subject_revision:
                reasons.append("evidence subject revision mismatch")
            if record.scope != obligation.scope:
                reasons.append("evidence scope mismatch")
            if tuple(record.assumptions) != tuple(obligation.assumptions):
                reasons.append("evidence assumptions mismatch")
            if record.expires_at is not None and now >= record.expires_at:
                reasons.append("evidence is expired")
            if record.evidence_class != EvidenceClass.HUMAN_APPROVAL.value:
                if record.producer.tool_digest != result.tool.digest:
                    reasons.append("evidence tool digest mismatch")
                if record.producer.environment_revision != result.environment_revision:
                    reasons.append("evidence environment revision mismatch")
        if result.status is ProofStatus.REFUTED_WITH_COUNTEREXAMPLE and result.counterexample_evidence_id not in record_ids:
            reasons.append("counterexample evidence was not resolved")
        return list(dict.fromkeys(reasons))

    def critical_unclosed(self) -> tuple[ProofObligation, ...]:
        return tuple(
            item for item in self.obligations if item.severity is Severity.CRITICAL and item.obligation_id not in self._closed
        )

    def refutations(self) -> tuple[ProofObligation, ...]:
        return tuple(item for item in self.obligations if item.status is ProofStatus.REFUTED_WITH_COUNTEREXAMPLE)

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.obligations:
            counts[item.status.value] = counts.get(item.status.value, 0) + 1
        return counts

    def all_critical_closed(self) -> bool:
        return not self.critical_unclosed()
