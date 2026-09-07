"""Unit tests for MultiTier CAS Cache Manager & Bloom Filter."""

import unittest
from elmos_build_cache.cas_cache_manager import (
    MultiTierCasCacheManager,
    SimpleBloomFilter,
    get_cas_manager,
)


class TestCasCacheManager(unittest.TestCase):

    def setUp(self):
        self.mgr = MultiTierCasCacheManager(max_l1_items=5)
        self.bloom = SimpleBloomFilter(size=1024)

    def test_bloom_filter_membership(self):
        self.bloom.add("key_alpha")
        self.assertTrue(self.bloom.contains("key_alpha"))
        self.assertFalse(self.bloom.contains("non_existent_key_xyz_12345"))

    def test_cas_put_get(self):
        key = "unit_test_action_key_1"
        payload = b"binary_code_compiled_bytecode"
        digest = self.mgr.put(key, payload, {"target": "csharp"})
        self.assertIsNotNone(digest)

        fetched = self.mgr.get(key)
        self.assertEqual(fetched, payload)

    def test_cas_inspect_and_purge(self):
        stats = self.mgr.inspect_stats()
        self.assertEqual(stats["status"], "HEALTHY")
        self.assertGreater(stats["total_cached_entries"], 0)
        self.assertGreater(stats["hit_ratio"], 0.0)

        purge_res = self.mgr.purge()
        self.assertEqual(purge_res["status"], "PURGED_SUCCESS")
        self.assertEqual(len(self.mgr._l1_cache), 0)

    def test_get_cas_manager_singleton(self):
        mgr1 = get_cas_manager()
        mgr2 = get_cas_manager()
        self.assertIs(mgr1, mgr2)


if __name__ == "__main__":
    unittest.main()
