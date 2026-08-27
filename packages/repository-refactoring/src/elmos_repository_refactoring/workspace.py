"""Content-addressed workspace snapshots.

Every Skill that needs to see repository content sees it through a
:class:`WorkspaceSnapshot`.  A snapshot is immutable, content-addressed and can
be built from two sources:

* an inline payload (``files: [{path, content}]``) — the default, which keeps
  the runtime hermetic and makes every test reproduce byte-for-byte;
* an approved on-disk root, which the host must hand over explicitly through
  the trusted context.  There is no way for a task payload to name a directory
  and have the runtime read it.

The snapshot never executes repository content, never follows a symlink out of
the root, and never reports an unreadable file as an empty one — unreadable
paths are recorded as ``unreadable`` so downstream coverage maths cannot
silently treat them as "nothing there".
"""

from __future__ import annotations

import os
import stat
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .contracts import (
    ContractError,
    canonical_json,
    detect_newline,
    integer_value,
    match_path_glob,
    normalize_relative_path,
    optional_string,
    require_digest,
    require_mapping,
    require_mapping_sequence,
    require_string,
    require_string_sequence,
    sha256_bytes,
    sha256_payload,
)

#: Hard ceiling for a single text file the pure core will parse.  Larger files
#: are still inventoried (path, size, digest) but are never loaded into memory
#: for transformation, because a runaway generated file must not be able to
#: exhaust a worker.
MAX_TEXT_BYTES = 4 * 1024 * 1024

#: Hard ceiling for the number of files in one snapshot partition.
MAX_FILES = 400_000

DEFAULT_EXCLUDED_DIRECTORIES: tuple[str, ...] = (
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".gradle",
    ".venv",
    "venv",
    "node_modules",
    "target/debug",
    "target/release",
)

#: Path fragments that mark generated or vendored trees.  These are *reported*,
#: never silently dropped: a refactor that must touch generated code needs to
#: know it is generated, not to be told the files do not exist.
GENERATED_MARKERS: tuple[str, ...] = (
    "**/generated/**",
    "**/gen/**",
    "**/*_pb2.py",
    "**/*_pb2_grpc.py",
    "**/*.pb.go",
    "**/*.g.dart",
    "**/*.freezed.dart",
    "**/*.generated.ts",
    "**/*.designer.cs",
    "**/target/generated-sources/**",
    "**/build/generated/**",
)

VENDOR_MARKERS: tuple[str, ...] = (
    "vendor/**",
    "**/third_party/**",
    "**/thirdparty/**",
    "**/node_modules/**",
    "**/Pods/**",
)

_BINARY_EXTENSIONS = frozenset(
    """
    png jpg jpeg gif bmp ico webp tiff psd
    pdf zip gz tgz bz2 xz zst 7z rar jar war ear
    class pyc pyo so dylib dll exe bin o a lib obj
    woff woff2 ttf otf eot mp3 mp4 mov avi wav flac
    db sqlite sqlite3 parquet avro pack idx wasm
    """.split()
)


@dataclass(frozen=True, slots=True)
class FileRecord:
    """One file in a snapshot.

    ``text`` is ``None`` for binary, oversized or unreadable files; callers must
    check :attr:`readable_text` rather than assuming content is present.
    """

    path: str
    size_bytes: int
    content_digest: str
    text: str | None = None
    binary: bool = False
    unreadable_reason: str | None = None
    newline: str = "\n"
    executable: bool = False

    @property
    def readable_text(self) -> bool:
        return self.text is not None

    @property
    def extension(self) -> str:
        name = self.path.rsplit("/", 1)[-1]
        return name.rsplit(".", 1)[-1].lower() if "." in name else ""

    @property
    def basename(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    def inventory_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "content_digest": self.content_digest,
            "binary": self.binary,
            "executable": self.executable,
        }
        if self.unreadable_reason is not None:
            payload["unreadable_reason"] = self.unreadable_reason
        return payload


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    """An immutable, content-addressed view of one repository revision."""

    repository_id: str
    revision: str
    files: Mapping[str, FileRecord]
    excluded_paths: tuple[str, ...] = ()
    truncated: bool = False
    filters_applied: tuple[str, ...] = ()
    root: Path | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.files, MappingProxyType):
            object.__setattr__(self, "files", MappingProxyType(dict(self.files)))

    # -- lookups ---------------------------------------------------------

    def __contains__(self, path: str) -> bool:
        return path in self.files

    def __len__(self) -> int:
        return len(self.files)

    def __iter__(self) -> Iterator[FileRecord]:
        for path in self.paths:
            yield self.files[path]

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(sorted(self.files))

    def get(self, path: str) -> FileRecord | None:
        return self.files.get(path)

    def require(self, path: str) -> FileRecord:
        record = self.files.get(path)
        if record is None:
            raise ContractError("unknown_path", f"path '{path}' is not present in the snapshot")
        return record

    def text_of(self, path: str) -> str:
        record = self.require(path)
        if record.text is None:
            raise ContractError(
                "unreadable_content",
                f"path '{path}' has no readable text ({record.unreadable_reason or 'binary'})",
            )
        return record.text

    def match(self, patterns: Sequence[str]) -> tuple[str, ...]:
        """Paths matching any glob in ``patterns`` (``**`` aware, ``/``-safe)."""

        if not patterns:
            return ()
        return tuple(
            path for path in self.paths if any(match_path_glob(path, pattern) for pattern in patterns)
        )

    def under(self, prefix: str) -> tuple[str, ...]:
        normalised = prefix.rstrip("/")
        return tuple(
            path for path in self.paths if path == normalised or path.startswith(normalised + "/")
        )

    # -- integrity -------------------------------------------------------

    @property
    def tree_digest(self) -> str:
        """Digest over (path, digest, mode) for every file, order-independent."""

        return sha256_payload(
            {
                "repository_id": self.repository_id,
                "revision": self.revision,
                "entries": [
                    {
                        "path": record.path,
                        "digest": record.content_digest,
                        "executable": record.executable,
                    }
                    for record in self
                ],
            }
        )

    @property
    def unreadable(self) -> tuple[FileRecord, ...]:
        return tuple(record for record in self if record.unreadable_reason is not None)

    @property
    def total_bytes(self) -> int:
        return sum(record.size_bytes for record in self.files.values())

    def coverage_payload(self) -> dict[str, Any]:
        readable = sum(1 for record in self.files.values() if record.readable_text)
        return {
            "file_count": len(self.files),
            "readable_text_files": readable,
            "binary_files": sum(1 for record in self.files.values() if record.binary),
            "unreadable_files": len(self.unreadable),
            "excluded_paths": list(self.excluded_paths),
            "filters_applied": list(self.filters_applied),
            "truncated": self.truncated,
            "total_bytes": self.total_bytes,
            "tree_digest": self.tree_digest,
        }

    # -- derivation ------------------------------------------------------

    def with_files(self, replacements: Mapping[str, str | None]) -> WorkspaceSnapshot:
        """Return a new snapshot with ``replacements`` applied.

        A ``None`` value deletes the path.  The original snapshot is untouched,
        which is what makes shard execution and rollback trivially correct.
        """

        updated = dict(self.files)
        for path, content in replacements.items():
            normalised = normalize_relative_path(path, "replacement.path")
            if content is None:
                updated.pop(normalised, None)
                continue
            previous = self.files.get(normalised)
            updated[normalised] = _text_record(
                normalised,
                content,
                executable=bool(previous.executable) if previous else False,
            )
        return WorkspaceSnapshot(
            repository_id=self.repository_id,
            revision=self.revision,
            files=updated,
            excluded_paths=self.excluded_paths,
            truncated=self.truncated,
            filters_applied=self.filters_applied,
            root=self.root,
        )

    # -- constructors ----------------------------------------------------

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> WorkspaceSnapshot:
        value = require_mapping(payload, "workspace")
        repository_id = require_string(value.get("repository_id"), "workspace.repository_id", max_length=128)
        revision = require_string(value.get("revision"), "workspace.revision", min_length=7, max_length=128)
        entries = require_mapping_sequence(value.get("files", ()), "workspace.files", max_items=MAX_FILES)
        files: dict[str, FileRecord] = {}
        for entry in entries:
            record = _record_from_payload(entry)
            if record.path in files:
                raise ContractError("duplicate_path", f"workspace contains duplicate path '{record.path}'")
            files[record.path] = record
        excluded = require_string_sequence(value.get("excluded_paths", ()), "workspace.excluded_paths")
        filters = require_string_sequence(value.get("filters_applied", ()), "workspace.filters_applied")
        return cls(
            repository_id=repository_id,
            revision=revision,
            files=files,
            excluded_paths=tuple(sorted(excluded)),
            filters_applied=tuple(sorted(filters)),
        )

    @classmethod
    def from_directory(
        cls,
        root: Path,
        *,
        repository_id: str,
        revision: str,
        include: Sequence[str] = (),
        exclude: Sequence[str] = (),
        excluded_directories: Sequence[str] = DEFAULT_EXCLUDED_DIRECTORIES,
        max_files: int = MAX_FILES,
        max_text_bytes: int = MAX_TEXT_BYTES,
    ) -> WorkspaceSnapshot:
        """Read an *approved* directory into a snapshot.

        The caller is responsible for having validated that ``root`` is an
        operator-approved workspace; this function only guarantees that nothing
        outside ``root`` is read once it starts.
        """

        resolved = root.resolve(strict=True)
        if not resolved.is_dir():
            raise ContractError("workspace_not_directory", "workspace root must be a directory")

        files: dict[str, FileRecord] = {}
        excluded_paths: list[str] = []
        truncated = False

        for current_root, dirnames, filenames in os.walk(resolved, followlinks=False):
            current = Path(current_root)
            rel_dir = current.relative_to(resolved).as_posix()
            pruned: list[str] = []
            for name in sorted(dirnames):
                rel = name if rel_dir in ("", ".") else f"{rel_dir}/{name}"
                candidate = current / name
                if candidate.is_symlink():
                    excluded_paths.append(f"{rel} (symlinked-directory)")
                    continue
                excluded_dir = name in excluded_directories or any(
                    match_path_glob(rel, pattern) for pattern in excluded_directories
                )
                if excluded_dir:
                    excluded_paths.append(f"{rel} (excluded-directory)")
                    continue
                if exclude and any(match_path_glob(rel, pattern) for pattern in exclude):
                    excluded_paths.append(f"{rel} (exclude-rule)")
                    continue
                pruned.append(name)
            dirnames[:] = pruned

            for name in sorted(filenames):
                rel = name if rel_dir in ("", ".") else f"{rel_dir}/{name}"
                if include and not any(match_path_glob(rel, pattern) for pattern in include):
                    continue
                if exclude and any(match_path_glob(rel, pattern) for pattern in exclude):
                    excluded_paths.append(f"{rel} (exclude-rule)")
                    continue
                if len(files) >= max_files:
                    truncated = True
                    break
                path = current / name
                files[rel] = _record_from_disk(rel, path, resolved, max_text_bytes)
            if truncated:
                break

        filters = tuple(sorted({*include, *exclude, *excluded_directories}))
        return cls(
            repository_id=repository_id,
            revision=revision,
            files=files,
            excluded_paths=tuple(sorted(excluded_paths)),
            truncated=truncated,
            filters_applied=filters,
            root=resolved,
        )


# ---------------------------------------------------------------------------
# Record construction
# ---------------------------------------------------------------------------


def _looks_binary(data: bytes) -> bool:
    if b"\x00" in data[:8192]:
        return True
    sample = data[:8192]
    if not sample:
        return False
    printable = sum(1 for byte in sample if byte in (9, 10, 13) or 32 <= byte < 127 or byte >= 128)
    return printable / len(sample) < 0.85


def _text_record(path: str, content: str, *, executable: bool = False) -> FileRecord:
    data = content.encode("utf-8")
    return FileRecord(
        path=path,
        size_bytes=len(data),
        content_digest=sha256_bytes(data),
        text=content,
        binary=False,
        newline=detect_newline(content),
        executable=executable,
    )


def _record_from_payload(entry: Mapping[str, Any]) -> FileRecord:
    path = normalize_relative_path(entry.get("path"), "workspace.files[].path")
    executable = bool(entry.get("executable", False))
    if "content" in entry:
        content = entry.get("content")
        if not isinstance(content, str):
            raise ContractError("invalid_string", "workspace.files[].content must be a string")
        record = _text_record(path, content, executable=executable)
        declared = entry.get("content_digest")
        declared_digest = (
            None if declared is None else require_digest(declared, "workspace.files[].content_digest")
        )
        if declared_digest is not None and declared_digest != record.content_digest:
            raise ContractError(
                "content_digest_mismatch",
                f"declared digest for '{path}' does not match its content",
            )
        return record
    digest = require_digest(entry.get("content_digest"), "workspace.files[].content_digest")
    size = integer_value(entry.get("size_bytes", 0), "workspace.files[].size_bytes", minimum=0)
    reason = optional_string(entry.get("unreadable_reason"), "workspace.files[].unreadable_reason")
    binary = bool(entry.get("binary", reason is None))
    return FileRecord(
        path=path,
        size_bytes=size,
        content_digest=digest,
        text=None,
        binary=binary,
        unreadable_reason=reason,
        executable=executable,
    )


def _record_from_disk(rel: str, path: Path, root: Path, max_text_bytes: int) -> FileRecord:
    try:
        info = path.lstat()
    except OSError as exc:
        return FileRecord(rel, 0, sha256_bytes(b""), None, False, f"stat-failed:{exc.errno}")
    if stat.S_ISLNK(info.st_mode):
        try:
            target = path.resolve(strict=True)
            target.relative_to(root)
        except (OSError, ValueError):
            return FileRecord(rel, 0, sha256_bytes(b""), None, False, "symlink-outside-workspace")
        try:
            info = path.stat()
        except OSError as exc:
            return FileRecord(rel, 0, sha256_bytes(b""), None, False, f"stat-failed:{exc.errno}")
    if not stat.S_ISREG(info.st_mode):
        return FileRecord(rel, 0, sha256_bytes(b""), None, False, "not-a-regular-file")
    executable = bool(info.st_mode & stat.S_IXUSR)
    size = int(info.st_size)
    try:
        data = path.read_bytes()
    except OSError as exc:
        return FileRecord(rel, size, sha256_bytes(b""), None, False, f"read-failed:{exc.errno}", executable=executable)
    digest = sha256_bytes(data)
    extension = rel.rsplit(".", 1)[-1].lower() if "." in rel.rsplit("/", 1)[-1] else ""
    if extension in _BINARY_EXTENSIONS or _looks_binary(data):
        return FileRecord(rel, size, digest, None, True, None, executable=executable)
    if size > max_text_bytes:
        return FileRecord(rel, size, digest, None, False, "exceeds-max-text-bytes", executable=executable)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return FileRecord(rel, size, digest, None, False, "not-utf8", executable=executable)
    return FileRecord(
        path=rel,
        size_bytes=size,
        content_digest=digest,
        text=text,
        binary=False,
        newline=detect_newline(text),
        executable=executable,
    )


def snapshot_from_context(
    payload: Mapping[str, Any],
    *,
    approved_root: Path | None,
    field_name: str = "workspace",
) -> WorkspaceSnapshot:
    """Build a snapshot from ``payload``, allowing a disk read only if approved.

    A payload may say ``{"source": "approved-root", ...}`` but that only works
    when the *host* supplied an approved root through the trusted context.  A
    task payload can therefore never widen filesystem reach on its own.
    """

    value = require_mapping(payload, field_name)
    source = value.get("source", "inline")
    if source == "inline":
        return WorkspaceSnapshot.from_payload(value)
    if source != "approved-root":
        raise ContractError("invalid_workspace_source", f"{field_name}.source must be inline or approved-root")
    if approved_root is None:
        raise ContractError(
            "workspace_root_not_approved",
            "reading an on-disk workspace requires a host-approved workspace root",
        )
    sub_path = value.get("sub_path")
    root = approved_root
    if sub_path is not None:
        relative = normalize_relative_path(sub_path, f"{field_name}.sub_path")
        root = (approved_root / relative).resolve()
        try:
            root.relative_to(approved_root)
        except ValueError as exc:
            raise ContractError("path_escape", f"{field_name}.sub_path escapes the approved root") from exc
    return WorkspaceSnapshot.from_directory(
        root,
        repository_id=require_string(value.get("repository_id"), f"{field_name}.repository_id", max_length=128),
        revision=require_string(value.get("revision"), f"{field_name}.revision", min_length=7, max_length=128),
        include=require_string_sequence(value.get("include", ()), f"{field_name}.include"),
        exclude=require_string_sequence(value.get("exclude", ()), f"{field_name}.exclude"),
    )


def classify_path(path: str) -> tuple[str, ...]:
    """Non-exclusive structural labels used across discovery and impact analysis."""

    labels: list[str] = []
    if any(match_path_glob(path, pattern) for pattern in GENERATED_MARKERS):
        labels.append("generated")
    if any(match_path_glob(path, pattern) for pattern in VENDOR_MARKERS):
        labels.append("vendored")
    lowered = path.lower()
    basename = lowered.rsplit("/", 1)[-1]
    if (
        "/test/" in f"/{lowered}"
        or "/tests/" in f"/{lowered}"
        or "/spec/" in f"/{lowered}"
        or basename.startswith("test_")
        or basename.endswith(("_test.py", "_test.go", ".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.js"))
        or basename.endswith(("test.java", "tests.cs", "spec.rb"))
    ):
        labels.append("test")
    if "/migrations/" in f"/{lowered}" or "/migration/" in f"/{lowered}" or basename.endswith(".sql"):
        labels.append("data-migration")
    if basename in {
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
    } or lowered.endswith((".tf", ".tfvars", ".yaml", ".yml", ".toml", ".ini", ".properties", ".env")):
        labels.append("configuration")
    return tuple(labels)


def digest_of_paths(snapshot: WorkspaceSnapshot, paths: Iterable[str]) -> str:
    return sha256_payload(
        {"entries": [{"path": path, "digest": snapshot.require(path).content_digest} for path in sorted(set(paths))]}
    )


def snapshot_manifest(snapshot: WorkspaceSnapshot) -> str:
    return canonical_json([record.inventory_payload() for record in snapshot])


@dataclass(frozen=True, slots=True)
class MaterializationReport:
    """What reached disk, and — just as importantly — what did not."""

    root: str
    written: tuple[str, ...]
    #: Files the snapshot describes but cannot reproduce: binary assets and
    #: anything it failed to decode.  A toolchain run over this tree is
    #: therefore running over an *incomplete* tree, and a caller that treats
    #: the result as covering the whole repository is wrong.
    skipped: tuple[Mapping[str, str], ...]

    @property
    def complete(self) -> bool:
        return not self.skipped

    def to_payload(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "written": list(self.written),
            "skipped": [dict(item) for item in self.skipped],
            "complete": self.complete,
        }


def materialize(
    snapshot: WorkspaceSnapshot,
    root: Path,
    *,
    allow_existing: bool = False,
) -> MaterializationReport:
    """Write a snapshot to a directory so a real toolchain can run over it.

    This is the *only* write path out of a snapshot, and it is deliberately a
    free function taking an explicit root rather than a method: materializing
    is a host decision with filesystem consequences, and it should read like
    one at the call site.

    What it refuses to do:

    * write anywhere but under ``root`` — every path is re-normalised and
      re-checked after joining, so a crafted path cannot escape;
    * write into a directory that already has contents, unless the caller says
      so, because silently merging into someone else's tree is how a sandbox
      run picks up files nobody accounted for;
    * invent content for a file it cannot reproduce.  A binary asset or an
      undecodable file is *skipped and reported*, never written as an empty
      file — an empty stand-in would make a compiler or a test runner report
      on a tree that does not exist anywhere.
    """

    resolved = root.resolve()
    if not resolved.is_dir():
        raise ContractError("materialize_root_missing", f"'{root}' is not a directory")
    if not allow_existing and any(resolved.iterdir()):
        raise ContractError(
            "materialize_root_not_empty",
            f"'{root}' is not empty; materializing into it would mix this snapshot with "
            "files it does not describe",
        )

    written: list[str] = []
    skipped: list[Mapping[str, str]] = []
    for record in snapshot:
        if record.text is None:
            skipped.append(
                {
                    "path": record.path,
                    "reason": record.unreadable_reason or ("binary" if record.binary else "no-content"),
                }
            )
            continue
        relative = normalize_relative_path(record.path, "snapshot.path")
        target = (resolved / relative).resolve()
        try:
            target.relative_to(resolved)
        except ValueError as exc:
            raise ContractError(
                "path_escape", f"'{record.path}' resolves outside the materialization root"
            ) from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(record.text, encoding="utf-8", newline="")
        if record.executable:
            target.chmod(target.stat().st_mode | stat.S_IXUSR)
        written.append(record.path)
    return MaterializationReport(
        root=str(resolved),
        written=tuple(sorted(written)),
        skipped=tuple(sorted(skipped, key=lambda item: item["path"])),
    )


__all__ = [
    "DEFAULT_EXCLUDED_DIRECTORIES",
    "GENERATED_MARKERS",
    "MAX_FILES",
    "MAX_TEXT_BYTES",
    "VENDOR_MARKERS",
    "FileRecord",
    "MaterializationReport",
    "WorkspaceSnapshot",
    "classify_path",
    "digest_of_paths",
    "materialize",
    "snapshot_from_context",
    "snapshot_manifest",
]
