"""Dependency-free, fail-closed HTTP boundary for PDHI K9 operations.

Identity is obtained only from a host-injected trusted authenticator.  Request
JSON never creates or changes tenant, project, actor, authority, or environment
bindings.  The service can be mounted as a WSGI application; TLS, OIDC/JWKS,
rate limiting, and edge protections remain responsibilities of configured,
independently operated deployment adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
import threading
import time
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Protocol
import uuid

from .canonical import canonical_json_bytes, require_sha256_digest, strict_json_loads
from .control_plane import Invocation, ProductionControlPlane
from .errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    PDHIError,
    ValidationError,
)
from .runtime import RuntimeRegistry
from .store import (
    IdempotencyConflict,
    InvalidTransition,
    LeaseConflict,
    OptimisticConflict,
    ScopeBinding,
    ScopeViolation,
    SqlitePdhiStore,
    StoreError,
)


SERVICE_VERSION = "1.0.0"
DEFAULT_MAX_REQUEST_BYTES = 1 * 1024 * 1024
MAX_CONFIGURED_REQUEST_BYTES = 4 * 1024 * 1024
INVOKE_SCOPE = "pdhi.control.invoke"
READ_SCOPE = "pdhi.control.read"
OBSERVE_SCOPE = "pdhi.control.observe"


def _text(value: object, field_name: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValidationError(f"{field_name} is required", code="INVALID_SERVICE_TEXT")
    if len(value) > maximum or any(ord(char) < 0x20 for char in value):
        raise ValidationError(f"{field_name} is invalid", code="INVALID_SERVICE_TEXT")
    return value


@dataclass(frozen=True, slots=True)
class RequestMetadata:
    method: str
    path: str
    headers: Mapping[str, str]
    peer: str

    def __post_init__(self) -> None:
        if self.method not in {"GET", "POST"}:
            raise ValidationError("unsupported request method")
        _text(self.path, "path", maximum=2048)
        _text(self.peer, "peer", maximum=1024)
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


@dataclass(frozen=True, slots=True)
class TrustedPrincipal:
    """Server-derived identity and exact resource authorization binding."""

    tenant_id: str
    project_id: str
    actor_id: str
    authority_revision: str
    environment_revision: str
    authentication_context_digest: str
    issuer: str
    audience: str
    permissions: frozenset[str]
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in ("tenant_id", "project_id", "actor_id", "issuer", "audience"):
            _text(getattr(self, name), name)
        for name in (
            "authority_revision",
            "environment_revision",
            "authentication_context_digest",
        ):
            require_sha256_digest(getattr(self, name), field=name)
        if not isinstance(self.permissions, frozenset) or not self.permissions:
            raise ValidationError("permissions must be a non-empty frozenset")
        for permission in self.permissions:
            _text(permission, "permission")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValidationError("principal expiry must be timezone-aware")

    def require(self, permission: str, *, now: datetime | None = None) -> None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        if current >= self.expires_at.astimezone(UTC):
            raise AuthenticationError("authenticated principal has expired", code="PRINCIPAL_EXPIRED")
        if permission not in self.permissions:
            raise AuthorizationError(
                "authenticated principal lacks required permission",
                code="PERMISSION_DENIED",
                details={"permission": permission},
            )

    def scope_binding(self) -> ScopeBinding:
        return ScopeBinding(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            actor_id=self.actor_id,
            authority_revision=self.authority_revision,
            environment_revision=self.environment_revision,
        )


class AuthenticationError(PDHIError):
    """The trusted identity adapter could not authenticate the request."""


class RequestTooLarge(PDHIError):
    pass


class UnsupportedMediaType(PDHIError):
    pass


class Authenticator(Protocol):
    """Trusted gateway adapter; implementations must verify, not parse-only."""

    trusted_for_production: bool

    def authenticate(self, request: RequestMetadata) -> TrustedPrincipal: ...

    def readiness(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ServiceResponse:
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def json(cls, status: int, value: Mapping[str, Any], *, request_id: str) -> "ServiceResponse":
        body = canonical_json_bytes(value)
        return cls(
            status=status,
            body=body,
            headers=MappingProxyType(
                {
                    "Content-Type": "application/json; charset=utf-8",
                    "Content-Length": str(len(body)),
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
                    "Referrer-Policy": "no-referrer",
                    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                    "X-Request-ID": request_id,
                }
            ),
        )


class _ServiceMetrics:
    """Low-cardinality process counters; never labels tenant or user data."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, int], int] = {}
        self._duration_sum: dict[str, float] = {}

    def observe(self, route: str, status: int, duration: float) -> None:
        with self._lock:
            key = (route, status)
            self._requests[key] = self._requests.get(key, 0) + 1
            self._duration_sum[route] = self._duration_sum.get(route, 0.0) + duration

    def render(self) -> bytes:
        with self._lock:
            requests = tuple(sorted(self._requests.items()))
            durations = tuple(sorted(self._duration_sum.items()))
        lines = [
            "# HELP elmos_pdhi_http_requests_total Process-local HTTP request count.",
            "# TYPE elmos_pdhi_http_requests_total counter",
        ]
        for (route, status), count in requests:
            lines.append(
                f'elmos_pdhi_http_requests_total{{route="{route}",status="{status}"}} {count}'
            )
        lines.extend(
            (
                "# HELP elmos_pdhi_http_request_duration_seconds_sum Process-local request duration sum.",
                "# TYPE elmos_pdhi_http_request_duration_seconds_sum counter",
            )
        )
        for route, duration_sum in durations:
            lines.append(
                f'elmos_pdhi_http_request_duration_seconds_sum{{route="{route}"}} {duration_sum:.9f}'
            )
        lines.append("")
        return "\n".join(lines).encode("ascii")


class PdhiService:
    """HTTP API around the exact K9 dispatcher."""

    def __init__(
        self,
        control_plane: ProductionControlPlane,
        store: SqlitePdhiStore,
        authenticator: Authenticator,
        *,
        max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
        expected_audience: str = "elmos-pdhi",
        allow_local_authenticator: bool = False,
    ) -> None:
        if not isinstance(control_plane, ProductionControlPlane):
            raise ValidationError("control_plane must be ProductionControlPlane")
        if not isinstance(store, SqlitePdhiStore):
            raise ValidationError("store must be SqlitePdhiStore")
        if (
            isinstance(max_request_bytes, bool)
            or not isinstance(max_request_bytes, int)
            or max_request_bytes < 1024
            or max_request_bytes > MAX_CONFIGURED_REQUEST_BYTES
        ):
            raise ValidationError("max_request_bytes is outside the permitted range")
        if not getattr(authenticator, "trusted_for_production", False) and not allow_local_authenticator:
            raise ValidationError(
                "production service requires a trusted authenticator",
                code="UNTRUSTED_AUTHENTICATOR",
            )
        self._control_plane = control_plane
        self._store = store
        self._authenticator = authenticator
        self._max_request_bytes = max_request_bytes
        self._expected_audience = _text(expected_audience, "expected_audience")
        self._metrics = _ServiceMetrics()

    def _authenticate(self, metadata: RequestMetadata, permission: str) -> TrustedPrincipal:
        principal = self._authenticator.authenticate(metadata)
        if not isinstance(principal, TrustedPrincipal):
            raise AuthenticationError(
                "authenticator returned an untrusted principal type",
                code="INVALID_AUTHENTICATOR_RESULT",
            )
        if principal.audience != self._expected_audience:
            raise AuthenticationError("principal audience mismatch", code="AUDIENCE_MISMATCH")
        principal.require(permission)
        return principal

    def readiness(self) -> Mapping[str, Any]:
        try:
            auth = dict(self._authenticator.readiness())
        except Exception:
            auth = {"status": "NOT_READY", "reason": "authenticator readiness failed"}
        storage = dict(self._store.readiness())
        operational = auth.get("status") == "READY" and storage.get("status") == "READY"
        production_ready = operational and bool(storage.get("production_multi_replica"))
        return MappingProxyType(
            {
                "status": "READY" if operational else "NOT_READY",
                "accepting_requests": operational,
                "production_ready": production_ready,
                "authentication": auth,
                "storage": storage,
                "external_evidence": "NOT_RUN",
                "independent_verification": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            }
        )

    def handle(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
        peer: str = "unknown",
    ) -> ServiceResponse:
        started = time.monotonic()
        request_id = str(uuid.uuid4())
        normalized_headers = {
            str(key).strip().lower(): str(value).strip()
            for key, value in (headers or {}).items()
        }
        route = path if path in {
            "/healthz",
            "/readyz",
            "/version",
            "/metrics",
            "/v1/runtime/manifest",
            "/v1/control-plane/invocations",
        } else "unmatched"
        try:
            response = self._dispatch(
                method.upper(),
                path,
                normalized_headers,
                body,
                peer,
                request_id,
            )
        except Exception as exc:  # converted to a non-leaking machine error
            response = self._error_response(exc, request_id)
        self._metrics.observe(route, response.status, time.monotonic() - started)
        return response

    def _dispatch(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes,
        peer: str,
        request_id: str,
    ) -> ServiceResponse:
        if method not in {"GET", "POST"}:
            return self._error(405, "METHOD_NOT_ALLOWED", "method is not allowed", request_id)
        metadata = RequestMetadata(method=method, path=path, headers=headers, peer=peer)
        if method == "GET" and path == "/healthz":
            return ServiceResponse.json(
                200,
                {
                    "status": "ALIVE",
                    "service": "elmos-pdhi",
                    "external_evidence": "NOT_RUN",
                    "certification": "NOT_CERTIFIED",
                },
                request_id=request_id,
            )
        if method == "GET" and path == "/readyz":
            readiness = dict(self.readiness())
            return ServiceResponse.json(
                200 if readiness["accepting_requests"] else 503,
                readiness,
                request_id=request_id,
            )
        if method == "GET" and path == "/version":
            return ServiceResponse.json(
                200,
                {
                    "service": "elmos-pdhi",
                    "version": SERVICE_VERSION,
                    "certification": "NOT_CERTIFIED",
                },
                request_id=request_id,
            )
        if method == "GET" and path == "/metrics":
            self._authenticate(metadata, OBSERVE_SCOPE)
            payload = self._metrics.render()
            return ServiceResponse(
                200,
                payload,
                MappingProxyType(
                    {
                        "Content-Type": "text/plain; version=0.0.4; charset=utf-8",
                        "Content-Length": str(len(payload)),
                        "Cache-Control": "no-store",
                        "X-Content-Type-Options": "nosniff",
                        "X-Request-ID": request_id,
                    }
                ),
            )
        if method == "GET" and path == "/v1/runtime/manifest":
            self._authenticate(metadata, READ_SCOPE)
            return ServiceResponse.json(
                200,
                dict(RuntimeRegistry().manifest()),
                request_id=request_id,
            )
        if method == "POST" and path == "/v1/control-plane/invocations":
            if len(body) > self._max_request_bytes:
                raise RequestTooLarge("request body exceeds configured limit", code="REQUEST_TOO_LARGE")
            media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if media_type != "application/json":
                raise UnsupportedMediaType(
                    "Content-Type must be application/json",
                    code="UNSUPPORTED_MEDIA_TYPE",
                )
            principal = self._authenticate(metadata, INVOKE_SCOPE)
            value = strict_json_loads(body, source="PDHI invocation")
            if not isinstance(value, dict):
                raise ValidationError("invocation must be a JSON object", code="INVALID_INVOCATION")
            exact = {"operation", "idempotency_key", "payload"}
            if set(value) != exact:
                raise ValidationError(
                    "invocation fields must be exactly operation, idempotency_key, payload",
                    code="INVALID_INVOCATION_FIELDS",
                )
            if not isinstance(value["payload"], dict):
                raise ValidationError("payload must be a JSON object", code="INVALID_INVOCATION_PAYLOAD")
            outcome = self._control_plane.invoke(
                Invocation(
                    scope=principal.scope_binding(),
                    operation=_text(value["operation"], "operation"),
                    idempotency_key=_text(value["idempotency_key"], "idempotency_key"),
                    payload=value["payload"],
                )
            )
            return ServiceResponse.json(
                200,
                {
                    "request_id": request_id,
                    "result": outcome.to_dict(),
                    "authenticated_scope": {
                        "tenant_id": principal.tenant_id,
                        "project_id": principal.project_id,
                        "actor_id": principal.actor_id,
                        "authority_revision": principal.authority_revision,
                        "environment_revision": principal.environment_revision,
                    },
                },
                request_id=request_id,
            )
        return self._error(404, "ROUTE_NOT_FOUND", "route was not found", request_id)

    def _error_response(self, error: Exception, request_id: str) -> ServiceResponse:
        if isinstance(error, AuthenticationError):
            return self._error(401, error.code, "authentication failed", request_id)
        if isinstance(error, (AuthorizationError, ScopeViolation)):
            code = getattr(error, "code", "SCOPE_DENIED")
            return self._error(403, code, "authorization failed", request_id)
        if isinstance(error, RequestTooLarge):
            return self._error(413, error.code, str(error), request_id)
        if isinstance(error, UnsupportedMediaType):
            return self._error(415, error.code, str(error), request_id)
        if isinstance(error, (NotFoundError,)):
            return self._error(404, getattr(error, "code", "NOT_FOUND"), str(error), request_id)
        if isinstance(
            error,
            (ConflictError, IdempotencyConflict, OptimisticConflict, InvalidTransition, LeaseConflict),
        ):
            return self._error(409, getattr(error, "code", "CONFLICT"), str(error), request_id)
        if isinstance(error, ValidationError):
            return self._error(400, error.code, str(error), request_id)
        if isinstance(error, StoreError):
            return self._error(503, "STORAGE_UNAVAILABLE", "storage operation failed", request_id)
        if isinstance(error, PDHIError):
            return self._error(400, error.code, str(error), request_id)
        return self._error(500, "INTERNAL_ERROR", "internal service error", request_id)

    @staticmethod
    def _error(status: int, code: str, message: str, request_id: str) -> ServiceResponse:
        return ServiceResponse.json(
            status,
            {"error": {"code": code, "message": message, "request_id": request_id}},
            request_id=request_id,
        )

    def __call__(self, environ: Mapping[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        headers: dict[str, str] = {}
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                headers[key[5:].replace("_", "-").lower()] = str(value)
        if environ.get("CONTENT_TYPE"):
            headers["content-type"] = str(environ["CONTENT_TYPE"])
        if environ.get("HTTP_TRANSFER_ENCODING"):
            response = self._error(
                400,
                "TRANSFER_ENCODING_NOT_SUPPORTED",
                "transfer encoding is not supported by this WSGI boundary",
                str(uuid.uuid4()),
            )
        else:
            raw_length = environ.get("CONTENT_LENGTH", "")
            if method == "POST" and not raw_length:
                response = self._error(411, "CONTENT_LENGTH_REQUIRED", "Content-Length is required", str(uuid.uuid4()))
            else:
                try:
                    length = int(raw_length or "0")
                except ValueError:
                    length = -1
                if length < 0:
                    response = self._error(400, "INVALID_CONTENT_LENGTH", "Content-Length is invalid", str(uuid.uuid4()))
                elif length > self._max_request_bytes:
                    response = self._error(413, "REQUEST_TOO_LARGE", "request body exceeds configured limit", str(uuid.uuid4()))
                else:
                    stream = environ.get("wsgi.input")
                    body = b"" if stream is None else stream.read(length + 1)
                    response = self.handle(
                        method,
                        path,
                        headers=headers,
                        body=body,
                        peer=str(environ.get("REMOTE_ADDR", "unknown")),
                    )
        phrase = HTTPStatus(response.status).phrase
        start_response(
            f"{response.status} {phrase}",
            [(name, value) for name, value in response.headers.items()],
        )
        return (response.body,)


__all__ = [
    "AuthenticationError",
    "Authenticator",
    "DEFAULT_MAX_REQUEST_BYTES",
    "INVOKE_SCOPE",
    "OBSERVE_SCOPE",
    "PdhiService",
    "READ_SCOPE",
    "RequestMetadata",
    "ServiceResponse",
    "TrustedPrincipal",
]
