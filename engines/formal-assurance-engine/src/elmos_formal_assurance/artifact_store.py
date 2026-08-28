from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol

from .canonical import canonical_json, digest_bytes, validate_digest, validate_identifier


class ArtifactStoreError(ValueError):
    """Raised when a content-addressed artifact cannot be safely stored/read."""


class ArtifactStore(Protocol):
    """Tenant-bound immutable CAS boundary for local or provider adapters."""

    def put(
        self,
        tenant_id: str,
        data: bytes,
        *,
        media_type: str,
        retention_class: str,
    ) -> dict[str, Any]: ...

    def get(self, tenant_id: str, digest: str) -> bytes: ...

    def metadata(self, tenant_id: str, digest: str) -> dict[str, Any]: ...

    def delete(
        self,
        tenant_id: str,
        digest: str,
        *,
        retention_class: str | None = None,
        legal_hold: bool = False,
    ) -> None: ...


class ContentAddressedArtifactStore:
    """Tenant-isolated, immutable filesystem CAS for local evidence.

    The production deployment may replace this adapter with the package's
    PostgreSQL/object-store implementation.  This adapter has the same
    security contract: tenant is part of the lookup, paths are confined,
    writes are atomic, and an existing digest can never be overwritten.
    """

    def __init__(self, root: str | Path) -> None:
        raw_root = Path(root).expanduser()
        if raw_root.is_symlink():
            raise ArtifactStoreError("artifact root must not be a symlink")
        self.root = raw_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ArtifactStoreError("artifact root must be a real directory")

    def put(
        self, tenant_id: str, data: bytes, *, media_type: str, retention_class: str
    ) -> dict[str, Any]:
        validate_identifier(tenant_id, "tenantId")
        if not isinstance(data, bytes):
            raise ArtifactStoreError("artifact data must be bytes")
        if len(data) > 4 * 1024 * 1024:
            raise ArtifactStoreError("artifact exceeds local size bound")
        if not media_type or len(media_type) > 200:
            raise ArtifactStoreError("media type is invalid")
        if retention_class not in {"EPHEMERAL", "STANDARD", "AUDIT", "LEGAL_HOLD"}:
            raise ArtifactStoreError("retention class is invalid")
        digest = digest_bytes(data)
        digest_hex = digest.removeprefix("sha256:")
        directory = self._tenant_directory(tenant_id) / digest_hex[:2]
        self._check_directory(directory)
        target = directory / digest_hex
        metadata_target = directory / f"{digest_hex}.metadata.json"
        if target.exists() or target.is_symlink():
            if (
                target.is_symlink()
                or not target.is_file()
                or target.read_bytes() != data
            ):
                raise ArtifactStoreError(
                    "content-addressed path is occupied by different content"
                )
        else:
            directory.mkdir(parents=True, exist_ok=True)
            temporary = Path(
                tempfile.mkstemp(prefix=f".{digest_hex}.", dir=directory)[1]
            )
            try:
                with temporary.open("wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temporary, 0o440)
                try:
                    os.link(temporary, target)
                except FileExistsError:
                    if (
                        target.is_symlink()
                        or not target.is_file()
                        or target.read_bytes() != data
                    ):
                        raise ArtifactStoreError(
                            "content-addressed path is occupied by different content"
                        )
            finally:
                if temporary.exists() or temporary.is_symlink():
                    temporary.unlink()
        metadata = {
            "tenantId": tenant_id,
            "sha256": digest,
            "mediaType": media_type,
            "sizeBytes": len(data),
            "retentionClass": retention_class,
        }
        metadata_bytes = canonical_json(metadata) + b"\n"
        if metadata_target.exists() or metadata_target.is_symlink():
            if metadata_target.is_symlink() or not metadata_target.is_file():
                raise ArtifactStoreError("artifact metadata path is unsafe")
            if metadata_target.read_bytes() != metadata_bytes:
                raise ArtifactStoreError("artifact metadata cannot be overwritten")
        else:
            temporary_metadata = Path(
                tempfile.mkstemp(prefix=f".{digest_hex}.metadata.", dir=directory)[1]
            )
            try:
                with temporary_metadata.open("wb") as handle:
                    handle.write(metadata_bytes)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temporary_metadata, 0o440)
                try:
                    os.link(temporary_metadata, metadata_target)
                except FileExistsError:
                    if metadata_target.read_bytes() != metadata_bytes:
                        raise ArtifactStoreError("artifact metadata cannot be overwritten")
            finally:
                if temporary_metadata.exists() or temporary_metadata.is_symlink():
                    temporary_metadata.unlink()
        return {
            "uri": f"cas://{tenant_id}/{digest}",
            "sha256": digest,
            "mediaType": media_type,
            "sizeBytes": len(data),
            "immutable": True,
            "retentionClass": retention_class,
        }

    def get(self, tenant_id: str, digest: str) -> bytes:
        validate_identifier(tenant_id, "tenantId")
        canonical = validate_digest(digest, "sha256")
        digest_hex = canonical.removeprefix("sha256:")
        path = self._tenant_directory(tenant_id) / digest_hex[:2] / digest_hex
        if path.is_symlink() or not path.is_file():
            raise ArtifactStoreError("artifact is missing or unsafe")
        data = path.read_bytes()
        if digest_bytes(data) != canonical:
            raise ArtifactStoreError("artifact content digest mismatch")
        return data

    def metadata(self, tenant_id: str, digest: str) -> dict[str, Any]:
        validate_identifier(tenant_id, "tenantId")
        canonical = validate_digest(digest, "sha256")
        digest_hex = canonical.removeprefix("sha256:")
        path = self._tenant_directory(tenant_id) / digest_hex[:2] / f"{digest_hex}.metadata.json"
        if path.is_symlink() or not path.is_file():
            raise ArtifactStoreError("artifact metadata is missing or unsafe")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise ArtifactStoreError("artifact metadata is invalid") from exc
        if not isinstance(value, dict) or value.get("sha256") != canonical:
            raise ArtifactStoreError("artifact metadata digest mismatch")
        return value

    def delete(
        self,
        tenant_id: str,
        digest: str,
        *,
        retention_class: str | None = None,
        legal_hold: bool = False,
    ) -> None:
        """Apply the local retention policy; audit evidence is never deleted."""
        if legal_hold:
            raise ArtifactStoreError("legal-hold artifacts cannot be deleted")
        metadata = self.metadata(tenant_id, digest)
        actual_retention = metadata.get("retentionClass")
        if retention_class is not None and retention_class != actual_retention:
            raise ArtifactStoreError("retention class does not match artifact metadata")
        if actual_retention != "EPHEMERAL":
            raise ArtifactStoreError("only EPHEMERAL artifacts may be deleted locally")
        canonical = validate_digest(digest, "sha256")
        digest_hex = canonical.removeprefix("sha256:")
        directory = self._tenant_directory(tenant_id) / digest_hex[:2]
        content = directory / digest_hex
        metadata_path = directory / f"{digest_hex}.metadata.json"
        if content.is_symlink() or metadata_path.is_symlink():
            raise ArtifactStoreError("artifact path is unsafe")
        try:
            content.unlink()
            metadata_path.unlink()
        except FileNotFoundError as exc:
            raise ArtifactStoreError("artifact is missing") from exc

    def _tenant_directory(self, tenant_id: str) -> Path:
        """Use a digest for the filesystem segment; IDs may contain '/'."""
        tenant_digest = digest_bytes(tenant_id.encode("utf-8")).removeprefix("sha256:")
        return self.root / tenant_digest

    def _check_directory(self, path: Path) -> None:
        relative = path.relative_to(self.root)
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.exists() and (current.is_symlink() or not current.is_dir()):
                raise ArtifactStoreError(
                    f"artifact path component is unsafe: {current}"
                )


__all__ = ["ArtifactStore", "ArtifactStoreError", "ContentAddressedArtifactStore"]
