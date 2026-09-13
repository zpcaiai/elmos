"""Secure Code Review and Approval Engine - Batch 40 Skill 1373.

Classifies sensitivity flags (auth, crypto, DDL, IAM), enforces multi-reviewer quorum
for high/critical risk changes, and gates production commits against security review standards.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set
import uuid

from .types import (
    CodeReviewRiskLevel,
    ApprovalGateStatus,
    ChangeSensitivityFlag,
    SecureCodeReviewRequest,
    SecureReviewApprovalVerdict,
)


class SecureCodeReviewApprovalEngine:
    """Evaluates change sensitivity, manages review quorums, and gates high-risk deployments."""

    def __init__(self) -> None:
        self._requests: Dict[str, SecureCodeReviewRequest] = {}
        self._verdicts: Dict[str, List[SecureReviewApprovalVerdict]] = {}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _derive_risk_level(self, flags: List[ChangeSensitivityFlag]) -> CodeReviewRiskLevel:
        """Derive risk level based on sensitivity flags."""
        flag_set = set(flags)
        if ChangeSensitivityFlag.CRYPTO_CHANGE in flag_set or ChangeSensitivityFlag.IAM_PERMISSION in flag_set:
            return CodeReviewRiskLevel.CRITICAL
        if ChangeSensitivityFlag.AUTH_CHANGE in flag_set:
            return CodeReviewRiskLevel.HIGH
        if ChangeSensitivityFlag.DATABASE_DDL in flag_set or ChangeSensitivityFlag.DATA_PIPELINE in flag_set:
            return CodeReviewRiskLevel.MEDIUM
        return CodeReviewRiskLevel.LOW

    def submit_review_request(self, request: SecureCodeReviewRequest) -> str:
        """Submit a code change for security review."""
        if not request.request_id or not request.change_title or not request.author:
            raise ValueError("request_id, change_title, and author must not be empty")

        if not request.risk_level or request.risk_level == CodeReviewRiskLevel.LOW:
            request.risk_level = self._derive_risk_level(request.sensitivity_flags)

        if not request.submitted_at:
            request.submitted_at = self._now_iso()
        request.status = ApprovalGateStatus.PENDING

        self._requests[request.request_id] = request
        self._verdicts[request.request_id] = []
        return request.request_id

    def add_sensitivity_flag(self, request_id: str, flag: ChangeSensitivityFlag) -> SecureCodeReviewRequest:
        """Tag an additional sensitivity flag and adjust risk level if necessary."""
        if request_id not in self._requests:
            raise ValueError(f"Review request {request_id} not found")

        req = self._requests[request_id]
        if flag not in req.sensitivity_flags:
            req.sensitivity_flags.append(flag)
            req.risk_level = self._derive_risk_level(req.sensitivity_flags)
        return req

    def record_verdict(self, verdict: SecureReviewApprovalVerdict) -> SecureCodeReviewRequest:
        """Record an individual reviewer's verdict and update overall gate status."""
        if verdict.request_id not in self._requests:
            raise ValueError(f"Review request {verdict.request_id} not found")
        if not verdict.reviewer:
            raise ValueError("reviewer must not be empty")

        req = self._requests[verdict.request_id]
        if req.author == verdict.reviewer:
            raise ValueError("Author cannot approve their own secure code review request (SOD violation)")

        if not verdict.evaluated_at:
            verdict.evaluated_at = self._now_iso()

        self._verdicts[verdict.request_id].append(verdict)

        if verdict.decision == ApprovalGateStatus.REJECTED:
            req.status = ApprovalGateStatus.REJECTED
            return req

        if verdict.decision == ApprovalGateStatus.ESCALATED:
            req.status = ApprovalGateStatus.ESCALATED
            return req

        if verdict.decision == ApprovalGateStatus.APPROVED:
            if verdict.reviewer not in req.approvers:
                req.approvers.append(verdict.reviewer)

            # Check quorum requirements
            if req.risk_level == CodeReviewRiskLevel.CRITICAL:
                # CRITICAL requires at least 2 distinct approvers
                if len(req.approvers) >= 2:
                    req.status = ApprovalGateStatus.APPROVED
                else:
                    req.status = ApprovalGateStatus.PENDING
            elif req.risk_level == CodeReviewRiskLevel.HIGH:
                # HIGH requires at least 1 designated security approver
                if any("sec" in a.lower() or "lead" in a.lower() for a in req.approvers):
                    req.status = ApprovalGateStatus.APPROVED
                else:
                    req.status = ApprovalGateStatus.PENDING
            else:
                # LOW / MEDIUM requires 1 approver
                if len(req.approvers) >= 1:
                    req.status = ApprovalGateStatus.APPROVED

        return req

    def get_request(self, request_id: str) -> Optional[SecureCodeReviewRequest]:
        """Retrieve review request by ID."""
        return self._requests.get(request_id)

    def get_verdicts_for_request(self, request_id: str) -> List[SecureReviewApprovalVerdict]:
        """Get all verdicts recorded for a request."""
        return list(self._verdicts.get(request_id, []))

    def list_pending_reviews(
        self,
        risk_level: Optional[CodeReviewRiskLevel] = None,
    ) -> List[SecureCodeReviewRequest]:
        """List requests in PENDING status, optionally filtered by risk level."""
        results = [r for r in self._requests.values() if r.status == ApprovalGateStatus.PENDING]
        if risk_level is not None:
            results = [r for r in results if r.risk_level == risk_level]
        return results

    def get_review_governance_report(self) -> Dict[str, Any]:
        """Generate summary of code review approvals, risk levels, and gate metrics."""
        total = len(self._requests)
        by_status = {s.value: 0 for s in ApprovalGateStatus}
        by_risk = {r.value: 0 for r in CodeReviewRiskLevel}
        flag_counts: Dict[str, int] = {}

        for req in self._requests.values():
            by_status[req.status.value] = by_status.get(req.status.value, 0) + 1
            by_risk[req.risk_level.value] = by_risk.get(req.risk_level.value, 0) + 1
            for f in req.sensitivity_flags:
                flag_counts[f.value] = flag_counts.get(f.value, 0) + 1

        approved = by_status.get("approved", 0)
        return {
            "total_requests": total,
            "approved_count": approved,
            "approval_rate_pct": round((approved / total * 100.0), 2) if total > 0 else 0.0,
            "by_status": by_status,
            "by_risk_level": by_risk,
            "sensitivity_flag_distribution": flag_counts,
        }
