from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from threading import RLock

from .errors import DomainError, require
from .models import (
    Entitlement,
    Plan,
    PlanSnapshot,
    PlanState,
    PriceBook,
    PriceBookState,
    PriceEntry,
    require_aware,
)
from .money import checked_add, require_positive


class PriceBookService:
    """Versioned immutable price-book repository with explicit approval."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._books: dict[tuple[str, int], PriceBook] = {}

    def create_draft(
        self,
        *,
        book_id: str,
        version: int,
        effective_from: datetime,
        entries: tuple[PriceEntry, ...],
        effective_to: datetime | None = None,
    ) -> PriceBook:
        key = (book_id, version)
        with self._lock:
            require(key not in self._books, "PRICE_BOOK_VERSION_EXISTS", "price-book version already exists")
            book = PriceBook(
                book_id=book_id,
                version=version,
                revision=1,
                state=PriceBookState.DRAFT,
                effective_from=effective_from,
                effective_to=effective_to,
                entries=entries,
            )
            self._books[key] = book
            return book

    def revise_draft(
        self,
        *,
        book_id: str,
        version: int,
        expected_revision: int,
        entries: tuple[PriceEntry, ...],
    ) -> PriceBook:
        key = (book_id, version)
        with self._lock:
            current = self._required(key)
            require(current.state is PriceBookState.DRAFT, "PRICE_BOOK_IMMUTABLE", "only a draft may be revised")
            require(
                current.revision == expected_revision,
                "PRICE_BOOK_REVISION_CONFLICT",
                "expected price-book revision does not match",
            )
            revised = replace(current, revision=current.revision + 1, entries=entries)
            self._books[key] = revised
            return revised

    def approve(self, *, book_id: str, version: int, expected_revision: int, approved_at: datetime) -> PriceBook:
        key = (book_id, version)
        normalized_at = require_aware(approved_at, field_name="approved_at")
        with self._lock:
            current = self._required(key)
            require(current.state is PriceBookState.DRAFT, "PRICE_BOOK_NOT_DRAFT", "price book is not a draft")
            require(
                current.revision == expected_revision,
                "PRICE_BOOK_REVISION_CONFLICT",
                "expected price-book revision does not match",
            )
            for other in self._books.values():
                if other.book_id != book_id or other.state is not PriceBookState.APPROVED:
                    continue
                require(
                    not self._windows_overlap(current, other),
                    "PRICE_BOOK_EFFECTIVE_OVERLAP",
                    "approved price-book windows cannot overlap",
                    other_version=other.version,
                )
            approved = replace(current, state=PriceBookState.APPROVED, approved_at=normalized_at)
            self._books[key] = approved
            return approved

    def get(self, *, book_id: str, version: int) -> PriceBook:
        with self._lock:
            return self._required((book_id, version))

    def resolve(self, *, book_id: str, sku: str, occurred_at: datetime) -> tuple[PriceBook, PriceEntry]:
        normalized_at = require_aware(occurred_at, field_name="occurred_at")
        with self._lock:
            candidates = [
                book
                for book in self._books.values()
                if book.book_id == book_id
                and book.state is PriceBookState.APPROVED
                and book.effective_from <= normalized_at
                and (book.effective_to is None or normalized_at < book.effective_to)
            ]
            require(
                len(candidates) == 1,
                "PRICE_BOOK_UNRESOLVED",
                "event time must resolve to exactly one approved price book",
            )
            book = candidates[0]
            entries = [entry for entry in book.entries if entry.sku == sku]
            require(len(entries) == 1, "SKU_NOT_PRICED", "sku is absent from the resolved price book", sku=sku)
            return book, entries[0]

    def approved_versions(self, *, book_id: str) -> tuple[PriceBook, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        book
                        for book in self._books.values()
                        if book.book_id == book_id and book.state is PriceBookState.APPROVED
                    ),
                    key=lambda book: book.version,
                )
            )

    def _required(self, key: tuple[str, int]) -> PriceBook:
        try:
            return self._books[key]
        except KeyError as exc:
            raise DomainError("PRICE_BOOK_NOT_FOUND", "price-book version was not found") from exc

    @staticmethod
    def _windows_overlap(left: PriceBook, right: PriceBook) -> bool:
        left_end = left.effective_to
        right_end = right.effective_to
        return (left_end is None or right.effective_from < left_end) and (
            right_end is None or left.effective_from < right_end
        )


class PlanEntitlementService:
    """Immutable plan snapshots with lock-protected quota and concurrency leases."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._plans: dict[tuple[str, int], Plan] = {}
        self._snapshots: dict[str, PlanSnapshot] = {}
        self._consumed: dict[tuple[str, str], int] = {}
        self._leases: dict[str, tuple[str, str]] = {}
        self._tenant_leases: dict[str, set[str]] = {}
        self._lease_sequence = 0

    def create_draft(
        self,
        *,
        plan_id: str,
        version: int,
        entitlements: tuple[Entitlement, ...],
        concurrency_limit: int,
    ) -> Plan:
        key = (plan_id, version)
        with self._lock:
            require(key not in self._plans, "PLAN_VERSION_EXISTS", "plan version already exists")
            plan = Plan(
                plan_id=plan_id,
                version=version,
                revision=1,
                state=PlanState.DRAFT,
                entitlements=entitlements,
                concurrency_limit=concurrency_limit,
            )
            self._plans[key] = plan
            return plan

    def revise_draft(
        self,
        *,
        plan_id: str,
        version: int,
        expected_revision: int,
        entitlements: tuple[Entitlement, ...],
        concurrency_limit: int,
    ) -> Plan:
        key = (plan_id, version)
        with self._lock:
            current = self._required_plan(key)
            require(current.state is PlanState.DRAFT, "PLAN_IMMUTABLE", "only a draft plan may be revised")
            require(current.revision == expected_revision, "PLAN_REVISION_CONFLICT", "plan revision conflict")
            revised = replace(
                current,
                revision=current.revision + 1,
                entitlements=entitlements,
                concurrency_limit=concurrency_limit,
            )
            self._plans[key] = revised
            return revised

    def approve(self, *, plan_id: str, version: int, expected_revision: int) -> Plan:
        key = (plan_id, version)
        with self._lock:
            current = self._required_plan(key)
            require(current.state is PlanState.DRAFT, "PLAN_NOT_DRAFT", "plan is not a draft")
            require(current.revision == expected_revision, "PLAN_REVISION_CONFLICT", "plan revision conflict")
            approved = replace(current, state=PlanState.APPROVED)
            self._plans[key] = approved
            return approved

    def activate(self, *, tenant_id: str, plan_id: str, version: int, activated_at: datetime) -> PlanSnapshot:
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        normalized_at = require_aware(activated_at, field_name="activated_at")
        with self._lock:
            plan = self._required_plan((plan_id, version))
            require(plan.state is PlanState.APPROVED, "PLAN_NOT_APPROVED", "only an approved plan may be activated")
            require(
                not self._tenant_leases.get(tenant_id),
                "PLAN_HAS_ACTIVE_LEASES",
                "cannot replace a plan with active leases",
            )
            snapshot = PlanSnapshot(
                tenant_id=tenant_id,
                plan_id=plan.plan_id,
                version=plan.version,
                digest=plan.digest,
                activated_at=normalized_at,
                entitlements=plan.entitlements,
                concurrency_limit=plan.concurrency_limit,
            )
            self._snapshots[tenant_id] = snapshot
            self._tenant_leases.setdefault(tenant_id, set())
            return snapshot

    def snapshot(self, *, tenant_id: str) -> PlanSnapshot:
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        with self._lock:
            try:
                return self._snapshots[tenant_id]
            except KeyError as exc:
                raise DomainError("PLAN_SNAPSHOT_NOT_FOUND", "tenant has no active plan snapshot") from exc

    def consume(self, *, tenant_id: str, capability: str, units: int) -> int:
        require_positive(units, field="units")
        with self._lock:
            snapshot = self.snapshot(tenant_id=tenant_id)
            entitlement = self._entitlement(snapshot, capability)
            key = (tenant_id, capability)
            projected = checked_add(self._consumed.get(key, 0), units, field="consumed_units")
            require(projected <= entitlement.limit_units, "ENTITLEMENT_EXCEEDED", "entitlement limit exceeded")
            self._consumed[key] = projected
            return entitlement.limit_units - projected

    def acquire(self, *, tenant_id: str, capability: str) -> str:
        with self._lock:
            snapshot = self.snapshot(tenant_id=tenant_id)
            self._entitlement(snapshot, capability)
            active = self._tenant_leases.setdefault(tenant_id, set())
            require(
                len(active) < snapshot.concurrency_limit, "CONCURRENCY_LIMIT_EXCEEDED", "concurrency limit exceeded"
            )
            self._lease_sequence += 1
            lease_id = f"lease:{tenant_id}:{self._lease_sequence}"
            self._leases[lease_id] = (tenant_id, capability)
            active.add(lease_id)
            return lease_id

    def release(self, *, tenant_id: str, lease_id: str) -> None:
        with self._lock:
            owner = self._leases.get(lease_id)
            if owner is None:
                raise DomainError("LEASE_NOT_FOUND", "lease does not exist")
            require(owner[0] == tenant_id, "TENANT_ISOLATION_VIOLATION", "lease belongs to another tenant")
            del self._leases[lease_id]
            self._tenant_leases[tenant_id].remove(lease_id)

    def active_count(self, *, tenant_id: str) -> int:
        with self._lock:
            return len(self._tenant_leases.get(tenant_id, set()))

    def _required_plan(self, key: tuple[str, int]) -> Plan:
        try:
            return self._plans[key]
        except KeyError as exc:
            raise DomainError("PLAN_NOT_FOUND", "plan version was not found") from exc

    @staticmethod
    def _entitlement(snapshot: PlanSnapshot, capability: str) -> Entitlement:
        matches = [item for item in snapshot.entitlements if item.capability == capability]
        require(len(matches) == 1, "CAPABILITY_NOT_ENTITLED", "capability is not included in the plan")
        return matches[0]
