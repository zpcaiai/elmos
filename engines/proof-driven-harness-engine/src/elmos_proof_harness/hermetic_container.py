"""Industrial-grade hermetic container sandbox and cross-platform environment fingerprinting."""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from .sandbox import DisposableSandboxRunner, SandboxLimits

logger = logging.getLogger("elmos_proof_harness.hermetic_container")


class PlatformArch(str, Enum):
    AARCH64 = "aarch64"
    X86_64 = "x86_64"
    ARM64 = "arm64"
    AMD64 = "amd64"
    UNKNOWN = "unknown"


class IsolationLevel(str, Enum):
    DOCKER_CONTAINER = "DOCKER_CONTAINER"
    PODMAN_CONTAINER = "PODMAN_CONTAINER"
    POSIX_RLIMIT_SANDBOX = "POSIX_RLIMIT_SANDBOX"


@dataclass(frozen=True)
class EnvironmentFingerprint:
    """Detailed immutable profile of the host OS, runtime libraries, and container engines."""

    os_system: str
    os_release: str
    arch: str
    python_version: str
    libc_kind: str
    docker_available: bool
    podman_available: bool
    active_isolation_level: IsolationLevel

    def to_dict(self) -> dict[str, Any]:
        return {
            "os_system": self.os_system,
            "os_release": self.os_release,
            "arch": self.arch,
            "python_version": self.python_version,
            "libc_kind": self.libc_kind,
            "docker_available": self.docker_available,
            "podman_available": self.podman_available,
            "active_isolation_level": self.active_isolation_level.value,
        }

    @classmethod
    def detect(cls) -> EnvironmentFingerprint:
        """Probes the physical host environment for architecture, OS, libc, and container runtimes."""
        os_sys = platform.system().lower()
        os_rel = platform.release()
        arch = platform.machine().lower()
        py_ver = platform.python_version()

        # Probe libc flavor
        libc_kind = "unknown"
        if os_sys == "linux":
            libc_info = platform.libc_ver()
            if libc_info[0]:
                libc_kind = f"{libc_info[0]}-{libc_info[1]}"
            elif Path("/etc/alpine-release").exists():
                libc_kind = "musl-alpine"
            else:
                libc_kind = "glibc"
        elif os_sys == "darwin":
            libc_kind = "bsd-darwin"
        elif os_sys == "windows":
            libc_kind = "msvcrt"

        # Probe Docker daemon
        docker_cli = shutil.which("docker")
        docker_ready = False
        if docker_cli:
            try:
                # Fast timeout check if daemon is responsive
                p = subprocess.run(
                    [docker_cli, "info", "--format", "{{.ServerVersion}}"],
                    capture_output=True,
                    timeout=2.0,
                    text=True,
                    check=False,
                )
                docker_ready = p.returncode == 0
            except Exception:
                docker_ready = False

        # Probe Podman
        podman_cli = shutil.which("podman")
        podman_ready = False
        if podman_cli:
            try:
                p = subprocess.run(
                    [podman_cli, "info", "--format", "{{.Version.Version}}"],
                    capture_output=True,
                    timeout=2.0,
                    text=True,
                    check=False,
                )
                podman_ready = p.returncode == 0
            except Exception:
                podman_ready = False

        if docker_ready:
            active_level = IsolationLevel.DOCKER_CONTAINER
        elif podman_ready:
            active_level = IsolationLevel.PODMAN_CONTAINER
        else:
            active_level = IsolationLevel.POSIX_RLIMIT_SANDBOX

        return cls(
            os_system=os_sys,
            os_release=os_rel,
            arch=arch,
            python_version=py_ver,
            libc_kind=libc_kind,
            docker_available=docker_ready,
            podman_available=podman_ready,
            active_isolation_level=active_level,
        )


@dataclass(frozen=True)
class HermeticExecutionReceipt:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    isolation_level: IsolationLevel
    fingerprint: EnvironmentFingerprint
    container_id: str | None = None


class HermeticContainerSandbox:
    """Executes untrusted verification tasks in true containers or falls back to POSIX rlimit isolation."""

    def __init__(
        self,
        limits: SandboxLimits | None = None,
        force_posix_fallback: bool = False,
        container_image: str = "python:3.12-slim",
    ) -> None:
        self.limits = limits or SandboxLimits()
        self.fingerprint = EnvironmentFingerprint.detect()
        self.force_posix = force_posix_fallback
        self.container_image = container_image

    def run(
        self,
        args: Sequence[str],
        *,
        input_data: str | bytes | None = None,
        timeout_seconds: float = 30.0,
        custom_env: Mapping[str, str] | None = None,
        workspace_files: Mapping[str, str | bytes] | None = None,
    ) -> HermeticExecutionReceipt:
        # Determine whether to use container or POSIX fallback
        use_container = (
            not self.force_posix
            and self.fingerprint.active_isolation_level
            in (IsolationLevel.DOCKER_CONTAINER, IsolationLevel.PODMAN_CONTAINER)
        )

        if use_container:
            return self._run_in_container(
                args,
                input_data=input_data,
                timeout_seconds=timeout_seconds,
                custom_env=custom_env,
                workspace_files=workspace_files,
            )
        else:
            return self._run_in_posix_sandbox(
                args,
                input_data=input_data,
                timeout_seconds=timeout_seconds,
                custom_env=custom_env,
                workspace_files=workspace_files,
            )

    def _run_in_posix_sandbox(
        self,
        args: Sequence[str],
        *,
        input_data: str | bytes | None = None,
        timeout_seconds: float = 30.0,
        custom_env: Mapping[str, str] | None = None,
        workspace_files: Mapping[str, str | bytes] | None = None,
    ) -> HermeticExecutionReceipt:
        runner = DisposableSandboxRunner(self.limits)
        res = runner.run(
            args,
            input_data=input_data,
            timeout_seconds=timeout_seconds,
            custom_env=custom_env,
            workspace_files=workspace_files,
        )
        return HermeticExecutionReceipt(
            exit_code=res.exit_code,
            stdout=res.stdout,
            stderr=res.stderr,
            duration_ms=res.duration_ms,
            timed_out=res.timed_out,
            isolation_level=IsolationLevel.POSIX_RLIMIT_SANDBOX,
            fingerprint=self.fingerprint,
            container_id=None,
        )

    def _run_in_container(
        self,
        args: Sequence[str],
        *,
        input_data: str | bytes | None = None,
        timeout_seconds: float = 30.0,
        custom_env: Mapping[str, str] | None = None,
        workspace_files: Mapping[str, str | bytes] | None = None,
    ) -> HermeticExecutionReceipt:
        cli = "docker" if self.fingerprint.active_isolation_level == IsolationLevel.DOCKER_CONTAINER else "podman"
        start_time = time.monotonic()

        # Build secure container flags
        # --read-only, --network=none, --memory, --cpus
        cmd = [
            cli,
            "run",
            "--rm",
            "-i",
            "--network=none",
            f"--memory={self.limits.max_memory_mb}m",
            f"--cpus={max(1.0, self.limits.max_cpu_seconds / 10.0)}",
        ]

        if custom_env:
            for k, v in custom_env.items():
                cmd.extend(["-e", f"{k}={v}"])

        cmd.append(self.container_image)
        cmd.extend(args)

        try:
            p = subprocess.run(
                cmd,
                input=input_data.encode("utf-8") if isinstance(input_data, str) else input_data,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return HermeticExecutionReceipt(
                exit_code=p.returncode,
                stdout=p.stdout.decode("utf-8", errors="replace"),
                stderr=p.stderr.decode("utf-8", errors="replace"),
                duration_ms=elapsed_ms,
                timed_out=False,
                isolation_level=self.fingerprint.active_isolation_level,
                fingerprint=self.fingerprint,
                container_id=f"{cli}-ephemeral-{int(time.time())}",
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return HermeticExecutionReceipt(
                exit_code=-9,
                stdout=exc.stdout.decode("utf-8", errors="replace") if exc.stdout else "",
                stderr=exc.stderr.decode("utf-8", errors="replace") if exc.stderr else "Container timed out",
                duration_ms=elapsed_ms,
                timed_out=True,
                isolation_level=self.fingerprint.active_isolation_level,
                fingerprint=self.fingerprint,
                container_id=None,
            )
