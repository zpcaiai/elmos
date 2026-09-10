"""Tests for Distributed Transactions: Saga Orchestrator, TCC Coordinator, Outbox, and Distributed Lock.
"""
from __future__ import annotations

import pytest

from elmos_project_synthesis.distributed_transactions import (
    DistributedLockManager,
    FencingTokenStaleError,
    LockAcquisitionError,
    OutboxDispatcher,
    OutboxRecord,
    OutboxStore,
    SagaOrchestrator,
    SagaStepDef,
    TccCoordinator,
    TccParticipantDef,
)


def test_distributed_lock_and_fencing_token():
    lock_mgr = DistributedLockManager()
    resource = "order:ord-1001"

    # Acquire lock #1
    token1 = lock_mgr.acquire(resource, owner_id="worker-1", ttl_seconds=5)
    assert token1 == 1

    # Concurrent acquire fails
    with pytest.raises(LockAcquisitionError):
        lock_mgr.acquire(resource, owner_id="worker-2", ttl_seconds=5)

    # Validate fencing token
    lock_mgr.verify_fencing_token(resource, token=1)

    # Stale token raises FencingTokenStaleError on assertion
    with pytest.raises(FencingTokenStaleError):
        lock_mgr.verify_fencing_token(resource, token=0)

    # Release lock
    released = lock_mgr.release(resource, owner_id="worker-1")
    assert released is True

    # Next acquire gets monotonic higher fencing token
    token2 = lock_mgr.acquire(resource, owner_id="worker-2", ttl_seconds=5)
    assert token2 == 2


def test_transactional_outbox_store_and_dispatcher():
    store = OutboxStore()
    events = [
        OutboxRecord(
            event_id=f"ev-{i}",
            tenant_id="tenant-1",
            aggregate_type="Order",
            aggregate_id="ord-99",
            event_type="OrderCreated",
            payload={"index": i},
        )
        for i in range(5)
    ]
    for ev in events:
        store.insert(ev)

    dispatched_events = []

    def mock_broker_publish(record: OutboxRecord) -> bool:
        dispatched_events.append(record.event_id)
        return True

    dispatcher = OutboxDispatcher(store, publisher=mock_broker_publish, batch_size=10)
    published_cnt, failed_cnt = dispatcher.dispatch_batch()

    assert published_cnt == 5
    assert failed_cnt == 0
    assert len(dispatched_events) == 5

    # Second dispatch returns 0 because all are published
    published_cnt_2, failed_cnt_2 = dispatcher.dispatch_batch()
    assert published_cnt_2 == 0


def test_saga_orchestrator_successful_forward_execution():
    steps_executed = []

    def step1_action(ctx):
        steps_executed.append("step1")
        return {"step1_done": True}

    def step2_action(ctx):
        steps_executed.append("step2")
        return {"step2_done": True}

    steps = [
        SagaStepDef(step_id="s1", name="Step1", forward_action=step1_action, compensation_action=lambda ctx: None),
        SagaStepDef(step_id="s2", name="Step2", forward_action=step2_action, compensation_action=lambda ctx: None),
    ]

    orchestrator = SagaOrchestrator(saga_name="SAGA-001", steps=steps)
    state = orchestrator.execute(initial_context={})

    assert state.status == "COMPLETED"
    assert steps_executed == ["step1", "step2"]
    assert state.context.get("step1_done") is True
    assert state.context.get("step2_done") is True


def test_saga_orchestrator_failure_and_lifo_compensation():
    actions_run = []
    compensations_run = []

    def order_action(ctx):
        actions_run.append("order_created")
        return {"order_id": "ord-501"}

    def order_compensate(ctx):
        compensations_run.append("order_cancelled")

    def payment_action(ctx):
        actions_run.append("payment_charged")
        return {"tx_id": "tx-701"}

    def payment_compensate(ctx):
        compensations_run.append("payment_refunded")

    def inventory_action(ctx):
        actions_run.append("inventory_reserved")
        raise RuntimeError("Inventory out of stock")

    def inventory_compensate(ctx):
        compensations_run.append("inventory_released")

    steps = [
        SagaStepDef(step_id="s_ord", name="OrderStep", forward_action=order_action, compensation_action=order_compensate, max_retries=1),
        SagaStepDef(step_id="s_pay", name="PaymentStep", forward_action=payment_action, compensation_action=payment_compensate, max_retries=1),
        SagaStepDef(step_id="s_inv", name="InventoryStep", forward_action=inventory_action, compensation_action=inventory_compensate, max_retries=1),
    ]

    orchestrator = SagaOrchestrator(saga_name="SAGA-ORDER-FAIL", steps=steps)
    state = orchestrator.execute(initial_context={})

    assert state.status == "COMPENSATED"
    assert "InventoryStep" in (state.error or "")
    # Forward actions ran up to the failing step
    assert actions_run == ["order_created", "payment_charged", "inventory_reserved"]
    # Compensations executed in strict reverse LIFO order for succeeded steps: Payment then Order
    assert compensations_run == ["payment_refunded", "order_cancelled"]


def test_tcc_coordinator_lifecycle_and_defenses():
    tried = []
    confirmed = []
    cancelled = []

    p1 = TccParticipantDef(
        participant_id="acc-svc",
        name="AccountService",
        try_action=lambda ctx: (tried.append("p1_try") or True),
        confirm_action=lambda ctx: (confirmed.append("p1_confirm") or True),
        cancel_action=lambda ctx: (cancelled.append("p1_cancel") or True),
    )
    p2 = TccParticipantDef(
        participant_id="inv-svc",
        name="InventoryService",
        try_action=lambda ctx: (tried.append("p2_try") or True),
        confirm_action=lambda ctx: (confirmed.append("p2_confirm") or True),
        cancel_action=lambda ctx: (cancelled.append("p2_cancel") or True),
    )

    coordinator = TccCoordinator(tx_name="TCC-101", participants=[p1, p2])

    # 1. Success case
    ok, msg = coordinator.execute(tx_context={})
    assert ok is True
    assert tried == ["p1_try", "p2_try"]
    assert confirmed == ["p1_confirm", "p2_confirm"]
    assert cancelled == []

    # 2. Failure case with empty-rollback defense
    tried.clear()
    confirmed.clear()
    cancelled.clear()

    p_fail = TccParticipantDef(
        participant_id="credit-svc",
        name="FailingCreditService",
        try_action=lambda ctx: False,  # Rejects Try
        confirm_action=lambda ctx: (confirmed.append("p_fail_confirm") or True),
        cancel_action=lambda ctx: (cancelled.append("p_fail_cancel") or True),
    )
    fail_coordinator = TccCoordinator(tx_name="TCC-102", participants=[p1, p_fail])

    ok2, msg2 = fail_coordinator.execute(tx_context={})
    assert ok2 is False
    assert "Try rejected" in msg2
    # p1 was tried, then p1 cancelled. p_fail failed try, never confirmed.
    assert "p1_try" in tried
    assert "p1_cancel" in cancelled
    assert len(confirmed) == 0
