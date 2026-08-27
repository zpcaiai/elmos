"""Bounded repository indexing and provenance-aware context packing."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

LANGUAGES = {".py": "python", ".java": "java", ".kt": "kotlin", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript", ".go": "go", ".rs": "rust", ".cs": "csharp", ".sql": "sql"}
DEFAULT_IGNORES = {".git", ".venv", "node_modules", "target", "dist", "build", "__pycache__"}


@dataclass(frozen=True)
class IndexedFile:
    path: str
    language: str | None
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ContextPack:
    files: tuple[IndexedFile, ...]
    digest: str
    excluded: tuple[str, ...]


class RepositoryIndexer:
    def __init__(self, root: str | Path, *, max_files: int = 100_000, max_bytes: int = 512 * 1024 * 1024) -> None:
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("repository root must be a directory")
        self.max_files = max_files
        self.max_bytes = max_bytes

    def build(self, *, ignores: Iterable[str] = DEFAULT_IGNORES) -> tuple[IndexedFile, ...]:
        ignored = set(ignores)
        result: list[IndexedFile] = []
        total = 0
        for directory, dirnames, filenames in os.walk(self.root, followlinks=False):
            dirnames[:] = [name for name in dirnames if name not in ignored]
            for name in sorted(filenames):
                path = Path(directory) / name
                if path.is_symlink() or len(result) >= self.max_files:
                    continue
                size = path.stat().st_size
                if total + size > self.max_bytes:
                    raise ValueError("repository index exceeds configured size")
                with path.open("rb") as handle:
                    sha = hashlib.sha256(handle.read()).hexdigest()
                result.append(IndexedFile(path.relative_to(self.root).as_posix(), LANGUAGES.get(path.suffix.lower()), size, "sha256:" + sha))
                total += size
        return tuple(result)

    @staticmethod
    def pack(files: Iterable[IndexedFile], *, max_files: int = 256) -> ContextPack:
        all_files = tuple(files)
        selected = tuple(sorted(all_files, key=lambda item: (item.language or "", item.path))[:max_files])
        excluded = tuple(sorted(item.path for item in all_files if item not in selected))
        payload = [{"path": item.path, "language": item.language, "size_bytes": item.size_bytes, "sha256": item.sha256} for item in selected]
        digest = "sha256:" + hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()
        return ContextPack(selected, digest, excluded)
