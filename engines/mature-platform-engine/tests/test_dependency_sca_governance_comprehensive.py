import unittest
from elmos_mature_platform.types import (
    LicenseRiskLevel,
    ScaDependencyRecord
)
from elmos_mature_platform.dependency_sca_governance_engine import DependencyScaGovernanceEngine

class TestDependencyScaGovernanceComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = DependencyScaGovernanceEngine()

    def _create_dep(self, dep_id="dep-1", name="lodash", version="4.17.21", spdx="MIT", vulns=None, direct=True, reachable=True, risk=LicenseRiskLevel.UNKNOWN):
        return ScaDependencyRecord(
            dependency_id=dep_id,
            package_name=name,
            version=version,
            ecosystem="npm",
            license_spdx=spdx,
            license_risk=risk,
            vulnerabilities=vulns or [],
            direct=direct,
            reachable=reachable
        )

    def test_classify_license_risk(self):
        self.assertEqual(self.engine.classify_license_risk("MIT"), LicenseRiskLevel.PERMISSIVE)
        self.assertEqual(self.engine.classify_license_risk("Apache-2.0"), LicenseRiskLevel.PERMISSIVE)
        self.assertEqual(self.engine.classify_license_risk("LGPL-3.0"), LicenseRiskLevel.WEAK_COPYLEFT)
        self.assertEqual(self.engine.classify_license_risk("GPL-3.0"), LicenseRiskLevel.STRONG_COPYLEFT)
        self.assertEqual(self.engine.classify_license_risk("AGPL-3.0"), LicenseRiskLevel.STRONG_COPYLEFT)
        self.assertEqual(self.engine.classify_license_risk("PROPRIETARY"), LicenseRiskLevel.PROPRIETARY)
        self.assertEqual(self.engine.classify_license_risk("CUSTOM-UNKNOWN"), LicenseRiskLevel.UNKNOWN)

    def test_classify_license_risk_whitespace_case(self):
        self.assertEqual(self.engine.classify_license_risk("  mit  "), LicenseRiskLevel.PERMISSIVE)
        self.assertEqual(self.engine.classify_license_risk("apache-2.0"), LicenseRiskLevel.PERMISSIVE)
        self.assertEqual(self.engine.classify_license_risk("lgpl-2.1"), LicenseRiskLevel.WEAK_COPYLEFT)

    def test_register_and_get_dependency(self):
        dep = self._create_dep()
        self.engine.register_dependency("proj-1", dep)
        retrieved = self.engine.get_dependency("dep-1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.license_risk, LicenseRiskLevel.PERMISSIVE)

    def test_register_duplicate_raises(self):
        dep = self._create_dep()
        self.engine.register_dependency("proj-1", dep)
        with self.assertRaises(ValueError):
            self.engine.register_dependency("proj-1", dep)

    def test_get_nonexistent_dependency(self):
        self.assertIsNone(self.engine.get_dependency("nonexistent-dep"))

    def test_list_dependencies_empty_project(self):
        deps = self.engine.list_dependencies("empty-project")
        self.assertEqual(len(deps), 0)

    def test_list_multiple_dependencies(self):
        self.engine.register_dependency("p1", self._create_dep("d1", "pkg1"))
        self.engine.register_dependency("p1", self._create_dep("d2", "pkg2"))
        self.engine.register_dependency("p2", self._create_dep("d3", "pkg3"))
        
        p1_deps = self.engine.list_dependencies("p1")
        self.assertEqual(len(p1_deps), 2)
        p2_deps = self.engine.list_dependencies("p2")
        self.assertEqual(len(p2_deps), 1)

    def test_quarantine_and_unquarantine(self):
        dep = self._create_dep()
        self.engine.register_dependency("proj-1", dep)
        self.assertFalse(dep.is_quarantined)

        self.engine.quarantine_dependency("dep-1")
        self.assertTrue(dep.is_quarantined)

        self.engine.unquarantine_dependency("dep-1")
        self.assertFalse(dep.is_quarantined)

    def test_quarantine_nonexistent_raises(self):
        with self.assertRaises(ValueError):
            self.engine.quarantine_dependency("missing-id")

    def test_unquarantine_nonexistent_raises(self):
        with self.assertRaises(ValueError):
            self.engine.unquarantine_dependency("missing-id")

    def test_evaluate_license_compliance_passed(self):
        self.engine.register_dependency("proj-1", self._create_dep("d1", "express", "4.18.2", "MIT"))
        self.engine.register_dependency("proj-1", self._create_dep("d2", "axios", "1.6.0", "Apache-2.0"))

        verdict = self.engine.evaluate_license_compliance("proj-1")
        self.assertTrue(verdict.passed)
        self.assertEqual(len(verdict.disallowed_licenses_found), 0)

    def test_evaluate_license_compliance_failed_strong_copyleft(self):
        self.engine.register_dependency("proj-1", self._create_dep("d1", "express", "4.18.2", "MIT"))
        self.engine.register_dependency("proj-1", self._create_dep("d2", "gpl-tool", "1.0.0", "GPL-3.0"))

        verdict = self.engine.evaluate_license_compliance("proj-1")
        self.assertFalse(verdict.passed)
        self.assertEqual(len(verdict.disallowed_licenses_found), 1)

    def test_evaluate_license_compliance_custom_disallowed(self):
        self.engine.register_dependency("proj-1", self._create_dep("d1", "libA", "1.0", "MIT"))
        self.engine.register_dependency("proj-1", self._create_dep("d2", "libB", "1.0", "Apache-2.0"))

        verdict = self.engine.evaluate_license_compliance("proj-1", disallowed_licenses=["Apache-2.0"])
        self.assertFalse(verdict.passed)
        self.assertEqual(len(verdict.disallowed_licenses_found), 1)

    def test_evaluate_license_compliance_custom_disallowed_risk(self):
        self.engine.register_dependency("proj-1", self._create_dep("d1", "weak-lib", "1.0", "LGPL-2.1"))
        
        # By default WEAK_COPYLEFT is permitted
        v1 = self.engine.evaluate_license_compliance("proj-1")
        self.assertTrue(v1.passed)

        # When WEAK_COPYLEFT is explicitly disallowed
        v2 = self.engine.evaluate_license_compliance("proj-1", disallowed_risks=[LicenseRiskLevel.WEAK_COPYLEFT])
        self.assertFalse(v2.passed)

    def test_evaluate_license_compliance_quarantined_fails(self):
        dep = self._create_dep("d1", "express", "4.18.2", "MIT")
        self.engine.register_dependency("proj-1", dep)
        self.engine.quarantine_dependency("d1")

        verdict = self.engine.evaluate_license_compliance("proj-1")
        self.assertFalse(verdict.passed)
        self.assertIn("express", verdict.quarantined_packages)

    def test_generate_sca_summary_compliant(self):
        self.engine.register_dependency("proj-1", self._create_dep("d1", "pkg1", "1.0", "MIT", direct=True))
        self.engine.register_dependency("proj-1", self._create_dep("d2", "pkg2", "1.0", "Apache-2.0", direct=False))

        summary = self.engine.generate_sca_summary("proj-1")
        self.assertEqual(summary.total_dependencies, 2)
        self.assertEqual(summary.direct_dependencies, 1)
        self.assertEqual(summary.transitive_dependencies, 1)
        self.assertEqual(summary.vulnerable_dependencies, 0)
        self.assertEqual(summary.high_risk_licenses_count, 0)
        self.assertTrue(summary.overall_compliant)

    def test_generate_sca_summary_non_compliant(self):
        self.engine.register_dependency("proj-1", self._create_dep("d1", "pkg1", "1.0", "MIT", direct=True))
        self.engine.register_dependency("proj-1", self._create_dep("d2", "pkg2", "1.0", "Apache-2.0", direct=False))
        self.engine.register_dependency("proj-1", self._create_dep("d3", "pkg3", "1.0", "GPL-3.0", direct=True, vulns=["CVE-2026-001"], reachable=True))

        summary = self.engine.generate_sca_summary("proj-1")
        self.assertEqual(summary.total_dependencies, 3)
        self.assertEqual(summary.direct_dependencies, 2)
        self.assertEqual(summary.transitive_dependencies, 1)
        self.assertEqual(summary.vulnerable_dependencies, 1)
        self.assertEqual(summary.high_risk_licenses_count, 1)
        self.assertFalse(summary.overall_compliant)

    def test_generate_sca_summary_unreachable_vuln_still_compliant(self):
        # Vulnerability exists but is unreachable
        self.engine.register_dependency("proj-1", self._create_dep("d1", "pkg1", "1.0", "MIT", direct=True, vulns=["CVE-2026-002"], reachable=False))
        summary = self.engine.generate_sca_summary("proj-1")
        self.assertEqual(summary.vulnerable_dependencies, 1)
        self.assertTrue(summary.overall_compliant)

    def test_audit_vulnerabilities_zero_threshold(self):
        self.engine.register_dependency("proj-1", self._create_dep("d1", "vuln-pkg", "1.0", "MIT", vulns=["CVE-2026-100", "CVE-2026-101"], reachable=True))
        self.engine.register_dependency("proj-1", self._create_dep("d2", "unreach-pkg", "1.0", "MIT", vulns=["CVE-2026-102"], reachable=False))

        audit = self.engine.audit_vulnerabilities("proj-1", max_allowed_cves=0)
        self.assertFalse(audit["compliant"])
        self.assertEqual(audit["total_cves"], 3)
        self.assertEqual(audit["reachable_cves"], 2)
        self.assertEqual(len(audit["vulnerable_packages"]), 2)

    def test_audit_vulnerabilities_tolerant_threshold(self):
        self.engine.register_dependency("proj-1", self._create_dep("d1", "vuln-pkg", "1.0", "MIT", vulns=["CVE-2026-100"], reachable=True))
        audit = self.engine.audit_vulnerabilities("proj-1", max_allowed_cves=5)
        self.assertTrue(audit["compliant"])
        self.assertEqual(audit["total_cves"], 1)

    def test_audit_vulnerabilities_no_vulns(self):
        self.engine.register_dependency("proj-1", self._create_dep("d1", "safe-pkg", "1.0", "MIT"))
        audit = self.engine.audit_vulnerabilities("proj-1", max_allowed_cves=0)
        self.assertTrue(audit["compliant"])
        self.assertEqual(audit["total_cves"], 0)
        self.assertEqual(audit["reachable_cves"], 0)
        self.assertEqual(len(audit["vulnerable_packages"]), 0)

    def test_pre_classified_risk_preserved(self):
        dep = self._create_dep(spdx="UNKNOWN", risk=LicenseRiskLevel.PROPRIETARY)
        self.engine.register_dependency("proj-1", dep)
        retrieved = self.engine.get_dependency(dep.dependency_id)
        self.assertEqual(retrieved.license_risk, LicenseRiskLevel.PROPRIETARY)

    def test_multiple_projects_isolation(self):
        self.engine.register_dependency("pA", self._create_dep("depA", "pkgA", spdx="GPL-3.0"))
        self.engine.register_dependency("pB", self._create_dep("depB", "pkgB", spdx="MIT"))

        verdictA = self.engine.evaluate_license_compliance("pA")
        verdictB = self.engine.evaluate_license_compliance("pB")

        self.assertFalse(verdictA.passed)
        self.assertTrue(verdictB.passed)

    def test_audit_vulnerability_structure(self):
        self.engine.register_dependency("p1", self._create_dep("d1", "lodash", "4.17.20", direct=True, reachable=True, vulns=["CVE-2021-23337"]))
        audit = self.engine.audit_vulnerabilities("p1")
        pkg = audit["vulnerable_packages"][0]
        self.assertEqual(pkg["package"], "lodash")
        self.assertEqual(pkg["version"], "4.17.20")
        self.assertTrue(pkg["direct"])
        self.assertTrue(pkg["reachable"])
        self.assertIn("CVE-2021-23337", pkg["cves"])

    def test_quarantined_package_causes_sca_summary_failure(self):
        dep = self._create_dep("d1", "pkg1", "1.0", "MIT")
        self.engine.register_dependency("proj-1", dep)
        self.engine.quarantine_dependency("d1")
        summary = self.engine.generate_sca_summary("proj-1")
        self.assertFalse(summary.overall_compliant)

    def test_empty_license_risk_handling(self):
        dep = self._create_dep("d1", "no-license", "1.0", spdx="")
        self.engine.register_dependency("p1", dep)
        self.assertEqual(dep.license_risk, LicenseRiskLevel.UNKNOWN)

if __name__ == "__main__":
    unittest.main()
