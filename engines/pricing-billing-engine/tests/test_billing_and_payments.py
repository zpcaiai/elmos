from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from elmos_pricing_billing.billing import (
    EnterpriseTermsService,
    PaymentReconciliationService,
    RefundDisputeService,
    SubscriptionInvoiceService,
)
from elmos_pricing_billing.errors import DomainError
from elmos_pricing_billing.ledger import LedgerService
from elmos_pricing_billing.models import (
    DisputeState,
    EnterpriseAgreement,
    InvoiceLine,
    PlanSnapshot,
    ProviderPaymentState,
    RefundState,
    SubscriptionState,
)
from elmos_pricing_billing.money import Money

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def snapshot(tenant_id: str = "tenant") -> PlanSnapshot:
    return PlanSnapshot(tenant_id, "plan", 1, "digest", NOW, (), 1)


def test_subscription_invoice_credit_note_and_dunning_facts_are_immutable() -> None:
    service = SubscriptionInvoiceService()
    subscription = service.subscribe(
        subscription_id="sub",
        tenant_id="tenant",
        plan_snapshot=snapshot(),
        started_at=NOW,
    )
    invoice = service.issue_invoice(
        invoice_id="invoice",
        tenant_id="tenant",
        subscription_id=subscription.subscription_id,
        lines=(
            InvoiceLine("line-1", "base", Money("USD", 900)),
            InvoiceLine("line-2", "usage", Money("USD", 100)),
        ),
        issued_at=NOW,
        due_at=NOW + timedelta(days=14),
    )
    assert invoice.total_minor == 1_000
    assert service.invoice(invoice_id="invoice", tenant_id="tenant") is invoice
    assert (
        service.issue_invoice(
            invoice_id="invoice",
            tenant_id="tenant",
            subscription_id=subscription.subscription_id,
            lines=invoice.lines,
            issued_at=NOW,
            due_at=NOW + timedelta(days=14),
        )
        is invoice
    )
    with pytest.raises(FrozenInstanceError):
        invoice.digest = "mutated"  # type: ignore[misc]

    note = service.issue_credit_note(
        credit_note_id="note",
        invoice_id="invoice",
        tenant_id="tenant",
        money=Money("USD", 200),
        reason="correction",
        issued_at=NOW,
    )
    assert note.money.minor == 200
    with pytest.raises(DomainError, match="CREDIT_EXCEEDS_INVOICE"):
        service.issue_credit_note(
            credit_note_id="too-large",
            invoice_id="invoice",
            tenant_id="tenant",
            money=Money("USD", 801),
            reason="bad",
            issued_at=NOW,
        )
    event = service.record_dunning(
        event_id="dunning-1",
        invoice_id="invoice",
        tenant_id="tenant",
        state=SubscriptionState.PAST_DUE,
        occurred_at=NOW + timedelta(days=15),
        reason="overdue",
    )
    assert event.sequence == 1
    assert service.mark_paid(invoice_id="invoice", tenant_id="tenant") == "PAID"
    assert service.mark_paid(invoice_id="invoice", tenant_id="tenant") == "PAID"
    with pytest.raises(DomainError, match="TENANT_ISOLATION_VIOLATION"):
        service.invoice(invoice_id="invoice", tenant_id="other")


def test_verified_webhook_dedup_unknown_state_and_four_way_suspense() -> None:
    service = PaymentReconciliationService()
    with pytest.raises(DomainError, match="WEBHOOK_SIGNATURE_UNVERIFIED"):
        service.observe_webhook(
            provider="demo",
            provider_event_id="event",
            tenant_id="tenant",
            payment_reference="payment",
            state=ProviderPaymentState.SUCCEEDED,
            raw_payload=b"payload",
            signature_verified=False,
            received_at=NOW,
        )
    with pytest.raises(DomainError, match="PROVIDER_STATE_UNKNOWN"):
        service.reconcile(
            reconciliation_id="unknown",
            tenant_id="tenant",
            payment_reference="missing",
            currency="USD",
            ledger_minor=100,
            invoice_minor=100,
            provider_minor=100,
            bank_minor=100,
        )
    first = service.observe_webhook(
        provider="demo",
        provider_event_id="event",
        tenant_id="tenant",
        payment_reference="payment",
        state=ProviderPaymentState.SUCCEEDED,
        raw_payload=b"payload",
        signature_verified=True,
        received_at=NOW,
    )
    repeated = service.observe_webhook(
        provider="demo",
        provider_event_id="event",
        tenant_id="tenant",
        payment_reference="payment",
        state=ProviderPaymentState.SUCCEEDED,
        raw_payload=b"payload",
        signature_verified=True,
        received_at=NOW,
    )
    assert first is repeated
    with pytest.raises(DomainError, match="WEBHOOK_EVENT_CONFLICT"):
        service.observe_webhook(
            provider="demo",
            provider_event_id="event",
            tenant_id="tenant",
            payment_reference="payment",
            state=ProviderPaymentState.FAILED,
            raw_payload=b"different",
            signature_verified=True,
            received_at=NOW,
        )
    with pytest.raises(DomainError, match="PAYMENT_STATE_REGRESSION"):
        service.observe_webhook(
            provider="demo",
            provider_event_id="event-regression",
            tenant_id="tenant",
            payment_reference="payment",
            state=ProviderPaymentState.PENDING,
            raw_payload=b"pending-after-success",
            signature_verified=True,
            received_at=NOW + timedelta(seconds=1),
        )
    match = service.reconcile(
        reconciliation_id="match",
        tenant_id="tenant",
        payment_reference="payment",
        currency="USD",
        ledger_minor=100,
        invoice_minor=100,
        provider_minor=100,
        bank_minor=100,
    )
    mismatch = service.reconcile(
        reconciliation_id="mismatch",
        tenant_id="tenant",
        payment_reference="payment",
        currency="USD",
        ledger_minor=100,
        invoice_minor=100,
        provider_minor=99,
        bank_minor=100,
    )
    assert match.matched and match.suspense_id is None
    assert (
        service.reconcile(
            reconciliation_id="match",
            tenant_id="tenant",
            payment_reference="payment",
            currency="USD",
            ledger_minor=100,
            invoice_minor=100,
            provider_minor=100,
            bank_minor=100,
        )
        is match
    )
    assert not mismatch.matched and mismatch.suspense_id == "suspense:mismatch"
    assert service.suspense_cases(tenant_id="tenant") == (mismatch,)


def test_refund_limits_maker_checker_reversal_and_dispute() -> None:
    ledger = LedgerService()
    service = RefundDisputeService(ledger)
    service.register_refundable(tenant_id="tenant", payment_reference="payment", money=Money("USD", 1_000))
    service.request_refund(
        refund_id="refund",
        tenant_id="tenant",
        payment_reference="payment",
        money=Money("USD", 600),
        requested_by="maker",
        reason="customer request",
    )
    with pytest.raises(DomainError, match="MAKER_CHECKER_VIOLATION"):
        service.approve(refund_id="refund", tenant_id="tenant", approved_by="maker")
    approved = service.approve(refund_id="refund", tenant_id="tenant", approved_by="checker")
    assert approved.state is RefundState.APPROVED
    with pytest.raises(DomainError, match="REFUND_LIMIT_EXCEEDED"):
        service.request_refund(
            refund_id="too-much",
            tenant_id="tenant",
            payment_reference="payment",
            money=Money("USD", 401),
            requested_by="other",
            reason="bad",
        )
    executed = service.execute_local_credit(refund_id="refund", tenant_id="tenant", occurred_at=NOW)
    assert executed.state is RefundState.EXECUTED_LOCAL
    assert ledger.balance(tenant_id="tenant", currency="USD").available_minor == 600
    reversed_refund = service.reverse_local_credit(
        refund_id="refund",
        tenant_id="tenant",
        occurred_at=NOW + timedelta(seconds=1),
    )
    assert reversed_refund.state is RefundState.REVERSED
    assert ledger.balance(tenant_id="tenant", currency="USD").available_minor == 0

    dispute = service.open_dispute(
        dispute_id="dispute",
        tenant_id="tenant",
        payment_reference="payment",
        money=Money("USD", 100),
        opened_by="maker",
        reason="evidence",
    )
    with pytest.raises(DomainError, match="MAKER_CHECKER_VIOLATION"):
        service.decide_dispute(
            dispute_id="dispute",
            tenant_id="tenant",
            decided_by="maker",
            state=DisputeState.WON,
        )
    decided = service.decide_dispute(
        dispute_id=dispute.dispute_id,
        tenant_id="tenant",
        decided_by="checker",
        state=DisputeState.WON,
    )
    assert decided.state is DisputeState.WON


def test_enterprise_commit_credit_byok_secret_reference_and_sla_cap() -> None:
    service = EnterpriseTermsService()
    with pytest.raises(DomainError, match="BYOK_SECRET_REFERENCE_REQUIRED"):
        service.create(EnterpriseAgreement("bad", "tenant", "USD", 1_000, 0, "plaintext-key", 100))
    agreement = service.create(
        EnterpriseAgreement("agreement", "tenant", "USD", 10_000, 5_000, "secret://tenant/key", 700)
    )
    assert (
        service.authorize_spend(
            agreement_id=agreement.agreement_id,
            tenant_id="tenant",
            amount_minor=14_000,
            idempotency_key="spend-1",
        )
        == 1_000
    )
    assert (
        service.authorize_spend(
            agreement_id=agreement.agreement_id,
            tenant_id="tenant",
            amount_minor=14_000,
            idempotency_key="spend-1",
        )
        == 1_000
    )
    with pytest.raises(DomainError, match="ENTERPRISE_CREDIT_LIMIT_EXCEEDED"):
        service.authorize_spend(
            agreement_id=agreement.agreement_id,
            tenant_id="tenant",
            amount_minor=1_001,
            idempotency_key="spend-2",
        )
    first = service.calculate_sla_credit(
        agreement_id=agreement.agreement_id,
        tenant_id="tenant",
        eligible_charge_minor=10_000,
        credit_basis_points=500,
        idempotency_key="sla-1",
    )
    repeated = service.calculate_sla_credit(
        agreement_id=agreement.agreement_id,
        tenant_id="tenant",
        eligible_charge_minor=10_000,
        credit_basis_points=500,
        idempotency_key="sla-1",
    )
    second = service.calculate_sla_credit(
        agreement_id=agreement.agreement_id,
        tenant_id="tenant",
        eligible_charge_minor=10_000,
        credit_basis_points=500,
        idempotency_key="sla-2",
    )
    assert repeated is first
    assert (first.minor, second.minor) == (500, 200)
