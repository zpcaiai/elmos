from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from elmos_pricing_billing.commercial import ProjectContractService, QuoteBudgetService, TaskCostEstimator
from elmos_pricing_billing.errors import DomainError
from elmos_pricing_billing.ledger import LedgerService
from elmos_pricing_billing.models import EstimateDistribution, PricingModel, QuoteState
from elmos_pricing_billing.money import Money

NOW = datetime(2026, 1, 1, tzinfo=UTC)
ESTIMATE = EstimateDistribution(8_000, 10_000, 12_000, 600, 3)


def create_quote(
    quotes: QuoteBudgetService,
    *,
    quote_id: str,
    money_minor: int,
    hard_cap_minor: int,
    threshold_percents: tuple[int, ...],
    expires_at: datetime,
) -> None:
    quotes.create(
        quote_id=quote_id,
        tenant_id="tenant",
        scope_digest="scope",
        money=Money("USD", money_minor),
        estimate=ESTIMATE,
        price_book_id="price-book",
        price_book_version=1,
        price_book_digest="price-book-digest",
        model_strategy="BALANCED",
        human_time_reference_seconds=3_600,
        confidence_basis_points=8_000,
        hard_cap_minor=hard_cap_minor,
        threshold_percents=threshold_percents,
        expires_at=expires_at,
    )


def funded_quote_service() -> tuple[LedgerService, QuoteBudgetService]:
    ledger = LedgerService()
    ledger.opening_balance(
        tenant_id="tenant",
        money=Money("USD", 100_000),
        idempotency_key="opening",
        reference="opening",
        occurred_at=NOW,
    )
    return ledger, QuoteBudgetService(ledger)


def test_estimate_percentiles_are_monotonic_and_eta_is_separate() -> None:
    estimate = TaskCostEstimator.estimate(
        cost_samples_minor=(10, 100, 30, 80, 50, 60, 20, 90, 70, 40),
        machine_eta_seconds=777,
    )
    assert (estimate.p50_minor, estimate.p80_minor, estimate.p90_minor) == (50, 80, 90)
    assert estimate.machine_eta_seconds == 777
    assert estimate.sample_count == 10


def test_quote_acceptance_is_scope_expiry_and_atomic_reserve_bound() -> None:
    ledger, quotes = funded_quote_service()
    create_quote(
        quotes,
        quote_id="quote",
        money_minor=10_000,
        hard_cap_minor=20_000,
        threshold_percents=(50, 80, 100),
        expires_at=NOW + timedelta(hours=1),
    )
    quote = quotes.get(quote_id="quote", tenant_id="tenant")

    def accept(index: int) -> str:
        try:
            quotes.accept(
                quote_id=quote.quote_id,
                tenant_id="tenant",
                scope_digest="scope",
                accepted_by=f"actor-{index}",
                accepted_at=NOW,
            )
            return "OK"
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = tuple(pool.map(accept, range(12)))
    assert outcomes.count("OK") == 1
    assert outcomes.count("QUOTE_ALREADY_ACCEPTED") == 11
    accepted = quotes.get(quote_id="quote", tenant_id="tenant")
    assert accepted.state is QuoteState.ACCEPTED
    assert accepted.reserve_transaction_id is not None
    assert ledger.balance(tenant_id="tenant", currency="USD").reserved_minor == 20_000


def test_quote_rejects_scope_expiry_cross_tenant_and_insufficient_funds() -> None:
    _, quotes = funded_quote_service()
    create_quote(
        quotes,
        quote_id="quote",
        money_minor=10_000,
        hard_cap_minor=10_000,
        threshold_percents=(100,),
        expires_at=NOW,
    )
    with pytest.raises(DomainError, match="QUOTE_SCOPE_MISMATCH"):
        quotes.accept(
            quote_id="quote",
            tenant_id="tenant",
            scope_digest="stale",
            accepted_by="actor",
            accepted_at=NOW,
        )
    with pytest.raises(DomainError, match="QUOTE_EXPIRED"):
        quotes.accept(
            quote_id="quote",
            tenant_id="tenant",
            scope_digest="scope",
            accepted_by="actor",
            accepted_at=NOW + timedelta(microseconds=1),
        )
    with pytest.raises(DomainError, match="TENANT_ISOLATION_VIOLATION"):
        quotes.get(quote_id="quote", tenant_id="other")
    with pytest.raises(DomainError, match="TENANT_ISOLATION_VIOLATION"):
        quotes.expire(
            quote_id="quote",
            tenant_id="other",
            as_of=NOW + timedelta(microseconds=1),
        )

    empty = QuoteBudgetService(LedgerService())
    create_quote(
        empty,
        quote_id="empty",
        money_minor=1,
        hard_cap_minor=1,
        threshold_percents=(100,),
        expires_at=NOW,
    )
    with pytest.raises(DomainError, match="INSUFFICIENT_AVAILABLE_BALANCE"):
        empty.accept(
            quote_id="empty",
            tenant_id="tenant",
            scope_digest="scope",
            accepted_by="actor",
            accepted_at=NOW,
        )


def test_budget_guard_runs_before_effect_at_thresholds_and_hard_cap() -> None:
    _, quotes = funded_quote_service()
    create_quote(
        quotes,
        quote_id="quote",
        money_minor=5_000,
        hard_cap_minor=10_000,
        threshold_percents=(50, 80, 100),
        expires_at=NOW + timedelta(days=1),
    )
    quotes.accept(
        quote_id="quote",
        tenant_id="tenant",
        scope_digest="scope",
        accepted_by="actor",
        accepted_at=NOW,
    )
    threshold = quotes.preflight_spend(quote_id="quote", tenant_id="tenant", next_minor=5_000)
    assert not threshold.allowed
    assert threshold.reason == "THRESHOLD_APPROVAL_REQUIRED"
    assert quotes.get(quote_id="quote", tenant_id="tenant").committed_spend_minor == 0

    quotes.commit_spend(
        quote_id="quote",
        tenant_id="tenant",
        amount_minor=5_000,
        idempotency_key="spend-1",
        approved_thresholds=frozenset({50}),
    )
    over_cap = quotes.preflight_spend(quote_id="quote", tenant_id="tenant", next_minor=5_001)
    assert not over_cap.allowed
    assert over_cap.reason == "HARD_CAP_EXCEEDED"
    assert quotes.get(quote_id="quote", tenant_id="tenant").committed_spend_minor == 5_000


def test_quote_reserves_hard_cap_and_spend_commands_are_idempotent() -> None:
    ledger, quotes = funded_quote_service()
    create_quote(
        quotes,
        quote_id="hard-cap",
        money_minor=10_000,
        hard_cap_minor=12_000,
        threshold_percents=(100,),
        expires_at=NOW + timedelta(days=1),
    )
    quote = quotes.get(quote_id="hard-cap", tenant_id="tenant")
    quotes.accept(
        quote_id=quote.quote_id,
        tenant_id="tenant",
        scope_digest=quote.scope_digest,
        accepted_by="approver",
        accepted_at=NOW,
    )
    assert ledger.balance(tenant_id="tenant", currency="USD").reserved_minor == 12_000

    first = quotes.commit_spend(
        quote_id=quote.quote_id,
        tenant_id="tenant",
        amount_minor=3_000,
        idempotency_key="spend-1",
    )
    repeated = quotes.commit_spend(
        quote_id=quote.quote_id,
        tenant_id="tenant",
        amount_minor=3_000,
        idempotency_key="spend-1",
    )
    assert first is repeated
    assert repeated.committed_spend_minor == 3_000
    with pytest.raises(DomainError, match="IDEMPOTENCY_CONFLICT"):
        quotes.commit_spend(
            quote_id=quote.quote_id,
            tenant_id="tenant",
            amount_minor=3_001,
            idempotency_key="spend-1",
        )

    final = quotes.commit_spend(
        quote_id=quote.quote_id,
        tenant_id="tenant",
        amount_minor=8_500,
        idempotency_key="spend-2",
    )
    assert final.committed_spend_minor == 11_500
    ledger.capture(
        tenant_id="tenant",
        money=Money("USD", final.committed_spend_minor),
        idempotency_key="capture",
        reference=quote.quote_id,
        occurred_at=NOW,
    )
    ledger.release(
        tenant_id="tenant",
        money=Money("USD", 500),
        idempotency_key="release",
        reference=quote.quote_id,
        occurred_at=NOW,
    )
    balance = ledger.balance(tenant_id="tenant", currency="USD")
    assert (balance.available_minor, balance.reserved_minor, balance.captured_minor) == (88_500, 0, 11_500)


def test_fixed_and_capped_contract_change_order_and_acceptance() -> None:
    projects = ProjectContractService()
    fixed = projects.create(
        contract_id="fixed",
        tenant_id="tenant",
        model=PricingModel.FIXED,
        scope_digest="scope-v1",
        currency="USD",
        fixed_minor=10_000,
    )
    capped = projects.create(
        contract_id="capped",
        tenant_id="tenant",
        model=PricingModel.CAPPED,
        scope_digest="cap-scope",
        currency="USD",
        cap_minor=20_000,
    )
    assert projects.billable_minor(contract_id=fixed.contract_id, tenant_id="tenant", measured_minor=99_999) == 10_000
    assert projects.billable_minor(contract_id=capped.contract_id, tenant_id="tenant", measured_minor=25_000) == 20_000

    change = projects.propose_change(
        change_id="change",
        contract_id="fixed",
        tenant_id="tenant",
        proposed_by="maker",
        new_scope_digest="scope-v2",
        delta_minor=2_000,
    )
    with pytest.raises(DomainError, match="MAKER_CHECKER_VIOLATION"):
        projects.approve_change(change_id=change.change_id, tenant_id="tenant", approved_by="maker")
    with pytest.raises(DomainError, match="TENANT_ISOLATION_VIOLATION"):
        projects.approve_change(change_id=change.change_id, tenant_id="other", approved_by="checker")
    revised = projects.approve_change(change_id=change.change_id, tenant_id="tenant", approved_by="checker")
    assert revised.fixed_minor == 12_000
    assert revised.version == 2
    with pytest.raises(DomainError, match="ACCEPTANCE_SCOPE_MISMATCH"):
        projects.accept_milestone(
            acceptance_id="acceptance",
            contract_id="fixed",
            tenant_id="tenant",
            milestone="M1",
            accepted_by="customer",
            accepted_at=NOW,
            scope_digest="scope-v1",
        )
    accepted = projects.accept_milestone(
        acceptance_id="acceptance",
        contract_id="fixed",
        tenant_id="tenant",
        milestone="M1",
        accepted_by="customer",
        accepted_at=NOW,
        scope_digest="scope-v2",
    )
    assert accepted.scope_digest == "scope-v2"
