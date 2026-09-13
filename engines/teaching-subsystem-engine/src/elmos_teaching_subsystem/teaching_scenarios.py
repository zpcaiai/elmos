from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

class ScenarioCategory(Enum):
    ONBOARDING = "ONBOARDING"
    ARCHITECTURE_REVIEW = "ARCHITECTURE_REVIEW"
    SECURITY_AUDIT = "SECURITY_AUDIT"
    PERFORMANCE_REVIEW = "PERFORMANCE_REVIEW"
    CODE_REVIEW = "CODE_REVIEW"
    DATABASE_DESIGN = "DATABASE_DESIGN"
    API_DESIGN = "API_DESIGN"

class DifficultyLevel(Enum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"
    EXPERT = "EXPERT"

@dataclass
class ScenarioStep:
    step_id: str
    title: str
    instruction: str
    expected_action: str
    hints: List[str] = field(default_factory=list)
    validation_criteria: List[str] = field(default_factory=list)
    related_diagrams: List[str] = field(default_factory=list)

@dataclass
class ScenarioTemplate:
    scenario_id: str
    title: str
    description: str
    category: ScenarioCategory
    difficulty: DifficultyLevel
    estimated_duration: int
    steps: List[ScenarioStep]
    prerequisites: List[str] = field(default_factory=list)
    learning_objectives: List[str] = field(default_factory=list)

def create_onboarding_scenario(project_root: str) -> ScenarioTemplate:
    return ScenarioTemplate(
        scenario_id="onboard-1",
        title="Onboarding",
        description="Welcome to the project",
        category=ScenarioCategory.ONBOARDING,
        difficulty=DifficultyLevel.BEGINNER,
        estimated_duration=60,
        steps=[ScenarioStep("step1", "Setup", "Run setup", "run setup script")]
    )

def create_architecture_review_scenario(project_root: str) -> ScenarioTemplate:
    return ScenarioTemplate(
        scenario_id="arch-1",
        title="Arch Review",
        description="Review architecture",
        category=ScenarioCategory.ARCHITECTURE_REVIEW,
        difficulty=DifficultyLevel.INTERMEDIATE,
        estimated_duration=120,
        steps=[]
    )

def create_security_audit_scenario(project_root: str) -> ScenarioTemplate:
    return ScenarioTemplate(
        scenario_id="sec-1",
        title="Security Audit",
        description="Find vulnerabilities",
        category=ScenarioCategory.SECURITY_AUDIT,
        difficulty=DifficultyLevel.ADVANCED,
        estimated_duration=90,
        steps=[]
    )

def create_performance_review_scenario(project_root: str) -> ScenarioTemplate:
    return ScenarioTemplate(
        scenario_id="perf-1",
        title="Performance",
        description="Find bottlenecks",
        category=ScenarioCategory.PERFORMANCE_REVIEW,
        difficulty=DifficultyLevel.ADVANCED,
        estimated_duration=90,
        steps=[]
    )

class TeachingEngine:
    def orchestrate(self, scenario: ScenarioTemplate) -> str:
        return f"Orchestrating {scenario.scenario_id}"
    
    def track_progress(self, session_id: str) -> Dict[str, Any]:
        return {"status": "in_progress"}

    def generate_report(self, session_id: str) -> Dict[str, Any]:
        return {"report": "done"}
