from typing import List, Dict, Optional
from datetime import datetime

from elmos_mature_platform.types import (
    SastSeverity,
    SastCategory,
    SastFindingState,
    SastFinding,
    SastScanRun,
    SastPolicy
)

class SastIntegrationEngine:
    """
    Engine for managing Static Application Security Testing (SAST) integration,
    handling policies, scans, findings, and evaluation.
    """
    def __init__(self):
        self._policies: Dict[str, SastPolicy] = {}
        self._scans: Dict[str, SastScanRun] = {}
        self._findings_by_scan: Dict[str, Dict[str, SastFinding]] = {}
        self._findings_global: Dict[str, SastFinding] = {}
    
    def create_policy(self, policy: SastPolicy) -> None:
        """Create a SAST policy."""
        self._policies[policy.policy_id] = policy
        
    def start_scan(self, scan: SastScanRun) -> str:
        """Start a new SAST scan run."""
        self._scans[scan.scan_id] = scan
        self._findings_by_scan[scan.scan_id] = {}
        return scan.scan_id
        
    def add_finding(self, finding: SastFinding, scan_id: str) -> None:
        """Add a finding to a specific scan run."""
        if scan_id not in self._scans:
            raise ValueError(f"Scan {scan_id} not found.")
        self._findings_by_scan[scan_id][finding.finding_id] = finding
        self._findings_global[finding.finding_id] = finding
        
    def complete_scan(self, scan_id: str) -> SastScanRun:
        """Complete a scan, tallying up findings."""
        if scan_id not in self._scans:
            raise ValueError(f"Scan {scan_id} not found.")
        
        scan = self._scans[scan_id]
        findings = self._findings_by_scan[scan_id].values()
        
        scan.total_findings = len(findings)
        scan.critical_count = sum(1 for f in findings if f.severity == SastSeverity.CRITICAL)
        scan.high_count = sum(1 for f in findings if f.severity == SastSeverity.HIGH)
        scan.completed_at = datetime.utcnow().isoformat()
        
        return scan
        
    def evaluate_policy(self, scan_id: str, policy_id: str) -> Dict:
        """Evaluate a completed scan against a policy."""
        if scan_id not in self._scans:
            raise ValueError(f"Scan {scan_id} not found.")
        if policy_id not in self._policies:
            raise ValueError(f"Policy {policy_id} not found.")
            
        scan = self._scans[scan_id]
        policy = self._policies[policy_id]
        
        passed = True
        violations = []
        
        if scan.critical_count > policy.max_critical:
            passed = False
            violations.append(f"Critical count {scan.critical_count} exceeds maximum {policy.max_critical}.")
            
        if scan.high_count > policy.max_high:
            passed = False
            violations.append(f"High count {scan.high_count} exceeds maximum {policy.max_high}.")
            
        findings = self._findings_by_scan.get(scan_id, {}).values()
        if policy.require_cwe_mapping:
            without_cwe = [f for f in findings if not f.cwe_id]
            if without_cwe:
                passed = False
                violations.append(f"{len(without_cwe)} findings missing CWE mapping.")
                
        return {
            "passed": passed,
            "violations": violations
        }
        
    def triage_finding(self, finding_id: str, new_state: SastFindingState, reason: str) -> SastFinding:
        """Update the state of a finding."""
        if finding_id not in self._findings_global:
            raise ValueError(f"Finding {finding_id} not found.")
            
        finding = self._findings_global[finding_id]
        finding.state = new_state
        if new_state == SastFindingState.FIXED:
            finding.resolved_at = datetime.utcnow().isoformat()
        return finding
        
    def get_findings(self, scan_id: str, severity: Optional[SastSeverity] = None, category: Optional[SastCategory] = None) -> List[SastFinding]:
        """Get findings for a scan, optionally filtered."""
        if scan_id not in self._scans:
            raise ValueError(f"Scan {scan_id} not found.")
            
        findings = list(self._findings_by_scan[scan_id].values())
        if severity:
            findings = [f for f in findings if f.severity == severity]
        if category:
            findings = [f for f in findings if f.category == category]
            
        return findings
        
    def get_trend(self, project_name: str) -> Dict:
        """Get finding trends across scans for a project."""
        project_scans = [s for s in self._scans.values() if s.project_name == project_name]
        project_scans.sort(key=lambda s: s.started_at or "")
        
        trend = []
        for scan in project_scans:
            trend.append({
                "scan_id": scan.scan_id,
                "total": scan.total_findings,
                "critical": scan.critical_count,
                "high": scan.high_count
            })
            
        return {"project": project_name, "trend": trend}
        
    def get_top_categories(self) -> Dict:
        """Get most common finding categories across all scans."""
        counts = {}
        for finding in self._findings_global.values():
            cat = finding.category.value
            counts[cat] = counts.get(cat, 0) + 1
            
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
        
    def get_fix_rate(self) -> Dict:
        """Get ratio of fixed vs total findings."""
        total = len(self._findings_global)
        if total == 0:
            return {"total": 0, "fixed": 0, "rate": 0.0}
            
        fixed = sum(1 for f in self._findings_global.values() if f.state == SastFindingState.FIXED)
        return {
            "total": total,
            "fixed": fixed,
            "rate": fixed / total
        }
        
    def get_scanning_report(self, scan_id: str) -> Dict:
        """Generate a summary report for a scan."""
        if scan_id not in self._scans:
            raise ValueError(f"Scan {scan_id} not found.")
            
        scan = self._scans[scan_id]
        findings = list(self._findings_by_scan[scan_id].values())
        
        severities = {s.value: 0 for s in SastSeverity}
        categories = {c.value: 0 for c in SastCategory}
        
        for f in findings:
            severities[f.severity.value] += 1
            categories[f.category.value] += 1
            
        return {
            "scan_id": scan.scan_id,
            "project": scan.project_name,
            "total_findings": scan.total_findings,
            "severities": severities,
            "categories": categories,
            "duration_secs": 0 # simplified
        }
