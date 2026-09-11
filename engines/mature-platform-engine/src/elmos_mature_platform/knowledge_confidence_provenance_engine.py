"""Knowledge Confidence and Provenance Engine (Batch 41 - Skill 1405).

Tracks empirical run evidence, calculates statistical confidence scores,
evaluates confidence levels (unverified, experimental, production proven, gold certified),
and applies time-decay policies across repository transformation knowledge.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    EvidenceProvenanceRecord,
    KnowledgeConfidenceLevel,
    KnowledgeDecayPolicy,
)


class KnowledgeConfidenceProvenanceEngine:
    """Industrial engine for knowledge confidence scoring and provenance tracking (B41)."""

    def __init__(self, default_decay_policy: Optional[KnowledgeDecayPolicy] = None):
        self.default_decay_policy = default_decay_policy or KnowledgeDecayPolicy(
            policy_id="default-90d-half-life",
            half_life_days=90,
            min_confidence_floor=0.2,
        )
        self._records: Dict[str, EvidenceProvenanceRecord] = {}  # knowledge_id -> record
        self._audit_history: List[Dict[str, Any]] = []

    def _determine_level(self, score: float, successes: int, failures: int) -> KnowledgeConfidenceLevel:
        """Derive confidence level based on score and empirical volume thresholds."""
        if successes >= 20 and failures == 0 and score >= 0.90:
            return KnowledgeConfidenceLevel.GOLD_CERTIFIED
        elif successes >= 20 and score >= 0.88:
            return KnowledgeConfidenceLevel.GOLD_CERTIFIED
        elif successes >= 5 and score >= 0.70:
            return KnowledgeConfidenceLevel.PRODUCTION_PROVEN
        elif score >= 0.40:
            return KnowledgeConfidenceLevel.EXPERIMENTAL
        else:
            return KnowledgeConfidenceLevel.UNVERIFIED

    def register_provenance(
        self,
        knowledge_id: str,
        source_run_id: str,
        author: str = "flywheel",
        initial_score: float = 0.5,
        citations: Optional[List[str]] = None,
    ) -> EvidenceProvenanceRecord:
        """Register a new knowledge item with baseline provenance."""
        if knowledge_id in self._records:
            raise ValueError(f"Knowledge provenance for '{knowledge_id}' already registered")

        provenance_id = f"prov-{uuid.uuid4().hex[:8]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        initial_level = self._determine_level(initial_score, 0, 0)

        record = EvidenceProvenanceRecord(
            provenance_id=provenance_id,
            knowledge_id=knowledge_id,
            source_run_id=source_run_id,
            author=author,
            empirical_success_count=0,
            empirical_failure_count=0,
            confidence_score=initial_score,
            confidence_level=initial_level,
            last_empirically_verified=now_iso,
            citation_urls=citations or [],
        )
        self._records[knowledge_id] = record
        self._audit_history.append({
            "action": "REGISTER",
            "knowledge_id": knowledge_id,
            "provenance_id": provenance_id,
            "timestamp": now_iso,
        })
        return record

    def record_empirical_outcome(
        self,
        knowledge_id: str,
        success: bool,
        weight: float = 1.0,
    ) -> EvidenceProvenanceRecord:
        """Incorporate a live execution run result into empirical confidence."""
        record = self._records.get(knowledge_id)
        if not record:
            raise ValueError(f"Knowledge '{knowledge_id}' not registered")

        if record.confidence_level == KnowledgeConfidenceLevel.DEPRECATED:
            raise ValueError(f"Cannot record outcome on deprecated knowledge '{knowledge_id}'")

        if success:
            record.empirical_success_count += int(weight)
        else:
            record.empirical_failure_count += int(weight)

        s = record.empirical_success_count
        f = record.empirical_failure_count
        # Empirical Bayesian posterior with Beta(2, 2) prior (prior mean = 0.5)
        new_score = round((s + 2.0) / (s + f + 4.0), 4)
        record.confidence_score = new_score
        record.confidence_level = self._determine_level(new_score, s, f)
        record.last_empirically_verified = datetime.now(timezone.utc).isoformat()

        self._audit_history.append({
            "action": "OUTCOME",
            "knowledge_id": knowledge_id,
            "success": success,
            "new_score": new_score,
            "new_level": record.confidence_level.value,
            "timestamp": record.last_empirically_verified,
        })
        return record

    def deprecate_knowledge(
        self,
        knowledge_id: str,
        reason: str = "Obsolete pattern",
    ) -> EvidenceProvenanceRecord:
        """Mark knowledge as deprecated with zero confidence score."""
        record = self._records.get(knowledge_id)
        if not record:
            raise ValueError(f"Knowledge '{knowledge_id}' not registered")

        record.confidence_level = KnowledgeConfidenceLevel.DEPRECATED
        record.confidence_score = 0.0
        now_iso = datetime.now(timezone.utc).isoformat()
        self._audit_history.append({
            "action": "DEPRECATE",
            "knowledge_id": knowledge_id,
            "reason": reason,
            "timestamp": now_iso,
        })
        return record

    def apply_time_decay(
        self,
        knowledge_id: str,
        elapsed_days: float,
        policy: Optional[KnowledgeDecayPolicy] = None,
    ) -> EvidenceProvenanceRecord:
        """Apply exponential half-life time decay to knowledge confidence score."""
        record = self._records.get(knowledge_id)
        if not record:
            raise ValueError(f"Knowledge '{knowledge_id}' not registered")

        if record.confidence_level == KnowledgeConfidenceLevel.DEPRECATED:
            return record

        pol = policy or self.default_decay_policy
        if elapsed_days < 0:
            raise ValueError("Elapsed days cannot be negative")

        half_life = float(pol.half_life_days)
        decay_factor = math.pow(0.5, elapsed_days / half_life)
        decayed_score = record.confidence_score * decay_factor
        floor = pol.min_confidence_floor
        record.confidence_score = round(max(floor, decayed_score), 4)

        record.confidence_level = self._determine_level(
            record.confidence_score,
            record.empirical_success_count,
            record.empirical_failure_count,
        )
        return record

    def get_provenance(self, knowledge_id: str) -> Optional[EvidenceProvenanceRecord]:
        """Retrieve record for a specific knowledge ID."""
        return self._records.get(knowledge_id)

    def get_provenance_chain(self, knowledge_id: str) -> Dict[str, Any]:
        """Retrieve complete audit provenance and history for an item."""
        record = self._records.get(knowledge_id)
        if not record:
            raise ValueError(f"Knowledge '{knowledge_id}' not found")

        events = [e for e in self._audit_history if e.get("knowledge_id") == knowledge_id]
        return {
            "knowledge_id": record.knowledge_id,
            "provenance_id": record.provenance_id,
            "author": record.author,
            "source_run_id": record.source_run_id,
            "confidence_score": record.confidence_score,
            "confidence_level": record.confidence_level.value,
            "empirical_success_count": record.empirical_success_count,
            "empirical_failure_count": record.empirical_failure_count,
            "citations": record.citation_urls,
            "last_verified": record.last_empirically_verified,
            "history": events,
        }

    def list_records_by_level(self, level: KnowledgeConfidenceLevel) -> List[EvidenceProvenanceRecord]:
        """Filter records by confidence level."""
        return [r for r in self._records.values() if r.confidence_level == level]

    def get_provenance_summary(self) -> Dict[str, Any]:
        """Aggregate metrics across all tracked knowledge assets."""
        counts: Dict[str, int] = {}
        for lvl in KnowledgeConfidenceLevel:
            counts[lvl.value] = 0

        total_score = 0.0
        total_runs = 0

        for r in self._records.values():
            counts[r.confidence_level.value] += 1
            total_score += r.confidence_score
            total_runs += (r.empirical_success_count + r.empirical_failure_count)

        total_records = len(self._records)
        avg_score = round(total_score / total_records, 4) if total_records > 0 else 0.0

        return {
            "total_knowledge_assets": total_records,
            "average_confidence_score": avg_score,
            "total_empirical_runs": total_runs,
            "counts_by_level": counts,
        }
