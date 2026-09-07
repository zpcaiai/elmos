from __future__ import annotations

import base64
import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from email.message import Message
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from elmos_multimodal_intake import MultimodalIntakeRuntime
import elmos_multimodal_intake.http_server as http_server_module
from elmos_multimodal_intake.http_server import (
    CAPABILITIES_PATH,
    EXECUTE_PATH,
    PROGRESS_JOB_EVENTS_PREFIX,
    PROGRESS_TASK_EVENTS_PREFIX,
    PROGRESS_TASK_WEBSOCKET_PREFIX,
    _BoundedThreadingHTTPServer,
    _BOUND_ACTOR_HEADER,
    _BOUND_PROJECT_HEADER,
    _BOUND_TENANT_HEADER,
    _server_class,
)
from elmos_multimodal_intake.models import TenantContext


_TOKEN = "progress-security-token-which-is-at-least-thirty-two"
_CONTEXT = TenantContext("tenant-a", "project-a", "actor-a")
_TASK_ID = "progress-security-task"


class _CountingRuntime(MultimodalIntakeRuntime):
    def __init__(self, database: Path, cas_root: Path) -> None:
        self.close_calls = 0
        super().__init__(database, cas_root)

    def close(self) -> None:
        self.close_calls += 1
        super().close()


class _Harness:
    def __init__(
        self,
        *,
        server: HTTPServer,
        handler: type[Any],
        runtime: _CountingRuntime,
        job_id: str,
        factory_calls: list[tuple[Path, Path]],
        store_reads: dict[str, int],
    ) -> None:
        self.server = server
        self.handler = handler
        self.runtime = runtime
        self.job_id = job_id
        self.factory_calls = factory_calls
        self.store_reads = store_reads

    @property
    def port(self) -> int:
        return int(self.server.server_port)

    @property
    def task_sse_path(self) -> str:
        return f"{PROGRESS_TASK_EVENTS_PREFIX}{_TASK_ID}/events"

    @property
    def task_websocket_path(self) -> str:
        return f"{PROGRESS_TASK_WEBSOCKET_PREFIX}{_TASK_ID}"

    @property
    def job_sse_path(self) -> str:
        return f"{PROGRESS_JOB_EVENTS_PREFIX}{self.job_id}/events"


@contextmanager
def _running_server(tmp_path: Path) -> Iterator[_Harness]:
    factory_calls: list[tuple[Path, Path]] = []
    runtimes: list[_CountingRuntime] = []

    def factory(database: Path, cas_root: Path) -> MultimodalIntakeRuntime:
        factory_calls.append((database, cas_root))
        runtime = _CountingRuntime(database, cas_root)
        runtimes.append(runtime)
        return runtime

    handler = _server_class(
        data_root=tmp_path / "runtime",
        bearer_token=_TOKEN,
        tenant_id=_CONTEXT.tenant_id,
        project_id=_CONTEXT.project_id,
        actor_id=_CONTEXT.actor_id,
        runtime_factory=factory,
    )
    assert len(factory_calls) == 1
    assert len(runtimes) == 1
    runtime = runtimes[0]
    runtime.store.bootstrap_project(_CONTEXT)
    runtime.store.apply_durable_transition(
        _CONTEXT,
        task_id=_TASK_ID,
        idempotency_key="progress-security-running",
        target_state="RUNNING",
        payload={"private": "never-expose"},
    )
    session = runtime.store.create_session(
        _CONTEXT,
        idempotency_key="progress-security-session",
    )
    job = runtime.store.create_job(
        _CONTEXT,
        session.session_id,
        idempotency_key="progress-security-job",
        request_digest="a" * 64,
    )

    # These sentinels prove the reader dereferences the exact factory-owned
    # store rather than constructing a second IntakeStore during GET.
    store_reads = {"page": 0, "job": 0}
    original_page = runtime.store.durable_task_progress_page
    original_get_job = runtime.store.get_job

    def durable_task_progress_page(*args: Any, **kwargs: Any) -> dict[str, Any]:
        store_reads["page"] += 1
        return original_page(*args, **kwargs)

    runtime.store.durable_task_progress_page = durable_task_progress_page  # type: ignore[method-assign]

    def get_job(*args: Any, **kwargs: Any) -> Any:
        store_reads["job"] += 1
        return original_get_job(*args, **kwargs)

    runtime.store.get_job = get_job  # type: ignore[method-assign]

    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    harness = _Harness(
        server=server,
        handler=handler,
        runtime=runtime,
        job_id=job.job_id,
        factory_calls=factory_calls,
        store_reads=store_reads,
    )
    try:
        yield harness
    finally:
        server.shutdown()
        thread.join(timeout=2)
        assert not thread.is_alive()
        # The handler wires direct HTTPServer embedders to its owner lifecycle.
        # Repeated closes must never invoke runtime.close more than once.
        server.server_close()
        server.server_close()
        handler.close_runtime()
        assert runtime.close_calls == 1


def _request_bytes(
    path: str,
    headers: list[tuple[str, str]],
    *,
    suffix: bytes = b"",
) -> bytes:
    lines = [f"GET {path} HTTP/1.1"]
    lines.extend(f"{name}: {value}" for name, value in headers)
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii") + suffix


def _exchange(port: int, request: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
        connection.sendall(request)
        connection.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            chunk = connection.recv(64 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)


def _exchange_without_peer_close(port: int, request: bytes) -> tuple[bytes, float]:
    started = time.monotonic()
    with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
        connection.sendall(request)
        chunks: list[bytes] = []
        while True:
            chunk = connection.recv(64 * 1024)
            if not chunk:
                return b"".join(chunks), time.monotonic() - started
            chunks.append(chunk)


def _status(raw: bytes) -> int:
    first_line = raw.split(b"\r\n", 1)[0]
    return int(first_line.split(b" ", 2)[1])


def _headers_and_body(raw: bytes) -> tuple[bytes, bytes]:
    headers, separator, body = raw.partition(b"\r\n\r\n")
    assert separator == b"\r\n\r\n"
    return headers, body


def _error_code(raw: bytes) -> str:
    _, body = _headers_and_body(raw)
    document = json.loads(body)
    status = _status(raw)
    assert set(document) == {
        "schema_version", "status", "code", "retryable", "trace_id"
    }
    assert document["schema_version"] == "1.0.0"
    assert document["status"] == ("FAILED" if status >= 500 else "BLOCKED")
    assert isinstance(document["retryable"], bool)
    assert isinstance(document["trace_id"], str)
    assert 1 <= len(document["trace_id"].encode("utf-8")) <= 128
    return str(document["code"])


def _sse_headers(port: int) -> list[tuple[str, str]]:
    return [
        ("Host", f"127.0.0.1:{port}"),
        ("Authorization", f"Bearer {_TOKEN}"),
        (_BOUND_TENANT_HEADER, _CONTEXT.tenant_id),
        (_BOUND_PROJECT_HEADER, _CONTEXT.project_id),
        (_BOUND_ACTOR_HEADER, _CONTEXT.actor_id),
        ("Accept", "text/event-stream"),
    ]


def _websocket_headers(
    port: int,
    *,
    connection: str = "Upgrade",
    version: str = "13",
) -> list[tuple[str, str]]:
    key = base64.b64encode(b"0123456789abcdef").decode("ascii")
    return [
        ("Host", f"127.0.0.1:{port}"),
        ("Authorization", f"Bearer {_TOKEN}"),
        (_BOUND_TENANT_HEADER, _CONTEXT.tenant_id),
        (_BOUND_PROJECT_HEADER, _CONTEXT.project_id),
        (_BOUND_ACTOR_HEADER, _CONTEXT.actor_id),
        ("Upgrade", "websocket"),
        ("Connection", connection),
        ("Sec-WebSocket-Version", version),
        ("Sec-WebSocket-Key", key),
    ]


def _masked_frame(opcode: int, payload: bytes, *, mask: bytes = b"\x01\x02\x03\x04") -> bytes:
    assert len(mask) == 4
    assert len(payload) <= 125
    encoded = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return bytes((0x80 | opcode, 0x80 | len(payload))) + mask + encoded


def test_progress_reuses_trusted_factory_runtime_store_and_closes_once(tmp_path: Path) -> None:
    with _running_server(tmp_path) as harness:
        request = _request_bytes(
            harness.task_sse_path,
            _sse_headers(harness.port),
        )
        raw = _exchange(harness.port, request)
        assert _status(raw) == 200
        assert b"event: progress" in raw
        assert b"never-expose" not in raw
        assert harness.store_reads == {"page": 1, "job": 0}

        capabilities = _request_bytes(
            CAPABILITIES_PATH,
            [
                ("Host", f"127.0.0.1:{harness.port}"),
                ("Authorization", f"Bearer {_TOKEN}"),
            ],
        )
        capability_raw = _exchange(harness.port, capabilities)
        assert _status(capability_raw) == 200
        assert len(harness.factory_calls) == 1
        assert harness.runtime.close_calls == 0


def test_progress_rejects_unbound_scope_before_known_job_read(tmp_path: Path) -> None:
    with _running_server(tmp_path) as harness:
        for header, wrong_value in (
            (_BOUND_TENANT_HEADER, "tenant-b"),
            (_BOUND_PROJECT_HEADER, "project-b"),
            (_BOUND_ACTOR_HEADER, "actor-b"),
        ):
            headers = [
                (name, wrong_value if name == header else value)
                for name, value in _sse_headers(harness.port)
            ]
            raw = _exchange(
                harness.port,
                _request_bytes(harness.job_sse_path, headers),
            )
            assert _status(raw) == 403
            assert _error_code(raw) == "BOUND_IDENTITY_MISMATCH"
            assert harness.store_reads == {"page": 0, "job": 0}

        missing_scope = [
            (name, value)
            for name, value in _sse_headers(harness.port)
            if name != _BOUND_PROJECT_HEADER
        ]
        raw = _exchange(
            harness.port,
            _request_bytes(harness.job_sse_path, missing_scope),
        )
        assert _status(raw) == 403
        assert _error_code(raw) == "BOUND_IDENTITY_MISMATCH"
        assert harness.store_reads == {"page": 0, "job": 0}

        duplicate_scope = _sse_headers(harness.port)
        duplicate_scope.append((_BOUND_TENANT_HEADER, _CONTEXT.tenant_id))
        raw = _exchange(
            harness.port,
            _request_bytes(harness.job_sse_path, duplicate_scope),
        )
        assert _status(raw) == 403
        assert _error_code(raw) == "BOUND_IDENTITY_MISMATCH"
        assert harness.store_reads == {"page": 0, "job": 0}

        accepted = _exchange(
            harness.port,
            _request_bytes(harness.job_sse_path, _sse_headers(harness.port)),
        )
        assert _status(accepted) == 200
        assert harness.store_reads == {"page": 0, "job": 1}


def test_bounded_threading_server_allows_cancel_while_process_is_active() -> None:
    process_started = threading.Event()
    cancel_entered = threading.Event()
    process_result: dict[str, bytes | BaseException] = {}

    class ConcurrentHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _empty_ok(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/process":
                process_started.set()
                if not cancel_entered.wait(timeout=2):
                    self.send_error(504)
                    return
                self._empty_ok()
                return
            if self.path == "/cancel":
                cancel_entered.set()
                self._empty_ok()
                return
            self.send_error(404)

    server = _BoundedThreadingHTTPServer(
        ("127.0.0.1", 0),
        ConcurrentHandler,
        maximum_workers=2,
    )
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()

    def request_process() -> None:
        try:
            process_result["response"] = _exchange(
                int(server.server_port),
                _request_bytes(
                    "/process",
                    [("Host", f"127.0.0.1:{server.server_port}")],
                ),
            )
        except BaseException as error:
            process_result["error"] = error

    process_client = threading.Thread(target=request_process)
    process_client.start()
    try:
        assert server.maximum_workers == 2
        assert server.daemon_threads is False
        assert server.block_on_close is True
        assert process_started.wait(timeout=1)

        cancel_response = _exchange(
            int(server.server_port),
            _request_bytes(
                "/cancel",
                [("Host", f"127.0.0.1:{server.server_port}")],
            ),
        )
        assert _status(cancel_response) == 200
        process_client.join(timeout=2)
        assert not process_client.is_alive()
        assert "error" not in process_result
        response = process_result.get("response")
        assert isinstance(response, bytes)
        assert _status(response) == 200
    finally:
        cancel_entered.set()
        process_client.join(timeout=2)
        server.shutdown()
        server_thread.join(timeout=2)
        server.server_close()
    assert not process_client.is_alive()
    assert not server_thread.is_alive()


def test_serve_selects_bounded_threading_server_and_closes_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, Any]] = []
    runtimes: list[_CountingRuntime] = []

    class RecordingBoundedServer:
        def __init__(self, address: Any, handler: type[Any]) -> None:
            calls.append(("created", address))
            calls.append(("handler", handler))

        def serve_forever(self, *, poll_interval: float) -> None:
            calls.append(("served", poll_interval))

        def server_close(self) -> None:
            calls.append(("closed", True))

    def factory(database: Path, cas_root: Path) -> MultimodalIntakeRuntime:
        runtime = _CountingRuntime(database, cas_root)
        runtimes.append(runtime)
        return runtime

    monkeypatch.setattr(
        http_server_module,
        "_BoundedThreadingHTTPServer",
        RecordingBoundedServer,
    )
    http_server_module.serve(
        data_root=tmp_path / "serve-runtime",
        bind="127.0.0.1",
        port=8765,
        bearer_token=_TOKEN,
        tenant_id=_CONTEXT.tenant_id,
        project_id=_CONTEXT.project_id,
        actor_id=_CONTEXT.actor_id,
        runtime_factory=factory,
    )

    assert [name for name, _value in calls] == [
        "created",
        "handler",
        "served",
        "closed",
    ]
    assert calls[0][1] == ("127.0.0.1", 8765)
    assert calls[2][1] == 0.25
    assert len(runtimes) == 1
    assert runtimes[0].close_calls == 1


def test_direct_zero_request_embedder_has_explicit_close_contract(tmp_path: Path) -> None:
    runtimes: list[_CountingRuntime] = []

    def factory(database: Path, cas_root: Path) -> MultimodalIntakeRuntime:
        runtime = _CountingRuntime(database, cas_root)
        runtimes.append(runtime)
        return runtime

    handler = _server_class(
        data_root=tmp_path / "runtime",
        bearer_token=_TOKEN,
        tenant_id=_CONTEXT.tenant_id,
        project_id=_CONTEXT.project_id,
        actor_id=_CONTEXT.actor_id,
        runtime_factory=factory,
    )
    assert len(runtimes) == 1
    runtime = runtimes[0]
    server = HTTPServer(("127.0.0.1", 0), handler)
    try:
        # No handler instance exists before the first request, so a private
        # direct embedder follows _server_class's documented explicit contract.
        server.server_close()
        assert runtime.close_calls == 0
    finally:
        handler.close_runtime()
        handler.close_runtime()
    assert runtime.close_calls == 1


def test_direct_handler_fails_closed_for_every_non_loopback_route(tmp_path: Path) -> None:
    runtimes: list[_CountingRuntime] = []

    def factory(database: Path, cas_root: Path) -> MultimodalIntakeRuntime:
        runtime = _CountingRuntime(database, cas_root)
        runtimes.append(runtime)
        return runtime

    handler = _server_class(
        data_root=tmp_path / "runtime",
        bearer_token=_TOKEN,
        tenant_id=_CONTEXT.tenant_id,
        project_id=_CONTEXT.project_id,
        actor_id=_CONTEXT.actor_id,
        runtime_factory=factory,
    )
    probe = object.__new__(handler)
    probe.client_address = ("198.51.100.8", 43123)
    probe.headers = Message()
    probe.headers.add_header("Authorization", f"Bearer {_TOKEN}")
    rejected: list[tuple[int, str]] = []

    def capture_error(status: int, code: str, **_kwargs: Any) -> None:
        rejected.append((int(status), code))

    probe._error = capture_error
    try:
        probe.command = "GET"
        probe.path = CAPABILITIES_PATH
        probe.do_GET()

        probe.command = "POST"
        probe.path = EXECUTE_PATH
        probe.do_POST()

        probe.command = "PUT"
        probe.path = CAPABILITIES_PATH
        probe._method_not_allowed()

        probe.command = "BROKEN"
        probe.send_error(400)
    finally:
        handler.close_runtime()
    assert rejected == [(403, "HTTP_LOOPBACK_REQUIRED")] * 4
    assert runtimes[0].close_calls == 1


def test_progress_rejects_host_body_and_duplicate_critical_headers(tmp_path: Path) -> None:
    with _running_server(tmp_path) as harness:
        path = harness.task_sse_path

        missing_host = _request_bytes(
            path,
            [
                ("Authorization", f"Bearer {_TOKEN}"),
                ("Accept", "text/event-stream"),
            ],
        )
        raw = _exchange(harness.port, missing_host)
        assert _status(raw) == 400
        assert _error_code(raw) == "PROGRESS_HOST_INVALID"

        wrong_authority_headers = _sse_headers(harness.port)
        wrong_authority_headers[0] = ("Host", f"example.invalid:{harness.port}")
        raw = _exchange(
            harness.port,
            _request_bytes(path, wrong_authority_headers),
        )
        assert _status(raw) == 400
        assert _error_code(raw) == "PROGRESS_HOST_INVALID"

        duplicate_host_headers = _sse_headers(harness.port)
        duplicate_host_headers.insert(1, ("Host", f"127.0.0.1:{harness.port}"))
        raw = _exchange(
            harness.port,
            _request_bytes(path, duplicate_host_headers),
        )
        assert _status(raw) == 400
        assert _error_code(raw) == "PROGRESS_HOST_INVALID"

        duplicate_length_headers = _sse_headers(harness.port)
        duplicate_length_headers.extend(
            [("Content-Length", "0"), ("Content-Length", "0")]
        )
        raw = _exchange(
            harness.port,
            _request_bytes(path, duplicate_length_headers),
        )
        assert _status(raw) == 400
        assert _error_code(raw) == "PROGRESS_REQUEST_BODY_FORBIDDEN"

        transfer_headers = _sse_headers(harness.port)
        transfer_headers.append(("Transfer-Encoding", "chunked"))
        raw = _exchange(harness.port, _request_bytes(path, transfer_headers))
        assert _status(raw) == 400
        assert _error_code(raw) == "PROGRESS_REQUEST_BODY_FORBIDDEN"

        duplicate_accept_headers = _sse_headers(harness.port)
        duplicate_accept_headers.append(("Accept", "text/event-stream"))
        raw = _exchange(
            harness.port,
            _request_bytes(path, duplicate_accept_headers),
        )
        assert _status(raw) == 406
        assert _error_code(raw) == "PROGRESS_SSE_ACCEPT_REQUIRED"

        duplicate_cursor_headers = _sse_headers(harness.port)
        cursor = "p1-1-" + "0" * 64
        duplicate_cursor_headers.extend(
            [("Last-Event-ID", cursor), ("Last-Event-ID", cursor)]
        )
        raw = _exchange(
            harness.port,
            _request_bytes(path, duplicate_cursor_headers),
        )
        assert _status(raw) == 400
        assert _error_code(raw) == "PROGRESS_CURSOR_INVALID"

        duplicate_authorization_headers = _sse_headers(harness.port)
        duplicate_authorization_headers.append(
            ("Authorization", f"Bearer {_TOKEN}")
        )
        raw = _exchange(
            harness.port,
            _request_bytes(path, duplicate_authorization_headers),
        )
        assert _status(raw) == 401
        assert _error_code(raw) == "BEARER_TOKEN_INVALID"

        zero_length_headers = _sse_headers(harness.port)
        zero_length_headers.append(("Content-Length", "0"))
        raw = _exchange(
            harness.port,
            _request_bytes(path, zero_length_headers),
        )
        assert _status(raw) == 200


def test_websocket_accepts_rfc_ows_and_rejects_ambiguous_headers(tmp_path: Path) -> None:
    with _running_server(tmp_path) as harness:
        close_echo = _masked_frame(0x8, b"\x03\xe8")
        ows_headers = _websocket_headers(
            harness.port,
            connection="keep-alive, \tUpgrade \t",
        )
        ows_headers = [
            (name, "\twebsocket \t" if name == "Upgrade" else value)
            for name, value in ows_headers
        ]
        raw = _exchange(
            harness.port,
            _request_bytes(
                harness.task_websocket_path,
                ows_headers,
                suffix=close_echo,
            ),
        )
        assert _status(raw) == 101
        _, frames = _headers_and_body(raw)
        assert frames.endswith(b"\x88\x02\x03\xe8")

        for ambiguous_connection in (
            "Upgrade, Upgrade",
            "close, Upgrade",
            "Upgrade, bad token",
        ):
            rejected = _exchange(
                harness.port,
                _request_bytes(
                    harness.task_websocket_path,
                    _websocket_headers(
                        harness.port,
                        connection=ambiguous_connection,
                    ),
                ),
            )
            assert _status(rejected) == 400
            assert _error_code(rejected) == "PROGRESS_WEBSOCKET_HANDSHAKE_INVALID"

        for name, value in (
            ("Upgrade", "websocket"),
            ("Connection", "Upgrade"),
            ("Sec-WebSocket-Version", "13"),
            (
                "Sec-WebSocket-Key",
                base64.b64encode(b"0123456789abcdef").decode("ascii"),
            ),
        ):
            headers = _websocket_headers(harness.port)
            headers.append((name, value))
            rejected = _exchange(
                harness.port,
                _request_bytes(harness.task_websocket_path, headers),
            )
            assert _status(rejected) == 400
            assert _error_code(rejected) == "PROGRESS_WEBSOCKET_HANDSHAKE_INVALID"

        for optional_header in ("Sec-WebSocket-Protocol", "Sec-WebSocket-Extensions"):
            headers = _websocket_headers(harness.port)
            headers.append((optional_header, "untrusted-client-selection"))
            rejected = _exchange(
                harness.port,
                _request_bytes(harness.task_websocket_path, headers),
            )
            assert _status(rejected) == 400
            assert _error_code(rejected) == "PROGRESS_WEBSOCKET_HANDSHAKE_INVALID"

        unsupported = _exchange(
            harness.port,
            _request_bytes(
                harness.task_websocket_path,
                _websocket_headers(harness.port, version="12"),
            ),
        )
        headers, _ = _headers_and_body(unsupported)
        assert _status(unsupported) == 426
        assert b"Sec-WebSocket-Version: 13\r\n" in headers + b"\r\n"
        assert b"Connection: close\r\n" in headers + b"\r\n"
        assert _error_code(unsupported) == "PROGRESS_WEBSOCKET_VERSION_UNSUPPORTED"


def test_websocket_reads_only_bounded_masked_peer_close_and_times_out(tmp_path: Path) -> None:
    with _running_server(tmp_path) as harness:
        handshake = _request_bytes(
            harness.task_websocket_path,
            _websocket_headers(harness.port),
        )

        echoed = _exchange(
            harness.port,
            handshake + _masked_frame(0x8, b"\x03\xe8"),
        )
        assert _status(echoed) == 101
        _, echoed_frames = _headers_and_body(echoed)
        assert echoed_frames.endswith(b"\x88\x02\x03\xe8")

        timed_out, elapsed = _exchange_without_peer_close(harness.port, handshake)
        assert _status(timed_out) == 101
        _, timed_out_frames = _headers_and_body(timed_out)
        assert timed_out_frames.endswith(b"\x88\x02\x03\xe8")
        assert 0.10 <= elapsed < 1.5

        forbidden_command = b'{"command":"change-subscription"}'
        rejected_data = _exchange(
            harness.port,
            handshake
            + _masked_frame(
                0x1,
                forbidden_command,
                mask=b"\x00\x00\x00\x00",
            ),
        )
        assert _status(rejected_data) == 101
        _, rejected_frames = _headers_and_body(rejected_data)
        assert rejected_frames.endswith(b"\x88\x02\x03\xe8")
        assert forbidden_command not in rejected_frames

        # A control frame cannot use extended lengths.  The server rejects it
        # from the two-byte header and never allocates or reads the claimed 126
        # byte payload.
        oversized_close = _exchange(
            harness.port,
            handshake + b"\x88\xfe" + b"\x00\x7e",
        )
        assert _status(oversized_close) == 101
        _, oversized_frames = _headers_and_body(oversized_close)
        assert oversized_frames.endswith(b"\x88\x02\x03\xe8")
