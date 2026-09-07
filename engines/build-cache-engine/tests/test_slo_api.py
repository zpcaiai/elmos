from __future__ import annotations

from typing import Any

from conftest import PROJECT, TENANT, digest
from elmos_build_cache.api import CacheControlPlane, Request
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.slo_service import CacheSloControlService


class _State:
    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": "1.2.0", "phase": "OBSERVE"}


class _SloService(CacheSloControlService):
    """Scope-valid test double for the production registry boundary.

    The API deliberately rejects duck-typed services returned by an untrusted
    registry.  This double keeps the handlers deterministic while carrying the
    same tenant/project/controller/principal and persistence bindings that the
    real service exposes.
    """

    def __init__(self, store: SqliteMetadataStore, cas: ContentAddressableStore) -> None:
        self.tenant_id = TENANT
        self.project_id = PROJECT
        self.controller_id = "controller-1"
        self.principal_digest = digest("9")
        self.store = store
        self.cas = cas
        self.calls: list[str] = []

    def status(self) -> dict[str, Any]:
        self.calls.append("status")
        return {"state": _State(), "sequence": 1, "certified": False}

    def propose(self) -> dict[str, Any]:
        self.calls.append("propose")
        return {"kind": "proposal", "shadow_only": True}

    def install(self, proposal_digest: str) -> dict[str, Any]:
        self.calls.append(f"install:{proposal_digest}")
        return {"state": _State(), "sequence": 2}

    def advance(self) -> dict[str, Any]:
        self.calls.append("advance")
        return {"state": _State(), "sequence": 2}

    def reconcile(self) -> dict[str, Any]:
        self.calls.append("reconcile")
        return {"state": _State(), "sequence": 2}

    def rollback(self, reason: Any) -> dict[str, Any]:
        self.calls.append(f"rollback:{reason}")
        return {"state": _State(), "sequence": 2}


class _Registry:
    def __init__(self, service: _SloService) -> None:
        self.service_instance = service

    def service(
        self,
        tenant_id: str,
        project_id: str,
        controller_id: str,
        principal_digest: str,
    ) -> _SloService:
        assert all((tenant_id, project_id, controller_id, principal_digest))
        return self.service_instance


class _JobResult:
    def to_dict(self) -> dict[str, Any]:
        return {"external_evidence_state": "NOT_RUN", "certification_state": "NOT_CERTIFIED"}


class _Jobs:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def run_harness_once(self, request: Any, *, authenticated_principal_digest: str) -> _JobResult:
        self.calls.append(("harness", (request, authenticated_principal_digest)))
        return _JobResult()

    def reconcile_slo_once(self, request: Any, *, authenticated_principal_digest: str) -> _JobResult:
        self.calls.append(("reconcile", (request, authenticated_principal_digest)))
        return _JobResult()


def _plane(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    registry: Any,
) -> CacheControlPlane:
    return CacheControlPlane(
        store,
        cas,
        TENANT,
        clock=clock,
        slo_runtime_registry=registry,
    )


def test_slo_status_is_json_safe_and_routes_are_wired(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    service = _SloService(store, cas)
    plane = _plane(store, cas, clock, _Registry(service))

    response = plane.handle(
        Request(
            "GET",
            f"/cache/slo/projects/{PROJECT}/controllers/controller-1",
            authenticated_principal_digest=digest("9"),
        )
    )

    assert response.status == 200
    assert response.json()["state"] == {"schema_version": "1.2.0", "phase": "OBSERVE"}
    assert service.calls == ["status"]


def test_slo_mutation_validates_before_claiming_idempotency(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    service = _SloService(store, cas)
    plane = _plane(store, cas, clock, _Registry(service))
    path = f"/cache/slo/projects/{PROJECT}/controllers/controller-1/advance"
    before = store.query_one("SELECT COUNT(*) FROM idempotency_records")

    response = plane.handle(
        Request(
            "POST",
            path,
            {"unexpected": True},
            {"Idempotency-Key": "slo-invalid-body"},
            authenticated_principal_digest=digest("9"),
        )
    )

    assert response.status == 422
    assert response.json()["code"] == "CONTRACT_VIOLATION"
    assert store.query_one("SELECT COUNT(*) FROM idempotency_records") == before
    assert service.calls == []


def test_slo_reconcile_dispatches_to_durable_service(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    service = _SloService(store, cas)
    plane = _plane(store, cas, clock, _Registry(service))

    response = plane.handle(
        Request(
            "POST",
            f"/cache/slo/projects/{PROJECT}/controllers/controller-1/reconcile",
            {},
            {"Idempotency-Key": "slo-reconcile"},
            authenticated_principal_digest=digest("9"),
        )
    )

    assert response.status == 200
    assert response.json()["state"] == {"schema_version": "1.2.0", "phase": "OBSERVE"}
    assert service.calls == ["reconcile"]


def test_local_parity_job_routes_require_exact_body_and_authenticated_scope(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    jobs = _Jobs()
    plane = CacheControlPlane(
        store,
        cas,
        TENANT,
        clock=clock,
        parity_job_service=jobs,  # type: ignore[arg-type]
    )
    response = plane.handle(
        Request(
            "POST",
            f"/cache/parity/projects/{PROJECT}/jobs/job-1/harness",
            {"runner_id": "runner-1", "report_id": "report-1"},
            {"Idempotency-Key": "job-1"},
            authenticated_principal_digest=digest("9"),
        )
    )
    assert response.status == 200
    assert response.json()["external_evidence_state"] == "NOT_RUN"
    assert [kind for kind, _ in jobs.calls] == ["harness"]

    invalid = plane.handle(
        Request(
            "POST",
            f"/cache/slo/projects/{PROJECT}/controllers/controller-1/jobs/job-2/reconcile",
            {"unexpected": True},
            {"Idempotency-Key": "job-2"},
            authenticated_principal_digest=digest("9"),
        )
    )
    assert invalid.status == 422
    assert [kind for kind, _ in jobs.calls] == ["harness"]
