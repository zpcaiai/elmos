from __future__ import annotations
from datetime import datetime, timezone
from typing import Iterable, Mapping
from .models import (
    AssuranceLevel, Criticality, GateDecision, ProofObligation,
    ProofResult, ProofStatus, Waiver,
)

_PROVED = {
    ProofStatus.PROVED_CERTIFIED,
    ProofStatus.PROVED_INDUCTIVE,
    ProofStatus.PROVED_SOLVER_TRUSTED,
    ProofStatus.PROVED_FOR_SUPPORTED_FRAGMENT,
}
_ASSURANCE_RANK = {
    AssuranceLevel.NONE: 0,
    AssuranceLevel.A0_TESTED: 1,
    AssuranceLevel.A1_BOUNDED: 2,
    AssuranceLevel.A2_SOLVER_PROVED: 3,
    AssuranceLevel.A3_CERTIFIED: 4,
    AssuranceLevel.A4_COMPOSED: 5,
    AssuranceLevel.TRUSTED: 6,
}

class ResultValidationError(ValueError):
    pass

def validate_result(result: ProofResult) -> None:
    if result.status == ProofStatus.BOUNDED_NO_COUNTEREXAMPLE:
        if result.mode != "BOUNDED":
            raise ResultValidationError("bounded status requires BOUNDED mode")
        if result.assurance_level != AssuranceLevel.A1_BOUNDED:
            raise ResultValidationError("bounded status requires A1_BOUNDED")
        if not result.bound:
            raise ResultValidationError("bounded status requires an explicit bound")
    if result.status in _PROVED and result.mode == "BOUNDED":
        raise ResultValidationError("a bounded run cannot emit a proved status")
    if result.status in {
        ProofStatus.UNKNOWN_TIMEOUT, ProofStatus.UNKNOWN_RESOURCE_LIMIT,
        ProofStatus.UNSUPPORTED, ProofStatus.ASSUMPTION_REQUIRED,
        ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
    } and result.assurance_level not in {AssuranceLevel.NONE, AssuranceLevel.A0_TESTED}:
        raise ResultValidationError("non-passing status cannot claim proof assurance")

def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

def _valid_waiver(waiver: Waiver, now: datetime) -> bool:
    return (
        waiver.status == "APPROVED"
        and len(set(waiver.approvals)) >= 2
        and len(waiver.compensating_controls) > 0
        and _parse_iso(waiver.expires_at) > now
    )

def evaluate_release_gate(
    obligations: Iterable[ProofObligation],
    results: Mapping[str, ProofResult],
    waivers: Mapping[str, Waiver] | None = None,
    *,
    required_gate: str = "E2_MODEL",
    deployment_complete: bool = True,
    now: datetime | None = None,
) -> GateDecision:
    now = now or datetime.now(timezone.utc)
    waivers = waivers or {}
    blocking: list[str] = []
    advisory: list[str] = []
    count = 0

    if required_gate == "P05_DEPLOYMENT_COMPLETE" and not deployment_complete:
        blocking.append("P05 deployment gate is not complete")

    for obligation in obligations:
        if not obligation.required:
            continue
        count += 1
        result = results.get(obligation.id)
        waiver = waivers.get(obligation.id)

        if result is None:
            if waiver and _valid_waiver(waiver, now):
                advisory.append(f"{obligation.id}: no result; approved waiver active")
                continue
            blocking.append(f"{obligation.id}: missing proof result")
            continue

        try:
            validate_result(result)
        except ResultValidationError as exc:
            blocking.append(f"{obligation.id}: invalid result: {exc}")
            continue

        if result.stale:
            blocking.append(f"{obligation.id}: proof evidence is stale")
            continue

        if result.status in _PROVED:
            if _ASSURANCE_RANK[result.assurance_level] < _ASSURANCE_RANK[obligation.required_assurance]:
                blocking.append(
                    f"{obligation.id}: assurance {result.assurance_level} is below "
                    f"{obligation.required_assurance}"
                )
            continue

        if result.status == ProofStatus.BOUNDED_NO_COUNTEREXAMPLE:
            bounded_allowed = (
                obligation.allow_bounded
                and _ASSURANCE_RANK[obligation.required_assurance] <= _ASSURANCE_RANK[AssuranceLevel.A1_BOUNDED]
            )
            if bounded_allowed:
                advisory.append(f"{obligation.id}: bounded evidence accepted by explicit policy")
            else:
                blocking.append(f"{obligation.id}: bounded evidence cannot satisfy required assurance")
            continue

        if waiver and _valid_waiver(waiver, now):
            forbidden = (
                obligation.criticality == Criticality.P0
                and obligation.property_kind in {"AUTHORIZATION_DOMINANCE", "NONINTERFERENCE"}
                and waiver.risk == "CRITICAL"
            )
            if forbidden:
                blocking.append(f"{obligation.id}: critical security property cannot be waived")
            else:
                advisory.append(f"{obligation.id}: {result.status}; approved waiver active")
            continue

        blocking.append(f"{obligation.id}: non-passing status {result.status}")

    return GateDecision(
        decision="DENY" if blocking else ("ADVISORY" if advisory else "ALLOW"),
        blocking_reasons=tuple(blocking),
        advisory_reasons=tuple(advisory),
        evaluated_count=count,
    )
