"""Thread-safe local model. NOT a database, durable workflow, or network executor.

Tests model fencing/idempotency, not external-system exactly-once guarantees.
"""
from __future__ import annotations
from dataclasses import dataclass
from threading import RLock
from .core import digest


@dataclass
class Lease:
    epoch: int
    expires_at: int
    cancelled: bool = False


class CommitLedger:
    def __init__(self) -> None:
        self._lock = RLock()
        self._leases: dict[tuple[str, str], Lease] = {}
        self._results: dict[tuple[str, str, str, str], str] = {}

    def create(self, tenant: str, run: str, now: int, ttl: int) -> int:
        if not tenant or not run or ttl <= 0:
            raise ValueError("INVALID_LEASE")
        with self._lock:
            key = tenant, run
            if key in self._leases:
                raise ValueError("RUN_EXISTS")
            self._leases[key] = Lease(1, now + ttl)
            return 1

    def replace_executor(self, tenant: str, run: str, now: int, ttl: int) -> int:
        if ttl <= 0:
            raise ValueError("INVALID_LEASE")
        with self._lock:
            lease = self._leases[(tenant, run)]
            if lease.cancelled:
                raise ValueError("RUN_CANCELLED")
            # This method models an ALREADY AUTHORIZED renewal. Actual auth
            # ceilings/revocations must be revalidated by the production broker.
            lease.epoch += 1
            lease.expires_at = now + ttl
            return lease.epoch

    def cancel(self, tenant: str, run: str) -> int:
        with self._lock:
            lease = self._leases[(tenant, run)]
            if not lease.cancelled:
                lease.epoch += 1
                lease.cancelled = True
            return lease.epoch

    def commit(self, tenant: str, run: str, step: str, epoch: int,
               idempotency_key: str, value: dict, now: int) -> str:
        if not step or not idempotency_key:
            raise ValueError("MISSING_COMMIT_IDENTITY")
        result_digest = digest(value)
        with self._lock:
            lease = self._leases[(tenant, run)]
            if lease.cancelled or epoch != lease.epoch:
                raise ValueError("FENCE_REJECTED")
            if now >= lease.expires_at:
                raise ValueError("LEASE_EXPIRED")
            key = tenant, run, step, idempotency_key
            if key in self._results:
                if self._results[key] != result_digest:
                    raise ValueError("IDEMPOTENCY_PAYLOAD_CONFLICT")
                return "DUPLICATE_SAME_RESULT"
            self._results[key] = result_digest
            return "COMMITTED"

    def result_count(self) -> int:
        with self._lock:
            return len(self._results)


class BudgetLedger:
    """Atomic local reservations; integer minor units, not approximate floats."""
    def __init__(self, available: int, concurrency_limit: int = 3) -> None:
        if type(available) is not int or available < 0 or concurrency_limit < 1:
            raise ValueError("INVALID_BUDGET")
        self.available = available
        self.concurrency_limit = concurrency_limit
        self._reservations: dict[str, int] = {}
        self._settled: dict[str, int] = {}
        self._lock = RLock()

    def reserve(self, attempt: str, maximum: int) -> str:
        if not attempt or type(maximum) is not int or maximum <= 0:
            raise ValueError("INVALID_RESERVATION")
        with self._lock:
            if attempt in self._settled:
                raise ValueError("ATTEMPT_ALREADY_SETTLED")
            if attempt in self._reservations:
                if self._reservations[attempt] != maximum:
                    raise ValueError("RESERVATION_CONFLICT")
                return "DUPLICATE"
            if len(self._reservations) >= self.concurrency_limit:
                raise ValueError("CONCURRENCY_LIMIT")
            if maximum > self.available:
                raise ValueError("BUDGET_EXHAUSTED")
            self.available -= maximum
            self._reservations[attempt] = maximum
            return "RESERVED"

    def settle(self, attempt: str, actual: int | None) -> str:
        with self._lock:
            if actual is None:
                if attempt not in self._reservations:
                    raise ValueError("UNKNOWN_RESERVATION")
                return "PENDING_RECONCILIATION"  # hold funds; do not assume zero.
            if type(actual) is not int or actual < 0:
                raise ValueError("INVALID_ACTUAL_COST")
            if attempt in self._settled:
                if self._settled[attempt] != actual:
                    raise ValueError("USAGE_CONFLICT")
                return "DUPLICATE"
            maximum = self._reservations[attempt]
            if actual > maximum:
                raise ValueError("OVERAGE_REQUIRES_RECONCILIATION")
            self.available += maximum - actual
            del self._reservations[attempt]
            self._settled[attempt] = actual
            return "SETTLED"
