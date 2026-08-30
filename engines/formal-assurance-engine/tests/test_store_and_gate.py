from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    def test_concurrent_retry_schedulers_cannot_fork_one_terminal_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "retry-race.sqlite3"
            first = StateStore(database)
            second = StateStore(database)
            current = make_scope()
            try:
                first.submit_run(current, "race-root", "race-obligation")
                leased = first.lease_run(current, "race-root", "worker-a", 1)
                first.start_run(
                    current, "race-root", "worker-a", leased["fencing_token"]
                )
                first.authorized_transition(
                    current,
                    "race-root",
                    "worker-a",
                    leased["fencing_token"],
                    ProofRunState.TIMED_OUT,
                )
                barrier = threading.Barrier(3)
                successes: list[str] = []
                failures: list[Exception] = []

                def schedule(store: StateStore, retry_id: str) -> None:
                    barrier.wait()
                    try:
                        result = store.retry_run(
                            current,
                            "race-root",
                            retry_id,
                            maximum_attempts=2,
                        )
                        successes.append(str(result["run_id"]))
                    except Exception as exc:  # captured for cross-thread assertion
                        failures.append(exc)

                threads = [
                    threading.Thread(
                        target=schedule, args=(first, "race-retry-a")
                    ),
                    threading.Thread(
                        target=schedule, args=(second, "race-retry-b")
                    ),
                ]
                for thread in threads:
                    thread.start()
                barrier.wait()
                for thread in threads:
                    thread.join(timeout=10)
                    self.assertFalse(thread.is_alive())
                self.assertEqual(len(successes), 1)
                self.assertEqual(len(failures), 1)
                self.assertIsInstance(failures[0], StoreError)
                retry_events = [
                    event
                    for event in first.events(current, "proof_run", "race-root")
                    if event["eventType"] == "retry_scheduled"
                ]
                self.assertEqual(len(retry_events), 1)
            finally:
                second.close()
                first.close()

    def test_legacy_sqlite_schema_migrates_retry_lineage_before_indexing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "legacy-state.sqlite3"
            connection = sqlite3.connect(database)
            connection.execute(
                """
                CREATE TABLE proof_runs (
                  tenant_id TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  account_id TEXT NOT NULL,
                  obligation_id TEXT NOT NULL,
                  state TEXT NOT NULL,
                  owner_id TEXT,
                  fencing_token INTEGER NOT NULL,
                  lease_expires_at TEXT,
                  result_json TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  PRIMARY KEY (tenant_id, run_id)
                )
                """
            )
            connection.commit()
            connection.close()

            store = StateStore(database)
            current = make_scope()
            try:
                root = store.submit_run(current, "legacy-root", "legacy-obligation")
                self.assertEqual(root["retry_attempt"], 0)
                leased = store.lease_run(current, "legacy-root", "worker-a", 1)
                store.start_run(
                    current, "legacy-root", "worker-a", leased["fencing_token"]
                )
                store.authorized_transition(
                    current,
                    "legacy-root",
                    "worker-a",
                    leased["fencing_token"],
                    ProofRunState.TIMED_OUT,
                )
                retry = store.retry_run(
                    current,
                    "legacy-root",
                    "legacy-retry",
                    maximum_attempts=1,
                )
                self.assertEqual(retry["retry_root_run_id"], "legacy-root")
                self.assertEqual(retry["retry_attempt"], 1)
                with self.assertRaises(StoreError):
                    store.retry_run(current, "legacy-root", "legacy-branch")
            finally:
                store.close()

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

    def test_gate_rejects_empty_obligation_coverage(self) -> None:
        decision = evaluate_release_gate([], {})
        self.assertEqual(decision.decision, "DENY")
        self.assertIn(
            "no required proof obligations were evaluated",
            decision.blocking_reasons,
        )

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
