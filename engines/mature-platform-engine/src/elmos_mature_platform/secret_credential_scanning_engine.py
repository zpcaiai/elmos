from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
import math

from .types import (
    SecretType,
    SecretFindingStatus,
    SecretScanFinding,
    SecretScanPolicy
)

class SecretCredentialScanningEngine:
    """
    Engine for scanning, reporting, and evaluating secrets and credentials.
    """
    def __init__(self) -> None:
        self.policies: Dict[str, SecretScanPolicy] = {}
        self.findings: Dict[str, SecretScanFinding] = {}

    def create_policy(self, policy: SecretScanPolicy) -> None:
        """Create a new scan policy."""
        self.policies[policy.policy_id] = policy

    def report_finding(self, finding: SecretScanFinding) -> str:
        """Report a new secret finding."""
        if not finding.detected_at:
            finding.detected_at = datetime.now(timezone.utc).isoformat()
        self.findings[finding.finding_id] = finding
        return finding.finding_id

    def get_findings(
        self, 
        status: Optional[SecretFindingStatus] = None, 
        secret_type: Optional[SecretType] = None
    ) -> List[SecretScanFinding]:
        """Get filtered findings based on status and secret type."""
        results = list(self.findings.values())
        if status:
            results = [f for f in results if f.status == status]
        if secret_type:
            results = [f for f in results if f.secret_type == secret_type]
        return results

    def mark_rotated(self, finding_id: str) -> SecretScanFinding:
        """Mark a secret finding as rotated."""
        if finding_id not in self.findings:
            raise ValueError(f"Finding {finding_id} not found")
        finding = self.findings[finding_id]
        finding.status = SecretFindingStatus.ROTATED
        finding.rotated_at = datetime.now(timezone.utc).isoformat()
        return finding

    def mark_revoked(self, finding_id: str) -> SecretScanFinding:
        """Mark a secret finding as revoked."""
        if finding_id not in self.findings:
            raise ValueError(f"Finding {finding_id} not found")
        finding = self.findings[finding_id]
        finding.status = SecretFindingStatus.REVOKED
        return finding

    def mark_false_positive(self, finding_id: str, reason: str) -> SecretScanFinding:
        """Mark a secret finding as a false positive."""
        if finding_id not in self.findings:
            raise ValueError(f"Finding {finding_id} not found")
        finding = self.findings[finding_id]
        finding.status = SecretFindingStatus.FALSE_POSITIVE
        # We could store the reason in a field if we had one
        return finding

    def evaluate_policy(self, policy_id: str) -> Dict[str, Any]:
        """Evaluate findings against a specific policy."""
        if policy_id not in self.policies:
            raise ValueError(f"Policy {policy_id} not found")
        
        policy = self.policies[policy_id]
        
        # Filter findings that apply to this policy (not excluded)
        applicable_findings = []
        for f in self.findings.values():
            if f.file_path in policy.excluded_paths:
                continue
            if f.secret_type in policy.excluded_types:
                continue
            applicable_findings.append(f)
            
        active_findings = [f for f in applicable_findings if f.status == SecretFindingStatus.ACTIVE]
        
        passed = True
        violations = []
        
        if policy.block_on_active_secrets and len(active_findings) > 0:
            passed = False
            violations.append("Active secrets found")
            
        if len(applicable_findings) > policy.max_allowed_findings:
            passed = False
            violations.append(f"Total findings ({len(applicable_findings)}) exceeds max allowed ({policy.max_allowed_findings})")
            
        return {
            "policy_id": policy_id,
            "passed": passed,
            "violations": violations,
            "applicable_findings_count": len(applicable_findings),
            "active_findings_count": len(active_findings)
        }

    def get_overdue_rotations(self, policy_id: str, current_time: str) -> List[SecretScanFinding]:
        """Get findings that need rotation based on policy."""
        if policy_id not in self.policies:
            raise ValueError(f"Policy {policy_id} not found")
            
        policy = self.policies[policy_id]
        current_dt = datetime.fromisoformat(current_time)
        
        overdue = []
        for f in self.findings.values():
            if f.status != SecretFindingStatus.ACTIVE:
                continue
            if not f.detected_at:
                continue
                
            detected_dt = datetime.fromisoformat(f.detected_at)
            delta_hours = (current_dt - detected_dt).total_seconds() / 3600
            
            if delta_hours > policy.require_rotation_within_hours:
                overdue.append(f)
                
        return overdue

    def get_findings_by_author(self, author: str) -> List[SecretScanFinding]:
        """Get all findings associated with a specific author."""
        return [f for f in self.findings.values() if f.author == author]

    def compute_entropy(self, value: str) -> float:
        """Calculate Shannon entropy for a given string."""
        if not value:
            return 0.0
            
        entropy = 0.0
        length = len(value)
        counts = {}
        for char in value:
            counts[char] = counts.get(char, 0) + 1
            
        for count in counts.values():
            probability = count / length
            entropy -= probability * math.log2(probability)
            
        return entropy

    def get_scanning_report(self) -> Dict[str, Any]:
        """Generate a summary report of all scanning findings."""
        report: Dict[str, Any] = {
            "total_findings": len(self.findings),
            "by_type": {},
            "by_status": {},
            "by_severity": {}
        }
        
        for f in self.findings.values():
            report["by_type"][f.secret_type.value] = report["by_type"].get(f.secret_type.value, 0) + 1
            report["by_status"][f.status.value] = report["by_status"].get(f.status.value, 0) + 1
            report["by_severity"][f.severity] = report["by_severity"].get(f.severity, 0) + 1
            
        return report
