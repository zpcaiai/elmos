from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Sequence

@dataclass(frozen=True)
class Candidate:
    target: str
    semantic_fit: float
    verification: float
    security: float
    durability: float
    operability: float
    cost: float
    reversibility: float
    blocked: bool = False

WEIGHTS = {
    "semantic_fit": 0.26,
    "verification": 0.18,
    "security": 0.16,
    "durability": 0.12,
    "operability": 0.11,
    "cost": 0.08,
    "reversibility": 0.09,
}

def rank(candidates: Sequence[Candidate]) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for c in candidates:
        if c.blocked:
            continue
        score = sum(getattr(c, key) * weight for key, weight in WEIGHTS.items())
        rows.append((c.target, round(score, 6)))
    return sorted(rows, key=lambda row: (-row[1], row[0]))
