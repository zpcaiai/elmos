from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from elmos_formal_assurance.contracts import (
    AssuranceLevel,
    Criticality,
    ProofObligation,
    ProofResult,
    ProofRunState,
    ProofStatus,
    Scope,
)
from elmos_formal_assurance.canonical import digest_value
from elmos_formal_assurance.gate import evaluate_release_gate
from elmos_formal_assurance.store import StateStore, StoreError


def make_scope(tenant: str = "tenant-a") -> Scope:
    return Scope(
        tenant, "account-a", "project-a", "a" * 64, "b" * 64, "c" * 64, "workload"
    )


def obligation(
    required: AssuranceLevel = AssuranceLevel.A1_BOUNDED,
    *,
    criticality: Criticality = Criticality.P1,
    property_kind: str = "FUNCTIONAL_CORRECTNESS",
    allow_bounded: bool = True,
) -> ProofObligation:
    return ProofObligation(
        "obl-1",
        criticality,
        property_kind,
        required,
        digest_value("x"),
        allow_bounded=allow_bounded,
    )


class StoreAndGateTests(unittest.TestCase):
    def test_hash_chain_and_fencing_reject_stale_worker(self) -> None:
        store = StateStore()
        current = make_scope()
        try:
            store.submit_run(current, "run-1", "obl-1")
            leased = store.lease_run(current, "run-1", "worker-a", 1)
            self.assertEqual(leased["fencing_token"], 2)
            store.start_run(current, "run-1", "worker-a", 2)
            with self.assertRaises(StoreError):
                store.commit_run(
                    current,
                    "run-1",
                    "worker-b",
                    2,
                    ProofResult(
                        "run-1",
                        "obl-1",
                        ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
                        AssuranceLevel.A1_BOUNDED,
                        "local",
                        "BOUNDED",
                        "a" * 64,
                        "b" * 64,
                        bound={"steps": 1},
                    ),
                )
            store.commit_run(
                current,
                "run-1",
                "worker-a",
                2,
                ProofResult(
                    "run-1",
                    "obl-1",
                    ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
                    AssuranceLevel.A1_BOUNDED,
                    "local",
                    "BOUNDED",
                    "a" * 64,
                    "b" * 64,
                    bound={"steps": 1},
                ),
            )
            self.assertEqual(
                store.verify_event_chain(current, "proof_run", "run-1"), []
            )
            self.assertEqual(
                store.get_run(current, "run-1")["state"], ProofRunState.SUCCEEDED.value
            )
        finally:
            store.close()

    def test_tenant_scoped_cache_and_event_queries(self) -> None:
        store = StateStore()
        first, second = make_scope("tenant-a"), make_scope("tenant-b")
        try:
            store.put_cache(first, "cache-1", {"dependencies": ["dep-1"], "value": 7})
            self.assertIsNotNone(store.get_cache(first, "cache-1"))
            self.assertIsNone(store.get_cache(second, "cache-1"))
            self.assertEqual(store.invalidate_cache(first, "dep-1"), 1)
            self.assertIsNone(store.get_cache(first, "cache-1"))
        finally:
            store.close()

    def test_gate_rejects_bounded_evidence_when_solver_assurance_is_required(
        self,
    ) -> None:
        result = ProofResult(
            "run-1",
            "obl-1",
            ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
            AssuranceLevel.A1_BOUNDED,
            "local",
            "BOUNDED",
            "a" * 64,
            "b" * 64,
            bound={"steps": 1},
        )
        decision = evaluate_release_gate(
            [obligation(AssuranceLevel.A2_SOLVER_PROVED)], {"obl-1": result}
        )
        self.assertEqual(decision.decision, "DENY")
        self.assertEqual(decision.readiness, "BLOCKED")

    def test_p05_and_e5_require_their_named_external_evidence(self) -> None:
        result = ProofResult(
            "run-1",
            "obl-1",
            ProofStatus.PROVED_SOLVER_TRUSTED,
            AssuranceLevel.A2_SOLVER_PROVED,
            "solver",
            "SMT",
            "a" * 64,
            "b" * 64,
        )
        p05 = evaluate_release_gate(
            [obligation(AssuranceLevel.A2_SOLVER_PROVED)],
            {"obl-1": result},
            required_gate="P05_DEPLOYMENT_COMPLETE",
        )
        e5 = evaluate_release_gate(
            [obligation(AssuranceLevel.A2_SOLVER_PROVED)],
            {"obl-1": result},
            required_gate="E5_CUSTOMER_GOLDEN_ROUTE",
        )
        self.assertEqual(p05.decision, "DENY")
        self.assertEqual(e5.decision, "DENY")

    def test_p0_security_cannot_be_waived(self) -> None:
        result = ProofResult(
            "run-1",
            "obl-1",
            ProofStatus.UNSUPPORTED,
            AssuranceLevel.NONE,
            "local",
            "RUNTIME",
            "a" * 64,
            "b" * 64,
        )
        from elmos_formal_assurance.contracts import Waiver

        waiver = Waiver(
            "obl-1",
            "APPROVED",
            "HIGH",
            ("a", "b"),
            ("control-1",),
            (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        )
        decision = evaluate_release_gate(
            [
                obligation(
                    AssuranceLevel.A1_BOUNDED,
                    criticality=Criticality.P0,
                    property_kind="NONINTERFERENCE",
                )
            ],
            {"obl-1": result},
            {"obl-1": waiver},
        )
        self.assertEqual(decision.decision, "DENY")


if __name__ == "__main__":
    unittest.main()
