#!/usr/bin/env python3
"""Portable Ethan-side exact-SHA runner.

Copy this reviewed file and request.json to an independent environment.  This
runner never accepts or reads a private key and never signs its own output.
Ethan signs response.unsigned.json only after reviewing the captured evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROTOCOL = "elmos-ethan-external-certification-v1"
MAX_INPUT = 512 * 1024 * 1024
SAFE_MAKE_TARGET = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")


class RunnerError(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def read_regular(
    path: Path, label: str, maximum: int = MAX_INPUT, *, allow_empty: bool = False
) -> bytes:
    absolute = Path(os.path.abspath(path))
    before = absolute.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RunnerError(f"{label} must be a regular non-symlink file")
    if before.st_size < 0 or before.st_size > maximum or (not allow_empty and before.st_size == 0):
        raise RunnerError(f"{label} size is invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RunnerError(f"{label} identity changed before open")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    verified = absolute.lstat()
    identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
    if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise RunnerError(f"{label} changed during read")
    if (before.st_dev, before.st_ino) != (verified.st_dev, verified.st_ino):
        raise RunnerError(f"{label} path identity changed after read")
    payload = b"".join(chunks)
    if len(payload) != opened.st_size or len(payload) > maximum:
        raise RunnerError(f"{label} size changed or exceeded the bound")
    return payload


def run_git(checkout: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=checkout, text=True, capture_output=True)
    if check and result.returncode != 0:
        raise RunnerError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def public_key_fingerprint(path: Path) -> str:
    raw = read_regular(path, "public key", 128 * 1024)
    if b"PRIVATE KEY" in raw:
        raise RunnerError("public key input contains private-key material")
    text = subprocess.run(
        ["openssl", "pkey", "-pubin", "-in", str(path), "-text", "-noout"],
        capture_output=True,
    )
    if text.returncode != 0 or b"ED25519" not in (text.stdout + text.stderr).upper():
        raise RunnerError("public key must be a valid Ed25519 public key")
    der = subprocess.run(
        ["openssl", "pkey", "-pubin", "-in", str(path), "-outform", "DER"],
        capture_output=True,
    )
    if der.returncode != 0:
        raise RunnerError("public key canonicalization failed")
    return digest(der.stdout)


def content_reference(path: Path, root: Path) -> dict[str, Any]:
    payload = read_regular(path, str(path), allow_empty=True)
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": digest(payload),
        "size_bytes": len(payload),
    }


def external_output(path: Path, checkout: Path) -> Path:
    output = path.expanduser().resolve(strict=False)
    try:
        output.relative_to(checkout)
    except ValueError:
        pass
    else:
        raise RunnerError("output must be outside the tested checkout")
    if output.exists():
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise RunnerError("output must be a new or empty non-symlink directory")
    else:
        output.mkdir(parents=True, mode=0o700)
    return output


def validate_checkout(checkout: Path, request: dict[str, Any]) -> dict[str, Any]:
    checkout = checkout.resolve(strict=True)
    subject = request["subject"]
    actual_sha = run_git(checkout, "rev-parse", "HEAD").stdout.strip()
    actual_tree = run_git(checkout, "rev-parse", "HEAD^{tree}").stdout.strip()
    if actual_sha != subject["target_sha"] or actual_tree != subject["tree_oid"]:
        raise RunnerError("checkout does not match the exact requested commit and tree")
    attached = run_git(checkout, "symbolic-ref", "-q", "HEAD", check=False)
    if attached.returncode == 0:
        raise RunnerError("checkout must use detached HEAD")
    if run_git(checkout, "status", "--porcelain=v1", "--untracked-files=all").stdout:
        raise RunnerError("checkout must be clean before execution")
    return {"sha": actual_sha, "tree": actual_tree, "checkout": checkout}


def copy_external_evidence(
    *, source: Path, destination: Path, root: Path
) -> dict[str, Any]:
    payload = read_regular(source, "external evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return content_reference(destination, root)


def run_exchange(args: argparse.Namespace) -> dict[str, Any]:
    request_raw = read_regular(args.request, "request", 8 * 1024 * 1024)
    request = json.loads(request_raw.decode("utf-8"))
    if request.get("schema_version") != 1 or request.get("protocol") != PROTOCOL:
        raise RunnerError("request protocol is unsupported")
    request_digest = digest(canonical_bytes(request))
    if request_digest != args.expected_request_digest:
        raise RunnerError("request does not match the independently delivered request digest")
    tooling = request.get("tooling")
    if not isinstance(tooling, dict):
        raise RunnerError("request tooling binding is missing")
    runner_digest = digest(read_regular(Path(__file__), "external runner", 2 * 1024 * 1024))
    if runner_digest != tooling.get("external_runner_sha256"):
        raise RunnerError("external runner bytes do not match the exact-SHA request")
    if not args.confirm_independent or not args.confirm_private_key_external:
        raise RunnerError("explicit independence and external-private-key confirmations are required")
    checkout_info = validate_checkout(args.checkout, request)
    checkout = checkout_info["checkout"]
    output = external_output(args.output, checkout)
    evidence_index = json.loads(read_regular(args.evidence_index, "evidence index").decode("utf-8"))
    fingerprint = public_key_fingerprint(args.public_key)
    execution_started = now()
    line_results: list[dict[str, Any]] = []
    unknowns: list[str] = []
    sanitized_env = {
        "HOME": os.environ.get("HOME", str(output / "home")),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for line in request["plan"]["business_lines"]:
        line_id = line["id"]
        commands: list[dict[str, Any]] = []
        line_pass = True
        for command in line["commands"]:
            argv = command["argv"]
            if (
                len(argv) != 2
                or argv[0] != "make"
                or SAFE_MAKE_TARGET.fullmatch(argv[1]) is None
            ):
                raise RunnerError(f"unsafe command plan rejected: {command['id']}")
            command_dir = output / "commands" / command["id"]
            command_dir.mkdir(parents=True)
            stdout_path = command_dir / "stdout.log"
            stderr_path = command_dir / "stderr.log"
            started = now()
            with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
                completed = subprocess.run(
                    argv,
                    cwd=checkout,
                    env=sanitized_env,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    check=False,
                )
            ended = now()
            if completed.returncode != 0:
                line_pass = False
            commands.append(
                {
                    "id": command["id"],
                    "argv": argv,
                    "exit_code": completed.returncode,
                    "started_at": started,
                    "completed_at": ended,
                    "stdout": content_reference(stdout_path, output),
                    "stderr": content_reference(stderr_path, output),
                }
            )
        external_evidence: list[dict[str, Any]] = []
        line_index = evidence_index.get(line_id, {}) if isinstance(evidence_index, dict) else {}
        for evidence_class in line["external_evidence_classes"]:
            source_value = line_index.get(evidence_class) if isinstance(line_index, dict) else None
            if not isinstance(source_value, str):
                line_pass = False
                unknowns.append(f"{line_id}:{evidence_class}:NOT_RUN")
                continue
            safe_name = re.sub(r"[^a-z0-9-]", "-", evidence_class.lower())
            destination = output / "external-evidence" / line_id / f"{safe_name}.evidence"
            external_evidence.append(
                {
                    "class": evidence_class,
                    "synthetic": False,
                    "independent": True,
                    "content": copy_external_evidence(
                        source=Path(source_value), destination=destination, root=output
                    ),
                }
            )
        line_results.append(
            {
                "id": line_id,
                "status": "PASS" if line_pass else "BLOCKED",
                "commands": commands,
                "external_evidence": external_evidence,
            }
        )
    clean_after = not bool(
        run_git(checkout, "status", "--porcelain=v1", "--untracked-files=all").stdout
    )
    if not clean_after:
        unknowns.append("POST_RUN_WORKTREE_DIRTY")
    overall = "PASS" if clean_after and not unknowns and all(
        line["status"] == "PASS" for line in line_results
    ) else "BLOCKED"
    response = {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "request_id": request["request_id"],
        "request_digest": request_digest,
        "target_sha": request["subject"]["target_sha"],
        "tree_oid": request["subject"]["tree_oid"],
        "challenge_nonce": request["challenge_nonce"],
        "certifier": {
            "actor_id": request["certifier"]["actor_id"],
            "organization_id": request["certifier"]["organization_id"],
            "role": request["certifier"]["role"],
            "public_key_fingerprint": fingerprint,
        },
        "independent_execution": {
            "environment_id": args.environment_id,
            "provider": args.provider,
            "region": args.region,
            "executor_actor_id": args.executor_actor_id,
            "executor_organization_id": args.executor_organization_id,
            "repository_owner_controlled": False,
            "private_key_repository_accessible": False,
            "detached_head_verified": True,
            "clean_worktree_before_verified": True,
            "clean_worktree_after_verified": clean_after,
            "started_at": execution_started,
            "completed_at": now(),
        },
        "business_line_results": line_results,
        "unknowns": sorted(unknowns),
        "overall_decision": overall,
    }
    response_path = output / "response.unsigned.json"
    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return {
        "status": overall,
        "response": str(response_path),
        "response_sha256": digest(response_path.read_bytes()),
        "next_action": "Ethan reviews response.unsigned.json and signs its exact bytes outside this runner",
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--request", type=Path, required=True)
    result.add_argument("--expected-request-digest", required=True)
    result.add_argument("--checkout", type=Path, required=True)
    result.add_argument("--public-key", type=Path, required=True)
    result.add_argument("--evidence-index", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--environment-id", required=True)
    result.add_argument("--provider", required=True)
    result.add_argument("--region", required=True)
    result.add_argument("--executor-actor-id", required=True)
    result.add_argument("--executor-organization-id", required=True)
    result.add_argument("--confirm-independent", action="store_true")
    result.add_argument("--confirm-private-key-external", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_exchange(parser().parse_args(argv))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RunnerError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
