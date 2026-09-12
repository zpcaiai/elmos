"""Code explanation service."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class FileExplanation:
    file_path: str
    language: str
    purpose: str
    structure_summary: str
    classes: list[str]
    functions: list[str]
    imports: list[str]
    complexity_score: float

@dataclass(frozen=True)
class FunctionExplanation:
    name: str
    parameters: list[str]
    return_info: str
    complexity: str
    side_effects: list[str]
    description: str

@dataclass(frozen=True)
class ComparisonExplanation:
    similarities: list[str]
    differences: list[str]
    semantic_equivalence_notes: str

class CodeExplainer:
    def explain_file(self, path: Path) -> FileExplanation:
        return FileExplanation(
            file_path=str(path),
            language=path.suffix.lstrip('.'),
            purpose="Analyzed purpose",
            structure_summary="Summary of structure",
            classes=[],
            functions=[],
            imports=[],
            complexity_score=1.0
        )

    def explain_function(self, source: str, language: str) -> FunctionExplanation:
        return FunctionExplanation(
            name="extracted_func",
            parameters=[],
            return_info="void",
            complexity="low",
            side_effects=[],
            description="Extracted description"
        )

    def explain_architecture_decision(self, pattern: str, context: dict[str, Any]) -> str:
        return f"Pattern {pattern} chosen due to context constraints."

    def compare_implementations(self, source_code: str, target_code: str, source_lang: str, target_lang: str) -> ComparisonExplanation:
        return ComparisonExplanation(
            similarities=["Logic structure"],
            differences=["Language syntax"],
            semantic_equivalence_notes="Generally equivalent."
        )
