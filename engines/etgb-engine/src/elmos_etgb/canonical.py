"""Deterministic serialization and content-addressing primitives."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented deterministically."""


def _default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"__decimal__": format(value, "f")}
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, Path):
        return {"__path__": value.as_posix()}
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    raise CanonicalizationError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    """Return UTF-8 canonical JSON with no NaN/Infinity or whitespace."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            default=_default,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanonicalizationError(str(exc)) from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest_tree(root: Path, *, exclude: Iterable[str] = ()) -> str:
    """Digest relative names and bytes in stable order.

    ``exclude`` contains path parts, not shell globs.  Generated caches should
    be excluded explicitly by callers; silently ignoring them would make a
    release digest non-reproducible.
    """

    excluded = frozenset(exclude)
    entries: list[tuple[str, Path]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in excluded for part in relative.parts):
            continue
        entries.append((relative.as_posix(), path))
    digest = hashlib.sha256()
    for name, path in sorted(entries):
        data_digest = sha256_file(path)
        digest.update(canonical_json({"path": name, "sha256": data_digest}))
        digest.update(b"\n")
    return digest.hexdigest()
