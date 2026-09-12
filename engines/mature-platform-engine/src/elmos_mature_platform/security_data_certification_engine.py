from typing import List, Dict, Optional
from datetime import datetime, timedelta

from elmos_mature_platform.types import (
    SecurityControl,
    SecurityControlStatus,
    DataClassification,
    DataProtectionLevel
)

class SecurityDataCertificationEngine:
    def __init__(self):
        self._controls: Dict[str, SecurityControl] = {}
        self._classifications: Dict[str, DataClassification] = {}

    def register_control(self, control: SecurityControl) -> str:
        """Register a security control in the engine."""
        self._controls[control.control_id] = control
        return control.control_id

    def verify_control(self, control_id: str, verifier: str, evidence_ids: List[str]) -> SecurityControl:
        """Verify a security control using evidence."""
        if control_id not in self._controls:
            raise ValueError(f"Control {control_id} not found.")
        if not evidence_ids:
            raise ValueError("Cannot verify without evidence.")

        control = self._controls[control_id]
        control.status = SecurityControlStatus.VERIFIED
        control.verified_by = verifier
        control.evidence_ids = list(evidence_ids)
        control.verified_at = datetime.utcnow().isoformat()
        control.last_tested = datetime.utcnow().isoformat()
        return control

    def fail_control(self, control_id: str, reason: str) -> SecurityControl:
        """Mark a control as failed and record the reason."""
        if control_id not in self._controls:
            raise ValueError(f"Control {control_id} not found.")

        control = self._controls[control_id]
        control.status = SecurityControlStatus.FAILED
        control.description = f"{control.description} | Failure Reason: {reason}".strip()
        return control

    def classify_data(self, classification: DataClassification) -> str:
        """Register a new data classification."""
        self._classifications[classification.classification_id] = classification
        return classification.classification_id

    def assess_data_compliance(self, classification_id: str) -> Dict:
        """
        Check data compliance based on encryption, retention, and cross-border rules:
        - CONFIDENTIAL+ must be encrypted at rest AND in transit
        - RESTRICTED+ cannot be cross_border without explicit approval
        - PCI/PHI data requires <= 365 day retention
        """
        if classification_id not in self._classifications:
            raise ValueError(f"Classification {classification_id} not found.")

        cls = self._classifications[classification_id]
        issues = []
        is_compliant = True

        # Rule 1: CONFIDENTIAL+ must be encrypted at rest and in transit
        if cls.protection_level in (DataProtectionLevel.CONFIDENTIAL, DataProtectionLevel.RESTRICTED, DataProtectionLevel.TOP_SECRET):
            if not cls.encrypted_at_rest or not cls.encrypted_in_transit:
                issues.append("CONFIDENTIAL+ data must be encrypted at rest and in transit.")
                is_compliant = False

        # Rule 2: RESTRICTED+ cannot be cross-border without explicit approval (default non-compliant)
        if cls.protection_level in (DataProtectionLevel.RESTRICTED, DataProtectionLevel.TOP_SECRET):
            if cls.cross_border:
                issues.append("RESTRICTED+ data cannot be cross_border without explicit approval.")
                is_compliant = False

        # Rule 3: PCI/PHI data requires <= 365 day retention
        if cls.data_type.upper() in ("PCI", "PHI"):
            if cls.retention_days > 365:
                issues.append("PCI/PHI data requires <= 365 day retention.")
                is_compliant = False

        cls.compliant = is_compliant

        return {
            "classification_id": classification_id,
            "compliant": is_compliant,
            "issues": issues
        }

    def get_framework_coverage(self, framework: str) -> Dict:
        """Get controls by status for a specific framework."""
        coverage = {status.value: 0 for status in SecurityControlStatus}
        controls = [c for c in self._controls.values() if c.framework == framework]
        
        for c in controls:
            coverage[c.status.value] += 1
            
        return {
            "framework": framework,
            "total_controls": len(controls),
            "status_counts": coverage
        }

    def get_unverified_controls(self) -> List[SecurityControl]:
        """Return a list of controls that are not VERIFIED."""
        return [c for c in self._controls.values() if c.status != SecurityControlStatus.VERIFIED]

    def get_overdue_controls(self, max_age_days: int = 0) -> List[SecurityControl]:
        """Return a list of controls past their test frequency."""
        overdue = []
        now = datetime.utcnow()
        for c in self._controls.values():
            if not c.last_tested:
                overdue.append(c)
                continue
                
            try:
                last_tested_date = datetime.fromisoformat(c.last_tested)
            except ValueError:
                # Fallback if invalid date
                overdue.append(c)
                continue

            limit = max_age_days if max_age_days > 0 else c.test_frequency_days
            if (now - last_tested_date).days > limit:
                overdue.append(c)
                
        return overdue

    def get_certification_readiness(self, framework: str) -> Dict:
        """Calculate % verified, identify gaps, blockers for a framework."""
        controls = [c for c in self._controls.values() if c.framework == framework]
        if not controls:
            return {
                "framework": framework,
                "percent_verified": 0.0,
                "gaps": [],
                "blockers": [],
                "ready": False
            }

        verified_count = sum(1 for c in controls if c.status == SecurityControlStatus.VERIFIED)
        percent_verified = (verified_count / len(controls)) * 100.0

        gaps = [c.control_id for c in controls if c.status not in (SecurityControlStatus.VERIFIED, SecurityControlStatus.FAILED)]
        blockers = [c.control_id for c in controls if c.status == SecurityControlStatus.FAILED]

        # Framework coverage requires ALL controls VERIFIED for certification
        ready = (verified_count == len(controls))

        return {
            "framework": framework,
            "percent_verified": percent_verified,
            "gaps": gaps,
            "blockers": blockers,
            "ready": ready
        }

    def get_data_protection_report(self) -> Dict:
        """Provide report by protection level, encryption coverage, cross-border."""
        report = {}
        for level in DataProtectionLevel:
            items = [c for c in self._classifications.values() if c.protection_level == level]
            total = len(items)
            encrypted = sum(1 for c in items if c.encrypted_at_rest and c.encrypted_in_transit)
            cross_border = sum(1 for c in items if c.cross_border)
            
            report[level.value] = {
                "total": total,
                "fully_encrypted": encrypted,
                "cross_border": cross_border
            }
            
        return report

    def get_security_posture(self) -> Dict:
        """Return overall security posture: controls by framework, coverage %, critical gaps."""
        frameworks = set(c.framework for c in self._controls.values())
        posture = {
            "frameworks": {},
            "critical_gaps": []
        }

        for fw in frameworks:
            fw_controls = [c for c in self._controls.values() if c.framework == fw]
            verified = sum(1 for c in fw_controls if c.status == SecurityControlStatus.VERIFIED)
            coverage = (verified / len(fw_controls)) * 100 if fw_controls else 0.0
            
            posture["frameworks"][fw] = {
                "total": len(fw_controls),
                "verified": verified,
                "coverage_percent": coverage
            }

        # Consider failed controls as critical gaps
        posture["critical_gaps"] = [c.control_id for c in self._controls.values() if c.status == SecurityControlStatus.FAILED]

        return posture
