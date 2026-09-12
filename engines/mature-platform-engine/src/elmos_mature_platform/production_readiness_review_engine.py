"""Production Readiness Review (PRR) Engine (Batch 39 - Skill 1364).

Automates enterprise SRE Production Readiness Reviews covering monitoring,
capacity scaling, disaster recovery, security compliance, incident runbooks,
deployment rollbacks, and dependency resilience prior to production admission.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    PrrCategory,
    PrrChecklistItem,
    PrrItemStatus,
    ProductionReadinessReviewRecord,
)


class ProductionReadinessReviewEngine:
    """Industrial engine for SRE Production Readiness Reviews (PRR - B39)."""

    def __init__(self, passing_score_threshold: float = 85.0):
        self.passing_score_threshold = passing_score_threshold
        self._reviews: Dict[str, ProductionReadinessReviewRecord] = {}

    def _default_checklist_items(self) -> List[PrrChecklistItem]:
        """Seed canonical SRE PRR checklist items across all categories."""
        templates = [
            (PrrCategory.MONITORING_ALERTS, "SLO Alerting & PagerDuty Route Configured", True),
            (PrrCategory.MONITORING_ALERTS, "Health and Readiness Check Probes Active", True),
            (PrrCategory.CAPACITY_SCALING, "HPA Autoscaling Policies Tested Under Load", True),
            (PrrCategory.CAPACITY_SCALING, "Resource Limits and Requests Baseline Sized", False),
            (PrrCategory.DISASTER_RECOVERY, "Backup and Point-in-Time Restore Verified (<1h RTO)", True),
            (PrrCategory.DISASTER_RECOVERY, "Multi-AZ Failover Tested Without Data Loss", True),
            (PrrCategory.SECURITY_COMPLIANCE, "Vulnerability Scan Clean & Secrets in KMS/Vault", True),
            (PrrCategory.SECURITY_COMPLIANCE, "TLS 1.3 & mTLS Enforced on Ingress and Egress", True),
            (PrrCategory.INCIDENT_RUNBOOKS, "On-Call Triage Runbook Linked and Accessible", True),
            (PrrCategory.INCIDENT_RUNBOOKS, "Escalation Matrix & Secondary On-Call Validated", False),
            (PrrCategory.DEPLOYMENT_ROLLBACK, "Canary Progressive Rollout & Auto-Rollback Configured", True),
            (PrrCategory.DEPLOYMENT_ROLLBACK, "Schema Migration Backward-Compatibility Verified", True),
            (PrrCategory.DEPENDENCY_RESILIENCE, "Circuit Breakers & Fallbacks on Downstream Services", True),
            (PrrCategory.DEPENDENCY_RESILIENCE, "Graceful Degradation Under Network Partition Tested", False),
        ]

        items = []
        for cat, title, blocking in templates:
            item_id = f"prr-{cat.value[:4]}-{uuid.uuid4().hex[:6]}"
            items.append(
                PrrChecklistItem(
                    item_id=item_id,
                    category=cat,
                    title=title,
                    status=PrrItemStatus.FAIL,
                    blocking=blocking,
                )
            )
        return items

    def create_review(
        self,
        service_name: str,
        target_environment: str = "production",
        auto_seed_checklist: bool = True,
    ) -> ProductionReadinessReviewRecord:
        """Create a new PRR record for a service targeting an environment."""
        review_id = f"prr-{uuid.uuid4().hex[:8]}"
        items = self._default_checklist_items() if auto_seed_checklist else []
        record = ProductionReadinessReviewRecord(
            review_id=review_id,
            service_name=service_name,
            target_environment=target_environment,
            checklist=items,
            approved=False,
            readiness_score=0.0,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
        )
        self._reviews[review_id] = record
        return record

    def add_custom_item(
        self,
        review_id: str,
        item: PrrChecklistItem,
    ) -> PrrChecklistItem:
        """Add a custom checklist item to an existing review."""
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review '{review_id}' not found")
        if not item.item_id:
            item.item_id = f"prr-cust-{uuid.uuid4().hex[:6]}"
        review.checklist.append(item)
        return item

    def record_checklist_item(
        self,
        review_id: str,
        item_id: str,
        status: PrrItemStatus,
        owner: str = "",
        remediation: str = "",
    ) -> PrrChecklistItem:
        """Update the status and remediation notes of a specific checklist item."""
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review '{review_id}' not found")

        target_item: Optional[PrrChecklistItem] = None
        for it in review.checklist:
            if it.item_id == item_id:
                target_item = it
                break

        if not target_item:
            raise ValueError(f"Checklist item '{item_id}' not found in review '{review_id}'")

        target_item.status = status
        if owner:
            target_item.owner = owner
        if remediation:
            target_item.remediation = remediation

        return target_item

    def waive_checklist_item(
        self,
        review_id: str,
        item_id: str,
        waiver_justification: str,
        approver: str,
    ) -> PrrChecklistItem:
        """Explicitly waive a checklist item with justification and approver audit."""
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review '{review_id}' not found")

        target_item: Optional[PrrChecklistItem] = None
        for it in review.checklist:
            if it.item_id == item_id:
                target_item = it
                break

        if not target_item:
            raise ValueError(f"Checklist item '{item_id}' not found in review '{review_id}'")

        if not waiver_justification.strip():
            raise ValueError("Waiver justification cannot be empty")
        if not approver.strip():
            raise ValueError("Waiver approver cannot be empty")

        target_item.status = PrrItemStatus.WAIVED
        target_item.remediation = f"WAIVER granted by {approver}: {waiver_justification}"
        return target_item

    def evaluate_approval(
        self,
        review_id: str,
        sign_off_sre: str,
    ) -> ProductionReadinessReviewRecord:
        """Evaluate checklist criteria and determine whether the service is approved for production."""
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review '{review_id}' not found")

        total_items = len(review.checklist)
        if total_items == 0:
            review.readiness_score = 0.0
            review.approved = False
            return review

        passing_items = sum(
            1 for it in review.checklist if it.status in (PrrItemStatus.PASS, PrrItemStatus.WAIVED)
        )
        score = round((passing_items / total_items) * 100.0, 2)
        review.readiness_score = score

        open_blockers = self.get_open_blockers(review_id)
        is_score_ok = score >= self.passing_score_threshold
        has_no_blockers = len(open_blockers) == 0

        review.approved = is_score_ok and has_no_blockers
        if review.approved:
            review.sign_off_sre = sign_off_sre
            review.reviewed_at = datetime.now(timezone.utc).isoformat()
        else:
            review.sign_off_sre = ""

        return review

    def get_open_blockers(self, review_id: str) -> List[PrrChecklistItem]:
        """Return all blocking checklist items that are currently FAIL or BLOCKED."""
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review '{review_id}' not found")

        return [
            it
            for it in review.checklist
            if it.blocking and it.status in (PrrItemStatus.FAIL, PrrItemStatus.BLOCKED)
        ]

    def get_review_scorecard(self, review_id: str) -> Dict[str, Any]:
        """Generate a detailed scorecard of review progress by category."""
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review '{review_id}' not found")

        category_breakdown: Dict[str, Dict[str, int]] = {}
        for cat in PrrCategory:
            category_breakdown[cat.value] = {
                "total": 0,
                "pass": 0,
                "fail": 0,
                "blocked": 0,
                "waived": 0,
            }

        for it in review.checklist:
            c_dict = category_breakdown[it.category.value]
            c_dict["total"] += 1
            if it.status == PrrItemStatus.PASS:
                c_dict["pass"] += 1
            elif it.status == PrrItemStatus.FAIL:
                c_dict["fail"] += 1
            elif it.status == PrrItemStatus.BLOCKED:
                c_dict["blocked"] += 1
            elif it.status == PrrItemStatus.WAIVED:
                c_dict["waived"] += 1

        total_items = len(review.checklist)
        passing_items = sum(
            1 for it in review.checklist if it.status in (PrrItemStatus.PASS, PrrItemStatus.WAIVED)
        )
        score = round((passing_items / total_items) * 100.0, 2) if total_items > 0 else 0.0

        return {
            "review_id": review.review_id,
            "service_name": review.service_name,
            "target_environment": review.target_environment,
            "total_items": total_items,
            "passing_items": passing_items,
            "readiness_score": score,
            "approved": review.approved,
            "sign_off_sre": review.sign_off_sre,
            "open_blockers_count": len(self.get_open_blockers(review_id)),
            "by_category": category_breakdown,
        }

    def get_review(self, review_id: str) -> Optional[ProductionReadinessReviewRecord]:
        """Retrieve review by ID."""
        return self._reviews.get(review_id)

    def list_reviews(self, service_name: Optional[str] = None) -> List[ProductionReadinessReviewRecord]:
        """List reviews, optionally filtered by service name."""
        if service_name:
            return [r for r in self._reviews.values() if r.service_name == service_name]
        return list(self._reviews.values())
