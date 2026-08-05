#!/usr/bin/env python3
"""Fail-closed dispatcher for the 38 real-domain execution result contracts.

The external/native toolchain performs the domain operation.  This dispatcher
does not accept a command from repository content: it verifies the exact
Batch/Claim/executor binding, independent corpus declaration, raw evidence
bytes, tool versions and assertion outcomes, then emits the only subject shape
accepted by the registered Claim Oracle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain_handlers import DomainHandlerError, execute_handler
from oracle_registry import OracleRegistry


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIRECTORY if (SCRIPT_DIRECTORY / "manifest.json").is_file() else SCRIPT_DIRECTORY.parent
REGISTRY_PATH = PACKAGE_ROOT / "domain-executor-registry.json"
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_RAW_EVIDENCE_BYTES = 512 * 1024 * 1024
ALLOWED_CORPORA = {"development", "negative", "holdout", "representative", "production"}


class DomainExecutionError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def read_regular(path: Path, maximum: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode) or observed.st_size > maximum:
            raise DomainExecutionError(f"{label} must be a bounded regular file")
        chunks: list[bytes] = []
        remaining = observed.st_size
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                raise DomainExecutionError(f"{label} changed while being read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise DomainExecutionError(f"{label} changed while being read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def confined(path: Path, roots: tuple[Path, ...]) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise DomainExecutionError("raw evidence path escapes approved roots")
    return resolved


@dataclass(frozen=True)
class ExecutorRegistry:
    by_batch: dict[int, dict[str, Any]]

    @classmethod
    def load(cls, path: Path = REGISTRY_PATH) -> "ExecutorRegistry":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "1.0" or payload.get("namespace") != "repository-migration-platform-b01-38":
            raise DomainExecutionError("domain-executor registry identity is invalid")
        entries = payload.get("entries")
        if not isinstance(entries, list) or len(entries) != 38 or payload.get("executor_count") != 38:
            raise DomainExecutionError("domain-executor registry must contain exactly 38 entries")
        by_batch: dict[int, dict[str, Any]] = {}
        handlers: set[str] = set()
        for entry in entries:
            batch = entry.get("batch") if isinstance(entry, dict) else None
            if not isinstance(batch, int) or not 1 <= batch <= 38 or batch in by_batch:
                raise DomainExecutionError("domain-executor Batch identity is invalid")
            if entry.get("executor_id") != f"b{batch:02d}-domain-executor-v1":
                raise DomainExecutionError("domain-executor identity is invalid")
            handler = entry.get("handler")
            if not isinstance(handler, str) or not handler or handler in handlers:
                raise DomainExecutionError("domain-executor handler identity is invalid or duplicated")
            if entry.get("repository_commands_allowed") is not False or entry.get("requires_actual_toolchain") is not True:
                raise DomainExecutionError("domain-executor policy was weakened")
            handlers.add(handler)
            by_batch[batch] = entry
        if sorted(by_batch) != list(range(1, 39)):
            raise DomainExecutionError("domain-executor Batch coverage is incomplete")
        return cls(by_batch)


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise DomainExecutionError(f"{label} must be sha256:<64 lowercase hex>")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise DomainExecutionError(f"{label} must be sha256:<64 lowercase hex>") from exc
    if value != value.lower():
        raise DomainExecutionError(f"{label} must be lowercase")
    return value


def validate_raw_reference(reference: Any, roots: tuple[Path, ...], label: str) -> dict[str, Any]:
    if not isinstance(reference, dict) or set(reference) != {"path", "sha256", "bytes", "role"}:
        raise DomainExecutionError(f"{label} raw evidence reference is invalid")
    if not isinstance(reference.get("role"), str) or not reference["role"]:
        raise DomainExecutionError(f"{label}.role is required")
    path_value = reference.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise DomainExecutionError(f"{label}.path is required")
    path = confined(Path(path_value), roots)
    data = read_regular(path, MAX_RAW_EVIDENCE_BYTES, label)
    expected_digest = require_digest(reference.get("sha256"), f"{label}.sha256")
    if reference.get("bytes") != len(data) or expected_digest != digest_bytes(data):
        raise DomainExecutionError(f"{label} raw evidence byte/digest mismatch")
    return {"role": reference["role"], "sha256": expected_digest, "bytes": len(data)}


def execute(result_file: Path, roots: tuple[Path, ...]) -> dict[str, Any]:
    payload = json.loads(read_regular(result_file.resolve(strict=True), MAX_RESULT_BYTES, "domain result").decode("utf-8"))
    required = {
        "schema_version", "batch", "executor_id", "claim", "corpus", "source_fingerprint",
        "environment", "domain_contract", "toolchain", "assertions", "raw_evidence", "decision", "limitations",
    }
    if not isinstance(payload, dict) or set(payload) != required or payload.get("schema_version") != "1.0":
        raise DomainExecutionError("domain result fields are invalid")
    batch = payload.get("batch")
    if not isinstance(batch, int):
        raise DomainExecutionError("domain result Batch is invalid")
    executor = ExecutorRegistry.load().by_batch.get(batch)
    if executor is None or payload.get("executor_id") != executor["executor_id"]:
        raise DomainExecutionError("domain result is not bound to the registered executor")
    claim = payload.get("claim")
    if not isinstance(claim, dict) or set(claim) != {"type", "index", "sha256"}:
        raise DomainExecutionError("domain result Claim identity is invalid")
    try:
        obligation = OracleRegistry.load().resolve(batch, claim["type"], claim["index"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainExecutionError(f"domain result Claim is unknown: {exc}") from exc
    if claim.get("sha256") != obligation.claim_sha256 or obligation.executor_id != executor["executor_id"]:
        raise DomainExecutionError("domain result Claim/executor binding is stale")
    corpus = payload.get("corpus")
    if not isinstance(corpus, dict) or set(corpus) != {"role", "id", "sha256", "independent"}:
        raise DomainExecutionError("domain result corpus declaration is invalid")
    corpus_role = corpus.get("role")
    if corpus_role not in ALLOWED_CORPORA or corpus_role not in obligation.required_corpora:
        raise DomainExecutionError("domain result corpus is not eligible for this Claim")
    if not isinstance(corpus.get("id"), str) or not corpus["id"] or require_digest(corpus.get("sha256"), "corpus.sha256") is None:
        raise DomainExecutionError("domain result corpus identity is invalid")
    if corpus_role in {"holdout", "representative", "production"} and corpus.get("independent") is not True:
        raise DomainExecutionError(f"{corpus_role} corpus must be independently owned")
    require_digest(payload.get("source_fingerprint"), "source_fingerprint")
    environment = payload.get("environment")
    if not isinstance(environment, dict) or set(environment) != {"id", "kind", "digest"}:
        raise DomainExecutionError("domain result environment is invalid")
    if not isinstance(environment.get("id"), str) or not environment["id"] or environment.get("kind") not in {"local", "clean", "holdout", "representative", "sandbox", "production"}:
        raise DomainExecutionError("domain result environment identity is invalid")
    require_digest(environment.get("digest"), "environment.digest")
    if corpus_role == "production" and environment.get("kind") not in {"sandbox", "production"}:
        raise DomainExecutionError("production corpus requires sandbox or production environment evidence")
    toolchain = payload.get("toolchain")
    if not isinstance(toolchain, list) or not toolchain:
        raise DomainExecutionError("domain result requires at least one real toolchain execution")
    tool_checks = []
    for index, tool in enumerate(toolchain):
        if not isinstance(tool, dict) or set(tool) != {"name", "version", "argv_sha256", "exit_code", "evidence_role"}:
            raise DomainExecutionError(f"toolchain[{index}] is invalid")
        if not isinstance(tool.get("name"), str) or not tool["name"] or not isinstance(tool.get("version"), str) or not tool["version"]:
            raise DomainExecutionError(f"toolchain[{index}] identity/version is required")
        if Path(tool["name"]).name.lower() in {"true", "false", "echo", "printf", "noop"}:
            raise DomainExecutionError(f"toolchain[{index}] is a generic/no-op command, not a domain executor")
        if not isinstance(tool.get("exit_code"), int) or isinstance(tool.get("exit_code"), bool):
            raise DomainExecutionError(f"toolchain[{index}].exit_code must be an integer")
        require_digest(tool.get("argv_sha256"), f"toolchain[{index}].argv_sha256")
        if not isinstance(tool.get("evidence_role"), str) or not tool["evidence_role"]:
            raise DomainExecutionError(f"toolchain[{index}].evidence_role is required")
        tool_checks.append({
            "name": f"toolchain:{tool['name']}@{tool['version']}",
            "outcome": "PASS" if tool.get("exit_code") == 0 else "FAIL",
            "detail": f"exit_code={tool.get('exit_code')}; argv={tool['argv_sha256']}",
        })
    assertions = payload.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        raise DomainExecutionError("domain result requires Claim-specific assertions")
    assertion_checks = []
    for index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict) or set(assertion) != {"name", "outcome", "detail"}:
            raise DomainExecutionError(f"assertions[{index}] is invalid")
        if assertion.get("outcome") not in {"PASS", "FAIL", "INCONCLUSIVE", "BLOCKED", "NOT_RUN"}:
            raise DomainExecutionError(f"assertions[{index}].outcome is invalid")
        if not isinstance(assertion.get("name"), str) or not assertion["name"] or not isinstance(assertion.get("detail"), str) or not assertion["detail"]:
            raise DomainExecutionError(f"assertions[{index}] requires name and detail")
        assertion_checks.append(assertion)
    raw = payload.get("raw_evidence")
    if not isinstance(raw, list) or not raw:
        raise DomainExecutionError("domain result requires raw evidence bytes")
    verified_raw = [validate_raw_reference(item, roots, f"raw_evidence[{index}]") for index, item in enumerate(raw)]
    required_roles = {tool["evidence_role"] for tool in toolchain}
    observed_roles = {item["role"] for item in verified_raw}
    if not required_roles.issubset(observed_roles):
        raise DomainExecutionError(f"raw evidence lacks toolchain roles: {sorted(required_roles - observed_roles)}")
    decision = payload.get("decision")
    if decision not in {"PASS", "FAIL", "INCONCLUSIVE", "BLOCKED", "NOT_RUN"}:
        raise DomainExecutionError("domain result decision is invalid")
    all_checks = tool_checks + assertion_checks + [{
        "name": f"raw-evidence:{item['role']}", "outcome": "PASS",
        "detail": f"{item['sha256']} bytes={item['bytes']}",
    } for item in verified_raw]
    try:
        domain_checks = execute_handler(
            batch, executor["handler"], payload.get("domain_contract"), obligation.oracle_id,
            toolchain, assertions, observed_roles, decision,
        )
    except DomainHandlerError as exc:
        raise DomainExecutionError(str(exc)) from exc
    all_checks.extend(domain_checks)
    if decision == "PASS" and any(check["outcome"] != "PASS" for check in all_checks):
        raise DomainExecutionError("domain result PASS contains failed, unknown or not-run checks")
    limitations = payload.get("limitations")
    if not isinstance(limitations, list) or any(not isinstance(item, str) for item in limitations):
        raise DomainExecutionError("domain result limitations must be strings")
    return {
        "schema_version": "1.0",
        "oracle_id": obligation.oracle_id,
        "executor_id": obligation.executor_id,
        "batch": batch,
        "claim": claim,
        "corpus": corpus,
        "decision": decision,
        "checks": all_checks,
        "limitations": limitations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--evidence-root", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    roots = tuple(path.expanduser().resolve(strict=True) for path in args.evidence_root)
    result = execute(args.result, roots)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            raise SystemExit("refusing to overwrite output")
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
