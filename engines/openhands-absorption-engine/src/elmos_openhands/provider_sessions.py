"""Stateful provider sessions, streaming normalization and routed shadow eval."""

from __future__ import annotations

import json
import re
import sqlite3
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from .errors import (
    ContractViolation,
    CorruptState,
    IdempotencyConflict,
    LeaseLost,
    NotConfigured,
    TenantIsolationError,
)
from .models import Identity, Usage, canonical_json, digest_of, new_id
from .providers import ProviderCapabilities, ProviderRequest, RouteConstraints


@dataclass(frozen=True, slots=True)
class ProviderSession:
    session_id: str
    identity: Identity
    provider: str
    model: str
    region: str
    state: str
    remote_session_id: str
    fencing_token: str
    capabilities_digest: str
    created_at: float
    updated_at: float


@dataclass(frozen=True, slots=True)
class ProviderCheckpoint:
    provider: str
    remote_session_id: str
    payload: Mapping[str, Any]
    manifest_digest: str
    sequence: int
    digest: str

    def __post_init__(self) -> None:
        body = {
            "provider": self.provider,
            "remote_session_id": self.remote_session_id,
            "payload": dict(self.payload),
            "manifest_digest": self.manifest_digest,
            "sequence": self.sequence,
        }
        if not self.provider or not self.remote_session_id or self.sequence < -1:
            raise ContractViolation("provider checkpoint identity/sequence is invalid")
        if not _sha256_digest(self.manifest_digest) or not _sha256_digest(self.digest) or digest_of(body) != self.digest:
            raise ContractViolation("provider checkpoint digest binding is invalid")


@dataclass(frozen=True, slots=True)
class NormalizedProviderEvent:
    sequence: int
    kind: str
    payload: Mapping[str, Any]
    usage: Usage = field(default_factory=Usage)
    terminal: bool = False
    provider_event_id: str | None = None

    def __post_init__(self) -> None:
        if self.sequence < 0 or self.kind not in {"text_delta", "reasoning_delta", "action", "completion", "usage", "checkpoint", "error", "heartbeat"}:
            raise ContractViolation("provider event contract is invalid")


class SessionTransport(Protocol):
    def request(self, provider: str, operation: str, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def stream(self, provider: str, operation: str, payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]: ...


class HttpJsonSseTransport:
    """TLS HTTP/JSON + SSE transport with short-lived token callback."""

    def __init__(
        self,
        endpoints: Mapping[str, str],
        token_provider: Callable[[str, Identity, str], str],
        *,
        timeout_seconds: float = 60.0,
        max_response_bytes: int = 16_777_216,
        max_events: int = 100_000,
        ssl_context: ssl.SSLContext | None = None,
        opener: Any | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_response_bytes < 1024 or max_events < 1:
            raise ContractViolation("provider HTTP timeout and response limits must be positive")
        self.endpoints = {name: _validated_endpoint(value) for name, value in endpoints.items()}
        self.token_provider = token_provider
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_events = max_events
        self.ssl_context = ssl_context or ssl.create_default_context()
        self.opener = opener or urllib.request.build_opener(_NoRedirectHandler(), urllib.request.HTTPSHandler(context=self.ssl_context))

    def request(self, provider: str, operation: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        response = self._open(provider, operation, payload, accept="application/json")
        try:
            raw = response.read(self.max_response_bytes + 1)
            if len(raw) > self.max_response_bytes:
                raise ContractViolation("provider JSON response exceeds the configured limit")
            value = json.loads(raw)
        finally:
            response.close()
        if not isinstance(value, Mapping):
            raise ContractViolation("provider response is not a JSON object")
        return dict(value)

    def stream(self, provider: str, operation: str, payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
        response = self._open(provider, operation, payload, accept="text/event-stream")
        try:
            data_lines: list[str] = []
            total_bytes = 0
            event_count = 0
            for raw in response:
                total_bytes += len(raw)
                if total_bytes > self.max_response_bytes:
                    raise ContractViolation("provider stream exceeds the configured byte limit")
                line = raw.decode("utf-8", errors="strict").rstrip("\r\n")
                if line == "":
                    if data_lines:
                        value = json.loads("\n".join(data_lines))
                        if not isinstance(value, Mapping):
                            raise ContractViolation("provider SSE event is not an object")
                        event_count += 1
                        if event_count > self.max_events:
                            raise ContractViolation("provider stream exceeds the configured event limit")
                        yield dict(value)
                        data_lines.clear()
                    continue
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
            if data_lines:
                value = json.loads("\n".join(data_lines))
                if not isinstance(value, Mapping):
                    raise ContractViolation("provider SSE event is not an object")
                event_count += 1
                if event_count > self.max_events:
                    raise ContractViolation("provider stream exceeds the configured event limit")
                yield dict(value)
        finally:
            response.close()

    def _open(self, provider: str, operation: str, payload: Mapping[str, Any], *, accept: str) -> Any:
        endpoint = self.endpoints.get(provider)
        if endpoint is None:
            raise NotConfigured("provider endpoint is not configured")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_-]{0,255}", operation) or ".." in operation.split("/"):
            raise ContractViolation("provider operation path is invalid")
        raw_identity = payload.get("identity")
        if not isinstance(raw_identity, Mapping):
            raise ContractViolation("provider transport payload requires authenticated identity scope")
        identity = Identity(
            str(raw_identity.get("tenant_id", "")),
            str(raw_identity.get("project_id", "")),
            str(raw_identity.get("task_id", "")),
            str(raw_identity.get("run_id", "")),
            str(raw_identity.get("node_id", "root")),
            None if raw_identity.get("agent_id") is None else str(raw_identity["agent_id"]),
        )
        token = self.token_provider(provider, identity, operation)
        if not token:
            raise NotConfigured("provider credential lease is unavailable")
        body = canonical_json(dict(payload)).encode("utf-8")
        request = urllib.request.Request(
            f"{endpoint}/{operation.lstrip('/')}", data=body, method="POST",
            headers={"Content-Type": "application/json", "Accept": accept, "Authorization": "Bearer " + token, "User-Agent": "elmos-openhands/1.0"},
        )
        try:
            response = self.opener.open(request, timeout=self.timeout_seconds)
            effective = urllib.parse.urlsplit(str(response.geturl()))
            configured = urllib.parse.urlsplit(endpoint)
            if (effective.scheme, effective.hostname, effective.port) != (configured.scheme, configured.hostname, configured.port):
                response.close()
                raise ProviderTransportError(0, None, "cross-origin provider redirect was rejected")
            return response
        except urllib.error.HTTPError as error:
            retry_after = error.headers.get("Retry-After") if error.headers else None
            raise ProviderTransportError(error.code, retry_after, error.read(2048).decode("utf-8", errors="replace")) from error
        except urllib.error.URLError as error:
            raise ProviderTransportError(0, None, str(error.reason)) from error


class ProviderTransportError(RuntimeError):
    def __init__(self, status_code: int, retry_after: str | None, detail: str) -> None:
        super().__init__(f"provider transport failed ({status_code}): {detail[:500]}")
        self.status_code = status_code
        self.retry_after = retry_after
        self.retryable = status_code in {0, 408, 409, 425, 429} or 500 <= status_code < 600


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class SessionProviderAdapter(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities: ...
    def start(self, request: ProviderRequest) -> Mapping[str, Any]: ...
    def send(self, remote_session_id: str, request: ProviderRequest, *, after_sequence: int) -> Iterable[NormalizedProviderEvent]: ...
    def checkpoint(self, remote_session_id: str) -> Mapping[str, Any]: ...
    def resume(self, checkpoint: ProviderCheckpoint) -> Mapping[str, Any]: ...
    def cancel(self, remote_session_id: str, reason: str) -> None: ...
    def collect_usage(self, remote_session_id: str) -> Usage: ...


class JsonSessionProviderAdapter:
    """Common contract used by Codex, Claude, OpenHands and ACP providers."""

    def __init__(self, provider: str, transport: SessionTransport, capabilities: ProviderCapabilities) -> None:
        if capabilities.provider != provider:
            raise ContractViolation("provider capability identity mismatch")
        self.provider = provider
        self.transport = transport
        self._capabilities = capabilities

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def start(self, request: ProviderRequest) -> Mapping[str, Any]:
        value = self.transport.request(self.provider, "sessions/start", _request_body(request))
        if not value.get("session_id"):
            raise ContractViolation("provider start returned no session id")
        return value

    def send(self, remote_session_id: str, request: ProviderRequest, *, after_sequence: int) -> Iterable[NormalizedProviderEvent]:
        expected = after_sequence + 1
        for raw in self.transport.stream(self.provider, "sessions/send", {**_request_body(request), "session_id": remote_session_id, "after_sequence": after_sequence}):
            event = self.normalize_event(raw)
            if event.sequence < expected:
                continue
            if event.sequence != expected:
                raise ContractViolation("provider stream has a sequence gap")
            expected += 1
            yield event

    def checkpoint(self, remote_session_id: str) -> Mapping[str, Any]:
        return self.transport.request(self.provider, "sessions/checkpoint", {"session_id": remote_session_id})

    def resume(self, checkpoint: ProviderCheckpoint) -> Mapping[str, Any]:
        return self.transport.request(self.provider, "sessions/resume", {"checkpoint": dict(checkpoint.payload), "digest": checkpoint.digest, "manifest_digest": checkpoint.manifest_digest})

    def cancel(self, remote_session_id: str, reason: str) -> None:
        if not reason:
            raise ContractViolation("provider cancellation reason is required")
        value = self.transport.request(self.provider, "sessions/cancel", {"session_id": remote_session_id, "reason": reason})
        if value.get("status") not in {"cancelled", "already_terminal"}:
            raise ContractViolation("provider did not acknowledge cancellation")

    def collect_usage(self, remote_session_id: str) -> Usage:
        value = self.transport.request(self.provider, "sessions/usage", {"session_id": remote_session_id})
        return Usage(**dict(value.get("usage", value)))

    @staticmethod
    def normalize_event(raw: Mapping[str, Any]) -> NormalizedProviderEvent:
        kind_map = {"message.delta": "text_delta", "reasoning.delta": "reasoning_delta", "tool.call": "action", "done": "completion", "rate_usage": "usage", "session.checkpoint": "checkpoint", "fault": "error", "ping": "heartbeat"}
        kind = kind_map.get(str(raw.get("type")), str(raw.get("kind", raw.get("type", ""))))
        return NormalizedProviderEvent(
            int(raw["sequence"]), kind, dict(raw.get("payload", {})), Usage(**dict(raw.get("usage", {}))),
            bool(raw.get("terminal", kind in {"completion", "error"})), None if raw.get("event_id") is None else str(raw["event_id"]),
        )


def codex_session_adapter(transport: SessionTransport) -> JsonSessionProviderAdapter:
    return JsonSessionProviderAdapter("codex", transport, ProviderCapabilities("codex", supports_checkpoints=True, supports_streaming=True, supports_browser=True, supports_mcp_acp=True, reasoning_visibility="summary", max_parallelism=8, external_network_required=True, regions=frozenset({"us", "eu", "local"}), privacy_classes=frozenset({"public", "internal", "confidential"})))


def claude_session_adapter(transport: SessionTransport) -> JsonSessionProviderAdapter:
    return JsonSessionProviderAdapter("claude", transport, ProviderCapabilities("claude", supports_checkpoints=False, supports_streaming=True, supports_browser=True, supports_mcp_acp=True, reasoning_visibility="summary", max_parallelism=4, external_network_required=True, regions=frozenset({"us", "eu"}), privacy_classes=frozenset({"public", "internal", "confidential"})))


def openhands_session_adapter(transport: SessionTransport) -> JsonSessionProviderAdapter:
    return JsonSessionProviderAdapter("openhands", transport, ProviderCapabilities("openhands", supports_checkpoints=True, supports_streaming=True, supports_browser=True, supports_mcp_acp=True, reasoning_visibility="full", max_parallelism=8, regions=frozenset({"local", "us", "eu"}), privacy_classes=frozenset({"public", "internal", "confidential", "restricted"})))


def opencode_session_adapter(transport: SessionTransport) -> JsonSessionProviderAdapter:
    return JsonSessionProviderAdapter("opencode", transport, ProviderCapabilities("opencode", supports_checkpoints=True, supports_streaming=True, supports_mcp_acp=True, reasoning_visibility="summary", max_parallelism=4, regions=frozenset({"local"}), privacy_classes=frozenset({"public", "internal", "confidential", "restricted"})))


def gemini_session_adapter(transport: SessionTransport) -> JsonSessionProviderAdapter:
    return JsonSessionProviderAdapter("gemini", transport, ProviderCapabilities("gemini", supports_checkpoints=False, supports_streaming=True, supports_browser=False, supports_mcp_acp=True, reasoning_visibility="hidden", max_parallelism=4, external_network_required=True, regions=frozenset({"us", "eu", "asia"}), privacy_classes=frozenset({"public", "internal", "confidential"})))


def junie_session_adapter(transport: SessionTransport) -> JsonSessionProviderAdapter:
    return JsonSessionProviderAdapter("junie", transport, ProviderCapabilities("junie", supports_checkpoints=True, supports_streaming=True, supports_browser=False, supports_mcp_acp=True, reasoning_visibility="summary", max_parallelism=2, external_network_required=True, regions=frozenset({"us", "eu"}), privacy_classes=frozenset({"public", "internal"})))


class ProviderSessionManager:
    def __init__(self, adapters: Iterable[SessionProviderAdapter], database: str = ":memory:") -> None:
        self.adapters = {adapter.capabilities.provider: adapter for adapter in adapters}
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """CREATE TABLE IF NOT EXISTS provider_sessions(session_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,node_id TEXT NOT NULL,agent_id TEXT,provider TEXT NOT NULL,model TEXT NOT NULL,region TEXT NOT NULL,state TEXT NOT NULL,remote_session_id TEXT NOT NULL,fencing_token TEXT NOT NULL,capabilities_digest TEXT NOT NULL,last_sequence INTEGER NOT NULL DEFAULT -1,checkpoint_json TEXT,usage_json TEXT NOT NULL DEFAULT '{}',created_at REAL NOT NULL,updated_at REAL NOT NULL);
               CREATE TABLE IF NOT EXISTS provider_events(tenant_id TEXT NOT NULL,session_id TEXT NOT NULL,sequence INTEGER NOT NULL,event_json TEXT NOT NULL,event_digest TEXT NOT NULL,PRIMARY KEY(tenant_id,session_id,sequence));
               CREATE TABLE IF NOT EXISTS provider_operations(tenant_id TEXT NOT NULL,operation_scope TEXT NOT NULL,operation TEXT NOT NULL,idempotency_key TEXT NOT NULL,request_digest TEXT NOT NULL,state TEXT NOT NULL,result_json TEXT,fencing_token TEXT NOT NULL,lease_expires_at REAL NOT NULL,updated_at REAL NOT NULL,PRIMARY KEY(tenant_id,operation_scope,operation,idempotency_key));"""
        )
        self._lock = threading.RLock()

    def close(self) -> None:
        self._connection.close()

    def start(self, provider: str, request: ProviderRequest, *, region: str) -> ProviderSession:
        adapter = self._adapter(provider)
        if region not in adapter.capabilities.regions:
            raise ContractViolation("provider region is unsupported")
        operation_scope = f"run:{request.identity.run_id}:{request.identity.node_id}"
        request_digest = digest_of({"provider": provider, "region": region, "request": _request_body(request)})
        fencing, cached = self._claim_operation(request.identity, operation_scope, "start", request.idempotency_key, request_digest)
        if cached is not None:
            return self._load_session(request.identity, str(cached["session_id"]))
        value = adapter.start(request)
        if not value.get("session_id"):
            raise ContractViolation("provider start returned no session id")
        session_id = new_id()
        now = time.time()
        session = ProviderSession(session_id, request.identity, provider, request.model, region, "active", str(value["session_id"]), new_id(), _capabilities_digest(adapter.capabilities), now, now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute("INSERT INTO provider_sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?, -1,NULL,'{}',?,?)", (session.session_id, *request.identity.scope(), request.identity.agent_id, provider, request.model, region, session.state, session.remote_session_id, session.fencing_token, session.capabilities_digest, now, now))
                self._finish_operation(request.identity.tenant_id, operation_scope, "start", request.idempotency_key, fencing, {"session_id": session.session_id})
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return session

    def send(self, session: ProviderSession, request: ProviderRequest) -> tuple[NormalizedProviderEvent, ...]:
        current, last_sequence = self._assert(session, allow_terminal=True)
        if request.identity.scope() != current.identity.scope():
            raise TenantIsolationError("provider request scope does not match session")
        adapter = self._adapter(session.provider)
        request_digest = digest_of({"session_id": session.session_id, "request": _request_body(request)})
        terminal_replay = self._completed_operation(session.identity, session.session_id, "send", request.idempotency_key, request_digest)
        if current.state != "active":
            if terminal_replay is not None:
                return tuple(_normalized_event(item) for item in terminal_replay.get("events", ()))
            raise LeaseLost("provider session is terminal and cannot accept a new send")
        fencing, cached = self._claim_operation(session.identity, session.session_id, "send", request.idempotency_key, request_digest)
        if cached is not None:
            return tuple(_normalized_event(item) for item in cached.get("events", ()))
        rows = tuple(adapter.send(session.remote_session_id, request, after_sequence=last_sequence))
        terminal_positions = [index for index, event in enumerate(rows) if event.terminal]
        if len(terminal_positions) > 1 or (terminal_positions and terminal_positions[0] != len(rows) - 1):
            raise ContractViolation("provider terminal event must be unique and last in the stream")
        expected = last_sequence
        added_usage = Usage()
        for event in rows:
            if event.sequence != last_sequence + 1:
                raise ContractViolation("provider session event stream is not contiguous")
            last_sequence = event.sequence
            added_usage = _add_usage(added_usage, event.usage)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                stored = self._connection.execute("SELECT last_sequence,usage_json,state FROM provider_sessions WHERE session_id=? AND fencing_token=?", (session.session_id, session.fencing_token)).fetchone()
                if stored is None or int(stored["last_sequence"]) != expected or stored["state"] != "active":
                    raise LeaseLost("provider session sequence was concurrently advanced")
                for event in rows:
                    body = _event_dict(event)
                    self._connection.execute("INSERT INTO provider_events VALUES(?,?,?,?,?)", (session.identity.tenant_id, session.session_id, event.sequence, canonical_json(body), digest_of(body)))
                prior_usage = Usage(**dict(json.loads(stored["usage_json"] or "{}")))
                usage = _add_usage(prior_usage, added_usage)
                terminal_state = "active"
                if any(event.terminal and event.kind == "completion" for event in rows):
                    terminal_state = "completed"
                elif any(event.terminal and event.kind == "error" for event in rows):
                    terminal_state = "failed"
                self._connection.execute("UPDATE provider_sessions SET last_sequence=?,usage_json=?,state=?,updated_at=? WHERE session_id=? AND fencing_token=?", (last_sequence, canonical_json(usage.as_dict()), terminal_state, time.time(), session.session_id, session.fencing_token))
                self._finish_operation(session.identity.tenant_id, session.session_id, "send", request.idempotency_key, fencing, {"events": [_event_dict(item) for item in rows]})
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return rows

    def checkpoint(self, session: ProviderSession, *, manifest_digest: str, idempotency_key: str) -> ProviderCheckpoint:
        current, sequence = self._assert(session, allow_terminal=True)
        adapter = self._adapter(session.provider)
        if not adapter.capabilities.supports_checkpoints:
            raise NotConfigured("provider does not support checkpoints")
        # The exact idempotent request is independent of later stream progress;
        # the resulting checkpoint remains sequence-bound in its signed digest.
        request_digest = digest_of({"session_id": session.session_id, "manifest_digest": manifest_digest})
        terminal_replay = self._completed_operation(session.identity, session.session_id, "checkpoint", idempotency_key, request_digest)
        if current.state != "active":
            if terminal_replay is not None:
                return _provider_checkpoint(terminal_replay)
            raise LeaseLost("provider session is terminal and cannot create a new checkpoint")
        fencing, cached = self._claim_operation(session.identity, session.session_id, "checkpoint", idempotency_key, request_digest)
        if cached is not None:
            return _provider_checkpoint(cached)
        payload = dict(adapter.checkpoint(session.remote_session_id))
        body = {"provider": session.provider, "remote_session_id": session.remote_session_id, "payload": payload, "manifest_digest": manifest_digest, "sequence": sequence}
        checkpoint = ProviderCheckpoint(session.provider, session.remote_session_id, payload, manifest_digest, sequence, digest_of(body))
        result = {**body, "digest": checkpoint.digest}
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                updated = self._connection.execute("UPDATE provider_sessions SET checkpoint_json=?,updated_at=? WHERE session_id=? AND fencing_token=? AND last_sequence=? AND state='active'", (canonical_json(result), time.time(), session.session_id, session.fencing_token, sequence)).rowcount
                if updated != 1:
                    raise LeaseLost("provider checkpoint lost session fencing")
                self._finish_operation(session.identity.tenant_id, session.session_id, "checkpoint", idempotency_key, fencing, result)
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return checkpoint

    def resume(self, identity: Identity, checkpoint: ProviderCheckpoint, *, model: str, region: str, idempotency_key: str) -> ProviderSession:
        body = {"provider": checkpoint.provider, "remote_session_id": checkpoint.remote_session_id, "payload": dict(checkpoint.payload), "manifest_digest": checkpoint.manifest_digest, "sequence": checkpoint.sequence}
        if digest_of(body) != checkpoint.digest:
            raise ContractViolation("provider checkpoint digest is invalid")
        adapter = self._adapter(checkpoint.provider)
        if region not in adapter.capabilities.regions:
            raise ContractViolation("provider resume region is unsupported")
        operation_scope = f"resume:{identity.run_id}:{identity.node_id}:{checkpoint.digest}"
        request_digest = digest_of({"identity": identity.scope(), "checkpoint": body, "model": model, "region": region})
        fencing, cached = self._claim_operation(identity, operation_scope, "resume", idempotency_key, request_digest)
        if cached is not None:
            return self._load_session(identity, str(cached["session_id"]))
        value = adapter.resume(checkpoint)
        if not value.get("session_id"):
            raise ContractViolation("provider resume returned no session id")
        now = time.time()
        session = ProviderSession(new_id(), identity, checkpoint.provider, model, region, "active", str(value["session_id"]), new_id(), _capabilities_digest(adapter.capabilities), now, now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute("INSERT INTO provider_sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (session.session_id, *identity.scope(), identity.agent_id, session.provider, model, region, session.state, session.remote_session_id, session.fencing_token, session.capabilities_digest, checkpoint.sequence, canonical_json({**body, "digest": checkpoint.digest}), '{}', now, now))
                self._finish_operation(identity.tenant_id, operation_scope, "resume", idempotency_key, fencing, {"session_id": session.session_id})
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return session

    def resume_state(self, identity: Identity, state: Mapping[str, Any]) -> ProviderSession:
        checkpoint = ProviderCheckpoint(str(state["provider"]), str(state["remote_session_id"]), dict(state["payload"]), str(state["manifest_digest"]), int(state["sequence"]), str(state["digest"]))
        return self.resume(identity, checkpoint, model=str(state["model"]), region=str(state["region"]), idempotency_key="resume:" + checkpoint.digest)

    def cancel(self, session: ProviderSession, reason: str, *, idempotency_key: str) -> None:
        current, _ = self._assert(session, allow_terminal=True)
        request_digest = digest_of({"session_id": session.session_id, "reason": reason})
        terminal_replay = self._completed_operation(session.identity, session.session_id, "cancel", idempotency_key, request_digest)
        if current.state != "active":
            if terminal_replay is not None:
                return
            raise LeaseLost("provider session is terminal and cannot accept a new cancellation")
        fencing, cached = self._claim_operation(session.identity, session.session_id, "cancel", idempotency_key, request_digest)
        if cached is not None:
            return
        self._adapter(session.provider).cancel(session.remote_session_id, reason)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                updated = self._connection.execute("UPDATE provider_sessions SET state='cancelled',updated_at=? WHERE session_id=? AND fencing_token=? AND state='active'", (time.time(), session.session_id, session.fencing_token)).rowcount
                if updated != 1:
                    raise LeaseLost("provider cancellation lost session fencing")
                self._finish_operation(session.identity.tenant_id, session.session_id, "cancel", idempotency_key, fencing, {"status": "cancelled"})
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def usage(self, session: ProviderSession) -> Usage:
        current, _ = self._assert(session, allow_terminal=True)
        usage = self._adapter(session.provider).collect_usage(session.remote_session_id)
        recorded = self.recorded_usage(session)
        if (
            usage.input_tokens < recorded.input_tokens
            or usage.output_tokens < recorded.output_tokens
            or usage.cost_micros < recorded.cost_micros
        ):
            raise CorruptState("provider usage reconciliation regressed below streamed usage")
        with self._lock:
            updated = self._connection.execute(
                "UPDATE provider_sessions SET usage_json=?,updated_at=? WHERE session_id=? AND tenant_id=? AND fencing_token=?",
                (canonical_json(usage.as_dict()), time.time(), session.session_id, current.identity.tenant_id, current.fencing_token),
            ).rowcount
        if updated != 1:
            raise LeaseLost("provider usage reconciliation lost session fencing")
        return usage

    def recorded_usage(self, session: ProviderSession) -> Usage:
        self._assert(session, allow_terminal=True)
        row = self._connection.execute("SELECT usage_json FROM provider_sessions WHERE session_id=?", (session.session_id,)).fetchone()
        if row is None:
            raise CorruptState("provider session usage is unavailable")
        try:
            value = json.loads(row["usage_json"] or "{}")
            return Usage(**dict(value))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise CorruptState("provider session usage is corrupt") from error

    def _assert(self, session: ProviderSession, *, allow_terminal: bool = False) -> tuple[ProviderSession, int]:
        row = self._connection.execute("SELECT * FROM provider_sessions WHERE session_id=?", (session.session_id,)).fetchone()
        if row is None:
            raise TenantIsolationError("provider session scope/fencing mismatch")
        current = self._session(row)
        if current.identity.scope() != session.identity.scope() or current.identity.agent_id != session.identity.agent_id or current.fencing_token != session.fencing_token:
            raise TenantIsolationError("provider session scope/fencing mismatch")
        if not allow_terminal and row["state"] != "active":
            raise LeaseLost("provider session is not active")
        return current, int(row["last_sequence"])

    def _adapter(self, provider: str) -> SessionProviderAdapter:
        adapter = self.adapters.get(provider)
        if adapter is None:
            raise NotConfigured("provider adapter is not registered")
        return adapter

    def _claim_operation(
        self,
        identity: Identity,
        operation_scope: str,
        operation: str,
        idempotency_key: str | None,
        request_digest: str,
        *,
        lease_seconds: float = 120.0,
    ) -> tuple[str, Mapping[str, Any] | None]:
        if not idempotency_key:
            raise ContractViolation("provider mutation requires an idempotency key")
        now = time.time()
        fencing = new_id()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute("SELECT * FROM provider_operations WHERE tenant_id=? AND operation_scope=? AND operation=? AND idempotency_key=?", (identity.tenant_id, operation_scope, operation, idempotency_key)).fetchone()
                if row is None:
                    self._connection.execute("INSERT INTO provider_operations VALUES(?,?,?,?,?,'pending',NULL,?,?,?)", (identity.tenant_id, operation_scope, operation, idempotency_key, request_digest, fencing, now + lease_seconds, now))
                    self._connection.execute("COMMIT")
                    return fencing, None
                if row["request_digest"] != request_digest:
                    raise IdempotencyConflict("provider idempotency key was reused with another request")
                if row["state"] == "completed":
                    value = json.loads(row["result_json"] or "{}")
                    if not isinstance(value, Mapping):
                        raise CorruptState("provider operation result is corrupt")
                    self._connection.execute("COMMIT")
                    return str(row["fencing_token"]), dict(value)
                if float(row["lease_expires_at"]) > now:
                    raise LeaseLost("provider operation is already in flight")
                updated = self._connection.execute("UPDATE provider_operations SET fencing_token=?,lease_expires_at=?,updated_at=? WHERE tenant_id=? AND operation_scope=? AND operation=? AND idempotency_key=? AND fencing_token=?", (fencing, now + lease_seconds, now, identity.tenant_id, operation_scope, operation, idempotency_key, row["fencing_token"])).rowcount
                if updated != 1:
                    raise LeaseLost("provider operation lease was concurrently claimed")
                self._connection.execute("COMMIT")
                return fencing, None
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def _completed_operation(
        self,
        identity: Identity,
        operation_scope: str,
        operation: str,
        idempotency_key: str | None,
        request_digest: str,
    ) -> Mapping[str, Any] | None:
        """Return an exact completed replay without creating a terminal-session journal row."""

        if not idempotency_key:
            raise ContractViolation("provider mutation requires an idempotency key")
        with self._lock:
            row = self._connection.execute(
                "SELECT request_digest,state,result_json FROM provider_operations WHERE tenant_id=? AND operation_scope=? AND operation=? AND idempotency_key=?",
                (identity.tenant_id, operation_scope, operation, idempotency_key),
            ).fetchone()
            if row is None:
                return None
            if row["request_digest"] != request_digest:
                raise IdempotencyConflict("provider idempotency key was reused with another request")
            if row["state"] != "completed":
                return None
            value = json.loads(row["result_json"] or "{}")
            if not isinstance(value, Mapping):
                raise CorruptState("provider operation result is corrupt")
            return dict(value)

    def _finish_operation(self, tenant_id: str, operation_scope: str, operation: str, idempotency_key: str | None, fencing: str, result: Mapping[str, Any]) -> None:
        updated = self._connection.execute("UPDATE provider_operations SET state='completed',result_json=?,lease_expires_at=0,updated_at=? WHERE tenant_id=? AND operation_scope=? AND operation=? AND idempotency_key=? AND fencing_token=? AND state='pending'", (canonical_json(dict(result)), time.time(), tenant_id, operation_scope, operation, idempotency_key, fencing)).rowcount
        if updated != 1:
            raise LeaseLost("provider operation journal lost fencing ownership")

    def _load_session(self, identity: Identity, session_id: str) -> ProviderSession:
        row = self._connection.execute("SELECT * FROM provider_sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise CorruptState("completed provider operation references a missing session")
        session = self._session(row)
        if session.identity.scope() != identity.scope():
            raise TenantIsolationError("provider operation session belongs to another scope")
        return session

    @staticmethod
    def _session(row: sqlite3.Row) -> ProviderSession:
        identity = Identity(row["tenant_id"], row["project_id"], row["task_id"], row["run_id"], row["node_id"], row["agent_id"])
        return ProviderSession(row["session_id"], identity, row["provider"], row["model"], row["region"], row["state"], row["remote_session_id"], row["fencing_token"], row["capabilities_digest"], float(row["created_at"]), float(row["updated_at"]))


@dataclass(frozen=True, slots=True)
class ProviderScore:
    provider: str
    benchmark: float
    cost_micros: int
    latency_ms: int
    failure_rate: float
    sample_count: int


class BenchmarkAwareSessionRouter:
    def __init__(self, adapters: Iterable[SessionProviderAdapter], scores: Iterable[ProviderScore]) -> None:
        self.adapters = {adapter.capabilities.provider: adapter for adapter in adapters}
        self.scores = {score.provider: score for score in scores}
        self._failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}
        self._lock = threading.RLock()

    def choose(self, constraints: RouteConstraints) -> SessionProviderAdapter:
        candidates: list[tuple[float, str, SessionProviderAdapter]] = []
        for name, adapter in self.adapters.items():
            caps = adapter.capabilities
            score = self.scores.get(name)
            if score is None or score.sample_count < 1 or score.benchmark < constraints.benchmark_floor:
                continue
            if constraints.allowed_providers and name not in constraints.allowed_providers:
                continue
            if constraints.required_region not in caps.regions or constraints.privacy_class not in caps.privacy_classes:
                continue
            if constraints.require_checkpoint and not caps.supports_checkpoints:
                continue
            if constraints.max_cost_micros is not None and score.cost_micros > constraints.max_cost_micros:
                continue
            if constraints.max_latency_ms is not None and score.latency_ms > constraints.max_latency_ms:
                continue
            if self._open_until.get(name, 0) > time.time():
                continue
            utility = score.benchmark - score.failure_rate - (score.cost_micros / max(1, constraints.max_cost_micros or score.cost_micros or 1)) * 0.1
            candidates.append((utility, name, adapter))
        if not candidates:
            raise NotConfigured("no benchmarked provider satisfies route constraints")
        return min(candidates, key=lambda item: (-item[0], item[1]))[2]

    def record_failure(self, provider: str, *, cooldown_seconds: float = 30.0) -> None:
        with self._lock:
            count = self._failures.get(provider, 0) + 1
            self._failures[provider] = count
            if count >= 3:
                self._open_until[provider] = time.time() + cooldown_seconds

    def record_success(self, provider: str) -> None:
        with self._lock:
            self._failures[provider] = 0
            self._open_until.pop(provider, None)

    def shadow(self, primary: str, request: ProviderRequest, providers: Iterable[str]) -> Mapping[str, tuple[NormalizedProviderEvent, ...] | str]:
        results: dict[str, tuple[NormalizedProviderEvent, ...] | str] = {}
        shadow_request = ProviderRequest(request.identity, request.model, {**dict(request.context), "shadow_mode": True, "side_effects_allowed": False}, request.tool_schemas, request.checkpoint, request.idempotency_key)
        for name in providers:
            if name == primary:
                continue
            adapter = self.adapters.get(name)
            if adapter is None:
                results[name] = "NOT_CONFIGURED"
                continue
            try:
                started = adapter.start(shadow_request)
                events = tuple(adapter.send(str(started["session_id"]), shadow_request, after_sequence=-1))
                if any(event.kind == "action" for event in events):
                    results[name] = "POLICY_BLOCKED_ACTION_IN_SHADOW"
                else:
                    results[name] = events
            except Exception as error:  # noqa: BLE001 - shadow failures are isolated per provider
                results[name] = "ERROR:" + type(error).__name__
        return results


def _request_body(request: ProviderRequest) -> dict[str, Any]:
    return {"schema_version": "1.0", "identity": {"tenant_id": request.identity.tenant_id, "project_id": request.identity.project_id, "task_id": request.identity.task_id, "run_id": request.identity.run_id, "node_id": request.identity.node_id, "agent_id": request.identity.agent_id}, "model": request.model, "context": dict(request.context), "tool_schemas": [dict(item) for item in request.tool_schemas], "checkpoint": request.checkpoint, "idempotency_key": request.idempotency_key}


def _event_dict(event: NormalizedProviderEvent) -> dict[str, Any]:
    return {"sequence": event.sequence, "kind": event.kind, "payload": dict(event.payload), "usage": event.usage.as_dict(), "terminal": event.terminal, "provider_event_id": event.provider_event_id}


def _normalized_event(value: Mapping[str, Any]) -> NormalizedProviderEvent:
    return NormalizedProviderEvent(
        int(value["sequence"]),
        str(value["kind"]),
        dict(value.get("payload", {})),
        Usage(**dict(value.get("usage", {}))),
        bool(value.get("terminal", False)),
        None if value.get("provider_event_id") is None else str(value["provider_event_id"]),
    )


def _provider_checkpoint(value: Mapping[str, Any]) -> ProviderCheckpoint:
    return ProviderCheckpoint(
        str(value["provider"]),
        str(value["remote_session_id"]),
        dict(value["payload"]),
        str(value["manifest_digest"]),
        int(value["sequence"]),
        str(value["digest"]),
    )


def _add_usage(left: Usage, right: Usage) -> Usage:
    return Usage(left.input_tokens + right.input_tokens, left.output_tokens + right.output_tokens, left.cached_input_tokens + right.cached_input_tokens, left.reasoning_tokens + right.reasoning_tokens, left.cost_micros + right.cost_micros, left.provider_latency_ms + right.provider_latency_ms)


def _capabilities_digest(value: ProviderCapabilities) -> str:
    return digest_of(
        {
            "provider": value.provider,
            "protocol_version": value.protocol_version,
            "supports_checkpoints": value.supports_checkpoints,
            "supports_streaming": value.supports_streaming,
            "supports_tool_calls": value.supports_tool_calls,
            "supported_tools": sorted(value.supported_tools),
            "regions": sorted(value.regions),
            "supports_file_edit": value.supports_file_edit,
            "supports_shell": value.supports_shell,
            "supports_browser": value.supports_browser,
            "supports_mcp_acp": value.supports_mcp_acp,
            "reasoning_visibility": value.reasoning_visibility,
            "supports_model_selection": value.supports_model_selection,
            "max_context_tokens": value.max_context_tokens,
            "max_parallelism": value.max_parallelism,
            "external_network_required": value.external_network_required,
            "privacy_classes": sorted(value.privacy_classes),
        }
    )


def _validated_endpoint(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.rstrip("/"))
    try:
        port = parsed.port
    except ValueError as error:
        raise ContractViolation("provider endpoint port is invalid") from error
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ContractViolation("provider endpoints must be credential-free HTTPS base URLs")
    if port is not None and not 1 <= port <= 65535:
        raise ContractViolation("provider endpoint port is invalid")
    return value.rstrip("/")


def _sha256_digest(value: str) -> bool:
    return len(value) == 71 and value.startswith("sha256:") and all(character in "0123456789abcdef" for character in value[7:])
