"""Fail-closed provider boundary for optional OCR, ASR, and PDF tools."""

from __future__ import annotations

import hmac
import json
import math
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from .canonical import (
    MAX_SAFE_JSON_INTEGER,
    canonical_digest,
    normalize_sha256,
    require_resource_id,
    sha256_bytes,
    utc_now,
)
from .models import ResultStatus


def _reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-finite provider JSON number: {value}")


def _safe_json_int(value: str) -> int:
    parsed = int(value)
    if abs(parsed) > MAX_SAFE_JSON_INTEGER:
        raise ValueError("provider JSON integer exceeds the safe range")
    return parsed


def _safe_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed.is_integer() and abs(parsed) > MAX_SAFE_JSON_INTEGER:
        raise ValueError("provider JSON number is not interoperable")
    return parsed


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate provider JSON key: {key}")
        value[key] = item
    return value


def _validate_provider_json(value: Any) -> None:
    remaining = 200_000
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        remaining -= 1
        if remaining < 0 or depth > 32:
            raise ValueError("provider JSON exceeds the complexity limit")
        if item is None or isinstance(item, bool):
            continue
        if isinstance(item, int):
            if abs(item) > MAX_SAFE_JSON_INTEGER:
                raise ValueError("provider JSON integer exceeds the safe range")
            continue
        if isinstance(item, float):
            if not math.isfinite(item) or item.is_integer() and abs(item) > MAX_SAFE_JSON_INTEGER:
                raise ValueError("provider JSON number is not interoperable")
            continue
        if isinstance(item, str):
            item.encode("utf-8", errors="strict")
            continue
        if isinstance(item, list):
            stack.extend((child, depth + 1) for child in reversed(item))
            continue
        if isinstance(item, dict):
            for key, child in reversed(tuple(item.items())):
                if not isinstance(key, str) or not key or len(key.encode("utf-8", errors="strict")) > 256:
                    raise ValueError("provider JSON object key is invalid")
                stack.append((child, depth + 1))
            continue
        raise ValueError("provider output is not strict JSON")


class ToolCapability(StrEnum):
    PDF_TEXT = "PDF_TEXT"
    OCR = "OCR"
    ASR = "ASR"
    VISUAL_UI = "VISUAL_UI"
    DIAGRAM = "DIAGRAM"
    MALWARE_SCAN = "MALWARE_SCAN"
    WORD_DOC_CONVERT = "WORD_DOC_CONVERT"


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    tool: str
    executable_sha256: str
    exit_code: int
    stdout: bytes
    stderr_summary: str = ""
    duration_ms: int = 0
    sandboxed: bool = True
    network_allowed: bool = False
    completed_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ProvisionedTool:
    executable: str
    executable_sha256: str


@runtime_checkable
class SandboxExecutor(Protocol):
    """Host-supplied sandbox; this package deliberately never invokes subprocess itself."""

    def execute(
        self,
        *,
        tool: str,
        executable: str,
        argv: tuple[str, ...],
        input_bytes: bytes,
        media_type: str,
        timeout_seconds: int,
        maximum_output_bytes: int,
    ) -> CommandReceipt: ...


def _implementation_identity_digest(component: object) -> str:
    """Hash callable/type identity without publishing module names or source paths."""

    module = getattr(component, "__module__", None)
    qualname = getattr(component, "__qualname__", None)
    if not isinstance(module, str) or not isinstance(qualname, str):
        component_type = type(component)
        module = component_type.__module__
        qualname = component_type.__qualname__
    entrypoint_bytecode: dict[str, str] = {}
    for name, entrypoint in (
        ("call", component),
        ("deliver", getattr(component, "deliver", None)),
        ("execute", getattr(component, "execute", None)),
        ("resolve_archive_password", getattr(component, "resolve_archive_password", None)),
        ("dunder_call", getattr(component, "__call__", None)),
    ):
        bytecode = getattr(getattr(entrypoint, "__code__", None), "co_code", None)
        if isinstance(bytecode, bytes):
            entrypoint_bytecode[name] = sha256_bytes(bytecode)
    return canonical_digest(
        {
            "module": module,
            "qualname": qualname,
            "entrypoint_bytecode": entrypoint_bytecode,
        }
    )


def execution_component_identity(
    component: object | None,
    *,
    component_kind: str,
) -> dict[str, Any]:
    """Return a canonical, path/secret-free identity for a host-owned component.

    Components may expose an exact ``execution_identity_digest`` string/property
    (or zero-argument method) to bind configuration that cannot safely be
    serialized.  The digest itself is the only declared value retained.
    """

    safe_kind = require_resource_id(component_kind, "component_kind")
    if component is None:
        return {
            "component_kind": safe_kind,
            "configured": False,
            "implementation_digest": None,
            "declared_configuration_digest": None,
            "identity_strength": "NOT_CONFIGURED",
        }
    declared = getattr(component, "execution_identity_digest", None)
    if callable(declared):
        declared = declared()
    declared_digest = normalize_sha256(declared) if declared is not None else None
    return {
        "component_kind": safe_kind,
        "configured": True,
        "implementation_digest": _implementation_identity_digest(component),
        "declared_configuration_digest": declared_digest,
        "identity_strength": "DECLARED" if declared_digest is not None else "IMPLEMENTATION_ONLY",
    }


@dataclass(frozen=True, slots=True)
class ProviderResult:
    status: ResultStatus
    capability: ToolCapability
    payload: Mapping[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    warnings: tuple[str, ...] = ()
    receipt: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "receipt", MappingProxyType(dict(self.receipt)))


class ExternalToolProvider:
    """Routes only to a compile-time allowlist through an injected sandbox executor."""

    _ALLOWED_BASENAMES: Mapping[ToolCapability, frozenset[str]] = MappingProxyType(
        {
            ToolCapability.PDF_TEXT: frozenset({"pdftotext"}),
            ToolCapability.OCR: frozenset({"tesseract"}),
            ToolCapability.ASR: frozenset({"whisper", "whisper-cli"}),
            ToolCapability.VISUAL_UI: frozenset({"elmos-ui-vision"}),
            ToolCapability.DIAGRAM: frozenset({"elmos-diagram-vision"}),
            ToolCapability.MALWARE_SCAN: frozenset({"elmos-malware-scan"}),
            ToolCapability.WORD_DOC_CONVERT: frozenset({"elmos-doc-convert"}),
        }
    )
    _FIXED_ARGUMENTS: Mapping[ToolCapability, tuple[str, ...]] = MappingProxyType(
        {
            ToolCapability.PDF_TEXT: ("-layout", "-", "-"),
            ToolCapability.OCR: ("stdin", "stdout", "--psm", "6"),
            ToolCapability.ASR: ("--output-json", "--no-timestamps", "false", "-"),
            ToolCapability.VISUAL_UI: ("--input", "-", "--output", "json"),
            ToolCapability.DIAGRAM: ("--input", "-", "--output", "json"),
            ToolCapability.MALWARE_SCAN: ("--input", "-", "--output", "json"),
            ToolCapability.WORD_DOC_CONVERT: ("--input", "-", "--output", "json"),
        }
    )
    _JSON_OUTPUT_CAPABILITIES = frozenset(
        {
            ToolCapability.ASR,
            ToolCapability.VISUAL_UI,
            ToolCapability.DIAGRAM,
            ToolCapability.MALWARE_SCAN,
            ToolCapability.WORD_DOC_CONVERT,
        }
    )

    def __init__(
        self,
        executor: SandboxExecutor | None = None,
        provisioned_tools: Mapping[
            ToolCapability | str,
            ProvisionedTool | Mapping[str, str] | tuple[str, str] | str,
        ]
        | None = None,
        *,
        timeout_seconds: int = 120,
        maximum_output_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        if not 1 <= timeout_seconds <= 300:
            raise ValueError("timeout_seconds must be positive")
        if not 1 <= maximum_output_bytes <= 16 * 1024 * 1024:
            raise ValueError("maximum_output_bytes must be positive")
        self.executor = executor
        self.timeout_seconds = timeout_seconds
        self.maximum_output_bytes = maximum_output_bytes
        self._receipt_auth_key = secrets.token_bytes(32)
        self.provisioned_tools: dict[ToolCapability, ProvisionedTool] = {}
        for raw_capability, raw_configuration in (provisioned_tools or {}).items():
            capability = ToolCapability(raw_capability)
            raw_path: object
            raw_digest: object
            if isinstance(raw_configuration, ProvisionedTool):
                raw_path = raw_configuration.executable
                raw_digest = raw_configuration.executable_sha256
            elif isinstance(raw_configuration, Mapping):
                raw_path = raw_configuration.get("executable") or raw_configuration.get("path")
                raw_digest = raw_configuration.get("executable_sha256") or raw_configuration.get("sha256")
            elif isinstance(raw_configuration, tuple) and len(raw_configuration) == 2:
                raw_path, raw_digest = raw_configuration
            else:
                raise ValueError(f"Tool configuration for {capability.value} requires path and SHA-256")
            if not isinstance(raw_path, str) or not isinstance(raw_digest, str):
                raise ValueError(f"Tool configuration for {capability.value} requires path and SHA-256")
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                raise ValueError(f"Tool path for {capability.value} must be absolute")
            path = path.resolve()
            allowed = self._ALLOWED_BASENAMES.get(capability, frozenset())
            if path.name not in allowed:
                raise ValueError(f"Tool path for {capability.value} is outside the fixed allowlist")
            try:
                executable_digest = normalize_sha256(raw_digest)
            except Exception as error:
                raise ValueError(f"Tool digest for {capability.value} is invalid") from error
            self.provisioned_tools[capability] = ProvisionedTool(str(path), executable_digest)

    def execution_environment_identity(self) -> dict[str, Any]:
        """Describe executable/provider semantics without paths or authentication keys."""

        tools = [
            {
                "capability": capability.value,
                "executable_sha256": configuration.executable_sha256,
                "fixed_arguments_digest": canonical_digest(list(self._FIXED_ARGUMENTS[capability])),
                "invocation_policy_digest": canonical_digest(
                    self._invocation_policy(capability, configuration)
                ),
            }
            for capability, configuration in sorted(
                self.provisioned_tools.items(),
                key=lambda item: item[0].value,
            )
        ]
        return {
            "schema_version": "elmos-external-tool-environment-v1",
            "provider_implementation_digest": _implementation_identity_digest(self),
            "sandbox_executor": execution_component_identity(
                self.executor,
                component_kind="sandbox-executor",
            ),
            "timeout_seconds": self.timeout_seconds,
            "maximum_output_bytes": self.maximum_output_bytes,
            "sandboxed_required": True,
            "network_allowed": False,
            "receipt_authentication": "runtime-ephemeral-hmac-sha256",
            "tools": tools,
        }

    @property
    def execution_environment_digest(self) -> str:
        return canonical_digest(self.execution_environment_identity())

    @property
    def execution_identity_digest(self) -> str:
        """Component protocol alias used by aggregate runtime identity."""

        return self.execution_environment_digest

    def invocation_policy_digest(self, capability: ToolCapability) -> str:
        """Bind an invocation to the exact private executable configuration.

        The digest is safe to persist and publish.  Its preimage deliberately
        retains the resolved host path so a same-named binary moved elsewhere
        is a different execution policy, while the path itself never crosses
        the provider boundary.
        """

        configuration = self.provisioned_tools.get(capability)
        if configuration is None or capability not in self._ALLOWED_BASENAMES:
            raise ValueError(f"Tool configuration for {capability.value} is unavailable")
        return canonical_digest(self._invocation_policy(capability, configuration))

    def _invocation_policy(
        self,
        capability: ToolCapability,
        configuration: ProvisionedTool,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "tool": capability.value,
            # Private policy input: this value is hashed and never included in
            # ProviderResult.receipt or any API response.
            "executable": configuration.executable,
            "expected_executable_sha256": configuration.executable_sha256,
            "argv": list(self._FIXED_ARGUMENTS[capability]),
            "timeout_seconds": self.timeout_seconds,
            "maximum_output_bytes": self.maximum_output_bytes,
            "sandboxed_required": True,
            "network_allowed": False,
        }

    def run(
        self,
        capability: ToolCapability,
        data: bytes,
        media_type: str,
        *,
        job_id: str | None = None,
        stage: str | None = None,
    ) -> ProviderResult:
        configuration = self.provisioned_tools.get(capability)
        if self.executor is None or configuration is None:
            return ProviderResult(
                status=ResultStatus.NOT_RUN,
                capability=capability,
                error_code="EXTERNAL_TOOL_SANDBOX_NOT_CONFIGURED",
            )
        if capability not in self._ALLOWED_BASENAMES:
            return ProviderResult(
                status=ResultStatus.NOT_RUN,
                capability=capability,
                error_code="CAPABILITY_HAS_NO_ALLOWLISTED_LOCAL_TOOL",
            )
        if not isinstance(data, bytes):
            return ProviderResult(
                status=ResultStatus.FAILED,
                capability=capability,
                error_code="PROVIDER_INPUT_INVALID",
            )
        normalized_media_type = str(media_type or "").split(";", 1)[0].strip().lower()
        if not normalized_media_type or "/" not in normalized_media_type or len(normalized_media_type) > 127:
            return ProviderResult(
                status=ResultStatus.FAILED,
                capability=capability,
                error_code="PROVIDER_MEDIA_TYPE_INVALID",
            )
        safe_job_id = require_resource_id(job_id, "job_id") if job_id is not None else "direct"
        safe_stage = require_resource_id(stage, "provider_stage") if stage is not None else "direct"
        argv = self._FIXED_ARGUMENTS[capability]
        input_digest = sha256_bytes(data)
        policy = self._invocation_policy(capability, configuration)
        policy_digest = canonical_digest(policy)
        started_at = utc_now()
        try:
            result = self.executor.execute(
                tool=capability.value,
                executable=configuration.executable,
                argv=argv,
                input_bytes=data,
                media_type=normalized_media_type,
                timeout_seconds=self.timeout_seconds,
                maximum_output_bytes=self.maximum_output_bytes,
            )
        except Exception:
            return ProviderResult(
                status=ResultStatus.FAILED,
                capability=capability,
                error_code="SANDBOX_EXECUTION_FAILED",
            )
        try:
            reported_digest = normalize_sha256(result.executable_sha256) if isinstance(result, CommandReceipt) else ""
        except Exception:
            reported_digest = ""
        completed_at_valid = False
        stderr_bytes: bytes | None = None
        if isinstance(result, CommandReceipt) and isinstance(result.completed_at, str):
            try:
                completed_at_value = datetime.fromisoformat(result.completed_at)
            except ValueError:
                completed_at_value = None
            completed_at_valid = completed_at_value is not None and completed_at_value.tzinfo is not None
        if isinstance(result, CommandReceipt) and isinstance(result.stderr_summary, str):
            try:
                stderr_bytes = result.stderr_summary.encode("utf-8", errors="strict")
            except UnicodeEncodeError:
                stderr_bytes = None
        if (
            not isinstance(result, CommandReceipt)
            or result.tool != capability.value
            or not isinstance(result.stdout, bytes)
            or not isinstance(result.stderr_summary, str)
            or stderr_bytes is None
            or len(stderr_bytes) > 64 * 1024
            or not isinstance(result.completed_at, str)
            or not isinstance(result.exit_code, int)
            or isinstance(result.exit_code, bool)
            or not isinstance(result.duration_ms, int)
            or isinstance(result.duration_ms, bool)
            or result.duration_ms < 0
            or not completed_at_valid
            or not hmac.compare_digest(reported_digest, configuration.executable_sha256)
            or result.sandboxed is not True
            or result.network_allowed is not False
        ):
            return ProviderResult(
                status=ResultStatus.FAILED,
                capability=capability,
                error_code="SANDBOX_RECEIPT_INVALID",
            )
        receipt = {
            "schema_version": "1.0.0",
            "tool": result.tool,
            # Public receipts identify only the allowlisted tool.  The exact
            # resolved host path remains bound by policy_sha256 and the
            # instance-authenticated provider tag below.
            "executable": Path(configuration.executable).name,
            "executable_sha256": reported_digest,
            "input_sha256": input_digest,
            "input_bytes": len(data),
            "media_type": normalized_media_type,
            "argv": list(argv),
            "argv_sha256": canonical_digest(list(argv)),
            "policy_sha256": policy_digest,
            "job_id": safe_job_id,
            "stage": safe_stage,
            "exit_code": result.exit_code,
            "stdout_sha256": sha256_bytes(result.stdout),
            "stdout_bytes": len(result.stdout),
            # Provider stderr is host-owned and can echo executable paths or
            # other local details.  Publish only a content digest.
            "stderr_summary": (
                f"sha256:{sha256_bytes(stderr_bytes)}"
                if stderr_bytes
                else ""
            ),
            "duration_ms": result.duration_ms,
            "sandboxed": result.sandboxed,
            "network_allowed": result.network_allowed,
            "started_at": started_at,
            "completed_at": result.completed_at,
            "received_at": utc_now(),
        }
        if len(result.stdout) > self.maximum_output_bytes:
            return ProviderResult(
                status=ResultStatus.FAILED,
                capability=capability,
                error_code="PROVIDER_OUTPUT_LIMIT_EXCEEDED",
                receipt=receipt,
            )
        if result.exit_code != 0:
            return ProviderResult(
                status=ResultStatus.FAILED,
                capability=capability,
                error_code="PROVIDER_COMMAND_FAILED",
                receipt=receipt,
            )
        try:
            decoded = result.stdout.decode("utf-8")
        except UnicodeDecodeError:
            return ProviderResult(
                status=ResultStatus.FAILED,
                capability=capability,
                error_code="PROVIDER_OUTPUT_ENCODING_INVALID",
                receipt=receipt,
            )
        try:
            parsed = json.loads(
                decoded,
                parse_constant=_reject_non_finite_json,
                parse_int=_safe_json_int,
                parse_float=_safe_json_float,
                object_pairs_hook=_unique_json_object,
            )
            _validate_provider_json(parsed)
        except (json.JSONDecodeError, UnicodeEncodeError, ValueError, RecursionError):
            if capability in self._JSON_OUTPUT_CAPABILITIES:
                return ProviderResult(
                    status=ResultStatus.FAILED,
                    capability=capability,
                    error_code="PROVIDER_OUTPUT_JSON_INVALID",
                    receipt=receipt,
                )
            payload: Mapping[str, Any] = {"text": decoded}
        else:
            payload = parsed if isinstance(parsed, dict) else {"result": parsed}
        return ProviderResult(
            status=ResultStatus.PASSED,
            capability=capability,
            payload=payload,
            receipt={
                **receipt,
                "provider_auth_tag": hmac.new(
                    self._receipt_auth_key,
                    canonical_digest(
                        {
                            "status": ResultStatus.PASSED.value,
                            "capability": capability.value,
                            "payload": dict(payload),
                            "error_code": None,
                            "warnings": [],
                            "receipt": receipt,
                        }
                    ).encode("ascii"),
                    "sha256",
                ).hexdigest(),
            },
        )

    def verify_issued_result(self, result: ProviderResult) -> bool:
        """Verify that this exact instance issued an untampered passed result."""

        if not isinstance(result, ProviderResult) or result.status is not ResultStatus.PASSED:
            return False
        receipt = dict(result.receipt)
        auth_tag = receipt.pop("provider_auth_tag", None)
        if not isinstance(auth_tag, str) or len(auth_tag) != 64:
            return False
        configuration = self.provisioned_tools.get(result.capability)
        if configuration is None:
            return False
        try:
            receipt_executable_digest = normalize_sha256(receipt.get("executable_sha256"))
            receipt_policy_digest = normalize_sha256(receipt.get("policy_sha256"))
            receipt_argv_digest = normalize_sha256(receipt.get("argv_sha256"))
            receipt_input_digest = normalize_sha256(receipt.get("input_sha256"))
            receipt_stdout_digest = normalize_sha256(receipt.get("stdout_sha256"))
            stderr_summary = receipt.get("stderr_summary")
            if stderr_summary:
                normalize_sha256(stderr_summary)
        except Exception:
            return False
        expected_argv = list(self._FIXED_ARGUMENTS[result.capability])
        input_bytes = receipt.get("input_bytes")
        stdout_bytes = receipt.get("stdout_bytes")
        if (
            receipt.get("schema_version") != "1.0.0"
            or receipt.get("tool") != result.capability.value
            or receipt.get("executable") != Path(configuration.executable).name
            or not hmac.compare_digest(
                receipt_executable_digest,
                configuration.executable_sha256,
            )
            or not hmac.compare_digest(
                receipt_policy_digest,
                canonical_digest(self._invocation_policy(result.capability, configuration)),
            )
            or receipt.get("argv") != expected_argv
            or not hmac.compare_digest(
                receipt_argv_digest,
                canonical_digest(expected_argv),
            )
            or not isinstance(input_bytes, int)
            or isinstance(input_bytes, bool)
            or not 0 <= input_bytes <= MAX_SAFE_JSON_INTEGER
            or len(receipt_input_digest) != 64
            or not isinstance(stdout_bytes, int)
            or isinstance(stdout_bytes, bool)
            or not 0 <= stdout_bytes <= MAX_SAFE_JSON_INTEGER
            or len(receipt_stdout_digest) != 64
            or not isinstance(stderr_summary, str)
            or (
                bool(stderr_summary)
                and not stderr_summary.startswith("sha256:")
            )
            or receipt.get("sandboxed") is not True
            or receipt.get("network_allowed") is not False
        ):
            return False
        try:
            body_digest = canonical_digest(
                {
                    "status": result.status.value,
                    "capability": result.capability.value,
                    "payload": dict(result.payload),
                    "error_code": result.error_code,
                    "warnings": list(result.warnings),
                    "receipt": receipt,
                }
            )
        except Exception:
            return False
        expected = hmac.new(
            self._receipt_auth_key,
            body_digest.encode("ascii"),
            "sha256",
        ).hexdigest()
        return hmac.compare_digest(auth_tag, expected)
