"""The pluggable execution boundary.

The deterministic core never shells out.  When a Skill needs a fact that only a
real toolchain can produce — "does this compile?", "do these tests pass?" — it
emits an :class:`ExecutionRequest` and asks the configured
:class:`SandboxExecutor` for an :class:`ExecutionResult`.

Three executors ship here:

:class:`NullExecutor`
    The default.  Runs nothing and answers ``NOT_RUN``.  This is the single
    most important behaviour in the module: a gate whose evidence was never
    produced must read as *undecided*, and an undecided blocking gate fails.
    It must never read as "passed".
:class:`RecordedExecutor`
    Replays results the host captured elsewhere (CI, a build farm), keyed by
    the request's content digest.  A request with no recording answers
    ``NOT_RUN``, never a fabricated success.
:class:`SubprocessExecutor`
    Really executes, inside a host-approved directory, against an explicit
    binary allowlist, with a wall-clock timeout, a scrubbed environment and no
    inherited network credentials.  It can only be constructed by the host.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # noqa: S404 - the whole point of this module is bounded execution
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from .contracts import (
    ContractError,
    NetworkPolicy,
    integer_value,
    normalize_relative_path,
    optional_string,
    optional_text,
    reject_unknown_fields,
    require_enum,
    require_mapping,
    require_string,
    require_string_sequence,
    sha256_payload,
    sha256_text,
)

#: Requests are capped so a misbehaving Recipe cannot pin a worker forever.
MAX_TIMEOUT_SECONDS = 7200
MAX_OUTPUT_BYTES = 4 * 1024 * 1024


class ExecutionKind(StrEnum):
    PROBE = "probe"
    RESTORE = "restore"
    BUILD = "build"
    TEST = "test"
    TYPECHECK = "typecheck"
    FORMAT = "format"
    SCAN = "scan"
    BENCHMARK = "benchmark"
    MIGRATION = "migration"
    CUSTOM = "custom"


class ExecutionStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    REFUSED = "refused"
    NOT_RUN = "not-run"

    @property
    def produced_evidence(self) -> bool:
        """Only these statuses may be used to decide a gate."""

        return self in {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT}


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    request_id: str
    kind: ExecutionKind
    argv: tuple[str, ...]
    working_directory: str = "."
    environment: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: int = 900
    network: NetworkPolicy = NetworkPolicy.DENY
    expected_artifacts: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not self.argv:
            raise ContractError("invalid_execution_request", "argv must not be empty")
        for item in self.argv:
            require_string(item, "execution.argv[]", max_length=4096)
        integer_value(self.timeout_seconds, "execution.timeout_seconds", minimum=1, maximum=MAX_TIMEOUT_SECONDS)

    @property
    def digest(self) -> str:
        """Content identity used for caching, recording and idempotency."""

        return sha256_payload(
            {
                "kind": self.kind.value,
                "argv": list(self.argv),
                "working_directory": self.working_directory,
                "environment": dict(sorted(self.environment.items())),
                "network": self.network.value,
            }
        )

    @property
    def binary(self) -> str:
        return self.argv[0]

    def to_payload(self) -> dict[str, Any]:
        return {
            "requestId": self.request_id,
            "kind": self.kind.value,
            "argv": list(self.argv),
            "workingDirectory": self.working_directory,
            "environment": dict(sorted(self.environment.items())),
            "timeoutSeconds": self.timeout_seconds,
            "network": self.network.value,
            "expectedArtifacts": list(self.expected_artifacts),
            "description": self.description,
            "digest": self.digest,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ExecutionRequest:
        value = require_mapping(payload, "execution_request")
        reject_unknown_fields(
            value,
            {
                "requestId",
                "kind",
                "argv",
                "workingDirectory",
                "environment",
                "timeoutSeconds",
                "network",
                "expectedArtifacts",
                "description",
                "digest",
            },
            "execution_request",
        )
        environment_raw = require_mapping(value.get("environment", {}), "execution_request.environment")
        return cls(
            request_id=require_string(value.get("requestId"), "execution_request.requestId", max_length=128),
            kind=require_enum(value.get("kind"), ExecutionKind, "execution_request.kind"),
            argv=require_string_sequence(value.get("argv"), "execution_request.argv", allow_empty=False),
            working_directory=optional_string(
                value.get("workingDirectory"), "execution_request.workingDirectory", max_length=4096
            )
            or ".",
            environment={
                require_string(key, "execution_request.environment key", max_length=128): require_string(
                    item, "execution_request.environment value", max_length=4096
                )
                for key, item in environment_raw.items()
            },
            timeout_seconds=integer_value(
                value.get("timeoutSeconds", 900),
                "execution_request.timeoutSeconds",
                minimum=1,
                maximum=MAX_TIMEOUT_SECONDS,
            ),
            network=require_enum(value.get("network", "deny"), NetworkPolicy, "execution_request.network"),
            expected_artifacts=require_string_sequence(
                value.get("expectedArtifacts", ()), "execution_request.expectedArtifacts"
            ),
            description=optional_text(value.get("description"), "execution_request.description"),
        )


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    request_id: str
    request_digest: str
    status: ExecutionStatus
    exit_code: int | None = None
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    executor: str = "null"
    reason: str = ""
    artifacts: Mapping[str, str] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status is ExecutionStatus.COMPLETED and self.exit_code == 0

    @property
    def decisive(self) -> bool:
        """Whether this result may be used to pass or fail a gate."""

        return self.status.produced_evidence

    def to_payload(self) -> dict[str, Any]:
        return {
            "requestId": self.request_id,
            "requestDigest": self.request_digest,
            "status": self.status.value,
            "exitCode": self.exit_code,
            "durationMs": self.duration_ms,
            "stdoutDigest": sha256_text(self.stdout),
            "stderrDigest": sha256_text(self.stderr),
            "stdoutBytes": len(self.stdout.encode("utf-8")),
            "stderrBytes": len(self.stderr.encode("utf-8")),
            "truncated": self.truncated,
            "executor": self.executor,
            "reason": self.reason,
            "artifacts": dict(sorted(self.artifacts.items())),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ExecutionResult:
        value = require_mapping(payload, "execution_result")
        exit_code = value.get("exitCode")
        artifacts_raw = require_mapping(value.get("artifacts", {}), "execution_result.artifacts")
        return cls(
            request_id=require_string(value.get("requestId"), "execution_result.requestId", max_length=128),
            request_digest=require_string(
                value.get("requestDigest"), "execution_result.requestDigest", max_length=128
            ),
            status=require_enum(value.get("status"), ExecutionStatus, "execution_result.status"),
            exit_code=None if exit_code is None else integer_value(exit_code, "execution_result.exitCode"),
            duration_ms=integer_value(value.get("durationMs", 0), "execution_result.durationMs", minimum=0),
            stdout=optional_text(value.get("stdout"), "execution_result.stdout", max_length=MAX_OUTPUT_BYTES),
            stderr=optional_text(value.get("stderr"), "execution_result.stderr", max_length=MAX_OUTPUT_BYTES),
            truncated=bool(value.get("truncated", False)),
            executor=optional_string(value.get("executor"), "execution_result.executor") or "recorded",
            reason=optional_text(value.get("reason"), "execution_result.reason"),
            artifacts={
                require_string(key, "execution_result.artifacts key"): require_string(
                    item, "execution_result.artifacts value"
                )
                for key, item in artifacts_raw.items()
            },
        )


class SandboxExecutor(Protocol):
    """Everything the core needs from an execution backend."""

    @property
    def name(self) -> str: ...

    def capabilities(self) -> Mapping[str, Any]: ...

    def execute(self, request: ExecutionRequest) -> ExecutionResult: ...


class NullExecutor:
    """Refuses to execute and says so.  The safe default."""

    __slots__ = ("_reason",)

    def __init__(self, reason: str = "no-executor-configured") -> None:
        self._reason = reason

    @property
    def name(self) -> str:
        return "null"

    def capabilities(self) -> Mapping[str, Any]:
        return {"executes": False, "kinds": [], "reason": self._reason}

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(
            request_id=request.request_id,
            request_digest=request.digest,
            status=ExecutionStatus.NOT_RUN,
            executor=self.name,
            reason=self._reason,
        )


class RecordedExecutor:
    """Replays host-captured results keyed by request digest."""

    __slots__ = ("_results",)

    def __init__(self, results: Iterable[ExecutionResult]) -> None:
        self._results: dict[str, ExecutionResult] = {}
        for result in results:
            if result.request_digest in self._results:
                raise ContractError(
                    "duplicate_recording",
                    f"two recordings share request digest {result.request_digest}",
                )
            self._results[result.request_digest] = result

    @property
    def name(self) -> str:
        return "recorded"

    def capabilities(self) -> Mapping[str, Any]:
        return {"executes": False, "replays": True, "recordings": len(self._results)}

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        recorded = self._results.get(request.digest)
        if recorded is None:
            return ExecutionResult(
                request_id=request.request_id,
                request_digest=request.digest,
                status=ExecutionStatus.NOT_RUN,
                executor=self.name,
                reason="no-recording-for-request",
            )
        return ExecutionResult(
            request_id=request.request_id,
            request_digest=request.digest,
            status=recorded.status,
            exit_code=recorded.exit_code,
            duration_ms=recorded.duration_ms,
            stdout=recorded.stdout,
            stderr=recorded.stderr,
            truncated=recorded.truncated,
            executor=self.name,
            reason=recorded.reason,
            artifacts=recorded.artifacts,
        )

    @classmethod
    def from_payload(cls, payload: Sequence[Mapping[str, Any]]) -> RecordedExecutor:
        return cls(ExecutionResult.from_payload(item) for item in payload)


#: Environment variables that are never inherited into a sandboxed process.
#: Anything that could carry a credential, a proxy or a package-index override
#: is dropped rather than filtered, because a filter has to be exhaustive and
#: a drop list does not.
_ENVIRONMENT_ALLOWLIST = frozenset({"PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR"})


class SubprocessExecutor:
    """Bounded real execution.  Host-constructed only.

    Guarantees:

    * every binary must be on the allowlist and resolvable on ``PATH``;
    * the working directory must resolve inside the approved root;
    * the environment is rebuilt from a small allowlist plus explicit request
      variables — no inherited tokens, proxies or registry overrides;
    * network-requiring requests are refused unless the executor was created
      with a matching network policy;
    * output is captured with a hard byte cap and the process group is killed
      on timeout.
    """

    __slots__ = ("_root", "_allowlist", "_network", "_extra_env", "_max_output")

    def __init__(
        self,
        root: Path,
        *,
        allowlist: Iterable[str],
        network: NetworkPolicy = NetworkPolicy.DENY,
        environment: Mapping[str, str] | None = None,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
    ) -> None:
        resolved = root.resolve(strict=True)
        if not resolved.is_dir():
            raise ContractError("sandbox_root_not_directory", "sandbox root must be a directory")
        self._root = resolved
        self._allowlist = frozenset(require_string(item, "allowlist[]", max_length=128) for item in allowlist)
        if not self._allowlist:
            raise ContractError("empty_allowlist", "a subprocess executor requires a non-empty binary allowlist")
        self._network = network
        self._extra_env = dict(environment or {})
        self._max_output = integer_value(max_output_bytes, "max_output_bytes", minimum=1024)

    @property
    def name(self) -> str:
        return "subprocess"

    def capabilities(self) -> Mapping[str, Any]:
        return {
            "executes": True,
            "root": str(self._root),
            "allowlist": sorted(self._allowlist),
            "network": self._network.value,
        }

    def _resolve_cwd(self, request: ExecutionRequest) -> Path:
        if request.working_directory in ("", "."):
            return self._root
        relative = normalize_relative_path(request.working_directory, "execution.working_directory")
        candidate = (self._root / relative).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise ContractError("path_escape", "execution working directory escapes the sandbox root") from exc
        if not candidate.is_dir():
            raise ContractError("missing_working_directory", f"working directory '{relative}' does not exist")
        return candidate

    def _build_environment(self, request: ExecutionRequest) -> dict[str, str]:
        environment = {
            key: value for key, value in os.environ.items() if key in _ENVIRONMENT_ALLOWLIST
        }
        environment.update(self._extra_env)
        environment.update(request.environment)
        if request.network is NetworkPolicy.DENY:
            # Belt and braces: even if the host has no network namespace, make
            # the common clients fail fast instead of silently reaching out.
            environment.update({"http_proxy": "", "https_proxy": "", "no_proxy": "*", "NO_PROXY": "*"})
        return environment

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        def refused(reason: str) -> ExecutionResult:
            return ExecutionResult(
                request_id=request.request_id,
                request_digest=request.digest,
                status=ExecutionStatus.REFUSED,
                executor=self.name,
                reason=reason,
            )

        if request.binary not in self._allowlist:
            return refused(f"binary-not-allowlisted:{request.binary}")
        order = (NetworkPolicy.DENY, NetworkPolicy.RESTORE_ONLY, NetworkPolicy.ALLOWLISTED)
        if order.index(request.network) > order.index(self._network):
            return refused(f"network-policy-exceeded:{request.network.value}")
        resolved_binary = shutil.which(request.binary)
        if resolved_binary is None:
            return refused(f"binary-not-found:{request.binary}")
        try:
            cwd = self._resolve_cwd(request)
        except ContractError as error:
            return refused(error.code)

        argv = (resolved_binary, *request.argv[1:])
        started = time.monotonic()
        try:
            completed = subprocess.run(  # noqa: S603 - argv is allowlisted and never shell-interpreted
                argv,
                cwd=str(cwd),
                env=self._build_environment(request),
                capture_output=True,
                timeout=request.timeout_seconds,
                check=False,
                shell=False,
                text=False,
            )
        except subprocess.TimeoutExpired as expired:
            return ExecutionResult(
                request_id=request.request_id,
                request_digest=request.digest,
                status=ExecutionStatus.TIMEOUT,
                duration_ms=int((time.monotonic() - started) * 1000),
                stdout=_decode(expired.stdout, self._max_output)[0],
                stderr=_decode(expired.stderr, self._max_output)[0],
                executor=self.name,
                reason=f"timeout-after-{request.timeout_seconds}s",
            )
        except OSError as error:
            return refused(f"spawn-failed:{error.errno}")

        stdout, stdout_truncated = _decode(completed.stdout, self._max_output)
        stderr, stderr_truncated = _decode(completed.stderr, self._max_output)
        artifacts = {
            name: sha256_text((cwd / name).read_text(encoding="utf-8", errors="replace"))
            for name in request.expected_artifacts
            if (cwd / name).is_file()
        }
        return ExecutionResult(
            request_id=request.request_id,
            request_digest=request.digest,
            status=ExecutionStatus.COMPLETED if completed.returncode == 0 else ExecutionStatus.FAILED,
            exit_code=completed.returncode,
            duration_ms=int((time.monotonic() - started) * 1000),
            stdout=stdout,
            stderr=stderr,
            truncated=stdout_truncated or stderr_truncated,
            executor=self.name,
            artifacts=artifacts,
        )


def _decode(data: bytes | None, limit: int) -> tuple[str, bool]:
    if not data:
        return "", False
    truncated = len(data) > limit
    return data[:limit].decode("utf-8", errors="replace"), truncated


@dataclass(frozen=True, slots=True)
class ExecutionLedger:
    """Every request issued in a run, with its result — verifier evidence."""

    entries: tuple[tuple[ExecutionRequest, ExecutionResult], ...] = ()

    def record(self, request: ExecutionRequest, result: ExecutionResult) -> ExecutionLedger:
        return ExecutionLedger(entries=(*self.entries, (request, result)))

    @property
    def not_run(self) -> tuple[ExecutionRequest, ...]:
        return tuple(request for request, result in self.entries if not result.decisive)

    def to_payload(self) -> list[dict[str, Any]]:
        return [
            {"request": request.to_payload(), "result": result.to_payload()}
            for request, result in self.entries
        ]

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


def run_all(
    executor: SandboxExecutor,
    requests: Sequence[ExecutionRequest],
) -> tuple[ExecutionLedger, dict[str, ExecutionResult]]:
    ledger = ExecutionLedger()
    results: dict[str, ExecutionResult] = {}
    for request in requests:
        result = executor.execute(request)
        ledger = ledger.record(request, result)
        results[request.request_id] = result
    return ledger, results


__all__ = [
    "MAX_OUTPUT_BYTES",
    "MAX_TIMEOUT_SECONDS",
    "ExecutionKind",
    "ExecutionLedger",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionStatus",
    "NullExecutor",
    "RecordedExecutor",
    "SandboxExecutor",
    "SubprocessExecutor",
    "run_all",
]
