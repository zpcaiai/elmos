from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Iterable

from .cas import LocalCAS
from .canonical import canonical_json_bytes


class TreeConflict(ValueError):
    pass


class AtomicPublisher:
    def __init__(self, publish_root: Path, cas: LocalCAS):
        self.publish_root = publish_root
        self.cas = cas
        self.publish_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def tree_digest(entries: list[dict]) -> str:
        normalized = sorted(entries, key=lambda item: item["logical_path"])
        return "sha256:" + hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()

    def validate_entries(self, entries: Iterable[dict]) -> list[dict]:
        normalized = []
        seen_exact: set[str] = set()
        seen_casefold: set[str] = set()
        for item in entries:
            path = item["logical_path"].replace("\\", "/")
            parts = Path(path).parts
            if Path(path).is_absolute() or any(part in ("", ".", "..") for part in parts):
                raise TreeConflict(f"unsafe tree path: {path}")
            if path in seen_exact:
                raise TreeConflict(f"duplicate path: {path}")
            folded = path.casefold()
            if folded in seen_casefold:
                raise TreeConflict(f"case-colliding path: {path}")
            seen_exact.add(path)
            seen_casefold.add(folded)
            self.cas.verify(item["artifact_digest"])
            normalized.append({**item, "logical_path": path})
        return sorted(normalized, key=lambda item: item["logical_path"])

    def build_candidate(self, entries: list[dict]) -> tuple[str, Path]:
        entries = self.validate_entries(entries)
        digest = self.tree_digest(entries)
        short = digest.split(":", 1)[1]
        candidate = self.publish_root / short
        if candidate.exists():
            return digest, candidate

        temporary = self.publish_root / f".{short}.elmos-tree-{os.getpid()}"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(parents=True)

        try:
            for item in entries:
                destination = temporary / item["logical_path"]
                self.cas.materialize(item["artifact_digest"], destination)
                try:
                    os.chmod(destination, int(item.get("mode", 0o644)))
                except OSError:
                    pass
            manifest = {
                "root_digest": digest,
                "entries": entries,
            }
            manifest_path = temporary / ".elmos-tree-manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with manifest_path.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, candidate)
            self._fsync_directory(candidate.parent)
            return digest, candidate
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    def publish(self, tree_digest: str, candidate: Path) -> Path:
        expected = self.publish_root / tree_digest.split(":", 1)[1]
        if candidate != expected or not candidate.exists():
            raise ValueError("candidate does not match tree digest")
        pointer = self.publish_root / "current"
        temporary_pointer = self.publish_root / f".current-{os.getpid()}"
        temporary_pointer.unlink(missing_ok=True)
        try:
            temporary_pointer.symlink_to(candidate.name, target_is_directory=True)
            os.replace(temporary_pointer, pointer)
        except (OSError, NotImplementedError):
            # Portable fallback records an atomically replaced pointer file.
            temporary_pointer.write_text(candidate.name + "\n", encoding="utf-8")
            with temporary_pointer.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary_pointer, pointer)
        self._fsync_directory(self.publish_root)
        return pointer

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        try:
            fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
