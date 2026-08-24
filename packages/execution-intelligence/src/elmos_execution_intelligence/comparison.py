"""System / human / human-assisted comparison under one Definition of Done."""
from __future__ import annotations

from typing import Any

HOURS_PER_CALENDAR_WEEK = 7.0 * 24.0


def compare(
    project: dict[str, Any],
    system_runtime: dict[str, Any],
    human: dict[str, Any],
    costs: dict[str, Any],
) -> dict[str, Any]:
    assisted = project.get("human_assisted", {})
    review_hours = float(assisted.get("review_person_hours", 0.0))
    approval_wait_hours = float(assisted.get("approval_wait_hours", 0.0))
    external_wait_hours = float(assisted.get("external_wait_hours", 0.0))
    parallel_fraction = min(1.0, max(0.0, float(assisted.get("review_parallel_fraction", 0.0))))
    serial_review_hours = review_hours * (1.0 - parallel_fraction)

    system = system_runtime["wall_clock_hours"]
    human_weeks = human["calendar_weeks"]
    human_person_hours = human["person_hours"]

    end_to_end = {
        label: round(float(system[label]) + serial_review_hours + approval_wait_hours + external_wait_hours, 3)
        for label in ("p50", "p80", "p90", "worst_case")
    }

    def speedup(label: str) -> float | None:
        denominator = float(system[label])
        if denominator <= 0:
            return None
        return round(float(human_weeks[label]) * HOURS_PER_CALENDAR_WEEK / denominator, 3)

    p50_person_hours = float(human_person_hours["p50"])
    labor_reduction = None
    if p50_person_hours > 0:
        labor_reduction = round(1.0 - review_hours / p50_person_hours, 5)

    return {
        "definition_of_done": project["definition_of_done"],
        "same_definition_of_done_for_both_baselines": True,
        "system_autonomous": system_runtime,
        "human_only": human,
        "human_assisted": {
            "review_person_hours": round(review_hours, 3),
            "review_parallel_fraction": parallel_fraction,
            "serial_review_hours": round(serial_review_hours, 3),
            "approval_wait_hours": round(approval_wait_hours, 3),
            "external_wait_hours": round(external_wait_hours, 3),
            "end_to_end_hours": end_to_end,
            "definition": "system autonomous wall-clock + non-parallelisable human review + approval/external waits",
        },
        "comparison": {
            "calendar_speedup": {
                "p50": speedup("p50"),
                "p80": speedup("p80"),
                "p90": speedup("p90"),
                "formula": "human calendar weeks x 7 x 24 / system autonomous wall-clock hours",
                "caveat": ("Human calendar weeks include nights and weekends; "
                       "the system figure is continuous machine time."),
            },
            "labor_reduction_ratio": labor_reduction,
            "human_hours_saved_p50": round(max(0.0, p50_person_hours - review_hours), 3),
            "automation_coverage": round(min(1.0, max(0.0, labor_reduction or 0.0)), 5),
        },
        "model_costs": costs,
        "confidence": float(project.get("confidence", 0.5)),
        "assumptions": list(project.get("assumptions", [])),
        "exclusions": list(project.get("exclusions", [])),
    }
