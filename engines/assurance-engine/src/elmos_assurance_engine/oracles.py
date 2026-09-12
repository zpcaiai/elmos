"""Implementation of B01: Independent requirement parsing and normative Oracles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .contracts import GateDecision


class OracleKind(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    INVARIANT = "INVARIANT"
    DIFFERENTIAL = "DIFFERENTIAL"
    METAMORPHIC = "METAMORPHIC"


@dataclass(frozen=True)
class RequirementObligation:
    obligation_id: str
    requirement_id: str
    description: str
    oracle_kind: OracleKind
    expected_predicate: str
    severity: str = "critical"


class RequirementOracle:
    """Independent oracle that evaluates candidates against normative specs.

    CRITICAL INVARIANT: The oracle must NEVER read the candidate implementation
    to determine the expected result.
    """

    def __init__(self, spec_contracts: Mapping[str, Any]) -> None:
        self.spec_contracts = dict(spec_contracts)

    def evaluate_response(
        self,
        obligation_id: str,
        actual_response: Mapping[str, Any],
        actual_state: Mapping[str, Any] | None = None,
    ) -> tuple[GateDecision, str]:
        if obligation_id not in self.spec_contracts:
            return GateDecision.INCONCLUSIVE, f"UNKNOWN_OBLIGATION: {obligation_id}"

        spec = self.spec_contracts[obligation_id]
        expected_status = spec.get("expected_status")
        expected_fields = spec.get("required_fields", [])

        # Check status code
        if expected_status is not None and actual_response.get("status_code") != expected_status:
            return GateDecision.FAIL, f"STATUS_CODE_MISMATCH: expected {expected_status}, got {actual_response.get('status_code')}"

        # Check required fields
        body = actual_response.get("body", {})
        for field_name in expected_fields:
            if field_name not in body:
                return GateDecision.FAIL, f"REQUIRED_FIELD_MISSING: {field_name}"

        # Check business invariants if present
        invariant_rule = spec.get("invariant")
        if invariant_rule == "non_negative_balance":
            balance = body.get("balance", actual_state.get("balance", 0) if actual_state else 0)
            if balance < 0:
                return GateDecision.FAIL, f"INVARIANT_VIOLATION: balance cannot be negative ({balance})"

        if invariant_rule == "business_logic_executed":
            # If the requirement dictates a state change, verify it actually occurred
            if not actual_state or not actual_state.get("order_persisted"):
                return GateDecision.FAIL, "BUSINESS_LOGIC_NOT_EXECUTED: order was not persisted despite 200 response"

        return GateDecision.PASS, "REQUIREMENT_OBLIGATION_SATISFIED"
