from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

class TourScenario(Enum):
    ARCHITECTURE_OVERVIEW = "ARCHITECTURE_OVERVIEW"
    DATA_FLOW_WALKTHROUGH = "DATA_FLOW_WALKTHROUGH"
    SECURITY_AUDIT = "SECURITY_AUDIT"
    API_SURFACE_REVIEW = "API_SURFACE_REVIEW"
    DEPENDENCY_ANALYSIS = "DEPENDENCY_ANALYSIS"
    ONBOARDING = "ONBOARDING"
    CUSTOM = "CUSTOM"

@dataclass
class TourStep:
    step_id: str
    title: str
    description: str
    target_file: str
    target_lines: List[int]
    diagram_ref: Optional[str] = None
    annotations: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)

@dataclass
class GuidedTour:
    tour_id: str
    title: str
    description: str
    steps: List[TourStep]
    scenario_type: TourScenario
    estimated_duration_minutes: int

class GuidedTourEngine:
    def generate_architecture_tour(self, project_root: str, options: Dict[str, Any]) -> GuidedTour:
        return GuidedTour(
            tour_id="arch-1",
            title="Architecture Tour",
            description="Tour of architecture",
            steps=[TourStep("step-1", "Main Entry", "Starts here", "main.py", [1, 2])],
            scenario_type=TourScenario.ARCHITECTURE_OVERVIEW,
            estimated_duration_minutes=15
        )

    def generate_dataflow_tour(self, project_root: str, options: Dict[str, Any]) -> GuidedTour:
        return GuidedTour(
            tour_id="df-1",
            title="Data Flow Tour",
            description="Data flow",
            steps=[],
            scenario_type=TourScenario.DATA_FLOW_WALKTHROUGH,
            estimated_duration_minutes=10
        )

    def generate_security_tour(self, project_root: str, options: Dict[str, Any]) -> GuidedTour:
        return GuidedTour(
            tour_id="sec-1",
            title="Security Tour",
            description="Security",
            steps=[],
            scenario_type=TourScenario.SECURITY_AUDIT,
            estimated_duration_minutes=20
        )

    def generate_custom_tour(self, steps: List[TourStep]) -> GuidedTour:
        return GuidedTour(
            tour_id="custom-1",
            title="Custom Tour",
            description="Custom",
            steps=steps,
            scenario_type=TourScenario.CUSTOM,
            estimated_duration_minutes=len(steps) * 2
        )

    def get_tour_progress(self, tour_id: str) -> Dict[str, Any]:
        return {"status": "in_progress", "completed_steps": []}
