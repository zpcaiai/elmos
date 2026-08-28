"""Fail-closed external compiler, verifier, and harness adapter execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import threading
import time
from typing import Any, Mapping, Sequence


_DANGEROUS_ENVIRONMENT_KEYS = {
    "BASH_ENV",
    "CDPATH",
    "ENV",
    "GCONV_PATH",
    "IFS",
    "JAVA_TOOL_OPTIONS",
    "JDK_JAVA_OPTIONS",
    "NODE_OPTIONS",
    "NODE_PATH",
    "PERL5OPT",
    "RUBYOPT",
    "SHELLOPTS",
    "_JAVA_OPTIONS",
}
_SECRET_ENVIRONMENT_MARKERS = (
    "ACCESS_KEY",
    "API_KEY",
    "CREDENTIAL",
    "PASSWORD",
    "PRIVATE_KEY",
    "SECRET",
    "TOKEN",
)


class AdapterStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_RUN = "NOT_RUN"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    DENIED = "DENIED"


@dataclass(frozen=True, slots=True)
class CapabilityAdapterSpec:
    capability: str
    provider: str
    authoritative_requirement: str


@dataclass(frozen=True, slots=True)
class DeclaredAdapterDescriptor:
    """Repository-owned declaration for one exact source-package boundary.

    Descriptors are inventory and policy contracts only.  They never load the
    ZIP's placeholder binary configuration and cannot be invoked until trusted
    deployment supplies an independently configured, digest-pinned manifest.
    """

    adapter_id: str
    adapter_kind: str
    capabilities: tuple[str, ...]
    required_authority: tuple[str, ...]
    scope: str
    verifier_kind: str | None = None
    implementation_state: str = "ADAPTER_REQUIRED"
    runtime_status: str = "NOT_RUN"

    def __post_init__(self) -> None:
        if not self.adapter_id or self.adapter_kind not in {"verifier", "harness"}:
            raise ValueError("declared adapter identity is invalid")
        if not self.capabilities or len(set(self.capabilities)) != len(
            self.capabilities
        ):
            raise ValueError("declared adapter capabilities must be non-empty and unique")
        if not self.required_authority or len(set(self.required_authority)) != len(
            self.required_authority
        ):
            raise ValueError("declared adapter authority must be non-empty and unique")
        if not self.scope:
            raise ValueError("declared adapter scope is required")
        if self.implementation_state != "ADAPTER_REQUIRED":
            raise ValueError("source adapter without a pinned binding must require an adapter")
        if self.runtime_status != "NOT_RUN":
            raise ValueError("source adapter declarations cannot claim runtime execution")

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapterId": self.adapter_id,
            "kind": self.adapter_kind,
            "capabilities": list(self.capabilities),
            "requiredAuthority": list(self.required_authority),
            "scope": self.scope,
            "verifierKind": self.verifier_kind,
            "implementationState": self.implementation_state,
            "runtimeStatus": self.runtime_status,
            "sourceConfigurationExecuted": False,
        }


def _verifier(
    adapter_id: str,
    verifier_kind: str,
    scope: str,
) -> DeclaredAdapterDescriptor:
    return DeclaredAdapterDescriptor(
        adapter_id=adapter_id,
        adapter_kind="verifier",
        capabilities=("proof.verify",),
        required_authority=("adapter.execute", "proof.verify"),
        scope=scope,
        verifier_kind=verifier_kind,
    )


def _harness(
    adapter_id: str,
    capabilities: tuple[str, ...],
    scope: str,
) -> DeclaredAdapterDescriptor:
    return DeclaredAdapterDescriptor(
        adapter_id=adapter_id,
        adapter_kind="harness",
        capabilities=capabilities,
        required_authority=("adapter.execute", "harness.session.execute"),
        scope=scope,
    )


# Exact identities and bounded capabilities transcribed as data from the
# source-package contracts. No source-package YAML, script, or binary pin is
# imported or executed at runtime.
VERIFIER_ADAPTER_REGISTRY: dict[str, DeclaredAdapterDescriptor] = {
    item.adapter_id: item
    for item in (
        _verifier("verifier-alive2", "LLVM translation validator", "LLVM IR optimization/refinement"),
        _verifier("verifier-alloy", "relational model finder", "bounded structural/relational properties"),
        _verifier("verifier-apalache", "symbolic TLA+ model checker", "bounded symbolic safety checks"),
        _verifier("verifier-boogie", "intermediate verifier", "Boogie VCs generated from Semantic IR"),
        _verifier("verifier-cbmc", "C/C++ bounded model checker", "C/C++ assertions, memory and unwinding bounds"),
        _verifier("verifier-cvc5-smt", "SMT solver", "SMT-LIB2, strings, datatypes, finite model finding"),
        _verifier("verifier-dafny", "verification language", "pre/postconditions, invariants, termination"),
        _verifier("verifier-differential-runtime", "source-target runtime oracle", "canonical observable traces/data/events"),
        _verifier("verifier-frama-c", "C deductive/static verification", "ACSL/WP/value analysis supported fragments"),
        _verifier("verifier-java-pathfinder", "Java model checker", "concurrency/state exploration"),
        _verifier("verifier-kani", "Rust model checker", "Rust MIR supported fragments"),
        _verifier("verifier-key-java", "Java deductive verification", "Java/JML dynamic logic supported fragments"),
        _verifier("verifier-lean-proof-checker", "proof assistant kernel", "Lean proof objects generated or authored by adapters"),
        _verifier("verifier-openjml", "Java JML verification", "Java/JML supported fragments"),
        _verifier("verifier-property-fuzz-mutation", "generative testing portfolio", "property/metamorphic/fuzz/mutation"),
        _verifier("verifier-security-performance-resilience", "non-functional portfolio", "SAST/DAST/SBOM/load/chaos/recovery"),
        _verifier("verifier-sqlsolver", "SQL equivalence", "supported SQL query equivalence"),
        _verifier("verifier-tla-tlc", "explicit-state model checker", "TLA+ safety/liveness bounded by model"),
        _verifier("verifier-verieql", "SQL equivalence", "bounded SQL equivalence/data constraints"),
        _verifier("verifier-z3-smt", "SMT solver", "SMT-LIB2 / API encodings"),
    )
}

HARNESS_ADAPTER_REGISTRY: dict[str, DeclaredAdapterDescriptor] = {
    item.adapter_id: item
    for item in (
        _harness("harness-claude-code", ("session continuity", "tool calls", "subagents", "hooks", "permission decisions", "checkpoint metadata"), "session/tool/subagent lifecycle, hooks, permissions and project instructions"),
        _harness("harness-codex-app-server", ("thread lifecycle", "turn lifecycle", "streamed items/events", "tool calls", "approval requests", "cancellation", "session persistence"), "thread/turn/item lifecycle, bidirectional events, tool approvals, sandbox and provider-native state"),
        _harness("harness-mcp-a2a", ("tool discovery", "schema invocation", "resources", "agent messages", "elicitation/approval"), "tool/resource/prompt and agent-to-agent interoperability"),
        _harness("harness-opencode", ("sessions", "provider routing", "tool calls", "file/terminal actions", "events"), "coding-agent sessions, tools, providers, permissions and terminal/file operations"),
        _harness("harness-openhands", ("workspace", "action/observation", "sandbox", "events", "pause/cancel", "agent state"), "agent runtime, sandbox/workspace, event stream and action/observation loop"),
        _harness("harness-openharness", ("agent run", "tool registry", "environment", "events", "artifacts"), "generic harness orchestration and environment integration"),
        _harness("harness-symphony", ("work item", "workspace creation", "agent launch", "event collection", "cleanup", "retry"), "issue/work item to isolated workspace/agent run and proof-of-work"),
    )
}

DECLARED_ADAPTER_REGISTRY: dict[str, DeclaredAdapterDescriptor] = {
    **VERIFIER_ADAPTER_REGISTRY,
    **HARNESS_ADAPTER_REGISTRY,
}

if (
    len(VERIFIER_ADAPTER_REGISTRY) != 20
    or len(HARNESS_ADAPTER_REGISTRY) != 7
    or len(DECLARED_ADAPTER_REGISTRY) != 27
):
    raise RuntimeError("exact source adapter registry is incomplete or colliding")


# Explicit declarations are preferable to silently applying a generic parser.
DEFAULT_CAPABILITY_SPECS: dict[str, CapabilityAdapterSpec] = {
    "python": CapabilityAdapterSpec("semantic.compile.python", "CPython ast", "exact source digest and CPython version"),
    "json": CapabilityAdapterSpec("semantic.compile.json", "RFC 8259 parser", "duplicate-key policy and exact bytes"),
    "yaml": CapabilityAdapterSpec("semantic.compile.yaml", "safe YAML composer", "safe tag policy and exact bytes"),
    "toml": CapabilityAdapterSpec("semantic.compile.toml", "TOML 1.0 parser", "exact bytes and parser version"),
    "sql": CapabilityAdapterSpec("semantic.compile.sql", "dialect parser plus engine catalog", "exact engine/dialect/version"),
    "java": CapabilityAdapterSpec("semantic.compile.java", "javac bridge", "exact JDK and processor policy"),
    "kotlin": CapabilityAdapterSpec("semantic.compile.kotlin", "Kotlin Analysis API", "exact compiler/plugin tuple"),
    "csharp": CapabilityAdapterSpec("semantic.compile.csharp", "Roslyn", "exact SDK/analyzer tuple"),
    "typescript": CapabilityAdapterSpec("semantic.compile.typescript", "TypeScript compiler API", "exact tsconfig/compiler tuple"),
    "javascript": CapabilityAdapterSpec("semantic.compile.javascript", "JavaScript parser plus runtime", "exact module/runtime tuple"),
    "go": CapabilityAdapterSpec("semantic.compile.go", "go/packages plus go/types", "exact Go/build tags tuple"),
    "rust": CapabilityAdapterSpec("semantic.compile.rust", "rustc HIR/MIR", "exact toolchain/features tuple"),
    "c": CapabilityAdapterSpec("semantic.compile.c", "Clang", "exact compiler/flags/target tuple"),
    "cpp": CapabilityAdapterSpec("semantic.compile.cpp", "Clang", "exact compiler/flags/target tuple"),
    "objective-c": CapabilityAdapterSpec("semantic.compile.objective-c", "Clang", "exact SDK/runtime/target tuple"),
    "swift": CapabilityAdapterSpec("semantic.compile.swift", "SwiftSyntax plus SIL", "exact SDK/compiler/target tuple"),
    "dart": CapabilityAdapterSpec("semantic.compile.dart", "Dart analyzer", "exact SDK/platform tuple"),
    "php": CapabilityAdapterSpec("semantic.compile.php", "PHP parser plus runtime", "exact PHP/extensions tuple"),
}


@dataclass(frozen=True, slots=True)
class AdapterManifest:
    adapter_id: str
    version: str
    executable: str
    executable_sha256: str
    capabilities: tuple[str, ...]
    required_authority: tuple[str, ...] = ()
    arguments: tuple[str, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict)
    max_timeout_seconds: float = 60.0
    max_input_bytes: int = 1024 * 1024
    max_output_bytes: int = 8 * 1024 * 1024

    def __post_init__(self) -> None:
        if not self.adapter_id or not self.version:
            raise ValueError("adapter id and version are required")
        if not os.path.isabs(self.executable):
            raise ValueError("adapter executable must be an absolute path")
        if len(self.executable_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.executable_sha256
        ):
            raise ValueError("adapter executable_sha256 must be lowercase SHA-256")
        if not self.capabilities or len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("adapter capabilities must be non-empty and unique")
        if len(set(self.required_authority)) != len(self.required_authority):
            raise ValueError("adapter authority must be unique")
        if self.max_timeout_seconds <= 0 or self.max_input_bytes <= 0 or self.max_output_bytes <= 0:
            raise ValueError("adapter limits must be positive")
        for key, value in self.environment.items():
            if not key or "=" in key or "\x00" in key or "\x00" in value:
                raise ValueError("invalid adapter environment entry")
            normalized_key = key.upper()
            if (
                normalized_key in _DANGEROUS_ENVIRONMENT_KEYS
                or normalized_key.startswith(("LD_", "DYLD_", "PYTHON"))
                or any(marker in normalized_key for marker in _SECRET_ENVIRONMENT_MARKERS)
            ):
                raise ValueError(
                    f"adapter environment entry is forbidden: {key}"
                )

    @property
    def identity_digest(self) -> str:
        return _digest(
            {
                "adapter_id": self.adapter_id,
                "version": self.version,
                "executable": self.executable,
                "executable_sha256": self.executable_sha256,
                "capabilities": sorted(self.capabilities),
                "required_authority": sorted(self.required_authority),
                "arguments": list(self.arguments),
                "environment": dict(sorted(self.environment.items())),
                "limits": [
                    self.max_timeout_seconds,
                    self.max_input_bytes,
                    self.max_output_bytes,
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class AdapterInvocation:
    adapter_id: str
    capability: str
    payload: Mapping[str, Any]
    requested_authority: tuple[str, ...] = ()
    timeout_seconds: float = 30.0
    request_id: str = ""

    @property
    def request_digest(self) -> str:
        return _digest(
            {
                "adapter_id": self.adapter_id,
                "capability": self.capability,
                "payload": self.payload,
                "requested_authority": sorted(self.requested_authority),
                "request_id": self.request_id,
            }
        )


@dataclass(frozen=True, slots=True)
class AdapterResult:
    status: AdapterStatus
    adapter_id: str
    capability: str
    request_digest: str
    manifest_digest: str | None
    executable_digest: str | None
    output: Mapping[str, Any] | None
    reason: str
    elapsed_ms: int
    exit_code: int | None = None
    runtime_evidence: str = "NOT_RUN"
    sandbox_evidence: str = "NOT_RUN"
    network_isolation: str = "NOT_RUN"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "adapter_id": self.adapter_id,
            "capability": self.capability,
            "request_digest": self.request_digest,
            "manifest_digest": self.manifest_digest,
            "executable_digest": self.executable_digest,
            "output": dict(self.output) if self.output is not None else None,
            "reason": self.reason,
            "elapsed_ms": self.elapsed_ms,
            "exit_code": self.exit_code,
            "runtime_evidence": self.runtime_evidence,
            "sandbox_evidence": self.sandbox_evidence,
            "network_isolation": self.network_isolation,
        }


class AdapterRegistry:
    def __init__(
        self,
        manifests: Sequence[AdapterManifest] = (),
        *,
        runtime_mode: str = "production",
    ) -> None:
        if runtime_mode not in {"local-engineering", "production"}:
            raise ValueError("invalid adapter runtime mode")
        self._manifests: dict[str, AdapterManifest] = {}
        self.runtime_mode = runtime_mode
        for manifest in manifests:
            self.register(manifest)

    def register(self, manifest: AdapterManifest) -> None:
        existing = self._manifests.get(manifest.adapter_id)
        if existing is not None and existing.identity_digest != manifest.identity_digest:
            raise ValueError(f"adapter id already registered with different identity: {manifest.adapter_id}")
        self._manifests[manifest.adapter_id] = manifest

    def manifests(self) -> tuple[AdapterManifest, ...]:
        return tuple(self._manifests[key] for key in sorted(self._manifests))

    def capability_matrix(self) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        registered = {
            capability: manifest
            for manifest in self._manifests.values()
            for capability in manifest.capabilities
        }
        for language, spec in sorted(DEFAULT_CAPABILITY_SPECS.items()):
            manifest = registered.get(spec.capability)
            rows.append(
                {
                    "language": language,
                    "capability": spec.capability,
                    "required_provider": spec.provider,
                    "authoritative_requirement": spec.authoritative_requirement,
                    "adapter_id": manifest.adapter_id if manifest else None,
                    "state": AdapterStatus.NOT_RUN.value if manifest else AdapterStatus.UNSUPPORTED.value,
                }
            )
        return tuple(rows)

    def invoke(
        self,
        invocation: AdapterInvocation,
        *,
        caller_authority: Sequence[str] = (),
        cancel_event: threading.Event | None = None,
        workspace: str | os.PathLike[str] | None = None,
    ) -> AdapterResult:
        started = time.monotonic()
        manifest = self._manifests.get(invocation.adapter_id)
        if manifest is None:
            return _result(AdapterStatus.UNSUPPORTED, invocation, None, None, "adapter is not registered", started)
        if invocation.capability not in manifest.capabilities:
            return _result(AdapterStatus.UNSUPPORTED, invocation, manifest, None, "adapter does not declare the requested capability", started)
        requested = tuple(sorted(set(invocation.requested_authority)))
        required = tuple(sorted(manifest.required_authority))
        if requested != required:
            return _result(AdapterStatus.DENIED, invocation, manifest, None, "requested authority must exactly match the manifest", started)
        if not set(required).issubset(set(caller_authority)):
            return _result(AdapterStatus.DENIED, invocation, manifest, None, "caller lacks required adapter authority", started)
        if invocation.timeout_seconds <= 0 or invocation.timeout_seconds > manifest.max_timeout_seconds:
            return _result(AdapterStatus.DENIED, invocation, manifest, None, "timeout exceeds the manifest limit", started)
        if self.runtime_mode == "production":
            return _result(
                AdapterStatus.NOT_RUN,
                invocation,
                manifest,
                None,
                "unsandboxed local adapter execution is disabled in production mode",
                started,
            )
        if (
            os.name != "posix"
            or not getattr(os, "O_NOFOLLOW", 0)
            or not Path("/dev/fd").is_dir()
        ):
            return _result(
                AdapterStatus.NOT_RUN,
                invocation,
                manifest,
                None,
                "inherited /dev/fd executable binding is unavailable on this platform",
                started,
            )
        executable_fd: int | None = None
        workspace_fd: int | None = None
        try:
            executable_fd = os.open(
                manifest.executable,
                os.O_RDONLY | os.O_NOFOLLOW,
            )
        except FileNotFoundError:
            return _result(AdapterStatus.NOT_RUN, invocation, manifest, None, "adapter executable is unavailable", started)
        except OSError as exc:
            return _result(
                AdapterStatus.NOT_RUN,
                invocation,
                manifest,
                None,
                f"adapter executable cannot be opened safely: {exc}",
                started,
            )
        try:
            executable_before = os.fstat(executable_fd)
            if (
                not stat.S_ISREG(executable_before.st_mode)
                or not executable_before.st_mode & 0o111
            ):
                return _result(
                    AdapterStatus.NOT_RUN,
                    invocation,
                    manifest,
                    None,
                    "adapter executable must be an executable regular file",
                    started,
                )
            executable_digest = _fd_digest(executable_fd)
            executable_verified = os.fstat(executable_fd)
            executable_identity = _file_identity(executable_before)
            if executable_identity != _file_identity(executable_verified):
                return _result(
                    AdapterStatus.NOT_RUN,
                    invocation,
                    manifest,
                    executable_digest,
                    "adapter executable changed while hashing",
                    started,
                )
            if executable_digest != manifest.executable_sha256:
                return _result(
                    AdapterStatus.NOT_RUN,
                    invocation,
                    manifest,
                    executable_digest,
                    "adapter executable digest mismatch",
                    started,
                )
            working_directory: str | None = None
            if workspace is not None:
                workspace_flags = (
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | os.O_NOFOLLOW
                )
                try:
                    workspace_fd = os.open(workspace, workspace_flags)
                except FileNotFoundError:
                    return _result(
                        AdapterStatus.NOT_RUN,
                        invocation,
                        manifest,
                        executable_digest,
                        "workspace is unavailable",
                        started,
                    )
                except OSError as exc:
                    return _result(
                        AdapterStatus.DENIED,
                        invocation,
                        manifest,
                        executable_digest,
                        f"workspace cannot be opened safely: {exc}",
                        started,
                    )
                if not stat.S_ISDIR(os.fstat(workspace_fd).st_mode):
                    return _result(
                        AdapterStatus.DENIED,
                        invocation,
                        manifest,
                        executable_digest,
                        "workspace must be a non-symlink directory",
                        started,
                    )
                working_directory = f"/dev/fd/{workspace_fd}"
            wire = json.dumps(
                {
                    "api_version": "elmos.ai/v3",
                    "adapter_id": manifest.adapter_id,
                    "manifest_digest": manifest.identity_digest,
                    "capability": invocation.capability,
                    "request_digest": invocation.request_digest,
                    "payload": invocation.payload,
                    "authority": list(requested),
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            if len(wire) > manifest.max_input_bytes:
                return _result(
                    AdapterStatus.DENIED,
                    invocation,
                    manifest,
                    executable_digest,
                    "adapter input exceeds max_input_bytes",
                    started,
                )
            environment = {
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": "/usr/bin:/bin",
                "TZ": "UTC",
                **manifest.environment,
            }
            executable_reference = f"/dev/fd/{executable_fd}"
            inherited_fds = tuple(
                descriptor
                for descriptor in (executable_fd, workspace_fd)
                if descriptor is not None
            )
            with (
                tempfile.TemporaryFile() as stdin_file,
                tempfile.TemporaryFile() as stdout_file,
                tempfile.TemporaryFile() as stderr_file,
            ):
                stdin_file.write(wire)
                stdin_file.seek(0)
                try:
                    process = subprocess.Popen(
                        [executable_reference, *manifest.arguments],
                        executable=executable_reference,
                        stdin=stdin_file,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        cwd=working_directory,
                        env=environment,
                        shell=False,
                        close_fds=True,
                        pass_fds=inherited_fds,
                        start_new_session=True,
                    )
                except OSError as exc:
                    return _result(
                        AdapterStatus.NOT_RUN,
                        invocation,
                        manifest,
                        executable_digest,
                        f"adapter could not start through the verified FD: {exc}",
                        started,
                    )
                if not _executable_binding_stable(
                    manifest.executable,
                    executable_fd,
                    executable_identity,
                ):
                    _stop_process(process)
                    return _result(
                        AdapterStatus.NOT_RUN,
                        invocation,
                        manifest,
                        executable_digest,
                        "adapter executable identity changed before execution",
                        started,
                        exit_code=process.returncode,
                        executed=True,
                    )
                deadline = started + invocation.timeout_seconds
                status: AdapterStatus | None = None
                reason = ""
                while process.poll() is None:
                    if cancel_event is not None and cancel_event.is_set():
                        status, reason = AdapterStatus.CANCELLED, "adapter invocation cancelled"
                        _stop_process(process)
                        break
                    if time.monotonic() >= deadline:
                        status, reason = AdapterStatus.TIMED_OUT, "adapter invocation timed out"
                        _stop_process(process)
                        break
                    if (
                        os.fstat(stdout_file.fileno()).st_size
                        > manifest.max_output_bytes
                        or os.fstat(stderr_file.fileno()).st_size
                        > manifest.max_output_bytes
                    ):
                        status, reason = (
                            AdapterStatus.FAILED,
                            "adapter output exceeds max_output_bytes",
                        )
                        _stop_process(process)
                        break
                    time.sleep(0.01)
                exit_code = process.wait()
                if not _executable_binding_stable(
                    manifest.executable,
                    executable_fd,
                    executable_identity,
                ):
                    return _result(
                        AdapterStatus.FAILED,
                        invocation,
                        manifest,
                        executable_digest,
                        "adapter executable identity changed during execution",
                        started,
                        exit_code=exit_code,
                        executed=True,
                    )
                if status is not None:
                    return _result(
                        status,
                        invocation,
                        manifest,
                        executable_digest,
                        reason,
                        started,
                        exit_code=exit_code,
                        executed=True,
                    )
                stdout_file.seek(0)
                stderr_file.seek(0)
                output_bytes = stdout_file.read(manifest.max_output_bytes + 1)
                stderr_bytes = stderr_file.read(
                    min(manifest.max_output_bytes, 16 * 1024)
                )
                if len(output_bytes) > manifest.max_output_bytes:
                    return _result(
                        AdapterStatus.FAILED,
                        invocation,
                        manifest,
                        executable_digest,
                        "adapter output exceeds max_output_bytes",
                        started,
                        exit_code=exit_code,
                        executed=True,
                    )
                if exit_code != 0:
                    detail = stderr_bytes.decode("utf-8", errors="replace")
                    return _result(
                        AdapterStatus.FAILED,
                        invocation,
                        manifest,
                        executable_digest,
                        f"adapter exited {exit_code}: {detail[:1000]}",
                        started,
                        exit_code=exit_code,
                        executed=True,
                    )
                try:
                    output = json.loads(output_bytes.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    return _result(
                        AdapterStatus.FAILED,
                        invocation,
                        manifest,
                        executable_digest,
                        f"adapter returned invalid JSON: {exc}",
                        started,
                        exit_code=exit_code,
                        executed=True,
                    )
                if not isinstance(output, Mapping):
                    return _result(
                        AdapterStatus.FAILED,
                        invocation,
                        manifest,
                        executable_digest,
                        "adapter output must be an object",
                        started,
                        exit_code=exit_code,
                        executed=True,
                    )
                if output.get("request_digest") != invocation.request_digest:
                    return _result(
                        AdapterStatus.FAILED,
                        invocation,
                        manifest,
                        executable_digest,
                        "adapter output is not bound to the request digest",
                        started,
                        exit_code=exit_code,
                        executed=True,
                    )
                return AdapterResult(
                    AdapterStatus.SUCCEEDED,
                    invocation.adapter_id,
                    invocation.capability,
                    invocation.request_digest,
                    manifest.identity_digest,
                    executable_digest,
                    dict(output),
                    "",
                    int((time.monotonic() - started) * 1000),
                    exit_code,
                    "LOCAL_EXECUTED_SELF_ATTESTED",
                    "NOT_RUN",
                    "NOT_RUN",
                )
        finally:
            if workspace_fd is not None:
                os.close(workspace_fd)
            if executable_fd is not None:
                os.close(executable_fd)


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=1)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass


def _fd_digest(descriptor: int) -> str:
    hasher = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        hasher.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return hasher.hexdigest()


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _executable_binding_stable(
    path: str,
    descriptor: int,
    expected: tuple[int, int, int, int, int],
) -> bool:
    try:
        descriptor_identity = _file_identity(os.fstat(descriptor))
        path_identity = _file_identity(os.stat(path, follow_symlinks=False))
    except OSError:
        return False
    return descriptor_identity == expected and path_identity == expected


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _result(
    status: AdapterStatus,
    invocation: AdapterInvocation,
    manifest: AdapterManifest | None,
    executable_digest: str | None,
    reason: str,
    started: float,
    *,
    exit_code: int | None = None,
    executed: bool = False,
) -> AdapterResult:
    return AdapterResult(
        status,
        invocation.adapter_id,
        invocation.capability,
        invocation.request_digest,
        manifest.identity_digest if manifest else None,
        executable_digest,
        None,
        reason,
        int((time.monotonic() - started) * 1000),
        exit_code,
        "LOCAL_EXECUTED_SELF_ATTESTED" if executed else "NOT_RUN",
        "NOT_RUN",
        "NOT_RUN",
    )


__all__ = [
    "AdapterInvocation",
    "AdapterManifest",
    "AdapterRegistry",
    "AdapterResult",
    "AdapterStatus",
    "CapabilityAdapterSpec",
    "DECLARED_ADAPTER_REGISTRY",
    "DEFAULT_CAPABILITY_SPECS",
    "DeclaredAdapterDescriptor",
    "HARNESS_ADAPTER_REGISTRY",
    "VERIFIER_ADAPTER_REGISTRY",
]
