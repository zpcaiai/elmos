"""Execution gateway bridge with action identity, generation fencing, and reconciliation."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import (
    ActionFenceError,
    ActionIntent,
    ContractError,
    Receipt,
    TrustedScope,
    canonical_digest,
)
from .scope import HostAuthority


class ExecutionGatewayBridge:
    """Action intent dispatcher and fail-closed reconciler."""

    def __init__(self, authority: HostAuthority) -> None:
        self.authority = authority
        # action_id -> (ActionIntent, status, receipt)
        self._actions: dict[str, tuple[ActionIntent, str, Receipt | None]] = {}
        # action_id -> generation_fenced_int
        self._action_generations: dict[str, str] = {}

    def compute_action_id(
        self,
        tenant: str,
        repository: str,
        logical_step: str,
        intent: ActionIntent,
        generation: str,
    ) -> str:
        payload = {
            "tenant": tenant,
            "repository": repository,
            "logical_step": logical_step,
            "intent": intent.to_dict(),
            "generation": generation,
        }
        return f"act-{canonical_digest(payload)[:24]}"

    def propose(
        self,
        scope: TrustedScope,
        repository: str,
        logical_step: str,
        intent: ActionIntent,
    ) -> str:
        grant = self.authority.get_grant(scope.tenant, repository)
        if grant is None or scope.principal not in grant.allowed_principals:
            raise ActionFenceError(f"Permission denied proposing action on {repository}")

        action_id = self.compute_action_id(
            scope.tenant,
            repository,
            logical_step,
            intent,
            grant.current_generation,
        )

        if action_id not in self._actions:
            self._actions[action_id] = (intent, "PROPOSED", None)
            self._action_generations[action_id] = grant.current_generation

        return action_id

    def dispatch(
        self,
        scope: TrustedScope,
        action_id: str,
        repository: str,
        execution_outcome: str = "SUCCEEDED",
    ) -> Receipt:
        if action_id not in self._actions:
            raise ContractError(f"Unknown action_id: {action_id}")

        intent, status, existing_receipt = self._actions[action_id]
        if existing_receipt is not None:
            # Idempotent replay of committed receipt
            return existing_receipt

        # Generation fence check
        grant = self.authority.get_grant(scope.tenant, repository)
        if grant is None:
            raise ActionFenceError("Repository not found")

        expected_gen = self._action_generations[action_id]
        if grant.current_generation != expected_gen:
            receipt = Receipt(
                action_id=action_id,
                state="FAILED",
                receipt_ref=f"fence-violation-gen-{grant.current_generation}-vs-{expected_gen}",
            )
            self._actions[action_id] = (intent, "FAILED", receipt)
            raise ActionFenceError(f"Generation fence violation: {grant.current_generation} != {expected_gen}")

        if execution_outcome not in {"SUCCEEDED", "FAILED", "UNKNOWN_RESULT"}:
            raise ContractError(f"Invalid execution outcome: {execution_outcome}")

        receipt = Receipt(
            action_id=action_id,
            state=execution_outcome,
            receipt_ref=f"rcpt-{action_id[-8:]}",
        )
        self._actions[action_id] = (intent, execution_outcome, receipt)
        return receipt

    def reconcile(self, action_id: str, resolved_state: str = "SUCCEEDED") -> Receipt:
        """Reconcile an UNKNOWN_RESULT action safely without blind re-dispatch."""
        if action_id not in self._actions:
            raise ContractError(f"Unknown action_id: {action_id}")

        intent, status, current_receipt = self._actions[action_id]
        if current_receipt and current_receipt.state != "UNKNOWN_RESULT":
            return current_receipt

        if resolved_state not in {"SUCCEEDED", "FAILED"}:
            raise ContractError(f"Cannot reconcile to non-terminal state: {resolved_state}")

        receipt = Receipt(
            action_id=action_id,
            state=resolved_state,
            receipt_ref=f"reconciled-{action_id[-8:]}",
        )
        self._actions[action_id] = (intent, resolved_state, receipt)
        return receipt
