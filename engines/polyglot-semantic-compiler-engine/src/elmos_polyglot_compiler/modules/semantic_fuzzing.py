"""Batch R aggregation for externally executed differential fuzz cases."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..contracts import digest_json, require_digest, require_identifier
from ..models import (
    BatchType,
    ObligationStatus,
    SemanticObligation,
    SemanticRisk,
    VerdictStatus,
)


_CASE_KEYS = frozenset(
    {
        "case_id",
        "input_digest",
        "source_result_digest",
        "target_result_digest",
        "evidence_digest",
        "execution_status",
        "verdict",
    }
)


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


class SemanticFuzzingModule:
    """Aggregates real case records; it does not run or simulate a fuzzer."""

    def __init__(self) -> None:
        self.fuzz_runs: List[Dict[str, Any]] = []

    def execute_differential_fuzz_campaign(
        self,
        route_id: str,
        iterations: int = 100,
        case_results: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Aggregate explicitly executed, digest-bound case results.

        With no ``case_results`` this compatibility API returns ``NOT_RUN``.
        It never invents iterations, zero divergences, or a passing verdict.
        """

        route_id = require_identifier(route_id, "route_id")
        if not isinstance(iterations, int) or isinstance(iterations, bool):
            raise ValueError("iterations must be an integer")
        if iterations < 1 or iterations > 1_000_000:
            raise ValueError("iterations must be between 1 and 1000000")
        fuzz_material = f"{route_id}\0{iterations}"
        fuzz_id = (
            "fuzz-"
            + hashlib.sha256(fuzz_material.encode("utf-8")).hexdigest()[:24]
        )
        if case_results is None:
            result = {
                "fuzz_id": fuzz_id,
                "route_id": route_id,
                "iterations_requested": iterations,
                "iterations_completed": 0,
                # Retained as an honest compatibility alias.
                "iterations": 0,
                "divergences_found": 0,
                "undetermined_cases": 0,
                "verdict": VerdictStatus.UNDETERMINED.value,
                "results_digest": None,
                "completed_at": None,
                "status": "NOT_RUN",
                "reason": "EXECUTED_CASE_RESULTS_REQUIRED",
            }
            self.fuzz_runs.append(result)
            return result
        if isinstance(case_results, (str, bytes)) or not isinstance(
            case_results, Sequence
        ):
            raise ValueError("case_results must be an array")
        if len(case_results) > iterations:
            raise ValueError("case_results exceeds requested iterations")

        normalized: List[Dict[str, Any]] = []
        seen_case_ids: set[str] = set()
        for index, case in enumerate(case_results):
            if not isinstance(case, Mapping) or set(case) != _CASE_KEYS:
                raise ValueError(
                    f"case_results[{index}] fields differ from the exact contract"
                )
            case_id = require_identifier(case.get("case_id"), f"case_results[{index}].case_id")
            if case_id in seen_case_ids:
                raise ValueError(f"duplicate fuzz case_id: {case_id}")
            seen_case_ids.add(case_id)
            for digest_field in (
                "input_digest",
                "source_result_digest",
                "target_result_digest",
                "evidence_digest",
            ):
                require_digest(
                    case.get(digest_field),
                    f"case_results[{index}].{digest_field}",
                )
            if case.get("execution_status") != "EXECUTED":
                raise ValueError(
                    f"case_results[{index}].execution_status must be EXECUTED"
                )
            try:
                verdict = VerdictStatus(str(case.get("verdict")))
            except ValueError as exc:
                raise ValueError(
                    f"case_results[{index}].verdict is unsupported"
                ) from exc
            normalized.append(
                {
                    "case_id": case_id,
                    "input_digest": case["input_digest"],
                    "source_result_digest": case["source_result_digest"],
                    "target_result_digest": case["target_result_digest"],
                    "evidence_digest": case["evidence_digest"],
                    "execution_status": "EXECUTED",
                    "verdict": verdict.value,
                }
            )

        divergences = sum(
            item["verdict"] == VerdictStatus.DIVERGENT.value for item in normalized
        )
        undetermined = sum(
            item["verdict"] == VerdictStatus.UNDETERMINED.value for item in normalized
        )
        complete = len(normalized) == iterations
        if divergences:
            aggregate_verdict = VerdictStatus.DIVERGENT
            status = "DIVERGENCES_FOUND"
            reason = "EXECUTED_CASE_DIVERGENCE"
        elif not complete or undetermined:
            aggregate_verdict = VerdictStatus.UNDETERMINED
            status = "INCOMPLETE"
            reason = (
                "UNDETERMINED_CASES_PRESENT"
                if undetermined
                else "REQUESTED_ITERATIONS_INCOMPLETE"
            )
        else:
            aggregate_verdict = VerdictStatus.UNDETERMINED
            status = "AGGREGATED_UNVERIFIED"
            reason = "HOST_VERIFIED_EVIDENCE_REQUIRED_FOR_EQUIVALENCE"

        result = {
            "fuzz_id": fuzz_id,
            "route_id": route_id,
            "iterations_requested": iterations,
            "iterations_completed": len(normalized),
            "iterations": len(normalized),
            "divergences_found": divergences,
            "undetermined_cases": undetermined,
            "verdict": aggregate_verdict.value,
            "results_digest": digest_json(normalized),
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": status,
            "reason": reason,
            "external_evidence": "EXTERNAL_EXECUTED_UNVERIFIED",
            "certification": "NOT_CERTIFIED",
        }
        self.fuzz_runs.append(result)
        return result

    def create_fuzzing_obligation(
        self,
        source_route: str,
        target_route: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emit a Batch R obligation without claiming fuzz execution."""

        source_route = require_identifier(source_route, "source_route")
        target_route = require_identifier(target_route, "target_route")
        property_name = require_identifier(property_name, "property_name")
        digest = _digest_text("\0".join((source_route, target_route, property_name)))
        return SemanticObligation(
            obligation_id=f"obl-R-{digest.removeprefix('sha256:')[:24]}",
            batch=BatchType.BATCH_R,
            layer="fuzzing",
            property_name=property_name,
            invariants=(
                "DIFFERENTIAL_ZERO_DIVERGENCE",
                "METAMORPHIC_RELATION_SATISFACTION",
            ),
            input_digest=digest,
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
