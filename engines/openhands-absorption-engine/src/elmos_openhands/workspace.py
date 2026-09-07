"""Workspace lifecycle and sandbox provider contracts."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Protocol

from .artifacts import ContentAddressedStore
from .errors import ContractViolation, CorruptState, NotConfigured, TenantIsolationError
from .models import ArtifactRef, Identity, new_id


class IsolationClass(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class WorkspaceState(StrEnum):
    ALLOCATED = "allocated"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RELEASED = "released"
    DESTROYED = "destroyed"


@dataclass(frozen=True, slots=True)
class WorkspaceRequest:
    identity: Identity
    isolation_class: IsolationClass = IsolationClass.L0
    cpu_limit: float = 1.0
    memory_mb: int = 1024
    disk_mb: int = 2048
    allowed_egress: tuple[str, ...] = ()
    source_path: str | None = None
    image_digest: str | None = None

    def __post_init__(self) -> None:
        if self.cpu_limit <= 0 or self.memory_mb <= 0 or self.disk_mb <= 0:
            raise ContractViolation("workspace quotas must be positive")
        if self.isolation_class != IsolationClass.L0 and not self.image_digest:
            raise ContractViolation("non-local isolation requires an immutable image digest")


@dataclass(frozen=True, slots=True)
class WorkspaceLease:
    workspace_id: str
    identity: Identity
    root: str
    state: WorkspaceState
    fencing_token: str
    expires_at: float
    isolation_class: IsolationClass
    image_digest: str | None


class WorkspaceProvider(Protocol):
    def allocate(self, request: WorkspaceRequest, *, now: float | None = None) -> WorkspaceLease: ...

    def heartbeat(self, lease: WorkspaceLease, *, now: float | None = None) -> WorkspaceLease: ...

    def snapshot(self, lease: WorkspaceLease) -> ArtifactRef: ...

    def restore(self, lease: WorkspaceLease, snapshot: ArtifactRef) -> None: ...

    def release(self, lease: WorkspaceLease) -> None: ...


class LocalWorkspaceProvider:
    """Reference workspace provider for trusted L0 development and tests."""

    def __init__(
        self,
        root: str | Path,
        artifacts: ContentAddressedStore,
        *,
        lease_seconds: float = 300.0,
        database: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifacts = artifacts
        self.lease_seconds = lease_seconds
        self._leases: dict[str, WorkspaceLease] = {}
        self._connection = sqlite3.connect(
            str(database or (self.root / "workspace-leases.sqlite")),
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS workspace_leases(workspace_id TEXT PRIMARY KEY,identity_json TEXT NOT NULL,root TEXT NOT NULL,state TEXT NOT NULL,fencing_token TEXT NOT NULL,expires_at REAL NOT NULL,isolation_class TEXT NOT NULL,image_digest TEXT)"
        )

    def allocate(self, request: WorkspaceRequest, *, now: float | None = None) -> WorkspaceLease:
        if request.isolation_class != IsolationClass.L0:
            raise NotConfigured("local provider refuses non-L0 untrusted execution")
        now = time.time() if now is None else now
        workspace_id = "ws_" + new_id().replace("-", "")
        tenant_root = self.root / request.identity.tenant_id
        target = (tenant_root / workspace_id).resolve()
        if not target.is_relative_to(self.root):
            raise TenantIsolationError("workspace path escapes provider root")
        target.mkdir(parents=True, mode=0o700)
        for name in ("source", "in", "out", "tmp"):
            (target / name).mkdir(mode=0o700)
        if request.source_path is not None:
            self._copy_source(Path(request.source_path), target / "source")
        lease = WorkspaceLease(
            workspace_id,
            request.identity,
            str(target),
            WorkspaceState.ALLOCATED,
            new_id(),
            now + self.lease_seconds,
            request.isolation_class,
            request.image_digest,
        )
        self._leases[workspace_id] = lease
        self._persist(lease)
        return lease

    def activate(self, lease: WorkspaceLease, *, now: float | None = None) -> WorkspaceLease:
        self._assert_lease(lease, now)
        updated = WorkspaceLease(
            lease.workspace_id,
            lease.identity,
            lease.root,
            WorkspaceState.ACTIVE,
            lease.fencing_token,
            lease.expires_at,
            lease.isolation_class,
            lease.image_digest,
        )
        self._leases[lease.workspace_id] = updated
        self._persist(updated)
        return updated

    def heartbeat(self, lease: WorkspaceLease, *, now: float | None = None) -> WorkspaceLease:
        now = time.time() if now is None else now
        self._assert_lease(lease, now)
        updated = WorkspaceLease(
            lease.workspace_id,
            lease.identity,
            lease.root,
            lease.state,
            lease.fencing_token,
            now + self.lease_seconds,
            lease.isolation_class,
            lease.image_digest,
        )
        self._leases[lease.workspace_id] = updated
        self._persist(updated)
        return updated

    def snapshot(self, lease: WorkspaceLease) -> ArtifactRef:
        self._assert_lease(lease, time.time(), allow_expired=True)
        root = self._safe_root(lease)
        data = _deterministic_tar(root)
        return self.artifacts.put(
            lease.identity.tenant_id, data, kind="workspace-snapshot", media_type="application/x-tar"
        )

    def restore(self, lease: WorkspaceLease, snapshot: ArtifactRef) -> None:
        self._assert_lease(lease, time.time(), allow_expired=True)
        if snapshot.tenant_id != lease.identity.tenant_id:
            raise TenantIsolationError("workspace snapshot belongs to another tenant")
        root = self._safe_root(lease)
        payload = self.artifacts.get(lease.identity.tenant_id, snapshot)
        with tempfile.TemporaryDirectory(prefix="restore-") as temporary:
            staging = Path(temporary) / "staging"
            staging.mkdir(mode=0o700)
            _safe_extract(payload, staging)
            for child in root.iterdir():
                if child.name not in {"source", "in", "out", "tmp"}:
                    _remove_tree(child)
            for child in staging.iterdir():
                destination = root / child.name
                if destination.exists():
                    _remove_tree(destination)
                os.replace(child, destination)

    def release(self, lease: WorkspaceLease) -> None:
        current = self._leases.get(lease.workspace_id)
        if current is None:
            return
        if (
            current.identity.scope() != lease.identity.scope()
            or current.identity.agent_id != lease.identity.agent_id
        ):
            raise TenantIsolationError("workspace release scope mismatch")
        if current.fencing_token != lease.fencing_token:
            raise TenantIsolationError("workspace release fencing mismatch")
        if current.state == WorkspaceState.RELEASED:
            return
        self._leases[lease.workspace_id] = WorkspaceLease(
            lease.workspace_id,
            lease.identity,
            lease.root,
            WorkspaceState.RELEASED,
            lease.fencing_token,
            time.time(),
            lease.isolation_class,
            lease.image_digest,
        )
        self._persist(self._leases[lease.workspace_id])

    def destroy(self, lease: WorkspaceLease) -> None:
        current = self._leases.get(lease.workspace_id)
        if current is None:
            return
        if (
            current.identity.scope() != lease.identity.scope()
            or current.identity.agent_id != lease.identity.agent_id
        ):
            raise TenantIsolationError("workspace destroy scope mismatch")
        if current.fencing_token != lease.fencing_token:
            raise TenantIsolationError("workspace destroy fencing mismatch")
        if current.state == WorkspaceState.DESTROYED:
            return
        root = self._safe_root(lease)
        _remove_tree(root)
        self._leases[lease.workspace_id] = WorkspaceLease(
            lease.workspace_id,
            lease.identity,
            lease.root,
            WorkspaceState.DESTROYED,
            lease.fencing_token,
            time.time(),
            lease.isolation_class,
            lease.image_digest,
        )
        self._persist(self._leases[lease.workspace_id])

    def execute(
        self,
        lease: WorkspaceLease,
        command: list[str],
        *,
        timeout_seconds: float = 30.0,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self._assert_lease(lease, time.time())
        if lease.state != WorkspaceState.ACTIVE:
            raise ContractViolation("workspace must be active before execution")
        if not command or any(not isinstance(item, str) or not item for item in command):
            raise ContractViolation("command must be a non-empty argv list")
        safe_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent", **(env or {})}
        safe_env.pop("ELMOS_SECRET", None)
        return subprocess.run(
            command,
            cwd=self._safe_root(lease) / "tmp",
            env=safe_env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )

    def reap_expired(self, *, now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        rows = self._connection.execute(
            "SELECT workspace_id FROM workspace_leases WHERE expires_at<=? AND state NOT IN ('destroyed','released')",
            (now,),
        ).fetchall()
        for (workspace_id,) in rows:
            if workspace_id not in self._leases:
                loaded = self._load(workspace_id)
                if loaded is not None:
                    self._leases[workspace_id] = loaded
        expired = [
            workspace_id
            for workspace_id, lease in self._leases.items()
            if lease.expires_at <= now
            and lease.state not in {WorkspaceState.DESTROYED, WorkspaceState.RELEASED}
        ]
        for workspace_id in expired:
            self.destroy(self._leases[workspace_id])
        return expired

    def _assert_lease(self, lease: WorkspaceLease, now: float | None, *, allow_expired: bool = False) -> None:
        current = self._current(lease.workspace_id)
        now = time.time() if now is None else now
        if (
            current is None
            or current.fencing_token != lease.fencing_token
            or current.identity.scope() != lease.identity.scope()
            or current.identity.agent_id != lease.identity.agent_id
        ):
            raise TenantIsolationError("workspace fencing or tenant scope mismatch")
        if not allow_expired and current.expires_at <= now:
            raise ContractViolation("workspace lease expired")

    def _safe_root(self, lease: WorkspaceLease) -> Path:
        root = Path(lease.root).resolve()
        if not root.is_relative_to(self.root) or root.parts[-2] != lease.identity.tenant_id:
            raise TenantIsolationError("workspace root is outside tenant scope")
        return root

    def close(self) -> None:
        self._connection.close()

    def _current(self, workspace_id: str) -> WorkspaceLease | None:
        current = self._leases.get(workspace_id)
        if current is not None:
            return current
        loaded = self._load(workspace_id)
        if loaded is not None:
            self._leases[workspace_id] = loaded
        return loaded

    def _persist(self, lease: WorkspaceLease) -> None:
        identity_json = json.dumps(
            {
                "tenant_id": lease.identity.tenant_id,
                "project_id": lease.identity.project_id,
                "task_id": lease.identity.task_id,
                "run_id": lease.identity.run_id,
                "node_id": lease.identity.node_id,
                "agent_id": lease.identity.agent_id,
            },
            sort_keys=True,
        )
        self._connection.execute(
            "INSERT INTO workspace_leases VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(workspace_id) DO UPDATE SET state=excluded.state,expires_at=excluded.expires_at,fencing_token=excluded.fencing_token,root=excluded.root",
            (
                lease.workspace_id,
                identity_json,
                lease.root,
                lease.state.value,
                lease.fencing_token,
                lease.expires_at,
                lease.isolation_class.value,
                lease.image_digest,
            ),
        )

    def _load(self, workspace_id: str) -> WorkspaceLease | None:
        row = self._connection.execute(
            "SELECT * FROM workspace_leases WHERE workspace_id=?", (workspace_id,)
        ).fetchone()
        if row is None:
            return None
        identity_data = json.loads(row[1])
        identity = Identity(**identity_data)
        return WorkspaceLease(
            row[0], identity, row[2], WorkspaceState(row[3]), row[4], row[5], IsolationClass(row[6]), row[7]
        )

    @staticmethod
    def _copy_source(source: Path, target: Path) -> None:
        source = source.resolve()
        if not source.is_dir():
            raise ContractViolation("workspace source_path must be a directory")
        if source == target or target.is_relative_to(source):
            raise ContractViolation("workspace source cannot be its own destination")
        for entry in sorted(source.iterdir()):
            if entry.is_symlink():
                raise ContractViolation("symlinks are not accepted in workspace source")
            destination = target / entry.name
            if entry.is_dir():
                shutil.copytree(entry, destination, symlinks=False)
            elif entry.is_file():
                shutil.copy2(entry, destination)


class ContainerSandboxProvider:
    """Hardened container command builder; execution is opt-in and injectable."""

    def __init__(self, engine: str = "docker") -> None:
        self.engine = engine

    def build_command(self, lease: WorkspaceLease, image_digest: str, command: list[str]) -> list[str]:
        if not image_digest.startswith("sha256:") or len(image_digest) != 71:
            raise ContractViolation("sandbox image must be digest pinned")
        if lease.isolation_class not in {IsolationClass.L1, IsolationClass.L2}:
            raise NotConfigured("container provider only implements L1/L2")
        root = Path(lease.root).resolve()
        return [
            self.engine,
            "run",
            "--rm",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=512",
            "--memory=1024m",
            f"--volume={root / 'source'}:/workspace/source:ro",
            f"--volume={root / 'out'}:/workspace/out:rw",
            f"--volume={root / 'tmp'}:/workspace/tmp:rw",
            "--workdir=/workspace/source",
            f"elmos/sandbox@{image_digest}",
            *command,
        ]


def _deterministic_tar(root: Path) -> bytes:
    with tempfile.NamedTemporaryFile(prefix="snapshot-", suffix=".tar") as temporary:
        with tarfile.open(fileobj=temporary, mode="w") as archive:
            for path in sorted(root.rglob("*")):
                relative = path.relative_to(root)
                if path.is_symlink():
                    raise ContractViolation("symlink cannot enter a workspace snapshot")
                info = archive.gettarinfo(str(path), arcname=relative.as_posix())
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                if path.is_file():
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)
                else:
                    archive.addfile(info)
        temporary.flush()
        temporary.seek(0)
        return temporary.read()


def _safe_extract(payload: bytes, destination: Path) -> None:
    with tempfile.NamedTemporaryFile(prefix="snapshot-input-", suffix=".tar") as temporary:
        temporary.write(payload)
        temporary.flush()
        with tarfile.open(temporary.name, mode="r") as archive:
            for member in archive.getmembers():
                target = (destination / PurePosixPath(member.name)).resolve()
                if not target.is_relative_to(destination.resolve()):
                    raise CorruptState("snapshot member escapes restore root")
                if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                    raise CorruptState("snapshot contains unsupported link or special file")
            # Extract validated regular files explicitly.  ``extractall`` is
            # intentionally avoided: its safety depends on interpreter
            # version and it is too easy to regress the traversal boundary.
            for member in archive.getmembers():
                target = (destination / PurePosixPath(member.name)).resolve()
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                source = archive.extractfile(member)
                if source is None:
                    raise CorruptState("snapshot regular file has no readable payload")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                os.chmod(target, member.mode & 0o777)


def _remove_tree(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)
