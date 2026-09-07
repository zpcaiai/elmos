#!/usr/bin/env python3
"""Signed native adapter runner for the 38 repository-migration Skills.

Only an operator-signed registry can select a digest-pinned executable and
typed argv contract. Mutating operations require a different approver, an
idempotency key, a monotonic fencing token, and a registered compensation.
Unknown side-effect outcomes remain UNKNOWN and cannot be retried implicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import migration_platform as platform
from actor_trust import ActorTrustStore
from domain_handlers import contract_for_batch
from transaction_store import StoreConflict


MAX_FILE_BYTES = 1024 * 1024 * 1024
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{0,62}[a-z0-9]$")
BASE_ENV = {"PATH", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR"}
FINAL_STATES = {"SUCCEEDED", "FAILED", "UNKNOWN", "COMPENSATED"}


class AdapterError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest(value: Any) -> str:
    return digest_bytes(canonical_bytes(value))


def read_regular(path: Path, maximum: int, label: str) -> bytes:
    resolved = path.expanduser().resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode) or observed.st_size > maximum:
            raise AdapterError(f"{label} must be a bounded regular file")
        result = bytearray()
        while len(result) < observed.st_size:
            chunk = os.read(descriptor, min(65536, observed.st_size - len(result)))
            if not chunk:
                raise AdapterError(f"{label} changed while being read")
            result.extend(chunk)
        if os.read(descriptor, 1):
            raise AdapterError(f"{label} changed while being read")
        return bytes(result)
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class Operation:
    name: str
    argv: tuple[str, ...]
    parameters: tuple[dict[str, Any], ...]
    timeout_seconds: int
    effect_class: str
    compensation_operation: str | None


@dataclass(frozen=True)
class Adapter:
    adapter_id: str
    capability: str
    executable: Path
    executable_sha256: str
    version: str
    environment_allowlist: tuple[str, ...]
    operations: dict[str, Operation]


@dataclass(frozen=True)
class Registry:
    registry_id: str
    sha256: str
    signer: dict[str, Any]
    adapters: dict[str, Adapter]

    @classmethod
    def load(cls, path: Path, trust: ActorTrustStore, source_fingerprint: str) -> "Registry":
        payload_envelope = json.loads(read_regular(path, 8 * 1024 * 1024, "adapter registry"))
        payload = payload_envelope.get("payload") if isinstance(payload_envelope, dict) else None
        if not isinstance(payload, dict):
            raise AdapterError("adapter registry signed payload is missing")
        registry_id, values = payload.get("registry_id"), payload.get("adapters")
        if (payload.get("schema_version") != "1.0" or not isinstance(registry_id, str) or
                not IDENTIFIER.fullmatch(registry_id) or payload.get("source_fingerprint") != source_fingerprint or
                not isinstance(values, list) or not values):
            raise AdapterError("adapter registry identity, source binding, or entries are invalid")
        signer = trust.verify(payload_envelope, "adapter-admin", {"registry_id": registry_id, "source_fingerprint": source_fingerprint})
        adapters: dict[str, Adapter] = {}
        for value in values:
            adapter = parse_adapter(value)
            if adapter.adapter_id in adapters:
                raise AdapterError(f"duplicate adapter id: {adapter.adapter_id}")
            adapters[adapter.adapter_id] = adapter
        material = {"registry_id": registry_id, "source_fingerprint": source_fingerprint, "adapters": values}
        return cls(registry_id, digest(material), signer, adapters)


def parse_adapter(value: Any) -> Adapter:
    fields = {"adapter_id", "capability", "executable", "executable_sha256", "version", "environment_allowlist", "operations"}
    if not isinstance(value, dict) or set(value) != fields:
        raise AdapterError("adapter fields are invalid")
    adapter_id, capability = value.get("adapter_id"), value.get("capability")
    executable_value = value.get("executable")
    if (not isinstance(adapter_id, str) or not IDENTIFIER.fullmatch(adapter_id) or
            not isinstance(capability, str) or not IDENTIFIER.fullmatch(capability) or
            not isinstance(executable_value, str) or not Path(executable_value).is_absolute()):
        raise AdapterError("adapter identity, capability, or executable is invalid")
    source_path = Path(executable_value)
    executable = source_path.resolve(strict=True)
    if source_path.is_symlink() or not executable.is_file() or not os.access(executable, os.X_OK):
        raise AdapterError(f"adapter {adapter_id} executable must be a non-symlink executable regular file")
    expected = platform.require_digest(value.get("executable_sha256"), f"adapter {adapter_id} executable_sha256")
    if digest_bytes(read_regular(executable, MAX_FILE_BYTES, f"adapter {adapter_id} executable")) != expected:
        raise AdapterError(f"adapter {adapter_id} executable digest mismatch")
    environment, operation_values, version = value.get("environment_allowlist"), value.get("operations"), value.get("version")
    if (not isinstance(environment, list) or len(environment) != len(set(environment)) or
            any(not isinstance(item, str) or not item or item in BASE_ENV for item in environment) or
            not isinstance(operation_values, list) or not operation_values or not isinstance(version, str) or not version):
        raise AdapterError(f"adapter {adapter_id} version/environment/operations are invalid")
    operations: dict[str, Operation] = {}
    for item in operation_values:
        operation = parse_operation(adapter_id, item)
        if operation.name in operations:
            raise AdapterError(f"adapter {adapter_id} duplicates operation {operation.name}")
        operations[operation.name] = operation
    referenced_compensations = {item.compensation_operation for item in operations.values() if item.compensation_operation}
    for operation in operations.values():
        if operation.effect_class == "read-only":
            if operation.compensation_operation is not None:
                raise AdapterError(f"read-only operation {adapter_id}/{operation.name} cannot declare compensation")
            continue
        if operation.compensation_operation == operation.name:
            raise AdapterError(f"operation {adapter_id}/{operation.name} cannot compensate itself")
        if operation.name in referenced_compensations:
            if operation.compensation_operation is not None:
                raise AdapterError(f"compensation {adapter_id}/{operation.name} cannot require another compensation")
            continue
        if operation.compensation_operation not in operations:
            raise AdapterError(f"mutating operation {adapter_id}/{operation.name} lacks registered compensation")
        compensation = operations[operation.compensation_operation]
        if compensation.effect_class == "read-only":
            raise AdapterError(f"compensation {adapter_id}/{operation.compensation_operation} cannot be read-only")
        if compensation.compensation_operation is not None:
            raise AdapterError(f"compensation {adapter_id}/{operation.compensation_operation} cannot require another compensation")
    return Adapter(adapter_id, capability, executable, expected, version, tuple(environment), operations)


def parse_operation(adapter_id: str, value: Any) -> Operation:
    fields = {"name", "argv", "parameters", "timeout_seconds", "effect_class", "compensation_operation"}
    if not isinstance(value, dict) or set(value) != fields:
        raise AdapterError(f"adapter {adapter_id} operation fields are invalid")
    name, argv, parameters = value.get("name"), value.get("argv"), value.get("parameters")
    timeout, effect, compensation = value.get("timeout_seconds"), value.get("effect_class"), value.get("compensation_operation")
    if (not isinstance(name, str) or not IDENTIFIER.fullmatch(name) or not isinstance(argv, list) or
            any(not isinstance(item, str) or not item for item in argv) or not isinstance(parameters, list) or
            not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 86400 or
            effect not in {"read-only", "reversible", "approval-required"} or
            compensation is not None and (not isinstance(compensation, str) or not IDENTIFIER.fullmatch(compensation))):
        raise AdapterError(f"adapter {adapter_id} operation {name!r} is invalid")
    names: set[str] = set()
    for parameter in parameters:
        if (not isinstance(parameter, dict) or set(parameter) != {"name", "flag", "type", "required"} or
                not isinstance(parameter.get("name"), str) or not IDENTIFIER.fullmatch(parameter["name"]) or parameter["name"] in names or
                not isinstance(parameter.get("flag"), str) or not parameter["flag"].startswith("-") or
                parameter.get("type") not in {"identifier", "integer", "path", "https-url"} or not isinstance(parameter.get("required"), bool)):
            raise AdapterError(f"adapter {adapter_id} operation parameter is invalid")
        names.add(parameter["name"])
    return Operation(name, tuple(argv), tuple(parameters), timeout, effect, compensation)


def parameter_value(value: Any, specification: dict[str, Any], roots: tuple[Path, ...]) -> str:
    kind, name = specification["type"], specification["name"]
    if kind == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise AdapterError(f"parameter {name} must be an integer")
        return str(value)
    if not isinstance(value, str) or not value or "\x00" in value:
        raise AdapterError(f"parameter {name} must be a non-empty string")
    if kind == "identifier" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,1023}", value):
        raise AdapterError(f"parameter {name} is not a safe identifier")
    if kind == "https-url":
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise AdapterError(f"parameter {name} must be an HTTPS URL without credentials")
    if kind == "path":
        resolved = Path(value).expanduser().resolve(strict=True)
        if not any(resolved == root or root in resolved.parents for root in roots):
            raise AdapterError(f"parameter {name} path escapes approved roots")
        return str(resolved)
    return value


def redacted(data: bytes, secrets: tuple[str, ...]) -> bytes:
    text = data[:MAX_CAPTURE_BYTES].decode("utf-8", errors="replace")
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return text.encode("utf-8")


def execute(workspace: Path, request_path: Path, registry_path: Path, trust_path: Path,
            approved_roots: tuple[Path, ...]) -> dict[str, Any]:
    request = json.loads(read_regular(request_path, 8 * 1024 * 1024, "adapter request"))
    fields = {"schema_version", "batch", "adapter_id", "operation", "parameters", "idempotency_key", "fencing_token", "source_fingerprint", "approval", "compensates_idempotency_key"}
    if not isinstance(request, dict) or set(request) != fields or request.get("schema_version") != "1.0":
        raise AdapterError("adapter request fields are invalid")
    batch, key, fencing = request.get("batch"), request.get("idempotency_key"), request.get("fencing_token")
    if (not isinstance(batch, int) or not 1 <= batch <= 38 or not isinstance(key, str) or not IDENTIFIER.fullmatch(key) or
            not isinstance(fencing, int) or isinstance(fencing, bool) or fencing < 1):
        raise AdapterError("adapter request Batch/idempotency/fencing identity is invalid")
    compensates_key = request.get("compensates_idempotency_key")
    if compensates_key is not None and (not isinstance(compensates_key, str) or not IDENTIFIER.fullmatch(compensates_key) or compensates_key == key):
        raise AdapterError("compensates_idempotency_key is invalid")
    paths, _, profile = platform.require_prepared(workspace, batch)
    metadata = platform.state_store(workspace).metadata()
    source_fingerprint = platform.require_digest(request.get("source_fingerprint"), "source_fingerprint")
    if source_fingerprint != metadata["source_fingerprint"]:
        raise AdapterError("adapter request source fingerprint is stale")
    trust = ActorTrustStore.load(trust_path)
    registry = Registry.load(registry_path, trust, source_fingerprint)
    adapter = registry.adapters.get(request.get("adapter_id"))
    operation = adapter.operations.get(request.get("operation")) if adapter else None
    if adapter is None or operation is None:
        raise AdapterError("adapter or operation is not registered")
    parameters = request.get("parameters")
    if not isinstance(parameters, dict):
        raise AdapterError("adapter parameters must be an object")
    specs = {item["name"]: item for item in operation.parameters}
    if set(parameters) - set(specs) or any(item["required"] and item["name"] not in parameters for item in operation.parameters):
        raise AdapterError("adapter parameters differ from the signed operation contract")
    roots = tuple(root.expanduser().resolve(strict=True) for root in approved_roots)
    argv = [str(adapter.executable), *operation.argv]
    for spec in operation.parameters:
        if spec["name"] in parameters:
            argv.extend((spec["flag"], parameter_value(parameters[spec["name"]], spec, roots)))
    identity = {
        "batch": batch, "skill": profile["skill"], "domain_contract": contract_for_batch(batch),
        "adapter_id": adapter.adapter_id, "adapter_registry_sha256": registry.sha256, "operation": operation.name,
        "parameters_sha256": digest(parameters), "source_fingerprint": source_fingerprint,
        "effect_class": operation.effect_class, "idempotency_key": key, "fencing_token": fencing,
        "compensates_idempotency_key": compensates_key,
    }
    request_sha256 = digest(identity)
    if operation.effect_class == "read-only":
        if request.get("approval") is not None:
            raise AdapterError("read-only adapter operation cannot carry an unnecessary approval")
        approval, actor_id, approval_id = None, registry.signer["actor_id"], "not-required"
    else:
        approval = trust.verify(request.get("approval"), "approver", {
            "request_sha256": request_sha256, "adapter_id": adapter.adapter_id, "operation": operation.name,
            "source_fingerprint": source_fingerprint, "effect_class": operation.effect_class,
        })
        if approval["actor_id"] == registry.signer["actor_id"]:
            raise AdapterError("adapter administrator and effect approver must be separate actors")
        actor_id, approval_id = approval["actor_id"], approval["record_id"]
    environment = {name: value for name, value in os.environ.items() if name in BASE_ENV}
    missing = [name for name in adapter.environment_allowlist if name not in os.environ]
    if missing:
        raise AdapterError(f"missing required environment references: {missing}")
    for name in adapter.environment_allowlist:
        environment[name] = os.environ[name]
    environment["ELMOS_IDEMPOTENCY_KEY"] = key
    store = platform.state_store(workspace)
    audit_findings = store.verify_event_chain()
    if audit_findings:
        raise AdapterError(f"transactional state audit failed: {audit_findings[0]}")
    if compensates_key is not None:
        original = next((item for item in store.effects() if item.get("idempotency_key") == compensates_key), None)
        original_receipt = original.get("receipt") if isinstance(original, dict) else None
        if (not isinstance(original, dict) or original.get("state") != "SUCCEEDED" or
                not isinstance(original_receipt, dict) or original_receipt.get("compensation_operation") != operation.name):
            raise AdapterError("compensation request is not bound to a succeeded compensatable effect")
    action = f"{adapter.adapter_id}:{operation.name}"
    target = f"{adapter.capability}:{digest(parameters)}"
    try:
        planned = platform.plan_effect(workspace, batch, key, action, target, actor_id, approval_id, fencing,
                                       operation.effect_class != "approval-required")
    except platform.RuntimeFailure as exc:
        raise AdapterError(str(exc)) from exc
    if planned["state"] in FINAL_STATES:
        return {**planned["receipt"], "idempotent_replay": True}
    if planned["state"] != "PLANNED":
        raise AdapterError(f"effect is {planned['state']}; reconcile before retry")
    effect_identity = {"batch": batch, "action": action, "target": target, "actor_id": actor_id,
                       "approval_id": approval_id, "fencing_token": fencing,
                       "reversible": operation.effect_class != "approval-required"}
    effect_sha256 = platform.sha256_bytes(platform.canonical_bytes({"idempotency_key": key, **effect_identity}))
    store.transition_effect(key, effect_sha256, "PLANNED", "RUNNING", {"request_sha256": request_sha256}, platform.utc_now())
    started, timed_out, ambiguous = platform.utc_now(), False, False
    try:
        process = subprocess.Popen(argv, cwd=paths["root"], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True, shell=False)
        try:
            stdout_raw, stderr_raw = process.communicate(timeout=operation.timeout_seconds)
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            timed_out, ambiguous = True, operation.effect_class != "read-only"
            try:
                os.killpg(process.pid, signal.SIGTERM)
                stdout_raw, stderr_raw = process.communicate(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout_raw, stderr_raw = process.communicate()
            exit_code = None
    except OSError as exc:
        stdout_raw, stderr_raw, exit_code = b"", str(exc).encode("utf-8"), None
    secrets = tuple(os.environ[name] for name in adapter.environment_allowlist)
    stdout, stderr = redacted(stdout_raw, secrets), redacted(stderr_raw, secrets)
    stdout_ref, stderr_ref = platform.store_bytes(paths, stdout), platform.store_bytes(paths, stderr)
    state = "UNKNOWN" if ambiguous else ("SUCCEEDED" if exit_code == 0 and not timed_out else "FAILED")
    receipt = {
        **identity, "request_sha256": request_sha256, "state": state,
        "decision": "PASS" if state == "SUCCEEDED" else ("INCONCLUSIVE" if state == "UNKNOWN" else "FAIL"),
        "started_at": started, "finished_at": platform.utc_now(), "exit_code": exit_code, "timed_out": timed_out,
        "stdout": stdout_ref, "stderr": stderr_ref, "approval": approval,
        "compensation_operation": operation.compensation_operation,
        "limitations": (["side-effect outcome is unknown; reconcile before retry or compensation"] if state == "UNKNOWN" else []),
        "idempotent_replay": False,
    }
    store.transition_effect(key, effect_sha256, "RUNNING", state, receipt, receipt["finished_at"], compensates_key)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--adapter-registry", type=Path, required=True)
    parser.add_argument("--actor-trust-store", type=Path, required=True)
    parser.add_argument("--approved-root", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = execute(args.workspace, args.request, args.adapter_registry, args.actor_trust_store, tuple(args.approved_root))
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise AdapterError("refusing to overwrite adapter receipt")
        platform.atomic_write(args.output, encoded.encode("utf-8"))
    print(encoded, end="")
    return 0 if result["state"] == "SUCCEEDED" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AdapterError, StoreConflict, platform.RuntimeFailure, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"decision": "BLOCKED", "error": str(exc)}, ensure_ascii=False), file=os.sys.stderr)
        raise SystemExit(2) from exc
