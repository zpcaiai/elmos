"""Tests for Deep-Water Industrial Pillars: SMT State Machine Prover & Jepsen Partition Verifier."""

from __future__ import annotations

import pytest

from elmos_project_synthesis.jepsen_partition_verifier import (
    JepsenNetworkPartitionVerifier,
    LockStatus,
    SettlementStatus,
)
from elmos_project_synthesis.smt_state_machine_prover import (
    DddAggregateStateMachine,
    DddStateMachineSmtProver,
    DddTransition,
    ProofVerdict,
    SmtSort,
)


def test_smt_state_machine_prover_inductive_invariants_with_real_z3() -> None:
    prover = DddStateMachineSmtProver()
    if not prover.is_z3_available():
        pytest.skip("Z3 solver binary not available in testing environment")

    # Define a sound Banking/Order Aggregate Root
    order_machine = DddAggregateStateMachine(
        name="OrderSettlementAggregate",
        states=("CREATED", "PAID", "CANCELLED"),
        initial_state="CREATED",
        terminal_states=("CANCELLED",),
        variables=(
            ("balance", SmtSort.INT),
            ("total_amount", SmtSort.INT),
            ("paid_amount", SmtSort.INT),
        ),
        invariants=(
            "balance >= 0",
            "total_amount > 0",
            "paid_amount <= total_amount",
        ),
        transitions=(
            DddTransition(
                name="AUTHORIZE_AND_SETTLE",
                from_state="CREATED",
                to_state="PAID",
                guards=(
                    "balance >= total_amount",
                    "total_amount > 0",
                ),
                actions=(
                    ("balance", "balance - total_amount"),
                    ("paid_amount", "total_amount"),
                ),
            ),
        ),
    )

    cert = prover.verify_aggregate(order_machine, timeout_sec=5)
    assert cert.is_fully_certified is True
    assert cert.theorems_verified >= 4
    assert cert.theorems_proved == cert.theorems_verified
    assert cert.theorems_refuted == 0
    assert len(cert.merkle_root_sha256) == 64
    assert "Z3" in cert.solver_version


def test_smt_state_machine_prover_counterexample_synthesis_on_buggy_transition() -> None:
    prover = DddStateMachineSmtProver()
    if not prover.is_z3_available():
        pytest.skip("Z3 solver binary not available in testing environment")

    # Buggy aggregate: forgets guard "balance >= total_amount", allowing balance to become negative!
    buggy_machine = DddAggregateStateMachine(
        name="BuggyOverdraftAggregate",
        states=("CREATED", "PAID"),
        initial_state="CREATED",
        terminal_states=(),
        variables=(
            ("balance", SmtSort.INT),
            ("total_amount", SmtSort.INT),
        ),
        invariants=(
            "balance >= 0",
            "total_amount > 0",
        ),
        transitions=(
            DddTransition(
                name="UNGUARDED_OVERDRAFT_PAY",
                from_state="CREATED",
                to_state="PAID",
                guards=("total_amount > 0",),  # MISSING "balance >= total_amount"!
                actions=(("balance", "balance - total_amount"),),
            ),
        ),
    )

    cert = prover.verify_aggregate(buggy_machine, timeout_sec=5)
    assert cert.is_fully_certified is False
    assert cert.theorems_refuted > 0

    refuted_results = [r for r in cert.proof_results if r.verdict == ProofVerdict.REFUTED]
    assert len(refuted_results) > 0
    refuted = refuted_results[0]

    assert refuted.counterexample_model is not None
    assert "balance" in refuted.counterexample_model
    assert "total_amount" in refuted.counterexample_model

    # Counterexample must satisfy: balance < total_amount so that balance_next < 0
    model = refuted.counterexample_model
    assert model["balance"] < model["total_amount"]

    # Synthesized regression test must be present and valid
    assert refuted.synthesized_regression_test is not None
    assert "def test_formal_counterexample" in refuted.synthesized_regression_test


def test_smt_terminal_state_immutability_violation() -> None:
    prover = DddStateMachineSmtProver()

    # Aggregate with illegal transition out of terminal state CANCELLED
    invalid_terminal_machine = DddAggregateStateMachine(
        name="IllegalResurrectionAggregate",
        states=("CREATED", "CANCELLED", "ACTIVE"),
        initial_state="CREATED",
        terminal_states=("CANCELLED",),
        variables=(("balance", SmtSort.INT),),
        invariants=("balance >= 0",),
        transitions=(
            DddTransition(
                name="ILLEGAL_RESURRECT",
                from_state="CANCELLED",  # Illegal transition out of terminal state!
                to_state="ACTIVE",
            ),
        ),
    )

    cert = prover.verify_aggregate(invalid_terminal_machine)
    assert cert.is_fully_certified is False
    assert cert.theorems_refuted == 1
    term_res = [r for r in cert.proof_results if "TH-TERMINAL-IMMUTABILITY" in r.theorem_id][0]
    assert term_res.verdict == ProofVerdict.REFUTED


def test_jepsen_normal_quorum_settlement() -> None:
    verifier = JepsenNetworkPartitionVerifier(node_ids=("node-a", "node-b", "node-c"))

    # Acquire distributed lock on Node A
    status, fence = verifier.acquire_distributed_lock("client-1", "ORD-1001", "node-a")
    assert status == LockStatus.ACQUIRED
    assert fence is not None

    # Settle order on Node A
    settle_status = verifier.settle_order("client-1", "ORD-1001", 10000, "node-a", fence)
    assert settle_status == SettlementStatus.COMMITTED

    # Verify replication across quorum (Node A and B and C)
    assert "ORD-1001" in verifier.nodes["node-a"].ledger
    assert "ORD-1001" in verifier.nodes["node-b"].ledger
    assert "ORD-1001" in verifier.nodes["node-c"].ledger


def test_jepsen_split_brain_partition_isolation_and_linearizability() -> None:
    verifier = JepsenNetworkPartitionVerifier(node_ids=("node-a", "node-b", "node-c"))

    # Inject partition: Majority={node-a, node-b}, Minority={node-c}
    verifier.inject_majority_minority_partition(majority=("node-a", "node-b"), minority=("node-c",))

    # 1. Minority Node C: Lock acquisition must fail closed (Quorum not reached)
    status_c, fence_c = verifier.acquire_distributed_lock("client-isolated", "ORD-2001", "node-c")
    assert status_c == LockStatus.QUORUM_NOT_REACHED
    assert fence_c is None

    # 2. Minority Node C: Settlement attempt must fail closed
    settle_c = verifier.settle_order("client-isolated", "ORD-2001", 5000, "node-c", 999)
    assert settle_c == SettlementStatus.REJECTED_SPLIT_BRAIN_MINORITY
    assert "ORD-2001" not in verifier.nodes["node-c"].ledger

    # 3. Majority Node A: Lock acquisition and settlement must succeed
    status_a, fence_a = verifier.acquire_distributed_lock("client-leader", "ORD-2001", "node-a")
    assert status_a == LockStatus.ACQUIRED
    assert fence_a is not None

    settle_a = verifier.settle_order("client-leader", "ORD-2001", 5000, "node-a", fence_a)
    assert settle_a == SettlementStatus.COMMITTED
    assert "ORD-2001" in verifier.nodes["node-a"].ledger
    assert "ORD-2001" in verifier.nodes["node-b"].ledger
    assert "ORD-2001" not in verifier.nodes["node-c"].ledger

    # 4. Audit linearizability: must prove zero split-brain divergence and zero double commits
    audit = verifier.audit_linearizability_and_split_brain()
    assert audit["passed"] is True
    assert audit["audit_verdict"] == "LINEARIZABLE_NO_SPLIT_BRAIN"
    assert audit["double_commits_count"] == 0
    assert audit["divergent_orders_count"] == 0
    assert audit["minority_rejections_count"] >= 1


def test_jepsen_partition_heal_and_anti_entropy_reconciliation() -> None:
    verifier = JepsenNetworkPartitionVerifier(node_ids=("node-a", "node-b", "node-c"))

    # Partition and commit on Majority
    verifier.inject_majority_minority_partition(majority=("node-a", "node-b"), minority=("node-c",))
    _, fence = verifier.acquire_distributed_lock("client-x", "ORD-3001", "node-a")
    assert fence is not None
    verifier.settle_order("client-x", "ORD-3001", 8000, "node-a", fence)

    assert "ORD-3001" not in verifier.nodes["node-c"].ledger

    # Heal network partition
    verifier.heal_partition()
    assert verifier.matrix.is_connected("node-a", "node-c") is True

    # Run anti-entropy reconciliation sync
    synced = verifier.synchronize_reconcile_after_heal(authoritative_node_id="node-a")
    assert synced["node-c"] == 1
    assert "ORD-3001" in verifier.nodes["node-c"].ledger
    assert verifier.nodes["node-c"].ledger["ORD-3001"].amount_cents == 8000
