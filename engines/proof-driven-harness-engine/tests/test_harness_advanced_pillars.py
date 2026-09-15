"""Physical automated test suite validating the 5 Advanced Production Harness Pillars:

1. Host Broker, Capability Lease Fencing & Two-Phase (2PC) Effect Settlement
2. PostgreSQL Adaptive Lifecycle Discovery & Reversible Forward/Undo Migrations
3. Multi-Tenant Fair Scheduling, Concurrency Slot Quotas & Noisy-Neighbor Defense
4. Crash Continuation, Orphan Task Reconciliation & Time-Travel Event Replay
5. RFC 3161 Trusted Timestamp Authority (TSA) & SCITT Merkle Transparency Log
"""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime, timedelta
import unittest

from elmos_proof_harness.host_broker import (
    CapabilityLease,
    CapabilityLeaseVerifier,
    EffectSettlementReceipt,
    HostBrokerChannel,
    SettlementLedger,
    SettlementStatus,
)
from elmos_proof_harness.postgres_lifecycle import (
    PostgresBinaryDiscovery,
    PostgresVersionInfo,
    ReversibleMigrationEngine,
)
from elmos_proof_harness.tenant_scheduler import (
    PriorityPreemptionQueue,
    PriorityTier,
    QueuedTask,
    TenantConcurrencyPool,
    TenantFairScheduler,
    TenantQuotaExceededError,
)
from elmos_proof_harness.crash_recovery import (
    InFlightOrphanReconciler,
    JournalEvent,
    TaskExecutionJournal,
    TaskLifecycleState,
    TimeTravelReplayer,
)
from elmos_proof_harness.tsa_notary import (
    MerkleTransparencyLog,
    TSANotaryAuthority,
    TimeStampToken,
)


class TestAdvancedHarnessPillars(unittest.TestCase):
    """Rigorous physical verification of the 5 production harness pillars."""

    def test_pillar1_host_broker_and_2pc_settlement(self) -> None:
        verifier = CapabilityLeaseVerifier(allowed_tenants=["tenant-enterprise", "tenant-fintech"])
        ledger = SettlementLedger()
        channel = HostBrokerChannel(lease_verifier=verifier, settlement_ledger=ledger)

        # 1. Lease verification rules
        now = datetime.now(UTC)
        valid_lease = CapabilityLease(
            lease_id="lease-001",
            tenant_id="tenant-enterprise",
            project_id="proj-core",
            actor_id="actor-orchestrator",
            purpose="production-migration",
            permissions=("external-llm-provider", "storage-upload"),
            generation_fence=10,
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=15)).isoformat(),
        )

        expired_lease = CapabilityLease(
            lease_id="lease-002",
            tenant_id="tenant-enterprise",
            project_id="proj-core",
            actor_id="actor-orchestrator",
            purpose="production-migration",
            permissions=("external-llm-provider",),
            generation_fence=10,
            issued_at=(now - timedelta(hours=2)).isoformat(),
            expires_at=(now - timedelta(hours=1)).isoformat(),
        )

        unauthorized_tenant_lease = CapabilityLease(
            lease_id="lease-003",
            tenant_id="tenant-untrusted",
            project_id="proj-core",
            actor_id="actor-orchestrator",
            purpose="test",
            permissions=("external-llm-provider",),
            generation_fence=10,
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=15)).isoformat(),
        )

        with self.assertRaises(PermissionError) as ctx:
            verifier.verify(expired_lease, "external-llm-provider", current_generation=10)
        self.assertIn("expired", str(ctx.exception))

        with self.assertRaises(PermissionError) as ctx:
            verifier.verify(unauthorized_tenant_lease, "external-llm-provider", current_generation=10)
        self.assertIn("not allowlisted", str(ctx.exception))

        with self.assertRaises(PermissionError) as ctx:
            verifier.verify(valid_lease, "external-llm-provider", current_generation=15)
        self.assertIn("stale generation fence", str(ctx.exception))

        with self.assertRaises(PermissionError) as ctx:
            verifier.verify(valid_lease, "unregistered-permission", current_generation=10)
        self.assertIn("lacks required permission", str(ctx.exception))

        # 2. HostBroker execution with 2PC commit
        channel.register_provider(
            "external-llm-provider",
            lambda payload: {"tokens_generated": 42, "model": payload.get("model", "mock-v1")},
        )

        result, receipt = channel.execute_brokered(
            capability="external-llm-provider",
            payload={"model": "deepseek-v3"},
            lease=valid_lease,
            current_generation=10,
            cost_tokens=42,
            cost_cents=2,
        )

        self.assertEqual(result["tokens_generated"], 42)
        self.assertEqual(receipt.status, SettlementStatus.COMMITTED)
        self.assertEqual(receipt.cost_tokens, 42)
        self.assertIsNotNone(receipt.execution_receipt_digest)

        # 3. HostBroker rollback on provider failure
        channel.register_provider(
            "storage-upload",
            lambda payload: (_ for _ in ()).throw(ConnectionResetError("S3 socket severed")),
        )

        with self.assertRaises(RuntimeError) as ctx:
            channel.execute_brokered(
                capability="storage-upload",
                payload={"bucket": "prod-backup"},
                lease=valid_lease,
                current_generation=10,
            )
        self.assertIn("escrow rolled back", str(ctx.exception))

    def test_pillar2_postgres_discovery_and_reversible_migrations(self) -> None:
        # Test binary discovery on this system
        discovery = PostgresBinaryDiscovery.discover()
        self.assertIsNotNone(discovery, "Postgres toolchain should be detected on host")
        self.assertGreaterEqual(discovery.major, 15, "PostgreSQL should be at least v15")

        # Test Reversible Migration Engine
        db_state: dict[str, list[str]] = {"tables": []}

        def mock_execute_sql(sql: str) -> None:
            for line in sql.strip().splitlines():
                line = line.strip()
                if line.startswith("CREATE TABLE"):
                    tbl = line.split()[2].rstrip(";(").strip()
                    db_state["tables"].append(tbl)
                elif line.startswith("DROP TABLE"):
                    tbl = line.split()[2].rstrip(";(").strip()
                    if tbl in db_state["tables"]:
                        db_state["tables"].remove(tbl)

        migration_engine = ReversibleMigrationEngine(mock_execute_sql)

        # Forward migration
        v1_sql = "CREATE TABLE proof_records (id serial, hash text);"
        migration_engine.apply_forward("V001", v1_sql)
        self.assertIn("proof_records", db_state["tables"])
        self.assertEqual(migration_engine.applied_versions, ("V001",))

        v2_sql = "CREATE TABLE audit_receipts (id serial, timestamp text);"
        migration_engine.apply_forward("V002", v2_sql)
        self.assertEqual(set(db_state["tables"]), {"proof_records", "audit_receipts"})
        self.assertEqual(migration_engine.applied_versions, ("V001", "V002"))

        # Reverse (undo) rollback
        u2_sql = "DROP TABLE audit_receipts;"
        migration_engine.apply_undo("V002", u2_sql)
        self.assertEqual(db_state["tables"], ["proof_records"])
        self.assertEqual(migration_engine.applied_versions, ("V001",))

        # Rollback V001
        u1_sql = "DROP TABLE proof_records;"
        migration_engine.apply_undo("V001", u1_sql)
        self.assertEqual(db_state["tables"], [])
        self.assertEqual(migration_engine.applied_versions, ())

        # Cannot undo unapplied
        with self.assertRaises(ValueError):
            migration_engine.apply_undo("V001", u1_sql)

    def test_pillar3_tenant_scheduler_and_noisy_neighbor_defense(self) -> None:
        # Cluster capacity = 4, Tenant quota = 2, Burst = 1
        pool = TenantConcurrencyPool(total_cluster_slots=4, default_tenant_slots=2, tenant_burst_allowance=1)
        queue = PriorityPreemptionQueue(aging_threshold_seconds=0.1, backpressure_threshold=0.75)
        scheduler = TenantFairScheduler(concurrency_pool=pool, queue=queue)

        # Tenant A acquires 2 slots (normal) + 1 slot (burst)
        s1 = scheduler.submit_or_queue("t-a-1", "tenant-a")
        s2 = scheduler.submit_or_queue("t-a-2", "tenant-a")
        s3 = scheduler.submit_or_queue("t-a-3", "tenant-a")
        self.assertEqual(s1, "EXECUTING")
        self.assertEqual(s2, "EXECUTING")
        self.assertEqual(s3, "EXECUTING")

        # Tenant A's 4th task exceeds limit -> queued
        s4 = scheduler.submit_or_queue("t-a-4", "tenant-a", priority=PriorityTier.NORMAL)
        self.assertEqual(s4, "QUEUED")

        # Total active = 3/4. Now Tenant B arrives with CRITICAL task -> immediately acquires slot 4/4!
        # Demonstrates Tenant A's excess cannot starve Tenant B!
        s_b1 = scheduler.submit_or_queue("t-b-1", "tenant-b", priority=PriorityTier.CRITICAL)
        self.assertEqual(s_b1, "EXECUTING")

        # Now cluster saturation = 4/4 = 100% (> 75% backpressure threshold)
        # Low priority BATCH task should be shed with 429 TenantQuotaExceededError
        with self.assertRaises(TenantQuotaExceededError) as ctx:
            scheduler.submit_or_queue("t-b-batch", "tenant-b", priority=PriorityTier.BATCH)
        self.assertGreater(ctx.exception.retry_after_seconds, 0)

        # Tenant A finishes task -> slot released, queued task dispatched
        next_dispatched = scheduler.complete_task("tenant-a")
        self.assertIsNotNone(next_dispatched)
        self.assertEqual(next_dispatched.task_id, "t-a-4")

    def test_pillar4_crash_recovery_and_time_travel_replay(self) -> None:
        journal = TaskExecutionJournal()

        # Simulate normal execution before crash
        journal.append_event(
            task_id="task-long-run",
            tenant_id="tenant-alpha",
            generation_fence=5,
            state=TaskLifecycleState.INITIALIZED,
            step_id=None,
            payload={"config": "v1"},
        )
        journal.append_event(
            task_id="task-long-run",
            tenant_id="tenant-alpha",
            generation_fence=5,
            state=TaskLifecycleState.STEP_COMMITTED,
            step_id="step-ast-parse",
            payload={"ast_nodes": 120},
        )
        journal.append_event(
            task_id="task-long-run",
            tenant_id="tenant-alpha",
            generation_fence=5,
            state=TaskLifecycleState.RUNNING,
            step_id="step-z3-verify",
            payload={"in_progress": True},
        )
        # --- SIMULATE SUDDEN CRASH (SIGKILL) HERE ---

        # Case A: Recover with same generation fence (safe to resume)
        reconciler_same = InFlightOrphanReconciler(journal)
        actions_same = reconciler_same.reconcile_on_startup(current_generation=5)
        self.assertEqual(actions_same["task-long-run"], "RESUMED")

        # Verify journal recorded checkpoint
        latest_event = journal.get_events("task-long-run")[-1]
        self.assertEqual(latest_event.state, TaskLifecycleState.CHECKPOINTED)
        self.assertEqual(latest_event.payload["resumable_from_step"], "step-z3-verify")

        # Case B: Stale generation fence (node restart after cluster fence incremented)
        journal_stale = TaskExecutionJournal()
        journal_stale.append_event(
            task_id="task-stale",
            tenant_id="tenant-alpha",
            generation_fence=3,
            state=TaskLifecycleState.RUNNING,
            step_id="step-db-write",
        )
        reconciler_stale = InFlightOrphanReconciler(journal_stale)
        actions_stale = reconciler_stale.reconcile_on_startup(current_generation=6)
        self.assertEqual(actions_stale["task-stale"], "ROLLED_BACK")

        # Test Time-Travel Replayer
        replayer = TimeTravelReplayer(journal)
        state_at_seq2 = replayer.replay_to_sequence("task-long-run", target_seq_num=2)
        self.assertEqual(state_at_seq2["completed_steps"], ["step-ast-parse"])
        self.assertEqual(state_at_seq2["accumulated_data"]["ast_nodes"], 120)
        self.assertNotIn("in_progress", state_at_seq2["accumulated_data"])

        state_at_seq3 = replayer.replay_to_sequence("task-long-run", target_seq_num=3)
        self.assertEqual(state_at_seq3["accumulated_data"]["in_progress"], True)

    def test_pillar5_tsa_notary_and_scitt_merkle_transparency(self) -> None:
        # 1. RFC 3161 TSA
        tsa = TSANotaryAuthority(tsa_identity="Elmos-Root-TSA-2026")
        artifact_imprint = hashlib.sha256(b"production-release-evidence-bundle-binary").hexdigest()

        token = tsa.issue_token(message_imprint=artifact_imprint, nonce=987654321)
        self.assertTrue(tsa.verify_token(token, expected_imprint=artifact_imprint))

        # Tampered imprint must fail
        tampered_imprint = hashlib.sha256(b"maliciously-altered-artifact").hexdigest()
        self.assertFalse(tsa.verify_token(token, expected_imprint=tampered_imprint))

        # 2. SCITT Merkle Transparency Log
        log = MerkleTransparencyLog()
        receipts = [
            f"receipt:{i}:{hashlib.sha256(str(i).encode()).hexdigest()}"
            for i in range(8)
        ]

        indices = [log.append(r) for r in receipts]
        self.assertEqual(len(log), 8)
        root = log.root_hash()
        self.assertEqual(len(root), 64)

        # Verify inclusion proof for every single receipt in the Merkle log
        for i, r in enumerate(receipts):
            proof = log.get_inclusion_proof(i)
            is_valid = MerkleTransparencyLog.verify_inclusion(
                leaf_entry=r,
                proof=proof,
                expected_root=root,
            )
            self.assertTrue(is_valid, f"Receipt {i} should be cryptographically proven in Merkle tree")

        # Tampered entry must fail verification
        tampered_proof = log.get_inclusion_proof(0)
        self.assertFalse(
            MerkleTransparencyLog.verify_inclusion(
                leaf_entry="forged-receipt-data",
                proof=tampered_proof,
                expected_root=root,
            )
        )


if __name__ == "__main__":
    unittest.main()
