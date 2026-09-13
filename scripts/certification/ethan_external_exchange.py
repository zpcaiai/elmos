#!/usr/bin/env python3
"""Prepare and verify an external, exact-SHA Ethan certification exchange.

This module never generates, imports, or uses a private key for signing.  It
prepares immutable requests and verifies externally signed response bundles.
Successful verification is deliberately capped at READY_FOR_DOMAIN_GATES.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = "elmos-ethan-external-certification-v1"
PLAN_PATH = "certification/ethan-certifier/external-certification-plan.json"
RUNNER_PATH = "certification/ethan-certifier/external_runner.py"
PROTOCOL_PATH = "certification/ethan-certifier/EXTERNAL_CERTIFICATION_PROTOCOL.md"
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_EVIDENCE_BYTES = 512 * 1024 * 1024
SHA = re.compile(r"^[0-9a-f]{40}$")
OID = re.compile(r"^[0-9a-f]{40,64}$")
FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$")


class ExchangeError(ValueError):
    """Raised when an exchange control fails closed."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def digest_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or IDENTITY.fullmatch(value) is None:
        raise ExchangeError(f"{label} must be an exact identity")
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExchangeError(f"{label} must be an object")
    return value


def _exact_fields(value: dict[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(fields - set(value))
    extra = sorted(set(value) - fields)
    if missing or extra:
        raise ExchangeError(f"{label} fields invalid; missing={missing}, extra={extra}")


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ExchangeError(f"{label} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExchangeError(f"{label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ExchangeError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def read_regular_file(
    path: Path, label: str, max_bytes: int, *, allow_empty: bool = False
) -> bytes:
    """Read a bounded regular file once without following symlinks."""

    candidate = Path(os.path.abspath(path))
    try:
        before = candidate.lstat()
    except OSError as exc:
        raise ExchangeError(f"{label} is unavailable: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ExchangeError(f"{label} must be a regular non-symlink file")
    if before.st_size < 0 or before.st_size > max_bytes or (not allow_empty and before.st_size == 0):
        lower = 0 if allow_empty else 1
        raise ExchangeError(f"{label} size is outside {lower}..{max_bytes}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise ExchangeError(f"{label} identity changed before open")
            chunks: list[bytes] = []
            remaining = max_bytes + 1
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise ExchangeError(f"{label} could not be read safely: {exc}") from exc
    verified = candidate.lstat()
    identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
    if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ExchangeError(f"{label} changed during read")
    if (before.st_dev, before.st_ino) != (verified.st_dev, verified.st_ino):
        raise ExchangeError(f"{label} path identity changed after read")
    if len(payload) != opened.st_size or len(payload) > max_bytes:
        raise ExchangeError(f"{label} size changed or exceeded the bound")
    return payload


def load_json(path: Path, label: str, max_bytes: int = MAX_JSON_BYTES) -> tuple[dict[str, Any], bytes]:
    raw = read_regular_file(path, label, max_bytes)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExchangeError(f"{label} must be UTF-8 JSON: {exc}") from exc
    return _object(value, label), raw


def _git(*args: str, root: Path = ROOT) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise ExchangeError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def resolve_exact_commit(target_sha: str, remote_ref: str) -> tuple[str, str]:
    if SHA.fullmatch(target_sha) is None:
        raise ExchangeError("target_sha must be a full lowercase 40-hex commit SHA")
    resolved = _git("rev-parse", f"{target_sha}^{{commit}}")
    if not hmac.compare_digest(resolved, target_sha):
        raise ExchangeError("target_sha did not resolve to itself")
    remote_tip = _git("rev-parse", f"{remote_ref}^{{commit}}")
    contains = subprocess.run(
        ["git", "merge-base", "--is-ancestor", target_sha, remote_tip], cwd=ROOT, check=False
    )
    if contains.returncode != 0:
        raise ExchangeError(f"target_sha is not reachable from {remote_ref}")
    tree_oid = _git("rev-parse", f"{target_sha}^{{tree}}")
    if OID.fullmatch(tree_oid) is None:
        raise ExchangeError("resolved tree object is invalid")
    return target_sha, tree_oid


def plan_at_commit(target_sha: str) -> tuple[dict[str, Any], str]:
    raw = subprocess.run(
        ["git", "show", f"{target_sha}:{PLAN_PATH}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if raw.returncode != 0:
        raise ExchangeError(f"the exact SHA does not contain {PLAN_PATH}")
    try:
        plan = json.loads(raw.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExchangeError("the exact-SHA certification plan is invalid JSON") from exc
    plan = _object(plan, "plan")
    validate_plan(plan)
    return plan, digest_bytes(canonical_bytes(plan))


def blob_at_commit(target_sha: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{target_sha}:{relative_path}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        raise ExchangeError(f"the exact SHA does not contain {relative_path}")
    return result.stdout


def validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema_version") != 1 or plan.get("protocol") != PROTOCOL:
        raise ExchangeError("plan version or protocol is unsupported")
    excluded = plan.get("excluded_business_lines")
    if excluded != ["M29"]:
        raise ExchangeError("the authoritative plan must exclude only M29")
    lines = plan.get("business_lines")
    if not isinstance(lines, list) or not lines:
        raise ExchangeError("plan.business_lines must be non-empty")
    ids: set[str] = set()
    command_ids: set[str] = set()
    for index, line_value in enumerate(lines):
        line = _object(line_value, f"plan.business_lines[{index}]")
        line_id = _identity(line.get("id"), f"plan.business_lines[{index}].id")
        if line_id == "M29" or line_id in ids:
            raise ExchangeError("plan business-line identities must be unique and exclude M29")
        ids.add(line_id)
        commands = line.get("commands")
        evidence = line.get("external_evidence_classes")
        if not isinstance(commands, list) or not commands:
            raise ExchangeError(f"{line_id} must declare commands")
        if not isinstance(evidence, list) or not evidence or len(set(evidence)) != len(evidence):
            raise ExchangeError(f"{line_id} external evidence classes are invalid")
        for command_value in commands:
            command = _object(command_value, f"{line_id}.command")
            command_id = _identity(command.get("id"), f"{line_id}.command.id")
            argv = command.get("argv")
            if command_id in command_ids:
                raise ExchangeError("command identities must be globally unique")
            if not isinstance(argv, list) or not argv or any(
                not isinstance(item, str) or not item or "\x00" in item for item in argv
            ):
                raise ExchangeError(f"{line_id}.{command_id}.argv is invalid")
            command_ids.add(command_id)


def _ensure_external_output(output_dir: Path) -> Path:
    candidate = output_dir.expanduser().resolve(strict=False)
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ExchangeError("output directory must be outside the repository")
    if candidate.exists():
        if candidate.is_symlink() or not candidate.is_dir() or any(candidate.iterdir()):
            raise ExchangeError("output directory must be a new or empty non-symlink directory")
    else:
        candidate.mkdir(parents=True, mode=0o700)
    return candidate


def prepare_request(
    *,
    target_sha: str,
    remote_ref: str,
    repository_url: str,
    requester_actor_id: str,
    requester_organization_id: str,
    output_dir: Path,
    challenge_nonce: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    target_sha, tree_oid = resolve_exact_commit(target_sha, remote_ref)
    plan, plan_digest = plan_at_commit(target_sha)
    runner_bytes = blob_at_commit(target_sha, RUNNER_PATH)
    protocol_bytes = blob_at_commit(target_sha, PROTOCOL_PATH)
    requester_actor_id = _identity(requester_actor_id, "requester_actor_id")
    requester_organization_id = _identity(requester_organization_id, "requester_organization_id")
    if not isinstance(repository_url, str) or not repository_url.startswith("https://"):
        raise ExchangeError("repository_url must be an authenticated HTTPS repository URL")
    challenge = challenge_nonce or uuid.uuid4().hex + uuid.uuid4().hex
    if re.fullmatch(r"[0-9a-f]{64,128}", challenge) is None:
        raise ExchangeError("challenge_nonce must contain 64..128 lowercase hex characters")
    issued = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    request = {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "request_id": f"ethan-{target_sha[:12]}-{challenge[:12]}",
        "issued_at": issued.isoformat().replace("+00:00", "Z"),
        "expires_at": (issued + timedelta(days=7)).isoformat().replace("+00:00", "Z"),
        "challenge_nonce": challenge,
        "requester": {
            "actor_id": requester_actor_id,
            "organization_id": requester_organization_id,
        },
        "certifier": plan["certifier"],
        "subject": {
            "repository_url": repository_url,
            "remote_ref": remote_ref,
            "target_sha": target_sha,
            "tree_oid": tree_oid,
        },
        "plan_digest": plan_digest,
        "plan": plan,
        "tooling": {
            "external_runner_path": RUNNER_PATH,
            "external_runner_sha256": digest_bytes(runner_bytes),
            "protocol_path": PROTOCOL_PATH,
            "protocol_sha256": digest_bytes(protocol_bytes),
        },
        "controls": {
            "private_key_must_remain_external": True,
            "detached_exact_sha_required": True,
            "clean_worktree_before_and_after_required": True,
            "shell_execution_prohibited": True,
            "independent_fingerprint_channel_required": True,
            "repository_auto_certification_prohibited": True,
        },
    }
    output = _ensure_external_output(output_dir)
    request_path = output / "request.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    request_digest = digest_bytes(canonical_bytes(request))
    (output / "request.digest").write_text(request_digest + "\n", encoding="utf-8")
    runner_path = output / "external_runner.py"
    runner_path.write_bytes(runner_bytes)
    runner_path.chmod(0o755)
    (output / "EXTERNAL_CERTIFICATION_PROTOCOL.md").write_bytes(protocol_bytes)
    return {
        "request": str(request_path),
        "request_digest": request_digest,
        "external_runner": str(runner_path),
        "external_runner_sha256": digest_bytes(runner_bytes),
        "target_sha": target_sha,
    }


def public_key_fingerprint(public_key: Path) -> str:
    raw = read_regular_file(public_key, "public key", 128 * 1024)
    if b"PRIVATE KEY" in raw:
        raise ExchangeError("public key input contains private-key material")
    text = subprocess.run(
        ["openssl", "pkey", "-pubin", "-in", str(public_key), "-text", "-noout"],
        capture_output=True,
        check=False,
    )
    if text.returncode != 0:
        raise ExchangeError("public key is not parseable by OpenSSL")
    if b"ED25519" not in text.stdout.upper() and b"ED25519" not in text.stderr.upper():
        raise ExchangeError("replacement certification keys must use Ed25519")
    der = subprocess.run(
        ["openssl", "pkey", "-pubin", "-in", str(public_key), "-outform", "DER"],
        capture_output=True,
        check=False,
    )
    if der.returncode != 0 or not der.stdout:
        raise ExchangeError("could not canonicalize the public key")
    return digest_bytes(der.stdout)


def _verify_content_reference(root: Path, value: Any, label: str) -> None:
    reference = _object(value, label)
    _exact_fields(reference, {"path", "sha256", "size_bytes"}, label)
    relative = reference.get("path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ExchangeError(f"{label}.path must be relative")
    parts = Path(relative).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ExchangeError(f"{label}.path contains an unsafe component")
    lexical = Path(os.path.abspath(root / relative))
    try:
        lexical.relative_to(root)
    except ValueError as exc:
        raise ExchangeError(f"{label}.path escapes the response root") from exc
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ExchangeError(f"{label}.path contains a symlink")
    payload = read_regular_file(lexical, label, MAX_EVIDENCE_BYTES, allow_empty=True)
    if reference.get("size_bytes") != len(payload):
        raise ExchangeError(f"{label}.size_bytes mismatch")
    actual = digest_bytes(payload)
    expected = reference.get("sha256")
    if not isinstance(expected, str) or not hmac.compare_digest(actual, expected):
        raise ExchangeError(f"{label}.sha256 mismatch")


def _verify_signature(public_key: Path, response_path: Path, signature_path: Path) -> None:
    read_regular_file(signature_path, "response signature", 64 * 1024)
    completed = subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public_key),
            "-rawin",
            "-in",
            str(response_path),
            "-sigfile",
            str(signature_path),
        ],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ExchangeError("external response signature verification failed")


def verify_response_bundle(
    *,
    request_path: Path,
    response_path: Path,
    signature_path: Path,
    public_key_path: Path,
    expected_fingerprint: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if FINGERPRINT.fullmatch(expected_fingerprint) is None:
        raise ExchangeError("expected fingerprint must be sha256:<64 lowercase hex>")
    fingerprint = public_key_fingerprint(public_key_path)
    if not hmac.compare_digest(fingerprint, expected_fingerprint):
        raise ExchangeError("public key does not match the independently delivered fingerprint")
    request, _ = load_json(request_path, "request")
    response, _ = load_json(response_path, "response")
    _verify_signature(public_key_path, response_path, signature_path)
    if request.get("schema_version") != 1 or request.get("protocol") != PROTOCOL:
        raise ExchangeError("request version or protocol is unsupported")
    request_plan = _object(request.get("plan"), "request.plan")
    validate_plan(request_plan)
    if request.get("plan_digest") != digest_bytes(canonical_bytes(request_plan)):
        raise ExchangeError("request.plan_digest mismatch")
    tooling = _object(request.get("tooling"), "request.tooling")
    _exact_fields(
        tooling,
        {
            "external_runner_path",
            "external_runner_sha256",
            "protocol_path",
            "protocol_sha256",
        },
        "request.tooling",
    )
    if tooling.get("external_runner_path") != RUNNER_PATH or tooling.get("protocol_path") != PROTOCOL_PATH:
        raise ExchangeError("request tooling paths are not authoritative")
    for field in ("external_runner_sha256", "protocol_sha256"):
        if not isinstance(tooling.get(field), str) or FINGERPRINT.fullmatch(tooling[field]) is None:
            raise ExchangeError(f"request.tooling.{field} is invalid")
    controls = _object(request.get("controls"), "request.controls")
    for control in (
        "private_key_must_remain_external",
        "detached_exact_sha_required",
        "clean_worktree_before_and_after_required",
        "shell_execution_prohibited",
        "independent_fingerprint_channel_required",
        "repository_auto_certification_prohibited",
    ):
        if controls.get(control) is not True:
            raise ExchangeError(f"request control {control} must be true")
    _exact_fields(
        response,
        {
            "schema_version",
            "protocol",
            "request_id",
            "request_digest",
            "target_sha",
            "tree_oid",
            "challenge_nonce",
            "certifier",
            "independent_execution",
            "business_line_results",
            "unknowns",
            "overall_decision",
        },
        "response",
    )
    if response.get("schema_version") != 1 or response.get("protocol") != PROTOCOL:
        raise ExchangeError("response version or protocol is unsupported")
    request_digest = digest_bytes(canonical_bytes(request))
    bindings = {
        "request_id": request.get("request_id"),
        "request_digest": request_digest,
        "target_sha": _object(request.get("subject"), "request.subject").get("target_sha"),
        "tree_oid": request["subject"].get("tree_oid"),
        "challenge_nonce": request.get("challenge_nonce"),
    }
    for field, expected in bindings.items():
        if response.get(field) != expected:
            raise ExchangeError(f"response.{field} does not bind the request")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    request_issued = _parse_time(request.get("issued_at"), "request.issued_at")
    request_expires = _parse_time(request.get("expires_at"), "request.expires_at")
    if request_expires <= request_issued or request_expires - request_issued > timedelta(days=7):
        raise ExchangeError("request validity interval is invalid")
    if current < request_issued - timedelta(minutes=5):
        raise ExchangeError("request is not yet valid")
    if current > request_expires:
        raise ExchangeError("request has expired")
    certifier = _object(response.get("certifier"), "response.certifier")
    _exact_fields(
        certifier,
        {"actor_id", "organization_id", "role", "public_key_fingerprint"},
        "response.certifier",
    )
    expected_certifier = _object(request.get("certifier"), "request.certifier")
    for field in ("actor_id", "organization_id", "role"):
        if certifier.get(field) != expected_certifier.get(field):
            raise ExchangeError(f"response.certifier.{field} mismatch")
    if certifier.get("public_key_fingerprint") != fingerprint:
        raise ExchangeError("response certifier fingerprint mismatch")
    requester = _object(request.get("requester"), "request.requester")
    execution = _object(response.get("independent_execution"), "response.independent_execution")
    _exact_fields(
        execution,
        {
            "environment_id",
            "provider",
            "region",
            "executor_actor_id",
            "executor_organization_id",
            "repository_owner_controlled",
            "private_key_repository_accessible",
            "detached_head_verified",
            "clean_worktree_before_verified",
            "clean_worktree_after_verified",
            "started_at",
            "completed_at",
        },
        "response.independent_execution",
    )
    for field in ("environment_id", "provider", "region", "executor_actor_id", "executor_organization_id"):
        _identity(execution.get(field), f"response.independent_execution.{field}")
    if certifier.get("actor_id") == requester.get("actor_id"):
        raise ExchangeError("certifier actor must be independent from requester")
    if certifier.get("organization_id") == requester.get("organization_id"):
        raise ExchangeError("certifier organization must be independent from requester")
    if execution.get("executor_actor_id") == requester.get("actor_id"):
        raise ExchangeError("executor actor must be independent from requester")
    for flag in (
        "detached_head_verified",
        "clean_worktree_before_verified",
        "clean_worktree_after_verified",
    ):
        if execution.get(flag) is not True:
            raise ExchangeError(f"response.independent_execution.{flag} must be true")
    for flag in ("repository_owner_controlled", "private_key_repository_accessible"):
        if execution.get(flag) is not False:
            raise ExchangeError(f"response.independent_execution.{flag} must be false")
    started = _parse_time(execution.get("started_at"), "execution.started_at")
    completed = _parse_time(execution.get("completed_at"), "execution.completed_at")
    if completed <= started:
        raise ExchangeError("independent execution interval must be positive")
    if started < request_issued or completed > request_expires:
        raise ExchangeError("independent execution is outside the request validity interval")
    if completed > current + timedelta(minutes=5):
        raise ExchangeError("independent execution completion is in the future")
    if response.get("unknowns") != [] or response.get("overall_decision") != "PASS":
        raise ExchangeError("response contains unknowns or is not an overall PASS")

    plan = request_plan
    expected_lines = {line["id"]: line for line in plan["business_lines"]}
    results_value = response.get("business_line_results")
    if not isinstance(results_value, list):
        raise ExchangeError("response.business_line_results must be a list")
    results: dict[str, dict[str, Any]] = {}
    response_parent = Path(os.path.abspath(response_path.parent))
    if response_parent.is_symlink():
        raise ExchangeError("response root must not be a symlink")
    response_root = response_parent.resolve(strict=True)
    for index, result_value in enumerate(results_value):
        result = _object(result_value, f"business_line_results[{index}]")
        _exact_fields(
            result,
            {"id", "status", "commands", "external_evidence"},
            f"business_line_results[{index}]",
        )
        line_id = _identity(result.get("id"), f"business_line_results[{index}].id")
        if line_id in results:
            raise ExchangeError("duplicate business-line result")
        results[line_id] = result
    if set(results) != set(expected_lines):
        raise ExchangeError("response business-line scope does not exactly match the request")
    for line_id, line in expected_lines.items():
        result = results[line_id]
        if result.get("status") != "PASS":
            raise ExchangeError(f"{line_id} is not PASS")
        command_values = result.get("commands")
        if not isinstance(command_values, list):
            raise ExchangeError(f"{line_id}.commands must be a list")
        commands = {item.get("id"): item for item in command_values if isinstance(item, dict)}
        expected_commands = {item["id"]: item for item in line["commands"]}
        if set(commands) != set(expected_commands):
            raise ExchangeError(f"{line_id} command scope mismatch")
        for command_id, expected_command in expected_commands.items():
            command = commands[command_id]
            _exact_fields(
                command,
                {"id", "argv", "exit_code", "started_at", "completed_at", "stdout", "stderr"},
                f"{line_id}.{command_id}",
            )
            if command.get("argv") != expected_command["argv"] or command.get("exit_code") != 0:
                raise ExchangeError(f"{line_id}.{command_id} command or exit code mismatch")
            command_started = _parse_time(command.get("started_at"), f"{line_id}.{command_id}.started_at")
            command_completed = _parse_time(command.get("completed_at"), f"{line_id}.{command_id}.completed_at")
            if command_completed <= command_started:
                raise ExchangeError(f"{line_id}.{command_id} interval must be positive")
            if command_started < started or command_completed > completed:
                raise ExchangeError(f"{line_id}.{command_id} is outside the execution interval")
            _verify_content_reference(response_root, command.get("stdout"), f"{line_id}.{command_id}.stdout")
            _verify_content_reference(response_root, command.get("stderr"), f"{line_id}.{command_id}.stderr")
        evidence_values = result.get("external_evidence")
        if not isinstance(evidence_values, list):
            raise ExchangeError(f"{line_id}.external_evidence must be a list")
        evidence = {item.get("class"): item for item in evidence_values if isinstance(item, dict)}
        if set(evidence) != set(line["external_evidence_classes"]):
            raise ExchangeError(f"{line_id} external evidence scope mismatch")
        for evidence_class, item in evidence.items():
            _exact_fields(
                item,
                {"class", "synthetic", "independent", "content"},
                f"{line_id}.external_evidence.{evidence_class}",
            )
            if item.get("synthetic") is not False or item.get("independent") is not True:
                raise ExchangeError(f"{line_id}.{evidence_class} is not independent non-synthetic evidence")
            _verify_content_reference(
                response_root, item.get("content"), f"{line_id}.external_evidence.{evidence_class}"
            )
    return {
        "status": "PASS",
        "decision": "READY_FOR_DOMAIN_GATES",
        "certification": "NOT_CERTIFIED",
        "reason": "cryptographic transport and exact-SHA evidence bindings verified; domain gates retain certification authority",
        "target_sha": response["target_sha"],
        "public_key_fingerprint": fingerprint,
        "business_lines_verified": sorted(results),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="prepare an unsigned exact-SHA request outside the repository")
    prepare.add_argument("--target-sha", required=True)
    prepare.add_argument("--remote-ref", required=True)
    prepare.add_argument("--repository-url", required=True)
    prepare.add_argument("--requester-actor-id", required=True)
    prepare.add_argument("--requester-organization-id", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--challenge-nonce")
    fingerprint = sub.add_parser("fingerprint", help="canonicalize an external Ed25519 public key")
    fingerprint.add_argument("--public-key", type=Path, required=True)
    verify = sub.add_parser("verify-response", help="verify an externally signed response bundle")
    verify.add_argument("--request", type=Path, required=True)
    verify.add_argument("--response", type=Path, required=True)
    verify.add_argument("--signature", type=Path, required=True)
    verify.add_argument("--public-key", type=Path, required=True)
    verify.add_argument("--expected-fingerprint", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_request(
                target_sha=args.target_sha,
                remote_ref=args.remote_ref,
                repository_url=args.repository_url,
                requester_actor_id=args.requester_actor_id,
                requester_organization_id=args.requester_organization_id,
                output_dir=args.output,
                challenge_nonce=args.challenge_nonce,
            )
        elif args.command == "fingerprint":
            result = {
                "status": "PASS",
                "public_key_fingerprint": public_key_fingerprint(args.public_key),
                "certification": "NOT_CERTIFIED",
            }
        else:
            result = verify_response_bundle(
                request_path=args.request,
                response_path=args.response,
                signature_path=args.signature,
                public_key_path=args.public_key,
                expected_fingerprint=args.expected_fingerprint,
            )
    except (ExchangeError, OSError) as exc:
        print(
            json.dumps(
                {"status": "BLOCKED", "decision": "NOT_CERTIFIED", "reason": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
