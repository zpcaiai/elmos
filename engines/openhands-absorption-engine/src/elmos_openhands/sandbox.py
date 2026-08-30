"""Production sandbox lifecycle, secret leases and isolation backends."""

from __future__ import annotations

import base64
import ipaddress
import json
import sqlite3
import subprocess
import threading
import time
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from .errors import ContractViolation, IdempotencyConflict, LeaseLost, NotConfigured, TenantIsolationError
from .models import Identity, canonical_json, digest_of, new_id
from .workspace import IsolationClass


@dataclass(frozen=True, slots=True)
class SandboxQuotas:
    cpu_cores: float = 1.0
    memory_mb: int = 1024
    disk_mb: int = 2048
    pid_limit: int = 256
    wall_seconds: float = 900.0
    output_bytes: int = 10_485_760

    def __post_init__(self) -> None:
        if self.cpu_cores <= 0 or min(self.memory_mb, self.disk_mb, self.pid_limit, self.output_bytes) <= 0 or self.wall_seconds <= 0:
            raise ContractViolation("sandbox quotas must be positive")


@dataclass(frozen=True, slots=True)
class NetworkPolicy:
    policy_id: str
    default_deny: bool = True
    allowed_egress: tuple[str, ...] = ()
    allowed_domains: tuple[str, ...] = ()
    dns_allowed: bool = False
    dns_server_cidrs: tuple[str, ...] = ()
    egress_proxy_ref: str | None = None
    audit_sink_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.policy_id or not self.default_deny:
            raise ContractViolation("sandbox network must be deny-by-default")
        for destination in self.allowed_egress:
            if not destination or destination in {"*", "0.0.0.0/0", "::/0"}:
                raise ContractViolation("sandbox egress entries must be explicit")
            try:
                ipaddress.ip_network(destination, strict=False)
            except ValueError as error:
                raise ContractViolation("sandbox direct egress entries must be CIDRs") from error
        for destination in self.dns_server_cidrs:
            try:
                ipaddress.ip_network(destination, strict=False)
            except ValueError as error:
                raise ContractViolation("sandbox DNS server entries must be CIDRs") from error
        if self.allowed_domains and (not self.egress_proxy_ref or not self.audit_sink_ref):
            raise ContractViolation("domain egress requires an audited deployment-owned proxy")
        if any(not value or value == "*" for value in self.allowed_domains):
            raise ContractViolation("sandbox domain allowlist entries must be explicit")
        if self.dns_allowed and (not self.dns_server_cidrs or not self.audit_sink_ref):
            raise ContractViolation("sandbox DNS requires explicit servers and an audit sink")
        if (self.allowed_egress or self.allowed_domains) and not self.audit_sink_ref:
            raise ContractViolation("sandbox egress requires an audit sink")


@dataclass(frozen=True, slots=True)
class MountSpec:
    source: str
    target: str
    read_only: bool = True

    def __post_init__(self) -> None:
        target = PurePosixPath(self.target)
        source = Path(self.source)
        if not target.is_absolute() or ".." in target.parts or not source.is_absolute() or ".." in source.parts or source == Path("/") or source.is_symlink():
            raise ContractViolation("sandbox mount target must be an absolute safe path")


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    identity: Identity
    isolation_class: IsolationClass
    image_digest: str
    region: str
    quotas: SandboxQuotas = SandboxQuotas()
    network: NetworkPolicy = NetworkPolicy("deny-all")
    mounts: tuple[MountSpec, ...] = ()
    secret_refs: tuple[str, ...] = ()
    runtime_class: str | None = None

    def __post_init__(self) -> None:
        if self.isolation_class not in {IsolationClass.L1, IsolationClass.L2, IsolationClass.L3, IsolationClass.L4}:
            raise ContractViolation("production sandbox requires L1-L4 isolation")
        if not _sha256_digest(self.image_digest):
            raise ContractViolation("sandbox image must be pinned by sha256 digest")
        if not self.region:
            raise ContractViolation("sandbox region is required")
        targets = [mount.target for mount in self.mounts]
        if len(targets) != len(set(targets)):
            raise ContractViolation("sandbox mount targets must be unique")


@dataclass(frozen=True, slots=True)
class SandboxHandle:
    sandbox_id: str
    identity: Identity
    backend: str
    backend_ref: str
    region: str
    isolation_class: IsolationClass
    image_digest: str
    state: str
    fencing_token: str
    expires_at: float
    spec_digest: str


@dataclass(frozen=True, slots=True)
class SandboxExecRequest:
    argv: tuple[str, ...]
    idempotency_key: str
    cwd: str = "/workspace/source"
    env: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float = 30.0
    secret_leases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.argv or any(not isinstance(item, str) or not item for item in self.argv):
            raise ContractViolation("sandbox exec requires a non-empty argv tuple")
        if not self.idempotency_key or self.timeout_seconds <= 0:
            raise ContractViolation("sandbox exec requires idempotency and timeout")
        path = PurePosixPath(self.cwd)
        if not path.is_absolute() or ".." in path.parts:
            raise ContractViolation("sandbox cwd must be an absolute safe path")
        object.__setattr__(self, "env", dict(self.env or {}))

    @property
    def digest(self) -> str:
        return digest_of({"argv": self.argv, "cwd": self.cwd, "env": dict(self.env), "timeout": self.timeout_seconds, "secret_leases": self.secret_leases})


@dataclass(frozen=True, slots=True)
class SandboxExecResult:
    exit_code: int
    stdout: bytes
    stderr: bytes
    started_at: float
    finished_at: float
    timed_out: bool = False
    cancelled: bool = False

    @property
    def digest(self) -> str:
        return digest_of({"exit_code": self.exit_code, "stdout": self.stdout.hex(), "stderr": self.stderr.hex(), "timed_out": self.timed_out, "cancelled": self.cancelled})


@dataclass(frozen=True, slots=True)
class SandboxStats:
    cpu_seconds: float
    memory_bytes: int
    disk_bytes: int
    pids: int
    sampled_at: float


class SandboxBackend(Protocol):
    name: str
    supported_isolation: frozenset[IsolationClass]

    def create(self, sandbox_id: str, spec: SandboxSpec) -> str: ...
    def exec(self, backend_ref: str, request: SandboxExecRequest, secrets: Mapping[str, str]) -> SandboxExecResult: ...
    def snapshot(self, backend_ref: str) -> str: ...
    def restore(self, sandbox_id: str, snapshot_ref: str, spec: SandboxSpec) -> str: ...
    def stats(self, backend_ref: str) -> SandboxStats: ...
    def destroy(self, backend_ref: str) -> None: ...


@dataclass(frozen=True, slots=True)
class SecretLease:
    lease_id: str
    identity: Identity
    secret_ref: str
    purpose: str
    expires_at: float
    revoked: bool = False


class SecretBroker(Protocol):
    def issue(self, identity: Identity, secret_ref: str, purpose: str, *, ttl_seconds: float) -> SecretLease: ...
    def resolve(self, identity: Identity, lease_id: str, *, purpose: str, now: float | None = None) -> str: ...
    def revoke(self, identity: Identity, lease_id: str) -> None: ...


class InMemorySecretBroker:
    """Local broker that never persists plaintext; use Vault/KMS in production."""

    def __init__(self, values: Mapping[tuple[str, str], str]) -> None:
        self._values = dict(values)
        self._leases: dict[str, SecretLease] = {}
        self._lock = threading.RLock()

    def issue(self, identity: Identity, secret_ref: str, purpose: str, *, ttl_seconds: float) -> SecretLease:
        if (identity.tenant_id, secret_ref) not in self._values or not purpose or ttl_seconds <= 0 or ttl_seconds > 3600:
            raise ContractViolation("secret lease request is invalid or unauthorized")
        lease = SecretLease(new_id(), identity, secret_ref, purpose, time.time() + ttl_seconds)
        with self._lock:
            self._leases[lease.lease_id] = lease
        return lease

    def resolve(self, identity: Identity, lease_id: str, *, purpose: str, now: float | None = None) -> str:
        now = time.time() if now is None else now
        with self._lock:
            lease = self._leases.get(lease_id)
            if lease is None or lease.revoked or lease.expires_at <= now:
                raise LeaseLost("secret lease is absent, expired or revoked")
            if lease.identity.scope() != identity.scope() or lease.identity.agent_id != identity.agent_id or lease.purpose != purpose:
                raise TenantIsolationError("secret lease scope does not match caller")
            return self._values[(lease.identity.tenant_id, lease.secret_ref)]

    def revoke(self, identity: Identity, lease_id: str) -> None:
        with self._lock:
            lease = self._leases.get(lease_id)
            if lease is None:
                return
            if lease.identity.scope() != identity.scope() or lease.identity.agent_id != identity.agent_id:
                raise TenantIsolationError("secret lease scope does not match caller")
            self._leases[lease_id] = replace(lease, revoked=True)


class VaultSecretBroker:
    """Adapter for an injected Vault-like client using response-wrapped leases."""

    def __init__(self, client: Any, *, mount: str = "secret") -> None:
        self.client = client
        self.mount = mount
        self._leases: dict[str, SecretLease] = {}

    def issue(self, identity: Identity, secret_ref: str, purpose: str, *, ttl_seconds: float) -> SecretLease:
        if not secret_ref or not purpose or ttl_seconds <= 0 or ttl_seconds > 3600:
            raise ContractViolation("invalid Vault secret lease request")
        response = self.client.issue_wrapped_secret(
            mount=self.mount,
            path=secret_ref,
            tenant_id=identity.tenant_id,
            project_id=identity.project_id,
            task_id=identity.task_id,
            run_id=identity.run_id,
            node_id=identity.node_id,
            agent_id=identity.agent_id,
            purpose=purpose,
            ttl_seconds=ttl_seconds,
        )
        lease_id = str(response["lease_id"])
        expires_at = float(response.get("expires_at", time.time() + ttl_seconds))
        lease = SecretLease(lease_id, identity, secret_ref, purpose, expires_at)
        self._leases[lease_id] = lease
        return lease

    def resolve(self, identity: Identity, lease_id: str, *, purpose: str, now: float | None = None) -> str:
        lease = self._leases.get(lease_id)
        now = time.time() if now is None else now
        if lease is None or lease.revoked or lease.expires_at <= now:
            raise LeaseLost("Vault lease is absent, expired or revoked")
        if lease.identity.scope() != identity.scope() or lease.identity.agent_id != identity.agent_id or lease.purpose != purpose:
            raise TenantIsolationError("Vault lease scope mismatch")
        return str(self.client.unwrap_secret(lease_id=lease_id, tenant_id=identity.tenant_id, project_id=identity.project_id, task_id=identity.task_id, run_id=identity.run_id, node_id=identity.node_id, agent_id=identity.agent_id, purpose=purpose))

    def revoke(self, identity: Identity, lease_id: str) -> None:
        lease = self._leases.get(lease_id)
        if lease is None:
            return
        if lease.identity.scope() != identity.scope() or lease.identity.agent_id != identity.agent_id:
            raise TenantIsolationError("Vault lease scope mismatch")
        self.client.revoke_lease(lease_id=lease_id, tenant_id=identity.tenant_id, project_id=identity.project_id, task_id=identity.task_id, run_id=identity.run_id, node_id=identity.node_id, agent_id=identity.agent_id)
        self._leases[lease_id] = replace(lease, revoked=True)


class ProductionSandboxProvider:
    """Durable, fenced lifecycle over a concrete isolation backend."""

    def __init__(self, backend: SandboxBackend, database: str = ":memory:", *, secret_broker: SecretBroker | None = None, lease_seconds: float = 300.0, warm_pool: SandboxWarmPool | None = None) -> None:
        if lease_seconds <= 0:
            raise ContractViolation("sandbox lease TTL must be positive")
        self.backend = backend
        self.secret_broker = secret_broker
        self.warm_pool = warm_pool
        self.lease_seconds = lease_seconds
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """CREATE TABLE IF NOT EXISTS sandbox_leases(
               sandbox_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,
               task_id TEXT NOT NULL,run_id TEXT NOT NULL,node_id TEXT NOT NULL,agent_id TEXT,
               backend TEXT NOT NULL,backend_ref TEXT NOT NULL,region TEXT NOT NULL,
               isolation_class TEXT NOT NULL,image_digest TEXT NOT NULL,state TEXT NOT NULL,
               fencing_token TEXT NOT NULL,expires_at REAL NOT NULL,spec_digest TEXT NOT NULL,
               spec_json TEXT NOT NULL);
               CREATE TABLE IF NOT EXISTS sandbox_exec_results(
               tenant_id TEXT NOT NULL,sandbox_id TEXT NOT NULL,idempotency_key TEXT NOT NULL,
               request_digest TEXT NOT NULL,result_json TEXT NOT NULL,
               PRIMARY KEY(tenant_id,sandbox_id,idempotency_key));
               CREATE TABLE IF NOT EXISTS sandbox_restore_operations(
               sandbox_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,
               task_id TEXT NOT NULL,run_id TEXT NOT NULL,node_id TEXT NOT NULL,snapshot_ref TEXT NOT NULL,
               request_digest TEXT NOT NULL,idempotency_key TEXT NOT NULL,state TEXT NOT NULL,
               backend_ref TEXT,reconciliation_json TEXT,updated_at REAL NOT NULL);"""
        )
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def create(self, spec: SandboxSpec, *, idempotency_key: str, now: float | None = None) -> SandboxHandle:
        if spec.isolation_class not in self.backend.supported_isolation:
            raise NotConfigured(f"{self.backend.name} does not implement {spec.isolation_class.value}")
        if not idempotency_key:
            raise ContractViolation("sandbox create requires idempotency")
        now = time.time() if now is None else now
        spec_body = _spec_dict(spec)
        spec_digest = digest_of(spec_body)
        sandbox_id = "sbx_" + digest_of({"identity": spec.identity.scope(), "agent_id": spec.identity.agent_id, "operation": "create", "key": idempotency_key}).split(":", 1)[1][:40]
        with self._lock:
            existing = self._connection.execute("SELECT * FROM sandbox_leases WHERE sandbox_id=?", (sandbox_id,)).fetchone()
            if existing is not None:
                if existing["spec_digest"] != spec_digest:
                    raise IdempotencyConflict("sandbox create key was reused with another spec")
                return self._handle(existing)
            backend_ref = None if self.warm_pool is None else self.warm_pool.claim(spec, sandbox_id)
            backend_ref = backend_ref or self.backend.create(sandbox_id, spec)
            if not backend_ref:
                raise ContractViolation("sandbox backend returned an empty reference")
            handle = SandboxHandle(sandbox_id, spec.identity, self.backend.name, backend_ref, spec.region, spec.isolation_class, spec.image_digest, "active", new_id(), now + self.lease_seconds, spec_digest)
            self._connection.execute(
                "INSERT INTO sandbox_leases VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sandbox_id, *spec.identity.scope(), spec.identity.agent_id, self.backend.name, backend_ref, spec.region, spec.isolation_class.value, spec.image_digest, handle.state, handle.fencing_token, handle.expires_at, spec_digest, canonical_json(spec_body)),
            )
        return handle

    def heartbeat(self, handle: SandboxHandle, *, now: float | None = None) -> SandboxHandle:
        now = time.time() if now is None else now
        self._assert(handle, now)
        expires = now + self.lease_seconds
        with self._lock:
            updated = self._connection.execute(
                "UPDATE sandbox_leases SET expires_at=? WHERE sandbox_id=? AND tenant_id=? AND fencing_token=? AND state='active'",
                (expires, handle.sandbox_id, handle.identity.tenant_id, handle.fencing_token),
            ).rowcount
        if updated != 1:
            raise LeaseLost("sandbox heartbeat lost fencing ownership")
        return replace(handle, expires_at=expires)

    def exec(self, handle: SandboxHandle, request: SandboxExecRequest, *, secret_purpose: str = "sandbox-exec", now: float | None = None) -> SandboxExecResult:
        now = time.time() if now is None else now
        self._assert(handle, now)
        row = self._connection.execute(
            "SELECT request_digest,result_json FROM sandbox_exec_results WHERE tenant_id=? AND sandbox_id=? AND idempotency_key=?",
            (handle.identity.tenant_id, handle.sandbox_id, request.idempotency_key),
        ).fetchone()
        if row is not None:
            if row["request_digest"] != request.digest:
                raise IdempotencyConflict("sandbox exec key was reused with another request")
            self._revoke_secret_leases(handle.identity, request.secret_leases)
            return _exec_result(json.loads(row["result_json"]))
        secrets: dict[str, str] = {}
        if request.secret_leases:
            if self.secret_broker is None:
                raise NotConfigured("sandbox exec requested secrets without a broker")
            for lease_id in request.secret_leases:
                secrets[lease_id] = self.secret_broker.resolve(handle.identity, lease_id, purpose=secret_purpose, now=now)
        try:
            result = self.backend.exec(handle.backend_ref, request, secrets)
        finally:
            self._revoke_secret_leases(handle.identity, request.secret_leases)
        result = replace(
            result,
            stdout=_redact_secret_bytes(result.stdout, tuple(secrets.values())),
            stderr=_redact_secret_bytes(result.stderr, tuple(secrets.values())),
        )
        output_size = len(result.stdout) + len(result.stderr)
        spec = self._spec(handle.sandbox_id)
        if output_size > spec.quotas.output_bytes:
            result = replace(result, stdout=result.stdout[: spec.quotas.output_bytes], stderr=b"", exit_code=137)
        with self._lock:
            self._connection.execute(
                "INSERT INTO sandbox_exec_results VALUES(?,?,?,?,?)",
                (handle.identity.tenant_id, handle.sandbox_id, request.idempotency_key, request.digest, canonical_json(_result_dict(result))),
            )
        return result

    def snapshot(self, handle: SandboxHandle) -> str:
        self._assert(handle, time.time(), allow_expired=True)
        reference = self.backend.snapshot(handle.backend_ref)
        if not _sha256_digest(reference):
            raise ContractViolation("sandbox snapshots must be content-addressed")
        return reference

    def restore(self, spec: SandboxSpec, snapshot_ref: str, *, idempotency_key: str, now: float | None = None) -> SandboxHandle:
        if spec.isolation_class not in self.backend.supported_isolation:
            raise NotConfigured(f"{self.backend.name} does not implement {spec.isolation_class.value}")
        if not idempotency_key or not _sha256_digest(snapshot_ref):
            raise ContractViolation("sandbox restore requires a digest reference")
        now = time.time() if now is None else now
        restore_digest = digest_of({"identity": spec.identity.scope(), "snapshot": snapshot_ref, "spec": _spec_dict(spec)})
        sandbox_id = "sbx_" + digest_of({"identity": spec.identity.scope(), "operation": "restore", "key": idempotency_key}).split(":", 1)[1][:40]
        with self._lock:
            existing = self._connection.execute("SELECT * FROM sandbox_leases WHERE sandbox_id=?", (sandbox_id,)).fetchone()
            if existing is not None:
                restored = self._connection.execute("SELECT * FROM sandbox_restore_operations WHERE sandbox_id=?", (sandbox_id,)).fetchone()
                if restored is not None:
                    self._assert_restore_scope(restored, spec.identity)
                if restored is None or restored["request_digest"] != restore_digest:
                    raise IdempotencyConflict("sandbox restore key was reused with another request")
                return self._handle(existing)
            operation = self._connection.execute("SELECT * FROM sandbox_restore_operations WHERE sandbox_id=?", (sandbox_id,)).fetchone()
            if operation is not None:
                self._assert_restore_scope(operation, spec.identity)
                if operation["request_digest"] != restore_digest:
                    raise IdempotencyConflict("sandbox restore key was reused with another request")
                if operation["state"] != "reconciled_absent":
                    raise LeaseLost("sandbox restore outcome is unknown and requires reconciliation")
                self._connection.execute("UPDATE sandbox_restore_operations SET state='pending',updated_at=? WHERE sandbox_id=? AND state='reconciled_absent'", (now, sandbox_id))
            else:
                self._connection.execute(
                    "INSERT INTO sandbox_restore_operations VALUES(?,?,?,?,?,?,?,?,?,'pending',NULL,NULL,?)",
                    (sandbox_id, *spec.identity.scope(), snapshot_ref, restore_digest, idempotency_key, now),
                )
        try:
            backend_ref = self.backend.restore(sandbox_id, snapshot_ref, spec)
        except Exception:
            with self._lock:
                self._connection.execute("UPDATE sandbox_restore_operations SET state='unknown',updated_at=? WHERE sandbox_id=?", (time.time(), sandbox_id))
            raise
        if not backend_ref:
            with self._lock:
                self._connection.execute("UPDATE sandbox_restore_operations SET state='unknown',updated_at=? WHERE sandbox_id=?", (time.time(), sandbox_id))
            raise ContractViolation("sandbox restore returned an empty backend reference")
        handle = SandboxHandle(sandbox_id, spec.identity, self.backend.name, backend_ref, spec.region, spec.isolation_class, spec.image_digest, "active", new_id(), now + self.lease_seconds, digest_of(_spec_dict(spec)))
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    "INSERT INTO sandbox_leases VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (sandbox_id, *spec.identity.scope(), spec.identity.agent_id, self.backend.name, backend_ref, spec.region, spec.isolation_class.value, spec.image_digest, handle.state, handle.fencing_token, handle.expires_at, handle.spec_digest, canonical_json(_spec_dict(spec))),
                )
                updated = self._connection.execute("UPDATE sandbox_restore_operations SET state='completed',backend_ref=?,updated_at=? WHERE sandbox_id=? AND state='pending'", (backend_ref, time.time(), sandbox_id)).rowcount
                if updated != 1:
                    raise LeaseLost("sandbox restore journal lost ownership")
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return handle

    def reconcile_restore(
        self,
        spec: SandboxSpec,
        snapshot_ref: str,
        *,
        idempotency_key: str,
        resolver: Callable[[str, str, SandboxSpec, str], Mapping[str, Any]],
        verifier: Callable[[Mapping[str, Any], str], bool],
        executor_id: str,
        verifier_id: str,
        evidence_ref: str,
        now: float | None = None,
    ) -> SandboxHandle:
        """Resolve an unknown restore without blindly repeating its side effect."""

        if not idempotency_key or not executor_id or not verifier_id or executor_id == verifier_id or not _sha256_digest(snapshot_ref) or not _sha256_digest(evidence_ref):
            raise ContractViolation("sandbox restore reconciliation requires independent, digest-bound evidence")
        now = time.time() if now is None else now
        spec_digest = digest_of(_spec_dict(spec))
        request_digest = digest_of({"identity": spec.identity.scope(), "snapshot": snapshot_ref, "spec": _spec_dict(spec)})
        sandbox_id = "sbx_" + digest_of({"identity": spec.identity.scope(), "operation": "restore", "key": idempotency_key}).split(":", 1)[1][:40]
        with self._lock:
            operation = self._connection.execute("SELECT * FROM sandbox_restore_operations WHERE sandbox_id=?", (sandbox_id,)).fetchone()
            if operation is None:
                raise KeyError(sandbox_id)
            self._assert_restore_scope(operation, spec.identity)
            if operation["request_digest"] != request_digest or operation["snapshot_ref"] != snapshot_ref or operation["idempotency_key"] != idempotency_key:
                raise IdempotencyConflict("sandbox restore reconciliation request does not match the journal")
            existing = self._connection.execute("SELECT * FROM sandbox_leases WHERE sandbox_id=?", (sandbox_id,)).fetchone()
            if existing is not None:
                return self._handle(existing)
            if operation["state"] == "completed":
                raise LeaseLost("completed sandbox restore is missing its durable lease")
        outcome = dict(resolver(sandbox_id, snapshot_ref, spec, idempotency_key))
        if not verifier(outcome, evidence_ref):
            with self._lock:
                self._connection.execute("UPDATE sandbox_restore_operations SET state='unknown',reconciliation_json=?,updated_at=? WHERE sandbox_id=?", (canonical_json({"status": "verification_failed", "evidence_ref": evidence_ref}), now, sandbox_id))
            raise LeaseLost("sandbox restore reconciliation evidence was not verified")
        status = str(outcome.get("status", "unknown"))
        reconciliation = canonical_json({"outcome": outcome, "evidence_ref": evidence_ref, "executor_id": executor_id, "verifier_id": verifier_id})
        if status == "absent":
            with self._lock:
                self._connection.execute("UPDATE sandbox_restore_operations SET state='reconciled_absent',reconciliation_json=?,updated_at=? WHERE sandbox_id=? AND state IN ('pending','unknown','executing','reconciled_absent')", (reconciliation, now, sandbox_id))
            return self.restore(spec, snapshot_ref, idempotency_key=idempotency_key, now=now)
        if status != "restored" or outcome.get("snapshot_ref") != snapshot_ref or outcome.get("spec_digest") != spec_digest or not str(outcome.get("backend_ref", "")):
            with self._lock:
                self._connection.execute("UPDATE sandbox_restore_operations SET state='unknown',reconciliation_json=?,updated_at=? WHERE sandbox_id=?", (reconciliation, now, sandbox_id))
            raise LeaseLost("sandbox restore reconciliation outcome remains unknown")
        backend_ref = str(outcome["backend_ref"])
        handle = SandboxHandle(sandbox_id, spec.identity, self.backend.name, backend_ref, spec.region, spec.isolation_class, spec.image_digest, "active", new_id(), now + self.lease_seconds, spec_digest)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    "INSERT INTO sandbox_leases VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (sandbox_id, *spec.identity.scope(), spec.identity.agent_id, self.backend.name, backend_ref, spec.region, spec.isolation_class.value, spec.image_digest, handle.state, handle.fencing_token, handle.expires_at, spec_digest, canonical_json(_spec_dict(spec))),
                )
                updated = self._connection.execute("UPDATE sandbox_restore_operations SET state='completed',backend_ref=?,reconciliation_json=?,updated_at=? WHERE sandbox_id=? AND state IN ('pending','unknown','executing')", (backend_ref, reconciliation, now, sandbox_id)).rowcount
                if updated != 1:
                    raise LeaseLost("sandbox restore reconciliation journal lost ownership")
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                self._connection.execute("UPDATE sandbox_restore_operations SET state='unknown',reconciliation_json=?,updated_at=? WHERE sandbox_id=?", (reconciliation, now, sandbox_id))
                raise
        return handle

    def stats(self, handle: SandboxHandle) -> SandboxStats:
        self._assert(handle, time.time())
        return self.backend.stats(handle.backend_ref)

    def destroy(self, handle: SandboxHandle) -> None:
        current = self._current(handle.sandbox_id)
        if current is None:
            return
        if current.identity.scope() != handle.identity.scope() or current.identity.agent_id != handle.identity.agent_id or current.fencing_token != handle.fencing_token:
            raise TenantIsolationError("sandbox destroy scope/fencing mismatch")
        if current.state == "destroyed":
            return
        self.backend.destroy(current.backend_ref)
        with self._lock:
            self._connection.execute("UPDATE sandbox_leases SET state='destroyed',expires_at=? WHERE sandbox_id=?", (time.time(), handle.sandbox_id))

    def reap_expired(self, *, now: float | None = None) -> tuple[str, ...]:
        now = time.time() if now is None else now
        rows = self._connection.execute("SELECT * FROM sandbox_leases WHERE state='active' AND expires_at<=?", (now,)).fetchall()
        destroyed: list[str] = []
        for row in rows:
            handle = self._handle(row)
            self.destroy(handle)
            destroyed.append(handle.sandbox_id)
        return tuple(destroyed)

    def _assert(self, handle: SandboxHandle, now: float, *, allow_expired: bool = False) -> None:
        current = self._current(handle.sandbox_id)
        if current is None or current.identity.scope() != handle.identity.scope() or current.identity.agent_id != handle.identity.agent_id or current.fencing_token != handle.fencing_token:
            raise TenantIsolationError("sandbox handle scope/fencing mismatch")
        if current.state != "active":
            raise LeaseLost("sandbox is not active")
        if not allow_expired and current.expires_at <= now:
            raise LeaseLost("sandbox lease expired")

    def _current(self, sandbox_id: str) -> SandboxHandle | None:
        row = self._connection.execute("SELECT * FROM sandbox_leases WHERE sandbox_id=?", (sandbox_id,)).fetchone()
        return None if row is None else self._handle(row)

    def _spec(self, sandbox_id: str) -> SandboxSpec:
        row = self._connection.execute("SELECT spec_json FROM sandbox_leases WHERE sandbox_id=?", (sandbox_id,)).fetchone()
        if row is None:
            raise KeyError(sandbox_id)
        return _spec_from_dict(json.loads(row["spec_json"]))

    def _revoke_secret_leases(self, identity: Identity, leases: tuple[str, ...]) -> None:
        if not leases:
            return
        if self.secret_broker is None:
            raise NotConfigured("sandbox secret broker is unavailable during lease revocation")
        errors: list[Exception] = []
        for lease_id in leases:
            try:
                self.secret_broker.revoke(identity, lease_id)
            except Exception as error:  # noqa: BLE001 - revocation failures are aggregated for lease safety
                errors.append(error)
        if errors:
            raise LeaseLost("one or more sandbox secret leases could not be revoked") from errors[0]

    @staticmethod
    def _assert_restore_scope(row: sqlite3.Row, identity: Identity) -> None:
        stored = tuple(row[name] for name in ("tenant_id", "project_id", "task_id", "run_id", "node_id"))
        if stored != identity.scope():
            raise TenantIsolationError("sandbox restore journal belongs to another project/task scope")

    @staticmethod
    def _handle(row: sqlite3.Row) -> SandboxHandle:
        identity = Identity(row["tenant_id"], row["project_id"], row["task_id"], row["run_id"], row["node_id"], row["agent_id"])
        return SandboxHandle(row["sandbox_id"], identity, row["backend"], row["backend_ref"], row["region"], IsolationClass(row["isolation_class"]), row["image_digest"], row["state"], row["fencing_token"], float(row["expires_at"]), row["spec_digest"])


CommandRunner = Callable[[list[str], float], Any]


class DockerSandboxBackend:
    name = "docker"

    def __init__(self, runner: CommandRunner | None = None, *, engine: str = "docker", io_client: Any | None = None, hardened_runtime: str | None = None, allowed_mount_roots: tuple[str | Path, ...] = ()) -> None:
        self.runner = runner or _subprocess_runner
        self.engine = engine
        self.io_client = io_client
        self.hardened_runtime = hardened_runtime
        self.allowed_mount_roots = tuple(Path(value).resolve() for value in allowed_mount_roots)
        self.supported_isolation = frozenset({IsolationClass.L1, IsolationClass.L2}) if hardened_runtime else frozenset({IsolationClass.L1})
        self._specs: dict[str, SandboxSpec] = {}

    def create(self, sandbox_id: str, spec: SandboxSpec) -> str:
        if spec.network.allowed_egress or spec.network.allowed_domains or spec.network.dns_allowed:
            raise NotConfigured("Docker CLI backend cannot enforce destination-level egress; use Kubernetes or an approved proxy backend")
        command = [
            self.engine, "create", "--name", sandbox_id, "--network=none", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--user=65532:65532", f"--cpus={spec.quotas.cpu_cores}", f"--memory={spec.quotas.memory_mb}m",
            f"--pids-limit={spec.quotas.pid_limit}", "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=256m",
        ]
        if spec.isolation_class == IsolationClass.L2:
            if not self.hardened_runtime:
                raise NotConfigured("Docker L2 requires an explicitly configured gVisor-compatible runtime")
            command.append("--runtime=" + self.hardened_runtime)
        for mount in spec.mounts:
            source = Path(mount.source).resolve()
            if not self.allowed_mount_roots or not any(source.is_relative_to(root) for root in self.allowed_mount_roots):
                raise TenantIsolationError("Docker mount source is outside deployment-owned roots")
            if not (source.is_file() or source.is_dir()):
                raise ContractViolation("Docker mount source must be a regular file or directory")
            mode = "ro" if mount.read_only else "rw"
            command.append(f"--mount=type=bind,src={source},dst={mount.target},{mode}")
        command.extend([f"elmos/sandbox@{spec.image_digest}", "sleep", "infinity"])
        result = self.runner(command, 60.0)
        if int(result.returncode) != 0:
            raise NotConfigured("Docker sandbox creation failed: " + _bounded_text(result.stderr))
        backend_ref = _bounded_text(result.stdout).strip() or sandbox_id
        started = self.runner([self.engine, "start", backend_ref], 60.0)
        if int(started.returncode) != 0:
            self.runner([self.engine, "rm", "-f", backend_ref], 60.0)
            raise NotConfigured("Docker sandbox start failed: " + _bounded_text(started.stderr))
        self._specs[backend_ref] = spec
        return backend_ref

    def exec(self, backend_ref: str, request: SandboxExecRequest, secrets: Mapping[str, str]) -> SandboxExecResult:
        if secrets:
            raise NotConfigured("Docker CLI secret injection is disabled because process arguments can expose values; use an API-backed secret mount")
        started_at = time.time()
        command = [self.engine, "exec", "--workdir", request.cwd]
        for key, value in sorted(request.env.items()):
            if not key.replace("_", "").isalnum() or key.upper() != key:
                raise ContractViolation("sandbox environment keys must be uppercase identifiers")
            command.extend(["--env", f"{key}={value}"])
        command.extend([backend_ref, *request.argv])
        result = self.runner(command, request.timeout_seconds)
        return SandboxExecResult(int(result.returncode), _bytes(result.stdout), _bytes(result.stderr), started_at, time.time(), bool(getattr(result, "timed_out", False)))

    def snapshot(self, backend_ref: str) -> str:
        value = _required_mapping(
            self._io().snapshot_container(container_id=backend_ref),
            "Docker snapshot",
        )
        reference = str(value.get("digest", ""))
        if not _sha256_digest(reference):
            raise ContractViolation("Docker snapshot is not content-addressed")
        return reference

    def restore(self, sandbox_id: str, snapshot_ref: str, spec: SandboxSpec) -> str:
        if not _sha256_digest(snapshot_ref):
            raise ContractViolation("invalid Docker snapshot reference")
        value = _required_mapping(
            self._io().restore_container(
                sandbox_id=sandbox_id,
                snapshot_digest=snapshot_ref,
                spec=_spec_dict(spec),
            ),
            "Docker restore",
        )
        backend_ref = str(value.get("container_id", ""))
        restored_digest = str(value.get("snapshot_digest", ""))
        if not backend_ref or restored_digest != snapshot_ref:
            raise ContractViolation("Docker restore did not attest the requested snapshot")
        self._specs[backend_ref] = spec
        return backend_ref

    def stats(self, backend_ref: str) -> SandboxStats:
        result = self.runner([self.engine, "stats", "--no-stream", "--format", "{{json .}}", backend_ref], 30.0)
        if int(result.returncode) != 0:
            raise NotConfigured("Docker stats failed")
        payload = json.loads(_bounded_text(result.stdout))
        return SandboxStats(float(payload.get("CPUPerc", "0").rstrip("%") or 0), _parse_bytes(payload.get("MemUsage", "0B").split("/")[0]), 0, int(payload.get("PIDs", 0)), time.time())

    def destroy(self, backend_ref: str) -> None:
        result = self.runner([self.engine, "rm", "-f", backend_ref], 60.0)
        if int(result.returncode) not in {0, 1}:
            raise NotConfigured("Docker sandbox destruction failed")
        self._specs.pop(backend_ref, None)

    def read_file(self, backend_ref: str, path: str, start: int, length: int | None) -> bytes:
        return _required_bytes(self._io().read_file(container_id=backend_ref, path=path, start=start, length=length), "Docker read_file")

    def write_file(self, backend_ref: str, path: str, data: bytes, expected_digest: str | None, idempotency_key: str) -> Mapping[str, Any]:
        return _required_mapping(self._io().write_file(container_id=backend_ref, path=path, data=data, expected_digest=expected_digest, idempotency_key=idempotency_key), "Docker write_file")

    def apply_patch(self, backend_ref: str, operations: list[Mapping[str, Any]], idempotency_key: str) -> Mapping[str, Any]:
        return _required_mapping(self._io().apply_patch(container_id=backend_ref, operations=operations, idempotency_key=idempotency_key), "Docker apply_patch")

    def git(self, backend_ref: str, operation: str, args: list[str], idempotency_key: str | None) -> Mapping[str, Any]:
        return _required_mapping(self._io().git(container_id=backend_ref, operation=operation, args=args, idempotency_key=idempotency_key), "Docker git")

    def expose_port(self, backend_ref: str, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        return _required_mapping(self._io().expose_port(container_id=backend_ref, spec=dict(spec)), "Docker expose_port")

    def _io(self) -> Any:
        if self.io_client is None:
            raise NotConfigured("Docker workspace I/O requires an authenticated sandbox-agent client")
        return self.io_client


class KubernetesSandboxBackend:
    name = "kubernetes"
    supported_isolation = frozenset({IsolationClass.L2, IsolationClass.L3})

    def __init__(self, client: Any, *, namespace: str = "elmos-sandboxes") -> None:
        self.client = client
        self.namespace = namespace
        self._specs: dict[str, SandboxSpec] = {}

    def create(self, sandbox_id: str, spec: SandboxSpec) -> str:
        runtime_class = spec.runtime_class or ("gvisor" if spec.isolation_class == IsolationClass.L2 else "kata")
        volumes: list[Mapping[str, Any]] = []
        volume_mounts: list[Mapping[str, Any]] = []
        if spec.mounts:
            resolver = getattr(self.client, "resolve_namespaced_sandbox_mounts", None)
            if not callable(resolver):
                raise NotConfigured("Kubernetes mounts require a deployment-owned mount resolver")
            resolved = _required_mapping(
                resolver(
                    namespace=self.namespace,
                    sandbox_id=sandbox_id,
                    tenant_id=spec.identity.tenant_id,
                    mounts=[asdict(item) for item in spec.mounts],
                ),
                "Kubernetes mount resolution",
            )
            raw_volumes = resolved.get("volumes")
            raw_mounts = resolved.get("volume_mounts")
            if not isinstance(raw_volumes, list) or not isinstance(raw_mounts, list):
                raise ContractViolation("Kubernetes mount resolver returned an invalid contract")
            if any(not isinstance(item, Mapping) or "hostPath" in item for item in raw_volumes):
                raise ContractViolation("Kubernetes sandbox volumes must be typed and cannot use hostPath")
            if any(not isinstance(item, Mapping) for item in raw_mounts):
                raise ContractViolation("Kubernetes sandbox volume mounts must be typed objects")
            expected_mounts = {(item.target, item.read_only) for item in spec.mounts}
            actual_mounts = {(str(item.get("mountPath", "")), bool(item.get("readOnly", False))) for item in raw_mounts}
            if actual_mounts != expected_mounts:
                raise ContractViolation("Kubernetes resolved mounts do not preserve target/read-only scope")
            volumes = [dict(item) for item in raw_volumes]
            volume_mounts = [dict(item) for item in raw_mounts]
        egress_cidrs = list(spec.network.allowed_egress)
        egress_cidrs.extend(spec.network.dns_server_cidrs if spec.network.dns_allowed else ())
        if spec.network.allowed_domains:
            proxy = self.client.configure_egress_proxy(
                namespace=self.namespace,
                sandbox_id=sandbox_id,
                proxy_ref=spec.network.egress_proxy_ref,
                allowed_domains=list(spec.network.allowed_domains),
                audit_sink_ref=spec.network.audit_sink_ref,
            )
            for cidr in proxy.get("proxy_cidrs", ()):
                ipaddress.ip_network(str(cidr), strict=False)
                egress_cidrs.append(str(cidr))
        body = {
            "apiVersion": "v1", "kind": "Pod", "metadata": {"name": sandbox_id, "labels": {"app": "elmos-sandbox", "tenant-digest": digest_of(spec.identity.tenant_id)[7:23], "sandbox-id": sandbox_id}},
            "spec": {
                "automountServiceAccountToken": False, "enableServiceLinks": False, "hostNetwork": False,
                "hostPID": False, "hostIPC": False, "restartPolicy": "Never", "runtimeClassName": runtime_class,
                "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{
                    "name": "agent", "image": f"elmos/sandbox@{spec.image_digest}", "command": ["sleep", "infinity"],
                    "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
                    "resources": {"limits": {"cpu": str(spec.quotas.cpu_cores), "memory": f"{spec.quotas.memory_mb}Mi", "ephemeral-storage": f"{spec.quotas.disk_mb}Mi"}},
                    "volumeMounts": volume_mounts,
                }],
                "volumes": volumes,
            },
        }
        created = False
        try:
            self.client.create_namespaced_pod(namespace=self.namespace, body=body)
            created = True
            self.client.apply_namespaced_network_policy(
                namespace=self.namespace,
                body={
                    "apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
                    "metadata": {"name": sandbox_id},
                    "spec": {
                        "podSelector": {"matchLabels": {"app": "elmos-sandbox", "tenant-digest": digest_of(spec.identity.tenant_id)[7:23], "sandbox-id": sandbox_id}},
                        "policyTypes": ["Ingress", "Egress"], "ingress": [],
                        "egress": [{"to": [{"ipBlock": {"cidr": destination}}]} for destination in sorted(set(egress_cidrs))],
                    },
                },
            )
            if spec.network.audit_sink_ref:
                audit = self.client.configure_network_audit(
                    namespace=self.namespace,
                    sandbox_id=sandbox_id,
                    sink_ref=spec.network.audit_sink_ref,
                    dns_logging=spec.network.dns_allowed,
                )
                if not bool(audit.get("accepted")):
                    raise NotConfigured("Kubernetes network audit configuration was not accepted")
        except Exception:
            if created:
                try:
                    self.client.delete_namespaced_pod(namespace=self.namespace, name=sandbox_id, grace_period_seconds=0, propagation_policy="Foreground")
                except Exception as cleanup_error:
                    raise LeaseLost("Kubernetes sandbox provisioning failed and orphan cleanup is unconfirmed") from cleanup_error
            raise
        self._specs[sandbox_id] = spec
        return sandbox_id

    def exec(self, backend_ref: str, request: SandboxExecRequest, secrets: Mapping[str, str]) -> SandboxExecResult:
        started = time.time()
        result = self.client.exec_namespaced_pod(
            namespace=self.namespace, name=backend_ref, argv=list(request.argv), cwd=request.cwd,
            env=dict(request.env), secret_values=dict(secrets),
            timeout_seconds=request.timeout_seconds,
        )
        return SandboxExecResult(int(result.get("exit_code", 1)), _bytes(result.get("stdout", b"")), _bytes(result.get("stderr", b"")), started, time.time(), bool(result.get("timed_out", False)))

    def snapshot(self, backend_ref: str) -> str:
        value = self.client.snapshot_namespaced_pod(namespace=self.namespace, name=backend_ref)
        reference = str(value["digest"])
        if not _sha256_digest(reference):
            raise ContractViolation("Kubernetes snapshot response is not digest-bound")
        return reference

    def restore(self, sandbox_id: str, snapshot_ref: str, spec: SandboxSpec) -> str:
        value = _required_mapping(
            self.client.restore_namespaced_pod(
                namespace=self.namespace,
                name=sandbox_id,
                snapshot_digest=snapshot_ref,
                tenant_id=spec.identity.tenant_id,
                run_id=spec.identity.run_id,
                spec=_spec_dict(spec),
            ),
            "Kubernetes restore",
        )
        if str(value.get("snapshot_digest", "")) != snapshot_ref or not bool(value.get("network_policy_attached", False)):
            raise TenantIsolationError("Kubernetes restore attestation is incomplete")
        reference = str(value.get("pod_name", ""))
        if not reference:
            raise ContractViolation("Kubernetes restore returned no pod identity")
        self._specs[reference] = spec
        return reference

    def stats(self, backend_ref: str) -> SandboxStats:
        value = self.client.pod_stats(namespace=self.namespace, name=backend_ref)
        return SandboxStats(float(value["cpu_seconds"]), int(value["memory_bytes"]), int(value["disk_bytes"]), int(value["pids"]), time.time())

    def destroy(self, backend_ref: str) -> None:
        self.client.delete_namespaced_pod(namespace=self.namespace, name=backend_ref, grace_period_seconds=0, propagation_policy="Foreground")
        self._specs.pop(backend_ref, None)

    def read_file(self, backend_ref: str, path: str, start: int, length: int | None) -> bytes:
        return _required_bytes(self.client.read_namespaced_pod_file(namespace=self.namespace, name=backend_ref, path=path, start=start, length=length), "Kubernetes read_file")

    def write_file(self, backend_ref: str, path: str, data: bytes, expected_digest: str | None, idempotency_key: str) -> Mapping[str, Any]:
        return _required_mapping(self.client.write_namespaced_pod_file(namespace=self.namespace, name=backend_ref, path=path, data=data, expected_digest=expected_digest, idempotency_key=idempotency_key), "Kubernetes write_file")

    def apply_patch(self, backend_ref: str, operations: list[Mapping[str, Any]], idempotency_key: str) -> Mapping[str, Any]:
        return _required_mapping(self.client.apply_namespaced_pod_patch(namespace=self.namespace, name=backend_ref, operations=operations, idempotency_key=idempotency_key), "Kubernetes apply_patch")

    def git(self, backend_ref: str, operation: str, args: list[str], idempotency_key: str | None) -> Mapping[str, Any]:
        return _required_mapping(self.client.git_namespaced_pod(namespace=self.namespace, name=backend_ref, operation=operation, args=args, idempotency_key=idempotency_key), "Kubernetes git")

    def expose_port(self, backend_ref: str, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        return _required_mapping(self.client.expose_namespaced_pod_port(namespace=self.namespace, name=backend_ref, spec=dict(spec)), "Kubernetes expose_port")


class FirecrackerSandboxBackend:
    name = "firecracker"
    supported_isolation = frozenset({IsolationClass.L3})

    def __init__(self, control_client: Any) -> None:
        self.client = control_client

    def create(self, sandbox_id: str, spec: SandboxSpec) -> str:
        value = _required_mapping(self.client.create_microvm(
            sandbox_id=sandbox_id, tenant_id=spec.identity.tenant_id, project_id=spec.identity.project_id,
            task_id=spec.identity.task_id, run_id=spec.identity.run_id, node_id=spec.identity.node_id, agent_id=spec.identity.agent_id,
            image_digest=spec.image_digest, vcpu=spec.quotas.cpu_cores, memory_mb=spec.quotas.memory_mb,
            disk_mb=spec.quotas.disk_mb, network_policy=asdict(spec.network), mounts=[asdict(mount) for mount in spec.mounts],
        ), "Firecracker create")
        reference = str(value.get("microvm_id", ""))
        if not reference or str(value.get("image_digest", "")) != spec.image_digest or str(value.get("isolation_class", "")) != IsolationClass.L3.value or not _response_identity_matches(value, spec.identity):
            raise TenantIsolationError("Firecracker creation attestation is incomplete")
        return reference

    def exec(self, backend_ref: str, request: SandboxExecRequest, secrets: Mapping[str, str]) -> SandboxExecResult:
        started = time.time()
        value = self.client.exec_microvm(microvm_id=backend_ref, argv=list(request.argv), cwd=request.cwd, env=dict(request.env), secrets=dict(secrets), timeout_seconds=request.timeout_seconds)
        return SandboxExecResult(int(value["exit_code"]), _bytes(value.get("stdout", b"")), _bytes(value.get("stderr", b"")), started, time.time(), bool(value.get("timed_out", False)))

    def snapshot(self, backend_ref: str) -> str:
        value = _required_mapping(self.client.snapshot_microvm(microvm_id=backend_ref), "Firecracker snapshot")
        reference = str(value.get("digest", ""))
        if not _sha256_digest(reference):
            raise ContractViolation("Firecracker snapshot is not content-addressed")
        return reference

    def restore(self, sandbox_id: str, snapshot_ref: str, spec: SandboxSpec) -> str:
        value = _required_mapping(self.client.restore_microvm(sandbox_id=sandbox_id, snapshot_digest=snapshot_ref, tenant_id=spec.identity.tenant_id, project_id=spec.identity.project_id, task_id=spec.identity.task_id, run_id=spec.identity.run_id, node_id=spec.identity.node_id, agent_id=spec.identity.agent_id), "Firecracker restore")
        reference = str(value.get("microvm_id", ""))
        if not reference or str(value.get("snapshot_digest", "")) != snapshot_ref or str(value.get("isolation_class", "")) != IsolationClass.L3.value or not _response_identity_matches(value, spec.identity):
            raise TenantIsolationError("Firecracker restore attestation is incomplete")
        return reference

    def stats(self, backend_ref: str) -> SandboxStats:
        value = self.client.microvm_stats(microvm_id=backend_ref)
        return SandboxStats(float(value["cpu_seconds"]), int(value["memory_bytes"]), int(value["disk_bytes"]), int(value["pids"]), time.time())

    def destroy(self, backend_ref: str) -> None:
        self.client.destroy_microvm(microvm_id=backend_ref)

    def read_file(self, backend_ref: str, path: str, start: int, length: int | None) -> bytes:
        return _required_bytes(self.client.read_microvm_file(microvm_id=backend_ref, path=path, start=start, length=length), "Firecracker read_file")

    def write_file(self, backend_ref: str, path: str, data: bytes, expected_digest: str | None, idempotency_key: str) -> Mapping[str, Any]:
        return _required_mapping(self.client.write_microvm_file(microvm_id=backend_ref, path=path, data=data, expected_digest=expected_digest, idempotency_key=idempotency_key), "Firecracker write_file")

    def apply_patch(self, backend_ref: str, operations: list[Mapping[str, Any]], idempotency_key: str) -> Mapping[str, Any]:
        return _required_mapping(self.client.apply_microvm_patch(microvm_id=backend_ref, operations=operations, idempotency_key=idempotency_key), "Firecracker apply_patch")

    def git(self, backend_ref: str, operation: str, args: list[str], idempotency_key: str | None) -> Mapping[str, Any]:
        return _required_mapping(self.client.git_microvm(microvm_id=backend_ref, operation=operation, args=args, idempotency_key=idempotency_key), "Firecracker git")

    def expose_port(self, backend_ref: str, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        return _required_mapping(self.client.expose_microvm_port(microvm_id=backend_ref, spec=dict(spec)), "Firecracker expose_port")


class SshEnterpriseSandboxBackend:
    """L4 enterprise/private environment through an attested control client.

    This adapter never shells out to a user-controlled SSH command. The
    deployment client owns host-key pinning, mTLS/SSH certificates, dedicated
    worker allocation and network enforcement and must return signed host
    attestations that the configured verifier accepts.
    """

    name = "ssh-enterprise"
    supported_isolation = frozenset({IsolationClass.L4})

    def __init__(self, control_client: Any, *, host_id: str, host_fingerprint: str, attestation_verifier: Callable[[Mapping[str, Any], str, SandboxSpec], bool]) -> None:
        if not host_id or not _sha256_digest(host_fingerprint):
            raise ContractViolation("enterprise host identity must be digest-pinned")
        self.client = control_client
        self.host_id = host_id
        self.host_fingerprint = host_fingerprint
        self.attestation_verifier = attestation_verifier

    def create(self, sandbox_id: str, spec: SandboxSpec) -> str:
        attestation = _required_mapping(self.client.host_attestation(host_id=self.host_id), "enterprise host attestation")
        if not self.attestation_verifier(attestation, self.host_fingerprint, spec):
            raise TenantIsolationError("enterprise host attestation or tenant dedication failed")
        value = _required_mapping(
            self.client.create_workspace(
                host_id=self.host_id,
                sandbox_id=sandbox_id,
                tenant_id=spec.identity.tenant_id,
                project_id=spec.identity.project_id,
                task_id=spec.identity.task_id,
                run_id=spec.identity.run_id,
                node_id=spec.identity.node_id,
                agent_id=spec.identity.agent_id,
                image_digest=spec.image_digest,
                quotas=asdict(spec.quotas),
                network_policy=asdict(spec.network),
                mounts=[asdict(item) for item in spec.mounts],
            ),
            "enterprise workspace create",
        )
        reference = str(value.get("workspace_id", ""))
        if (
            not reference
            or not bool(value.get("dedicated", False))
            or str(value.get("tenant_id", "")) != spec.identity.tenant_id
            or not _response_identity_matches(value, spec.identity)
            or str(value.get("image_digest", "")) != spec.image_digest
        ):
            raise TenantIsolationError("enterprise backend did not attest a dedicated workspace")
        return reference

    def exec(self, backend_ref: str, request: SandboxExecRequest, secrets: Mapping[str, str]) -> SandboxExecResult:
        started = time.time()
        value = _required_mapping(self.client.exec_workspace(workspace_id=backend_ref, argv=list(request.argv), cwd=request.cwd, env=dict(request.env), secret_values=dict(secrets), timeout_seconds=request.timeout_seconds), "enterprise workspace exec")
        return SandboxExecResult(int(value["exit_code"]), _bytes(value.get("stdout", b"")), _bytes(value.get("stderr", b"")), started, time.time(), bool(value.get("timed_out", False)))

    def snapshot(self, backend_ref: str) -> str:
        value = _required_mapping(self.client.snapshot_workspace(workspace_id=backend_ref), "enterprise workspace snapshot")
        reference = str(value.get("digest", ""))
        if not _sha256_digest(reference):
            raise ContractViolation("enterprise snapshot is not content-addressed")
        return reference

    def restore(self, sandbox_id: str, snapshot_ref: str, spec: SandboxSpec) -> str:
        attestation = _required_mapping(self.client.host_attestation(host_id=self.host_id), "enterprise host attestation")
        if not self.attestation_verifier(attestation, self.host_fingerprint, spec):
            raise TenantIsolationError("enterprise restore host attestation failed")
        value = _required_mapping(self.client.restore_workspace(host_id=self.host_id, sandbox_id=sandbox_id, tenant_id=spec.identity.tenant_id, project_id=spec.identity.project_id, task_id=spec.identity.task_id, run_id=spec.identity.run_id, node_id=spec.identity.node_id, agent_id=spec.identity.agent_id, snapshot_digest=snapshot_ref), "enterprise workspace restore")
        if (
            str(value.get("snapshot_digest", "")) != snapshot_ref
            or not bool(value.get("dedicated", False))
            or not _response_identity_matches(value, spec.identity)
        ):
            raise TenantIsolationError("enterprise restore attestation is incomplete")
        return str(value["workspace_id"])

    def stats(self, backend_ref: str) -> SandboxStats:
        value = _required_mapping(self.client.workspace_stats(workspace_id=backend_ref), "enterprise workspace stats")
        return SandboxStats(float(value["cpu_seconds"]), int(value["memory_bytes"]), int(value["disk_bytes"]), int(value["pids"]), time.time())

    def destroy(self, backend_ref: str) -> None:
        value = _required_mapping(self.client.destroy_workspace(workspace_id=backend_ref), "enterprise workspace destroy")
        if str(value.get("state", "")) not in {"destroyed", "absent"}:
            raise NotConfigured("enterprise workspace destruction was not acknowledged")

    def read_file(self, backend_ref: str, path: str, start: int, length: int | None) -> bytes:
        return _required_bytes(self.client.read_workspace_file(workspace_id=backend_ref, path=path, start=start, length=length), "enterprise read_file")

    def write_file(self, backend_ref: str, path: str, data: bytes, expected_digest: str | None, idempotency_key: str) -> Mapping[str, Any]:
        return _required_mapping(self.client.write_workspace_file(workspace_id=backend_ref, path=path, data=data, expected_digest=expected_digest, idempotency_key=idempotency_key), "enterprise write_file")

    def apply_patch(self, backend_ref: str, operations: list[Mapping[str, Any]], idempotency_key: str) -> Mapping[str, Any]:
        return _required_mapping(self.client.apply_workspace_patch(workspace_id=backend_ref, operations=operations, idempotency_key=idempotency_key), "enterprise apply_patch")

    def git(self, backend_ref: str, operation: str, args: list[str], idempotency_key: str | None) -> Mapping[str, Any]:
        return _required_mapping(self.client.git_workspace(workspace_id=backend_ref, operation=operation, args=args, idempotency_key=idempotency_key), "enterprise git")

    def expose_port(self, backend_ref: str, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        return _required_mapping(self.client.expose_workspace_port(workspace_id=backend_ref, spec=dict(spec)), "enterprise expose_port")


@dataclass(frozen=True, slots=True)
class WarmPoolPolicy:
    minimum_ready: int = 0
    maximum_ready: int = 10
    maximum_age_seconds: float = 3600.0

    def __post_init__(self) -> None:
        if self.minimum_ready < 0 or self.maximum_ready < self.minimum_ready or self.maximum_age_seconds <= 0:
            raise ContractViolation("sandbox warm-pool policy is invalid")


@dataclass(frozen=True, slots=True)
class WarmTemplate:
    template_id: str
    backend_ref: str
    image_digest: str
    isolation_class: IsolationClass
    region: str
    created_at: float
    state: str


class SandboxWarmPool:
    """Pools tenant-empty templates; tenant workspaces are never recycled."""

    def __init__(self, backend: Any, database: str = ":memory:", *, policy: WarmPoolPolicy | None = None) -> None:
        self.backend, self.policy = backend, policy if policy is not None else WarmPoolPolicy()
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("CREATE TABLE IF NOT EXISTS warm_templates(template_id TEXT PRIMARY KEY,backend_ref TEXT NOT NULL,image_digest TEXT NOT NULL,isolation_class TEXT NOT NULL,region TEXT NOT NULL,created_at REAL NOT NULL,state TEXT NOT NULL,scrub_receipt TEXT)")
        self._lock = threading.RLock()

    def close(self) -> None:
        self._connection.close()

    def reconcile(self, *, image_digest: str, isolation_class: IsolationClass, region: str, now: float | None = None) -> tuple[WarmTemplate, ...]:
        now = time.time() if now is None else now
        if not callable(getattr(self.backend, "prepare_tenant_empty_template", None)):
            raise NotConfigured("sandbox backend does not implement tenant-empty warm templates")
        with self._lock:
            expired = self._connection.execute("SELECT * FROM warm_templates WHERE state='ready' AND created_at<=?", (now - self.policy.maximum_age_seconds,)).fetchall()
            for row in expired:
                self.backend.destroy_template(template_ref=row["backend_ref"])
                self._connection.execute("UPDATE warm_templates SET state='destroyed' WHERE template_id=?", (row["template_id"],))
            rows = self._connection.execute("SELECT * FROM warm_templates WHERE state='ready' AND image_digest=? AND isolation_class=? AND region=? ORDER BY created_at", (image_digest, isolation_class.value, region)).fetchall()
            while len(rows) < self.policy.minimum_ready:
                template_id = "warm_" + new_id()
                value = self.backend.prepare_tenant_empty_template(template_id=template_id, image_digest=image_digest, isolation_class=isolation_class.value, region=region)
                if value.get("tenant_data_present") is not False or not _sha256_digest(str(value.get("attestation_digest", ""))):
                    raise ContractViolation("warm template lacks tenant-empty attestation")
                self._connection.execute("INSERT INTO warm_templates VALUES(?,?,?,?,?,?, 'ready',?)", (template_id, str(value["template_ref"]), image_digest, isolation_class.value, region, now, str(value["attestation_digest"])))
                rows = self._connection.execute("SELECT * FROM warm_templates WHERE state='ready' AND image_digest=? AND isolation_class=? AND region=? ORDER BY created_at", (image_digest, isolation_class.value, region)).fetchall()
            for row in rows[self.policy.maximum_ready :]:
                self.backend.destroy_template(template_ref=row["backend_ref"])
                self._connection.execute("UPDATE warm_templates SET state='destroyed' WHERE template_id=?", (row["template_id"],))
        return tuple(self._template(row) for row in rows[: self.policy.maximum_ready])

    def claim(self, spec: SandboxSpec, sandbox_id: str) -> str | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM warm_templates WHERE state='ready' AND image_digest=? AND isolation_class=? AND region=? ORDER BY created_at LIMIT 1", (spec.image_digest, spec.isolation_class.value, spec.region)).fetchone()
            if row is None:
                return None
            updated = self._connection.execute("UPDATE warm_templates SET state='claimed' WHERE template_id=? AND state='ready'", (row["template_id"],)).rowcount
            if updated != 1:
                return None
        value = self.backend.instantiate_from_template(template_ref=row["backend_ref"], sandbox_id=sandbox_id, tenant_id=spec.identity.tenant_id, project_id=spec.identity.project_id, task_id=spec.identity.task_id, run_id=spec.identity.run_id, node_id=spec.identity.node_id, agent_id=spec.identity.agent_id, network_policy=asdict(spec.network), quotas=asdict(spec.quotas))
        return str(value["sandbox_ref"])

    @staticmethod
    def _template(row: sqlite3.Row) -> WarmTemplate:
        return WarmTemplate(row["template_id"], row["backend_ref"], row["image_digest"], IsolationClass(row["isolation_class"]), row["region"], float(row["created_at"]), row["state"])


def _spec_dict(spec: SandboxSpec) -> dict[str, Any]:
    return {
        "identity": {"tenant_id": spec.identity.tenant_id, "project_id": spec.identity.project_id, "task_id": spec.identity.task_id, "run_id": spec.identity.run_id, "node_id": spec.identity.node_id, "agent_id": spec.identity.agent_id},
        "isolation_class": spec.isolation_class.value, "image_digest": spec.image_digest, "region": spec.region,
        "quotas": asdict(spec.quotas), "network": asdict(spec.network), "mounts": [asdict(mount) for mount in spec.mounts],
        "secret_refs": list(spec.secret_refs), "runtime_class": spec.runtime_class,
    }


def _response_identity_matches(value: Mapping[str, Any], identity: Identity) -> bool:
    stored = tuple(str(value.get(name, "")) for name in ("tenant_id", "project_id", "task_id", "run_id", "node_id"))
    agent_id = None if value.get("agent_id") is None else str(value["agent_id"])
    return stored == identity.scope() and agent_id == identity.agent_id


def _spec_from_dict(value: Mapping[str, Any]) -> SandboxSpec:
    return SandboxSpec(
        Identity(**dict(value["identity"])), IsolationClass(str(value["isolation_class"])), str(value["image_digest"]), str(value["region"]),
        SandboxQuotas(**dict(value["quotas"])), NetworkPolicy(**dict(value["network"])),
        tuple(MountSpec(**item) for item in value.get("mounts", ())), tuple(value.get("secret_refs", ())), value.get("runtime_class"),
    )


def _result_dict(result: SandboxExecResult) -> dict[str, Any]:
    return {"exit_code": result.exit_code, "stdout": result.stdout.hex(), "stderr": result.stderr.hex(), "started_at": result.started_at, "finished_at": result.finished_at, "timed_out": result.timed_out, "cancelled": result.cancelled}


def _exec_result(value: Mapping[str, Any]) -> SandboxExecResult:
    return SandboxExecResult(int(value["exit_code"]), bytes.fromhex(str(value["stdout"])), bytes.fromhex(str(value["stderr"])), float(value["started_at"]), float(value["finished_at"]), bool(value.get("timed_out", False)), bool(value.get("cancelled", False)))


def _subprocess_runner(command: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(command, 124, error.stdout or b"", error.stderr or b"timeout")


def _bounded_text(value: Any) -> str:
    return _bytes(value).decode("utf-8", errors="replace")[:2000]


def _bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")


def _parse_bytes(value: str) -> int:
    text = value.strip().upper()
    units = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3}
    for suffix in sorted(units, key=len, reverse=True):
        if text.endswith(suffix):
            return int(float(text[: -len(suffix)].strip()) * units[suffix])
    return int(float(text or "0"))


def _required_bytes(value: Any, operation: str) -> bytes:
    if not isinstance(value, bytes):
        raise ContractViolation(operation + " returned non-bytes")
    return value


def _required_mapping(value: Any, operation: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractViolation(operation + " returned a non-object")
    return dict(value)


def _sha256_digest(value: str) -> bool:
    return len(value) == 71 and value.startswith("sha256:") and all(character in "0123456789abcdef" for character in value[7:])


def _redact_secret_bytes(value: bytes, secrets: tuple[str, ...]) -> bytes:
    variants: set[bytes] = set()
    for secret in secrets:
        if not secret:
            continue
        raw = secret.encode("utf-8")
        variants.update(
            {
                raw,
                urllib.parse.quote(secret, safe="").encode("ascii"),
                urllib.parse.quote_plus(secret, safe="").encode("ascii"),
                base64.b64encode(raw),
                base64.urlsafe_b64encode(raw),
                raw.hex().encode("ascii"),
            }
        )
    for encoded in sorted(variants, key=len, reverse=True):
        value = value.replace(encoded, b"[REDACTED_SECRET]")
    return value
