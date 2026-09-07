"""Tenant-scoped content-addressed artifact storage."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from .errors import CorruptState, TenantIsolationError
from .models import ArtifactRef


class ContentAddressedStore:
    """Small CAS reference implementation.

    The tenant is part of the lookup path even though the content digest is
    global. This prevents a digest learned in one tenant from becoming an
    authorization bypass in another tenant.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        tenant_id: str,
        data: bytes,
        *,
        kind: str = "artifact",
        media_type: str = "application/octet-stream",
    ) -> ArtifactRef:
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        tenant_root = self._tenant_root(tenant_id)
        tenant_root.mkdir(parents=True, exist_ok=True)
        target = tenant_root / digest.removeprefix("sha256:")
        if target.exists():
            if target.is_symlink() or target.read_bytes() != data:
                raise CorruptState("CAS digest collision or symlink detected")
        else:
            fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=tenant_root)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return ArtifactRef(tenant_id, digest, len(data), media_type, kind)

    def get(self, tenant_id: str, ref: ArtifactRef | str) -> bytes:
        digest = ref.digest if isinstance(ref, ArtifactRef) else ref
        if not digest.startswith("sha256:"):
            raise CorruptState("invalid CAS reference")
        if isinstance(ref, ArtifactRef) and ref.tenant_id != tenant_id:
            raise TenantIsolationError("artifact belongs to another tenant")
        target = self._tenant_root(tenant_id) / digest.removeprefix("sha256:")
        if not target.is_file() or target.is_symlink():
            raise FileNotFoundError(digest)
        data = target.read_bytes()
        actual = "sha256:" + hashlib.sha256(data).hexdigest()
        if actual != digest:
            raise CorruptState("CAS object failed digest verification")
        return data

    def exists(self, tenant_id: str, digest: str) -> bool:
        if not digest.startswith("sha256:"):
            return False
        target = self._tenant_root(tenant_id) / digest.removeprefix("sha256:")
        return target.is_file() and not target.is_symlink()

    def _tenant_root(self, tenant_id: str) -> Path:
        if not tenant_id or "/" in tenant_id or "\\" in tenant_id or tenant_id in {".", ".."}:
            raise TenantIsolationError("invalid tenant storage scope")
        target = (self.root / tenant_id).resolve()
        if not target.is_relative_to(self.root):
            raise TenantIsolationError("tenant storage escapes CAS root")
        return target
