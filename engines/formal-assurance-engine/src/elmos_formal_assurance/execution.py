from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol

try:  # pragma: no cover - POSIX is used in production and CI
    import resource
except ImportError:  # pragma: no cover
    resource = None  # type: ignore[assignment]

from .artifact_store import ContentAddressedArtifactStore
from .canonical import canonical_json, digest_bytes, digest_value, validate_digest, validate_identifier
from .contracts import AssuranceLevel, ProofStatus, Scope, TrustedIdentity, utc_now
from .store import StateStore


class ExecutionContractError(ValueError):
    """Raised when an execution contract is malformed or crosses policy."""


class ExecutionAuthorizationError(PermissionError):
    """Raised when a native execution is not authorized by the trusted host."""


class ExecutionState(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    REFUSED = "REFUSED"
    NOT_RUN = "NOT_RUN"


class SandboxKind(StrEnum):
    LOCAL_PROCESS = "LOCAL_PROCESS"
    OCI_CONTAINER = "OCI_CONTAINER"


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    timeout_seconds: int = 60
    cpu_seconds: int = 60
    memory_bytes: int = 1024 * 1024 * 1024
    process_count: int = 64
    file_bytes: int = 16 * 1024 * 1024
    output_bytes: int = 4 * 1024 * 1024

    def __post_init__(self) -> None:
        bounds = {
            "timeout_seconds": (self.timeout_seconds, 1, 3600),
            "cpu_seconds": (self.cpu_seconds, 1, 3600),
            "memory_bytes": (self.memory_bytes, 64 * 1024 * 1024, 32 * 1024**3),
            "process_count": (self.process_count, 1, 1024),
            "file_bytes": (self.file_bytes, 1024, 256 * 1024 * 1024),
            "output_bytes": (self.output_bytes, 1024, 64 * 1024 * 1024),
        }
        for name, (value, minimum, maximum) in bounds.items():
            if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
                raise ExecutionContractError(f"{name} must be between {minimum} and {maximum}")

    def constrained(self, requested_timeout: int) -> ResourceLimits:
        if not isinstance(requested_timeout, int) or isinstance(requested_timeout, bool):
            raise ExecutionContractError("productionExecution.timeoutSeconds must be an integer")
        if requested_timeout < 1 or requested_timeout > self.timeout_seconds:
            raise ExecutionContractError("requested timeout exceeds the host execution policy")
        return ResourceLimits(
            timeout_seconds=requested_timeout,
            cpu_seconds=min(self.cpu_seconds, requested_timeout),
            memory_bytes=self.memory_bytes,
            process_count=self.process_count,
            file_bytes=self.file_bytes,
            output_bytes=self.output_bytes,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "timeoutSeconds": self.timeout_seconds,
            "cpuSeconds": self.cpu_seconds,
            "memoryBytes": self.memory_bytes,
            "processCount": self.process_count,
            "fileBytes": self.file_bytes,
            "outputBytes": self.output_bytes,
        }


def _sha256_file(path: Path, maximum: int = 1024 * 1024 * 1024) -> str:
    if path.is_symlink() or not path.is_file():
        raise ExecutionContractError(f"toolchain path is missing or unsafe: {path}")
    size = path.stat().st_size
    if size < 1 or size > maximum:
        raise ExecutionContractError(f"toolchain file size is outside policy: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


@dataclass(frozen=True, slots=True)
class TrustedToolFile:
    path: Path
    sha256: str

    def __post_init__(self) -> None:
        resolved = self.path.expanduser().resolve(strict=True)
        object.__setattr__(self, "path", resolved)
        expected = validate_digest(self.sha256, "trustedToolFile.sha256")
        object.__setattr__(self, "sha256", expected)
        if _sha256_file(resolved) != expected:
            raise ExecutionContractError(f"trusted tool file digest mismatch: {resolved}")


_ENVIRONMENT_KEY = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")


@dataclass(frozen=True, slots=True)
class ToolchainRegistration:
    """Host-owned, digest-pinned registration; request data cannot create one."""

    adapter_id: str
    executable: Path
    executable_sha256: str
    version_args: tuple[str, ...] = ("--version",)
    version_pattern: str = ".+"
    fixed_args: tuple[str, ...] = ()
    environment: Mapping[str, str] = field(default_factory=dict)
    trusted_files: tuple[TrustedToolFile, ...] = ()
    sandbox_kind: SandboxKind = SandboxKind.LOCAL_PROCESS
    container_image: str | None = None
    container_executable: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.adapter_id, "toolchain.adapterId")
        executable = self.executable.expanduser().resolve(strict=True)
        object.__setattr__(self, "executable", executable)
        expected = validate_digest(self.executable_sha256, "toolchain.executableSha256")
        object.__setattr__(self, "executable_sha256", expected)
        if _sha256_file(executable) != expected:
            raise ExecutionContractError(f"toolchain executable digest mismatch: {self.adapter_id}")
        try:
            re.compile(self.version_pattern)
        except re.error as exc:
            raise ExecutionContractError("toolchain versionPattern is invalid") from exc
        for value in (*self.version_args, *self.fixed_args):
            if not isinstance(value, str) or not value or "\x00" in value or "\n" in value or "\r" in value:
                raise ExecutionContractError("toolchain arguments must be non-empty single-line strings")
        trusted_paths = {item.path for item in self.trusted_files}
        for value in self.fixed_args:
            if Path(value).is_absolute() and Path(value).resolve() not in trusted_paths:
                raise ExecutionContractError(
                    f"absolute fixed argument is not digest-bound: {value}"
                )
        for key, value in self.environment.items():
            if not isinstance(key, str) or not _ENVIRONMENT_KEY.fullmatch(key):
                raise ExecutionContractError(f"invalid host environment key: {key}")
            if not isinstance(value, str) or "\x00" in value:
                raise ExecutionContractError(f"invalid host environment value: {key}")
        if self.sandbox_kind == SandboxKind.OCI_CONTAINER:
            if not isinstance(self.container_image, str) or not re.fullmatch(
                r"[^\s@]+@sha256:[0-9a-f]{64}", self.container_image
            ):
                raise ExecutionContractError("OCI toolchain image must be digest pinned")
            if not isinstance(self.container_executable, str) or not self.container_executable.startswith("/"):
                raise ExecutionContractError("OCI container executable must be an absolute path")
        elif self.container_image is not None or self.container_executable is not None:
            raise ExecutionContractError("container fields require OCI_CONTAINER sandboxKind")

    @property
    def identity_digest(self) -> str:
        return digest_value(
            {
                "adapterId": self.adapter_id,
                "executableSha256": self.executable_sha256,
                "versionArgs": self.version_args,
                "versionPattern": self.version_pattern,
                "fixedArgs": self.fixed_args,
                "environment": {key: digest_bytes(value.encode("utf-8")) for key, value in sorted(self.environment.items())},
                "trustedFiles": [
                    {"path": item.path.name, "sha256": item.sha256}
                    for item in self.trusted_files
                ],
                "sandboxKind": self.sandbox_kind.value,
                "containerImage": self.container_image,
                "containerExecutable": self.container_executable,
            }
        )

    def verify_integrity(self) -> None:
        if _sha256_file(self.executable) != self.executable_sha256:
            raise ExecutionContractError(f"toolchain executable drift: {self.adapter_id}")
        for item in self.trusted_files:
            if _sha256_file(item.path) != item.sha256:
                raise ExecutionContractError(f"trusted tool file drift: {item.path}")

    @classmethod
    def from_dict(cls, value: Any) -> ToolchainRegistration:
        if not isinstance(value, dict):
            raise ExecutionContractError("toolchain registration must be an object")
        allowed = {
            "adapterId",
            "executable",
            "executableSha256",
            "versionArgs",
            "versionPattern",
            "fixedArgs",
            "environment",
            "trustedFiles",
            "sandboxKind",
            "containerImage",
            "containerExecutable",
        }
        extra = set(value) - allowed
        required = {"adapterId", "executable", "executableSha256"}
        missing = required - set(value)
        if extra or missing:
            raise ExecutionContractError(
                f"toolchain fields mismatch; missing={sorted(missing)} extra={sorted(extra)}"
            )
        trusted = value.get("trustedFiles", [])
        if not isinstance(trusted, list):
            raise ExecutionContractError("toolchain.trustedFiles must be an array")
        trusted_files: list[TrustedToolFile] = []
        for item in trusted:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                raise ExecutionContractError("trusted tool file entry is invalid")
            trusted_files.append(TrustedToolFile(Path(item["path"]), item["sha256"]))
        environment = value.get("environment", {})
        if not isinstance(environment, dict):
            raise ExecutionContractError("toolchain.environment must be an object")
        try:
            sandbox_kind = SandboxKind(value.get("sandboxKind", "LOCAL_PROCESS"))
        except ValueError as exc:
            raise ExecutionContractError("toolchain.sandboxKind is invalid") from exc
        for field_name in ("versionArgs", "fixedArgs"):
            field_value = value.get(field_name, ["--version"] if field_name == "versionArgs" else [])
            if not isinstance(field_value, list) or any(not isinstance(item, str) for item in field_value):
                raise ExecutionContractError(f"toolchain.{field_name} must be an array of strings")
        return cls(
            adapter_id=value["adapterId"],
            executable=Path(value["executable"]),
            executable_sha256=value["executableSha256"],
            version_args=tuple(value.get("versionArgs", ["--version"])),
            version_pattern=value.get("versionPattern", ".+"),
            fixed_args=tuple(value.get("fixedArgs", [])),
            environment={str(key): str(item) for key, item in environment.items()},
            trusted_files=tuple(trusted_files),
            sandbox_kind=sandbox_kind,
            container_image=value.get("containerImage"),
            container_executable=value.get("containerExecutable"),
        )


def load_toolchain_registry(
    path: str | Path, expected_sha256: str
) -> tuple[ToolchainRegistration, ...]:
    """Load a deployment registry only when its complete bytes are pinned."""
    raw_path = Path(path).expanduser()
    if raw_path.is_symlink() or not raw_path.is_file():
        raise ExecutionContractError("toolchain registry path is unsafe")
    registry_path = raw_path.resolve(strict=True)
    expected = validate_digest(expected_sha256, "toolchainRegistrySha256")
    raw = registry_path.read_bytes()
    if len(raw) > 4 * 1024 * 1024 or digest_bytes(raw) != expected:
        raise ExecutionContractError("toolchain registry digest mismatch")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionContractError("toolchain registry is invalid JSON") from exc
    if not isinstance(document, dict) or set(document) != {"format", "toolchains"}:
        raise ExecutionContractError("toolchain registry root contract is invalid")
    if document["format"] != "elmos-formal-toolchain-registry/v1" or not isinstance(
        document["toolchains"], list
    ):
        raise ExecutionContractError("toolchain registry format is unsupported")
    registrations = tuple(
        ToolchainRegistration.from_dict(item) for item in document["toolchains"]
    )
    identifiers = [item.adapter_id for item in registrations]
    if len(identifiers) != len(set(identifiers)):
        raise ExecutionContractError("toolchain registry contains duplicate adapters")
    return registrations


@dataclass(frozen=True, slots=True)
class ExecutionPermit:
    permit_id: str
    nonce: str
    tenant_id: str
    account_id: str
    project_id: str | None
    skill_id: str
    subject_id: str
    adapter_id: str
    execution_digest: str
    source_artifact_digest: str
    target_artifact_digest: str
    environment_digest: str
    issued_at_epoch: int
    expires_at_epoch: int
    signature: str
    version: int = 1

    def __post_init__(self) -> None:
        for name, value in (
            ("permitId", self.permit_id),
            ("nonce", self.nonce),
            ("tenantId", self.tenant_id),
            ("accountId", self.account_id),
            ("skillId", self.skill_id),
            ("subjectId", self.subject_id),
            ("adapterId", self.adapter_id),
        ):
            validate_identifier(value, f"permit.{name}")
        if self.project_id is not None:
            validate_identifier(self.project_id, "permit.projectId")
        for name, value in (
            ("executionDigest", self.execution_digest),
            ("sourceArtifactDigest", self.source_artifact_digest),
            ("targetArtifactDigest", self.target_artifact_digest),
            ("environmentDigest", self.environment_digest),
        ):
            validate_digest(value, f"permit.{name}")
        if self.version != 1:
            raise ExecutionContractError("unsupported execution permit version")
        if not isinstance(self.issued_at_epoch, int) or isinstance(self.issued_at_epoch, bool):
            raise ExecutionContractError("permit.issuedAtEpoch must be an integer")
        if not isinstance(self.expires_at_epoch, int) or isinstance(self.expires_at_epoch, bool):
            raise ExecutionContractError("permit.expiresAtEpoch must be an integer")
        if self.expires_at_epoch <= self.issued_at_epoch:
            raise ExecutionContractError("execution permit expiry must follow issue time")
        if not re.fullmatch(r"hmac-sha256:[0-9a-f]{64}", self.signature):
            raise ExecutionContractError("execution permit signature is invalid")

    def signed_document(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "permitId": self.permit_id,
            "nonce": self.nonce,
            "tenantId": self.tenant_id,
            "accountId": self.account_id,
            "projectId": self.project_id,
            "skillId": self.skill_id,
            "subjectId": self.subject_id,
            "adapterId": self.adapter_id,
            "executionDigest": self.execution_digest,
            "sourceArtifactDigest": self.source_artifact_digest,
            "targetArtifactDigest": self.target_artifact_digest,
            "environmentDigest": self.environment_digest,
            "issuedAtEpoch": self.issued_at_epoch,
            "expiresAtEpoch": self.expires_at_epoch,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.signed_document(), "signature": self.signature}

    @classmethod
    def from_dict(cls, value: Any) -> ExecutionPermit:
        if not isinstance(value, dict):
            raise ExecutionContractError("productionExecution.permit must be an object")
        expected = {
            "version", "permitId", "nonce", "tenantId", "accountId", "projectId",
            "skillId", "subjectId", "adapterId", "executionDigest",
            "sourceArtifactDigest", "targetArtifactDigest", "environmentDigest",
            "issuedAtEpoch", "expiresAtEpoch", "signature",
        }
        extra = set(value) - expected
        missing = expected - set(value)
        if extra or missing:
            raise ExecutionContractError(
                f"execution permit fields mismatch; missing={sorted(missing)} extra={sorted(extra)}"
            )
        return cls(
            permit_id=value["permitId"], nonce=value["nonce"], tenant_id=value["tenantId"],
            account_id=value["accountId"], project_id=value["projectId"], skill_id=value["skillId"],
            subject_id=value["subjectId"], adapter_id=value["adapterId"],
            execution_digest=value["executionDigest"], source_artifact_digest=value["sourceArtifactDigest"],
            target_artifact_digest=value["targetArtifactDigest"], environment_digest=value["environmentDigest"],
            issued_at_epoch=value["issuedAtEpoch"], expires_at_epoch=value["expiresAtEpoch"],
            signature=value["signature"], version=value["version"],
        )


class ExecutionPermitSigner:
    """HMAC permit authority for one deployment trust domain.

    It authorizes execution only. It is deliberately not an independent proof
    verifier or certification signer.
    """

    def __init__(self, secret: bytes) -> None:
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ExecutionContractError("execution permit key must contain at least 32 bytes")
        self._secret = bytes(secret)

    def _signature(self, document: Mapping[str, Any]) -> str:
        value = hmac.new(self._secret, canonical_json(document), hashlib.sha256).hexdigest()
        return "hmac-sha256:" + value

    def issue(
        self,
        *,
        permit_id: str,
        nonce: str,
        scope: Scope,
        skill_id: str,
        subject_id: str,
        adapter_id: str,
        execution_digest: str,
        ttl_seconds: int = 300,
        now_epoch: int | None = None,
    ) -> ExecutionPermit:
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        if not 1 <= ttl_seconds <= 3600:
            raise ExecutionContractError("execution permit ttl must be between 1 and 3600 seconds")
        unsigned = ExecutionPermit(
            permit_id=permit_id, nonce=nonce, tenant_id=scope.tenant_id,
            account_id=scope.account_id, project_id=scope.project_id, skill_id=skill_id,
            subject_id=subject_id, adapter_id=adapter_id, execution_digest=execution_digest,
            source_artifact_digest=scope.source_artifact_digest,
            target_artifact_digest=scope.target_artifact_digest,
            environment_digest=scope.environment_digest, issued_at_epoch=now,
            expires_at_epoch=now + ttl_seconds,
            signature="hmac-sha256:" + "0" * 64,
        )
        return replace(
            unsigned, signature=self._signature(unsigned.signed_document())
        )

    def verify(
        self,
        permit: ExecutionPermit,
        *,
        scope: Scope,
        identity: TrustedIdentity,
        skill_id: str,
        subject_id: str,
        adapter_id: str,
        execution_digest: str,
        now_epoch: int | None = None,
    ) -> None:
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        expected = self._signature(permit.signed_document())
        if not hmac.compare_digest(expected, permit.signature):
            raise ExecutionAuthorizationError("execution permit signature verification failed")
        actual = (
            permit.tenant_id, permit.account_id, permit.project_id, permit.skill_id,
            permit.subject_id, permit.adapter_id, permit.execution_digest,
            permit.source_artifact_digest, permit.target_artifact_digest, permit.environment_digest,
        )
        required = (
            scope.tenant_id, scope.account_id, scope.project_id, skill_id, subject_id,
            adapter_id, execution_digest, scope.source_artifact_digest,
            scope.target_artifact_digest, scope.environment_digest,
        )
        if actual != required:
            raise ExecutionAuthorizationError("execution permit is not bound to this exact request scope")
        if identity.tenant_id != scope.tenant_id or identity.project_id != scope.project_id:
            raise ExecutionAuthorizationError("trusted identity is not bound to the execution scope")
        if not ({"formal-assurance:execute", "formal-assurance:admin"} & set(identity.roles)):
            raise ExecutionAuthorizationError("trusted identity lacks formal-assurance execution role")
        if permit.issued_at_epoch > now + 30:
            raise ExecutionAuthorizationError("execution permit issue time is in the future")
        if permit.expires_at_epoch < now:
            raise ExecutionAuthorizationError("execution permit has expired")


def execution_binding_digest(
    scope: Scope,
    skill_id: str,
    subject_id: str,
    production_execution: Mapping[str, Any],
) -> str:
    if not isinstance(production_execution, Mapping):
        raise ExecutionContractError("productionExecution must be an object")
    unsigned = dict(production_execution)
    unsigned.pop("permit", None)
    return digest_value(
        {
            "contract": "elmos-formal-native-execution/v1",
            "scope": scope.to_dict(),
            "skillId": validate_identifier(skill_id, "skillId"),
            "subjectId": validate_identifier(subject_id, "subjectId"),
            "execution": unsigned,
        }
    )


def _safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 512:
        raise ExecutionContractError("execution file path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ExecutionContractError(f"execution file path escapes workspace: {value}")
    if any("\x00" in part or part.startswith(".git") for part in path.parts):
        raise ExecutionContractError(f"execution file path is forbidden: {value}")
    return path.as_posix()


@dataclass(frozen=True, slots=True)
class ExecutionFile:
    path: str
    data: bytes

    @classmethod
    def parse_many(cls, value: Any, maximum_bytes: int) -> tuple[ExecutionFile, ...]:
        if not isinstance(value, dict) or not value:
            raise ExecutionContractError("productionExecution.files must be a non-empty object")
        if len(value) > 512:
            raise ExecutionContractError("productionExecution.files exceeds the file-count bound")
        files: list[ExecutionFile] = []
        total = 0
        for raw_path, raw_content in value.items():
            path = _safe_relative_path(raw_path)
            if isinstance(raw_content, str):
                data = raw_content.encode("utf-8")
            elif isinstance(raw_content, dict) and set(raw_content) == {"encoding", "data"} and raw_content.get("encoding") == "base64":
                try:
                    data = base64.b64decode(raw_content.get("data", ""), validate=True)
                except (binascii.Error, ValueError, TypeError) as exc:
                    raise ExecutionContractError(f"invalid base64 execution file: {path}") from exc
            else:
                raise ExecutionContractError(f"execution file {path} must be UTF-8 text or explicit base64")
            total += len(data)
            if total > maximum_bytes:
                raise ExecutionContractError("execution files exceed the host byte bound")
            files.append(cls(path, data))
        paths = [item.path for item in files]
        if len(paths) != len(set(paths)):
            raise ExecutionContractError("execution file paths must be unique")
        return tuple(sorted(files, key=lambda item: item.path))


@dataclass(frozen=True, slots=True)
class NativeExecutionRequest:
    adapter_id: str
    files: tuple[ExecutionFile, ...]
    options: Mapping[str, Any]
    query_semantics: str
    timeout_seconds: int
    permit: ExecutionPermit
    binding_digest: str

    @classmethod
    def from_payload(
        cls,
        value: Any,
        *,
        scope: Scope,
        skill_id: str,
        subject_id: str,
        limits: ResourceLimits,
    ) -> NativeExecutionRequest:
        if not isinstance(value, dict):
            raise ExecutionContractError("productionExecution must be an object")
        allowed = {"adapterId", "files", "options", "querySemantics", "timeoutSeconds", "permit"}
        extra = set(value) - allowed
        missing = {"adapterId", "files", "querySemantics", "permit"} - set(value)
        if extra or missing:
            raise ExecutionContractError(
                f"productionExecution fields mismatch; missing={sorted(missing)} extra={sorted(extra)}"
            )
        adapter_id = validate_identifier(value["adapterId"], "productionExecution.adapterId")
        options = value.get("options", {})
        if not isinstance(options, dict) or len(canonical_json(options)) > 1024 * 1024:
            raise ExecutionContractError("productionExecution.options must be a bounded object")
        query_semantics = value["querySemantics"]
        if query_semantics not in {"COUNTEREXAMPLE_SEARCH", "PROOF_CHECK", "DIFFERENTIAL_EXECUTION", "BOUNDARY_INVENTORY"}:
            raise ExecutionContractError("productionExecution.querySemantics is invalid")
        timeout = value.get("timeoutSeconds", limits.timeout_seconds)
        constrained = limits.constrained(timeout)
        binding = execution_binding_digest(scope, skill_id, subject_id, value)
        return cls(
            adapter_id=adapter_id,
            files=ExecutionFile.parse_many(value["files"], constrained.file_bytes),
            options=options,
            query_semantics=query_semantics,
            timeout_seconds=timeout,
            permit=ExecutionPermit.from_dict(value["permit"]),
            binding_digest=binding,
        )


@dataclass(frozen=True, slots=True)
class AdapterDefinition:
    adapter_id: str
    required_files: tuple[str, ...]
    allowed_suffixes: tuple[str, ...]
    argv: tuple[str, ...]
    parser: str
    assurance_level: AssuranceLevel
    requires_strong_sandbox: bool = False
    accepted_semantics: tuple[str, ...] = ("COUNTEREXAMPLE_SEARCH", "PROOF_CHECK")

    def validate_request(self, request: NativeExecutionRequest) -> None:
        paths = {item.path for item in request.files}
        missing = set(self.required_files) - paths
        if missing:
            raise ExecutionContractError(f"{self.adapter_id} is missing required files: {sorted(missing)}")
        if any(not path.endswith(self.allowed_suffixes) for path in paths):
            raise ExecutionContractError(f"{self.adapter_id} received an unsupported file type")
        if request.query_semantics not in self.accepted_semantics:
            raise ExecutionContractError(f"{self.adapter_id} does not support {request.query_semantics}")


ADAPTERS: dict[str, AdapterDefinition] = {
    "alive2": AdapterDefinition("alive2", ("source.ll", "target.ll"), (".ll",), ("source.ll", "target.ll"), "alive2", AssuranceLevel.A2_SOLVER_PROVED),
    "alloy": AdapterDefinition("alloy", ("model.als",), (".als",), ("exec", "model.als"), "alloy", AssuranceLevel.A1_BOUNDED),
    "apalache": AdapterDefinition("apalache", ("Model.tla", "apalache.cfg"), (".tla", ".cfg"), ("check", "--config=apalache.cfg", "Model.tla"), "apalache", AssuranceLevel.A1_BOUNDED),
    "boogie": AdapterDefinition("boogie", ("input.bpl",), (".bpl",), ("input.bpl",), "boogie", AssuranceLevel.A2_SOLVER_PROVED),
    "cvc5": AdapterDefinition("cvc5", ("input.smt2",), (".smt2",), ("--lang=smt2", "input.smt2"), "smt", AssuranceLevel.A2_SOLVER_PROVED),
    "dafny": AdapterDefinition("dafny", ("input.dfy",), (".dfy",), ("verify", "input.dfy"), "dafny", AssuranceLevel.A2_SOLVER_PROVED),
    "frama-c": AdapterDefinition("frama-c", ("input.c",), (".c", ".h"), ("-wp", "-wp-rte", "input.c"), "frama-c", AssuranceLevel.A2_SOLVER_PROVED),
    "jpf": AdapterDefinition("jpf", ("model.jpf",), (".jpf", ".java", ".class"), ("model.jpf",), "jpf", AssuranceLevel.A1_BOUNDED, True),
    "k-framework": AdapterDefinition("k-framework", ("program.ir", "definition/manifest.json"), (".ir", ".json", ".kompiled", ".bin"), ("program.ir", "--definition", "definition"), "expected-digest", AssuranceLevel.A1_BOUNDED, True, ("DIFFERENTIAL_EXECUTION", "PROOF_CHECK")),
    "kani": AdapterDefinition("kani", ("Cargo.toml", "src/lib.rs"), (".toml", ".rs", ".lock"), ("kani", "--harness", "elmos_proof"), "kani", AssuranceLevel.A1_BOUNDED, True),
    "key": AdapterDefinition("key", ("input.key",), (".key", ".java"), ("--auto", "input.key"), "key", AssuranceLevel.A2_SOLVER_PROVED, True),
    "lean": AdapterDefinition("lean", ("Main.lean",), (".lean", ".toml", ".json"), ("env", "lean", "Main.lean"), "lean", AssuranceLevel.A2_SOLVER_PROVED, True),
    "openjml": AdapterDefinition("openjml", ("Input.java",), (".java",), ("--esc", "Input.java"), "openjml", AssuranceLevel.A2_SOLVER_PROVED, True),
    "sqlsolver": AdapterDefinition("sqlsolver", ("source.sql", "target.sql", "schema.sql"), (".sql",), ("--source", "source.sql", "--target", "target.sql", "--schema", "schema.sql"), "equivalence", AssuranceLevel.A2_SOLVER_PROVED),
    "tlc": AdapterDefinition("tlc", ("Model.tla", "Model.cfg"), (".tla", ".cfg"), ("-config", "Model.cfg", "Model.tla"), "tlc", AssuranceLevel.A1_BOUNDED, True),
    "verieql": AdapterDefinition("verieql", ("spec.json",), (".json", ".sql"), ("--spec", "spec.json"), "equivalence", AssuranceLevel.A2_SOLVER_PROVED, True),
    "z3": AdapterDefinition("z3", ("input.smt2",), (".smt2",), ("-smt2", "input.smt2"), "smt", AssuranceLevel.A2_SOLVER_PROVED),
    "maven-spring": AdapterDefinition("maven-spring", ("pom.xml",), (".xml", ".java", ".properties", ".yml", ".yaml", ".json", ".sql"), ("--offline", "--batch-mode", "--no-transfer-progress", "verify"), "build", AssuranceLevel.A0_TESTED, True, ("DIFFERENTIAL_EXECUTION",)),
    "gradle-spring": AdapterDefinition("gradle-spring", ("build.gradle",), (".gradle", ".java", ".kt", ".properties", ".yml", ".yaml", ".json", ".sql"), ("--offline", "--no-daemon", "check"), "build", AssuranceLevel.A0_TESTED, True, ("DIFFERENTIAL_EXECUTION",)),
    "nm": AdapterDefinition("nm", ("input.bin",), (".bin",), ("-g", "input.bin"), "symbols", AssuranceLevel.A0_TESTED, False, ("BOUNDARY_INVENTORY",)),
    "otool": AdapterDefinition("otool", ("input.bin",), (".bin",), ("-L", "input.bin"), "symbols", AssuranceLevel.A0_TESTED, False, ("BOUNDARY_INVENTORY",)),
    "readelf": AdapterDefinition("readelf", ("input.bin",), (".bin",), ("-Ws", "input.bin"), "symbols", AssuranceLevel.A0_TESTED, False, ("BOUNDARY_INVENTORY",)),
    "javap": AdapterDefinition("javap", ("Input.class",), (".class",), ("-public", "-s", "Input.class"), "symbols", AssuranceLevel.A0_TESTED, False, ("BOUNDARY_INVENTORY",)),
}


@dataclass(frozen=True, slots=True)
class ProcessExecutionResult:
    state: ExecutionState
    exit_code: int | None
    duration_ms: int
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool
    version_output: str
    containment: str
    command_digest: str


class SandboxRunner(Protocol):
    def execute(
        self,
        registration: ToolchainRegistration,
        definition: AdapterDefinition,
        workspace: Path,
        limits: ResourceLimits,
    ) -> ProcessExecutionResult: ...


def _apply_resource_limits(limits: ResourceLimits) -> None:
    if resource is None:  # pragma: no cover
        return
    for kind, value in (
        (resource.RLIMIT_CPU, limits.cpu_seconds),
        (resource.RLIMIT_AS, limits.memory_bytes),
        (resource.RLIMIT_NPROC, limits.process_count),
        (resource.RLIMIT_FSIZE, limits.output_bytes),
    ):
        try:
            resource.setrlimit(kind, (value, value))
        except (OSError, ValueError):
            continue


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            process.kill()
        except ProcessLookupError:
            pass


def _run_bounded(
    argv: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    limits: ResourceLimits,
) -> tuple[ExecutionState, int | None, bytes, bytes, bool, bool, int]:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="elmos-formal-output-") as output_dir:
        stdout_path = Path(output_dir) / "stdout.bin"
        stderr_path = Path(output_dir) / "stderr.bin"
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            try:
                process = subprocess.Popen(
                    argv,
                    cwd=cwd,
                    env=dict(env),
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    close_fds=True,
                    start_new_session=True,
                    preexec_fn=(lambda: _apply_resource_limits(limits)) if os.name == "posix" else None,
                )
            except OSError as exc:
                raise ExecutionContractError(f"unable to launch registered toolchain: {exc}") from exc
            try:
                process.wait(timeout=limits.timeout_seconds)
                state = ExecutionState.COMPLETED if process.returncode == 0 else ExecutionState.FAILED
            except subprocess.TimeoutExpired:
                _terminate_group(process)
                process.wait(timeout=5)
                state = ExecutionState.TIMED_OUT
        stdout_raw = stdout_path.read_bytes()
        stderr_raw = stderr_path.read_bytes()
    return (
        state,
        process.returncode,
        stdout_raw[: limits.output_bytes],
        stderr_raw[: limits.output_bytes],
        len(stdout_raw) > limits.output_bytes,
        len(stderr_raw) > limits.output_bytes,
        int((time.monotonic() - started) * 1000),
    )


class ControlledSandboxRunner:
    """Shell-free local and OCI runner with immutable toolchain identities."""

    def execute(
        self,
        registration: ToolchainRegistration,
        definition: AdapterDefinition,
        workspace: Path,
        limits: ResourceLimits,
    ) -> ProcessExecutionResult:
        registration.verify_integrity()
        base_env = {
            "PATH": f"{registration.executable.parent}:/usr/bin:/bin",
            "HOME": str(workspace / ".runtime-home"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
            "PYTHONHASHSEED": "0",
            "NO_PROXY": "*",
            "no_proxy": "*",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "ALL_PROXY": "",
            "ELMOS_NETWORK_POLICY": "DENY",
            **registration.environment,
        }
        (workspace / ".runtime-home").mkdir(mode=0o700)
        version_limits = ResourceLimits(
            timeout_seconds=min(10, limits.timeout_seconds), cpu_seconds=min(10, limits.cpu_seconds),
            memory_bytes=limits.memory_bytes, process_count=limits.process_count,
            file_bytes=limits.file_bytes, output_bytes=min(limits.output_bytes, 256 * 1024),
        )
        if registration.sandbox_kind == SandboxKind.LOCAL_PROCESS:
            version_argv = [str(registration.executable), *registration.version_args]
        else:
            version_argv = self._oci_argv(
                registration,
                workspace,
                limits,
                (*registration.fixed_args, *registration.version_args),
            )
        version_state, _, version_out, version_err, _, _, _ = _run_bounded(
            version_argv,
            cwd=workspace,
            env=base_env,
            limits=version_limits,
        )
        version_text = (version_out + b"\n" + version_err).decode("utf-8", errors="replace").strip()
        if version_state != ExecutionState.COMPLETED or not re.search(registration.version_pattern, version_text):
            raise ExecutionContractError(f"toolchain version probe failed: {registration.adapter_id}")

        if registration.sandbox_kind == SandboxKind.LOCAL_PROCESS:
            if definition.requires_strong_sandbox:
                raise ExecutionAuthorizationError(
                    f"{definition.adapter_id} executes project/runtime code and requires OCI_CONTAINER"
                )
            argv = [str(registration.executable), *registration.fixed_args, *definition.argv]
            containment = "PROCESS_GROUP_RLIMIT_SCRUBBED_ENV_NETWORK_NOT_KERNEL_ENFORCED"
        else:
            argv = self._oci_argv(
                registration,
                workspace,
                limits,
                (*registration.fixed_args, *definition.argv),
            )
            containment = "OCI_ROOTFS_READ_ONLY_NETWORK_NONE_CAP_DROP_ALL_NO_NEW_PRIVILEGES"
        state, exit_code, stdout, stderr, out_truncated, err_truncated, duration = _run_bounded(
            argv, cwd=workspace, env=base_env, limits=limits
        )
        return ProcessExecutionResult(
            state=state, exit_code=exit_code, duration_ms=duration, stdout=stdout, stderr=stderr,
            stdout_truncated=out_truncated, stderr_truncated=err_truncated,
            version_output=version_text,
            containment=containment,
            command_digest=digest_value(
                {
                    "adapter": definition.adapter_id,
                    "toolchain": registration.identity_digest,
                    "fixedArgv": registration.fixed_args,
                    "adapterArgv": definition.argv,
                    "sandbox": registration.sandbox_kind.value,
                }
            ),
        )

    @staticmethod
    def _oci_argv(
        registration: ToolchainRegistration,
        workspace: Path,
        limits: ResourceLimits,
        tool_args: tuple[str, ...],
    ) -> list[str]:
        return [
            str(registration.executable),
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--pids-limit={limits.process_count}",
            f"--memory={limits.memory_bytes}",
            "--cpus=1",
            "--user=65534:65534",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=256m",
            f"--volume={workspace}:/workspace:rw",
            "--workdir=/workspace",
            registration.container_image or "",
            registration.container_executable or "",
            *tool_args,
        ]


def _marker(text: str, positive: tuple[str, ...], negative: tuple[str, ...]) -> str:
    lowered = text.lower()
    if any(value.lower() in lowered for value in negative):
        return "REFUTED"
    if any(value.lower() in lowered for value in positive):
        return "PROVED"
    return "UNKNOWN"


def interpret_tool_result(
    definition: AdapterDefinition,
    request: NativeExecutionRequest,
    result: ProcessExecutionResult,
) -> tuple[ProofStatus, AssuranceLevel, tuple[str, ...], dict[str, Any] | None]:
    text = (result.stdout + b"\n" + result.stderr).decode("utf-8", errors="replace")
    diagnostics: list[str] = []
    counterexample: dict[str, Any] | None = None
    if result.state == ExecutionState.TIMED_OUT:
        return ProofStatus.UNKNOWN_TIMEOUT, AssuranceLevel.NONE, ("registered toolchain timed out",), None
    if result.stdout_truncated or result.stderr_truncated:
        return ProofStatus.UNKNOWN_RESOURCE_LIMIT, AssuranceLevel.NONE, ("tool output exceeded the evidence bound",), None

    parser = definition.parser
    verdict = "UNKNOWN"
    if parser == "smt":
        tokens = [line.strip().lower() for line in result.stdout.decode("utf-8", errors="replace").splitlines() if line.strip() and not line.lstrip().startswith(";")]
        first = tokens[0] if tokens else ""
        if first == "unsat" and request.query_semantics == "COUNTEREXAMPLE_SEARCH":
            verdict = "PROVED"
        elif first == "sat" and request.query_semantics == "COUNTEREXAMPLE_SEARCH":
            verdict = "REFUTED"
            counterexample = {"solverOutputDigest": digest_bytes(result.stdout), "modelAvailable": len(tokens) > 1}
        elif first == "sat" and request.query_semantics == "PROOF_CHECK":
            verdict = "PROVED"
        elif first == "unsat" and request.query_semantics == "PROOF_CHECK":
            verdict = "REFUTED"
            counterexample = {"solverOutputDigest": digest_bytes(result.stdout)}
    elif parser == "alive2":
        verdict = _marker(text, ("transformation seems to be correct",), ("error:", "mismatch", "counterexample"))
    elif parser == "alloy":
        lowered = text.lower()
        if "no counterexample found" in lowered or "no instance found" in lowered:
            verdict = "PROVED"
        elif "counterexample found" in lowered or "instance found" in lowered:
            verdict = "REFUTED"
    elif parser == "apalache":
        verdict = _marker(text, ("the outcome is: noerror",), ("the outcome is: error", "counterexample"))
    elif parser in {"boogie", "dafny"}:
        verdict = _marker(text, ("0 errors",), ("1 error", "2 errors", "3 errors", "assertion might not hold"))
    elif parser == "frama-c":
        verdict = _marker(text, ("proved goals: 100%",), ("unknown", "untried", "failed"))
    elif parser == "jpf":
        verdict = _marker(text, ("no errors detected",), ("error #", "property violation"))
    elif parser == "kani":
        verdict = _marker(text, ("verification result: success",), ("verification result: failure", "failed checks"))
    elif parser == "key":
        verdict = _marker(text, ("proof closed",), ("proof open", "unclosed goal"))
    elif parser == "lean":
        verdict = "PROVED" if result.state == ExecutionState.COMPLETED and result.exit_code == 0 else "UNKNOWN"
    elif parser == "openjml":
        verdict = _marker(text, ("esc: 0 warnings", "0 verification failures"), ("verification failure", "warning:"))
    elif parser == "equivalence":
        verdict = _marker(text, ("equivalent",), ("not equivalent", "counterexample"))
    elif parser == "tlc":
        verdict = _marker(text, ("model checking completed. no error has been found",), ("error: invariant", "counterexample", "behavior up to this point"))
    elif parser == "expected-digest":
        expected = request.options.get("expectedStdoutSha256")
        if expected is not None:
            expected = validate_digest(expected, "productionExecution.options.expectedStdoutSha256")
            verdict = "PROVED" if digest_bytes(result.stdout) == expected else "REFUTED"
    elif parser == "build":
        verdict = "PROVED" if result.state == ExecutionState.COMPLETED and result.exit_code == 0 else "UNKNOWN"
    elif parser == "symbols":
        verdict = "PROVED" if result.state == ExecutionState.COMPLETED and result.exit_code == 0 else "UNKNOWN"

    if result.state == ExecutionState.FAILED and verdict == "PROVED":
        verdict = "UNKNOWN"
        diagnostics.append("success marker ignored because the process exited non-zero")
    if verdict == "REFUTED":
        counterexample = counterexample or {"toolOutputDigest": digest_value({"stdout": digest_bytes(result.stdout), "stderr": digest_bytes(result.stderr)})}
        return ProofStatus.REFUTED_WITH_COUNTEREXAMPLE, AssuranceLevel.NONE, tuple(diagnostics), counterexample
    if verdict == "PROVED":
        status = (
            ProofStatus.BOUNDED_NO_COUNTEREXAMPLE
            if definition.assurance_level in {AssuranceLevel.A0_TESTED, AssuranceLevel.A1_BOUNDED}
            else ProofStatus.PROVED_SOLVER_TRUSTED
        )
        return status, definition.assurance_level, tuple(diagnostics), None
    diagnostics.append("tool output was not decisive under the registered conservative parser")
    return ProofStatus.UNSUPPORTED, AssuranceLevel.NONE, tuple(diagnostics), None


@dataclass(frozen=True, slots=True)
class NativeExecutionReceipt:
    execution_id: str
    adapter_id: str
    binding_digest: str
    toolchain_digest: str
    state: ExecutionState
    proof_status: ProofStatus
    assurance_level: AssuranceLevel
    started_at: str
    duration_ms: int
    exit_code: int | None
    containment: str
    command_digest: str
    input_manifest_digest: str
    version_output_digest: str
    artifact_refs: tuple[dict[str, Any], ...]
    diagnostics: tuple[str, ...]
    counterexample: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "elmos-formal-native-execution-receipt/v1",
            "executionId": self.execution_id,
            "adapterId": self.adapter_id,
            "bindingDigest": self.binding_digest,
            "toolchainDigest": self.toolchain_digest,
            "state": self.state.value,
            "proofStatus": self.proof_status.value,
            "assuranceLevel": self.assurance_level.value,
            "startedAt": self.started_at,
            "durationMs": self.duration_ms,
            "exitCode": self.exit_code,
            "containment": self.containment,
            "commandDigest": self.command_digest,
            "inputManifestDigest": self.input_manifest_digest,
            "versionOutputDigest": self.version_output_digest,
            "artifactRefs": list(self.artifact_refs),
            "diagnostics": list(self.diagnostics),
            "counterexample": self.counterexample,
            "externalEvidenceStatus": "NOT_RUN",
            "certificationStatus": "NOT_CERTIFIED",
        }


class NativeVerificationExecutor:
    def __init__(
        self,
        *,
        store: StateStore,
        artifact_store: ContentAddressedArtifactStore | None,
        permit_signer: ExecutionPermitSigner | None,
        toolchains: tuple[ToolchainRegistration, ...],
        limits: ResourceLimits,
        execution_root: Path | None = None,
        runner: SandboxRunner | None = None,
    ) -> None:
        self.store = store
        self.artifact_store = artifact_store
        self.permit_signer = permit_signer
        self.limits = limits
        self.runner = runner or ControlledSandboxRunner()
        self.toolchains = {item.adapter_id: item for item in toolchains}
        if len(self.toolchains) != len(toolchains):
            raise ExecutionContractError("duplicate toolchain adapter registration")
        root = execution_root or Path(tempfile.gettempdir()) / "elmos-formal-executions"
        root = root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.is_symlink() or not root.is_dir():
            raise ExecutionContractError("execution root must be a real directory")
        self.execution_root = root

    def execute(
        self,
        *,
        scope: Scope,
        identity: TrustedIdentity,
        skill_id: str,
        subject_id: str,
        payload: Mapping[str, Any],
        allowed_adapters: tuple[str, ...],
    ) -> NativeExecutionReceipt | None:
        raw = payload.get("productionExecution")
        if raw is None:
            return None
        request = NativeExecutionRequest.from_payload(
            raw, scope=scope, skill_id=skill_id, subject_id=subject_id, limits=self.limits
        )
        if request.adapter_id not in allowed_adapters:
            raise ExecutionAuthorizationError(
                f"adapter {request.adapter_id} is not allowlisted for {skill_id}"
            )
        definition = ADAPTERS.get(request.adapter_id)
        registration = self.toolchains.get(request.adapter_id)
        if definition is None or registration is None:
            raise ExecutionContractError(f"registered adapter is unavailable: {request.adapter_id}")
        definition.validate_request(request)
        if self.permit_signer is None:
            raise ExecutionAuthorizationError("native execution permit authority is not configured")
        self.permit_signer.verify(
            request.permit, scope=scope, identity=identity, skill_id=skill_id,
            subject_id=subject_id, adapter_id=request.adapter_id,
            execution_digest=request.binding_digest,
        )
        self.store.consume_execution_permit(
            scope, request.permit.permit_id, request.permit.nonce,
            request.binding_digest, request.permit.expires_at_epoch,
        )
        execution_id = "exec-" + request.binding_digest.removeprefix("sha256:")[:32]
        input_manifest = [
            {"path": item.path, "sha256": digest_bytes(item.data), "sizeBytes": len(item.data)}
            for item in request.files
        ]
        started_at = utc_now()
        with tempfile.TemporaryDirectory(prefix=f"{execution_id}-", dir=self.execution_root) as temporary:
            workspace = Path(temporary).resolve()
            for item in request.files:
                destination = workspace / item.path
                try:
                    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    destination.resolve(strict=False).relative_to(workspace)
                except (OSError, ValueError) as exc:
                    raise ExecutionContractError(f"execution file escapes workspace: {item.path}") from exc
                if destination.exists() or destination.is_symlink():
                    raise ExecutionContractError(f"execution file path collision: {item.path}")
                with destination.open("xb") as handle:
                    handle.write(item.data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(destination, 0o440)
            process_result = self.runner.execute(
                registration, definition, workspace,
                self.limits.constrained(request.timeout_seconds),
            )
        status, assurance, diagnostics, counterexample = interpret_tool_result(
            definition, request, process_result
        )
        artifacts: list[dict[str, Any]] = []
        if self.artifact_store is not None:
            for data, media_type in (
                (process_result.stdout, "text/plain; role=stdout"),
                (process_result.stderr, "text/plain; role=stderr"),
            ):
                artifacts.append(
                    self.artifact_store.put(
                        scope.tenant_id, data, media_type=media_type, retention_class="AUDIT"
                    )
                )
        receipt = NativeExecutionReceipt(
            execution_id=execution_id, adapter_id=request.adapter_id,
            binding_digest=request.binding_digest, toolchain_digest=registration.identity_digest,
            state=process_result.state, proof_status=status, assurance_level=assurance,
            started_at=started_at, duration_ms=process_result.duration_ms,
            exit_code=process_result.exit_code, containment=process_result.containment,
            command_digest=process_result.command_digest,
            input_manifest_digest=digest_value(input_manifest),
            version_output_digest=digest_bytes(process_result.version_output.encode("utf-8")),
            artifact_refs=tuple(artifacts), diagnostics=diagnostics,
            counterexample=counterexample,
        )
        document = receipt.to_dict()
        self.store.put_execution_receipt(scope, execution_id, request.binding_digest, document)
        return receipt


__all__ = [
    "ADAPTERS", "AdapterDefinition", "ControlledSandboxRunner", "ExecutionAuthorizationError",
    "ExecutionContractError", "ExecutionPermit", "ExecutionPermitSigner", "ExecutionState",
    "NativeExecutionReceipt", "NativeExecutionRequest", "NativeVerificationExecutor",
    "ResourceLimits", "SandboxKind", "ToolchainRegistration", "TrustedToolFile",
    "execution_binding_digest", "interpret_tool_result",
    "load_toolchain_registry",
]
