"""Comprehensive test suite for AirGappedEditionEngine (Batch 38 - Skill 1333)."""

import unittest
from datetime import datetime, timezone

from elmos_mature_platform.air_gapped_edition_engine import AirGappedEditionEngine
from elmos_mature_platform.types import (
    AirgapComplianceCheck,
    AirgapEditionDeployment,
    AirgapIsolationStatus,
    AirgapTransferMedium,
)


class TestAirGappedEditionComprehensive(unittest.TestCase):
    """Rigorous tests covering isolation audits, offline licensing, and transfer mediums."""

    def setUp(self) -> None:
        self.engine = AirGappedEditionEngine()

    def test_register_deployment_success(self) -> None:
        dep = AirgapEditionDeployment(
            deployment_id="",
            customer_id="cust-gov-01",
            site_name="Underground Facility Alpha",
            version="v2.5.0",
            allowed_transfer_mediums=[AirgapTransferMedium.OPTICAL_DISC, AirgapTransferMedium.DATA_DIODE],
        )
        dep_id = self.engine.register_deployment(dep)
        self.assertTrue(dep_id.startswith("airgap-"))

        retrieved = self.engine.get_deployment(dep_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.customer_id, "cust-gov-01")
        self.assertEqual(retrieved.isolation_status, AirgapIsolationStatus.ISOLATED)
        self.assertTrue(retrieved.network_interfaces_disabled)

    def test_register_deployment_missing_fields(self) -> None:
        dep = AirgapEditionDeployment(
            deployment_id="",
            customer_id="",
            site_name="",
            version="v1.0.0",
        )
        with self.assertRaises(ValueError):
            self.engine.register_deployment(dep)

        dep2 = AirgapEditionDeployment(
            deployment_id="",
            customer_id="cust-01",
            site_name="Site 1",
            version="",
        )
        with self.assertRaises(ValueError):
            self.engine.register_deployment(dep2)

    def test_record_compliance_check_passed(self) -> None:
        dep_id = self.engine.register_deployment(
            AirgapEditionDeployment(
                deployment_id="dep-air-01",
                customer_id="cust-01",
                site_name="Site 1",
                version="v1.0.0",
            )
        )
        check = AirgapComplianceCheck(
            check_id="chk-01",
            name="Physical Perimeter Inspection",
            passed=True,
            details="Perimeter secure, no unauthorized wireless transmitters detected.",
        )
        rec = self.engine.record_compliance_check(dep_id, check)
        self.assertEqual(rec.check_id, "chk-01")
        self.assertTrue(rec.passed)

        audit = self.engine.audit_isolation(dep_id)
        self.assertEqual(audit["isolation_status"], "isolated")
        self.assertEqual(audit["compliance_pct"], 100.0)

    def test_record_compliance_check_degraded_and_breached(self) -> None:
        dep_id = self.engine.register_deployment(
            AirgapEditionDeployment(
                deployment_id="dep-air-02",
                customer_id="cust-02",
                site_name="Site 2",
                version="v1.0.0",
            )
        )
        # Non-breach failure -> DEGRADED
        check_fail = AirgapComplianceCheck(
            check_id="chk-soft",
            name="Backup USB Vault Audit",
            passed=False,
            details="Vault log missing one signature.",
        )
        self.engine.record_compliance_check(dep_id, check_fail)
        dep = self.engine.get_deployment(dep_id)
        self.assertEqual(dep.isolation_status, AirgapIsolationStatus.DEGRADED)

        # Critical failure -> BREACHED
        check_breach = AirgapComplianceCheck(
            check_id="chk-hard",
            name="Wireless RF Leak Detection",
            passed=False,
            details="Active 2.4GHz beacon detected in server room.",
        )
        self.engine.record_compliance_check(dep_id, check_breach)
        self.assertEqual(dep.isolation_status, AirgapIsolationStatus.BREACHED)

    def test_offline_licensing_lifecycle(self) -> None:
        dep_id = self.engine.register_deployment(
            AirgapEditionDeployment(
                deployment_id="dep-air-03",
                customer_id="cust-03",
                site_name="Site 3",
                version="v1.0.0",
            )
        )
        with self.assertRaises(ValueError):
            self.engine.install_offline_license(dep_id, "short-key", "2027-01-01")

        valid_token = "ELMOS-AIRGAP-KEY-2026-SECURE-CRYPTO-SIGNATURE-TOKEN-XYZ"
        success = self.engine.install_offline_license(dep_id, valid_token, "2027-12-31")
        self.assertTrue(success)

        dep = self.engine.get_deployment(dep_id)
        self.assertTrue(dep.offline_license_valid)
        self.assertEqual(dep.license_expires_at, "2027-12-31")

        # Revoke
        revoked = self.engine.revoke_offline_license(dep_id)
        self.assertTrue(revoked)
        self.assertFalse(dep.offline_license_valid)

    def test_attach_airgap_bundle_allowed_vs_forbidden_medium(self) -> None:
        dep_id = self.engine.register_deployment(
            AirgapEditionDeployment(
                deployment_id="dep-air-04",
                customer_id="cust-04",
                site_name="Site 4",
                version="v1.0.0",
                allowed_transfer_mediums=[AirgapTransferMedium.DATA_DIODE],
            )
        )

        # Forbidden medium
        with self.assertRaises(ValueError):
            self.engine.attach_airgap_bundle(
                dep_id, "bundle-update-01", AirgapTransferMedium.SECURE_USB
            )

        # Allowed medium
        dep = self.engine.attach_airgap_bundle(
            dep_id, "bundle-update-01", AirgapTransferMedium.DATA_DIODE
        )
        self.assertIn("bundle-update-01", dep.active_bundle_ids)

    def test_fleet_report(self) -> None:
        self.engine.register_deployment(
            AirgapEditionDeployment(
                deployment_id="dep-01", customer_id="c1", site_name="s1", version="v1"
            )
        )
        self.engine.register_deployment(
            AirgapEditionDeployment(
                deployment_id="dep-02", customer_id="c2", site_name="s2", version="v1"
            )
        )
        report = self.engine.get_airgap_fleet_report()
        self.assertEqual(report["total_deployments"], 2)
        self.assertEqual(report["licensed_count"], 2)


if __name__ == "__main__":
    unittest.main()
