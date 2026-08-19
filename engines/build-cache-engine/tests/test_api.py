"""Control-plane contract tests: idempotency, digest addressing, pagination."""

from __future__ import annotations

import json

import pytest

from conftest import TENANT, claim_node, digest
from elmos_build_cache.api import CacheControlPlane, Request, wsgi_app
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.journal import RunCoordinator
from elmos_build_cache.publish import TreePublisher
from elmos_build_cache.staging import Workspace

KEY = digest("7")


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


def test_blob_upload_is_digest_addressed(plane: CacheControlPlane) -> None:
    response = plane.handle(
        Request("PUT", "/blobs/" + digest("0")[7:], b"not the declared content", {"Idempotency-Key": "x"})
    )
    assert response.status == 422
    assert response.json()["code"] == "DIGEST_MISMATCH"


def test_blob_head_get_roundtrip(plane: CacheControlPlane, cas: ContentAddressableStore) -> None:
    stored = cas.put_bytes(b"artifact bytes")
    head = plane.handle(Request("HEAD", f"/blobs/{stored[7:]}"))
    assert head.status == 200
    assert head.headers is not None and head.headers["X-Elmos-Digest"] == stored
    body = plane.handle(Request("GET", f"/blobs/{stored[7:]}"))
    assert body.body == b"artifact bytes"
    assert plane.handle(Request("HEAD", f"/blobs/{digest('f')[7:]}")).status == 404


def test_action_lookup_returns_structured_miss_reasons(plane: CacheControlPlane) -> None:
    response = plane.handle(Request("GET", f"/cache/actions/{KEY[7:]}"))
    assert response.status == 404
    assert response.json()["miss_reasons"] == ["NO_ENTRY"]


def test_action_commit_then_lookup(plane: CacheControlPlane, cas: ContentAddressableStore) -> None:
    output = cas.put_bytes(b"generated")
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
            },
            start_response,
        )
    )
    assert captured["status"].startswith("200")  # type: ignore[union-attr]
    assert json.loads(body)["api_version"] == "v1"


def test_openapi_document_declares_every_implemented_operation() -> None:
    from elmos_build_cache.schemas import SCHEMA_DIR

    openapi = SCHEMA_DIR.parent / "openapi" / "cache-control-plane.openapi.yaml"
    text = openapi.read_text(encoding="utf-8")
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
