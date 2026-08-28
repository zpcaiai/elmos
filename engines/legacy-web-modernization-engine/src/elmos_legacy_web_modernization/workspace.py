"""Private, tenant-scoped staged workspaces for idempotent change sets."""

from __future__ import annotations

import hashlib
import os
import secrets
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .canonical import canonical_bytes, canonical_digest
from .contracts import RuntimeRequest
from .transformation import TransformationError, validate_generated_files


class WorkspaceError(RuntimeError):
    pass


def safe_relative_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise WorkspaceError("workspace path must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise WorkspaceError("workspace path escapes its isolated root")
    if len(path.parts) > 64 or len(value.encode("utf-8")) > 1_024:
        raise WorkspaceError("workspace path exceeds policy limits")
    return path


class StagedWorkspaceStore:
    """Atomically materialize generated files without touching a Git checkout."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).absolute()
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise WorkspaceError("workspace store must be a real directory")

    @staticmethod
    def _scope_component(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]

    def _workspace(self, request: RuntimeRequest, change_set_id: str) -> Path:
        identity = (
            f"{request.tenant_id}/{request.project_id}/{request.job_id}/{change_set_id}"
        )
        return self.root / self._scope_component(identity)

    @staticmethod
    def _assert_real_ancestry(root: Path, destination: Path) -> None:
        try:
            destination.relative_to(root)
        except ValueError as exc:
            raise WorkspaceError("workspace destination escaped its root") from exc
        current = root
        for part in destination.relative_to(root).parts[:-1]:
            current = current / part
            if current.exists() and current.is_symlink():
                raise WorkspaceError("workspace ancestry contains a symlink")

    @staticmethod
    def _atomic_write(destination: Path, data: bytes) -> None:
        if destination.exists() and destination.is_symlink():
            raise WorkspaceError("workspace destination is a symlink")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.parent / (".staging-" + secrets.token_hex(12))
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temp, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, destination)
        finally:
            if temp.exists():
                temp.unlink()

    def materialize(
        self, request: RuntimeRequest, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        change_set_id = payload.get("changeSetId")
        digest = payload.get("digest")
        content = payload.get("content")
        if (
            not isinstance(change_set_id, str)
            or not isinstance(digest, str)
            or not isinstance(content, Mapping)
        ):
            raise WorkspaceError("change set identity, digest and content are required")
        if canonical_digest(content) != digest:
            raise WorkspaceError("change set digest does not bind its content")
        raw_files = content.get("files")
        if not isinstance(raw_files, Mapping):
            raise WorkspaceError("change set files are required")
        try:
            files = validate_generated_files(raw_files)
        except TransformationError as exc:
            raise WorkspaceError(str(exc)) from exc
        workspace = self._workspace(request, change_set_id)
        workspace.mkdir(parents=True, exist_ok=True)
        if workspace.is_symlink():
            raise WorkspaceError("workspace identity collides with a symlink")
        manifest_files: list[dict[str, Any]] = []
        for relative_value in sorted(files):
            relative = safe_relative_path(relative_value)
            destination = workspace.joinpath(*relative.parts)
            self._assert_real_ancestry(workspace, destination)
            data = files[relative_value].encode("utf-8")
            file_digest = "sha256:" + hashlib.sha256(data).hexdigest()
            if destination.exists():
                if not destination.is_file() or destination.read_bytes() != data:
                    raise WorkspaceError(
                        "idempotent materialization found divergent content"
                    )
            else:
                self._atomic_write(destination, data)
            manifest_files.append(
                {"path": relative_value, "digest": file_digest, "sizeBytes": len(data)}
            )
        manifest = {
            "changeSetId": change_set_id,
            "digest": digest,
            "scopeDigest": canonical_digest(
                {
                    "tenant": request.tenant_id,
                    "project": request.project_id,
                    "job": request.job_id,
                }
            ),
            "files": manifest_files,
            "fileCount": len(manifest_files),
            "byteCount": sum(item["sizeBytes"] for item in manifest_files),
            "commitType": "content-addressed-private-staging",
            "gitMutation": False,
            "reversible": True,
        }
        manifest_data = canonical_bytes(manifest)
        manifest_path = workspace / ".elmos-change-set.json"
        if manifest_path.exists() and manifest_path.read_bytes() != manifest_data:
            raise WorkspaceError("workspace manifest is not idempotent")
        if not manifest_path.exists():
            self._atomic_write(manifest_path, manifest_data)
        return {
            **manifest,
            "workspaceRef": "workspace://private/" + workspace.name,
            "manifestDigest": "sha256:" + hashlib.sha256(manifest_data).hexdigest(),
        }
