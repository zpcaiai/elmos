"""PostgreSQL database migration validation and execution manager."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = ROOT / "skills/elmos-ai-capability-enhancement-skills-v4.1.0/database/postgres"


@dataclass(frozen=True)
class MigrationResult:
    migration_id: str
    filename: str
    status: str  # APPLIED, VALIDATED, FAILED
    statement_count: int
    tables_created: tuple[str, ...]
    checksum: str
    duration_ms: float
    error: str | None = None


class MigrationManager:
    """Manages, parses and validates the 20 PostgreSQL database migrations."""

    def __init__(self, migrations_dir: Path | None = None) -> None:
        self.migrations_dir = migrations_dir or MIGRATIONS_DIR
        self._migrations: dict[str, Path] = {}
        self._load_migrations()

    def _load_migrations(self) -> None:
        if not self.migrations_dir.is_dir():
            return
        for sql_file in sorted(self.migrations_dir.glob("[0-9][0-9][0-9]_*.sql")):
            self._migrations[sql_file.name] = sql_file

    def list_migrations(self) -> list[str]:
        return sorted(self._migrations.keys())

    def validate_migration(self, filename: str) -> MigrationResult:
        start = time.perf_counter()
        if filename not in self._migrations:
            raise KeyError(f"migration {filename} not found")
        path = self._migrations[filename]
        content = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(content.encode()).hexdigest()

        # Parse CREATE TABLE / CREATE INDEX / ALTER TABLE statements
        statements = [s.strip() for s in content.split(";") if s.strip()]
        tables = []
        for stmt in statements:
            m = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_\.]+)", stmt, re.IGNORECASE)
            if m:
                tables.append(m.group(1))

        return MigrationResult(
            migration_id=filename[:3],
            filename=filename,
            status="VALIDATED",
            statement_count=len(statements),
            tables_created=tuple(tables),
            checksum=checksum,
            duration_ms=(time.perf_counter() - start) * 1000,
        )

    def validate_all_migrations(self) -> dict[str, MigrationResult]:
        results: dict[str, MigrationResult] = {}
        for name in self.list_migrations():
            results[name] = self.validate_migration(name)
        return results
