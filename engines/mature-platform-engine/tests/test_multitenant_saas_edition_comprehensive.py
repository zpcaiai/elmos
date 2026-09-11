"""Comprehensive tests for MultitenantSaasEditionEngine (Batch 38 - Skill 1327)."""

import unittest

from elmos_mature_platform.multitenant_saas_edition_engine import (
    MultitenantSaasEditionEngine,
)
from elmos_mature_platform.types import (
    SaasTenantTier,
    TenantIsolationMode,
)


class TestMultitenantSaasEditionComprehensive(unittest.TestCase):
    """Test suite verifying multitenant SaaS cluster quotas, provisioning, and isolation."""

    def setUp(self):
        self.engine = MultitenantSaasEditionEngine()
        self.cluster = self.engine.create_cluster(
            cluster_id="us-east-cluster-01",
            max_tenants=5,
            total_storage_gb=1000.0,
        )

    def test_create_cluster_and_duplicate_error(self):
        """Verify cluster creation and duplicate cluster prevention."""
        self.assertEqual(self.cluster.cluster_id, "us-east-cluster-01")
        self.assertEqual(self.cluster.active_tenant_count, 0)

        with self.assertRaises(ValueError):
            self.engine.create_cluster("us-east-cluster-01")

    def test_provision_tenant_standard_tier(self):
        """Verify provisioning standard tier tenant with defaults."""
        tenant = self.engine.provision_tenant(
            cluster_id="us-east-cluster-01",
            name="Alpha Corp",
            tier=SaasTenantTier.STANDARD,
        )
        self.assertTrue(tenant.tenant_id.startswith("tnt-"))
        self.assertEqual(tenant.name, "Alpha Corp")
        self.assertEqual(tenant.tier, SaasTenantTier.STANDARD)
        self.assertEqual(tenant.isolation_mode, TenantIsolationMode.POOLED)
        self.assertEqual(tenant.storage_quota_gb, 50.0)
        self.assertEqual(tenant.rps_limit, 100)
        self.assertFalse(tenant.is_suspended)

        # Cluster usage updated
        cluster = self.engine.get_cluster_quota("us-east-cluster-01")
        self.assertEqual(cluster.active_tenant_count, 1)
        self.assertEqual(cluster.allocated_storage_gb, 50.0)

    def test_custom_domain_validation_by_tier(self):
        """Verify custom domains are rejected on free/standard and allowed on premium/enterprise."""
        with self.assertRaises(ValueError):
            self.engine.provision_tenant(
                "us-east-cluster-01",
                "Beta Corp",
                tier=SaasTenantTier.STANDARD,
                custom_domain="beta.example.com",
            )

        premium_tenant = self.engine.provision_tenant(
            "us-east-cluster-01",
            "Gamma Corp",
            tier=SaasTenantTier.PREMIUM,
            custom_domain="gamma.example.com",
        )
        self.assertEqual(premium_tenant.custom_domain, "gamma.example.com")

    def test_cluster_capacity_exhaustion(self):
        """Verify cluster rejects provisioning when max tenants capacity is hit."""
        small_cluster = self.engine.create_cluster("tiny-cluster", max_tenants=1, total_storage_gb=100.0)
        self.engine.provision_tenant("tiny-cluster", "T1")

        with self.assertRaises(ValueError):
            self.engine.provision_tenant("tiny-cluster", "T2")

    def test_upgrade_tier(self):
        """Verify tenant tier upgrade reallocates cluster storage quota."""
        tenant = self.engine.provision_tenant("us-east-cluster-01", "Delta Corp", tier=SaasTenantTier.STANDARD)
        upgraded = self.engine.upgrade_tier(tenant.tenant_id, new_tier=SaasTenantTier.PREMIUM)

        self.assertEqual(upgraded.tier, SaasTenantTier.PREMIUM)
        self.assertEqual(upgraded.storage_quota_gb, 250.0)
        self.assertEqual(upgraded.isolation_mode, TenantIsolationMode.HYBRID)

        cluster = self.engine.get_cluster_quota("us-east-cluster-01")
        self.assertEqual(cluster.allocated_storage_gb, 250.0)

    def test_suspend_reactivate_and_storage_quota_breach(self):
        """Verify tenant suspension, reactivation, and auto-suspension on storage breach."""
        tenant = self.engine.provision_tenant("us-east-cluster-01", "Epsilon Corp", tier=SaasTenantTier.FREE)
        self.assertFalse(tenant.is_suspended)

        # Manual suspension
        self.engine.suspend_tenant(tenant.tenant_id)
        self.assertTrue(tenant.is_suspended)

        # Reactivation
        self.engine.reactivate_tenant(tenant.tenant_id)
        self.assertFalse(tenant.is_suspended)

        # Storage consumption beyond 5GB quota causes auto-suspension
        self.engine.update_storage_usage(tenant.tenant_id, 6.5)
        self.assertTrue(tenant.is_suspended)

    def test_get_cluster_utilization(self):
        """Verify cluster utilization aggregates tenant counts and storage percentages."""
        self.engine.provision_tenant("us-east-cluster-01", "T1", SaasTenantTier.STANDARD)
        self.engine.provision_tenant("us-east-cluster-01", "T2", SaasTenantTier.FREE)

        util = self.engine.get_cluster_utilization("us-east-cluster-01")
        self.assertEqual(util["active_tenant_count"], 2)
        self.assertEqual(util["allocated_storage_gb"], 55.0)
        self.assertAlmostEqual(util["storage_allocation_pct"], 5.5, places=1)
        self.assertEqual(util["tier_distribution"][SaasTenantTier.STANDARD.value], 1)


if __name__ == "__main__":
    unittest.main()
