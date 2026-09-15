"""Financial Clearing, Payment Settlement Sandbox, and Digital Tax Invoice Engine.

Pillar 3: Bridges the gap between local mock orders and bank/tax authority clearing closures.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import hashlib
import hmac
import json
from typing import Any


@dataclasses.dataclass(frozen=True)
class PaymentNotification:
    channel: str  # "wechat_pay", "alipay"
    out_trade_no: str
    channel_trade_no: str
    amount_cents: int
    currency: str
    timestamp: str
    signature: str


class MerchantPaymentGatewaySandbox:
    """Simulates enterprise merchant gateways with cryptographic signature verification and idempotent settlement."""

    def __init__(self, secret_key: str = "elmos-prod-settlement-secret-2026") -> None:  # noqa: S107
        self.secret_key = secret_key
        self.settled_orders: dict[str, dict[str, Any]] = {}

    def sign_payload(self, payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True)
        return hmac.new(self.secret_key.encode("utf-8"), serialized.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_and_settle(self, notification: PaymentNotification) -> dict[str, Any]:
        """Verifies merchant callback signature and atomically commits payment idempotently."""
        payload = {
            "channel": notification.channel,
            "out_trade_no": notification.out_trade_no,
            "channel_trade_no": notification.channel_trade_no,
            "amount_cents": notification.amount_cents,
            "currency": notification.currency,
            "timestamp": notification.timestamp,
        }
        expected_sig = self.sign_payload(payload)
        if not hmac.compare_digest(expected_sig, notification.signature):
            return {
                "success": False,
                "error": "SIGNATURE_VERIFICATION_FAILED",
                "out_trade_no": notification.out_trade_no,
            }

        # Idempotency check
        if notification.out_trade_no in self.settled_orders:
            return {
                "success": True,
                "status": "DUPLICATE_IDEMPOTENT_IGNORE",
                "order": self.settled_orders[notification.out_trade_no],
            }

        settlement_record = {
            "out_trade_no": notification.out_trade_no,
            "channel_trade_no": notification.channel_trade_no,
            "channel": notification.channel,
            "amount_cents": notification.amount_cents,
            "settled_at": dt.datetime.now(dt.UTC).isoformat(),
        }
        self.settled_orders[notification.out_trade_no] = settlement_record

        return {
            "success": True,
            "status": "SETTLED_COMMITTED",
            "order": settlement_record,
        }


@dataclasses.dataclass
class TransactionRecord:
    order_id: str
    amount: decimal.Decimal
    currency: str = "CNY"


class ReconciliationEngine:
    """T+1 Financial Reconciliation Engine comparing internal ledger against external clearing statements."""

    def reconcile(
        self,
        internal_transactions: list[TransactionRecord],
        channel_statements: list[TransactionRecord],
    ) -> dict[str, Any]:
        internal_map = {t.order_id: t for t in internal_transactions}
        channel_map = {t.order_id: t for t in channel_statements}

        matched: list[str] = []
        amount_mismatches: list[dict[str, Any]] = []
        missing_in_internal: list[dict[str, Any]] = []
        missing_in_channel: list[dict[str, Any]] = []

        all_ids = set(internal_map.keys()) | set(channel_map.keys())
        for order_id in sorted(all_ids):
            in_rec = internal_map.get(order_id)
            ch_rec = channel_map.get(order_id)

            if in_rec and ch_rec:
                if in_rec.amount == ch_rec.amount:
                    matched.append(order_id)
                else:
                    amount_mismatches.append({
                        "order_id": order_id,
                        "internal_amount": str(in_rec.amount),
                        "channel_amount": str(ch_rec.amount),
                        "difference": str(in_rec.amount - ch_rec.amount),
                    })
            elif ch_rec and not in_rec:
                missing_in_internal.append({
                    "order_id": order_id,
                    "channel_amount": str(ch_rec.amount),
                })
            elif in_rec and not ch_rec:
                missing_in_channel.append({
                    "order_id": order_id,
                    "internal_amount": str(in_rec.amount),
                })

        balanced = len(amount_mismatches) == 0 and len(missing_in_internal) == 0 and len(missing_in_channel) == 0

        return {
            "balanced": balanced,
            "matched_count": len(matched),
            "discrepancies_count": len(amount_mismatches) + len(missing_in_internal) + len(missing_in_channel),
            "amount_mismatches": amount_mismatches,
            "missing_in_internal": missing_in_internal,
            "missing_in_channel": missing_in_channel,
        }


@dataclasses.dataclass
class DigitalTaxInvoice:
    invoice_number: str  # 20 digits for modern digital invoices
    buyer_tax_id: str
    seller_tax_id: str
    total_amount: decimal.Decimal
    tax_rate: decimal.Decimal
    tax_amount: decimal.Decimal
    is_negative_reversal: bool = False
    original_invoice_number: str | None = None
    status: str = "ISSUED"


class DigitalTaxInvoiceEngine:
    """Official Digital Tax Invoice (数电发票) compliance validator and lifecycle state machine."""

    def __init__(self) -> None:
        self.issued_invoices: dict[str, DigitalTaxInvoice] = {}

    def issue_invoice(
        self,
        invoice_number: str,
        buyer_tax_id: str,
        seller_tax_id: str,
        total_amount: decimal.Decimal,
        tax_rate: decimal.Decimal = decimal.Decimal("0.13"),
    ) -> DigitalTaxInvoice:
        if len(invoice_number) != 20 or not invoice_number.isdigit():
            raise ValueError("DIGITAL_TAX_INVOICE_NUMBER_MUST_BE_20_DIGITS")
        if not buyer_tax_id or not seller_tax_id:
            raise ValueError("TAX_ID_MANDATORY")

        tax_amount = (total_amount * tax_rate).quantize(decimal.Decimal("0.01"))
        invoice = DigitalTaxInvoice(
            invoice_number=invoice_number,
            buyer_tax_id=buyer_tax_id,
            seller_tax_id=seller_tax_id,
            total_amount=total_amount,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            status="ISSUED",
        )
        self.issued_invoices[invoice_number] = invoice
        return invoice

    def reverse_with_negative_invoice(
        self,
        negative_invoice_number: str,
        original_invoice_number: str,
        reason: str = "Order cancelled or refunded",
    ) -> DigitalTaxInvoice:
        """Issues a red-letter negative tax invoice (红字发票冲红) to reverse an existing invoice."""
        if original_invoice_number not in self.issued_invoices:
            raise ValueError(f"ORIGINAL_INVOICE_NOT_FOUND:{original_invoice_number}")

        orig = self.issued_invoices[original_invoice_number]
        if orig.status == "REVERSED":
            raise ValueError("INVOICE_ALREADY_REVERSED")

        if len(negative_invoice_number) != 20 or not negative_invoice_number.isdigit():
            raise ValueError("NEGATIVE_INVOICE_NUMBER_MUST_BE_20_DIGITS")

        negative_invoice = DigitalTaxInvoice(
            invoice_number=negative_invoice_number,
            buyer_tax_id=orig.buyer_tax_id,
            seller_tax_id=orig.seller_tax_id,
            total_amount=-orig.total_amount,
            tax_rate=orig.tax_rate,
            tax_amount=-orig.tax_amount,
            is_negative_reversal=True,
            original_invoice_number=original_invoice_number,
            status="REVERSED_CONFIRMED",
        )
        orig.status = "REVERSED"
        self.issued_invoices[negative_invoice_number] = negative_invoice
        return negative_invoice
