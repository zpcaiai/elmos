#!/usr/bin/env python3
"""Materialize and verify a client-pack source snapshot from immutable Git blobs.

The source manifest is treated as untrusted input.  Paths, object types, the
complete Git tree inventory, byte counts, and SHA-256 digests are checked before
anything is written below the fixed pack-local snapshot directory.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import uuid


SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
REVISION_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
MANIFEST_KIND = "elmos.git-source-snapshot-manifest"
SOURCE_ROOT = "source-snapshots/files"


class SnapshotError(RuntimeError):
    """Raised when a snapshot cannot be proven safe and content-exact."""


@dataclass(frozen=True)
class VerifiedEntry:
    path: str
    sha256: str
    size: int
    mode: str
    data: bytes


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SnapshotError(f"JSON document must be an object: {path}")
    return value


def _safe_relative(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or any(character in value for character in ("\0", "\r", "\n"))
    ):
        raise SnapshotError(f"{label} must be a non-empty POSIX relative path")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise SnapshotError(f"{label} is unsafe: {value!r}")
    normalized = candidate.as_posix()
    if normalized != value:
        raise SnapshotError(f"{label} is not canonical: {value!r}")
    return normalized


def _inside(root: Path, relative: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    try:
        candidate.resolve(strict=False).relative_to(root.resolve())
    except ValueError as exc:
        raise SnapshotError(f"path escapes declared root: {relative}") from exc
    return candidate


def _git(repo_root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise SnapshotError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _git_blobs(repo_root: Path, object_ids: list[str]) -> dict[str, bytes]:
    unique_ids = list(dict.fromkeys(object_ids))
    completed = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=repo_root,
        input="".join(f"{object_id}\n" for object_id in unique_ids).encode("ascii"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise SnapshotError(f"git cat-file --batch failed: {detail}")
    stream = io.BytesIO(completed.stdout)
    blobs: dict[str, bytes] = {}
    for requested_id in unique_ids:
        header = stream.readline()
        try:
            actual_id, object_type, raw_size = header.rstrip(b"\n").decode("ascii").split(" ")
            size = int(raw_size)
        except (UnicodeError, ValueError) as exc:
            raise SnapshotError(f"invalid git cat-file response for {requested_id}") from exc
        if actual_id != requested_id or object_type != "blob" or size < 0:
            raise SnapshotError(f"unexpected git cat-file response for {requested_id}")
        data = stream.read(size)
        if len(data) != size or stream.read(1) != b"\n":
            raise SnapshotError(f"truncated git blob response for {requested_id}")
        blobs[requested_id] = data
    if stream.read():
        raise SnapshotError("git cat-file emitted trailing unbound bytes")
    return blobs


def _aggregate_digest(entries: list[VerifiedEntry]) -> str:
    serialized = "\n".join(
        f"{entry.path}\0{entry.sha256}\0{entry.size}"
        for entry in sorted(entries, key=lambda item: item.path)
    ).encode("utf-8")
    return _sha256(serialized)


def _manifest_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw_entries = manifest.get("files")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise SnapshotError("source snapshot file inventory is empty")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise SnapshotError(f"source snapshot entry {index} is not an object")
        path = _safe_relative(raw.get("path"), f"files[{index}].path")
        digest = raw.get("sha256")
        size = raw.get("bytes")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise SnapshotError(f"files[{index}].sha256 is invalid")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise SnapshotError(f"files[{index}].bytes is invalid")
        if path in seen:
            raise SnapshotError(f"duplicate source snapshot path: {path}")
        seen.add(path)
        entries.append({"path": path, "sha256": digest, "bytes": size})
    if [entry["path"] for entry in entries] != sorted(seen):
        raise SnapshotError("source snapshot entries must be sorted by canonical path")
    return entries


def _verify_git_manifest(
    repo_root: Path, manifest: dict[str, Any]
) -> list[VerifiedEntry]:
    if manifest.get("kind") != MANIFEST_KIND:
        raise SnapshotError(f"manifest kind must be {MANIFEST_KIND!r}")
    revision = manifest.get("source_revision")
    if not isinstance(revision, str) or REVISION_RE.fullmatch(revision) is None:
        raise SnapshotError("source_revision must be a full lowercase Git object ID")
    resolved = _git(repo_root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if resolved.decode("ascii").strip() != revision:
        raise SnapshotError("source_revision does not resolve to its exact commit ID")

    repository_root = _safe_relative(
        manifest.get("repository_relative_root"), "repository_relative_root"
    )
    entries = _manifest_entries(manifest)
    prefix = repository_root + "/"
    if any(not entry["path"].startswith(prefix) for entry in entries):
        raise SnapshotError("manifest path is outside repository_relative_root")

    tree_output = _git(
        repo_root,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        revision,
        "--",
        repository_root,
    )
    tree: dict[str, tuple[str, str]] = {}
    for record in tree_output.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split(" ")
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise SnapshotError("Git tree contains an unsupported path record") from exc
        _safe_relative(path, "Git tree path")
        if object_type != "blob" or mode not in {"100644", "100755"}:
            raise SnapshotError(
                f"unsupported Git object in source snapshot: {path} ({mode} {object_type})"
            )
        tree[path] = (mode, object_id)

    declared_paths = {entry["path"] for entry in entries}
    tree_paths = set(tree)
    if declared_paths != tree_paths:
        missing = sorted(tree_paths - declared_paths)
        extra = sorted(declared_paths - tree_paths)
        raise SnapshotError(
            "manifest does not bind the exact Git tree; "
            f"missing={missing[:5]!r}, extra={extra[:5]!r}"
        )

    blobs = _git_blobs(repo_root, [tree[entry["path"]][1] for entry in entries])
    verified: list[VerifiedEntry] = []
    for entry in entries:
        mode, object_id = tree[entry["path"]]
        data = blobs[object_id]
        actual_digest = _sha256(data)
        if actual_digest != entry["sha256"] or len(data) != entry["bytes"]:
            raise SnapshotError(f"Git blob does not match manifest: {entry['path']}")
        verified.append(
            VerifiedEntry(
                path=entry["path"],
                sha256=actual_digest,
                size=len(data),
                mode=mode,
                data=data,
            )
        )
    return verified


def _snapshot_root(pack: Path, manifest: dict[str, Any], *, allow_missing: bool) -> Path:
    value = manifest.get("source_root")
    if value is None and allow_missing:
        value = SOURCE_ROOT
    value = _safe_relative(value, "source_root")
    if value != SOURCE_ROOT:
        raise SnapshotError(f"source_root must be the fixed pack-local path {SOURCE_ROOT!r}")
    return _inside(pack, value)


def _walk_exact_files(root: Path) -> set[str]:
    if not root.is_dir() or root.is_symlink():
        raise SnapshotError("materialized source_root is missing or unsafe")
    files: set[str] = set()
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for directory in directories:
            candidate = current_path / directory
            if candidate.is_symlink():
                raise SnapshotError(f"materialized snapshot contains a symlink: {candidate}")
        for name in names:
            candidate = current_path / name
            if candidate.is_symlink() or not candidate.is_file():
                raise SnapshotError(f"materialized snapshot file is unsafe: {candidate}")
            files.add(candidate.relative_to(root).as_posix())
    return files


def _verify_materialized(root: Path, entries: list[VerifiedEntry]) -> None:
    expected = {entry.path for entry in entries}
    actual = _walk_exact_files(root)
    if actual != expected:
        raise SnapshotError(
            "materialized snapshot does not contain the exact file set; "
            f"missing={sorted(expected - actual)[:5]!r}, extra={sorted(actual - expected)[:5]!r}"
        )
    for entry in entries:
        path = _inside(root, entry.path)
        data = path.read_bytes()
        if len(data) != entry.size or _sha256(data) != entry.sha256:
            raise SnapshotError(f"materialized snapshot drift: {entry.path}")


def _verify_git_trackable(
    repo_root: Path, source_root: Path, entries: list[VerifiedEntry]
) -> None:
    try:
        relative_root = source_root.resolve(strict=False).relative_to(repo_root.resolve())
    except ValueError as exc:
        raise SnapshotError("pack-local source_root must be inside the Git repository") from exc
    paths = [
        (relative_root / PurePosixPath(entry.path)).as_posix()
        for entry in entries
    ]
    completed = subprocess.run(
        ["git", "check-ignore", "--no-index", "-z", "--stdin"],
        cwd=repo_root,
        input=("\0".join(paths) + "\0").encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode not in {0, 1}:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise SnapshotError(f"git check-ignore failed: {detail}")
    ignored = [
        value.decode("utf-8", "replace")
        for value in completed.stdout.split(b"\0")
        if value
    ]
    if ignored:
        raise SnapshotError(
            "materialized snapshot files are ignored by Git and would be omitted from a commit: "
            f"{ignored[:5]!r}"
        )


def _write_directory_atomically(
    target: Path, entries: list[VerifiedEntry], *, force: bool
) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            _verify_materialized(target, entries)
            return False
        except SnapshotError:
            if not force:
                raise SnapshotError(
                    "existing materialized snapshot is stale; rerun with --force to replace only that snapshot root"
                )

    temporary = Path(tempfile.mkdtemp(prefix=".files.tmp-", dir=target.parent))
    backup: Path | None = None
    try:
        for entry in entries:
            destination = _inside(temporary, entry.path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(entry.data)
            destination.chmod(0o755 if entry.mode == "100755" else 0o644)
        _verify_materialized(temporary, entries)
        if target.exists():
            backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
            os.replace(target, backup)
        try:
            os.replace(temporary, target)
        except BaseException:
            if backup is not None and backup.exists() and not target.exists():
                os.replace(backup, target)
            raise
        if backup is not None:
            shutil.rmtree(backup)
        return True
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    _atomic_write(
        path,
        (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def _rewrite_json_bindings(
    pack: Path, source_root: Path, manifest_path: Path, old_digest: str, new_digest: str
) -> list[str]:
    if old_digest == new_digest:
        return []
    if SHA256_RE.fullmatch(old_digest) is None:
        raise SnapshotError("legacy snapshot_digest is invalid; refusing broad binding rewrite")
    old_bytes = old_digest.encode("ascii")
    new_bytes = new_digest.encode("ascii")
    updated: list[str] = []
    for path in sorted(pack.rglob("*.json")):
        if path == manifest_path:
            continue
        try:
            path.resolve().relative_to(source_root.resolve())
            continue
        except ValueError:
            pass
        data = path.read_bytes()
        if old_bytes not in data:
            continue
        try:
            json.loads(data)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SnapshotError(f"refusing to rewrite invalid JSON binding {path}: {exc}") from exc
        rewritten = data.replace(old_bytes, new_bytes)
        try:
            json.loads(rewritten)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SnapshotError(f"rewritten JSON binding became invalid {path}: {exc}") from exc
        _atomic_write(path, rewritten)
        updated.append(path.relative_to(pack).as_posix())
    return updated


def _check(pack: Path, repo_root: Path) -> dict[str, Any]:
    manifest_path = pack / "source-snapshots" / "manifest.json"
    manifest = _load_json(manifest_path)
    entries = _verify_git_manifest(repo_root, manifest)
    digest = _aggregate_digest(entries)
    if manifest.get("source_root") != SOURCE_ROOT:
        raise SnapshotError(f"manifest source_root must be {SOURCE_ROOT!r}")
    if manifest.get("aggregate_digest") != digest:
        raise SnapshotError("manifest aggregate_digest is stale")
    if manifest.get("snapshot_digest") != digest:
        raise SnapshotError("manifest snapshot_digest is stale")
    if manifest.get("file_count") != len(entries):
        raise SnapshotError("manifest file_count is stale")
    total_bytes = sum(entry.size for entry in entries)
    if manifest.get("total_bytes") != total_bytes:
        raise SnapshotError("manifest total_bytes is stale")
    source_root = _snapshot_root(pack, manifest, allow_missing=False)
    _verify_git_trackable(repo_root, source_root, entries)
    _verify_materialized(source_root, entries)
    return {
        "status": "PASSED",
        "pack": pack.name,
        "source_revision": manifest["source_revision"],
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "aggregate_digest": digest,
        "certification": "NOT_CERTIFIED",
    }


def _materialize(pack: Path, repo_root: Path, *, force: bool) -> dict[str, Any]:
    manifest_path = pack / "source-snapshots" / "manifest.json"
    manifest = _load_json(manifest_path)
    entries = _verify_git_manifest(repo_root, manifest)
    digest = _aggregate_digest(entries)
    old_digest = manifest.get("snapshot_digest")
    if not isinstance(old_digest, str):
        raise SnapshotError("manifest snapshot_digest is missing")
    source_root = _snapshot_root(pack, manifest, allow_missing=True)
    _verify_git_trackable(repo_root, source_root, entries)
    wrote_files = _write_directory_atomically(source_root, entries, force=force)

    manifest["source_root"] = SOURCE_ROOT
    manifest["file_count"] = len(entries)
    manifest["total_bytes"] = sum(entry.size for entry in entries)
    manifest["snapshot_digest"] = digest
    manifest["aggregate_digest"] = digest
    manifest["digest_algorithm"] = "sha256-lf-records-v1:path-nul-digest-nul-bytes"
    manifest["materialization"] = {
        "state": "MATERIALIZED_FROM_GIT",
        "git_object_verification": "PASSED",
        "source_revision": manifest["source_revision"],
        "file_count": len(entries),
        "total_bytes": manifest["total_bytes"],
        "external_runtime_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
    manifest["boundary"] = (
        "Pack-local files are exact copies of the complete regular-file Git tree at "
        "source_revision; no source script is executed during materialization."
    )
    _write_manifest(manifest_path, manifest)
    rewritten = _rewrite_json_bindings(
        pack, source_root, manifest_path, old_digest, digest
    )
    checked = _check(pack, repo_root)
    checked.update(
        {
            "mode": "materialize",
            "materialized_files_replaced": wrote_files,
            "rewritten_json_bindings": rewritten,
        }
    )
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("materialize", "check"))
    parser.add_argument("pack_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace only a stale pack-local source-snapshots/files directory",
    )
    args = parser.parse_args()
    pack = args.pack_dir.resolve()
    repo_root = args.repo_root.resolve()
    try:
        if not pack.is_dir():
            raise SnapshotError(f"pack directory is missing: {pack}")
        if not (repo_root / ".git").exists():
            raise SnapshotError(f"repo root does not contain .git: {repo_root}")
        result = (
            _materialize(pack, repo_root, force=args.force)
            if args.mode == "materialize"
            else _check(pack, repo_root)
        )
    except SnapshotError as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
