#!/usr/bin/env python3
"""Capture the artifact, environment and provenance of a real evidence run.

Every value here is read from the machine that performed the run — repository
revision, uncommitted changes under the artifact roots, tool digests, interpreter
and OS versions. Nothing is asserted on the operator's behalf: if the artifact
roots carry uncommitted changes, the record says so, because the recorded
revision then does not reproduce the run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


GIT_TIMEOUT_SECONDS = 30


def git(*args: str, cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            check=False, timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def tracked_changes(repo: Path, roots: list[str]) -> tuple[int | None, str]:
    """Count uncommitted changes to tracked files under the artifact roots.

    A full `git status` walks the entire working tree, which on a repository
    this size is slow enough to look like a hang. Scoping the diff to the roots
    that actually make up the artifact is both faster and more honest: it is the
    artifact's reproducibility we are recording, not the whole tree's.
    """
    scope = roots or ["."]
    output = git("diff", "--name-only", "HEAD", "--", *scope, cwd=repo)
    if output is None:
        return None, "git was unavailable or timed out, so reproducibility could not be established"
    changed = len([line for line in output.splitlines() if line.strip()])
    if changed:
        return changed, f"{changed} tracked file(s) under {scope} differ from HEAD"
    return 0, f"no tracked file under {scope} differs from HEAD (untracked files were not enumerated)"


def tool_version(*command: str) -> str | None:
    try:
        completed = subprocess.run(list(command), capture_output=True, text=True, check=False)
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return (completed.stdout or completed.stderr).strip().splitlines()[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--run-report", type=Path, required=True,
                        help="the JSON report produced by the check being attested")
    parser.add_argument("--claim", action="append", required=True,
                        help="claim id this provenance record binds to (repeatable)")
    parser.add_argument("--surface-root", action="append", default=[],
                        help="repository root whose files constitute the artifact under test")
    parser.add_argument("--surface-glob", default="*.schema.json")
    arguments = parser.parse_args()

    repo, pack = arguments.repo.resolve(), arguments.pack.resolve()
    report = json.loads(arguments.run_report.read_text(encoding="utf-8"))

    # Artifact: the exact bytes the claim is about, enumerated with digests.
    members = []
    for root in arguments.surface_root:
        for path in sorted((repo / root).rglob(arguments.surface_glob)):
            members.append({"path": path.relative_to(repo).as_posix(), "sha256": sha256_file(path),
                            "bytes": path.stat().st_size})
    if not members:
        print("ERROR: the artifact surface is empty; pass at least one --surface-root", file=sys.stderr)
        return 2
    surface = {
        "artifactType": "schema-surface",
        "roots": arguments.surface_root,
        "memberCount": len(members),
        "compositeDigest": "sha256:" + hashlib.sha256(
            "".join(f"{item['path']}:{item['sha256']}\n" for item in members).encode()
        ).hexdigest(),
        "members": members,
    }
    artifact_path = pack / "artifact" / "schema-surface.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(surface, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Environment: the toolchain that produced the run.
    changed_count, cleanliness_note = tracked_changes(repo, arguments.surface_root)
    environment = {
        "capturedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "pythonVersion": platform.python_version(),
        "pythonImplementation": platform.python_implementation(),
        "gitVersion": tool_version("git", "--version"),
        "opensslVersion": tool_version("openssl", "version"),
        "repositoryRevision": git("rev-parse", "HEAD", cwd=repo),
        "artifactRootsClean": changed_count == 0 if changed_count is not None else None,
        "uncommittedTrackedPathCount": changed_count,
        "cleanlinessNote": cleanliness_note,
    }
    environment_path = pack / "environment" / "toolchain.json"
    environment_path.parent.mkdir(parents=True, exist_ok=True)
    environment_path.write_text(json.dumps(environment, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Provenance: what ran, against what, producing which bytes.
    provenance = {
        "recordType": "provenance",
        "batch": report.get("batch"),
        "check": report.get("check"),
        "claimIds": sorted(set(arguments.claim)),
        "repositoryRevision": environment["repositoryRevision"],
        "artifactRootsClean": environment["artifactRootsClean"],
        "baselineRevision": report.get("baselineRevision"),
        "replayCommand": report.get("replayCommand"),
        "toolDigest": report.get("toolDigest"),
        "runReport": {
            "path": arguments.run_report.resolve().relative_to(pack).as_posix(),
            "sha256": sha256_file(arguments.run_report),
            "bytes": arguments.run_report.stat().st_size,
        },
        "artifactCompositeDigest": surface["compositeDigest"],
        "environmentDigest": sha256_file(environment_path),
        "startedAt": report.get("startedAt"),
        "finishedAt": report.get("finishedAt"),
        "reproducible": bool(environment["artifactRootsClean"]),
        "reproducibilityNote": (
            f"{environment['cleanlinessNote']}; this run replays from the recorded revision."
            if environment["artifactRootsClean"]
            else f"{environment['cleanlinessNote']}; the recorded revision alone does not reproduce this run."
        ),
    }
    provenance_path = pack / "evidence" / "provenance" / f"{report.get('check', 'run')}-provenance.json"
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    provenance_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for path in (artifact_path, environment_path, provenance_path):
        print(f"wrote {path.relative_to(pack)}")
    if not environment["artifactRootsClean"]:
        print(f"WARNING: {environment['cleanlinessNote']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
