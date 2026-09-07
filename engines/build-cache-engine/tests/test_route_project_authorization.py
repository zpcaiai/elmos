"""BC-10: project authorization precedes the durable idempotency claim.

Every mutating cache-parity route carries its tenancy in the request *body*
rather than in the path, so nothing in the URL tells the dispatcher which
project a request is about.  Until this suite existed, four of them --
``compilePromptPrefix``, ``appendContextLedgerEvent``, ``decideCacheAffinity``
and ``startCacheParityRun`` -- were dispatched with no ownership check at all,
which produced two distinct oracles:

* the *project* oracle: a foreign project answered ``TENANT_MISMATCH`` while an
  absent one answered ``200`` and quietly created the project, so a single
  probe read the global project namespace and, worse, claimed any name in it;
* the *idempotency-key* oracle: because :meth:`CacheControlPlane.handle` takes
  the durable claim before the handler runs, an already-used key answered
  ``IDEMPOTENCY_CONFLICT`` where a fresh key answered the handler's own
  refusal, so the difference alone enumerated the tenant's live keys -- and
  every one of those refusals burned a durable ``idempotency_records`` row for
  a request that was never authorized.

The tests below pin the closed behavior for all six body-scoped routes at
once, from the real HTTP entry point, and assert against the tables rather
than the response wherever durable state is the thing at stake.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from conftest import PROJECT, TENANT, digest
from elmos_build_cache.api import BODY_PROJECT_SCOPED_HANDLERS, CacheControlPlane, Request, Response
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.errors import TenantMismatch
from elmos_build_cache.parity_store import ParityMetadataRepository

ATTACKER_TENANT = "tenant-attacker"
ATTACKER_PROJECT = "project-attacker"
# ``PROJECT`` (from conftest) belongs to ``TENANT`` and is the victim here.
ABSENT_PROJECT = "project-never-created"
SQUATTABLE_PROJECT = "acme-production"
PRINCIPAL_A = digest("8")
PRINCIPAL_B = digest("b")


# -- the six body-scoped mutating routes ---------------------------------


@dataclass(frozen=True)
class Route:
    """One mutating route whose project scope lives in the request body."""

    handler: str
    path: str
    body: Callable[[str], dict[str, Any]]


def _prompt_body(project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "identity": {
            "provider": "openai",
            "provider_namespace_digest": digest("2"),
            "model": "gpt-5.6",
            "effort_profile": "high",
            "tool_schema_digest": digest("3"),
            "compatibility_digest": digest("4"),
        },
        "segments": [
            {
                "segment_id": "system-policy",
                "stability": "stable",
                "ordinal": 0,
                "content": "Stable system policy",
            }
        ],
    }


def _prepare_body(project_id: str) -> dict[str, Any]:
    return {**_prompt_body(project_id), "request_class": "DETERMINISTIC_CONVERSION"}


def _usage_body(project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "prompt_manifest_id": "manifest-probe",
        "provider": "openai",
        "request_id": digest("9"),
        "reason_code": "HIT",
        "usage": {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 12,
                "input_tokens_details": {"cached_tokens": 90},
            }
        },
    }


def _context_body(project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "branch_lineage": "refs/heads/main@abc123",
        "repository_snapshot_digest": digest("1"),
        "event_type": "FILE_READ",
        "payload": {"logical_path": "src/main.py", "content_digest": digest("2")},
    }


def _affinity_body(project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "request_id": "affinity-request-probe",
        "request": {
            "authorization_scope_digest": digest("5"),
            "trust_namespace": "branch-main",
            "provider": "openai",
            "model": "gpt-5.6",
            "effort_profile": "high",
            "tool_schema_digest": digest("6"),
            "prefix_compatibility_digest": digest("7"),
            "platform_digest": digest("8"),
            "required_capacity": 1,
        },
    }


def _parity_body(project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "report_id": "parity-probe",
        "metrics": {},
        "cohorts": {},
        "scenarios": [],
        "binding": {
            "source_digest": digest("a"),
            "configuration_digest": digest("b"),
            "provider_profiles_digest": digest("c"),
            "corpus_digest": digest("d"),
            "platform_digest": digest("e"),
            "generated_at": "2026-08-20T00:00:00Z",
            "executor_identity": "executor-1",
            "verifier_identity": "verifier-2",
        },
    }


ROUTES = (
    Route("compile_prompt_prefix", "/cache/prompt-prefixes/compile", _prompt_body),
    Route(
        "append_context_ledger_event",
        "/cache/context-ledgers/stream-probe/events",
        _context_body,
    ),
    Route("decide_cache_affinity", "/cache/affinity/decide", _affinity_body),
    Route("start_cache_parity_run", "/cache/parity/runs", _parity_body),
    Route("prepare_provider_prompt", "/cache/provider-prompts/prepare", _prepare_body),
    Route("record_provider_usage", "/cache/provider-prompts/usage", _usage_body),
)
ROUTE_IDS = [route.handler for route in ROUTES]


def test_every_body_scoped_route_is_covered_here() -> None:
    """The sweep below is the whole set, not a sample of it.

    A new body-scoped mutating route added to the preflight without a case in
    this file would otherwise be silently untested for both oracles.
    """

    assert {route.handler for route in ROUTES} == set(BODY_PROJECT_SCOPED_HANDLERS)


# -- fixtures ------------------------------------------------------------


@pytest.fixture
def attacker_store(store: SqliteMetadataStore) -> SqliteMetadataStore:
    with store.transaction():
        store.ensure_project(ATTACKER_TENANT, ATTACKER_PROJECT)
    return store


@pytest.fixture
def attacker(
    attacker_store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> CacheControlPlane:
    return CacheControlPlane(attacker_store, cas, ATTACKER_TENANT, clock=clock)


def _probe(
    plane: CacheControlPlane,
    route: Route,
    project_id: str,
    *,
    key: str,
    principal: str | None = None,
    body: dict[str, Any] | None = None,
) -> Response:
    return plane.handle(
        Request(
            "POST",
            route.path,
            route.body(project_id) if body is None else body,
            {"Idempotency-Key": key},
            authenticated_principal_digest=principal,
        )
    )


def _idempotency_rows(store: SqliteMetadataStore, tenant_id: str) -> list[tuple[object, ...]]:
    return [
        tuple(row)
        for row in store.query(
            "SELECT * FROM idempotency_records WHERE tenant_id=? ORDER BY idempotency_key",
            (tenant_id,),
        )
    ]


def _project_owner(store: SqliteMetadataStore, project_id: str) -> str | None:
    row = store.query_one(
        "SELECT tenant_id FROM projects WHERE project_id=?", (project_id,)
    )
    return None if row is None else str(row[0])


def _refusal_shape(response: Response) -> tuple[Any, ...]:
    """Everything an attacker can observe, except their own echoed input.

    ``details.project_id`` is the identifier the caller themself supplied, so
    it is compared separately rather than folded into the shape: echoing the
    request back is not a disclosure, differing on it would be.
    """

    body = dict(response.json())
    details = dict(body.pop("details", {}))
    details.pop("project_id", None)
    return (response.status, body.get("code"), body.get("message"), sorted(body), details)


def _burn(plane: CacheControlPlane, key: str, *, principal: str | None = None) -> Response:
    """Consume one idempotency key through the designated claim path."""

    return plane.handle(
        Request(
            "POST",
            "/runs",
            {
                "run_id": f"run-{key}",
                "project_id": ATTACKER_PROJECT,
                "source_snapshot": digest("1"),
            },
            {"Idempotency-Key": key},
            authenticated_principal_digest=principal,
        )
    )


# -- the project oracle --------------------------------------------------


@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
@pytest.mark.parametrize("principal", [None, PRINCIPAL_A], ids=["anonymous", "principal-a"])
def test_a_foreign_project_is_indistinguishable_from_an_absent_one(
    attacker: CacheControlPlane,
    route: Route,
    principal: str | None,
) -> None:
    """Response code alone must not enumerate the global project namespace."""

    foreign = _probe(attacker, route, PROJECT, key=f"foreign-{route.handler}", principal=principal)
    absent = _probe(
        attacker, route, ABSENT_PROJECT, key=f"absent-{route.handler}", principal=principal
    )
    second_absent = _probe(
        attacker,
        route,
        "project-also-never-created",
        key=f"absent2-{route.handler}",
        principal=principal,
    )

    assert foreign.status == 404
    assert _refusal_shape(foreign) == _refusal_shape(absent) == _refusal_shape(second_absent)
    assert foreign.json() == {
        "code": "NOT_FOUND",
        "message": "project does not exist",
        "details": {"project_id": PROJECT},
    }
    assert absent.json()["details"] == {"project_id": ABSENT_PROJECT}


@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
def test_the_refusal_does_not_depend_on_the_rest_of_the_body(
    attacker: CacheControlPlane,
    route: Route,
) -> None:
    """Ownership is settled before the body is ever parsed.

    A well-formed body and a body that could not survive validation must be
    refused identically; otherwise the *validation* outcome becomes a second
    channel that tells an unauthorized caller their payload was at least
    structurally interesting to this project.
    """

    valid = _probe(attacker, route, PROJECT, key=f"shape-valid-{route.handler}")
    malformed = _probe(
        attacker,
        route,
        PROJECT,
        key=f"shape-malformed-{route.handler}",
        body={"project_id": PROJECT, "utterly": "wrong"},
    )

    assert valid.status == malformed.status == 404
    assert valid.json() == malformed.json()


@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
def test_no_route_brings_a_project_into_existence(
    attacker: CacheControlPlane,
    attacker_store: SqliteMetadataStore,
    route: Route,
) -> None:
    """A compile-like call is not a claim on a globally unique name."""

    assert _project_owner(attacker_store, ABSENT_PROJECT) is None

    response = _probe(attacker, route, ABSENT_PROJECT, key=f"squat-{route.handler}")

    assert response.status == 404
    assert _project_owner(attacker_store, ABSENT_PROJECT) is None


def test_project_scope_is_claimed_only_by_the_run_route(
    attacker: CacheControlPlane,
    attacker_store: SqliteMetadataStore,
) -> None:
    """``POST /runs`` is the designated -- and only -- claim path.

    ``create_run`` treats ``project_id`` as an identifier being *claimed* and
    keeps ``CONFLICT`` for a name it may not have, which is exactly why it is
    the right place for creation: the caller asked to own something, and the
    refusal it gets is about their own claim rather than about somebody else's
    project.
    """

    for route in ROUTES:
        assert (
            _probe(attacker, route, SQUATTABLE_PROJECT, key=f"pre-{route.handler}").status
            == 404
        )
    assert _project_owner(attacker_store, SQUATTABLE_PROJECT) is None

    created = attacker.handle(
        Request(
            "POST",
            "/runs",
            {
                "run_id": "run-claimed-0001",
                "project_id": SQUATTABLE_PROJECT,
                "source_snapshot": digest("1"),
            },
            {"Idempotency-Key": "claim-the-name"},
        )
    )

    assert created.status == 201
    assert _project_owner(attacker_store, SQUATTABLE_PROJECT) == ATTACKER_TENANT
    # And now that the scope exists and is owned, the parity routes work.
    compiled = _probe(
        attacker, ROUTES[0], SQUATTABLE_PROJECT, key="compile-after-claim"
    )
    assert compiled.status == 200


# -- the idempotency-key oracle ------------------------------------------


@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
def test_a_used_key_and_a_fresh_key_answer_an_unauthorized_caller_identically(
    attacker: CacheControlPlane,
    attacker_store: SqliteMetadataStore,
    route: Route,
) -> None:
    """The refusal must not leak which idempotency keys exist in the tenant."""

    used = f"used-{route.handler}"
    assert _burn(attacker, used).status == 201
    before = _idempotency_rows(attacker_store, ATTACKER_TENANT)

    reused = _probe(attacker, route, PROJECT, key=used)
    fresh = _probe(attacker, route, PROJECT, key=f"fresh-{route.handler}")

    assert reused.status == fresh.status == 404
    assert reused.json() == fresh.json()
    # Neither probe wrote a row, and neither overwrote the burned key's own
    # record: the durable table is byte-for-byte what it was before.
    assert _idempotency_rows(attacker_store, ATTACKER_TENANT) == before


@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
def test_a_cross_tenant_refusal_writes_no_idempotency_record(
    attacker: CacheControlPlane,
    attacker_store: SqliteMetadataStore,
    route: Route,
) -> None:
    """A request that was never authorized must not burn the caller's key."""

    owner_rows = _idempotency_rows(attacker_store, TENANT)
    key = f"cross-tenant-{route.handler}"

    assert _probe(attacker, route, PROJECT, key=key).status == 404

    assert (
        attacker_store.query_one(
            "SELECT COUNT(*) FROM idempotency_records"
            " WHERE tenant_id=? AND idempotency_key=?",
            (ATTACKER_TENANT, key),
        )[0]
        == 0
    )
    # No read of, and no write to, the victim tenant's records either.
    assert _idempotency_rows(attacker_store, TENANT) == owner_rows
    # The key is still unused, so the attacker's own legitimate work with it
    # still succeeds -- a refusal consumed nothing.
    assert _burn(attacker, key).status == 201


@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
def test_a_cross_principal_refusal_writes_no_idempotency_record(
    attacker: CacheControlPlane,
    attacker_store: SqliteMetadataStore,
    route: Route,
) -> None:
    """Idempotency keys are tenant-scoped, so a second principal shares them.

    Principal B may therefore neither burn nor detect principal A's key by
    probing a project the tenant does not own: the refusal is decided before
    the claim, so it is identical whether or not A's key exists, and it leaves
    A's record exactly as it was.
    """

    key = f"cross-principal-{route.handler}"
    assert _burn(attacker, key, principal=PRINCIPAL_A).status == 201
    before = _idempotency_rows(attacker_store, ATTACKER_TENANT)

    stolen = _probe(attacker, route, PROJECT, key=key, principal=PRINCIPAL_B)
    unrelated = _probe(
        attacker, route, PROJECT, key=f"{key}-unused", principal=PRINCIPAL_B
    )

    assert stolen.status == unrelated.status == 404
    assert stolen.json() == unrelated.json()
    assert _idempotency_rows(attacker_store, ATTACKER_TENANT) == before
    # Principal A's own replay is untouched by principal B's probe.
    replay = _burn(attacker, key, principal=PRINCIPAL_A)
    assert replay.status == 201
    assert replay.headers is not None
    assert replay.headers["Idempotent-Replay"] == "true"


def test_preflight_precedes_the_durable_claim_on_every_body_scoped_route(
    attacker: CacheControlPlane,
    attacker_store: SqliteMetadataStore,
) -> None:
    """The ordering regression test: this fails if the preflight moves back.

    Moving ``_authorize_resource_preflight`` after ``claim_idempotent`` in
    :meth:`CacheControlPlane.handle` flips both halves at once -- the reused
    key starts answering ``409 IDEMPOTENCY_CONFLICT`` while the fresh key
    answers the handler's own refusal, and every probe leaves a ``PENDING`` or
    ``COMPLETE`` row behind. Both halves are asserted here for all six routes
    in one place so the ordering cannot be quietly relaxed for one of them.
    """

    assert _burn(attacker, "ordering-key").status == 201
    baseline = _idempotency_rows(attacker_store, ATTACKER_TENANT)

    for route in ROUTES:
        reused = _probe(attacker, route, PROJECT, key="ordering-key")
        fresh = _probe(attacker, route, PROJECT, key=f"ordering-fresh-{route.handler}")

        assert reused.status == 404, route.handler
        assert reused.json()["code"] == "NOT_FOUND", route.handler
        assert reused.json() == fresh.json(), route.handler

    assert _idempotency_rows(attacker_store, ATTACKER_TENANT) == baseline
    assert (
        attacker_store.query_one("SELECT COUNT(*) FROM idempotency_records")[0]
        == len(baseline)
    )


# -- the repository can no longer be used as a claim primitive -----------


def test_the_control_planes_parity_repository_cannot_claim_a_project(
    attacker: CacheControlPlane,
    attacker_store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
) -> None:
    """Defence in depth beneath the preflight.

    The preflight is what closes the routes, but the repository the plane
    serves requests with refuses to claim scope at all -- including when the
    repository was injected by whoever composed the plane -- so a future route
    that forgets its preflight clause still cannot squat a global name.
    """

    injected = ParityMetadataRepository(attacker_store)
    assert injected.project_scope_claim is True
    plane = CacheControlPlane(
        attacker_store,
        cas,
        ATTACKER_TENANT,
        clock=clock,
        parity_repository=injected,
    )

    serving = plane.parity_repository
    assert isinstance(serving, ParityMetadataRepository)
    assert serving.project_scope_claim is False
    assert isinstance(attacker.parity_repository, ParityMetadataRepository)
    assert attacker.parity_repository.project_scope_claim is False
    # The injected repository the composer still holds keeps its own claim
    # capability: the plane took a non-claiming view rather than disarming a
    # collaborator's object underneath it.
    assert injected.project_scope_claim is True

    with pytest.raises(TenantMismatch):
        serving._ensure_scope(ATTACKER_TENANT, ABSENT_PROJECT)
    assert _project_owner(attacker_store, ABSENT_PROJECT) is None


def test_a_request_serving_repository_answers_absent_and_foreign_alike(
    attacker_store: SqliteMetadataStore,
) -> None:
    serving = ParityMetadataRepository(attacker_store, project_scope_claim=False)

    with pytest.raises(TenantMismatch) as absent:
        serving._ensure_scope(ATTACKER_TENANT, ABSENT_PROJECT)
    with pytest.raises(TenantMismatch) as foreign:
        serving._ensure_scope(ATTACKER_TENANT, PROJECT)

    assert absent.value.code == foreign.value.code
    assert absent.value.message == foreign.value.message
    assert absent.value.http_status == foreign.value.http_status == 404
