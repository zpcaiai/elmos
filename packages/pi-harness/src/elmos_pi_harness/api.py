"""Small production-shaped HTTP API for the durable kernel.

The standard-library server is intentionally dependency-light.  Deployments
should place it behind an mTLS/TLS-capable ingress and provide an authenticated
bearer token; it is not a substitute for an enterprise identity provider.
"""

from __future__ import annotations

import hmac
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .models import (
    ConflictError,
    HarnessError,
    NotFoundError,
    PolicyDeniedError,
    QuotaExceededError,
    StaleGenerationError,
)
from .persistence import DurableStore

TASK_ROUTE = re.compile(r"^/v1/tasks/(?P<task_id>[0-9a-fA-F-]{36})(?P<tail>/[a-z-]+)?$")


class HarnessHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], store: DurableStore, *, api_token: str, allow_unauthenticated_for_testing: bool = False, max_body_bytes: int = 1_048_576) -> None:
        if not api_token and not allow_unauthenticated_for_testing:
            raise ValueError("api_token is required; unauthenticated mode is test-only")
        if max_body_bytes < 1024:
            raise ValueError("max_body_bytes is too small")
        self.store = store
        self.api_token = api_token
        self.max_body_bytes = max_body_bytes
        self.allow_unauthenticated_for_testing = allow_unauthenticated_for_testing
        super().__init__(address, HarnessRequestHandler)


class HarnessRequestHandler(BaseHTTPRequestHandler):
    server: HarnessHTTPServer
    protocol_version = "HTTP/1.1"
    server_version = "elmos-pi-harness/5.1"

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _send(self, status: int, payload: Any, *, content_type: str = "application/json") -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _problem(self, status: int, title: str, detail: str = "", *, code: str | None = None) -> None:
        payload: dict[str, Any] = {"type": "https://elmos.dev/problems/" + (code or title.lower().replace(" ", "-")), "title": title, "status": status}
        if detail:
            payload["detail"] = detail[:2000]
        self._send(status, payload, content_type="application/problem+json")

    def _authorised(self) -> bool:
        if self.server.allow_unauthenticated_for_testing:
            return True
        value = self.headers.get("Authorization", "")
        expected = "Bearer " + self.server.api_token
        return hmac.compare_digest(value, expected)

    def _context(self) -> tuple[str, str]:
        tenant_id = self.headers.get("X-Tenant-Id", "")
        actor_id = self.headers.get("X-Actor-Id", "")
        from .canonical import require_nonempty, require_uuid

        return require_uuid(tenant_id, "X-Tenant-Id"), require_nonempty(actor_id, "X-Actor-Id", 256)

    def _body(self) -> dict[str, Any]:
        header = self.headers.get("Content-Length")
        try:
            length = int(header or "0")
        except ValueError as exc:
            raise ValueError("Content-Length must be an integer") from exc
        if length < 0 or length > self.server.max_body_bytes:
            raise ValueError("request body exceeds configured limit")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise TypeError("request body must be a JSON object")
        return value

    def _idempotency(self) -> str:
        from .canonical import require_nonempty

        return require_nonempty(self.headers.get("Idempotency-Key", ""), "Idempotency-Key", 256)

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/healthz":
                return self._send(200, {"status": "ok", "service": "elmos-pi-harness"})
            if parsed.path == "/readyz":
                self.server.store._connection.execute("SELECT 1")
                return self._send(200, {"status": "ready"})
            if not self._authorised():
                return self._problem(401, "Unauthorized", code="unauthorized")
            tenant_id, _actor_id = self._context()
            match = TASK_ROUTE.match(parsed.path)
            if not match:
                return self._problem(404, "Not Found", code="not-found")
            task_id = match.group("task_id")
            tail = (match.group("tail") or "").lstrip("/")
            if tail == "":
                return self._send(200, self.server.store.get_task(tenant_id, task_id))
            if tail == "events":
                query = parse_qs(parsed.query)
                after = int(query.get("after", ["0"])[0])
                limit = int(query.get("limit", ["100"])[0])
                return self._send(200, self.server.store.events(tenant_id, task_id, after_sequence=after, limit=limit))
            if tail == "artifacts":
                return self._send(200, {"items": self.server.store.artifacts(tenant_id, task_id)})
            return self._problem(404, "Not Found", code="not-found")
        except Exception as exc:  # noqa: BLE001 - HTTP boundary must normalize unexpected failures
            self._handle_error(exc)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if not self._authorised():
                return self._problem(401, "Unauthorized", code="unauthorized")
            tenant_id, actor_id = self._context()
            body = self._body()
            if parsed.path == "/v1/tasks":
                project_id = body.get("project_id")
                if body.get("tenant_id") not in (None, tenant_id):
                    return self._problem(403, "Forbidden", "tenant_id must come from X-Tenant-Id", code="tenant-binding")
                if not project_id:
                    return self._problem(422, "Validation Failed", "project_id is required", code="validation")
                result = self.server.store.create_task(tenant_id, project_id, body.get("objective"), idempotency_key=self._idempotency(), request_payload=body, actor_id=actor_id, project_name=body.get("project_name"))
                return self._send(200 if result.get("replayed") else 201, result)
            match = TASK_ROUTE.match(parsed.path)
            if not match:
                return self._problem(404, "Not Found", code="not-found")
            task_id = match.group("task_id")
            tail = (match.group("tail") or "").lstrip("/")
            key = self._idempotency()
            if tail in {"queue", "planning", "run", "verify", "pause", "resume", "cancel", "retry", "approve"}:
                target = {"queue": "QUEUED", "planning": "PLANNING", "run": "RUNNING", "verify": "VERIFYING", "pause": "PAUSED", "resume": "RUNNING", "cancel": "CANCEL_REQUESTED", "retry": "RETRY_QUEUED", "approve": "RUNNING"}[tail]
                result = self.server.store.transition_task(tenant_id, task_id, target, idempotency_key=key, actor_id=actor_id, payload=body, max_running_tasks=int(body.get("max_running_tasks", 3)))
                return self._send(200, result)
            if tail == "branch":
                result = self.server.store.branch_task(tenant_id, task_id, body.get("objective"), idempotency_key=key, actor_id=actor_id)
                return self._send(201, result)
            return self._problem(404, "Not Found", code="not-found")
        except Exception as exc:  # noqa: BLE001 - HTTP boundary must normalize unexpected failures
            self._handle_error(exc)

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, NotFoundError):
            return self._problem(404, "Not Found", str(exc), code="not-found")
        if isinstance(exc, (ConflictError, QuotaExceededError, StaleGenerationError)):
            return self._problem(409, "Conflict", str(exc), code="conflict")
        if isinstance(exc, (PolicyDeniedError, PermissionError)):
            return self._problem(403, "Forbidden", str(exc), code="policy-denied")
        if isinstance(exc, (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError)):
            return self._problem(422, "Validation Failed", str(exc), code="validation")
        if isinstance(exc, HarnessError):
            return self._problem(503, "Service Unavailable", str(exc), code="store-unavailable")
        return self._problem(500, "Internal Server Error", "request could not be completed", code="internal-error")


def serve(*, host: str, port: int, database: str, api_token: str, artifact_root: str | None = None) -> None:
    resolved_artifact_root = str(Path(artifact_root).resolve()) if artifact_root else None
    store = DurableStore(database, artifact_root=resolved_artifact_root)
    server = HarnessHTTPServer((host, port), store, api_token=api_token)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        store.close()
