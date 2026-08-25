"""A reference HTTP server for ``openapi/task-execution-api.yaml``.

An OpenAPI document that nothing implements is a contract nobody has ever tested.
This serves the parts of it that carry the actual guarantees -- reconnectable
event replay and idempotent submission -- on top of the same durable store the
rest of the package uses, with nothing but the standard library.

It is a reference, not a deployment: strictly single-threaded (one request at a
time), no auth beyond a bearer check, no TLS, no rate limiting, no tenancy
isolation beyond the store's own. Its
job is to let a person run `curl` against the contract and see the reconnect
guarantee hold, and to let a test assert it end to end.
"""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .durable import Conflict, DurableStore
from .runner import execute_run

RUN_PATH = re.compile(r"^/api/v1/runs/(?P<run_id>[0-9a-fA-F-]+)(?P<tail>/[a-z]+)?$")


class _Handler(BaseHTTPRequestHandler):
    """Request handling for the subset of the contract that carries guarantees."""

    server_version = "elmos-execution-intelligence/1.0"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------ helpers --

    @property
    def store(self) -> DurableStore:
        store: DurableStore = self.server.store  # type: ignore[attr-defined]
        return store

    @property
    def bearer(self) -> str | None:
        token: str | None = self.server.bearer  # type: ignore[attr-defined]
        return token

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        return  # a reference server that spams stderr during tests helps nobody

    def _authorised(self) -> bool:
        if not self.bearer:
            return True
        header = self.headers.get("Authorization", "")
        return header == f"Bearer {self.bearer}"

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _problem(self, status: int, title: str, detail: str = "", missing: list[str] | None = None) -> None:
        payload: dict[str, Any] = {
            "type": f"https://elmos.dev/problems/{title.lower().replace(' ', '-')}",
            "title": title,
            "status": status,
        }
        if detail:
            payload["detail"] = detail
        if missing:
            payload["missing"] = missing
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/problem+json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _run_json(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        return {
            "runId": run["run_id"],
            "tenantId": run["tenant_id"],
            "projectId": run["project_id"],
            "dagId": run["dag_id"],
            "state": run["state"],
            "createdAt": run["created_at"],
            "startedAt": run["started_at"],
            "finishedAt": run["finished_at"],
            "lastEventSeq": run["last_event_seq"],
        }

    # ---------------------------------------------------------------------- GET --

    def do_GET(self) -> None:  # noqa: N802 - stdlib signature
        if not self._authorised():
            return self._problem(401, "Unauthorized")
        parsed = urlparse(self.path)
        match = RUN_PATH.match(parsed.path)
        if parsed.path == "/api/v1/runs":
            return self._send_json(200, {"runs": []})
        if not match:
            return self._problem(404, "Not Found", f"no route for {parsed.path}")

        run_id = match.group("run_id")
        tail = (match.group("tail") or "").lstrip("/")
        try:
            self.store.get_run(run_id)
        except ValueError:
            return self._problem(404, "Not Found", f"unknown run {run_id}")

        if tail == "":
            detail = self._run_json(run_id)
            detail["tasks"] = [
                {"taskId": task["task_id"], "name": task["name"], "state": task["state"],
                 "attemptCount": task["attempt_count"],
                 "lastFailureClass": task["last_failure_class"]}
                for task in self.store.tasks(run_id)
            ]
            from .durable import recovery_aware_eta
            eta = recovery_aware_eta(self.store, run_id)
            detail["eta"] = {
                "wallClockHours": eta["wall_clock_hours"],
                "completedFraction": eta["completed_fraction"],
                "basis": eta["basis"],
                "excludes": eta["excludes"],
            }
            return self._send_json(200, detail)

        if tail == "events":
            return self._events(run_id, parsed)
        if tail == "eta":
            from .durable import recovery_aware_eta
            eta = recovery_aware_eta(self.store, run_id)
            return self._send_json(200, {
                "wallClockHours": eta["wall_clock_hours"],
                "completedFraction": eta["completed_fraction"],
                "recoveryHoursIncluded": eta["recovery_hours_included"],
                "basis": eta["basis"],
                "excludes": eta["excludes"],
            })
        if tail == "checkpoints":
            return self._send_json(200, {"checkpoints": [
                {"checkpointId": cp["checkpoint_id"], "taskId": cp["task_id"], "kind": cp["kind"],
                 "gitCommit": cp["git_commit"], "createdAt": cp["created_at"]}
                for cp in self.store.checkpoints(run_id)
            ]})
        if tail == "artifacts":
            artifacts = self.store.artifacts(run_id)
            return self._send_json(200, {
                "runId": run_id,
                "sealed": self.store.get_run(run_id)["state"] in {"succeeded", "failed", "cancelled"},
                "artifacts": [
                    {"logicalName": a["logical_name"], "version": a["version"],
                     "mediaType": a["media_type"], "sizeBytes": a["size_bytes"],
                     "sha256": a["sha256"], "storageUri": a["storage_uri"], "gitRef": a["git_ref"]}
                    for a in artifacts
                ],
            })
        return self._problem(404, "Not Found", f"no route for {parsed.path}")

    def _events(self, run_id: str, parsed: Any) -> None:
        """Serve the reconnect contract: Last-Event-ID for SSE, afterSeq for polling.

        Both read the same append-only rows, which is what lets a client switch
        between them without a gap or a duplicate.
        """
        query = parse_qs(parsed.query)
        after = int(query.get("afterSeq", ["0"])[0])
        header = self.headers.get("Last-Event-ID")
        if header:
            try:
                after = max(after, int(header))
            except ValueError:
                return self._problem(400, "Bad Request", "Last-Event-ID must be an integer sequence")
        limit = min(1000, int(query.get("limit", ["500"])[0]))

        accept = self.headers.get("Accept", "")
        if "text/event-stream" in accept:
            frames = self.store.sse_frames(run_id, last_event_id=after, limit=limit)
            body = (frames + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        events = self.store.events_since(run_id, after, limit=limit)
        self._send_json(200, {
            "events": [
                {"seq": event["seq"], "runId": event["run_id"], "taskId": event["task_id"],
                 "eventType": event["event_type"], "createdAt": event["created_at"],
                 "payload": event["payload"]}
                for event in events
            ],
            "lastSeq": events[-1]["seq"] if events else after,
            "hasMore": len(events) == limit,
        })

    # --------------------------------------------------------------------- POST --

    def do_POST(self) -> None:  # noqa: N802 - stdlib signature
        if not self._authorised():
            return self._problem(401, "Unauthorized")
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._problem(400, "Bad Request", "body is not valid JSON")

        key = self.headers.get("Idempotency-Key")
        if not key:
            return self._problem(422, "Blocked",
                                 "every state-changing request needs an Idempotency-Key",
                                 missing=["Idempotency-Key"])

        if parsed.path == "/api/v1/runs":
            return self._create_run(key, payload)

        match = RUN_PATH.match(parsed.path)
        if match and (match.group("tail") or "").lstrip("/") == "cancel":
            run_id = match.group("run_id")
            try:
                self.store.get_run(run_id)
            except ValueError:
                return self._problem(404, "Not Found", f"unknown run {run_id}")
            try:
                status, replay = self.store.begin_idempotent("cancel", key, {"run": run_id})
            except Conflict as exc:
                return self._problem(409, "Conflict", str(exc))
            if status == "replayed":
                return self._send_json(202, replay)
            self.store.set_run_state(run_id, "cancelled")
            response = self._run_json(run_id)
            self.store.complete_idempotent("cancel", key, response)
            return self._send_json(202, response)

        return self._problem(404, "Not Found", f"no route for {parsed.path}")

    def _create_run(self, key: str, payload: dict[str, Any]) -> None:
        missing = [field for field in ("projectProfile", "taskDag") if field not in payload]
        if missing:
            return self._problem(422, "Blocked", "required fields are absent", missing=missing)
        try:
            status, replay = self.store.begin_idempotent("createRun", key, payload)
        except Conflict as exc:
            return self._problem(409, "Conflict", str(exc))
        if status == "replayed":
            # 200, not 201: nothing was created this time.
            return self._send_json(200, replay)
        if status == "in_flight":
            return self._problem(409, "Conflict", "a request with this key is already in flight")

        try:
            result = execute_run(payload["projectProfile"], payload["taskDag"], self.store)
        except Exception as exc:  # pragma: no cover - defensive
            self.store.fail_idempotent("createRun", key)
            return self._problem(500, "Internal Error", str(exc))

        response = self._run_json(result["run_id"])
        self.store.complete_idempotent("createRun", key, response)
        self._send_json(201, response)


class ReferenceServer:
    """Start/stop wrapper so tests and humans drive it the same way."""

    def __init__(self, store: DurableStore, host: str = "127.0.0.1", port: int = 0,
                 bearer: str | None = None) -> None:
        if not getattr(store, "allow_cross_thread", False):
            raise ValueError(
                "the reference server serves from its own thread, so the store must be opened with "
                "DurableStore(..., allow_cross_thread=True). Leaving the sqlite thread check on "
                "everywhere else is deliberate: it catches real concurrency bugs."
            )
        # Deliberately serial: one request at a time, one connection, no locking
        # to reason about. A production server would not do this, and this is not
        # a production server.
        self.httpd = HTTPServer((host, port), _Handler)
        self.httpd.store = store          # type: ignore[attr-defined]
        self.httpd.bearer = bearer        # type: ignore[attr-defined]
        self.thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    @property
    def base_url(self) -> str:
        host = self.httpd.server_address[0]
        if isinstance(host, bytes):  # pragma: no cover - platform dependent
            host = host.decode("ascii")
        return f"http://{host}:{self.port}/api/v1"

    def start(self) -> ReferenceServer:
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread:
            self.thread.join(timeout=5)

    def __enter__(self) -> ReferenceServer:
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.stop()
