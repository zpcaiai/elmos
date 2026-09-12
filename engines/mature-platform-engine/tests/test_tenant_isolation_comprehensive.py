import unittest
import uuid
from elmos_mature_platform.types import (
    RegionId,
    TenantDescriptor,
    TenantIsolationLevel,
    TenantWorkspaceBinding
)
from elmos_mature_platform.tenant_isolation_engine import TenantIsolationEngine

class TestTenantIsolationComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = TenantIsolationEngine()
        
    def _make_tenant(self, tenant_id, region, status="ACTIVE", cpu=8.0, mem=32.0, storage=100.0, rate=100.0):
        return TenantDescriptor(
            tenant_id=tenant_id,
            name=f"Tenant {tenant_id}",
            edition="enterprise",
            isolation_level=TenantIsolationLevel.CONTAINER_HARDENED,
            residency_region=region,
            kms_key_arn=f"arn:aws:kms:{region.value}:111122223333:key/123",
            status=status,
            cpu_cores_limit=cpu,
            memory_gb_limit=mem,
            storage_gb_limit=storage,
            rate_limit_rps=rate
        )

    # 1. Provisioning tests
    def test_provision_tenant_creates_workspace(self):
        t = self._make_tenant("t1", RegionId.US_EAST_1)
        ws = self.engine.provision_tenant(t)
        self.assertEqual(ws.tenant_id, "t1")
        self.assertTrue(ws.read_only_rootfs)
        self.assertEqual(ws.container_security_profile, "no-new-privileges")
        
    def test_provision_multiple_tenants(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1)
        t2 = self._make_tenant("t2", RegionId.EU_WEST_1)
        self.engine.provision_tenant(t1)
        self.engine.provision_tenant(t2)
        self.assertEqual(len(self.engine.list_tenants()), 2)

    # 2. Boundary / Cross-tenant access tests
    def test_verify_tenant_boundary_allowed(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1)
        self.engine.provision_tenant(t1)
        res = self.engine.verify_tenant_boundary("t1", "t1", "resource_a")
        self.assertTrue(res.allowed)
        
    def test_verify_tenant_boundary_cross_tenant_denied(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1)
        t2 = self._make_tenant("t2", RegionId.US_EAST_1)
        self.engine.provision_tenant(t1)
        self.engine.provision_tenant(t2)
        with self.assertRaises(PermissionError):
            self.engine.verify_tenant_boundary("t1", "t2", "resource_b")
            
    def test_verify_tenant_boundary_tracks_violations(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1)
        t2 = self._make_tenant("t2", RegionId.US_EAST_1)
        self.engine.provision_tenant(t1)
        self.engine.provision_tenant(t2)
        try:
            self.engine.verify_tenant_boundary("t1", "t2", "resource_c")
        except PermissionError:
            pass
        rep = self.engine.get_tenant_isolation_report()
        self.assertEqual(rep["cross_tenant_violations"], 1)

    def test_verify_tenant_boundary_unknown_tenant(self):
        with self.assertRaises(PermissionError):
            self.engine.verify_tenant_boundary("unknown", "unknown", "res")

    # 3. Status tests
    def test_suspended_tenant_denied_access(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1, status="SUSPENDED")
        self.engine.provision_tenant(t1)
        with self.assertRaises(PermissionError):
            self.engine.verify_tenant_boundary("t1", "t1", "res")

    def test_suspend_tenant_action(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1)
        self.engine.provision_tenant(t1)
        self.engine.suspend_tenant("t1")
        with self.assertRaises(PermissionError):
            self.engine.verify_tenant_boundary("t1", "t1", "res")

    # 4. Quota tests
    def test_check_quota_cpu_allowed(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1, cpu=8.0)
        self.engine.provision_tenant(t1)
        self.assertTrue(self.engine.check_quota("t1", "cpu", 4.0))

    def test_check_quota_cpu_exceeded(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1, cpu=8.0)
        self.engine.provision_tenant(t1)
        self.engine.record_usage("t1", cpu=6.0, memory=0, storage=0, egress=0)
        self.assertFalse(self.engine.check_quota("t1", "cpu", 4.0))

    def test_check_quota_memory_allowed(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1, mem=32.0)
        self.engine.provision_tenant(t1)
        self.assertTrue(self.engine.check_quota("t1", "memory", 16.0))

    def test_check_quota_memory_exceeded(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1, mem=32.0)
        self.engine.provision_tenant(t1)
        self.engine.record_usage("t1", cpu=0, memory=20.0, storage=0, egress=0)
        self.assertFalse(self.engine.check_quota("t1", "memory", 16.0))

    def test_check_quota_storage_exceeded(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1, storage=10.0) # 10GB
        self.engine.provision_tenant(t1)
        self.engine.record_usage("t1", cpu=0, memory=0, storage=10*1024*1024*1024, egress=0)
        self.assertFalse(self.engine.check_quota("t1", "storage", 1))

    def test_check_quota_rate_allowed(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1, rate=100.0)
        self.engine.provision_tenant(t1)
        self.assertTrue(self.engine.check_quota("t1", "rate", 50.0))

    def test_check_quota_rate_exceeded(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1, rate=100.0)
        self.engine.provision_tenant(t1)
        self.assertFalse(self.engine.check_quota("t1", "rate", 150.0))

    def test_check_quota_unknown_tenant(self):
        self.assertFalse(self.engine.check_quota("unknown", "cpu", 1.0))

    def test_check_quota_suspended_tenant(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1, status="SUSPENDED", cpu=8.0)
        self.engine.provision_tenant(t1)
        self.assertFalse(self.engine.check_quota("t1", "cpu", 1.0))

    # 5. Usage tests
    def test_record_usage_aggregates(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1)
        self.engine.provision_tenant(t1)
        self.engine.record_usage("t1", cpu=2.0, memory=4.0, storage=1000, egress=500)
        self.engine.record_usage("t1", cpu=1.0, memory=2.0, storage=500, egress=100)
        usage = self.engine.get_usage("t1")
        self.assertEqual(usage.allocated_cpu_cores, 3.0)
        self.assertEqual(usage.allocated_memory_gb, 6.0)
        self.assertEqual(usage.current_storage_bytes, 1500)
        self.assertEqual(usage.period_egress_bytes, 600)
        self.assertEqual(usage.active_runners, 2)

    def test_get_usage_empty(self):
        usage = self.engine.get_usage("unknown")
        self.assertEqual(usage.tenant_id, "unknown")
        self.assertEqual(usage.active_runners, 0)

    # 6. Residency tests
    def test_verify_data_residency_allowed(self):
        t1 = self._make_tenant("t1", RegionId.EU_WEST_1)
        self.engine.provision_tenant(t1)
        self.assertTrue(self.engine.verify_data_residency("t1", RegionId.EU_WEST_1))

    def test_verify_data_residency_denied(self):
        t1 = self._make_tenant("t1", RegionId.EU_WEST_1)
        self.engine.provision_tenant(t1)
        self.assertFalse(self.engine.verify_data_residency("t1", RegionId.US_EAST_1))

    def test_verify_data_residency_tracks_violations(self):
        t1 = self._make_tenant("t1", RegionId.EU_WEST_1)
        self.engine.provision_tenant(t1)
        self.engine.verify_data_residency("t1", RegionId.US_EAST_1)
        rep = self.engine.get_tenant_isolation_report()
        self.assertEqual(rep["residency_violations"], 1)

    def test_verify_data_residency_suspended_tenant(self):
        t1 = self._make_tenant("t1", RegionId.EU_WEST_1, status="SUSPENDED")
        self.engine.provision_tenant(t1)
        self.assertFalse(self.engine.verify_data_residency("t1", RegionId.EU_WEST_1))

    # 7. Container hardening tests
    def test_verify_container_hardening(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1)
        ws = self.engine.provision_tenant(t1)
        checks = self.engine.verify_container_hardening(ws)
        self.assertTrue(checks["read_only_rootfs"])
        self.assertTrue(checks["cgroup_isolated"])
        self.assertTrue(checks["network_isolated"])
        self.assertTrue(checks["no_new_privileges"])

    # 8. Encryption tests
    def test_resolve_encryption_context(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1)
        self.engine.provision_tenant(t1)
        ctx = self.engine.resolve_encryption_context("t1")
        self.assertEqual(ctx["tenant_id"], "t1")
        self.assertEqual(ctx["kms_key_arn"], t1.kms_key_arn)
        self.assertEqual(ctx["isolation_level"], t1.isolation_level.value)

    def test_resolve_encryption_context_unknown_tenant(self):
        with self.assertRaises(ValueError):
            self.engine.resolve_encryption_context("unknown")

    # 9. Report & filtering tests
    def test_list_tenants_filtering(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1, status="ACTIVE")
        t2 = self._make_tenant("t2", RegionId.US_EAST_1, status="SUSPENDED")
        self.engine.provision_tenant(t1)
        self.engine.provision_tenant(t2)
        active = self.engine.list_tenants(status="ACTIVE")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].tenant_id, "t1")

    def test_get_tenant_isolation_report(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1, status="ACTIVE")
        t2 = self._make_tenant("t2", RegionId.US_EAST_1, status="SUSPENDED")
        self.engine.provision_tenant(t1)
        self.engine.provision_tenant(t2)
        try:
            self.engine.verify_tenant_boundary("t1", "t2", "res")
        except PermissionError:
            pass
        self.engine.verify_data_residency("t1", RegionId.EU_WEST_1)
        
        rep = self.engine.get_tenant_isolation_report()
        self.assertEqual(rep["cross_tenant_violations"], 1)
        self.assertEqual(rep["residency_violations"], 1)
        self.assertEqual(rep["access_attempts"], 1)
        self.assertEqual(rep["active_tenants"], 1)
        self.assertEqual(rep["suspended_tenants"], 1)

    def test_terminated_tenant_cleanup(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1, status="TERMINATED")
        self.engine.provision_tenant(t1)
        with self.assertRaises(PermissionError):
            self.engine.verify_tenant_boundary("t1", "t1", "res")
            
    def test_noisy_neighbor_protection(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1, cpu=4.0)
        t2 = self._make_tenant("t2", RegionId.US_EAST_1, cpu=4.0)
        self.engine.provision_tenant(t1)
        self.engine.provision_tenant(t2)
        
        self.engine.record_usage("t1", cpu=4.0, memory=0, storage=0, egress=0)
        self.assertFalse(self.engine.check_quota("t1", "cpu", 1.0))
        self.assertTrue(self.engine.check_quota("t2", "cpu", 1.0))
        
    def test_concurrent_tenant_usage_tracking(self):
        t1 = self._make_tenant("t1", RegionId.US_EAST_1)
        self.engine.provision_tenant(t1)
        for _ in range(5):
            self.engine.record_usage("t1", cpu=1.0, memory=1.0, storage=10, egress=5)
        usage = self.engine.get_usage("t1")
        self.assertEqual(usage.active_runners, 5)
        self.assertEqual(usage.allocated_cpu_cores, 5.0)

if __name__ == '__main__':
    unittest.main()
