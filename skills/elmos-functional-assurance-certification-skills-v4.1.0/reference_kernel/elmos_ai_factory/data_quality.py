from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class QualityResult:
    completeness: float
    duplicate_rate: float
    freshness_seconds: float
    distribution_distance: float


def quality_gate(q: QualityResult, *, min_completeness=.99,max_duplicate_rate=.01,max_freshness_seconds=3600,max_distribution_distance=.1) -> tuple[str,tuple[str,...]]:
    reasons=[]
    if q.completeness<min_completeness: reasons.append('completeness')
    if q.duplicate_rate>max_duplicate_rate: reasons.append('duplicates')
    if q.freshness_seconds>max_freshness_seconds: reasons.append('freshness')
    if q.distribution_distance>max_distribution_distance: reasons.append('distribution-drift')
    return ('BLOCKED' if reasons else 'PASS',tuple(reasons))
