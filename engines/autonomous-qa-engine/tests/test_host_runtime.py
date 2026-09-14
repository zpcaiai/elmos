from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from elmos_autonomous_qa.contracts import RuntimeRequest
from elmos_autonomous_qa.host_runtime import (
    HostExecutionLease,
    HostRuntimeError,
    QaHostBroker,
    SQLiteHostOperationStore,
    build_host_route_registry,
    host_runtime_coverage,
)
from elmos_autonomous_qa.skill_runtime import SKILL_REGISTRY


NOW = datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)


def request(*, request_id: str = "invocation-1", tenant_id: str = "tenant-a") -> RuntimeRequest:
    return RuntimeRequest.parse(
        {
            "schema_version": "1.0",
            "request_id": request_id,
            "tenant_id": tenant_id,
            "project_id": "project-a",
            "actor_id": "actor-a",
            "idempotency_key": "operation-1",
            "inputs": {"operation": "create", "run_id": "run-a"},
        }
    )


def lease(*, source_id: str = "00-qa-control-plane", **changes: object) -> HostExecutionLease:
    route = build_host_route_registry(SKILL_REGISTRY)[source_id]
    values: dict[str, object] = {
        "lease_id": "lease-a",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "actor_id": "actor-a",
        "environment_id": "environment-a",
        "workspace_id": "workspace-a",
        "revision_id": "revision-a",
        "purpose": "qa-qualification",
        "invocation_id": "invocation-1",
        "capability": route.capability,
        "expires_at": "2026-09-14T08:05:00Z",
        "revoked": False,
    }
    values.update(changes)
    return HostExecutionLease.parse(values)


class Provider:
    provider_id = "provider-a"

    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail
        self.last_envelope: dict[str, object] | None = None

    def execute(self, envelope: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        self.last_envelope = envelope
        if self.fail:
            raise RuntimeError("uncertain provider outcome")
        route = envelope["route"]
        assert isinstance(route, dict)
        return {
            "schema_version": "elmos.autonomous-qa.host-receipt.v1",
            "state": "SUCCEEDED",
            "request_digest": envelope["request_digest"],
            "route_digest": route["route_digest"],
            "provider_id": self.provider_id,
            "provider_receipt_digest": "sha256:" + "a" * 64,
            "external_evidence_status": "NOT_RUN",
            "independent_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }


def permit_verifier(permit: object, *_: object) -> bool:
    return isinstance(permit, dict) and permit == {"permit_id": "permit-a"}


def receipt_verifier(receipt: object, *_: object) -> bool:
    return isinstance(receipt, dict) and receipt.get("provider_id") == "provider-a"


class HostRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db = Path(temporary.name) / "host-operations.sqlite3"
        self.routes = build_host_route_registry(SKILL_REGISTRY)
        self.broker = QaHostBroker(
            routes=self.routes,
            store=SQLiteHostOperationStore(self.db),
            permit_verifier=permit_verifier,
            receipt_verifier=receipt_verifier,
            now=lambda: NOW,
        )

    def test_exact_code_coverage_is_complete_without_claiming_whole_skills(self) -> None:
        self.assertEqual(len(self.routes), 34)
        self.assertEqual(len({route.route_id for route in self.routes.values()}), 34)
        self.assertEqual(len({route.route_digest for route in self.routes.values()}), 34)
        self.assertEqual(
            host_runtime_coverage(SKILL_REGISTRY),
            {
                "exact_native_programs": 40,
                "local_terminal_programs": 6,
                "host_route_bound": 34,
                "prepare_only": 0,
                "code_binding_coverage_percent": 100,
                "whole_skills_complete": 0,
                "host_routes_digest": host_runtime_coverage(SKILL_REGISTRY)[
                    "host_routes_digest"
                ],
            },
        )

    def test_trusted_host_execution_is_durable_and_idempotent(self) -> None:
        provider = Provider()
        result = self.broker.execute(
            source_id="00-qa-control-plane",
            request=request(),
            lease=lease(),
            permit={"permit_id": "permit-a"},
            provider=provider,
        )
        replay = self.broker.execute(
            source_id="00-qa-control-plane",
            request=request(),
            lease=lease(),
            permit={"permit_id": "permit-a"},
            provider=provider,
        )
        self.assertEqual(provider.calls, 1)
        self.assertEqual(replay, result)
        self.assertEqual(result["external_evidence_status"], "NOT_RUN")
        self.assertEqual(result["certification_status"], "NOT_CERTIFIED")

    def test_scope_expiry_revocation_and_permit_fail_closed(self) -> None:
        cases = (
            (request(tenant_id="tenant-b"), lease(), {"permit_id": "permit-a"}, "scope"),
            (request(), lease(expires_at="2026-09-14T07:59:59Z"), {"permit_id": "permit-a"}, "expired"),
            (request(), lease(revoked=True), {"permit_id": "permit-a"}, "revoked"),
            (request(), lease(), {"permit_id": "wrong"}, "permit"),
        )
        for runtime_request, runtime_lease, permit, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(HostRuntimeError, message):
                self.broker.execute(
                    source_id="00-qa-control-plane",
                    request=runtime_request,
                    lease=runtime_lease,
                    permit=permit,
                    provider=Provider(),
                )

    def test_uncertain_result_blocks_retry_until_trusted_reconciliation(self) -> None:
        provider = Provider(fail=True)
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            self.broker.execute(
                source_id="00-qa-control-plane",
                request=request(),
                lease=lease(),
                permit={"permit_id": "permit-a"},
                provider=provider,
            )
        with self.assertRaisesRegex(HostRuntimeError, "reconciliation"):
            self.broker.execute(
                source_id="00-qa-control-plane",
                request=request(),
                lease=lease(),
                permit={"permit_id": "permit-a"},
                provider=Provider(),
            )
        route = self.routes["00-qa-control-plane"]
        assert provider.last_envelope is not None
        reconciled = {
            "schema_version": "elmos.autonomous-qa.host-receipt.v1",
            "state": "SUCCEEDED",
            "request_digest": provider.last_envelope["request_digest"],
            "route_digest": route.route_digest,
            "provider_id": "provider-a",
            "provider_receipt_digest": "sha256:" + "a" * 64,
        }
        self.broker.store.reconcile(
            lease=lease(),
            binding=route,
            idempotency_key="operation-1",
            result=reconciled,
            receipt_verifier=receipt_verifier,
        )
        replay = self.broker.execute(
            source_id="00-qa-control-plane",
            request=request(),
            lease=lease(),
            permit={"permit_id": "permit-a"},
            provider=Provider(),
        )
        self.assertEqual(replay, reconciled)


if __name__ == "__main__":
    unittest.main()
