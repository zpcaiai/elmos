from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime

from elmos_proof_harness.canonical import digest_bytes
from elmos_proof_harness.contracts import (
    EvidenceProducer,
    ProofObligation,
    ProofResult,
    ProofStatus,
    SecurityContext,
    Severity,
    ToolIdentity,
)
from elmos_proof_harness.evidence import EvidenceService
from elmos_proof_harness.errors import ProofError
from elmos_proof_harness.proof_graph import ProofObligationGraph
from elmos_proof_harness.store import SQLiteStore


NOW = datetime(2026, 8, 28, 6, 0, tzinfo=UTC)


def d(value: str, domain: str = "test") -> str:
    return digest_bytes(value.encode(), domain=domain)


class ProofGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteStore(":memory:")
        self.context = SecurityContext("tenant-a", "project-a", "verifier-a")
        self.store.register_scope(self.context, now=NOW)
        self.evidence = EvidenceService(self.store)
        self.subject = d("subject", "repository-revision")
        self.environment = d("environment", "environment")
        self.tool_digest = d("tool", "tool-binary")
        self.encoder = d("encoder", "encoder")
        self.tool = ToolIdentity("solver", "1.0", self.tool_digest, "1", self.encoder)
        self.producer = EvidenceProducer(
            "execution-1", "VERIFIER", "solver", self.tool_digest, self.environment, independent=True
        )
        self.record = self.evidence.record_bytes(
            self.context,
            subject_revision=self.subject,
            kind="solver-result",
            evidence_class="solver-model-result",
            scope="module:ledger",
            content=b"unsat-proof",
            media_type="application/octet-stream",
            producer=self.producer,
            evidence_id="proof-evidence",
            artifact_id="proof-artifact",
            created_at=NOW,
        )

    def tearDown(self) -> None:
        self.store.close()

    def obligation(self, obligation_id: str = "po-1", *, minimum: ProofStatus = ProofStatus.PROVED_SOLVER_TRUSTED) -> ProofObligation:
        return ProofObligation(
            obligation_id=obligation_id,
            tenant_id="tenant-a",
            project_id="project-a",
            graph_id="graph-1",
            goal_id="goal-1",
            subject_revision=self.subject,
            family="semantic-equivalence",
            relation="trace-refinement",
            scope="module:ledger",
            severity=Severity.CRITICAL,
            required_minimum_status=minimum,
            accepted_evidence_classes=frozenset({"solver-model-result"}),
            accepted_tool_digests=frozenset({self.tool_digest}),
            accepted_environment_revisions=frozenset({self.environment}),
        )

    def result(
        self,
        result_id: str,
        status: ProofStatus,
        *,
        tool: ToolIdentity | None = None,
        error_code: str | None = None,
    ) -> ProofResult:
        return ProofResult(
            result_id=result_id,
            obligation_id="po-1",
            tenant_id="tenant-a",
            project_id="project-a",
            actor_id="verifier-a",
            status=status,
            subject_revision=self.subject,
            scope="module:ledger",
            assumptions=(),
            tool=tool or self.tool,
            environment_revision=self.environment,
            inputs_sha256=d("inputs", "proof-inputs"),
            evidence_ids=("proof-evidence",),
            evidence_classes=frozenset({"solver-model-result"}),
            created_at=NOW,
            error_code=error_code,
            independent_verifier=True,
        )

    def test_valid_result_closes_but_bounded_and_error_results_do_not(self) -> None:
        graph = ProofObligationGraph([self.obligation()])
        bounded = graph.apply_result(
            self.result("result-bounded", ProofStatus.BOUNDED_NO_COUNTEREXAMPLE),
            self.evidence,
            self.context,
            now=NOW,
        )
        self.assertFalse(bounded.closed)
        self.assertEqual(ProofStatus.PENDING, bounded.applied_status)

        graph = ProofObligationGraph([self.obligation()])
        error = graph.apply_result(
            self.result("result-error", ProofStatus.PROVED_CERTIFIED, error_code="SOLVER_CRASH"),
            self.evidence,
            self.context,
            now=NOW,
        )
        self.assertTrue(error.accepted)
        self.assertFalse(error.closed)
        self.assertEqual(ProofStatus.PENDING, error.applied_status)

        graph = ProofObligationGraph([self.obligation()])
        valid = graph.apply_result(
            self.result("result-valid", ProofStatus.PROVED_SOLVER_TRUSTED),
            self.evidence,
            self.context,
            now=NOW,
        )
        self.assertTrue(valid.closed)
        self.assertTrue(graph.all_critical_closed())

    def test_claimed_status_cannot_inflate_when_tool_binding_is_wrong(self) -> None:
        wrong_tool = ToolIdentity("solver", "1.0", d("wrong", "tool-binary"), "1", self.encoder)
        graph = ProofObligationGraph([self.obligation()])
        decision = graph.apply_result(
            self.result("result-inflated", ProofStatus.PROVED_CERTIFIED, tool=wrong_tool),
            self.evidence,
            self.context,
            now=NOW,
        )
        self.assertFalse(decision.accepted)
        self.assertFalse(decision.closed)
        self.assertEqual(ProofStatus.PENDING, graph.obligations[0].status)
        self.assertIn("proof tool digest is not approved", decision.reasons)

    def test_self_declared_certified_and_unapproved_evidence_cannot_close(self) -> None:
        graph = ProofObligationGraph([self.obligation()])
        fake_certified = graph.apply_result(
            self.result("result-fake-certified", ProofStatus.PROVED_CERTIFIED),
            self.evidence,
            self.context,
            now=NOW,
        )
        self.assertFalse(fake_certified.closed)
        self.assertIn(
            "certified proof status requires external cryptographic verification",
            fake_certified.reasons,
        )

        self.evidence.record_bytes(
            self.context,
            subject_revision=self.subject,
            kind="unapproved-result",
            evidence_class="runtime-monitor",
            scope="module:ledger",
            content=b"monitor-only",
            media_type="application/octet-stream",
            producer=self.producer,
            evidence_id="unapproved-evidence",
            artifact_id="unapproved-artifact",
            created_at=NOW,
        )
        graph = ProofObligationGraph([self.obligation()])
        mixed = graph.apply_result(
            replace(
                self.result("result-mixed-evidence", ProofStatus.PROVED_SOLVER_TRUSTED),
                evidence_ids=("proof-evidence", "unapproved-evidence"),
                evidence_classes=frozenset({"solver-model-result", "runtime-monitor"}),
            ),
            self.evidence,
            self.context,
            now=NOW,
        )
        self.assertFalse(mixed.accepted)
        self.assertFalse(mixed.closed)
        self.assertIn("one or more evidence classes are not approved", mixed.reasons)

    def test_cycle_and_preclosed_obligation_are_rejected(self) -> None:
        second = ProofObligation(
            **{
                **{field: getattr(self.obligation(), field) for field in self.obligation().__dataclass_fields__},
                "obligation_id": "po-2",
            }
        )
        with self.assertRaises(ProofError) as cycle:
            ProofObligationGraph([self.obligation(), second], [("po-1", "po-2"), ("po-2", "po-1")])
        self.assertEqual("PROOF_GRAPH_CYCLE", cycle.exception.code)
        preclosed = ProofObligation(
            **{
                **{field: getattr(self.obligation(), field) for field in self.obligation().__dataclass_fields__},
                "status": ProofStatus.PROVED_CERTIFIED,
            }
        )
        with self.assertRaises(ProofError) as inflation:
            ProofObligationGraph([preclosed])
        self.assertEqual("STATUS_INFLATION", inflation.exception.code)


if __name__ == "__main__":
    unittest.main()
