import hmac
import hashlib
import base64
import re
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from elmos_mature_platform.types import (
    ScanType, ScanStatus, VexJustification, ArtifactType, ScanResult,
    SlsaProvenance, ArtifactSignature, ThreatModelEntry, VexStatement,
    ComplianceControlMapping, SbomComponent, SeverityLevel
)

class SupplyChainSecurityEngine:
    def __init__(self):
        self.sboms: Dict[str, List[SbomComponent]] = {}
        self.scan_results: Dict[str, ScanResult] = {}
        self.provenance_records: Dict[str, SlsaProvenance] = {}
        self.signatures: Dict[str, ArtifactSignature] = {}
        self.threat_models: Dict[str, List[ThreatModelEntry]] = {}
        self.vex_statements: Dict[str, VexStatement] = {}
        self.compliance_mappings: Dict[str, ComplianceControlMapping] = {}

    def register_sbom(self, sbom_id: str, components: List[SbomComponent]) -> Dict[str, Any]:
        """Register a Software Bill of Materials."""
        self.sboms[sbom_id] = components
        cve_count = sum(len(c.cves) for c in components)
        licenses = {}
        for c in components:
            licenses[c.license] = licenses.get(c.license, 0) + 1
        
        return {
            "component_count": len(components),
            "cve_count": cve_count,
            "license_distribution": licenses
        }

    def run_security_scan(self, scan_type: ScanType, target: str, tool_name: str = "elmos-scanner") -> ScanResult:
        """Simulate a security scan."""
        started_at = datetime.now(timezone.utc).isoformat()
        findings = []
        critical = 0
        high = 0
        medium = 0
        low = 0
        
        if scan_type == ScanType.SAST:
            # Simulate SAST scan finding eval/exec
            if "eval(" in target or "exec(" in target or "subprocess" in target:
                findings.append({"rule": "avoid_eval_exec", "severity": "high"})
                high += 1
        elif scan_type == ScanType.SECRET:
            # Simulate SECRET scan detecting AWS keys, GitHub tokens, private keys
            if re.search(r"AKIA[0-9A-Z]{16}", target):
                findings.append({"rule": "aws_access_key", "severity": "critical"})
                critical += 1
            if re.search(r"ghp_[a-zA-Z0-9]{36}", target):
                findings.append({"rule": "github_token", "severity": "critical"})
                critical += 1
            if "BEGIN RSA PRIVATE KEY" in target:
                findings.append({"rule": "rsa_private_key", "severity": "critical"})
                critical += 1
        elif scan_type == ScanType.SCA:
            # Cross-reference registered SBOMs for known CVEs
            # Here we expect target to be sbom_id
            if target in self.sboms:
                for c in self.sboms[target]:
                    for cve in c.cves:
                        findings.append({"rule": "known_cve", "cve": cve, "severity": "high"})
                        high += 1
        elif scan_type == ScanType.CONTAINER:
            # Simulate container scan
            if "latest" in target:
                findings.append({"rule": "use_specific_tag", "severity": "medium"})
                medium += 1

        scan_id = f"scan-{len(self.scan_results)+1}"
        result = ScanResult(
            scan_id=scan_id,
            scan_type=scan_type,
            target=target,
            status=ScanStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            findings_count=len(findings),
            critical_count=critical,
            high_count=high,
            medium_count=medium,
            low_count=low,
            findings=findings,
            tool_name=tool_name,
            tool_version="1.0.0"
        )
        self.scan_results[scan_id] = result
        return result

    def generate_slsa_provenance(self, artifact_id: str, artifact_type: ArtifactType, source_repo: str, source_commit: str, builder_id: str = "elmos-trusted-builder") -> SlsaProvenance:
        """Generate SLSA L3 provenance."""
        digest = hashlib.sha256(artifact_id.encode()).hexdigest()
        reproducible = "trusted" in builder_id
        prov = SlsaProvenance(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            sha256_digest=digest,
            builder_id=builder_id,
            build_type="https://elmos.dev/slsa/v1",
            source_repo=source_repo,
            source_commit=source_commit,
            source_branch="main",
            build_timestamp=datetime.now(timezone.utc).isoformat(),
            slsa_level=3,
            reproducible=reproducible,
            hermetic=True
        )
        self.provenance_records[artifact_id] = prov
        return prov

    def sign_artifact(self, artifact_id: str, sha256_digest: str, signer_identity: str, signing_key_id: str) -> ArtifactSignature:
        """Create HMAC-based signature for artifact."""
        mac = hmac.new(b"secret-key", f"{artifact_id}:{sha256_digest}".encode(), hashlib.sha256).digest()
        sig_b64 = base64.b64encode(mac).decode('utf-8')
        sig = ArtifactSignature(
            artifact_id=artifact_id,
            sha256_digest=sha256_digest,
            signature_b64=sig_b64,
            signer_identity=signer_identity,
            signing_key_id=signing_key_id,
            signing_timestamp=datetime.now(timezone.utc).isoformat(),
            verified=False
        )
        self.signatures[artifact_id] = sig
        return sig

    def verify_artifact_signature(self, signature: ArtifactSignature) -> bool:
        """Verify a previously created signature."""
        mac = hmac.new(b"secret-key", f"{signature.artifact_id}:{signature.sha256_digest}".encode(), hashlib.sha256).digest()
        expected_sig_b64 = base64.b64encode(mac).decode('utf-8')
        if signature.signature_b64 == expected_sig_b64:
            signature.verified = True
            return True
        return False

    def create_threat_model(self, model_id: str, threats: List[ThreatModelEntry]) -> Dict[str, Any]:
        """Register threat model."""
        self.threat_models[model_id] = threats
        categories = {}
        severities = {}
        for t in threats:
            categories[t.category] = categories.get(t.category, 0) + 1
            severities[t.severity.value] = severities.get(t.severity.value, 0) + 1
            
        return {
            "total_threats": len(threats),
            "by_category": categories,
            "by_severity": severities
        }

    def issue_vex_statement(self, vex_id: str, cve_id: str, product_id: str, status: str, justification: Optional[VexJustification] = None) -> VexStatement:
        """Issue a VEX statement for a CVE."""
        vex = VexStatement(
            vex_id=vex_id,
            cve_id=cve_id,
            product_id=product_id,
            status=status,
            justification=justification,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        self.vex_statements[vex_id] = vex
        return vex

    def evaluate_vulnerability_risk(self, sbom_id: str) -> Dict[str, Any]:
        """For registered SBOM, cross-reference VEX statements and compute vulnerability risk."""
        if sbom_id not in self.sboms:
            raise ValueError("SBOM not found")
            
        total_vulns = 0
        exploitable_vulns = 0
        mitigated_vulns = 0
        
        cve_map = {}
        for v in self.vex_statements.values():
            cve_map[v.cve_id] = v
            
        for c in self.sboms[sbom_id]:
            for cve in c.cves:
                total_vulns += 1
                vex = cve_map.get(cve)
                if vex and vex.status == "not_affected":
                    mitigated_vulns += 1
                else:
                    exploitable_vulns += 1
                    
        risk_score = 0
        if total_vulns > 0:
            risk_score = (exploitable_vulns / total_vulns) * 100
            
        return {
            "total_vulns": total_vulns,
            "exploitable_vulns": exploitable_vulns,
            "mitigated_vulns": mitigated_vulns,
            "risk_score": risk_score
        }

    def map_compliance_control(self, mapping: ComplianceControlMapping) -> None:
        """Register compliance control mapping."""
        self.compliance_mappings[mapping.control_id] = mapping

    def assess_compliance_posture(self, framework: str) -> Dict[str, Any]:
        """Assess compliance posture for a given framework."""
        total = 0
        compliant = 0
        non_compliant = 0
        not_assessed = 0
        
        for m in self.compliance_mappings.values():
            if m.framework == framework:
                total += 1
                if m.status == "compliant":
                    compliant += 1
                elif m.status == "non_compliant":
                    non_compliant += 1
                else:
                    not_assessed += 1
                    
        pct = (compliant / total * 100) if total > 0 else 0
        return {
            "total_controls": total,
            "compliant": compliant,
            "non_compliant": non_compliant,
            "not_assessed": not_assessed,
            "compliance_percentage": pct
        }

    def generate_supply_chain_report(self) -> Dict[str, Any]:
        """Comprehensive supply chain report."""
        return {
            "sbom_count": len(self.sboms),
            "scan_summary": len(self.scan_results),
            "provenance_count": len(self.provenance_records),
            "signature_count": len(self.signatures),
            "threat_model_summary": len(self.threat_models),
            "vex_summary": len(self.vex_statements),
            "compliance_summary": len(self.compliance_mappings)
        }

    def check_artifact_integrity(self, artifact_id: str) -> Dict[str, Any]:
        """Check artifact integrity: SBOM, provenance, signature, no unresolved critical CVEs."""
        has_sbom = False
        unresolved_critical = False
        
        # Check if any SBOM corresponds to this artifact
        # For simplicity in this demo, let's assume sbom_id == artifact_id
        if artifact_id in self.sboms:
            has_sbom = True
            cve_map = {v.cve_id: v.status for v in self.vex_statements.values()}
            for c in self.sboms[artifact_id]:
                for cve in c.cves:
                    # simplistic check: assuming all CVEs are critical unless VEX says not_affected
                    if cve_map.get(cve) != "not_affected":
                        unresolved_critical = True
        
        has_provenance = artifact_id in self.provenance_records
        
        has_signature = False
        if artifact_id in self.signatures:
            sig = self.signatures[artifact_id]
            has_signature = self.verify_artifact_signature(sig)
            
        passed = has_sbom and has_provenance and has_signature and not unresolved_critical
        
        return {
            "has_sbom": has_sbom,
            "has_provenance": has_provenance,
            "has_valid_signature": has_signature,
            "unresolved_critical_cves": unresolved_critical,
            "overall_pass": passed
        }
