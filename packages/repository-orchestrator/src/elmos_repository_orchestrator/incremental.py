"""Digest-driven incremental analysis, verified cache, and bounded batching."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Generic, Iterable, Iterator, Mapping, Sequence, TypeVar

from .contracts import ContractError, canonical_json, normalize_relative_path, require_string, sha256_payload


T = TypeVar("T")
R = TypeVar("R")


def _confined(root: Path, relative: str) -> Path:
    normalized = normalize_relative_path(relative)
    candidate = (root / normalized).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ContractError("path_escape", "path escapes the approved repository root") from exc
    return candidate


def _file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return "sha256:" + digest.hexdigest(), size


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    path: str
    content_sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ManifestDelta:
    changed: tuple[FileFingerprint, ...]
    deleted: tuple[str, ...]
    unchanged: tuple[str, ...]
    manifest_digest: str


class IncrementalManifest:
    """Updates only paths reported by SCM/watchers; it does not rescan the tree."""

    def __init__(self, root: Path, entries: Mapping[str, FileFingerprint] | None = None):
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ContractError("repository_root_invalid", "repository root must be a directory")
        self._entries = dict(entries or {})

    def update(self, changed_paths: Iterable[str], deleted_paths: Iterable[str] = ()) -> ManifestDelta:
        changed: list[FileFingerprint] = []
        unchanged: list[str] = []
        for relative in sorted(set(changed_paths)):
            normalized = normalize_relative_path(relative)
            path = _confined(self.root, normalized)
            if not path.is_file():
                raise ContractError("changed_file_missing", f"changed path is not a file: {normalized}")
            digest, size = _file_digest(path)
            fingerprint = FileFingerprint(normalized, digest, size)
            if self._entries.get(normalized) == fingerprint:
                unchanged.append(normalized)
            else:
                self._entries[normalized] = fingerprint
                changed.append(fingerprint)
        deleted: list[str] = []
        for relative in sorted(set(deleted_paths)):
            normalized = normalize_relative_path(relative)
            if normalized in self._entries:
                del self._entries[normalized]
                deleted.append(normalized)
        digest = sha256_payload(
            [
                {"path": item.path, "content_sha256": item.content_sha256, "size_bytes": item.size_bytes}
                for item in sorted(self._entries.values(), key=lambda value: value.path)
            ]
        )
        return ManifestDelta(tuple(changed), tuple(deleted), tuple(unchanged), digest)

    @property
    def entries(self) -> Mapping[str, FileFingerprint]:
        return dict(self._entries)


class VerifiedArtifactCache:
    """Durable scoped cache that re-hashes payloads before every read."""

    def __init__(self, database_path: Path):
        self.path = database_path.resolve(strict=False)
        if not self.path.parent.is_dir():
            raise ContractError("cache_parent_missing", "cache database parent must exist")
        self.connection = sqlite3.connect(self.path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS artifact_cache (
              tenant_id TEXT NOT NULL,
              project_id TEXT NOT NULL,
              revision_id TEXT NOT NULL,
              cache_key TEXT NOT NULL,
              contract_digest TEXT NOT NULL,
              payload_json BLOB NOT NULL,
              payload_sha256 TEXT NOT NULL,
              PRIMARY KEY (tenant_id, project_id, revision_id, cache_key, contract_digest)
            )
            """
        )
        self.connection.commit()

    @staticmethod
    def _scope(values: Sequence[str]) -> tuple[str, ...]:
        return tuple(require_string(value, "cache.scope") for value in values)

    def put(
        self,
        *,
        tenant_id: str,
        project_id: str,
        revision_id: str,
        cache_key: str,
        contract_digest: str,
        payload: Mapping[str, Any],
    ) -> str:
        tenant_id, project_id, revision_id, cache_key, contract_digest = self._scope(
            (tenant_id, project_id, revision_id, cache_key, contract_digest)
        )
        encoded = canonical_json(payload).encode("utf-8")
        digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
        self.connection.execute(
            """
            INSERT INTO artifact_cache VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, project_id, revision_id, cache_key, contract_digest)
            DO UPDATE SET payload_json=excluded.payload_json, payload_sha256=excluded.payload_sha256
            """,
            (tenant_id, project_id, revision_id, cache_key, contract_digest, encoded, digest),
        )
        self.connection.commit()
        return digest

    def get(
        self,
        *,
        tenant_id: str,
        project_id: str,
        revision_id: str,
        cache_key: str,
        contract_digest: str,
    ) -> Mapping[str, Any] | None:
        scope = self._scope((tenant_id, project_id, revision_id, cache_key, contract_digest))
        row = self.connection.execute(
            """
            SELECT payload_json, payload_sha256 FROM artifact_cache
            WHERE tenant_id=? AND project_id=? AND revision_id=? AND cache_key=? AND contract_digest=?
            """,
            scope,
        ).fetchone()
        if row is None:
            return None
        encoded, expected = row
        actual = "sha256:" + hashlib.sha256(encoded).hexdigest()
        if actual != expected:
            raise ContractError("cache_integrity_failure", "cached artifact digest mismatch")
        parsed = json.loads(encoded)
        if not isinstance(parsed, Mapping):
            raise ContractError("cache_contract_failure", "cached artifact is not an object")
        return parsed

    def invalidate_revision(self, *, tenant_id: str, project_id: str, revision_id: str) -> int:
        cursor = self.connection.execute(
            "DELETE FROM artifact_cache WHERE tenant_id=? AND project_id=? AND revision_id=?",
            self._scope((tenant_id, project_id, revision_id)),
        )
        self.connection.commit()
        return cursor.rowcount

    def close(self) -> None:
        self.connection.close()


@dataclass(frozen=True, slots=True)
class BatchResult(Generic[R]):
    items: tuple[R, ...]
    batch_count: int
    max_concurrency: int


class BoundedBatchExecutor(Generic[T, R]):
    """Batch provider calls with bounded concurrency and stable output order."""

    def __init__(self, batch_call: Callable[[Sequence[T]], Sequence[R]], *, batch_size: int, max_concurrency: int):
        if not 1 <= batch_size <= 1024:
            raise ContractError("invalid_batch_size", "batch_size must be between 1 and 1024")
        if not 1 <= max_concurrency <= 64:
            raise ContractError("invalid_concurrency", "max_concurrency must be between 1 and 64")
        self.batch_call = batch_call
        self.batch_size = batch_size
        self.max_concurrency = max_concurrency

    def stream(self, items: Sequence[T]) -> Iterator[tuple[int, tuple[R, ...]]]:
        batches = [(index, items[index : index + self.batch_size]) for index in range(0, len(items), self.batch_size)]
        with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
            futures = {pool.submit(self.batch_call, batch): start for start, batch in batches}
            for future in as_completed(futures):
                start = futures[future]
                output = tuple(future.result())
                expected = len(items[start : start + self.batch_size])
                if len(output) != expected:
                    raise ContractError("batch_cardinality_mismatch", "provider batch response changed cardinality")
                yield start, output

    def run(self, items: Sequence[T]) -> BatchResult[R]:
        chunks = sorted(self.stream(items), key=lambda item: item[0])
        flattened = tuple(value for _, chunk in chunks for value in chunk)
        return BatchResult(flattened, len(chunks), self.max_concurrency)


def analyze_repositories(
    repository_roots: Sequence[str],
    analyzer: Callable[[str], R],
    *,
    max_workers: int | None = None,
) -> tuple[R, ...]:
    """Avoid process startup for one repo; isolate multiple repos by process."""

    roots = tuple(require_string(root, "repository_root") for root in repository_roots)
    if not roots:
        return ()
    if len(roots) == 1:
        return (analyzer(roots[0]),)
    workers = min(max_workers or (os.cpu_count() or 1), len(roots), 16)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return tuple(pool.map(analyzer, roots))
