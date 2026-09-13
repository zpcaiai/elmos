import unittest
from datetime import datetime, timedelta
from elmos_mature_platform.knowledge_isolation_engine import KnowledgeIsolationEngine
from elmos_mature_platform.types import (
    KnowledgePartition,
    KnowledgeAccessGrant,
    KnowledgeBoundary,
    KnowledgeAccessLevel
)

class TestKnowledgeIsolationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = KnowledgeIsolationEngine()
        
    def _create_test_partition(self, p_id="p1", boundary=KnowledgeBoundary.TENANT, owner="t1"):
        return KnowledgePartition(
            partition_id=p_id,
            name=f"Test Partition {p_id}",
            boundary=boundary,
            owner=owner
        )

    def test_create_partition_success(self):
        p = self._create_test_partition()
        res = self.engine.create_partition(p)
        self.assertEqual(res, "p1")
        self.assertIn("p1", self.engine._partitions)

    def test_create_partition_duplicate_fails(self):
        p = self._create_test_partition()
        self.engine.create_partition(p)
        with self.assertRaises(ValueError):
            self.engine.create_partition(p)

    def test_create_partition_sets_created_at(self):
        p = self._create_test_partition()
        self.engine.create_partition(p)
        self.assertTrue(bool(self.engine._partitions["p1"].created_at))

    def test_grant_access_success(self):
        self.engine.create_partition(self._create_test_partition())
        grant = KnowledgeAccessGrant(
            grant_id="g1",
            partition_id="p1",
            principal="user1",
            access_level=KnowledgeAccessLevel.READ
        )
        res = self.engine.grant_access(grant)
        self.assertEqual(res, "g1")
        self.assertIn("g1", self.engine._grants)

    def test_grant_access_partition_not_found(self):
        grant = KnowledgeAccessGrant(
            grant_id="g1",
            partition_id="p1",
            principal="user1",
            access_level=KnowledgeAccessLevel.READ
        )
        with self.assertRaises(ValueError):
            self.engine.grant_access(grant)

    def test_grant_access_revoked_fails(self):
        self.engine.create_partition(self._create_test_partition())
        grant = KnowledgeAccessGrant(
            grant_id="g1",
            partition_id="p1",
            principal="user1",
            access_level=KnowledgeAccessLevel.READ,
            revoked=True
        )
        with self.assertRaises(ValueError):
            self.engine.grant_access(grant)

    def test_revoke_access_success(self):
        self.engine.create_partition(self._create_test_partition())
        grant = KnowledgeAccessGrant(grant_id="g1", partition_id="p1", principal="u1", access_level=KnowledgeAccessLevel.READ)
        self.engine.grant_access(grant)
        revoked_grant = self.engine.revoke_access("g1")
        self.assertTrue(revoked_grant.revoked)
        self.assertTrue(self.engine._grants["g1"].revoked)

    def test_revoke_access_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.revoke_access("nonexistent")

    def test_check_access_none_by_default(self):
        self.engine.create_partition(self._create_test_partition())
        level = self.engine.check_access("user1", "p1")
        self.assertEqual(level, KnowledgeAccessLevel.NONE)

    def test_check_access_public_is_read(self):
        self.engine.create_partition(self._create_test_partition("p_pub", KnowledgeBoundary.PUBLIC))
        level = self.engine.check_access("user1", "p_pub")
        self.assertEqual(level, KnowledgeAccessLevel.READ)

    def test_check_access_public_with_write_grant(self):
        self.engine.create_partition(self._create_test_partition("p_pub", KnowledgeBoundary.PUBLIC))
        grant = KnowledgeAccessGrant(grant_id="g1", partition_id="p_pub", principal="u1", access_level=KnowledgeAccessLevel.WRITE)
        self.engine.grant_access(grant)
        level = self.engine.check_access("u1", "p_pub")
        self.assertEqual(level, KnowledgeAccessLevel.WRITE)

    def test_check_access_explicit_grant(self):
        self.engine.create_partition(self._create_test_partition())
        grant = KnowledgeAccessGrant(grant_id="g1", partition_id="p1", principal="u1", access_level=KnowledgeAccessLevel.ADMIN)
        self.engine.grant_access(grant)
        level = self.engine.check_access("u1", "p1")
        self.assertEqual(level, KnowledgeAccessLevel.ADMIN)

    def test_check_access_revoked_grant_ignored(self):
        self.engine.create_partition(self._create_test_partition())
        grant = KnowledgeAccessGrant(grant_id="g1", partition_id="p1", principal="u1", access_level=KnowledgeAccessLevel.READ)
        self.engine.grant_access(grant)
        self.engine.revoke_access("g1")
        level = self.engine.check_access("u1", "p1")
        self.assertEqual(level, KnowledgeAccessLevel.NONE)

    def test_check_access_expired_grant_ignored(self):
        self.engine.create_partition(self._create_test_partition())
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        grant = KnowledgeAccessGrant(grant_id="g1", partition_id="p1", principal="u1", access_level=KnowledgeAccessLevel.READ, expires_at=past)
        self.engine.grant_access(grant)
        level = self.engine.check_access("u1", "p1")
        self.assertEqual(level, KnowledgeAccessLevel.NONE)

    def test_check_access_upgrade_level(self):
        self.engine.create_partition(self._create_test_partition())
        grant1 = KnowledgeAccessGrant(grant_id="g1", partition_id="p1", principal="u1", access_level=KnowledgeAccessLevel.READ)
        grant2 = KnowledgeAccessGrant(grant_id="g2", partition_id="p1", principal="u1", access_level=KnowledgeAccessLevel.WRITE)
        self.engine.grant_access(grant1)
        self.engine.grant_access(grant2)
        level = self.engine.check_access("u1", "p1")
        self.assertEqual(level, KnowledgeAccessLevel.WRITE)

    def test_check_access_partition_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.check_access("u1", "nonexistent")

    def test_add_item_success(self):
        self.engine.create_partition(self._create_test_partition())
        p = self.engine.add_item("p1", "i1", 100)
        self.assertEqual(p.item_count, 1)
        self.assertEqual(p.size_bytes, 100)
        self.assertIn("i1", self.engine._items["p1"])

    def test_add_item_partition_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.add_item("nonexistent", "i1", 100)

    def test_add_item_duplicate_fails(self):
        self.engine.create_partition(self._create_test_partition())
        self.engine.add_item("p1", "i1", 100)
        with self.assertRaises(ValueError):
            self.engine.add_item("p1", "i1", 50)

    def test_remove_item_success(self):
        self.engine.create_partition(self._create_test_partition())
        self.engine.add_item("p1", "i1", 100)
        self.engine.add_item("p1", "i2", 200)
        p = self.engine.remove_item("p1", "i1", 100)
        self.assertEqual(p.item_count, 1)
        self.assertEqual(p.size_bytes, 200)
        self.assertNotIn("i1", self.engine._items["p1"])

    def test_remove_item_partition_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.remove_item("nonexistent", "i1", 100)

    def test_remove_item_not_found(self):
        self.engine.create_partition(self._create_test_partition())
        with self.assertRaises(ValueError):
            self.engine.remove_item("p1", "i1", 100)

    def test_get_partition_items(self):
        self.engine.create_partition(self._create_test_partition())
        self.engine.add_item("p1", "i1", 10)
        self.engine.add_item("p1", "i2", 20)
        items = self.engine.get_partition_items("p1")
        self.assertEqual(set(items), {"i1", "i2"})

    def test_get_partition_items_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_partition_items("p1")

    def test_get_cross_boundary_leaks_none(self):
        self.engine.create_partition(self._create_test_partition("p1", KnowledgeBoundary.TENANT, "t1"))
        self.engine.grant_access(KnowledgeAccessGrant(grant_id="g1", partition_id="p1", principal="u1", access_level=KnowledgeAccessLevel.READ))
        leaks = self.engine.get_cross_boundary_leaks("u1")
        self.assertEqual(len(leaks), 0)

    def test_get_cross_boundary_leaks_found(self):
        self.engine.create_partition(self._create_test_partition("p1", KnowledgeBoundary.TENANT, "t1"))
        self.engine.create_partition(self._create_test_partition("p2", KnowledgeBoundary.TENANT, "t2"))
        
        self.engine.grant_access(KnowledgeAccessGrant(grant_id="g1", partition_id="p1", principal="u1", access_level=KnowledgeAccessLevel.READ))
        self.engine.grant_access(KnowledgeAccessGrant(grant_id="g2", partition_id="p2", principal="u1", access_level=KnowledgeAccessLevel.READ))
        
        leaks = self.engine.get_cross_boundary_leaks("u1")
        self.assertEqual(len(leaks), 1)
        self.assertEqual(leaks[0]["principal"], "u1")
        self.assertTrue(leaks[0]["partition_id"] in ["p1", "p2"])

    def test_get_partition_stats(self):
        self.engine.create_partition(self._create_test_partition("p1", KnowledgeBoundary.TENANT))
        self.engine.create_partition(self._create_test_partition("p2", KnowledgeBoundary.TENANT))
        self.engine.create_partition(self._create_test_partition("p3", KnowledgeBoundary.PUBLIC))
        
        self.engine.add_item("p1", "i1", 10)
        self.engine.add_item("p2", "i2", 20)
        
        stats = self.engine.get_partition_stats()
        self.assertEqual(stats[KnowledgeBoundary.TENANT.value]["count"], 2)
        self.assertEqual(stats[KnowledgeBoundary.TENANT.value]["total_items"], 2)
        self.assertEqual(stats[KnowledgeBoundary.TENANT.value]["total_size"], 30)
        self.assertEqual(stats[KnowledgeBoundary.PUBLIC.value]["count"], 1)
        
    def test_get_access_audit(self):
        self.engine.create_partition(self._create_test_partition())
        self.engine.grant_access(KnowledgeAccessGrant(grant_id="g1", partition_id="p1", principal="u1", access_level=KnowledgeAccessLevel.READ))
        self.engine.grant_access(KnowledgeAccessGrant(grant_id="g2", partition_id="p1", principal="u2", access_level=KnowledgeAccessLevel.WRITE))
        
        audit = self.engine.get_access_audit("p1")
        self.assertEqual(len(audit), 2)
        
    def test_get_access_audit_partition_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_access_audit("p1")

    def test_get_expired_grants(self):
        self.engine.create_partition(self._create_test_partition())
        future = (datetime.utcnow() + timedelta(days=1)).isoformat()
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        
        self.engine.grant_access(KnowledgeAccessGrant(grant_id="g1", partition_id="p1", principal="u1", access_level=KnowledgeAccessLevel.READ, expires_at=future))
        self.engine.grant_access(KnowledgeAccessGrant(grant_id="g2", partition_id="p1", principal="u2", access_level=KnowledgeAccessLevel.WRITE, expires_at=past))
        
        expired = self.engine.get_expired_grants()
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0].grant_id, "g2")

    def test_get_isolation_report(self):
        p1 = self._create_test_partition("p1", KnowledgeBoundary.TENANT, "t1")
        p1.encrypted = True
        self.engine.create_partition(p1)
        
        p2 = self._create_test_partition("p2", KnowledgeBoundary.TENANT, "t2")
        self.engine.create_partition(p2)
        
        self.engine.grant_access(KnowledgeAccessGrant(grant_id="g1", partition_id="p1", principal="u1", access_level=KnowledgeAccessLevel.READ))
        self.engine.grant_access(KnowledgeAccessGrant(grant_id="g2", partition_id="p2", principal="u1", access_level=KnowledgeAccessLevel.READ))
        
        report = self.engine.get_isolation_report()
        self.assertEqual(report["encrypted_percentage"], 50.0)
        self.assertEqual(report["total_access_grants"], 2)
        self.assertEqual(len(report["leaks_detected"]), 1)
        
    def test_cross_boundary_leaks_ignores_revoked(self):
        self.engine.create_partition(self._create_test_partition("p1", KnowledgeBoundary.TENANT, "t1"))
        self.engine.create_partition(self._create_test_partition("p2", KnowledgeBoundary.TENANT, "t2"))
        
        self.engine.grant_access(KnowledgeAccessGrant(grant_id="g1", partition_id="p1", principal="u1", access_level=KnowledgeAccessLevel.READ))
        self.engine.grant_access(KnowledgeAccessGrant(grant_id="g2", partition_id="p2", principal="u1", access_level=KnowledgeAccessLevel.READ))
        self.engine.revoke_access("g2")
        
        leaks = self.engine.get_cross_boundary_leaks("u1")
        self.assertEqual(len(leaks), 0)

if __name__ == '__main__':
    unittest.main()
