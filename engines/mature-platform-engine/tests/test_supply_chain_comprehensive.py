import unittest
from datetime import datetime, timezone
import copy

from elmos_mature_platform.types import (
    ScanType, ScanStatus, VexJustification, ArtifactType,
    SbomComponent, ThreatModelEntry, SeverityLevel, ComplianceControlMapping
)
from elmos_mature_platform.supply_chain_security_engine import SupplyChainSecurityEngine

class TestSupplyChainComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = SupplyChainSecurityEngine()
        
    def test_sbom_registration_with_components_and_cves(self):
        comp = SbomComponent(
            component_id="comp-1", name="openssl", version="1.1.1",
            purl="pkg:generic/openssl@1.1.1", sha256="123", license="MIT",
            cves=["CVE-2021-1234"]
        )
        res = self.engine.register_sbom("sbom-1", [comp])
        self.assertEqual(res["component_count"], 1)
        self.assertEqual(res["cve_count"], 1)
        self.assertEqual(res["license_distribution"]["MIT"], 1)

    def test_sast_scan_detecting_eval_exec_patterns(self):
        res = self.engine.run_security_scan(ScanType.SAST, "eval('bad')")
        self.assertEqual(res.status, ScanStatus.COMPLETED)
        self.assertEqual(res.high_count, 1)
        self.assertEqual(res.findings[0]["rule"], "avoid_eval_exec")

    def test_secret_scan_detecting_aws_keys_github_tokens_rsa_keys(self):
        target = "AKIAIOSFODNN7EXAMPLE ghp_123456789012345678901234567890123456 -----BEGIN RSA PRIVATE KEY-----"
        res = self.engine.run_security_scan(ScanType.SECRET, target)
        self.assertEqual(res.critical_count, 3)

    def test_secret_scan_on_clean_content(self):
        res = self.engine.run_security_scan(ScanType.SECRET, "clean code")
        self.assertEqual(res.critical_count, 0)
        self.assertEqual(res.findings_count, 0)

    def test_sca_scan_cross_referencing_sbom_cves(self):
        comp = SbomComponent(
            component_id="comp-1", name="log4j", version="2.14.0",
            purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.0", sha256="123",
            license="Apache-2.0", cves=["CVE-2021-44228"]
        )
        self.engine.register_sbom("sbom-log4j", [comp])
        res = self.engine.run_security_scan(ScanType.SCA, "sbom-log4j")
        self.assertEqual(res.high_count, 1)
        self.assertEqual(res.findings[0]["cve"], "CVE-2021-44228")

    def test_container_scan(self):
        res = self.engine.run_security_scan(ScanType.CONTAINER, "my-image:latest")
        self.assertEqual(res.medium_count, 1)
        self.assertEqual(res.findings[0]["rule"], "use_specific_tag")

    def test_slsa_provenance_generation(self):
        prov = self.engine.generate_slsa_provenance("art-1", ArtifactType.CONTAINER_IMAGE, "repo", "commit")
        self.assertEqual(prov.artifact_id, "art-1")
        self.assertEqual(prov.slsa_level, 3)
        self.assertTrue(prov.hermetic)
        self.assertTrue(prov.reproducible)

    def test_artifact_signing_and_successful_verification(self):
        sig = self.engine.sign_artifact("art-1", "abcd", "signer", "key-1")
        self.assertTrue(self.engine.verify_artifact_signature(sig))

    def test_signature_verification_with_tampered_digest_fails(self):
        sig = self.engine.sign_artifact("art-1", "abcd", "signer", "key-1")
        sig.sha256_digest = "efgh"
        self.assertFalse(self.engine.verify_artifact_signature(sig))

    def test_threat_model_creation(self):
        t1 = ThreatModelEntry("t1", "Spoofing", "title", "desc", "vector", SeverityLevel.HIGH)
        t2 = ThreatModelEntry("t2", "Tampering", "title2", "desc", "vector", SeverityLevel.CRITICAL)
        res = self.engine.create_threat_model("tm-1", [t1, t2])
        self.assertEqual(res["total_threats"], 2)
        self.assertEqual(res["by_category"]["Spoofing"], 1)

    def test_threat_model_summary_statistics(self):
        t1 = ThreatModelEntry("t1", "Spoofing", "title", "desc", "vector", SeverityLevel.HIGH)
        res = self.engine.create_threat_model("tm-1", [t1])
        self.assertEqual(res["by_severity"]["HIGH"], 1)

    def test_vex_statement_issuance_not_affected(self):
        vex = self.engine.issue_vex_statement("vex-1", "CVE-1", "prod-1", "not_affected", VexJustification.COMPONENT_NOT_PRESENT)
        self.assertEqual(vex.status, "not_affected")
        self.assertEqual(vex.justification, VexJustification.COMPONENT_NOT_PRESENT)

    def test_vex_statement_issuance_affected(self):
        vex = self.engine.issue_vex_statement("vex-2", "CVE-2", "prod-1", "affected")
        self.assertEqual(vex.status, "affected")

    def test_vulnerability_risk_evaluation_mixed_statuses(self):
        comp1 = SbomComponent(
            component_id="c1", name="lib1", version="1", purl="p1", sha256="s1", license="MIT", cves=["CVE-1"]
        )
        comp2 = SbomComponent(
            component_id="c2", name="lib2", version="1", purl="p2", sha256="s2", license="MIT", cves=["CVE-2"]
        )
        self.engine.register_sbom("sbom-mixed", [comp1, comp2])
        self.engine.issue_vex_statement("vex-1", "CVE-1", "prod-1", "not_affected", VexJustification.COMPONENT_NOT_PRESENT)
        
        res = self.engine.evaluate_vulnerability_risk("sbom-mixed")
        self.assertEqual(res["total_vulns"], 2)
        self.assertEqual(res["mitigated_vulns"], 1)
        self.assertEqual(res["exploitable_vulns"], 1)
        self.assertEqual(res["risk_score"], 50.0)

    def test_compliance_control_mapping(self):
        map1 = ComplianceControlMapping("ctrl-1", "SOC2", "Control 1", status="compliant")
        self.engine.map_compliance_control(map1)
        self.assertEqual(self.engine.compliance_mappings["ctrl-1"].status, "compliant")

    def test_compliance_posture_assessment(self):
        map1 = ComplianceControlMapping("ctrl-1", "SOC2", "C1", status="compliant")
        map2 = ComplianceControlMapping("ctrl-2", "SOC2", "C2", status="non_compliant")
        self.engine.map_compliance_control(map1)
        self.engine.map_compliance_control(map2)
        res = self.engine.assess_compliance_posture("SOC2")
        self.assertEqual(res["total_controls"], 2)
        self.assertEqual(res["compliance_percentage"], 50.0)

    def test_full_supply_chain_report(self):
        comp = SbomComponent(component_id="c1", name="lib1", version="1", purl="p1", sha256="s1", license="MIT")
        self.engine.register_sbom("sbom-1", [comp])
        self.engine.run_security_scan(ScanType.SAST, "code")
        self.engine.generate_slsa_provenance("art-1", ArtifactType.BINARY, "repo", "commit")
        self.engine.sign_artifact("art-1", "digest", "signer", "key-1")
        
        rep = self.engine.generate_supply_chain_report()
        self.assertEqual(rep["sbom_count"], 1)
        self.assertEqual(rep["scan_summary"], 1)
        self.assertEqual(rep["provenance_count"], 1)
        self.assertEqual(rep["signature_count"], 1)

    def test_artifact_integrity_check_all_pass(self):
        self.engine.register_sbom("art-1", [])
        self.engine.generate_slsa_provenance("art-1", ArtifactType.BINARY, "repo", "commit")
        self.engine.sign_artifact("art-1", "digest", "signer", "key-1")
        res = self.engine.check_artifact_integrity("art-1")
        self.assertTrue(res["overall_pass"])

    def test_artifact_integrity_check_missing_sbom(self):
        self.engine.generate_slsa_provenance("art-1", ArtifactType.BINARY, "repo", "commit")
        self.engine.sign_artifact("art-1", "digest", "signer", "key-1")
        res = self.engine.check_artifact_integrity("art-1")
        self.assertFalse(res["overall_pass"])
        self.assertFalse(res["has_sbom"])

    def test_artifact_integrity_check_unresolved_cve(self):
        comp = SbomComponent(
            component_id="c1", name="lib1", version="1", purl="p1", sha256="s1", license="MIT", cves=["CVE-CRIT"]
        )
        self.engine.register_sbom("art-1", [comp])
        self.engine.generate_slsa_provenance("art-1", ArtifactType.BINARY, "repo", "commit")
        self.engine.sign_artifact("art-1", "digest", "signer", "key-1")
        
        res = self.engine.check_artifact_integrity("art-1")
        self.assertFalse(res["overall_pass"])
        self.assertTrue(res["unresolved_critical_cves"])

    def test_multiple_sbom_registration(self):
        self.engine.register_sbom("s1", [])
        self.engine.register_sbom("s2", [])
        self.assertEqual(len(self.engine.sboms), 2)

    def test_scan_multiple_finding_types(self):
        res = self.engine.run_security_scan(ScanType.SAST, "eval() exec() subprocess")
        self.assertEqual(res.high_count, 1)

    def test_slsa_level_validation(self):
        prov = self.engine.generate_slsa_provenance("art-1", ArtifactType.BINARY, "r", "c")
        self.assertEqual(prov.slsa_level, 3)

    def test_vulnerability_risk_no_vulns(self):
        self.engine.register_sbom("s1", [SbomComponent("c1", "n", "v", "p", "s", "l")])
        res = self.engine.evaluate_vulnerability_risk("s1")
        self.assertEqual(res["total_vulns"], 0)
        self.assertEqual(res["risk_score"], 0)
        
    def test_vulnerability_risk_invalid_sbom(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate_vulnerability_risk("invalid")

if __name__ == "__main__":
    unittest.main()
