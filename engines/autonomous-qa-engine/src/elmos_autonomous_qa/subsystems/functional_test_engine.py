"""Industrial Functional Test Generation Engine: BVA, Equivalence Partitioning, Decision Tables.

Implements 7-point Boundary Value Analysis (BVA), Equivalence Partitioning (EP),
and truth-table decision logic for comprehensive functional testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import itertools
from typing import Any, Callable, Dict, List, Set, Tuple, Optional


@dataclass
class BVAResult:
    parameter_name: str
    min_value: float
    max_value: float
    nominal_value: float
    test_points: List[float]
    test_labels: List[str]


@dataclass
class EquivalencePartition:
    partition_id: str
    is_valid: bool
    description: str
    sample_values: List[Any]


@dataclass
class DecisionRule:
    rule_id: str
    conditions: Dict[str, bool]
    expected_actions: Dict[str, bool]


class FunctionalTestEngine:
    """Algorithmic functional testing generator."""

    @staticmethod
    def generate_7point_bva(
        parameter_name: str,
        min_val: float,
        max_val: float,
        nominal_val: Optional[float] = None,
        step: float = 1.0,
    ) -> BVAResult:
        """Computes standard 7-point BVA: [min-step, min, min+step, nominal, max-step, max, max+step]."""
        if min_val >= max_val:
            raise ValueError(f"min_val ({min_val}) must be strictly less than max_val ({max_val})")
        if nominal_val is None:
            nominal_val = (min_val + max_val) / 2.0

        points = [
            min_val - step,
            min_val,
            min_val + step,
            nominal_val,
            max_val - step,
            max_val,
            max_val + step,
        ]
        labels = [
            "MIN_MINUS_1_INVALID",
            "MIN_BOUNDARY_VALID",
            "MIN_PLUS_1_VALID",
            "NOMINAL_VALID",
            "MAX_MINUS_1_VALID",
            "MAX_BOUNDARY_VALID",
            "MAX_PLUS_1_INVALID",
        ]
        return BVAResult(
            parameter_name=parameter_name,
            min_value=min_val,
            max_value=max_val,
            nominal_value=nominal_val,
            test_points=points,
            test_labels=labels,
        )

    @staticmethod
    def partition_numeric_range(
        min_val: float,
        max_val: float,
        valid_samples_count: int = 3,
    ) -> List[EquivalencePartition]:
        """Creates Equivalence Partitions: Below Min (Invalid), Within Range (Valid), Above Max (Invalid)."""
        valid_step = (max_val - min_val) / (valid_samples_count + 1)
        valid_samples = [min_val + valid_step * (i + 1) for i in range(valid_samples_count)]

        return [
            EquivalencePartition(
                partition_id="EP_INVALID_LOW",
                is_valid=False,
                description=f"Values strictly below {min_val}",
                sample_values=[min_val - 10.0, min_val - 1.0],
            ),
            EquivalencePartition(
                partition_id="EP_VALID_IN_RANGE",
                is_valid=True,
                description=f"Values within [{min_val}, {max_val}]",
                sample_values=valid_samples,
            ),
            EquivalencePartition(
                partition_id="EP_INVALID_HIGH",
                is_valid=False,
                description=f"Values strictly above {max_val}",
                sample_values=[max_val + 1.0, max_val + 10.0],
            ),
        ]

    @staticmethod
    def evaluate_decision_table(
        rules: List[DecisionRule],
        inputs: Dict[str, bool],
    ) -> Optional[Dict[str, bool]]:
        """Evaluates inputs against decision table rules and returns matching actions."""
        for rule in rules:
            match = True
            for cond_name, expected_val in rule.conditions.items():
                if inputs.get(cond_name) != expected_val:
                    match = False
                    break
            if match:
                return rule.expected_actions
        return None

    @staticmethod
    def verify_decision_table_completeness(
        condition_names: List[str],
        rules: List[DecisionRule],
    ) -> Tuple[bool, List[Dict[str, bool]]]:
        """Verifies if all 2^N combinations are covered by the decision table."""
        n = len(condition_names)
        uncovered = []
        for combination in itertools.product([True, False], repeat=n):
            input_dict = dict(zip(condition_names, combination))
            matched = any(
                all(input_dict.get(c) == exp for c, exp in r.conditions.items())
                for r in rules
            )
            if not matched:
                uncovered.append(input_dict)
        return len(uncovered) == 0, uncovered
