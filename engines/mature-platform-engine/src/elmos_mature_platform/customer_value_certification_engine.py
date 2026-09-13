"""Customer Value Certification Engine (Batch 45 - Skill 1450).

Certifies customer business value attainment, ROI milestones, latency improvements,
TCO reductions, code quality improvements, and customer stakeholder signoff.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    CustomerValueCertificate,
    MilestoneStatus,
    ValueMetricCategory,
    ValueMilestone,
)


class CustomerValueCertificationEngine:
    """Industrial customer business value & ROI certification engine (B45)."""

    def __init__(self):
        self._certificates: Dict[str, CustomerValueCertificate] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def create_certificate(
        self,
        customer_id: str,
        project_name: str,
        contract_reference: str,
    ) -> CustomerValueCertificate:
        """Initialize a new customer value certificate."""
        cert_id = f"cvc-{uuid.uuid4().hex[:8]}"
        cert = CustomerValueCertificate(
            certificate_id=cert_id,
            customer_id=customer_id,
            project_name=project_name,
            contract_reference=contract_reference,
            certified_at="",
            certifier="",
            milestones=[],
            overall_roi_pct=0.0,
            customer_signoff=False,
            customer_signoff_date="",
            notes="",
        )
        self._certificates[cert_id] = cert
        self._record_audit("certificate_created", cert_id, {"customer_id": customer_id, "project": project_name})
        return cert

    def get_certificate(self, certificate_id: str) -> Optional[CustomerValueCertificate]:
        """Fetch certificate by ID."""
        return self._certificates.get(certificate_id)

    def add_milestone(
        self,
        certificate_id: str,
        milestone: ValueMilestone,
    ) -> CustomerValueCertificate:
        """Add a target business or technical value milestone."""
        cert = self._get_cert_or_raise(certificate_id)
        cert.milestones.append(milestone)
        return cert

    def update_milestone_progress(
        self,
        certificate_id: str,
        milestone_id: str,
        actual_value: float,
        status: Optional[MilestoneStatus] = None,
    ) -> ValueMilestone:
        """Update actual measured value and determine milestone achievement."""
        cert = self._get_cert_or_raise(certificate_id)
        milestone = next((m for m in cert.milestones if m.milestone_id == milestone_id), None)
        if not milestone:
            raise ValueError(f"Milestone {milestone_id} not found in certificate {certificate_id}")

        milestone.actual_value = actual_value

        # Automatic achievement assessment if target >= baseline (improvement) or target <= baseline (reduction)
        if milestone.category in (ValueMetricCategory.TCO_REDUCTION, ValueMetricCategory.LATENCY_IMPROVEMENT, ValueMetricCategory.LICENSING_SAVINGS):
            # Lower is better or reduction is better
            achieved = actual_value <= milestone.target_value
        else:
            # Higher is better
            achieved = actual_value >= milestone.target_value

        milestone.achieved = achieved
        if status:
            milestone.status = status
        else:
            milestone.status = MilestoneStatus.ACHIEVED if achieved else MilestoneStatus.IN_PROGRESS

        # Re-calculate overall ROI
        cert.overall_roi_pct = self.calculate_overall_roi(certificate_id)
        return milestone

    def calculate_overall_roi(self, certificate_id: str) -> float:
        """Calculate weighted or aggregate ROI percentage across achieved milestones."""
        cert = self._get_cert_or_raise(certificate_id)
        if not cert.milestones:
            return 0.0

        improvements: List[float] = []
        for m in cert.milestones:
            if m.baseline_value != 0.0:
                if m.category in (ValueMetricCategory.TCO_REDUCTION, ValueMetricCategory.LATENCY_IMPROVEMENT, ValueMetricCategory.LICENSING_SAVINGS):
                    # Reduction pct
                    pct = ((m.baseline_value - m.actual_value) / m.baseline_value) * 100.0
                else:
                    pct = ((m.actual_value - m.baseline_value) / m.baseline_value) * 100.0
                improvements.append(pct)

        if not improvements:
            return 0.0
        return round(sum(improvements) / len(improvements), 2)

    def certify_value(self, certificate_id: str, certifier: str) -> CustomerValueCertificate:
        """Formally issue certificate if all mandatory milestones are achieved or waived."""
        cert = self._get_cert_or_raise(certificate_id)
        if not cert.milestones:
            raise ValueError("Cannot certify without defined value milestones")

        unmet = [m for m in cert.milestones if m.status not in (MilestoneStatus.ACHIEVED, MilestoneStatus.WAIVED)]
        if unmet:
            unmet_names = [m.name for m in unmet]
            raise ValueError(f"Cannot certify value: unmet milestones: {', '.join(unmet_names)}")

        cert.certified_at = datetime.now(timezone.utc).isoformat()
        cert.certifier = certifier
        self._record_audit("value_certified", certificate_id, {"certifier": certifier, "roi_pct": cert.overall_roi_pct})
        return cert

    def record_customer_signoff(
        self,
        certificate_id: str,
        signoff_date: str,
        notes: str = "",
    ) -> CustomerValueCertificate:
        """Record explicit customer executive or stakeholder acceptance signoff."""
        cert = self._get_cert_or_raise(certificate_id)
        if not cert.certified_at:
            raise ValueError("Cannot record customer signoff on uncertified certificate")

        cert.customer_signoff = True
        cert.customer_signoff_date = signoff_date or datetime.now(timezone.utc).isoformat()
        cert.notes = notes
        self._record_audit("customer_signoff", certificate_id, {"signoff_date": cert.customer_signoff_date})
        return cert

    def get_customer_report(self, certificate_id: str) -> Dict[str, Any]:
        """Generate executive-level customer business value report."""
        cert = self._get_cert_or_raise(certificate_id)
        total_m = len(cert.milestones)
        achieved_m = sum(1 for m in cert.milestones if m.status == MilestoneStatus.ACHIEVED)

        return {
            "certificate_id": cert.certificate_id,
            "customer_id": cert.customer_id,
            "project_name": cert.project_name,
            "contract_reference": cert.contract_reference,
            "certified": bool(cert.certified_at),
            "certified_at": cert.certified_at,
            "certifier": cert.certifier,
            "customer_signed_off": cert.customer_signoff,
            "customer_signoff_date": cert.customer_signoff_date,
            "overall_roi_pct": cert.overall_roi_pct,
            "milestone_progress": {
                "total": total_m,
                "achieved": achieved_m,
                "achievement_rate_pct": round((achieved_m / total_m) * 100.0, 2) if total_m > 0 else 0.0,
            },
            "milestones": [
                {
                    "name": m.name,
                    "category": m.category.value,
                    "baseline": m.baseline_value,
                    "target": m.target_value,
                    "actual": m.actual_value,
                    "unit": m.unit,
                    "status": m.status.value,
                    "achieved": m.achieved,
                }
                for m in cert.milestones
            ],
            "notes": cert.notes,
        }

    def _get_cert_or_raise(self, certificate_id: str) -> CustomerValueCertificate:
        if certificate_id not in self._certificates:
            raise ValueError(f"Certificate {certificate_id} not found")
        return self._certificates[certificate_id]

    def _record_audit(self, action: str, target: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
