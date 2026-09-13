"""Usage Billing Reconciliation Engine (Batch 44 - Skill 1473).

Double-entry ledger reconciliation between metered platform consumption,
issued invoices, and financial journal entries with cryptographic audit trails.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from elmos_mature_platform.types import (
    BillingDiscrepancy,
    BillingItemType,
    BillingReconciliationStatement,
    DiscrepancyType,
    InvoiceLineItemRecord,
    MeteredUsageRecord,
)


class UsageBillingReconciliationEngine:
    """Industrial engine for usage, billing, and financial reconciliation (B44)."""

    def __init__(self, default_tolerance_usd: float = 0.01):
        self.default_tolerance_usd = default_tolerance_usd
        # Metered usage: tenant_id -> List[MeteredUsageRecord]
        self._metered_usage: Dict[str, List[MeteredUsageRecord]] = {}
        # Invoices: tenant_id -> invoice_id -> List[InvoiceLineItemRecord]
        self._invoices: Dict[str, Dict[str, List[InvoiceLineItemRecord]]] = {}
        # Statements: statement_id -> BillingReconciliationStatement
        self._statements: Dict[str, BillingReconciliationStatement] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def record_metered_usage(
        self,
        meter_id: str,
        tenant_id: str,
        item_type: BillingItemType,
        quantity: float,
        unit_price_usd: float,
    ) -> MeteredUsageRecord:
        """Record an immutable metered usage event with cryptographic hash chaining."""
        tenant_records = self._metered_usage.setdefault(tenant_id, [])
        prev_hash = tenant_records[-1].hash_curr if tenant_records else "genesis-meter-hash-000000"

        subtotal = round(quantity * unit_price_usd, 4)
        now_ts = datetime.now(timezone.utc).isoformat()

        # Compute tamper-evident hash
        raw_payload = f"{meter_id}|{tenant_id}|{item_type.value}|{quantity}|{unit_price_usd}|{subtotal}|{now_ts}|{prev_hash}"
        curr_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()

        record = MeteredUsageRecord(
            meter_id=meter_id,
            tenant_id=tenant_id,
            item_type=item_type,
            quantity=quantity,
            unit_price_usd=unit_price_usd,
            subtotal_usd=subtotal,
            timestamp=now_ts,
            hash_prev=prev_hash,
            hash_curr=curr_hash,
        )
        tenant_records.append(record)
        self._record_audit("usage_metered", tenant_id, {
            "meter_id": meter_id,
            "item_type": item_type.value,
            "subtotal": subtotal,
        })
        return record

    def record_invoice_line_item(
        self,
        tenant_id: str,
        invoice_id: str,
        line_item: InvoiceLineItemRecord,
    ) -> None:
        """Record an issued invoice line item for a tenant."""
        tenant_invoices = self._invoices.setdefault(tenant_id, {})
        invoice_lines = tenant_invoices.setdefault(invoice_id, [])
        invoice_lines.append(line_item)
        self._record_audit("invoice_line_recorded", tenant_id, {
            "invoice_id": invoice_id,
            "line_id": line_item.line_id,
            "amount": line_item.total_billed_usd,
        })

    def verify_meter_chain_integrity(self, tenant_id: str) -> Tuple[bool, str]:
        """Verify cryptographic hash chain of metered events for tamper detection."""
        records = self._metered_usage.get(tenant_id, [])
        if not records:
            return (True, "No records to verify")

        prev_hash = "genesis-meter-hash-000000"
        for idx, rec in enumerate(records):
            if rec.hash_prev != prev_hash:
                return (False, f"Hash chain broken at index {idx}: expected prev {prev_hash}, found {rec.hash_prev}")

            raw_payload = f"{rec.meter_id}|{rec.tenant_id}|{rec.item_type.value}|{rec.quantity}|{rec.unit_price_usd}|{rec.subtotal_usd}|{rec.timestamp}|{rec.hash_prev}"
            computed = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
            if computed != rec.hash_curr:
                return (False, f"Hash mismatch at index {idx}: computed {computed}, recorded {rec.hash_curr}")
            prev_hash = rec.hash_curr

        return (True, f"All {len(records)} metered events verified intact")

    def reconcile_tenant_period(
        self,
        tenant_id: str,
        period_start: str,
        period_end: str,
        tolerance_usd: Optional[float] = None,
    ) -> BillingReconciliationStatement:
        """Execute double-entry reconciliation between metered consumption and billed invoices."""
        tol = tolerance_usd if tolerance_usd is not None else self.default_tolerance_usd
        metered_records = self._metered_usage.get(tenant_id, [])

        # Filter metered usage by period
        filtered_meter = [
            r for r in metered_records
            if (not period_start or r.timestamp >= period_start) and (not period_end or r.timestamp <= period_end)
        ]

        # Aggregate metered totals by item type
        meter_totals_by_type: Dict[str, float] = {}
        for r in filtered_meter:
            meter_totals_by_type[r.item_type.value] = meter_totals_by_type.get(r.item_type.value, 0.0) + r.subtotal_usd

        total_metered = sum(meter_totals_by_type.values())

        # Aggregate invoiced totals by item type
        tenant_invoices = self._invoices.get(tenant_id, {})
        invoiced_totals_by_type: Dict[str, float] = {}
        for inv_id, lines in tenant_invoices.items():
            for line in lines:
                invoiced_totals_by_type[line.item_type.value] = invoiced_totals_by_type.get(line.item_type.value, 0.0) + line.total_billed_usd

        total_invoiced = sum(invoiced_totals_by_type.values())

        # Detect discrepancies
        all_types = set(meter_totals_by_type.keys()) | set(invoiced_totals_by_type.keys())
        discrepancies: List[BillingDiscrepancy] = []

        for itype_str in sorted(all_types):
            m_amt = meter_totals_by_type.get(itype_str, 0.0)
            i_amt = invoiced_totals_by_type.get(itype_str, 0.0)
            variance = i_amt - m_amt

            if abs(variance) > tol:
                if variance > tol:
                    disc_type = DiscrepancyType.OVERBILLING
                elif variance < -tol:
                    disc_type = DiscrepancyType.UNDERBILLING
                else:
                    disc_type = DiscrepancyType.ROUNDING_ERROR

                d_id = f"disc-{tenant_id}-{itype_str}-{int(datetime.now(timezone.utc).timestamp())}"
                discrepancy = BillingDiscrepancy(
                    discrepancy_id=d_id,
                    tenant_id=tenant_id,
                    item_type=BillingItemType(itype_str),
                    metered_amount_usd=round(m_amt, 4),
                    invoiced_amount_usd=round(i_amt, 4),
                    variance_usd=round(variance, 4),
                    discrepancy_type=disc_type,
                    resolved=False,
                    adjustment_credit_usd=round(variance, 4) if disc_type == DiscrepancyType.OVERBILLING else 0.0,
                )
                discrepancies.append(discrepancy)

        total_variance = total_invoiced - total_metered
        balanced = len(discrepancies) == 0 and abs(total_variance) <= tol

        # Compute audit hash over statement
        audit_payload = f"{tenant_id}|{period_start}|{period_end}|{total_metered}|{total_invoiced}|{balanced}|{len(discrepancies)}"
        audit_hash = hashlib.sha256(audit_payload.encode("utf-8")).hexdigest()

        statement_id = f"stmt-{tenant_id}-{int(datetime.now(timezone.utc).timestamp())}"
        statement = BillingReconciliationStatement(
            statement_id=statement_id,
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            total_metered_usd=round(total_metered, 4),
            total_invoiced_usd=round(total_invoiced, 4),
            variance_total_usd=round(total_variance, 4),
            discrepancies=discrepancies,
            balanced=balanced,
            tolerance_threshold_usd=tol,
            audit_hash=audit_hash,
            reconciled_at=datetime.now(timezone.utc).isoformat(),
        )
        self._statements[statement_id] = statement
        self._record_audit("reconciliation_completed", tenant_id, {
            "statement_id": statement_id,
            "balanced": balanced,
            "discrepancies_count": len(discrepancies),
        })
        return statement

    def apply_credit_adjustment(self, statement_id: str, discrepancy_id: str) -> bool:
        """Apply a credit adjustment to resolve an overbilling discrepancy."""
        stmt = self._statements.get(statement_id)
        if not stmt:
            return False

        for disc in stmt.discrepancies:
            if disc.discrepancy_id == discrepancy_id and not disc.resolved:
                disc.resolved = True
                self._record_audit("credit_adjustment_applied", stmt.tenant_id, {
                    "statement_id": statement_id,
                    "discrepancy_id": discrepancy_id,
                    "credit_usd": disc.adjustment_credit_usd,
                })
                # Check if all discrepancies are now resolved
                if all(d.resolved for d in stmt.discrepancies):
                    stmt.balanced = True
                return True
        return False

    def get_statement(self, statement_id: str) -> Optional[BillingReconciliationStatement]:
        """Fetch reconciliation statement by ID."""
        return self._statements.get(statement_id)

    def _record_audit(self, action: str, tenant_id: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "tenant_id": tenant_id,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
