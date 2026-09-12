"""Runnable production-like systems with planted concurrency defects.

These are not synthetic assertion stubs.  Each module is valid Python that
exhibits a real industrial failure class until healed.
"""

from __future__ import annotations

PLANTED_RACE = '''\
"""Shared-balance ledger with a classic lost-update race."""
from __future__ import annotations

import threading
from typing import Callable


def _preempt_point() -> None:
    return None


class BankLedger:
    def __init__(self) -> None:
        self.balance = 0

    def deposit(self, amount: int) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        current = self.balance
        _preempt_point()
        current += amount
        self.balance = current

    def withdraw(self, amount: int) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        current = self.balance
        if current < amount:
            raise ValueError("insufficient funds")
        _preempt_point()
        current -= amount
        self.balance = current


def run_concurrent_deposits(n_threads: int, n_each: int, preempt: Callable[[], None] | None = None) -> int:
    ledger = BankLedger()
    if preempt is not None:
        globals()["_preempt_point"] = preempt
    threads = [threading.Thread(target=lambda: [ledger.deposit(1) for _ in range(n_each)]) for _ in range(n_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return ledger.balance
'''

PLANTED_DEADLOCK = '''\
"""Two-lock transfer with inverted acquisition order."""
from __future__ import annotations

import threading
from typing import Callable


def _preempt_point() -> None:
    return None


class DualResource:
    def __init__(self) -> None:
        self.lock_a = threading.Lock()
        self.lock_b = threading.Lock()
        self.a = 10
        self.b = 10

    def move_ab(self) -> None:
        with self.lock_a:
            _preempt_point()
            with self.lock_b:
                self.a -= 1
                self.b += 1

    def move_ba(self) -> None:
        with self.lock_b:
            _preempt_point()
            with self.lock_a:
                self.b -= 1
                self.a += 1


def run_opposite_transfers(timeout: float = 0.4, preempt: Callable[[], None] | None = None) -> bool:
    resource = DualResource()
    if preempt is not None:
        globals()["_preempt_point"] = preempt
    first = threading.Thread(target=resource.move_ab, daemon=True)
    second = threading.Thread(target=resource.move_ba, daemon=True)
    first.start()
    second.start()
    first.join(timeout)
    second.join(timeout)
    alive = first.is_alive() or second.is_alive()
    return not alive
'''

PLANTED_ROW_LOCK = '''\
"""In-memory two-phase row lock manager that deadlocks on opposite key order."""
from __future__ import annotations

import threading
from typing import Callable


def _preempt_point() -> None:
    return None


class RowLockManager:
    def __init__(self) -> None:
        self.balances = {1: 100, 2: 100}
        self._row_locks = {1: threading.Lock(), 2: threading.Lock()}

    def transfer(self, from_id: int, to_id: int, amount: int) -> None:
        if from_id == to_id:
            raise ValueError("same account")
        self._row_locks[from_id].acquire()
        _preempt_point()
        self._row_locks[to_id].acquire()
        try:
            if self.balances[from_id] < amount:
                raise ValueError("insufficient funds")
            self.balances[from_id] -= amount
            self.balances[to_id] += amount
        finally:
            self._row_locks[to_id].release()
            self._row_locks[from_id].release()


def run_crossing_transfers(timeout: float = 0.4, preempt: Callable[[], None] | None = None) -> bool:
    store = RowLockManager()
    if preempt is not None:
        globals()["_preempt_point"] = preempt
    first = threading.Thread(target=lambda: store.transfer(1, 2, 10), daemon=True)
    second = threading.Thread(target=lambda: store.transfer(2, 1, 10), daemon=True)
    first.start()
    second.start()
    first.join(timeout)
    second.join(timeout)
    return not (first.is_alive() or second.is_alive())
'''

PLANTED_LEASE = '''\
"""Lease lock without fencing tokens: stale holders can still mutate state."""
from __future__ import annotations


class StaleFencingToken(RuntimeError):
    pass


class LeaseLockStore:
    def __init__(self) -> None:
        self.holder = None
        self.value = 0

    def acquire(self, holder: str) -> bool:
        self.holder = holder
        return True

    def write(self, holder: str, value: int) -> None:
        self.value = value


def demo_stale_overwrite() -> int:
    store = LeaseLockStore()
    store.acquire("writer-a")
    store.acquire("writer-b")
    store.write("writer-a", 99)
    return store.value
'''

PLANTED_ASYNC = '''\
"""Async pipeline that uses sleep as a synchronization barrier."""
from __future__ import annotations

import asyncio


class AsyncPipeline:
    def __init__(self) -> None:
        self.done = False
        self.result = None

    async def produce(self) -> None:
        await asyncio.sleep(0)
        self.result = 42
        self.done = True

    async def consume(self) -> int:
        await asyncio.sleep(0.01)
        if not self.done:
            raise RuntimeError("timing: producer has not published")
        return int(self.result)


async def run_pipeline() -> int:
    pipe = AsyncPipeline()
    consumer = asyncio.create_task(pipe.consume())
    producer = asyncio.create_task(pipe.produce())
    await producer
    return await consumer
'''

STRICT_RACE_TEST = '''\
def test_ledger_conserves_deposits(ledger_balance, expected):
    assert ledger_balance == expected
    assert expected == 4000
    assert ledger_balance > 0
'''

STRICT_DEADLOCK_TEST = '''\
def test_opposite_transfers_complete(completed):
    assert completed is True
    assert completed == True
'''

STRICT_LEASE_TEST = '''\
def test_stale_writer_cannot_commit(raised):
    assert raised is True
'''

STRICT_ASYNC_TEST = '''\
def test_pipeline_result(result):
    assert result == 42
'''

PLANTED: dict[str, str] = {
    "ledger_race.py": PLANTED_RACE,
    "lock_deadlock.py": PLANTED_DEADLOCK,
    "row_lock_deadlock.py": PLANTED_ROW_LOCK,
    "lease_no_fence.py": PLANTED_LEASE,
    "async_sleep_race.py": PLANTED_ASYNC,
}

STRICT_TESTS: dict[str, str] = {
    "test_ledger_race.py": STRICT_RACE_TEST,
    "test_lock_deadlock.py": STRICT_DEADLOCK_TEST,
    "test_lease_no_fence.py": STRICT_LEASE_TEST,
    "test_async_sleep_race.py": STRICT_ASYNC_TEST,
}
