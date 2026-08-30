from __future__ import annotations

from datetime import UTC, datetime, timedelta
import io
import json
import unittest

from elmos_pdhi.control_plane import ProductionControlPlane
from elmos_pdhi.service import (
    INVOKE_SCOPE,
    OBSERVE_SCOPE,
    READ_SCOPE,
    AuthenticationError,
    PdhiService,
    RequestMetadata,
    TrustedPrincipal,
)
from elmos_pdhi.store import ScopeBinding, SqlitePdhiStore


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


class _Authenticator:
    trusted_for_production = True

    def __init__(self, principal: TrustedPrincipal | None) -> None:
        self.principal = principal

    def authenticate(self, request: RequestMetadata) -> TrustedPrincipal:
        if self.principal is None:
            raise AuthenticationError("invalid token", code="BAD_TOKEN")
        return self.principal

    def readiness(self):
        return {"status": "READY", "provider": "test-independent-adapter"}


def principal(*, tenant: str = "tenant-a", project: str = "project-a", expired: bool = False) -> TrustedPrincipal:
    return TrustedPrincipal(
        tenant,
        project,
        "actor-a",
        DIGEST_A,
        DIGEST_B,
        DIGEST_C,
        "https://identity.example.test",
        "elmos-pdhi",
        frozenset({INVOKE_SCOPE, READ_SCOPE, OBSERVE_SCOPE}),
        datetime.now(UTC) + (timedelta(seconds=-1) if expired else timedelta(minutes=5)),
    )


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SqlitePdhiStore(":memory:")
        self.scope = ScopeBinding("tenant-a", "project-a", "actor-a", DIGEST_A, DIGEST_B)
        self.store.register_scope(self.scope)
        self.service = PdhiService(
            ProductionControlPlane(self.store),
            self.store,
            _Authenticator(principal()),
        )

    def tearDown(self) -> None:
        self.store.close()

    @staticmethod
    def invocation(payload: dict | None = None) -> bytes:
        return json.dumps(
            {
                "operation": "tenant-isolation",
                "idempotency_key": "request-1",
                "payload": payload or {},
            }
        ).encode()

    def test_liveness_and_readiness_are_honest(self) -> None:
        live = self.service.handle("GET", "/healthz")
        ready = self.service.handle("GET", "/readyz")
        self.assertEqual(200, live.status)
        self.assertEqual(200, ready.status)
        body = json.loads(ready.body)
        self.assertTrue(body["accepting_requests"])
        self.assertFalse(body["production_ready"])
        self.assertEqual("NOT_RUN", body["external_evidence"])
        self.assertEqual("NOT_CERTIFIED", body["certification"])

    def test_invocation_uses_principal_scope(self) -> None:
        response = self.service.handle(
            "POST",
            "/v1/control-plane/invocations",
            headers={"content-type": "application/json"},
            body=self.invocation(),
        )
        self.assertEqual(200, response.status, response.body)
        body = json.loads(response.body)
        self.assertEqual("tenant-a", body["authenticated_scope"]["tenant_id"])
        self.assertEqual("project-a", body["authenticated_scope"]["project_id"])
        self.assertEqual("NOT_CERTIFIED", body["result"]["certification_status"])

    def test_request_cannot_inject_authoritative_identity(self) -> None:
        value = json.loads(self.invocation())
        value["actor_id"] = "attacker"
        response = self.service.handle(
            "POST",
            "/v1/control-plane/invocations",
            headers={"content-type": "application/json"},
            body=json.dumps(value).encode(),
        )
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_INVOCATION_FIELDS", json.loads(response.body)["error"]["code"])

    def test_cross_tenant_payload_fails_closed(self) -> None:
        response = self.service.handle(
            "POST",
            "/v1/control-plane/invocations",
            headers={"content-type": "application/json"},
            body=self.invocation({"tenant_id": "tenant-b"}),
        )
        self.assertEqual(400, response.status)
        self.assertEqual("SCOPE_MISMATCH", json.loads(response.body)["error"]["code"])

    def test_expired_principal_is_unauthorized_without_detail_leak(self) -> None:
        service = PdhiService(
            ProductionControlPlane(self.store),
            self.store,
            _Authenticator(principal(expired=True)),
        )
        response = service.handle(
            "POST",
            "/v1/control-plane/invocations",
            headers={"content-type": "application/json"},
            body=self.invocation(),
        )
        self.assertEqual(401, response.status)
        body = json.loads(response.body)
        self.assertEqual("PRINCIPAL_EXPIRED", body["error"]["code"])
        self.assertEqual("authentication failed", body["error"]["message"])

    def test_content_type_size_and_duplicate_keys_fail(self) -> None:
        wrong_type = self.service.handle(
            "POST", "/v1/control-plane/invocations", headers={}, body=self.invocation()
        )
        self.assertEqual(415, wrong_type.status)
        duplicate = self.service.handle(
            "POST",
            "/v1/control-plane/invocations",
            headers={"content-type": "application/json"},
            body=b'{"operation":"tenant-isolation","operation":"readiness","idempotency_key":"a","payload":{}}',
        )
        self.assertEqual(400, duplicate.status)
        self.assertEqual("DUPLICATE_JSON_KEY", json.loads(duplicate.body)["error"]["code"])
        too_large = PdhiService(
            ProductionControlPlane(self.store),
            self.store,
            _Authenticator(principal()),
            max_request_bytes=1024,
        ).handle(
            "POST",
            "/v1/control-plane/invocations",
            headers={"content-type": "application/json"},
            body=b"x" * 1025,
        )
        self.assertEqual(413, too_large.status)

    def test_wsgi_requires_content_length(self) -> None:
        status: list[str] = []

        def start_response(value, headers):
            status.append(value)

        output = self.service(
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/v1/control-plane/invocations",
                "CONTENT_TYPE": "application/json",
                "wsgi.input": io.BytesIO(self.invocation()),
                "REMOTE_ADDR": "127.0.0.1",
            },
            start_response,
        )
        self.assertTrue(status[0].startswith("411 "))
        self.assertIn(b"CONTENT_LENGTH_REQUIRED", b"".join(output))

    def test_metrics_requires_authentication(self) -> None:
        blocked = PdhiService(
            ProductionControlPlane(self.store),
            self.store,
            _Authenticator(None),
        ).handle("GET", "/metrics")
        self.assertEqual(401, blocked.status)
        allowed = self.service.handle("GET", "/metrics")
        self.assertEqual(200, allowed.status)
        self.assertIn(b"elmos_pdhi_http_requests_total", allowed.body)


if __name__ == "__main__":
    unittest.main()
