"""Exact host continuation runtime for Autonomous QA Skills.

The local handlers always run first.  When a handler returns ``PARTIAL`` or
``BLOCKED`` because it needs a runner, SCM, durable store, publisher, signer,
or other trusted service, this module provides the repository-owned continuation
boundary.  It never supplies a default provider or treats a provider receipt as
independent evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from types import MappingProxyType
from typing import Any, Protocol

from .contracts import ContractError, RuntimeRequest, digest_json, require_resource_id, strict_json


class HostRuntimeError(ContractError):
    """Raised when a host continuation is missing, stale, or unreconciled."""


PACKAGE_ID = "elmos-autonomous-qa-self-healing-skills-v1.1.0"
SOURCE_ARCHIVE_DIGEST = (
    "sha256:07928b59925c80b1b158cce42e729ee97510172676989badf7dd656971a56ae2"
)


@dataclass(frozen=True)
class HostContinuationBinding:
    source_id: str
    capability: str
    adapter_id: str
    route_id: str
    route_digest: str
    operation_id: str
    phase: str
    mutating: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "capability": self.capability,
            "adapter_id": self.adapter_id,
            "route_id": self.route_id,
            "route_digest": self.route_digest,
            "operation_id": self.operation_id,
            "phase": self.phase,
            "mutating": self.mutating,
        }


@dataclass(frozen=True)
class HostExecutionLease:
    lease_id: str
    tenant_id: str
    project_id: str
    actor_id: str
    environment_id: str
    workspace_id: str
    revision_id: str
    purpose: str
    invocation_id: str
    capability: str
    expires_at: str
    revoked: bool = False

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> "HostExecutionLease":
        if not isinstance(value, Mapping):
            raise HostRuntimeError("host lease must be an object")
        expected = {
            "lease_id", "tenant_id", "project_id", "actor_id", "environment_id",
            "workspace_id", "revision_id", "purpose", "invocation_id", "capability",
            "expires_at", "revoked",
        }
        if set(value) != expected:
            raise HostRuntimeError("host lease fields are incomplete or unsupported")
        identities = {
            key: require_resource_id(value[key], f"lease.{key}")
            for key in expected - {"expires_at", "revoked"}
        }
        expires_at = value["expires_at"]
        if not isinstance(expires_at, str):
            raise HostRuntimeError("lease.expires_at must be an RFC3339 timestamp")
        try:
            instant = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HostRuntimeError("lease.expires_at must be an RFC3339 timestamp") from exc
        if instant.tzinfo is None:
            raise HostRuntimeError("lease.expires_at must include a timezone")
        revoked = value["revoked"]
        if not isinstance(revoked, bool):
            raise HostRuntimeError("lease.revoked must be boolean")
        return cls(**identities, expires_at=expires_at, revoked=revoked)

    def assert_active(self, *, now: datetime) -> None:
        expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        if now.tzinfo is None:
            raise HostRuntimeError("host clock must be timezone-aware")
        if self.revoked:
            raise HostRuntimeError("host capability lease is revoked")
        if expiry <= now:
            raise HostRuntimeError("host capability lease is expired")


class QaHostProvider(Protocol):
    provider_id: str

    def execute(self, envelope: Mapping[str, Any]) -> Mapping[str, Any]:
        """Perform one exact host operation and return its provider receipt."""


PermitVerifier = Callable[[Mapping[str, Any], HostExecutionLease, HostContinuationBinding], bool]
ReceiptVerifier = Callable[[Mapping[str, Any], HostExecutionLease, HostContinuationBinding], bool]


# These are the exact Skills whose reviewed local fixture does not reach a
# terminal semantic result without a trusted continuation.  The identity is
# explicit and versioned; no phase-level generic fallback is permitted.
_HOST_CAPABILITIES = MappingProxyType(
    {
        "00-qa-control-plane": "durable-control-plane",
        "01-project-context-ingestion": "trusted-project-snapshot",
        "05-test-model-dsl": "native-test-emission",
        "06-functional-test-generation": "native-functional-execution",
        "07-api-contract-testing": "api-contract-execution",
        "08-data-database-testing": "database-test-execution",
        "09-message-workflow-testing": "message-workflow-execution",
        "10-ui-e2e-testing": "browser-journey-execution",
        "11-visual-responsive-testing": "browser-visual-execution",
        "12-accessibility-compatibility-testing": "accessibility-runtime-execution",
        "13-performance-baseline-testing": "performance-runner-execution",
        "14-load-stress-spike-soak-testing": "load-runner-execution",
        "15-security-abuse-testing": "security-runner-execution",
        "16-resilience-chaos-recovery-testing": "chaos-runner-execution",
        "17-test-data-management": "trusted-test-data-materialization",
        "18-environment-orchestration": "environment-provider-execution",
        "19-distributed-test-execution": "distributed-runner-execution",
        "20-test-oracle-evidence": "trusted-evidence-attestation",
        "21-flaky-test-control": "isolated-rerun-execution",
        "22-defect-triage-rca": "trusted-reproduction-execution",
        "24-safe-code-auto-fix": "sandboxed-patch-execution",
        "25-test-self-healing": "sandboxed-test-heal-execution",
        "26-impact-analysis-regression": "trusted-graph-resolution",
        "27-mutation-property-fuzz-testing": "native-advanced-test-execution",
        "28-quality-gate-release-certification": "independent-release-verification",
        "30-checkpoint-resume-idempotency": "durable-checkpoint-store",
        "31-runtime-cost-eta": "observed-cost-reconciliation",
        "33-ci-cd-pr-integration": "scm-provider-execution",
        "34-continuous-learning-knowledge-base": "governed-knowledge-publication",
        "35-governance-approval-audit": "trusted-approval-resolution",
        "36-project-output-contract": "project-output-preflight",
        "37-test-source-materialization": "native-toolchain-validation",
        "38-project-output-bundle-publishing": "trusted-artifact-publication",
        "39-output-versioning-retention": "trusted-lifecycle-execution",
    }
)

LOCAL_TERMINAL_SOURCE_IDS = frozenset(
    {
        "02-spec-normalization",
        "03-requirement-traceability-graph",
        "04-risk-coverage-planning",
        "23-repair-planning",
        "29-reporting-observability",
        "32-multilanguage-adapter-sdk",
    }
)


def exact_host_continuation(
    *, source_id: str, operation_id: str, phase: str, mutating: bool
) -> HostContinuationBinding:
    try:
        capability = _HOST_CAPABILITIES[source_id]
    except KeyError as exc:
        raise HostRuntimeError(f"Skill has no host continuation: {source_id}") from exc
    adapter_id = f"elmos.qa.{source_id}.host-v1"
    route_id = f"qa-host:{source_id}:v1"
    seed = {
        "schema_version": "elmos.autonomous-qa.host-route.v1",
        "package_id": PACKAGE_ID,
        "source_archive_digest": SOURCE_ARCHIVE_DIGEST,
        "source_id": source_id,
        "operation_id": operation_id,
        "phase": phase,
        "mutating": mutating,
        "capability": capability,
        "adapter_id": adapter_id,
        "route_id": route_id,
    }
    return HostContinuationBinding(
        source_id=source_id,
        capability=capability,
        adapter_id=adapter_id,
        route_id=route_id,
        route_digest=digest_json(seed),
        operation_id=operation_id,
        phase=phase,
        mutating=mutating,
    )


def build_host_route_registry(bindings: Mapping[str, Any]) -> Mapping[str, HostContinuationBinding]:
    source_rows = {binding.source_id: binding for binding in bindings.values()}
    if set(source_rows) != set(_HOST_CAPABILITIES) | set(LOCAL_TERMINAL_SOURCE_IDS):
        raise HostRuntimeError("host/local coverage does not match the exact forty-Skill registry")
    routes = {
        source_id: exact_host_continuation(
            source_id=source_id,
            operation_id=source_rows[source_id].operation_id,
            phase=source_rows[source_id].phase,
            mutating=source_rows[source_id].mutating,
        )
        for source_id in _HOST_CAPABILITIES
    }
    if len(routes) != 34 or len(source_rows) != 40:
        raise HostRuntimeError("Autonomous QA runtime requires 34 host routes and 40 programs")
    return MappingProxyType(dict(sorted(routes.items())))


class SQLiteHostOperationStore:
    """Durable idempotency and unknown-result journal for host continuations."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_absolute():
            raise HostRuntimeError("host operation database path must be absolute")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS qa_host_operations (
                    tenant_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    route_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    result_json TEXT,
                    PRIMARY KEY (tenant_id, project_id, source_id, idempotency_key)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def claim(
        self, *, lease: HostExecutionLease, binding: HostContinuationBinding,
        idempotency_key: str, request_digest: str,
    ) -> tuple[str, int, Mapping[str, Any] | None]:
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT request_digest, route_digest, state, attempt, result_json
                   FROM qa_host_operations
                   WHERE tenant_id=? AND project_id=? AND source_id=? AND idempotency_key=?""",
                (lease.tenant_id, lease.project_id, binding.source_id, idempotency_key),
            ).fetchone()
            if row is not None:
                if row["request_digest"] != request_digest or row["route_digest"] != binding.route_digest:
                    db.execute("ROLLBACK")
                    raise HostRuntimeError("idempotency key is bound to a different request or route")
                if row["state"] == "SUCCEEDED":
                    result = json.loads(row["result_json"])
                    db.execute("COMMIT")
                    return "REPLAY", int(row["attempt"]), result
                if row["state"] in {"IN_FLIGHT", "UNKNOWN"}:
                    db.execute("ROLLBACK")
                    raise HostRuntimeError("host operation requires explicit reconciliation")
                attempt = int(row["attempt"]) + 1
                db.execute(
                    """UPDATE qa_host_operations SET state='IN_FLIGHT', attempt=?, result_json=NULL
                       WHERE tenant_id=? AND project_id=? AND source_id=? AND idempotency_key=?""",
                    (attempt, lease.tenant_id, lease.project_id, binding.source_id, idempotency_key),
                )
            else:
                attempt = 1
                db.execute(
                    """INSERT INTO qa_host_operations
                       (tenant_id, project_id, source_id, idempotency_key, request_digest,
                        route_digest, state, attempt, result_json)
                       VALUES (?, ?, ?, ?, ?, ?, 'IN_FLIGHT', 1, NULL)""",
                    (lease.tenant_id, lease.project_id, binding.source_id, idempotency_key,
                     request_digest, binding.route_digest),
                )
            db.execute("COMMIT")
            return "CLAIMED", attempt, None

    def finish(
        self, *, lease: HostExecutionLease, binding: HostContinuationBinding,
        idempotency_key: str, state: str, result: Mapping[str, Any] | None,
    ) -> None:
        if state not in {"SUCCEEDED", "FAILED", "UNKNOWN"}:
            raise HostRuntimeError("invalid durable host operation state")
        encoded = None if result is None else json.dumps(
            strict_json(result, "host result", output=True),
            ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        with closing(self._connect()) as db:
            changed = db.execute(
                """UPDATE qa_host_operations SET state=?, result_json=?
                   WHERE tenant_id=? AND project_id=? AND source_id=? AND idempotency_key=?
                     AND state='IN_FLIGHT'""",
                (state, encoded, lease.tenant_id, lease.project_id, binding.source_id, idempotency_key),
            ).rowcount
            if changed != 1:
                raise HostRuntimeError("host operation state changed concurrently")

    def reconcile(
        self, *, lease: HostExecutionLease, binding: HostContinuationBinding,
        idempotency_key: str, result: Mapping[str, Any], receipt_verifier: ReceiptVerifier,
    ) -> None:
        normalized = strict_json(result, "reconciled result", output=True)
        if (
            not isinstance(normalized, Mapping)
            or normalized.get("state") != "SUCCEEDED"
            or normalized.get("route_digest") != binding.route_digest
            or not receipt_verifier(normalized, lease, binding)
        ):
            raise HostRuntimeError("reconciliation receipt is not trusted")
        encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with closing(self._connect()) as db:
            row = db.execute(
                """SELECT request_digest FROM qa_host_operations
                   WHERE tenant_id=? AND project_id=? AND source_id=? AND idempotency_key=?
                     AND state='UNKNOWN'""",
                (lease.tenant_id, lease.project_id, binding.source_id, idempotency_key),
            ).fetchone()
            if row is None or normalized.get("request_digest") != row["request_digest"]:
                raise HostRuntimeError("reconciliation receipt is bound to a different request")
            changed = db.execute(
                """UPDATE qa_host_operations SET state='SUCCEEDED', result_json=?
                   WHERE tenant_id=? AND project_id=? AND source_id=? AND idempotency_key=?
                     AND state='UNKNOWN'""",
                (encoded, lease.tenant_id, lease.project_id, binding.source_id, idempotency_key),
            ).rowcount
            if changed != 1:
                raise HostRuntimeError("only an unknown operation may be reconciled")


class QaHostBroker:
    """Execute exact host continuations through injected trusted collaborators."""

    def __init__(
        self, *, routes: Mapping[str, HostContinuationBinding],
        store: SQLiteHostOperationStore, permit_verifier: PermitVerifier,
        receipt_verifier: ReceiptVerifier, now: Callable[[], datetime] | None = None,
    ) -> None:
        if set(routes) != set(_HOST_CAPABILITIES):
            raise HostRuntimeError("broker requires the complete exact host route registry")
        self.routes = routes
        self.store = store
        self.permit_verifier = permit_verifier
        self.receipt_verifier = receipt_verifier
        self.now = now or (lambda: datetime.now(timezone.utc))

    def execute(
        self, *, source_id: str, request: RuntimeRequest, lease: HostExecutionLease,
        permit: Mapping[str, Any], provider: QaHostProvider,
    ) -> Mapping[str, Any]:
        try:
            binding = self.routes[source_id]
        except KeyError as exc:
            raise HostRuntimeError(f"unknown host route: {source_id}") from exc
        lease.assert_active(now=self.now())
        if request.actor_id is None or request.idempotency_key is None:
            raise HostRuntimeError("host continuation requires actor and idempotency identities")
        if (
            lease.tenant_id != request.tenant_id
            or lease.project_id != request.project_id
            or lease.actor_id != request.actor_id
            or lease.invocation_id != request.request_id
            or lease.capability != binding.capability
        ):
            raise HostRuntimeError("host lease scope does not match the exact request and route")
        normalized_permit = strict_json(permit, "host permit")
        if not isinstance(normalized_permit, Mapping) or not self.permit_verifier(
            normalized_permit, lease, binding
        ):
            raise HostRuntimeError("host permit verification failed")
        request_document = {
            "schema_version": "elmos.autonomous-qa.host-envelope.v1",
            "source_id": source_id,
            "route": binding.as_dict(),
            "lease": lease.__dict__,
            "permit": normalized_permit,
            "request": {
                "request_id": request.request_id,
                "tenant_id": request.tenant_id,
                "project_id": request.project_id,
                "actor_id": request.actor_id,
                "idempotency_key": request.idempotency_key,
                "trace_id": request.trace_id,
                "inputs": request.inputs,
            },
        }
        request_digest = digest_json(request_document)
        action, attempt, replay = self.store.claim(
            lease=lease, binding=binding, idempotency_key=request.idempotency_key,
            request_digest=request_digest,
        )
        if action == "REPLAY":
            assert replay is not None
            return replay
        envelope = {**request_document, "request_digest": request_digest, "attempt": attempt}
        try:
            raw = provider.execute(envelope)
            result = strict_json(raw, "host provider receipt", output=True)
            if not isinstance(result, Mapping) or not self.receipt_verifier(result, lease, binding):
                raise HostRuntimeError("host provider receipt verification failed")
            if result.get("request_digest") != request_digest:
                raise HostRuntimeError("host provider receipt is bound to a different request")
            if result.get("route_digest") != binding.route_digest:
                raise HostRuntimeError("host provider receipt is bound to a different route")
            if result.get("state") != "SUCCEEDED":
                raise HostRuntimeError("host provider did not report a terminal success")
        except Exception:
            self.store.finish(
                lease=lease, binding=binding, idempotency_key=request.idempotency_key,
                state="UNKNOWN", result=None,
            )
            raise
        self.store.finish(
            lease=lease, binding=binding, idempotency_key=request.idempotency_key,
            state="SUCCEEDED", result=result,
        )
        return result


def host_runtime_coverage(bindings: Mapping[str, Any]) -> dict[str, Any]:
    routes = build_host_route_registry(bindings)
    return {
        "exact_native_programs": len(bindings),
        "local_terminal_programs": len(LOCAL_TERMINAL_SOURCE_IDS),
        "host_route_bound": len(routes),
        "prepare_only": 0,
        "code_binding_coverage_percent": 100,
        "whole_skills_complete": 0,
        "host_routes_digest": digest_json([routes[key].as_dict() for key in routes]),
    }


__all__ = [
    "HostContinuationBinding", "HostExecutionLease", "HostRuntimeError",
    "LOCAL_TERMINAL_SOURCE_IDS", "QaHostBroker", "QaHostProvider",
    "SQLiteHostOperationStore", "build_host_route_registry",
    "exact_host_continuation", "host_runtime_coverage",
]
