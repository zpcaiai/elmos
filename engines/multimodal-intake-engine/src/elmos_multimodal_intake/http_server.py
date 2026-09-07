"""Minimal authenticated HTTP adapter for the local reference runtime."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import math
import re
import secrets
import socket
from collections.abc import Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from threading import BoundedSemaphore, Lock
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from .canonical import MAX_SAFE_JSON_INTEGER, canonical_json, require_actor_id, require_resource_id
from .cli import RuntimeFactory, _compose, _runtime_root
from .contracts import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, SkillExecutionRequest
from .errors import IntakeError, ValidationError

from .models import TenantContext
from .progress_stream import ProgressBatch, ProgressStreamReader, parse_progress_cursor


CAPABILITIES_PATH = "/api/v1/multimodal-intake/capabilities"
EXECUTE_PATH = "/api/v1/multimodal-intake/execute"
PROGRESS_TASK_EVENTS_PREFIX = "/api/v1/multimodal-intake/progress/tasks/"
PROGRESS_JOB_EVENTS_PREFIX = "/api/v1/multimodal-intake/progress/jobs/"
PROGRESS_TASK_WEBSOCKET_PREFIX = "/api/v1/multimodal-intake/progress/ws/tasks/"
PROGRESS_JOB_WEBSOCKET_PREFIX = "/api/v1/multimodal-intake/progress/ws/jobs/"
_PUBLIC_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_:-]{0,127}$")
_SAFE_ROUTE_ID = r"([A-Za-z0-9][A-Za-z0-9._:-]{0,127})"
_PROGRESS_ROUTES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(rf"^{re.escape(PROGRESS_TASK_EVENTS_PREFIX)}{_SAFE_ROUTE_ID}/events$"), "sse", "task"),
    (re.compile(rf"^{re.escape(PROGRESS_JOB_EVENTS_PREFIX)}{_SAFE_ROUTE_ID}/events$"), "sse", "job"),
    (re.compile(rf"^{re.escape(PROGRESS_TASK_WEBSOCKET_PREFIX)}{_SAFE_ROUTE_ID}$"), "websocket", "task"),
    (re.compile(rf"^{re.escape(PROGRESS_JOB_WEBSOCKET_PREFIX)}{_SAFE_ROUTE_ID}$"), "websocket", "job"),
)
_WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_HTTP_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_WEBSOCKET_CLOSE_TIMEOUT_SECONDS = 0.25
_WEBSOCKET_MAX_CLIENT_CLOSE_BYTES = 2 + 4 + 125
_BOUND_TENANT_HEADER = "X-ELMOS-Bound-Tenant"
_BOUND_PROJECT_HEADER = "X-ELMOS-Bound-Project"
_BOUND_ACTOR_HEADER = "X-ELMOS-Bound-Actor"
MAX_HTTP_WORKERS = 8


class _WebSocketVersionUnsupported(ValidationError):
    """Internal discriminator for the RFC 6455 426 response."""


class _ProgressBoundIdentityMismatch(ValidationError):
    """Internal discriminator for a BFF context that is not server-bound."""


class _BoundedThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded loopback server with a hard worker cap and joined shutdown."""

    daemon_threads = False
    block_on_close = True
    request_queue_size = 16

    def __init__(
        self,
        server_address: Any,
        request_handler_class: type[BaseHTTPRequestHandler],
        bind_and_activate: bool = True,
        *,
        maximum_workers: int = MAX_HTTP_WORKERS,
    ) -> None:
        if (
            not isinstance(maximum_workers, int)
            or isinstance(maximum_workers, bool)
            or not 2 <= maximum_workers <= MAX_HTTP_WORKERS
        ):
            raise ValueError("HTTP_WORKER_LIMIT_INVALID")
        self.maximum_workers = maximum_workers
        self._request_slots = BoundedSemaphore(maximum_workers)
        super().__init__(server_address, request_handler_class, bind_and_activate)

    def process_request(
        self,
        request: socket.socket | tuple[bytes, socket.socket],
        client_address: Any,
    ) -> None:
        # Never create an unbounded thread or queue inside the process. The OS
        # listen backlog is bounded separately; excess accepted connections are
        # closed without parsing content or invoking a handler.
        if not self._request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(
        self,
        request: socket.socket | tuple[bytes, socket.socket],
        client_address: Any,
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


def _http_token_list(value: str) -> tuple[str, ...]:
    """Parse RFC field OWS around comma-separated tokens without ambiguity."""

    if not isinstance(value, str) or not value:
        raise ValidationError("PROGRESS_WEBSOCKET_HANDSHAKE_INVALID")
    tokens: list[str] = []
    seen: set[str] = set()
    for part in value.split(","):
        token = part.strip(" \t")
        if not token or not _HTTP_TOKEN.fullmatch(token):
            raise ValidationError("PROGRESS_WEBSOCKET_HANDSHAKE_INVALID")
        normalized = token.lower()
        if normalized in seen:
            raise ValidationError("PROGRESS_WEBSOCKET_HANDSHAKE_INVALID")
        seen.add(normalized)
        tokens.append(normalized)
    return tuple(tokens)


def _single_http_token(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("PROGRESS_WEBSOCKET_HANDSHAKE_INVALID")
    token = value.strip(" \t")
    if not token or not _HTTP_TOKEN.fullmatch(token):
        raise ValidationError("PROGRESS_WEBSOCKET_HANDSHAKE_INVALID")
    return token.lower()


def _progress_path(path: str) -> tuple[str, str, str] | None:
    for pattern, transport, resource_kind in _PROGRESS_ROUTES:
        matched = pattern.fullmatch(path)
        if matched is not None:
            return transport, resource_kind, matched.group(1)
    return None


def _progress_target(target: str) -> tuple[str, str, str, str | None] | None:
    if not isinstance(target, str) or len(target) > 2048:
        raise ValidationError("PROGRESS_REQUEST_TARGET_INVALID")
    parsed = urlsplit(target)
    route = _progress_path(parsed.path)
    if route is None:
        return None
    if parsed.scheme or parsed.netloc or parsed.fragment or len(parsed.query) > 512:
        raise ValidationError("PROGRESS_REQUEST_TARGET_INVALID")
    try:
        pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=2,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise ValidationError("PROGRESS_QUERY_INVALID") from error
    if len(pairs) > 1 or any(key != "cursor" or not value for key, value in pairs):
        raise ValidationError("PROGRESS_QUERY_INVALID")
    cursor = pairs[0][1] if pairs else None
    parse_progress_cursor(cursor)
    return (*route, cursor)


def _websocket_text_frame(payload: bytes) -> bytes:
    if not payload or len(payload) > MAX_RESPONSE_BYTES:
        raise ValidationError("PROGRESS_WEBSOCKET_PAYLOAD_INVALID")
    if len(payload) <= 125:
        header = bytes((0x81, len(payload)))
    elif len(payload) <= 65_535:
        header = bytes((0x81, 126)) + len(payload).to_bytes(2, "big")
    else:
        header = bytes((0x81, 127)) + len(payload).to_bytes(8, "big")
    return header + payload


def _reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _safe_json_int(value: str) -> int:
    parsed = int(value)
    if abs(parsed) > MAX_SAFE_JSON_INTEGER:
        raise ValueError("JSON integer exceeds the interoperable safe range")
    return parsed


def _safe_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("JSON number is not finite")
    if parsed.is_integer() and abs(parsed) > MAX_SAFE_JSON_INTEGER:
        raise ValueError("JSON integer exceeds the interoperable safe range")
    return parsed


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def _server_class(
    *,
    data_root: Path,
    bearer_token: str,
    tenant_id: str,
    project_id: str,
    actor_id: str,
    runtime_factory: RuntimeFactory | None = None,
) -> type[BaseHTTPRequestHandler]:
    """Compose one trusted runtime and return its private HTTP handler.

    The supported :func:`serve` entry point owns the complete lifecycle.  A
    direct ``HTTPServer(..., _server_class(...))`` embedder MUST also invoke
    ``Handler.close_runtime()`` in its ``finally`` block: before the first
    request there is no handler instance that could bind runtime cleanup to the
    third-party server object's ``server_close`` method.
    """

    # The trusted host composes one runtime for the whole server lifecycle.
    # Progress readers, capabilities and execution all use this exact runtime;
    # a GET can therefore never instantiate or migrate an independent store.
    root = _runtime_root(data_root)
    context = TenantContext(tenant_id, project_id, actor_id)
    runtime, api = _compose(
        root,
        bound_context=context,
        runtime_factory=runtime_factory,
    )
    try:
        progress_reader = ProgressStreamReader(runtime.store)
    except BaseException:
        runtime.close()
        raise
    lifecycle_lock = Lock()
    runtime_closed = False
    runtime_owner_token = object()

    class Handler(BaseHTTPRequestHandler):
        server_version = "ELMOSMultimodalIntake/1.0"
        sys_version = ""

        @classmethod
        def close_runtime(cls) -> None:
            """Release the server-owned runtime once, even after repeated close calls."""

            nonlocal runtime_closed
            with lifecycle_lock:
                if runtime_closed:
                    return
                runtime_closed = True
            runtime.close()

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(30.0)
            # Boundary errors can occur before an execution request has a
            # trusted caller-supplied trace.  Give every handler a private,
            # non-user-controlled correlation identifier so direct HTTP SDKs
            # still receive the exact five-field error contract.
            self._http_trace_id = f"http-{secrets.token_hex(16)}"
            # Direct embedders historically construct ``HTTPServer`` with the
            # returned handler class.  Bind its normal server_close lifecycle
            # to the same idempotent runtime closer without requiring a second
            # public server factory.
            with lifecycle_lock:
                owner = getattr(
                    self.server,
                    "_elmos_multimodal_runtime_owner",
                    None,
                )
                if owner is None:
                    original_server_close = self.server.server_close

                    def close_server_and_runtime() -> None:
                        try:
                            original_server_close()
                        finally:
                            Handler.close_runtime()

                    setattr(
                        self.server,
                        "_elmos_multimodal_runtime_owner",
                        runtime_owner_token,
                    )
                    setattr(self.server, "server_close", close_server_and_runtime)
                elif owner is not runtime_owner_token:
                    raise RuntimeError("HTTP server already owns a different runtime")

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _authorized(self) -> bool:
            headers = getattr(self, "headers", None)
            if headers is None:
                return False
            values = headers.get_all("Authorization", [])
            if len(values) != 1:
                return False
            supplied = values[0]
            expected = f"Bearer {bearer_token}"
            return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))

        def _loopback_client(self) -> bool:
            try:
                address = str(self.client_address[0]).split("%", 1)[0]
                return ipaddress.ip_address(address).is_loopback
            except (IndexError, TypeError, ValueError):
                return False

        def _boundary_authorized(self, *, head_only: bool = False) -> bool:
            if not self._loopback_client():
                self._error(
                    HTTPStatus.FORBIDDEN,
                    "HTTP_LOOPBACK_REQUIRED",
                    head_only=head_only,
                )
                return False
            if not self._authorized():
                self._error(
                    HTTPStatus.UNAUTHORIZED,
                    "BEARER_TOKEN_INVALID",
                    head_only=head_only,
                )
                return False
            return True

        def _progress_host_is_valid(self) -> bool:
            if self.request_version != "HTTP/1.1":
                return False
            values = self.headers.get_all("Host", [])
            if len(values) != 1:
                return False
            value = values[0]
            if (
                not value
                or len(value) > 255
                or "%" in value
                or value != value.strip(" \t")
                or any(ord(character) < 33 or ord(character) > 126 for character in value)
            ):
                return False
            try:
                authority = urlsplit(f"//{value}")
                hostname = authority.hostname
                port = authority.port
            except ValueError:
                return False
            if (
                not hostname
                or authority.username is not None
                or authority.password is not None
                or authority.path
                or authority.query
                or authority.fragment
                or port is None
            ):
                return False
            try:
                loopback_host = (
                    hostname.lower() == "localhost"
                    or ipaddress.ip_address(hostname.split("%", 1)[0]).is_loopback
                )
            except ValueError:
                loopback_host = False
            server_address = self.server.server_address
            if not isinstance(server_address, tuple) or len(server_address) < 2:
                return False
            try:
                expected_port = int(server_address[1])
            except (IndexError, TypeError, ValueError):
                return False
            return loopback_host and port == expected_port

        def _progress_cursor(self, query_cursor: str | None) -> str | None:
            values = self.headers.get_all("Last-Event-ID", [])
            if len(values) > 1:
                raise ValidationError("PROGRESS_CURSOR_INVALID")
            header_cursor = values[0] if values else None
            parse_progress_cursor(header_cursor)
            if (
                query_cursor is not None
                and header_cursor is not None
                and not hmac.compare_digest(
                    query_cursor.encode("ascii"),
                    header_cursor.encode("ascii"),
                )
            ):
                raise ValidationError("PROGRESS_CURSOR_CONFLICT")
            return query_cursor if query_cursor is not None else header_cursor

        def _validate_progress_request_headers(self) -> None:
            if not self._progress_host_is_valid():
                raise ValidationError("PROGRESS_HOST_INVALID")
            if self.headers.get_all("Transfer-Encoding", []):
                raise ValidationError("PROGRESS_REQUEST_BODY_FORBIDDEN")
            lengths = self.headers.get_all("Content-Length", [])
            if lengths and (len(lengths) != 1 or lengths[0] != "0"):
                raise ValidationError("PROGRESS_REQUEST_BODY_FORBIDDEN")
            expected_scope = (
                (_BOUND_TENANT_HEADER, tenant_id),
                (_BOUND_PROJECT_HEADER, project_id),
                (_BOUND_ACTOR_HEADER, actor_id),
            )
            for header, expected in expected_scope:
                values = self.headers.get_all(header, [])
                if len(values) != 1 or not hmac.compare_digest(
                    values[0].encode("utf-8"),
                    expected.encode("utf-8"),
                ):
                    raise _ProgressBoundIdentityMismatch("BOUND_IDENTITY_MISMATCH")

        def _progress_batch(
            self,
            resource_kind: str,
            resource_id: str,
            cursor: str | None,
        ) -> ProgressBatch:
            if resource_kind == "task":
                return progress_reader.task_events(context, resource_id, cursor=cursor)
            if resource_kind == "job":
                return progress_reader.job_events(context, resource_id, cursor=cursor)
            raise ValidationError("PROGRESS_RESOURCE_KIND_INVALID")

        @staticmethod
        def _progress_documents(batch: ProgressBatch) -> tuple[tuple[str, Mapping[str, Any]], ...]:
            if batch.documents and batch.heartbeat is not None:
                raise ValidationError("PROGRESS_BATCH_INVALID")
            if batch.documents:
                return tuple(("progress", document) for document in batch.documents)
            if batch.heartbeat is not None:
                return (("heartbeat", batch.heartbeat),)
            raise ValidationError("PROGRESS_BATCH_INVALID")

        def _write_sse(self, batch: ProgressBatch) -> None:
            chunks: list[bytes] = []
            total = 0
            for event_name, document in self._progress_documents(batch):
                encoded = canonical_json(document).encode("utf-8")
                cursor = document.get("cursor")
                prefix = b""
                if event_name == "progress":
                    if not isinstance(cursor, str) or not cursor.isascii():
                        raise ValidationError("PROGRESS_BATCH_INVALID")
                    prefix = f"id: {cursor}\n".encode("ascii")
                chunk = prefix + f"event: {event_name}\n".encode("ascii") + b"data: " + encoded + b"\n\n"
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise ValidationError("PROGRESS_RESPONSE_TOO_LARGE")
                chunks.append(chunk)
            body = b"".join(chunks)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "private, no-store, max-age=0")
            self.send_header("Connection", "close")
            self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.close_connection = True
            try:
                self.wfile.write(body)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                return

        def _websocket_key(self) -> str:
            if self.request_version != "HTTP/1.1":
                raise ValidationError("PROGRESS_WEBSOCKET_HANDSHAKE_INVALID")
            upgrades = self.headers.get_all("Upgrade", [])
            connections = self.headers.get_all("Connection", [])
            versions = self.headers.get_all("Sec-WebSocket-Version", [])
            keys = self.headers.get_all("Sec-WebSocket-Key", [])
            if (
                len(upgrades) != 1
                or len(connections) != 1
                or len(versions) != 1
                or len(keys) != 1
                or self.headers.get_all("Sec-WebSocket-Protocol")
                or self.headers.get_all("Sec-WebSocket-Extensions")
            ):
                raise ValidationError("PROGRESS_WEBSOCKET_HANDSHAKE_INVALID")
            if _single_http_token(upgrades[0]) != "websocket":
                raise ValidationError("PROGRESS_WEBSOCKET_HANDSHAKE_INVALID")
            connection_tokens = _http_token_list(connections[0])
            if "upgrade" not in connection_tokens or "close" in connection_tokens:
                raise ValidationError("PROGRESS_WEBSOCKET_HANDSHAKE_INVALID")
            if versions[0] != "13":
                raise _WebSocketVersionUnsupported(
                    "PROGRESS_WEBSOCKET_VERSION_UNSUPPORTED"
                )
            key = keys[0]
            try:
                decoded = base64.b64decode(key, validate=True)
            except (binascii.Error, ValueError) as error:
                raise ValidationError("PROGRESS_WEBSOCKET_KEY_INVALID") from error
            if len(decoded) != 16 or base64.b64encode(decoded).decode("ascii") != key:
                raise ValidationError("PROGRESS_WEBSOCKET_KEY_INVALID")
            return key

        def _read_websocket_bytes(self, count: int) -> bytes:
            if not 0 <= count <= _WEBSOCKET_MAX_CLIENT_CLOSE_BYTES:
                raise ValidationError("PROGRESS_WEBSOCKET_CLIENT_FRAME_INVALID")
            value = bytearray()
            while len(value) < count:
                chunk = self.rfile.read(count - len(value))
                if not chunk:
                    raise EOFError("peer closed during WebSocket close acknowledgement")
                value.extend(chunk)
            return bytes(value)

        def _read_peer_websocket_close(self) -> bytes:
            """Read one bounded masked peer close; client data is never accepted."""

            header = self._read_websocket_bytes(2)
            first, second = header
            # FIN=1, RSV=0 and opcode=close are exact because extensions are
            # forbidden at handshake.  Every client frame must be masked.
            if first != 0x88 or second & 0x80 == 0:
                raise ValidationError("PROGRESS_WEBSOCKET_CLIENT_FRAME_FORBIDDEN")
            payload_length = second & 0x7F
            if payload_length > 125 or payload_length == 1:
                raise ValidationError("PROGRESS_WEBSOCKET_CLIENT_CLOSE_INVALID")
            mask = self._read_websocket_bytes(4)
            encoded = self._read_websocket_bytes(payload_length)
            payload = bytes(
                value ^ mask[index % 4]
                for index, value in enumerate(encoded)
            )
            if payload_length >= 2:
                code = int.from_bytes(payload[:2], "big")
                valid_code = (
                    1000 <= code <= 1014
                    and code not in {1004, 1005, 1006}
                    or 3000 <= code <= 4999
                )
                if not valid_code:
                    raise ValidationError("PROGRESS_WEBSOCKET_CLIENT_CLOSE_INVALID")
                try:
                    payload[2:].decode("utf-8", errors="strict")
                except UnicodeDecodeError as error:
                    raise ValidationError(
                        "PROGRESS_WEBSOCKET_CLIENT_CLOSE_INVALID"
                    ) from error
            return payload

        def _write_websocket(self, key: str, batch: ProgressBatch) -> None:
            frames: list[bytes] = []
            total = 0
            for _, document in self._progress_documents(batch):
                frame = _websocket_text_frame(canonical_json(document).encode("utf-8"))
                total += len(frame)
                if total > MAX_RESPONSE_BYTES:
                    raise ValidationError("PROGRESS_RESPONSE_TOO_LARGE")
                frames.append(frame)
            accept = base64.b64encode(
                hashlib.sha1((key + _WEBSOCKET_GUID).encode("ascii")).digest()
            ).decode("ascii")
            # Only this successful upgrade response uses HTTP/1.1.  Existing
            # JSON adapter responses retain their prior HTTP/1.0 behavior.
            self.protocol_version = "HTTP/1.1"
            self.send_response(HTTPStatus.SWITCHING_PROTOCOLS)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept)
            self.send_header("Cache-Control", "private, no-store, max-age=0")
            self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.close_connection = True
            try:
                for frame in frames:
                    self.wfile.write(frame)
                # Initiate an orderly close, then accept only the client's
                # bounded masked close acknowledgement.  Text, binary, ping,
                # pong, continuation and fragmented frames are never commands.
                self.wfile.write(b"\x88\x02\x03\xe8")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                return
            try:
                self.connection.settimeout(_WEBSOCKET_CLOSE_TIMEOUT_SECONDS)
                self._read_peer_websocket_close()
            except (
                EOFError,
                IntakeError,
                BrokenPipeError,
                ConnectionResetError,
                TimeoutError,
                OSError,
            ):
                # The response is already upgraded and closed.  Protocol
                # violations and missing acknowledgements terminate the socket;
                # they must not produce an invalid second HTTP response.
                return

        def _write(
            self,
            status: int,
            document: Mapping[str, Any],
            *,
            head_only: bool = False,
            extra_headers: Mapping[str, str] | None = None,
        ) -> None:
            try:
                encoded = canonical_json(document).encode("utf-8")
                if len(encoded) > MAX_RESPONSE_BYTES:
                    raise ValueError("response exceeds the transport limit")
            except (TypeError, ValueError, IntakeError):
                status = HTTPStatus.INTERNAL_SERVER_ERROR
                encoded = canonical_json(
                    {
                        "schema_version": "1.0.0",
                        "status": "FAILED",
                        "code": "MULTIMODAL_INTERNAL_ERROR",
                        "retryable": True,
                        "trace_id": self._http_trace_id,
                    }
                ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "private, no-store, max-age=0")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if not head_only:
                self.wfile.write(encoded)

        def _error(
            self,
            status: int,
            code: str,
            *,
            retryable: bool = False,
            head_only: bool = False,
            extra_headers: Mapping[str, str] | None = None,
        ) -> None:
            if not isinstance(code, str) or not _PUBLIC_ERROR_CODE.fullmatch(code):
                code = "MULTIMODAL_INTERNAL_ERROR" if int(status) >= 500 else "MULTIMODAL_BOUNDARY_ERROR"
            self._write(
                status,
                {
                    "schema_version": "1.0.0",
                    "status": "FAILED" if int(status) >= 500 else "BLOCKED",
                    "code": code,
                    "retryable": retryable,
                    "trace_id": self._http_trace_id,
                },
                head_only=head_only,
                extra_headers=extra_headers,
            )

        def _method_not_allowed(self) -> None:
            head_only = self.command == "HEAD"
            if not self._boundary_authorized(head_only=head_only):
                return
            request_path = urlsplit(self.path).path
            if request_path == CAPABILITIES_PATH:
                allowed = "GET"
            elif request_path == EXECUTE_PATH:
                allowed = "POST"
            elif _progress_path(request_path) is not None:
                allowed = "GET"
            else:
                self._error(
                    HTTPStatus.NOT_FOUND,
                    "MULTIMODAL_ROUTE_NOT_FOUND",
                    head_only=head_only,
                )
                return
            self._error(
                HTTPStatus.METHOD_NOT_ALLOWED,
                "MULTIMODAL_METHOD_NOT_ALLOWED",
                head_only=head_only,
                extra_headers={"Allow": allowed},
            )

        def send_error(
            self,
            code: int,
            message: str | None = None,
            explain: str | None = None,
        ) -> None:
            del message, explain
            if not self._boundary_authorized(
                head_only=getattr(self, "command", None) == "HEAD"
            ):
                return
            if code == HTTPStatus.NOT_IMPLEMENTED:
                self._method_not_allowed()
                return
            safe_status = code if 400 <= code <= 599 else HTTPStatus.INTERNAL_SERVER_ERROR
            self._error(
                safe_status,
                "MULTIMODAL_INTERNAL_ERROR" if safe_status >= 500 else "MULTIMODAL_BOUNDARY_ERROR",
                retryable=safe_status >= 500,
                head_only=self.command == "HEAD",
            )

        do_HEAD = _method_not_allowed  # noqa: N815 - BaseHTTPRequestHandler protocol
        do_PUT = _method_not_allowed  # noqa: N815 - BaseHTTPRequestHandler protocol
        do_PATCH = _method_not_allowed  # noqa: N815 - BaseHTTPRequestHandler protocol
        do_DELETE = _method_not_allowed  # noqa: N815 - BaseHTTPRequestHandler protocol
        do_OPTIONS = _method_not_allowed  # noqa: N815 - BaseHTTPRequestHandler protocol
        do_TRACE = _method_not_allowed  # noqa: N815 - BaseHTTPRequestHandler protocol
        do_CONNECT = _method_not_allowed  # noqa: N815 - BaseHTTPRequestHandler protocol

        def do_GET(self) -> None:  # noqa: N802
            if not self._boundary_authorized():
                return
            try:
                progress = _progress_target(self.path)
            except IntakeError as error:
                self._error(HTTPStatus.BAD_REQUEST, error.code, retryable=error.retryable)
                return
            if progress is not None:
                transport, resource_kind, resource_id, query_cursor = progress
                try:
                    self._validate_progress_request_headers()
                    cursor = self._progress_cursor(query_cursor)
                    key = self._websocket_key() if transport == "websocket" else None
                except _WebSocketVersionUnsupported as error:
                    self.protocol_version = "HTTP/1.1"
                    self._error(
                        HTTPStatus.UPGRADE_REQUIRED,
                        error.code,
                        extra_headers={
                            "Sec-WebSocket-Version": "13",
                            "Connection": "close",
                        },
                    )
                    self.close_connection = True
                    return
                except _ProgressBoundIdentityMismatch as error:
                    self._error(
                        HTTPStatus.FORBIDDEN,
                        error.code,
                        retryable=error.retryable,
                    )
                    return
                except IntakeError as error:
                    self._error(HTTPStatus.BAD_REQUEST, error.code, retryable=error.retryable)
                    return
                if transport == "sse":
                    accepts = self.headers.get_all("Accept", [])
                    if len(accepts) != 1 or accepts[0].strip().lower() != "text/event-stream":
                        self._error(HTTPStatus.NOT_ACCEPTABLE, "PROGRESS_SSE_ACCEPT_REQUIRED")
                        return
                try:
                    batch = self._progress_batch(resource_kind, resource_id, cursor)
                    if transport == "sse":
                        self._write_sse(batch)
                        return
                    if key is None:
                        raise ValidationError("PROGRESS_WEBSOCKET_HANDSHAKE_INVALID")
                    self._write_websocket(key, batch)
                    return
                except IntakeError as error:
                    self._error(error.http_status, error.code, retryable=error.retryable)
                    return
                except Exception:
                    self._error(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        "MULTIMODAL_INTERNAL_ERROR",
                        retryable=True,
                    )
                    return
            if self.path != CAPABILITIES_PATH:
                self._error(HTTPStatus.NOT_FOUND, "MULTIMODAL_ROUTE_NOT_FOUND")
                return
            try:
                response = api.capabilities()
            except IntakeError as error:
                self._error(error.http_status, error.code, retryable=error.retryable)
                return
            except Exception:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "MULTIMODAL_INTERNAL_ERROR", retryable=True)
                return
            self._write(response.status_code, response.body)

        def do_POST(self) -> None:  # noqa: N802
            if not self._boundary_authorized():
                return
            if _progress_path(urlsplit(self.path).path) is not None:
                self._method_not_allowed()
                return
            if self.path != EXECUTE_PATH:
                self._error(HTTPStatus.NOT_FOUND, "MULTIMODAL_ROUTE_NOT_FOUND")
                return
            content_types = self.headers.get_all("Content-Type", [])
            media_type = content_types[0].split(";", 1)[0].strip().lower() if len(content_types) == 1 else ""
            if media_type != "application/json":
                self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "JSON_CONTENT_TYPE_REQUIRED")
                return
            content_encodings = self.headers.get_all("Content-Encoding", [])
            if len(content_encodings) > 1 or (
                content_encodings and content_encodings[0].strip().lower() != "identity"
            ):
                self._error(
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                    "MULTIMODAL_CONTENT_ENCODING_UNSUPPORTED",
                )
                return
            if self.headers.get_all("Transfer-Encoding", []):
                self._error(HTTPStatus.BAD_REQUEST, "MULTIMODAL_TRANSFER_ENCODING_UNSUPPORTED")
                return
            lengths = self.headers.get_all("Content-Length", [])
            length = lengths[0] if len(lengths) == 1 else ""
            if not re.fullmatch(r"[0-9]+", length):
                self._error(HTTPStatus.BAD_REQUEST, "MULTIMODAL_REQUEST_SIZE_INVALID")
                return
            if len(length) > 10:
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "MULTIMODAL_REQUEST_SIZE_INVALID")
                return
            try:
                content_length = int(length)
            except ValueError:
                self._error(HTTPStatus.BAD_REQUEST, "MULTIMODAL_REQUEST_SIZE_INVALID")
                return
            if content_length <= 0:
                self._error(HTTPStatus.BAD_REQUEST, "MULTIMODAL_REQUEST_SIZE_INVALID")
                return
            if content_length > MAX_REQUEST_BYTES:
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "MULTIMODAL_REQUEST_SIZE_INVALID")
                return
            try:
                raw = self.rfile.read(content_length)
            except (TimeoutError, OSError):
                self._error(HTTPStatus.REQUEST_TIMEOUT, "MULTIMODAL_REQUEST_READ_TIMEOUT", retryable=True)
                return
            if len(raw) != content_length:
                self._error(HTTPStatus.BAD_REQUEST, "MULTIMODAL_REQUEST_SIZE_INVALID")
                return
            try:
                value = json.loads(
                    raw.decode("utf-8"),
                    parse_constant=_reject_non_finite_json,
                    parse_int=_safe_json_int,
                    parse_float=_safe_json_float,
                    object_pairs_hook=_unique_json_object,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
                self._error(HTTPStatus.BAD_REQUEST, "MULTIMODAL_REQUEST_JSON_INVALID")
                return
            if not isinstance(value, Mapping):
                self._error(HTTPStatus.BAD_REQUEST, "MULTIMODAL_REQUEST_INVALID")
                return
            try:
                SkillExecutionRequest.parse(value)
            except IntakeError as error:
                self._error(error.http_status, error.code, retryable=error.retryable)
                return
            if (
                value.get("tenant_id") != tenant_id
                or value.get("project_id") != project_id
                or value.get("actor_id") != actor_id
            ):
                self._error(HTTPStatus.FORBIDDEN, "BOUND_IDENTITY_MISMATCH")
                return
            try:
                response = api.execute(value)
            except IntakeError as error:
                self._error(error.http_status, error.code, retryable=error.retryable)
                return
            except Exception:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "MULTIMODAL_INTERNAL_ERROR", retryable=True)
                return
            self._write(response.status_code, response.body)

    return Handler


def serve(
    *,
    data_root: str | Path,
    bind: str,
    port: int,
    bearer_token: str,
    tenant_id: str,
    project_id: str,
    actor_id: str,
    runtime_factory: RuntimeFactory | None = None,
) -> None:
    if (
        not isinstance(bearer_token, str)
        or not 32 <= len(bearer_token) <= 4096
        or any(ord(character) < 33 or ord(character) > 126 for character in bearer_token)
    ):
        raise ValidationError("BEARER_TOKEN_REQUIRED")
    if not isinstance(bind, str) or not bind:
        raise ValidationError("HTTP_BIND_INVALID")
    try:
        loopback = bind == "localhost" or ipaddress.ip_address(bind).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        raise ValidationError("HTTP_BIND_LOOPBACK_REQUIRED")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValidationError("HTTP_PORT_INVALID")
    if not isinstance(tenant_id, str) or not isinstance(project_id, str) or not isinstance(actor_id, str):
        raise ValidationError("BOUND_IDENTITY_INVALID")
    safe_tenant = require_resource_id(tenant_id, "tenant_id")
    safe_project = require_resource_id(project_id, "project_id")
    safe_actor = require_actor_id(actor_id)
    root = _runtime_root(data_root)
    handler = _server_class(
        data_root=root,
        bearer_token=bearer_token,
        tenant_id=safe_tenant,
        project_id=safe_project,
        actor_id=safe_actor,
        runtime_factory=runtime_factory,
    )
    # One trusted runtime/API/store is owned by this server.  A bounded worker
    # pool lets an authenticated cancel request enter while a long-running
    # process request is active without permitting unbounded request threads.
    safe_bind = "127.0.0.1" if bind == "localhost" else bind
    server_class: type[_BoundedThreadingHTTPServer] = _BoundedThreadingHTTPServer
    if ipaddress.ip_address(safe_bind).version == 6:
        class IPv6HTTPServer(_BoundedThreadingHTTPServer):
            address_family = socket.AF_INET6

        server_class = IPv6HTTPServer
    try:
        server = server_class((safe_bind, port), handler)
    except BaseException:
        handler.close_runtime()  # type: ignore[attr-defined]
        raise
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.server_close()
        finally:
            # Handles the zero-request case.  When at least one handler ran,
            # server_close is already wrapped to call this same idempotent
            # closer, so runtime.close itself still executes exactly once.
            handler.close_runtime()  # type: ignore[attr-defined]


__all__ = [
    "CAPABILITIES_PATH",
    "EXECUTE_PATH",
    "PROGRESS_JOB_EVENTS_PREFIX",
    "PROGRESS_JOB_WEBSOCKET_PREFIX",
    "PROGRESS_TASK_EVENTS_PREFIX",
    "PROGRESS_TASK_WEBSOCKET_PREFIX",
    "serve",
]
