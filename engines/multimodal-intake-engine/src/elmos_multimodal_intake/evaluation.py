"""Compatibility facade for the durable Skill24 evaluation boundary.

Evaluation used to accept caller-authored case statuses and evidence metadata.
That path is intentionally removed. Runtime execution must use
``EvaluationSkillBridge`` so bytes are persisted, hashed, evaluated and
independently replayed by trusted local code.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .durable_evaluation import (
    EVALUATION_SKILL,
    LOCAL_EVALUATORS,
    EvaluationSkillBridge,
    EvaluationStore,
)


class EvaluationContractError(ValueError):
    """Retained as a source-compatible error identity for older importers."""


def run_multimodal_evaluation(request: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed when legacy in-memory evaluation is invoked directly."""

    del request
    return {
        "state": "BLOCKED",
        "code": "DURABLE_EVALUATION_BRIDGE_REQUIRED",
        "outputs": {
            "decision": "NOT_RUN",
            "external_evidence": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
        },
        "metrics": {},
        "retryable": False,
    }


__all__ = [
    "EVALUATION_SKILL",
    "LOCAL_EVALUATORS",
    "EvaluationContractError",
    "EvaluationSkillBridge",
    "EvaluationStore",
    "run_multimodal_evaluation",
]
