"""Fail-closed local execution controls for ETGB fixtures.

This is deliberately a defense-in-depth boundary, not a claim of container or
VM isolation.  Cases that require a real sandbox must use an external adapter;
they are reported as unavailable until that environment is attested.
"""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

try:
    import resource
except ImportError:  # pragma: no cover - resource is POSIX-only
    resource = None  # type: ignore[assignment]


class SecurityBoundaryError(RuntimeError):
    """Raised when an execution request crosses the local safety boundary."""


@dataclass(frozen=True)
class ExecutionPolicy:
    root: Path
    timeout_seconds: int
    max_output_bytes: int = 2 * 1024 * 1024
    max_cpu_seconds: int = 120
    max_memory_bytes: int = 2 * 1024 * 1024 * 1024
    max_processes: int = 128
    network: str = "deny-by-default"
    allowed_executables: tuple[str, ...] = ("java", "javac", "python", "python3")

    def __post_init__(self) -> None:
        root = self.root.resolve(strict=True)
        object.__setattr__(self, "root", root)
        if self.timeout_seconds < 1 or self.timeout_seconds > 86400:
            raise SecurityBoundaryError("timeout must be between 1 and 86400 seconds")
        if self.max_output_bytes < 1 or self.max_output_bytes > 256 * 1024 * 1024:
            raise SecurityBoundaryError("max_output_bytes must be between 1 byte and 256 MiB")
        if self.max_cpu_seconds < 1 or self.max_memory_bytes < 1 or self.max_processes < 1:
            raise SecurityBoundaryError("process resource limits must be positive")
        if self.network != "deny-by-default":
            raise SecurityBoundaryError("local process execution only supports network denial")


def resolve_within(root: Path, relative: str | Path, *, must_exist: bool = True) -> Path:
    """Resolve a package-relative path without permitting traversal."""

    candidate = (root / Path(relative)).resolve(strict=False)
    try:
        candidate.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise SecurityBoundaryError(f"path escapes execution root: {relative}") from exc
    if must_exist and not candidate.exists():
        raise SecurityBoundaryError(f"path does not exist: {relative}")
    return candidate


_FORBIDDEN_SHELL_TOKENS = frozenset({";", "|", "||", "&", ">", ">>", "<", "2>", "2>>"})
_FORBIDDEN_ARGUMENT_RE = re.compile(r"[`$]\(|\$\{|\x00|\r|\n")


def parse_command(command: str, *, allowed_executables: Iterable[str]) -> list[list[str]]:
    """Parse the legacy command field without invoking a shell.

    ``&&`` is supported only as a sequence separator for the checked-in Java
    smoke fixture.  All other shell syntax is rejected.
    """

    if not isinstance(command, str) or not command.strip():
        raise SecurityBoundaryError("command must be a non-empty string")
    if _FORBIDDEN_ARGUMENT_RE.search(command):
        raise SecurityBoundaryError("shell interpolation, NUL, or newline is forbidden")
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        raise SecurityBoundaryError(f"invalid command quoting: {exc}") from exc
    if not tokens:
        raise SecurityBoundaryError("command produced no arguments")
    commands: list[list[str]] = []
    current: list[str] = []
    allowed = frozenset(allowed_executables)
    for token in tokens + ["&&"]:
        if token == "&&":
            if not current:
                raise SecurityBoundaryError("empty command in sequence")
            executable = Path(current[0]).name
            if executable not in allowed or Path(current[0]).is_absolute():
                raise SecurityBoundaryError(f"executable is not allowlisted: {current[0]}")
            if any(part in _FORBIDDEN_SHELL_TOKENS for part in current):
                raise SecurityBoundaryError("shell operator is forbidden")
            commands.append(current)
            current = []
            continue
        if token in _FORBIDDEN_SHELL_TOKENS:
            raise SecurityBoundaryError(f"shell operator is forbidden: {token}")
        current.append(token)
    return commands


def _limit_process(policy: ExecutionPolicy) -> None:
    """Apply child limits on POSIX without mutating the parent process."""

    if resource is None:
        return
    limits = (
        (resource.RLIMIT_CPU, policy.max_cpu_seconds),
        (resource.RLIMIT_AS, policy.max_memory_bytes),
        (resource.RLIMIT_NPROC, policy.max_processes),
        (resource.RLIMIT_FSIZE, policy.max_output_bytes),
    )
    for kind, value in limits:
        try:
            resource.setrlimit(kind, (value, value))
        except (OSError, ValueError):
            # macOS/container runtimes may expose a limit as read-only. The
            # process remains shell-free and output/time bounded; callers can
            # see the local defense-in-depth attestation in the evidence.
            continue


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            process.kill()
        except ProcessLookupError:
            pass


def run_command_sequence(command: str, cwd: Path, policy: ExecutionPolicy, *, env: Mapping[str, str] | None = None) -> dict:
    """Run an allowlisted, shell-free command sequence with bounded output."""

    cwd = resolve_within(policy.root, cwd, must_exist=True)
    if not cwd.is_dir():
        raise SecurityBoundaryError(f"execution cwd is not a directory: {cwd}")
    commands = parse_command(command, allowed_executables=policy.allowed_executables)
    safe_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        "ETGB_NETWORK_POLICY": policy.network,
    }
    if env:
        for key, value in env.items():
            if not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,63}", str(key)):
                raise SecurityBoundaryError(f"invalid environment key: {key}")
            if any(word in str(key).lower() for word in ("token", "password", "secret", "authorization")):
                raise SecurityBoundaryError(f"secret-bearing environment key is forbidden: {key}")
            safe_env[str(key)] = str(value)

    started = time.monotonic()
    command_results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="etgb-process-") as temporary:
        stdout_path = Path(temporary) / "stdout"
        stderr_path = Path(temporary) / "stderr"
        for argv in commands:
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                try:
                    process = subprocess.Popen(
                        argv,
                        cwd=cwd,
                        env=safe_env,
                        stdout=stdout,
                        stderr=stderr,
                        stdin=subprocess.DEVNULL,
                        close_fds=True,
                        start_new_session=True,
                        preexec_fn=(lambda: _limit_process(policy)) if os.name == "posix" else None,
                    )
                    try:
                        process.wait(timeout=policy.timeout_seconds)
                        timed_out = False
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        _kill_process_group(process)
                        process.wait(timeout=5)
                except OSError as exc:
                    raise SecurityBoundaryError(f"unable to execute {argv[0]}: {exc}") from exc
            stdout_bytes = stdout_path.read_bytes()
            stderr_bytes = stderr_path.read_bytes()
            command_results.append({
                "argv": argv,
                "returncode": process.returncode,
                "timed_out": timed_out,
                "stdout": stdout_bytes[: policy.max_output_bytes].decode("utf-8", errors="replace"),
                "stderr": stderr_bytes[: policy.max_output_bytes].decode("utf-8", errors="replace"),
                "stdout_truncated": len(stdout_bytes) > policy.max_output_bytes,
                "stderr_truncated": len(stderr_bytes) > policy.max_output_bytes,
            })
            if timed_out or process.returncode != 0:
                break
    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "command": command,
        "cwd": str(cwd),
        "commands": command_results,
        "returncode": command_results[-1]["returncode"],
        "timed_out": any(item["timed_out"] for item in command_results),
        "duration_ms": duration_ms,
        "stdout": "".join(item["stdout"] for item in command_results),
        "stderr": "".join(item["stderr"] for item in command_results),
        "output_truncated": any(item["stdout_truncated"] or item["stderr_truncated"] for item in command_results),
    }
