"""Default-deny subprocess boundary.

The kernel never invokes a shell.  Network isolation is an OS/container
responsibility; when a profile requests disabled networking, a backend must
explicitly attest that it enforced it before this runner will execute.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class SandboxNotEnforced(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxProfile:
    name: str
    allowed_executables: tuple[str, ...] = ()
    read_roots: tuple[str, ...] = ()
    write_root: str | None = None
    environment_keys: tuple[str, ...] = ()
    network_policy: str = "disabled"
    network_isolated: bool = False
    max_output_bytes: int = 4 * 1024 * 1024


@dataclass(frozen=True)
class SandboxResult:
    command: tuple[str, ...]
    returncode: int | None
    timed_out: bool
    stdout: bytes
    stderr: bytes
    enforcement: Mapping[str, object]


class SandboxRunner:
    def run(self, command: Sequence[str], *, cwd: str | Path, profile: SandboxProfile, timeout_seconds: int, environment: Mapping[str, str] | None = None) -> SandboxResult:
        if not command or any(not isinstance(item, str) or not item for item in command):
            raise ValueError("command must be a non-empty sequence of strings")
        if timeout_seconds < 1 or timeout_seconds > 86_400:
            raise ValueError("timeout_seconds out of range")
        if profile.network_policy not in {"disabled", "allow"}:
            raise ValueError("unsupported network policy")
        if profile.network_policy == "disabled" and not profile.network_isolated:
            raise SandboxNotEnforced("network isolation must be supplied by an approved OS/container backend")
        executable = str(Path(command[0]).resolve(strict=True))
        allowed = {str(Path(path).resolve(strict=True)) for path in profile.allowed_executables}
        if executable not in allowed:
            raise PermissionError("executable is not allowlisted")
        workdir = Path(cwd).resolve(strict=True)
        if not workdir.is_dir():
            raise ValueError("cwd must be a directory")
        roots = tuple(Path(root).resolve(strict=True) for root in profile.read_roots)
        write_root = Path(profile.write_root).resolve(strict=True) if profile.write_root else None
        if not any(workdir == root or root in workdir.parents for root in roots + ((write_root,) if write_root else ())):
            raise PermissionError("cwd is outside the sandbox roots")
        if profile.max_output_bytes < 1:
            raise ValueError("max_output_bytes must be positive")
        source_environment = environment or {}
        child_environment = {key: source_environment[key] for key in profile.environment_keys if key in source_environment}
        child_environment.update({"LC_ALL": "C", "LANG": "C"})
        try:
            completed = subprocess.run(tuple(command), cwd=str(workdir), env=child_environment, shell=False, capture_output=True, timeout=timeout_seconds, check=False)
            timed_out = False
            returncode: int | None = completed.returncode
            stdout, stderr = completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode = None
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
        return SandboxResult(tuple(command), returncode, timed_out, stdout[: profile.max_output_bytes], stderr[: profile.max_output_bytes], {"network": profile.network_policy, "network_isolated": profile.network_isolated, "shell": False, "environment_keys": list(profile.environment_keys)})
