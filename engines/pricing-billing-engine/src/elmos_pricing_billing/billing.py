from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from threading import RLock

from .errors import DomainError, require
from .ledger import LedgerService
from .models import (
    CreditNote,
    DisputeCase,
    DisputeState,
    DunningEvent,
    EnterpriseAgreement,
    Invoice,
    InvoiceLine,
    InvoiceState,
    PlanSnapshot,
    ProviderPaymentState,
    ReconciliationResult,
    RefundRequest,
    RefundState,
    Subscription,
    SubscriptionState,
    VerifiedWebhook,
    canonical_digest,
    require_aware,
)
from .money import (
    Money,
    checked_add,
    checked_mul,
    normalize_currency,
    require_non_negative,
    require_positive,
    round_half_up_div,
)


class SubscriptionInvoiceService:
    """Subscription projections around immutable invoice, credit-note, and dunning facts."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._subscriptions: dict[str, Subscription] = {}
        self._invoices: dict[str, Invoice] = {}
        self._invoice_states: dict[str, InvoiceState] = {}
        self._invoice_fingerprints: dict[str, str] = {}
        self._credit_notes: dict[str, CreditNote] = {}
        self._credit_note_fingerprints: dict[str, str] = {}
        self._dunning: dict[str, list[DunningEvent]] = {}
        self._dunning_by_id: dict[str, tuple[str, DunningEvent]] = {}

    def subscribe(
        self,
        *,
        subscription_id: str,
        tenant_id: str,
        plan_snapshot: PlanSnapshot,
        started_at: datetime,
    ) -> Subscription:
        require(bool(subscription_id.strip()), "SUBSCRIPTION_ID_REQUIRED", "subscription_id is required")
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        normalized_at = require_aware(started_at, field_name="started_at")
        require(
            plan_snapshot.tenant_id == tenant_id,
            "TENANT_ISOLATION_VIOLATION",
            "plan snapshot belongs to another tenant",
        )
        with self._lock:
            require(subscription_id not in self._subscriptions, "SUBSCRIPTION_EXISTS", "subscription already exists")
            subscription = Subscription(
                subscription_id=subscription_id,
                tenant_id=tenant_id,
                plan_snapshot=plan_snapshot,
                state=SubscriptionState.ACTIVE,
                started_at=normalized_at,
            )
            self._subscriptions[subscription_id] = subscription
            return subscription

    def issue_invoice(
        self,
        *,
        invoice_id: str,
        tenant_id: str,
        subscription_id: str,
        lines: tuple[InvoiceLine, ...],
        issued_at: datetime,
        due_at: datetime,
    ) -> Invoice:
        normalized_issued = require_aware(issued_at, field_name="issued_at")
        normalized_due = require_aware(due_at, field_name="due_at")
        require(bool(invoice_id.strip()), "INVOICE_ID_REQUIRED", "invoice_id is required")
        require(normalized_due >= normalized_issued, "INVALID_INVOICE_DUE_DATE", "invoice due date precedes issue date")
        require(bool(lines), "INVOICE_LINES_REQUIRED", "invoice requires at least one line")
        require(
            len({line.line_id for line in lines}) == len(lines),
            "DUPLICATE_INVOICE_LINE",
            "invoice line ids must be unique",
        )
        currencies = {line.money.currency for line in lines}
        require(len(currencies) == 1, "MIXED_INVOICE_CURRENCY", "invoice lines must use one currency")
        content = {
            "invoice_id": invoice_id,
            "tenant_id": tenant_id,
            "subscription_id": subscription_id,
            "issued_at": normalized_issued.isoformat(),
            "due_at": normalized_due.isoformat(),
            "lines": [(line.line_id, line.description, line.money.currency, line.money.minor) for line in lines],
        }
        fingerprint = canonical_digest(content)
        with self._lock:
            existing = self._invoices.get(invoice_id)
            if existing is not None:
                require(
                    existing.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "invoice belongs to another tenant"
                )
                require(
                    self._invoice_fingerprints[invoice_id] == fingerprint,
                    "INVOICE_IDEMPOTENCY_CONFLICT",
                    "invoice id was reused with different input",
                )
                return existing
            subscription = self._required_subscription(subscription_id)
            require(
                subscription.tenant_id == tenant_id,
                "TENANT_ISOLATION_VIOLATION",
                "subscription belongs to another tenant",
            )
            invoice = Invoice(
                invoice_id=invoice_id,
                tenant_id=tenant_id,
                subscription_id=subscription_id,
                currency=next(iter(currencies)),
                lines=lines,
                issued_at=normalized_issued,
                due_at=normalized_due,
                digest=fingerprint,
            )
            self._invoices[invoice_id] = invoice
            self._invoice_fingerprints[invoice_id] = fingerprint
            self._invoice_states[invoice_id] = InvoiceState.OPEN
            return invoice

    def mark_paid(self, *, invoice_id: str, tenant_id: str) -> InvoiceState:
        with self._lock:
            invoice = self._required_invoice(invoice_id)
            require(invoice.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "invoice belongs to another tenant")
            if self._invoice_states[invoice_id] is InvoiceState.PAID:
                return InvoiceState.PAID
            require(
                self._invoice_states[invoice_id] is InvoiceState.OPEN,
                "INVOICE_NOT_OPEN",
                "only an open invoice may be paid",
            )
            self._invoice_states[invoice_id] = InvoiceState.PAID
            subscription = self._required_subscription(invoice.subscription_id)
            self._subscriptions[subscription.subscription_id] = replace(subscription, state=SubscriptionState.ACTIVE)
            return InvoiceState.PAID

    def issue_credit_note(
        self,
        *,
        credit_note_id: str,
        invoice_id: str,
        tenant_id: str,
        money: Money,
        reason: str,
        issued_at: datetime,
    ) -> CreditNote:
        require_positive(money.minor, field="credit_note_minor")
        require(bool(reason.strip()), "CREDIT_NOTE_REASON_REQUIRED", "credit note reason is required")
        normalized_at = require_aware(issued_at, field_name="issued_at")
        fingerprint = canonical_digest(
            {
                "credit_note_id": credit_note_id,
                "invoice_id": invoice_id,
                "tenant_id": tenant_id,
                "currency": money.currency,
                "minor": money.minor,
                "reason": reason,
                "issued_at": normalized_at.isoformat(),
            }
        )
        with self._lock:
            invoice = self._required_invoice(invoice_id)
            require(invoice.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "invoice belongs to another tenant")
            require(
                invoice.currency == money.currency, "CURRENCY_MISMATCH", "credit note currency differs from invoice"
            )
            existing = self._credit_notes.get(credit_note_id)
            if existing is not None:
                require(
                    self._credit_note_fingerprints[credit_note_id] == fingerprint,
                    "CREDIT_NOTE_IDEMPOTENCY_CONFLICT",
                    "credit note id was reused with different input",
                )
                return existing
            credited = checked_add(
                *(note.money.minor for note in self._credit_notes.values() if note.invoice_id == invoice_id),
                field="credited_minor",
            )
            projected_credit = checked_add(credited, money.minor, field="credited_minor")
            require(
                projected_credit <= invoice.total_minor, "CREDIT_EXCEEDS_INVOICE", "credit notes exceed invoice total"
            )
            note = CreditNote(
                credit_note_id=credit_note_id,
                invoice_id=invoice_id,
                money=money,
                reason=reason,
                issued_at=normalized_at,
            )
            self._credit_notes[credit_note_id] = note
            self._credit_note_fingerprints[credit_note_id] = fingerprint
            return note

    def record_dunning(
        self,
        *,
        event_id: str,
        invoice_id: str,
        tenant_id: str,
        state: SubscriptionState,
        occurred_at: datetime,
        reason: str,
    ) -> DunningEvent:
        require(bool(event_id.strip()), "DUNNING_EVENT_ID_REQUIRED", "event_id is required")
        require(bool(reason.strip()), "DUNNING_REASON_REQUIRED", "dunning reason is required")
        require(
            state in {SubscriptionState.PAST_DUE, SubscriptionState.SUSPENDED},
            "INVALID_DUNNING_STATE",
            "dunning state must be PAST_DUE or SUSPENDED",
        )
        normalized_at = require_aware(occurred_at, field_name="occurred_at")
        fingerprint = canonical_digest(
            {
                "event_id": event_id,
                "invoice_id": invoice_id,
                "tenant_id": tenant_id,
                "state": state,
                "occurred_at": normalized_at.isoformat(),
                "reason": reason,
            }
        )
        with self._lock:
            invoice = self._required_invoice(invoice_id)
            require(invoice.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "invoice belongs to another tenant")
            existing = self._dunning_by_id.get(event_id)
            if existing is not None:
                require(existing[0] == fingerprint, "DUNNING_EVENT_CONFLICT", "dunning event has different input")
                return existing[1]
            require(
                self._invoice_states[invoice_id] is InvoiceState.OPEN, "INVOICE_NOT_OPEN", "paid invoice cannot dunn"
            )
            require(normalized_at >= invoice.due_at, "DUNNING_BEFORE_DUE", "dunning cannot precede invoice due time")
            events = self._dunning.setdefault(invoice_id, [])
            if events:
                require(
                    normalized_at >= events[-1].occurred_at,
                    "DUNNING_TIME_REGRESSION",
                    "dunning events must be time ordered",
                )
            event = DunningEvent(
                event_id=event_id,
                invoice_id=invoice_id,
                sequence=len(events) + 1,
                state=state,
                occurred_at=normalized_at,
                reason=reason,
            )
            events.append(event)
            self._dunning_by_id[event_id] = (fingerprint, event)
            subscription = self._required_subscription(invoice.subscription_id)
            self._subscriptions[subscription.subscription_id] = replace(subscription, state=state)
            return event

    def invoice_state(self, *, invoice_id: str, tenant_id: str) -> InvoiceState:
        with self._lock:
            invoice = self._required_invoice(invoice_id)
            require(invoice.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "invoice belongs to another tenant")
            return self._invoice_states[invoice_id]

    def invoice(self, *, invoice_id: str, tenant_id: str) -> Invoice:
        with self._lock:
            invoice = self._required_invoice(invoice_id)
            require(invoice.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "invoice belongs to another tenant")
            return invoice

    def _required_subscription(self, subscription_id: str) -> Subscription:
        try:
            return self._subscriptions[subscription_id]
        except KeyError as exc:
            raise DomainError("SUBSCRIPTION_NOT_FOUND", "subscription was not found") from exc

    def _required_invoice(self, invoice_id: str) -> Invoice:
        try:
            return self._invoices[invoice_id]
        except KeyError as exc:
            raise DomainError("INVOICE_NOT_FOUND", "invoice was not found") from exc


class PaymentReconciliationService:
    """Verified provider-neutral observations and exact four-way reconciliation."""

    _ALLOWED_TRANSITIONS: dict[ProviderPaymentState, frozenset[ProviderPaymentState]] = {
        ProviderPaymentState.PENDING: frozenset(
            {ProviderPaymentState.PENDING, ProviderPaymentState.SUCCEEDED, ProviderPaymentState.FAILED}
        ),
        ProviderPaymentState.SUCCEEDED: frozenset({ProviderPaymentState.SUCCEEDED, ProviderPaymentState.REFUNDED}),
        ProviderPaymentState.FAILED: frozenset({ProviderPaymentState.FAILED}),
        ProviderPaymentState.REFUNDED: frozenset({ProviderPaymentState.REFUNDED}),
    }

    def __init__(self) -> None:
        self._lock = RLock()
        self._webhooks: dict[tuple[str, str], tuple[str, VerifiedWebhook]] = {}
        self._states: dict[tuple[str, str], ProviderPaymentState] = {}
        self._reconciliations: dict[str, ReconciliationResult] = {}
        self._reconciliation_fingerprints: dict[str, str] = {}
        self._suspense: dict[str, ReconciliationResult] = {}

    def observe_webhook(
        self,
        *,
        provider: str,
        provider_event_id: str,
        tenant_id: str,
        payment_reference: str,
        state: ProviderPaymentState,
        raw_payload: bytes,
        signature_verified: bool,
        received_at: datetime,
    ) -> VerifiedWebhook:
        require(signature_verified, "WEBHOOK_SIGNATURE_UNVERIFIED", "unverified webhook is rejected")
        require(bool(raw_payload), "WEBHOOK_PAYLOAD_REQUIRED", "webhook payload is required")
        require(bool(provider.strip()), "PROVIDER_REQUIRED", "provider is required")
        require(bool(provider_event_id.strip()), "PROVIDER_EVENT_ID_REQUIRED", "provider event id is required")
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        require(bool(payment_reference.strip()), "PAYMENT_REFERENCE_REQUIRED", "payment reference is required")
        require(state is not ProviderPaymentState.UNKNOWN, "PROVIDER_STATE_UNKNOWN", "unknown is not an observation")
        normalized_at = require_aware(received_at, field_name="received_at")
        payload_digest = sha256(raw_payload).hexdigest()
        fingerprint = canonical_digest(
            {
                "provider": provider,
                "event": provider_event_id,
                "tenant": tenant_id,
                "reference": payment_reference,
                "state": state,
                "payload_digest": payload_digest,
            }
        )
        key = (provider, provider_event_id)
        with self._lock:
            existing = self._webhooks.get(key)
            if existing is not None:
                require(
                    existing[0] == fingerprint,
                    "WEBHOOK_EVENT_CONFLICT",
                    "provider event id was reused with different data",
                )
                return existing[1]
            observation = VerifiedWebhook(
                provider=provider,
                provider_event_id=provider_event_id,
                tenant_id=tenant_id,
                payment_reference=payment_reference,
                state=state,
                payload_digest=payload_digest,
                received_at=normalized_at,
            )
            state_key = (tenant_id, payment_reference)
            current_state = self._states.get(state_key)
            if current_state is not None:
                require(
                    state in self._ALLOWED_TRANSITIONS[current_state],
                    "PAYMENT_STATE_REGRESSION",
                    "provider observation would regress a final payment state",
                )
            self._webhooks[key] = (fingerprint, observation)
            self._states[state_key] = state
            return observation

    def resolved_state(self, *, tenant_id: str, payment_reference: str) -> ProviderPaymentState:
        with self._lock:
            state = self._states.get((tenant_id, payment_reference), ProviderPaymentState.UNKNOWN)
            require(state is not ProviderPaymentState.UNKNOWN, "PROVIDER_STATE_UNKNOWN", "provider state is unknown")
            return state

    def reconcile(
        self,
        *,
        reconciliation_id: str,
        tenant_id: str,
        payment_reference: str,
        currency: str,
        ledger_minor: int,
        invoice_minor: int,
        provider_minor: int,
        bank_minor: int,
    ) -> ReconciliationResult:
        values = (ledger_minor, invoice_minor, provider_minor, bank_minor)
        for value in values:
            require_non_negative(value, field="reconciliation_minor")
        state = self.resolved_state(tenant_id=tenant_id, payment_reference=payment_reference)
        require(
            state in {ProviderPaymentState.SUCCEEDED, ProviderPaymentState.REFUNDED},
            "PROVIDER_STATE_NOT_FINAL",
            "reconciliation requires a final provider state",
        )
        fingerprint = canonical_digest(
            {
                "reconciliation_id": reconciliation_id,
                "tenant_id": tenant_id,
                "payment_reference": payment_reference,
                "currency": normalize_currency(currency),
                "values": values,
            }
        )
        with self._lock:
            existing = self._reconciliations.get(reconciliation_id)
            if existing is not None:
                require(
                    self._reconciliation_fingerprints[reconciliation_id] == fingerprint,
                    "RECONCILIATION_IDEMPOTENCY_CONFLICT",
                    "reconciliation id was reused with different input",
                )
                return existing
            matched = len(set(values)) == 1
            suspense_id = None if matched else f"suspense:{reconciliation_id}"
            result = ReconciliationResult(
                reconciliation_id=reconciliation_id,
                tenant_id=tenant_id,
                reference=payment_reference,
                currency=normalize_currency(currency),
                ledger_minor=ledger_minor,
                invoice_minor=invoice_minor,
                provider_minor=provider_minor,
                bank_minor=bank_minor,
                matched=matched,
                suspense_id=suspense_id,
            )
            self._reconciliations[reconciliation_id] = result
            self._reconciliation_fingerprints[reconciliation_id] = fingerprint
            if suspense_id is not None:
                self._suspense[suspense_id] = result
            return result

    def suspense_cases(self, *, tenant_id: str) -> tuple[ReconciliationResult, ...]:
        with self._lock:
            return tuple(result for result in self._suspense.values() if result.tenant_id == tenant_id)


class RefundDisputeService:
    """Bounded local refund ledger behavior with maker/checker and reversible facts."""

    def __init__(self, ledger: LedgerService) -> None:
        self._ledger = ledger
        self._lock = RLock()
        self._payments: dict[tuple[str, str], Money] = {}
        self._refunds: dict[str, RefundRequest] = {}
        self._disputes: dict[str, DisputeCase] = {}

    def register_refundable(self, *, tenant_id: str, payment_reference: str, money: Money) -> None:
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        require(bool(payment_reference.strip()), "PAYMENT_REFERENCE_REQUIRED", "payment reference is required")
        require_positive(money.minor, field="refundable_minor")
        with self._lock:
            key = (tenant_id, payment_reference)
            require(key not in self._payments, "PAYMENT_ALREADY_REGISTERED", "refundable payment already registered")
            self._payments[key] = money

    def request_refund(
        self,
        *,
        refund_id: str,
        tenant_id: str,
        payment_reference: str,
        money: Money,
        requested_by: str,
        reason: str,
    ) -> RefundRequest:
        require_positive(money.minor, field="refund_minor")
        require(bool(requested_by.strip()), "REQUESTED_BY_REQUIRED", "requested_by is required")
        require(bool(reason.strip()), "REFUND_REASON_REQUIRED", "refund reason is required")
        with self._lock:
            require(refund_id not in self._refunds, "REFUND_EXISTS", "refund id already exists")
            try:
                paid = self._payments[(tenant_id, payment_reference)]
            except KeyError as exc:
                raise DomainError("REFUNDABLE_PAYMENT_NOT_FOUND", "refundable payment was not registered") from exc
            require(paid.currency == money.currency, "CURRENCY_MISMATCH", "refund currency differs from payment")
            allocated = sum(
                item.money.minor
                for item in self._refunds.values()
                if item.tenant_id == tenant_id
                and item.payment_reference == payment_reference
                and item.state is not RefundState.REJECTED
                and item.state is not RefundState.REVERSED
            )
            require(allocated + money.minor <= paid.minor, "REFUND_LIMIT_EXCEEDED", "refunds exceed captured payment")
            refund = RefundRequest(
                refund_id=refund_id,
                tenant_id=tenant_id,
                payment_reference=payment_reference,
                money=money,
                requested_by=requested_by,
                reason=reason,
                state=RefundState.REQUESTED,
            )
            self._refunds[refund_id] = refund
            return refund

    def approve(self, *, refund_id: str, tenant_id: str, approved_by: str) -> RefundRequest:
        require(bool(approved_by.strip()), "APPROVED_BY_REQUIRED", "approved_by is required")
        with self._lock:
            refund = self._required_refund(refund_id, tenant_id)
            require(refund.state is RefundState.REQUESTED, "REFUND_NOT_REQUESTED", "refund is not awaiting approval")
            require(
                refund.requested_by != approved_by, "MAKER_CHECKER_VIOLATION", "requester cannot approve own refund"
            )
            approved = replace(refund, state=RefundState.APPROVED, approved_by=approved_by)
            self._refunds[refund_id] = approved
            return approved

    def execute_local_credit(self, *, refund_id: str, tenant_id: str, occurred_at: datetime) -> RefundRequest:
        with self._lock:
            refund = self._required_refund(refund_id, tenant_id)
            if refund.state is RefundState.EXECUTED_LOCAL:
                return refund
            require(refund.state is RefundState.APPROVED, "REFUND_NOT_APPROVED", "refund requires approval")
            transaction = self._ledger.refund(
                tenant_id=tenant_id,
                money=refund.money,
                idempotency_key=f"refund:{refund_id}",
                reference=refund.payment_reference,
                occurred_at=occurred_at,
            )
            executed = replace(
                refund,
                state=RefundState.EXECUTED_LOCAL,
                ledger_transaction_id=transaction.transaction_id,
            )
            self._refunds[refund_id] = executed
            return executed

    def reverse_local_credit(self, *, refund_id: str, tenant_id: str, occurred_at: datetime) -> RefundRequest:
        with self._lock:
            refund = self._required_refund(refund_id, tenant_id)
            if refund.state is RefundState.REVERSED:
                return refund
            require(
                refund.state is RefundState.EXECUTED_LOCAL,
                "REFUND_NOT_EXECUTED",
                "only executed local refund can reverse",
            )
            transaction_id = refund.ledger_transaction_id
            if transaction_id is None:
                raise DomainError("REFUND_LEDGER_LINK_MISSING", "refund ledger link is missing")
            self._ledger.reverse(
                tenant_id=tenant_id,
                transaction_id=transaction_id,
                idempotency_key=f"refund-reversal:{refund_id}",
                reference=refund.payment_reference,
                occurred_at=occurred_at,
            )
            reversed_refund = replace(refund, state=RefundState.REVERSED)
            self._refunds[refund_id] = reversed_refund
            return reversed_refund

    def open_dispute(
        self,
        *,
        dispute_id: str,
        tenant_id: str,
        payment_reference: str,
        money: Money,
        opened_by: str,
        reason: str,
    ) -> DisputeCase:
        require_positive(money.minor, field="dispute_minor")
        require(bool(opened_by.strip()), "OPENED_BY_REQUIRED", "opened_by is required")
        require(bool(reason.strip()), "DISPUTE_REASON_REQUIRED", "dispute reason is required")
        with self._lock:
            require(dispute_id not in self._disputes, "DISPUTE_EXISTS", "dispute id already exists")
            paid = self._payments.get((tenant_id, payment_reference))
            if paid is None:
                raise DomainError("PAYMENT_NOT_FOUND", "payment was not registered")
            require(paid.currency == money.currency, "CURRENCY_MISMATCH", "dispute currency differs from payment")
            require(money.minor <= paid.minor, "DISPUTE_LIMIT_EXCEEDED", "dispute exceeds captured payment")
            dispute = DisputeCase(
                dispute_id=dispute_id,
                tenant_id=tenant_id,
                payment_reference=payment_reference,
                money=money,
                opened_by=opened_by,
                reason=reason,
                state=DisputeState.OPEN,
            )
            self._disputes[dispute_id] = dispute
            return dispute

    def decide_dispute(
        self,
        *,
        dispute_id: str,
        tenant_id: str,
        decided_by: str,
        state: DisputeState,
    ) -> DisputeCase:
        require(bool(decided_by.strip()), "DECIDED_BY_REQUIRED", "decided_by is required")
        require(
            state in {DisputeState.WON, DisputeState.LOST, DisputeState.WITHDRAWN},
            "INVALID_DISPUTE_DECISION",
            "invalid final dispute state",
        )
        with self._lock:
            try:
                dispute = self._disputes[dispute_id]
            except KeyError as exc:
                raise DomainError("DISPUTE_NOT_FOUND", "dispute was not found") from exc
            require(dispute.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "dispute belongs to another tenant")
            require(dispute.state is DisputeState.OPEN, "DISPUTE_NOT_OPEN", "dispute is not open")
            require(dispute.opened_by != decided_by, "MAKER_CHECKER_VIOLATION", "opener cannot decide own dispute")
            decided = replace(dispute, state=state, decided_by=decided_by)
            self._disputes[dispute_id] = decided
            return decided

    def _required_refund(self, refund_id: str, tenant_id: str) -> RefundRequest:
        try:
            refund = self._refunds[refund_id]
        except KeyError as exc:
            raise DomainError("REFUND_NOT_FOUND", "refund was not found") from exc
        require(refund.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "refund belongs to another tenant")
        return refund


class EnterpriseTermsService:
    """Enterprise commit/credit/BYOK/SLA calculations without secret material or side effects."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._agreements: dict[str, EnterpriseAgreement] = {}
        self._consumed: dict[str, int] = {}
        self._sla_credits: dict[str, int] = {}
        self._spend_idempotency: dict[tuple[str, str], tuple[str, int]] = {}
        self._sla_idempotency: dict[tuple[str, str], tuple[str, Money]] = {}

    def create(self, agreement: EnterpriseAgreement) -> EnterpriseAgreement:
        require_non_negative(agreement.committed_minor, field="committed_minor")
        require_non_negative(agreement.credit_limit_minor, field="credit_limit_minor")
        require_non_negative(agreement.sla_credit_cap_minor, field="sla_credit_cap_minor")
        if agreement.byok_secret_ref is not None:
            require(
                agreement.byok_secret_ref.startswith("secret://") and len(agreement.byok_secret_ref) > len("secret://"),
                "BYOK_SECRET_REFERENCE_REQUIRED",
                "BYOK must use an opaque secret:// reference",
            )
            require(
                "=" not in agreement.byok_secret_ref and " " not in agreement.byok_secret_ref,
                "INLINE_SECRET_FORBIDDEN",
                "secret values must not be embedded",
            )
        with self._lock:
            require(agreement.agreement_id not in self._agreements, "AGREEMENT_EXISTS", "agreement already exists")
            self._agreements[agreement.agreement_id] = agreement
            self._consumed[agreement.agreement_id] = 0
            self._sla_credits[agreement.agreement_id] = 0
            return agreement

    def authorize_spend(
        self,
        *,
        agreement_id: str,
        tenant_id: str,
        amount_minor: int,
        idempotency_key: str,
    ) -> int:
        require_positive(amount_minor, field="amount_minor")
        require(bool(idempotency_key.strip()), "IDEMPOTENCY_KEY_REQUIRED", "idempotency key is required")
        fingerprint = canonical_digest(
            {"agreement_id": agreement_id, "tenant_id": tenant_id, "amount_minor": amount_minor}
        )
        with self._lock:
            key = (tenant_id, idempotency_key)
            existing = self._spend_idempotency.get(key)
            if existing is not None:
                require(existing[0] == fingerprint, "IDEMPOTENCY_CONFLICT", "idempotency key has different input")
                return existing[1]
            agreement = self._required(agreement_id, tenant_id)
            projected = checked_add(self._consumed[agreement_id], amount_minor, field="enterprise_consumed_minor")
            limit = checked_add(
                agreement.committed_minor,
                agreement.credit_limit_minor,
                field="enterprise_credit_limit_minor",
            )
            require(
                projected <= limit, "ENTERPRISE_CREDIT_LIMIT_EXCEEDED", "enterprise commit and credit limit exceeded"
            )
            self._consumed[agreement_id] = projected
            remaining = limit - projected
            self._spend_idempotency[key] = (fingerprint, remaining)
            return remaining

    def calculate_sla_credit(
        self,
        *,
        agreement_id: str,
        tenant_id: str,
        eligible_charge_minor: int,
        credit_basis_points: int,
        idempotency_key: str,
    ) -> Money:
        require_non_negative(eligible_charge_minor, field="eligible_charge_minor")
        require(
            0 <= credit_basis_points <= 10_000, "INVALID_CREDIT_BASIS_POINTS", "credit basis points must be in 0..10000"
        )
        require(bool(idempotency_key.strip()), "IDEMPOTENCY_KEY_REQUIRED", "idempotency key is required")
        fingerprint = canonical_digest(
            {
                "agreement_id": agreement_id,
                "tenant_id": tenant_id,
                "eligible_charge_minor": eligible_charge_minor,
                "credit_basis_points": credit_basis_points,
            }
        )
        with self._lock:
            key = (tenant_id, idempotency_key)
            existing = self._sla_idempotency.get(key)
            if existing is not None:
                require(existing[0] == fingerprint, "IDEMPOTENCY_CONFLICT", "idempotency key has different input")
                return existing[1]
            agreement = self._required(agreement_id, tenant_id)
            numerator = checked_mul(
                eligible_charge_minor,
                credit_basis_points,
                field="sla_credit_numerator",
            )
            calculated = round_half_up_div(numerator, 10_000)
            remaining_cap = agreement.sla_credit_cap_minor - self._sla_credits[agreement_id]
            amount = max(0, min(calculated, remaining_cap))
            self._sla_credits[agreement_id] = checked_add(
                self._sla_credits[agreement_id],
                amount,
                field="sla_credited_minor",
            )
            result = Money(agreement.currency, amount)
            self._sla_idempotency[key] = (fingerprint, result)
            return result

    def _required(self, agreement_id: str, tenant_id: str) -> EnterpriseAgreement:
        try:
            agreement = self._agreements[agreement_id]
        except KeyError as exc:
            raise DomainError("AGREEMENT_NOT_FOUND", "enterprise agreement was not found") from exc
        require(agreement.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "agreement belongs to another tenant")
        return agreement
