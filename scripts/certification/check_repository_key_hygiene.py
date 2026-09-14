#!/usr/bin/env python3
"""Fail closed when a tracked file contains private signing-key material."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PEM_PATTERN = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\r\n]+"
    rb"(?:[A-Za-z0-9+/=]{16,}[\r\n]+){2,}"
)
FORBIDDEN_NAMES = re.compile(
    r"(?:^|/)(?:certifier-private\.pem|[^/]+\.private\.pem|[^/]+-private\.pem)$",
    re.IGNORECASE,
)
FORBIDDEN_SUFFIXES = {".p12", ".pfx", ".jks", ".keystore"}


def tracked_paths(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    )
    return [item.decode("utf-8") for item in completed.stdout.split(b"\0") if item]


def find_violations(root: Path, paths: list[str], *, scan_content: bool = True) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    for relative in paths:
        path = root / relative
        if not path.exists() or path.is_symlink() or not path.is_file():
            continue
        if FORBIDDEN_NAMES.search(relative) or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            violations.append({"path": relative, "reason": "forbidden-private-key-filename"})
            continue
        if not scan_content:
            continue
        try:
            payload = path.read_bytes()
        except OSError as exc:
            violations.append({"path": relative, "reason": f"unreadable:{exc.__class__.__name__}"})
            continue
        if PEM_PATTERN.search(payload):
            violations.append({"path": relative, "reason": "private-key-pem-block"})
    return violations


def main() -> int:
    paths = tracked_paths(ROOT)
    candidates = [
        relative for relative in paths
        if FORBIDDEN_NAMES.search(relative)
        or Path(relative).suffix.lower() in FORBIDDEN_SUFFIXES | {".pem", ".key"}
    ]
    violations = find_violations(ROOT, candidates)
    print(json.dumps({
        "check": "repository-private-key-hygiene",
        "status": "PASS" if not violations else "FAIL",
        "certification": "NOT_CERTIFIED",
        "tracked_private_key_count": len(violations),
        "violations": violations,
    }, ensure_ascii=False, indent=2))
    return 0 if not violations else 2


if __name__ == "__main__":
    raise SystemExit(main())
