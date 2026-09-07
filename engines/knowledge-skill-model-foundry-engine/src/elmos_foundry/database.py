"""Bounded static inspection of untrusted SQL; repository state uses store.py."""

from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import Any, Iterator, Sequence

from .canonical import digest_bytes, require_identifier
from .kernel import ExecutionKernel
from .store import FoundryStore


class DatabaseBoundaryError(RuntimeError):
    pass


class SchemaInspectionError(RuntimeError):
    pass


ROOT = Path(__file__).resolve().parents[4]
_MIRROR = ROOT / "skills/elmos-knowledge-skill-model-foundry-v3.0.0"
_CANDIDATES = (
    _MIRROR / "elmos-knowledge-skill-model-foundry-v3.0.0/database/postgresql-schema.sql",
    _MIRROR / "database/postgresql-schema.sql",
)
_MAX_BYTES = 8 * 1024 * 1024
_REQUIRED = {"knowledge_source", "skill", "dataset_item", "model_artifact", "audit_event"}


def _find_postgres_schema() -> Path:
    return next(
        (item for item in _CANDIDATES if item.is_file() and not item.is_symlink()), _CANDIDATES[0]
    )


POSTGRES_SCHEMA_PATH = _find_postgres_schema()


def _read(path: Path, root_path: Path) -> bytes:
    try:
        root = root_path.resolve(strict=True)
        resolved = path.expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise SchemaInspectionError("PostgreSQL source schema is unavailable") from exc
    if path.is_symlink() or not resolved.is_relative_to(root):
        raise SchemaInspectionError("schema path is symlinked or escapes allowed root")
    cursor = root
    for part in resolved.relative_to(root).parts:
        cursor /= part
        if cursor.is_symlink():
            raise SchemaInspectionError("schema path contains a symbolic link")
    descriptor = os.open(
        resolved, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_BYTES:
            raise SchemaInspectionError("schema is not a bounded regular file")
        chunks, remaining = [], before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise SchemaInspectionError("schema was truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise SchemaInspectionError("schema changed during inspection")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _tokens(sql: str) -> Iterator[str]:
    index, count, length = 0, 0, len(sql)
    while index < length:
        char = sql[index]
        if char.isspace():
            index += 1
            continue
        if sql.startswith("--", index):
            end = sql.find("\n", index + 2)
            index = length if end < 0 else end + 1
            continue
        if sql.startswith("/*", index):
            depth, index = 1, index + 2
            while index < length and depth:
                if sql.startswith("/*", index):
                    depth += 1
                    index += 2
                elif sql.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise SchemaInspectionError("unterminated block comment")
            continue
        if char == "'":
            index += 1
            while index < length:
                if sql[index] == "'":
                    if index + 1 < length and sql[index + 1] == "'":
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            else:
                raise SchemaInspectionError("unterminated string literal")
            continue
        if char == "$":
            end = sql.find("$", index + 1, min(length, index + 130))
            if end >= 0:
                tag = sql[index : end + 1]
                if all(item.isalnum() or item in "_$" for item in tag):
                    close = sql.find(tag, end + 1)
                    if close < 0:
                        raise SchemaInspectionError("unterminated dollar quote")
                    index = close + len(tag)
                    continue
        if char == '"':
            index += 1
            value = []
            while index < length:
                if sql[index] == '"':
                    if index + 1 < length and sql[index + 1] == '"':
                        value.append('"')
                        index += 2
                        continue
                    index += 1
                    break
                value.append(sql[index])
                index += 1
            else:
                raise SchemaInspectionError("unterminated quoted identifier")
            token = "".join(value)
        elif char.isalpha() or char == "_":
            end = index + 1
            while end < length and (sql[end].isalnum() or sql[end] in "_$"):
                end += 1
            token, index = sql[index:end], end
        elif char in ".;(),":
            token, index = char, index + 1
        else:
            index += 1
            continue
        count += 1
        if count > 1_000_000:
            raise SchemaInspectionError("SQL token limit exceeded")
        yield token


def _tables(sql: str) -> tuple[str, ...]:
    tokens, names, index = tuple(_tokens(sql)), [], 0
    while index + 2 < len(tokens):
        if tokens[index].upper() != "CREATE" or tokens[index + 1].upper() != "TABLE":
            index += 1
            continue
        cursor = index + 2
        if tuple(item.upper() for item in tokens[cursor : cursor + 3]) == ("IF", "NOT", "EXISTS"):
            cursor += 3
        if cursor >= len(tokens) or tokens[cursor] in ".;(),":
            raise SchemaInspectionError("CREATE TABLE lacks identifier")
        name = (
            tokens[cursor + 2]
            if cursor + 2 < len(tokens) and tokens[cursor + 1] == "."
            else tokens[cursor]
        )
        names.append(require_identifier(name, "table_name"))
        index = cursor + 1
    folded: set[str] = set()
    for name in names:
        if name.casefold() in folded:
            raise SchemaInspectionError(f"duplicate table identity: {name}")
        folded.add(name.casefold())
    return tuple(names)


class DatabaseManager:
    def __init__(
        self, schema_path: Path | None = None, *, allowed_root: Path | None = None
    ) -> None:
        self.schema_path = schema_path or _find_postgres_schema()
        self.allowed_root = allowed_root or (
            _MIRROR if schema_path is None else self.schema_path.parent
        )

    def get_postgres_schema_bytes(self) -> bytes:
        return _read(self.schema_path, self.allowed_root)

    def get_postgres_schema_text(self) -> str:
        try:
            return self.get_postgres_schema_bytes().decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise SchemaInspectionError("source schema is not UTF-8") from exc

    def get_table_names(self) -> Sequence[str]:
        return _tables(self.get_postgres_schema_text())

    def validate_schema_structure(self) -> dict[str, Any]:
        data = self.get_postgres_schema_bytes()
        try:
            tables = _tables(data.decode("utf-8", "strict"))
        except UnicodeDecodeError as exc:
            raise SchemaInspectionError("source schema is not UTF-8") from exc
        missing = tuple(sorted(_REQUIRED - {name.casefold() for name in tables}))
        valid = len(tables) >= 38 and not missing
        return {
            "valid": valid,
            "structurally_valid": valid,
            "table_count": len(tables),
            "table_names": tables,
            "missing_tables": missing,
            "source_digest": digest_bytes(data),
            "source_status": "UNTRUSTED_DECLARATIVE_INPUT",
            "execution_status": "NOT_RUN",
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }

    def create_in_memory_sqlite_db(self) -> None:
        raise DatabaseBoundaryError(
            "regex-translated execution of untrusted PostgreSQL SQL is forbidden"
        )

    @staticmethod
    def open_local_store(path: str | os.PathLike[str], kernel: ExecutionKernel) -> FoundryStore:
        if not isinstance(kernel, ExecutionKernel):
            raise TypeError("kernel must be ExecutionKernel")
        return FoundryStore(path, context_verifier=kernel.require_context)


__all__ = [
    "DatabaseBoundaryError",
    "DatabaseManager",
    "POSTGRES_SCHEMA_PATH",
    "SchemaInspectionError",
]
