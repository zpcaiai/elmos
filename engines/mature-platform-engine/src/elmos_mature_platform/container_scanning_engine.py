import uuid
import datetime
from typing import Dict, List, Optional
from .types import (
    ContainerImage, ContainerPolicy, ContainerScanResult, ContainerFinding,
    ContainerScanStatus, ContainerFindingType
)

class ContainerScanningEngine:
    """Engine for container image scanning and policy enforcement."""
    
    def __init__(self):
        self._images: Dict[str, ContainerImage] = {}
        self._policies: Dict[str, ContainerPolicy] = {}
        self._scans: Dict[str, ContainerScanResult] = {}
        self._findings: Dict[str, List[ContainerFinding]] = {}

    def register_image(self, image: ContainerImage) -> str:
        """Register a new container image for scanning."""
        if not image.image_id:
            image.image_id = str(uuid.uuid4())
        self._images[image.image_id] = image
        return image.image_id

    def create_policy(self, policy: ContainerPolicy) -> str:
        """Create a new scanning policy."""
        if not policy.policy_id:
            policy.policy_id = str(uuid.uuid4())
        self._policies[policy.policy_id] = policy
        return policy.policy_id

    def start_scan(self, image_id: str) -> ContainerScanResult:
        """Start a new scan for the given image."""
        if image_id not in self._images:
            raise ValueError(f"Image {image_id} not found")
        
        scan_id = str(uuid.uuid4())
        scan = ContainerScanResult(
            scan_id=scan_id,
            image_id=image_id,
            status=ContainerScanStatus.SCANNING,
            started_at=datetime.datetime.utcnow().isoformat()
        )
        self._scans[scan_id] = scan
        self._findings[scan_id] = []
        return scan

    def add_finding(self, finding: ContainerFinding) -> None:
        """Add a finding to an ongoing scan."""
        if finding.scan_id not in self._scans:
            raise ValueError(f"Scan {finding.scan_id} not found")
        if self._scans[finding.scan_id].status != ContainerScanStatus.SCANNING:
            raise ValueError(f"Scan {finding.scan_id} is not in scanning state")
        
        if not finding.finding_id:
            finding.finding_id = str(uuid.uuid4())
        self._findings[finding.scan_id].append(finding)

    def complete_scan(self, scan_id: str) -> ContainerScanResult:
        """Complete a scan and tally findings."""
        if scan_id not in self._scans:
            raise ValueError(f"Scan {scan_id} not found")
        
        scan = self._scans[scan_id]
        if scan.status != ContainerScanStatus.SCANNING:
            raise ValueError(f"Scan {scan_id} is not in scanning state")
            
        scan.status = ContainerScanStatus.COMPLETED
        scan.completed_at = datetime.datetime.utcnow().isoformat()
        
        # Reset counts
        scan.critical_count = 0
        scan.high_count = 0
        scan.medium_count = 0
        scan.low_count = 0
        scan.misconfig_count = 0
        scan.secret_count = 0
        
        for finding in self._findings[scan_id]:
            sev = finding.severity.lower() if finding.severity else ""
            if sev == "critical":
                scan.critical_count += 1
            elif sev == "high":
                scan.high_count += 1
            elif sev == "medium":
                scan.medium_count += 1
            elif sev == "low":
                scan.low_count += 1
                
            if finding.finding_type == ContainerFindingType.MISCONFIG:
                scan.misconfig_count += 1
            elif finding.finding_type == ContainerFindingType.SECRET:
                scan.secret_count += 1
                
        return scan

    def evaluate_policy(self, scan_id: str, policy_id: str) -> Dict:
        """Evaluate a completed scan against a policy."""
        if scan_id not in self._scans:
            raise ValueError(f"Scan {scan_id} not found")
        if policy_id not in self._policies:
            raise ValueError(f"Policy {policy_id} not found")
            
        scan = self._scans[scan_id]
        if scan.status != ContainerScanStatus.COMPLETED:
            raise ValueError(f"Scan {scan_id} must be completed to evaluate policy")
            
        policy = self._policies[policy_id]
        image = self._images[scan.image_id]
        
        reasons = []
        passed = True
        
        if scan.critical_count > policy.max_critical:
            passed = False
            reasons.append(f"Critical findings ({scan.critical_count}) exceed maximum allowed ({policy.max_critical})")
            
        if scan.high_count > policy.max_high:
            passed = False
            reasons.append(f"High findings ({scan.high_count}) exceed maximum allowed ({policy.max_high})")
            
        if policy.block_secrets and scan.secret_count > 0:
            passed = False
            reasons.append(f"Contains {scan.secret_count} blocked secrets")
            
        if policy.block_malware:
            malware_count = sum(1 for f in self._findings[scan_id] if f.finding_type == ContainerFindingType.MALWARE)
            if malware_count > 0:
                passed = False
                reasons.append(f"Contains {malware_count} malware findings")
                
        if policy.allowed_registries and image.registry not in policy.allowed_registries:
            passed = False
            reasons.append(f"Registry {image.registry} is not in allowed registries list")
            
        # Update scan record
        scan.passed_policy = passed
        
        return {
            "passed": passed,
            "reasons": reasons,
            "scan_id": scan_id,
            "policy_id": policy_id
        }

    def get_findings(self, scan_id: str, severity: Optional[str] = None, finding_type: Optional[ContainerFindingType] = None) -> List[ContainerFinding]:
        """Get filtered findings for a scan."""
        if scan_id not in self._findings:
            raise ValueError(f"Scan {scan_id} not found")
            
        findings = self._findings[scan_id]
        
        if severity:
            sev_lower = severity.lower()
            findings = [f for f in findings if f.severity.lower() == sev_lower]
            
        if finding_type:
            findings = [f for f in findings if f.finding_type == finding_type]
            
        return findings

    def get_image_history(self, image_id: str) -> List[ContainerScanResult]:
        """Get scan history for an image."""
        if image_id not in self._images:
            raise ValueError(f"Image {image_id} not found")
            
        return [scan for scan in self._scans.values() if scan.image_id == image_id]

    def get_fixable_findings(self, scan_id: str) -> List[ContainerFinding]:
        """Get findings that have a fixed_version available."""
        if scan_id not in self._findings:
            raise ValueError(f"Scan {scan_id} not found")
            
        return [f for f in self._findings[scan_id] if bool(f.fixed_version)]

    def check_registry_compliance(self, image_id: str, policy_id: str) -> Dict:
        """Check if an image complies with registry requirements of a policy."""
        if image_id not in self._images:
            raise ValueError(f"Image {image_id} not found")
        if policy_id not in self._policies:
            raise ValueError(f"Policy {policy_id} not found")
            
        image = self._images[image_id]
        policy = self._policies[policy_id]
        
        is_compliant = True
        reason = "Compliant"
        
        if policy.allowed_registries and image.registry not in policy.allowed_registries:
            is_compliant = False
            reason = f"Registry {image.registry} not allowed"
            
        return {
            "compliant": is_compliant,
            "reason": reason,
            "image_id": image_id,
            "policy_id": policy_id
        }

    def get_scanning_report(self) -> Dict:
        """Get summary of scanning activities."""
        total_images = len(self._images)
        total_scans = len(self._scans)
        
        completed_scans = [s for s in self._scans.values() if s.status == ContainerScanStatus.COMPLETED]
        passed_scans = [s for s in completed_scans if s.passed_policy]
        
        pass_rate = (len(passed_scans) / len(completed_scans) * 100) if completed_scans else 0.0
        
        findings_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        findings_by_type = {t.value: 0 for t in ContainerFindingType}
        
        for findings in self._findings.values():
            for f in findings:
                if f.severity:
                    sev = f.severity.lower()
                    if sev in findings_by_severity:
                        findings_by_severity[sev] += 1
                if f.finding_type:
                    findings_by_type[f.finding_type.value] += 1
                    
        return {
            "total_images_registered": total_images,
            "total_scans": total_scans,
            "completed_scans": len(completed_scans),
            "policy_pass_rate": pass_rate,
            "findings_by_severity": findings_by_severity,
            "findings_by_type": findings_by_type
        }
