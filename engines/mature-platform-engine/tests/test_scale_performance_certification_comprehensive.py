import unittest
from datetime import datetime, timedelta

from elmos_mature_platform.types import (
    PerformanceTestType,
    PerformanceVerdict,
    PerformanceBenchmark,
    PerformanceResult
)
from elmos_mature_platform.scale_performance_certification_engine import ScalePerformanceCertificationEngine


class TestScalePerformanceCertificationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ScalePerformanceCertificationEngine()

    def _create_benchmark(self, name="Test BM", target_rps=1000, target_p95=50.0, target_p99=100.0, cpu=80.0, mem=80.0, error=1.0):
        bm = PerformanceBenchmark(
            benchmark_id="",
            name=name,
            test_type=PerformanceTestType.LOAD,
            target_rps=target_rps,
            target_p95_ms=target_p95,
            target_p99_ms=target_p99,
            target_error_rate_pct=error,
            max_cpu_pct=cpu,
            max_memory_pct=mem,
            duration_minutes=30,
            concurrent_users=100
        )
        return self.engine.define_benchmark(bm)

    def _create_result(self, b_id, actual_rps=1000, actual_p95=50.0, actual_p99=100.0, cpu=80.0, mem=80.0, error=1.0, tested_at=None):
        if tested_at is None:
            tested_at = datetime.utcnow().isoformat()
        r = PerformanceResult(
            result_id="",
            benchmark_id=b_id,
            actual_rps=actual_rps,
            actual_p95_ms=actual_p95,
            actual_p99_ms=actual_p99,
            actual_error_rate_pct=error,
            actual_cpu_pct=cpu,
            actual_memory_pct=mem,
            duration_minutes=30,
            tested_at=tested_at
        )
        return self.engine.submit_result(r)

    # 1. Test defining a benchmark sets an ID if none provided
    def test_define_benchmark_generates_id(self):
        b_id = self._create_benchmark()
        self.assertTrue(len(b_id) > 0)
        
    # 2. Test defining a benchmark with an existing ID keeps it
    def test_define_benchmark_keeps_id(self):
        bm = PerformanceBenchmark("b-123", "Test", PerformanceTestType.LOAD)
        res_id = self.engine.define_benchmark(bm)
        self.assertEqual(res_id, "b-123")

    # 3. Test submit result invalid benchmark
    def test_submit_result_invalid_benchmark(self):
        with self.assertRaises(ValueError):
            self._create_result("invalid")

    # 4. Test evaluate result missing result
    def test_evaluate_missing_result(self):
        self.assertEqual(self.engine.evaluate_result("invalid"), PerformanceVerdict.INCONCLUSIVE)

    # 5. Test evaluate perfect PASS
    def test_evaluate_perfect_pass(self):
        b_id = self._create_benchmark()
        r_id = self._create_result(b_id, 1100, 40, 90, 70, 70, 0.5)
        self.assertEqual(self.engine.evaluate_result(r_id), PerformanceVerdict.PASS)

    # 6. Test evaluate RPS failure (lower than 50% target)
    def test_evaluate_rps_fail(self):
        b_id = self._create_benchmark(target_rps=1000)
        r_id = self._create_result(b_id, actual_rps=499) # < 50% of 1000
        self.assertEqual(self.engine.evaluate_result(r_id), PerformanceVerdict.FAIL)

    # 7. Test evaluate RPS degraded (between 50% and 100%)
    def test_evaluate_rps_degraded(self):
        b_id = self._create_benchmark(target_rps=1000)
        r_id = self._create_result(b_id, actual_rps=800) # 80% is degraded
        self.assertEqual(self.engine.evaluate_result(r_id), PerformanceVerdict.DEGRADED)

    # 8. Test evaluate p95 fail (>150%)
    def test_evaluate_p95_fail(self):
        b_id = self._create_benchmark(target_p95=100)
        r_id = self._create_result(b_id, actual_p95=151)
        self.assertEqual(self.engine.evaluate_result(r_id), PerformanceVerdict.FAIL)

    # 9. Test evaluate p95 degraded (100% < x <= 150%)
    def test_evaluate_p95_degraded(self):
        b_id = self._create_benchmark(target_p95=100)
        r_id = self._create_result(b_id, actual_p95=120)
        self.assertEqual(self.engine.evaluate_result(r_id), PerformanceVerdict.DEGRADED)

    # 10. Test evaluate p99 fail
    def test_evaluate_p99_fail(self):
        b_id = self._create_benchmark(target_p99=200)
        r_id = self._create_result(b_id, actual_p99=301)
        self.assertEqual(self.engine.evaluate_result(r_id), PerformanceVerdict.FAIL)

    # 11. Test evaluate error rate fail (>2x)
    def test_evaluate_error_fail(self):
        b_id = self._create_benchmark(error=1.0)
        r_id = self._create_result(b_id, error=2.1)
        self.assertEqual(self.engine.evaluate_result(r_id), PerformanceVerdict.FAIL)

    # 12. Test evaluate CPU fail
    def test_evaluate_cpu_fail(self):
        b_id = self._create_benchmark(cpu=80.0)
        r_id = self._create_result(b_id, cpu=121)
        self.assertEqual(self.engine.evaluate_result(r_id), PerformanceVerdict.FAIL)

    # 13. Test evaluate memory fail
    def test_evaluate_mem_fail(self):
        b_id = self._create_benchmark(mem=50.0)
        r_id = self._create_result(b_id, mem=76)
        self.assertEqual(self.engine.evaluate_result(r_id), PerformanceVerdict.FAIL)

    # 14. Test compare results invalid
    def test_compare_results_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.compare_results("a", "b")

    # 15. Test compare results correct deltas
    def test_compare_results_deltas(self):
        b_id = self._create_benchmark()
        r1 = self._create_result(b_id, actual_rps=1000, actual_p95=100)
        r2 = self._create_result(b_id, actual_rps=1100, actual_p95=150)
        diff = self.engine.compare_results(r1, r2)
        self.assertAlmostEqual(diff["rps"]["delta_pct"], 10.0)
        self.assertAlmostEqual(diff["p95_ms"]["delta_pct"], 50.0)

    # 16. Test compare with zero base
    def test_compare_results_zero_base(self):
        b_id = self._create_benchmark()
        r1 = self._create_result(b_id, actual_rps=0)
        r2 = self._create_result(b_id, actual_rps=100)
        diff = self.engine.compare_results(r1, r2)
        self.assertEqual(diff["rps"]["delta_pct"], float('inf'))

    # 17. Test regression detection insufficient data
    def test_regression_insufficient_data(self):
        b_id = self._create_benchmark()
        self._create_result(b_id)
        reg = self.engine.detect_regression(b_id)
        self.assertFalse(reg["regression_detected"])

    # 18. Test regression detection RPS drop
    def test_regression_rps_drop(self):
        b_id = self._create_benchmark()
        self._create_result(b_id, actual_rps=1000)
        self._create_result(b_id, actual_rps=800) # 20% drop
        reg = self.engine.detect_regression(b_id)
        self.assertTrue(reg["regression_detected"])
        self.assertTrue(any("RPS dropped" in r for r in reg["reasons"]))

    # 19. Test regression detection P95 increase
    def test_regression_p95_increase(self):
        b_id = self._create_benchmark()
        self._create_result(b_id, actual_p95=100)
        self._create_result(b_id, actual_p95=125) # 25% increase
        reg = self.engine.detect_regression(b_id)
        self.assertTrue(reg["regression_detected"])

    # 20. Test regression detection P99 increase
    def test_regression_p99_increase(self):
        b_id = self._create_benchmark()
        self._create_result(b_id, actual_p99=100)
        self._create_result(b_id, actual_p99=125) # 25% increase
        reg = self.engine.detect_regression(b_id)
        self.assertTrue(reg["regression_detected"])

    # 21. Test regression detection no regression
    def test_regression_none(self):
        b_id = self._create_benchmark()
        self._create_result(b_id, actual_rps=1000, actual_p99=100)
        self._create_result(b_id, actual_rps=1050, actual_p99=105) # small changes
        reg = self.engine.detect_regression(b_id)
        self.assertFalse(reg["regression_detected"])

    # 22. Test benchmark history sorting
    def test_history_sorting(self):
        b_id = self._create_benchmark()
        r1 = self._create_result(b_id, tested_at="2020-01-02T00:00:00")
        r2 = self._create_result(b_id, tested_at="2020-01-01T00:00:00")
        r3 = self._create_result(b_id, tested_at="2020-01-03T00:00:00")
        hist = self.engine.get_benchmark_history(b_id)
        self.assertEqual(hist[0].result_id, r2)
        self.assertEqual(hist[1].result_id, r1)
        self.assertEqual(hist[2].result_id, r3)

    # 23. Test certification status invalid
    def test_cert_status_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_certification_status(["invalid"])

    # 24. Test certification status all pass
    def test_cert_status_all_pass(self):
        b1 = self._create_benchmark()
        b2 = self._create_benchmark()
        self._create_result(b1, actual_rps=1500)
        self._create_result(b2, actual_rps=1500)
        status = self.engine.get_certification_status([b1, b2])
        self.assertTrue(status["certified"])

    # 25. Test certification status one degraded
    def test_cert_status_one_degraded(self):
        b1 = self._create_benchmark()
        b2 = self._create_benchmark(target_rps=1000)
        self._create_result(b1, actual_rps=1500)
        self._create_result(b2, actual_rps=800) # degraded
        status = self.engine.get_certification_status([b1, b2])
        self.assertFalse(status["certified"])
        self.assertEqual(status["benchmark_status"][b2], "degraded")

    # 26. Test certification status missing results
    def test_cert_status_no_results(self):
        b1 = self._create_benchmark()
        status = self.engine.get_certification_status([b1])
        self.assertFalse(status["certified"])

    # 27. Test capacity headroom
    def test_capacity_headroom(self):
        b_id = self._create_benchmark(target_rps=1000, target_p95=100)
        self._create_result(b_id, actual_rps=1200, actual_p95=80)
        hd = self.engine.get_capacity_headroom(b_id)
        self.assertAlmostEqual(hd["rps_headroom_pct"], 20.0) # 200/1000 * 100
        self.assertAlmostEqual(hd["p95_ms_headroom_pct"], 20.0) # (100-80)/100 * 100

    # 28. Test capacity headroom zero target
    def test_capacity_headroom_zero(self):
        b_id = self._create_benchmark(target_rps=0)
        self._create_result(b_id, actual_rps=1200)
        hd = self.engine.get_capacity_headroom(b_id)
        self.assertEqual(hd["rps_headroom_pct"], float('inf'))

    # 29. Test performance trends stable
    def test_trends_stable(self):
        b_id = self._create_benchmark()
        self._create_result(b_id, actual_rps=1000)
        self._create_result(b_id, actual_rps=1010) # +1%
        trends = self.engine.get_performance_trends(b_id)
        self.assertEqual(trends["rps"], "stable")

    # 30. Test performance trends improving
    def test_trends_improving(self):
        b_id = self._create_benchmark()
        self._create_result(b_id, actual_rps=1000, actual_p95=100)
        self._create_result(b_id, actual_rps=1200, actual_p95=80) 
        trends = self.engine.get_performance_trends(b_id)
        self.assertEqual(trends["rps"], "improving")
        self.assertEqual(trends["p95_ms"], "improving")

    # 31. Test performance trends degrading
    def test_trends_degrading(self):
        b_id = self._create_benchmark()
        self._create_result(b_id, actual_rps=1000, actual_p95=100)
        self._create_result(b_id, actual_rps=800, actual_p95=120) 
        trends = self.engine.get_performance_trends(b_id)
        self.assertEqual(trends["rps"], "degrading")
        self.assertEqual(trends["p95_ms"], "degrading")

    # 32. Test scale report
    def test_scale_report(self):
        b_id = self._create_benchmark(name="Main API")
        self._create_result(b_id, actual_rps=1500)
        rep = self.engine.get_scale_report()
        self.assertEqual(rep["total_benchmarks"], 1)
        self.assertIn(b_id, rep["benchmarks"])
        self.assertEqual(rep["benchmarks"][b_id]["verdict"], "pass")
        self.assertFalse(rep["benchmarks"][b_id]["regression_detected"])

if __name__ == '__main__':
    unittest.main()
