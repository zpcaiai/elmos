"""Tests for Seata Distributed Transaction Engine: TM, TC, RM, AT Mode 2PC, and TCC."""

from __future__ import annotations

from typing import Any

import pytest

from elmos_project_synthesis.seata_distributed_transactions import (
    BranchType,
    DirtyWriteException,
    GlobalTransactionStatus,
    LockConflictError,
    RootContext,
    SeataResourceManager,
    SeataTransactionCoordinator,
    SeataTransactionManager,
    TccAntiHangingManager,
)


def test_seata_at_mode_successful_commit():
    tc = SeataTransactionCoordinator()
    tm = SeataTransactionManager(tc)
    rm = SeataResourceManager(tc)

    # 1. TM Begin global transaction
    xid = tm.begin(transaction_name="create_enterprise_order", timeout_ms=30000)
    assert xid.startswith("127.0.0.1:8091:")
    assert RootContext.get_xid() == xid

    # Simulated database table state
    db_state = {"order:1001": {"id": "1001", "status": "DRAFT", "amount": "0.00"}}

    # 2. Branch 1: Update order state
    before_img1 = dict(db_state["order:1001"])
    db_state["order:1001"] = {"id": "1001", "status": "PAID", "amount": "250.00"}
    after_img1 = dict(db_state["order:1001"])

    b1_id = rm.register_branch(
        xid=xid,
        resource_id="jdbc:mysql://orders-db:3306/orders",
        branch_type=BranchType.AT,
        lock_keys=["orders:order:1001"],
    )
    rm.record_undo_log(
        xid=xid,
        branch_id=b1_id,
        table_name="orders",
        pk="order:1001",
        before_image=before_img1,
        after_image=after_img1,
    )

    # 3. TM Commit global transaction
    status = tm.commit(xid)
    assert status == GlobalTransactionStatus.COMMITTED
    assert RootContext.get_xid() is None

    # Verify locks released and undo logs deleted
    assert not rm.lock_mgr.is_locked("orders:order:1001")
    assert rm.undo_table.get_records_for_xid(xid) == []


def test_seata_at_mode_rollback_and_restore():
    tc = SeataTransactionCoordinator()
    tm = SeataTransactionManager(tc)
    rm = SeataResourceManager(tc)

    xid = tm.begin(transaction_name="transfer_funds")
    
    # State tracking
    account_state = {"acc-01": 500}

    def current_accessor(pk: str) -> dict[str, Any]:
        return {"balance": account_state[pk]}

    def state_mutator(pk: str, field: str, val: Any) -> None:
        account_state.update({pk: val})

    rm.register_data_accessor("accounts", current_accessor, state_mutator)

    # Branch 1 executes: balance from 500 down to 300
    before_img = {"balance": 500}
    account_state["acc-01"] = 300
    after_img = {"balance": 300}

    b1_id = rm.register_branch(
        xid=xid,
        resource_id="jdbc:mysql://account-db:3306/accounts",
        branch_type=BranchType.AT,
        lock_keys=["accounts:acc-01"],
    )
    rm.record_undo_log(
        xid=xid,
        branch_id=b1_id,
        table_name="accounts",
        pk="acc-01",
        before_image=before_img,
        after_image=after_img,
    )

    # Branch 2 fails -> TM initiates rollback
    status = tm.rollback(xid)
    assert status == GlobalTransactionStatus.ROLLBACKED

    # Verify state rolled back to before_image
    assert account_state["acc-01"] == 500
    assert not rm.lock_mgr.is_locked("accounts:acc-01")


def test_seata_dirty_write_detection():
    tc = SeataTransactionCoordinator()
    tm = SeataTransactionManager(tc)
    rm = SeataResourceManager(tc)

    xid = tm.begin(transaction_name="dirty_write_demo")

    account_state = {"acc-99": 200}

    def current_accessor(pk: str) -> dict[str, Any]:
        return {"balance": account_state[pk]}

    def state_mutator(pk: str, field: str, val: Any) -> None:
        account_state.update({pk: val})

    rm.register_data_accessor("accounts", current_accessor, state_mutator)

    before_img = {"balance": 200}
    account_state["acc-99"] = 150
    after_img = {"balance": 150}

    b_id = rm.register_branch(
        xid=xid,
        resource_id="jdbc:mysql://account-db:3306/accounts",
        branch_type=BranchType.AT,
        lock_keys=["accounts:acc-99"],
    )
    rm.record_undo_log(
        xid=xid,
        branch_id=b_id,
        table_name="accounts",
        pk="acc-99",
        before_image=before_img,
        after_image=after_img,
    )

    # Rogue write behind the back (e.g. manual DBA update or concurrent non-locked tx)
    account_state["acc-99"] = 999  # Does not match after_img (150)

    # Rollback must detect dirty write and raise DirtyWriteException
    with pytest.raises(DirtyWriteException) as exc_info:
        tm.rollback(xid)
    assert "Dirty write detected" in str(exc_info.value)


def test_seata_global_lock_conflict():
    tc = SeataTransactionCoordinator()
    tm = SeataTransactionManager(tc)
    rm = SeataResourceManager(tc)

    xid1 = tm.begin("tx1")
    xid2 = tm.begin("tx2")

    # Tx1 acquires lock
    b1 = rm.register_branch(xid1, "res-1", BranchType.AT, ["orders:1001"])
    assert b1 is not None

    # Tx2 tries to acquire same lock -> raises LockConflictError
    with pytest.raises((LockConflictError, RuntimeError)) as exc_info:
        rm.register_branch(xid2, "res-1", BranchType.AT, ["orders:1001"])
    assert "Global lock conflict" in str(exc_info.value)

    # Tx1 commits and releases
    tm.commit(xid1)
    assert not rm.lock_mgr.is_locked("orders:1001")

    # Tx2 now acquires lock successfully
    b2 = rm.register_branch(xid2, "res-1", BranchType.AT, ["orders:1001"])
    assert b2 is not None
    tm.commit(xid2)


def test_seata_tcc_mode_anti_hanging_and_empty_rollback():
    anti_hanging = TccAntiHangingManager()
    xid = "127.0.0.1:8091:tcc-001"
    branch_id = "branch-tcc-01"

    # Scenario: Cancel arrives before Try (network delay / timeout)
    # 1. Cancel called -> empty rollback permitted, records execution
    assert anti_hanging.can_execute_cancel(xid, branch_id) is True
    anti_hanging.record_cancel_executed(xid, branch_id)

    # 2. Delayed Try arrives later -> anti-hanging rejects it
    assert anti_hanging.can_execute_try(xid, branch_id) is False

    # Scenario: Normal Try -> Confirm
    xid_normal = "127.0.0.1:8091:tcc-002"
    branch_normal = "branch-tcc-02"
    assert anti_hanging.can_execute_try(xid_normal, branch_normal) is True
    anti_hanging.record_try_executed(xid_normal, branch_normal)
    assert anti_hanging.can_execute_confirm(xid_normal, branch_normal) is True


def test_root_context_thread_and_contextvar_isolation():
    RootContext.unbind()
    assert RootContext.get_xid() is None

    RootContext.bind("test-xid-123")
    assert RootContext.get_xid() == "test-xid-123"
    assert RootContext.in_global_transaction() is True

    RootContext.unbind()
    assert RootContext.get_xid() is None
    assert RootContext.in_global_transaction() is False
