from typing import Dict, List, Optional
import hashlib
import datetime
import uuid
from elmos_mature_platform.types import (
    ComplianceFramework,
    ControlStatus,
    ComplianceControl,
    AuditEvidence,
    AuditFinding,
    ComplianceReport
)

class ComplianceAuditEngine:
    def __init__(self):
        self._controls: Dict[str, ComplianceControl] = {}
        self._evidence: Dict[str, AuditEvidence] = {}
        self._findings: Dict[str, AuditFinding] = {}

    def register_control(self, control: ComplianceControl) -> None:
        """Register a new compliance control."""
        self._controls[control.control_id] = control

    def attach_evidence(self, evidence: AuditEvidence) -> None:
        """Attach evidence to a specific control."""
        if evidence.control_id not in self._controls:
            raise ValueError(f"Control {evidence.control_id} does not exist.")
        self._evidence[evidence.evidence_id] = evidence
        control = self._controls[evidence.control_id]
        if evidence.evidence_id not in control.evidence_ids:
            control.evidence_ids.append(evidence.evidence_id)

    def record_finding(self, finding: AuditFinding) -> None:
        """Record an audit finding for a control."""
        if finding.control_id not in self._controls:
            raise ValueError(f"Control {finding.control_id} does not exist.")
        self._findings[finding.finding_id] = finding

    def update_finding_status(self, finding_id: str, new_status: str) -> None:
        """Update the status of an existing finding."""
        if finding_id not in self._findings:
            raise ValueError(f"Finding {finding_id} does not exist.")
        self._findings[finding_id].status = new_status

    def assess_control(self, control_id: str) -> ComplianceControl:
        """Re-assess a control based on its evidence and findings."""
        if control_id not in self._controls:
            raise ValueError(f"Control {control_id} does not exist.")
            
        control = self._controls[control_id]
        
        # Check findings
        control_findings = [f for f in self._findings.values() if f.control_id == control_id and f.status != "remediated" and f.status != "accepted_risk"]
        has_failed_finding = any(f.severity in ["critical", "high"] for f in control_findings)
        
        if has_failed_finding:
            control.status = ControlStatus.FAILED
        elif control.status == ControlStatus.IMPLEMENTED and not control.evidence_ids:
            # An implemented control must have evidence
            control.status = ControlStatus.PARTIALLY_IMPLEMENTED
        
        # A control with no critical/high findings but missing evidence might be PARTIALLY_IMPLEMENTED
        control.last_assessed = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return control

    def generate_compliance_report(self, framework: ComplianceFramework) -> ComplianceReport:
        """Generate a comprehensive compliance report for a specific framework."""
        report = ComplianceReport(
            report_id=str(uuid.uuid4()),
            framework=framework,
            assessment_date=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
        
        framework_controls = [c for c in self._controls.values() if c.framework == framework]
        report.total_controls = len(framework_controls)
        
        for control in framework_controls:
            # Reassess just in case
            self.assess_control(control.control_id)
            if control.status == ControlStatus.IMPLEMENTED:
                report.implemented += 1
            elif control.status == ControlStatus.PARTIALLY_IMPLEMENTED:
                report.partially_implemented += 1
            elif control.status == ControlStatus.FAILED:
                report.failed += 1
            elif control.status == ControlStatus.NOT_APPLICABLE:
                report.not_applicable += 1
                
        applicable_controls = report.total_controls - report.not_applicable
        if applicable_controls > 0:
            report.coverage_pct = report.implemented / applicable_controls * 100.0
            
        report.findings = [f for f in self._findings.values() if f.control_id in [c.control_id for c in framework_controls]]
        
        return report

    def get_control_gaps(self, framework: ComplianceFramework) -> List[ComplianceControl]:
        """Return controls that are not fully implemented."""
        return [
            c for c in self._controls.values() 
            if c.framework == framework and c.status not in (ControlStatus.IMPLEMENTED, ControlStatus.NOT_APPLICABLE)
        ]

    def crosswalk_frameworks(self, source: ComplianceFramework, target: ComplianceFramework, mapping: Dict[str, str]) -> List[Dict]:
        """Map controls from a source framework to a target framework."""
        results = []
        for source_id, target_id in mapping.items():
            if source_id in self._controls:
                results.append({
                    "source_control": self._controls[source_id],
                    "target_control_id": target_id,
                    "target_framework": target
                })
        return results

    def export_audit_package(self, framework: ComplianceFramework) -> Dict:
        """Export all controls, evidence, and findings for an auditor."""
        controls = [c for c in self._controls.values() if c.framework == framework]
        control_ids = {c.control_id for c in controls}
        
        evidence = [e for e in self._evidence.values() if e.control_id in control_ids]
        findings = [f for f in self._findings.values() if f.control_id in control_ids]
        
        return {
            "framework": framework,
            "export_date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "controls": controls,
            "evidence": evidence,
            "findings": findings
        }

    def get_overdue_findings(self) -> List[AuditFinding]:
        """Get findings that are past their due date and not resolved."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return [
            f for f in self._findings.values() 
            if f.status in ("open", "in_progress") and f.due_date and f.due_date < now
        ]

    def compute_compliance_score(self, framework: ComplianceFramework) -> float:
        """Calculate weighted compliance percentage."""
        framework_controls = [c for c in self._controls.values() if c.framework == framework]
        if not framework_controls:
            return 0.0
            
        applicable_controls = [c for c in framework_controls if c.status != ControlStatus.NOT_APPLICABLE]
        if not applicable_controls:
            return 100.0
            
        implemented_count = sum(1 for c in applicable_controls if c.status == ControlStatus.IMPLEMENTED)
        return (implemented_count / len(applicable_controls)) * 100.0

    def validate_evidence_integrity(self, evidence_id: str, content: bytes) -> bool:
        """Verify the evidence content hash matches the recorded hash."""
        if evidence_id not in self._evidence:
            raise ValueError(f"Evidence {evidence_id} does not exist.")
            
        evidence = self._evidence[evidence_id]
        computed_hash = hashlib.sha256(content).hexdigest()
        return computed_hash == evidence.content_hash
