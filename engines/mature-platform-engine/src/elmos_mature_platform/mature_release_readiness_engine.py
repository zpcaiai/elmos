"""Mature Release Readiness Engine (Batch 45 - Skill 1491).

Executes the comprehensive cross-pillar release readiness review for
General Availability (GA), evaluating functional, security, SRE, performance,
compliance, customer outcome, and economic evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    MatureReleaseReadinessRecord,
    PillarEvaluation,
    PillarStatus,
    ReleasePillar,
)


class MatureReleaseReadinessEngine:
    """Industrial engine for comprehensive mature release readiness reviews (B45)."""

    def __init__(self):
        self._reviews: Dict[str, MatureReleaseReadinessRecord] = {}
        self._waivers: List[Dict[str, Any]] = []
        self._audit_log: List[Dict[str, Any]] = []

    def create_readiness_review(
        self,
        release_version: str,
        lead_owner: str,
    ) -> MatureReleaseReadinessRecord:
        """Create a new mature release readiness review with default pillars."""
        review_id = f"rrr-{uuid.uuid4().hex[:8]}"

        # Initialize all 7 standard maturity pillars
        pillars: Dict[str, PillarEvaluation] = {}
        for p in ReleasePillar:
            pillars[p.value] = PillarEvaluation(
                pillar=p,
                status=PillarStatus.NOT_STARTED,
                score=0.0,
                blocking_issues=[],
                lead_owner=lead_owner,
                evidence_hashes=[],
                notes="",
            )

        review = MatureReleaseReadinessRecord(
            review_id=review_id,
            target_release=release_version,
            pillars=pillars,
            overall_score=0.0,
            ready_for_general_availability=False,
            sign_off_director="",
            reviewed_at="",
        )
        self._reviews[review_id] = review
        self._record_audit("create_readiness_review", review_id, {
            "version": release_version,
            "owner": lead_owner,
        })
        return review

    def record_pillar_evaluation(
        self,
        review_id: str,
        eval_data: PillarEvaluation,
    ) -> MatureReleaseReadinessRecord:
        """Submit assessment and evidence for a specific readiness pillar."""
        review = self._get_review_or_raise(review_id)
        review.pillars[eval_data.pillar.value] = eval_data

        # Recalculate average score
        scores = [p.score for p in review.pillars.values()]
        review.overall_score = round(sum(scores) / len(scores), 2)

        self._record_audit("record_pillar_evaluation", review_id, {
            "pillar": eval_data.pillar.value,
            "status": eval_data.status.value,
            "score": eval_data.score,
            "blockers_count": len(eval_data.blocking_issues),
        })
        return review

    def waive_pillar_blocker(
        self,
        review_id: str,
        pillar: ReleasePillar,
        waiver_reason: str,
        approved_by: str,
    ) -> MatureReleaseReadinessRecord:
        """Grant an explicit, audit-tracked waiver for a specific blocked pillar."""
        review = self._get_review_or_raise(review_id)
        pillar_entry = review.pillars.get(pillar.value)
        if not pillar_entry:
            raise ValueError(f"Pillar {pillar.value} not present in review")

        pillar_entry.status = PillarStatus.WAIVED
        pillar_entry.notes = f"WAIVED: {waiver_reason} (Approved by: {approved_by})"

        waiver_record = {
            "review_id": review_id,
            "pillar": pillar.value,
            "reason": waiver_reason,
            "approved_by": approved_by,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._waivers.append(waiver_record)
        self._record_audit("waive_pillar_blocker", review_id, waiver_record)
        return review

    def evaluate_general_availability(
        self,
        review_id: str,
        sign_off_director: str,
    ) -> MatureReleaseReadinessRecord:
        """Evaluate if release satisfies all strict GA criteria (no open blockers, score >= 90)."""
        review = self._get_review_or_raise(review_id)
        review.reviewed_at = datetime.now(timezone.utc).isoformat()

        # Check: Every pillar must be PASSED or WAIVED
        unpassed = [
            p for p in review.pillars.values()
            if p.status not in (PillarStatus.PASSED, PillarStatus.WAIVED)
        ]

        # Check: Total blocking issues across all pillars
        total_blockers = sum(len(p.blocking_issues) for p in review.pillars.values() if p.status != PillarStatus.WAIVED)

        # GA decision
        if len(unpassed) == 0 and total_blockers == 0 and review.overall_score >= 90.0:
            review.ready_for_general_availability = True
            review.sign_off_director = sign_off_director
        else:
            review.ready_for_general_availability = False
            review.sign_off_director = ""

        self._record_audit("evaluate_ga", review_id, {
            "ready_for_ga": review.ready_for_general_availability,
            "director": sign_off_director,
            "score": review.overall_score,
            "unpassed_pillars": [p.pillar.value for p in unpassed],
        })
        return review

    def get_readiness_scorecard(self, review_id: str) -> Dict[str, Any]:
        """Produce full executive readiness scorecard."""
        review = self._get_review_or_raise(review_id)
        pillar_summaries = {}
        for k, p in review.pillars.items():
            pillar_summaries[k] = {
                "status": p.status.value,
                "score": p.score,
                "blockers": p.blocking_issues,
                "lead_owner": p.lead_owner,
                "evidence_count": len(p.evidence_hashes),
            }

        return {
            "review_id": review.review_id,
            "target_release": review.target_release,
            "overall_score": review.overall_score,
            "ready_for_general_availability": review.ready_for_general_availability,
            "sign_off_director": review.sign_off_director,
            "reviewed_at": review.reviewed_at,
            "pillars": pillar_summaries,
            "waivers_granted": [w for w in self._waivers if w["review_id"] == review_id],
        }

    def get_unresolved_blockers(self, review_id: str) -> List[Dict[str, Any]]:
        """Return all unresolved blockers across all un-waived pillars."""
        review = self._get_review_or_raise(review_id)
        blockers: List[Dict[str, Any]] = []
        for p in review.pillars.values():
            if p.status != PillarStatus.WAIVED and p.blocking_issues:
                for b in p.blocking_issues:
                    blockers.append({
                        "pillar": p.pillar.value,
                        "blocker": b,
                        "lead_owner": p.lead_owner,
                    })
        return blockers

    def _get_review_or_raise(self, review_id: str) -> MatureReleaseReadinessRecord:
        if review_id not in self._reviews:
            raise ValueError(f"Readiness review {review_id} not found")
        return self._reviews[review_id]

    def _record_audit(self, action: str, target: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })
