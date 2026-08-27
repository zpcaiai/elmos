"""Verification result composition; completion is evidence-gated."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationResult:
    gate: str
    status: str
    evidence_digest: str | None = None
    verifier_id: str | None = None


def evaluate(results: Iterable[VerificationResult], required_gates: set[str]) -> dict[str, object]:
    values = list(results)
    by_gate = {item.gate: item for item in values}
    missing = sorted(required_gates - set(by_gate))
    failed = sorted(item.gate for item in values if item.status not in {"PASS", "VERIFIED"})
    unsigned = sorted(item.gate for item in values if item.status in {"PASS", "VERIFIED"} and (not item.evidence_digest or not item.verifier_id))
    blockers = sorted(set(missing + failed + unsigned))
    return {"passed": not blockers and required_gates.issubset(by_gate), "blockers": blockers, "required_gates": sorted(required_gates)}
