from __future__ import annotations

from pathlib import Path
from typing import Any

from etgb.harness import PhaseResult


class ExampleAdapter:
    """Skeleton only; replace phase bodies with Elmos production adapters."""

    def prepare(self, context: dict[str, Any]) -> PhaseResult:
        return PhaseResult("passed", outputs={"workspace": context["workspace"]})

    def baseline(self, context: dict[str, Any]) -> PhaseResult:
        return PhaseResult("passed", outputs={"source_contract_digest": "sha256:..."})

    def transform_or_generate(self, context: dict[str, Any]) -> PhaseResult:
        return PhaseResult(
            "passed",
            outputs={"target_repository_digest": "sha256:..."},
            usage={"input_tokens": 1000, "output_tokens": 500, "credit_usd": 0.05},
        )

    def build(self, context: dict[str, Any]) -> PhaseResult:
        return PhaseResult("passed", artifacts=[Path(context["build_log"])])

    def validate(self, context: dict[str, Any]) -> PhaseResult:
        return PhaseResult("passed", outputs={"critical_oracles_passed": True})

    def score(self, context: dict[str, Any]) -> PhaseResult:
        return PhaseResult("passed", outputs={"score": 1.0})

    def publish(self, context: dict[str, Any]) -> PhaseResult:
        return PhaseResult("passed")

    def compensate(self, context: dict[str, Any]) -> PhaseResult:
        return PhaseResult("passed")

    def cleanup(self, context: dict[str, Any]) -> PhaseResult:
        return PhaseResult("passed")
