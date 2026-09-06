"""Host-owned bounded work scheduling; no repository-controlled executors."""

from __future__ import annotations

import threading
from collections.abc import Callable, Hashable, Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True)
class ExecutionBudget:
    max_workers: int = 1
    memory_budget_mib: int = 1024
    per_worker_mib: int = 512

    def __post_init__(self) -> None:
        if (
            type(self.max_workers) is not int or not 1 <= self.max_workers <= 8
            or type(self.memory_budget_mib) is not int or not 1 <= self.memory_budget_mib <= 65536
            or type(self.per_worker_mib) is not int or not 1 <= self.per_worker_mib <= self.memory_budget_mib
        ):
            raise ValueError("EXECUTION_RESOURCE_BUDGET_INVALID")

    @property
    def workers(self) -> int:
        return min(self.max_workers, self.memory_budget_mib // self.per_worker_mib)


def bounded_map(function: Callable[[T], R], items: Iterable[T], budget: ExecutionBudget) -> Iterator[R]:
    """At most ``workers`` running/submitted units; deterministic result order.

    There is no unbounded ThreadPoolExecutor.map submission or waiting queue.
    On failure, cancel work not started and await active work before returning,
    so pipeline cleanup cannot race workers still writing owned unit outputs.
    """
    iterator = iter(items)
    if budget.workers == 1:
        for item in iterator:
            yield function(item)
        return
    pending: list[Future[R]] = []
    with ThreadPoolExecutor(max_workers=budget.workers, thread_name_prefix="elmos-work-unit") as pool:
        try:
            for _ in range(budget.workers):
                try:
                    pending.append(pool.submit(function, next(iterator)))
                except StopIteration:
                    break
            while pending:
                future = pending.pop(0)
                yield future.result()
                try:
                    pending.append(pool.submit(function, next(iterator)))
                except StopIteration:
                    pass
        finally:
            for future in pending:
                future.cancel()


_guard = threading.Lock()
_locks: dict[Hashable, tuple[threading.RLock, int]] = {}


@contextmanager
def keyed_lock(key: Hashable) -> Iterator[None]:
    """Single-flight initialization per identity; retire entries after waiters."""
    with _guard:
        lock, users = _locks.get(key, (threading.RLock(), 0))
        _locks[key] = lock, users + 1
    try:
        with lock:
            yield
    finally:
        with _guard:
            _, users = _locks[key]
            if users == 1:
                del _locks[key]
            else:
                _locks[key] = lock, users - 1
