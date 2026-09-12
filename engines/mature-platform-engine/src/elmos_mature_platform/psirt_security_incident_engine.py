import uuid
import datetime
from typing import List, Dict, Optional
from .types import SecurityVulnerability, PsirtSeverity, PsirtStatus, PsirtAdvisory

class PsirtSecurityIncidentEngine:
    """
    Engine for managing PSIRT security incidents, vulnerabilities, and advisories.
    """
    def __init__(self):
        self.vulnerabilities: Dict[str, SecurityVulnerability] = {}
        self.advisories: Dict[str, PsirtAdvisory] = {}

    def report_vulnerability(self, vuln: SecurityVulnerability) -> str:
        """Report a new vulnerability."""
        if not vuln.reported_at:
            vuln.reported_at = datetime.datetime.utcnow().isoformat()
            
        if vuln.exploited_in_wild:
            vuln.severity = PsirtSeverity.CRITICAL

        self.vulnerabilities[vuln.vuln_id] = vuln
        return vuln.vuln_id

    def triage(self, vuln_id: str, assignee: str, severity: PsirtSeverity) -> SecurityVulnerability:
        """Triage a reported vulnerability by assigning it and setting severity."""
        if vuln_id not in self.vulnerabilities:
            raise ValueError(f"Vulnerability {vuln_id} not found")
            
        vuln = self.vulnerabilities[vuln_id]
        if vuln.status != PsirtStatus.REPORTED:
            raise ValueError(f"Cannot triage vulnerability in status {vuln.status}")
            
        vuln.assignee = assignee
        
        # Enforce critical floor for exploited in wild
        if vuln.exploited_in_wild:
            vuln.severity = PsirtSeverity.CRITICAL
        else:
            vuln.severity = severity
            
        vuln.status = PsirtStatus.TRIAGED
        return vuln

    def start_investigation(self, vuln_id: str) -> SecurityVulnerability:
        """Start investigation of a triaged vulnerability."""
        if vuln_id not in self.vulnerabilities:
            raise ValueError(f"Vulnerability {vuln_id} not found")
            
        vuln = self.vulnerabilities[vuln_id]
        if vuln.status != PsirtStatus.TRIAGED:
            raise ValueError(f"Cannot start investigation for vulnerability in status {vuln.status}. Must be TRIAGED.")
            
        vuln.status = PsirtStatus.INVESTIGATING
        return vuln

    def develop_fix(self, vuln_id: str, fixed_version: str, patch_url: str) -> SecurityVulnerability:
        """Record fix development for a vulnerability."""
        if vuln_id not in self.vulnerabilities:
            raise ValueError(f"Vulnerability {vuln_id} not found")
            
        vuln = self.vulnerabilities[vuln_id]
        if vuln.status not in [PsirtStatus.INVESTIGATING, PsirtStatus.FIX_DEVELOPING]:
            raise ValueError(f"Cannot develop fix for vulnerability in status {vuln.status}.")
            
        vuln.fixed_version = fixed_version
        vuln.patch_url = patch_url
        vuln.status = PsirtStatus.FIX_DEVELOPING
        return vuln

    def release_fix(self, vuln_id: str) -> SecurityVulnerability:
        """Move vulnerability to FIX_AVAILABLE status."""
        if vuln_id not in self.vulnerabilities:
            raise ValueError(f"Vulnerability {vuln_id} not found")
            
        vuln = self.vulnerabilities[vuln_id]
        if vuln.status != PsirtStatus.FIX_DEVELOPING:
            raise ValueError(f"Cannot release fix for vulnerability in status {vuln.status}. Must be FIX_DEVELOPING.")
        if not vuln.fixed_version or not vuln.patch_url:
            raise ValueError("Cannot release fix without fixed_version and patch_url.")
            
        vuln.status = PsirtStatus.FIX_AVAILABLE
        return vuln

    def create_advisory(self, advisory: PsirtAdvisory) -> str:
        """Create an advisory for a vulnerability."""
        if advisory.vuln_id not in self.vulnerabilities:
            raise ValueError(f"Vulnerability {advisory.vuln_id} not found")
            
        self.advisories[advisory.advisory_id] = advisory
        return advisory.advisory_id

    def publish_advisory(self, advisory_id: str) -> PsirtAdvisory:
        """Publish an advisory."""
        if advisory_id not in self.advisories:
            raise ValueError(f"Advisory {advisory_id} not found")
            
        advisory = self.advisories[advisory_id]
        if not advisory.published_at:
            advisory.published_at = datetime.datetime.utcnow().isoformat()
        advisory.published = True
        return advisory

    def disclose(self, vuln_id: str) -> SecurityVulnerability:
        """Publicly disclose a vulnerability. Must have fix available."""
        if vuln_id not in self.vulnerabilities:
            raise ValueError(f"Vulnerability {vuln_id} not found")
            
        vuln = self.vulnerabilities[vuln_id]
        if vuln.status != PsirtStatus.FIX_AVAILABLE:
            raise ValueError(f"Cannot disclose vulnerability without a fix available. Status is {vuln.status}.")
            
        vuln.status = PsirtStatus.DISCLOSED
        vuln.disclosed_at = datetime.datetime.utcnow().isoformat()
        return vuln

    def close(self, vuln_id: str) -> SecurityVulnerability:
        """Close a vulnerability after disclosure."""
        if vuln_id not in self.vulnerabilities:
            raise ValueError(f"Vulnerability {vuln_id} not found")
            
        vuln = self.vulnerabilities[vuln_id]
        if vuln.status != PsirtStatus.DISCLOSED:
            raise ValueError(f"Cannot close vulnerability before disclosure. Status is {vuln.status}.")
            
        vuln.status = PsirtStatus.CLOSED
        return vuln

    def check_sla_violations(self) -> List[SecurityVulnerability]:
        """Return vulnerabilities exceeding their SLA response time."""
        violations = []
        now = datetime.datetime.utcnow()
        for vuln in self.vulnerabilities.values():
            if vuln.status == PsirtStatus.CLOSED:
                continue
                
            if vuln.reported_at:
                try:
                    reported_at = datetime.datetime.fromisoformat(vuln.reported_at)
                    elapsed_hours = (now - reported_at).total_seconds() / 3600
                    if elapsed_hours > vuln.sla_hours:
                        violations.append(vuln)
                except ValueError:
                    continue
        return violations

    def get_active_vulnerabilities(self) -> List[SecurityVulnerability]:
        """Return all vulnerabilities that are not closed."""
        return [v for v in self.vulnerabilities.values() if v.status != PsirtStatus.CLOSED]

    def get_psirt_report(self) -> Dict:
        """Return a report of PSIRT metrics."""
        report = {
            "by_severity": {
                PsirtSeverity.CRITICAL.value: 0,
                PsirtSeverity.HIGH.value: 0,
                PsirtSeverity.MEDIUM.value: 0,
                PsirtSeverity.LOW.value: 0
            },
            "by_status": {status.value: 0 for status in PsirtStatus},
            "total_vulnerabilities": len(self.vulnerabilities),
            "sla_violations": len(self.check_sla_violations())
        }
        
        for vuln in self.vulnerabilities.values():
            report["by_severity"][vuln.severity.value] += 1
            report["by_status"][vuln.status.value] += 1
            
        return report
