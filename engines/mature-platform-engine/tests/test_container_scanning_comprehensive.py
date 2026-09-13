import unittest
import uuid
from typing import Dict, List
from elmos_mature_platform.types import (
    ContainerImage, ContainerPolicy, ContainerScanResult, ContainerFinding,
    ContainerScanStatus, ContainerFindingType
)
from elmos_mature_platform.container_scanning_engine import ContainerScanningEngine

class TestContainerScanningEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ContainerScanningEngine()
        
    def _create_test_image(self, registry="docker.io", tag="latest"):
        image = ContainerImage(
            image_id="",
            registry=registry,
            repository="myrepo/app",
            tag=tag,
            digest_sha256="sha256:dummy",
            size_mb=100.0,
            os_family="alpine",
            layers_count=5
        )
        image_id = self.engine.register_image(image)
        return image_id
        
    def _create_test_policy(self, max_critical=0, max_high=5, allowed_registries=None):
        if allowed_registries is None:
            allowed_registries = ["docker.io", "gcr.io"]
        policy = ContainerPolicy(
            policy_id="",
            name="Test Policy",
            max_critical=max_critical,
            max_high=max_high,
            block_secrets=True,
            block_malware=True,
            allowed_registries=allowed_registries
        )
        return self.engine.create_policy(policy)

    # 1. Register image generates id
    def test_register_image_generates_id(self):
        img_id = self._create_test_image()
        self.assertTrue(bool(img_id))
        
    # 2. Register image stores image
    def test_register_image_stores_image(self):
        img_id = self._create_test_image()
        self.assertIn(img_id, self.engine._images)
        
    # 3. Create policy generates id
    def test_create_policy_generates_id(self):
        pol_id = self._create_test_policy()
        self.assertTrue(bool(pol_id))
        
    # 4. Create policy stores policy
    def test_create_policy_stores_policy(self):
        pol_id = self._create_test_policy()
        self.assertIn(pol_id, self.engine._policies)
        
    # 5. Start scan creates scan
    def test_start_scan_creates_scan(self):
        img_id = self._create_test_image()
        scan = self.engine.start_scan(img_id)
        self.assertEqual(scan.image_id, img_id)
        self.assertEqual(scan.status, ContainerScanStatus.SCANNING)
        self.assertTrue(bool(scan.scan_id))
        
    # 6. Start scan for unknown image fails
    def test_start_scan_unknown_image_raises(self):
        with self.assertRaises(ValueError):
            self.engine.start_scan("bad_id")
            
    # 7. Add finding to scanning scan succeeds
    def test_add_finding_succeeds(self):
        img_id = self._create_test_image()
        scan = self.engine.start_scan(img_id)
        f = ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.OS_VULNERABILITY, severity="high")
        self.engine.add_finding(f)
        self.assertEqual(len(self.engine._findings[scan.scan_id]), 1)
        
    # 8. Add finding to unknown scan fails
    def test_add_finding_unknown_scan_raises(self):
        f = ContainerFinding(finding_id="", scan_id="bad", finding_type=ContainerFindingType.OS_VULNERABILITY)
        with self.assertRaises(ValueError):
            self.engine.add_finding(f)
            
    # 9. Add finding to completed scan fails
    def test_add_finding_completed_scan_raises(self):
        img_id = self._create_test_image()
        scan = self.engine.start_scan(img_id)
        self.engine.complete_scan(scan.scan_id)
        f = ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.OS_VULNERABILITY)
        with self.assertRaises(ValueError):
            self.engine.add_finding(f)
            
    # 10. Complete scan tallies findings correctly
    def test_complete_scan_tallies_findings(self):
        img_id = self._create_test_image()
        scan = self.engine.start_scan(img_id)
        self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.OS_VULNERABILITY, severity="critical"))
        self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.MISCONFIG, severity="high"))
        self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.SECRET, severity="high"))
        
        c_scan = self.engine.complete_scan(scan.scan_id)
        self.assertEqual(c_scan.critical_count, 1)
        self.assertEqual(c_scan.high_count, 2)
        self.assertEqual(c_scan.misconfig_count, 1)
        self.assertEqual(c_scan.secret_count, 1)
        self.assertEqual(c_scan.status, ContainerScanStatus.COMPLETED)
        
    # 11. Complete unknown scan fails
    def test_complete_unknown_scan_raises(self):
        with self.assertRaises(ValueError):
            self.engine.complete_scan("bad")
            
    # 12. Evaluate policy unknown scan fails
    def test_evaluate_policy_unknown_scan(self):
        pol_id = self._create_test_policy()
        with self.assertRaises(ValueError):
            self.engine.evaluate_policy("bad", pol_id)
            
    # 13. Evaluate policy unknown policy fails
    def test_evaluate_policy_unknown_policy(self):
        img_id = self._create_test_image()
        scan = self.engine.start_scan(img_id)
        self.engine.complete_scan(scan.scan_id)
        with self.assertRaises(ValueError):
            self.engine.evaluate_policy(scan.scan_id, "bad")
            
    # 14. Evaluate policy on scanning scan fails
    def test_evaluate_policy_scanning_state_raises(self):
        img_id = self._create_test_image()
        pol_id = self._create_test_policy()
        scan = self.engine.start_scan(img_id)
        with self.assertRaises(ValueError):
            self.engine.evaluate_policy(scan.scan_id, pol_id)
            
    # 15. Policy pass: 0 critical, low high
    def test_evaluate_policy_pass(self):
        img_id = self._create_test_image()
        pol_id = self._create_test_policy(max_critical=0, max_high=5)
        scan = self.engine.start_scan(img_id)
        for _ in range(3):
            self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.OS_VULNERABILITY, severity="high"))
        self.engine.complete_scan(scan.scan_id)
        res = self.engine.evaluate_policy(scan.scan_id, pol_id)
        self.assertTrue(res["passed"])
        
    # 16. Policy fail: critical exceeds
    def test_evaluate_policy_fail_critical(self):
        img_id = self._create_test_image()
        pol_id = self._create_test_policy(max_critical=0)
        scan = self.engine.start_scan(img_id)
        self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.OS_VULNERABILITY, severity="critical"))
        self.engine.complete_scan(scan.scan_id)
        res = self.engine.evaluate_policy(scan.scan_id, pol_id)
        self.assertFalse(res["passed"])
        self.assertIn("Critical findings", res["reasons"][0])
        
    # 17. Policy fail: high exceeds
    def test_evaluate_policy_fail_high(self):
        img_id = self._create_test_image()
        pol_id = self._create_test_policy(max_high=1)
        scan = self.engine.start_scan(img_id)
        for _ in range(2):
            self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.OS_VULNERABILITY, severity="high"))
        self.engine.complete_scan(scan.scan_id)
        res = self.engine.evaluate_policy(scan.scan_id, pol_id)
        self.assertFalse(res["passed"])
        
    # 18. Policy fail: secrets block
    def test_evaluate_policy_fail_secrets(self):
        img_id = self._create_test_image()
        pol_id = self._create_test_policy()
        scan = self.engine.start_scan(img_id)
        self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.SECRET, severity="high"))
        self.engine.complete_scan(scan.scan_id)
        res = self.engine.evaluate_policy(scan.scan_id, pol_id)
        self.assertFalse(res["passed"])
        
    # 19. Policy fail: malware block
    def test_evaluate_policy_fail_malware(self):
        img_id = self._create_test_image()
        pol_id = self._create_test_policy()
        scan = self.engine.start_scan(img_id)
        self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.MALWARE, severity="high"))
        self.engine.complete_scan(scan.scan_id)
        res = self.engine.evaluate_policy(scan.scan_id, pol_id)
        self.assertFalse(res["passed"])
        
    # 20. Policy fail: disallowed registry
    def test_evaluate_policy_fail_registry(self):
        img_id = self._create_test_image(registry="evil.com")
        pol_id = self._create_test_policy() # allows docker.io, gcr.io
        scan = self.engine.start_scan(img_id)
        self.engine.complete_scan(scan.scan_id)
        res = self.engine.evaluate_policy(scan.scan_id, pol_id)
        self.assertFalse(res["passed"])
        
    # 21. Get findings filtered by severity
    def test_get_findings_by_severity(self):
        img_id = self._create_test_image()
        scan = self.engine.start_scan(img_id)
        self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.OS_VULNERABILITY, severity="low"))
        self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.OS_VULNERABILITY, severity="high"))
        f = self.engine.get_findings(scan.scan_id, severity="high")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].severity.lower(), "high")
        
    # 22. Get findings filtered by type
    def test_get_findings_by_type(self):
        img_id = self._create_test_image()
        scan = self.engine.start_scan(img_id)
        self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.MISCONFIG, severity="low"))
        self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.SECRET, severity="high"))
        f = self.engine.get_findings(scan.scan_id, finding_type=ContainerFindingType.SECRET)
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].finding_type, ContainerFindingType.SECRET)
        
    # 23. Get image history
    def test_get_image_history(self):
        img_id = self._create_test_image()
        scan1 = self.engine.start_scan(img_id)
        self.engine.complete_scan(scan1.scan_id)
        scan2 = self.engine.start_scan(img_id)
        history = self.engine.get_image_history(img_id)
        self.assertEqual(len(history), 2)
        
    # 24. Get image history unknown image
    def test_get_image_history_unknown(self):
        with self.assertRaises(ValueError):
            self.engine.get_image_history("bad")
            
    # 25. Get fixable findings
    def test_get_fixable_findings(self):
        img_id = self._create_test_image()
        scan = self.engine.start_scan(img_id)
        self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.OS_VULNERABILITY, severity="low", fixed_version="1.2.3"))
        self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.OS_VULNERABILITY, severity="high"))
        f = self.engine.get_fixable_findings(scan.scan_id)
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].fixed_version, "1.2.3")
        
    # 26. Get fixable findings unknown scan
    def test_get_fixable_findings_unknown(self):
        with self.assertRaises(ValueError):
            self.engine.get_fixable_findings("bad")
            
    # 27. Check registry compliance pass
    def test_check_registry_compliance_pass(self):
        img_id = self._create_test_image(registry="docker.io")
        pol_id = self._create_test_policy()
        res = self.engine.check_registry_compliance(img_id, pol_id)
        self.assertTrue(res["compliant"])
        
    # 28. Check registry compliance fail
    def test_check_registry_compliance_fail(self):
        img_id = self._create_test_image(registry="evil.com")
        pol_id = self._create_test_policy()
        res = self.engine.check_registry_compliance(img_id, pol_id)
        self.assertFalse(res["compliant"])
        
    # 29. Check registry compliance unknown image
    def test_check_registry_compliance_unknown_image(self):
        pol_id = self._create_test_policy()
        with self.assertRaises(ValueError):
            self.engine.check_registry_compliance("bad", pol_id)
            
    # 30. Check registry compliance unknown policy
    def test_check_registry_compliance_unknown_policy(self):
        img_id = self._create_test_image()
        with self.assertRaises(ValueError):
            self.engine.check_registry_compliance(img_id, "bad")
            
    # 31. Get scanning report
    def test_get_scanning_report(self):
        img_id = self._create_test_image()
        pol_id = self._create_test_policy(max_critical=0)
        scan = self.engine.start_scan(img_id)
        self.engine.add_finding(ContainerFinding(finding_id="", scan_id=scan.scan_id, finding_type=ContainerFindingType.OS_VULNERABILITY, severity="critical"))
        self.engine.complete_scan(scan.scan_id)
        self.engine.evaluate_policy(scan.scan_id, pol_id)
        
        rep = self.engine.get_scanning_report()
        self.assertEqual(rep["total_images_registered"], 1)
        self.assertEqual(rep["total_scans"], 1)
        self.assertEqual(rep["completed_scans"], 1)
        self.assertEqual(rep["policy_pass_rate"], 0.0)
        self.assertEqual(rep["findings_by_severity"]["critical"], 1)
        self.assertEqual(rep["findings_by_type"][ContainerFindingType.OS_VULNERABILITY.value], 1)

if __name__ == '__main__':
    unittest.main()
