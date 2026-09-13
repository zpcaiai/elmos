"""Implementation of B02: Bounded repair loop with counterexample localization."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import GateDecision


@dataclass(frozen=True)
class RepairAttempt:
    attempt_index: int
    counterexample: str
    proposed_patch_digest: str
    verdict_after_patch: GateDecision


@dataclass
class BoundedRepairLoop:
    max_attempts: int = 3
    attempts: list[RepairAttempt] = field(default_factory=list)

    def record_attempt(
        self,
        counterexample: str,
        proposed_patch_digest: str,
        verdict: GateDecision,
    ) -> tuple[bool, str]:
        """Records repair attempt. Returns (can_continue, message)."""
        idx = len(self.attempts) + 1
        attempt = RepairAttempt(
            attempt_index=idx,
            counterexample=counterexample,
            proposed_patch_digest=proposed_patch_digest,
            verdict_after_patch=verdict,
        )
        self.attempts.append(attempt)

        if verdict == GateDecision.PASS:
            return False, f"REPAIR_SUCCEEDED_AT_ATTEMPT_{idx}"

        if idx >= self.max_attempts:
            return False, f"REPAIR_ATTEMPTS_EXHAUSTED: {idx}/{self.max_attempts}"

        return True, f"REPAIR_ATTEMPT_{idx}_FAILED_PROCEED_TO_NEXT"
