#!/usr/bin/env python3
"""Shared helpers for ELMOS Batch 46 runnable-smoke packs.

Stdlib only. Every ELMOS-generated or ELMOS-converted project must be able to
run these helpers from an empty checkout with no extra install step.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_PREFIX = "elmos.batch46"

# Data-source classes allowed by docs/batch46/MINIMAL_DATA_POLICY.md.
DATA_SOURCES = ("synthetic-from-contract", "desensitized-sample", "corpus-trim")

# Every artifact produced by Batch 46 is disposable by construction.
DATA_CLASSIFICATION = "ephemeral-disposable"

# Free runtime quota for a one-click smoke run, in seconds.
DEFAULT_FREE_QUOTA_SECONDS = 600
DEFAULT_GRACE_SECONDS = 30

RUNNER_ENTRIES = ("script", "compose", "make", "zero-dep")

# Seed primary keys are allocated from a reserved high range so that a smoke row
# cannot collide with a row the application creates while it is running, and so
# an operator can spot fixture identifiers at a glance.
SEED_KEY_BASE = 900_000_000

TRISTATE_NOT_RUN = "NOT_RUN"
TRISTATE_PASS = "PASS"
TRISTATE_FAIL = "FAIL"
TRISTATE_UNKNOWN = "UNKNOWN"

NON_SUCCESS = (TRISTATE_NOT_RUN, TRISTATE_FAIL, TRISTATE_UNKNOWN)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
    return path


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_text(path: Path, limit: int = 400_000) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")[:limit]
    except (OSError, UnicodeDecodeError):
        return ""


def iter_files(root: Path, patterns: Iterable[str], max_depth: int = 4) -> list[Path]:
    root = Path(root)
    skip = {
        ".git", "node_modules", "target", "build", "dist", "bin", "obj",
        "__pycache__", ".venv", "venv", ".gradle", ".idea", ".mypy_cache",
        ".pytest_cache", ".ruff_cache", "smoke",
    }
    found: list[Path] = []
    for pattern in patterns:
        for path in root.rglob(pattern):
            rel = path.relative_to(root)
            if any(part in skip for part in rel.parts[:-1]):
                continue
            if len(rel.parts) > max_depth:
                continue
            if path.is_file():
                found.append(path)
    return sorted(set(found))


def rel(root: Path, path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(path)


def free_port(preferred: int | None = None) -> int:
    """Return a bindable localhost port, preferring `preferred` when free."""
    if preferred:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", preferred))
                return preferred
            except OSError:
                pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout)
        return probe.connect_ex((host, port)) == 0


def wait_for_port(host: str, port: int, timeout: float = 60.0, interval: float = 0.4) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(host, port):
            return True
        time.sleep(interval)
    return False


def deterministic_value(seed: str, kind: str, index: int = 0) -> Any:
    """Deterministic, obviously-fake values.

    Smoke data must never look like production data. Every generated string is
    prefixed so an operator reading a database can tell at a glance that the row
    is disposable smoke fixture data.
    """
    digest = hashlib.sha256(f"{seed}|{kind}|{index}".encode("utf-8")).hexdigest()
    number = int(digest[:8], 16)
    kind = (kind or "string").lower()
    if kind in ("int", "integer", "bigint", "smallint", "serial", "bigserial"):
        return (number % 9000) + 1000
    if kind in ("decimal", "numeric", "money", "float", "double", "real"):
        return round(((number % 900000) + 100000) / 100.0, 2)
    if kind in ("bool", "boolean", "bit"):
        return bool(number % 2)
    if kind in ("uuid", "guid"):
        return f"{digest[0:8]}-{digest[8:12]}-4{digest[13:16]}-8{digest[17:20]}-{digest[20:32]}"
    if kind in ("date",):
        return "2000-01-01"
    if kind in ("time",):
        return "00:00:00"
    if kind in ("timestamp", "datetime", "timestamptz", "datetimeoffset"):
        # Portable literal: PostgreSQL, MySQL, SQL Server, SQLite and H2 all accept it.
        return "2000-01-01 00:00:00"
    if kind in ("email",):
        return f"smoke-{digest[:8]}@smoke.invalid"
    if kind in ("phone",):
        return "+10000000000"
    if kind in ("url",):
        return f"https://smoke.invalid/{digest[:8]}"
    if kind in ("json", "jsonb"):
        return "{}"
    return f"SMOKE-{digest[:10].upper()}"


DAEMON_UNREACHABLE_MARKERS = (
    "cannot connect to the docker daemon",
    "failed to connect to the docker api",
    "is the docker daemon running",
    "docker.sock: connect:",
    "permission denied while trying to connect to the docker daemon",
    "error during connect",
)


def daemon_unreachable(stderr: str) -> bool:
    """True when docker itself is unavailable, as opposed to the run failing."""
    low = (stderr or "").lower()
    return any(marker in low for marker in DAEMON_UNREACHABLE_MARKERS)


SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|private[_-]?key|credential|access[_-]?key)"
)


def is_secret_name(name: str) -> bool:
    return bool(SECRET_PATTERN.search(name or ""))


def smoke_secret(seed: str, name: str) -> str:
    """A throwaway credential for local smoke runs only."""
    digest = hashlib.sha256(f"{seed}|secret|{name}".encode("utf-8")).hexdigest()
    return f"smoke-local-only-{digest[:16]}"


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def fail(message: str, code: int = 2) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def smoke_dir(project_root: Path) -> Path:
    return Path(project_root) / "smoke"


def load_pack(project_root: Path, name: str) -> Any:
    path = smoke_dir(project_root) / name
    if not path.is_file():
        fail(f"missing {path}; run scripts/batch46/scaffold_smoke_pack.py first")
    return read_json(path)
