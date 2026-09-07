"""Fail-closed HTTP boundary for the durable proof-harness control plane."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import ssl
import stat
import threading
import time
from typing import Any, Callable, Mapping, Protocol, Type
import unicodedata
from urllib.parse import urlsplit
import uuid

from .canonical import digest_bytes
from .control_plane import DurableControlPlane
from .errors import HarnessError, ValidationError
from .observability import MetricsRegistry
from .skills import SKILL_REGISTRY, SkillRuntime


SERVICE_VERSION = "3.1.0"
SERVICE_CONTRACT_DIGEST = digest_bytes(
    b"elmos-proof-harness-http-contract:v3.1.0",
    domain="http-contract",
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,159}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_INVOCATION_DURATION_BUCKETS = (
    0.01,
    0.05,
    0.1,
    0.5,
    1.0,
    5.0,
    15.0,
    60.0,
    300.0,
    900.0,
)
_API_SCOPES = frozenset(
    {
        "proof-harness.invoke",
        "proof-harness.read",
        "proof-harness.cancel",
        "proof-harness.observe",
        "proof-harness.evidence.read",
        "proof-harness.review.read",
    }
)
_RSA_SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


@dataclass(frozen=True, slots=True)
class AuthPrincipal:
    """Server-derived identity and immutable execution-authority binding."""

    tenant_id: str
    project_id: str
    actor_id: str
    authority: tuple[str, ...]
    authentication_context_digest: str
    authority_id: str
    authority_revision: str
    environment_id: str
    environment_revision: str
    execution_epoch: int
    fencing_generation: int
    expires_at: datetime
    issuer: str = "local-static-authenticator"
    audience: str = "elmos-proof-harness"

    def __post_init__(self) -> None:
        for name in (
            "tenant_id",
            "project_id",
            "actor_id",
            "authority_id",
            "environment_id",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"invalid {name}")
        for name in (
            "authentication_context_digest",
            "authority_revision",
            "environment_revision",
        ):
            if not _is_digest(getattr(self, name)):
                raise ValueError(f"invalid {name}")
        if len(set(self.authority)) != len(self.authority):
            raise ValueError("authority entries must be unique")
        if any(not isinstance(item, str) or not item for item in self.authority):
            raise ValueError("authority entries must be non-empty strings")
        if self.execution_epoch < 1 or self.fencing_generation < 1:
            raise ValueError("execution epoch and fencing generation must be positive")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("principal expiry must be timezone-aware")
        for name in ("issuer", "audience"):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or not value
                or len(value) > 512
                or any(character in "\x00\r\n" for character in value)
            ):
                raise ValueError(f"invalid {name}")

    def context(self, request_id: str) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "actor_id": self.actor_id,
            "request_id": request_id,
            "authority": list(self.authority),
            "authentication_context_digest": self.authentication_context_digest,
            "authority_id": self.authority_id,
            "authority_revision": self.authority_revision,
            "environment_id": self.environment_id,
            "environment_revision": self.environment_revision,
            "execution_epoch": self.execution_epoch,
            "fencing_generation": self.fencing_generation,
        }


@dataclass(frozen=True, slots=True)
class ServiceResponse:
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def json(
        cls,
        status: int,
        value: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
        *,
        media_type: str = "application/json",
    ) -> "ServiceResponse":
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return cls(
            status,
            payload,
            {
                "Content-Type": f"{media_type}; charset=utf-8",
                "Content-Length": str(len(payload)),
                "Cache-Control": "no-store",
                **(headers or {}),
            },
        )


class AuthenticationError(RuntimeError):
    """Authentication failed without yielding a trusted principal."""


class Authenticator(Protocol):
    """Trusted identity-gateway boundary used by the production service."""

    trusted_for_production: bool

    def authenticate(self, headers: Mapping[str, str]) -> AuthPrincipal: ...

    def readiness(self) -> bool | tuple[bool, str]: ...


class StaticTokenAuthenticator:
    """Constant-time static token mapping for local engineering only."""

    trusted_for_production = False

    def __init__(self, tokens: Mapping[str, AuthPrincipal]) -> None:
        if not tokens:
            raise ValueError("at least one local authentication token is required")
        if any(not token or len(token.encode("utf-8")) < 16 for token in tokens):
            raise ValueError("local authentication tokens must contain at least 16 bytes")
        self._tokens = tuple(tokens.items())

    def authenticate(self, headers: Mapping[str, str]) -> AuthPrincipal:
        authorization = headers.get("authorization", "")
        scheme, separator, candidate = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not candidate:
            raise AuthenticationError("Bearer token is required")
        matched: AuthPrincipal | None = None
        candidate_bytes = candidate.encode("utf-8")
        # Compare against every configured token to avoid an early-exit timing
        # oracle over token order.
        for token, principal in self._tokens:
            if hmac.compare_digest(candidate_bytes, token.encode("utf-8")):
                matched = principal
        if matched is None:
            raise AuthenticationError("Bearer token is invalid")
        return matched

    def readiness(self) -> tuple[bool, str]:
        return True, "local static-token authenticator is configured"


@dataclass(frozen=True, slots=True)
class _RsaVerificationKey:
    kid: str
    modulus: int
    exponent: int
    byte_length: int


class FileJwksAuthenticator:
    """Built-in RS256 JWT verifier backed by a trusted read-only JWKS file.

    The verifier deliberately supports one locked algorithm and never fetches
    keys over the network.  Rotation is an explicit bounded file refresh; an
    invalid replacement fails closed and the readiness probe reports failure.
    """

    trusted_for_production = True

    def __init__(
        self,
        jwks_file: str | os.PathLike[str],
        *,
        issuer: str,
        audience: str,
        algorithm: str = "RS256",
        refresh_seconds: int = 300,
        leeway_seconds: int = 30,
        allowed_scopes: frozenset[str] = _API_SCOPES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        path = Path(jwks_file)
        if not path.is_absolute():
            raise ValueError("JWKS path must be absolute")
        if algorithm != "RS256":
            raise ValueError("built-in JWKS authentication supports only locked RS256")
        if not issuer or not audience:
            raise ValueError("JWT issuer and audience are required")
        if isinstance(refresh_seconds, bool) or not 1 <= refresh_seconds <= 86_400:
            raise ValueError("JWKS refresh interval is outside the safe range")
        if isinstance(leeway_seconds, bool) or not 0 <= leeway_seconds <= 300:
            raise ValueError("JWT clock leeway is outside the safe range")
        if not allowed_scopes:
            raise ValueError("at least one JWT scope must be allowlisted")
        self.jwks_file = path
        self.issuer = issuer
        self.audience = audience
        self.algorithm = algorithm
        self.refresh_seconds = refresh_seconds
        self.leeway_seconds = leeway_seconds
        self.allowed_scopes = allowed_scopes
        self._clock = clock or (lambda: datetime.now(UTC))
        self._keys: dict[str, _RsaVerificationKey] = {}
        self._loaded_monotonic = 0.0
        self._lock = threading.Lock()
        self._load_keys(force=True)

    def readiness(self) -> tuple[bool, str]:
        try:
            self._load_keys()
            return True, "trusted read-only JWKS is loaded"
        except Exception:
            return False, "trusted JWKS is unavailable or invalid"

    def authenticate(self, headers: Mapping[str, str]) -> AuthPrincipal:
        authorization = headers.get("authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token:
            raise AuthenticationError("Bearer JWT is required")
        if len(token) > 16 * 1024 or token.count(".") != 2:
            raise AuthenticationError("Bearer JWT is malformed")
        encoded_header, encoded_claims, encoded_signature = token.split(".")
        header = _decode_jwt_object(encoded_header, "header")
        if set(header) - {"alg", "kid", "typ"}:
            raise AuthenticationError("JWT header contains unsupported fields")
        if header.get("alg") != self.algorithm:
            raise AuthenticationError("JWT algorithm is not allowed")
        if header.get("typ", "JWT") != "JWT":
            raise AuthenticationError("JWT type is invalid")
        kid = header.get("kid")
        if not isinstance(kid, str) or not _IDENTIFIER.fullmatch(kid):
            raise AuthenticationError("JWT kid is required")
        self._load_keys()
        with self._lock:
            key = self._keys.get(kid)
        if key is None:
            # An unknown kid can be a just-rotated key.  Perform one immediate
            # stable-file refresh, then fail closed if it is still absent.
            self._load_keys(force=True)
            with self._lock:
                key = self._keys.get(kid)
        if key is None:
            raise AuthenticationError("JWT signing key is unavailable")
        signature = _decode_base64url(encoded_signature, "signature")
        signed = f"{encoded_header}.{encoded_claims}".encode("ascii")
        if not _verify_rs256(key, signed, signature):
            raise AuthenticationError("JWT signature is invalid")
        claims = _decode_jwt_object(encoded_claims, "claims")
        return self._principal_from_claims(claims)

    def _principal_from_claims(self, claims: Mapping[str, Any]) -> AuthPrincipal:
        now = self._clock().astimezone(UTC)
        issuer = claims.get("iss")
        audience = claims.get("aud")
        if not isinstance(issuer, str) or not hmac.compare_digest(issuer, self.issuer):
            raise AuthenticationError("JWT issuer is invalid")
        if isinstance(audience, list):
            valid_audience = len(audience) == 1 and audience[0] == self.audience
        else:
            valid_audience = isinstance(audience, str) and hmac.compare_digest(
                audience, self.audience
            )
        if not valid_audience:
            raise AuthenticationError("JWT audience is invalid")
        exp = _jwt_numeric_date(claims.get("exp"), "exp")
        nbf = _jwt_numeric_date(claims.get("nbf"), "nbf")
        if now.timestamp() >= exp + self.leeway_seconds:
            raise AuthenticationError("JWT has expired")
        if now.timestamp() + self.leeway_seconds < nbf:
            raise AuthenticationError("JWT is not yet valid")
        scope = claims.get("scope")
        if not isinstance(scope, str) or not scope.strip():
            raise AuthenticationError("JWT scope claim is required")
        scopes = tuple(item for item in scope.split(" ") if item)
        if len(set(scopes)) != len(scopes):
            raise AuthenticationError("JWT scope claim contains duplicates")
        if not set(scopes).issubset(self.allowed_scopes):
            raise AuthenticationError("JWT scope claim contains an unapproved grant")
        required = {
            "tenant_id",
            "project_id",
            "actor_id",
            "authentication_context_digest",
            "authority_id",
            "authority_revision",
            "environment_id",
            "environment_revision",
            "execution_epoch",
            "fencing_generation",
        }
        if any(name not in claims for name in required):
            raise AuthenticationError("JWT execution binding claims are incomplete")
        try:
            return AuthPrincipal(
                tenant_id=claims["tenant_id"],
                project_id=claims["project_id"],
                actor_id=claims["actor_id"],
                authority=scopes,
                authentication_context_digest=claims[
                    "authentication_context_digest"
                ],
                authority_id=claims["authority_id"],
                authority_revision=claims["authority_revision"],
                environment_id=claims["environment_id"],
                environment_revision=claims["environment_revision"],
                execution_epoch=claims["execution_epoch"],
                fencing_generation=claims["fencing_generation"],
                expires_at=datetime.fromtimestamp(exp, UTC),
                issuer=issuer,
                audience=self.audience,
            )
        except (TypeError, ValueError) as exc:
            raise AuthenticationError("JWT execution binding claims are invalid") from exc

    def _load_keys(self, *, force: bool = False) -> None:
        with self._lock:
            now = time.monotonic()
            if (
                not force
                and self._keys
                and now - self._loaded_monotonic < self.refresh_seconds
            ):
                return
            payload = _read_trusted_jwks(self.jwks_file)
            try:
                document = json.loads(
                    payload.decode("utf-8"),
                    object_pairs_hook=_strict_json_object,
                    parse_constant=_reject_json_constant,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                raise AuthenticationError("JWKS document is invalid JSON") from exc
            if not isinstance(document, dict) or set(document) != {"keys"}:
                raise AuthenticationError("JWKS document must contain only keys")
            entries = document["keys"]
            if not isinstance(entries, list) or not 1 <= len(entries) <= 128:
                raise AuthenticationError("JWKS key count is outside the safe range")
            keys: dict[str, _RsaVerificationKey] = {}
            for entry in entries:
                key = _parse_rsa_jwk(entry, self.algorithm)
                if key.kid in keys:
                    raise AuthenticationError("JWKS contains duplicate kid values")
                keys[key.kid] = key
            self._keys = keys
            self._loaded_monotonic = now


class HarnessService:
    """Authenticate, authorize, validate, and dispatch exact v3 contracts."""

    def __init__(
        self,
        runtime: SkillRuntime,
        *,
        auth_tokens: Mapping[str, AuthPrincipal] | None = None,
        authenticator: Authenticator | None = None,
        control_plane: DurableControlPlane | None = None,
        max_request_bytes: int = 2 * 1024 * 1024,
        metrics: MetricsRegistry | None = None,
        readiness_checks: Mapping[
            str, Callable[[], bool | tuple[bool, str]]
        ]
        | None = None,
        runtime_mode: str = "production",
        allow_legacy_local: bool = False,
        expected_issuer: str | None = None,
        expected_audience: str | None = None,
        transport_mode: str | None = None,
        tls_cert_file: str | None = None,
        tls_key_file: str | None = None,
        tls_client_ca_file: str | None = None,
        trusted_proxy_cidrs: tuple[str, ...] = (),
        request_timeout_seconds: float = 30.0,
        max_concurrent_requests: int = 64,
        graceful_shutdown_seconds: float = 30.0,
    ) -> None:
        if max_request_bytes < 1:
            raise ValueError("max_request_bytes must be positive")
        if runtime_mode not in {"local-engineering", "production"}:
            raise ValueError("runtime_mode must be local-engineering or production")
        if transport_mode is None:
            transport_mode = "local" if runtime_mode == "local-engineering" else ""
        if transport_mode not in {"local", "tls", "trusted-proxy"}:
            raise ValueError("transport_mode must be local, tls, or trusted-proxy")
        if allow_legacy_local and runtime_mode != "local-engineering":
            raise ValueError("legacy endpoints are permitted only in local-engineering mode")
        if auth_tokens is not None and authenticator is not None:
            raise ValueError("configure exactly one authentication boundary")
        if auth_tokens is not None:
            if runtime_mode != "local-engineering":
                raise ValueError(
                    "static token authentication is permitted only in local-engineering mode"
                )
            authenticator = StaticTokenAuthenticator(auth_tokens)
        if authenticator is None:
            raise ValueError("an authenticator is required")
        if runtime_mode == "production":
            if not bool(getattr(authenticator, "trusted_for_production", False)):
                raise ValueError(
                    "production requires a trusted identity-gateway authenticator"
                )
            if not expected_issuer or not expected_audience:
                raise ValueError(
                    "production requires exact expected issuer and audience bindings"
                )
            if transport_mode == "local":
                raise ValueError(
                    "production requires TLS or an explicitly trusted reverse proxy"
                )
        if transport_mode == "tls" and (not tls_cert_file or not tls_key_file):
            raise ValueError("TLS transport requires certificate and private-key files")
        parsed_proxy_networks: tuple[Any, ...] = ()
        if transport_mode == "trusted-proxy":
            if not trusted_proxy_cidrs:
                raise ValueError("trusted-proxy transport requires explicit proxy CIDRs")
            try:
                parsed_proxy_networks = tuple(
                    ipaddress.ip_network(value, strict=True)
                    for value in trusted_proxy_cidrs
                )
            except ValueError as exc:
                raise ValueError("trusted proxy CIDR is invalid or non-canonical") from exc
        if (
            isinstance(request_timeout_seconds, bool)
            or not 0.1 <= request_timeout_seconds <= 300
        ):
            raise ValueError("request timeout is outside the safe range")
        if (
            isinstance(max_concurrent_requests, bool)
            or not 1 <= max_concurrent_requests <= 4096
        ):
            raise ValueError("max concurrent requests is outside the safe range")
        if (
            isinstance(graceful_shutdown_seconds, bool)
            or not 0 <= graceful_shutdown_seconds <= 300
        ):
            raise ValueError("graceful shutdown timeout is outside the safe range")
        self.runtime = runtime
        self.control_plane = control_plane
        self.authenticator = authenticator
        self.max_request_bytes = max_request_bytes
        self.metrics = metrics or MetricsRegistry()
        self._readiness_checks = dict(readiness_checks or {})
        self.runtime_mode = runtime_mode
        self.allow_legacy_local = allow_legacy_local
        self.expected_issuer = expected_issuer
        self.expected_audience = expected_audience
        self.transport_mode = transport_mode
        self.tls_cert_file = tls_cert_file
        self.tls_key_file = tls_key_file
        self.tls_client_ca_file = tls_client_ca_file
        self.trusted_proxy_networks = parsed_proxy_networks
        self.request_timeout_seconds = request_timeout_seconds
        self.max_concurrent_requests = max_concurrent_requests
        self.graceful_shutdown_seconds = graceful_shutdown_seconds

    def handle_request(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes = b"",
    ) -> ServiceResponse:
        method = method.upper()
        route = urlsplit(path).path.rstrip("/") or "/"
        normalized_headers = {
            str(key).lower(): str(value) for key, value in headers.items()
        }
        request_id = _request_id(normalized_headers.get("x-request-id"))
        try:
            if len(body) > self.max_request_bytes:
                return self._error(
                    413,
                    "REQUEST_TOO_LARGE",
                    "request body exceeds the configured limit",
                    request_id,
                )
            if method == "GET" and route == "/livez":
                return ServiceResponse.json(
                    200,
                    {"status": "live"},
                    {"X-Request-ID": request_id},
                )
            if method == "GET" and route == "/readyz":
                ready, checks = self._readiness()
                return ServiceResponse.json(
                    200 if ready else 503,
                    {"status": "ready" if ready else "not-ready", "checks": checks},
                    {"X-Request-ID": request_id},
                )
            if method == "GET" and route == "/version":
                return ServiceResponse.json(
                    200,
                    {
                        "name": "elmos-proof-driven-harness-engine",
                        "version": SERVICE_VERSION,
                        "contractDigest": SERVICE_CONTRACT_DIGEST,
                        "runtimeMode": self.runtime_mode,
                    },
                    {"X-Request-ID": request_id},
                )
            if method == "GET" and route == "/metrics":
                principal = self._authenticate(normalized_headers)
                self._require_scope(principal, "proof-harness.observe")
                payload = self.metrics.render_prometheus().encode("utf-8")
                return ServiceResponse(
                    200,
                    payload,
                    {
                        "Content-Type": "text/plain; version=0.0.4; charset=utf-8",
                        "Content-Length": str(len(payload)),
                        "Cache-Control": "no-store",
                    },
                )
            if method == "GET" and route == "/v3/skills":
                principal = self._authenticate(normalized_headers)
                self._require_scope(principal, "proof-harness.read")
                description = self.runtime.describe()
                return ServiceResponse.json(
                    200,
                    {
                        "registryVersion": SERVICE_VERSION,
                        "skills": [
                            _public_skill(name) for name in sorted(SKILL_REGISTRY)
                        ],
                        "adapters": description["adapters"],
                    },
                )
            if method == "POST" and route == "/v3/invocations":
                principal = self._authenticate(normalized_headers)
                self._require_scope(principal, "proof-harness.invoke")
                return self._invoke_v3(
                    normalized_headers,
                    body,
                    principal,
                    request_id,
                )
            run_id = _match_run_route(route)
            if method == "GET" and run_id is not None:
                principal = self._authenticate(normalized_headers)
                self._require_scope(principal, "proof-harness.read")
                control_plane = self._require_control_plane()
                control_plane.reconcile_scope(principal)
                return ServiceResponse.json(
                    200,
                    control_plane.get_run(principal, run_id),
                    {"X-Request-ID": request_id},
                )
            cancel_run_id = _match_cancel_route(route)
            if method == "POST" and cancel_run_id is not None:
                principal = self._authenticate(normalized_headers)
                self._require_scope(principal, "proof-harness.cancel")
                return self._cancel(
                    cancel_run_id,
                    normalized_headers,
                    body,
                    principal,
                    request_id,
                )
            evidence_id = _match_resource_route(route, "/v3/evidence/")
            if method == "GET" and evidence_id is not None:
                principal = self._authenticate(normalized_headers)
                self._require_scope(principal, "proof-harness.evidence.read")
                control_plane = self._require_control_plane()
                return ServiceResponse.json(
                    200,
                    control_plane.get_evidence_metadata(principal, evidence_id),
                    {"X-Request-ID": request_id},
                )
            review_id = _match_resource_route(route, "/v3/completion-reviews/")
            if method == "GET" and review_id is not None:
                principal = self._authenticate(normalized_headers)
                self._require_scope(principal, "proof-harness.review.read")
                return self._error(
                    501,
                    "NOT_CONFIGURED",
                    "durable completion-review storage is not configured",
                    request_id,
                )
            if method == "POST" and route.startswith("/v1/skills/"):
                return self._invoke_legacy_local(
                    route,
                    normalized_headers,
                    body,
                    request_id,
                )
            if method not in {"GET", "POST"}:
                return self._error(
                    405,
                    "METHOD_NOT_ALLOWED",
                    "method is not supported",
                    request_id,
                    headers={"Allow": "GET, POST"},
                )
            return self._error(404, "NOT_FOUND", "route was not found", request_id)
        except AuthenticationError as exc:
            self._record_authority_denial("authentication", "authenticate")
            return self._error(
                401,
                "UNAUTHENTICATED",
                str(exc),
                request_id,
                headers={"WWW-Authenticate": "Bearer"},
            )
        except _ScopeError as exc:
            self._record_authority_denial("scope_missing", exc.capability)
            return self._error(
                403,
                "AUTHORITY_DENIED",
                str(exc),
                request_id,
            )
        except HarnessError as exc:
            if exc.code in {"STALE_EPOCH", "STALE_FENCE"}:
                self.metrics.increment(
                    "elmos_proof_harness_stale_fence_rejections_total",
                    labels={"operation": _operation_for_route(route)},
                )
            return self._error(
                exc.http_status,
                exc.code,
                exc.message,
                request_id,
                retryable=exc.retryable,
            )
        except Exception:
            return self._error(
                500,
                "INTERNAL_ERROR",
                "request failed without a trustworthy result",
                request_id,
            )

    def _invoke_v3(
        self,
        headers: Mapping[str, str],
        body: bytes,
        principal: AuthPrincipal,
        request_id: str,
    ) -> ServiceResponse:
        request = self._parse_json_request(headers, body)
        self._validate_invocation(request, headers, principal, len(body))
        control_plane = self._require_control_plane()
        skill = str(request["skill"])
        started = time.monotonic()
        outcome = control_plane.invoke(principal, request, input_bytes=len(body))
        elapsed = time.monotonic() - started
        status = str(outcome.result["status"])
        self.metrics.increment(
            "elmos_proof_harness_invocations_total",
            labels={
                "skill": skill,
                "status": status,
                "runtime_mode": self.runtime_mode,
            },
        )
        self.metrics.observe(
            "elmos_proof_harness_invocation_duration_seconds",
            elapsed,
            {"skill": skill, "phase": "admission"},
            buckets=_INVOCATION_DURATION_BUCKETS,
        )
        return ServiceResponse.json(
            200 if outcome.completed else 202,
            outcome.result,
            {
                "Idempotent-Replay": "true" if outcome.replay else "false",
                "X-Request-ID": str(request["requestId"]),
                "X-Run-ID": outcome.run.run_id,
            },
        )

    def _cancel(
        self,
        run_id: str,
        headers: Mapping[str, str],
        body: bytes,
        principal: AuthPrincipal,
        request_id: str,
    ) -> ServiceResponse:
        request = self._parse_json_request(headers, body)
        _require_exact_keys(
            request,
            required={"expectedVersion", "reason"},
            optional=set(),
            field="cancel request",
        )
        expected_version = request["expectedVersion"]
        if (
            not isinstance(expected_version, int)
            or isinstance(expected_version, bool)
            or expected_version < 1
        ):
            raise ValidationError("expectedVersion must be a positive integer")
        reason = request["reason"]
        if not isinstance(reason, str) or not 1 <= len(reason) <= 1024:
            raise ValidationError("reason must contain between 1 and 1024 characters")
        idempotency_key = _header_idempotency_key(headers)
        control_plane = self._require_control_plane()
        outcome = control_plane.cancel(
            principal,
            run_id,
            expected_version=expected_version,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        return ServiceResponse.json(
            200 if outcome.replay else 202,
            outcome.run,
            {
                "Idempotent-Replay": "true" if outcome.replay else "false",
                "X-Request-ID": request_id,
            },
        )

    def _invoke_legacy_local(
        self,
        route: str,
        headers: Mapping[str, str],
        body: bytes,
        request_id: str,
    ) -> ServiceResponse:
        if not self.allow_legacy_local or self.runtime_mode != "local-engineering":
            return self._error(
                404,
                "NOT_FOUND",
                "route was not found",
                request_id,
            )
        if headers.get("x-elmos-legacy-local", "").lower() != "true":
            return self._error(
                403,
                "LEGACY_LOCAL_ACK_REQUIRED",
                "X-ELMOS-Legacy-Local: true is required",
                request_id,
            )
        principal = self._authenticate(headers)
        self._require_scope(principal, "proof-harness.invoke")
        request = self._parse_json_request(headers, body)
        _require_exact_keys(
            request,
            required={"payload"},
            optional=set(),
            field="legacy request",
        )
        payload = request["payload"]
        if not isinstance(payload, Mapping):
            raise ValidationError("legacy payload must be an object")
        skill = route.removeprefix("/v1/skills/")
        if skill not in SKILL_REGISTRY:
            return self._error(
                404,
                "SKILL_NOT_FOUND",
                "requested Skill is not registered",
                request_id,
            )
        result = self.runtime.execute(
            skill,
            payload,
            context=principal.context(request_id),
        )
        return ServiceResponse.json(
            200,
            {
                "apiVersion": "elmos.ai/proof-harness/legacy-local/v1",
                "requestId": request_id,
                "result": result.to_dict(),
            },
            {"X-Request-ID": request_id},
        )

    def _parse_json_request(
        self,
        headers: Mapping[str, str],
        body: bytes,
    ) -> dict[str, Any]:
        content_type = headers.get("content-type", "")
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            raise _HttpValidationError(
                "Content-Type must be application/json",
                code="UNSUPPORTED_MEDIA_TYPE",
                http_status=415,
            )
        try:
            value = json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_strict_json_object,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise _HttpValidationError(
                "request body is not valid JSON",
                code="INVALID_JSON",
                http_status=400,
            ) from exc
        if not isinstance(value, dict):
            raise _HttpValidationError(
                "request body must be an object",
                code="INVALID_REQUEST",
                http_status=400,
            )
        return value

    def _validate_invocation(
        self,
        request: Mapping[str, Any],
        headers: Mapping[str, str],
        principal: AuthPrincipal,
        input_bytes: int,
    ) -> None:
        _require_exact_keys(
            request,
            required={
                "apiVersion",
                "requestId",
                "skill",
                "identity",
                "revisionSet",
                "authority",
                "idempotencyKey",
                "input",
            },
            optional={"deadline", "limits"},
            field="invocation",
        )
        if request["apiVersion"] != "elmos.ai/proof-harness/v3":
            raise ValidationError("apiVersion must be elmos.ai/proof-harness/v3")
        body_request_id = request["requestId"]
        if not isinstance(body_request_id, str) or not 1 <= len(body_request_id) <= 160:
            raise ValidationError("requestId length is outside the contract")
        skill = request["skill"]
        if not isinstance(skill, str) or skill not in SKILL_REGISTRY:
            raise ValidationError("skill is not in the exact v3 registry", code="SKILL_NOT_FOUND")
        identity = _require_object(request["identity"], "identity")
        _require_exact_keys(
            identity,
            required={
                "tenantId",
                "projectId",
                "actorId",
                "authenticationContextDigest",
            },
            optional=set(),
            field="identity",
        )
        expected_identity = {
            "tenantId": principal.tenant_id,
            "projectId": principal.project_id,
            "actorId": principal.actor_id,
            "authenticationContextDigest": principal.authentication_context_digest,
        }
        if identity != expected_identity:
            raise ValidationError(
                "identity must exactly match the authenticated principal",
                code="IDENTITY_MISMATCH",
            )
        revision_set = _require_object(request["revisionSet"], "revisionSet")
        _require_exact_keys(
            revision_set,
            required={
                "revisionSetId",
                "source",
                "baseline",
                "requirements",
                "policy",
                "toolchain",
                "environment",
                "domainPack",
                "workflow",
                "modelRoute",
            },
            optional=set(),
            field="revisionSet",
        )
        revision_set_id = revision_set["revisionSetId"]
        if (
            not isinstance(revision_set_id, str)
            or not 1 <= len(revision_set_id) <= 160
        ):
            raise ValidationError("revisionSetId length is outside the contract")
        for name in set(revision_set) - {"revisionSetId"}:
            if not _is_digest(revision_set[name]):
                raise ValidationError(f"revisionSet.{name} must be a SHA-256 digest")
        if revision_set["environment"] != principal.environment_revision:
            raise ValidationError(
                "revisionSet.environment is not bound to the server environment",
                code="ENVIRONMENT_MISMATCH",
            )
        authority = _require_object(request["authority"], "authority")
        _require_exact_keys(
            authority,
            required={
                "authorityId",
                "revision",
                "environmentId",
                "executionEpoch",
                "fencingGeneration",
                "expiresAt",
            },
            optional=set(),
            field="authority",
        )
        if authority["authorityId"] != principal.authority_id:
            raise ValidationError(
                "authorityId is not bound to the authenticated principal",
                code="AUTHORITY_MISMATCH",
            )
        if authority["revision"] != principal.authority_revision:
            raise ValidationError(
                "authority revision is not bound to the server",
                code="AUTHORITY_MISMATCH",
            )
        if authority["environmentId"] != principal.environment_id:
            raise ValidationError(
                "environmentId is not bound to the server",
                code="ENVIRONMENT_MISMATCH",
            )
        epoch = authority["executionEpoch"]
        fence = authority["fencingGeneration"]
        if not _positive_int(epoch) or not _positive_int(fence):
            raise ValidationError("executionEpoch and fencingGeneration must be positive")
        if epoch != principal.execution_epoch:
            raise ValidationError(
                "execution epoch is stale or not server-bound",
                code="STALE_EPOCH",
            )
        if fence != principal.fencing_generation:
            raise ValidationError(
                "fencing generation is stale or not server-bound",
                code="STALE_FENCE",
            )
        authority_expiry = _parse_rfc3339(authority["expiresAt"], "authority.expiresAt")
        principal_expiry = principal.expires_at.astimezone(UTC)
        if authority_expiry != principal_expiry:
            raise ValidationError(
                "authority expiry is not bound to the authenticated principal",
                code="AUTHORITY_MISMATCH",
            )
        now = datetime.now(UTC)
        if now >= principal_expiry:
            raise ValidationError("execution authority has expired", code="AUTHORITY_EXPIRED")
        header_key = _header_idempotency_key(headers)
        body_key = request["idempotencyKey"]
        if not isinstance(body_key, str) or not _valid_idempotency_key(body_key):
            raise ValidationError("idempotencyKey is outside the contract")
        if not hmac.compare_digest(header_key, body_key):
            raise ValidationError(
                "header and body idempotency keys must be identical",
                code="IDEMPOTENCY_MISMATCH",
            )
        payload = request["input"]
        if not isinstance(payload, Mapping):
            raise ValidationError("input must be an object")
        deadline_value = request.get("deadline")
        if deadline_value is not None:
            deadline = _parse_rfc3339(deadline_value, "deadline")
            if deadline <= now:
                raise ValidationError("deadline has elapsed", code="DEADLINE_EXCEEDED")
            if deadline > principal_expiry:
                raise ValidationError(
                    "deadline exceeds execution-authority expiry",
                    code="DEADLINE_EXCEEDS_AUTHORITY",
                )
        limits_value = request.get("limits")
        if limits_value is not None:
            self._validate_limits(limits_value, input_bytes)

    @staticmethod
    def _validate_limits(value: Any, input_bytes: int) -> None:
        limits = _require_object(value, "limits")
        _require_exact_keys(
            limits,
            required=set(),
            optional={
                "wallClockSeconds",
                "maxInputBytes",
                "maxOutputBytes",
                "maxCostMicrounits",
            },
            field="limits",
        )
        wall_clock = limits.get("wallClockSeconds")
        if wall_clock is not None and (
            isinstance(wall_clock, bool)
            or not isinstance(wall_clock, (int, float))
            or not 0 < wall_clock <= 86_400
        ):
            raise ValidationError("limits.wallClockSeconds is outside the contract")
        for name in ("maxInputBytes", "maxOutputBytes"):
            candidate = limits.get(name)
            if candidate is not None and (
                not _positive_int(candidate) or candidate > 1_073_741_824
            ):
                raise ValidationError(f"limits.{name} is outside the contract")
        cost = limits.get("maxCostMicrounits")
        if cost is not None and (
            not isinstance(cost, int) or isinstance(cost, bool) or cost < 0
        ):
            raise ValidationError("limits.maxCostMicrounits is outside the contract")
        maximum_input = limits.get("maxInputBytes")
        if maximum_input is not None and input_bytes > maximum_input:
            raise ValidationError(
                "request exceeds limits.maxInputBytes",
                code="INPUT_LIMIT_EXCEEDED",
            )

    def _authenticate(self, headers: Mapping[str, str]) -> AuthPrincipal:
        try:
            matched = self.authenticator.authenticate(headers)
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError(
                "trusted authentication gateway did not yield a principal"
            ) from exc
        if not isinstance(matched, AuthPrincipal):
            raise AuthenticationError(
                "trusted authentication gateway returned an invalid principal"
            )
        if self.expected_issuer is not None and not hmac.compare_digest(
            matched.issuer, self.expected_issuer
        ):
            raise AuthenticationError("Bearer principal issuer is invalid")
        if self.expected_audience is not None and not hmac.compare_digest(
            matched.audience, self.expected_audience
        ):
            raise AuthenticationError("Bearer principal audience is invalid")
        if datetime.now(UTC) >= matched.expires_at.astimezone(UTC):
            raise AuthenticationError("Bearer principal authority has expired")
        return matched

    @staticmethod
    def _require_scope(principal: AuthPrincipal, capability: str) -> None:
        if capability not in principal.authority:
            raise _ScopeError(capability)

    def _require_control_plane(self) -> DurableControlPlane:
        if self.control_plane is None:
            raise _HttpValidationError(
                "durable control plane is not configured",
                code="NOT_CONFIGURED",
                http_status=503,
            )
        ready, reason = self.control_plane.ready()
        if not ready:
            raise _HttpValidationError(reason, code="NOT_READY", http_status=503)
        if self.runtime_mode == "production":
            storage = self.control_plane.store.readiness()
            if not storage.ready or storage.backend != "postgresql":
                raise _HttpValidationError(
                    "production requires a ready PostgreSQL durable store",
                    code="NOT_READY",
                    http_status=503,
                )
            assurance_ready, assurance_reason = (
                self.control_plane.runtime_assurance_ready(production=True)
            )
            if not assurance_ready:
                raise _HttpValidationError(
                    assurance_reason,
                    code="NOT_READY",
                    http_status=503,
                )
        return self.control_plane

    def _readiness(self) -> tuple[bool, dict[str, str]]:
        checks: dict[str, str] = {}
        try:
            runtime_ready, _ = self.runtime.readiness()
        except Exception:
            runtime_ready = False
        checks["runtimeRegistry"] = "ready" if runtime_ready else "not-ready"
        if self.control_plane is None:
            checks["durableStore"] = "not-configured"
            checks["runtimeAssurance"] = (
                "not-ready" if self.runtime_mode == "production" else "ready"
            )
        else:
            ready, _ = self.control_plane.ready()
            if ready and self.runtime_mode == "production":
                try:
                    storage = self.control_plane.store.readiness()
                    ready = storage.ready and storage.backend == "postgresql"
                except Exception:
                    ready = False
            checks["durableStore"] = "ready" if ready else "not-ready"
            try:
                assurance_ready, _ = self.control_plane.runtime_assurance_ready(
                    production=self.runtime_mode == "production"
                )
            except Exception:
                assurance_ready = False
            checks["runtimeAssurance"] = (
                "ready" if assurance_ready else "not-ready"
            )
        try:
            auth_value = self.authenticator.readiness()
            auth_ready = (
                bool(auth_value[0]) if isinstance(auth_value, tuple) else bool(auth_value)
            )
        except Exception:
            auth_ready = False
        if self.runtime_mode == "production":
            auth_ready = (
                auth_ready
                and bool(getattr(self.authenticator, "trusted_for_production", False))
                and bool(self.expected_issuer)
                and bool(self.expected_audience)
            )
        checks["authentication"] = "ready" if auth_ready else "not-ready"
        transport_ready = self.transport_mode == "local"
        if self.transport_mode == "tls":
            transport_ready = bool(self.tls_cert_file and self.tls_key_file)
            if transport_ready:
                try:
                    _build_tls_context(self)
                except Exception:
                    transport_ready = False
        elif self.transport_mode == "trusted-proxy":
            transport_ready = bool(self.trusted_proxy_networks)
        if self.runtime_mode == "production" and self.transport_mode == "local":
            transport_ready = False
        checks["transportSecurity"] = "ready" if transport_ready else "not-ready"
        config_ready = auth_ready and transport_ready
        if self.runtime_mode == "production":
            storage_ready = False
            assurance_ready = False
            if self.control_plane is not None:
                try:
                    storage = self.control_plane.store.readiness()
                    storage_ready = storage.ready and storage.backend == "postgresql"
                except Exception:
                    storage_ready = False
                try:
                    assurance_ready, _ = (
                        self.control_plane.runtime_assurance_ready(production=True)
                    )
                except Exception:
                    assurance_ready = False
            config_ready = config_ready and storage_ready and assurance_ready
        checks["requiredConfig"] = "ready" if config_ready else "not-ready"
        for name, check in sorted(self._readiness_checks.items()):
            try:
                value = check()
                ready = bool(value[0]) if isinstance(value, tuple) else bool(value)
            except Exception:
                ready = False
            checks[name] = "ready" if ready else "not-ready"
        return all(value == "ready" for value in checks.values()), checks

    def _record_authority_denial(self, reason: str, capability: str) -> None:
        self.metrics.increment(
            "elmos_proof_harness_authority_denials_total",
            labels={"reason": reason, "capability": capability},
        )

    @staticmethod
    def _error(
        status: int,
        code: str,
        detail: str,
        request_id: str,
        *,
        retryable: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> ServiceResponse:
        return ServiceResponse.json(
            status,
            {
                "type": f"/problems/{code.lower().replace('_', '-')}",
                "title": code.replace("_", " ").title(),
                "status": status,
                "code": code,
                "detail": detail[:4096],
                "requestId": request_id,
                "retryable": retryable,
            },
            headers,
            media_type="application/problem+json",
        )


class _ScopeError(PermissionError):
    def __init__(self, capability: str) -> None:
        self.capability = capability
        super().__init__(f"{capability} scope is required")


class _HttpValidationError(HarnessError):
    def __init__(self, message: str, *, code: str, http_status: int) -> None:
        super().__init__(code, message, {}, False, http_status)


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    normalized: set[str] = set()
    for key, value in pairs:
        if not isinstance(key, str):
            raise ValueError("JSON object key must be a string")
        canonical_key = unicodedata.normalize("NFC", key)
        if key != canonical_key:
            raise ValueError("JSON object key must use NFC normalization")
        if key in result or canonical_key in normalized:
            raise ValueError("JSON object contains a duplicate or normalized-colliding key")
        result[key] = value
        normalized.add(canonical_key)
    return result


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _decode_base64url(value: str, field: str) -> bytes:
    if not value or "=" in value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise AuthenticationError(f"JWT {field} encoding is invalid")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (binascii.Error, ValueError) as exc:
        raise AuthenticationError(f"JWT {field} encoding is invalid") from exc
    if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
        raise AuthenticationError(f"JWT {field} encoding is non-canonical")
    return decoded


def _decode_jwt_object(value: str, field: str) -> Mapping[str, Any]:
    try:
        decoded = _decode_base64url(value, field).decode("utf-8")
        document = json.loads(
            decoded,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise AuthenticationError(f"JWT {field} is invalid JSON") from exc
    if not isinstance(document, dict):
        raise AuthenticationError(f"JWT {field} must be an object")
    return document


def _jwt_numeric_date(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AuthenticationError(f"JWT {field} must be an integer NumericDate")
    return value


def _parse_rsa_jwk(value: Any, algorithm: str) -> _RsaVerificationKey:
    if not isinstance(value, Mapping):
        raise AuthenticationError("JWKS entry must be an object")
    allowed = {"kty", "kid", "use", "key_ops", "alg", "n", "e"}
    if set(value) - allowed or not {"kty", "kid", "n", "e"}.issubset(value):
        raise AuthenticationError("JWKS entry fields are invalid")
    if value["kty"] != "RSA" or value.get("alg", algorithm) != algorithm:
        raise AuthenticationError("JWKS entry algorithm is not allowed")
    if value.get("use", "sig") != "sig":
        raise AuthenticationError("JWKS entry is not a signature key")
    key_ops = value.get("key_ops", ["verify"])
    if not isinstance(key_ops, list) or set(key_ops) != {"verify"}:
        raise AuthenticationError("JWKS entry key_ops must be exactly verify")
    kid = value["kid"]
    if not isinstance(kid, str) or not _IDENTIFIER.fullmatch(kid):
        raise AuthenticationError("JWKS kid is invalid")
    if not isinstance(value["n"], str) or not isinstance(value["e"], str):
        raise AuthenticationError("JWKS RSA parameters are invalid")
    modulus_bytes = _decode_base64url(value["n"], "JWK modulus")
    exponent_bytes = _decode_base64url(value["e"], "JWK exponent")
    modulus = int.from_bytes(modulus_bytes, "big")
    exponent = int.from_bytes(exponent_bytes, "big")
    if not 2048 <= modulus.bit_length() <= 8192:
        raise AuthenticationError("JWKS RSA modulus size is outside policy")
    if not 3 <= exponent <= 0xFFFFFFFF or exponent % 2 == 0:
        raise AuthenticationError("JWKS RSA exponent is outside policy")
    return _RsaVerificationKey(kid, modulus, exponent, len(modulus_bytes))


def _verify_rs256(
    key: _RsaVerificationKey,
    signed: bytes,
    signature: bytes,
) -> bool:
    if len(signature) != key.byte_length:
        return False
    signature_number = int.from_bytes(signature, "big")
    if signature_number >= key.modulus:
        return False
    decoded = pow(signature_number, key.exponent, key.modulus).to_bytes(
        key.byte_length, "big"
    )
    digest_info = _RSA_SHA256_DIGEST_INFO + hashlib.sha256(signed).digest()
    padding_length = key.byte_length - len(digest_info) - 3
    if padding_length < 8:
        return False
    expected = b"\x00\x01" + b"\xff" * padding_length + b"\x00" + digest_info
    return hmac.compare_digest(decoded, expected)


def _read_trusted_jwks(path: Path) -> bytes:
    """Read one absolute file without following any path component symlink."""

    flags_directory = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags_nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open("/", flags_directory)
    try:
        parts = path.parts[1:]
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise AuthenticationError("trusted JWKS path is invalid")
        for component in parts[:-1]:
            next_fd = os.open(
                component,
                flags_directory | flags_nofollow,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(
            parts[-1], os.O_RDONLY | flags_nofollow, dir_fd=directory_fd
        )
        try:
            before = os.fstat(file_fd)
            if not stat.S_ISREG(before.st_mode):
                raise AuthenticationError("trusted JWKS is not a regular file")
            if before.st_mode & 0o022:
                raise AuthenticationError("trusted JWKS must not be group/world writable")
            if before.st_uid not in {0, os.geteuid()}:
                raise AuthenticationError("trusted JWKS owner is not approved")
            if not 1 <= before.st_size <= 1024 * 1024:
                raise AuthenticationError("trusted JWKS size is outside policy")
            chunks: list[bytes] = []
            remaining = before.st_size
            while remaining:
                chunk = os.read(file_fd, min(remaining, 64 * 1024))
                if not chunk:
                    raise AuthenticationError("trusted JWKS changed while reading")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(file_fd, 1):
                raise AuthenticationError("trusted JWKS grew while reading")
            after = os.fstat(file_fd)
            before_identity = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            after_identity = (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            if before_identity != after_identity:
                raise AuthenticationError("trusted JWKS changed while reading")
            return b"".join(chunks)
        finally:
            os.close(file_fd)
    except OSError as exc:
        raise AuthenticationError("trusted JWKS path is unavailable") from exc
    finally:
        os.close(directory_fd)


def _public_skill(name: str) -> dict[str, str]:
    descriptor = SKILL_REGISTRY[name]
    implementation_state = "LOCAL" if descriptor.kind == "kernel" else "PARTIAL"
    if descriptor.name in {
        "elmos-proof-verification-kernel",
        "elmos-harness-runtime-kernel",
        "elmos-certification-kernel",
    }:
        implementation_state = "PARTIAL"
    return {
        "id": descriptor.skill_id,
        "name": descriptor.name,
        "owner": descriptor.owner,
        "kind": descriptor.kind,
        "implementationState": implementation_state,
        "externalEvidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def _require_object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{field} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ValidationError(f"{field} keys must be strings")
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str],
    field: str,
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required - optional)
    if missing or unexpected:
        detail: list[str] = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if unexpected:
            detail.append("unexpected=" + ",".join(unexpected))
        raise ValidationError(f"{field} has invalid fields ({'; '.join(detail)})")


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _valid_idempotency_key(value: str) -> bool:
    return (
        16 <= len(value) <= 256
        and all(char >= " " and char not in {"\x7f", "\r", "\n"} for char in value)
    )


def _header_idempotency_key(headers: Mapping[str, str]) -> str:
    value = headers.get("idempotency-key")
    if value is None or not _valid_idempotency_key(value):
        raise ValidationError(
            "a valid Idempotency-Key header is required",
            code="IDEMPOTENCY_KEY_REQUIRED",
        )
    return value


def _parse_rfc3339(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be an RFC 3339 date-time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field} must be an RFC 3339 date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _request_id(value: str | None) -> str:
    if value and _IDENTIFIER.fullmatch(value):
        return value
    return f"req-{uuid.uuid4().hex}"


def _match_run_route(route: str) -> str | None:
    prefix = "/v3/runs/"
    if not route.startswith(prefix) or route.endswith("/cancel"):
        return None
    return _validated_resource_id(route.removeprefix(prefix))


def _match_cancel_route(route: str) -> str | None:
    prefix = "/v3/runs/"
    suffix = "/cancel"
    if not route.startswith(prefix) or not route.endswith(suffix):
        return None
    return _validated_resource_id(route[len(prefix) : -len(suffix)])


def _match_resource_route(route: str, prefix: str) -> str | None:
    if not route.startswith(prefix):
        return None
    return _validated_resource_id(route.removeprefix(prefix))


def _validated_resource_id(value: str) -> str | None:
    if not value or "/" in value or len(value) > 160:
        return None
    return value


def _operation_for_route(route: str) -> str:
    if route.endswith("/cancel"):
        return "cancel"
    if route == "/v3/invocations":
        return "invoke"
    return "read"


def make_http_handler(service: HarnessService) -> Type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "ELMOSProofHarness/3.0"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            self._dispatch(b"")

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            raw_length = self.headers.get("Content-Length")
            request_id = f"req-{uuid.uuid4().hex}"
            if raw_length is None:
                self._send(
                    service._error(
                        411,
                        "LENGTH_REQUIRED",
                        "Content-Length is required",
                        request_id,
                    )
                )
                return
            try:
                length = int(raw_length)
            except ValueError:
                self._send(
                    service._error(
                        400,
                        "INVALID_CONTENT_LENGTH",
                        "Content-Length is invalid",
                        request_id,
                    )
                )
                return
            if length < 0 or length > service.max_request_bytes:
                self._send(
                    service._error(
                        413,
                        "REQUEST_TOO_LARGE",
                        "request body exceeds the configured limit",
                        request_id,
                    )
                )
                return
            try:
                body = self.rfile.read(length)
            except (TimeoutError, socket.timeout):
                self._send(
                    service._error(
                        408,
                        "REQUEST_TIMEOUT",
                        "request body was not received within the configured timeout",
                        request_id,
                    )
                )
                return
            if len(body) != length:
                self._send(
                    service._error(
                        400,
                        "INCOMPLETE_REQUEST_BODY",
                        "request body ended before Content-Length bytes arrived",
                        request_id,
                    )
                )
                return
            self._dispatch(body)

        def _dispatch(self, body: bytes) -> None:
            if service.transport_mode == "trusted-proxy":
                try:
                    peer = ipaddress.ip_address(self.client_address[0])
                except ValueError:
                    peer = None
                if peer is None or not any(
                    peer in network for network in service.trusted_proxy_networks
                ):
                    self._send(
                        service._error(
                            403,
                            "UNTRUSTED_PROXY",
                            "connection did not originate from an approved proxy CIDR",
                            f"req-{uuid.uuid4().hex}",
                        )
                    )
                    return
            lowered = {str(key).lower() for key in self.headers}
            if lowered.intersection(
                {
                    "x-forwarded-user",
                    "x-forwarded-tenant",
                    "x-forwarded-project",
                    "x-forwarded-actor",
                }
            ):
                self._send(
                    service._error(
                        400,
                        "FORWARDED_IDENTITY_FORBIDDEN",
                        "forwarded identity headers cannot grant proof-harness authority",
                        f"req-{uuid.uuid4().hex}",
                    )
                )
                return
            response = service.handle_request(
                self.command,
                self.path,
                dict(self.headers.items()),
                body,
            )
            self._send(response)

        def _send(self, response: ServiceResponse) -> None:
            self.send_response(response.status)
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(response.body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


class _BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        server_address: tuple[str, int],
        handler: Type[BaseHTTPRequestHandler],
        service: HarnessService,
    ) -> None:
        self._service = service
        self._slots = threading.BoundedSemaphore(service.max_concurrent_requests)
        self._active = 0
        self._active_condition = threading.Condition()
        self._draining = False
        super().__init__(server_address, handler)

    def get_request(self) -> tuple[socket.socket, Any]:
        request, address = super().get_request()
        request.settimeout(self._service.request_timeout_seconds)
        return request, address

    def process_request(self, request: socket.socket, client_address: Any) -> None:
        if self._draining or not self._slots.acquire(blocking=False):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\nContent-Length: 0\r\n\r\n"
                )
            except OSError:
                pass
            self.shutdown_request(request)
            return
        with self._active_condition:
            self._active += 1
        try:
            super().process_request(request, client_address)
        except Exception:
            with self._active_condition:
                self._active -= 1
                self._active_condition.notify_all()
            self._slots.release()
            raise

    def process_request_thread(
        self, request: socket.socket, client_address: Any
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self._active_condition:
                self._active -= 1
                self._active_condition.notify_all()
            self._slots.release()

    def begin_drain(self) -> None:
        self._draining = True
        threading.Thread(target=self.shutdown, daemon=True).start()

    def wait_for_drain(self) -> None:
        deadline = time.monotonic() + self._service.graceful_shutdown_seconds
        with self._active_condition:
            while self._active and time.monotonic() < deadline:
                self._active_condition.wait(deadline - time.monotonic())


def _build_tls_context(service: HarnessService) -> ssl.SSLContext:
    if not service.tls_cert_file or not service.tls_key_file:
        raise ValueError("TLS certificate and key are required")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.options |= ssl.OP_NO_COMPRESSION
    context.load_cert_chain(service.tls_cert_file, service.tls_key_file)
    if service.tls_client_ca_file:
        context.load_verify_locations(cafile=service.tls_client_ca_file)
        context.verify_mode = ssl.CERT_REQUIRED
    return context


def serve(service: HarnessService, host: str, port: int) -> None:
    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    server = _BoundedThreadingHTTPServer(
        (host, port), make_http_handler(service), service
    )
    if service.transport_mode == "tls":
        server.socket = _build_tls_context(service).wrap_socket(
            server.socket, server_side=True
        )
    previous_handlers: dict[int, Any] = {}
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, lambda _signum, _frame: server.begin_drain())
    try:
        server.serve_forever()
    finally:
        server.begin_drain()
        server.wait_for_drain()
        server.server_close()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


__all__ = [
    "AuthenticationError",
    "Authenticator",
    "AuthPrincipal",
    "FileJwksAuthenticator",
    "HarnessService",
    "SERVICE_CONTRACT_DIGEST",
    "SERVICE_VERSION",
    "ServiceResponse",
    "StaticTokenAuthenticator",
    "make_http_handler",
    "serve",
]
