"""Industrial-grade PostgreSQL database migration manager for the Elmos Proof Harness.

Enforces:
1. Deterministic version ordering (V<version>__<description>.sql).
2. Content SHA-256 checksum hashing and immutable drift detection.
3. Concurrent-safe distributed advisory lock (pg_advisory_lock).
4. Transactional execution per migration script with detailed audit trails in harness_schema_history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import importlib
from pathlib import Path
import re
import time
from typing import Any


_MIGRATION_PATTERN = re.compile(r"^V([0-9]+(?:_[0-9]+)*)__(.*)\.sql$")
_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


class MigrationError(RuntimeError):
    """Base error for migration execution failures."""


class MigrationDriftError(MigrationError):
    """Raised when an already applied migration has a modified checksum or content."""


@dataclass(frozen=True)
class MigrationScript:
    version: str
    description: str
    script_name: str
    file_path: Path
    checksum: str
    version_key: tuple[int, ...]


@dataclass(frozen=True)
class AppliedMigration:
    installed_rank: int
    version: str
    description: str
    script: str
    checksum: str
    installed_by: str
    installed_on: datetime
    execution_time_ms: int
    success: bool


def _parse_version_key(v_str: str) -> tuple[int, ...]:
    parts = v_str.split("_")
    return tuple(int(p) for p in parts if p.isdigit())


class MigrationManager:
    """Manages schema history, checksum validation, and automated forward migrations."""

    def __init__(
        self,
        dsn: str,
        migrations_dir: Path | str | None = None,
        installed_by: str = "elmos-migration-manager",
        schema: str | None = None,
    ) -> None:
        self.dsn = dsn
        self.migrations_dir = Path(migrations_dir) if migrations_dir is not None else _DEFAULT_MIGRATIONS_DIR
        self.installed_by = installed_by
        self.schema = schema

    def _get_driver(self) -> Any:
        try:
            return importlib.import_module("psycopg")
        except ImportError as exc:
            raise MigrationError("psycopg driver is required for database migrations; install 'psycopg'") from exc

    def _setup_connection(self, conn: Any) -> None:
        """Configures search_path if an isolated schema was provided."""
        if self.schema:
            clean_schema = "".join(c for c in self.schema if c.isalnum() or c == "_")
            if clean_schema:
                with conn.cursor() as cur:
                    cur.execute(f"SET search_path TO {clean_schema}, public")

    def discover_migrations(self) -> list[MigrationScript]:
        """Discovers and deterministically orders all V*.sql scripts."""
        if not self.migrations_dir.exists():
            return []

        discovered: list[MigrationScript] = []
        for file in self.migrations_dir.glob("V*.sql"):
            if not file.is_file():
                continue
            match = _MIGRATION_PATTERN.match(file.name)
            if not match:
                continue
            v_str, desc_str = match.groups()
            content = file.read_bytes()
            csum = hashlib.sha256(content).hexdigest()
            v_key = _parse_version_key(v_str)
            readable_desc = desc_str.replace("_", " ")
            discovered.append(
                MigrationScript(
                    version=v_str,
                    description=readable_desc,
                    script_name=file.name,
                    file_path=file,
                    checksum=csum,
                    version_key=v_key,
                )
            )

        discovered.sort(key=lambda m: m.version_key)
        return discovered

    def ensure_history_table(self, conn: Any) -> None:
        """Initializes the schema history table if not present."""
        ddl = """
        CREATE TABLE IF NOT EXISTS harness_schema_history (
            installed_rank SERIAL PRIMARY KEY,
            version VARCHAR(50) UNIQUE NOT NULL,
            description VARCHAR(200) NOT NULL,
            type VARCHAR(20) NOT NULL,
            script VARCHAR(1000) NOT NULL,
            checksum VARCHAR(64) NOT NULL,
            installed_by VARCHAR(100) NOT NULL,
            installed_on TIMESTAMPTZ DEFAULT clock_timestamp() NOT NULL,
            execution_time_ms INTEGER NOT NULL,
            success BOOLEAN NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_harness_schema_history_success ON harness_schema_history(success);
        """
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()

    def get_applied_migrations(self, conn: Any) -> dict[str, AppliedMigration]:
        """Loads all applied migrations keyed by version."""
        self.ensure_history_table(conn)
        applied: dict[str, AppliedMigration] = {}
        with conn.cursor() as cur:
            cur.execute("""
                SELECT installed_rank, version, description, script, checksum,
                       installed_by, installed_on, execution_time_ms, success
                FROM harness_schema_history
                ORDER BY installed_rank ASC
            """)
            for row in cur.fetchall():
                rec = AppliedMigration(
                    installed_rank=row[0],
                    version=row[1],
                    description=row[2],
                    script=row[3],
                    checksum=row[4],
                    installed_by=row[5],
                    installed_on=row[6],
                    execution_time_ms=row[7],
                    success=row[8],
                )
                applied[rec.version] = rec
        return applied

    def check_status(self) -> dict[str, Any]:
        """Inspects status of all discovered migrations against current database state."""
        driver = self._get_driver()
        with driver.connect(self.dsn) as conn:
            self._setup_connection(conn)
            applied = self.get_applied_migrations(conn)
            discovered = self.discover_migrations()

            status_list: list[dict[str, Any]] = []
            drift_detected = False

            for m in discovered:
                is_applied = m.version in applied
                app_rec = applied.get(m.version)
                checksum_match = True
                if app_rec is not None:
                    if app_rec.checksum != m.checksum:
                        checksum_match = False
                        drift_detected = True

                status_list.append({
                    "version": m.version,
                    "description": m.description,
                    "script": m.script_name,
                    "checksum": m.checksum,
                    "applied": is_applied,
                    "checksum_match": checksum_match,
                    "installed_on": app_rec.installed_on.isoformat() if app_rec else None,
                })

            return {
                "total_discovered": len(discovered),
                "total_applied": len(applied),
                "pending_count": len(discovered) - len(applied),
                "drift_detected": drift_detected,
                "migrations": status_list,
            }

    def apply_pending(self) -> list[dict[str, Any]]:
        """Applies pending migrations under a distributed lock, validating checksum integrity."""
        driver = self._get_driver()
        applied_results: list[dict[str, Any]] = []

        with driver.connect(self.dsn) as conn:
            self._setup_connection(conn)
            # Acquire Postgres advisory lock for safe distributed execution
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_lock(hashtext('elmos_proof_harness_migration_lock'))")
            conn.commit()

            try:
                self.ensure_history_table(conn)
                already_applied = self.get_applied_migrations(conn)
                discovered = self.discover_migrations()

                # 1. Check for drift in previously applied migrations
                for m in discovered:
                    if m.version in already_applied:
                        prev = already_applied[m.version]
                        if prev.checksum != m.checksum:
                            raise MigrationDriftError(
                                f"Migration {m.version} ({m.script_name}) checksum mismatch: "
                                f"database has {prev.checksum}, disk has {m.checksum}. "
                                "Modifying already applied migrations violates execution integrity!"
                            )

                # 2. Apply pending migrations sequentially
                for m in discovered:
                    if m.version in already_applied:
                        continue

                    sql_text = m.file_path.read_text(encoding="utf-8")
                    start_time = time.monotonic()

                    with conn.cursor() as cur:
                        try:
                            # Execute the migration script
                            cur.execute(sql_text)
                            elapsed_ms = int((time.monotonic() - start_time) * 1000)

                            # Record success in history
                            cur.execute(
                                """
                                INSERT INTO harness_schema_history
                                (version, description, type, script, checksum, installed_by, execution_time_ms, success)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                """,
                                (
                                    m.version,
                                    m.description,
                                    "SQL",
                                    m.script_name,
                                    m.checksum,
                                    self.installed_by,
                                    elapsed_ms,
                                    True,
                                ),
                            )
                            conn.commit()

                            applied_results.append({
                                "version": m.version,
                                "script": m.script_name,
                                "status": "SUCCESS",
                                "execution_time_ms": elapsed_ms,
                            })
                        except Exception as exc:
                            conn.rollback()
                            elapsed_ms = int((time.monotonic() - start_time) * 1000)
                            # In a fresh sub-transaction record failure if possible
                            with conn.cursor() as fail_cur:
                                fail_cur.execute(
                                    """
                                    INSERT INTO harness_schema_history
                                    (version, description, type, script, checksum, installed_by, execution_time_ms, success)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                    """,
                                    (
                                        m.version,
                                        m.description,
                                        "SQL",
                                        m.script_name,
                                        m.checksum,
                                        self.installed_by,
                                        elapsed_ms,
                                        False,
                                    ),
                                )
                                conn.commit()
                            raise MigrationError(f"Migration {m.version} failed: {exc}") from exc

            finally:
                # Always release advisory lock
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(hashtext('elmos_proof_harness_migration_lock'))")
                conn.commit()

        return applied_results
