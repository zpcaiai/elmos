from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterable
from pathlib import Path

import pytest

from elmos_multimodal_intake.errors import ConflictError, IntegrityError, NotFoundError, ValidationError
from elmos_multimodal_intake.models import TenantContext
from elmos_multimodal_intake.project_package_lifecycle import ProjectPackageLifecycle, ProjectPackageLifecycleBridge
from elmos_multimodal_intake.skill_runtime import RuntimeContext
from elmos_multimodal_intake.store import IntakeStore, LocalCasStore


def _sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _part(value: bytes, number: int) -> dict[str, object]:
    return {
        "part_number": number,
        "byte_count": len(value),
        "part_digest": _sha_bytes(value),
        "data_base64": base64.b64encode(value).decode("ascii"),
    }


def _open(tmp_path: Path) -> tuple[IntakeStore, ProjectPackageLifecycle, TenantContext]:
    store = IntakeStore(tmp_path / "intake.sqlite3")
    context = TenantContext("tenant-a", "project-a", "actor-a")
    store.bootstrap_project(context)
    return store, ProjectPackageLifecycle(store, LocalCasStore(tmp_path / "cas")), context


def _entry(path: str, value: str) -> dict[str, object]:
    return {
        "path": path,
        "kind": "file",
        "byte_count": len(value.encode("utf-8")),
        "content_digest": _sha(value),
        "role": "PRIMARY",
        "model_read_allowed": True,
        "metadata": {},
    }


def _finalize(
    lifecycle: ProjectPackageLifecycle,
    context: TenantContext,
    session_id: str,
    entries: list[dict[str, object]],
) -> dict[str, object]:
    lifecycle.begin(context, {"session_id": session_id, "expected_entry_count": len(entries)})
    for chunk_index, offset in enumerate(range(0, len(entries), 2)):
        lifecycle.append(
            context,
            {"session_id": session_id, "chunk_index": chunk_index, "entries": entries[offset : offset + 2]},
        )
    return lifecycle.finalize(context, session_id)


def test_chunked_manifest_is_scoped_merkle_bound_and_cursor_paginated(tmp_path: Path) -> None:
    store, lifecycle, context = _open(tmp_path)
    try:
        status = _finalize(
            lifecycle,
            context,
            "session-1",
            [_entry("src/a.py", "a"), _entry("src/b.py", "b"), _entry("README.md", "readme")],
        )
        assert status["complete"] is True
        assert status["package_version"] == 1
        assert isinstance(status["merkle_root"], str) and len(status["merkle_root"]) == 64

        first = lifecycle.page(context, {"package_version": 1, "limit": 2})
        assert len(first["items"]) == 2
        assert first["total"] == 3
        assert first["next_cursor"] is not None
        second = lifecycle.page(
            context,
            {"package_version": 1, "limit": 2, "cursor": first["next_cursor"]},
        )
        assert len(second["items"]) == 1
        assert second["next_cursor"] is None

        other = TenantContext("tenant-b", "project-a", "actor-b")
        store.bootstrap_project(other)
        with pytest.raises(NotFoundError):
            lifecycle.status(other, "session-1")
    finally:
        store.close()


def test_partial_finalize_and_exact_old_new_diff(tmp_path: Path) -> None:
    store, lifecycle, context = _open(tmp_path)
    try:
        lifecycle.begin(context, {"session_id": "partial", "expected_entry_count": 2})
        lifecycle.append(
            context,
            {"session_id": "partial", "chunk_index": 0, "entries": [_entry("a.py", "a")]},
        )
        assert lifecycle.finalize(context, "partial")["state"] == "PARTIAL"

        _finalize(lifecycle, context, "version-1", [_entry("a.py", "a"), _entry("old.py", "old")])
        _finalize(lifecycle, context, "version-2", [_entry("a.py", "changed"), _entry("new.py", "new")])
        diff = lifecycle.diff(context, 1, 2)
        assert diff["old_version"] == 1
        assert diff["new_version"] == 2
        assert diff["added"] == ["new.py"]
        assert diff["removed"] == ["old.py"]
        assert diff["changed"] == ["a.py"]
        assert diff["exact_versions"] is True
        with pytest.raises(ValidationError):
            lifecycle.diff(context, 2, 2)
    finally:
        store.close()


def test_server_confirmed_parts_never_report_complete_early(tmp_path: Path) -> None:
    store, lifecycle, context = _open(tmp_path)
    try:
        first_bytes = b"a" * 65_536
        second_bytes = b"b" * 65_536
        whole = first_bytes + second_bytes
        lifecycle.begin(context, {"session_id": "upload", "expected_entry_count": 0})
        negotiated = lifecycle.upload(
            context,
            "negotiate",
            {
                "session_id": "upload",
                "path": "large.bin",
                "byte_count": len(whole),
                "content_digest": _sha_bytes(whole),
                "part_size": 65_536,
            },
        )
        assert negotiated["state"] == "PARTIAL"
        first = lifecycle.upload(
            context,
            "confirm_part",
            {
                "session_id": "upload",
                "path": "large.bin",
                **_part(first_bytes, 0),
            },
        )
        assert first["complete"] is False
        assert first["files"][0]["confirmed_parts"] == 1
        second = lifecycle.upload(
            context,
            "confirm_part",
            {
                "session_id": "upload",
                "path": "large.bin",
                **_part(second_bytes, 1),
            },
        )
        assert second["complete"] is True
        assert second["files"][0]["final_cas_digest"] == _sha_bytes(whole)
        assert lifecycle.cas is not None
        assert lifecycle.cas.read_bytes(context.tenant_id, _sha_bytes(whole), expected_size=len(whole)) == whole
        with pytest.raises(ConflictError):
            lifecycle.upload(
                context,
                "confirm_part",
                {
                    "session_id": "upload",
                    "path": "large.bin",
                    **_part(b"c" * 65_536, 1),
                },
            )
    finally:
        store.close()


def test_part_bytes_are_recomputed_and_last_part_size_is_exact(tmp_path: Path) -> None:
    store, lifecycle, context = _open(tmp_path)
    try:
        first_bytes = b"x" * 65_536
        last_bytes = b"tail"
        whole = first_bytes + last_bytes
        lifecycle.begin(context, {"session_id": "exact", "expected_entry_count": 0})
        lifecycle.upload(context, "negotiate", {"session_id": "exact", "path": "exact.bin", "byte_count": len(whole), "content_digest": _sha_bytes(whole), "part_size": 65_536})
        with pytest.raises(ValidationError, match="PART_DIGEST_MISMATCH"):
            lifecycle.upload(context, "confirm_part", {"session_id": "exact", "path": "exact.bin", **{**_part(first_bytes, 0), "part_digest": _sha_bytes(b"caller-lie")}})
        lifecycle.upload(context, "confirm_part", {"session_id": "exact", "path": "exact.bin", **_part(first_bytes, 0)})
        with pytest.raises(ValidationError, match="PART_SIZE_MISMATCH"):
            lifecycle.upload(context, "confirm_part", {"session_id": "exact", "path": "exact.bin", **_part(last_bytes + b"!", 1)})
        with pytest.raises(ValidationError, match="PART_BASE64_INVALID"):
            lifecycle.upload(context, "confirm_part", {"session_id": "exact", "path": "exact.bin", "part_number": 1, "byte_count": 4, "part_digest": _sha_bytes(last_bytes), "data_base64": "not base64"})
        done = lifecycle.upload(context, "confirm_part", {"session_id": "exact", "path": "exact.bin", **_part(last_bytes, 1)})
        assert done["complete"] is True
    finally:
        store.close()


def test_full_digest_mismatch_never_marks_complete(tmp_path: Path) -> None:
    store, lifecycle, context = _open(tmp_path)
    try:
        first_bytes, second_bytes = b"a" * 65_536, b"b" * 65_536
        lifecycle.begin(context, {"session_id": "bad-final", "expected_entry_count": 0})
        lifecycle.upload(context, "negotiate", {"session_id": "bad-final", "path": "bad.bin", "byte_count": 131_072, "content_digest": _sha_bytes(b"wrong"), "part_size": 65_536})
        lifecycle.upload(context, "confirm_part", {"session_id": "bad-final", "path": "bad.bin", **_part(first_bytes, 0)})
        with pytest.raises(IntegrityError) as failure:
            lifecycle.upload(context, "confirm_part", {"session_id": "bad-final", "path": "bad.bin", **_part(second_bytes, 1)})
        assert failure.value.code == "CAS_DIGEST_MISMATCH"
        status = lifecycle.upload(context, "status", {"session_id": "bad-final", "path": "bad.bin"})
        assert status["complete"] is False
        assert status["files"][0]["confirmed_parts"] == 2
        assert status["files"][0]["state"] == "PARTIAL"
    finally:
        store.close()


class _CrashAfterFinalCas(LocalCasStore):
    def __init__(self, root: Path, final_size: int) -> None:
        super().__init__(root)
        self.final_size = final_size
        self.fail_once = True

    def put_stream(self, tenant_id: str, expected_sha256: str, expected_size: int, chunks: Iterable[bytes]) -> str:
        result = super().put_stream(tenant_id, expected_sha256, expected_size, chunks)
        if expected_size == self.final_size and self.fail_once:
            self.fail_once = False
            raise RuntimeError("simulated crash after final CAS publication")
        return result


def test_crash_after_cas_publication_replays_without_duplicate_effect(tmp_path: Path) -> None:
    store = IntakeStore(tmp_path / "intake.sqlite3")
    context = TenantContext("tenant-a", "project-a", "actor-a")
    store.bootstrap_project(context)
    first_bytes, second_bytes = b"a" * 65_536, b"b" * 65_536
    whole = first_bytes + second_bytes
    cas = _CrashAfterFinalCas(tmp_path / "cas", len(whole))
    lifecycle = ProjectPackageLifecycle(store, cas)
    try:
        lifecycle.begin(context, {"session_id": "crash", "expected_entry_count": 0})
        lifecycle.upload(context, "negotiate", {"session_id": "crash", "path": "large.bin", "byte_count": len(whole), "content_digest": _sha_bytes(whole), "part_size": 65_536})
        lifecycle.upload(context, "confirm_part", {"session_id": "crash", "path": "large.bin", **_part(first_bytes, 0)})
        with pytest.raises(RuntimeError, match="simulated crash"):
            lifecycle.upload(context, "confirm_part", {"session_id": "crash", "path": "large.bin", **_part(second_bytes, 1)})
        assert lifecycle.upload(context, "status", {"session_id": "crash", "path": "large.bin"})["complete"] is False
        replay = lifecycle.upload(context, "confirm_part", {"session_id": "crash", "path": "large.bin", **_part(second_bytes, 1)})
        assert replay["complete"] is True
        assert cas.read_bytes(context.tenant_id, _sha_bytes(whole), expected_size=len(whole)) == whole
    finally:
        store.close()


def test_upload_records_are_project_scoped(tmp_path: Path) -> None:
    store, lifecycle, context = _open(tmp_path)
    try:
        lifecycle.begin(context, {"session_id": "scoped", "expected_entry_count": 0})
        lifecycle.upload(context, "negotiate", {"session_id": "scoped", "path": "file.bin", "byte_count": 0, "content_digest": _sha_bytes(b""), "part_size": 65_536})
        other_project = TenantContext(context.tenant_id, "project-b", "actor-b")
        store.bootstrap_project(other_project)
        with pytest.raises(NotFoundError):
            lifecycle.upload(other_project, "status", {"session_id": "scoped", "path": "file.bin"})
        other_tenant = TenantContext("tenant-b", context.project_id, "actor-b")
        store.bootstrap_project(other_tenant)
        with pytest.raises(NotFoundError):
            lifecycle.upload(other_tenant, "status", {"session_id": "scoped", "path": "file.bin"})
    finally:
        store.close()


def test_skill49_bridge_uses_exact_durable_diff_and_never_artifact_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = IntakeStore(tmp_path / "intake.sqlite3")
    context = TenantContext("tenant-a", "project-a", "actor-a")
    store.bootstrap_project(context)
    bridge = ProjectPackageLifecycleBridge(store, LocalCasStore(tmp_path / "cas"))
    try:
        _finalize(bridge.lifecycle, context, "v1", [_entry("old.py", "old")])
        _finalize(bridge.lifecycle, context, "v2", [_entry("new.py", "new")])

        def forbidden_fallback(*args: object, **kwargs: object) -> dict[str, object]:
            raise AssertionError("Skill49 must not use artifact fallback")

        monkeypatch.setattr(bridge.lifecycle, "artifact", forbidden_fallback)
        output = bridge.handle(
            "elmos-project-package-version-and-incremental-update",
            RuntimeContext(
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                actor_id=context.actor_id,
                request_id="request-diff",
                trace_id="trace-diff",
                idempotency_key="idem-diff",
                policy={},
                capabilities={},
            ),
            {"lifecycle_action": "diff", "old_version": 1, "new_version": 2},
        )
        assert output["state"] == "SUCCEEDED"
        assert output["outputs"]["added"] == ["new.py"]
        assert output["outputs"]["removed"] == ["old.py"]
        assert output["outputs"]["exact_versions"] is True
    finally:
        store.close()


def test_override_audit_undo_and_security_isolation(tmp_path: Path) -> None:
    store, lifecycle, context = _open(tmp_path)
    try:
        _finalize(
            lifecycle,
            context,
            "review",
            [_entry("safe.py", "safe"), _entry("unsafe.py", "unsafe")],
        )
        changed = lifecycle.override(
            context,
            {
                "package_version": 1,
                "path": "safe.py",
                "expected_override_version": 0,
                "role": "REFERENCE",
                "model_read_allowed": False,
                "reason": "reviewed",
            },
            undo=False,
        )
        undone = lifecycle.override(
            context,
            {
                "package_version": 1,
                "path": "safe.py",
                "expected_override_version": 1,
                "audit_id": changed["audit_id"],
                "reason": "revert",
            },
            undo=True,
        )
        assert undone["entry"]["role"] == "PRIMARY"
        assert undone["entry"]["model_read_allowed"] is False
        with pytest.raises(ValidationError, match="SECURITY_ISOLATION"):
            lifecycle.override(
                context,
                {
                    "package_version": 1,
                    "path": "unsafe.py",
                    "expected_override_version": 0,
                    "role": "PRIMARY",
                    "model_read_allowed": True,
                    "reason": "forbidden",
                },
                undo=False,
            )
    finally:
        store.close()


def test_artifacts_bind_package_version_and_non_python_symbols_stay_partial(tmp_path: Path) -> None:
    store, lifecycle, context = _open(tmp_path)
    try:
        _finalize(lifecycle, context, "artifacts", [_entry("src/main.ts", "export const x = 1")])
        runtime_context = RuntimeContext(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            actor_id=context.actor_id,
            request_id="request-1",
            trace_id="trace-1",
            idempotency_key="idem-1",
            policy={},
            capabilities={},
        )
        source = "export const x = 1"
        rebuilt = lifecycle.artifact(
            "elmos-repository-map-and-symbol-indexing",
            runtime_context,
            {
                "package_version": 1,
                "source_input": {
                    "languages": ["TypeScript"],
                    "files": [
                        {
                            "path": "src/main.ts",
                            "content": source,
                            "content_digest": _sha(source),
                            "source_version": "package:1",
                            "anchor": {"package_version": 1, "path": "src/main.ts"},
                        }
                    ],
                },
            },
            "rebuild",
        )
        assert rebuilt["package_version"] == 1
        assert rebuilt["state"] == "PARTIAL"
        assert rebuilt["repository_content_executed"] is False
        rolled_back = lifecycle.artifact(
            "elmos-repository-map-and-symbol-indexing",
            runtime_context,
            {"package_version": 1, "artifact_version": 1},
            "rollback",
        )
        assert rolled_back["artifact_version"] == 2
        assert rolled_back["state"] == "PARTIAL"
    finally:
        store.close()
