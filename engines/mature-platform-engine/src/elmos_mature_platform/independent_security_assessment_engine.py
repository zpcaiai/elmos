"""Independent Security Assessment Engine (Batch 40 - Skill 1391).

Coordinates external pen tests, accredited third-party code audits,
red team exercises, findings tracking, remediation verification, and gate sign-off.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    AssessmentStatus,
    AssessmentType,
    AssessorType,
    IndependentAssessmentRecord,
    IndependentAuditFinding,
)


class IndependentSecurityAssessmentEngine:
    """Industrial engine for independent security assessments and code audits (B40)."""

    def __init__(self):
        self._assessments: Dict[str, IndependentAssessmentRecord] = {}
        self._findings: Dict[str, IndependentAuditFinding] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def initiate_assessment(self, record: IndependentAssessmentRecord) -> str:
        """Initiate and scope a new third-party security assessment."""
        if not record.assessment_id:
            record.assessment_id = f"sec-eval-{uuid.uuid4().hex[:8]}"
        if not record.started_at:
            record.started_at = datetime.now(timezone.utc).isoformat()
        record.status = AssessmentStatus.SCOPING
        record.total_findings = 0
        record.open_blockers = 0
        record.passed_gate = False

        self._assessments[record.assessment_id] = record
        self._record_audit("initiate_assessment", record.assessment_id, {
            "firm": record.assessor_firm,
            "type": record.assessment_type.value,
            "target": record.target_release,
        })
        return record.assessment_id

    def record_finding(self, finding: IndependentAuditFinding) -> str:
        """Log a new security finding identified by the independent assessor."""
        assessment = self._get_assessment_or_raise(finding.assessment_id)
        if not finding.finding_id:
            finding.finding_id = f"fnd-{uuid.uuid4().hex[:6]}"
        finding.verified_closed = False

        self._findings[finding.finding_id] = finding
        assessment.findings.append(finding)
        assessment.total_findings = len(assessment.findings)

        if finding.severity.lower() in ("critical", "high"):
            assessment.open_blockers += 1

        self._record_audit("record_finding", finding.assessment_id, {
            "finding_id": finding.finding_id,
            "severity": finding.severity,
            "cwe": finding.cwe_id,
        })
        return finding.finding_id

    def remediate_finding(self, finding_id: str, notes: str) -> IndependentAuditFinding:
        """Mark finding as remediated by engineering team, pending assessor re-test."""
        finding = self._get_finding_or_raise(finding_id)
        finding.remediation_notes = notes
        self._record_audit("remediate_finding", finding.assessment_id, {"finding_id": finding_id})
        return finding

    def verify_finding_closure(self, finding_id: str, verifier: str) -> IndependentAuditFinding:
        """Assessor re-tests and confirms closure of finding."""
        finding = self._get_finding_or_raise(finding_id)
        if not finding.verified_closed:
            finding.verified_closed = True
            finding.closed_at = datetime.now(timezone.utc).isoformat()
            finding.verified_by = verifier

            assessment = self._assessments.get(finding.assessment_id)
            if assessment and finding.severity.lower() in ("critical", "high"):
                assessment.open_blockers = max(0, assessment.open_blockers - 1)

        self._record_audit("verify_closure", finding.assessment_id, {
            "finding_id": finding_id,
            "verifier": verifier,
        })
        return finding

    def conclude_assessment(
        self,
        assessment_id: str,
        sign_off_attestation: str,
        lead_assessor: str,
    ) -> IndependentAssessmentRecord:
        """Conclude assessment and determine gate pass/fail status."""
        assessment = self._get_assessment_or_raise(assessment_id)

        # Fail-closed rule: any open critical or high finding blocks certification
        open_critical_high = sum(
            1 for f in assessment.findings
            if not f.verified_closed and f.severity.lower() in ("critical", "high")
        )

        assessment.open_blockers = open_critical_high
        assessment.completed_at = datetime.now(timezone.utc).isoformat()
        assessment.sign_off_attestation = sign_off_attestation

        if open_critical_high == 0:
            assessment.status = AssessmentStatus.CERTIFIED_CLOSED
            assessment.passed_gate = True
        else:
            assessment.status = AssessmentStatus.REMEDIATION
            assessment.passed_gate = False

        self._record_audit("conclude_assessment", assessment_id, {
            "passed_gate": assessment.passed_gate,
            "open_blockers": open_critical_high,
            "lead_assessor": lead_assessor,
        })
        return assessment

    def get_assessment_report(self, assessment_id: str) -> Dict[str, Any]:
        """Produce structured security assessment compliance report."""
        assessment = self._get_assessment_or_raise(assessment_id)
        severity_counts: Dict[str, int] = {}
        closed_count = sum(1 for f in assessment.findings if f.verified_closed)

        for f in assessment.findings:
            sev = f.severity.lower()
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        return {
            "assessment_id": assessment.assessment_id,
            "target_release": assessment.target_release,
            "type": assessment.assessment_type.value,
            "assessor_firm": assessment.assessor_firm,
            "status": assessment.status.value,
            "total_findings": assessment.total_findings,
            "closed_findings": closed_count,
            "open_blockers": assessment.open_blockers,
            "passed_gate": assessment.passed_gate,
            "severity_breakdown": severity_counts,
            "sign_off_attestation": assessment.sign_off_attestation,
        }

    def _get_assessment_or_raise(self, assessment_id: str) -> IndependentAssessmentRecord:
        if assessment_id not in self._assessments:
            raise ValueError(f"Assessment {assessment_id} not found")
        return self._assessments[assessment_id]

    def _get_finding_or_raise(self, finding_id: str) -> IndependentAuditFinding:
        if finding_id not in self._findings:
            raise ValueError(f"Finding {finding_id} not found")
        return self._findings[finding_id]

    def _record_audit(self, action: str, target: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })
