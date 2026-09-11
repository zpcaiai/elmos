"""Secure SDLC and SSDF Governance Engine (Batch 40 - Skill 1370).

Implements NIST SP 800-218 Secure Software Development Framework (SSDF)
practice tracking, SDLC phase gating, compliance auditing, and attestation.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    SdlcStage,
    SecureSdlcAudit,
    SsdfPracticeGroup,
    SsdfPracticeTask,
    SsdfTaskStatus,
)


class SecureSdlcSsdfEngine:
    """Manages NIST SP 800-218 SSDF compliance practices and release audits."""

    def __init__(self, seed_defaults: bool = True) -> None:
        self._tasks: Dict[str, SsdfPracticeTask] = {}
        self._audits: Dict[str, SecureSdlcAudit] = {}
        if seed_defaults:
            self._seed_default_practices()

    def _seed_default_practices(self) -> None:
        defaults = [
            SsdfPracticeTask(
                task_id="ssdf-po-1-1",
                group=SsdfPracticeGroup.PREPARE_ORGANIZATION,
                practice_code="PO.1.1",
                title="Define security requirements for software development",
                applicable_sdlc_stages=[SdlcStage.REQUIREMENTS],
                mandatory=True,
            ),
            SsdfPracticeTask(
                task_id="ssdf-ps-1-1",
                group=SsdfPracticeGroup.PROTECT_SOFTWARE,
                practice_code="PS.1.1",
                title="Store and protect software components in immutable repository",
                applicable_sdlc_stages=[SdlcStage.CODING_IMPLEMENTATION],
                mandatory=True,
            ),
            SsdfPracticeTask(
                task_id="ssdf-pw-1-1",
                group=SsdfPracticeGroup.PRODUCE_SECURED_SOFTWARE,
                practice_code="PW.1.1",
                title="Design software architecture to meet security requirements",
                applicable_sdlc_stages=[SdlcStage.ARCHITECTURE_DESIGN],
                mandatory=True,
            ),
            SsdfPracticeTask(
                task_id="ssdf-pw-5-1",
                group=SsdfPracticeGroup.PRODUCE_SECURED_SOFTWARE,
                practice_code="PW.5.1",
                title="Review human-readable source code for vulnerabilities",
                applicable_sdlc_stages=[SdlcStage.TESTING_VERIFICATION],
                mandatory=True,
            ),
            SsdfPracticeTask(
                task_id="ssdf-rv-1-1",
                group=SsdfPracticeGroup.RESPOND_VULNERABILITIES,
                practice_code="RV.1.1",
                title="Identify and confirm vulnerabilities continuously",
                applicable_sdlc_stages=[SdlcStage.RELEASE_DEPLOYMENT, SdlcStage.MAINTENANCE],
                mandatory=True,
            ),
        ]
        for t in defaults:
            self._tasks[t.task_id] = t

    def register_practice_task(self, task: SsdfPracticeTask) -> str:
        """Register a new SSDF practice task."""
        if not task.task_id:
            task.task_id = f"ssdf-task-{uuid.uuid4().hex[:8]}"
        self._tasks[task.task_id] = task
        return task.task_id

    def update_task_status(
        self,
        task_id: str,
        status: SsdfTaskStatus,
        evidence_ref: str = "",
        auditor: str = "",
    ) -> SsdfPracticeTask:
        """Update practice task status and attach evidence."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        task.status = status
        task.last_audited = datetime.now(timezone.utc).isoformat()
        if auditor:
            task.auditor = auditor
        if evidence_ref:
            task.evidence_artifacts.append(evidence_ref)
        return task

    def record_deficiency(self, task_id: str, deficiency: str) -> SsdfPracticeTask:
        """Record an audit deficiency against a practice task."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        task.deficiencies.append(deficiency)
        task.status = SsdfTaskStatus.AUDIT_FAILED
        return task

    def create_audit(
        self,
        repository_name: str,
        release_version: str,
        task_ids: Optional[List[str]] = None,
    ) -> SecureSdlcAudit:
        """Create a release compliance audit with associated tasks."""
        if not repository_name or not release_version:
            raise ValueError("repository_name and release_version are required")

        audit_id = f"ssdf-audit-{uuid.uuid4().hex[:8]}"
        if task_ids is not None:
            tasks = [self._tasks[tid] for tid in task_ids if tid in self._tasks]
        else:
            tasks = list(self._tasks.values())

        audit = SecureSdlcAudit(
            audit_id=audit_id,
            repository_name=repository_name,
            release_version=release_version,
            tasks=tasks,
            audited_at=datetime.now(timezone.utc).isoformat(),
        )
        self._audits[audit_id] = audit
        return audit

    def evaluate_audit_compliance(self, audit_id: str) -> SecureSdlcAudit:
        """Evaluate compliance score and determine whether release is certified."""
        audit = self._audits.get(audit_id)
        if not audit:
            raise ValueError(f"Audit not found: {audit_id}")

        if not audit.tasks:
            audit.compliance_score = 0.0
            audit.is_certified = False
            audit.blocking_findings = ["No SSDF tasks assigned to audit"]
            return audit

        satisfied_count = sum(
            1
            for t in audit.tasks
            if t.status in (SsdfTaskStatus.SATISFIED, SsdfTaskStatus.EXEMPTION_GRANTED)
        )
        audit.compliance_score = round((satisfied_count / len(audit.tasks)) * 100.0, 2)

        blocking = []
        for t in audit.tasks:
            if t.mandatory and t.status in (SsdfTaskStatus.AUDIT_FAILED, SsdfTaskStatus.NOT_IMPLEMENTED):
                blocking.append(f"Mandatory practice {t.practice_code} ({t.title}) is {t.status.value}")

        audit.blocking_findings = blocking
        audit.is_certified = (audit.compliance_score >= 80.0 and len(blocking) == 0)
        return audit

    def get_group_compliance_breakdown(self, audit_id: str) -> Dict[str, Any]:
        """Return compliance statistics grouped by SSDF practice group."""
        audit = self._audits.get(audit_id)
        if not audit:
            raise ValueError(f"Audit not found: {audit_id}")

        breakdown: Dict[str, Dict[str, Any]] = {}
        for group in SsdfPracticeGroup:
            group_tasks = [t for t in audit.tasks if t.group == group]
            total = len(group_tasks)
            satisfied = sum(
                1
                for t in group_tasks
                if t.status in (SsdfTaskStatus.SATISFIED, SsdfTaskStatus.EXEMPTION_GRANTED)
            )
            rate = round((satisfied / total) * 100.0, 1) if total > 0 else 100.0
            breakdown[group.value] = {
                "total": total,
                "satisfied": satisfied,
                "compliance_rate": rate,
            }
        return breakdown

    def get_stage_requirements(self, stage: SdlcStage) -> List[SsdfPracticeTask]:
        """Return all registered practice tasks applicable to a given SDLC stage."""
        return [t for t in self._tasks.values() if stage in t.applicable_sdlc_stages]

    def export_ssdf_attestation(self, audit_id: str) -> Dict[str, Any]:
        """Export a formal NIST SP 800-218 attestation package."""
        audit = self.evaluate_audit_compliance(audit_id)
        return {
            "standard": "NIST SP 800-218 (SSDF v1.1)",
            "audit_id": audit.audit_id,
            "repository": audit.repository_name,
            "release_version": audit.release_version,
            "certified": audit.is_certified,
            "compliance_score": audit.compliance_score,
            "evaluated_at": audit.audited_at,
            "blocking_findings_count": len(audit.blocking_findings),
            "task_attestations": [
                {
                    "practice_code": t.practice_code,
                    "title": t.title,
                    "status": t.status.value,
                    "evidence_count": len(t.evidence_artifacts),
                }
                for t in audit.tasks
            ],
        }

    def get_critical_deficiencies(self) -> List[Dict[str, Any]]:
        """Return deficiencies recorded against mandatory practices."""
        deficiencies = []
        for t in self._tasks.values():
            if t.mandatory and t.deficiencies:
                deficiencies.append({
                    "task_id": t.task_id,
                    "practice_code": t.practice_code,
                    "title": t.title,
                    "deficiencies": t.deficiencies,
                })
        return deficiencies

    def get_overall_ssdf_report(self) -> Dict[str, Any]:
        """Summarize all tasks, audits, and certification metrics across the engine."""
        total_audits = len(self._audits)
        certified_audits = sum(1 for a in self._audits.values() if a.is_certified)
        return {
            "total_registered_tasks": len(self._tasks),
            "total_audits": total_audits,
            "certified_audits": certified_audits,
            "audit_certification_rate": (
                round(certified_audits / total_audits, 4) if total_audits > 0 else 0.0
            ),
        }
