"""Showback and Chargeback Engine (Batch 44 - Skill 1458).

Provides enterprise IT financial management (ITFM), departmental consumption invoicing,
cost center showback/chargeback allocation, and dispute resolution workflows.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    ChargebackBillingCycle,
    ChargebackDispute,
    ChargebackInvoice,
    DepartmentShowbackSummary,
)


class ShowbackChargebackEngine:
    """Enterprise showback and chargeback cost allocation engine."""

    def __init__(self) -> None:
        self._invoices: Dict[str, ChargebackInvoice] = {}
        self._disputes: Dict[str, ChargebackDispute] = {}

    def generate_invoice(self, invoice: ChargebackInvoice) -> str:
        """Generate a departmental chargeback invoice."""
        if invoice.total_amount_usd < 0:
            raise ValueError("total_amount_usd cannot be negative")

        if not invoice.department_id:
            raise ValueError("department_id is required")

        if not invoice.invoice_id:
            invoice.invoice_id = f"inv-{uuid.uuid4().hex[:8]}"

        if not invoice.issued_at:
            invoice.issued_at = datetime.now(timezone.utc).isoformat()

        # If line items sum > 0 and total_amount_usd was 0, compute from line items
        if invoice.line_items and invoice.total_amount_usd == 0:
            invoice.total_amount_usd = round(sum(invoice.line_items.values()), 2)

        self._invoices[invoice.invoice_id] = invoice
        return invoice.invoice_id

    def pay_invoice(self, invoice_id: str) -> ChargebackInvoice:
        """Record payment settlement for a chargeback invoice."""
        invoice = self._invoices.get(invoice_id)
        if not invoice:
            raise ValueError(f"Invoice not found: {invoice_id}")

        if invoice.paid:
            return invoice

        invoice.paid = True
        invoice.paid_at = datetime.now(timezone.utc).isoformat()
        return invoice

    def raise_dispute(self, dispute: ChargebackDispute) -> str:
        """Raise a billing dispute against an invoice."""
        if dispute.disputed_amount_usd <= 0:
            raise ValueError("disputed_amount_usd must be positive")

        invoice = self._invoices.get(dispute.invoice_id)
        if not invoice:
            raise ValueError(f"Target invoice not found: {dispute.invoice_id}")

        if dispute.disputed_amount_usd > invoice.total_amount_usd:
            raise ValueError("Disputed amount cannot exceed total invoice amount")

        if not dispute.dispute_id:
            dispute.dispute_id = f"disp-{uuid.uuid4().hex[:8]}"

        dispute.status = "open"
        self._disputes[dispute.dispute_id] = dispute
        return dispute.dispute_id

    def resolve_dispute(
        self, dispute_id: str, approved: bool, notes: str = ""
    ) -> ChargebackDispute:
        """Resolve an open chargeback billing dispute."""
        dispute = self._disputes.get(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute not found: {dispute_id}")

        if dispute.status != "open":
            raise ValueError(f"Dispute {dispute_id} is already {dispute.status}")

        dispute.status = "resolved" if approved else "rejected"
        dispute.resolved_at = datetime.now(timezone.utc).isoformat()
        dispute.notes = notes

        # If dispute approved, adjust invoice amount accordingly
        if approved:
            invoice = self._invoices.get(dispute.invoice_id)
            if invoice:
                invoice.total_amount_usd = max(
                    0.0, round(invoice.total_amount_usd - dispute.disputed_amount_usd, 2)
                )

        return dispute

    def get_invoice(self, invoice_id: str) -> Optional[ChargebackInvoice]:
        """Retrieve an invoice by ID."""
        return self._invoices.get(invoice_id)

    def get_dispute(self, dispute_id: str) -> Optional[ChargebackDispute]:
        """Retrieve a dispute by ID."""
        return self._disputes.get(dispute_id)

    def get_department_showback(self, department_id: str) -> DepartmentShowbackSummary:
        """Compute consolidated consumption showback for a specific department."""
        dept_invoices = [
            inv for inv in self._invoices.values() if inv.department_id == department_id
        ]
        total_spend = sum(inv.total_amount_usd for inv in dept_invoices)

        open_disputes = sum(
            1
            for disp in self._disputes.values()
            if disp.department_id == department_id and disp.status == "open"
        )

        categories: Dict[str, float] = {}
        for inv in dept_invoices:
            for cat, amount in inv.line_items.items():
                categories[cat] = round(categories.get(cat, 0.0) + amount, 2)

        return DepartmentShowbackSummary(
            department_id=department_id,
            total_spend_usd=round(total_spend, 2),
            invoices_count=len(dept_invoices),
            open_disputes_count=open_disputes,
            spend_by_category=categories,
        )

    def get_chargeback_report(self) -> Dict[str, Any]:
        """Generate global showback and chargeback financial governance report."""
        total_invoiced = sum(inv.total_amount_usd for inv in self._invoices.values())
        paid_invoices = [inv for inv in self._invoices.values() if inv.paid]
        total_paid = sum(inv.total_amount_usd for inv in paid_invoices)
        total_outstanding = total_invoiced - total_paid

        open_disp = sum(1 for d in self._disputes.values() if d.status == "open")
        resolved_disp = sum(1 for d in self._disputes.values() if d.status == "resolved")
        rejected_disp = sum(1 for d in self._disputes.values() if d.status == "rejected")
        disputed_spend = sum(d.disputed_amount_usd for d in self._disputes.values() if d.status == "open")

        return {
            "total_invoices_count": len(self._invoices),
            "paid_invoices_count": len(paid_invoices),
            "total_invoiced_usd": round(total_invoiced, 2),
            "total_paid_usd": round(total_paid, 2),
            "total_outstanding_usd": round(total_outstanding, 2),
            "open_disputes_count": open_disp,
            "resolved_disputes_count": resolved_disp,
            "rejected_disputes_count": rejected_disp,
            "active_disputed_usd": round(disputed_spend, 2),
        }
