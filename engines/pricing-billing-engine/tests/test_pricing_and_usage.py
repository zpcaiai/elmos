from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from elmos_pricing_billing.errors import DomainError
from elmos_pricing_billing.models import Entitlement, PlanState, PriceBookState, PriceEntry, UsageEvent
from elmos_pricing_billing.pricing import PlanEntitlementService, PriceBookService
from elmos_pricing_billing.usage import UsageMeteringService

JAN = datetime(2026, 1, 1, tzinfo=UTC)
FEB = datetime(2026, 2, 1, tzinfo=UTC)
MAR = datetime(2026, 3, 1, tzinfo=UTC)


def approved_book(service: PriceBookService, *, version: int, start: datetime, end: datetime | None, rate: int) -> None:
    draft = service.create_draft(
        book_id="book",
        version=version,
        effective_from=start,
        effective_to=end,
        entries=(PriceEntry("sku", "usd", rate, provider_rate_micro=rate // 2),),
    )
    approved = service.approve(
        book_id="book",
        version=version,
        expected_revision=draft.revision,
        approved_at=start,
    )
    assert approved.state is PriceBookState.APPROVED


def test_price_books_are_versioned_event_time_bound_and_immutable() -> None:
    service = PriceBookService()
    approved_book(service, version=1, start=JAN, end=FEB, rate=20_000)
    approved_book(service, version=2, start=FEB, end=None, rate=40_000)

    january, january_entry = service.resolve(book_id="book", sku="sku", occurred_at=JAN)
    february, february_entry = service.resolve(book_id="book", sku="sku", occurred_at=FEB)

    assert (january.version, january_entry.unit_rate_micro) == (1, 20_000)
    assert (february.version, february_entry.unit_rate_micro) == (2, 40_000)
    with pytest.raises(DomainError, match="PRICE_BOOK_IMMUTABLE"):
        service.revise_draft(
            book_id="book",
            version=1,
            expected_revision=1,
            entries=(PriceEntry("sku", "USD", 99_000),),
        )


def test_price_book_rejects_overlapping_approved_windows() -> None:
    service = PriceBookService()
    approved_book(service, version=1, start=JAN, end=MAR, rate=20_000)
    draft = service.create_draft(
        book_id="book",
        version=2,
        effective_from=FEB,
        entries=(PriceEntry("sku", "USD", 40_000),),
    )
    with pytest.raises(DomainError, match="PRICE_BOOK_EFFECTIVE_OVERLAP"):
        service.approve(book_id="book", version=2, expected_revision=draft.revision, approved_at=FEB)


def test_plan_snapshot_quota_and_atomic_concurrency() -> None:
    service = PlanEntitlementService()
    draft = service.create_draft(
        plan_id="pro",
        version=1,
        entitlements=(Entitlement("build", 10),),
        concurrency_limit=3,
    )
    plan = service.approve(plan_id="pro", version=1, expected_revision=draft.revision)
    snapshot = service.activate(tenant_id="tenant-a", plan_id="pro", version=1, activated_at=JAN)

    assert plan.state is PlanState.APPROVED
    assert snapshot.digest == plan.digest
    assert service.consume(tenant_id="tenant-a", capability="build", units=7) == 3
    with pytest.raises(DomainError, match="ENTITLEMENT_EXCEEDED"):
        service.consume(tenant_id="tenant-a", capability="build", units=4)

    def try_acquire(_: int) -> str:
        try:
            return service.acquire(tenant_id="tenant-a", capability="build")
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=20) as pool:
        outcomes = tuple(pool.map(try_acquire, range(20)))
    leases = tuple(value for value in outcomes if value.startswith("lease:"))
    assert len(leases) == 3
    assert outcomes.count("CONCURRENCY_LIMIT_EXCEEDED") == 17
    assert service.active_count(tenant_id="tenant-a") == 3

    with pytest.raises(DomainError, match="TENANT_ISOLATION_VIOLATION"):
        service.release(tenant_id="tenant-b", lease_id=leases[0])
    for lease in leases:
        service.release(tenant_id="tenant-a", lease_id=lease)
    assert service.active_count(tenant_id="tenant-a") == 0


def test_usage_is_immutable_deduped_event_time_rated_and_byok_split() -> None:
    prices = PriceBookService()
    approved_book(prices, version=1, start=JAN, end=FEB, rate=20_000)
    approved_book(prices, version=2, start=FEB, end=None, rate=40_000)
    usage = UsageMeteringService(prices, book_id="book")

    january = UsageEvent("tenant", "event-1", "sku", 2_000_000, JAN, True, "corr-1")
    first = usage.ingest(january)
    duplicate = usage.ingest(january)
    later = usage.ingest(UsageEvent("tenant", "event-2", "sku", 2_000_000, FEB, False, "corr-2"))

    assert first is duplicate
    assert first.price_book_version == 1
    assert first.provider_cost_micro == 0
    assert first.platform_cost_micro == 20_000
    assert first.billable_minor == 2
    assert later.price_book_version == 2
    assert later.provider_cost_micro == 40_000
    assert later.billable_minor == 8
    with pytest.raises(DomainError, match="USAGE_EVENT_CONFLICT"):
        usage.ingest(UsageEvent("tenant", "event-1", "sku", 3_000_000, JAN, True, "corr-1"))


def test_usage_rejects_unapproved_or_ambiguous_rate() -> None:
    prices = PriceBookService()
    prices.create_draft(
        book_id="book",
        version=1,
        effective_from=JAN,
        entries=(PriceEntry("sku", "USD", 10_000),),
    )
    usage = UsageMeteringService(prices, book_id="book")
    with pytest.raises(DomainError, match="PRICE_BOOK_UNRESOLVED"):
        usage.ingest(UsageEvent("tenant", "event", "sku", 1_000_000, JAN, False, "corr"))
