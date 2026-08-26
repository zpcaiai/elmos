from __future__ import annotations

import csv
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from elmos_pricing_billing.commercial_closure import ExactAmount
from elmos_pricing_billing.errors import DomainError
from elmos_pricing_billing.financial_exactness_closure import (
    AccountingEventKind,
    AllocationRule,
    AnalysisDimensions,
    AnalysisFact,
    AnalysisFactKind,
    AnalysisFactSource,
    AnalysisFactState,
    BillingCadence,
    CostDriver,
    CostMarginExactnessService,
    CreditWalletExactnessService,
    EnterpriseCreditTerms,
    InvoiceInputSnapshot,
    InvoiceLine,
    InvoiceLineKind,
    InvoiceState,
    LineDirection,
    MarginAlertKind,
    NormalizationRule,
    PipelineState,
    ProviderRate,
    RawUsageEvent,
    ResourceCategory,
    Subscription,
    SubscriptionInvoicingExactnessService,
    SubscriptionState,
    SuggestionState,
    UsageDecision,
    UsageMeteringExactnessService,
    UsageTreatment,
    WalletBucket,
)
from elmos_pricing_billing.operations_closure import (
    CertificationState,
    ExternalExecutionState,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
USD_1 = ExactAmount("USD", Decimal("1.000000"))
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def amount(value: str) -> ExactAmount:
    return ExactAmount("USD", Decimal(value))


def test_exact_40_requirement_bindings_match_pinned_traceability_source() -> None:
    mapping_path = (
        REPOSITORY_ROOT
        / "verification-packs/pricing-billing-local-v1/requirements/eb04-05-09-13.json"
    )
    source_path = (
        REPOSITORY_ROOT
        / "skills/elmos-pricing-billing-skills-v1.0.0/manifests/requirements.traceability.csv"
    )
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    with source_path.open(encoding="utf-8", newline="") as source_file:
        source_rows = tuple(
            row
            for row in csv.DictReader(source_file)
            if row["requirement_id"].split("-")[1] in {"04", "05", "09", "13"}
        )
    requirements = tuple(mapping["requirements"])
    assert mapping["requirement_count"] == len(requirements) == len(source_rows) == 40
    assert tuple(item["source_requirement_id"] for item in requirements) == tuple(
        row["requirement_id"] for row in source_rows
    )
    assert tuple(item["source_statement"] for item in requirements) == tuple(
        row["statement"] for row in source_rows
    )
    assert all(
        item["id"] == f"elmos.pricing-billing.v1/{item['source_requirement_id']}"
        for item in requirements
    )
    for item in requirements:
        module_name, symbol_name = item["implementation_symbol"].rsplit(".", 1)
        assert getattr(importlib.import_module(module_name), symbol_name) is not None
        assert "dispatcher" not in item["implementation_symbol"].casefold()
        test_path, test_name = item["local_test_node_id"].split("::", 1)
        test_source = (REPOSITORY_ROOT / "engines/pricing-billing-engine" / test_path).read_text(
            encoding="utf-8"
        )
        assert f"def {test_name}(" in test_source
    evidence = mapping["evidence_state"]
    assert evidence["java_tests"] == "LOCAL_EXECUTED"
    assert evidence["postgresql_migration_execution"] == "NOT_RUN"
    assert evidence["provider_bank_tax_runtime"] == evidence["independent_verification"] == "NOT_RUN"
    assert evidence["production_certification"] == "NOT_CERTIFIED"


def test_eb04_append_only_wallet_conserves_paid_promotional_reserved_refunded_and_expired() -> None:
    wallet = CreditWalletExactnessService()
    wallet.credit(
        tenant_id="tenant-a",
        amount=amount("100.000000"),
        promotional=False,
        idempotency_key="credit-paid",
        reference="payment-1",
        occurred_at=NOW,
    )
    wallet.credit(
        tenant_id="tenant-a",
        amount=amount("20.000000"),
        promotional=True,
        idempotency_key="credit-promo",
        reference="campaign-1",
        occurred_at=NOW,
    )
    wallet.reserve(
        tenant_id="tenant-a",
        reservation_id="reservation-1",
        amount=amount("30.000000"),
        idempotency_key="reserve-1",
        occurred_at=NOW + timedelta(minutes=1),
    )
    wallet.capture(
        tenant_id="tenant-a",
        reservation_id="reservation-1",
        amount=amount("12.000000"),
        idempotency_key="capture-1",
        occurred_at=NOW + timedelta(minutes=2),
    )
    wallet.release(
        tenant_id="tenant-a",
        reservation_id="reservation-1",
        amount=amount("18.000000"),
        idempotency_key="release-1",
        occurred_at=NOW + timedelta(minutes=3),
    )
    wallet.refund(
        tenant_id="tenant-a",
        amount=amount("5.000000"),
        idempotency_key="refund-1",
        payment_reference="refund-provider-1",
        occurred_at=NOW + timedelta(minutes=4),
    )
    snapshot = wallet.expire_promotional(
        tenant_id="tenant-a",
        amount=amount("3.000000"),
        idempotency_key="expire-1",
        grant_reference="campaign-1",
        occurred_at=NOW + timedelta(minutes=5),
    )

    assert snapshot.paid == Decimal("100.000000")
    assert snapshot.promotional == Decimal("5.000000")
    assert snapshot.reserved == Decimal("0.000000")
    assert snapshot.consumed == Decimal("7.000000")
    assert snapshot.refunded == Decimal("5.000000")
    assert snapshot.expired == Decimal("3.000000")
    postings = wallet.postings(tenant_id="tenant-a")
    assert len(postings) == 9
    assert all(posting.debit != posting.credit and posting.amount.value > 0 for posting in postings)
    outbox = wallet.outbox_facts(tenant_id="tenant-a")
    assert len(outbox) == 7
    assert all(fact.posting_ids and fact.publication_state is ExternalExecutionState.NOT_RUN for fact in outbox)

    replayed = wallet.snapshot(
        tenant_id="tenant-a",
        currency="USD",
        as_of=NOW + timedelta(days=1),
    )
    day_end = wallet.day_end(
        tenant_id="tenant-a",
        currency="USD",
        as_of=NOW + timedelta(days=1),
    )
    assert replayed == day_end.snapshot
    assert day_end.conserved and day_end.debit_total == day_end.credit_total
    assert day_end.source_posting_ids == tuple(posting.posting_id for posting in postings)


def test_eb04_manual_adjustment_requires_independent_approval_and_evidence() -> None:
    wallet = CreditWalletExactnessService()
    wallet.credit(
        tenant_id="tenant-a",
        amount=amount("25.000000"),
        promotional=False,
        idempotency_key="credit",
        reference="payment",
        occurred_at=NOW,
    )
    adjustment = wallet.request_adjustment(
        adjustment_id="adjustment-1",
        tenant_id="tenant-a",
        bucket=WalletBucket.PAID,
        signed_amount=Decimal("-4.000000"),
        currency="USD",
        reason="duplicate provider funding correction",
        evidence_ref="evidence-sha256",
        requested_by="maker",
        requested_at=NOW,
    )
    assert adjustment.approved_by is None
    with pytest.raises(DomainError, match="MAKER_CHECKER_VIOLATION"):
        wallet.approve_adjustment(
            tenant_id="tenant-a",
            adjustment_id="adjustment-1",
            approved_by="maker",
            idempotency_key="approve-self",
            occurred_at=NOW,
        )
    approved = wallet.approve_adjustment(
        tenant_id="tenant-a",
        adjustment_id="adjustment-1",
        approved_by="checker",
        idempotency_key="approve-1",
        occurred_at=NOW,
    )
    assert approved.paid == Decimal("21.000000")
    posting = wallet.postings(tenant_id="tenant-a")[-1]
    assert posting.requested_by == "maker" and posting.approved_by == "checker"
    assert posting.reason and posting.evidence_ref == "evidence-sha256"


def test_eb04_idempotency_tenant_isolation_negative_balance_and_external_unknown_fail_closed() -> None:
    wallet = CreditWalletExactnessService()
    first = wallet.credit(
        tenant_id="tenant-a",
        amount=amount("10.000000"),
        promotional=False,
        idempotency_key="same-key",
        reference="payment-a",
        occurred_at=NOW,
    )
    assert wallet.credit(
        tenant_id="tenant-a",
        amount=amount("10.000000"),
        promotional=False,
        idempotency_key="same-key",
        reference="payment-a",
        occurred_at=NOW,
    ) == first
    with pytest.raises(DomainError, match="IDEMPOTENCY_PAYLOAD_CONFLICT"):
        wallet.credit(
            tenant_id="tenant-a",
            amount=amount("11.000000"),
            promotional=False,
            idempotency_key="same-key",
            reference="payment-a",
            occurred_at=NOW,
        )
    wallet.credit(
        tenant_id="tenant-b",
        amount=amount("7.000000"),
        promotional=False,
        idempotency_key="same-key",
        reference="payment-b",
        occurred_at=NOW,
    )
    with pytest.raises(DomainError, match="INSUFFICIENT_AVAILABLE_BALANCE"):
        wallet.reserve(
            tenant_id="tenant-a",
            reservation_id="too-large",
            amount=amount("10.000001"),
            idempotency_key="overdraw",
            occurred_at=NOW,
        )
    assert wallet.snapshot(tenant_id="tenant-b", currency="USD", as_of=NOW).paid == Decimal("7.000000")

    day_end = wallet.day_end(tenant_id="tenant-a", currency="USD", as_of=NOW)
    reconciliation = wallet.reconcile_external(
        day_end,
        external_paid_balance=None,
        external_reference=None,
        external_state=ExternalExecutionState.NOT_RUN,
    )
    assert reconciliation.matched is None and reconciliation.difference is None
    assert wallet.external_reconciliation is ExternalExecutionState.NOT_RUN
    assert wallet.certification is CertificationState.NOT_CERTIFIED


def test_eb04_bounded_concurrent_reservation_never_corrupts_or_overdraws_projection() -> None:
    wallet = CreditWalletExactnessService()
    wallet.credit(
        tenant_id="tenant-a",
        amount=amount("100.000000"),
        promotional=False,
        idempotency_key="fund",
        reference="payment",
        occurred_at=NOW,
    )

    def reserve(index: int) -> str:
        try:
            wallet.reserve(
                tenant_id="tenant-a",
                reservation_id=f"reservation-{index}",
                amount=amount("80.000000"),
                idempotency_key=f"reserve-{index}",
                occurred_at=NOW + timedelta(seconds=1),
            )
        except DomainError as exc:
            return exc.code
        return "LOCAL_EXECUTED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(reserve, (1, 2)))
    assert sorted(outcomes) == ["INSUFFICIENT_AVAILABLE_BALANCE", "LOCAL_EXECUTED"]
    snapshot = wallet.snapshot(tenant_id="tenant-a", currency="USD", as_of=NOW + timedelta(seconds=1))
    assert snapshot.available == Decimal("20.000000") and snapshot.reserved == Decimal("80.000000")
    assert wallet.day_end(
        tenant_id="tenant-a", currency="USD", as_of=NOW + timedelta(seconds=1)
    ).conserved


def usage_event(
    source_id: str,
    *,
    category: ResourceCategory = ResourceCategory.TOKEN,
    quantity: str = "10.000000",
    treatment: UsageTreatment = UsageTreatment.USER_BILLABLE,
    event_at: datetime = NOW,
    received_at: datetime = NOW,
) -> RawUsageEvent:
    unit = f"raw-{category.value.lower()}"
    return RawUsageEvent(
        f"event-{source_id}",
        source_id,
        "tenant-a",
        "task-a",
        f"run-{source_id}",
        "node-a",
        category,
        Decimal(quantity),
        unit,
        "provider-a",
        treatment,
        event_at,
        received_at,
    )


def configured_usage(*categories: ResourceCategory, queue_capacity: int = 2) -> UsageMeteringExactnessService:
    service = UsageMeteringExactnessService(queue_capacity=queue_capacity, maximum_attempts=2)
    for category in categories:
        raw_unit = f"raw-{category.value.lower()}"
        normalized_unit = f"normalized-{category.value.lower()}"
        service.register_rule(
            NormalizationRule("normalization-v1", category, raw_unit, normalized_unit, Decimal("0.100000"), 6)
        )
        service.register_rate(
            ProviderRate(
                "rate-v1",
                "provider-a",
                category,
                normalized_unit,
                ExactAmount("USD", Decimal("0.500000")),
                NOW - timedelta(days=1),
                NOW + timedelta(days=30),
            )
        )
    return service


def test_eb05_typed_resources_attribution_precision_rate_version_and_treatments() -> None:
    categories = tuple(ResourceCategory)
    service = configured_usage(*categories)
    records = tuple(
        service.ingest(usage_event(f"source-{index}", category=category), idempotency_key=f"key-{index}")
        for index, category in enumerate(categories)
    )
    assert {record.raw.category for record in records} == set(ResourceCategory)
    assert all(
        record.raw.task_id == "task-a"
        and record.raw.run_id
        and record.raw.node_id == "node-a"
        and record.normalization_version == "normalization-v1"
        and record.provider_rate_version == "rate-v1"
        and record.normalized_quantity == Decimal("1.000000")
        and record.conversion_factor == Decimal("0.100000")
        for record in records
    )

    treatment_service = configured_usage(ResourceCategory.TOKEN)
    treatment_records = tuple(
        treatment_service.ingest(
            usage_event(f"treatment-{treatment.value}", treatment=treatment),
            idempotency_key=f"key-{treatment.value}",
        )
        for treatment in UsageTreatment
    )
    assert treatment_records[0].customer_charge.value == Decimal("0.500000")
    assert all(record.customer_charge.value == 0 for record in treatment_records[1:])
    byok = next(record for record in treatment_records if record.raw.treatment is UsageTreatment.BYOK)
    assert byok.internal_cost.value == 0


def test_eb05_dedupe_correction_late_window_and_detail_lineage_are_deterministic() -> None:
    service = configured_usage(ResourceCategory.TOKEN)
    original_event = usage_event("original", quantity="10.000000")
    original = service.ingest(original_event, idempotency_key="original-command")
    assert service.ingest(original_event, idempotency_key="duplicate-command") == original
    with pytest.raises(DomainError, match="USAGE_SOURCE_COLLISION"):
        service.ingest(usage_event("original", quantity="11.000000"), idempotency_key="collision-command")

    corrected = service.correct(
        tenant_id="tenant-a",
        original_source_event_id="original",
        correction=usage_event("correction", quantity="4.000000"),
        idempotency_key="correction-command",
    )
    assert corrected.correction_of == "original"
    aggregate = service.aggregate(
        tenant_id="tenant-a",
        category=ResourceCategory.TOKEN,
        normalized_unit="normalized-token",
        as_of=NOW,
    )
    assert aggregate.quantity == Decimal("0.400000")
    assert aggregate.internal_cost.value == Decimal("0.200000")
    assert aggregate.detail_event_ids == ("event-original", "event-correction")

    service.close_through(tenant_id="tenant-a", closed_through=NOW + timedelta(days=1))
    late = service.ingest(
        usage_event(
            "late",
            event_at=NOW,
            received_at=NOW + timedelta(days=2),
        ),
        idempotency_key="late-command",
    )
    assert late.decision is UsageDecision.LATE_REVIEW
    after_late = service.aggregate(
        tenant_id="tenant-a",
        category=ResourceCategory.TOKEN,
        normalized_unit="normalized-token",
        as_of=NOW + timedelta(days=3),
    )
    assert after_late.quantity == aggregate.quantity
    assert after_late.closed_through == NOW + timedelta(days=1)


def test_eb05_bounded_backpressure_retry_dead_letter_replay_and_reconciliation_fail_closed() -> None:
    service = configured_usage(ResourceCategory.TOKEN, queue_capacity=1)
    first = usage_event("pipeline-1")
    second = usage_event("pipeline-2")
    assert service.enqueue_pipeline(first, idempotency_key="pipeline-key-1").reason == "QUEUED"
    assert service.enqueue_pipeline(second, idempotency_key="pipeline-key-2").state is PipelineState.BACKPRESSURE_RETRY
    assert service.process_next_pipeline(simulate_failure=True).state is PipelineState.RETRY
    assert service.submit_pipeline(
        first,
        idempotency_key="pipeline-key-1",
        simulate_failure=True,
    ).state is PipelineState.DEAD_LETTER
    assert service.replay_dead_letter(
        tenant_id="tenant-a",
        source_event_id="pipeline-1",
    ).state is PipelineState.REPLAYED

    result = service.reconcile_period(
        tenant_id="tenant-a",
        period_start=NOW - timedelta(seconds=1),
        period_end=NOW + timedelta(seconds=1),
        provider_bill=None,
        provider_state=ExternalExecutionState.NOT_RUN,
        evidenced_run_ids=frozenset(),
        run_evidence_state=ExternalExecutionState.NOT_RUN,
    )
    assert result.matched is None and result.provider_difference is None
    assert result.missing_run_ids == ("run-pipeline-1",)
    assert service.provider_bill_evidence is ExternalExecutionState.NOT_RUN
    assert service.run_evidence is ExternalExecutionState.NOT_RUN
    assert service.certification is CertificationState.NOT_CERTIFIED


def subscription(
    subscription_id: str = "subscription-1",
    *,
    cadence: BillingCadence = BillingCadence.MONTHLY,
    state: SubscriptionState = SubscriptionState.TRIAL,
) -> Subscription:
    return Subscription(
        subscription_id,
        "tenant-a",
        "plan-basic",
        cadence,
        state,
        2,
        NOW,
        NOW + timedelta(days=31),
        "UTC",
        1,
    )


def snapshot() -> InvoiceInputSnapshot:
    return InvoiceInputSnapshot("price-v1", "tax-v1", "contract-v1", "usage-v1", NOW)


def invoice_lines() -> tuple[InvoiceLine, ...]:
    values = (
        (InvoiceLineKind.PLAN, LineDirection.CHARGE, "100.000000"),
        (InvoiceLineKind.SEAT, LineDirection.CHARGE, "20.000000"),
        (InvoiceLineKind.USAGE, LineDirection.CHARGE, "10.000000"),
        (InvoiceLineKind.PROJECT, LineDirection.CHARGE, "5.000000"),
        (InvoiceLineKind.DISCOUNT, LineDirection.CREDIT, "15.000000"),
        (InvoiceLineKind.TAX, LineDirection.CHARGE, "10.000000"),
        (InvoiceLineKind.ADJUSTMENT, LineDirection.CREDIT, "2.000000"),
    )
    return tuple(
        InvoiceLine(f"line-{kind.value.lower()}", kind, direction, amount(value), (f"source-{kind.value}",))
        for kind, direction, value in values
    )


def test_eb09_subscription_lifecycle_idempotency_and_calendar_boundaries() -> None:
    service = SubscriptionInvoicingExactnessService()
    created = service.create_subscription(subscription(), idempotency_key="create")
    active = service.transition(
        tenant_id="tenant-a",
        subscription_id=created.subscription_id,
        target=SubscriptionState.ACTIVE,
        seats=None,
        plan_id=None,
        idempotency_key="activate",
        effective_at=NOW,
    )
    upgraded = service.transition(
        tenant_id="tenant-a",
        subscription_id=created.subscription_id,
        target=SubscriptionState.ACTIVE,
        seats=5,
        plan_id="plan-pro",
        idempotency_key="upgrade",
        effective_at=NOW + timedelta(days=1),
    )
    downgraded = service.transition(
        tenant_id="tenant-a",
        subscription_id=created.subscription_id,
        target=SubscriptionState.ACTIVE,
        seats=2,
        plan_id="plan-basic",
        idempotency_key="downgrade",
        effective_at=NOW + timedelta(days=2),
    )
    paused = service.transition(
        tenant_id="tenant-a",
        subscription_id=created.subscription_id,
        target=SubscriptionState.PAUSED,
        seats=None,
        plan_id=None,
        idempotency_key="pause",
        effective_at=NOW + timedelta(days=3),
    )
    cancelled = service.transition(
        tenant_id="tenant-a",
        subscription_id=created.subscription_id,
        target=SubscriptionState.CANCELLED,
        seats=None,
        plan_id=None,
        idempotency_key="cancel",
        effective_at=NOW + timedelta(days=4),
    )
    reactivated = service.transition(
        tenant_id="tenant-a",
        subscription_id=created.subscription_id,
        target=SubscriptionState.ACTIVE,
        seats=None,
        plan_id=None,
        idempotency_key="reactivate",
        effective_at=NOW + timedelta(days=5),
    )
    assert active.state is SubscriptionState.ACTIVE
    assert upgraded.plan_id == "plan-pro" and upgraded.seats == 5
    assert downgraded.plan_id == "plan-basic" and downgraded.seats == 2
    assert paused.state is SubscriptionState.PAUSED
    assert cancelled.state is SubscriptionState.CANCELLED
    assert reactivated.state is SubscriptionState.ACTIVE
    assert service.transition(
        tenant_id="tenant-a",
        subscription_id=created.subscription_id,
        target=SubscriptionState.ACTIVE,
        seats=None,
        plan_id=None,
        idempotency_key="reactivate",
        effective_at=NOW + timedelta(days=5),
    ) == reactivated

    january_31 = datetime(2028, 1, 31, 10, tzinfo=UTC)
    assert service.next_period_boundary(
        january_31,
        cadence=BillingCadence.MONTHLY,
        timezone="UTC",
    ) == datetime(2028, 2, 29, 10, tzinfo=UTC)
    assert service.next_period_boundary(
        january_31,
        cadence=BillingCadence.ANNUAL,
        timezone="UTC",
    ) == datetime(2029, 1, 31, 10, tzinfo=UTC)


def test_eb09_typed_invoice_snapshot_draft_final_and_correction_lineage() -> None:
    service = SubscriptionInvoicingExactnessService()
    service.create_subscription(
        subscription(state=SubscriptionState.ACTIVE),
        idempotency_key="create",
    )
    lines = invoice_lines()
    draft = service.create_draft(
        invoice_id="invoice-1",
        tenant_id="tenant-a",
        subscription_id="subscription-1",
        lines=lines,
        inputs=snapshot(),
        period_start=NOW,
        period_end=NOW + timedelta(days=31),
    )
    assert {line.kind for line in draft.lines} == set(InvoiceLineKind)
    assert draft.total.value == Decimal("128.000000")
    recalculated = service.recalculate_draft(
        tenant_id="tenant-a",
        invoice_id="invoice-1",
        lines=lines,
    )
    assert recalculated.revision == 2
    finalized = service.finalize(
        tenant_id="tenant-a",
        invoice_id="invoice-1",
        finalized_at=NOW + timedelta(days=31),
    )
    assert finalized.state is InvoiceState.FINALIZED and finalized.inputs == snapshot()
    with pytest.raises(DomainError, match="FINAL_INVOICE_IMMUTABLE"):
        service.recalculate_draft(tenant_id="tenant-a", invoice_id="invoice-1", lines=lines)

    credit = service.credit_note(
        tenant_id="tenant-a",
        original_invoice_id="invoice-1",
        credit_note_id="credit-note-1",
        amount=amount("8.000000"),
        occurred_at=NOW + timedelta(days=32),
    )
    assert credit.state is InvoiceState.FINALIZED
    assert credit.correction_of == "invoice-1"
    assert credit.lines[0].direction is LineDirection.CREDIT
    replacement = service.replacement_invoice(
        tenant_id="tenant-a",
        original_invoice_id="invoice-1",
        replacement_invoice_id="invoice-2",
        lines=lines,
        inputs=snapshot(),
        occurred_at=NOW + timedelta(days=33),
    )
    assert service.invoice(tenant_id="tenant-a", invoice_id="invoice-1").state is InvoiceState.REPLACED
    assert replacement.state is InvoiceState.DRAFT and replacement.correction_of == "invoice-1"
    assert len(service.invoice_history(tenant_id=" tenant-a ", invoice_id=" invoice-1 ")) == 4
    with pytest.raises(DomainError, match="INVOICE_INPUT_UNKNOWN"):
        InvoiceInputSnapshot("price-v1", "UNKNOWN", "contract-v1", "usage-v1", NOW)


def test_eb09_renewal_credit_terms_dunning_and_accounting_events_are_distinct() -> None:
    service = SubscriptionInvoicingExactnessService()
    service.create_subscription(
        subscription(state=SubscriptionState.ACTIVE),
        idempotency_key="create",
    )
    service.set_credit_terms(
        EnterpriseCreditTerms("tenant-a", 30, amount("500.000000"), amount("0.000000"))
    )
    service.create_draft(
        invoice_id="invoice-1",
        tenant_id="tenant-a",
        subscription_id="subscription-1",
        lines=(InvoiceLine("plan", InvoiceLineKind.PLAN, LineDirection.CHARGE, amount("100.000000"), ("plan-v1",)),),
        inputs=snapshot(),
        period_start=NOW,
        period_end=NOW + timedelta(days=31),
    )
    invoice = service.finalize(
        tenant_id="tenant-a",
        invoice_id="invoice-1",
        finalized_at=NOW + timedelta(days=31),
    )
    receipt = service.renewal(
        tenant_id="tenant-a",
        subscription_id="subscription-1",
        cycle_id="cycle-1",
        renewal_charge=amount("100.000000"),
        included_credit=Decimal("10.000000"),
        charge_idempotency_key="charge-key",
        credit_idempotency_key="credit-key",
    )
    assert service.renewal(
        tenant_id="tenant-a",
        subscription_id="subscription-1",
        cycle_id="cycle-1",
        renewal_charge=amount("100.000000"),
        included_credit=Decimal("10.000000"),
        charge_idempotency_key="charge-key",
        credit_idempotency_key="credit-key",
    ) == receipt
    assert receipt.charge_idempotency_key != receipt.credit_idempotency_key and receipt.local_only
    with pytest.raises(DomainError, match="RENEWAL_KEYS_COLLIDE"):
        service.renewal(
            tenant_id="tenant-a",
            subscription_id="subscription-1",
            cycle_id="cycle-2",
            renewal_charge=amount("100.000000"),
            included_credit=Decimal("10.000000"),
            charge_idempotency_key="same",
            credit_idempotency_key="same",
        )

    dunning = service.fail_payment(
        tenant_id="tenant-a",
        invoice_id=invoice.invoice_id,
        payment_reference="payment-failure-1",
        failed_at=NOW + timedelta(days=31),
        next_attempt_at=NOW + timedelta(days=32),
    )
    recognized = service.recognize_revenue(
        tenant_id="tenant-a",
        invoice_id=invoice.invoice_id,
        amount=amount("25.000000"),
        occurred_at=NOW + timedelta(days=32),
    )
    events = service.accounting_events(tenant_id="tenant-a", invoice_id=invoice.invoice_id)
    assert dunning.state == "RETRY_SCHEDULED"
    assert recognized.kind is AccountingEventKind.REVENUE_RECOGNIZED
    assert {event.kind for event in events} == set(AccountingEventKind)
    assert service.tax_engine is ExternalExecutionState.NOT_RUN
    assert service.payment_provider is ExternalExecutionState.NOT_RUN
    assert service.accounting_system is ExternalExecutionState.NOT_RUN
    assert service.certification is CertificationState.NOT_CERTIFIED


def dimensions() -> AnalysisDimensions:
    return AnalysisDimensions(
        "task-a",
        "project-a",
        "tenant-a",
        "plan-a",
        "model-a",
        "provider-a",
        NOW,
        NOW + timedelta(days=1),
    )


def fact(
    fact_id: str,
    *,
    source: AnalysisFactSource,
    state: AnalysisFactState,
    kind: AnalysisFactKind,
    value: str,
    driver: CostDriver | None = None,
) -> AnalysisFact:
    return AnalysisFact(
        fact_id,
        "tenant-a",
        source,
        f"source-{fact_id}",
        state,
        kind,
        amount(value),
        dimensions(),
        NOW,
        driver,
    )


def test_eb13_fact_sources_states_dimensions_versioned_allocation_and_estimate_variance() -> None:
    service = CostMarginExactnessService()
    facts = (
        fact(
            "ledger-revenue",
            source=AnalysisFactSource.LEDGER,
            state=AnalysisFactState.POSTED,
            kind=AnalysisFactKind.REVENUE,
            value="100.000000",
        ),
        fact(
            "usage-cost",
            source=AnalysisFactSource.USAGE,
            state=AnalysisFactState.RECOGNIZED,
            kind=AnalysisFactKind.COST,
            value="40.000000",
            driver=CostDriver.CACHE,
        ),
        fact(
            "payment-refund",
            source=AnalysisFactSource.PAYMENT,
            state=AnalysisFactState.POSTED,
            kind=AnalysisFactKind.REFUND,
            value="5.000000",
        ),
        fact(
            "invoice-estimate",
            source=AnalysisFactSource.INVOICE,
            state=AnalysisFactState.ESTIMATED,
            kind=AnalysisFactKind.REVENUE,
            value="15.000000",
        ),
        fact(
            "payment-pending",
            source=AnalysisFactSource.PAYMENT,
            state=AnalysisFactState.PENDING,
            kind=AnalysisFactKind.COST,
            value="10.000000",
        ),
    )
    for source_fact in facts:
        service.append_fact(source_fact)
    assert {source_fact.source for source_fact in facts} == set(AnalysisFactSource)
    assert {source_fact.state for source_fact in facts} == set(AnalysisFactState)
    with pytest.raises(DomainError, match="ANALYSIS_FACT_IMMUTABLE"):
        service.append_fact(
            fact(
                "ledger-revenue",
                source=AnalysisFactSource.LEDGER,
                state=AnalysisFactState.POSTED,
                kind=AnalysisFactKind.REVENUE,
                value="101.000000",
            )
        )

    service.register_allocation_rule(
        AllocationRule(
            "shared-cost",
            1,
            (("team-a", Decimal("0.333333")), ("team-b", Decimal("0.666667"))),
            NOW - timedelta(days=1),
        )
    )
    allocated = service.allocate(
        tenant_id="tenant-a",
        fact_id="usage-cost",
        rule_id="shared-cost",
        version=1,
    )
    assert sum((row.amount.value for row in allocated), Decimal("0.000000")) == Decimal("40.000000")
    assert {row.rule_version for row in allocated} == {1}
    with pytest.raises(DomainError, match="ALLOCATION_NOT_CONSERVING"):
        AllocationRule(
            "invalid",
            1,
            (("a", Decimal("0.600000")), ("b", Decimal("0.500000"))),
            NOW,
        )

    variance = service.estimate_variance(
        estimate_id="estimate-1",
        p50=amount("80.000000"),
        p80=amount("90.000000"),
        p90=amount("100.000000"),
        actual=amount("95.000000"),
    )
    assert variance.variance_to_p50 == Decimal("15.000000")
    assert variance.variance_to_p80 == Decimal("5.000000")
    assert variance.variance_to_p90 == Decimal("-5.000000")


def test_eb13_as_of_close_coverage_cost_drivers_alerts_and_price_approval() -> None:
    service = CostMarginExactnessService()
    service.append_fact(
        fact(
            "revenue",
            source=AnalysisFactSource.INVOICE,
            state=AnalysisFactState.RECOGNIZED,
            kind=AnalysisFactKind.REVENUE,
            value="50.000000",
        )
    )
    for index, driver in enumerate(CostDriver, start=1):
        service.append_fact(
            fact(
                f"driver-{driver.value}",
                source=AnalysisFactSource.USAGE,
                state=AnalysisFactState.POSTED,
                kind=AnalysisFactKind.COST,
                value=f"{10 + index}.000000",
                driver=driver,
            )
        )
    service.append_fact(
        fact(
            "estimated-uncovered",
            source=AnalysisFactSource.USAGE,
            state=AnalysisFactState.ESTIMATED,
            kind=AnalysisFactKind.COST,
            value="9.000000",
        )
    )
    service.close_through(tenant_id="tenant-a", closed_through=NOW)
    report = service.margin(tenant_id="tenant-a", as_of=NOW, dimensions=dimensions())
    impacts = service.driver_impacts(tenant_id="tenant-a", as_of=NOW)
    assert report.as_of == NOW and report.closed_through == NOW
    assert report.coverage_basis_points == 8571
    assert set(impacts) == set(CostDriver)
    assert all(value > 0 for value in impacts.values())
    assert report.gross_margin < 0

    alerts = service.evaluate_alerts(
        report=report,
        previous_margin=Decimal("100.000000"),
        rate_drift=Decimal("0.200000"),
        refund_ratio=Decimal("0.300000"),
        decline_threshold=Decimal("1.000000"),
        drift_threshold=Decimal("0.100000"),
        refund_threshold=Decimal("0.100000"),
    )
    assert {alert.kind for alert in alerts} == set(MarginAlertKind)
    with pytest.raises(DomainError, match="ALERT_THRESHOLD_NEGATIVE"):
        service.evaluate_alerts(
            report=report,
            previous_margin=Decimal("0.000000"),
            rate_drift=Decimal("0.000000"),
            refund_ratio=Decimal("0.000000"),
            decline_threshold=Decimal("-1.000000"),
            drift_threshold=Decimal("0.000000"),
            refund_threshold=Decimal("0.000000"),
        )

    suggestion = service.propose_price(
        suggestion_id="suggestion-1",
        tenant_id="tenant-a",
        proposed_rate=USD_1,
        proposed_by="analyst",
        reason="loss alert",
        evidence_digest="digest-1",
    )
    assert suggestion.state is SuggestionState.PENDING_APPROVAL
    with pytest.raises(DomainError, match="MAKER_CHECKER_VIOLATION"):
        service.approve_price_suggestion(
            tenant_id="tenant-a",
            suggestion_id="suggestion-1",
            approved_by="analyst",
        )
    approved = service.approve_price_suggestion(
        tenant_id="tenant-a",
        suggestion_id="suggestion-1",
        approved_by="pricing-owner",
    )
    assert approved.state is SuggestionState.APPROVED_FOR_PRICE_BOOK_REVIEW
    assert service.authority == "READ_ONLY_LOCAL_ANALYTICS"
    assert service.price_book_write_authority is False
    assert service.external_financial_evidence is ExternalExecutionState.NOT_RUN
    assert service.certification is CertificationState.NOT_CERTIFIED
