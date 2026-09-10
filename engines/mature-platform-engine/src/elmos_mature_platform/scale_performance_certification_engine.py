from typing import List, Dict, Optional
from datetime import datetime
import uuid

from elmos_mature_platform.types import (
    PerformanceTestType,
    PerformanceVerdict,
    PerformanceBenchmark,
    PerformanceResult
)

class ScalePerformanceCertificationEngine:
    def __init__(self):
        self._benchmarks: Dict[str, PerformanceBenchmark] = {}
        self._results: Dict[str, PerformanceResult] = {}

    def define_benchmark(self, benchmark: PerformanceBenchmark) -> str:
        """
        Defines a new performance benchmark.
        """
        if not benchmark.benchmark_id:
            benchmark.benchmark_id = str(uuid.uuid4())
        self._benchmarks[benchmark.benchmark_id] = benchmark
        return benchmark.benchmark_id

    def submit_result(self, result: PerformanceResult) -> str:
        """
        Submits a performance result. Ensures it references a valid benchmark.
        """
        if result.benchmark_id not in self._benchmarks:
            raise ValueError(f"Invalid benchmark_id: {result.benchmark_id}")
        if not result.result_id:
            result.result_id = str(uuid.uuid4())
        self._results[result.result_id] = result
        return result.result_id

    def evaluate_result(self, result_id: str) -> PerformanceVerdict:
        """
        Auto-evaluates a performance result based on its associated benchmark targets.
        
        - PASS: all metrics within targets
        - DEGRADED: within 120% of targets but not all met
        - FAIL: any metric > 150% of target or error rate > 2x target
        - INCONCLUSIVE: missing benchmark or unevaluable
        """
        if result_id not in self._results:
            return PerformanceVerdict.INCONCLUSIVE
        
        result = self._results[result_id]
        if result.benchmark_id not in self._benchmarks:
            result.verdict = PerformanceVerdict.INCONCLUSIVE
            return PerformanceVerdict.INCONCLUSIVE
            
        benchmark = self._benchmarks[result.benchmark_id]
        
        # Helper to check if actual is worse than target (for higher-is-worse metrics)
        def is_worse(actual, target, threshold):
            if target == 0:
                return actual > 0
            return actual > (target * threshold)
            
        def is_worse_lower(actual, target, threshold):
            if target == 0:
                return False
            # For lower-is-worse metrics like RPS
            return actual < (target * threshold)
        
        # Check FAIL conditions
        if (is_worse_lower(result.actual_rps, benchmark.target_rps, 0.5) or # < 50% RPS is fail
            is_worse(result.actual_p95_ms, benchmark.target_p95_ms, 1.5) or
            is_worse(result.actual_p99_ms, benchmark.target_p99_ms, 1.5) or
            is_worse(result.actual_error_rate_pct, benchmark.target_error_rate_pct, 2.0) or
            is_worse(result.actual_cpu_pct, benchmark.max_cpu_pct, 1.5) or
            is_worse(result.actual_memory_pct, benchmark.max_memory_pct, 1.5)):
            result.verdict = PerformanceVerdict.FAIL
            return PerformanceVerdict.FAIL
            
        # Check DEGRADED conditions
        if (is_worse_lower(result.actual_rps, benchmark.target_rps, 1.0) or # 50% <= RPS < 100%
            is_worse(result.actual_p95_ms, benchmark.target_p95_ms, 1.0) or # > 100% and <= 150%
            is_worse(result.actual_p99_ms, benchmark.target_p99_ms, 1.0) or
            is_worse(result.actual_error_rate_pct, benchmark.target_error_rate_pct, 1.0) or
            is_worse(result.actual_cpu_pct, benchmark.max_cpu_pct, 1.0) or
            is_worse(result.actual_memory_pct, benchmark.max_memory_pct, 1.0)):
            result.verdict = PerformanceVerdict.DEGRADED
            return PerformanceVerdict.DEGRADED
            
        result.verdict = PerformanceVerdict.PASS
        return PerformanceVerdict.PASS

    def compare_results(self, result_id_a: str, result_id_b: str) -> Dict:
        """
        Returns a side-by-side comparison of two results with delta percentages.
        Base is result_a, so positive delta means result_b is higher.
        """
        if result_id_a not in self._results or result_id_b not in self._results:
            raise ValueError("One or both result IDs are invalid")
            
        a = self._results[result_id_a]
        b = self._results[result_id_b]
        
        def calc_delta(val_a, val_b):
            if val_a == 0:
                return float('inf') if val_b > 0 else 0.0
            return ((val_b - val_a) / val_a) * 100.0

        return {
            "rps": {"a": a.actual_rps, "b": b.actual_rps, "delta_pct": calc_delta(a.actual_rps, b.actual_rps)},
            "p95_ms": {"a": a.actual_p95_ms, "b": b.actual_p95_ms, "delta_pct": calc_delta(a.actual_p95_ms, b.actual_p95_ms)},
            "p99_ms": {"a": a.actual_p99_ms, "b": b.actual_p99_ms, "delta_pct": calc_delta(a.actual_p99_ms, b.actual_p99_ms)},
            "error_rate_pct": {"a": a.actual_error_rate_pct, "b": b.actual_error_rate_pct, "delta_pct": calc_delta(a.actual_error_rate_pct, b.actual_error_rate_pct)},
            "cpu_pct": {"a": a.actual_cpu_pct, "b": b.actual_cpu_pct, "delta_pct": calc_delta(a.actual_cpu_pct, b.actual_cpu_pct)},
            "memory_pct": {"a": a.actual_memory_pct, "b": b.actual_memory_pct, "delta_pct": calc_delta(a.actual_memory_pct, b.actual_memory_pct)},
        }

    def detect_regression(self, benchmark_id: str) -> Dict:
        """
        Compares the latest result with the previous one for the given benchmark.
        Detects regression if RPS drop > 10% or latency increase > 20%.
        """
        history = self.get_benchmark_history(benchmark_id)
        if len(history) < 2:
            return {"regression_detected": False, "reason": "Not enough history to detect regression"}
            
        latest = history[-1]
        previous = history[-2]
        
        comparison = self.compare_results(previous.result_id, latest.result_id)
        
        reasons = []
        if comparison["rps"]["delta_pct"] < -10.0:
            reasons.append(f"RPS dropped by {-comparison['rps']['delta_pct']:.1f}%")
        if comparison["p95_ms"]["delta_pct"] > 20.0:
            reasons.append(f"P95 latency increased by {comparison['p95_ms']['delta_pct']:.1f}%")
        if comparison["p99_ms"]["delta_pct"] > 20.0:
            reasons.append(f"P99 latency increased by {comparison['p99_ms']['delta_pct']:.1f}%")
            
        return {
            "regression_detected": len(reasons) > 0,
            "reasons": reasons,
            "latest_result_id": latest.result_id,
            "previous_result_id": previous.result_id
        }

    def get_benchmark_history(self, benchmark_id: str) -> List[PerformanceResult]:
        """
        Returns all results for a specific benchmark, sorted by tested_at if available,
        otherwise by insertion order (which we preserve naturally here).
        """
        if benchmark_id not in self._benchmarks:
            raise ValueError(f"Invalid benchmark_id: {benchmark_id}")
            
        results = [r for r in self._results.values() if r.benchmark_id == benchmark_id]
        
        # Sort by tested_at if present
        def sort_key(r):
            if r.tested_at:
                try:
                    return datetime.fromisoformat(r.tested_at)
                except ValueError:
                    pass
            return datetime.min
            
        return sorted(results, key=sort_key)

    def get_certification_status(self, benchmark_ids: List[str]) -> Dict:
        """
        Checks if all specified benchmarks are certified.
        A benchmark is certified if its LATEST result has a PASS verdict.
        """
        status_map = {}
        all_passed = True
        
        for bid in benchmark_ids:
            if bid not in self._benchmarks:
                raise ValueError(f"Invalid benchmark_id: {bid}")
                
            history = self.get_benchmark_history(bid)
            if not history:
                status_map[bid] = "NO_RESULTS"
                all_passed = False
            else:
                latest = history[-1]
                # Re-evaluate just to be sure
                verdict = self.evaluate_result(latest.result_id)
                status_map[bid] = verdict.value
                if verdict != PerformanceVerdict.PASS:
                    all_passed = False
                    
        return {
            "certified": all_passed,
            "benchmark_status": status_map
        }

    def get_capacity_headroom(self, benchmark_id: str) -> Dict:
        """
        Returns headroom for the latest result.
        Headroom formula: (target - actual) / target * 100
        For RPS, headroom is positive if actual > target (we're above target).
        Wait, standard headroom is usually positive if we have room.
        For RPS: (actual - target) / target * 100
        For latency/resources: (target - actual) / target * 100
        """
        history = self.get_benchmark_history(benchmark_id)
        if not history:
            raise ValueError("No results available for benchmark")
            
        latest = history[-1]
        benchmark = self._benchmarks[benchmark_id]
        
        def calc_headroom(actual, target, is_higher_better=False):
            if target == 0:
                return float('inf')
            if is_higher_better:
                return ((actual - target) / target) * 100.0
            else:
                return ((target - actual) / target) * 100.0
                
        return {
            "rps_headroom_pct": calc_headroom(latest.actual_rps, benchmark.target_rps, True),
            "p95_ms_headroom_pct": calc_headroom(latest.actual_p95_ms, benchmark.target_p95_ms, False),
            "p99_ms_headroom_pct": calc_headroom(latest.actual_p99_ms, benchmark.target_p99_ms, False),
            "cpu_headroom_pct": calc_headroom(latest.actual_cpu_pct, benchmark.max_cpu_pct, False),
            "memory_headroom_pct": calc_headroom(latest.actual_memory_pct, benchmark.max_memory_pct, False),
        }

    def get_performance_trends(self, benchmark_id: str) -> Dict:
        """
        Returns trend per metric based on all historical results.
        Simple logic: compares latest vs earliest, or looks at general slope.
        """
        history = self.get_benchmark_history(benchmark_id)
        if len(history) < 2:
            return {"trend": "insufficient_data"}
            
        earliest = history[0]
        latest = history[-1]
        
        def get_trend(val_e, val_l, is_higher_better=False):
            if val_e == val_l:
                return "stable"
            
            improved = (val_l > val_e) if is_higher_better else (val_l < val_e)
            
            diff = abs(val_l - val_e)
            if val_e > 0 and diff / val_e < 0.05: # Within 5% is stable
                return "stable"
                
            return "improving" if improved else "degrading"
            
        return {
            "rps": get_trend(earliest.actual_rps, latest.actual_rps, True),
            "p95_ms": get_trend(earliest.actual_p95_ms, latest.actual_p95_ms, False),
            "p99_ms": get_trend(earliest.actual_p99_ms, latest.actual_p99_ms, False),
            "cpu": get_trend(earliest.actual_cpu_pct, latest.actual_cpu_pct, False),
            "memory": get_trend(earliest.actual_memory_pct, latest.actual_memory_pct, False)
        }

    def get_scale_report(self) -> Dict:
        """
        Generates a summary report for all benchmarks.
        """
        report = {
            "total_benchmarks": len(self._benchmarks),
            "benchmarks": {}
        }
        
        for bid, benchmark in self._benchmarks.items():
            history = self.get_benchmark_history(bid)
            if not history:
                report["benchmarks"][bid] = {"status": "NO_RESULTS"}
                continue
                
            latest = history[-1]
            verdict = self.evaluate_result(latest.result_id)
            
            reg_info = self.detect_regression(bid)
            
            report["benchmarks"][bid] = {
                "name": benchmark.name,
                "verdict": verdict.value,
                "latest_result_id": latest.result_id,
                "regression_detected": reg_info["regression_detected"],
                "regression_reasons": reg_info.get("reasons", [])
            }
            
        return report
