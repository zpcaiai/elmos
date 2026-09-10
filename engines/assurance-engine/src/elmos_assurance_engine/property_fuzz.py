"""Implementation of B03: Property-based testing and metamorphic relation verifier."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .contracts import GateDecision


class PropertyVerifier:
    """Verifies algebraic and metamorphic invariants across generated test domains."""

    @classmethod
    def verify_idempotency(
        cls,
        operation: Callable[[Any], Any],
        samples: Sequence[Any],
    ) -> tuple[GateDecision, list[str]]:
        reasons: list[str] = []
        for sample in samples:
            first_run = operation(sample)
            second_run = operation(sample)
            if first_run != second_run:
                reasons.append(f"IDEMPOTENCY_VIOLATION: f(x) != f(f(x)) for sample={sample!r}")
                return GateDecision.FAIL, reasons
        return GateDecision.PASS, ["IDEMPOTENCY_VERIFIED"]

    @classmethod
    def verify_conservation(
        cls,
        transfer_op: Callable[[dict[str, int], str, str, int], dict[str, int]],
        accounts: dict[str, int],
        sender: str,
        receiver: str,
        amount: int,
    ) -> tuple[GateDecision, list[str]]:
        initial_total = sum(accounts.values())
        updated = transfer_op(accounts, sender, receiver, amount)
        new_total = sum(updated.values())
        if initial_total != new_total:
            return GateDecision.FAIL, [
                f"MONEY_CONSERVATION_VIOLATION: initial={initial_total} != final={new_total}"
            ]
        return GateDecision.PASS, ["CONSERVATION_PROPERTY_VERIFIED"]
