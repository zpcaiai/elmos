"""PSIR requirement refinement and validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    message: str
    location: str

@dataclass(frozen=True)
class CompletionSuggestion:
    target: str
    suggestion: str
    rationale: str
    priority: str

@dataclass(frozen=True)
class RefinementReport:
    issues: list[ValidationIssue]
    suggestions: list[CompletionSuggestion]
    completeness_score: float

class PSIRValidator:
    def validate(self, psir: dict[str, Any]) -> list[ValidationIssue]:
        issues = []
        entities = psir.get("entities", [])
        for entity in entities:
            fields = entity.get("fields", [])
            has_pk = any(f.get("is_primary_key") for f in fields)
            if not has_pk:
                issues.append(ValidationIssue("error", f"Entity {entity.get('name', 'Unknown')} missing primary key", f"entities.{entity.get('name')}"))
        return issues

class PSIRCompleter:
    def complete(self, psir: dict[str, Any]) -> list[CompletionSuggestion]:
        suggestions = []
        entities = psir.get("entities", [])
        for entity in entities:
            fields = [f.get("name") for f in entity.get("fields", [])]
            if "created_at" not in fields or "updated_at" not in fields:
                suggestions.append(CompletionSuggestion(
                    target=f"entities.{entity.get('name')}",
                    suggestion="Add created_at and updated_at fields",
                    rationale="Audit fields are recommended for all entities",
                    priority="high"
                ))
        return suggestions

class RequirementRefiner:
    def __init__(self) -> None:
        self.validator = PSIRValidator()
        self.completer = PSIRCompleter()

    def refine(self, psir: dict[str, Any]) -> RefinementReport:
        issues = self.validator.validate(psir)
        suggestions = self.completer.complete(psir)
        score = 100.0 - (len(issues) * 10) - (len(suggestions) * 5)
        return RefinementReport(
            issues=issues,
            suggestions=suggestions,
            completeness_score=max(0.0, score)
        )
