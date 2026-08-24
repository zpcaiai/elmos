"""Bounded handler for the exact database and Big Data orchestrator Skill."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..catalog import SKILL_CONTRACT_BY_NAME
from ..contracts import RuntimeRequest
from .common import compile_bounded_plan


def handle_elmos_bigdata_project_orchestrator(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return compile_bounded_plan(
        SKILL_CONTRACT_BY_NAME["elmos-bigdata-project-orchestrator"],
        request,
        record,
        focus=(
            "immutable-input-snapshot",
            "dependency-closed-plan",
            "tenant-concurrency-boundary",
            "checkpoint-and-recovery",
            "explicit-migration-and-ha-dr-composition",
            "evidence-handoff",
        ),
    )


__all__ = ["handle_elmos_bigdata_project_orchestrator"]
