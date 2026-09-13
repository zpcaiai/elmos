"""Orchestrator for the FDE Autonomous Delivery lifecycle.

Coordinates the 6 capability packs across the complete forward deployed engineering
journey: Engagement, Intake, Semantic Intelligence, Unified Assessment,
Planning & Transformation, and Verification & Release Operations.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from .dispatcher import FdeSkillDispatcher
from .registry import (
    ARCHIVE_SHA256,
    PACKAGE_NAME,
    PACKAGE_VERSION,
    TOPOLOGICAL_ORDER,
)

FDE_PHASES: Final = (
    ("01-fde-engagement", "Engagement & Commercial Alignment"),
    ("02-repository-intake-runtime", "Intake, Custody & Reproducible Runtime"),
    ("03-semantic-intelligence", "Polyglot Semantic Graph & Lineage"),
    ("04-unified-assessment", "Comprehensive Multi-Dimension Audit"),
    ("05-planning-transformation", "Planning, Architecture & Atomic Transformation"),
    ("06-verification-release-operations", "Verification, E3 Readiness & Operational Handoff"),
)


class FdeDeliveryOrchestrator:
    """Manages multi-stage execution and evidence aggregation for FDE engagements."""

    def __init__(self, dispatcher: type[FdeSkillDispatcher] = FdeSkillDispatcher) -> None:
        self.dispatcher = dispatcher

    def run_stage(
        self,
        pack_id: str,
        stage_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute all skills belonging to a specific pack in topological sequence."""
        from .registry import PACK_BY_SKILL

        payload = dict(stage_payload) if stage_payload is not None else {}
        stage_skills = [
            skill_id
            for skill_id in TOPOLOGICAL_ORDER
            if PACK_BY_SKILL.get(skill_id) == pack_id
        ]

        step_results: list[dict[str, Any]] = []
        overall_status = "PASS"

        for skill_id in stage_skills:
            res = self.dispatcher.dispatch(skill_id, payload)
            step_results.append(res)
            if res.get("status") not in ("PASS", "LOCAL_EXECUTED"):
                overall_status = "FAIL"
                break

        return {
            "pack": pack_id,
            "status": overall_status,
            "skill_count": len(step_results),
            "step_results": step_results,
        }

    def run_full_lifecycle(
        self,
        engagement_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute the entire 6-pack FDE autonomous delivery lifecycle in order."""
        payload = dict(engagement_payload) if engagement_payload is not None else {}
        phase_reports: list[dict[str, Any]] = []
        all_skills_executed: list[str] = []
        overall_status = "PASS"

        for pack_id, pack_desc in FDE_PHASES:
            stage_out = self.run_stage(pack_id, payload)
            stage_out["description"] = pack_desc
            phase_reports.append(stage_out)
            all_skills_executed.extend([r["skill"] for r in stage_out["step_results"]])

            if stage_out["status"] != "PASS":
                overall_status = "FAIL"
                break

        return {
            "package": PACKAGE_NAME,
            "version": PACKAGE_VERSION,
            "archive_sha256": f"sha256:{ARCHIVE_SHA256}",
            "status": overall_status,
            "phases_executed": len(phase_reports),
            "total_phases": len(FDE_PHASES),
            "skills_executed_count": len(all_skills_executed),
            "phase_reports": phase_reports,
            "standalone_boundary": "E3",
            "certification": "NOT_CERTIFIED",
            "production_ready": False,
        }
