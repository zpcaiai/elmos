"""Comprehensive unit tests for CustomerVpcEditionEngine (Batch 38 Skill 1330)."""

import unittest

from elmos_mature_platform.customer_vpc_edition_engine import CustomerVpcEditionEngine
from elmos_mature_platform.types import (
    CloudProvider,
    VpcPeeringStatus,
    CustomerVpcConfig,
    VpcDeploymentVerification,
)


class TestCustomerVpcEditionComprehensive(unittest.TestCase):
    """Test suite for customer VPC edition lifecycle and deployment validation."""

    def setUp(self) -> None:
        self.engine = CustomerVpcEditionEngine()
        self.sample_config = CustomerVpcConfig(
            vpc_id="vpc-cust-001",
            customer_id="cust-enterprise-alpha",
            provider=CloudProvider.AWS,
            cidr_block="10.100.0.0/16",
            private_subnet_ids=["subnet-priv-1a", "subnet-priv-1b"],
            egress_mode="nat_gateway",
            kms_key_arn="arn:aws:kms:us-east-1:123456789012:key/byok-1",
        )

    def test_provision_customer_vpc_success(self) -> None:
        vpc_id = self.engine.provision_customer_vpc(self.sample_config)
        self.assertEqual(vpc_id, "vpc-cust-001")
        retrieved = self.engine.get_vpc_config("vpc-cust-001")
        self.assertIsNotNone(retrieved)
        self.assertFalse(retrieved.is_deployed)
        self.assertTrue(retrieved.created_at)

    def test_provision_customer_vpc_invalid_cidr(self) -> None:
        cfg = CustomerVpcConfig(
            vpc_id="vpc-bad-cidr",
            customer_id="cust-1",
            provider=CloudProvider.AWS,
            cidr_block="999.100.0.0/16",
            private_subnet_ids=["sub-1"],
        )
        with self.assertRaises(ValueError):
            self.engine.provision_customer_vpc(cfg)

    def test_provision_customer_vpc_no_subnets(self) -> None:
        cfg = CustomerVpcConfig(
            vpc_id="vpc-no-subs",
            customer_id="cust-1",
            provider=CloudProvider.GCP,
            cidr_block="10.20.0.0/20",
            private_subnet_ids=[],
        )
        with self.assertRaises(ValueError):
            self.engine.provision_customer_vpc(cfg)

    def test_verify_deployment_success(self) -> None:
        self.engine.provision_customer_vpc(self.sample_config)
        verif = self.engine.verify_deployment(
            vpc_id="vpc-cust-001",
            subnets_reachable=True,
            kms_encrypt_decrypt_ok=True,
            egress_connectivity_ok=True,
        )
        self.assertTrue(verif.passed)
        cfg = self.engine.get_vpc_config("vpc-cust-001")
        self.assertTrue(cfg.is_deployed)

    def test_verify_deployment_failure(self) -> None:
        self.engine.provision_customer_vpc(self.sample_config)
        verif = self.engine.verify_deployment(
            vpc_id="vpc-cust-001",
            subnets_reachable=True,
            kms_encrypt_decrypt_ok=False,  # KMS access failure
            egress_connectivity_ok=True,
        )
        self.assertFalse(verif.passed)
        cfg = self.engine.get_vpc_config("vpc-cust-001")
        self.assertFalse(cfg.is_deployed)

    def test_request_vpc_peering_and_status_update(self) -> None:
        self.engine.provision_customer_vpc(self.sample_config)
        cfg = self.engine.request_vpc_peering("vpc-cust-001", "pcx-abc12345")
        self.assertEqual(cfg.peering_connection_id, "pcx-abc12345")
        self.assertEqual(cfg.peering_status, VpcPeeringStatus.ACTIVE)

        updated = self.engine.update_peering_status("vpc-cust-001", VpcPeeringStatus.EXPIRED)
        self.assertEqual(updated.peering_status, VpcPeeringStatus.EXPIRED)

    def test_update_kms_key(self) -> None:
        self.engine.provision_customer_vpc(self.sample_config)
        new_arn = "arn:aws:kms:us-east-1:123456789012:key/byok-rotated"
        updated = self.engine.update_kms_key("vpc-cust-001", new_arn)
        self.assertEqual(updated.kms_key_arn, new_arn)

    def test_decommission_and_reporting(self) -> None:
        self.engine.provision_customer_vpc(self.sample_config)
        report = self.engine.get_vpc_report()
        self.assertEqual(report["total_vpcs"], 1)
        self.assertEqual(report["deployed_vpcs"], 0)

        decom = self.engine.decommission_vpc("vpc-cust-001")
        self.assertTrue(decom)
        self.assertIsNone(self.engine.get_vpc_config("vpc-cust-001"))


if __name__ == "__main__":
    unittest.main()
