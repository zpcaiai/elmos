"""Durable, approval-bound cloud provider control plane.

Provider-native DTOs terminate at ``ProviderAdapter``. Unknown external results
are persisted and require explicit reconciliation; they are never retried as if
the first request had failed.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .canonical import canonical_bytes, digest, require_nonempty, require_uuid, utc_now
from .models import ConflictError, NotFoundError, PolicyDeniedError
from .production import (
    ApprovalGrant,
    ExactTarget,
    OperationState,
    assert_monotonic_state,
)


class ProviderOutcomeUnknown(RuntimeError):
    """The provider may have accepted the effect, so automatic retry is unsafe."""


@dataclass(frozen=True)
class NativeProviderResult:
    state: OperationState
    native_id: str | None
    native_payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.state not in {
            OperationState.SUBMITTED,
            OperationState.SUCCEEDED,
            OperationState.FAILED,
            OperationState.UNKNOWN,
        }:
            raise ValueError("provider adapter returned an invalid effect state")
        if (
            self.state in {OperationState.SUBMITTED, OperationState.SUCCEEDED}
            and not self.native_id
        ):
            raise ValueError("submitted provider operations require a native id")
        canonical_bytes(dict(self.native_payload))


class ProviderAdapter(Protocol):
    target: ExactTarget

    def plan(self, action: str, request: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def apply(
        self, operation_id: str, action: str, request: Mapping[str, Any]
    ) -> NativeProviderResult: ...
    def observe(self, native_id: str, action: str) -> NativeProviderResult: ...
    def recover(
        self,
        operation_id: str,
        action: str,
        request: Mapping[str, Any],
        plan: Mapping[str, Any],
    ) -> NativeProviderResult: ...
    def rollback(
        self, native_id: str, action: str, request: Mapping[str, Any]
    ) -> NativeProviderResult: ...
    def destroy(
        self, native_id: str, action: str, request: Mapping[str, Any]
    ) -> NativeProviderResult: ...


JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_operation (
  operation_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL,
  target_json TEXT NOT NULL,
  target_digest TEXT NOT NULL,
  request_json TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  plan_json TEXT NOT NULL,
  plan_digest TEXT NOT NULL,
  approval_json TEXT,
  state TEXT NOT NULL,
  provider_native_id TEXT,
  native_evidence_json TEXT,
  native_evidence_digest TEXT,
  normalized_evidence_digest TEXT,
  reconciliation_required INTEGER NOT NULL DEFAULT 0,
  pending_terminal_state TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, action, request_digest, target_digest)
);
CREATE TABLE IF NOT EXISTS provider_operation_event (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  operation_id TEXT NOT NULL REFERENCES provider_operation(operation_id),
  from_state TEXT,
  to_state TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  evidence_digest TEXT,
  created_at TEXT NOT NULL
);
"""


class ProviderOperationJournal:
    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:" and not Path(path).is_absolute():
            raise ValueError("provider journal path must be absolute")
        self._connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(JOURNAL_SCHEMA)
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def prepare(
        self,
        *,
        operation_id: str,
        tenant_id: str,
        actor_id: str,
        action: str,
        target: ExactTarget,
        request: Mapping[str, Any],
        plan: Mapping[str, Any],
    ) -> dict[str, Any]:
        operation_id = require_uuid(operation_id, "operation_id")
        tenant_id = require_uuid(tenant_id, "tenant_id")
        actor_id = require_nonempty(actor_id, "actor_id", 256)
        action = require_nonempty(action, "action", 128)
        request_value = dict(request)
        plan_value = dict(plan)
        request_json = canonical_bytes(request_value).decode()
        plan_json = canonical_bytes(plan_value).decode()
        target_json = canonical_bytes(target.to_dict()).decode()
        request_digest = digest(request_value)
        target_digest = digest(target.to_dict())
        plan_digest = digest(plan_value)
        now = utc_now()
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT * FROM provider_operation WHERE tenant_id=? AND action=? AND request_digest=? AND target_digest=?",
                (tenant_id, action, request_digest, target_digest),
            ).fetchone()
            if existing:
                return self._row(existing) | {"replayed": True}
            self._connection.execute(
                "INSERT INTO provider_operation(operation_id,tenant_id,actor_id,action,target_json,target_digest,request_json,request_digest,plan_json,plan_digest,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    operation_id,
                    tenant_id,
                    actor_id,
                    action,
                    target_json,
                    target_digest,
                    request_json,
                    request_digest,
                    plan_json,
                    plan_digest,
                    OperationState.PREPARED.value,
                    now,
                    now,
                ),
            )
            self._event(
                operation_id, None, OperationState.PREPARED, actor_id, plan_digest
            )
            row = self._connection.execute(
                "SELECT * FROM provider_operation WHERE operation_id=?", (operation_id,)
            ).fetchone()
            return self._row(row) | {"replayed": False}

    def approve(
        self, tenant_id: str, operation_id: str, grant: ApprovalGrant, *, actor_id: str
    ) -> dict[str, Any]:
        with self._lock, self._connection:
            row = self._locked_row(tenant_id, operation_id)
            current = OperationState(row["state"])
            assert_monotonic_state(current, OperationState.APPROVED)
            target = ExactTarget(**json.loads(row["target_json"]))
            grant.assert_valid(
                operation_id=operation_id,
                request_digest=row["request_digest"],
                target=target,
                action=row["action"],
                actor_id=row["actor_id"],
            )
            if actor_id != grant.approved_by:
                raise PolicyDeniedError(
                    "approval actor does not match the signed grant"
                )
            self._connection.execute(
                "UPDATE provider_operation SET approval_json=?,state=?,updated_at=? WHERE operation_id=?",
                (
                    canonical_bytes(grant.__dict__).decode(),
                    OperationState.APPROVED.value,
                    utc_now(),
                    operation_id,
                ),
            )
            self._event(
                operation_id,
                current,
                OperationState.APPROVED,
                actor_id,
                digest(grant.__dict__),
            )
            return self.get(tenant_id, operation_id)

    def record_result(
        self,
        tenant_id: str,
        operation_id: str,
        result: NativeProviderResult,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        with self._lock, self._connection:
            row = self._locked_row(tenant_id, operation_id)
            current = OperationState(row["state"])
            target_state = result.state
            if (
                current == OperationState.APPROVED
                and target_state != OperationState.SUBMITTED
            ):
                assert_monotonic_state(current, OperationState.SUBMITTED)
                self._event(
                    operation_id, current, OperationState.SUBMITTED, actor_id, None
                )
                current = OperationState.SUBMITTED
            assert_monotonic_state(current, target_state)
            native_payload = dict(result.native_payload)
            native_digest = digest(native_payload)
            normalized = {
                "operation_id": operation_id,
                "state": target_state.value,
                "native_id": result.native_id,
                "action": row["action"],
                "target_digest": row["target_digest"],
                "request_digest": row["request_digest"],
            }
            reconciliation = target_state == OperationState.UNKNOWN
            self._connection.execute(
                "UPDATE provider_operation SET state=?,provider_native_id=COALESCE(?,provider_native_id),native_evidence_json=?,native_evidence_digest=?,normalized_evidence_digest=?,reconciliation_required=?,updated_at=? WHERE operation_id=?",
                (
                    target_state.value,
                    result.native_id,
                    canonical_bytes(native_payload).decode(),
                    native_digest,
                    digest(normalized),
                    int(reconciliation),
                    utc_now(),
                    operation_id,
                ),
            )
            self._event(operation_id, current, target_state, actor_id, native_digest)
            if reconciliation:
                self._connection.execute(
                    "UPDATE provider_operation SET state=?,updated_at=? WHERE operation_id=?",
                    (
                        OperationState.RECONCILIATION_REQUIRED.value,
                        utc_now(),
                        operation_id,
                    ),
                )
                self._event(
                    operation_id,
                    target_state,
                    OperationState.RECONCILIATION_REQUIRED,
                    actor_id,
                    native_digest,
                )
            return self.get(tenant_id, operation_id)

    def record_terminal_action(
        self,
        tenant_id: str,
        operation_id: str,
        state: OperationState,
        result: NativeProviderResult,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        if state not in {OperationState.ROLLED_BACK, OperationState.DESTROYED}:
            raise ValueError("terminal provider action must be rollback or destroy")
        with self._lock, self._connection:
            row = self._locked_row(tenant_id, operation_id)
            current = OperationState(row["state"])
            assert_monotonic_state(current, state)
            evidence_digest = digest(dict(result.native_payload))
            self._connection.execute(
                "UPDATE provider_operation SET state=?,native_evidence_json=?,native_evidence_digest=?,reconciliation_required=0,pending_terminal_state=NULL,updated_at=? WHERE operation_id=?",
                (
                    state.value,
                    canonical_bytes(dict(result.native_payload)).decode(),
                    evidence_digest,
                    utc_now(),
                    operation_id,
                ),
            )
            self._event(operation_id, current, state, actor_id, evidence_digest)
            return self.get(tenant_id, operation_id)

    def record_terminal_unknown(
        self,
        tenant_id: str,
        operation_id: str,
        intended_state: OperationState,
        evidence: Mapping[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        if intended_state not in {OperationState.ROLLED_BACK, OperationState.DESTROYED}:
            raise ValueError("unknown terminal intent must be rollback or destroy")
        with self._lock, self._connection:
            row = self._locked_row(tenant_id, operation_id)
            current = OperationState(row["state"])
            assert_monotonic_state(current, OperationState.RECONCILIATION_REQUIRED)
            evidence_value = dict(evidence)
            evidence_digest = digest(evidence_value)
            self._connection.execute(
                "UPDATE provider_operation SET state=?,native_evidence_json=?,native_evidence_digest=?,reconciliation_required=1,pending_terminal_state=?,updated_at=? WHERE operation_id=?",
                (
                    OperationState.RECONCILIATION_REQUIRED.value,
                    canonical_bytes(evidence_value).decode(),
                    evidence_digest,
                    intended_state.value,
                    utc_now(),
                    operation_id,
                ),
            )
            self._event(
                operation_id,
                current,
                OperationState.RECONCILIATION_REQUIRED,
                actor_id,
                evidence_digest,
            )
            return self.get(tenant_id, operation_id)

    def get(self, tenant_id: str, operation_id: str) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        operation_id = require_uuid(operation_id, "operation_id")
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM provider_operation WHERE tenant_id=? AND operation_id=?",
                (tenant_id, operation_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("provider operation not found")
            return self._row(row)

    def events(self, tenant_id: str, operation_id: str) -> list[dict[str, Any]]:
        self.get(tenant_id, operation_id)
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM provider_operation_event WHERE operation_id=? ORDER BY sequence",
                (operation_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def _locked_row(self, tenant_id: str, operation_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM provider_operation WHERE tenant_id=? AND operation_id=?",
            (tenant_id, operation_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("provider operation not found")
        return row

    def _event(
        self,
        operation_id: str,
        current: OperationState | None,
        target: OperationState,
        actor_id: str,
        evidence_digest: str | None,
    ) -> None:
        self._connection.execute(
            "INSERT INTO provider_operation_event(operation_id,from_state,to_state,actor_id,evidence_digest,created_at) VALUES(?,?,?,?,?,?)",
            (
                operation_id,
                current.value if current else None,
                target.value,
                actor_id,
                evidence_digest,
                utc_now(),
            ),
        )

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "operation_id": row["operation_id"],
            "tenant_id": row["tenant_id"],
            "actor_id": row["actor_id"],
            "action": row["action"],
            "target": json.loads(row["target_json"]),
            "target_digest": row["target_digest"],
            "request": json.loads(row["request_json"]),
            "request_digest": row["request_digest"],
            "plan": json.loads(row["plan_json"]),
            "plan_digest": row["plan_digest"],
            "state": row["state"],
            "provider_native_id": row["provider_native_id"],
            "native_evidence_digest": row["native_evidence_digest"],
            "normalized_evidence_digest": row["normalized_evidence_digest"],
            "reconciliation_required": bool(row["reconciliation_required"]),
            "pending_terminal_state": row["pending_terminal_state"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


class ProviderControlPlane:
    def __init__(
        self, journal: ProviderOperationJournal, adapters: Mapping[str, ProviderAdapter]
    ) -> None:
        self.journal = journal
        self.adapters = dict(adapters)

    def prepare(
        self,
        *,
        operation_id: str,
        tenant_id: str,
        actor_id: str,
        adapter_name: str,
        action: str,
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        adapter = self._adapter(adapter_name)
        plan = dict(adapter.plan(action, request))
        if plan.get("valid") is not True or plan.get("policy_denials"):
            raise PolicyDeniedError("provider plan did not pass policy validation")
        return self.journal.prepare(
            operation_id=operation_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action,
            target=adapter.target,
            request=request,
            plan=plan,
        )

    def execute(
        self, tenant_id: str, operation_id: str, adapter_name: str, *, actor_id: str
    ) -> dict[str, Any]:
        operation = self.journal.get(tenant_id, operation_id)
        if operation["state"] != OperationState.APPROVED.value:
            raise ConflictError("provider operation is not approved")
        adapter = self._adapter(adapter_name)
        self._assert_target(operation, adapter)
        try:
            result = adapter.apply(
                operation_id, operation["action"], operation["request"]
            )
        except ProviderOutcomeUnknown as exc:
            result = NativeProviderResult(
                OperationState.UNKNOWN,
                operation.get("provider_native_id"),
                {"error_type": type(exc).__name__, "message": str(exc)[:1000]},
            )
        return self.journal.record_result(
            tenant_id, operation_id, result, actor_id=actor_id
        )

    def reconcile(
        self, tenant_id: str, operation_id: str, adapter_name: str, *, actor_id: str
    ) -> dict[str, Any]:
        operation = self.journal.get(tenant_id, operation_id)
        if operation["state"] != OperationState.RECONCILIATION_REQUIRED.value:
            raise ConflictError("operation is not ready for provider reconciliation")
        adapter = self._adapter(adapter_name)
        self._assert_target(operation, adapter)
        observation_action = (
            operation.get("pending_terminal_state") or operation["action"]
        )
        try:
            if operation["provider_native_id"]:
                result = adapter.observe(
                    operation["provider_native_id"], observation_action
                )
            else:
                result = adapter.recover(
                    operation_id,
                    operation["action"],
                    operation["request"],
                    operation["plan"],
                )
        except ProviderOutcomeUnknown as exc:
            result = NativeProviderResult(
                OperationState.UNKNOWN,
                operation["provider_native_id"],
                {"error_type": type(exc).__name__, "message": str(exc)[:1000]},
            )
        if (
            operation.get("pending_terminal_state")
            and result.state == OperationState.SUCCEEDED
        ):
            return self.journal.record_terminal_action(
                tenant_id,
                operation_id,
                OperationState(operation["pending_terminal_state"]),
                result,
                actor_id=actor_id,
            )
        return self.journal.record_result(
            tenant_id, operation_id, result, actor_id=actor_id
        )

    def rollback(
        self, tenant_id: str, operation_id: str, adapter_name: str, *, actor_id: str
    ) -> dict[str, Any]:
        return self._terminal(
            tenant_id, operation_id, adapter_name, actor_id, OperationState.ROLLED_BACK
        )

    def destroy(
        self, tenant_id: str, operation_id: str, adapter_name: str, *, actor_id: str
    ) -> dict[str, Any]:
        return self._terminal(
            tenant_id, operation_id, adapter_name, actor_id, OperationState.DESTROYED
        )

    def _terminal(
        self,
        tenant_id: str,
        operation_id: str,
        adapter_name: str,
        actor_id: str,
        state: OperationState,
    ) -> dict[str, Any]:
        operation = self.journal.get(tenant_id, operation_id)
        if not operation["provider_native_id"]:
            raise ConflictError("provider native id is unavailable")
        adapter = self._adapter(adapter_name)
        self._assert_target(operation, adapter)
        method = (
            adapter.rollback if state == OperationState.ROLLED_BACK else adapter.destroy
        )
        try:
            result = method(
                operation["provider_native_id"],
                operation["action"],
                operation["request"],
            )
        except ProviderOutcomeUnknown as exc:
            return self.journal.record_terminal_unknown(
                tenant_id,
                operation_id,
                state,
                {"error_type": type(exc).__name__, "message": str(exc)[:1000]},
                actor_id=actor_id,
            )
        if result.state not in {OperationState.SUCCEEDED, OperationState.FAILED}:
            return self.journal.record_terminal_unknown(
                tenant_id,
                operation_id,
                state,
                dict(result.native_payload),
                actor_id=actor_id,
            )
        if result.state == OperationState.FAILED:
            raise ConflictError("terminal provider action failed")
        return self.journal.record_terminal_action(
            tenant_id, operation_id, state, result, actor_id=actor_id
        )

    def _adapter(self, name: str) -> ProviderAdapter:
        try:
            return self.adapters[name]
        except KeyError as exc:
            raise NotFoundError("provider adapter is not registered") from exc

    @staticmethod
    def _assert_target(operation: Mapping[str, Any], adapter: ProviderAdapter) -> None:
        if operation["target_digest"] != digest(adapter.target.to_dict()):
            raise ConflictError("provider target changed after planning")


class AWSCloudFormationAdapter:
    """AWS adapter that executes only a pre-created, reviewed change set."""

    def __init__(
        self,
        target: ExactTarget,
        *,
        cloudformation_client: Any | None = None,
        sts_client: Any | None = None,
    ) -> None:
        if target.provider != "aws" or target.service != "cloudformation":
            raise ValueError(
                "AWS adapter requires provider=aws and service=cloudformation"
            )
        self.target = target
        if cloudformation_client is None or sts_client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - optional production extra
                raise RuntimeError(
                    "boto3 is required; install elmos-pi-harness[cloud]"
                ) from exc
            session = boto3.Session(region_name=target.region)
            cloudformation_client = session.client("cloudformation")
            sts_client = session.client("sts")
        self.client = cloudformation_client
        identity = sts_client.get_caller_identity()
        if str(identity.get("Account")) != target.account_id:
            raise PolicyDeniedError(
                "AWS credential account does not match the exact target"
            )

    def plan(self, action: str, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if action != "execute_change_set":
            return {"valid": False, "policy_denials": ["unsupported_action"]}
        change_set_arn = request.get("change_set_arn")
        if not isinstance(change_set_arn, str) or not change_set_arn.startswith(
            "arn:aws:cloudformation:"
        ):
            return {"valid": False, "policy_denials": ["exact_change_set_arn_required"]}
        arn_parts = change_set_arn.split(":", 5)
        if (
            len(arn_parts) != 6
            or arn_parts[3] != self.target.region
            or arn_parts[4] != self.target.account_id
        ):
            return {"valid": False, "policy_denials": ["change_set_target_mismatch"]}
        response = self.client.describe_change_set(ChangeSetName=change_set_arn)
        forbidden = [
            change
            for change in response.get("Changes", [])
            if _widens_aws_access(change)
        ]
        executable = (
            response.get("Status") == "CREATE_COMPLETE"
            and response.get("ExecutionStatus") == "AVAILABLE"
        )
        return {
            "valid": not forbidden and executable,
            "policy_denials": (
                ["iam_or_public_exposure_widening"]
                if forbidden
                else ["change_set_not_executable"]
                if not executable
                else []
            ),
            "change_set_arn": change_set_arn,
            "change_set_id": response.get("ChangeSetId"),
            "stack_id": response.get("StackId"),
            "change_count": len(response.get("Changes", [])),
        }

    def apply(
        self, operation_id: str, action: str, request: Mapping[str, Any]
    ) -> NativeProviderResult:
        if action != "execute_change_set":
            raise PolicyDeniedError("unsupported AWS action")
        arn = require_nonempty(request.get("change_set_arn"), "change_set_arn", 2048)
        try:
            self.client.execute_change_set(
                ChangeSetName=arn, ClientRequestToken=operation_id
            )
            described = self.client.describe_change_set(ChangeSetName=arn)
        except (
            Exception
        ) as exc:  # provider exceptions are intentionally normalized at this boundary
            raise ProviderOutcomeUnknown(str(exc)) from exc
        native_id = described.get("StackId") or described.get("ChangeSetId")
        return NativeProviderResult(
            OperationState.SUBMITTED,
            native_id,
            {
                "change_set_id": described.get("ChangeSetId"),
                "stack_id": described.get("StackId"),
                "execution_status": described.get("ExecutionStatus"),
            },
        )

    def observe(self, native_id: str, action: str) -> NativeProviderResult:
        try:
            response = self.client.describe_stacks(StackName=native_id)
        except Exception as exc:
            error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if (
                action == OperationState.DESTROYED.value
                and error_code == "ValidationError"
            ):
                return NativeProviderResult(
                    OperationState.SUCCEEDED,
                    native_id,
                    {"stack_id": native_id, "stack_status": "NOT_FOUND_AFTER_DELETE"},
                )
            raise ProviderOutcomeUnknown(str(exc)) from exc
        stack = response["Stacks"][0]
        status = stack["StackStatus"]
        if action == OperationState.ROLLED_BACK.value:
            state = (
                OperationState.SUCCEEDED
                if "ROLLBACK_COMPLETE" in status
                else OperationState.FAILED
                if status.endswith("_FAILED")
                else OperationState.UNKNOWN
            )
        else:
            state = (
                OperationState.SUCCEEDED
                if status.endswith("_COMPLETE") and "ROLLBACK" not in status
                else OperationState.FAILED
                if status.endswith("_FAILED") or "ROLLBACK_COMPLETE" in status
                else OperationState.UNKNOWN
            )
        return NativeProviderResult(
            state, native_id, {"stack_id": native_id, "stack_status": status}
        )

    def recover(
        self,
        operation_id: str,
        action: str,
        request: Mapping[str, Any],
        plan: Mapping[str, Any],
    ) -> NativeProviderResult:
        """Recover identity after an ambiguous execute-change-set response."""
        if action != "execute_change_set":
            raise PolicyDeniedError("unsupported AWS recovery action")
        planned_id = plan.get("stack_id")
        if not planned_id:
            change_set_arn = require_nonempty(
                request.get("change_set_arn"), "change_set_arn", 2048
            )
            try:
                described = self.client.describe_change_set(
                    ChangeSetName=change_set_arn
                )
            except Exception as exc:
                raise ProviderOutcomeUnknown(str(exc)) from exc
            planned_id = described.get("StackId")
        if not planned_id:
            return NativeProviderResult(
                OperationState.UNKNOWN,
                None,
                {
                    "client_request_token": operation_id,
                    "recovery": "stack_identity_not_yet_observable",
                },
            )
        return self.observe(str(planned_id), action)

    def rollback(
        self, native_id: str, action: str, request: Mapping[str, Any]
    ) -> NativeProviderResult:
        rollback_change_set = require_nonempty(
            request.get("rollback_change_set_arn"), "rollback_change_set_arn", 2048
        )
        self.client.execute_change_set(ChangeSetName=rollback_change_set)
        return NativeProviderResult(
            OperationState.UNKNOWN,
            native_id,
            {
                "stack_id": native_id,
                "rollback_change_set_arn": rollback_change_set,
                "submitted": True,
            },
        )

    def destroy(
        self, native_id: str, action: str, request: Mapping[str, Any]
    ) -> NativeProviderResult:
        if request.get("allow_destroy") is not True:
            raise PolicyDeniedError(
                "destroy requires exact allow_destroy authorization"
            )
        self.client.delete_stack(
            StackName=native_id, ClientRequestToken=str(uuid.uuid4())
        )
        return NativeProviderResult(
            OperationState.UNKNOWN,
            native_id,
            {"stack_id": native_id, "delete_requested": True},
        )


def _widens_aws_access(change: Mapping[str, Any]) -> bool:
    resource = change.get("ResourceChange", {})
    resource_type = resource.get("ResourceType", "")
    if resource_type in {
        "AWS::IAM::Policy",
        "AWS::IAM::ManagedPolicy",
        "AWS::IAM::Role",
    }:
        return True
    return resource_type in {
        "AWS::S3::BucketPolicy",
        "AWS::EC2::SecurityGroup",
        "AWS::EC2::SecurityGroupIngress",
    }
