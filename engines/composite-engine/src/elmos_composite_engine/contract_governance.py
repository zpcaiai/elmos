"""Contract consumer governance and compatibility window evaluation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import CompatibilityWindow, ContractConsumerMatrix


class ContractGovernanceEngine:
    """Evaluates cross-service API, message, and RPC contracts against consumers."""

    def evaluate_contract_change(
        self,
        matrix: ContractConsumerMatrix,
        change_kind: str,
        target_version: str,
        unregistered_traffic_detected: bool = False
    ) -> Dict[str, Any]:
        """Evaluates breaking consequences of proposed API or schema alterations."""
        if unregistered_traffic_detected:
            return {
                "verdict": "UNKNOWN_CONSUMER_BLOCKER",
                "can_proceed": False,
                "reason": f"Contract {matrix.contractId} has active traffic from unknown/unregistered consumers.",
                "affected_consumers": ["UNKNOWN_EXTERNAL_CONSUMER"]
            }

        if change_kind == "PROTOBUF_FIELD_TAG_ALTERED":
            return {
                "verdict": "WIRE_BREAKING",
                "can_proceed": False,
                "reason": "Protobuf field number alteration breaks binary wire serialization compatibility.",
                "affected_consumers": [c.consumerNodeId for c in matrix.consumers]
            }

        incompatible_consumers = [
            c.consumerNodeId for c in matrix.consumers
            if c.supportedVersion != target_version
        ]

        if len(incompatible_consumers) > 1:
            return {
                "verdict": "MULTI_CONSUMER_BREAKING",
                "can_proceed": False,
                "reason": f"Contract modification breaks {len(incompatible_consumers)} distinct consumers across subsystems.",
                "affected_consumers": incompatible_consumers
            }
        elif len(incompatible_consumers) == 1:
            return {
                "verdict": "CONTRACT_BREAKING",
                "can_proceed": False,
                "reason": f"Contract modification breaks consumer [{incompatible_consumers[0]}].",
                "affected_consumers": incompatible_consumers
            }

        return {
            "verdict": "BACKWARD_COMPATIBLE",
            "can_proceed": True,
            "reason": "All active consumers support target version.",
            "affected_consumers": []
        }

    def check_compatibility_window(self, window: CompatibilityWindow, current_time_iso: str) -> Dict[str, Any]:
        """Checks if a dual-version compatibility window has expired while still receiving traffic."""
        is_expired = current_time_iso > window.expiresAt
        if is_expired and window.oldVersionUsage > 0:
            return {
                "status": "EXPIRED_WITH_USAGE",
                "action_required": "EXTEND_OR_MIGRATE_CALLERS",
                "usage_count": window.oldVersionUsage,
                "removal_blocked": True,
                "reason": f"Window {window.windowId} expired at {window.expiresAt}, but {window.oldVersionUsage} calls were observed on {window.oldVersion}."
            }
        elif is_expired:
            return {
                "status": "SAFE_FOR_DECOMMISSION",
                "action_required": "DELETE_LEGACY_CODE",
                "usage_count": 0,
                "removal_blocked": False,
                "reason": "Compatibility window expired with 0 active legacy calls."
            }
        return {
            "status": "ACTIVE",
            "action_required": "NONE",
            "usage_count": window.oldVersionUsage,
            "removal_blocked": True,
            "reason": f"Compatibility window remains active until {window.expiresAt}."
        }
