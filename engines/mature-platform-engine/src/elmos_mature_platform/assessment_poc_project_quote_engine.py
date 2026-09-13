"""Assessment and POC Project Quote Engine (Batch 44 - Skill 1466).

Prepares commercial assessment, proof-of-concept (POC), and enterprise modernization project quotes,
cost estimates, line item scoping, discounts, and customer acceptance workflows.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    AssessmentPocQuote,
    ProjectQuoteItem,
    QuoteTier,
)


class AssessmentPocProjectQuoteEngine:
    """Commercial scoping, quotation generation, and POC pricing engine for repository migrations."""

    def __init__(self) -> None:
        self._quotes: Dict[str, AssessmentPocQuote] = {}

    def create_quote(self, quote: AssessmentPocQuote) -> str:
        """Create a new commercial quote with line items and duration estimates."""
        if not quote.customer_name or not quote.project_scope:
            raise ValueError("customer_name and project_scope are required")

        if not quote.quote_id:
            quote.quote_id = f"quote-{uuid.uuid4().hex[:8]}"

        if not quote.created_at:
            quote.created_at = datetime.now(timezone.utc).isoformat()

        quote.total_cost_usd = self._calculate_total(quote.items)
        self._quotes[quote.quote_id] = quote
        return quote.quote_id

    def add_item(self, quote_id: str, item: ProjectQuoteItem) -> AssessmentPocQuote:
        """Append a scoped work item to an existing quote and recalculate total pricing."""
        quote = self._quotes.get(quote_id)
        if not quote:
            raise ValueError(f"Quote not found: {quote_id}")

        if not item.item_id:
            item.item_id = f"qitem-{uuid.uuid4().hex[:8]}"

        quote.items.append(item)
        quote.total_cost_usd = self._calculate_total(quote.items)
        return quote

    def _calculate_total(self, items: List[ProjectQuoteItem]) -> float:
        total = 0.0
        for it in items:
            gross = it.quantity * it.unit_rate_usd
            discounted = gross * (1.0 - (it.discount_pct / 100.0))
            total += max(0.0, discounted)
        return round(total, 2)

    def update_status(self, quote_id: str, new_status: str) -> AssessmentPocQuote:
        """Update commercial status (draft, presented, accepted, declined)."""
        quote = self._quotes.get(quote_id)
        if not quote:
            raise ValueError(f"Quote not found: {quote_id}")

        valid_statuses = {"draft", "presented", "accepted", "declined"}
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status '{new_status}'. Must be one of: {valid_statuses}")

        quote.status = new_status
        return quote

    def get_quote(self, quote_id: str) -> Optional[AssessmentPocQuote]:
        """Retrieve quote details."""
        return self._quotes.get(quote_id)

    def get_quote_pipeline_report(self) -> Dict[str, Any]:
        """Generate commercial sales pipeline and quotation conversion metrics."""
        total = len(self._quotes)
        total_val = sum(q.total_cost_usd for q in self._quotes.values())
        accepted_val = sum(q.total_cost_usd for q in self._quotes.values() if q.status == "accepted")
        accepted_count = sum(1 for q in self._quotes.values() if q.status == "accepted")

        by_tier: Dict[str, int] = {}
        for q in self._quotes.values():
            t = q.tier.value
            by_tier[t] = by_tier.get(t, 0) + 1

        return {
            "total_quotes": total,
            "total_pipeline_value_usd": round(total_val, 2),
            "total_accepted_value_usd": round(accepted_val, 2),
            "quotes_by_tier": by_tier,
            "acceptance_rate_pct": (accepted_count / total * 100.0) if total > 0 else 0.0,
        }
