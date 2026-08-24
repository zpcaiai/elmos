from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from elmos_cache_ref.dag_prefetch import ArtifactInfo, FutureUseIndex
from elmos_cache_ref.policies import (
    GDSFCache,
    PolicyRouter,
    S3FIFOCache,
    SieveCache,
    WTinyLFUCache,
    WorkloadFeatures,
    create_policy,
)
from elmos_cache_ref.simulator import TraceEvent, compare, simulate


class PolicyBehaviorTests(unittest.TestCase):
    def test_sieve_second_chance_survives_scan(self):
        cache = SieveCache(3)
        for key in ("a", "b", "c"):
            cache.access(key, 1)
        self.assertTrue(cache.access("a", 1).hit)
        result = cache.access("d", 1)
        self.assertIn("b", result.evicted)
        self.assertTrue(cache.contains("a"))
        self.assertFalse(cache.contains("b"))

    def test_s3fifo_graduates_reused_item(self):
        cache = S3FIFOCache(4, small_ratio=0.25)
        cache.access("hot", 1)
        cache.access("hot", 1)
        cache.access("hot", 1)
        for key in ("cold-1", "cold-2", "cold-3", "cold-4"):
            cache.access(key, 1)
        self.assertTrue(cache.contains("hot"))

    def test_wtinylfu_frequency_admission(self):
        cache = WTinyLFUCache(4, window_ratio=0.25, sketch_width=64)
        for _ in range(8):
            cache.access("hot", 1)
        for key in ("a", "b", "c", "d", "e", "f"):
            cache.access(key, 1)
        self.assertTrue(cache.contains("hot"))

    def test_gdsf_retains_expensive_object(self):
        cache = GDSFCache(2)
        cache.access("expensive", 1, recompute_ms=100, restore_ms=1)
        cache.access("cheap", 1, recompute_ms=2, restore_ms=1)
        cache.access("new-cheap", 1, recompute_ms=2, restore_ms=1)
        self.assertTrue(cache.contains("expensive"))
        self.assertFalse(cache.contains("cheap"))

    def test_oversized_object_is_bypassed(self):
        for name in ("LRU", "SIEVE", "S3_FIFO", "W_TINY_LFU", "GDSF"):
            policy = create_policy(name, 10)
            result = policy.access("too-large", 11)
            self.assertFalse(result.hit, name)
            self.assertFalse(result.admitted, name)
            self.assertEqual(result.bypass_reason, "OBJECT_EXCEEDS_CAPACITY", name)

    def test_router_prefers_quick_demotion_for_one_hit_workload(self):
        events = [
            {"key": f"key-{i}", "size_bytes": 1, "recompute_ms": 1}
            for i in range(120)
        ]
        features = WorkloadFeatures.from_events(events)
        choice = PolicyRouter().choose(features)
        self.assertEqual(choice.policy, "S3_FIFO")
        self.assertIn("ONE_HIT_RATIO_HIGH", choice.reason_codes)


class SimulatorTests(unittest.TestCase):
    def test_simulation_reports_avoided_work(self):
        events = [
            TraceEvent("a", 1, recompute_ms=100, restore_ms=5, model_tokens=10),
            TraceEvent("b", 1, recompute_ms=10, restore_ms=1),
            TraceEvent("a", 1, recompute_ms=100, restore_ms=5, model_tokens=10),
        ]
        report = simulate(create_policy("LRU", 2), events)
        self.assertEqual(report.hits, 1)
        self.assertAlmostEqual(report.object_hit_ratio, 1 / 3)
        self.assertEqual(report.avoided_model_tokens, 10)
        self.assertAlmostEqual(report.net_saved_ms, 95)

    def test_compare_uses_equal_capacity(self):
        events = [TraceEvent(str(i % 3), 1, 10, 1) for i in range(30)]
        reports = compare(["LRU", "SIEVE", "S3_FIFO", "W_TINY_LFU", "GDSF"], 2, events)
        self.assertEqual(len(reports), 5)
        self.assertEqual({report.capacity_bytes for report in reports}, {2})
        self.assertEqual({report.requests for report in reports}, {30})


class DAGPrefetchTests(unittest.TestCase):
    def test_protection_and_prefetch_prioritize_early_high_value(self):
        schedule = [
            {"source"},
            {"ast"},
            {"ir"},
            {"compile"},
            {"test"},
        ]
        index = FutureUseIndex(schedule)
        self.assertEqual(index.protected_keys(0, 2), {"ast", "ir"})
        artifacts = {
            "ast": ArtifactInfo("ast", 10, restore_ms=1, recompute_ms=20),
            "ir": ArtifactInfo("ir", 20, restore_ms=2, recompute_ms=100),
            "compile": ArtifactInfo("compile", 100, restore_ms=10, recompute_ms=1000),
            "unused": ArtifactInfo("unused", 1, restore_ms=1, recompute_ms=100),
        }
        decisions = index.prefetch_candidates(
            0,
            artifacts,
            resident_keys={"source"},
            bandwidth_budget_bytes=40,
            max_items=2,
            horizon_steps=3,
        )
        self.assertEqual([item.key for item in decisions], ["ir", "ast"])

    def test_eviction_keeps_protected_and_prefers_no_future_use(self):
        index = FutureUseIndex([{"a"}, {"b"}, {"a"}])
        artifacts = {
            "a": ArtifactInfo("a", 1, 1, 10),
            "b": ArtifactInfo("b", 1, 1, 2),
            "c": ArtifactInfo("c", 1, 1, 100),
        }
        order = index.eviction_order(0, artifacts, {"a", "b", "c"}, protected_keys={"a"})
        self.assertEqual(order[0], "c")
        self.assertNotIn("a", order)


if __name__ == "__main__":
    unittest.main()
