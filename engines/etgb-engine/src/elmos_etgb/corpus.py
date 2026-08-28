"""Corpus lock validation and explicitly authorized, digest-checked fetches."""

from __future__ import annotations

import re
import subprocess
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml

from .attestation import AttestationError, load_json_object, verify_signed_record
from .security import SecurityBoundaryError, resolve_within
from .canonical import digest_json


def load_lock(root: Path) -> dict[str, Any]:
    path = root / "corpora" / "corpus-lock.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("repositories"), list):
        raise ValueError("corpus lock must contain repositories")
    return value


def build_license_review_request(root: Path) -> dict[str, Any]:
    """Build a deterministic, unsigned request for independent corpus review.

    This is an intake artifact, not an approval. It deliberately contains no
    reviewer identity, signature, or ``approved`` state so a local process
    cannot manufacture the evidence required by the release gate.
    """

    lock = load_lock(root)
    repositories = []
    for repository in sorted(lock["repositories"], key=lambda item: str(item.get("id", ""))):
        repositories.append({
            "corpus_id": str(repository["id"]),
            "repository": str(repository["repository"]),
            "commit": str(repository["commit"]),
            "business_lines": sorted(str(value) for value in repository.get("business_lines", [])),
            "purpose": str(repository.get("purpose", "")),
            "redistribution": str(repository.get("redistribution", "")),
            "requested_review": [
                "license_spdx",
                "patent_and_trademark_scope",
                "data_and_export_control_scope",
                "redistribution_decision",
                "review_status",
            ],
            "required_record_binding": {"record_type": "license-review", "repository": str(repository["repository"]), "commit": str(repository["commit"])},
            "status": "PENDING_EXTERNAL_REVIEW",
        })
    request = {
        "schema_version": "1.0",
        "request_type": "corpus-license-review-request",
        "status": "PENDING_EXTERNAL_REVIEW",
        "lock_digest": digest_json(lock),
        "repository_count": len(repositories),
        "repositories": repositories,
        "release_effect": "release remains BLOCKED until every request has an approved, non-expired, independently signed review record",
    }
    request["request_digest"] = digest_json(request)
    return request


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"governance record at {path}:{line_number} must be an object")
            records.append(value)
    return records


def verify_license_reviews(root: Path, *, release: bool = False, trust_store: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Verify signed, commit-bound corpus license review records.

    The lock remains the source of corpus identity. A review record can satisfy
    the lock's ``required`` state only when a separate trusted reviewer signs a
    non-expired record for the exact repository and commit.
    """

    errors: list[str] = []
    warnings: list[str] = []
    lock = load_lock(root)
    review_path = root / "corpora" / "license-reviews.jsonl"
    required_ids = {str(repo.get("id")) for repo in lock["repositories"]}
    if not review_path.is_file():
        messages = [f"license review evidence missing: {identifier}" for identifier in sorted(required_ids)]
        (errors if release else warnings).extend(messages)
        return {"valid": not errors, "records": 0, "approved": 0, "unapproved": len(required_ids), "errors": errors, "warnings": warnings}
    try:
        records = _load_jsonl(review_path)
    except (OSError, ValueError) as exc:
        return {"valid": False, "records": 0, "approved": 0, "unapproved": len(required_ids), "errors": [str(exc)], "warnings": []}
    if trust_store is None:
        trust_path = root / "corpora" / "trust-store.json"
        if trust_path.is_file():
            try:
                trust_store = load_json_object(trust_path)
            except AttestationError as exc:
                trust_store = {}
                errors.append(str(exc))
        else:
            trust_store = {}
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        payload = record.get("payload") if isinstance(record, dict) else None
        identifier = str(payload.get("corpus_id")) if isinstance(payload, dict) else ""
        if identifier in by_id:
            errors.append(f"duplicate license review record: {identifier}")
            continue
        by_id[identifier] = record
        verification = verify_signed_record(record, trust_store, record_type="license-review")
        if not verification["valid"]:
            errors.extend(f"license review {identifier}: {error}" for error in verification["errors"])
            continue
        if not isinstance(payload, dict):
            errors.append(f"license review {identifier}: payload must be an object")
            continue
        if payload.get("review_status") != "approved":
            errors.append(f"license review {identifier}: review_status is not approved")
    approved = 0
    for repo in lock["repositories"]:
        identifier = str(repo.get("id"))
        record = by_id.get(identifier)
        payload = record.get("payload") if isinstance(record, dict) else None
        if not isinstance(payload, dict):
            errors.append(f"license review evidence missing: {identifier}")
            continue
        if payload.get("repository") != repo.get("repository") or payload.get("commit") != repo.get("commit"):
            errors.append(f"license review is not bound to locked repository/commit: {identifier}")
            continue
        if payload.get("review_status") == "approved":
            approved += 1
    unresolved = len(required_ids) - approved
    if unresolved:
        message = f"{unresolved} corpus license review(s) are not approved and verified"
        (errors if release else warnings).append(message)
    return {"valid": not errors, "records": len(records), "approved": approved, "unapproved": unresolved, "errors": errors, "warnings": warnings}


def verify_lock(root: Path, *, release: bool = False, trust_store: Mapping[str, Any] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        lock = load_lock(root)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return {"valid": False, "repositories": 0, "approved": 0, "unapproved": 0, "errors": [str(exc)], "warnings": []}
    seen: set[str] = set()
    for repo in lock["repositories"]:
        identifier = str(repo.get("id", ""))
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", identifier) or identifier in seen:
            errors.append(f"invalid or duplicate corpus id: {identifier}")
        seen.add(identifier)
        if not re.fullmatch(r"[0-9a-f]{40}", str(repo.get("commit", ""))):
            errors.append(f"corpus commit is not an immutable SHA-1: {identifier}")
        repository = str(repo.get("repository", ""))
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            errors.append(f"corpus repository is not an allowlisted GitHub path: {identifier}")
        policy = repo.get("policy", {})
        if policy.get("network") != "allowlisted" or policy.get("secrets") != "none":
            errors.append(f"unsafe corpus policy: {identifier}")
    license_reviews = verify_license_reviews(root, release=release, trust_store=trust_store)
    errors.extend(license_reviews["errors"])
    warnings.extend(license_reviews["warnings"])
    approved = license_reviews["approved"]
    return {"valid": not errors, "repositories": len(lock["repositories"]), "approved": approved, "unapproved": license_reviews["unapproved"], "errors": errors, "warnings": warnings, "license_reviews": license_reviews}


def fetch_approved(root: Path, *, allow_network: bool = False) -> list[dict[str, Any]]:
    """Fetch only approved GitHub repositories at their locked commit.

    The caller must still provide an OS/container sandbox for build execution;
    this function only performs Git metadata operations and never runs project
    build scripts.
    """

    if not allow_network:
        raise SecurityBoundaryError("network fetch requires explicit --allow-network")
    lock = load_lock(root)
    destination_root = root / "corpora" / "worktrees"
    destination_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    outcomes: list[dict[str, Any]] = []
    for repo in lock["repositories"]:
        if repo.get("license_review") != "approved":
            outcomes.append({"id": repo["id"], "status": "blocked", "reason": "license_review is not approved"})
            continue
        identifier = repo["id"]
        destination = resolve_within(destination_root, identifier, must_exist=False)
        remote = f"https://github.com/{repo['repository']}.git"
        if not destination.exists():
            subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", remote, str(destination)], check=True, cwd=root)
        subprocess.run(["git", "fetch", "--depth", "1", "origin", repo["commit"]], check=True, cwd=destination)
        subprocess.run(["git", "checkout", "--detach", repo["commit"]], check=True, cwd=destination)
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=destination, text=True).strip()
        if actual != repo["commit"]:
            raise RuntimeError(f"commit mismatch for {identifier}: {actual}")
        outcomes.append({"id": identifier, "status": "fetched", "commit": actual})
    return outcomes
