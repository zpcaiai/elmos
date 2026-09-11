"""Seata-Compatible Distributed Transactions Engine.

Implements the enterprise-standard Seata distributed transaction protocol:
1. TM (Transaction Manager):
   - Global transaction boundary definition (@global_transactional).
   - Lifecycle orchestration: begin, commit, rollback.
2. TC (Transaction Coordinator):
   - Global session & branch session tracking.
   - Global lock management (table & row lock mutex) preventing dirty-writes.
   - Two-phase commit (Phase 2 Commit) and rollback (Phase 2 Rollback) orchestration.
3. RM (Resource Manager):
   - AT Mode (Automatic 2PC):
     * Phase 1: Before-Image capture, business SQL execution, After-Image capture,
       undo_log persistence, and branch registration.
     * Phase 2 Commit: Asynchronous cleanup of undo_log records.
     * Phase 2 Rollback: Dirty-write detection (validating DB state == After-Image),
       data rollback to Before-Image, and lock release.
   - TCC Mode:
     * Try, Confirm, Cancel with empty rollback protection and anti-hanging.
4. Context Propagation:
   - RootContext for thread-local and contextvar XID binding.
   - Standard HTTP headers: TX_XID, X-Global-XID, X-Branch-ID.
"""

from __future__ import annotations

import contextvars
import copy
import datetime as dt
import enum
import functools
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# Standard Seata HTTP Headers
SEATA_HEADER_XID = "TX_XID"
SEATA_HEADER_GLOBAL_XID = "X-Global-XID"
SEATA_HEADER_BRANCH_ID = "X-Branch-ID"


class GlobalStatus(enum.Enum):
    """Seata Global Transaction Lifecycle States."""

    BEGIN = "Begin"
    COMMITTING = "Committing"
    COMMITTED = "Committed"
    ROLLBACKING = "Rollbacking"
    ROLLBACKED = "Rollbacked"
    TIMEOUT_ROLLBACKING = "TimeoutRollbacking"
    FAILED = "Failed"


GlobalTransactionStatus = GlobalStatus


class BranchStatus(enum.Enum):
    """Seata Branch Transaction States."""

    REGISTERED = "Registered"
    PHASE_ONE_DONE = "PhaseOne_Done"
    PHASE_ONE_FAILED = "PhaseOne_Failed"
    PHASE_TWO_COMMITTED = "PhaseTwo_Committed"
    PHASE_TWO_ROLLBACKED = "PhaseTwo_Rollbacked"
    PHASE_TWO_FAILED = "PhaseTwo_Failed"


class BranchType(enum.Enum):
    """Supported Seata Branch Types."""

    AT = "AT"
    TCC = "TCC"
    SAGA = "SAGA"
    XA = "XA"


# ============================================================================
# Context Propagation (RootContext)
# ============================================================================

_xid_context_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("seata_xid", default=None)


class RootContext:
    """Thread-safe and Async-safe Global Transaction Context Manager."""

    _thread_local = threading.local()

    @classmethod
    def bind(cls, xid: str) -> None:
        """Bind XID to current context."""
        _xid_context_var.set(xid)
        cls._thread_local.xid = xid

    @classmethod
    def unbind(cls) -> str | None:
        """Unbind and return previous XID."""
        prev = cls.get_xid()
        _xid_context_var.set(None)
        cls._thread_local.xid = None
        return prev

    @classmethod
    def get_xid(cls) -> str | None:
        """Retrieve current XID from contextvar or thread-local."""
        val = _xid_context_var.get()
        if val is not None:
            return val
        return getattr(cls._thread_local, "xid", None)

    @classmethod
    def in_global_transaction(cls) -> bool:
        """Check if currently executing within a global transaction."""
        return cls.get_xid() is not None


# ============================================================================
# Global Lock Manager
# ============================================================================


class LockConflictError(Exception):
    """Raised when a branch fails to acquire a global row lock."""


class DirtyWriteError(Exception):
    """Raised when After-Image mismatch indicates an unmanaged dirty write."""


DirtyWriteException = DirtyWriteError


class GlobalLockManager:
    """Manages table and row-level distributed locks for Seata AT mode."""

    def __init__(self) -> None:
        self._locks: dict[str, str] = {}  # "table:pk" -> xid
        self._lock = threading.Lock()

    def acquire_locks(self, xid: str, lock_keys: list[str]) -> bool:
        """Acquire row locks for a list of table:pk resources. Atomic."""
        with self._lock:
            # First check for conflicts
            for key in lock_keys:
                current_holder = self._locks.get(key)
                if current_holder is not None and current_holder != xid:
                    raise LockConflictError(
                        f"Global lock conflict on resource '{key}': held by '{current_holder}', requested by '{xid}'"
                    )

            # Grant all locks
            for key in lock_keys:
                self._locks[key] = xid
            return True

    def release_locks(self, xid: str) -> None:
        """Release all locks held by the given XID."""
        with self._lock:
            keys_to_remove = [k for k, v in self._locks.items() if v == xid]
            for k in keys_to_remove:
                del self._locks[k]

    def is_locked(self, lock_key: str) -> bool:
        with self._lock:
            return lock_key in self._locks


# ============================================================================
# AT Mode Undo Log Models
# ============================================================================


@dataclass
class UndoLogRecord:
    """Persistent representation of an AT mode undo_log record."""

    id: str
    branch_id: str
    xid: str
    context: dict[str, Any]
    rollback_info: dict[str, Any]  # {"table": str, "before_image": dict, "after_image": dict}
    log_status: str = "Normal"  # Normal, GlobalFinished
    created_at: str = field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())


class UndoLogTable:
    """In-memory or database-backed undo_log storage."""

    def __init__(self) -> None:
        self._records: dict[str, UndoLogRecord] = {}  # record_id -> record
        self._lock = threading.Lock()

    def insert(self, record: UndoLogRecord) -> None:
        with self._lock:
            self._records[record.id] = record

    def find_by_xid(self, xid: str) -> list[UndoLogRecord]:
        with self._lock:
            return [r for r in self._records.values() if r.xid == xid]

    def find_by_branch_id(self, branch_id: str) -> list[UndoLogRecord]:
        with self._lock:
            return [r for r in self._records.values() if r.branch_id == branch_id]

    def delete_by_xid(self, xid: str) -> int:
        with self._lock:
            to_delete = [r.id for r in self._records.values() if r.xid == xid]
            for rid in to_delete:
                del self._records[rid]
            return len(to_delete)

    def mark_finished(self, xid: str) -> None:
        with self._lock:
            for r in self._records.values():
                if r.xid == xid:
                    r.log_status = "GlobalFinished"

    get_records_for_xid = find_by_xid


class TccAntiHangingManager:
    """Protects against TCC empty rollback and hanging calls.

    If Cancel is executed first (empty rollback due to timeout or network loss),
    a subsequent delayed Try for the same (xid, branch_id) must be blocked (anti-hanging).
    """

    def __init__(self) -> None:
        self._try_executed: set[str] = set()
        self._confirm_executed: set[str] = set()
        self._cancel_executed: set[str] = set()
        self._lock = threading.Lock()

    def _key(self, xid: str, branch_id: str) -> str:
        return f"{xid}:{branch_id}"

    def can_execute_try(self, xid: str, branch_id: str) -> bool:
        with self._lock:
            k = self._key(xid, branch_id)
            return k not in self._cancel_executed

    def record_try_executed(self, xid: str, branch_id: str) -> None:
        with self._lock:
            self._try_executed.add(self._key(xid, branch_id))

    def can_execute_confirm(self, xid: str, branch_id: str) -> bool:
        with self._lock:
            k = self._key(xid, branch_id)
            return k in self._try_executed and k not in self._cancel_executed

    def record_confirm_executed(self, xid: str, branch_id: str) -> None:
        with self._lock:
            self._confirm_executed.add(self._key(xid, branch_id))

    def can_execute_cancel(self, xid: str, branch_id: str) -> bool:
        with self._lock:
            k = self._key(xid, branch_id)
            return k not in self._confirm_executed

    def record_cancel_executed(self, xid: str, branch_id: str) -> None:
        with self._lock:
            self._cancel_executed.add(self._key(xid, branch_id))


# ============================================================================
# TC (Transaction Coordinator)
# ============================================================================


@dataclass
class BranchSession:
    """Session state for a registered branch transaction."""

    branch_id: str
    xid: str
    resource_id: str
    branch_type: BranchType
    status: BranchStatus
    lock_keys: list[str] = field(default_factory=list)
    application_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class GlobalSession:
    """Session state for an active global transaction."""

    xid: str
    transaction_name: str
    timeout_seconds: float
    status: GlobalStatus
    started_at: float = field(default_factory=time.monotonic)
    branches: list[BranchSession] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        return (time.monotonic() - self.started_at) > self.timeout_seconds


class SeataTransactionCoordinator:
    """Coordinates global transactions, branches, and global locks."""

    def __init__(self) -> None:
        self._sessions: dict[str, GlobalSession] = {}
        self.lock_manager = GlobalLockManager()
        self._lock = threading.Lock()

    def begin(self, transaction_name: str, timeout_seconds: float = 60.0) -> str:
        """Start a new global transaction, returns unique XID."""
        xid = f"127.0.0.1:8091:{uuid4().hex[:12]}"
        session = GlobalSession(
            xid=xid,
            transaction_name=transaction_name,
            timeout_seconds=timeout_seconds,
            status=GlobalStatus.BEGIN,
        )
        with self._lock:
            self._sessions[xid] = session
        logger.info("Seata TC: Global transaction [%s] begun: '%s'", xid, transaction_name)
        return xid

    def register_branch(
        self,
        xid: str,
        resource_id: str,
        branch_type: BranchType,
        lock_keys: list[str],
        application_data: dict[str, Any] | None = None,
    ) -> str:
        """Register a branch transaction with TC and acquire global locks."""
        with self._lock:
            session = self._sessions.get(xid)
            if not session:
                raise ValueError(f"Global transaction [{xid}] not found")
            if session.status != GlobalStatus.BEGIN:
                raise ValueError(f"Global transaction [{xid}] is not in active state (status={session.status})")

            # Acquire global locks
            if lock_keys:
                self.lock_manager.acquire_locks(xid, lock_keys)

            branch_id = f"br-{uuid4().hex[:10]}"
            branch = BranchSession(
                branch_id=branch_id,
                xid=xid,
                resource_id=resource_id,
                branch_type=branch_type,
                status=BranchStatus.REGISTERED,
                lock_keys=lock_keys,
                application_data=application_data or {},
            )
            session.branches.append(branch)
            logger.info("Seata TC: Branch [%s] registered under XID [%s] (type=%s)", branch_id, xid, branch_type.value)
            return branch_id

    def report_branch_status(self, xid: str, branch_id: str, status: BranchStatus) -> None:
        """Update branch status reported by RM."""
        with self._lock:
            session = self._sessions.get(xid)
            if not session:
                return
            for b in session.branches:
                if b.branch_id == branch_id:
                    b.status = status
                    break

    def get_session(self, xid: str) -> GlobalSession | None:
        with self._lock:
            return self._sessions.get(xid)

    def commit(self, xid: str, resource_manager: SeataResourceManager | None = None) -> bool:
        """Coordinate Phase 2 Commit across all branches."""
        rm = resource_manager or getattr(self, "_default_rm", None)
        if rm is None:
            rm = SeataResourceManager(self)

        with self._lock:
            session = self._sessions.get(xid)
            if not session:
                raise ValueError(f"Global transaction [{xid}] not found")
            session.status = GlobalStatus.COMMITTING

        all_committed = True
        for branch in session.branches:
            ok = rm.branch_commit(branch.branch_id, xid, branch.branch_type)
            if ok:
                branch.status = BranchStatus.PHASE_TWO_COMMITTED
            else:
                branch.status = BranchStatus.PHASE_TWO_FAILED
                all_committed = False

        with self._lock:
            session.status = GlobalStatus.COMMITTED if all_committed else GlobalStatus.FAILED
            # Release all global locks upon successful commit
            self.lock_manager.release_locks(xid)

        logger.info("Seata TC: Global transaction [%s] commit finished. Success: %s", xid, all_committed)
        return all_committed

    def rollback(self, xid: str, resource_manager: SeataResourceManager | None = None) -> bool:
        """Coordinate Phase 2 Rollback in reverse (LIFO) order across all branches."""
        rm = resource_manager or getattr(self, "_default_rm", None)
        if rm is None:
            rm = SeataResourceManager(self)

        with self._lock:
            session = self._sessions.get(xid)
            if not session:
                raise ValueError(f"Global transaction [{xid}] not found")
            session.status = GlobalStatus.ROLLBACKING

        all_rollbacked = True
        # Rollback in reverse branch order
        for branch in reversed(session.branches):
            ok = rm.branch_rollback(branch.branch_id, xid, branch.branch_type)
            if ok:
                branch.status = BranchStatus.PHASE_TWO_ROLLBACKED
            else:
                branch.status = BranchStatus.PHASE_TWO_FAILED
                all_rollbacked = False

        with self._lock:
            session.status = GlobalStatus.ROLLBACKED if all_rollbacked else GlobalStatus.FAILED
            # Release all global locks upon rollback
            self.lock_manager.release_locks(xid)

        logger.info("Seata TC: Global transaction [%s] rollback finished. Success: %s", xid, all_rollbacked)
        return all_rollbacked


# ============================================================================
# RM (Resource Manager)
# ============================================================================


class SeataResourceManager:
    """Resource Manager managing AT undo_log and TCC lifecycle."""

    def __init__(self, coordinator: SeataTransactionCoordinator) -> None:
        self.coordinator = coordinator
        self.coordinator._default_rm = self
        self.undo_log_table = UndoLogTable()
        self._tcc_actions: dict[str, dict[str, Callable[[dict[str, Any]], bool]]] = {}
        # Simulated database table store: table_name -> {pk: row_dict}
        self.simulated_db: dict[str, dict[str, dict[str, Any]]] = {}
        self._custom_accessors: dict[str, tuple[Callable[[str], dict[str, Any]], Callable[[str, str, Any], None]]] = {}

    @property
    def lock_mgr(self) -> GlobalLockManager:
        return self.coordinator.lock_manager

    @property
    def undo_table(self) -> UndoLogTable:
        return self.undo_log_table

    def register_data_accessor(
        self,
        table: str,
        accessor: Callable[[str], dict[str, Any]],
        mutator: Callable[[str, str, Any], None],
    ) -> None:
        self._custom_accessors[table] = (accessor, mutator)

    def register_branch(
        self,
        xid: str,
        resource_id: str,
        branch_type: BranchType,
        lock_keys: list[str],
        application_data: dict[str, Any] | None = None,
    ) -> str:
        return self.coordinator.register_branch(
            xid=xid,
            resource_id=resource_id,
            branch_type=branch_type,
            lock_keys=lock_keys,
            application_data=application_data,
        )

    def record_undo_log(
        self,
        xid: str,
        branch_id: str,
        table_name: str,
        pk: str,
        before_image: dict[str, Any],
        after_image: dict[str, Any],
    ) -> UndoLogRecord:
        record = UndoLogRecord(
            id=f"undo-{uuid4().hex[:12]}",
            branch_id=branch_id,
            xid=xid,
            context={"table": table_name, "pk": pk},
            rollback_info={
                "table": table_name,
                "pk": pk,
                "before_image": before_image,
                "after_image": after_image,
            },
        )
        self.undo_log_table.insert(record)
        return record

    def register_tcc_participant(
        self,
        action_name: str,
        confirm: Callable[[dict[str, Any]], bool],
        cancel: Callable[[dict[str, Any]], bool],
    ) -> None:
        """Register TCC two-phase handlers."""
        self._tcc_actions[action_name] = {"confirm": confirm, "cancel": cancel}

    # --- AT Mode Execution ---

    def execute_at_update(
        self,
        table: str,
        pk: str,
        update_fn: Callable[[dict[str, Any]], dict[str, Any]],
        resource_id: str = "default_ds",
    ) -> dict[str, Any]:
        """Execute DML in AT mode: Capture Before-Image, execute, capture After-Image, save undo_log."""
        xid = RootContext.get_xid()
        if not xid:
            raise RuntimeError("Cannot execute AT update outside an active Seata global transaction")

        lock_key = f"{table}:{pk}"
        branch_id = self.coordinator.register_branch(
            xid=xid,
            resource_id=resource_id,
            branch_type=BranchType.AT,
            lock_keys=[lock_key],
        )

        table_data = self.simulated_db.setdefault(table, {})
        current_row = table_data.get(pk)
        if current_row is None:
            raise ValueError(f"Record '{pk}' in table '{table}' does not exist")

        # 1. Capture Before-Image
        before_image = copy.deepcopy(current_row)

        # 2. Execute business modification
        after_image = update_fn(copy.deepcopy(before_image))
        table_data[pk] = copy.deepcopy(after_image)

        # 3. Write undo_log record
        record = UndoLogRecord(
            id=f"undo-{uuid4().hex[:12]}",
            branch_id=branch_id,
            xid=xid,
            context={"table": table, "pk": pk},
            rollback_info={
                "table": table,
                "pk": pk,
                "before_image": before_image,
                "after_image": after_image,
            },
        )
        self.undo_log_table.insert(record)

        # 4. Report Phase 1 Done
        self.coordinator.report_branch_status(xid, branch_id, BranchStatus.PHASE_ONE_DONE)
        return after_image

    # --- Phase 2 Handlers ---

    def branch_commit(self, branch_id: str, xid: str, branch_type: BranchType) -> bool:
        """Phase 2 Commit handler."""
        if branch_type == BranchType.AT:
            # In AT mode, commit simply clears undo_log records
            self.undo_log_table.delete_by_xid(xid)
            return True
        elif branch_type == BranchType.TCC:
            session = self.coordinator.get_session(xid)
            if not session:
                return False
            for b in session.branches:
                if b.branch_id == branch_id:
                    action_name = b.application_data.get("action_name")
                    if action_name and action_name in self._tcc_actions:
                        return self._tcc_actions[action_name]["confirm"](b.application_data)
            return True
        return True

    def branch_rollback(self, branch_id: str, xid: str, branch_type: BranchType) -> bool:
        """Phase 2 Rollback handler."""
        if branch_type == BranchType.AT:
            records = self.undo_log_table.find_by_branch_id(branch_id)
            for r in records:
                table = r.rollback_info["table"]
                pk = r.rollback_info["pk"]
                before = r.rollback_info["before_image"]
                after = r.rollback_info["after_image"]

                if table in self._custom_accessors:
                    acc, mut = self._custom_accessors[table]
                    current = acc(pk)
                    if current != after:
                        raise DirtyWriteError(
                            f"Dirty write detected on table '{table}', pk '{pk}'! Current={current}, Expected After={after}"
                        )
                    for k, v in before.items():
                        mut(pk, k, v)
                else:
                    table_data = self.simulated_db.setdefault(table, {})
                    current = table_data.get(pk)

                    # Dirty-write detection: current row state MUST match After-Image!
                    if current != after:
                        raise DirtyWriteError(
                            f"Dirty write detected on table '{table}', pk '{pk}'! Current={current}, Expected After={after}"
                        )

                    # Revert data to Before-Image
                    table_data[pk] = copy.deepcopy(before)
                logger.info("Seata RM: AT Rollback restored %s:%s to Before-Image", table, pk)

            self.undo_log_table.mark_finished(xid)
            return True

        elif branch_type == BranchType.TCC:
            session = self.coordinator.get_session(xid)
            if not session:
                return False
            for b in session.branches:
                if b.branch_id == branch_id:
                    action_name = b.application_data.get("action_name")
                    if action_name and action_name in self._tcc_actions:
                        return self._tcc_actions[action_name]["cancel"](b.application_data)
            return True

        return True


# ============================================================================
# TM (Transaction Manager) & Decorator
# ============================================================================


class SeataTransactionManager:
    """Transaction Manager that orchestrates the global transaction lifecycle."""

    def __init__(
        self,
        coordinator: SeataTransactionCoordinator,
        resource_manager: SeataResourceManager | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.resource_manager = resource_manager

    def begin(
        self,
        transaction_name: str,
        timeout_ms: int = 60000,
        timeout_seconds: float | None = None,
    ) -> str:
        secs = timeout_seconds if timeout_seconds is not None else (timeout_ms / 1000.0)
        xid = self.coordinator.begin(transaction_name, timeout_seconds=secs)
        RootContext.bind(xid)
        return xid

    def commit(self, xid: str) -> GlobalStatus:
        rm = self.resource_manager or getattr(self.coordinator, "_default_rm", None)
        if rm is None:
            rm = SeataResourceManager(self.coordinator)
        ok = self.coordinator.commit(xid, rm)
        RootContext.unbind()
        return GlobalStatus.COMMITTED if ok else GlobalStatus.FAILED

    def rollback(self, xid: str) -> GlobalStatus:
        rm = self.resource_manager or getattr(self.coordinator, "_default_rm", None)
        if rm is None:
            rm = SeataResourceManager(self.coordinator)
        ok = self.coordinator.rollback(xid, rm)
        RootContext.unbind()
        return GlobalStatus.ROLLBACKED if ok else GlobalStatus.FAILED

    def execute_global_transaction(
        self,
        name: str,
        action: Callable[[], Any],
        timeout_seconds: float = 60.0,
    ) -> Any:
        """Execute action within a managed Seata global transaction."""
        xid = self.coordinator.begin(name, timeout_seconds=timeout_seconds)
        RootContext.bind(xid)

        try:
            result = action()
            # Phase 2: Commit
            rm = self.resource_manager or getattr(self.coordinator, "_default_rm", None)
            if rm is None:
                rm = SeataResourceManager(self.coordinator)
            commit_ok = self.coordinator.commit(xid, rm)
            if not commit_ok:
                raise RuntimeError(f"Seata Phase 2 Commit failed for global transaction [{xid}]")
            return result
        except Exception as exc:
            logger.warning("Seata TM: Exception caught in [%s], triggering Phase 2 Rollback: %s", xid, exc)
            # Phase 2: Rollback
            rm = self.resource_manager or getattr(self.coordinator, "_default_rm", None)
            if rm is None:
                rm = SeataResourceManager(self.coordinator)
            self.coordinator.rollback(xid, rm)
            raise
        finally:
            RootContext.unbind()


def global_transactional(
    name: str | None = None,
    timeout_seconds: float = 60.0,
    tm_provider: Callable[[], SeataTransactionManager] | None = None,
) -> Callable[..., Any]:
    """Decorator to wrap a method with Seata @GlobalTransactional boundary."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tx_name = name or func.__name__
            if RootContext.in_global_transaction():
                # Already in a global transaction; propagate existing XID
                return func(*args, **kwargs)

            if tm_provider is None:
                raise RuntimeError("No SeataTransactionManager provider configured")

            tm = tm_provider()
            return tm.execute_global_transaction(
                name=tx_name,
                action=lambda: func(*args, **kwargs),
                timeout_seconds=timeout_seconds,
            )

        return wrapper

    return decorator
