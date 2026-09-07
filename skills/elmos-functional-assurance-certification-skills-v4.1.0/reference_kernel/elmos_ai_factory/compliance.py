from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class Control:
    control_id: str
    required: bool
    implementation: str | None
    evidence: tuple[str,...]
    legal_decision: bool=False


def profile_decision(controls: Iterable[Control], *, legal_review_approved: bool) -> tuple[str,tuple[str,...]]:
    unresolved=[]
    for c in controls:
        if c.required and (not c.implementation or not c.evidence):unresolved.append(c.control_id)
        if c.legal_decision and not legal_review_approved:unresolved.append(f"legal:{c.control_id}")
    return ('BLOCKED',tuple(sorted(set(unresolved)))) if unresolved else ('READY_FOR_INDEPENDENT_GATE',())
