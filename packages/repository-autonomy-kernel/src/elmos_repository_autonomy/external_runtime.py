"""Pinned external command transports and fail-closed qualification preflight.

The kernel never executes arbitrary shell text.  A host may bind an approved,
content-addressed adapter executable which accepts canonical JSON on stdin and
returns one JSON object on stdout.  Credentials are inherited only through
named environment references; values are never copied into plans or evidence.
Sidecars are execution mechanisms, never authority or certification sources.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import os
import re
import selectors
import signal
import stat
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import AuthorizationError, ContractError
from .external import PROVIDER_PROFILES, SecretResolution
from .models import (
    bytes_digest,
    canonical_json,
    digest,
    require_int,
    require_mapping,
    require_sha256_digest,
    require_string,
    utc_now,
)


_BINDING_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_PROTOCOL = re.compile(r"^elmos\.[a-z0-9][a-z0-9.-]*\.v2$")
_SECRET_FIELDS = frozenset({"secret", "secret_value", "password", "token", "api_key", "private_key", "authorization"})
_RESERVED_ENV = frozenset({"HOME", "PATH", "PYTHONPATH", "LD_PRELOAD", "DYLD_INSERT_LIBRARIES"})
_RESPONSE_STATUSES = frozenset(
    {
        "SUCCEEDED",
        "PASS",
        "FAILED",
        "DENIED",
        "CANCELLED",
        "NOT_RUN",
        "UNKNOWN",
        "TIMEOUT",
        "PUBLISHED",
        "NOT_PUBLISHED",
    }
)
_COMMAND_BINDING_FIELDS = frozenset(
    {
        "binding_id",
        "executable",
        "executable_sha256",
        "protocols",
        "args",
        "environment_refs",
        "timeout_seconds",
        "max_input_bytes",
        "max_output_bytes",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "scope",
        "command_bindings",
        "resources",
        "providers",
        "independent_verifier",
    }
)
_SCOPE_FIELDS = frozenset(
    {
        "tenant_id",
        "account_id",
        "project_id",
        "actor_id",
        "environment_authority_id",
        "idempotency_key",
        "revision_digest",
        "candidate_digest",
        "workload_digest",
        "authorization_receipt",
    }
)
_PROVIDER_FIELDS = frozenset({"version", "provider_instance", "credential_lease_ref", "binding_id"})
_VERIFIER_FIELDS = frozenset(
    {
        "verifier_id",
        "trust_store_ref",
        "public_key_digest",
        "authorization_receipt",
        "binding_id",
    }
)


def _assert_no_inline_secrets(
    value: Any,
    path: str = "$",
    *,
    allowed_paths: frozenset[str] = frozenset(),
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            child_path = f"{path}.{key}"
            if normalized in _SECRET_FIELDS and child_path not in allowed_paths:
                raise ContractError("SECRET_EXPOSURE", f"inline secret material is forbidden at {child_path}")
            _assert_no_inline_secrets(child, child_path, allowed_paths=allowed_paths)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _assert_no_inline_secrets(child, f"{path}[{index}]", allowed_paths=allowed_paths)


def _require_exact_fields(
    value: Mapping[str, Any],
    allowed: frozenset[str] | set[str],
    name: str,
) -> None:
    unknown = sorted(str(key) for key in value if key not in allowed)
    if unknown:
        raise ContractError(
            "FIELD_UNKNOWN",
            f"{name} contains unsupported fields: {', '.join(unknown)}",
        )


def _file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return "sha256:" + hasher.hexdigest()


def _wire_value(value: Any, path: str = "$") -> Any:
    """Convert typed requests to canonical JSON without losing binary identity."""

    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise ContractError("COMMAND_INPUT_INVALID", f"request key at {path} must be a non-empty string")
            normalized[key] = _wire_value(child, f"{path}.{key}")
        return normalized
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        return {
            "$elmos_binary": "base64",
            "content_sha256": bytes_digest(raw),
            "size_bytes": len(raw),
            "data": base64.b64encode(raw).decode("ascii"),
        }
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [_wire_value(child, f"{path}[]") for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError("COMMAND_INPUT_INVALID", f"non-finite number at {path}")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ContractError("COMMAND_INPUT_INVALID", f"unsupported request value at {path}")


def _bounded_int(
    value: Any,
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    parsed = require_int(default if value is None else value, name, minimum=minimum)
    if parsed > maximum:
        raise ContractError("INVALID_INPUT", f"{name} must be <= {maximum}")
    return parsed


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        if process.poll() is None:
            process.kill()


@dataclass(frozen=True, slots=True)
class CommandBinding:
    """Immutable host binding for one approved adapter executable."""

    binding_id: str
    executable: str
    executable_sha256: str
    protocols: tuple[str, ...]
    args: tuple[str, ...] = ()
    environment_refs: tuple[tuple[str, str], ...] = ()
    timeout_seconds: int = 30
    max_input_bytes: int = 1024 * 1024
    max_output_bytes: int = 1024 * 1024

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CommandBinding":
        record = require_mapping(value, "command binding")
        _require_exact_fields(record, _COMMAND_BINDING_FIELDS, "command binding")
        binding_id = require_string(record.get("binding_id"), "command binding.binding_id")
        if not _BINDING_ID.fullmatch(binding_id):
            raise ContractError("BINDING_ID_INVALID", "command binding.binding_id has an invalid format")
        executable_value = require_string(record.get("executable"), "command binding.executable")
        executable = Path(executable_value)
        if not executable.is_absolute():
            raise ContractError("COMMAND_PATH_INVALID", "adapter executable must use an absolute path")
        if executable.is_symlink():
            raise ContractError("COMMAND_PATH_INVALID", "adapter executable must not be a symlink")
        try:
            resolved = executable.resolve(strict=True)
        except OSError as exc:
            raise ContractError("COMMAND_UNAVAILABLE", "adapter executable is unavailable") from exc
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise ContractError("COMMAND_UNAVAILABLE", "adapter executable must be a regular executable file")
        if stat.S_IMODE(resolved.stat().st_mode) & (stat.S_IWGRP | stat.S_IWOTH):
            raise ContractError("COMMAND_INSECURE", "adapter executable must not be group- or world-writable")
        expected = require_sha256_digest(record.get("executable_sha256"), "command binding.executable_sha256")
        observed = _file_digest(resolved)
        if observed != expected:
            raise ContractError("COMMAND_DIGEST_DRIFT", "adapter executable digest does not match its binding")

        protocols_value = record.get("protocols")
        if not isinstance(protocols_value, Sequence) or isinstance(protocols_value, (str, bytes, bytearray)):
            raise ContractError("COMMAND_PROTOCOL_INVALID", "command binding.protocols must be an array")
        protocols = tuple(require_string(item, "command binding.protocols[]") for item in protocols_value)
        if (
            not protocols
            or len(protocols) > 64
            or len(protocols) != len(set(protocols))
            or any(not _PROTOCOL.fullmatch(protocol) for protocol in protocols)
        ):
            raise ContractError(
                "COMMAND_PROTOCOL_INVALID",
                "command binding.protocols must contain unique supported protocol identifiers",
            )

        args_value = record.get("args", [])
        if not isinstance(args_value, Sequence) or isinstance(args_value, (str, bytes, bytearray)):
            raise ContractError("INVALID_INPUT", "command binding.args must be an array")
        args = tuple(require_string(item, "command binding.args[]") for item in args_value)
        if len(args) > 64 or any("\x00" in item or len(item) > 4096 for item in args):
            raise ContractError("COMMAND_ARGUMENT_INVALID", "adapter arguments exceed the safe boundary")

        refs = require_mapping(record.get("environment_refs", {}), "command binding.environment_refs")
        environment_refs: list[tuple[str, str]] = []
        for target, source in sorted(refs.items()):
            target_name = require_string(target, "environment target")
            source_name = require_string(source, f"environment_refs.{target_name}")
            if not _ENV_NAME.fullmatch(target_name) or not _ENV_NAME.fullmatch(source_name):
                raise ContractError("ENVIRONMENT_REF_INVALID", "environment references must be uppercase names")
            if target_name in _RESERVED_ENV or source_name in _RESERVED_ENV:
                raise AuthorizationError("ENVIRONMENT_REF_DENIED", "reserved process environment cannot be inherited")
            environment_refs.append((target_name, source_name))
        if len(environment_refs) > 64:
            raise ContractError("ENVIRONMENT_REF_INVALID", "at most 64 environment references are allowed")

        return cls(
            binding_id=binding_id,
            executable=str(resolved),
            executable_sha256=expected,
            protocols=protocols,
            args=args,
            environment_refs=tuple(environment_refs),
            timeout_seconds=_bounded_int(
                record.get("timeout_seconds"),
                "command binding.timeout_seconds",
                default=30,
                minimum=1,
                maximum=3600,
            ),
            max_input_bytes=_bounded_int(
                record.get("max_input_bytes"),
                "command binding.max_input_bytes",
                default=1024 * 1024,
                minimum=1024,
                maximum=16 * 1024 * 1024,
            ),
            max_output_bytes=_bounded_int(
                record.get("max_output_bytes"),
                "command binding.max_output_bytes",
                default=1024 * 1024,
                minimum=1024,
                maximum=16 * 1024 * 1024,
            ),
        )

    def verify_current(self) -> None:
        path = Path(self.executable)
        if path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
            raise ContractError("COMMAND_UNAVAILABLE", "adapter executable is no longer available")
        if stat.S_IMODE(path.stat().st_mode) & (stat.S_IWGRP | stat.S_IWOTH):
            raise ContractError("COMMAND_INSECURE", "adapter executable permissions changed after binding")
        if _file_digest(path) != self.executable_sha256:
            raise ContractError("COMMAND_DIGEST_DRIFT", "adapter executable changed after binding")


class JsonCommandRunner:
    """Run one pinned adapter process without a shell and emit digest-only execution evidence."""

    evidence_class = "EXTERNAL_EXECUTED"

    def __init__(self, binding: CommandBinding, *, environment: Mapping[str, str] | None = None) -> None:
        self.binding = binding
        self.environment = os.environ if environment is None else environment

    def _environment(self) -> tuple[dict[str, str], list[str], list[str]]:
        child = {"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin"}
        missing: list[str] = []
        invalid: list[str] = []
        for target, source in self.binding.environment_refs:
            value = self.environment.get(source)
            if value is None or value == "":
                missing.append(source)
            elif not isinstance(value, str) or "\x00" in value:
                invalid.append(source)
            else:
                child[target] = value
        return child, missing, invalid

    @staticmethod
    def _failure(status: str, code: str, receipt: Mapping[str, Any], **details: Any) -> dict[str, Any]:
        return {
            "status": status,
            "result": {},
            "raw_evidence": {"command_execution": dict(receipt)},
            "error": {"code": code, **details},
            "side_effect_performed": False if status == "NOT_RUN" else None,
        }

    def invoke(
        self,
        protocol: str,
        request: Mapping[str, Any],
        *,
        allowed_secret_paths: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        self.binding.verify_current()
        if not _PROTOCOL.fullmatch(protocol) or protocol not in self.binding.protocols:
            raise AuthorizationError(
                "COMMAND_PROTOCOL_DENIED",
                "the command binding is not authorized for the requested protocol",
            )
        _assert_no_inline_secrets(request)
        environment, missing, invalid = self._environment()
        wire_request = _wire_value(request)
        request_hash = digest(
            {
                "protocol": protocol,
                "binding_id": self.binding.binding_id,
                "request": wire_request,
            }
        )
        initial_receipt = {
            "binding_id": self.binding.binding_id,
            "protocol": protocol,
            "request_hash": request_hash,
            "executable_sha256": self.binding.executable_sha256,
            "started_at": utc_now(),
        }
        if missing:
            return self._failure(
                "NOT_RUN",
                "ENVIRONMENT_REFERENCE_UNAVAILABLE",
                initial_receipt,
                missing_environment_refs=missing,
            )
        if invalid:
            return self._failure(
                "NOT_RUN",
                "ENVIRONMENT_REFERENCE_INVALID",
                initial_receipt,
                invalid_environment_refs=invalid,
            )

        try:
            envelope = canonical_json(
                {
                    "protocol": protocol,
                    "binding_id": self.binding.binding_id,
                    "request": wire_request,
                }
            )
        except (TypeError, ValueError) as exc:
            raise ContractError("COMMAND_INPUT_INVALID", "request cannot be canonicalized") from exc
        if len(envelope) > self.binding.max_input_bytes:
            return self._failure(
                "NOT_RUN",
                "ADAPTER_INPUT_LIMIT",
                {**initial_receipt, "input_bytes": len(envelope)},
            )

        started = time.monotonic()
        stdout = bytearray()
        stderr = bytearray()
        observed = {"stdout": 0, "stderr": 0}
        termination: str | None = None
        process: subprocess.Popen[bytes]
        with tempfile.TemporaryFile() as stdin_file:
            stdin_file.write(envelope)
            stdin_file.seek(0)
            try:
                process = subprocess.Popen(  # noqa: S603 - executable and argv are digest-bound and shell-free
                    [self.binding.executable, *self.binding.args],
                    stdin=stdin_file,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd="/",
                    env=environment,
                    start_new_session=True,
                )
            except (OSError, ValueError, subprocess.SubprocessError):
                receipt = {
                    **initial_receipt,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "finished_at": utc_now(),
                }
                return self._failure("NOT_RUN", "ADAPTER_START_FAILED", receipt)

            if process.stdout is None or process.stderr is None:
                _kill_process_group(process)
                process.wait()
                return self._failure("NOT_RUN", "ADAPTER_START_FAILED", initial_receipt)

            output_streams = {"stdout": process.stdout, "stderr": process.stderr}
            selector = selectors.DefaultSelector()
            for name, stream in output_streams.items():
                selector.register(stream, selectors.EVENT_READ, name)
            deadline = started + self.binding.timeout_seconds
            try:
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        termination = "ADAPTER_TIMEOUT"
                        _kill_process_group(process)
                        break
                    for key, _ in selector.select(timeout=min(0.1, remaining)):
                        name = str(key.data)
                        try:
                            chunk = os.read(key.fileobj.fileno(), 64 * 1024)
                        except BlockingIOError:
                            continue
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        observed[name] += len(chunk)
                        target = stdout if name == "stdout" else stderr
                        room = self.binding.max_output_bytes + 1 - len(target)
                        if room > 0:
                            target.extend(chunk[:room])
                        if observed[name] > self.binding.max_output_bytes:
                            termination = "ADAPTER_OUTPUT_LIMIT"
                            _kill_process_group(process)
                            break
                    if termination is not None:
                        break
            finally:
                selector.close()
                for stream in output_streams.values():
                    stream.close()

            if termination is None:
                remaining = max(0.001, deadline - time.monotonic())
                try:
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    termination = "ADAPTER_TIMEOUT"
                    _kill_process_group(process)
            process.wait()

        output_complete = termination is None
        sensitive_output = bool(allowed_secret_paths)
        receipt = {
            **initial_receipt,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "finished_at": utc_now(),
            "return_code": process.returncode,
            "stdout_bytes_observed": observed["stdout"],
            "stderr_bytes_observed": observed["stderr"],
            "stdout_sha256": (bytes_digest(bytes(stdout)) if output_complete and not sensitive_output else None),
            "stderr_sha256": (bytes_digest(bytes(stderr)) if output_complete and not sensitive_output else None),
            "stdout_prefix_sha256": (
                bytes_digest(bytes(stdout)) if not output_complete and not sensitive_output else None
            ),
            "stderr_prefix_sha256": (
                bytes_digest(bytes(stderr)) if not output_complete and not sensitive_output else None
            ),
            "output_complete": output_complete,
            "output_hash_withheld": sensitive_output,
        }
        if termination == "ADAPTER_TIMEOUT":
            return self._failure("UNKNOWN", "ADAPTER_TIMEOUT", receipt)
        if termination == "ADAPTER_OUTPUT_LIMIT":
            return self._failure("UNKNOWN", "ADAPTER_OUTPUT_LIMIT", receipt)
        if process.returncode != 0:
            return self._failure(
                "UNKNOWN",
                "ADAPTER_EXIT_NONZERO",
                receipt,
                return_code=process.returncode,
            )
        raw = bytes(stdout)

        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._failure("UNKNOWN", "ADAPTER_RESPONSE_INVALID", receipt)
        if not isinstance(decoded, Mapping):
            return self._failure("UNKNOWN", "ADAPTER_RESPONSE_INVALID", receipt)
        response = dict(decoded)
        status_value = str(response.get("status", "UNKNOWN")).upper()
        if status_value not in _RESPONSE_STATUSES:
            return self._failure("UNKNOWN", "ADAPTER_STATUS_INVALID", receipt)
        try:
            _assert_no_inline_secrets(response, allowed_paths=allowed_secret_paths)
        except ContractError:
            return self._failure("UNKNOWN", "ADAPTER_SECRET_EXPOSURE", receipt)
        try:
            response["result"] = require_mapping(response.get("result", {}), "adapter result")
            adapter_evidence = require_mapping(
                response.get("raw_evidence", {}),
                "adapter raw_evidence",
            )
            if response.get("error") is not None:
                response["error"] = require_mapping(response["error"], "adapter error")
        except ContractError:
            return self._failure("UNKNOWN", "ADAPTER_RESPONSE_INVALID", receipt)
        response["status"] = status_value
        response["raw_evidence"] = {**adapter_evidence, "command_execution": receipt}
        return response


class CommandSCMTransport:
    evidence_class = "EXTERNAL_EXECUTED"

    def __init__(self, runner: JsonCommandRunner) -> None:
        self.runner = runner

    def invoke(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.runner.invoke("elmos.scm.v2", request)


class CommandPostgresTransport:
    evidence_class = "EXTERNAL_EXECUTED"

    def __init__(self, runner: JsonCommandRunner) -> None:
        self.runner = runner

    def invoke(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.runner.invoke("elmos.postgresql.v2", request)


class CommandS3Transport:
    evidence_class = "EXTERNAL_EXECUTED"

    def __init__(self, runner: JsonCommandRunner) -> None:
        self.runner = runner

    def invoke(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.runner.invoke("elmos.s3.v2", request)


class CommandEventBusTransport:
    evidence_class = "EXTERNAL_EXECUTED"

    def __init__(self, runner: JsonCommandRunner) -> None:
        self.runner = runner

    def publish(self, event: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.runner.invoke("elmos.event-bus.v2", {"operation": "publish", "event": dict(event)})

    def reconcile(self, event: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.runner.invoke("elmos.event-bus.v2", {"operation": "reconcile", "event": dict(event)})


class CommandKubernetesTransport:
    evidence_class = "EXTERNAL_EXECUTED"

    def __init__(self, runner: JsonCommandRunner) -> None:
        self.runner = runner

    def invoke(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.runner.invoke("elmos.kubernetes.v2", request)


class CommandProviderTransport:
    evidence_class = "EXTERNAL_EXECUTED"

    def __init__(self, runners: Mapping[str, JsonCommandRunner]) -> None:
        unknown = sorted(set(runners) - set(PROVIDER_PROFILES))
        if unknown:
            raise ContractError("ADAPTER_UNKNOWN", f"unknown provider command bindings: {', '.join(unknown)}")
        self.runners = dict(runners)

    def invoke(self, adapter_id: str, envelope: Mapping[str, Any]) -> Mapping[str, Any]:
        if adapter_id not in PROVIDER_PROFILES:
            raise ContractError("ADAPTER_UNKNOWN", f"unknown adapter: {adapter_id}")
        runner = self.runners.get(adapter_id)
        if runner is None:
            return {
                "status": "NOT_RUN",
                "result": {},
                "raw_evidence": {"adapter_id": adapter_id, "binding": "MISSING"},
                "error": {"code": "PROVIDER_BINDING_MISSING"},
            }
        return runner.invoke(f"elmos.provider.{adapter_id}.v2", envelope)


class CommandIndependentVerifierTransport:
    """Invoke a separate verifier without granting it certification authority."""

    evidence_class = "EXTERNAL_EXECUTED"

    def __init__(self, runner: JsonCommandRunner) -> None:
        self.runner = runner

    def verify(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        response = dict(self.runner.invoke("elmos.independent-verifier.v2", request))
        result = require_mapping(response.get("result", {}), "independent verifier result")
        forbidden = sorted(
            set(result)
            & {
                "certification",
                "certificate",
                "p05",
                "p05_issued",
                "deployment_complete",
            }
        )
        if forbidden:
            return {
                "status": "UNKNOWN",
                "result": {},
                "raw_evidence": require_mapping(
                    response.get("raw_evidence", {}),
                    "independent verifier raw evidence",
                ),
                "error": {
                    "code": "VERIFIER_AUTHORITY_ESCALATION",
                    "forbidden_fields": forbidden,
                },
                "side_effect_performed": False,
            }
        response["result"] = result
        return response


class CommandSecretsBrokerTransport:
    """Resolve and revoke broker leases without persisting returned secret material."""

    evidence_class = "EXTERNAL_EXECUTED"

    def __init__(self, runner: JsonCommandRunner, *, max_secret_bytes: int = 1024 * 1024) -> None:
        if (
            isinstance(max_secret_bytes, bool)
            or not isinstance(max_secret_bytes, int)
            or max_secret_bytes < 1
            or max_secret_bytes > 16 * 1024 * 1024
        ):
            raise ContractError(
                "SECRET_BROKER_BOUND_INVALID",
                "max_secret_bytes must be between 1 and 16777216",
            )
        self.runner = runner
        self.max_secret_bytes = max_secret_bytes

    def resolve(self, secret_ref: str) -> SecretResolution:
        response = self.runner.invoke(
            "elmos.secrets-broker.v2",
            {"operation": "lease", "secret_ref": require_string(secret_ref, "secret_ref")},
            allowed_secret_paths=frozenset({"$.result.secret_value"}),
        )
        if response.get("status") != "SUCCEEDED":
            raise AuthorizationError("SECRET_BROKER_UNAVAILABLE", "secret broker did not issue a lease")
        result = require_mapping(response.get("result", {}), "secret broker result")
        encoded = require_string(result.pop("secret_value", None), "secret broker result.secret_value")
        response["result"] = result
        try:
            material = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ContractError("SECRET_BROKER_RESPONSE_INVALID", "secret material must be base64") from exc
        if not material or len(material) > self.max_secret_bytes:
            raise ContractError("SECRET_BROKER_RESPONSE_INVALID", "secret material size is invalid")
        native_lease_id = require_string(result.get("native_lease_id"), "secret broker result.native_lease_id")
        return SecretResolution(
            material=material,
            native_lease_id=native_lease_id,
            receipt={
                "result": result,
                "raw_evidence": require_mapping(response.get("raw_evidence", {}), "secret broker raw evidence"),
                "secret_material_persisted": False,
            },
            evidence_class="EXTERNAL_EXECUTED",
        )

    def revoke(self, lease: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.runner.invoke(
            "elmos.secrets-broker.v2",
            {
                "operation": "revoke",
                "native_lease_id": require_string(lease.get("native_lease_id"), "lease.native_lease_id"),
                "lease_id": require_string(lease.get("lease_id"), "lease.lease_id"),
            },
        )


_RESOURCE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "postgresql": ("service_ref", "engine_version", "operator_role_ref", "binding_id"),
    "scm": ("provider_instance", "native_repository_id", "exact_commit", "credential_lease_ref", "binding_id"),
    "object-store": ("account_id", "region", "bucket", "credential_lease_ref", "binding_id"),
    "event-bus": ("provider_instance", "region", "topic", "credential_lease_ref", "binding_id"),
    "secrets-broker": ("broker_id", "role_ref", "binding_id"),
    "kubernetes": ("context", "namespace", "image_digest", "service_account", "binding_id"),
    "customer-repository": (
        "provider_instance",
        "native_repository_id",
        "exact_commit",
        "credential_lease_ref",
        "customer_authorization_receipt",
        "binding_id",
    ),
}

_RESOURCE_PROTOCOLS = {
    "postgresql": "elmos.postgresql.v2",
    "scm": "elmos.scm.v2",
    "object-store": "elmos.s3.v2",
    "event-bus": "elmos.event-bus.v2",
    "secrets-broker": "elmos.secrets-broker.v2",
    "kubernetes": "elmos.kubernetes.v2",
    "customer-repository": "elmos.scm.v2",
}


class ExternalQualificationPreflight:
    """Validate exact external bindings without executing or certifying them."""

    def __init__(self, *, environment: Mapping[str, str] | None = None) -> None:
        self.environment = os.environ if environment is None else environment

    @staticmethod
    def _scope(manifest: Mapping[str, Any]) -> dict[str, Any]:
        scope = require_mapping(manifest.get("scope", {}), "qualification manifest.scope")
        _require_exact_fields(scope, _SCOPE_FIELDS, "qualification manifest.scope")
        for field in (
            "tenant_id",
            "account_id",
            "project_id",
            "actor_id",
            "environment_authority_id",
            "idempotency_key",
        ):
            require_string(scope.get(field), f"qualification manifest.scope.{field}")
        for field in (
            "revision_digest",
            "candidate_digest",
            "workload_digest",
            "authorization_receipt",
        ):
            require_sha256_digest(scope.get(field), f"qualification manifest.scope.{field}")
        return scope

    def evaluate(self, value: Mapping[str, Any]) -> dict[str, Any]:
        manifest = require_mapping(value, "qualification manifest")
        _require_exact_fields(manifest, _MANIFEST_FIELDS, "qualification manifest")
        _assert_no_inline_secrets(manifest)
        if manifest.get("schema_version") != "2.0.0":
            raise ContractError("SCHEMA_VERSION_UNSUPPORTED", "qualification manifest schema_version must be 2.0.0")
        scope = self._scope(manifest)
        binding_values = require_mapping(
            manifest.get("command_bindings", {}), "qualification manifest.command_bindings"
        )
        if not binding_values:
            raise ContractError(
                "COMMAND_BINDING_MISSING",
                "qualification manifest.command_bindings must not be empty",
            )
        bindings: dict[str, CommandBinding] = {}
        binding_errors: dict[str, str] = {}
        for key, raw in binding_values.items():
            binding_name = require_string(key, "command binding key")
            try:
                binding = CommandBinding.from_mapping(require_mapping(raw, f"command_bindings.{binding_name}"))
                if binding.binding_id != binding_name:
                    raise ContractError("BINDING_ID_MISMATCH", "command binding key must equal binding_id")
                missing = [source for _, source in binding.environment_refs if not self.environment.get(source)]
                if missing:
                    binding_errors[binding_name] = "ENVIRONMENT_REFERENCE_UNAVAILABLE"
                else:
                    bindings[binding_name] = binding
            except (AuthorizationError, ContractError) as exc:
                binding_errors[binding_name] = exc.info.code

        resources = require_mapping(manifest.get("resources", {}), "qualification manifest.resources")
        extra_resources = sorted(set(resources) - set(_RESOURCE_REQUIREMENTS))
        if extra_resources:
            raise ContractError(
                "CAPABILITY_UNKNOWN",
                f"unknown resource bindings: {', '.join(extra_resources)}",
            )
        capability_results: dict[str, Any] = {}
        for capability, required_fields in _RESOURCE_REQUIREMENTS.items():
            record = resources.get(capability)
            reasons: list[str] = []
            if not isinstance(record, Mapping):
                reasons.append("RESOURCE_BINDING_MISSING")
                normalized: dict[str, Any] = {}
            else:
                normalized = dict(record)
                _require_exact_fields(
                    normalized,
                    set(required_fields),
                    f"qualification manifest.resources.{capability}",
                )
                for field in required_fields:
                    if not isinstance(normalized.get(field), str) or not str(normalized[field]).strip():
                        reasons.append(f"FIELD_MISSING:{field}")
            if capability in {"scm", "customer-repository"} and normalized.get("exact_commit"):
                commit = str(normalized["exact_commit"])
                if len(commit) not in {40, 64} or not all(char in "0123456789abcdefABCDEF" for char in commit):
                    reasons.append("EXACT_COMMIT_INVALID")
            if capability == "kubernetes" and normalized.get("image_digest"):
                try:
                    require_sha256_digest(normalized["image_digest"], "resources.kubernetes.image_digest")
                except ContractError:
                    reasons.append("IMAGE_DIGEST_INVALID")
            binding_id = normalized.get("binding_id")
            if binding_id:
                if binding_id in binding_errors:
                    reasons.append(f"COMMAND_BINDING_INVALID:{binding_errors[binding_id]}")
                elif binding_id not in bindings:
                    reasons.append("COMMAND_BINDING_MISSING")
                elif _RESOURCE_PROTOCOLS[capability] not in bindings[binding_id].protocols:
                    reasons.append("COMMAND_PROTOCOL_DENIED")
            if capability == "customer-repository" and normalized.get("customer_authorization_receipt"):
                try:
                    require_sha256_digest(
                        normalized["customer_authorization_receipt"],
                        "resources.customer-repository.customer_authorization_receipt",
                    )
                except ContractError:
                    reasons.append("CUSTOMER_AUTHORIZATION_RECEIPT_INVALID")
            capability_results[capability] = {
                "status": "READY_FOR_AUTHORIZED_EXECUTION" if not reasons else "BLOCKED",
                "reasons": sorted(set(reasons)),
                "execution_performed": False,
                "external_evidence": "NOT_RUN",
            }

        provider_values = require_mapping(manifest.get("providers", {}), "qualification manifest.providers")
        provider_results: dict[str, Any] = {}
        for adapter_id in PROVIDER_PROFILES:
            raw = provider_values.get(adapter_id)
            reasons = []
            if not isinstance(raw, Mapping):
                reasons.append("PROVIDER_BINDING_MISSING")
                provider = {}
            else:
                provider = dict(raw)
                _require_exact_fields(
                    provider,
                    _PROVIDER_FIELDS,
                    f"qualification manifest.providers.{adapter_id}",
                )
                for field in ("version", "provider_instance", "credential_lease_ref", "binding_id"):
                    if not isinstance(provider.get(field), str) or not str(provider[field]).strip():
                        reasons.append(f"FIELD_MISSING:{field}")
            binding_id = provider.get("binding_id")
            if binding_id:
                if binding_id in binding_errors:
                    reasons.append(f"COMMAND_BINDING_INVALID:{binding_errors[binding_id]}")
                elif binding_id not in bindings:
                    reasons.append("COMMAND_BINDING_MISSING")
                elif f"elmos.provider.{adapter_id}.v2" not in bindings[binding_id].protocols:
                    reasons.append("COMMAND_PROTOCOL_DENIED")
            provider_results[adapter_id] = {
                "status": "READY_FOR_AUTHORIZED_EXECUTION" if not reasons else "BLOCKED",
                "reasons": sorted(set(reasons)),
                "conformance_units": 12,
                "execution_performed": False,
                "external_evidence": "NOT_RUN",
            }
        extra_providers = sorted(set(provider_values) - set(PROVIDER_PROFILES))
        if extra_providers:
            raise ContractError("ADAPTER_UNKNOWN", f"unknown provider bindings: {', '.join(extra_providers)}")

        verifier = require_mapping(
            manifest.get("independent_verifier", {}), "qualification manifest.independent_verifier"
        )
        _require_exact_fields(
            verifier,
            _VERIFIER_FIELDS,
            "qualification manifest.independent_verifier",
        )
        verifier_reasons = []
        for field in (
            "verifier_id",
            "trust_store_ref",
            "public_key_digest",
            "authorization_receipt",
            "binding_id",
        ):
            if not isinstance(verifier.get(field), str) or not str(verifier[field]).strip():
                verifier_reasons.append(f"FIELD_MISSING:{field}")
        for field in ("public_key_digest", "authorization_receipt"):
            if not verifier.get(field):
                continue
            try:
                require_sha256_digest(
                    verifier[field],
                    f"independent_verifier.{field}",
                )
            except ContractError:
                verifier_reasons.append(f"{field.upper()}_INVALID")
        verifier_binding_id = verifier.get("binding_id")
        if verifier_binding_id:
            if verifier_binding_id in binding_errors:
                verifier_reasons.append(f"COMMAND_BINDING_INVALID:{binding_errors[verifier_binding_id]}")
            elif verifier_binding_id not in bindings:
                verifier_reasons.append("COMMAND_BINDING_MISSING")
            elif "elmos.independent-verifier.v2" not in bindings[verifier_binding_id].protocols:
                verifier_reasons.append("COMMAND_PROTOCOL_DENIED")
        verifier_status = "READY_FOR_INDEPENDENT_VERIFICATION" if not verifier_reasons else "BLOCKED"

        all_ready = (
            not binding_errors
            and all(item["status"] == "READY_FOR_AUTHORIZED_EXECUTION" for item in capability_results.values())
            and all(item["status"] == "READY_FOR_AUTHORIZED_EXECUTION" for item in provider_results.values())
            and verifier_status == "READY_FOR_INDEPENDENT_VERIFICATION"
        )
        suite_readiness = {
            "T00": "LOCAL_GATE_REQUIRED",
            "T01": capability_results["postgresql"]["status"],
            "T02": capability_results["scm"]["status"],
            "T03": capability_results["object-store"]["status"],
            "T04": capability_results["event-bus"]["status"],
            "T05": capability_results["secrets-broker"]["status"],
            "T06": (
                "READY_FOR_AUTHORIZED_EXECUTION"
                if all(item["status"] == "READY_FOR_AUTHORIZED_EXECUTION" for item in provider_results.values())
                else "BLOCKED"
            ),
            "T07": capability_results["kubernetes"]["status"],
            "T08": (
                "READY_FOR_AUTHORIZED_EXECUTION"
                if capability_results["customer-repository"]["status"] == "READY_FOR_AUTHORIZED_EXECUTION"
                and verifier_status == "READY_FOR_INDEPENDENT_VERIFICATION"
                else "BLOCKED"
            ),
        }
        return {
            "schema_version": "2.0.0",
            "manifest_hash": digest(manifest),
            "scope_hash": digest(scope),
            "ready_for_authorized_execution": all_ready,
            "command_bindings": {
                binding_id: {
                    "status": ("BLOCKED" if binding_id in binding_errors else "READY_FOR_AUTHORIZED_EXECUTION"),
                    "reason": binding_errors.get(binding_id),
                    "protocols": (list(bindings[binding_id].protocols) if binding_id in bindings else []),
                    "executable_sha256": (bindings[binding_id].executable_sha256 if binding_id in bindings else None),
                    "execution_performed": False,
                }
                for binding_id in sorted(binding_values)
            },
            "capabilities": capability_results,
            "providers": provider_results,
            "provider_count": len(provider_results),
            "provider_conformance_units": len(provider_results) * 12,
            "independent_verifier": {"status": verifier_status, "reasons": sorted(set(verifier_reasons))},
            "suite_readiness": suite_readiness,
            "execution_performed": False,
            "external_evidence": "NOT_RUN",
            "levels": {level: "NOT_RUN" for level in ("E1", "E2", "E3", "E4", "E5")},
            "certification": "NOT_CERTIFIED",
            "p05": {"issued": False, "decision": "P05_DEPLOYMENT_COMPLETE_NOT_ISSUED"},
            "evaluated_at": utc_now(),
        }


def load_qualification_manifest(path_value: str | os.PathLike[str]) -> dict[str, Any]:
    path = Path(path_value)
    if path.is_symlink():
        raise ContractError("MANIFEST_PATH_INVALID", "qualification manifest must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ContractError("MANIFEST_PATH_INVALID", "qualification manifest is unavailable") from exc
    if not resolved.is_file() or resolved.stat().st_size > 1024 * 1024:
        raise ContractError("MANIFEST_PATH_INVALID", "qualification manifest must be a regular file under 1 MiB")
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("MANIFEST_INVALID", "qualification manifest must be valid UTF-8 JSON") from exc
    return require_mapping(value, "qualification manifest")
