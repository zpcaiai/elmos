#!/usr/bin/env python3
"""Trusted external operation runtime for Precision Migration campaigns.

Repository content cannot choose a command.  Only an externally supplied,
Ed25519-signed adapter registry may bind a stage to a digest-pinned executable
and typed argv template.  Mutating operations require a separate production
approver, fencing, idempotency, and a registered rollback adapter.  Ambiguous
side-effect outcomes become UNKNOWN and cannot be retried implicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import sqlite3
import stat
import subprocess
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from scripts.precision_migration.external import (
    ExternalProfileRegistry,
    STAGES,
    STAGE_PARTITIONS,
    validate_external_case_binding,
)
from scripts.precision_migration.trust import (
    TrustStore,
    canonical_digest,
    configured_roots,
    verify_content_reference,
)


MAX_REGISTRY_BYTES = 8 * 1024 * 1024
MAX_CAPTURE_BYTES = 4 * 1024 * 1024
PRODUCTION_STAGES = ("production_hsm", "authorized_canary", "verified_rollback")
ALL_STAGES = (*STAGES, *PRODUCTION_STAGES)
IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{0,62}[a-z0-9]$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
PLACEHOLDER = re.compile(r"^\{param:([a-z][a-z0-9-]{0,62}[a-z0-9])\}$")
BASE_ENV = ("PATH", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR", "SYSTEMROOT")
FINAL_STATES = {"SUCCEEDED", "FAILED", "UNKNOWN", "COMPENSATED"}


class ProductionRuntimeError(ValueError):
    pass


def _sha_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _read_regular(path: Path, maximum: int, label: str) -> bytes:
    supplied = path.expanduser()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(supplied, flags)
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode) or observed.st_size > maximum:
            raise ProductionRuntimeError(f"{label} must be a bounded regular file")
        result = bytearray()
        remaining = observed.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ProductionRuntimeError(f"{label} changed while being read")
            result.extend(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ProductionRuntimeError(f"{label} changed while being read")
        return bytes(result)
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class Parameter:
    name: str
    kind: str
    required: bool


@dataclass(frozen=True)
class Adapter:
    adapter_id: str
    stage: str
    executable: Path
    executable_digest: str
    argv: tuple[str, ...]
    parameters: tuple[Parameter, ...]
    environment_allowlist: tuple[str, ...]
    timeout_seconds: int
    effect_class: str
    compensation_adapter: str | None


@dataclass(frozen=True)
class TrustedAdapterRegistry:
    registry_id: str
    digest: str
    signer: dict[str, Any]
    adapters: dict[str, Adapter]

    @classmethod
    def load(
        cls,
        path: Path,
        trust_store: TrustStore,
        profile_registry: ExternalProfileRegistry,
    ) -> "TrustedAdapterRegistry":
        envelope = json.loads(_read_regular(path, MAX_REGISTRY_BYTES, "adapter registry").decode("utf-8"))
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            raise ProductionRuntimeError("signed adapter registry payload is missing")
        registry_id = payload.get("registry_id")
        if not isinstance(registry_id, str) or IDENTIFIER.fullmatch(registry_id) is None:
            raise ProductionRuntimeError("adapter registry identity is invalid")
        signer = trust_store.verify_envelope(
            envelope,
            required_role="external-adapter-admin",
            bindings={
                "record_type": "PRECISION_EXTERNAL_ADAPTER_REGISTRY",
                "registry_id": registry_id,
                "profile_registry_digest": profile_registry.digest,
            },
        )
        values = payload.get("adapters")
        if not isinstance(values, list) or not values:
            raise ProductionRuntimeError("adapter registry must contain adapters")
        adapters: dict[str, Adapter] = {}
        for value in values:
            adapter = _parse_adapter(value)
            if adapter.adapter_id in adapters:
                raise ProductionRuntimeError(f"duplicate adapter id: {adapter.adapter_id}")
            adapters[adapter.adapter_id] = adapter
        for adapter in adapters.values():
            if adapter.effect_class == "reversible":
                compensation = adapters.get(str(adapter.compensation_adapter))
                if compensation is None or compensation.stage != "verified_rollback":
                    raise ProductionRuntimeError(f"reversible adapter lacks a rollback adapter: {adapter.adapter_id}")
                if compensation.effect_class not in {"reversible", "approval-required"}:
                    raise ProductionRuntimeError(f"rollback adapter has an invalid effect class: {compensation.adapter_id}")
            elif adapter.compensation_adapter is not None:
                raise ProductionRuntimeError(f"non-reversible adapter cannot name compensation: {adapter.adapter_id}")
        return cls(
            registry_id=registry_id,
            digest=canonical_digest(payload),
            signer=signer,
            adapters=adapters,
        )


def _parse_adapter(value: Any) -> Adapter:
    fields = {
        "adapter_id", "stage", "executable", "executable_digest", "argv", "parameters",
        "environment_allowlist", "timeout_seconds", "effect_class", "compensation_adapter",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ProductionRuntimeError("adapter fields are invalid")
    adapter_id = value.get("adapter_id")
    stage = value.get("stage")
    executable_value = value.get("executable")
    if (
        not isinstance(adapter_id, str)
        or IDENTIFIER.fullmatch(adapter_id) is None
        or stage not in ALL_STAGES
        or not isinstance(executable_value, str)
        or not Path(executable_value).is_absolute()
    ):
        raise ProductionRuntimeError("adapter identity, stage, or executable is invalid")
    supplied = Path(executable_value)
    executable = supplied.resolve(strict=True)
    if supplied.is_symlink() or not executable.is_file() or not os.access(executable, os.X_OK):
        raise ProductionRuntimeError(f"adapter executable must be a non-symlink executable: {adapter_id}")
    executable_digest = value.get("executable_digest")
    if not isinstance(executable_digest, str) or DIGEST.fullmatch(executable_digest) is None:
        raise ProductionRuntimeError(f"adapter executable digest is invalid: {adapter_id}")
    if _sha_bytes(_read_regular(executable, 1024 * 1024 * 1024, f"adapter executable {adapter_id}")) != executable_digest:
        raise ProductionRuntimeError(f"adapter executable digest mismatch: {adapter_id}")
    argv = value.get("argv")
    parameter_values = value.get("parameters")
    if not isinstance(argv, list) or any(not isinstance(item, str) or not item or "\x00" in item for item in argv):
        raise ProductionRuntimeError(f"adapter argv is invalid: {adapter_id}")
    if not isinstance(parameter_values, list):
        raise ProductionRuntimeError(f"adapter parameters are invalid: {adapter_id}")
    parameters: list[Parameter] = []
    names: set[str] = set()
    for item in parameter_values:
        if (
            not isinstance(item, dict)
            or set(item) != {"name", "type", "required"}
            or not isinstance(item.get("name"), str)
            or IDENTIFIER.fullmatch(item["name"]) is None
            or item["name"] in names
            or item.get("type") not in {"identifier", "integer", "path", "digest"}
            or not isinstance(item.get("required"), bool)
        ):
            raise ProductionRuntimeError(f"adapter parameter contract is invalid: {adapter_id}")
        names.add(item["name"])
        parameters.append(Parameter(item["name"], item["type"], item["required"]))
    referenced: set[str] = set()
    for token in argv:
        match = PLACEHOLDER.fullmatch(token)
        if match:
            referenced.add(match.group(1))
        elif "{param:" in token:
            raise ProductionRuntimeError(f"adapter placeholders must occupy a complete argv token: {adapter_id}")
    if referenced != names:
        raise ProductionRuntimeError(f"adapter argv/parameter bindings diverge: {adapter_id}")
    environment = value.get("environment_allowlist")
    if (
        not isinstance(environment, list)
        or len(environment) != len(set(environment))
        or any(not isinstance(item, str) or not item or item in BASE_ENV for item in environment)
    ):
        raise ProductionRuntimeError(f"adapter environment allowlist is invalid: {adapter_id}")
    timeout = value.get("timeout_seconds")
    effect = value.get("effect_class")
    compensation = value.get("compensation_adapter")
    if (
        not isinstance(timeout, int)
        or isinstance(timeout, bool)
        or not 1 <= timeout <= 86400
        or effect not in {"read-only", "reversible", "approval-required"}
        or compensation is not None and (not isinstance(compensation, str) or IDENTIFIER.fullmatch(compensation) is None)
    ):
        raise ProductionRuntimeError(f"adapter timeout/effect/compensation is invalid: {adapter_id}")
    if stage in STAGES and effect != "read-only":
        raise ProductionRuntimeError(f"qualification stage adapter must be read-only: {adapter_id}")
    if stage == "authorized_canary" and effect != "reversible":
        raise ProductionRuntimeError(f"Canary adapter must be reversible: {adapter_id}")
    return Adapter(
        adapter_id, str(stage), executable, executable_digest, tuple(argv), tuple(parameters),
        tuple(environment), timeout, str(effect), compensation,
    )


class OperationLedger:
    def __init__(self, path: Path) -> None:
        supplied = path.expanduser()
        if supplied.is_symlink():
            raise ProductionRuntimeError("operation ledger must not be a symlink")
        supplied.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent = supplied.parent.resolve(strict=True)
        self.path = parent / supplied.name
        if self.path.exists():
            observed = self.path.lstat()
            if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
                raise ProductionRuntimeError("operation ledger must be a regular file")
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=FULL;
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    target_digest TEXT NOT NULL,
                    fencing_token INTEGER NOT NULL,
                    request_digest TEXT NOT NULL,
                    adapter_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    state TEXT NOT NULL,
                    receipt_json TEXT,
                    compensates_idempotency_key TEXT,
                    UNIQUE(target_digest, fencing_token)
                );
                """
            )
        os.chmod(self.path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def begin(self, identity: dict[str, Any]) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM operations WHERE idempotency_key=?", (identity["idempotency_key"],)
            ).fetchone()
            if existing:
                if existing["request_digest"] != identity["request_digest"]:
                    raise ProductionRuntimeError("idempotency key is bound to a different request")
                if existing["state"] in FINAL_STATES and existing["receipt_json"]:
                    connection.execute("COMMIT")
                    return json.loads(existing["receipt_json"])
                raise ProductionRuntimeError(f"operation is {existing['state']}; reconcile before retry")
            higher = connection.execute(
                "SELECT MAX(fencing_token) AS token FROM operations WHERE target_digest=?",
                (identity["target_digest"],),
            ).fetchone()["token"]
            if higher is not None and identity["fencing_token"] <= int(higher):
                raise ProductionRuntimeError("fencing token is stale")
            connection.execute(
                "INSERT INTO operations(operation_id,idempotency_key,target_digest,fencing_token,request_digest,adapter_id,stage,state,compensates_idempotency_key) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    identity["operation_id"], identity["idempotency_key"], identity["target_digest"],
                    identity["fencing_token"], identity["request_digest"], identity["adapter_id"],
                    identity["stage"], "RUNNING", identity["compensates_idempotency_key"],
                ),
            )
            connection.execute("COMMIT")
            return None
        except sqlite3.IntegrityError as exc:
            connection.execute("ROLLBACK")
            raise ProductionRuntimeError(f"operation identity/fencing conflict: {exc}") from exc
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def original(self, key: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM operations WHERE idempotency_key=?", (key,)).fetchone()
            return dict(row) if row else None

    def finish(self, operation_id: str, state: str, receipt: dict[str, Any]) -> None:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT state FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
            if row is None or row["state"] != "RUNNING" or state not in FINAL_STATES:
                connection.execute("ROLLBACK")
                raise ProductionRuntimeError("operation state transition is invalid")
            connection.execute(
                "UPDATE operations SET state=?,receipt_json=? WHERE operation_id=?",
                (state, json.dumps(receipt, ensure_ascii=False, sort_keys=True), operation_id),
            )
            connection.execute("COMMIT")

    def mark_compensated(self, key: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT state,receipt_json FROM operations WHERE idempotency_key=?", (key,)).fetchone()
            if row is None or row["state"] != "SUCCEEDED":
                connection.execute("ROLLBACK")
                raise ProductionRuntimeError("compensated operation is not in SUCCEEDED state")
            receipt = json.loads(row["receipt_json"])
            receipt["compensated"] = True
            connection.execute(
                "UPDATE operations SET state='COMPENSATED',receipt_json=? WHERE idempotency_key=?",
                (json.dumps(receipt, ensure_ascii=False, sort_keys=True), key),
            )
            connection.execute("COMMIT")


def _parameter(value: Any, specification: Parameter, roots: tuple[Path, ...]) -> str:
    if specification.kind == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ProductionRuntimeError(f"parameter {specification.name} must be an integer")
        return str(value)
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ProductionRuntimeError(f"parameter {specification.name} must be a non-empty string")
    if specification.kind == "identifier" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,1023}", value) is None:
        raise ProductionRuntimeError(f"parameter {specification.name} is not a safe identifier")
    if specification.kind == "digest" and DIGEST.fullmatch(value) is None:
        raise ProductionRuntimeError(f"parameter {specification.name} is not a SHA-256 digest")
    if specification.kind == "path":
        resolved = Path(value).expanduser().resolve(strict=True)
        if not any(resolved == root or root in resolved.parents for root in roots):
            raise ProductionRuntimeError(f"parameter {specification.name} path escapes approved roots")
        return str(resolved)
    return value


def _redact(value: bytes, secrets: tuple[str, ...]) -> str:
    text = value[:MAX_CAPTURE_BYTES].decode("utf-8", errors="replace")
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return text


def _captured(sink: Any) -> tuple[bytes, bool]:
    size = os.fstat(sink.fileno()).st_size
    sink.seek(0)
    return sink.read(MAX_CAPTURE_BYTES), size > MAX_CAPTURE_BYTES


def _write_once_json(path: Path, payload: dict[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        rendered = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        offset = 0
        while offset < len(rendered):
            offset += os.write(descriptor, rendered[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def execute_operation(
    request: dict[str, Any],
    *,
    registry: TrustedAdapterRegistry,
    trust_store: TrustStore,
    evidence_roots: Iterable[Path],
    ledger: OperationLedger,
    output_dir: Path,
) -> dict[str, Any]:
    fields = {
        "schema_version", "operation_id", "campaign_id", "adapter_id", "stage", "parameters",
        "input_refs", "qualification_binding", "idempotency_key", "fencing_token",
        "compensates_idempotency_key", "authorization",
    }
    if not isinstance(request, dict) or set(request) != fields or request.get("schema_version") != 1:
        raise ProductionRuntimeError("external operation request fields are invalid")
    operation_id = request.get("operation_id")
    campaign_id = request.get("campaign_id")
    idempotency_key = request.get("idempotency_key")
    if any(not isinstance(item, str) or IDENTIFIER.fullmatch(item) is None for item in (operation_id, campaign_id, idempotency_key)):
        raise ProductionRuntimeError("operation/campaign/idempotency identity is invalid")
    fencing = request.get("fencing_token")
    if not isinstance(fencing, int) or isinstance(fencing, bool) or fencing < 1:
        raise ProductionRuntimeError("fencing_token must be a positive integer")
    adapter = registry.adapters.get(str(request.get("adapter_id")))
    if adapter is None or request.get("stage") != adapter.stage:
        raise ProductionRuntimeError("adapter/stage is not present in the signed registry")
    parameters = request.get("parameters")
    if not isinstance(parameters, dict):
        raise ProductionRuntimeError("parameters must be an object")
    specifications = {item.name: item for item in adapter.parameters}
    if set(parameters) - set(specifications) or any(item.required and item.name not in parameters for item in adapter.parameters):
        raise ProductionRuntimeError("parameters differ from the signed adapter contract")
    roots = configured_roots(evidence_roots)
    input_refs = request.get("input_refs")
    if not isinstance(input_refs, list) or len(input_refs) > 100:
        raise ProductionRuntimeError("input_refs must be a bounded array")
    observed_inputs = [verify_content_reference(item, roots) for item in input_refs]
    qualification = request.get("qualification_binding")
    verified_qualification: dict[str, Any] | None = None
    if adapter.stage in STAGES:
        qualification_fields = {
            "skill", "profile_digest", "partition", "case_digest", "corpus_ref_index",
        }
        if not isinstance(qualification, dict) or set(qualification) != qualification_fields:
            raise ProductionRuntimeError("qualification stage requires an exact Skill/corpus binding")
        corpus_index = qualification.get("corpus_ref_index")
        if (
            not isinstance(corpus_index, int)
            or isinstance(corpus_index, bool)
            or not 0 <= corpus_index < len(input_refs)
        ):
            raise ProductionRuntimeError("qualification corpus_ref_index is invalid")
        expected_partition = STAGE_PARTITIONS[adapter.stage]
        if qualification.get("partition") != expected_partition:
            raise ProductionRuntimeError("qualification corpus partition does not match the stage")
        try:
            verified_qualification = validate_external_case_binding(
                expected_partition,
                input_refs[corpus_index],
                skill=str(qualification.get("skill")),
                profile_digest=str(qualification.get("profile_digest")),
                case_digest=str(qualification.get("case_digest")),
                profile_registry=ExternalProfileRegistry.load(),
                evidence_roots=roots,
            )
        except ValueError as exc:
            raise ProductionRuntimeError(f"qualification binding failed verification: {exc}") from exc
        verified_qualification["corpus_ref_index"] = corpus_index
    elif qualification is not None:
        raise ProductionRuntimeError("production operation must not claim a qualification binding")
    values = {name: _parameter(value, specifications[name], roots) for name, value in parameters.items()}
    argv = [str(adapter.executable)]
    for token in adapter.argv:
        match = PLACEHOLDER.fullmatch(token)
        if match:
            name = match.group(1)
            if name in values:
                argv.append(values[name])
        else:
            argv.append(token)
    target_digest = canonical_digest({"adapter_id": adapter.adapter_id, "parameters": parameters})
    identity = {
        "operation_id": operation_id,
        "campaign_id": campaign_id,
        "adapter_id": adapter.adapter_id,
        "adapter_registry_digest": registry.digest,
        "stage": adapter.stage,
        "parameters_digest": canonical_digest(parameters),
        "input_digests": [item["digest"] for item in observed_inputs],
        "qualification_binding": verified_qualification,
        "idempotency_key": idempotency_key,
        "fencing_token": fencing,
        "compensates_idempotency_key": request.get("compensates_idempotency_key"),
        "target_digest": target_digest,
    }
    request_digest = canonical_digest(identity)
    role = "external-execution-authorizer" if adapter.effect_class == "read-only" else "production-change-approver"
    authorization = trust_store.verify_envelope(
        request.get("authorization"),
        required_role=role,
        bindings={
            "record_type": "PRECISION_EXTERNAL_OPERATION_AUTHORIZATION",
            "operation_id": operation_id,
            "campaign_id": campaign_id,
            "request_digest": request_digest,
            "decision": "APPROVED",
        },
    )
    if adapter.effect_class != "read-only" and authorization["key_id"] == registry.signer["key_id"]:
        raise ProductionRuntimeError("adapter administrator and production approver must be separate")
    compensation_key = request.get("compensates_idempotency_key")
    if compensation_key is not None:
        if not isinstance(compensation_key, str) or IDENTIFIER.fullmatch(compensation_key) is None:
            raise ProductionRuntimeError("compensates_idempotency_key is invalid")
        original = ledger.original(compensation_key)
        original_adapter = registry.adapters.get(original["adapter_id"]) if original else None
        if (
            original is None
            or original["state"] != "SUCCEEDED"
            or original_adapter is None
            or original_adapter.compensation_adapter != adapter.adapter_id
        ):
            raise ProductionRuntimeError("rollback is not bound to a succeeded compensatable operation")
    environment = {name: os.environ[name] for name in BASE_ENV if name in os.environ}
    missing_environment = [name for name in adapter.environment_allowlist if name not in os.environ]
    if missing_environment:
        raise ProductionRuntimeError(f"required environment references are missing: {missing_environment}")
    secrets = tuple(os.environ[name] for name in adapter.environment_allowlist)
    for name in adapter.environment_allowlist:
        environment[name] = os.environ[name]
    environment["ELMOS_PRECISION_OPERATION_ID"] = str(operation_id)
    environment["ELMOS_PRECISION_IDEMPOTENCY_KEY"] = str(idempotency_key)
    if output_dir.is_symlink():
        raise ProductionRuntimeError("external operation output directory must not be a symlink")
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not output_dir.is_dir():
        raise ProductionRuntimeError("external operation output path must be a directory")
    destination = output_dir / f"{operation_id}.json"
    existing_operation = ledger.original(str(idempotency_key))
    if existing_operation is not None:
        if existing_operation["request_digest"] != request_digest:
            raise ProductionRuntimeError("idempotency key is bound to a different request")
        if existing_operation["state"] in FINAL_STATES and existing_operation.get("receipt_json"):
            return {**json.loads(existing_operation["receipt_json"]), "idempotent_replay": True}
        raise ProductionRuntimeError(f"operation is {existing_operation['state']}; reconcile before retry")
    if destination.exists():
        raise ProductionRuntimeError("refusing to overwrite external operation receipt")
    ledger_identity = {**identity, "request_digest": request_digest}
    previous = ledger.begin(ledger_identity)
    if previous is not None:
        return {**previous, "idempotent_replay": True}
    timed_out = False
    stdout_truncated = False
    stderr_truncated = False
    try:
        # File-backed capture prevents an untrusted external tool from growing
        # the controller process without bound before the receipt truncates it.
        with tempfile.TemporaryFile() as stdout_sink, tempfile.TemporaryFile() as stderr_sink:
            process = subprocess.Popen(
                argv,
                cwd=output_dir,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_sink,
                stderr=stderr_sink,
                shell=False,
                start_new_session=True,
            )
            try:
                process.communicate(timeout=adapter.timeout_seconds)
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.communicate(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.communicate()
                exit_code = None
            stdout_raw, stdout_truncated = _captured(stdout_sink)
            stderr_raw, stderr_truncated = _captured(stderr_sink)
    except OSError as exc:
        stdout_raw, stderr_raw, exit_code = b"", str(exc).encode("utf-8"), None
    if exit_code == 0:
        state = "SUCCEEDED"
    elif adapter.effect_class == "read-only":
        state = "FAILED"
    else:
        state = "UNKNOWN"
    receipt_without_digest = {
        "schema_version": 1,
        **identity,
        "request_digest": request_digest,
        "state": state,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "effect_class": adapter.effect_class,
        "executable_digest": adapter.executable_digest,
        "argv_digest": canonical_digest(argv),
        "stdout": _redact(stdout_raw, secrets),
        "stderr": _redact(stderr_raw, secrets),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "authorization": authorization,
        "external_verification": "NOT_RUN",
    }
    receipt = {**receipt_without_digest, "receipt_digest": canonical_digest(receipt_without_digest)}
    ledger.finish(str(operation_id), state, receipt)
    if state == "SUCCEEDED" and compensation_key is not None:
        ledger.mark_compensated(compensation_key)
    _write_once_json(destination, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--adapter-registry", type=Path, required=True)
    parser.add_argument("--trust-store", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, action="append", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        trust = TrustStore.load(args.trust_store)
        profiles = ExternalProfileRegistry.load()
        registry = TrustedAdapterRegistry.load(args.adapter_registry, trust, profiles)
        request = json.loads(_read_regular(args.request, 8 * 1024 * 1024, "operation request").decode("utf-8"))
        args.output_dir.mkdir(parents=True, exist_ok=True)
        result = execute_operation(
            request,
            registry=registry,
            trust_store=trust,
            evidence_roots=args.evidence_root,
            ledger=OperationLedger(args.ledger),
            output_dir=args.output_dir,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["state"] == "SUCCEEDED" else 2
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"state": "FAILED", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
