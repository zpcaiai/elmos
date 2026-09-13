from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    recommendation: str
    blockers: tuple[str, ...]

class GateEvaluator:
    LEVELS = {"E0": 0, "E1": 1, "E2": 2, "E3": 3}

    def evaluate(self, items: Iterable[dict], requested_level: str, producer_independent: bool) -> GateDecision:
        if requested_level not in self.LEVELS:
            return GateDecision(False, "reject", ("requested level is outside E0-E3",))
        blockers = []
        for item in items:
            status = str(item.get("status", "unknown")).lower()
            material = bool(item.get("material", True))
            if material and status in {"unknown", "unsupported", "stale", "failed", "fail"}:
                blockers.append(str(item.get("id", status)))
            if item.get("approval_required") and not item.get("approved"):
                blockers.append(str(item.get("id", "missing-approval")))
            if item.get("unresolved_effect"):
                blockers.append(str(item.get("id", "unresolved-effect")))
        if not producer_independent:
            blockers.append("producer-self-approval")
        blockers = sorted(set(blockers))
        return GateDecision(not blockers, requested_level if not blockers else "rework", tuple(blockers))
