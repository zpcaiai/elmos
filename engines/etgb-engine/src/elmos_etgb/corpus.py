"""Corpus lock validation and explicitly authorized, digest-checked fetches."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from .security import SecurityBoundaryError, resolve_within


def load_lock(root: Path) -> dict[str, Any]:
    path = root / "corpora" / "corpus-lock.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("repositories"), list):
        raise ValueError("corpus lock must contain repositories")
    return value


def verify_lock(root: Path, *, release: bool = False) -> dict[str, Any]:
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
        if repo.get("license_review") != "approved":
            message = f"license review required: {identifier}"
            (errors if release else warnings).append(message)
    approved = sum(1 for repo in lock["repositories"] if repo.get("license_review") == "approved")
    return {"valid": not errors, "repositories": len(lock["repositories"]), "approved": approved, "unapproved": len(lock["repositories"]) - approved, "errors": errors, "warnings": warnings}


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
