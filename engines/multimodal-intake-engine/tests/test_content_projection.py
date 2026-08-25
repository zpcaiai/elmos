from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

import pytest

from elmos_multimodal_intake.canonical import canonical_digest, sha256_bytes
from elmos_multimodal_intake.content import ContentContractError, normalize_content_ir
from elmos_multimodal_intake.content_projection import ContentProjectionBridge, ContentProjectionStore
from elmos_multimodal_intake.errors import ConflictError, IntegrityError, NotFoundError, ValidationError
from elmos_multimodal_intake.models import InputAsset, TenantContext
from elmos_multimodal_intake.skill_runtime import RuntimeContext, SkillDispatcher
from elmos_multimodal_intake.store import IntakeStore, LocalCasStore


def _anchor(asset: str, digest: str, version: int = 1) -> dict:
    return {
        "asset_id": asset,
        "asset_digest": digest,
        "asset_version": version,
        "locator": {"kind": "text_range", "start_line": 1, "end_line": 2},
    }


def _runtime_context(
    tenant: TenantContext,
    *,
    key: str,
    sources: list[dict],
    package_version: str = "package-v1",
    request_id: str = "request-1",
    review_links: dict | None = None,
) -> RuntimeContext:
    binding = {"tenant_id": tenant.tenant_id, "project_id": tenant.project_id, "package_version": package_version, "sources": sources}
    capabilities = {"content_projection_package": {**binding, "verified": True, "registry_digest": "sha256:" + canonical_digest(binding)}}
    if review_links is not None:
        capabilities["human_review_links"] = {"tenant_id": tenant.tenant_id, "project_id": tenant.project_id, "links": review_links}
    return RuntimeContext(tenant.tenant_id, tenant.project_id, tenant.actor_id, request_id, "trace-1", key, {"content_projection_min_confidence": 0.8}, capabilities)


def _source_binding(source_id: str, content_digest: str, anchor: dict, version: int = 1) -> dict:
    return {"source_id": source_id, "content_digest": content_digest, "provenance_digest": "sha256:" + canonical_digest(anchor), "version": version}


def _committed_asset(
    store: IntakeStore,
    tenant: TenantContext,
    *,
    suffix: str,
    content: bytes = b"source",
) -> InputAsset:
    digest = sha256_bytes(content)
    session = store.create_session(
        tenant,
        idempotency_key=f"authority-session-{suffix}",
    )
    _, upload = store.create_upload(
        tenant,
        session_id=session.session_id,
        display_name=f"source-{suffix}.txt",
        declared_media_type="text/plain",
        expected_size=len(content),
        expected_sha256=digest,
        part_size=len(content),
        idempotency_key=f"authority-upload-{suffix}",
        request_digest=canonical_digest({"suffix": suffix, "digest": digest}),
        expires_at="2099-01-01T00:00:00+00:00",
    )
    store.record_part(
        tenant,
        upload.upload_id,
        part_number=0,
        idempotency_key=f"authority-part-{suffix}",
        byte_offset=0,
        byte_size=len(content),
        sha256=digest,
        cas_digest=digest,
    )
    return store.complete_upload(
        tenant,
        upload.upload_id,
        commit_idempotency_key=f"authority-commit-{suffix}",
        digest=digest,
        byte_size=len(content),
    )


def _skill_request(
    tenant: TenantContext,
    inputs: dict,
    *,
    key: str,
) -> dict:
    return {
        "schema_version": "1.0",
        "tenant_id": tenant.tenant_id,
        "project_id": tenant.project_id,
        "actor_id": tenant.actor_id,
        "request_id": f"request-{key}",
        "trace_id": f"trace-{key}",
        "idempotency_key": key,
        "inputs": inputs,
        "policy": {},
        "capabilities": {},
    }


def test_projection_storage_requires_absolute_non_root_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError, match="CONTENT_PROJECTION_DATABASE_INVALID"):
        ContentProjectionStore(Path("relative.sqlite3"))
    with pytest.raises(ValidationError, match="CONTENT_PROJECTION_DATABASE_INVALID"):
        ContentProjectionStore(Path(Path.cwd().anchor))
    assert not (tmp_path / "relative.sqlite3").exists()


def test_projection_storage_rejects_insecure_parent_permissions(tmp_path: Path) -> None:
    parent = tmp_path / "insecure-parent"
    parent.mkdir(mode=0o700)
    parent.chmod(0o755)
    try:
        with pytest.raises(ValidationError, match="CONTENT_PROJECTION_STORAGE_PERMISSIONS_INVALID"):
            ContentProjectionStore(parent / "content_projection.sqlite3")
        assert not (parent / "content_projection.sqlite3").exists()
    finally:
        parent.chmod(0o700)


def test_projection_storage_rejects_insecure_database_permissions(tmp_path: Path) -> None:
    database = tmp_path / "content_projection.sqlite3"
    descriptor = os.open(database, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    database.chmod(0o644)
    with pytest.raises(ValidationError, match="CONTENT_PROJECTION_DATABASE_PERMISSIONS_INVALID"):
        ContentProjectionStore(database)


def test_projection_storage_rejects_parent_and_database_symlinks(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir(mode=0o700)
    parent_link = tmp_path / "parent-link"
    parent_link.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ValidationError, match="CONTENT_PROJECTION_STORAGE_PERMISSIONS_INVALID"):
        ContentProjectionStore(parent_link / "content_projection.sqlite3")

    target = tmp_path / "target.sqlite3"
    descriptor = os.open(target, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    database_link = tmp_path / "database-link.sqlite3"
    database_link.symlink_to(target)
    with pytest.raises(ValidationError, match="CONTENT_PROJECTION_DATABASE_INVALID"):
        ContentProjectionStore(database_link)


def test_projection_store_uses_bounded_wal_and_close_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "content_projection.sqlite3"
    store = ContentProjectionStore(database)
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
    assert store._connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert store._connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert store._connection.execute("PRAGMA wal_autocheckpoint").fetchone()[0] == 1000
    store.close()
    store.close()
    with pytest.raises(sqlite3.ProgrammingError):
        store._connection.execute("SELECT 1")


def test_requirement_projection_is_exact_idempotent_and_content_minimized(tmp_path: Path) -> None:
    store = ContentProjectionStore(tmp_path / "content_projection.sqlite3")
    bridge = ContentProjectionBridge(store)
    tenant = TenantContext("tenant-a", "project-a", "actor-a")
    text = "Requirement: retain exact source anchors\nAcceptance: source digest matches"
    digest = "sha256:" + sha256_bytes(text.encode())
    anchor = _anchor("asset-a", digest)
    ctx = _runtime_context(tenant, key="requirement-once", sources=[_source_binding("source-a", digest, anchor)])
    payload = {"operation": "extract", "package_version": "package-v1", "projection_key": "requirements-main", "sources": [{"source_id": "source-a", "text": text, "anchor": anchor, "confidence": 1.0}]}
    first = bridge.handle("elmos-multimodal-requirement-extraction", ctx, payload)
    replay = bridge.handle("elmos-multimodal-requirement-extraction", ctx, payload)
    assert first["outputs"]["requirements"][0]["statement"] == "retain exact source anchors"
    assert replay["outputs"]["projection_id"] == first["outputs"]["projection_id"]
    assert replay["outputs"]["idempotent_replay"] is True
    row = store._connection.execute("SELECT * FROM projection_versions").fetchone()
    assert text not in row["source_binding_json"]
    assert text not in row["request_digest"]
    assert store._connection.execute("SELECT count(*) FROM projection_outbox").fetchone()[0] == 1
    store.close()


def test_same_idempotency_with_source_drift_fails_closed(tmp_path: Path) -> None:
    store = ContentProjectionStore(tmp_path / "content_projection.sqlite3")
    bridge = ContentProjectionBridge(store)
    tenant = TenantContext("tenant-a", "project-a", "actor-a")
    text = "Requirement: first"
    digest = "sha256:" + sha256_bytes(text.encode())
    anchor = _anchor("asset-a", digest)
    ctx = _runtime_context(tenant, key="same-key", sources=[_source_binding("source-a", digest, anchor)])
    payload = {"operation": "extract", "package_version": "package-v1", "sources": [{"source_id": "source-a", "text": text, "anchor": anchor}]}
    bridge.handle("elmos-multimodal-requirement-extraction", ctx, payload)
    changed = {**payload, "projection_key": "changed-key"}
    with pytest.raises(ConflictError, match="CONTENT_PROJECTION_IDEMPOTENCY_CONFLICT"):
        bridge.handle("elmos-multimodal-requirement-extraction", ctx, changed)
    store.close()


def test_fusion_versions_are_immutable_and_role_conflict_needs_review(tmp_path: Path) -> None:
    store = ContentProjectionStore(tmp_path / "content_projection.sqlite3")
    bridge = ContentProjectionBridge(store)
    tenant = TenantContext("tenant-a", "project-a", "actor-a")
    content = "same bytes"
    digest = "sha256:" + sha256_bytes(content.encode())
    bindings = [
        {"source_id": "asset-a", "content_digest": digest, "provenance_digest": "sha256:" + canonical_digest({"anchor_ids": ["a1"]}), "version": 1},
        {"source_id": "asset-b", "content_digest": digest, "provenance_digest": "sha256:" + canonical_digest({"anchor_ids": ["b1"]}), "version": 1},
    ]
    payload = {"operation": "fuse", "package_version": "package-v1", "projection_key": "fusion-main", "assets": [
        {"asset_id": "asset-a", "content": content, "content_digest": digest, "version": 1, "anchor_ids": ["a1"], "role": "requirement"},
        {"asset_id": "asset-b", "content": content, "content_digest": digest, "version": 1, "anchor_ids": ["b1"], "role": "design"},
    ]}
    first = bridge.handle("elmos-multi-asset-content-fusion", _runtime_context(tenant, key="fusion-v1", sources=bindings, review_links={"fusion-main": "review-item-7"}), payload)
    second = bridge.handle("elmos-multi-asset-content-fusion", _runtime_context(tenant, key="fusion-v2", request_id="request-2", sources=bindings, review_links={"fusion-main": "review-item-7"}), payload)
    assert first["state"] == "PARTIAL"
    assert first["outputs"]["review_state"] == "NEEDS_REVIEW"
    assert first["outputs"]["human_review_link"] == "review-item-7"
    assert second["outputs"]["projection_version"] == 2
    history = store.history(tenant, kind="FUSION", projection_key="fusion-main")
    assert [item["version"] for item in history] == [2, 1]
    with pytest.raises(sqlite3.IntegrityError):
        store._connection.execute("UPDATE projection_versions SET output_json='{}'")
    store.close()


def test_conflicts_remain_unresolved_and_caller_cannot_claim_approval(tmp_path: Path) -> None:
    store = ContentProjectionStore(tmp_path / "content_projection.sqlite3")
    bridge = ContentProjectionBridge(store)
    tenant = TenantContext("tenant-a", "project-a", "actor-a")
    digest_a, digest_b = "sha256:" + "a" * 64, "sha256:" + "b" * 64
    anchor_a, anchor_b = _anchor("asset-a", digest_a), _anchor("asset-b", digest_b)
    claims = [
        {"claim_id": "claim-a", "subject": "retention", "value": "30 days", "version": 1, "anchor": anchor_a, "impact_scope": ["storage"]},
        {"claim_id": "claim-b", "subject": "retention", "value": "90 days", "version": 2, "anchor": anchor_b, "impact_scope": ["storage"]},
    ]
    bindings = [
        _source_binding("claim-a", "sha256:" + canonical_digest({"subject": "retention", "value": "30 days"}), anchor_a),
        _source_binding("claim-b", "sha256:" + canonical_digest({"subject": "retention", "value": "90 days"}), anchor_b, 2),
    ]
    ctx = _runtime_context(tenant, key="conflict-v1", sources=bindings)
    result = bridge.handle("elmos-document-version-and-conflict-detection", ctx, {"operation": "detect_conflicts", "package_version": "package-v1", "projection_key": "conflicts-main", "claims": claims})
    assert result["state"] == "PARTIAL"
    assert result["outputs"]["conflicts"][0]["status"] == "UNRESOLVED"
    assert result["outputs"]["automatic_resolution_applied"] is False
    claimed = {**claims[0], "approval_state": "APPROVED"}
    blocked = bridge.handle("elmos-document-version-and-conflict-detection", _runtime_context(tenant, key="conflict-forged", sources=bindings), {"operation": "detect_conflicts", "package_version": "package-v1", "claims": [claimed, claims[1]]})
    assert blocked["code"] == "CONTENT_PROJECTION_AUTHORITY_INPUT_UNTRUSTED"
    store.close()


def test_projection_reads_and_outbox_claims_are_tenant_project_scoped(tmp_path: Path) -> None:
    store = ContentProjectionStore(tmp_path / "content_projection.sqlite3")
    bridge = ContentProjectionBridge(store)
    tenant_a = TenantContext("tenant-a", "project-a", "actor-a")
    tenant_b = TenantContext("tenant-b", "project-b", "actor-b")
    text = "Requirement: isolate tenants"
    digest = "sha256:" + sha256_bytes(text.encode())
    anchor = _anchor("asset-a", digest)
    result = bridge.handle("elmos-multimodal-requirement-extraction", _runtime_context(tenant_a, key="tenant-a-projection", sources=[_source_binding("source-a", digest, anchor)]), {"operation": "extract", "package_version": "package-v1", "sources": [{"source_id": "source-a", "text": text, "anchor": anchor}]})
    with pytest.raises(NotFoundError):
        store.get(tenant_b, result["outputs"]["projection_id"])
    assert store.claim_outbox(tenant_b, worker_token="worker-b") is None
    claimed = store.claim_outbox(tenant_a, worker_token="worker-a")
    assert claimed is not None and claimed["state"] == "CLAIMED"
    store.finish_outbox(tenant_a, event_id=claimed["event_id"], worker_token="worker-a", outcome="UNKNOWN")
    recovered = store.claim_outbox(tenant_a, worker_token="worker-a-reconcile")
    assert recovered is not None and recovered["attempt"] == 2
    store.finish_outbox(tenant_a, event_id=recovered["event_id"], worker_token="worker-a-reconcile", outcome="DELIVERED")
    store.close()


def test_public_content_ir_and_provenance_bind_exact_authoritative_asset(
    tmp_path: Path,
) -> None:
    intake_store = IntakeStore(tmp_path / "intake.sqlite3")
    projection_store = ContentProjectionStore(tmp_path / "content_projection.sqlite3")
    tenant = TenantContext("tenant-a", "project-a", "actor-a")
    intake_store.bootstrap_project(tenant)
    asset = _committed_asset(intake_store, tenant, suffix="positive")
    assert asset.sha256 is not None
    cas = LocalCasStore(tmp_path / "cas")
    cas.put_bytes(tenant.tenant_id, b"source", asset.sha256)
    anchor = {
        **_anchor(asset.asset_id, "sha256:" + asset.sha256, asset.version),
        "anchor_id": "anchor-authoritative",
    }
    bridge = ContentProjectionBridge(projection_store, intake_store, cas)
    dispatcher = SkillDispatcher()
    dispatcher.register_bridge("elmos-unified-multimodal-content-ir", bridge)
    dispatcher.register_bridge("elmos-source-anchor-and-provenance", bridge)
    try:
        content_result = dispatcher.dispatch(
            "elmos-unified-multimodal-content-ir",
            _skill_request(
                tenant,
                {
                    "operation": "normalize",
                    "document_id": "document-authoritative",
                    "blocks": [
                        {
                            "id": "block-authoritative",
                            "type": "paragraph",
                            "text": "Bound to immutable source bytes.",
                            "anchors": [anchor],
                        }
                    ],
                },
                key="authority-content-positive",
            ),
        )
        assert content_result["state"] == "SUCCEEDED"
        assert content_result["code"] == "CONTENT_IR_NORMALIZED"
        assert content_result["outputs"]["authority_state"] == "BOUND"
        assert content_result["metrics"]["authoritative_anchor_count"] == 1

        provenance_result = dispatcher.dispatch(
            "elmos-source-anchor-and-provenance",
            _skill_request(
                tenant,
                {
                    "operation": "build",
                    "anchors": [anchor],
                    "critical_item_ids": [],
                    "derivations": [],
                },
                key="authority-provenance-positive",
            ),
        )
        assert provenance_result["state"] == "SUCCEEDED"
        assert provenance_result["code"] == "PROVENANCE_COMPLETE"
        assert provenance_result["outputs"]["authority_state"] == "BOUND"
        assert provenance_result["metrics"]["authoritative_anchor_count"] == 1
    finally:
        projection_store.close()
        intake_store.close()


def test_client_reported_digest_and_cross_tenant_asset_stay_unbound(
    tmp_path: Path,
) -> None:
    intake_store = IntakeStore(tmp_path / "intake.sqlite3")
    projection_store = ContentProjectionStore(tmp_path / "content_projection.sqlite3")
    tenant_a = TenantContext("tenant-a", "project-a", "actor-a")
    tenant_b = TenantContext("tenant-b", "project-b", "actor-b")
    intake_store.bootstrap_project(tenant_a)
    intake_store.bootstrap_project(tenant_b)
    asset = _committed_asset(intake_store, tenant_a, suffix="isolation")
    assert asset.sha256 is not None
    exact_anchor = {
        **_anchor(asset.asset_id, "sha256:" + asset.sha256, asset.version),
        "anchor_id": "anchor-foreign",
    }
    bridge = ContentProjectionBridge(projection_store, intake_store)
    try:
        foreign = bridge.handle(
            "elmos-unified-multimodal-content-ir",
            _runtime_context(tenant_b, key="authority-cross-tenant", sources=[]),
            {
                "operation": "normalize",
                "blocks": [
                    {"id": "foreign-block", "type": "paragraph", "anchors": [exact_anchor]}
                ],
            },
        )
        forged_digest = bridge.handle(
            "elmos-unified-multimodal-content-ir",
            _runtime_context(tenant_a, key="authority-forged-digest", sources=[]),
            {
                "operation": "normalize",
                "blocks": [
                    {
                        "id": "forged-block",
                        "type": "paragraph",
                        "anchors": [
                            {
                                **exact_anchor,
                                "anchor_id": "anchor-forged",
                                "asset_digest": "sha256:" + "0" * 64,
                            }
                        ],
                    }
                ],
            },
        )
        for result, anchor_id in (
            (foreign, "anchor-foreign"),
            (forged_digest, "anchor-forged"),
        ):
            assert result["state"] == "PARTIAL"
            assert result["code"] == "CONTENT_IR_AUTHORITY_REQUIRED"
            assert result["outputs"]["authority_state"] == "NEEDS_REVIEW"
            assert result["outputs"]["validation"]["unbound_anchor_ids"] == [anchor_id]
            assert result["metrics"]["authoritative_anchor_count"] == 0
    finally:
        projection_store.close()
        intake_store.close()


def test_authoritative_asset_requires_present_and_digest_valid_cas_bytes(
    tmp_path: Path,
) -> None:
    intake_store = IntakeStore(tmp_path / "intake.sqlite3")
    projection_store = ContentProjectionStore(tmp_path / "content_projection.sqlite3")
    cas = LocalCasStore(tmp_path / "cas")
    tenant = TenantContext("tenant-a", "project-a", "actor-a")
    intake_store.bootstrap_project(tenant)
    asset = _committed_asset(intake_store, tenant, suffix="cas-authority")
    assert asset.sha256 is not None
    anchor = {
        **_anchor(asset.asset_id, "sha256:" + asset.sha256, asset.version),
        "anchor_id": "anchor-cas-authority",
    }
    bridge = ContentProjectionBridge(projection_store, intake_store, cas)
    try:
        missing = bridge.handle(
            "elmos-source-anchor-and-provenance",
            _runtime_context(tenant, key="authority-cas-missing", sources=[]),
            {"operation": "build", "anchors": [anchor], "derivations": []},
        )
        assert missing["state"] == "PARTIAL"
        assert missing["code"] == "PROVENANCE_AUTHORITY_REQUIRED"
        assert missing["outputs"]["unbound_anchor_ids"] == ["anchor-cas-authority"]

        cas.put_bytes(tenant.tenant_id, b"source", asset.sha256)
        cas.path_for(tenant.tenant_id, asset.sha256).write_bytes(b"tamper")
        with pytest.raises(IntegrityError, match="CAS_OBJECT_CORRUPT"):
            bridge.handle(
                "elmos-source-anchor-and-provenance",
                _runtime_context(tenant, key="authority-cas-corrupt", sources=[]),
                {"operation": "build", "anchors": [anchor], "derivations": []},
            )
    finally:
        projection_store.close()
        intake_store.close()


def test_authoritative_asset_lookup_requires_actor_read_permission(tmp_path: Path) -> None:
    intake_store = IntakeStore(tmp_path / "intake.sqlite3")
    projection_store = ContentProjectionStore(tmp_path / "content_projection.sqlite3")
    owner = TenantContext("tenant-a", "project-a", "actor-a")
    outsider = TenantContext("tenant-a", "project-a", "actor-outsider")
    intake_store.bootstrap_project(owner)
    asset = _committed_asset(intake_store, owner, suffix="actor")
    assert asset.sha256 is not None
    bridge = ContentProjectionBridge(projection_store, intake_store)
    dispatcher = SkillDispatcher()
    dispatcher.register_bridge("elmos-source-anchor-and-provenance", bridge)
    try:
        result = dispatcher.dispatch(
            "elmos-source-anchor-and-provenance",
            _skill_request(
                outsider,
                {
                    "operation": "build",
                    "anchors": [
                        {
                            **_anchor(
                                asset.asset_id,
                                "sha256:" + asset.sha256,
                                asset.version,
                            ),
                            "anchor_id": "anchor-denied",
                        }
                    ],
                    "critical_item_ids": [],
                    "derivations": [],
                },
                key="authority-actor-denied",
            )
        )
        assert result["state"] == "BLOCKED"
        assert result["code"] == "INTAKE_PROJECT_ACCESS_DENIED"
        assert result["metrics"]["http_status"] == 403
    finally:
        projection_store.close()
        intake_store.close()


@pytest.mark.parametrize(
    "locator",
    [
        {"line_start": 1, "line_end": 1},
        {"kind": "text_range", "start_line": 1},
        {"kind": "audio_time", "start_ms": 2, "end_ms": 1},
        {"kind": "pdf_region", "page": 1, "bbox": [0, 0, 0, 10]},
        {"kind": "image_region", "polygon": [[0, 0], [1, 1]]},
        {
            "kind": "code_range",
            "relative_path": "../secret.txt",
            "start_line": 1,
            "end_line": 1,
        },
        {
            "kind": "text_range",
            "start_line": 1,
            "end_line": 1,
            "unexpected": True,
        },
    ],
)
def test_source_anchor_locator_is_strict_typed_one_of(locator: dict) -> None:
    request = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "actor_id": "actor-a",
        "request_id": "request-malformed-locator",
        "inputs": {
            "blocks": [
                {
                    "id": "block-malformed",
                    "type": "paragraph",
                    "anchors": [
                        {
                            "anchor_id": "anchor-malformed",
                            "asset_id": "asset-a",
                            "asset_version": 1,
                            "asset_digest": "sha256:" + "a" * 64,
                            "locator": locator,
                        }
                    ],
                }
            ]
        },
    }
    with pytest.raises(ContentContractError):
        normalize_content_ir(request)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("asset_version", 9_007_199_254_740_992),
        ("anchor_id", 7),
    ],
)
def test_source_anchor_rejects_unsafe_integer_and_coerced_identifier(
    field: str,
    value: object,
) -> None:
    anchor = {
        "anchor_id": "anchor-strict",
        "asset_id": "asset-a",
        "asset_version": 1,
        "asset_digest": "sha256:" + "a" * 64,
        "locator": {"kind": "text_range", "start_line": 1, "end_line": 1},
    }
    anchor[field] = value
    with pytest.raises(ContentContractError):
        normalize_content_ir(
            {
                "inputs": {
                    "blocks": [
                        {"id": "block-strict", "type": "paragraph", "anchors": [anchor]}
                    ]
                }
            }
        )
