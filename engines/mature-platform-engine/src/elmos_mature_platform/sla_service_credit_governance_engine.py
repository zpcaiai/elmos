"""SLA Service Credit Governance Engine - Batch 39 Skill 1365.

Enforces contractual SLA tiers, calculates service credits based on monthly recurring fees,
and manages executive approval workflows and credit disbursements.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import uuid

from .types import (
    SlaBreachTier,
    ServiceCreditStatus,
    SlaServiceCreditPolicy,
    CustomerSlaBreachRecord,
    ServiceCreditDisbursement,
)


class SlaServiceCreditGovernanceEngine:
    """Governs SLA breach evaluations, service credit calculations, approvals, and disbursements."""

    def __init__(self, policy: Optional[SlaServiceCreditPolicy] = None) -> None:
        self._policy = policy or SlaServiceCreditPolicy(
            policy_id="default-sla-policy",
            tier_1_credit_pct=10.0,
            tier_2_credit_pct=25.0,
            tier_3_credit_pct=50.0,
            requires_executive_approval_over=5000.0,
        )
        self._breaches: Dict[str, CustomerSlaBreachRecord] = {}
        self._disbursements: Dict[str, ServiceCreditDisbursement] = {}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def set_policy(self, policy: SlaServiceCreditPolicy) -> str:
        """Update active service credit policy."""
        if not policy.policy_id:
            raise ValueError("policy_id must not be empty")
        self._policy = policy
        return policy.policy_id

    def record_breach(self, breach: CustomerSlaBreachRecord) -> str:
        """Record and automatically classify an SLA breach and calculate eligible credit."""
        if not breach.breach_id or not breach.customer_id or not breach.service_name:
            raise ValueError("breach_id, customer_id, and service_name must not be empty")
        if breach.monthly_invoice_amount < 0.0:
            raise ValueError("monthly_invoice_amount must be non-negative")
        if breach.actual_availability_pct >= breach.target_availability_pct:
            raise ValueError(
                f"Actual availability {breach.actual_availability_pct}% meets or exceeds "
                f"target {breach.target_availability_pct}%; no breach occurred."
            )

        # Determine breach tier
        if breach.actual_availability_pct >= 99.0:
            breach.breach_tier = SlaBreachTier.TIER_1_MINOR
            credit_pct = self._policy.tier_1_credit_pct
        elif breach.actual_availability_pct >= 95.0:
            breach.breach_tier = SlaBreachTier.TIER_2_MODERATE
            credit_pct = self._policy.tier_2_credit_pct
        else:
            breach.breach_tier = SlaBreachTier.TIER_3_SEVERE
            credit_pct = self._policy.tier_3_credit_pct

        breach.calculated_credit_amount = round(
            breach.monthly_invoice_amount * (credit_pct / 100.0), 2
        )
        breach.status = ServiceCreditStatus.CALCULATED
        if not breach.recorded_at:
            breach.recorded_at = self._now_iso()

        self._breaches[breach.breach_id] = breach
        return breach.breach_id

    def approve_credit(self, breach_id: str, approver: str) -> CustomerSlaBreachRecord:
        """Approve calculated service credit, checking executive threshold when required."""
        if breach_id not in self._breaches:
            raise ValueError(f"Breach record {breach_id} not found")
        if not approver:
            raise ValueError("approver must not be empty")

        breach = self._breaches[breach_id]
        if breach.status not in (ServiceCreditStatus.CALCULATED, ServiceCreditStatus.PENDING_CALCULATION):
            raise ValueError(f"Cannot approve breach in status {breach.status.value}")

        if breach.calculated_credit_amount > self._policy.requires_executive_approval_over:
            if not approver.lower().startswith(("exec", "vp-", "c-level", "dir-")):
                raise ValueError(
                    f"Credit amount ${breach.calculated_credit_amount} exceeds executive approval "
                    f"threshold ${self._policy.requires_executive_approval_over}; requires executive role."
                )

        breach.status = ServiceCreditStatus.APPROVED
        breach.approved_by = approver
        return breach

    def reject_credit(self, breach_id: str, reason: str) -> CustomerSlaBreachRecord:
        """Reject service credit claim with recorded justification."""
        if breach_id not in self._breaches:
            raise ValueError(f"Breach record {breach_id} not found")
        if not reason:
            raise ValueError("Rejection reason must be provided")

        breach = self._breaches[breach_id]
        breach.status = ServiceCreditStatus.REJECTED
        return breach

    def disburse_credit(self, breach_id: str, reference: str) -> ServiceCreditDisbursement:
        """Issue credit note / refund disbursement for an approved SLA breach."""
        if breach_id not in self._breaches:
            raise ValueError(f"Breach record {breach_id} not found")
        if not reference:
            raise ValueError("Disbursement reference must not be empty")

        breach = self._breaches[breach_id]
        if breach.status != ServiceCreditStatus.APPROVED:
            raise ValueError(f"Cannot disburse credit for breach in status {breach.status.value}; must be APPROVED")

        disbursement_id = f"disb-{uuid.uuid4().hex[:12]}"
        disbursement = ServiceCreditDisbursement(
            disbursement_id=disbursement_id,
            breach_id=breach_id,
            customer_id=breach.customer_id,
            amount=breach.calculated_credit_amount,
            disbursed_at=self._now_iso(),
            disbursement_reference=reference,
        )
        self._disbursements[disbursement_id] = disbursement
        breach.status = ServiceCreditStatus.DISBURSED
        return disbursement

    def get_breach(self, breach_id: str) -> Optional[CustomerSlaBreachRecord]:
        """Retrieve breach record by ID."""
        return self._breaches.get(breach_id)

    def get_disbursement(self, disbursement_id: str) -> Optional[ServiceCreditDisbursement]:
        """Retrieve disbursement by ID."""
        return self._disbursements.get(disbursement_id)

    def get_disbursements_for_customer(self, customer_id: str) -> List[ServiceCreditDisbursement]:
        """List all disbursements for a customer."""
        return [d for d in self._disbursements.values() if d.customer_id == customer_id]

    def get_pending_approvals(self) -> List[CustomerSlaBreachRecord]:
        """List all breaches awaiting approval."""
        return [
            b for b in self._breaches.values()
            if b.status in (ServiceCreditStatus.CALCULATED, ServiceCreditStatus.PENDING_CALCULATION)
        ]

    def get_governance_report(self) -> Dict[str, Any]:
        """Generate high-level report on SLA breaches, credits calculated, and disbursements."""
        total = len(self._breaches)
        by_status = {s.value: 0 for s in ServiceCreditStatus}
        by_tier = {t.value: 0 for t in SlaBreachTier}
        total_calculated = sum(b.calculated_credit_amount for b in self._breaches.values())
        total_disbursed = sum(d.amount for d in self._disbursements.values())

        for b in self._breaches.values():
            by_status[b.status.value] = by_status.get(b.status.value, 0) + 1
            by_tier[b.breach_tier.value] = by_tier.get(b.breach_tier.value, 0) + 1

        return {
            "total_breaches": total,
            "total_credit_calculated": round(total_calculated, 2),
            "total_credit_disbursed": round(total_disbursed, 2),
            "by_status": by_status,
            "by_breach_tier": by_tier,
            "total_disbursements_count": len(self._disbursements),
        }
