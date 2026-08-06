#!/usr/bin/env python3
"""Collect exact SCM evidence for a Batch 105-108 release candidate.

This collector is intentionally read-only.  It observes an existing GitHub
Draft PR and binds it to the exact clean source commit recorded by the image
builder.  Observation by the executor is not independent verification and
therefore cannot authorize deployment or certification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class EvidenceFailure(RuntimeError):
    """A stable evidence-contract failure."""


def canonical_json(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def validate_pr(
    document: dict[str, Any], *, repository: str, expected_head_sha: str
) -> dict[str, Any]:
    """Return a minimal normalized PR observation or fail closed."""
    head = document.get("head") or {}
    base = document.get("base") or {}
    observed_repository = ((base.get("repo") or {}).get("full_name"))
    if document.get("state") != "open":
        raise EvidenceFailure("SCM PR is not open")
    if document.get("draft") is not True:
        raise EvidenceFailure("SCM PR is not a Draft PR")
    if observed_repository != repository:
        raise EvidenceFailure("SCM PR repository does not match the requested repository")
    if base.get("ref") != "main":
        raise EvidenceFailure("SCM PR base branch is not main")
    if head.get("sha") != expected_head_sha:
        raise EvidenceFailure("SCM PR head does not match the image source commit")
    if not COMMIT.fullmatch(str(head.get("sha", ""))):
        raise EvidenceFailure("SCM PR head is not an exact commit SHA")
    html_url = str(document.get("html_url", ""))
    expected_prefix = f"https://github.com/{repository}/pull/"
    if not html_url.startswith(expected_prefix):
        raise EvidenceFailure("SCM PR URL is outside the expected repository")
    return {
        "provider": "github",
        "repository": repository,
        "number": int(document["number"]),
        "url": html_url,
        "state": "open",
        "draft": True,
        "head_sha": head["sha"],
        "head_ref": head.get("ref"),
        "base_ref": "main",
        "author": (document.get("user") or {}).get("login"),
    }


def merge_production_blockers(
    image_blockers: list[Any], boundary_blockers: list[str]
) -> list[str]:
    """Carry image blockers forward while replacing its stale SCM state."""
    retained = {
        blocker
        for blocker in image_blockers
        if isinstance(blocker, str)
        and not blocker.startswith("SCM_DRAFT_PULL_REQUEST_")
    }
    return sorted(retained | set(boundary_blockers))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--image-receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not REPOSITORY.fullmatch(args.repository):
        raise SystemExit("invalid GitHub owner/repository")
    if args.pr <= 0:
        raise SystemExit("PR number must be positive")

    image_receipt = json.loads(args.image_receipt.read_text(encoding="utf-8"))
    source_commit = str(image_receipt.get("source_commit", ""))
    if not COMMIT.fullmatch(source_commit):
        raise EvidenceFailure("image receipt is missing an exact source commit")
    if image_receipt.get("source_worktree_clean") is not True:
        raise EvidenceFailure("image receipt source worktree is not clean")
    immutable_reference = image_receipt.get("immutable_reference")
    if not isinstance(immutable_reference, str) or "@sha256:" not in immutable_reference:
        raise EvidenceFailure("image receipt lacks an immutable registry reference")

    process = subprocess.run(
        ["gh", "api", f"repos/{args.repository}/pulls/{args.pr}"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise EvidenceFailure("GitHub PR evidence query failed")
    pr_document = json.loads(process.stdout)
    observation = validate_pr(
        pr_document, repository=args.repository, expected_head_sha=source_commit
    )
    observation["observed_at"] = datetime.now(timezone.utc).isoformat()
    observation["observation_sha256"] = sha256_bytes(canonical_json(observation))

    boundaries = dict(image_receipt.get("external_boundaries") or {})
    boundaries["SCM_DRAFT_PULL_REQUEST"] = "EXECUTED_AWAITING_INDEPENDENT_VERIFICATION"
    image_blockers = (
        (image_receipt.get("production_readiness") or {}).get("blockers") or []
    )
    boundary_blockers = [
        f"{operation}_{state}"
        for operation, state in sorted(boundaries.items())
        if state != "INDEPENDENTLY_VERIFIED"
    ]
    blockers = merge_production_blockers(image_blockers, boundary_blockers)
    result = {
        "schema_version": 1,
        "image_receipt": {
            "path": str(args.image_receipt.resolve()),
            "sha256": sha256_file(args.image_receipt),
            "source_commit": source_commit,
            "immutable_reference": immutable_reference,
        },
        "scm_draft_pull_request": observation,
        "external_boundaries": boundaries,
        "production_readiness": {
            "status": "NOT_READY",
            "blockers": blockers,
        },
        "production_ready": False,
        "certified": False,
        "independently_verified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output.resolve()),
        "sha256": sha256_file(args.output),
        "scm_status": boundaries["SCM_DRAFT_PULL_REQUEST"],
        "production_ready": False,
        "certified": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
