"""Knowledge Flywheel Engine module."""

import math
from typing import Any, Dict, List, Optional, Tuple

from elmos_mature_platform.types import (
    KnowledgeConfidence,
    KnowledgeEntry,
    MigrationPattern,
    PredictionResult,
)


class KnowledgeFlywheelEngine:
    """Engine for the Knowledge Flywheel."""

    def __init__(self) -> None:
        """Initialize empty knowledge store, pattern registry, prediction models."""
        self.knowledge_store: Dict[str, KnowledgeEntry] = {}
        self.pattern_registry: Dict[str, MigrationPattern] = {}
        self.prediction_models: Dict[str, Any] = {}

    def ingest_knowledge(self, entry: KnowledgeEntry) -> None:
        """Add to store. Auto-increment usage_count if duplicate entry_id."""
        if entry.entry_id in self.knowledge_store:
            existing = self.knowledge_store[entry.entry_id]
            existing.usage_count += 1
        else:
            self.knowledge_store[entry.entry_id] = entry

    def query_knowledge(
        self,
        source_tech: str,
        target_tech: str,
        category: Optional[str] = None,
        min_confidence: KnowledgeConfidence = KnowledgeConfidence.LOW,
    ) -> List[KnowledgeEntry]:
        """Filter and return matching entries, sorted by confidence desc then usage_count desc."""
        confidence_levels = {
            KnowledgeConfidence.UNVERIFIED: 0,
            KnowledgeConfidence.LOW: 1,
            KnowledgeConfidence.MEDIUM: 2,
            KnowledgeConfidence.HIGH: 3,
            KnowledgeConfidence.VERIFIED: 4,
        }
        
        min_val = confidence_levels.get(min_confidence, 0)
        results = []
        for entry in self.knowledge_store.values():
            if entry.source_technology != source_tech or entry.target_technology != target_tech:
                continue
            if category is not None and entry.category != category:
                continue
            if confidence_levels.get(entry.confidence, 0) < min_val:
                continue
            results.append(entry)
            
        results.sort(key=lambda e: (confidence_levels.get(e.confidence, 0), e.usage_count), reverse=True)
        return results

    def extract_pattern(self, source_stack: str, target_stack: str, entries: List[str]) -> MigrationPattern:
        """From knowledge entry IDs, create a reusable pattern. Compute complexity from entry count and average confidence."""
        valid_entries = [self.knowledge_store[eid] for eid in entries if eid in self.knowledge_store]
        entry_count = len(valid_entries)
        
        confidence_levels = {
            KnowledgeConfidence.UNVERIFIED: 0,
            KnowledgeConfidence.LOW: 1,
            KnowledgeConfidence.MEDIUM: 2,
            KnowledgeConfidence.HIGH: 3,
            KnowledgeConfidence.VERIFIED: 4,
        }
        
        avg_conf = 0.0
        if entry_count > 0:
            avg_conf = sum(confidence_levels.get(e.confidence, 0) for e in valid_entries) / entry_count
            
        if entry_count > 10 or avg_conf < 1.5:
            complexity = "high"
        elif entry_count > 5 or avg_conf < 2.5:
            complexity = "medium"
        else:
            complexity = "low"
            
        pattern = MigrationPattern(
            pattern_id=f"pat_{source_stack}_{target_stack}",
            name=f"Migration from {source_stack} to {target_stack}",
            source_stack=source_stack,
            target_stack=target_stack,
            complexity=complexity,
            estimated_effort_hours=entry_count * 10.0,
            success_count=sum(1 for e in valid_entries if e.success_rate > 0.8),
            failure_count=sum(1 for e in valid_entries if e.success_rate <= 0.8),
        )
        self.pattern_registry[pattern.pattern_id] = pattern
        return pattern

    def predict_migration_risk(self, source_stack: str, target_stack: str, repo_size_loc: int, dependency_count: int) -> PredictionResult:
        """Simple model: risk = base_risk * (1 + log(loc/1000)) * (1 + dep_count/50). Confidence interval from pattern success_rate."""
        base_risk = 0.1
        loc_factor = 1.0
        if repo_size_loc >= 1000:
            loc_factor = 1.0 + math.log(repo_size_loc / 1000)
            
        dep_factor = 1.0 + (dependency_count / 50.0)
        risk = base_risk * loc_factor * dep_factor
        
        pattern_id = f"pat_{source_stack}_{target_stack}"
        success_rate = 0.5
        if pattern_id in self.pattern_registry:
            pat = self.pattern_registry[pattern_id]
            total = pat.success_count + pat.failure_count
            if total > 0:
                success_rate = pat.success_count / total
                
        interval = 0.1 / max(0.1, success_rate)
        return PredictionResult(
            prediction_id=f"pred_risk_{source_stack}_{target_stack}",
            prediction_type="risk",
            predicted_value=min(1.0, risk),
            confidence_interval_low=max(0.0, risk - interval),
            confidence_interval_high=min(1.0, risk + interval),
            model_version="1.0.0",
        )

    def predict_effort(self, source_stack: str, target_stack: str, repo_size_loc: int) -> PredictionResult:
        """Effort = base_hours * (loc / 1000) * complexity_multiplier. Based on matched patterns."""
        base_hours = 40.0
        loc_k = max(1.0, repo_size_loc / 1000.0)
        
        pattern_id = f"pat_{source_stack}_{target_stack}"
        complexity_mult = 1.0
        if pattern_id in self.pattern_registry:
            comp = self.pattern_registry[pattern_id].complexity
            if comp == "low":
                complexity_mult = 0.8
            elif comp == "medium":
                complexity_mult = 1.2
            elif comp == "high":
                complexity_mult = 2.0
            elif comp == "critical":
                complexity_mult = 3.5
                
        effort = base_hours * loc_k * complexity_mult
        return PredictionResult(
            prediction_id=f"pred_effort_{source_stack}_{target_stack}",
            prediction_type="effort",
            predicted_value=effort,
            confidence_interval_low=effort * 0.8,
            confidence_interval_high=effort * 1.2,
            model_version="1.0.0",
        )

    def validate_prediction_calibration(self, predictions: List[Tuple[str, float, float]]) -> float:
        """Given (id, predicted, actual) triples, compute calibration score (1 - mean absolute error / mean actual)."""
        if not predictions:
            return 0.0
        
        sum_abs_error = 0.0
        sum_actual = 0.0
        for _, pred, act in predictions:
            sum_abs_error += abs(pred - act)
            sum_actual += act
            
        mean_abs_error = sum_abs_error / len(predictions)
        mean_actual = sum_actual / len(predictions)
        
        if mean_actual == 0:
            return 0.0
            
        score = 1.0 - (mean_abs_error / mean_actual)
        return max(0.0, min(1.0, score))

    def isolate_tenant_knowledge(self, tenant_id: str) -> List[KnowledgeEntry]:
        """Return only entries belonging to this tenant."""
        return [e for e in self.knowledge_store.values() if e.tenant_id == tenant_id]

    def get_knowledge_stats(self) -> Dict[str, Any]:
        """Summary: total_entries, by_category, by_confidence, top_patterns."""
        stats = {
            "total_entries": len(self.knowledge_store),
            "by_category": {},
            "by_confidence": {},
            "top_patterns": []
        }
        
        for e in self.knowledge_store.values():
            stats["by_category"][e.category] = stats["by_category"].get(e.category, 0) + 1
            stats["by_confidence"][e.confidence] = stats["by_confidence"].get(e.confidence, 0) + 1
            
        pats = list(self.pattern_registry.values())
        pats.sort(key=lambda p: p.success_count, reverse=True)
        stats["top_patterns"] = [p.pattern_id for p in pats[:5]]
        
        return stats

    def recommend_recipe(self, source_stack: str, target_stack: str) -> List[MigrationPattern]:
        """Return patterns sorted by success_rate descending."""
        patterns = []
        for p in self.pattern_registry.values():
            if p.source_stack == source_stack and p.target_stack == target_stack:
                patterns.append(p)
                
        def success_rate(p):
            tot = p.success_count + p.failure_count
            return p.success_count / tot if tot > 0 else 0.0
            
        patterns.sort(key=success_rate, reverse=True)
        return patterns
