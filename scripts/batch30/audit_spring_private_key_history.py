#!/usr/bin/env python3
"""Fail closed while Spring certification private keys remain Git-reachable.

The audit reads object names only; it never prints or opens secret contents.  It
is safe to run before and after an administrator-coordinated history rewrite.
Current-tree removal and trust-store revocation are separate from rewriting all
shared refs and rotating every disclosed key in its external system.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable


PRIVATE_PEM = re.compile(r"(?:^|/)[^/]*private[^/]*\.pem$", re.IGNORECASE)


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout


def parse_reachable_objects(lines: Iterable[str]) -> list[dict[str, str]]:
    findings: set[tuple[str, str]] = set()
    for raw_line in lines:
        object_id, separator, path = raw_line.rstrip("\r\n").partition(" ")
        canonical_path = path.replace("\\", "/")
        if separator and PRIVATE_PEM.search(canonical_path):
            findings.add((object_id, canonical_path))
    return [
        {"object_id": object_id, "path": path}
        for object_id, path in sorted(findings, key=lambda item: (item[1], item[0]))
    ]


def parse_current_paths(lines: Iterable[str]) -> list[str]:
    return sorted(
        {
            line.rstrip("\r\n").replace("\\", "/")
            for line in lines
            if PRIVATE_PEM.search(line.rstrip("\r\n").replace("\\", "/"))
        }
    )


def audit(repo: Path) -> dict[str, object]:
    root = repo.resolve(strict=True)
    _git(root, "rev-parse", "--show-toplevel")
    reachable = parse_reachable_objects(
        _git(root, "rev-list", "--objects", "--all").splitlines()
    )
    current = parse_current_paths(
        _git(root, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
    )
    unique_paths = sorted({finding["path"] for finding in reachable})
    clean = not reachable and not current
    return {
        "schema_version": 1,
        "audit_scope": "ALL_LOCALLY_REACHABLE_GIT_REFS",
        "decision": "PASS" if clean else "HISTORY_REWRITE_REQUIRED",
        "certification_eligible": False,
        "current_tree_private_key_paths": current,
        "current_tree_private_key_count": len(current),
        "reachable_private_key_object_count": len(reachable),
        "reachable_private_key_path_count": len(unique_paths),
        "reachable_private_key_objects": reachable,
        "external_key_rotation_status": "NOT_RUN",
        "required_administrator_actions": [
            "coordinate and back up an exact-ref Git history rewrite",
            "force-update only the explicitly approved remote refs",
            "expire old clones, forks, caches, and pull-request refs",
            "rotate or revoke every disclosed key in its external trust system",
            "rerun this audit from a fresh clone of the rewritten remote",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--allow-findings",
        action="store_true",
        help="emit the report without a failing exit code (never changes its decision)",
    )
    arguments = parser.parse_args()
    try:
        report = audit(arguments.repo)
    except (OSError, RuntimeError) as error:
        print(json.dumps({"decision": "AUDIT_ERROR", "error": str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    if report["decision"] == "PASS" or arguments.allow_findings:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
