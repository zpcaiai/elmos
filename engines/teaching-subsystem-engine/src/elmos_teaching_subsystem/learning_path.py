"""Learning path recommendation service."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

@dataclass(frozen=True)
class LearningStep:
    order: int
    title: str
    description: str
    files_to_read: list[str]
    concepts: list[str]
    estimated_minutes: int
    exercises: list[str]

@dataclass(frozen=True)
class LearningPath:
    title: str
    description: str
    steps: list[LearningStep]
    estimated_hours: float
    prerequisite_skills: list[str]

class LearningPathRecommender:
    def recommend_onboarding_path(self, project_root: Path, role: str) -> LearningPath:
        steps = [
            LearningStep(
                order=1,
                title="Understand entry point",
                description="Read main program logic",
                files_to_read=[],
                concepts=["entrypoint"],
                estimated_minutes=30,
                exercises=[]
            )
        ]
        return LearningPath(
            title=f"Onboarding for {role}",
            description="Path to learn codebase",
            steps=steps,
            estimated_hours=0.5,
            prerequisite_skills=["Basic programming"]
        )
