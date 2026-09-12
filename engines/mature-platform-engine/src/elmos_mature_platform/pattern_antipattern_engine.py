import uuid
from typing import List, Dict, Optional
from datetime import datetime

from .types import (
    PatternType,
    PatternConfidence,
    PatternRecord,
    PatternMatch,
    PatternRule
)

class PatternAntipatternEngine:
    """
    Engine for pattern and antipattern extraction and knowledge.
    """
    
    def __init__(self):
        self._patterns: Dict[str, PatternRecord] = {}
        self._matches: Dict[str, List[PatternMatch]] = {}
        self._rules: Dict[str, PatternRule] = {}
        
    def register_pattern(self, pattern: PatternRecord) -> str:
        """
        Register a pattern or antipattern.
        """
        if pattern.is_antipattern and not pattern.fix_suggestion:
            raise ValueError("Antipatterns must have a fix_suggestion.")
            
        self._patterns[pattern.pattern_id] = pattern
        if pattern.pattern_id not in self._matches:
            self._matches[pattern.pattern_id] = []
        return pattern.pattern_id
        
    def record_match(self, match: PatternMatch) -> None:
        """
        Record a pattern match and increment occurrences.
        """
        if match.pattern_id not in self._patterns:
            raise ValueError(f"Pattern {match.pattern_id} not found.")
            
        if match.pattern_id not in self._matches:
            self._matches[match.pattern_id] = []
            
        self._matches[match.pattern_id].append(match)
        
        # Auto-increment occurrence and update last_seen
        pattern = self._patterns[match.pattern_id]
        pattern.occurrences += 1
        pattern.last_seen = datetime.utcnow().isoformat()
        if not pattern.first_seen:
            pattern.first_seen = pattern.last_seen

        # Promote automatically? No, only on explicit promote? Wait, requirement says "Promotion: >=5 occurrences → MEDIUM, >=20 → HIGH"
        # Is it auto-promoted or via `promote_pattern`? 
        # Requirement: `promote_pattern(pattern_id: str) -> PatternRecord - Increase confidence if enough occurrences (>=5: MEDIUM, >=20: HIGH)`
        
    def add_rule(self, rule: PatternRule) -> None:
        """
        Add detection rule for a pattern.
        """
        if rule.pattern_id not in self._patterns:
            raise ValueError(f"Pattern {rule.pattern_id} not found.")
            
        self._rules[rule.rule_id] = rule

    def search_patterns(self, pattern_type: Optional[PatternType] = None, is_antipattern: Optional[bool] = None, language: Optional[str] = None) -> List[PatternRecord]:
        """
        Search patterns.
        """
        results = []
        for p in self._patterns.values():
            if pattern_type and p.pattern_type != pattern_type:
                continue
            if is_antipattern is not None and p.is_antipattern != is_antipattern:
                continue
            if language and language not in p.languages:
                continue
            results.append(p)
        return results
        
    def get_matches(self, pattern_id: str) -> List[PatternMatch]:
        """
        Get all matches for a pattern.
        """
        if pattern_id not in self._patterns:
            raise ValueError(f"Pattern {pattern_id} not found.")
        return self._matches.get(pattern_id, [])
        
    def get_top_patterns(self, n: int = 10) -> List[PatternRecord]:
        """
        Top N patterns by occurrence count.
        """
        patterns = [p for p in self._patterns.values() if not p.is_antipattern]
        patterns.sort(key=lambda x: x.occurrences, reverse=True)
        return patterns[:n]
        
    def get_top_antipatterns(self, n: int = 10) -> List[PatternRecord]:
        """
        Top N antipatterns by occurrence count.
        """
        antipatterns = [p for p in self._patterns.values() if p.is_antipattern]
        antipatterns.sort(key=lambda x: x.occurrences, reverse=True)
        return antipatterns[:n]
        
    def promote_pattern(self, pattern_id: str) -> PatternRecord:
        """
        Increase confidence if enough occurrences (>=5: MEDIUM, >=20: HIGH).
        """
        if pattern_id not in self._patterns:
            raise ValueError(f"Pattern {pattern_id} not found.")
            
        pattern = self._patterns[pattern_id]
        if pattern.occurrences >= 20:
            pattern.confidence = PatternConfidence.HIGH
        elif pattern.occurrences >= 5:
            pattern.confidence = PatternConfidence.MEDIUM
            
        return pattern
        
    def deprecate_pattern(self, pattern_id: str) -> PatternRecord:
        """
        Mark as EXPERIMENTAL.
        """
        if pattern_id not in self._patterns:
            raise ValueError(f"Pattern {pattern_id} not found.")
            
        pattern = self._patterns[pattern_id]
        pattern.confidence = PatternConfidence.EXPERIMENTAL
        return pattern
        
    def get_pattern_trends(self) -> Dict:
        """
        Patterns by type, new vs growing vs declining.
        """
        by_type = {}
        for p in self._patterns.values():
            t = p.pattern_type.value
            by_type[t] = by_type.get(t, 0) + 1
            
        # Simplistic growing vs declining based on occurrences
        growing = [p.pattern_id for p in self._patterns.values() if p.occurrences >= 5]
        new = [p.pattern_id for p in self._patterns.values() if p.occurrences < 5 and p.occurrences > 0]
        
        return {
            "by_type": by_type,
            "growing": growing,
            "new": new,
            "declining": []
        }
        
    def get_pattern_report(self) -> Dict:
        """
        Summary report.
        """
        total = len(self._patterns)
        by_type = {}
        by_lang = {}
        for p in self._patterns.values():
            t = p.pattern_type.value
            by_type[t] = by_type.get(t, 0) + 1
            for lang in p.languages:
                by_lang[lang] = by_lang.get(lang, 0) + 1
                
        return {
            "total_patterns": total,
            "by_type": by_type,
            "top_patterns": [p.pattern_id for p in self.get_top_patterns(5)],
            "top_antipatterns": [p.pattern_id for p in self.get_top_antipatterns(5)],
            "coverage_by_language": by_lang
        }
