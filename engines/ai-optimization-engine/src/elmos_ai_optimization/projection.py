"""Multi-version projection catalog with atomic CAS transitions."""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from .contracts import ContractError, StaleVersionError


class ProjectionCatalog:
    """Catalog tracking projection lifecycle and atomic CAS head updates."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.db:
            self.db.executescript(
                """
                CREATE TABLE IF NOT EXISTS versions (
                    tenant TEXT,
                    repository TEXT,
                    generation TEXT,
                    snapshot TEXT,
                    state TEXT,
                    expected INT,
                    actual INT,
                    PRIMARY KEY(tenant, repository, generation)
                );
                CREATE TABLE IF NOT EXISTS heads (
                    tenant TEXT,
                    repository TEXT,
                    generation TEXT,
                    PRIMARY KEY(tenant, repository)
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    event_id TEXT PRIMARY KEY,
                    tenant TEXT,
                    repository TEXT,
                    generation TEXT,
                    event_type TEXT,
                    payload TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def begin(self, tenant: str, repository: str, generation: str, snapshot: str, expected_count: int) -> None:
        if not all([tenant, repository, generation, snapshot]) or expected_count < 0:
            raise ContractError("Invalid projection manifest parameters")
        with self.db:
            try:
                self.db.execute(
                    "INSERT INTO versions VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (tenant, repository, generation, snapshot, "BUILDING", expected_count, 0),
                )
            except sqlite3.IntegrityError as exc:
                raise StaleVersionError(f"Version already exists: {tenant}/{repository}/{generation}") from exc

    def validate(self, tenant: str, repository: str, generation: str, actual_count: int) -> None:
        with self.db:
            row = self.db.execute(
                "SELECT state, expected FROM versions WHERE tenant = ? AND repository = ? AND generation = ?",
                (tenant, repository, generation),
            ).fetchone()
            if not row:
                raise StaleVersionError(f"Version not found: {tenant}/{repository}/{generation}")
            state, expected = row[0], row[1]
            if state != "BUILDING":
                raise StaleVersionError(f"Version state is not BUILDING: {state}")
            if actual_count != expected:
                raise StaleVersionError(f"Chunk count mismatch: expected {expected}, got {actual_count}")

            self.db.execute(
                "UPDATE versions SET state = 'VALIDATED', actual = ? "
                "WHERE tenant = ? AND repository = ? AND generation = ?",
                (actual_count, tenant, repository, generation),
            )

    def get_head(self, tenant: str, repository: str) -> str | None:
        row = self.db.execute(
            "SELECT generation FROM heads WHERE tenant = ? AND repository = ?",
            (tenant, repository),
        ).fetchone()
        return row[0] if row else None

    def publish(self, tenant: str, repository: str, generation: str, expected_head: str | None) -> None:
        """Atomic Compare-And-Swap (CAS) head promotion."""
        try:
            self.db.execute("BEGIN IMMEDIATE")
            current_head = self.get_head(tenant, repository)
            if current_head != expected_head:
                raise StaleVersionError(
                    f"Head CAS mismatch: expected {expected_head}, current {current_head}"
                )

            row = self.db.execute(
                "SELECT state FROM versions WHERE tenant = ? AND repository = ? AND generation = ?",
                (tenant, repository, generation),
            ).fetchone()
            if not row:
                raise StaleVersionError("Version does not exist")
            if row[0] != "VALIDATED":
                raise StaleVersionError(f"Cannot publish version in state: {row[0]}")

            self.db.execute(
                "INSERT INTO heads VALUES(?, ?, ?) ON CONFLICT(tenant, repository) "
                "DO UPDATE SET generation = excluded.generation",
                (tenant, repository, generation),
            )
            self.db.execute(
                "UPDATE versions SET state = 'PUBLISHED' "
                "WHERE tenant = ? AND repository = ? AND generation = ?",
                (tenant, repository, generation),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def close(self) -> None:
        self.db.close()
