"""Complete workspace provider API over local and production sandboxes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol

from .artifacts import ContentAddressedStore
from .errors import ContractViolation, CorruptState, IdempotencyConflict, NotConfigured, TenantIsolationError
from .models import ArtifactRef, Identity, canonical_json, digest_of, new_id
from .sandbox import ProductionSandboxProvider, SandboxHandle, SandboxStats
from .workspace import LocalWorkspaceProvider, WorkspaceLease


@dataclass(frozen=True, slots=True)
class FileRange:
    start: int = 0
    length: int | None = None

    def __post_init__(self) -> None:
        if self.start < 0 or (self.length is not None and self.length < 0):
            raise ContractViolation("workspace file range is invalid")


@dataclass(frozen=True, slots=True)
class FileWriteResult:
    path: str
    previous_digest: str | None
    digest: str
    size_bytes: int
    changed: bool


@dataclass(frozen=True, slots=True)
class PatchOperation:
    operation: str
    path: str
    content: ArtifactRef | None = None
    expected_digest: str | None = None
    destination: str | None = None

    def __post_init__(self) -> None:
        if self.operation not in {"create", "replace", "delete", "move"}:
            raise ContractViolation("workspace patch operation is invalid")
        _safe_relative(self.path)
        if self.destination is not None:
            _safe_relative(self.destination)
        if self.operation in {"create", "replace"} and self.content is None:
            raise ContractViolation("workspace patch content is required")
        if self.operation == "move" and self.destination is None:
            raise ContractViolation("workspace move destination is required")


@dataclass(frozen=True, slots=True)
class PatchSet:
    operations: tuple[PatchOperation, ...]
    idempotency_key: str

    def __post_init__(self) -> None:
        if not self.operations or not self.idempotency_key:
            raise ContractViolation("workspace patch set requires operations and idempotency")


@dataclass(frozen=True, slots=True)
class PatchResult:
    changed_paths: tuple[str, ...]
    before_digest: str
    after_digest: str
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class GitOperation:
    operation: str
    args: tuple[str, ...] = ()
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        allowed = {"status", "diff", "rev_parse", "add", "commit", "branch", "merge", "fetch", "push"}
        if self.operation not in allowed or any("\x00" in item for item in self.args):
            raise ContractViolation("workspace git operation is invalid")
        _validate_git_args(self.operation, self.args)
        if self.operation in {"add", "commit", "branch", "merge", "fetch", "push"} and not self.idempotency_key:
            raise ContractViolation("mutating/network git operation requires idempotency")


@dataclass(frozen=True, slots=True)
class GitResult:
    exit_code: int
    stdout: str
    stderr: str
    head_before: str | None
    head_after: str | None
    changed: bool


@dataclass(frozen=True, slots=True)
class PortSpec:
    port: int
    protocol: str = "http"
    audience: str = "tenant-authenticated"
    ttl_seconds: int = 600
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535 or self.protocol not in {"http", "https", "tcp"} or self.audience not in {"loopback", "tenant-authenticated"} or not 1 <= self.ttl_seconds <= 3600 or not self.idempotency_key:
            raise ContractViolation("workspace port exposure is invalid")


@dataclass(frozen=True, slots=True)
class EndpointRef:
    endpoint_id: str
    url: str
    audience: str
    expires_at: float
    auth_reference: str | None


@dataclass(frozen=True, slots=True)
class ResourceStats:
    cpu_seconds: float
    memory_bytes: int
    disk_bytes: int
    pids: int
    sampled_at: float


class WorkspaceApi(Protocol):
    def read_file(self, identity: Identity, path: str, file_range: FileRange | None = None) -> ArtifactRef: ...
    def write_file(self, identity: Identity, path: str, content: ArtifactRef, *, idempotency_key: str, expected_digest: str | None = None) -> FileWriteResult: ...
    def apply_patch(self, identity: Identity, patch: PatchSet) -> PatchResult: ...
    def git(self, identity: Identity, operation: GitOperation) -> GitResult: ...
    def expose_port(self, identity: Identity, spec: PortSpec) -> EndpointRef: ...
    def stats(self, identity: Identity) -> ResourceStats: ...
    def destroy(self, identity: Identity) -> None: ...


class WorkspaceMutationStore:
    def __init__(self, database: str = ":memory:") -> None:
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("CREATE TABLE IF NOT EXISTS workspace_mutations(tenant_id TEXT NOT NULL,workspace_id TEXT NOT NULL,idempotency_key TEXT NOT NULL,request_digest TEXT NOT NULL,result_json TEXT NOT NULL,PRIMARY KEY(tenant_id,workspace_id,idempotency_key))")
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def get(self, tenant_id: str, workspace_id: str, key: str, request_digest: str) -> Mapping[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT request_digest,result_json FROM workspace_mutations WHERE tenant_id=? AND workspace_id=? AND idempotency_key=?", (tenant_id, workspace_id, key)).fetchone()
        if row is None:
            return None
        if row["request_digest"] != request_digest:
            raise IdempotencyConflict("workspace mutation key was reused with another request")
        value = json.loads(row["result_json"])
        if not isinstance(value, Mapping):
            raise ContractViolation("workspace mutation result is corrupt")
        return dict(value)

    def put(self, tenant_id: str, workspace_id: str, key: str, request_digest: str, result: Mapping[str, Any]) -> None:
        encoded = canonical_json(dict(result))
        with self._lock:
            try:
                self._connection.execute("INSERT INTO workspace_mutations VALUES(?,?,?,?,?)", (tenant_id, workspace_id, key, request_digest, encoded))
            except sqlite3.IntegrityError:
                row = self._connection.execute("SELECT request_digest,result_json FROM workspace_mutations WHERE tenant_id=? AND workspace_id=? AND idempotency_key=?", (tenant_id, workspace_id, key)).fetchone()
                if row is None:
                    raise
                if row["request_digest"] != request_digest:
                    raise IdempotencyConflict("workspace mutation key was reused with another request")
                if row["result_json"] != encoded:
                    raise CorruptState("workspace mutation produced conflicting results")


class LocalWorkspaceApi:
    def __init__(self, provider: LocalWorkspaceProvider, lease: WorkspaceLease, artifacts: ContentAddressedStore, mutations: WorkspaceMutationStore) -> None:
        self.provider, self.lease, self.artifacts, self.mutations = provider, lease, artifacts, mutations

    def read_file(self, identity: Identity, path: str, file_range: FileRange | None = None) -> ArtifactRef:
        root = self._root(identity)
        target = _local_path(root, path)
        if not target.is_file() or target.is_symlink():
            raise FileNotFoundError(path)
        data = target.read_bytes()
        selected = file_range or FileRange()
        data = data[selected.start:] if selected.length is None else data[selected.start : selected.start + selected.length]
        return self.artifacts.put(identity.tenant_id, data, kind="workspace-file")

    def write_file(self, identity: Identity, path: str, content: ArtifactRef, *, idempotency_key: str, expected_digest: str | None = None) -> FileWriteResult:
        root = self._root(identity)
        target = _local_path(root, path)
        request_digest = digest_of({"operation": "write", "path": path, "content": content.as_dict(), "expected": expected_digest})
        previous = self.mutations.get(identity.tenant_id, self.lease.workspace_id, idempotency_key, request_digest)
        if previous is not None:
            return FileWriteResult(**previous)
        old_state = _file_state(target)
        old_data = None if old_state is None else old_state[0]
        old_digest = None if old_data is None else digest_of_bytes(old_data)
        if expected_digest is not None and old_digest != expected_digest:
            raise ContractViolation("workspace file compare-and-swap digest mismatch")
        data = self.artifacts.get(identity.tenant_id, content)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name("." + target.name + ".pending-" + new_id())
        try:
            temporary.write_bytes(data)
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
            result = FileWriteResult(path, old_digest, digest_of_bytes(data), len(data), old_data != data)
            self.mutations.put(identity.tenant_id, self.lease.workspace_id, idempotency_key, request_digest, asdict(result))
        except Exception:
            _restore_file(target, old_state)
            raise
        finally:
            temporary.unlink(missing_ok=True)
        return result

    def apply_patch(self, identity: Identity, patch: PatchSet) -> PatchResult:
        root = self._root(identity)
        request_digest = digest_of({"operations": [_patch_dict(item) for item in patch.operations]})
        previous = self.mutations.get(identity.tenant_id, self.lease.workspace_id, patch.idempotency_key, request_digest)
        if previous is not None:
            return PatchResult(**{**previous, "changed_paths": tuple(previous["changed_paths"])})
        before = _tree_digest(root)
        touched = [operation.path for operation in patch.operations]
        touched.extend(operation.destination for operation in patch.operations if operation.destination is not None)
        if len(touched) != len(set(touched)):
            raise ContractViolation("workspace patch paths must not overlap")
        pure_paths = [PurePosixPath(value) for value in touched]
        if any(left in right.parents or right in left.parents for index, left in enumerate(pure_paths) for right in pure_paths[index + 1 :]):
            raise ContractViolation("workspace patch cannot mix parent and child targets")
        prepared_content: dict[str, bytes] = {}
        # Validate every precondition before applying the first operation.
        for operation in patch.operations:
            target = _local_path(root, operation.path)
            actual = digest_of_bytes(target.read_bytes()) if target.is_file() and not target.is_symlink() else None
            if operation.expected_digest is not None and operation.expected_digest != actual:
                raise ContractViolation("workspace patch precondition mismatch: " + operation.path)
            if operation.operation == "create" and target.exists():
                raise ContractViolation("workspace patch create target already exists")
            if operation.operation in {"replace", "delete", "move"} and not target.is_file():
                raise ContractViolation("workspace patch source is not a regular file: " + operation.path)
            if operation.operation in {"create", "replace"}:
                assert operation.content is not None
                prepared_content[operation.path] = self.artifacts.get(identity.tenant_id, operation.content)
            if operation.operation == "move":
                assert operation.destination is not None
                if _local_path(root, operation.destination).exists():
                    raise ContractViolation("workspace move destination already exists")
        originals = {_safe_relative(value): _file_state(_local_path(root, value)) for value in touched}
        changed: list[str] = []
        try:
            for operation in patch.operations:
                target = _local_path(root, operation.path)
                if operation.operation in {"create", "replace"}:
                    _replace_file(target, prepared_content[operation.path])
                elif operation.operation == "delete":
                    target.unlink()
                else:
                    assert operation.destination is not None
                    destination = _local_path(root, operation.destination)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(target, destination)
                    changed.append(operation.destination)
                changed.append(operation.path)
            after = _tree_digest(root)
            receipt = digest_of({"before": before, "after": after, "changed": sorted(set(changed)), "request": request_digest})
            result = PatchResult(tuple(sorted(set(changed))), before, after, receipt)
            self.mutations.put(identity.tenant_id, self.lease.workspace_id, patch.idempotency_key, request_digest, {**asdict(result), "changed_paths": list(result.changed_paths)})
        except Exception:
            try:
                for relative in sorted(originals, key=lambda value: len(PurePosixPath(value).parts), reverse=True):
                    _restore_file(_local_path(root, relative), originals[relative])
            except Exception as rollback_error:
                raise CorruptState("workspace patch failed and rollback could not restore the original tree") from rollback_error
            raise
        return result

    def git(self, identity: Identity, operation: GitOperation) -> GitResult:
        root = self._root(identity) / "source"
        mutating = operation.idempotency_key is not None
        request_digest = digest_of({"operation": operation.operation, "args": operation.args})
        if mutating:
            previous = self.mutations.get(identity.tenant_id, self.lease.workspace_id, operation.idempotency_key or "", request_digest)
            if previous is not None:
                return GitResult(**previous)
        import subprocess

        head_before = _git_head(root)
        command = [
            "git", "-C", str(root),
            "-c", "core.hooksPath=/dev/null",
            "-c", "protocol.file.allow=never",
            "-c", "protocol.ext.allow=never",
            operation.operation.replace("_", "-"), *operation.args,
        ]
        completed = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120, check=False, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"})
        head_after = _git_head(root)
        result = GitResult(completed.returncode, completed.stdout[:1_048_576], completed.stderr[:1_048_576], head_before, head_after, head_before != head_after)
        if mutating:
            self.mutations.put(identity.tenant_id, self.lease.workspace_id, operation.idempotency_key or "", request_digest, asdict(result))
        return result

    def expose_port(self, identity: Identity, spec: PortSpec) -> EndpointRef:
        self._root(identity)
        if spec.audience != "loopback":
            raise NotConfigured("local provider exposes loopback endpoints only")
        request_digest = digest_of(asdict(spec))
        previous = self.mutations.get(identity.tenant_id, self.lease.workspace_id, spec.idempotency_key, request_digest)
        if previous is not None:
            return EndpointRef(**previous)
        endpoint = EndpointRef(new_id(), f"http://127.0.0.1:{spec.port}", spec.audience, time.time() + spec.ttl_seconds, None)
        self.mutations.put(identity.tenant_id, self.lease.workspace_id, spec.idempotency_key, request_digest, asdict(endpoint))
        return endpoint

    def stats(self, identity: Identity) -> ResourceStats:
        root = self._root(identity)
        disk = sum(path.stat().st_size for path in root.rglob("*") if path.is_file() and not path.is_symlink())
        return ResourceStats(0.0, 0, disk, 0, time.time())

    def destroy(self, identity: Identity) -> None:
        self._root(identity)
        self.provider.destroy(self.lease)

    def _root(self, identity: Identity) -> Path:
        if identity.scope() != self.lease.identity.scope():
            raise TenantIsolationError("workspace API identity does not match lease")
        return Path(self.lease.root).resolve()


class SandboxWorkspaceApi:
    """Workspace API delegated to a sandbox-agent control channel."""

    def __init__(self, provider: ProductionSandboxProvider, handle: SandboxHandle, artifacts: ContentAddressedStore, mutations: WorkspaceMutationStore) -> None:
        self.provider, self.handle, self.artifacts, self.mutations = provider, handle, artifacts, mutations

    def read_file(self, identity: Identity, path: str, file_range: FileRange | None = None) -> ArtifactRef:
        self._check(identity)
        backend = self._io_backend("read_file")
        selected = file_range or FileRange()
        data = backend.read_file(self.handle.backend_ref, _safe_relative(path), selected.start, selected.length)
        if not isinstance(data, bytes):
            raise ContractViolation("sandbox file channel returned non-bytes")
        return self.artifacts.put(identity.tenant_id, data, kind="workspace-file")

    def write_file(self, identity: Identity, path: str, content: ArtifactRef, *, idempotency_key: str, expected_digest: str | None = None) -> FileWriteResult:
        self._check(identity)
        safe = _safe_relative(path)
        request_digest = digest_of({"operation": "write", "path": safe, "content": content.as_dict(), "expected": expected_digest})
        previous = self.mutations.get(identity.tenant_id, self.handle.sandbox_id, idempotency_key, request_digest)
        if previous is not None:
            return FileWriteResult(**previous)
        data = self.artifacts.get(identity.tenant_id, content)
        value = self._io_backend("write_file").write_file(self.handle.backend_ref, safe, data, expected_digest, idempotency_key)
        result = FileWriteResult(safe, value.get("previous_digest"), str(value["digest"]), int(value["size_bytes"]), bool(value["changed"]))
        self.mutations.put(identity.tenant_id, self.handle.sandbox_id, idempotency_key, request_digest, asdict(result))
        return result

    def apply_patch(self, identity: Identity, patch: PatchSet) -> PatchResult:
        self._check(identity)
        body = {"operations": [_patch_dict(item) for item in patch.operations]}
        request_digest = digest_of(body)
        previous = self.mutations.get(identity.tenant_id, self.handle.sandbox_id, patch.idempotency_key, request_digest)
        if previous is not None:
            return PatchResult(tuple(previous["changed_paths"]), previous["before_digest"], previous["after_digest"], previous["receipt_digest"])
        operations = []
        for operation in patch.operations:
            row = _patch_dict(operation)
            if operation.content is not None:
                row["content_bytes"] = self.artifacts.get(identity.tenant_id, operation.content)
            operations.append(row)
        value = self._io_backend("apply_patch").apply_patch(self.handle.backend_ref, operations, patch.idempotency_key)
        result = PatchResult(tuple(value["changed_paths"]), str(value["before_digest"]), str(value["after_digest"]), str(value["receipt_digest"]))
        self.mutations.put(identity.tenant_id, self.handle.sandbox_id, patch.idempotency_key, request_digest, {**asdict(result), "changed_paths": list(result.changed_paths)})
        return result

    def git(self, identity: Identity, operation: GitOperation) -> GitResult:
        self._check(identity)
        value = self._io_backend("git").git(self.handle.backend_ref, operation.operation, list(operation.args), operation.idempotency_key)
        return GitResult(int(value["exit_code"]), str(value.get("stdout", "")), str(value.get("stderr", "")), value.get("head_before"), value.get("head_after"), bool(value.get("changed", False)))

    def expose_port(self, identity: Identity, spec: PortSpec) -> EndpointRef:
        self._check(identity)
        value = self._io_backend("expose_port").expose_port(self.handle.backend_ref, asdict(spec))
        return EndpointRef(str(value["endpoint_id"]), str(value["url"]), spec.audience, float(value["expires_at"]), value.get("auth_reference"))

    def stats(self, identity: Identity) -> ResourceStats:
        self._check(identity)
        value: SandboxStats = self.provider.stats(self.handle)
        return ResourceStats(value.cpu_seconds, value.memory_bytes, value.disk_bytes, value.pids, value.sampled_at)

    def destroy(self, identity: Identity) -> None:
        self._check(identity)
        self.provider.destroy(self.handle)

    def _check(self, identity: Identity) -> None:
        if identity.scope() != self.handle.identity.scope():
            raise TenantIsolationError("sandbox workspace API identity mismatch")
        self.provider.stats(self.handle)

    def _io_backend(self, method: str) -> Any:
        if not callable(getattr(self.provider.backend, method, None)):
            raise NotConfigured(f"sandbox backend does not implement workspace {method}")
        return self.provider.backend


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\x00" in value:
        raise ContractViolation("workspace path must be a safe relative path")
    return path.as_posix()


def _local_path(root: Path, relative: str) -> Path:
    root = root.resolve()
    target = root
    for part in PurePosixPath(_safe_relative(relative)).parts:
        target = target / part
        if target.is_symlink():
            raise TenantIsolationError("workspace path crosses a symlink")
    target = target.resolve()
    if not target.is_relative_to(root):
        raise TenantIsolationError("workspace path escapes root or crosses a symlink")
    return target


def _file_state(target: Path) -> tuple[bytes, int] | None:
    if not target.exists():
        return None
    if not target.is_file() or target.is_symlink():
        raise ContractViolation("workspace mutation target must be a regular file")
    return target.read_bytes(), target.stat().st_mode & 0o777


def _replace_file(target: Path, data: bytes, mode: int = 0o600) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name("." + target.name + ".pending-" + new_id())
    try:
        temporary.write_bytes(data)
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _restore_file(target: Path, state: tuple[bytes, int] | None) -> None:
    if state is None:
        if target.is_dir():
            raise CorruptState("rollback target unexpectedly became a directory")
        target.unlink(missing_ok=True)
        return
    data, mode = state
    _replace_file(target, data, mode)


def _patch_dict(operation: PatchOperation) -> dict[str, Any]:
    return {"operation": operation.operation, "path": operation.path, "content": None if operation.content is None else operation.content.as_dict(), "expected_digest": operation.expected_digest, "destination": operation.destination}


def _tree_digest(root: Path) -> str:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise TenantIsolationError("workspace tree contains a symlink")
        if path.is_file():
            rows.append((path.relative_to(root).as_posix(), digest_of_bytes(path.read_bytes())))
    return digest_of(rows)


def _git_head(root: Path) -> str | None:
    import subprocess

    completed = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=15, check=False, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent", "GIT_TERMINAL_PROMPT": "0"})
    return completed.stdout.strip() if completed.returncode == 0 else None


def digest_of_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _validate_git_args(operation: str, args: tuple[str, ...]) -> None:
    denied_options = (
        "--config",
        "--exec-path",
        "--ext-diff",
        "--git-dir",
        "--no-index",
        "--output",
        "--pathspec-from-file",
        "--receive-pack",
        "--repo",
        "--textconv",
        "--upload-pack",
        "--work-tree",
    )
    for argument in args:
        if len(argument.encode("utf-8")) > 16_384 or any(ord(character) < 32 and character not in {"\t"} for character in argument):
            raise ContractViolation("workspace git argument is oversized or contains control characters")
        lowered = argument.lower()
        if lowered == "-c" or any(lowered == option or lowered.startswith(option + "=") for option in denied_options):
            raise ContractViolation("workspace git argument can alter execution or escape repository scope")
        path = PurePosixPath(argument)
        if path.is_absolute() or ".." in path.parts:
            raise ContractViolation("workspace git argument contains an external path")
    if operation in {"fetch", "push"}:
        positional = [argument for argument in args if not argument.startswith("-")]
        if positional:
            remote = positional[0]
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", remote):
                raise ContractViolation("workspace network git operation requires a configured remote name")
