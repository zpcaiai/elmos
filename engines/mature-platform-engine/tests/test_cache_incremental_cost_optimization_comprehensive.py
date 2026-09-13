"""Comprehensive test suite for CacheIncrementalCostOptimizationEngine (Batch 44 - Skill 1469)."""

import unittest
from datetime import datetime, timezone

from elmos_mature_platform.cache_incremental_cost_optimization_engine import CacheIncrementalCostOptimizationEngine
from elmos_mature_platform.types import (
    CacheCostOptimizationRecommendation,
    CachePartitionMetric,
    CacheStorageTier,
)


class TestCacheIncrementalCostOptimizationComprehensive(unittest.TestCase):
    """Rigorous unit testing for CacheIncrementalCostOptimizationEngine."""

    def setUp(self) -> None:
        self.engine = CacheIncrementalCostOptimizationEngine()

    def test_register_partition_success(self) -> None:
        metric = CachePartitionMetric(
            partition_id="part-100",
            tier=CacheStorageTier.DISTRIBUTED_REDIS,
            cost_per_month_usd=450.0,
            saved_compute_cost_usd=2500.0,
        )
        pid = self.engine.register_partition(metric)
        self.assertEqual(pid, "part-100")
        fetched = self.engine.get_partition("part-100")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.tier, CacheStorageTier.DISTRIBUTED_REDIS)
        self.assertEqual(fetched.hits, 0)
        self.assertEqual(fetched.misses, 0)

    def test_register_partition_auto_generates_id(self) -> None:
        metric = CachePartitionMetric(
            partition_id="",
            tier=CacheStorageTier.LOCAL_MEMORY,
        )
        pid = self.engine.register_partition(metric)
        self.assertTrue(pid.startswith("part-"))

    def test_record_access_hits_and_misses(self) -> None:
        metric = CachePartitionMetric(
            partition_id="part-rec",
            tier=CacheStorageTier.DISTRIBUTED_REDIS,
        )
        self.engine.register_partition(metric)

        p1 = self.engine.record_access("part-rec", hit=True, bytes_transferred=1024)
        self.assertEqual(p1.hits, 1)
        self.assertEqual(p1.misses, 0)
        self.assertEqual(p1.bytes_stored, 1024)

        p2 = self.engine.record_access("part-rec", hit=False, bytes_transferred=512)
        self.assertEqual(p2.hits, 1)
        self.assertEqual(p2.misses, 1)
        self.assertEqual(p2.bytes_stored, 1024)  # max preserved

    def test_record_access_nonexistent_partition_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.record_access("missing-part", hit=True)

    def test_analyze_optimization_evict_cold_entries(self) -> None:
        metric = CachePartitionMetric(
            partition_id="part-cold",
            tier=CacheStorageTier.DISTRIBUTED_REDIS,
            hits=5,
            misses=95,  # hit rate 5% (<15%)
            bytes_stored=60000,  # > 50000
            cost_per_month_usd=100.0,
        )
        self.engine.register_partition(metric)
        rec = self.engine.analyze_optimization("part-cold")
        self.assertEqual(rec.action, "evict_cold_entries")
        self.assertEqual(rec.estimated_monthly_savings_usd, 65.0)

    def test_analyze_optimization_promote_to_redis(self) -> None:
        metric = CachePartitionMetric(
            partition_id="part-s3-hot",
            tier=CacheStorageTier.S3_OBJECT_CACHE,
            hits=85,
            misses=15,  # hit rate 85% (>75%)
            bytes_stored=10000,
            saved_compute_cost_usd=2000.0,
        )
        self.engine.register_partition(metric)
        rec = self.engine.analyze_optimization("part-s3-hot")
        self.assertEqual(rec.action, "promote_to_redis")
        self.assertEqual(rec.estimated_monthly_savings_usd, 500.0)
        self.assertEqual(rec.projected_hit_rate_impact_pct, 10.0)

    def test_analyze_optimization_compress_partition(self) -> None:
        metric = CachePartitionMetric(
            partition_id="part-mem-large",
            tier=CacheStorageTier.LOCAL_MEMORY,
            hits=50,
            misses=50,  # hit rate 50%
            bytes_stored=600000,  # > 500000
            cost_per_month_usd=200.0,
        )
        self.engine.register_partition(metric)
        rec = self.engine.analyze_optimization("part-mem-large")
        self.assertEqual(rec.action, "compress_partition")
        self.assertEqual(rec.estimated_monthly_savings_usd, 80.0)

    def test_analyze_optimization_maintain_current_tier(self) -> None:
        metric = CachePartitionMetric(
            partition_id="part-nominal",
            tier=CacheStorageTier.DISTRIBUTED_REDIS,
            hits=50,
            misses=50,
            bytes_stored=1000,
            cost_per_month_usd=50.0,
        )
        self.engine.register_partition(metric)
        rec = self.engine.analyze_optimization("part-nominal")
        self.assertEqual(rec.action, "maintain_current_tier")
        self.assertEqual(rec.estimated_monthly_savings_usd, 0.0)

    def test_analyze_optimization_missing_partition_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.analyze_optimization("unknown-id")

    def test_get_optimization_report(self) -> None:
        rep_empty = self.engine.get_optimization_report()
        self.assertEqual(rep_empty["total_partitions"], 0)
        self.assertEqual(rep_empty["total_monthly_cache_cost_usd"], 0.0)

        p1 = CachePartitionMetric(
            partition_id="p1",
            tier=CacheStorageTier.DISTRIBUTED_REDIS,
            hits=5, misses=95, bytes_stored=60000,
            cost_per_month_usd=200.0, saved_compute_cost_usd=1000.0,
        )
        self.engine.register_partition(p1)
        self.engine.analyze_optimization("p1")

        rep = self.engine.get_optimization_report()
        self.assertEqual(rep["total_partitions"], 1)
        self.assertEqual(rep["total_monthly_cache_cost_usd"], 200.0)
        self.assertEqual(rep["total_saved_compute_cost_usd"], 1000.0)
        self.assertEqual(rep["potential_monthly_savings_usd"], 130.0)
        self.assertEqual(rep["total_recommendations_generated"], 1)


if __name__ == "__main__":
    unittest.main()
