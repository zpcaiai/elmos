"""Security Architecture Review Engine (Batch 40 - Skill 1369).

Performs STRIDE threat modeling, trust boundary verification, mitigation tracking,
residual risk acceptance governance, and formal security review verdicts.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    SecurityArchitectureReviewRecord,
    SecurityReviewVerdict,
    SecurityThreatModel,
    StrideCategory,
    ThreatSeverity,
)


class SecurityArchitectureReviewEngine:
    """Conducts STRIDE threat modeling and architectural security reviews."""

    def __init__(self) -> None:
        self._reviews: Dict[str, SecurityArchitectureReviewRecord] = {}

    def initiate_review(
        self,
        system_name: str,
        architecture_version: str,
        trust_boundaries_defined: bool = True,
    ) -> str:
        """Initialize a new security architecture review."""
        if not system_name or not architecture_version:
            raise ValueError("system_name and architecture_version are required")

        review_id = f"rev-{uuid.uuid4().hex[:8]}"
        record = SecurityArchitectureReviewRecord(
            review_id=review_id,
            system_name=system_name,
            architecture_version=architecture_version,
            trust_boundaries_defined=trust_boundaries_defined,
            verdict=SecurityReviewVerdict.REJECTED,
        )
        self._reviews[review_id] = record
        return review_id

    def add_threat_model(
        self, review_id: str, threat: SecurityThreatModel
    ) -> SecurityThreatModel:
        """Add an identified STRIDE threat to the review."""
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review not found: {review_id}")

        if not threat.threat_id:
            threat.threat_id = f"threat-{uuid.uuid4().hex[:8]}"

        review.threats.append(threat)
        return threat

    def mitigate_threat(
        self, review_id: str, threat_id: str, control: str
    ) -> SecurityThreatModel:
        """Record technical mitigation control against an identified threat."""
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review not found: {review_id}")

        threat = next((t for t in review.threats if t.threat_id == threat_id), None)
        if not threat:
            raise ValueError(f"Threat not found: {threat_id}")
        if not control:
            raise ValueError("Mitigation control cannot be empty")

        threat.mitigation_control = control
        threat.is_mitigated = True
        return threat

    def accept_residual_risk(
        self, review_id: str, threat_id: str, justification: str
    ) -> SecurityThreatModel:
        """Accept residual risk for low or medium unmitigated threats."""
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review not found: {review_id}")

        threat = next((t for t in review.threats if t.threat_id == threat_id), None)
        if not threat:
            raise ValueError(f"Threat not found: {threat_id}")

        if threat.severity == ThreatSeverity.CRITICAL:
            raise PermissionError("CRITICAL threats cannot have residual risk accepted without mitigation")

        threat.residual_risk_accepted = True
        review.action_items.append(f"Risk accepted for {threat.threat_id}: {justification}")
        return threat

    def evaluate_security_verdict(
        self, review_id: str, reviewer: str = "security-architect"
    ) -> SecurityArchitectureReviewRecord:
        """Establish architectural security approval verdict based on open threats."""
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review not found: {review_id}")

        review.reviewed_by = reviewer
        review.reviewed_at = datetime.now(timezone.utc).isoformat()

        if not review.trust_boundaries_defined:
            review.verdict = SecurityReviewVerdict.REJECTED
            review.action_items.append("Must define formal trust boundaries before approval")
            return review

        unmitigated_critical = [
            t for t in review.threats if t.severity == ThreatSeverity.CRITICAL and not t.is_mitigated
        ]
        unmitigated_high = [
            t
            for t in review.threats
            if t.severity == ThreatSeverity.HIGH and not t.is_mitigated and not t.residual_risk_accepted
        ]
        unmitigated_medium = [
            t
            for t in review.threats
            if t.severity == ThreatSeverity.MEDIUM and not t.is_mitigated and not t.residual_risk_accepted
        ]

        if unmitigated_critical or unmitigated_high:
            review.verdict = SecurityReviewVerdict.REJECTED
        elif unmitigated_medium:
            review.verdict = SecurityReviewVerdict.CONDITIONAL_APPROVAL
            review.action_items.append(
                f"Requires remediation of {len(unmitigated_medium)} medium threats in 30 days"
            )
        else:
            review.verdict = SecurityReviewVerdict.APPROVED

        return review

    def get_review(self, review_id: str) -> Optional[SecurityArchitectureReviewRecord]:
        """Retrieve review record by ID."""
        return self._reviews.get(review_id)

    def get_threats_by_stride_category(
        self, review_id: str
    ) -> Dict[str, List[SecurityThreatModel]]:
        """Group review threats by STRIDE classification."""
        review = self._reviews.get(review_id)
        if not review:
            raise ValueError(f"Review not found: {review_id}")

        groups: Dict[str, List[SecurityThreatModel]] = {}
        for cat in StrideCategory:
            groups[cat.value] = [t for t in review.threats if t.category == cat]
        return groups

    def get_security_architecture_summary(self) -> Dict[str, Any]:
        """Aggregate metrics across all architectural security reviews."""
        total_rev = len(self._reviews)
        approved = sum(
            1 for r in self._reviews.values() if r.verdict == SecurityReviewVerdict.APPROVED
        )
        rejected = sum(
            1 for r in self._reviews.values() if r.verdict == SecurityReviewVerdict.REJECTED
        )
        total_threats = sum(len(r.threats) for r in self._reviews.values())

        return {
            "total_reviews": total_rev,
            "approved_reviews": approved,
            "rejected_reviews": rejected,
            "approval_rate": round(approved / total_rev, 4) if total_rev > 0 else 0.0,
            "total_modeled_threats": total_threats,
        }
