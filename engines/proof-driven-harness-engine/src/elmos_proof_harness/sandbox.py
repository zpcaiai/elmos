"""Industrial-grade physical disposable process sandbox with POSIX rlimits and environment sanitization."""

from __future__ import annotations

import logging
import os
import resource
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

logger = logging.getLogger("elmos_proof_harness.sandbox")

_DEFAULT_ALLOWED_ENV: frozenset[str] = frozenset({
    "PATH",
    "LANG",
    "LC_ALL",
    "HOME",
    "USER",
    "TERM",
    "TZ",
})


@dataclass(frozen=True)
class SandboxLimits:
    max_cpu_seconds: int = 30
    max_memory_mb: int = 512
    max_file_size_mb: int = 50
    max_open_files: int = 256


@dataclass(frozen=True)
class SandboxExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    rlimit_enforced: bool
    scratch_dir: str


class DisposableSandboxRunner:
    """Runs commands in an isolated disposable scratch directory with resource limits."""

    def __init__(
        self,
        limits: SandboxLimits | None = None,
        allowed_env_vars: Sequence[str] | None = None,
    ) -> None:
        self.limits = limits or SandboxLimits()
        self.allowed_env = frozenset(allowed_env_vars or _DEFAULT_ALLOWED_ENV)

    def _sanitize_env(self, custom_env: Mapping[str, str] | None = None) -> dict[str, str]:
        clean: dict[str, str] = {}
        for key in self.allowed_env:
            val = os.environ.get(key)
            if val is not None:
                clean[key] = val
        if custom_env:
            for k, v in custom_env.items():
                if not any(token in k.upper() for token in ("KEY", "SECRET", "TOKEN", "PASSWORD")):
                    clean[k] = v
        return clean

    def run(
        self,
        args: Sequence[str],
        *,
        input_data: str | bytes | None = None,
        timeout_seconds: float = 30.0,
        custom_env: Mapping[str, str] | None = None,
        workspace_files: Mapping[str, str | bytes] | None = None,
    ) -> SandboxExecutionResult:
        with tempfile.TemporaryDirectory(prefix="harness_sandbox_") as tmp_dir:
            scratch_path = Path(tmp_dir)

            # Stage files into scratch space if provided
            if workspace_files:
                for rel_path, content in workspace_files.items():
                    target_file = scratch_path / rel_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    if isinstance(content, str):
                        target_file.write_text(content, encoding="utf-8")
                    else:
                        target_file.write_bytes(content)

            env = self._sanitize_env(custom_env)
            env["TMPDIR"] = tmp_dir
            env["TMP"] = tmp_dir

            limits = self.limits

            def _preexec() -> None:
                # Create a new process group for clean subtree kill
                os.setpgrp()

                # Enforce CPU limit
                try:
                    resource.setrlimit(
                        resource.RLIMIT_CPU,
                        (limits.max_cpu_seconds, limits.max_cpu_seconds + 5),
                    )
                except Exception:
                    pass

                # Enforce File Size limit
                try:
                    fsize_bytes = limits.max_file_size_mb * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_bytes, fsize_bytes))
                except Exception:
                    pass

                # Enforce Max Open Files
                try:
                    resource.setrlimit(
                        resource.RLIMIT_NOFILE,
                        (limits.max_open_files, limits.max_open_files),
                    )
                except Exception:
                    pass

                # Disable Core Dumps
                try:
                    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                except Exception:
                    pass

            started = time.monotonic()
            timed_out = False
            proc: subprocess.Popen[str] | None = None
            stdin_data = input_data if isinstance(input_data, str) else (
                input_data.decode("utf-8") if input_data is not None else None
            )

            try:
                proc = subprocess.Popen(
                    list(args),
                    cwd=tmp_dir,
                    env=env,
                    stdin=subprocess.PIPE if stdin_data is not None else None,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    preexec_fn=_preexec if os.name == "posix" else None,
                )
                stdout_data, stderr_data = proc.communicate(
                    input=stdin_data,
                    timeout=timeout_seconds,
                )
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                if proc is not None:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except Exception:
                        proc.kill()
                    stdout_data, stderr_data = proc.communicate()
                else:
                    stdout_data, stderr_data = "", ""
                exit_code = -1
            except Exception as exc:
                stdout_data = ""
                stderr_data = f"Failed to execute sandbox command: {exc}"
                exit_code = 1

            duration_ms = int((time.monotonic() - started) * 1000)

            return SandboxExecutionResult(
                exit_code=exit_code,
                stdout=stdout_data,
                stderr=stderr_data,
                duration_ms=duration_ms,
                timed_out=timed_out,
                rlimit_enforced=os.name == "posix",
                scratch_dir=tmp_dir,
            )
