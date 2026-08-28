from __future__ import annotations

import copy
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from elmos_spring_golden_route.errors import (
    IdempotencyConflict,
    StepBudgetAuthorizationDenied,
    StepBudgetConflict,
    StepBudgetExhausted,
    StepBudgetNotFound,
    StepBudgetSchemaMigrationRequired,
    StepBudgetValidationError,
    StepSettlementRequired,
)
from elmos_spring_golden_route.step_budget import (
    BLOCKED_RECONCILIATION,
    BudgetScope,
    PERMISSIONS,
    REQUEST_SCHEMA_VERSION,
    StepBudgetStore,
    authorization_scope_sha256,
    validate_step_budget_request,
)


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 28, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class StepBudgetStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "budgets.sqlite3"
        self.clock = MutableClock()
        self.verifier_calls: list[dict[str, object]] = []

        def verifier(authorization: dict[str, object]) -> bool:
            self.verifier_calls.append(dict(authorization))
            return str(authorization["token"]).startswith("trusted/")

        self.store = StepBudgetStore(
            self.database,
            authorization_verifier=verifier,
            clock=self.clock,
        )
        self.scope = BudgetScope("tenant-a", "project-a", "run-a", "task-a", "agent-a")

    @staticmethod
    def policy(**changes: object) -> dict[str, object]:
        value: dict[str, object] = {
            "base_max_steps": 2,
            "base_max_turns": 2,
            "hard_max_steps": 2,
            "hard_max_turns": 2,
            "complexity": "MEDIUM",
            "expected_step_cost_microusd": 10,
            "max_cost_microusd": 100,
            "max_tokens": 1000,
            "warning_remaining_steps": 1,
            "warning_remaining_turns": 1,
            "reservation_timeout_seconds": 60,
        }
        value.update(changes)
        return value

    def request(
        self,
        operation: str,
        input_value: dict[str, object],
        *,
        scope: BudgetScope | None = None,
        idempotency_key: str | None = None,
        actor_id: str = "actor-a",
        decision: str = "ALLOW",
        token: str = "trusted/local-test-secret",
        permission: str | None = None,
        scope_digest: str | None = None,
    ) -> dict[str, object]:
        selected_scope = scope or self.scope
        selected_permission = permission or PERMISSIONS[operation]
        issued_at = (self.clock() - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        expires_at = (self.clock() + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        return {
            "schema_version": REQUEST_SCHEMA_VERSION,
            "operation": operation,
            "skill_name": "agent-step-budget",
            **selected_scope.as_dict(),
            "actor_id": actor_id,
            "idempotency_key": idempotency_key or f"idem-{selected_scope.run_id}-{operation}",
            "authorization": {
                "authorization_id": f"auth-{selected_scope.run_id}-{operation}",
                "decision": decision,
                "permission": selected_permission,
                "subject_actor_id": actor_id,
                "scope_sha256": scope_digest or authorization_scope_sha256(selected_scope, selected_permission),
                "issued_at": issued_at,
                "expires_at": expires_at,
                "token": token,
            },
            "input": input_value,
        }

    def admit(
        self,
        *,
        scope: BudgetScope | None = None,
        policy: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        return self.store.execute(
            self.request(
                "admit",
                {"policy": policy or self.policy()},
                scope=scope,
                idempotency_key=idempotency_key,
            )
        )

    def reserve(
        self,
        *,
        version: int,
        step_id: str,
        turn_id: str = "turn-a",
        scope: BudgetScope | None = None,
        idempotency_key: str | None = None,
        remaining_work: list[str] | None = None,
        estimated_tokens: int = 100,
        estimated_cost: int = 10,
        side_effect: bool = True,
    ) -> dict[str, object]:
        return self.store.execute(
            self.request(
                "reserve",
                {
                    "expected_version": version,
                    "step_id": step_id,
                    "turn_id": turn_id,
                    "estimated_tokens": estimated_tokens,
                    "estimated_cost_microusd": estimated_cost,
                    "side_effect": side_effect,
                    "remaining_work": remaining_work if remaining_work is not None else ["Settle this step"],
                    "blockers": [],
                },
                scope=scope,
                idempotency_key=idempotency_key or f"idem-{(scope or self.scope).run_id}-reserve-{step_id}",
            )
        )

    def settle(
        self,
        *,
        version: int,
        step_id: str,
        outcome: str = "SUCCEEDED",
        failure_type: str | None = None,
        scope: BudgetScope | None = None,
        idempotency_key: str | None = None,
        actual_tokens: int = 90,
        actual_cost: int = 9,
    ) -> dict[str, object]:
        return self.store.execute(
            self.request(
                "settle",
                {
                    "expected_version": version,
                    "step_id": step_id,
                    "outcome": outcome,
                    "actual_tokens": actual_tokens,
                    "actual_cost_microusd": actual_cost,
                    "failure_type": failure_type,
                    "remaining_work": ["Continue with the bounded plan"],
                    "blockers": [],
                },
                scope=scope,
                idempotency_key=idempotency_key or f"idem-{(scope or self.scope).run_id}-settle-{step_id}",
            )
        )

    def status(self, *, scope: BudgetScope | None = None) -> dict[str, object]:
        selected = scope or self.scope
        return self.store.execute(
            self.request(
                "status",
                {},
                scope=selected,
                idempotency_key=f"idem-{selected.run_id}-status-{len(self.verifier_calls)}",
            )
        )

    def test_dynamic_policy_validation_and_exact_public_schema(self) -> None:
        request = self.request(
            "admit",
            {
                "policy": self.policy(
                    base_max_steps=2,
                    hard_max_steps=4,
                    base_max_turns=2,
                    hard_max_turns=4,
                    complexity="HIGH",
                    expected_step_cost_microusd=20,
                    max_cost_microusd=50,
                )
            },
        )
        validated = validate_step_budget_request(request)
        self.assertEqual(validated.input["policy"]["complexity_multiplier_bps"], 15_000)
        self.assertEqual(validated.input["policy"]["effective_max_steps"], 2)
        self.assertEqual(validated.input["policy"]["effective_max_turns"], 3)
        admitted = self.store.execute(request)
        self.assertEqual(admitted["remaining"]["steps"], 2)
        self.assertEqual(admitted["remaining"]["turns"], 3)
        self.assertEqual(admitted["domain_runtime_evidence_status"], "LOCAL_EXECUTED_SELF_ATTESTED")
        self.assertEqual(admitted["certification"], "NOT_CERTIFIED")
        self.assertFalse(admitted["side_effects_performed"])

        bad = copy.deepcopy(request)
        bad["unexpected"] = True
        with self.assertRaises(StepBudgetValidationError):
            validate_step_budget_request(bad)
        bad_policy = copy.deepcopy(request)
        bad_policy["input"]["policy"]["complexity"] = "UNKNOWN"
        with self.assertRaises(StepBudgetValidationError):
            validate_step_budget_request(bad_policy)
        floating = copy.deepcopy(request)
        floating["input"]["policy"]["max_tokens"] = 100.0
        with self.assertRaises(StepBudgetValidationError):
            validate_step_budget_request(floating)

    def test_full_lifecycle_idempotency_recovery_and_explicit_exhaustion(self) -> None:
        admission_request = self.request("admit", {"policy": self.policy()})
        admitted = self.store.execute(admission_request)
        self.assertEqual(admitted["decision"], "CONTINUE")
        replay = self.store.execute(copy.deepcopy(admission_request))
        self.assertTrue(replay["replayed"])
        changed = copy.deepcopy(admission_request)
        changed["input"]["policy"]["max_tokens"] = 999
        with self.assertRaises(IdempotencyConflict):
            self.store.execute(changed)

        first_reservation_request = self.request(
            "reserve",
            {
                "expected_version": 1,
                "step_id": "step-1",
                "turn_id": "turn-1",
                "estimated_tokens": 100,
                "estimated_cost_microusd": 10,
                "side_effect": True,
                "remaining_work": ["Run the final bounded step"],
                "blockers": [],
            },
            idempotency_key="idem-reserve-1",
        )
        reserved = self.store.execute(first_reservation_request)
        self.assertEqual(reserved["decision"], "WAIT_FOR_SETTLEMENT")
        self.assertTrue(reserved["permit"]["side_effect_registered"])
        self.assertEqual(reserved["remaining"]["steps"], 1)
        replayed_reservation = self.store.execute(copy.deepcopy(first_reservation_request))
        self.assertTrue(replayed_reservation["replayed"])
        with self.assertRaises(StepSettlementRequired):
            self.reserve(version=2, step_id="step-2", idempotency_key="blocked-reserve")

        reopened = StepBudgetStore(
            self.database,
            authorization_verifier=lambda authorization: str(authorization["token"]).startswith("trusted/"),
            clock=self.clock,
            create=False,
        )
        reopened_status = reopened.execute(self.request("status", {}, idempotency_key="reopened-status"))
        self.assertEqual(reopened_status["pending_step"]["step_id"], "step-1")

        settled = self.settle(version=2, step_id="step-1")
        self.assertEqual(settled["decision"], "CONTINUE")
        self.assertEqual(settled["metrics"]["success_count"], 1)
        with self.assertRaises(StepBudgetValidationError):
            self.reserve(version=3, step_id="step-2", remaining_work=[], idempotency_key="empty-warning")
        second = self.reserve(version=3, step_id="step-2", idempotency_key="reserve-2")
        self.assertTrue(second["permit"]["stop_after_step"])
        exhausted = self.settle(version=4, step_id="step-2", idempotency_key="settle-2")
        self.assertEqual(exhausted["decision"], "STOP")
        self.assertEqual(exhausted["stop_reason"], "STEP_LIMIT_REACHED")
        self.assertEqual(exhausted["metrics"]["settled_steps"], 2)
        with self.assertRaises(StepBudgetExhausted):
            self.reserve(version=5, step_id="step-3")

        self.assertEqual(os.stat(self.database).st_mode & 0o777, 0o600)
        self.assertNotIn(b"local-test-secret", self.database.read_bytes())

    def test_authorization_is_checked_before_state_access_and_scopes_are_isolated(self) -> None:
        denied = self.request("admit", {"policy": self.policy()}, decision="DENY")
        with self.assertRaises(StepBudgetAuthorizationDenied):
            self.store.execute(denied)
        wrong_permission = self.request(
            "admit",
            {"policy": self.policy()},
            permission="agent-step-budget.status",
        )
        with self.assertRaises(StepBudgetAuthorizationDenied):
            self.store.execute(wrong_permission)
        untrusted = self.request(
            "admit",
            {"policy": self.policy()},
            token="caller-self-asserted",
        )
        with self.assertRaises(StepBudgetAuthorizationDenied):
            self.store.execute(untrusted)
        without_verifier = StepBudgetStore(
            Path(self.temporary.name) / "no-verifier.sqlite3",
            authorization_verifier=None,
            clock=self.clock,
        )
        with self.assertRaises(StepBudgetAuthorizationDenied):
            without_verifier.execute(self.request("admit", {"policy": self.policy()}))

        self.admit()
        other_scope = BudgetScope("tenant-b", "project-a", "run-a", "task-a", "agent-a")
        with self.assertRaises(StepBudgetNotFound):
            self.status(scope=other_scope)
        self.assertGreaterEqual(len(self.verifier_calls), 4)

    def test_timeout_unknown_outcome_reconciliation_and_safe_cancel(self) -> None:
        self.admit()
        self.reserve(version=1, step_id="step-timeout", idempotency_key="reserve-timeout")
        self.clock.advance(seconds=61)
        timed_out = self.status()
        self.assertEqual(timed_out["decision"], "WAIT_FOR_SETTLEMENT")
        self.assertEqual(timed_out["stop_reason"], "RESERVATION_TIMEOUT_REQUIRES_RECONCILIATION")
        with self.assertRaises(StepSettlementRequired):
            self.store.execute(
                self.request(
                    "cancel",
                    {"expected_version": 2, "reason": "operator requested cancellation"},
                    idempotency_key="cancel-pending",
                )
            )
        unknown = self.settle(
            version=2,
            step_id="step-timeout",
            outcome="UNKNOWN",
            failure_type="EXTERNAL_OUTCOME_UNKNOWN",
            idempotency_key="settle-unknown",
        )
        self.assertEqual(unknown["state"], BLOCKED_RECONCILIATION)
        self.assertEqual(unknown["decision"], "BLOCKED")
        self.assertEqual(unknown["stop_reason"], "UNRECONCILED_EXTERNAL_OUTCOME")
        with self.assertRaises(StepBudgetExhausted):
            self.reserve(version=3, step_id="unsafe-retry")

        cancel_scope = BudgetScope("tenant-a", "project-a", "run-cancel", "task-a", "agent-a")
        self.admit(scope=cancel_scope, idempotency_key="admit-cancel")
        cancelled = self.store.execute(
            self.request(
                "cancel",
                {"expected_version": 1, "reason": "human stop"},
                scope=cancel_scope,
                idempotency_key="cancel-clean",
            )
        )
        self.assertEqual(cancelled["decision"], "STOP")
        self.assertEqual(cancelled["stop_reason"], "CANCELLED")

    def test_append_only_audit_digest_and_schema_drift_fail_closed(self) -> None:
        self.admit()
        self.reserve(version=1, step_id="step-audit", idempotency_key="reserve-audit")
        self.settle(version=2, step_id="step-audit", idempotency_key="settle-audit")
        audit = self.store.execute(
            self.request(
                "audit",
                {"after_sequence": 0, "limit": 2},
                idempotency_key="audit-page",
            )
        )
        self.assertEqual(len(audit["events"]), 2)
        self.assertTrue(audit["has_more"])
        self.assertIsNone(audit["events"][0]["previous_sha256"])
        self.assertEqual(
            audit["events"][1]["previous_sha256"],
            audit["events"][0]["event_sha256"],
        )
        with closing(sqlite3.connect(self.database)) as connection, connection:
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("DELETE FROM budget_events")
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("UPDATE budget_operations SET operation = 'forged'")

        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("DROP TRIGGER budget_events_no_update")
            connection.execute("UPDATE budget_events SET actor_id = 'forged' WHERE sequence = 1")
        with self.assertRaises(StepBudgetConflict):
            self.status()
        with self.assertRaises(StepBudgetSchemaMigrationRequired):
            StepBudgetStore(
                self.database,
                authorization_verifier=lambda _: True,
                clock=self.clock,
                create=False,
            )


if __name__ == "__main__":
    unittest.main()
