"""Comprehensive unit tests for SelfHostedEditionEngine (Batch 38 Skill 1331)."""

import hashlib
import unittest

from elmos_mature_platform.self_hosted_edition_engine import SelfHostedEditionEngine
from elmos_mature_platform.types import (
    SelfHostedPackagingType,
    SelfHostedLicenseCheckStatus,
    SelfHostedEditionConfig,
    SelfHostedInstallationVerification,
)


class TestSelfHostedEditionComprehensive(unittest.TestCase):
    """Test suite for self-hosted enterprise deployments and offline licensing."""

    def setUp(self) -> None:
        self.engine = SelfHostedEditionEngine()
        payload = "ELMOS-SH-CUST1-UNLIMITED"
        chk = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8].upper()
        self.valid_key = f"{payload}-{chk}"

        self.sample_config = SelfHostedEditionConfig(
            install_id="sh-inst-001",
            customer_id="cust-enterprise-corp",
            packaging=SelfHostedPackagingType.HELM,
            server_hostname="k8s.internal.corp.com",
            license_key=self.valid_key,
            telemetry_opt_in=True,
            airgap_mode=False,
            installed_version="2.1.0",
        )

    def test_register_installation_valid_license(self) -> None:
        inst_id = self.engine.register_installation(self.sample_config)
        self.assertEqual(inst_id, "sh-inst-001")
        cfg = self.engine.get_installation("sh-inst-001")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.license_status, SelfHostedLicenseCheckStatus.VALID)
        self.assertTrue(cfg.telemetry_opt_in)

    def test_airgap_mode_forces_telemetry_off(self) -> None:
        self.sample_config.airgap_mode = True
        self.sample_config.telemetry_opt_in = True  # User asked for opt-in
        self.engine.register_installation(self.sample_config)
        cfg = self.engine.get_installation("sh-inst-001")
        # Must be forced to False in airgap mode
        self.assertFalse(cfg.telemetry_opt_in)

    def test_tampered_and_expired_license_key(self) -> None:
        tampered_cfg = SelfHostedEditionConfig(
            install_id="sh-bad-1",
            customer_id="cust-2",
            packaging=SelfHostedPackagingType.DOCKER_COMPOSE,
            server_hostname="srv1.local",
            license_key="ELMOS-SH-TAMPERED-BADCHECK",
        )
        self.engine.register_installation(tampered_cfg)
        cfg = self.engine.get_installation("sh-bad-1")
        self.assertEqual(cfg.license_status, SelfHostedLicenseCheckStatus.TAMPERED)

        expired_cfg = SelfHostedEditionConfig(
            install_id="sh-bad-2",
            customer_id="cust-3",
            packaging=SelfHostedPackagingType.RPM_DEB,
            server_hostname="srv2.local",
            license_key="ELMOS-SH-EXPIRED-KEY-0000",
        )
        self.engine.register_installation(expired_cfg)
        cfg2 = self.engine.get_installation("sh-bad-2")
        self.assertEqual(cfg2.license_status, SelfHostedLicenseCheckStatus.EXPIRED)

    def test_verify_installation_success(self) -> None:
        self.engine.register_installation(self.sample_config)
        verif = self.engine.verify_installation(
            install_id="sh-inst-001",
            database_connected=True,
            redis_connected=True,
            workers_healthy=True,
        )
        self.assertTrue(verif.passed)
        self.assertTrue(verif.license_valid)

    def test_verify_installation_failure_on_unhealthy_component(self) -> None:
        self.engine.register_installation(self.sample_config)
        verif = self.engine.verify_installation(
            install_id="sh-inst-001",
            database_connected=True,
            redis_connected=False,  # Redis down
            workers_healthy=True,
        )
        self.assertFalse(verif.passed)

    def test_update_license_and_upgrade_version(self) -> None:
        self.engine.register_installation(self.sample_config)
        updated = self.engine.upgrade_version("sh-inst-001", "2.2.0")
        self.assertEqual(updated.installed_version, "2.2.0")

        new_payload = "ELMOS-SH-RENEWED-2027"
        new_chk = hashlib.sha256(new_payload.encode("utf-8")).hexdigest()[:8].upper()
        new_key = f"{new_payload}-{new_chk}"
        lic_updated = self.engine.update_license("sh-inst-001", new_key)
        self.assertEqual(lic_updated.license_status, SelfHostedLicenseCheckStatus.VALID)

    def test_installation_reporting(self) -> None:
        self.engine.register_installation(self.sample_config)
        report = self.engine.get_installation_report()
        self.assertEqual(report["total_installations"], 1)
        self.assertEqual(report["by_packaging"]["helm"], 1)
        self.assertEqual(report["valid_license_rate_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
