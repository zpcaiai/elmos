#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SHA256_REF = re.compile(r"^sha256:[0-9a-f]{64}$")


def emit(scope: str, status: str, reason: str, **extra: Any) -> None:
    print(json.dumps({"scope": scope, "status": status, "reason": reason, **extra}, indent=2))


def nonempty_identity(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    identity = value.get("identity")
    return identity if isinstance(identity, str) and identity.strip() else None


def validate_evidence_files(result: dict[str, Any], evidence_root: Path) -> tuple[list[str], set[str]]:
    errors: list[str] = []
    verified_refs: set[str] = set()
    roles: set[str] = set()
    records = result.get("evidence_files")
    if not isinstance(records, list) or len(records) < 2:
        return ["evidence_files must contain at least two byte-bound records"], verified_refs
    root = evidence_root.resolve()
    paths: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"evidence file {index} must be an object")
            continue
        relative = record.get("path")
        digest = record.get("sha256")
        size = record.get("size_bytes")
        role = record.get("role")
        if not isinstance(relative, str) or not relative or relative in paths:
            errors.append(f"evidence file {index} path is invalid or duplicated")
            continue
        paths.add(relative)
        if not isinstance(role, str) or not role:
            errors.append(f"evidence file {index} role is missing")
        else:
            roles.add(role)
        if not isinstance(digest, str) or SHA256_REF.fullmatch(digest) is None:
            errors.append(f"evidence file {index} digest is invalid")
            continue
        try:
            relative_path = Path(relative)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise ValueError
            candidate = root / relative_path
            current = root
            for part in relative_path.parts:
                current = current / part
                if current.is_symlink():
                    raise ValueError
            path = candidate.resolve(strict=True)
            path.relative_to(root)
        except (OSError, ValueError):
            errors.append(f"evidence file {index} is missing or escapes evidence root")
            continue
        if not path.is_file():
            errors.append(f"evidence file {index} is not a regular file")
            continue
        try:
            before = path.stat()
            hasher = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    hasher.update(chunk)
            after = path.stat()
        except OSError:
            errors.append(f"evidence file {index} cannot be read")
            continue
        stable = (before.st_ino, before.st_size, before.st_mtime_ns) == (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        actual = "sha256:" + hasher.hexdigest()
        if not stable:
            errors.append(f"evidence file {index} changed during verification")
        if not isinstance(size, int) or isinstance(size, bool) or size < 1 or size != after.st_size:
            errors.append(f"evidence file {index} byte count does not match")
        if actual != digest:
            errors.append(f"evidence file {index} digest does not match")
        if stable and actual == digest and size == after.st_size:
            verified_refs.add(digest)
    required_roles = {
        "authorization",
        "runner-attestation",
        "runtime-environment",
        "test-result",
        "certification-request",
    }
    missing_roles = sorted(required_roles - roles)
    if missing_roles:
        errors.append(f"required evidence roles are missing: {missing_roles}")
    return errors, verified_refs


def validate_candidate(scope: str, result: Any, evidence_root: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["result must be an object"]
    if result.get("scope") != scope:
        errors.append("scope mismatch")
    if result.get("status") != "candidate":
        errors.append("status must be candidate")
    file_errors, verified_refs = validate_evidence_files(result, evidence_root)
    errors.extend(file_errors)
    refs = result.get("evidence_refs")
    refs_are_valid = (
        isinstance(refs, list)
        and len(refs) >= 2
        and all(isinstance(ref, str) and SHA256_REF.fullmatch(ref) is not None for ref in refs)
    )
    if not refs_are_valid or len(refs) != len(set(refs)):
        errors.append("evidence_refs must contain at least two unique SHA-256 references")
        refs_set: set[str] = set()
    else:
        refs_set = set(refs)
        if refs_set != verified_refs:
            errors.append("evidence_refs must exactly match byte-verified evidence_files")

    executor = nonempty_identity(result.get("executor"))
    verifier = nonempty_identity(result.get("independent_verifier"))
    if executor is None:
        errors.append("executor identity is missing")
    if verifier is None:
        errors.append("independent verifier identity is missing")
    if executor is not None and verifier == executor:
        errors.append("executor and independent verifier must differ")
    verifier_object = result.get("independent_verifier")
    if isinstance(verifier_object, dict) and verifier_object.get("decision") != "approved":
        errors.append("independent verifier decision is not approved")

    authorization = result.get("authorization")
    if not isinstance(authorization, dict):
        errors.append("authorization is missing")
    else:
        if authorization.get("status") != "approved":
            errors.append("authorization is not approved")
        if authorization.get("scope") != scope:
            errors.append("authorization scope mismatch")
        if not isinstance(authorization.get("approval_ref"), str) or SHA256_REF.fullmatch(authorization["approval_ref"]) is None:
            errors.append("authorization approval_ref is invalid")
        elif authorization["approval_ref"] not in refs_set:
            errors.append("authorization approval_ref is not byte-bound evidence")

    runtime = result.get("runtime")
    if not isinstance(runtime, dict):
        errors.append("runtime evidence is missing")
    else:
        if runtime.get("status") != "passed":
            errors.append("runtime status is not passed")
        for key in ("environment_digest", "runner_attestation_ref"):
            value = runtime.get(key)
            if not isinstance(value, str) or SHA256_REF.fullmatch(value) is None:
                errors.append(f"runtime {key} is invalid")
            elif value not in refs_set:
                errors.append(f"runtime {key} is not byte-bound evidence")

    tests = result.get("tests")
    if not isinstance(tests, list) or not tests:
        errors.append("tests are missing")
    else:
        if not any(test.get("priority") == "P0" for test in tests if isinstance(test, dict)):
            errors.append("at least one P0 test is required")
        identifiers: set[str] = set()
        for index, test in enumerate(tests):
            if not isinstance(test, dict):
                errors.append(f"test {index} must be an object")
                continue
            identifier = test.get("id")
            if not isinstance(identifier, str) or not identifier:
                errors.append(f"test {index} identity is invalid or duplicated")
            elif identifier in identifiers:
                errors.append(f"test {index} identity is invalid or duplicated")
            else:
                identifiers.add(identifier)
            if test.get("required") is not True or test.get("status") != "passed":
                errors.append(f"required test did not pass: {identifier or index}")
            test_refs = test.get("evidence_refs")
            if not isinstance(test_refs, list) or not test_refs or any(
                not isinstance(ref, str) or SHA256_REF.fullmatch(ref) is None for ref in test_refs
            ):
                errors.append(f"test evidence is invalid: {identifier or index}")
            elif not set(test_refs).issubset(refs_set):
                errors.append(f"test evidence is not byte-bound: {identifier or index}")

    request = result.get("certification_request")
    if not isinstance(request, dict):
        errors.append("certification request is missing")
    else:
        digest = request.get("digest")
        if not isinstance(digest, str) or SHA256_REF.fullmatch(digest) is None:
            errors.append("certification request digest is invalid")
        elif digest not in refs_set:
            errors.append("certification request digest is not byte-bound evidence")
        if request.get("status") != "prepared":
            errors.append("certification request must be prepared")
        if request.get("scope") != scope:
            errors.append("certification request scope mismatch")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", default=".")
    parser.add_argument("--scope", required=True)
    parser.add_argument("--result")
    parser.add_argument("--evidence-root")
    args = parser.parse_args()
    try:
        manifest = json.loads((Path(args.package) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        emit(args.scope, "blocked", "package manifest is unavailable", error=str(exc))
        return 2
    matches = [
        skill for skill in manifest.get("skills", [])
        if skill.get("id") == args.scope or skill.get("name") == args.scope
    ]
    if len(matches) != 1:
        emit(args.scope, "blocked", "unknown or ambiguous scope")
        return 2
    canonical_scope = matches[0]["id"]
    if not args.result:
        emit(canonical_scope, "not_run", "no runtime evidence result supplied")
        return 3
    try:
        result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        emit(canonical_scope, "blocked", "result document is invalid", error=str(exc))
        return 4
    evidence_root = Path(args.evidence_root) if args.evidence_root else Path(args.result).parent
    errors = validate_candidate(canonical_scope, result, evidence_root)
    if errors:
        emit(canonical_scope, "blocked", "candidate evidence is incomplete or invalid", errors=errors)
        return 5
    emit(
        canonical_scope,
        "ready_for_external_gate",
        "candidate is structurally complete; external trust-store signature verification is still required",
        evidence_refs=result["evidence_refs"],
        independent_verifier=result["independent_verifier"]["identity"],
        certified=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
