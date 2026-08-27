from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping

from .contracts import (
    AssuranceLevel,
    Criticality,
    GateDecision,
    ProofObligation,
    ProofResult,
    ProofStatus,
    Waiver,
)


_PROVED = frozenset(
    {
        ProofStatus.PROVED_CERTIFIED,
        ProofStatus.PROVED_INDUCTIVE,
        ProofStatus.PROVED_SOLVER_TRUSTED,
        ProofStatus.PROVED_FOR_SUPPORTED_FRAGMENT,
    }
)
_ASSURANCE_RANK = {value: index for index, value in enumerate(AssuranceLevel)}
_PROOF_MODES = {"CERTIFIED", "INDUCTIVE", "SMT", "BOUNDED", "RUNTIME"}
_SECURITY_PROPERTIES = {"AUTHORIZATION_DOMINANCE", "NONINTERFERENCE"}
_RELEASE_GATES = {
    "P05_DEPLOYMENT_COMPLETE",
    "E1_STATIC",
    "E2_MODEL",
    "E3_DIFFERENTIAL",
    "E4_FAILURE_INJECTION",
    "E5_CUSTOMER_GOLDEN_ROUTE",
}


class ResultValidationError(ValueError):
    pass


def validate_result(result: ProofResult) -> None:
    if result.mode not in _PROOF_MODES:
        raise ResultValidationError(f"unsupported proof mode: {result.mode}")
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
        ProofStatus.UNKNOWN_TIMEOUT,
        ProofStatus.UNKNOWN_RESOURCE_LIMIT,
        ProofStatus.UNSUPPORTED,
        ProofStatus.ASSUMPTION_REQUIRED,
        ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
    } and result.assurance_level not in {AssuranceLevel.NONE, AssuranceLevel.A0_TESTED}:
        raise ResultValidationError("non-passing status cannot claim proof assurance")
    if (
        result.status == ProofStatus.REFUTED_WITH_COUNTEREXAMPLE
        and not result.counterexample_id
    ):
        raise ResultValidationError("refuted result requires counterexampleId")
    if result.status in _PROVED and not result.assumption_hash:
        raise ResultValidationError("proved result requires assumption hash")
    if result.status in _PROVED and not result.tcb_hash:
        raise ResultValidationError("proved result requires TCB hash")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _valid_waiver(waiver: Waiver, now: datetime) -> bool:
    approval_ids = tuple(
        item.get("approver") if isinstance(item, dict) else item
        for item in waiver.approvals
    )
    try:
        expiry_valid = _parse_time(waiver.expires_at) > now
    except (TypeError, ValueError, OverflowError):
        expiry_valid = False
    return (
        waiver.status == "APPROVED"
        and len(set(approval_ids)) >= 2
        and len(waiver.compensating_controls) > 0
        and expiry_valid
    )


def evaluate_release_gate(
    obligations: Iterable[ProofObligation],
    results: Mapping[str, ProofResult],
    waivers: Mapping[str, Waiver] | None = None,
    *,
    required_gate: str = "E2_MODEL",
    deployment_complete: bool = False,
    external_evidence_complete: bool = False,
    now: datetime | None = None,
) -> GateDecision:
    now = now or datetime.now(timezone.utc)
    waivers = waivers or {}
    blocking: list[str] = []
    advisory: list[str] = []
    evaluated = 0
    if required_gate not in _RELEASE_GATES:
        blocking.append(f"unknown release gate: {required_gate}")
    if required_gate == "P05_DEPLOYMENT_COMPLETE" and not deployment_complete:
        blocking.append("P05 deployment evidence is not complete")
    if required_gate == "E5_CUSTOMER_GOLDEN_ROUTE" and not external_evidence_complete:
        blocking.append("E5 customer Golden Route evidence is not complete")

    for obligation in obligations:
        if not obligation.required:
            continue
        evaluated += 1
        result = results.get(obligation.id)
        waiver = waivers.get(obligation.id)
        if result is None:
            if (
                waiver
                and _valid_waiver(waiver, now)
                and obligation.criticality != Criticality.P0
            ):
                advisory.append(
                    f"{obligation.id}: missing result; approved waiver active"
                )
            else:
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
            if (
                _ASSURANCE_RANK[result.assurance_level]
                < _ASSURANCE_RANK[obligation.required_assurance]
            ):
                blocking.append(
                    f"{obligation.id}: assurance {result.assurance_level} is below {obligation.required_assurance}"
                )
            continue
        if result.status == ProofStatus.BOUNDED_NO_COUNTEREXAMPLE:
            allowed = (
                obligation.allow_bounded
                and _ASSURANCE_RANK[obligation.required_assurance]
                <= _ASSURANCE_RANK[AssuranceLevel.A1_BOUNDED]
            )
            if allowed:
                advisory.append(
                    f"{obligation.id}: bounded evidence accepted only under explicit A1 policy"
                )
            else:
                blocking.append(
                    f"{obligation.id}: bounded evidence cannot satisfy required assurance"
                )
            continue
        if waiver and _valid_waiver(waiver, now):
            if (
                obligation.criticality == Criticality.P0
                and obligation.property_kind in _SECURITY_PROPERTIES
            ):
                blocking.append(
                    f"{obligation.id}: critical security property cannot be waived"
                )
            else:
                advisory.append(
                    f"{obligation.id}: {result.status}; approved waiver active"
                )
            continue
        blocking.append(f"{obligation.id}: non-passing status {result.status}")

    decision = "DENY" if blocking else ("ADVISORY" if advisory else "ALLOW")
    return GateDecision(
        decision=decision,
        blocking_reasons=tuple(blocking),
        advisory_reasons=tuple(advisory),
        evaluated_count=evaluated,
        readiness="READY_FOR_EXTERNAL_GATE" if decision != "DENY" else "BLOCKED",
    )
