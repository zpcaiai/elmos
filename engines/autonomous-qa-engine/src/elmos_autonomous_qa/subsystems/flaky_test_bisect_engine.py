"""Flaky Test Bisector & Binomial Confidence Interval Engine.

Calculates Wilson score intervals to determine flakiness probability with 95% confidence,
and schedules order permutations to identify order-dependent test contamination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Callable, Dict, List, Tuple


@dataclass
class FlakinessReport:
    test_identifier: str
    total_runs: int
    pass_count: int
    fail_count: int
    flakiness_ratio: float
    confidence_interval: Tuple[float, float]
    is_flaky: bool
    failure_signatures: List[str] = field(default_factory=list)


class FlakyTestBisectEngine:
    """Detects and quarantines flaky tests using statistical inference."""

    @classmethod
    def calculate_wilson_interval(
        cls,
        successes: int,
        trials: int,
        confidence: float = 0.95,
    ) -> Tuple[float, float]:
        """Computes Wilson score binomial confidence interval."""
        if trials == 0:
            return (0.0, 0.0)

        # Standard normal quantile for 95% confidence
        z = 1.95996 if confidence == 0.95 else 2.57583
        p_hat = successes / trials

        denominator = 1.0 + (z ** 2) / trials
        center = (p_hat + (z ** 2) / (2.0 * trials)) / denominator
        margin = (z / denominator) * math.sqrt((p_hat * (1.0 - p_hat) / trials) + ((z ** 2) / (4.0 * (trials ** 2))))

        lower = max(0.0, center - margin)
        upper = min(1.0, center + margin)
        return (round(lower, 4), round(upper, 4))

    @classmethod
    def evaluate_test_flakiness(
        cls,
        test_id: str,
        execution_results: List[bool],  # True = Pass, False = Fail
    ) -> FlakinessReport:
        total = len(execution_results)
        if total == 0:
            return FlakinessReport(
                test_identifier=test_id,
                total_runs=0,
                pass_count=0,
                fail_count=0,
                flakiness_ratio=0.0,
                confidence_interval=(0.0, 0.0),
                is_flaky=False,
            )

        passes = sum(1 for r in execution_results if r)
        fails = total - passes
        flaky_ratio = round(fails / total, 4) if passes > 0 else 0.0
        # Wilson interval for failure probability
        interval = cls.calculate_wilson_interval(fails, total)

        # A test is flaky if it has both passes and fails in repeated runs
        is_flaky = passes > 0 and fails > 0

        return FlakinessReport(
            test_identifier=test_id,
            total_runs=total,
            pass_count=passes,
            fail_count=fails,
            flakiness_ratio=flaky_ratio,
            confidence_interval=interval,
            is_flaky=is_flaky,
        )
