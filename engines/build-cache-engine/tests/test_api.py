"""Control-plane contract tests: idempotency, digest addressing, pagination."""

from __future__ import annotations

import json
import threading

import pytest

from conftest import TENANT, claim_node, digest
from elmos_build_cache.api import (
    AUTHENTICATED_CONTEXT_ENVIRON_KEY,
    MAX_REQUEST_BODY_BYTES,
    AuthenticatedHttpContext,
    CacheControlPlane,
    Request,
    Response,
    wsgi_app,
)
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.db.records import StagedFileRecord
from elmos_build_cache.enums import FileClass, StagedFileStatus
from elmos_build_cache.journal import RunCoordinator
from elmos_build_cache.publish import TreePublisher
from elmos_build_cache.staging import Workspace

KEY = digest("7")
OTHER_TENANT = "tenant-other"
HTTP_CONTEXT = AuthenticatedHttpContext(TENANT, digest("9"))


@pytest.fixture
def plane(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    workspace: Workspace,
    publisher: TreePublisher,
    clock: ManualClock,
    run: str,
) -> CacheControlPlane:
    return CacheControlPlane(
        store,
        cas,
        TENANT,
        workspaces={run: workspace},
        publishers={run: publisher},
        clock=clock,
    )


def create_foreign_run_and_staged_file(store: SqliteMetadataStore) -> tuple[str, str]:
    run_id = "run-foreign"
    staged_file_id = "sf-foreign"
    with store.transaction():
        store.ensure_project(OTHER_TENANT, "project-other")
        snapshot_id = store.record_snapshot(
            OTHER_TENANT,
            "project-other",
            digest("3"),
            digest("4"),
            "elmos.snapshot-policy/1.0.0",
        )
        store.create_run(
            run_id,
            OTHER_TENANT,
            "project-other",
            snapshot_id,
            "1.0.0",
        )
        store.insert_staged_file(
            StagedFileRecord(
                staged_file_id=staged_file_id,
                tenant_id=OTHER_TENANT,
                project_id="project-other",
                run_id=run_id,
                node_id="foreign-node",
                attempt=1,
                logical_path="foreign.txt",
                file_class=FileClass.STAGED_INTERMEDIATE,
                status=StagedFileStatus.RESERVED,
                lease_epoch=1,
                version=0,
            )
        )
    return run_id, staged_file_id


def test_mutations_require_an_idempotency_key(plane: CacheControlPlane) -> None:
    response = plane.handle(Request("PUT", f"/blobs/{digest('a')[7:]}", b"payload"))
    assert response.status == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_replaying_the_same_request_returns_the_original_response(plane: CacheControlPlane) -> None:
    headers = {"Idempotency-Key": "upload-1"}
    first = plane.handle(Request("PUT", "/blobs/" + digest("a")[7:], b"payload", headers))
    assert first.status == 422  # digest mismatch: the body is not "payload"'s digest

    body = b"payload"
    from elmos_build_cache.canonical import sha256_bytes

    correct = sha256_bytes(body)
    second = plane.handle(Request("PUT", f"/blobs/{correct}", body, {"Idempotency-Key": "upload-2"}))
    replay = plane.handle(Request("PUT", f"/blobs/{correct}", body, {"Idempotency-Key": "upload-2"}))
    assert second.status == 201
    assert replay.json() == second.json()
    assert replay.headers is not None and replay.headers.get("Idempotent-Replay") == "true"


def test_reusing_a_key_for_a_different_request_is_a_conflict(plane: CacheControlPlane) -> None:
    from elmos_build_cache.canonical import sha256_bytes

    first = b"one"
    plane.handle(Request("PUT", f"/blobs/{sha256_bytes(first)}", first, {"Idempotency-Key": "k"}))
    clash = plane.handle(
        Request("PUT", f"/blobs/{sha256_bytes(b'two-different')}", b"two-different", {"Idempotency-Key": "k"})
    )
    assert clash.status == 409
    assert clash.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_binary_idempotency_binds_bytes_not_only_length(plane: CacheControlPlane) -> None:
    from elmos_build_cache.canonical import sha256_bytes

    first = b"one"
    second = b"two"
    path = f"/blobs/{sha256_bytes(first)}"
    headers = {"Idempotency-Key": "same-length-different-bytes"}

    assert plane.handle(Request("PUT", path, first, headers)).status == 201
    conflict = plane.handle(Request("PUT", path, second, headers))

    assert conflict.status == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_idempotency_cannot_replay_across_authenticated_principals(
    plane: CacheControlPlane,
) -> None:
    calls: list[str] = []

    def effect(_request: Request, _params: dict[str, str]) -> Response:
        calls.append("called")
        return Response(201, {"created": True})

    plane.route("POST", "/test/principal-idempotency", effect)
    headers = {"Idempotency-Key": "principal-bound-key"}
    first = plane.handle(
        Request(
            "POST",
            "/test/principal-idempotency",
            {"same": "body"},
            headers,
            authenticated_principal_digest=digest("8"),
        )
    )
    conflict = plane.handle(
        Request(
            "POST",
            "/test/principal-idempotency",
            {"same": "body"},
            headers,
            authenticated_principal_digest=digest("9"),
        )
    )

    assert first.status == 201
    assert conflict.status == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert calls == ["called"]


def test_idempotency_binds_semantic_query_and_content_headers(
    plane: CacheControlPlane,
) -> None:
    calls: list[str] = []

    def effect(_request: Request, _params: dict[str, str]) -> Response:
        calls.append("called")
        return Response(202, {"receipt": "receipt-1"})

    plane.route("POST", "/test/fingerprint", effect)
    body = {"value": "stable"}
    base_headers = {
        "Idempotency-Key": "semantic-query",
        "Content-Type": "application/json",
    }
    first = plane.handle(
        Request(
            "POST",
            "/test/fingerprint",
            body,
            base_headers,
            {"alpha": "1", "omega": "9"},
        )
    )
    replay = plane.handle(
        Request(
            "POST",
            "/test/fingerprint",
            body,
            base_headers,
            {"omega": "9", "alpha": "1"},
        )
    )
    query_drift = plane.handle(
        Request(
            "POST",
            "/test/fingerprint",
            body,
            base_headers,
            {"alpha": "2", "omega": "9"},
        )
    )
    assert first.status == replay.status == 202
    assert replay.headers["Idempotent-Replay"] == "true"
    assert query_drift.status == 409
    assert query_drift.json()["code"] == "IDEMPOTENCY_CONFLICT"

    header_key = {**base_headers, "Idempotency-Key": "semantic-header"}
    assert (
        plane.handle(
            Request("POST", "/test/fingerprint", body, header_key, {"alpha": "1"})
        ).status
        == 202
    )
    header_drift = plane.handle(
        Request(
            "POST",
            "/test/fingerprint",
            body,
            {**header_key, "Content-Type": "application/octet-stream"},
            {"alpha": "1"},
        )
    )
    assert header_drift.status == 409
    assert header_drift.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert calls == ["called", "called"]


def test_idempotency_replays_full_binary_response(plane: CacheControlPlane) -> None:
    def effect(_request: Request, _params: dict[str, str]) -> Response:
        return Response(
            207,
            b"durable response bytes",
            {"Content-Type": "application/octet-stream", "X-Receipt": "receipt-7"},
        )

    plane.route("POST", "/test/binary-response", effect)
    request = Request(
        "POST",
        "/test/binary-response",
        b"request bytes",
        {"Idempotency-Key": "binary-response", "Content-Type": "application/octet-stream"},
    )
    first = plane.handle(request)
    replay = plane.handle(request)

    assert first.status == replay.status == 207
    assert first.body == replay.body == b"durable response bytes"
    assert first.headers["X-Receipt"] == replay.headers["X-Receipt"] == "receipt-7"
    assert first.headers["X-Elmos-Api-Version"] == replay.headers["X-Elmos-Api-Version"]
    assert replay.headers["Idempotent-Replay"] == "true"


def test_concurrent_idempotency_claim_executes_only_one_handler(
    tmp_path, clock: ManualClock
) -> None:
    database = tmp_path / "concurrent" / "index.sqlite"
    cas_root = tmp_path / "concurrent" / "cache"
    entered = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    calls: list[str] = []
    responses: dict[str, Response] = {}

    def worker(name: str, block: bool) -> None:
        store = SqliteMetadataStore.open(database, clock)
        try:
            control_plane = CacheControlPlane(
                store, ContentAddressableStore(cas_root), TENANT, clock=clock
            )

            def effect(_request: Request, _params: dict[str, str]) -> Response:
                with lock:
                    calls.append(name)
                if block:
                    entered.set()
                    assert release.wait(timeout=5)
                return Response(201, {"owner": name})

            control_plane.route("POST", "/test/concurrent-effect", effect)
            responses[name] = control_plane.handle(
                Request(
                    "POST",
                    "/test/concurrent-effect",
                    {"value": "same"},
                    {"Idempotency-Key": "concurrent-key", "Content-Type": "application/json"},
                )
            )
        finally:
            store.close()

    first = threading.Thread(target=worker, args=("first", True))
    second = threading.Thread(target=worker, args=("second", False))
    first.start()
    assert entered.wait(timeout=5)
    second.start()
    second.join(timeout=5)
    try:
        assert not second.is_alive()
        assert responses["second"].status == 409
        assert responses["second"].json()["code"] == "OUTCOME_UNKNOWN"
    finally:
        release.set()
        first.join(timeout=5)
        second.join(timeout=5)
    assert not first.is_alive()
    assert responses["first"].status == 201
    assert calls == ["first"]


def test_crash_after_effect_leaves_pending_and_never_automatically_retries(
    tmp_path, clock: ManualClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "crash" / "index.sqlite"
    first_store = SqliteMetadataStore.open(database, clock)
    second_store = SqliteMetadataStore.open(database, clock)
    calls: list[str] = []
    try:
        first = CacheControlPlane(
            first_store, ContentAddressableStore(tmp_path / "crash" / "cache"), TENANT, clock=clock
        )
        second = CacheControlPlane(
            second_store, ContentAddressableStore(tmp_path / "crash" / "cache"), TENANT, clock=clock
        )

        def effect(_request: Request, _params: dict[str, str]) -> Response:
            calls.append("effect")
            return Response(201, {"external_receipt": "receipt-unknown"})

        first.route("POST", "/test/crash-effect", effect)
        second.route("POST", "/test/crash-effect", effect)

        def crash(_request: Request, _response: Response) -> None:
            raise RuntimeError("simulated process death")

        monkeypatch.setattr(first, "_idempotency_before_complete", crash)
        request = Request(
            "POST",
            "/test/crash-effect",
            {"value": "same"},
            {"Idempotency-Key": "crash-key", "Content-Type": "application/json"},
        )
        ambiguous = first.handle(request)
        retry = second.handle(request)

        assert ambiguous.status == 500
        assert ambiguous.json()["code"] == "OUTCOME_UNKNOWN"
        assert retry.status == 409
        assert retry.json()["code"] == "OUTCOME_UNKNOWN"
        assert calls == ["effect"]
        row = second_store.query_one(
            "SELECT state, completed_at FROM idempotency_records"
            " WHERE tenant_id=? AND idempotency_key=?",
            (TENANT, "crash-key"),
        )
        assert row == ("PENDING", None)
    finally:
        first_store.close()
        second_store.close()


def test_blob_upload_is_digest_addressed(plane: CacheControlPlane) -> None:
    response = plane.handle(
        Request("PUT", "/blobs/" + digest("0")[7:], b"not the declared content", {"Idempotency-Key": "x"})
    )
    assert response.status == 422
    assert response.json()["code"] == "DIGEST_MISMATCH"


def test_blob_head_get_roundtrip(
    plane: CacheControlPlane,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
) -> None:
    stored = cas.put_bytes(b"artifact bytes")
    with store.transaction():
        store.register_artifact(
            TENANT,
            stored,
            size_bytes=len(b"artifact bytes"),
            media_type="application/octet-stream",
            artifact_kind="blob",
        )
    head = plane.handle(Request("HEAD", f"/blobs/{stored[7:]}"))
    assert head.status == 200
    assert head.headers is not None and head.headers["X-Elmos-Digest"] == stored
    body = plane.handle(Request("GET", f"/blobs/{stored[7:]}"))
    assert body.body == b"artifact bytes"
    assert plane.handle(Request("HEAD", f"/blobs/{digest('f')[7:]}")).status == 404


def test_blob_reads_require_current_tenant_registration_without_leaking_shared_cas(
    plane: CacheControlPlane,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
) -> None:
    shared = cas.put_bytes(b"registered only to another tenant")
    with store.transaction():
        store.register_artifact(
            OTHER_TENANT,
            shared,
            size_bytes=len(b"registered only to another tenant"),
            media_type="application/octet-stream",
            artifact_kind="blob",
        )
    before_cas = cas.accounting()
    before_rows = store.query_one("SELECT COUNT(*) FROM artifacts")

    foreign_head = plane.handle(Request("HEAD", f"/blobs/{shared[7:]}"))
    absent_head = plane.handle(Request("HEAD", f"/blobs/{digest('e')[7:]}"))
    foreign_get = plane.handle(Request("GET", f"/blobs/{shared[7:]}"))
    absent_get = plane.handle(Request("GET", f"/blobs/{digest('e')[7:]}"))

    assert foreign_head.status == absent_head.status == 404
    assert foreign_head.json() == absent_head.json()
    assert foreign_get.status == absent_get.status == 404
    assert foreign_get.json() == absent_get.json()
    assert cas.accounting() == before_cas
    assert store.query_one("SELECT COUNT(*) FROM artifacts") == before_rows
    assert store.get_artifact(TENANT, shared) is None


def test_action_lookup_returns_structured_miss_reasons(plane: CacheControlPlane) -> None:
    response = plane.handle(Request("GET", f"/cache/actions/{KEY[7:]}"))
    assert response.status == 404
    assert response.json()["miss_reasons"] == ["NO_ENTRY"]


def test_action_commit_then_lookup(
    plane: CacheControlPlane,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
) -> None:
    output = cas.put_bytes(b"generated")
    with store.transaction():
        store.register_artifact(
            TENANT,
            output,
            size_bytes=len(b"generated"),
            media_type="application/octet-stream",
            artifact_kind="stage-output",
        )
    payload = {
        "stage_id": "target-code-generation",
        "stage_version": "1.0.0",
        "output_artifacts": [output],
        "required_outputs": [output],
        "validation_level": "TEST_VERIFIED",
        "producer_identity": "worker-1",
        "metrics": {"wall_ms": 1200, "cpu_ms": 900, "model_tokens": 5000},
    }
    created = plane.handle(
        Request("PUT", f"/cache/actions/{KEY[7:]}", payload, {"Idempotency-Key": "commit-1"})
    )
    assert created.status == 201

    found = plane.handle(
        Request("GET", f"/cache/actions/{KEY[7:]}", query={"minimumValidation": "COMPILE_VERIFIED"})
    )
    assert found.status == 200
    assert found.json()["result"]["output_artifacts"] == [output]


def test_action_commit_denies_foreign_output_before_idempotency_or_cas_write(
    plane: CacheControlPlane,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
) -> None:
    output = cas.put_bytes(b"foreign output")
    with store.transaction():
        store.register_artifact(
            OTHER_TENANT,
            output,
            size_bytes=len(b"foreign output"),
            media_type="application/octet-stream",
            artifact_kind="stage-output",
        )
    payload = {
        "stage_id": "target-code-generation",
        "stage_version": "1.0.0",
        "output_artifacts": [output],
        "required_outputs": [output],
    }
    before_cas = cas.accounting()
    before_idempotency = store.query_one("SELECT COUNT(*) FROM idempotency_records")

    denied = plane.handle(
        Request(
            "PUT",
            f"/cache/actions/{KEY[7:]}",
            payload,
            {"Idempotency-Key": "foreign-action-output"},
        )
    )

    assert denied.status == 404
    assert denied.json()["code"] == "NOT_FOUND"
    assert cas.accounting() == before_cas
    assert store.query_one("SELECT COUNT(*) FROM idempotency_records") == before_idempotency
    assert store.get_action_entry(TENANT, plane.trust_namespace, KEY) is None


def test_run_creation_and_retrieval(plane: CacheControlPlane) -> None:
    payload = {
        "run_id": "run-api-1",
        "project_id": "project-test",
        "source_snapshot": digest("1"),
        "snapshot_manifest": digest("2"),
    }
    created = plane.handle(Request("POST", "/runs", payload, {"Idempotency-Key": "run-1"}))
    assert created.status == 201
    fetched = plane.handle(Request("GET", "/runs/run-api-1"))
    assert fetched.json()["status"] == "PENDING"


def test_global_run_and_staged_ids_are_tenant_scoped_before_idempotency(
    plane: CacheControlPlane,
    store: SqliteMetadataStore,
    run: str,
) -> None:
    foreign_run, foreign_staged = create_foreign_run_and_staged_file(store)
    with store.transaction():
        foreign_plan = store.create_gc_plan(
            OTHER_TENANT,
            {"candidates": [], "protected": [], "created_at": 0.0, "quota_pressure": 0.0},
        )
    before_idempotency = store.query_one("SELECT COUNT(*) FROM idempotency_records")

    collision = plane.handle(
        Request(
            "POST",
            "/runs",
            {
                "run_id": foreign_run,
                "project_id": "project-other",
                "source_snapshot": digest("3"),
            },
            {"Idempotency-Key": "foreign-run-create"},
        )
    )

    foreign_get = plane.handle(Request("GET", f"/runs/{foreign_run}"))
    absent_get = plane.handle(Request("GET", "/runs/run-absent"))
    denied = [
        plane.handle(
            Request(
                "POST",
                f"/runs/{foreign_run}/resume",
                {"expected_version": 0},
                {"Idempotency-Key": "foreign-resume"},
            )
        ),
        plane.handle(
            Request(
                "POST",
                f"/runs/{foreign_run}/staged-files",
                {
                    "node_id": "foreign-node",
                    "attempt": 1,
                    "logical_path": "denied.txt",
                    "lease_epoch": 1,
                },
                {"Idempotency-Key": "foreign-reserve"},
            )
        ),
        plane.handle(
            Request(
                "POST",
                f"/runs/{run}/staged-files/{foreign_staged}/start",
                {},
                {"Idempotency-Key": "foreign-staged"},
            )
        ),
        plane.handle(
            Request(
                "POST",
                f"/runs/{foreign_run}/publish",
                {},
                {"Idempotency-Key": "foreign-publish"},
            )
        ),
        plane.handle(
            Request(
                "POST",
                f"/gc/plans/{foreign_plan}/apply",
                {"confirm": True},
                {"Idempotency-Key": "foreign-gc-plan"},
            )
        ),
    ]

    assert foreign_get.status == absent_get.status == 404
    assert foreign_get.json() == absent_get.json()
    assert collision.status == 409
    assert collision.json() == {
        "code": "CONFLICT",
        "message": "run identifier is unavailable",
        "details": {},
    }
    assert all(response.status == 404 for response in denied)
    assert all(response.json()["code"] == "NOT_FOUND" for response in denied)
    assert all(response.json()["details"] == {} for response in denied)
    assert store.query_one("SELECT COUNT(*) FROM idempotency_records") == before_idempotency
    assert store.get_staged_file(foreign_staged).status is StagedFileStatus.RESERVED
    assert store.get_gc_plan(foreign_plan)["status"] == "DRY_RUN"  # type: ignore[index]


def test_resume_requires_the_expected_version(plane: CacheControlPlane, run: str) -> None:
    stale = plane.handle(
        Request("POST", f"/runs/{run}/resume", {"expected_version": 99}, {"Idempotency-Key": "r1"})
    )
    assert stale.status == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"


def test_staged_file_lifecycle_over_the_api(
    plane: CacheControlPlane,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    cas: ContentAddressableStore,
    run: str,
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    reserved = plane.handle(
        Request(
            "POST",
            f"/runs/{run}/staged-files",
            {"node_id": "gen", "attempt": 1, "logical_path": "src/App.cs", "lease_epoch": lease.epoch},
            {"Idempotency-Key": "reserve-1"},
        )
    )
    assert reserved.status == 201
    staged_id = reserved.json()["staged_file_id"]

    started = plane.handle(
        Request("POST", f"/runs/{run}/staged-files/{staged_id}/start", {}, {"Idempotency-Key": "start-1"})
    )
    assert "upload_token" in started.json()

    content = cas.put_bytes(b"class App {}")
    with store.transaction():
        store.register_artifact(
            TENANT,
            content,
            size_bytes=len(b"class App {}"),
            media_type="application/octet-stream",
            artifact_kind="stage-output",
        )
    sealed = plane.handle(
        Request(
            "POST",
            f"/runs/{run}/staged-files/{staged_id}/seal",
            {"content_digest": content, "lease_epoch": lease.epoch},
            {"Idempotency-Key": "seal-1"},
        )
    )
    assert sealed.json()["status"] == "SEALED"

    promoted = plane.handle(
        Request("POST", f"/runs/{run}/staged-files/{staged_id}/promote", {}, {"Idempotency-Key": "promote-1"})
    )
    assert promoted.json()["status"] == "CAS_PROMOTED"
    assert promoted.json()["artifact_digest"] == content


def test_seal_cannot_read_a_content_digest_owned_only_by_another_tenant(
    plane: CacheControlPlane,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    cas: ContentAddressableStore,
    run: str,
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    reserved = plane.handle(
        Request(
            "POST",
            f"/runs/{run}/staged-files",
            {
                "node_id": "gen",
                "attempt": 1,
                "logical_path": "foreign-content.txt",
                "lease_epoch": lease.epoch,
            },
            {"Idempotency-Key": "reserve-foreign-content"},
        )
    )
    staged_id = reserved.json()["staged_file_id"]
    foreign = cas.put_bytes(b"foreign content")
    with store.transaction():
        store.register_artifact(
            OTHER_TENANT,
            foreign,
            size_bytes=len(b"foreign content"),
            media_type="application/octet-stream",
            artifact_kind="blob",
        )
    before_cas = cas.accounting()
    before_idempotency = store.query_one("SELECT COUNT(*) FROM idempotency_records")

    denied = plane.handle(
        Request(
            "POST",
            f"/runs/{run}/staged-files/{staged_id}/seal",
            {"content_digest": foreign, "lease_epoch": lease.epoch},
            {"Idempotency-Key": "seal-foreign-content"},
        )
    )

    assert denied.status == 404
    assert denied.json()["code"] == "NOT_FOUND"
    assert cas.accounting() == before_cas
    assert store.query_one("SELECT COUNT(*) FROM idempotency_records") == before_idempotency
    assert store.get_staged_file(staged_id).status is StagedFileStatus.RESERVED
    assert store.get_artifact(TENANT, foreign) is None


def test_gc_is_dry_run_by_default_and_requires_confirmation(plane: CacheControlPlane) -> None:
    plan = plane.handle(Request("POST", "/gc/plans", {}, {"Idempotency-Key": "gc-plan"}))
    assert plan.status == 201
    assert plan.json()["dry_run"] is True
    plan_id = plan.json()["plan_id"]

    refused = plane.handle(
        Request("POST", f"/gc/plans/{plan_id}/apply", {}, {"Idempotency-Key": "gc-apply"})
    )
    assert refused.status == 400
    assert refused.json()["code"] == "CONFIRMATION_REQUIRED"


def test_pagination_is_stable_and_bounded(
    plane: CacheControlPlane,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    workspace: Workspace,
    run: str,
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        for index in range(5):
            workspace.reserve("gen", 1, f"src/File{index}.cs", lease.epoch)

    first = plane.handle(Request("GET", f"/runs/{run}/staged-files", query={"limit": "2"}))
    page = first.json()
    assert len(page["items"]) == 2 and page["total"] == 5
    second = plane.handle(
        Request("GET", f"/runs/{run}/staged-files", query={"limit": "2", "cursor": page["next_cursor"]})
    )
    assert {item["staged_file_id"] for item in page["items"]} & {
        item["staged_file_id"] for item in second.json()["items"]
    } == set()


def test_unknown_route_is_a_typed_error(plane: CacheControlPlane) -> None:
    response = plane.handle(Request("GET", "/nonexistent"))
    assert response.status == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_status_endpoint_reports_health(plane: CacheControlPlane) -> None:
    body = plane.handle(Request("GET", "/status")).json()
    assert body["api_version"] == "v1"
    assert "cas" in body and "action_cache" in body
    assert not any(body["cache_parity"]["serving"].values())
    assert body["cache_parity"]["wiring"]["control_plane_authorizer"] == "NOT_WIRED"


def test_default_control_plane_denies_unwired_serving_routes(
    plane: CacheControlPlane,
) -> None:
    environment = plane.handle(
        Request(
            "GET",
            f"/cache/environments/{digest('a')}",
            query={"projectId": "project-a"},
        )
    )
    affinity = plane.handle(
        Request(
            "POST",
            "/cache/affinity/decide",
            {"project_id": "project-a"},
            {"Idempotency-Key": "unwired-affinity"},
        )
    )

    assert environment.status == 403
    assert affinity.status == 403
    assert environment.json()["details"]["state"] == "NOT_WIRED"
    assert affinity.json()["details"]["state"] == "NOT_WIRED"


def test_wsgi_adapter_serialises_json(plane: CacheControlPlane) -> None:
    application = wsgi_app(plane)
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = dict(headers)

    import io

    body = b"".join(
        application(
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/status",
                "QUERY_STRING": "",
                "wsgi.input": io.BytesIO(b""),
                "CONTENT_LENGTH": "0",
                AUTHENTICATED_CONTEXT_ENVIRON_KEY: HTTP_CONTEXT,
            },
            start_response,
        )
    )
    assert captured["status"].startswith("200")  # type: ignore[union-attr]
    assert json.loads(body)["api_version"] == "v1"


def test_wsgi_rejects_an_oversized_body_before_reading_it(
    plane: CacheControlPlane,
) -> None:
    import io

    application = wsgi_app(plane)
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(
        application(
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/cache/prompt-prefixes/compile",
                "QUERY_STRING": "",
                "wsgi.input": io.BytesIO(b"must-not-be-read"),
                "CONTENT_LENGTH": str(MAX_REQUEST_BODY_BYTES + 1),
                AUTHENTICATED_CONTEXT_ENVIRON_KEY: HTTP_CONTEXT,
            },
            start_response,
        )
    )
    assert str(captured["status"]).startswith("413")
    assert json.loads(body)["code"] == "REQUEST_TOO_LARGE"


def test_wsgi_rejects_missing_or_cross_tenant_trusted_context(
    plane: CacheControlPlane,
) -> None:
    import io

    application = wsgi_app(plane)

    def invoke(extra: dict[str, object]) -> tuple[str, dict[str, object]]:
        captured: dict[str, object] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            captured["status"] = status
            captured["headers"] = dict(headers)

        payload = b"".join(
            application(
                {
                    "REQUEST_METHOD": "GET",
                    "PATH_INFO": "/status",
                    "QUERY_STRING": "",
                    "wsgi.input": io.BytesIO(b""),
                    "CONTENT_LENGTH": "0",
                    # HTTP headers cannot manufacture the trusted environ object.
                    "HTTP_AUTHORIZATION": "Bearer attacker-controlled",
                    **extra,
                },
                start_response,
            )
        )
        decoded = json.loads(payload)
        assert isinstance(decoded, dict)
        return str(captured["status"]), decoded

    missing_status, missing = invoke({})
    assert missing_status.startswith("401")
    assert missing["code"] == "AUTHENTICATION_REQUIRED"

    wrong_status, wrong = invoke(
        {
            AUTHENTICATED_CONTEXT_ENVIRON_KEY: AuthenticatedHttpContext(
                "tenant-other",
                digest("8"),
            )
        }
    )
    assert wrong_status.startswith("403")
    assert wrong["code"] == "PERMISSION_DENIED"


def test_wsgi_authentication_denials_have_zero_metadata_and_cas_side_effects(
    plane: CacheControlPlane,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
) -> None:
    import io

    from elmos_build_cache.canonical import sha256_bytes

    application = wsgi_app(plane)
    body = b"must not be stored"
    path = f"/blobs/{sha256_bytes(body)}"
    before_cas = cas.accounting()
    before_artifacts = store.query_one("SELECT COUNT(*) FROM artifacts")
    before_idempotency = store.query_one("SELECT COUNT(*) FROM idempotency_records")

    def invoke(context: object | None) -> tuple[str, dict[str, object]]:
        captured: dict[str, object] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            captured["status"] = status
            captured["headers"] = dict(headers)

        environ: dict[str, object] = {
            "REQUEST_METHOD": "PUT",
            "PATH_INFO": path,
            "QUERY_STRING": "",
            "wsgi.input": io.BytesIO(body),
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/octet-stream",
            "HTTP_IDEMPOTENCY_KEY": "denied-upload",
        }
        if context is not None:
            environ[AUTHENTICATED_CONTEXT_ENVIRON_KEY] = context
        raw = b"".join(application(environ, start_response))
        decoded = json.loads(raw)
        assert isinstance(decoded, dict)
        return str(captured["status"]), decoded

    anonymous_status, anonymous = invoke(None)
    foreign_status, foreign = invoke(
        AuthenticatedHttpContext(OTHER_TENANT, digest("8"))
    )

    assert anonymous_status.startswith("401")
    assert anonymous["code"] == "AUTHENTICATION_REQUIRED"
    assert foreign_status.startswith("403")
    assert foreign["code"] == "PERMISSION_DENIED"
    assert cas.accounting() == before_cas
    assert store.query_one("SELECT COUNT(*) FROM artifacts") == before_artifacts
    assert store.query_one("SELECT COUNT(*) FROM idempotency_records") == before_idempotency


def test_openapi_document_declares_every_implemented_operation() -> None:
    from elmos_build_cache.schemas import SCHEMA_DIR

    openapi = SCHEMA_DIR.parent / "openapi" / "cache-control-plane.openapi.yaml"
    text = openapi.read_text(encoding="utf-8")
    assert "security:\n  - gatewayMutualTLS: []" in text
    assert "type: mutualTLS" in text
    for operation in (
        "lookupAction",
        "commitAction",
        "blobExists",
        "putBlob",
        "getBlob",
        "createRun",
        "getRun",
        "resumeRun",
        "reserveStagedFile",
        "startStagedFileWrite",
        "sealStagedFile",
        "promoteStagedFile",
        "commitCheckpoint",
        "publishTree",
    ):
        assert operation in text
