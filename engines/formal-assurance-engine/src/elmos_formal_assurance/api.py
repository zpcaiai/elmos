from __future__ import annotations

import json
from io import BytesIO
from typing import Any, Callable

from .contracts import TrustedIdentity
from .runtime import (
    FormalAssuranceRuntime,
    RuntimeAuthorizationError,
    RuntimeRequestError,
)
from .store import StoreError


def _response(
    start_response: Callable[..., Any],
    status: str,
    payload: Any,
    content_type: str = "application/json",
) -> list[bytes]:
    body = (
        payload
        if isinstance(payload, bytes)
        else json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    start_response(
        status, [("Content-Type", content_type), ("Content-Length", str(len(body)))]
    )
    return [body]


class FormalAssuranceApi:
    """Small WSGI adapter; trusted identity must come from the transport."""

    def __init__(self, runtime: FormalAssuranceRuntime | None = None) -> None:
        self.runtime = runtime or FormalAssuranceRuntime()

    def __call__(
        self, environ: dict[str, Any], start_response: Callable[..., Any]
    ) -> list[bytes]:
        path = str(environ.get("PATH_INFO", "/"))
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        if method == "GET" and path == "/livez":
            return _response(start_response, "200 OK", {"status": "live"})
        if method == "GET" and path == "/readyz":
            return _response(
                start_response,
                "200 OK",
                {
                    "status": "ready",
                    "externalEvidence": "NOT_REQUIRED_FOR_LOCAL_READINESS",
                },
            )
        if method == "GET" and path == "/version":
            return _response(
                start_response,
                "200 OK",
                {
                    "name": "elmos-formal-assurance-engine",
                    "version": "0.1.0",
                    "skills": self.runtime.registry.count,
                },
            )
        if method == "GET" and path == "/metrics":
            return _response(
                start_response,
                "200 OK",
                b"elmos_formal_assurance_runtime_ready 1\n",
                "text/plain; version=0.0.4",
            )
        if method == "GET" and path == "/v1/skills":
            return _response(
                start_response,
                "200 OK",
                {
                    "skills": self.runtime.list_skills(),
                    "certification": "NOT_CERTIFIED",
                },
            )
        try:
            if (
                method == "POST"
                and path.startswith("/v1/skills/")
                and path.endswith("/execute")
            ):
                skill_id = path[len("/v1/skills/") : -len("/execute")].strip("/")
                identity = self._identity(environ)
                payload = self._payload(environ)
                result = self.runtime.dispatch(skill_id, payload, identity)
                return _response(start_response, "200 OK", result)
            if method == "POST" and path == "/v1/runs":
                identity = self._identity(environ)
                result = self.runtime.submit_run(self._payload(environ), identity)
                return _response(start_response, "201 Created", result)
        except KeyError as exc:
            return _response(start_response, "404 Not Found", {"error": str(exc)})
        except RuntimeAuthorizationError as exc:
            return _response(start_response, "403 Forbidden", {"error": str(exc)})
        except (
            RuntimeRequestError,
            StoreError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            return _response(start_response, "400 Bad Request", {"error": str(exc)})
        return _response(start_response, "404 Not Found", {"error": "not found"})

    def _payload(self, environ: dict[str, Any]) -> dict[str, Any]:
        raw_length = environ.get("CONTENT_LENGTH")
        if raw_length is None or str(raw_length).strip() == "":
            raise RuntimeRequestError("content length is required")
        length = int(raw_length)
        if length < 0 or length > self.runtime.config.max_request_bytes:
            raise RuntimeRequestError("request body exceeds local bound")
        body = environ.get("wsgi.input", BytesIO()).read(length)
        value = json.loads(body or b"{}")
        if not isinstance(value, dict):
            raise RuntimeRequestError("request body must be an object")
        return value

    @staticmethod
    def _identity(environ: dict[str, Any]) -> TrustedIdentity:
        identity = environ.get("elmos.trusted_identity")
        if isinstance(identity, TrustedIdentity):
            return identity
        if environ.get("elmos.trusted_transport") is not True:
            raise RuntimeAuthorizationError("trusted transport identity is required")
        tenant = environ.get("HTTP_X_ELMOS_TENANT_ID")
        actor = environ.get("HTTP_X_ELMOS_ACTOR_ID")
        if not tenant or not actor:
            raise RuntimeAuthorizationError(
                "tenant and actor identity headers are required"
            )
        return TrustedIdentity(
            tenant_id=tenant,
            actor_id=actor,
            project_id=environ.get("HTTP_X_ELMOS_PROJECT_ID"),
        )


application = FormalAssuranceApi()


def make_environ(
    path: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    identity: TrustedIdentity | None = None,
) -> dict[str, Any]:
    data = json.dumps(payload or {}).encode("utf-8")
    result: dict[str, Any] = {
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        "CONTENT_LENGTH": str(len(data)),
        "wsgi.input": BytesIO(data),
        "elmos.trusted_transport": True,
    }
    if identity is not None:
        result["elmos.trusted_identity"] = identity
    return result
