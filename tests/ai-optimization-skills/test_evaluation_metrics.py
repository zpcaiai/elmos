from __future__ import annotations

import unittest

from elmos_ai_optimization.evaluation import (
    compare_paired,
    cost_per_accepted,
    nearest_rank,
    ranked_metrics,
)


class EvaluationMetricsTest(unittest.TestCase):
    def test_ranked_metrics_perfect_ndcg(self) -> None:
        metrics = ranked_metrics(["a", "b"], {"a": 3, "b": 1}, k=5)
        self.assertTrue(metrics["answerable"])
        self.assertEqual(metrics["ndcg"], 1.0)
        self.assertEqual(metrics["mrr"], 1.0)
        self.assertEqual(metrics["recall"], 1.0)

    def test_ranked_metrics_unanswerable(self) -> None:
        metrics = ranked_metrics([], {}, k=5)
        self.assertFalse(metrics["answerable"])
        self.assertIsNone(metrics["recall"])
        self.assertIsNone(metrics["mrr"])
        self.assertIsNone(metrics["ndcg"])

    def test_ranked_metrics_deduplication(self) -> None:
        metrics = ranked_metrics(["a", "a"], {"a": 1, "b": 1}, k=5)
        self.assertEqual(metrics["recall"], 0.5)

    def test_nearest_rank_percentiles(self) -> None:
        samples = list(range(1, 101))
        p95 = nearest_rank(samples, 0.95)
        self.assertEqual(p95, 95.0)
        p50 = nearest_rank(samples, 0.50)
        self.assertEqual(p50, 50.0)

    def test_cost_per_accepted_with_amortization(self) -> None:
        # 3 attempts: 1.0, 2.0, 3.0, accepted: 2, amortization: 2.0 -> total = 8.0 / 2 = 4.0
        val = cost_per_accepted([1.0, 2.0, 3.0], 2, amortization=2.0)
        self.assertEqual(val, 4.0)

    def test_cost_per_accepted_zero_accepted(self) -> None:
        val = cost_per_accepted([1.0, 2.0], 0)
        self.assertIsNone(val)

    def test_compare_paired_qualified_and_rejected(self) -> None:
        common = {
            "dataset_digest": "d" * 64,
            "environment_digest": "e" * 64,
            "scope_digest": "s" * 64,
            "model_profile": "claude-sonnet-v1",
            "warm_state": "warm",
        }
        baseline = {
            **common,
            "cases": {
                "c1": {"quality": 0.80, "latency_ms": 100.0, "cost": 0.05, "leaks": 0},
            },
        }
        # Candidate with improved quality, acceptable latency, acceptable cost
        candidate_good = {
            **common,
            "cases": {
                "c1": {"quality": 0.85, "latency_ms": 105.0, "cost": 0.05, "leaks": 0},
            },
        }
        res_good = compare_paired(baseline, candidate_good)
        self.assertEqual(res_good["decision"], "QUALIFIED")

        # Candidate with security leak
        candidate_leaky = {
            **common,
            "cases": {
                "c1": {"quality": 0.95, "latency_ms": 105.0, "cost": 0.05, "leaks": 1},
            },
        }
        res_leaky = compare_paired(baseline, candidate_leaky)
        self.assertEqual(res_leaky["decision"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
