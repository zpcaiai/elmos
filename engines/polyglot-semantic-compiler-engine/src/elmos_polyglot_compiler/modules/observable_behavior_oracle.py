"""Batch N: Observable Behavior Oracles Module (Skills 233-248)."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional

from ..models import (
    BatchType,
    BehaviorOracle,
    DifferentialResult,
    ObligationStatus,
    SemanticObligation,
    SemanticRisk,
    VerdictStatus,
)


class ObservableBehaviorOracleModule:
    """Defines observable behavior oracles, input domain partitioning, and differential output evaluation."""

    def __init__(self):
        self.oracles: Dict[str, BehaviorOracle] = {}
        self.differential_results: List[DifferentialResult] = []

    def create_behavior_oracle(
        self,
        scope: str,
        signals: List[str],
        partitions: List[Dict[str, Any]],
        side_effects: Optional[List[str]] = None,
        tolerance_epsilon: float = 0.0,
    ) -> BehaviorOracle:
        """Constructs an observable behavior oracle for differential validation."""
        oracle_id = f"oracle-{scope}-{hashlib.sha256(''.join(signals).encode('utf-8')).hexdigest()[:8]}"
        oracle = BehaviorOracle(
            oracle_id=oracle_id,
            scope=scope,
            observable_signals=signals,
            input_domain_partitions=partitions,
            side_effect_channels=side_effects or ["return_value", "stdout"],
            tolerance_epsilon=tolerance_epsilon,
        )
        self.oracles[oracle_id] = oracle
        return oracle

    def compare_differential_output(
        self,
        source_language: str,
        target_language: str,
        test_case_id: str,
        source_output: Any,
        target_output: Any,
        epsilon: float = 0.0,
    ) -> DifferentialResult:
        """Compares execution outputs across source and target engines."""
        run_id = f"diff-{test_case_id}-{int(time.time()*1000)}"

        if source_output == target_output:
            verdict = VerdictStatus.EQUIVALENT
            summary = "Strict identical output"
        elif isinstance(source_output, (int, float)) and isinstance(target_output, (int, float)):
            diff = abs(source_output - target_output)
            if diff <= epsilon:
                verdict = VerdictStatus.EQUIVALENT
                summary = f"Numeric match within epsilon {epsilon} (diff={diff})"
            else:
                verdict = VerdictStatus.DIVERGENT
                summary = f"Numeric divergence: diff={diff} > {epsilon}"
        else:
            verdict = VerdictStatus.DIVERGENT
            summary = f"Value divergence: {source_output} != {target_output}"

        res = DifferentialResult(
            run_id=run_id,
            source_language=source_language,
            target_language=target_language,
            test_case_id=test_case_id,
            verdict=verdict,
            source_output=source_output,
            target_output=target_output,
            divergence_summary=summary,
        )
        self.differential_results.append(res)
        return res

    def create_behavior_obligation(
        self,
        source_func: str,
        target_func: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emits a Batch N behavior obligation."""
        obl_id = f"obl-N-{hashlib.sha256((source_func + target_func + property_name).encode('utf-8')).hexdigest()[:10]}"
        return SemanticObligation(
            obligation_id=obl_id,
            batch=BatchType.BATCH_N,
            layer="behavior-oracle",
            source_construct=source_func,
            target_construct=target_func,
            property_name=property_name,
            invariants=["IO_EQUIVALENCE", "SIDE_EFFECT_CONFINEMENT", "DETERMINISTIC_REPLAY_STABILITY"],
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
