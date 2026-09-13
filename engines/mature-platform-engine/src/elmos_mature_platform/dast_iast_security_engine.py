from typing import Dict, List, Optional
from datetime import datetime, timedelta

from .types import (
    SecurityScanType,
    FindingSeverity,
    FindingStatus,
    SecurityScan,
    SecurityFinding,
    SecurityPolicy
)

class DastIastSecurityEngine:
    def __init__(self):
        self.policies: Dict[str, SecurityPolicy] = {}
        self.scans: Dict[str, SecurityScan] = {}
        self.findings: Dict[str, SecurityFinding] = {}

    def create_policy(self, policy: SecurityPolicy) -> None:
        """Create a new security policy."""
        self.policies[policy.policy_id] = policy

    def start_scan(self, scan: SecurityScan) -> str:
        """Start a new security scan."""
        scan.started_at = datetime.utcnow().isoformat()
        self.scans[scan.scan_id] = scan
        return scan.scan_id

    def complete_scan(self, scan_id: str, duration: float) -> SecurityScan:
        """Mark a scan as completed and update its findings count."""
        if scan_id not in self.scans:
            raise ValueError(f"Scan {scan_id} not found")
        scan = self.scans[scan_id]
        scan.completed_at = datetime.utcnow().isoformat()
        scan.duration_seconds = duration
        
        # Calculate findings count
        count = sum(1 for f in self.findings.values() if f.scan_id == scan_id)
        scan.findings_count = count
        return scan

    def add_finding(self, finding: SecurityFinding) -> None:
        """Add a finding from a scan, applying SLA deadlines based on policy if available."""
        if finding.scan_id in self.scans:
            scan = self.scans[finding.scan_id]
            if scan.policy_id in self.policies:
                policy = self.policies[scan.policy_id]
                first_seen = datetime.fromisoformat(finding.first_seen) if finding.first_seen else datetime.utcnow()
                
                hours = 0
                if finding.severity == FindingSeverity.CRITICAL:
                    hours = policy.sla_critical_hours
                elif finding.severity == FindingSeverity.HIGH:
                    hours = policy.sla_high_hours
                elif finding.severity == FindingSeverity.MEDIUM:
                    hours = policy.sla_medium_hours
                
                if hours > 0:
                    deadline = first_seen + timedelta(hours=hours)
                    finding.sla_deadline = deadline.isoformat()
        
        self.findings[finding.finding_id] = finding

    def triage_finding(self, finding_id: str, status: FindingStatus, reason: str) -> SecurityFinding:
        """Triage an existing finding by updating its status and potentially providing a false positive reason."""
        if finding_id not in self.findings:
            raise ValueError(f"Finding {finding_id} not found")
        finding = self.findings[finding_id]
        finding.status = status
        if status == FindingStatus.FALSE_POSITIVE:
            finding.false_positive_reason = reason
        return finding

    def evaluate_gate(self, policy_id: str) -> Dict:
        """Evaluate current findings against a security policy to determine if a gate passes or fails."""
        if policy_id not in self.policies:
            raise ValueError(f"Policy {policy_id} not found")
        policy = self.policies[policy_id]
        
        # Collect relevant scans for this policy
        relevant_scan_ids = {s.scan_id for s in self.scans.values() if s.policy_id == policy_id}
        
        # Collect findings from relevant scans that are active (not remediated/false_positive/accepted_risk)
        active_findings = [f for f in self.findings.values() 
                           if f.scan_id in relevant_scan_ids and 
                           f.status not in (FindingStatus.REMEDIATED, FindingStatus.FALSE_POSITIVE, FindingStatus.ACCEPTED_RISK)]
        
        critical_count = sum(1 for f in active_findings if f.severity == FindingSeverity.CRITICAL)
        high_count = sum(1 for f in active_findings if f.severity == FindingSeverity.HIGH)
        
        violations = []
        if critical_count > policy.max_critical:
            violations.append(f"Critical findings ({critical_count}) exceed maximum allowed ({policy.max_critical})")
        if high_count > policy.max_high:
            violations.append(f"High findings ({high_count}) exceed maximum allowed ({policy.max_high})")
            
        if policy.block_on_critical and critical_count > 0:
            if not any("exceed maximum allowed" in v and "Critical" in v for v in violations):
                violations.append("Blocking on critical findings")
                
        # Check required scan types
        scan_types_run = {s.scan_type.value for s in self.scans.values() if s.policy_id == policy_id and s.completed_at}
        for req_type in policy.require_scan_types:
            if req_type not in scan_types_run:
                violations.append(f"Required scan type '{req_type}' has not been completed")

        return {
            "pass": len(violations) == 0,
            "violations": violations,
            "critical_count": critical_count,
            "high_count": high_count
        }

    def get_findings(self, scan_id: Optional[str] = None, severity: Optional[FindingSeverity] = None, status: Optional[FindingStatus] = None) -> List[SecurityFinding]:
        """Filter and retrieve findings based on provided criteria."""
        results = list(self.findings.values())
        if scan_id:
            results = [f for f in results if f.scan_id == scan_id]
        if severity:
            results = [f for f in results if f.severity == severity]
        if status:
            results = [f for f in results if f.status == status]
        return results

    def get_sla_violations(self, current_time: str) -> List[SecurityFinding]:
        """Retrieve findings that are active and have breached their SLA deadline."""
        current_dt = datetime.fromisoformat(current_time)
        violations = []
        for finding in self.findings.values():
            if finding.status not in (FindingStatus.REMEDIATED, FindingStatus.FALSE_POSITIVE, FindingStatus.ACCEPTED_RISK):
                if finding.sla_deadline:
                    deadline_dt = datetime.fromisoformat(finding.sla_deadline)
                    if current_dt > deadline_dt:
                        violations.append(finding)
        return violations

    def get_finding_trends(self) -> Dict:
        """Generate trends of new vs remediated findings over time."""
        # Simple trend mapping: counts per day based on first_seen and last_seen/remediation
        new_by_date = {}
        remediated_by_date = {}
        
        for f in self.findings.values():
            if f.first_seen:
                date = f.first_seen[:10]
                new_by_date[date] = new_by_date.get(date, 0) + 1
            if f.status == FindingStatus.REMEDIATED and f.last_seen:
                date = f.last_seen[:10]
                remediated_by_date[date] = remediated_by_date.get(date, 0) + 1
                
        dates = sorted(list(set(new_by_date.keys()) | set(remediated_by_date.keys())))
        trends = {
            "dates": dates,
            "new": [new_by_date.get(d, 0) for d in dates],
            "remediated": [remediated_by_date.get(d, 0) for d in dates]
        }
        return trends

    def get_scan_history(self, scan_type: Optional[SecurityScanType] = None) -> List[SecurityScan]:
        """Retrieve history of scans, optionally filtered by scan type."""
        history = list(self.scans.values())
        if scan_type:
            history = [s for s in history if s.scan_type == scan_type]
        # Sort by started_at descending
        history.sort(key=lambda x: x.started_at or "", reverse=True)
        return history

    def deduplicate_findings(self) -> int:
        """Find and merge duplicate findings (same cwe_id + location). Return the count merged."""
        grouped = {}
        merged_count = 0
        to_delete = []
        
        # Sort to ensure predictable deduplication (keep older ones)
        sorted_findings = sorted(self.findings.values(), key=lambda x: x.first_seen or x.finding_id)
        
        for f in sorted_findings:
            key = (f.cwe_id, f.location)
            if key not in grouped:
                grouped[key] = f
            else:
                existing = grouped[key]
                # Merge logic: if either is not remediated/false_positive/accepted_risk, keep it active
                # Also we consider the existing one as the primary.
                merged_count += 1
                to_delete.append(f.finding_id)
                # Update last_seen
                if f.last_seen and (not existing.last_seen or f.last_seen > existing.last_seen):
                    existing.last_seen = f.last_seen
                    
                # Update status logic: if new finding is active and existing is remediated, reopen
                active_statuses = [FindingStatus.NEW, FindingStatus.CONFIRMED, FindingStatus.REOPENED]
                if f.status in active_statuses and existing.status not in active_statuses:
                    existing.status = FindingStatus.REOPENED
        
        for fid in to_delete:
            del self.findings[fid]
            
        return merged_count

    def get_security_report(self) -> Dict:
        """Generate a full summary report of findings and scans."""
        severity_counts = {s.value: 0 for s in FindingSeverity}
        status_counts = {s.value: 0 for s in FindingStatus}
        
        for f in self.findings.values():
            severity_counts[f.severity.value] += 1
            status_counts[f.status.value] += 1
            
        scan_counts = {s.value: 0 for s in SecurityScanType}
        for s in self.scans.values():
            scan_counts[s.scan_type.value] += 1
            
        return {
            "total_findings": len(self.findings),
            "total_scans": len(self.scans),
            "findings_by_severity": severity_counts,
            "findings_by_status": status_counts,
            "scans_by_type": scan_counts,
            "sla_compliance_rate": self._calculate_sla_compliance()
        }
        
    def _calculate_sla_compliance(self) -> float:
        total_with_sla = 0
        missed_sla = 0
        now = datetime.utcnow()
        for f in self.findings.values():
            if f.sla_deadline:
                total_with_sla += 1
                deadline_dt = datetime.fromisoformat(f.sla_deadline)
                # If remediated, check if it was remediated before deadline
                # Simplify: if currently active and past deadline OR remediated past deadline (if we tracked remediation time, but we use last_seen)
                # For this engine, we'll just check if it breached based on current time or if it's active past deadline
                if f.status not in (FindingStatus.REMEDIATED, FindingStatus.FALSE_POSITIVE, FindingStatus.ACCEPTED_RISK):
                    if now > deadline_dt:
                        missed_sla += 1
                        
        if total_with_sla == 0:
            return 1.0
        return (total_with_sla - missed_sla) / total_with_sla
