from __future__ import annotations

import json
from io import BytesIO
from typing import Any, Callable
from urllib.parse import parse_qs

from .canonical import digest_value
from .contracts import TrustedIdentity
from .execution import ExecutionAuthorizationError, ExecutionContractError
from .observability import ObservabilityError
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
                    "version": "1.0.0",
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
            if method == "POST" and path in {"/v1/runs", "/v1/proof-runs"}:
                identity = self._identity(environ)
                payload = self._payload(environ)
                if path == "/v1/proof-runs":
                    trusted_scope = self._scope_from_headers(environ, identity)
                    if "scope" in payload and payload["scope"] != trusted_scope:
                        raise RuntimeAuthorizationError(
                            "proof run body scope does not match trusted resource scope"
                        )
                    payload["scope"] = trusted_scope
                elif "scope" not in payload:
                    payload["scope"] = self._scope_from_headers(environ, identity)
                payload.setdefault("runId", payload.get("id"))
                tenant = payload.get("tenant")
                if isinstance(tenant, dict):
                    if tenant.get("tenantId") != identity.tenant_id:
                        raise RuntimeAuthorizationError(
                            "proof run tenant does not match trusted identity"
                        )
                    if tenant.get("accountId") != payload["scope"].get("accountId"):
                        raise RuntimeAuthorizationError(
                            "proof run account does not match trusted resource scope"
                        )
                if payload.get("state", "QUEUED") != "QUEUED":
                    raise RuntimeRequestError("new proof runs must begin in QUEUED state")
                if int(payload.get("fencingToken", 1)) != 1:
                    raise RuntimeRequestError("new proof runs must begin with fencingToken 1")
                result = self.runtime.submit_run(payload, identity)
                return _response(start_response, "202 Accepted", result)
            if method == "GET" and path.startswith("/v1/proof-runs/"):
                run_id = path[len("/v1/proof-runs/") :].strip("/")
                if not run_id or "/" in run_id:
                    return _response(start_response, "404 Not Found", {"error": "not found"})
                identity = self._identity(environ)
                result = self.runtime.get_run(
                    {"scope": self._scope_from_headers(environ, identity), "runId": run_id},
                    identity,
                )
                return _response(start_response, "200 OK", result)
            if method == "GET" and path.startswith("/v1/executions/"):
                execution_id = path[len("/v1/executions/") :].strip("/")
                if not execution_id or "/" in execution_id:
                    return _response(start_response, "404 Not Found", {"error": "not found"})
                identity = self._identity(environ)
                scope = self.runtime._scope(
                    self._scope_from_headers(environ, identity), identity
                )
                result = self.runtime.store.get_execution_receipt(scope, execution_id)
                return _response(start_response, "200 OK", result)
            if method == "POST" and path.startswith("/v1/proof-runs/") and path.endswith("/execute-local"):
                run_id = path[
                    len("/v1/proof-runs/") : -len("/execute-local")
                ].strip("/")
                identity = self._identity(environ)
                payload = self._payload(environ)
                payload["runId"] = run_id
                payload["scope"] = self._scope_from_headers(environ, identity)
                result = self.runtime.execute_local_run(payload, identity)
                return _response(start_response, "200 OK", result)
            if method == "POST" and path.startswith("/v1/proof-runs/") and path.endswith("/actions"):
                run_id = path[len("/v1/proof-runs/") : -len("/actions")].strip("/")
                identity = self._identity(environ)
                payload = self._payload(environ)
                payload["runId"] = run_id
                payload["scope"] = self._scope_from_headers(environ, identity)
                result = self.runtime.control_run(payload, identity)
                return _response(start_response, "202 Accepted", result)
            if method == "POST" and path == "/v1/formal/specs":
                identity = self._identity(environ)
                document = self._payload(environ)
                result = self.runtime.dispatch(
                    "elmos-formal-spec-ir",
                    self._dispatch_envelope(
                        environ,
                        identity,
                        subject_id=document.get("id"),
                        payload={"formalSpec": document},
                    ),
                    identity,
                )
                return _response(start_response, "201 Created", result)
            if method == "POST" and path == "/v1/proof-plans":
                identity = self._identity(environ)
                document = self._payload(environ)
                result = self.runtime.dispatch(
                    "elmos-proof-obligation-planner",
                    self._dispatch_envelope(
                        environ,
                        identity,
                        subject_id=document.get("id"),
                        payload={"proofPlan": document},
                    ),
                    identity,
                )
                return _response(start_response, "202 Accepted", result)
            if method == "POST" and path == "/v1/proof-artifacts":
                identity = self._identity(environ)
                document = self._payload(environ)
                result = self.runtime.dispatch(
                    "elmos-proof-artifact-store",
                    self._dispatch_envelope(
                        environ,
                        identity,
                        subject_id=document.get("id"),
                        payload={"proofArtifact": document},
                    ),
                    identity,
                )
                return _response(start_response, "201 Created", result)
            if method == "POST" and path == "/v1/proof-counterexamples":
                identity = self._identity(environ)
                document = self._payload(environ)
                result = self.runtime.dispatch(
                    "elmos-counterexample-to-test",
                    self._dispatch_envelope(
                        environ,
                        identity,
                        subject_id=document.get("id"),
                        payload={"counterexample": document},
                    ),
                    identity,
                )
                return _response(start_response, "201 Created", result)
            if method == "POST" and path == "/v1/evidence-bundles":
                identity = self._identity(environ)
                request = self._payload(environ)
                subject_id = str(request.get("subjectId", ""))
                scope = self.runtime._scope(
                    self._scope_from_headers(environ, identity), identity
                )
                bundle_id = "bundle-" + self.runtime.store.put_document(
                    scope,
                    "evidence_bundle_request",
                    subject_id,
                    request,
                    version="request-"
                    + digest_value(request).removeprefix("sha256:")[:24],
                )["contentDigest"].removeprefix("sha256:")[:24]
                return _response(
                    start_response,
                    "202 Accepted",
                    {
                        "bundleId": bundle_id,
                        "subjectId": subject_id,
                        "state": "QUEUED",
                        "capabilityState": "BLOCKED_EVIDENCE_FILES_REQUIRED",
                        "externalEvidenceStatus": "NOT_RUN",
                        "certification": "NOT_CERTIFIED",
                    },
                )
            if method == "GET" and path.startswith("/v1/gates/") and path.endswith("/latest"):
                identity = self._identity(environ)
                subject_id = path[len("/v1/gates/") : -len("/latest")].strip("/")
                query = parse_qs(str(environ.get("QUERY_STRING", "")))
                gate = query.get("gate", [None])[0]
                if not gate:
                    raise RuntimeRequestError("gate query parameter is required")
                scope = self.runtime._scope(
                    self._scope_from_headers(environ, identity), identity
                )
                document = self.runtime.store.get_document(
                    scope, "gate_decision", subject_id
                )
                if document["document"].get("requiredGate") != gate:
                    raise StoreError("no latest decision exists for the requested gate")
                return _response(start_response, "200 OK", document["document"])
            if method == "POST" and path == "/v1/gates/evaluate":
                identity = self._identity(environ)
                payload = self._payload(environ)
                subject_id = payload.get("subjectId", "gate-subject")
                gate_payload = {
                    **payload,
                    "obligations": payload.get("obligations", []),
                    "results": payload.get("results", []),
                    "requiredGate": payload.get("gate", payload.get("requiredGate", "E2_MODEL")),
                }
                result = self.runtime.dispatch(
                    "elmos-formal-release-gate",
                    self._dispatch_envelope(
                        environ,
                        identity,
                        subject_id=subject_id,
                        payload=gate_payload,
                    ),
                    identity,
                )
                return _response(start_response, "200 OK", result)
        except KeyError as exc:
            return _response(start_response, "404 Not Found", {"error": str(exc)})
        except (RuntimeAuthorizationError, ExecutionAuthorizationError) as exc:
            return _response(start_response, "403 Forbidden", {"error": str(exc)})
        except (
            RuntimeRequestError,
            ExecutionContractError,
            ObservabilityError,
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

    def _dispatch_envelope(
        self,
        environ: dict[str, Any],
        identity: TrustedIdentity,
        *,
        subject_id: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        idempotency_key = environ.get("HTTP_X_ELMOS_IDEMPOTENCY_KEY")
        if not idempotency_key:
            raise RuntimeRequestError("X-Elmos-Idempotency-Key is required")
        return {
            "scope": self._scope_from_headers(environ, identity),
            "subjectId": subject_id,
            "idempotencyKey": idempotency_key,
            **payload,
        }

    @staticmethod
    def _scope_from_headers(
        environ: dict[str, Any], identity: TrustedIdentity | None = None
    ) -> dict[str, Any]:
        """Build a read/action scope from transport-bound resource headers.

        Run reads cannot accept a request body.  Requiring all resource
        bindings here prevents a tenant-only identity from reading another
        account's proof run by guessing its identifier.
        """
        required = {
            "accountId": "HTTP_X_ELMOS_ACCOUNT_ID",
            "sourceArtifactDigest": "HTTP_X_ELMOS_SOURCE_ARTIFACT_DIGEST",
            "targetArtifactDigest": "HTTP_X_ELMOS_TARGET_ARTIFACT_DIGEST",
            "environmentDigest": "HTTP_X_ELMOS_ENVIRONMENT_DIGEST",
            "workloadKey": "HTTP_X_ELMOS_WORKLOAD_KEY",
        }
        missing = [header for key, header in required.items() if not environ.get(header)]
        if missing:
            raise RuntimeRequestError(
                "resource scope headers are required: " + ", ".join(missing)
            )
        return {
            "tenantId": environ.get("HTTP_X_ELMOS_TENANT_ID")
            or (identity.tenant_id if identity is not None else None),
            "accountId": environ[required["accountId"]],
            "projectId": environ.get("HTTP_X_ELMOS_PROJECT_ID")
            or (identity.project_id if identity is not None else None),
            "sourceArtifactDigest": environ[required["sourceArtifactDigest"]],
            "targetArtifactDigest": environ[required["targetArtifactDigest"]],
            "environmentDigest": environ[required["environmentDigest"]],
            "workloadKey": environ[required["workloadKey"]],
            "dataClassification": environ.get(
                "HTTP_X_ELMOS_DATA_CLASSIFICATION", "confidential"
            ),
        }

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
