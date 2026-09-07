"""Production-shaped external operation boundary and adapter SPI.

The coordinator is deliberately inert without a trusted authorization verifier
and a registered adapter.  Caller payloads cannot promote local/emulated output
to external evidence.  Uncertain side effects are persisted as ``UNKNOWN`` and
must be reconciled before retry or compensation.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import subprocess
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from .errors import AuthorizationError, ContractError, StaleStateError
from .models import (
    bytes_digest,
    canonical_json,
    digest,
    relative_path,
    require_mapping,
    require_sha256_digest,
    require_string,
)
from .storage import DurableStore


class ExternalState(StrEnum):
    DRY_RUN = "DRY_RUN"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    UNKNOWN = "UNKNOWN"
    RECONCILING = "RECONCILING"
    RECONCILED = "RECONCILED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"
    DENIED = "DENIED"
    CANCELLED = "CANCELLED"


class OutcomeStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    DENIED = "DENIED"
    CANCELLED = "CANCELLED"
    NOT_RUN = "NOT_RUN"


CAPABILITIES = frozenset(
    {
        "scm",
        "object-store",
        "event-bus",
        "secrets-broker",
        "provider",
        "kubernetes",
        "customer-repository",
    }
)

EXTERNAL_EVIDENCE_CLASSES = frozenset({"EXTERNAL_EXECUTED", "INDEPENDENTLY_VERIFIED"})
LOCAL_EVIDENCE_CLASSES = frozenset({"LOCAL_ENGINEERING_VALIDATED", "EMULATOR_EXECUTED", "STATIC_VALIDATED"})


def _parse_timestamp(value: Any, name: str) -> datetime:
    raw = require_string(value, name)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ContractError("INVALID_INPUT", f"{name} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractError("INVALID_INPUT", f"{name} must include a timezone")
    return parsed.astimezone(UTC)


def _safe_request_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return persistable metadata while refusing inline credentials."""

    secret_keys = {"secret", "secret_value", "password", "token", "api_key", "private_key", "authorization"}

    def visit(item: Any, path: str) -> Any:
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            for key, child in item.items():
                normalized = str(key).casefold().replace("-", "_")
                if normalized in secret_keys:
                    raise ContractError("SECRET_EXPOSURE", f"inline secret material is forbidden at {path}.{key}")
                if normalized in {"content", "body", "data"} and isinstance(child, (str, bytes, bytearray)):
                    raw = child.encode("utf-8") if isinstance(child, str) else bytes(child)
                    result[str(key)] = {"content_hash": bytes_digest(raw), "size_bytes": len(raw), "redacted": True}
                else:
                    result[str(key)] = visit(child, f"{path}.{key}")
            return result
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            return [visit(child, f"{path}[]") for child in item]
        if isinstance(item, bytes):
            return {"content_hash": bytes_digest(item), "size_bytes": len(item), "redacted": True}
        return item

    return visit(value, "request")


@dataclass(frozen=True, slots=True)
class ExternalOperationRequest:
    tenant_id: str
    account_id: str
    capability: str
    adapter_id: str
    adapter_version: str
    provider_instance: str
    region: str
    native_resource_id: str
    action: str
    idempotency_key: str
    side_effects: bool
    payload: Mapping[str, Any] = field(default_factory=dict)
    run_id: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ExternalOperationRequest:
        capability = require_string(value.get("capability"), "capability")
        if capability not in CAPABILITIES:
            raise ContractError("CAPABILITY_UNKNOWN", f"unsupported external capability: {capability}")
        side_effects = value.get("side_effects", True)
        if not isinstance(side_effects, bool):
            raise ContractError("INVALID_INPUT", "side_effects must be a boolean")
        payload = require_mapping(value.get("payload", {}), "payload")
        _safe_request_metadata(payload)
        return cls(
            tenant_id=require_string(value.get("tenant_id"), "tenant_id"),
            account_id=require_string(value.get("account_id"), "account_id"),
            capability=capability,
            adapter_id=require_string(value.get("adapter_id"), "adapter_id"),
            adapter_version=require_string(value.get("adapter_version"), "adapter_version"),
            provider_instance=require_string(value.get("provider_instance"), "provider_instance"),
            region=require_string(value.get("region"), "region"),
            native_resource_id=require_string(value.get("native_resource_id"), "native_resource_id"),
            action=require_string(value.get("action"), "action"),
            idempotency_key=require_string(value.get("idempotency_key"), "idempotency_key"),
            side_effects=side_effects,
            payload=payload,
            run_id=str(value["run_id"]) if value.get("run_id") else None,
        )

    @property
    def request_hash(self) -> str:
        return digest(
            {
                "tenant_id": self.tenant_id,
                "account_id": self.account_id,
                "capability": self.capability,
                "adapter_id": self.adapter_id,
                "adapter_version": self.adapter_version,
                "provider_instance": self.provider_instance,
                "region": self.region,
                "native_resource_id": self.native_resource_id,
                "action": self.action,
                "idempotency_key": self.idempotency_key,
                "side_effects": self.side_effects,
                "payload": self.payload,
            }
        )


@dataclass(frozen=True, slots=True)
class AdapterOutcome:
    status: OutcomeStatus
    result: Mapping[str, Any] = field(default_factory=dict)
    raw_evidence: Mapping[str, Any] = field(default_factory=dict)
    evidence_class: str = "LOCAL_ENGINEERING_VALIDATED"
    native_operation_id: str | None = None
    side_effect_performed: bool = False
    retryable: bool = False
    compensation_token: str | None = None
    error: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        allowed = EXTERNAL_EVIDENCE_CLASSES | LOCAL_EVIDENCE_CLASSES | {"NOT_RUN"}
        if self.evidence_class not in allowed:
            raise ContractError("EVIDENCE_INVALID", f"unsupported evidence class: {self.evidence_class}")
        _safe_request_metadata(self.result)
        _safe_request_metadata(self.raw_evidence)


class ExternalAdapter(Protocol):
    adapter_id: str
    adapter_version: str
    capability: str

    def execute(self, operation: Mapping[str, Any], payload: Mapping[str, Any]) -> AdapterOutcome: ...

    def reconcile(self, operation: Mapping[str, Any]) -> AdapterOutcome: ...

    def compensate(self, operation: Mapping[str, Any]) -> AdapterOutcome: ...


class AuthorizationVerifier(Protocol):
    def verify(self, grant: Mapping[str, Any], operation: Mapping[str, Any]) -> bool: ...


class DenyAllAuthorizationVerifier:
    def verify(self, grant: Mapping[str, Any], operation: Mapping[str, Any]) -> bool:
        del grant, operation
        return False


class HMACAuthorizationVerifier:
    """Verify grants produced by a separately configured authority service."""

    def __init__(self, keys: Mapping[str, bytes]) -> None:
        self._keys = dict(keys)

    @staticmethod
    def payload(grant: Mapping[str, Any]) -> dict[str, Any]:
        return {str(key): value for key, value in grant.items() if key != "signature"}

    @classmethod
    def sign(cls, grant: Mapping[str, Any], key: bytes) -> str:
        return hmac.new(key, canonical_json(cls.payload(grant)), hashlib.sha256).hexdigest()

    def verify(self, grant: Mapping[str, Any], operation: Mapping[str, Any]) -> bool:
        key_id = str(grant.get("key_id", ""))
        key = self._keys.get(key_id)
        signature = str(grant.get("signature", ""))
        if key is None or not signature:
            return False
        expected = self.sign(grant, key)
        if not hmac.compare_digest(expected, signature):
            return False
        if str(grant.get("source", "")).casefold() in {"conversation", "model", "adapter"}:
            return False
        if grant.get("tenant_id") != operation.get("tenant_id") or grant.get("account_id") != operation.get("account_id"):
            return False
        if operation.get("capability") not in set(grant.get("capabilities", [])):
            return False
        if operation.get("action") not in set(grant.get("actions", [])):
            return False
        resource_ids = set(grant.get("native_resource_ids", []))
        if resource_ids and operation.get("native_resource_id") not in resource_ids:
            return False
        try:
            expires_at = _parse_timestamp(grant.get("expires_at"), "grant.expires_at")
        except ContractError:
            return False
        return expires_at > datetime.now(UTC)


class ExternalOperationCoordinator:
    def __init__(
        self,
        store: DurableStore,
        *,
        authorizer: AuthorizationVerifier | None = None,
        receipt_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
    ) -> None:
        self.store = store
        self.authorizer = authorizer or DenyAllAuthorizationVerifier()
        self.receipt_verifier = receipt_verifier
        self._adapters: dict[tuple[str, str], ExternalAdapter] = {}
        self._ephemeral_payloads: dict[str, Mapping[str, Any]] = {}

    def register(self, adapter: ExternalAdapter) -> None:
        if adapter.capability not in CAPABILITIES:
            raise ContractError("CAPABILITY_UNKNOWN", f"adapter has unsupported capability: {adapter.capability}")
        key = (adapter.adapter_id, adapter.adapter_version)
        if key in self._adapters:
            raise ContractError("ADAPTER_CONFLICT", "adapter version is already registered")
        self._adapters[key] = adapter

    def plan(self, request: ExternalOperationRequest | Mapping[str, Any]) -> dict[str, Any]:
        parsed = request if isinstance(request, ExternalOperationRequest) else ExternalOperationRequest.from_mapping(request)
        operation = self.store.create_external_operation(
            tenant_id=parsed.tenant_id,
            account_id=parsed.account_id,
            run_id=parsed.run_id,
            capability=parsed.capability,
            adapter_id=parsed.adapter_id,
            adapter_version=parsed.adapter_version,
            provider_instance=parsed.provider_instance,
            region=parsed.region,
            native_resource_id=parsed.native_resource_id,
            action=parsed.action,
            side_effects=parsed.side_effects,
            idempotency_key=parsed.idempotency_key,
            request_hash=parsed.request_hash,
            request_metadata=_safe_request_metadata(parsed.payload),
        )
        self._ephemeral_payloads[operation["operation_id"]] = dict(parsed.payload)
        return {**operation, "external_evidence": "NOT_RUN", "certification": "NOT_CERTIFIED"}

    def authorize(self, operation_id: str, *, tenant_id: str, grant: Mapping[str, Any]) -> dict[str, Any]:
        operation = self._require(operation_id, tenant_id)
        if operation["state"] != ExternalState.DRY_RUN.value:
            raise StaleStateError("EXTERNAL_OPERATION_STATE_CONFLICT", "only DRY_RUN operations can be authorized")
        if not self.authorizer.verify(grant, operation):
            self.store.transition_external_operation(
                operation_id, tenant_id=tenant_id, expected_states={ExternalState.DRY_RUN.value},
                target=ExternalState.DENIED.value, error={"code": "AUTHORITY_DENIED"},
            )
            raise AuthorizationError("AUTHORITY_DENIED", "external authorization grant is invalid or out of scope")
        authority_hash = digest(HMACAuthorizationVerifier.payload(grant))
        authorized = self.store.transition_external_operation(
            operation_id, tenant_id=tenant_id, expected_states={ExternalState.DRY_RUN.value},
            target=ExternalState.AUTHORIZED.value, authority_hash=authority_hash,
        )
        self.store.record_external_receipt(
            tenant_id=tenant_id, operation_id=operation_id, receipt_type="authorization", status="VERIFIED",
            producer_id=str(grant.get("issuer", "external-authority")), verifier_id="kernel-authorizer",
            evidence_class="EXTERNAL_EXECUTED", raw_evidence={"grant_hash": authority_hash, "key_id": grant.get("key_id")},
        )
        return authorized

    def execute(
        self, operation_id: str, *, tenant_id: str, payload: Mapping[str, Any] | None = None,
        producer_id: str = "kernel-executor",
    ) -> dict[str, Any]:
        operation = self._require(operation_id, tenant_id)
        if operation["state"] == ExternalState.EXECUTED.value:
            return self._with_receipts(operation)
        if operation["state"] == ExternalState.UNKNOWN.value:
            raise StaleStateError("UNKNOWN_OUTCOME_REQUIRES_RECONCILIATION", "unknown side effects cannot be retried")
        if operation["state"] != ExternalState.AUTHORIZED.value:
            raise StaleStateError("EXTERNAL_OPERATION_STATE_CONFLICT", "operation is not authorized")
        adapter = self._adapter(operation)
        request_payload = dict(payload or self._ephemeral_payloads.get(operation_id, {}))
        if not request_payload and operation.get("request_metadata"):
            raise ContractError(
                "EXECUTION_PAYLOAD_REQUIRED",
                "the original payload is not persisted; it must be supplied again after coordinator restart",
            )
        if request_payload:
            reconstructed = ExternalOperationRequest(
                tenant_id=operation["tenant_id"], account_id=operation["account_id"],
                capability=operation["capability"], adapter_id=operation["adapter_id"],
                adapter_version=operation["adapter_version"], provider_instance=operation["provider_instance"],
                region=operation["region"], native_resource_id=operation["native_resource_id"],
                action=operation["action"], idempotency_key=operation["idempotency_key"],
                side_effects=bool(operation["side_effects"]), payload=request_payload, run_id=operation.get("run_id"),
            )
            if reconstructed.request_hash != operation["request_hash"]:
                raise ContractError("REQUEST_DIGEST_MISMATCH", "execution payload differs from the planned request")
        self.store.transition_external_operation(
            operation_id, tenant_id=tenant_id, expected_states={ExternalState.AUTHORIZED.value},
            target=ExternalState.EXECUTING.value,
        )
        try:
            outcome = adapter.execute(operation, request_payload)
        except TimeoutError:
            outcome = AdapterOutcome(
                status=OutcomeStatus.UNKNOWN if operation["side_effects"] else OutcomeStatus.FAILED,
                error={"code": "ADAPTER_TIMEOUT"}, retryable=not bool(operation["side_effects"]),
            )
        except Exception as exc:  # noqa: BLE001 - adapter boundary becomes structured state
            outcome = AdapterOutcome(
                status=OutcomeStatus.UNKNOWN if operation["side_effects"] else OutcomeStatus.FAILED,
                error={"code": "ADAPTER_FAILURE", "type": type(exc).__name__}, retryable=False,
            )
        target = {
            OutcomeStatus.SUCCEEDED: ExternalState.EXECUTED,
            OutcomeStatus.UNKNOWN: ExternalState.UNKNOWN,
            OutcomeStatus.FAILED: ExternalState.FAILED,
            OutcomeStatus.DENIED: ExternalState.DENIED,
            OutcomeStatus.CANCELLED: ExternalState.CANCELLED,
            OutcomeStatus.NOT_RUN: ExternalState.FAILED,
        }[outcome.status]
        persisted_result = dict(outcome.result)
        if outcome.native_operation_id:
            persisted_result["native_operation_id"] = outcome.native_operation_id
        updated = self.store.transition_external_operation(
            operation_id, tenant_id=tenant_id, expected_states={ExternalState.EXECUTING.value},
            target=target.value, result=persisted_result, error=dict(outcome.error or {}),
            unknown_outcome=outcome.status == OutcomeStatus.UNKNOWN,
            compensation_token=outcome.compensation_token,
        )
        evidence_class = outcome.evidence_class
        if evidence_class == "INDEPENDENTLY_VERIFIED":
            evidence_class = "EXTERNAL_EXECUTED"
        if evidence_class in EXTERNAL_EVIDENCE_CLASSES and not outcome.raw_evidence:
            evidence_class = "LOCAL_ENGINEERING_VALIDATED"
        self.store.record_external_receipt(
            tenant_id=tenant_id, operation_id=operation_id, receipt_type="execution",
            status=outcome.status.value, producer_id=producer_id, verifier_id=None,
            evidence_class=evidence_class,
            raw_evidence={
                "native_operation_id": outcome.native_operation_id,
                "side_effect_performed": outcome.side_effect_performed,
                "retryable": outcome.retryable,
                **dict(outcome.raw_evidence),
            },
        )
        self.store.enqueue_outbox(
            tenant_id=tenant_id, operation_id=operation_id, topic="autonomy.external-operations",
            ordering_key=operation_id, event_type=f"EXTERNAL_{target.value}",
            payload={"operation_id": operation_id, "state": target.value, "request_hash": operation["request_hash"]},
            idempotency_key=f"{operation_id}:{target.value}",
        )
        return self._with_receipts(updated)

    def reconcile(self, operation_id: str, *, tenant_id: str, verifier_id: str) -> dict[str, Any]:
        operation = self._require(operation_id, tenant_id)
        if operation["state"] not in {ExternalState.UNKNOWN.value, ExternalState.EXECUTED.value}:
            raise StaleStateError("EXTERNAL_OPERATION_STATE_CONFLICT", "operation is not reconcilable")
        previous = operation["state"]
        self.store.transition_external_operation(
            operation_id, tenant_id=tenant_id, expected_states={previous}, target=ExternalState.RECONCILING.value,
        )
        try:
            outcome = self._adapter(operation).reconcile(operation)
        except Exception as exc:  # noqa: BLE001 - reconciliation uncertainty must be durable
            outcome = AdapterOutcome(
                status=OutcomeStatus.UNKNOWN,
                error={"code": "RECONCILIATION_FAILED", "type": type(exc).__name__},
                evidence_class="NOT_RUN",
            )
        if outcome.status == OutcomeStatus.SUCCEEDED:
            target = ExternalState.RECONCILED
        elif outcome.status == OutcomeStatus.UNKNOWN:
            target = ExternalState.UNKNOWN
        else:
            target = ExternalState.FAILED
        updated = self.store.transition_external_operation(
            operation_id, tenant_id=tenant_id, expected_states={ExternalState.RECONCILING.value},
            target=target.value, result=dict(outcome.result), error=dict(outcome.error or {}),
            unknown_outcome=target == ExternalState.UNKNOWN,
        )
        verification_record = {
            "operation_id": operation_id,
            "tenant_id": tenant_id,
            "producer_id": operation["adapter_id"],
            "verifier_id": verifier_id,
            "status": outcome.status.value,
            "raw_evidence": dict(outcome.raw_evidence),
        }
        independent = bool(
            verifier_id
            and verifier_id != operation["adapter_id"]
            and outcome.raw_evidence
            and self.receipt_verifier is not None
            and self.receipt_verifier(verification_record)
        )
        if outcome.evidence_class in EXTERNAL_EVIDENCE_CLASSES:
            evidence_class = "INDEPENDENTLY_VERIFIED" if independent else "EXTERNAL_EXECUTED"
        else:
            evidence_class = outcome.evidence_class
        self.store.record_external_receipt(
            tenant_id=tenant_id, operation_id=operation_id, receipt_type="reconciliation",
            status=outcome.status.value, producer_id=operation["adapter_id"], verifier_id=verifier_id,
            evidence_class=evidence_class, raw_evidence=dict(outcome.raw_evidence),
        )
        return self._with_receipts(updated)

    def compensate(self, operation_id: str, *, tenant_id: str, producer_id: str = "kernel-executor") -> dict[str, Any]:
        operation = self._require(operation_id, tenant_id)
        if operation["state"] not in {ExternalState.EXECUTED.value, ExternalState.RECONCILED.value}:
            raise StaleStateError("EXTERNAL_OPERATION_STATE_CONFLICT", "operation is not compensatable")
        previous = operation["state"]
        self.store.transition_external_operation(
            operation_id, tenant_id=tenant_id, expected_states={previous}, target=ExternalState.COMPENSATING.value,
        )
        try:
            outcome = self._adapter(operation).compensate(operation)
        except Exception as exc:  # noqa: BLE001 - compensation uncertainty must be durable
            outcome = AdapterOutcome(
                status=OutcomeStatus.UNKNOWN,
                error={"code": "COMPENSATION_FAILED", "type": type(exc).__name__},
                evidence_class="NOT_RUN",
            )
        target = ExternalState.COMPENSATED if outcome.status == OutcomeStatus.SUCCEEDED else ExternalState.UNKNOWN if outcome.status == OutcomeStatus.UNKNOWN else ExternalState.FAILED
        updated = self.store.transition_external_operation(
            operation_id, tenant_id=tenant_id, expected_states={ExternalState.COMPENSATING.value},
            target=target.value, result=dict(outcome.result), error=dict(outcome.error or {}),
            unknown_outcome=target == ExternalState.UNKNOWN,
        )
        self.store.record_external_receipt(
            tenant_id=tenant_id, operation_id=operation_id, receipt_type="compensation",
            status=outcome.status.value, producer_id=producer_id, verifier_id=None,
            evidence_class=(
                "EXTERNAL_EXECUTED"
                if outcome.evidence_class == "INDEPENDENTLY_VERIFIED"
                else outcome.evidence_class
            ),
            raw_evidence=dict(outcome.raw_evidence),
        )
        return self._with_receipts(updated)

    def get(self, operation_id: str, *, tenant_id: str) -> dict[str, Any]:
        return self._with_receipts(self._require(operation_id, tenant_id))

    def _require(self, operation_id: str, tenant_id: str) -> dict[str, Any]:
        value = self.store.get_external_operation(operation_id, tenant_id=tenant_id)
        if value is None:
            raise ContractError("EXTERNAL_OPERATION_NOT_FOUND", "operation is not visible in the requested tenant")
        return value

    def _adapter(self, operation: Mapping[str, Any]) -> ExternalAdapter:
        adapter = self._adapters.get((str(operation["adapter_id"]), str(operation["adapter_version"])))
        if adapter is None or adapter.capability != operation["capability"]:
            raise ContractError("ADAPTER_UNAVAILABLE", "exact adapter version/capability is not registered")
        return adapter

    def _with_receipts(self, operation: Mapping[str, Any]) -> dict[str, Any]:
        receipts = self.store.list_external_receipts(str(operation["operation_id"]), tenant_id=str(operation["tenant_id"]))
        successful_receipts = [
            item
            for item in receipts
            if item.get("receipt_type") != "authorization"
            and item.get("status") in {"SUCCEEDED", "PASS", "VERIFIED", "PUBLISHED"}
        ]
        independently_verified = any(
            item.get("evidence_class") == "INDEPENDENTLY_VERIFIED" for item in successful_receipts
        )
        externally_executed = any(
            item.get("evidence_class") in EXTERNAL_EVIDENCE_CLASSES for item in successful_receipts
        )
        return {
            **dict(operation),
            "receipts": receipts,
            "external_evidence": "INDEPENDENTLY_VERIFIED" if independently_verified else "EXTERNAL_EXECUTED" if externally_executed else "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }


class ScriptedExternalAdapter:
    """Deterministic adapter used for local integration and fault tests."""

    def __init__(
        self, adapter_id: str, capability: str, *, adapter_version: str = "2.0.0",
        execute_outcome: AdapterOutcome | Callable[[Mapping[str, Any], Mapping[str, Any]], AdapterOutcome] | None = None,
        reconcile_outcome: AdapterOutcome | None = None, compensate_outcome: AdapterOutcome | None = None,
    ) -> None:
        self.adapter_id = adapter_id
        self.adapter_version = adapter_version
        self.capability = capability
        self._execute = execute_outcome or AdapterOutcome(status=OutcomeStatus.NOT_RUN, evidence_class="NOT_RUN")
        self._reconcile = reconcile_outcome or AdapterOutcome(status=OutcomeStatus.UNKNOWN, evidence_class="NOT_RUN")
        self._compensate = compensate_outcome or AdapterOutcome(status=OutcomeStatus.NOT_RUN, evidence_class="NOT_RUN")

    def execute(self, operation: Mapping[str, Any], payload: Mapping[str, Any]) -> AdapterOutcome:
        return self._execute(operation, payload) if callable(self._execute) else self._execute

    def reconcile(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        del operation
        return self._reconcile

    def compensate(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        del operation
        return self._compensate


class LocalGitSCMAdapter:
    """Exact-commit local Git adapter; network operations are intentionally absent."""

    adapter_id = "local-git"
    adapter_version = "2.0.0"
    capability = "scm"

    def __init__(self, allowed_roots: Sequence[str], *, allow_writes: bool = False) -> None:
        self.allowed_roots = tuple(Path(root).resolve() for root in allowed_roots)
        self.allow_writes = allow_writes

    def _repository(self, payload: Mapping[str, Any]) -> Path:
        repository = Path(require_string(payload.get("repository_path"), "payload.repository_path")).resolve()
        if not any(repository == root or repository.is_relative_to(root) for root in self.allowed_roots):
            raise AuthorizationError("SCM_SCOPE_DENIED", "repository path is outside approved roots")
        if not (repository / ".git").exists():
            raise ContractError("SCM_REPOSITORY_INVALID", "approved path is not a Git repository")
        return repository

    @staticmethod
    def _git(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
        environment = {"PATH": os.environ.get("PATH", ""), "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
        return subprocess.run(
            ["git", "-C", str(repository), *args], check=True, capture_output=True, text=True,
            timeout=30, env=environment,
        )

    def execute(self, operation: Mapping[str, Any], payload: Mapping[str, Any]) -> AdapterOutcome:
        repository = self._repository(payload)
        action = str(operation["action"])
        if action == "resolve-exact-commit":
            commit = require_string(payload.get("commit"), "payload.commit")
            resolved = self._git(repository, "rev-parse", "--verify", f"{commit}^{{commit}}").stdout.strip()
            tree = self._git(repository, "rev-parse", f"{resolved}^{{tree}}").stdout.strip()
            return AdapterOutcome(
                status=OutcomeStatus.SUCCEEDED,
                result={"commit": resolved, "tree": tree, "complete": True},
                raw_evidence={"command": ["git", "rev-parse"], "commit": resolved, "tree": tree},
                evidence_class="LOCAL_ENGINEERING_VALIDATED",
                native_operation_id=resolved,
            )
        if action == "create-branch":
            if not self.allow_writes:
                return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "SCM_WRITE_DENIED"})
            branch = require_string(payload.get("branch"), "payload.branch")
            base = require_string(payload.get("base_commit"), "payload.base_commit")
            if branch.startswith("-") or ".." in branch or any(char.isspace() for char in branch):
                raise ContractError("SCM_BRANCH_INVALID", "branch name is unsafe")
            base_commit = self._git(repository, "rev-parse", "--verify", f"{base}^{{commit}}").stdout.strip()
            self._git(repository, "branch", branch, base_commit)
            return AdapterOutcome(
                status=OutcomeStatus.SUCCEEDED, result={"branch": branch, "base_commit": base_commit},
                raw_evidence={"branch": branch, "base_commit": base_commit},
                side_effect_performed=True, compensation_token=branch,
            )
        return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "SCM_ACTION_DENIED"})

    def reconcile(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        result = operation.get("result") if isinstance(operation.get("result"), Mapping) else {}
        if result.get("commit") or result.get("branch"):
            return AdapterOutcome(status=OutcomeStatus.SUCCEEDED, result=result, raw_evidence={"reconciled": True})
        return AdapterOutcome(status=OutcomeStatus.UNKNOWN, evidence_class="NOT_RUN")

    def compensate(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        metadata = require_mapping(operation.get("request_metadata", {}), "operation.request_metadata")
        repository = self._repository(metadata)
        branch = operation.get("compensation_token")
        if not self.allow_writes or not isinstance(branch, str):
            return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "SCM_COMPENSATION_DENIED"})
        self._git(repository, "branch", "-D", branch)
        return AdapterOutcome(
            status=OutcomeStatus.SUCCEEDED, result={"deleted_branch": branch},
            raw_evidence={"deleted_branch": branch}, side_effect_performed=True,
        )


class SCMTransport(Protocol):
    evidence_class: str

    def invoke(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class CanonicalSCMAdapter:
    """Remote SCM SPI bound to provider instance, native repository and commit."""

    adapter_id = "canonical-scm"
    adapter_version = "2.0.0"
    capability = "scm"
    _actions = frozenset(
        {
            "resolve-exact-commit",
            "hydrate-workspace",
            "create-branch",
            "create-pull-request",
            "create-tag",
            "register-webhook",
            "delete-branch",
        }
    )
    _write_actions = frozenset(
        {"create-branch", "create-pull-request", "create-tag", "register-webhook", "delete-branch"}
    )

    def __init__(self, transport: SCMTransport, *, adapter_id: str, adapter_version: str = "2.0.0") -> None:
        self.transport = transport
        self.adapter_id = require_string(adapter_id, "adapter_id")
        self.adapter_version = require_string(adapter_version, "adapter_version")

    def execute(self, operation: Mapping[str, Any], payload: Mapping[str, Any]) -> AdapterOutcome:
        action = str(operation["action"])
        if action not in self._actions:
            return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "SCM_ACTION_DENIED"})
        commit = payload.get("exact_commit")
        if action in {"resolve-exact-commit", "hydrate-workspace", *self._write_actions}:
            commit = require_string(commit, "payload.exact_commit")
            if len(commit) not in {40, 64} or any(char not in "0123456789abcdefABCDEF" for char in commit):
                raise ContractError("SCM_COMMIT_INVALID", "SCM actions require an exact 40/64 hex commit")
        credential_ref = require_string(payload.get("credential_lease_ref"), "payload.credential_lease_ref")
        sparse_value = payload.get("sparse_paths", [])
        if not isinstance(sparse_value, Sequence) or isinstance(sparse_value, (str, bytes, bytearray)):
            raise ContractError("SCM_SPARSE_PATHS_INVALID", "sparse_paths must be an array")
        sparse_paths = [relative_path(str(path), "payload.sparse_paths[]") for path in sparse_value]
        request = {
            "schema_version": "2.0.0",
            "provider_instance": operation["provider_instance"],
            "native_repository_id": operation["native_resource_id"],
            "region": operation["region"],
            "action": action,
            "exact_commit": str(commit).lower() if commit else None,
            "credential_lease_ref": credential_ref,
            "idempotency_key": operation["idempotency_key"],
            "submodules": bool(payload.get("submodules", False)),
            "lfs": bool(payload.get("lfs", False)),
            "sparse_paths": sparse_paths,
            "write": {key: value for key, value in payload.items() if key in {"branch", "title", "body_ref", "tag", "webhook_ref"}},
        }
        response = require_mapping(self.transport.invoke(request), "SCM response")
        status = str(response.get("status", "UNKNOWN")).upper()
        mapped = {
            "SUCCEEDED": OutcomeStatus.SUCCEEDED,
            "FAILED": OutcomeStatus.FAILED,
            "DENIED": OutcomeStatus.DENIED,
            "UNKNOWN": OutcomeStatus.UNKNOWN,
            "NOT_RUN": OutcomeStatus.NOT_RUN,
        }.get(status, OutcomeStatus.UNKNOWN)
        result = require_mapping(response.get("result", {}), "SCM response.result")
        if mapped == OutcomeStatus.SUCCEEDED:
            observed_commit = str(result.get("exact_commit", "")).lower()
            if commit and observed_commit != str(commit).lower():
                raise ContractError("SCM_COMMIT_DRIFT", "SCM provider resolved a different commit")
            if action == "hydrate-workspace":
                complete = (
                    result.get("workspace_complete") is True
                    and (not request["submodules"] or result.get("submodules_verified") is True)
                    and (not request["lfs"] or result.get("lfs_verified") is True)
                    and (not sparse_paths or result.get("sparse_hydrated") is True)
                )
                if not complete:
                    return AdapterOutcome(
                        status=OutcomeStatus.FAILED,
                        result={**dict(result), "workspace_complete": False},
                        raw_evidence=require_mapping(response.get("raw_evidence", {}), "SCM raw evidence"),
                        evidence_class=getattr(self.transport, "evidence_class", "NOT_RUN"),
                        error={"code": "SCM_WORKSPACE_INCOMPLETE"},
                    )
        return AdapterOutcome(
            status=mapped,
            result=result,
            raw_evidence=require_mapping(response.get("raw_evidence", {}), "SCM response.raw_evidence"),
            evidence_class=getattr(self.transport, "evidence_class", "NOT_RUN"),
            native_operation_id=str(response["native_operation_id"]) if response.get("native_operation_id") else None,
            side_effect_performed=action in self._write_actions and bool(response.get("side_effect_performed", False)),
            compensation_token=str(response["compensation_token"]) if response.get("compensation_token") else None,
            error=require_mapping(response.get("error", {}), "SCM response.error") if response.get("error") else None,
        )

    def reconcile(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        response = require_mapping(
            self.transport.invoke(
                {
                    "schema_version": "2.0.0",
                    "action": "reconcile",
                    "provider_instance": operation["provider_instance"],
                    "native_repository_id": operation["native_resource_id"],
                    "idempotency_key": operation["idempotency_key"],
                    "native_operation_id": (
                        operation.get("result", {}).get("native_operation_id")
                        if isinstance(operation.get("result"), Mapping)
                        else None
                    ),
                }
            ),
            "SCM reconciliation response",
        )
        return AdapterOutcome(
            status=OutcomeStatus.SUCCEEDED if response.get("status") == "SUCCEEDED" else OutcomeStatus.UNKNOWN,
            result=require_mapping(response.get("result", {}), "SCM result"),
            raw_evidence=require_mapping(response.get("raw_evidence", {}), "SCM raw evidence"),
            evidence_class=getattr(self.transport, "evidence_class", "NOT_RUN"),
        )

    def compensate(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        token = operation.get("compensation_token")
        if not isinstance(token, str):
            return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "SCM_COMPENSATION_TOKEN_MISSING"})
        response = require_mapping(
            self.transport.invoke(
                {
                    "schema_version": "2.0.0",
                    "action": "compensate",
                    "provider_instance": operation["provider_instance"],
                    "native_repository_id": operation["native_resource_id"],
                    "compensation_token": token,
                    "idempotency_key": f"{operation['idempotency_key']}:compensate",
                }
            ),
            "SCM compensation response",
        )
        return AdapterOutcome(
            status=OutcomeStatus.SUCCEEDED if response.get("status") == "SUCCEEDED" else OutcomeStatus.UNKNOWN,
            result=require_mapping(response.get("result", {}), "SCM result"),
            raw_evidence=require_mapping(response.get("raw_evidence", {}), "SCM raw evidence"),
            evidence_class=getattr(self.transport, "evidence_class", "NOT_RUN"),
            side_effect_performed=True,
        )


class FileObjectStoreAdapter:
    """Content-addressed local object-store emulator with tenant isolation."""

    adapter_id = "filesystem-object-store"
    adapter_version = "2.0.0"
    capability = "object-store"

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant_id: str, key: str) -> Path:
        safe_key = relative_path(key, "payload.key")
        target = (self.root / relative_path(tenant_id, "tenant_id") / safe_key).resolve()
        tenant_root = (self.root / relative_path(tenant_id, "tenant_id")).resolve()
        if not target.is_relative_to(tenant_root):
            raise AuthorizationError("OBJECT_SCOPE_DENIED", "object key escapes tenant prefix")
        return target

    def execute(self, operation: Mapping[str, Any], payload: Mapping[str, Any]) -> AdapterOutcome:
        target = self._path(str(operation["tenant_id"]), require_string(payload.get("key"), "payload.key"))
        action = str(operation["action"])
        if action == "put":
            content_value = payload.get("content")
            if not isinstance(content_value, (str, bytes, bytearray)):
                raise ContractError("INVALID_INPUT", "payload.content must be bytes or text")
            content = content_value.encode("utf-8") if isinstance(content_value, str) else bytes(content_value)
            expected = payload.get("content_hash")
            if expected and expected != bytes_digest(content):
                raise ContractError("ARTIFACT_CORRUPT", "object content does not match declared hash")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            temporary.write_bytes(content)
            os.replace(temporary, target)
            observed = bytes_digest(target.read_bytes())
            return AdapterOutcome(
                status=OutcomeStatus.SUCCEEDED,
                result={"key": str(payload["key"]), "content_hash": observed, "size_bytes": len(content)},
                raw_evidence={"read_back_hash": observed, "storage": "filesystem-emulator"},
                evidence_class="EMULATOR_EXECUTED", side_effect_performed=True,
                compensation_token=str(payload["key"]),
            )
        if action in {"get", "head"}:
            if not target.is_file():
                return AdapterOutcome(status=OutcomeStatus.FAILED, error={"code": "OBJECT_NOT_FOUND"})
            content = target.read_bytes()
            result = {"key": str(payload["key"]), "content_hash": bytes_digest(content), "size_bytes": len(content)}
            if action == "get":
                result["content_returned"] = False
            return AdapterOutcome(
                status=OutcomeStatus.SUCCEEDED, result=result,
                raw_evidence={"read_back_hash": bytes_digest(content), "storage": "filesystem-emulator"},
                evidence_class="EMULATOR_EXECUTED",
            )
        if action == "delete":
            if payload.get("legal_hold") is True:
                return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "LEGAL_HOLD_ACTIVE"})
            target.unlink(missing_ok=True)
            return AdapterOutcome(
                status=OutcomeStatus.SUCCEEDED, result={"deleted": True, "key": str(payload["key"])},
                raw_evidence={"exists_after_delete": target.exists()}, evidence_class="EMULATOR_EXECUTED",
                side_effect_performed=True,
            )
        return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "OBJECT_ACTION_DENIED"})

    def reconcile(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        metadata = require_mapping(operation.get("request_metadata", {}), "operation.request_metadata")
        target = self._path(str(operation["tenant_id"]), require_string(metadata.get("key"), "request_metadata.key"))
        evidence = {"exists": target.exists()}
        if target.exists():
            evidence["read_back_hash"] = bytes_digest(target.read_bytes())
        return AdapterOutcome(
            status=OutcomeStatus.SUCCEEDED, result=evidence, raw_evidence=evidence,
            evidence_class="EMULATOR_EXECUTED",
        )

    def compensate(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        key = operation.get("compensation_token")
        if not isinstance(key, str):
            return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "COMPENSATION_TOKEN_MISSING"})
        target = self._path(str(operation["tenant_id"]), key)
        target.unlink(missing_ok=True)
        return AdapterOutcome(
            status=OutcomeStatus.SUCCEEDED, result={"deleted": True, "key": key},
            raw_evidence={"exists_after_delete": target.exists()}, evidence_class="EMULATOR_EXECUTED",
            side_effect_performed=True,
        )


@dataclass(slots=True)
class SecretLeaseHandle:
    lease: Mapping[str, Any]
    _material: bytearray
    _revoked: bool = False

    def reveal(self) -> bytes:
        if self._revoked or self.lease.get("state") != "ACTIVE" or _parse_timestamp(self.lease.get("expires_at"), "expires_at") <= datetime.now(UTC):
            raise AuthorizationError("SECRET_LEASE_EXPIRED", "secret lease is not active")
        return bytes(self._material)

    def zeroize(self) -> None:
        for index in range(len(self._material)):
            self._material[index] = 0
        self._revoked = True


@dataclass(frozen=True, slots=True)
class SecretResolution:
    material: bytes
    native_lease_id: str
    receipt: Mapping[str, Any]
    evidence_class: str = "EXTERNAL_EXECUTED"


class EphemeralSecretsBroker:
    """Lease secret references while keeping secret values out of durable state."""

    def __init__(
        self,
        store: DurableStore,
        broker_id: str,
        resolver: Callable[[str], bytes | SecretResolution],
        *,
        revoker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        receipt_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
    ) -> None:
        self.store = store
        self.broker_id = broker_id
        self.resolver = resolver
        self.revoker = revoker
        self.receipt_verifier = receipt_verifier
        self._handles: dict[str, SecretLeaseHandle] = {}

    def lease(
        self, *, tenant_id: str, secret_ref: str, scope: Mapping[str, Any], ttl_seconds: int = 60,
    ) -> SecretLeaseHandle:
        if ttl_seconds < 1 or ttl_seconds > 3600:
            raise ContractError("INVALID_INPUT", "secret lease ttl must be between 1 and 3600 seconds")
        resolved = self.resolver(secret_ref)
        if isinstance(resolved, SecretResolution):
            material = bytearray(resolved.material)
            receipt = _safe_request_metadata(resolved.receipt)
            evidence_class = resolved.evidence_class
            if evidence_class == "INDEPENDENTLY_VERIFIED" and (
                self.receipt_verifier is None or not self.receipt_verifier(receipt)
            ):
                evidence_class = "EXTERNAL_EXECUTED"
            native_lease_id = require_string(resolved.native_lease_id, "native_lease_id")
        else:
            material = bytearray(resolved)
            receipt = {"source": "local-resolver", "broker_id": self.broker_id}
            evidence_class = "LOCAL_ENGINEERING_VALIDATED"
            native_lease_id = None
        expires_at = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z")
        receipt_hash = digest(
            {
                "tenant_id": tenant_id,
                "secret_ref": secret_ref,
                "scope": scope,
                "expires_at": expires_at,
                "native_lease_id": native_lease_id,
                "receipt": receipt,
            }
        )
        lease = self.store.record_secret_lease(
            tenant_id=tenant_id, broker_id=self.broker_id, secret_ref=secret_ref, scope=scope,
            expires_at=expires_at, receipt_hash=receipt_hash, native_lease_id=native_lease_id,
            evidence_class=evidence_class,
        )
        handle = SecretLeaseHandle(lease=lease, _material=material)
        self._handles[str(lease["lease_id"])] = handle
        return handle

    def revoke(self, lease_id: str, *, tenant_id: str) -> dict[str, Any]:
        handle = self._handles.pop(lease_id, None)
        if handle is not None:
            handle.zeroize()
        if handle is None or self.revoker is None:
            return self.store.revoke_secret_lease(lease_id, tenant_id=tenant_id)
        try:
            response = require_mapping(self.revoker(handle.lease), "secret revoke response")
        except TimeoutError:
            response = {"status": "UNKNOWN", "error": {"code": "BROKER_REVOKE_TIMEOUT"}}
        state = "REVOKED" if response.get("status") == "SUCCEEDED" else "REVOKE_UNKNOWN"
        verified = self.receipt_verifier is not None and self.receipt_verifier(response)
        result = self.store.revoke_secret_lease(
            lease_id,
            tenant_id=tenant_id,
            state=state,
            revoke_receipt_hash=digest(_safe_request_metadata(response)),
        )
        return {
            **result,
            "external_evidence": (
                "INDEPENDENTLY_VERIFIED" if state == "REVOKED" and verified else "NOT_RUN"
            ),
        }


class S3Transport(Protocol):
    evidence_class: str

    def invoke(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class S3ObjectStoreAdapter:
    """S3 SPI with exact account/region/bucket binding and digest readback."""

    adapter_id = "aws-s3"
    adapter_version = "2.0.0"
    capability = "object-store"

    def __init__(self, transport: S3Transport) -> None:
        self.transport = transport

    def execute(self, operation: Mapping[str, Any], payload: Mapping[str, Any]) -> AdapterOutcome:
        key = relative_path(require_string(payload.get("key"), "payload.key"), "payload.key")
        bucket = require_string(operation.get("native_resource_id"), "native_resource_id")
        action = str(operation["action"])
        if action not in {"put", "get", "head", "delete"}:
            return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "S3_ACTION_DENIED"})
        acl = str(payload.get("acl", "private"))
        if acl != "private":
            raise AuthorizationError("S3_PUBLIC_ACCESS_DENIED", "only private object ACL is allowed")
        request = {
            "account_id": operation["account_id"],
            "region": operation["region"],
            "bucket": bucket,
            "key": key,
            "action": action,
            "idempotency_key": operation["idempotency_key"],
            "content_hash": payload.get("content_hash"),
            "secret_ref": payload.get("secret_ref"),
        }
        if action == "put":
            encryption = str(payload.get("server_side_encryption", ""))
            if encryption not in {"AES256", "aws:kms"}:
                raise AuthorizationError("S3_ENCRYPTION_REQUIRED", "server-side encryption must be explicit")
            if encryption == "aws:kms" and not payload.get("kms_key_ref"):
                raise AuthorizationError("S3_KMS_KEY_REQUIRED", "KMS encryption requires a scoped key reference")
            request["server_side_encryption"] = encryption
            request["kms_key_ref"] = payload.get("kms_key_ref")
            content = payload.get("content")
            if not isinstance(content, (str, bytes, bytearray)):
                raise ContractError("INVALID_INPUT", "payload.content must be bytes or text")
            raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
            observed = bytes_digest(raw)
            if payload.get("content_hash") not in {None, observed}:
                raise ContractError("ARTIFACT_CORRUPT", "object content does not match declared hash")
            request["content"] = raw
            request["content_hash"] = observed
        if action == "delete":
            retention = require_mapping(
                self.transport.invoke({**request, "action": "retention-status"}), "S3 retention response"
            )
            retention_result = require_mapping(retention.get("result", {}), "S3 retention response.result")
            if retention.get("status") != "SUCCEEDED" or retention_result.get("legal_hold") is not False:
                return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "S3_LEGAL_HOLD_OR_UNKNOWN"})
            if retention_result.get("retention_active") is not False:
                return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "S3_RETENTION_ACTIVE_OR_UNKNOWN"})
        response = require_mapping(self.transport.invoke(request), "S3 response")
        status = str(response.get("status", "UNKNOWN")).upper()
        mapped = {
            "SUCCEEDED": OutcomeStatus.SUCCEEDED,
            "FAILED": OutcomeStatus.FAILED,
            "DENIED": OutcomeStatus.DENIED,
            "UNKNOWN": OutcomeStatus.UNKNOWN,
        }.get(status, OutcomeStatus.UNKNOWN)
        result = require_mapping(response.get("result", {}), "S3 response.result")
        if mapped == OutcomeStatus.SUCCEEDED and action in {"put", "get", "head"}:
            expected = request.get("content_hash") or result.get("content_hash")
            if not expected or result.get("read_back_hash") != expected:
                raise ContractError("ARTIFACT_CORRUPT", "S3 readback digest is missing or mismatched")
        return AdapterOutcome(
            status=mapped,
            result={key: value for key, value in result.items() if key != "content"},
            raw_evidence=require_mapping(response.get("raw_evidence", {}), "S3 response.raw_evidence"),
            evidence_class=getattr(self.transport, "evidence_class", "NOT_RUN"),
            native_operation_id=str(response["native_operation_id"]) if response.get("native_operation_id") else None,
            side_effect_performed=bool(response.get("side_effect_performed", False)),
            compensation_token=key if mapped == OutcomeStatus.SUCCEEDED and action == "put" else None,
            error=require_mapping(response.get("error", {}), "S3 response.error") if response.get("error") else None,
        )

    def reconcile(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        response = require_mapping(
            self.transport.invoke(
                {
                    "action": "reconcile",
                    "account_id": operation["account_id"],
                    "region": operation["region"],
                    "bucket": operation["native_resource_id"],
                    "idempotency_key": operation["idempotency_key"],
                }
            ),
            "S3 reconciliation response",
        )
        return AdapterOutcome(
            status=OutcomeStatus.SUCCEEDED if response.get("status") == "SUCCEEDED" else OutcomeStatus.UNKNOWN,
            result=require_mapping(response.get("result", {}), "result"),
            raw_evidence=require_mapping(response.get("raw_evidence", {}), "raw_evidence"),
            evidence_class=getattr(self.transport, "evidence_class", "NOT_RUN"),
        )

    def compensate(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        token = operation.get("compensation_token")
        if not isinstance(token, str):
            return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "COMPENSATION_TOKEN_MISSING"})
        retention = require_mapping(
            self.transport.invoke(
                {
                    "action": "retention-status",
                    "account_id": operation["account_id"],
                    "region": operation["region"],
                    "bucket": operation["native_resource_id"],
                    "key": token,
                    "idempotency_key": f"{operation['idempotency_key']}:retention-check",
                }
            ),
            "S3 retention response",
        )
        retention_result = require_mapping(retention.get("result", {}), "S3 retention response.result")
        if (
            retention.get("status") != "SUCCEEDED"
            or retention_result.get("legal_hold") is not False
            or retention_result.get("retention_active") is not False
        ):
            return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "S3_RETENTION_OR_HOLD_UNKNOWN"})
        response = require_mapping(
            self.transport.invoke(
                {
                    "action": "delete",
                    "account_id": operation["account_id"],
                    "region": operation["region"],
                    "bucket": operation["native_resource_id"],
                    "key": token,
                    "idempotency_key": f"{operation['idempotency_key']}:compensate",
                }
            ),
            "S3 compensation response",
        )
        return AdapterOutcome(
            status=OutcomeStatus.SUCCEEDED if response.get("status") == "SUCCEEDED" else OutcomeStatus.UNKNOWN,
            result=require_mapping(response.get("result", {}), "result"),
            raw_evidence=require_mapping(response.get("raw_evidence", {}), "raw_evidence"),
            evidence_class=getattr(self.transport, "evidence_class", "NOT_RUN"),
            side_effect_performed=True,
        )


@dataclass(slots=True)
class PresignedRequestHandle:
    url: str
    expires_at: str
    method: str
    request_hash: str
    evidence: Mapping[str, Any]

    def reveal(self) -> str:
        if _parse_timestamp(self.expires_at, "expires_at") <= datetime.now(UTC):
            raise AuthorizationError("SIGNED_REQUEST_EXPIRED", "presigned request has expired")
        return self.url


class S3PresignService:
    """Issue short-lived method/hash-bound URLs without persisting URL secrets."""

    def __init__(self, transport: S3Transport) -> None:
        self.transport = transport

    def issue(
        self, *, tenant_id: str, account_id: str, region: str, bucket: str,
        key: str, method: str, ttl_seconds: int, content_hash: str | None = None,
    ) -> PresignedRequestHandle:
        safe_key = relative_path(key, "key")
        tenant_prefix = relative_path(tenant_id, "tenant_id") + "/"
        if not safe_key.startswith(tenant_prefix):
            raise AuthorizationError("S3_TENANT_PREFIX_DENIED", "object key is outside the tenant prefix")
        normalized_method = method.upper()
        if normalized_method not in {"GET", "PUT"}:
            raise ContractError("SIGNED_REQUEST_METHOD_INVALID", "only GET and PUT may be presigned")
        if ttl_seconds < 1 or ttl_seconds > 900:
            raise ContractError("SIGNED_REQUEST_TTL_INVALID", "presigned request TTL must be 1-900 seconds")
        if normalized_method == "PUT" and not content_hash:
            raise ContractError("SIGNED_REQUEST_HASH_REQUIRED", "presigned PUT requires an exact content hash")
        if content_hash is not None:
            require_sha256_digest(content_hash, "content_hash")
        request = {
            "action": "presign",
            "tenant_id": tenant_id,
            "account_id": account_id,
            "region": region,
            "bucket": bucket,
            "key": safe_key,
            "method": normalized_method,
            "ttl_seconds": ttl_seconds,
            "content_hash": content_hash,
            "acl": "private",
        }
        response = require_mapping(self.transport.invoke(request), "S3 presign response")
        result = require_mapping(response.get("result", {}), "S3 presign response.result")
        if response.get("status") != "SUCCEEDED":
            raise ContractError("SIGNED_REQUEST_FAILED", "object store did not issue a signed request")
        url = require_string(result.get("url"), "S3 presign response.result.url")
        expires_at = require_string(result.get("expires_at"), "S3 presign response.result.expires_at")
        if _parse_timestamp(expires_at, "expires_at") <= datetime.now(UTC):
            raise ContractError("SIGNED_REQUEST_EXPIRED", "object store returned an expired request")
        return PresignedRequestHandle(
            url=url,
            expires_at=expires_at,
            method=normalized_method,
            request_hash=digest(request),
            evidence={
                "request_hash": digest(request),
                "provider_request_id": response.get("native_operation_id"),
                "evidence_class": getattr(self.transport, "evidence_class", "NOT_RUN"),
                "url_persisted": False,
            },
        )
class EventBusTransport(Protocol):
    evidence_class: str

    def publish(self, event: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def reconcile(self, event: Mapping[str, Any]) -> Mapping[str, Any]: ...


class DurableEventPublisher:
    """Transactional-outbox publisher with explicit uncertain-outcome recovery."""

    def __init__(
        self,
        store: DurableStore,
        transport: EventBusTransport,
        *,
        receipt_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
    ) -> None:
        self.store = store
        self.transport = transport
        self.receipt_verifier = receipt_verifier

    def publish_pending(self, *, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for event in self.store.claim_outbox(tenant_id=tenant_id, limit=limit):
            try:
                outcome = require_mapping(self.transport.publish(event), "event bus response")
                status = str(outcome.get("status", "UNKNOWN")).upper()
            except TimeoutError:
                outcome, status = {}, "UNKNOWN"
            target = {
                "SUCCEEDED": "PUBLISHED",
                "PUBLISHED": "PUBLISHED",
                "FAILED": "RETRY",
                "DENIED": "DEAD_LETTER",
                "UNKNOWN": "UNKNOWN",
            }.get(status, "UNKNOWN")
            updated = self.store.complete_outbox(str(event["event_id"]), tenant_id=tenant_id, outcome=target)
            declared_class = getattr(self.transport, "evidence_class", "NOT_RUN")
            evidence_class = "EXTERNAL_EXECUTED" if declared_class in EXTERNAL_EVIDENCE_CLASSES else declared_class
            receipt = self.store.record_outbox_receipt(
                event_id=str(event["event_id"]),
                tenant_id=tenant_id,
                status=target,
                producer_id=str(outcome.get("producer_id", "event-bus-transport")),
                verifier_id=None,
                evidence_class=evidence_class,
                raw_evidence=_safe_request_metadata(outcome),
            )
            results.append(
                {
                    **updated,
                    "receipt": receipt,
                    "external_evidence": (
                        "EXTERNAL_EXECUTED"
                        if target == "PUBLISHED" and evidence_class == "EXTERNAL_EXECUTED"
                        else "NOT_RUN"
                    ),
                }
            )
        return results

    def reconcile_unknown(self, event_id: str, *, tenant_id: str) -> dict[str, Any]:
        event = self.store.get_outbox_event(event_id, tenant_id=tenant_id)
        if event is None:
            raise ContractError("EVENT_NOT_FOUND", "outbox event is not visible in the requested tenant")
        if event["state"] != "UNKNOWN":
            raise StaleStateError("EVENT_STATE_CONFLICT", "event is not awaiting reconciliation")
        response = require_mapping(self.transport.reconcile(event), "event bus reconciliation response")
        status = str(response.get("status", "UNKNOWN")).upper()
        published = True if status in {"SUCCEEDED", "PUBLISHED"} else False if status == "NOT_PUBLISHED" else None
        updated = self.store.reconcile_outbox(event_id, tenant_id=tenant_id, published=published)
        independently_verified = (
            getattr(self.transport, "evidence_class", "NOT_RUN") == "INDEPENDENTLY_VERIFIED"
            and bool(response.get("raw_evidence"))
            and response.get("producer_id") != response.get("verifier_id")
            and self.receipt_verifier is not None
            and self.receipt_verifier(response)
        )
        evidence_class = "INDEPENDENTLY_VERIFIED" if independently_verified else (
            "EXTERNAL_EXECUTED"
            if getattr(self.transport, "evidence_class", "NOT_RUN") in EXTERNAL_EVIDENCE_CLASSES
            else getattr(self.transport, "evidence_class", "NOT_RUN")
        )
        receipt = self.store.record_outbox_receipt(
            event_id=event_id,
            tenant_id=tenant_id,
            status=updated["state"],
            producer_id=str(response.get("producer_id", "event-bus-transport")),
            verifier_id=str(response.get("verifier_id")) if response.get("verifier_id") else None,
            evidence_class=evidence_class,
            raw_evidence=_safe_request_metadata(response),
        )
        return {
            **updated,
            "receipt": receipt,
            "external_evidence": "INDEPENDENTLY_VERIFIED" if independently_verified else "NOT_RUN",
        }


class IdempotentEventConsumer:
    """Inbox consumer that never repeats an uncertain side effect."""

    def __init__(self, store: DurableStore, consumer_id: str) -> None:
        self.store = store
        self.consumer_id = require_string(consumer_id, "consumer_id")

    def consume(
        self, *, tenant_id: str, event: Mapping[str, Any],
        handler: Callable[[Mapping[str, Any]], Mapping[str, Any]], side_effects: bool,
    ) -> dict[str, Any]:
        event_id = require_string(event.get("event_id"), "event.event_id")
        ordering_key = require_string(event.get("ordering_key"), "event.ordering_key")
        payload = require_mapping(event.get("payload", {}), "event.payload")
        record = self.store.begin_inbox_event(
            tenant_id=tenant_id,
            consumer_id=self.consumer_id,
            event_id=event_id,
            payload=payload,
            ordering_key=ordering_key,
            side_effects=side_effects,
        )
        if record.get("replayed"):
            return record
        try:
            result = require_mapping(handler(payload), "event handler result")
        except TimeoutError:
            return self.store.complete_inbox_event(
                tenant_id=tenant_id,
                consumer_id=self.consumer_id,
                event_id=event_id,
                state="UNKNOWN" if side_effects else "RETRY",
                error={"code": "EVENT_HANDLER_TIMEOUT"},
            )
        except Exception as exc:  # noqa: BLE001 - handler failures become durable outcomes
            return self.store.complete_inbox_event(
                tenant_id=tenant_id,
                consumer_id=self.consumer_id,
                event_id=event_id,
                state="UNKNOWN" if side_effects else "DEAD_LETTER",
                error={"code": "EVENT_HANDLER_FAILED", "type": type(exc).__name__},
            )
        return self.store.complete_inbox_event(
            tenant_id=tenant_id,
            consumer_id=self.consumer_id,
            event_id=event_id,
            state="PROCESSED",
            result=result,
        )

    def reconcile(
        self, *, tenant_id: str, event_id: str, processed: bool | None,
        evidence: Mapping[str, Any], verifier: Callable[[Mapping[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        if processed is not None and (verifier is None or not verifier(evidence)):
            raise AuthorizationError(
                "EVENT_RECONCILIATION_EVIDENCE_DENIED",
                "a trusted receipt is required to resolve an uncertain consumer side effect",
            )
        return self.store.reconcile_inbox_event(
            tenant_id=tenant_id,
            consumer_id=self.consumer_id,
            event_id=event_id,
            processed=processed,
            evidence=_safe_request_metadata(evidence),
        )


class ProviderTransport(Protocol):
    evidence_class: str

    def invoke(self, adapter_id: str, envelope: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    adapter_id: str
    adapter_type: str
    protocol: str
    required_capabilities: tuple[str, ...]
    supports_stream_resume: bool
    supports_safe_cancel: bool


PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    "anthropic-agent-sdk": ProviderProfile("anthropic-agent-sdk", "agent-sdk", "python-sdk", ("tools", "stream", "usage"), True, True),
    "claude-code": ProviderProfile("claude-code", "terminal-agent", "json-lines-cli", ("tools", "interrupt", "usage"), True, True),
    "generic-mcp-a2a": ProviderProfile("generic-mcp-a2a", "protocol", "json-rpc-2.0", ("tools", "tasks", "cancellation"), True, True),
    "openai-codex": ProviderProfile("openai-codex", "coding-agent", "task-runtime", ("tools", "stream", "usage"), True, True),
    "opencode": ProviderProfile("opencode", "coding-agent", "json-lines-cli", ("tools", "interrupt", "usage"), True, True),
    "openharness": ProviderProfile("openharness", "harness", "harness-rpc", ("tools", "checkpoints", "usage"), True, True),
    "openrouter": ProviderProfile("openrouter", "model-router", "http-json", ("stream", "usage", "routing"), True, True),
}


class CanonicalProviderAdapter:
    capability = "provider"

    def __init__(self, profile: ProviderProfile, transport: ProviderTransport, *, version: str) -> None:
        self.profile = profile
        self.transport = transport
        self.adapter_id = profile.adapter_id
        self.adapter_version = version

    def execute(self, operation: Mapping[str, Any], payload: Mapping[str, Any]) -> AdapterOutcome:
        envelope = {
            "schema_version": "2.0.0",
            "request_id": operation["idempotency_key"],
            "operation": operation["action"],
            "provider_instance": operation["provider_instance"],
            "region": operation["region"],
            "input": payload,
            "authority": {"source": "kernel", "digest": operation.get("authority_hash")},
            "required_capabilities": list(self.profile.required_capabilities),
        }
        response = require_mapping(self.transport.invoke(self.adapter_id, envelope), "provider response")
        status = str(response.get("status", "UNKNOWN")).upper()
        mapped = {
            "PASS": OutcomeStatus.SUCCEEDED,
            "SUCCEEDED": OutcomeStatus.SUCCEEDED,
            "FAILED": OutcomeStatus.FAILED,
            "DENIED": OutcomeStatus.DENIED,
            "CANCELLED": OutcomeStatus.CANCELLED,
            "NOT_RUN": OutcomeStatus.NOT_RUN,
            "UNKNOWN": OutcomeStatus.UNKNOWN,
            "TIMEOUT": OutcomeStatus.UNKNOWN if operation["side_effects"] else OutcomeStatus.FAILED,
        }.get(status, OutcomeStatus.UNKNOWN)
        evidence_class = getattr(self.transport, "evidence_class", "NOT_RUN")
        return AdapterOutcome(
            status=mapped,
            result=require_mapping(response.get("result", {}), "provider response.result"),
            raw_evidence=require_mapping(response.get("raw_evidence", {}), "provider response.raw_evidence"),
            evidence_class=evidence_class,
            native_operation_id=str(response["native_operation_id"]) if response.get("native_operation_id") else None,
            side_effect_performed=bool(response.get("side_effect_performed", False)),
            retryable=bool(response.get("retryable", False)),
            compensation_token=str(response["compensation_token"]) if response.get("compensation_token") else None,
            error=require_mapping(response.get("error", {}), "provider response.error") if response.get("error") else None,
        )

    def reconcile(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        response = require_mapping(
            self.transport.invoke(self.adapter_id, {"schema_version": "2.0.0", "operation": "reconcile", "native_operation_id": operation.get("result", {}).get("native_operation_id") if isinstance(operation.get("result"), Mapping) else None, "request_id": operation["idempotency_key"]}),
            "provider reconciliation response",
        )
        status = OutcomeStatus.SUCCEEDED if str(response.get("status", "UNKNOWN")).upper() in {"PASS", "SUCCEEDED"} else OutcomeStatus.UNKNOWN
        return AdapterOutcome(
            status=status, result=require_mapping(response.get("result", {}), "result"),
            raw_evidence=require_mapping(response.get("raw_evidence", {}), "raw_evidence"),
            evidence_class=getattr(self.transport, "evidence_class", "NOT_RUN"),
        )

    def compensate(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        response = require_mapping(
            self.transport.invoke(self.adapter_id, {"schema_version": "2.0.0", "operation": "compensate", "compensation_token": operation.get("compensation_token"), "request_id": operation["idempotency_key"]}),
            "provider compensation response",
        )
        status = OutcomeStatus.SUCCEEDED if str(response.get("status", "UNKNOWN")).upper() in {"PASS", "SUCCEEDED"} else OutcomeStatus.UNKNOWN
        return AdapterOutcome(
            status=status, result=require_mapping(response.get("result", {}), "result"),
            raw_evidence=require_mapping(response.get("raw_evidence", {}), "raw_evidence"),
            evidence_class=getattr(self.transport, "evidence_class", "NOT_RUN"), side_effect_performed=True,
        )


def provider_adapters(transport: ProviderTransport, *, version: str = "2.0.0") -> tuple[CanonicalProviderAdapter, ...]:
    return tuple(CanonicalProviderAdapter(profile, transport, version=version) for profile in PROVIDER_PROFILES.values())
