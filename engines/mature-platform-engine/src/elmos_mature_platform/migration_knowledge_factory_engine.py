"""Migration Knowledge Factory Engine (Batch 41 - Skill 1393).

Turns migration outcomes, rules, repair patterns, and counterexamples into governed,
categorized, reusable migration knowledge units with rigorous confidence promotion.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    KnowledgeConfidenceLevel,
    KnowledgeIngestionReceipt,
    KnowledgeItemType,
    MigrationKnowledgeUnit,
)


class MigrationKnowledgeFactoryEngine:
    """Curates, governs, and retrieves verified migration recipes, antipatterns, and repairs."""

    def __init__(self) -> None:
        self._units: Dict[str, MigrationKnowledgeUnit] = {}
        self._receipts: List[KnowledgeIngestionReceipt] = []

    def ingest_knowledge_unit(
        self, unit: MigrationKnowledgeUnit, project_ref: str = ""
    ) -> KnowledgeIngestionReceipt:
        """Ingest a new candidate knowledge unit into the factory registry."""
        if not unit.source_language_or_framework or not unit.target_language_or_framework:
            raise ValueError("source and target language/framework are required")
        if not unit.title:
            raise ValueError("title is required")

        if not unit.unit_id:
            unit.unit_id = f"mku-{uuid.uuid4().hex[:8]}"

        if not unit.created_at:
            unit.created_at = datetime.now(timezone.utc).isoformat()

        self._units[unit.unit_id] = unit

        receipt = KnowledgeIngestionReceipt(
            receipt_id=f"rcpt-{uuid.uuid4().hex[:8]}",
            unit_id=unit.unit_id,
            source_project_ref=project_ref,
            status="ingested",
            ingested_at=datetime.now(timezone.utc).isoformat(),
        )
        self._receipts.append(receipt)
        return receipt

    def promote_confidence(
        self, unit_id: str, new_level: KnowledgeConfidenceLevel, approver: str = ""
    ) -> MigrationKnowledgeUnit:
        """Promote knowledge unit confidence level (requires human approver for GOLD_CERTIFIED)."""
        unit = self._units.get(unit_id)
        if not unit:
            raise ValueError(f"Knowledge unit not found: {unit_id}")

        if new_level == KnowledgeConfidenceLevel.GOLD_CERTIFIED and not approver:
            raise PermissionError("Human approver required to promote to GOLD_CERTIFIED")

        unit.confidence_level = new_level
        return unit

    def record_usage(self, unit_id: str, success: bool) -> MigrationKnowledgeUnit:
        """Record execution outcome when this knowledge unit was applied."""
        unit = self._units.get(unit_id)
        if not unit:
            raise ValueError(f"Knowledge unit not found: {unit_id}")

        total = unit.usage_count + 1
        prev_successes = unit.usage_count * unit.success_rate
        new_successes = prev_successes + (1.0 if success else 0.0)

        unit.usage_count = total
        unit.success_rate = round(new_successes / total, 4)
        return unit

    def search_knowledge(
        self,
        source: str,
        target: str,
        item_type: Optional[KnowledgeItemType] = None,
        tags: Optional[List[str]] = None,
    ) -> List[MigrationKnowledgeUnit]:
        """Search for knowledge matching source/target route and filters, excluding DEPRECATED."""
        matches = []
        for u in self._units.values():
            if u.confidence_level == KnowledgeConfidenceLevel.DEPRECATED:
                continue

            if source.lower() not in u.source_language_or_framework.lower():
                continue
            if target.lower() not in u.target_language_or_framework.lower():
                continue

            if item_type and u.item_type != item_type:
                continue

            if tags:
                if not any(tag in u.tags for tag in tags):
                    continue

            matches.append(u)

        return sorted(matches, key=lambda x: (x.success_rate, x.usage_count), reverse=True)

    def deprecate_unit(self, unit_id: str, reason: str) -> MigrationKnowledgeUnit:
        """Mark a knowledge unit as deprecated with cause."""
        unit = self._units.get(unit_id)
        if not unit:
            raise ValueError(f"Knowledge unit not found: {unit_id}")

        unit.confidence_level = KnowledgeConfidenceLevel.DEPRECATED
        unit.tags.append(f"deprecated_reason:{reason}")
        return unit

    def get_golden_recipes(self, source: str, target: str) -> List[MigrationKnowledgeUnit]:
        """Retrieve only GOLD_CERTIFIED units for a given route."""
        results = self.search_knowledge(source, target)
        return [u for u in results if u.confidence_level == KnowledgeConfidenceLevel.GOLD_CERTIFIED]

    def get_unit(self, unit_id: str) -> Optional[MigrationKnowledgeUnit]:
        """Retrieve unit by ID."""
        return self._units.get(unit_id)

    def get_factory_knowledge_report(self) -> Dict[str, Any]:
        """Generate aggregated repository knowledge inventory report."""
        total = len(self._units)
        by_type: Dict[str, int] = {}
        for it in KnowledgeItemType:
            by_type[it.value] = sum(1 for u in self._units.values() if u.item_type == it)

        by_conf: Dict[str, int] = {}
        for cl in KnowledgeConfidenceLevel:
            by_conf[cl.value] = sum(1 for u in self._units.values() if u.confidence_level == cl)

        total_uses = sum(u.usage_count for u in self._units.values())
        avg_success = (
            round(sum(u.success_rate * u.usage_count for u in self._units.values()) / total_uses, 4)
            if total_uses > 0
            else 0.0
        )

        return {
            "total_knowledge_units": total,
            "units_by_type": by_type,
            "units_by_confidence": by_conf,
            "total_applied_usages": total_uses,
            "overall_empirical_success_rate": avg_success,
        }
