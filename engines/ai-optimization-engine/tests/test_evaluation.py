import unittest
from elmos_ai_optimization.evaluation import ranked_metrics, nearest_rank, cost_per_accepted, compare_paired
from elmos_ai_optimization.contracts import ContractError

class TestEvaluation(unittest.TestCase):

    def test_ranked_metrics_unanswerable(self):
        ranking = ["a", "b"]
        relevance = {"a": 0, "b": 0}
        res = ranked_metrics(ranking, relevance, k=2)
        self.assertFalse(res["answerable"])
        self.assertTrue(res["returned_any"])

    def test_ranked_metrics_empty_ranking(self):
        ranking = []
        relevance = {"a": 1}
        res = ranked_metrics(ranking, relevance, k=2)
        self.assertTrue(res["answerable"])
        self.assertEqual(res["recall"], 0.0)
        self.assertEqual(res["mrr"], 0.0)
        self.assertEqual(res["ndcg"], 0.0)
        self.assertFalse(res["returned_any"])

    def test_ranked_metrics_perfect(self):
        ranking = ["a", "b"]
        relevance = {"a": 3, "b": 2, "c": 1}
        res = ranked_metrics(ranking, relevance, k=2)
        self.assertTrue(res["answerable"])
        self.assertEqual(res["recall"], 2/3)
        self.assertEqual(res["mrr"], 1.0)
        self.assertTrue(res["ndcg"] > 0)

    def test_ranked_metrics_invalid_k(self):
        with self.assertRaises(ContractError):
            ranked_metrics(["a"], {"a": 1}, k=0)

    def test_ranked_metrics_invalid_relevance(self):
        with self.assertRaises(ContractError):
            ranked_metrics(["a"], {"a": 4}, k=1)
        with self.assertRaises(ContractError):
            ranked_metrics(["a"], {"a": -1}, k=1)

    def test_nearest_rank_happy(self):
        samples = [1.0, 3.0, 5.0, 7.0, 9.0]
        self.assertEqual(nearest_rank(samples, 0.5), 5.0)
        self.assertEqual(nearest_rank(samples, 1.0), 9.0)
        self.assertEqual(nearest_rank(samples, 0.1), 1.0)

    def test_nearest_rank_invalid(self):
        with self.assertRaises(ContractError):
            nearest_rank([], 0.5)
        with self.assertRaises(ContractError):
            nearest_rank([1.0], 1.5)
        with self.assertRaises(ContractError):
            nearest_rank([1.0], 0.0)

    def test_cost_per_accepted_happy(self):
        self.assertEqual(cost_per_accepted([1.0, 2.0], 2, amortization=1.0), 2.0)
        self.assertEqual(cost_per_accepted([1.0, 2.0], 1, amortization=0.0), 3.0)

    def test_cost_per_accepted_zero(self):
        self.assertIsNone(cost_per_accepted([1.0, 2.0], 0))

    def test_cost_per_accepted_invalid(self):
        with self.assertRaises(ContractError):
            cost_per_accepted([1.0], -1)
        with self.assertRaises(ContractError):
            cost_per_accepted([-1.0], 1)
        with self.assertRaises(ContractError):
            cost_per_accepted([1.0], 1, amortization=-1.0)

    def _make_run(self, cases):
        return {
            "dataset_digest": "d",
            "environment_digest": "e",
            "scope_digest": "s",
            "model_profile": "m",
            "warm_state": "w",
            "cases": cases
        }

    def test_compare_paired_qualified(self):
        base_cases = {
            "1": {"quality": 0.5, "latency_ms": 100, "cost": 1.0}
        }
        cand_cases = {
            "1": {"quality": 0.6, "latency_ms": 105, "cost": 1.05}
        }
        b = self._make_run(base_cases)
        c = self._make_run(cand_cases)
        res = compare_paired(b, c)
        self.assertTrue(res["qualified"])
        self.assertEqual(res["decision"], "QUALIFIED")

    def test_compare_paired_rejected_quality(self):
        base_cases = {
            "1": {"quality": 0.5, "latency_ms": 100, "cost": 1.0}
        }
        cand_cases = {
            "1": {"quality": 0.51, "latency_ms": 105, "cost": 1.05} # delta 0.01 < 0.03
        }
        b = self._make_run(base_cases)
        c = self._make_run(cand_cases)
        res = compare_paired(b, c)
        self.assertFalse(res["qualified"])
        self.assertEqual(res["decision"], "REJECTED")

    def test_compare_paired_rejected_latency(self):
        base_cases = {
            "1": {"quality": 0.5, "latency_ms": 100, "cost": 1.0}
        }
        cand_cases = {
            "1": {"quality": 0.6, "latency_ms": 120, "cost": 1.05} # ratio 1.2 > 1.10
        }
        b = self._make_run(base_cases)
        c = self._make_run(cand_cases)
        res = compare_paired(b, c)
        self.assertFalse(res["qualified"])

    def test_compare_paired_rejected_cost(self):
        base_cases = {
            "1": {"quality": 0.5, "latency_ms": 100, "cost": 1.0}
        }
        cand_cases = {
            "1": {"quality": 0.6, "latency_ms": 105, "cost": 1.20} # ratio 1.2 > 1.10
        }
        b = self._make_run(base_cases)
        c = self._make_run(cand_cases)
        res = compare_paired(b, c)
        self.assertFalse(res["qualified"])

    def test_compare_paired_security_leak(self):
        base_cases = {
            "1": {"quality": 0.5, "latency_ms": 100, "cost": 1.0}
        }
        cand_cases = {
            "1": {"quality": 0.6, "latency_ms": 105, "cost": 1.0, "leaks": 1}
        }
        b = self._make_run(base_cases)
        c = self._make_run(cand_cases)
        res = compare_paired(b, c)
        self.assertFalse(res["qualified"])
        self.assertEqual(res["decision"], "REJECTED")
        self.assertIn("Security leak", res["reason"])

    def test_compare_paired_incomparable(self):
        b = self._make_run({"1": {"quality": 0.5, "latency_ms": 100}})
        c = self._make_run({"1": {"quality": 0.6, "latency_ms": 100}})
        c["dataset_digest"] = "different"
        with self.assertRaises(ContractError):
            compare_paired(b, c)

    def test_compare_paired_mismatched_cases(self):
        b = self._make_run({"1": {"quality": 0.5, "latency_ms": 100}})
        c = self._make_run({"2": {"quality": 0.6, "latency_ms": 100}})
        with self.assertRaises(ContractError):
            compare_paired(b, c)

if __name__ == '__main__':
    unittest.main()
