"""PostgreSQL Adaptive Lifecycle Management and Reversible Schema Migrations.

Supports dynamic PG version autodetection (PG15-18), ephemeral cluster creation,
forward migration, and full reversible Undo (U-script) rollbacks.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

logger = logging.getLogger("elmos_proof_harness.postgres_lifecycle")


@dataclass(frozen=True)
class PostgresVersionInfo:
    major: int
    minor: int
    raw_string: str
    bin_path: Path


class PostgresBinaryDiscovery:
    """Locates postgres toolchain across Homebrew, Linux distributions, and system paths."""

    SEARCH_PATHS = (
        Path("/opt/homebrew/opt/postgresql@17/bin"),
        Path("/opt/homebrew/opt/postgresql@16/bin"),
        Path("/opt/homebrew/bin"),
        Path("/usr/lib/postgresql/17/bin"),
        Path("/usr/lib/postgresql/16/bin"),
        Path("/usr/lib/postgresql/15/bin"),
        Path("/usr/local/bin"),
    )

    @classmethod
    def discover(cls) -> PostgresVersionInfo | None:
        custom = os.environ.get("ELMOS_POSTGRES_BIN")
        candidates = [Path(custom)] if custom else list(cls.SEARCH_PATHS)

        # Also add which initdb
        which_initdb = shutil.which("initdb")
        if which_initdb:
            candidates.insert(0, Path(which_initdb).resolve().parent)

        for path in candidates:
            initdb = path / "initdb"
            postgres = path / "postgres"
            if initdb.is_file() and postgres.is_file() and os.access(initdb, os.X_OK):
                try:
                    res = subprocess.run(
                        [str(postgres), "--version"],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    raw = res.stdout.strip()
                    # e.g., postgres (PostgreSQL) 16.8 (Homebrew) or 17.5
                    m = re.search(r"(\d+)\.(\d+)", raw)
                    if m:
                        return PostgresVersionInfo(
                            major=int(m.group(1)),
                            minor=int(m.group(2)),
                            raw_string=raw,
                            bin_path=path,
                        )
                except Exception as exc:
                    logger.debug(f"failed checking postgres binary at {path}: {exc}")
                    continue
        return None


class EphemeralPostgresCluster:
    """Disposable, non-production PostgreSQL instance with guaranteed process cleanup."""

    def __init__(self, version_info: PostgresVersionInfo | None = None) -> None:
        self.version_info = version_info or PostgresBinaryDiscovery.discover()
        if not self.version_info:
            raise RuntimeError("no valid PostgreSQL binary found on host system")

        self.root = Path(tempfile.mkdtemp(prefix="elmos-pg-ephemeral-"))
        self.data_dir = self.root / "data"
        self.port = self._find_free_port()
        self.process: subprocess.Popen[str] | None = None

    @staticmethod
    def _find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    @property
    def dsn(self) -> str:
        return f"postgresql://127.0.0.1:{self.port}/postgres?sslmode=disable"

    def init_and_start(self, timeout_seconds: float = 15.0) -> None:
        bin_dir = self.version_info.bin_path
        initdb = bin_dir / "initdb"
        postgres = bin_dir / "postgres"

        # 1. Initialize cluster
        subprocess.run(
            [str(initdb), "-D", str(self.data_dir), "-U", "postgres", "--no-instructions", "-E", "UTF8"],
            capture_output=True,
            check=True,
        )

        # 2. Start postgres daemon
        cmd = [
            str(postgres),
            "-D", str(self.data_dir),
            "-p", str(self.port),
            "-h", "127.0.0.1",
            "-F",  # fsync off for throwaway integration speed
        ]
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # 3. Wait for readiness
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    logger.info(f"ephemeral postgres {self.version_info.major} started on port {self.port}")
                    return
            except (ConnectionRefusedError, socket.timeout):
                time.sleep(0.1)

        self.stop()
        raise TimeoutError(f"ephemeral postgres failed to start within {timeout_seconds}s")

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self) -> EphemeralPostgresCluster:
        self.init_and_start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()


class ReversibleMigrationEngine:
    """Manages forward (V) and rollback (U) SQL migrations against an active database."""

    def __init__(self, execute_sql_func: Any) -> None:
        """execute_sql_func takes (sql: str) -> None"""
        self.execute_sql = execute_sql_func
        self._applied: list[str] = []

    def apply_forward(self, version_id: str, script_sql: str) -> None:
        logger.info(f"applying forward migration: {version_id}")
        self.execute_sql(script_sql)
        self._applied.append(version_id)

    def apply_undo(self, version_id: str, undo_sql: str) -> None:
        if version_id not in self._applied:
            raise ValueError(f"cannot undo {version_id}: not currently applied")
        logger.info(f"applying reverse rollback migration: {version_id}")
        self.execute_sql(undo_sql)
        self._applied.remove(version_id)

    @property
    def applied_versions(self) -> Sequence[str]:
        return tuple(self._applied)
