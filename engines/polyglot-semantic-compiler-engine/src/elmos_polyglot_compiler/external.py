"""Host-authorized external execution primitives.

The ZIP package is never dispatched.  A host may opt in to this module with a
host-minted :class:`ExecutionAuthority` and an explicit, allowlisted
toolchain id.  Commands run in a private ephemeral directory with no shell,
no inherited environment, no network policy other than ``disabled``, bounded
input/output, and a process-group timeout.  Results are self-attested
execution observations; they are not independent verification or
certification evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Any, Mapping, Protocol, Sequence

from .contracts import (
    AuthorityError,
    ContractError,
    ExecutionAuthority,
    RuntimeRequest,
    canonical_json,
    digest_json,
    require_identifier,
    require_digest,
)


MAX_FILES = 256
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_STDIN_BYTES = 2 * 1024 * 1024
MAX_ARGUMENTS = 64
MAX_ARGUMENT_BYTES = 16 * 1024
MAX_CAPTURE_BYTES = 512 * 1024
MAX_TIMEOUT_MS = 120_000


class ExternalExecutionError(ContractError):
    """A host-authorized external execution could not be started safely."""


@dataclass(frozen=True)
class ToolchainDescriptor:
    """A repository-independent executable selected by the host registry."""

    toolchain_id: str
    executable: str
    path_entries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.toolchain_id, "toolchain.toolchain_id")
        executable = Path(self.executable)
        if not executable.is_absolute() or not executable.is_file():
            raise ExternalExecutionError("toolchain executable must be an existing absolute file")
        if executable.is_symlink() or executable.resolve() != executable or not os.access(executable, os.X_OK):
            raise ExternalExecutionError("toolchain executable must be a non-symlink executable")
        for entry in self.path_entries:
            path = Path(entry)
            if not path.is_absolute() or not path.is_dir() or path.is_symlink():
                raise ExternalExecutionError("toolchain PATH entries must be real absolute directories")


@dataclass(frozen=True)
class ExternalExecutionSpec:
    """Strict JSON request for one invocation of a registered toolchain."""

    toolchain_id: str
    argv: tuple[str, ...]
    files: Mapping[str, str]
    stdin: str
    cwd: str
    timeout_ms: int
    network_policy: str

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> "ExternalExecutionSpec":
        if not isinstance(value, Mapping):
            raise ContractError("execution_profile must be an object")
        expected = {
            "toolchain_id",
            "argv",
            "files",
            "stdin",
            "cwd",
            "timeout_ms",
            "network_policy",
        }
        if set(value) != expected:
            raise ContractError(
                "execution_profile fields differ from the exact external execution contract"
            )
        toolchain_id = require_identifier(value.get("toolchain_id"), "execution_profile.toolchain_id")
        argv_value = value.get("argv")
        if not isinstance(argv_value, list) or not argv_value or len(argv_value) > MAX_ARGUMENTS:
            raise ContractError("execution_profile.argv must be a bounded non-empty array")
        argv: list[str] = []
        for index, item in enumerate(argv_value):
            if not isinstance(item, str) or not item or "\x00" in item:
                raise ContractError(f"execution_profile.argv[{index}] is invalid")
            if len(item.encode("utf-8")) > MAX_ARGUMENT_BYTES:
                raise ContractError(f"execution_profile.argv[{index}] is oversized")
            argv.append(item)
        files_value = value.get("files")
        if not isinstance(files_value, Mapping) or len(files_value) > MAX_FILES:
            raise ContractError("execution_profile.files must be a bounded object")
        files: dict[str, str] = {}
        total_bytes = 0
        for raw_path, content in files_value.items():
            if not isinstance(raw_path, str) or not isinstance(content, str):
                raise ContractError("execution_profile.files keys and values must be strings")
            path = _safe_relative_path(raw_path, "execution_profile.files path")
            size = len(content.encode("utf-8"))
            if size > MAX_FILE_BYTES or total_bytes + size > MAX_FILES * MAX_FILE_BYTES:
                raise ContractError("execution_profile.files exceeds the local byte budget")
            total_bytes += size
            files[path] = content
        stdin = value.get("stdin")
        if not isinstance(stdin, str) or len(stdin.encode("utf-8")) > MAX_STDIN_BYTES:
            raise ContractError("execution_profile.stdin must be a bounded string")
        cwd = value.get("cwd")
        if not isinstance(cwd, str):
            raise ContractError("execution_profile.cwd must be a string")
        cwd = "." if cwd in {"", "."} else _safe_relative_path(cwd, "execution_profile.cwd")
        timeout_ms = value.get("timeout_ms")
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or not 1 <= timeout_ms <= MAX_TIMEOUT_MS:
            raise ContractError("execution_profile.timeout_ms is outside the bounded range")
        network_policy = value.get("network_policy")
        if network_policy != "disabled":
            raise ContractError("external execution requires network_policy='disabled'")
        return cls(
            toolchain_id=toolchain_id,
            argv=tuple(argv),
            files=files,
            stdin=stdin,
            cwd=cwd,
            timeout_ms=timeout_ms,
            network_policy=network_policy,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "toolchain_id": self.toolchain_id,
            "argv": list(self.argv),
            "files": dict(self.files),
            "stdin": self.stdin,
            "cwd": self.cwd,
            "timeout_ms": self.timeout_ms,
            "network_policy": self.network_policy,
        }


def _safe_relative_path(value: str, label: str) -> str:
    if not value or "\x00" in value or "\\" in value:
        raise ContractError(f"{label} is not a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ContractError(f"{label} is not a safe relative path")
    normalized = path.as_posix()
    if len(normalized.encode("utf-8")) > 512:
        raise ContractError(f"{label} is oversized")
    return normalized


@dataclass(frozen=True)
class ExternalExecutionResult:
    toolchain_id: str
    argv: tuple[str, ...]
    cwd: str
    exit_code: int | None
    timed_out: bool
    stdout: str
    stderr: str
    stdout_digest: str
    stderr_digest: str
    output_truncated: bool
    files_digest: str
    command_digest: str
    started_at_epoch_seconds: int
    finished_at_epoch_seconds: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "toolchain_id": self.toolchain_id,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "stdout_digest": self.stdout_digest,
            "stderr_digest": self.stderr_digest,
            "output_truncated": self.output_truncated,
            "files_digest": self.files_digest,
            "command_digest": self.command_digest,
            "started_at_epoch_seconds": self.started_at_epoch_seconds,
            "finished_at_epoch_seconds": self.finished_at_epoch_seconds,
        }


def _default_toolchains() -> dict[str, ToolchainDescriptor]:
    """Discover only named common compilers; caller input cannot add a binary."""

    candidates = {
        "python": ("python3",),
        "node": ("node",),
        "javac": ("javac",),
        "rustc": ("rustc",),
        "cargo": ("cargo",),
        "gcc": ("gcc",),
        "clang": ("clang",),
        "go": ("go",),
        "dotnet": ("dotnet",),
        "php": ("php",),
        "swift": ("swift",),
        "z3": ("z3",),
    }
    path_candidates = (
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        str(Path.home() / ".local/bin"),
    )
    path_entries = tuple(
        path for path in path_candidates if Path(path).is_dir() and not Path(path).is_symlink()
    )
    registry: dict[str, ToolchainDescriptor] = {}
    for toolchain_id, names in candidates.items():
        executable = next((shutil.which(name) for name in names), None)
        if executable is None:
            continue
        resolved = Path(executable).resolve()
        if resolved.is_file() and not resolved.is_symlink() and os.access(resolved, os.X_OK):
            registry[toolchain_id] = ToolchainDescriptor(
                toolchain_id=toolchain_id,
                executable=str(resolved),
                path_entries=path_entries,
            )
    return registry


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            process.kill()
        except ProcessLookupError:
            pass


def _bounded_communicate(
    process: subprocess.Popen[bytes],
    stdin: bytes,
    timeout_ms: int,
) -> tuple[bytes, bytes, bool, bool]:
    """Communicate while bounding both output streams and process lifetime."""
    selector = selectors.DefaultSelector()
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    timed_out = False
    output_truncated = False
    input_offset = 0
    stdin_fd = process.stdin.fileno() if process.stdin is not None else None
    if stdin_fd is not None:
        os.set_blocking(stdin_fd, False)
        selector.register(stdin_fd, selectors.EVENT_WRITE, "stdin")
    stdout_fd = process.stdout.fileno() if process.stdout is not None else None
    stderr_fd = process.stderr.fileno() if process.stderr is not None else None
    if stdout_fd is not None:
        os.set_blocking(stdout_fd, False)
        selector.register(stdout_fd, selectors.EVENT_READ, "stdout")
    if stderr_fd is not None:
        os.set_blocking(stderr_fd, False)
        selector.register(stderr_fd, selectors.EVENT_READ, "stderr")
    deadline = time.monotonic() + timeout_ms / 1000
    while selector.get_map():
        remaining = deadline - time.monotonic()
        if remaining <= 0 and not timed_out:
            timed_out = True
            _kill_process_group(process)
        events = selector.select(max(0.0, min(remaining, 0.1)))
        for key, _ in events:
            fd = int(key.fd)
            if key.data == "stdin":
                if input_offset >= len(stdin):
                    selector.unregister(fd)
                    os.close(fd)
                    continue
                try:
                    input_offset += os.write(fd, stdin[input_offset : input_offset + 64 * 1024])
                except (BrokenPipeError, OSError):
                    selector.unregister(fd)
                    os.close(fd)
            else:
                try:
                    chunk = os.read(fd, 64 * 1024)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(fd)
                    os.close(fd)
                    continue
                target = stdout_buffer if key.data == "stdout" else stderr_buffer
                if len(target) + len(chunk) > MAX_CAPTURE_BYTES:
                    remaining_bytes = MAX_CAPTURE_BYTES - len(target)
                    if remaining_bytes > 0:
                        target.extend(chunk[:remaining_bytes])
                    output_truncated = True
                    _kill_process_group(process)
                else:
                    target.extend(chunk)
        if stdin_fd is not None and input_offset >= len(stdin) and stdin_fd in selector.get_map():
            selector.unregister(stdin_fd)
            os.close(stdin_fd)
            stdin_fd = None
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        _kill_process_group(process)
        process.wait(timeout=2)
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
    return bytes(stdout_buffer), bytes(stderr_buffer), timed_out, output_truncated


class ProviderAdapter(Protocol):
    """Host-supplied provider boundary; implementations own credentials/network."""

    provider_id: str

    def invoke(
        self,
        request: RuntimeRequest,
        authority: ExecutionAuthority,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class ProviderRegistry:
    """Explicit provider adapters without implicit network or credential access."""

    def __init__(self, adapters: Sequence[ProviderAdapter] = ()):
        adapter_map: dict[str, ProviderAdapter] = {}
        for adapter in adapters:
            require_identifier(adapter.provider_id, "provider_id")
            if adapter.provider_id in adapter_map:
                raise ExternalExecutionError("provider adapter IDs must be unique")
            adapter_map[adapter.provider_id] = adapter
        self._adapters = adapter_map

    def invoke(
        self,
        provider_id: str,
        request: RuntimeRequest,
        authority: ExecutionAuthority,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        require_identifier(provider_id, "provider_id")
        authority.authorize_scope(request)
        if "provider-call" not in authority.allowed_effects:
            raise AuthorityError("authority does not allow provider calls")
        if f"provider:{provider_id}" not in authority.allowed_effects:
            raise AuthorityError("provider is outside host-minted authority")
        if authority.allowed_providers and provider_id not in authority.allowed_providers:
            raise AuthorityError("provider is outside authority.allowed_providers")
        adapter = self._adapters.get(provider_id)
        if adapter is None:
            raise ExternalExecutionError("provider adapter is not registered on this host")
        result = adapter.invoke(request, authority, payload)
        if not isinstance(result, Mapping):
            raise ExternalExecutionError("provider adapter returned a non-object result")
        return dict(result)


class ExternalRunner:
    """Run a parsed profile using only a host-owned toolchain registry."""

    def __init__(
        self,
        *,
        sandbox_root: Path | None = None,
        toolchains: Mapping[str, ToolchainDescriptor] | None = None,
        providers: ProviderRegistry | None = None,
    ):
        if sandbox_root is None:
            sandbox_root = Path(tempfile.gettempdir()).resolve() / "elmos-polyglot-sandboxes"
        root = Path(sandbox_root)
        if not root.is_absolute():
            raise ExternalExecutionError("sandbox root must be absolute")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.is_symlink() or not root.is_dir() or root.resolve() != root:
            raise ExternalExecutionError("sandbox root must be a real directory without symlink ancestors")
        os.chmod(root, 0o700)
        self.sandbox_root = root
        self.toolchains = dict(toolchains or _default_toolchains())
        self.providers = providers or ProviderRegistry()

    def available_toolchains(self) -> tuple[str, ...]:
        return tuple(sorted(self.toolchains))

    def run(
        self,
        profile: Mapping[str, Any],
        *,
        request: RuntimeRequest,
        authority: ExecutionAuthority,
    ) -> ExternalExecutionResult:
        spec = ExternalExecutionSpec.parse(profile)
        authority.authorize_scope(request)
        if "external-execution" not in authority.allowed_effects:
            raise AuthorityError("authority does not allow external execution")
        if (
            f"toolchain:{spec.toolchain_id}" not in authority.allowed_effects
            and spec.toolchain_id not in authority.allowed_toolchains
        ):
            raise AuthorityError("toolchain is outside host-minted authority")
        descriptor = self.toolchains.get(spec.toolchain_id)
        if descriptor is None:
            raise ExternalExecutionError(f"toolchain is unavailable: {spec.toolchain_id}")
        sandbox = Path(tempfile.mkdtemp(prefix="run-", dir=self.sandbox_root))
        os.chmod(sandbox, 0o700)
        try:
            self._write_files(sandbox, spec.files)
            cwd = sandbox if spec.cwd == "." else sandbox / spec.cwd
            cwd.mkdir(parents=True, exist_ok=True, mode=0o700)
            if cwd.is_symlink() or cwd.resolve() != cwd or not cwd.is_relative_to(sandbox):
                raise ExternalExecutionError("execution cwd escaped its private sandbox")
            command = (descriptor.executable, *spec.argv)
            started = int(time.time())
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
                env={
                    "PATH": os.pathsep.join(descriptor.path_entries),
                    "HOME": str(sandbox),
                    "TMPDIR": str(sandbox),
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PYTHONNOUSERSITE": "1",
                    "NO_PROXY": "*",
                },
            )
            stdout, stderr, timed_out, output_truncated = _bounded_communicate(
                process, spec.stdin.encode("utf-8"), spec.timeout_ms
            )
            finished = int(time.time())
            file_digests = {
                path: "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
                for path, content in sorted(spec.files.items())
            }
            return ExternalExecutionResult(
                toolchain_id=spec.toolchain_id,
                argv=spec.argv,
                cwd=spec.cwd,
                exit_code=None if timed_out else process.returncode,
                timed_out=timed_out,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                stdout_digest="sha256:" + hashlib.sha256(stdout).hexdigest(),
                stderr_digest="sha256:" + hashlib.sha256(stderr).hexdigest(),
                output_truncated=output_truncated,
                files_digest=digest_json(file_digests),
                command_digest=digest_json(
                    {
                        "toolchain_id": spec.toolchain_id,
                        "executable": descriptor.executable,
                        "argv": list(spec.argv),
                        "cwd": spec.cwd,
                        "network_policy": spec.network_policy,
                    }
                ),
                started_at_epoch_seconds=started,
                finished_at_epoch_seconds=finished,
            )
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)

    @staticmethod
    def _write_files(sandbox: Path, files: Mapping[str, str]) -> None:
        for relative, content in files.items():
            destination = sandbox / relative
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if destination.parent.resolve() != destination.parent or not destination.parent.is_relative_to(sandbox):
                raise ExternalExecutionError("execution input path escaped its private sandbox")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(destination, flags, 0o600)
            except OSError as exc:
                raise ExternalExecutionError("execution input file could not be created safely") from exc
            try:
                payload = content.encode("utf-8")
                written = os.write(descriptor, payload)
                if written != len(payload):
                    raise ExternalExecutionError("execution input file write was short")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)


def execution_subject_digest(result: ExternalExecutionResult) -> str:
    """Return the canonical digest to bind a host evidence receipt to a run."""

    return digest_json(result.to_dict())


def build_execution_receipt(
    result: ExternalExecutionResult,
    *,
    request: RuntimeRequest,
    evidence_type: str,
    producer_id: str,
    verifier_id: str,
    artifact_digest: str,
    independent: bool = False,
    expires_at_epoch_seconds: int | None = None,
) -> dict[str, Any]:
    """Build an exact receipt; host verification must still mint its digest.

    This helper deliberately does not mutate ``ExecutionAuthority`` and cannot
    turn a self-attested run into certification.  A host-side independent
    verifier must set ``independent=True``, use a distinct verifier identity,
    and add the canonical receipt digest to its subsequent authority context.
    """

    now = int(time.time())
    expiry = expires_at_epoch_seconds if expires_at_epoch_seconds is not None else now + 3600
    require_identifier(evidence_type, "evidence_type")
    require_identifier(producer_id, "producer_id")
    require_identifier(verifier_id, "verifier_id")
    require_digest(artifact_digest, "artifact_digest")
    if not isinstance(expiry, int) or expiry <= now:
        raise ContractError("evidence receipt expiry must be in the future")
    return {
        "schema_version": "1.0",
        "evidence_id": "execution-" + hashlib.sha256(canonical_json(result.to_dict())).hexdigest()[:32],
        "evidence_type": evidence_type,
        "producer_id": producer_id,
        "verifier_id": verifier_id,
        "tenant_id": request.tenant_id,
        "project_id": request.project_id,
        "revision_digest": request.revision_digest,
        "environment_authority_id": request.environment_authority_id,
        "subject_digest": execution_subject_digest(result),
        "artifact_digest": artifact_digest,
        "status": (
            "PASSED"
            if result.exit_code == 0 and not result.timed_out and not result.output_truncated
            else "FAILED"
        ),
        "independent": independent,
        "executed_at_epoch_seconds": result.started_at_epoch_seconds,
        "expires_at_epoch_seconds": expiry,
    }


__all__ = [
    "ExternalExecutionError",
    "ExternalExecutionResult",
    "ExternalExecutionSpec",
    "ExternalRunner",
    "ProviderAdapter",
    "ProviderRegistry",
    "ToolchainDescriptor",
    "build_execution_receipt",
    "execution_subject_digest",
]
