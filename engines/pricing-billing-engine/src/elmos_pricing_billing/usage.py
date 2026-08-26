from __future__ import annotations

from threading import RLock

from .errors import require
from .models import RatedUsage, UsageEvent, canonical_digest
from .money import QUANTITY_SCALE, checked_add, checked_mul, micro_to_minor, round_half_up_div
from .pricing import PriceBookService


class UsageMeteringService:
    """Immutable, deduplicated usage with event-time price resolution."""

    def __init__(self, price_books: PriceBookService, *, book_id: str) -> None:
        self._price_books = price_books
        self._book_id = book_id
        self._lock = RLock()
        self._events: dict[tuple[str, str], tuple[str, RatedUsage]] = {}

    def ingest(self, event: UsageEvent) -> RatedUsage:
        fingerprint = canonical_digest(
            {
                "tenant_id": event.tenant_id,
                "event_id": event.event_id,
                "sku": event.sku,
                "quantity_micro": event.quantity_micro,
                "occurred_at": event.occurred_at.isoformat(),
                "byok": event.byok,
                "correlation_id": event.correlation_id,
            }
        )
        key = (event.tenant_id, event.event_id)
        with self._lock:
            existing = self._events.get(key)
            if existing is not None:
                require(
                    existing[0] == fingerprint, "USAGE_EVENT_CONFLICT", "usage event id was reused with different input"
                )
                return existing[1]
            book, price = self._price_books.resolve(
                book_id=self._book_id,
                sku=event.sku,
                occurred_at=event.occurred_at,
            )
            gross_numerator = checked_mul(
                event.quantity_micro,
                price.unit_rate_micro,
                field="gross_usage_cost_numerator",
            )
            provider_numerator = checked_mul(
                event.quantity_micro,
                price.provider_rate_micro,
                field="provider_usage_cost_numerator",
            )
            gross_micro = round_half_up_div(gross_numerator, QUANTITY_SCALE)
            provider_component = round_half_up_div(provider_numerator, QUANTITY_SCALE)
            platform_component = gross_micro - provider_component
            charged_provider = 0 if event.byok else provider_component
            billable_micro = checked_add(platform_component, charged_provider, field="billable_micro")
            billable_minor = max(price.minimum_minor, micro_to_minor(billable_micro))
            rated = RatedUsage(
                event=event,
                price_book_id=book.book_id,
                price_book_version=book.version,
                price_book_digest=book.digest,
                currency=price.currency,
                platform_cost_micro=platform_component,
                provider_cost_micro=charged_provider,
                billable_micro=billable_micro,
                billable_minor=billable_minor,
            )
            self._events[key] = (fingerprint, rated)
            return rated

    def events(self, *, tenant_id: str) -> tuple[RatedUsage, ...]:
        with self._lock:
            return tuple(value[1] for key, value in self._events.items() if key[0] == tenant_id)
