#!/usr/bin/env python3
"""Conservative aggregate launch gate for the Project Synthesis P0 line.

The gate derives repository state from Git and derives gate decisions from
content-addressed, Ed25519-signed evidence. It never accepts a caller supplied
``PASS``/``production_ready``/``certified`` field as authority and never
issues certification. Production
trust keys come only from the repository-owned launch contract; there is no
command-line trust-root override.

The current contract intentionally has no production trust root.  Consequently
production evaluation fails closed until independently governed public keys
are committed to the policy.  ``--test-mode`` validates only the local contract
and repository identity and can emit at most ``LOCAL_CONTRACT_VALID``.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, cast


SOURCE_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = SOURCE_ROOT / "docs" / "project-synthesis" / "p0-launch-gate-contract.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_OBJECT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
EXPECTED_GATE_IDS = (
    "release_bundle",
    "production_runner",
    "managed_postgresql",
    "rs256_idp",
    "cloud_run",
    "supply_chain_signature",
    "independent_uat",
    "independent_security",
    "release_approval",
    "production_certification",
)
NON_SUCCESS_STATES = {"NOT_RUN", "UNKNOWN", "INCONCLUSIVE", "FAILED", "BLOCKED"}


class LaunchGateFailure(RuntimeError):
    """Stable fail-closed validation failure."""


def canonical_json(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def add_blocker(blockers: list[str], value: str) -> None:
    if value not in blockers:
        blockers.append(value)


def _parse_time(value: object, reason: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise LaunchGateFailure(reason)
    normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise LaunchGateFailure(reason) from error
    if parsed.tzinfo is None:
        raise LaunchGateFailure(reason)
    return parsed.astimezone(UTC)


def _safe_regular_file(path: Path, *, maximum_bytes: int, reason: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise LaunchGateFailure(reason)
    resolved = path.resolve(strict=True)
    if resolved != path.absolute() or resolved.stat().st_size > maximum_bytes:
        raise LaunchGateFailure(reason)
    return resolved


def _load_json_file(path: Path, *, maximum_bytes: int, reason: str) -> dict[str, Any]:
    safe = _safe_regular_file(path, maximum_bytes=maximum_bytes, reason=reason)
    try:
        value = json.loads(safe.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LaunchGateFailure(reason) from error
    if not isinstance(value, dict):
        raise LaunchGateFailure(reason)
    return value


def _relative_path(value: object, *, reason: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise LaunchGateFailure(reason)
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts or "." in path.parts:
        raise LaunchGateFailure(reason)
    return path


def _git(repository: Path, *arguments: str) -> str:
    git = shutil.which("git")
    if git is None:
        raise LaunchGateFailure("GIT_NOT_AVAILABLE")
    completed = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), *arguments],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise LaunchGateFailure(f"GIT_OBSERVATION_FAILED:{arguments[0]}")
    return completed.stdout.strip()


def load_contract() -> dict[str, Any]:
    """Load and validate the repository-owned, non-overridable trust policy."""

    contract = _load_json_file(
        CONTRACT_PATH,
        maximum_bytes=2 * 1024 * 1024,
        reason="LAUNCH_CONTRACT_INVALID",
    )
    if (
        contract.get("schema_version") != "1.0.0"
        or contract.get("kind") != "elmos.project-synthesis.p0-launch-gate-contract"
        or contract.get("contract_id") != "project-synthesis-p0-production-launch-v1"
    ):
        raise LaunchGateFailure("LAUNCH_CONTRACT_IDENTITY_INVALID")
    raw_repository = contract.get("repository")
    raw_scope = contract.get("scope")
    raw_policy = contract.get("evidence_policy")
    raw_gates = contract.get("gates")
    if not all(isinstance(item, dict) for item in (raw_repository, raw_scope, raw_policy)) or not isinstance(
        raw_gates, list
    ):
        raise LaunchGateFailure("LAUNCH_CONTRACT_SHAPE_INVALID")
    repository = cast(dict[str, Any], raw_repository)
    scope = cast(dict[str, Any], raw_scope)
    policy = cast(dict[str, Any], raw_policy)
    gates = raw_gates
    if (
        scope.get("path") != "docs/project-synthesis/p0-launch-scope-v1.json"
        or scope.get("id") != "project-synthesis-api-v1"
        or not isinstance(scope.get("canonical_sha256"), str)
        or SHA256.fullmatch(scope["canonical_sha256"]) is None
        or scope.get("required_status") != "FROZEN"
    ):
        raise LaunchGateFailure("LAUNCH_CONTRACT_SCOPE_INVALID")
    allowed_origins = repository.get("allowed_origin_urls")
    tracked = repository.get("required_tracked_paths")
    if (
        not isinstance(allowed_origins, list)
        or not allowed_origins
        or any(not isinstance(item, str) or not item for item in allowed_origins)
        or not isinstance(tracked, list)
        or not tracked
        or any(not isinstance(item, str) or not item for item in tracked)
        or repository.get("exact_repository_full_name") != "zpcaiai/elmos"
        or repository.get("engine_project_name") != "elmos-project-synthesis"
    ):
        raise LaunchGateFailure("LAUNCH_CONTRACT_REPOSITORY_INVALID")
    if (
        policy.get("directory_must_be_outside_source_repository") is not True
        or policy.get("signature_algorithm") != "ed25519"
        or policy.get("payload_format") != "canonical-json"
        or any(
            not isinstance(policy.get(name), int) or policy[name] <= 0
            for name in (
                "maximum_artifact_bytes",
                "maximum_signature_envelope_bytes",
                "maximum_evidence_file_bytes",
            )
        )
        or policy.get("production_trust_policy_status") not in {"CONFIGURED", "NOT_CONFIGURED"}
        or not isinstance(policy.get("production_trust_keys"), list)
    ):
        raise LaunchGateFailure("LAUNCH_CONTRACT_EVIDENCE_POLICY_INVALID")
    keys = policy["production_trust_keys"]
    if policy["production_trust_policy_status"] == "NOT_CONFIGURED" and keys:
        raise LaunchGateFailure("UNCONFIGURED_TRUST_POLICY_HAS_KEYS")
    if policy["production_trust_policy_status"] == "CONFIGURED" and not keys:
        raise LaunchGateFailure("CONFIGURED_TRUST_POLICY_HAS_NO_KEYS")
    seen_keys: set[tuple[str, str]] = set()
    fingerprint_roles: dict[str, str] = {}
    for key in keys:
        if not isinstance(key, dict) or set(key) != {
            "key_id",
            "role",
            "algorithm",
            "status",
            "public_key_path",
            "public_key_sha256",
            "valid_from",
            "valid_until",
        }:
            raise LaunchGateFailure("TRUST_KEY_SHAPE_INVALID")
        identity = (str(key.get("key_id")), str(key.get("role")))
        if (
            identity in seen_keys
            or not all(identity)
            or key.get("algorithm") != "ed25519"
            or key.get("status") != "ACTIVE"
            or not isinstance(key.get("public_key_sha256"), str)
            or SHA256.fullmatch(key["public_key_sha256"]) is None
        ):
            raise LaunchGateFailure("TRUST_KEY_INVALID")
        seen_keys.add(identity)
        fingerprint = str(key["public_key_sha256"])
        previous_role = fingerprint_roles.get(fingerprint)
        if previous_role is not None and previous_role != identity[1]:
            raise LaunchGateFailure("TRUST_KEY_REUSED_ACROSS_INDEPENDENT_ROLES")
        fingerprint_roles[fingerprint] = identity[1]
        _relative_path(key.get("public_key_path"), reason="TRUST_KEY_PATH_INVALID")
        if _parse_time(key.get("valid_from"), "TRUST_KEY_TIME_INVALID") >= _parse_time(
            key.get("valid_until"), "TRUST_KEY_TIME_INVALID"
        ):
            raise LaunchGateFailure("TRUST_KEY_TIME_INVALID")
    if tuple(gate.get("id") for gate in gates if isinstance(gate, dict)) != EXPECTED_GATE_IDS:
        raise LaunchGateFailure("LAUNCH_GATE_SET_INVALID")
    for gate in gates:
        if set(gate) != {
            "id",
            "artifact",
            "signature",
            "kind",
            "signer_role",
            "evidence_class",
            "required_evidence_roles",
            "required_claims",
        }:
            raise LaunchGateFailure(f"GATE_CONTRACT_SHAPE_INVALID:{gate.get('id')}")
        if (
            not all(isinstance(gate.get(name), str) and gate[name] for name in ("id", "kind", "signer_role", "evidence_class"))
            or not isinstance(gate.get("required_claims"), dict)
            or not gate["required_claims"]
            or not isinstance(gate.get("required_evidence_roles"), list)
            or not gate["required_evidence_roles"]
            or len(set(gate["required_evidence_roles"])) != len(gate["required_evidence_roles"])
        ):
            raise LaunchGateFailure(f"GATE_CONTRACT_INVALID:{gate.get('id')}")
        _relative_path(gate.get("artifact"), reason=f"GATE_ARTIFACT_PATH_INVALID:{gate['id']}")
        _relative_path(gate.get("signature"), reason=f"GATE_SIGNATURE_PATH_INVALID:{gate['id']}")
    return contract


def observe_repository(repository: Path, contract: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    try:
        if repository.is_symlink() or not repository.is_dir():
            raise LaunchGateFailure("SOURCE_REPOSITORY_UNSAFE")
        root = repository.resolve(strict=True)
        if Path(_git(root, "rev-parse", "--show-toplevel")).resolve(strict=True) != root:
            raise LaunchGateFailure("SOURCE_REPOSITORY_ROOT_MISMATCH")
        commit_sha = _git(root, "rev-parse", "HEAD")
        tree_sha = _git(root, "rev-parse", "HEAD^{tree}")
        if GIT_OBJECT.fullmatch(commit_sha) is None or GIT_OBJECT.fullmatch(tree_sha) is None:
            raise LaunchGateFailure("SOURCE_GIT_OBJECT_INVALID")
        status = _git(root, "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none")
        clean = not status
        if not clean:
            add_blocker(blockers, "SOURCE_WORKTREE_NOT_CLEAN")
        origin = _git(root, "config", "--get", "remote.origin.url")
        allowed = contract["repository"]["allowed_origin_urls"]
        if origin not in allowed:
            add_blocker(blockers, "SOURCE_REPOSITORY_ORIGIN_NOT_ALLOWED")
        for raw_path in contract["repository"]["required_tracked_paths"]:
            relative = _relative_path(raw_path, reason="SOURCE_MARKER_PATH_INVALID")
            try:
                _git(root, "ls-files", "--error-unmatch", relative.as_posix())
                _git(root, "cat-file", "-e", f"HEAD:{relative.as_posix()}")
            except LaunchGateFailure:
                add_blocker(blockers, f"SOURCE_MARKER_NOT_TRACKED:{relative.as_posix()}")
                continue
            path = root.joinpath(*relative.parts)
            if path.is_symlink() or not path.is_file():
                add_blocker(blockers, f"SOURCE_MARKER_UNSAFE:{relative.as_posix()}")
        engine_path = root / "engines" / "project-synthesis-engine" / "pyproject.toml"
        try:
            engine = tomllib.loads(engine_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            add_blocker(blockers, "SOURCE_ENGINE_PACKAGE_INVALID")
        else:
            if (engine.get("project") or {}).get("name") != contract["repository"]["engine_project_name"]:
                add_blocker(blockers, "SOURCE_ENGINE_PACKAGE_IDENTITY_MISMATCH")
        repository_contract_path = root / "docs" / "project-synthesis" / "p0-launch-gate-contract.json"
        try:
            repository_contract = _load_json_file(
                repository_contract_path,
                maximum_bytes=2 * 1024 * 1024,
                reason="SOURCE_LAUNCH_CONTRACT_INVALID",
            )
        except LaunchGateFailure as error:
            add_blocker(blockers, str(error))
        else:
            if repository_contract != contract:
                add_blocker(blockers, "SOURCE_LAUNCH_CONTRACT_BINDING_MISMATCH")
        scope_path = root / contract["scope"]["path"]
        try:
            scope = _load_json_file(scope_path, maximum_bytes=2 * 1024 * 1024, reason="SOURCE_SCOPE_INVALID")
        except LaunchGateFailure as error:
            add_blocker(blockers, str(error))
            scope_sha = None
        else:
            scope_sha = sha256_bytes(canonical_json(scope))
            if scope.get("scope_id") != contract["scope"]["id"]:
                add_blocker(blockers, "SOURCE_SCOPE_ID_MISMATCH")
            if scope.get("status") != contract["scope"]["required_status"]:
                add_blocker(blockers, "SOURCE_SCOPE_NOT_FROZEN")
            if scope_sha != contract["scope"]["canonical_sha256"]:
                add_blocker(blockers, "SOURCE_SCOPE_DIGEST_MISMATCH")
        return (
            {
                "status": "PASSED" if not blockers else "BLOCKED",
                "root": str(root),
                "origin": origin,
                "commit_sha": commit_sha,
                "tree_sha": tree_sha,
                "worktree_clean": clean,
                "scope_id": contract["scope"]["id"],
                "scope_sha256": scope_sha,
            },
            blockers,
        )
    except (OSError, LaunchGateFailure) as error:
        add_blocker(blockers, str(error))
        return (
            {
                "status": "BLOCKED",
                "root": str(repository.absolute()),
                "origin": None,
                "commit_sha": None,
                "tree_sha": None,
                "worktree_clean": False,
                "scope_id": contract["scope"]["id"],
                "scope_sha256": None,
            },
            blockers,
        )


def _resolve_inside(root: Path, raw_path: object, *, reason: str) -> Path:
    relative = _relative_path(raw_path, reason=reason)
    candidate = root.joinpath(*relative.parts)
    if candidate.is_symlink():
        raise LaunchGateFailure(reason)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise LaunchGateFailure(reason) from error
    return resolved


def _validate_evidence_refs(
    artifact: Mapping[str, Any],
    *,
    gate: Mapping[str, Any],
    evidence_root: Path,
    maximum_bytes: int,
    repository: Mapping[str, Any],
    scope: Mapping[str, Any],
    now: datetime,
) -> list[dict[str, Any]]:
    references = artifact.get("evidence_refs")
    if not isinstance(references, list) or not references:
        raise LaunchGateFailure("EVIDENCE_REFS_MISSING")
    observed_roles: set[str] = set()
    observed_paths: set[Path] = set()
    normalized: list[dict[str, Any]] = []
    for reference in references:
        if not isinstance(reference, dict) or set(reference) != {"role", "path", "sha256", "byte_count"}:
            raise LaunchGateFailure("EVIDENCE_REF_SHAPE_INVALID")
        role = reference.get("role")
        if not isinstance(role, str) or role in observed_roles:
            raise LaunchGateFailure("EVIDENCE_REF_ROLE_INVALID")
        observed_roles.add(role)
        path = _resolve_inside(evidence_root, reference.get("path"), reason="EVIDENCE_REF_PATH_INVALID")
        if path in observed_paths:
            raise LaunchGateFailure("EVIDENCE_REF_FILE_REUSED")
        observed_paths.add(path)
        _safe_regular_file(path, maximum_bytes=maximum_bytes, reason=f"EVIDENCE_FILE_MISSING_OR_UNSAFE:{role}")
        if reference.get("byte_count") != path.stat().st_size:
            raise LaunchGateFailure(f"EVIDENCE_BYTE_COUNT_MISMATCH:{role}")
        digest = reference.get("sha256")
        if not isinstance(digest, str) or SHA256.fullmatch(digest) is None or digest != sha256_file(path):
            raise LaunchGateFailure(f"EVIDENCE_SHA256_MISMATCH:{role}")
        document = _load_json_file(
            path,
            maximum_bytes=maximum_bytes,
            reason=f"EVIDENCE_DOCUMENT_INVALID:{role}",
        )
        if set(document) != {
            "schema_version", "kind", "role", "status", "scope",
            "source_revision", "producer", "observed_at", "details",
        }:
            raise LaunchGateFailure(f"EVIDENCE_DOCUMENT_SHAPE_INVALID:{role}")
        if (
            document.get("schema_version") != "1.0.0"
            or document.get("kind") != "elmos.project-synthesis.evidence-reference"
            or document.get("role") != role
            or document.get("status") != "PASSED"
            or document.get("scope") != {"id": scope["id"], "sha256": scope["canonical_sha256"]}
            or document.get("source_revision") != {
                "commit_sha": repository["commit_sha"],
                "tree_sha": repository["tree_sha"],
            }
            or not isinstance(document.get("producer"), dict)
            or set(document["producer"]) != {"id"}
            or not isinstance(document["producer"].get("id"), str)
            or not document["producer"]["id"]
            or not isinstance(document.get("details"), dict)
            or not document["details"]
            or _parse_time(document.get("observed_at"), f"EVIDENCE_DOCUMENT_TIME_INVALID:{role}") > now
        ):
            raise LaunchGateFailure(f"EVIDENCE_DOCUMENT_BINDING_INVALID:{role}")
        if role == "scm_attestation" and document["details"] != {
            "repository_full_name": "zpcaiai/elmos",
            "commit_sha": repository["commit_sha"],
            "tree_sha": repository["tree_sha"],
            "branch_protection_status": "PASSED",
            "required_checks_status": "PASSED",
            "deployment_sha_status": "PASSED",
        }:
            raise LaunchGateFailure("SCM_ATTESTATION_BINDING_INVALID")
        normalized.append({"role": role, "path": path.relative_to(evidence_root).as_posix(), "sha256": digest})
    required = set(gate["required_evidence_roles"])
    if observed_roles != required:
        raise LaunchGateFailure("EVIDENCE_ROLES_NOT_EXACT")
    return sorted(normalized, key=lambda item: item["role"])


def _trusted_key(
    *,
    policy: Mapping[str, Any],
    gate: Mapping[str, Any],
    envelope: Mapping[str, Any],
    now: datetime,
) -> Mapping[str, Any]:
    if policy.get("production_trust_policy_status") != "CONFIGURED":
        raise LaunchGateFailure("PRODUCTION_TRUST_POLICY_NOT_CONFIGURED")
    matches = [
        key
        for key in policy["production_trust_keys"]
        if isinstance(key, dict)
        and key.get("key_id") == envelope.get("key_id")
        and key.get("role") == gate["signer_role"]
    ]
    if len(matches) != 1:
        raise LaunchGateFailure("EVIDENCE_SIGNING_KEY_NOT_TRUSTED_FOR_GATE")
    key = matches[0]
    signed_at = _parse_time(envelope.get("signed_at"), "EVIDENCE_SIGNATURE_TIME_INVALID")
    valid_from = _parse_time(key.get("valid_from"), "TRUST_KEY_TIME_INVALID")
    valid_until = _parse_time(key.get("valid_until"), "TRUST_KEY_TIME_INVALID")
    if signed_at > now or not valid_from <= signed_at <= valid_until or now > valid_until:
        raise LaunchGateFailure("EVIDENCE_SIGNING_KEY_OUTSIDE_VALIDITY")
    return key


def _verify_signature(
    artifact: Mapping[str, Any],
    *,
    envelope: Mapping[str, Any],
    gate: Mapping[str, Any],
    policy: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    if set(envelope) != {
        "schema_version",
        "kind",
        "gate_id",
        "algorithm",
        "key_id",
        "signer_role",
        "payload_format",
        "payload_sha256",
        "signature_base64",
        "signed_at",
    }:
        raise LaunchGateFailure("EVIDENCE_SIGNATURE_ENVELOPE_SHAPE_INVALID")
    if (
        envelope.get("schema_version") != "1.0.0"
        or envelope.get("kind") != "elmos.project-synthesis.p0-gate-signature"
        or envelope.get("gate_id") != gate["id"]
        or envelope.get("algorithm") != policy["signature_algorithm"]
        or envelope.get("signer_role") != gate["signer_role"]
        or envelope.get("payload_format") != policy["payload_format"]
    ):
        raise LaunchGateFailure("EVIDENCE_SIGNATURE_ENVELOPE_INVALID")
    payload = canonical_json(artifact)
    payload_sha256 = sha256_bytes(payload)
    if envelope.get("payload_sha256") != payload_sha256:
        raise LaunchGateFailure("EVIDENCE_SIGNATURE_PAYLOAD_MISMATCH")
    key = _trusted_key(policy=policy, gate=gate, envelope=envelope, now=now)
    signed_at = _parse_time(envelope.get("signed_at"), "EVIDENCE_SIGNATURE_TIME_INVALID")
    observed_at = _parse_time(artifact.get("observed_at"), "ARTIFACT_TIME_INVALID")
    expires_at = _parse_time(artifact.get("expires_at"), "ARTIFACT_TIME_INVALID")
    if not observed_at <= signed_at <= expires_at:
        raise LaunchGateFailure("EVIDENCE_SIGNATURE_OUTSIDE_ARTIFACT_WINDOW")
    relative = _relative_path(key["public_key_path"], reason="TRUST_KEY_PATH_INVALID")
    public_key = CONTRACT_PATH.parent.joinpath(*relative.parts)
    _safe_regular_file(public_key, maximum_bytes=1024 * 1024, reason="TRUST_PUBLIC_KEY_UNSAFE")
    if key["public_key_sha256"] != sha256_file(public_key):
        raise LaunchGateFailure("TRUST_PUBLIC_KEY_DIGEST_MISMATCH")
    try:
        signature = base64.b64decode(envelope.get("signature_base64", ""), validate=True)
    except (binascii.Error, ValueError) as error:
        raise LaunchGateFailure("EVIDENCE_SIGNATURE_ENCODING_INVALID") from error
    if len(signature) != 64:
        raise LaunchGateFailure("EVIDENCE_SIGNATURE_LENGTH_INVALID")
    openssl = shutil.which("openssl")
    if openssl is None:
        raise LaunchGateFailure("OPENSSL_REQUIRED_FOR_ED25519_VERIFICATION")
    with tempfile.TemporaryDirectory(prefix="elmos-p0-launch-signature-") as temporary:
        payload_path = Path(temporary) / "payload.json"
        signature_path = Path(temporary) / "payload.sig"
        payload_path.write_bytes(payload)
        signature_path.write_bytes(signature)
        completed = subprocess.run(  # noqa: S603
            [
                openssl,
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(public_key),
                "-rawin",
                "-in",
                str(payload_path),
                "-sigfile",
                str(signature_path),
            ],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    if completed.returncode != 0:
        raise LaunchGateFailure("EVIDENCE_SIGNATURE_INVALID")
    return {
        "status": "PASSED",
        "algorithm": "ed25519",
        "key_id": key["key_id"],
        "signer_role": key["role"],
        "payload_sha256": payload_sha256,
    }


def evaluate_gate(
    gate: Mapping[str, Any],
    *,
    evidence_root: Path,
    policy: Mapping[str, Any],
    repository: Mapping[str, Any],
    scope: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    blockers: list[str] = []
    artifact_path = _resolve_inside(evidence_root, gate["artifact"], reason="ARTIFACT_PATH_INVALID")
    signature_path = _resolve_inside(evidence_root, gate["signature"], reason="SIGNATURE_PATH_INVALID")
    artifact_binding: dict[str, Any] | None = None
    signature_binding: dict[str, Any] | None = None
    if not artifact_path.exists():
        add_blocker(blockers, "ARTIFACT_NOT_RUN")
        return {
            "status": "NOT_RUN",
            "artifact": None,
            "signature": None,
            "blockers": blockers,
        }
    try:
        artifact = _load_json_file(
            artifact_path,
            maximum_bytes=policy["maximum_artifact_bytes"],
            reason="ARTIFACT_INVALID_OR_UNSAFE",
        )
        artifact_binding = {
            "path": artifact_path.relative_to(evidence_root).as_posix(),
            "sha256": sha256_file(artifact_path),
            "byte_count": artifact_path.stat().st_size,
        }
        if set(artifact) != {
            "schema_version",
            "kind",
            "gate_id",
            "scope",
            "source_revision",
            "status",
            "evidence_class",
            "producer",
            "independent_verifier",
            "observed_at",
            "expires_at",
            "claims",
            "evidence_refs",
            "production_ready",
            "certified",
        }:
            raise LaunchGateFailure("ARTIFACT_SHAPE_INVALID")
        if (
            artifact.get("schema_version") != "1.0.0"
            or artifact.get("kind") != gate["kind"]
            or artifact.get("gate_id") != gate["id"]
            or artifact.get("evidence_class") != gate["evidence_class"]
        ):
            raise LaunchGateFailure("ARTIFACT_IDENTITY_INVALID")
        if artifact.get("status") != "PASSED":
            observed = artifact.get("status")
            suffix = observed if isinstance(observed, str) and observed in NON_SUCCESS_STATES else "INVALID"
            raise LaunchGateFailure(f"ARTIFACT_STATUS_{suffix}")
        if artifact.get("production_ready") is not False or artifact.get("certified") is not False:
            raise LaunchGateFailure("ARTIFACT_SELF_PROMOTION_REJECTED")
        if artifact.get("scope") != {"id": scope["id"], "sha256": scope["canonical_sha256"]}:
            raise LaunchGateFailure("ARTIFACT_SCOPE_BINDING_MISMATCH")
        if artifact.get("source_revision") != {
            "commit_sha": repository["commit_sha"],
            "tree_sha": repository["tree_sha"],
        }:
            raise LaunchGateFailure("ARTIFACT_SOURCE_REVISION_MISMATCH")
        producer = artifact.get("producer")
        verifier = artifact.get("independent_verifier")
        if (
            not isinstance(producer, dict)
            or set(producer) != {"id"}
            or not isinstance(producer.get("id"), str)
            or not producer["id"]
            or not isinstance(verifier, dict)
            or set(verifier) != {"id", "role"}
            or not isinstance(verifier.get("id"), str)
            or not verifier["id"]
            or verifier.get("role") != gate["signer_role"]
            or verifier["id"] == producer["id"]
        ):
            raise LaunchGateFailure("ARTIFACT_VERIFIER_INDEPENDENCE_INVALID")
        observed_at = _parse_time(artifact.get("observed_at"), "ARTIFACT_TIME_INVALID")
        expires_at = _parse_time(artifact.get("expires_at"), "ARTIFACT_TIME_INVALID")
        if observed_at > now or expires_at <= observed_at or now > expires_at:
            raise LaunchGateFailure("ARTIFACT_EXPIRED_OR_FROM_FUTURE")
        if artifact.get("claims") != gate["required_claims"]:
            raise LaunchGateFailure("ARTIFACT_REQUIRED_CLAIMS_NOT_EXACT")
        refs = _validate_evidence_refs(
            artifact,
            gate=gate,
            evidence_root=evidence_root,
            maximum_bytes=policy["maximum_evidence_file_bytes"],
            repository=repository,
            scope=scope,
            now=now,
        )
        if not signature_path.exists():
            raise LaunchGateFailure("SIGNATURE_NOT_RUN")
        envelope = _load_json_file(
            signature_path,
            maximum_bytes=policy["maximum_signature_envelope_bytes"],
            reason="SIGNATURE_INVALID_OR_UNSAFE",
        )
        signature_binding = _verify_signature(
            artifact,
            envelope=envelope,
            gate=gate,
            policy=policy,
            now=now,
        )
        artifact_binding["evidence_refs"] = refs
    except (OSError, LaunchGateFailure) as error:
        add_blocker(blockers, str(error))
    return {
        "status": "PASSED" if not blockers else "BLOCKED",
        "artifact": artifact_binding,
        "signature": signature_binding,
        "blockers": blockers,
    }


def evaluate_launch_gate(
    repository_path: Path,
    evidence_directory: Path,
    *,
    test_mode: bool = False,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate all ten mandatory gates and return a derived decision."""

    contract = load_contract()
    now = (evaluated_at or datetime.now(UTC)).astimezone(UTC)
    repository, repository_blockers = observe_repository(repository_path, contract)
    evidence_blockers: list[str] = []
    try:
        if evidence_directory.is_symlink():
            raise LaunchGateFailure("EVIDENCE_DIRECTORY_UNSAFE")
        evidence_root = evidence_directory.resolve(strict=True)
        if not evidence_root.is_dir():
            raise LaunchGateFailure("EVIDENCE_DIRECTORY_UNSAFE")
        source_root = Path(repository["root"]).resolve(strict=False)
        if evidence_root == source_root or evidence_root.is_relative_to(source_root):
            raise LaunchGateFailure("EVIDENCE_DIRECTORY_INSIDE_SOURCE_REPOSITORY")
    except (OSError, LaunchGateFailure) as error:
        evidence_root = evidence_directory.absolute()
        add_blocker(evidence_blockers, str(error))

    gates: dict[str, dict[str, Any]] = {}
    if repository_blockers or evidence_blockers:
        for gate in contract["gates"]:
            gates[gate["id"]] = {
                "status": "BLOCKED",
                "artifact": None,
                "signature": None,
                "blockers": ["REPOSITORY_OR_EVIDENCE_ROOT_INVALID"],
            }
    else:
        for gate in contract["gates"]:
            gates[gate["id"]] = evaluate_gate(
                gate,
                evidence_root=evidence_root,
                policy=contract["evidence_policy"],
                repository=repository,
                scope=contract["scope"],
                now=now,
            )

    final_repository, final_repository_blockers = observe_repository(repository_path, contract)
    if (
        final_repository_blockers
        or final_repository.get("commit_sha") != repository.get("commit_sha")
        or final_repository.get("tree_sha") != repository.get("tree_sha")
        or final_repository.get("worktree_clean") is not True
    ):
        add_blocker(repository_blockers, "SOURCE_REVISION_CHANGED_DURING_GATE_EVALUATION")

    blockers = [f"repository:{item}" for item in repository_blockers]
    blockers.extend(f"evidence:{item}" for item in evidence_blockers)
    if contract["evidence_policy"]["production_trust_policy_status"] != "CONFIGURED":
        add_blocker(blockers, "trust:PRODUCTION_TRUST_POLICY_NOT_CONFIGURED")
    for gate_id, result in gates.items():
        for blocker in result["blockers"]:
            add_blocker(blockers, f"{gate_id}:{blocker}")

    all_production_gates_passed = (
        not blockers
        and all(result["status"] == "PASSED" for result in gates.values())
        and repository["status"] == "PASSED"
    )
    production_ready = all_production_gates_passed and not test_mode
    local_contract_valid = not repository_blockers and not evidence_blockers
    if test_mode and local_contract_valid:
        decision = "LOCAL_CONTRACT_VALID"
    elif production_ready:
        decision = "PRODUCTION_READY"
    else:
        decision = "BLOCKED"
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.project-synthesis.p0-launch-gate-result",
        "contract": {
            "id": contract["contract_id"],
            "path": CONTRACT_PATH.relative_to(SOURCE_ROOT).as_posix(),
            "sha256": sha256_file(CONTRACT_PATH),
            "scope_id": contract["scope"]["id"],
            "scope_sha256": contract["scope"]["canonical_sha256"],
            "production_trust_policy_status": contract["evidence_policy"][
                "production_trust_policy_status"
            ],
        },
        "mode": "TEST_CONTRACT_ONLY" if test_mode else "PRODUCTION",
        "evaluated_at": now.isoformat(),
        "repository": repository,
        "gates": gates,
        "decision": decision,
        "launch_decision": "PRODUCTION_READY" if production_ready else "BLOCKED",
        "blockers": sorted(blockers),
        "maximum_test_decision": "LOCAL_CONTRACT_VALID",
        "external_certification_status": (
            "VERIFIED"
            if gates["production_certification"]["status"] == "PASSED" and not test_mode
            else "NOT_RUN"
        ),
        "production_ready": production_ready,
        "certified": False,
    }


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--evidence-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--test-mode", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = evaluate_launch_gate(
            args.repository,
            args.evidence_directory,
            test_mode=args.test_mode,
        )
    except (OSError, ValueError, LaunchGateFailure) as error:
        result = {
            "schema_version": "1.0.0",
            "kind": "elmos.project-synthesis.p0-launch-gate-result",
            "mode": "TEST_CONTRACT_ONLY" if args.test_mode else "PRODUCTION",
            "decision": "BLOCKED",
            "launch_decision": "BLOCKED",
            "blockers": [str(error)],
            "production_ready": False,
            "certified": False,
        }
    rendered = (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output = args.output.expanduser().resolve(strict=False)
    try:
        repository = args.repository.expanduser().resolve(strict=False)
        if output == repository or output.is_relative_to(repository):
            raise LaunchGateFailure("OUTPUT_MUST_BE_OUTSIDE_SOURCE_REPOSITORY")
        _write_atomic(output, rendered)
    except (OSError, LaunchGateFailure) as error:
        print(json.dumps({"decision": "BLOCKED", "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(rendered.decode("utf-8"), end="")
    if result.get("decision") == "LOCAL_CONTRACT_VALID" and args.test_mode:
        return 0
    return 0 if result.get("production_ready") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
