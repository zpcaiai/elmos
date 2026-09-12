"""Circuit breaker for self-healing cycles.

Async and timing repairs historically oscillated (add sleep → flake → add more
sleep).  This guard aborts on hash oscillation or a hard cycle ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class LoopDecision(StrEnum):
    CONTINUE = "CONTINUE"
    OSCILLATION_ABORT = "OSCILLATION_ABORT"
    MAX_CYCLES_ABORT = "MAX_CYCLES_ABORT"
    REPEAT_FAILURE_ABORT = "REPEAT_FAILURE_ABORT"


@dataclass
class RepairLoopGuard:
    max_cycles: int = 3
    patch_hashes: list[str] = field(default_factory=list)
    failure_signatures: list[str] = field(default_factory=list)

    def begin_cycle(self, failure_signature: str) -> LoopDecision:
        if len(self.patch_hashes) >= self.max_cycles:
            return LoopDecision.MAX_CYCLES_ABORT
        if self.failure_signatures and self.failure_signatures[-1] == failure_signature and self.patch_hashes:
            # Same failure after a patch was already applied.
            if self.failure_signatures.count(failure_signature) >= 2:
                return LoopDecision.REPEAT_FAILURE_ABORT
        self.failure_signatures.append(failure_signature)
        return LoopDecision.CONTINUE

    def record_patch(self, patch_hash: str) -> LoopDecision:
        if patch_hash in self.patch_hashes:
            return LoopDecision.OSCILLATION_ABORT
        if len(self.patch_hashes) >= self.max_cycles:
            return LoopDecision.MAX_CYCLES_ABORT
        self.patch_hashes.append(patch_hash)
        return LoopDecision.CONTINUE

    @property
    def cycles_used(self) -> int:
        return len(self.patch_hashes)
