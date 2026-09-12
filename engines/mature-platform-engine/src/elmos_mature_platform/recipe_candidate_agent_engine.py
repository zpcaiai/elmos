"""Recipe Candidate Agent Engine (Batch 42 - Skill 1431).

Discovers, synthesizes, and evaluates candidate transformation recipes mined from
successful refactoring diffs, assessing confidence scores, deduplicating patterns,
and governing staging before promotion to canonical migration knowledge.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    RecipeCandidateStatus,
    SynthesizedRecipeCandidate,
)


class RecipeCandidateAgentEngine:
    """Agentic pattern miner and recipe candidate synthesizer for automated refactoring."""

    def __init__(self) -> None:
        self._candidates: Dict[str, SynthesizedRecipeCandidate] = {}

    def register_candidate(self, candidate: SynthesizedRecipeCandidate) -> str:
        """Register a newly discovered or synthesized transformation pattern."""
        if not candidate.name or not candidate.source_pattern or not candidate.target_transformation:
            raise ValueError("name, source_pattern, and target_transformation are required")

        if not candidate.candidate_id:
            candidate.candidate_id = f"rcand-{uuid.uuid4().hex[:8]}"

        if not candidate.created_at:
            candidate.created_at = datetime.now(timezone.utc).isoformat()

        candidate.status = RecipeCandidateStatus.DISCOVERED
        candidate.confidence_score = 0.5

        self._candidates[candidate.candidate_id] = candidate
        return candidate.candidate_id

    def record_pattern_occurrence(self, candidate_id: str) -> SynthesizedRecipeCandidate:
        """Record an additional occurrence of the pattern in codebase diffs, increasing confidence."""
        cand = self._candidates.get(candidate_id)
        if not cand:
            raise ValueError(f"Recipe candidate not found: {candidate_id}")

        cand.occurrence_count += 1
        cand.confidence_score = min(1.0, 0.5 + (cand.occurrence_count * 0.05))

        if cand.occurrence_count >= 5 and cand.status == RecipeCandidateStatus.DISCOVERED:
            cand.status = RecipeCandidateStatus.SYNTHESIZED

        return cand

    def approve_candidate(self, candidate_id: str, approver: str) -> SynthesizedRecipeCandidate:
        """Approve a synthesized recipe for production promotion to the recipe registry."""
        cand = self._candidates.get(candidate_id)
        if not cand:
            raise ValueError(f"Recipe candidate not found: {candidate_id}")
        if not approver:
            raise ValueError("approver is required to approve recipe candidate")

        cand.status = RecipeCandidateStatus.APPROVED
        cand.approver = approver
        return cand

    def reject_candidate(self, candidate_id: str, reason: str = "") -> SynthesizedRecipeCandidate:
        """Reject a candidate recipe that causes regressions or is semantically incorrect."""
        cand = self._candidates.get(candidate_id)
        if not cand:
            raise ValueError(f"Recipe candidate not found: {candidate_id}")

        cand.status = RecipeCandidateStatus.REJECTED
        return cand

    def get_candidate(self, candidate_id: str) -> Optional[SynthesizedRecipeCandidate]:
        """Retrieve recipe candidate details."""
        return self._candidates.get(candidate_id)

    def get_candidates_by_status(
        self, status: RecipeCandidateStatus
    ) -> List[SynthesizedRecipeCandidate]:
        """Filter candidates by lifecycle status."""
        return [c for c in self._candidates.values() if c.status == status]

    def get_recipe_candidate_report(self) -> Dict[str, Any]:
        """Generate summary report of mined recipe candidates and status metrics."""
        total = len(self._candidates)
        by_status: Dict[str, int] = {}
        for c in self._candidates.values():
            st = c.status.value
            by_status[st] = by_status.get(st, 0) + 1

        avg_conf = (
            sum(c.confidence_score for c in self._candidates.values()) / total
            if total > 0 else 0.0
        )

        return {
            "total_candidates": total,
            "by_status": by_status,
            "average_confidence_score": avg_conf,
            "high_confidence_count": sum(1 for c in self._candidates.values() if c.confidence_score >= 0.8),
        }
