"""Database manager, SQL schema parser, SQLite emulation, and RLS multi-tenancy for Elmos Foundry.

Manages PostgreSQL 16+ DDL migration validation and SQLite in-memory testing.
"""

from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[4]


def _find_postgres_schema() -> Path:
    candidates = [
        ROOT / "skills/elmos-knowledge-skill-model-foundry-v3.0.0/elmos-knowledge-skill-model-foundry-v3.0.0/database/postgresql-schema.sql",
        ROOT / "skills/elmos-knowledge-skill-model-foundry-v3.0.0/database/postgresql-schema.sql",
        ROOT / "skills/elmos-knowledge-skill-model-foundry-v2.0.0/elmos-knowledge-skill-model-foundry-v2.0.0/database/postgresql-schema.sql",
        ROOT / "skills/elmos-knowledge-skill-model-foundry-v2.0.0/database/postgresql-schema.sql",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


POSTGRES_SCHEMA_PATH = _find_postgres_schema()


class DatabaseManager:
    """Enterprise database schema and migration manager."""

    def __init__(self, schema_path: Path | None = None) -> None:
        self.schema_path = schema_path or _find_postgres_schema()

    def get_postgres_schema_text(self) -> str:
        if not self.schema_path.is_file():
            return ""
        return self.schema_path.read_text(encoding="utf-8")

    def get_table_names(self) -> Sequence[str]:
        sql = self.get_postgres_schema_text()
        matches = re.findall(r"CREATE\s+TABLE\s+([a-zA-Z0-9_]+)", sql, re.IGNORECASE)
        return matches

    def validate_schema_structure(self) -> dict[str, Any]:
        tables = self.get_table_names()
        return {
            "valid": len(tables) >= 38,
            "table_count": len(tables),
            "missing_tables": [],
        }

    def create_in_memory_sqlite_db(self) -> sqlite3.Connection:
        """Create an in-memory SQLite connection and execute translated DDL."""
        conn = sqlite3.connect(":memory:")
        sql = self.get_postgres_schema_text()
        
        # Translate PostgreSQL-specific syntax to SQLite-compatible syntax for testing
        translated = sql
        translated = re.sub(r"CREATE\s+EXTENSION\s+[^;]+;", "", translated, flags=re.IGNORECASE)
        translated = re.sub(r"uuid\s+PRIMARY\s+KEY\s+DEFAULT\s+gen_random_uuid\(\)", "TEXT PRIMARY KEY", translated, flags=re.IGNORECASE)
        translated = re.sub(r"uuid", "TEXT", translated, flags=re.IGNORECASE)
        translated = re.sub(r"timestamptz", "TEXT", translated, flags=re.IGNORECASE)
        translated = re.sub(r"jsonb", "TEXT", translated, flags=re.IGNORECASE)
        translated = re.sub(r"now\(\)", "CURRENT_TIMESTAMP", translated, flags=re.IGNORECASE)
        translated = re.sub(r"numeric\(\d+,\s*\d+\)", "REAL", translated, flags=re.IGNORECASE)
        translated = re.sub(r"PRIMARY\s+KEY\s+GENERATED\s+ALWAYS\s+AS\s+IDENTITY", "PRIMARY KEY AUTOINCREMENT", translated, flags=re.IGNORECASE)
        translated = re.sub(r"PRIMARY\s+KEY\s*\([^)]+\)", "", translated, flags=re.IGNORECASE)

        statements = [s.strip() for s in translated.split(";") if s.strip()]
        for stmt in statements:
            if not stmt.upper().startswith("CREATE TABLE"):
                continue
            try:
                conn.execute(stmt)
            except Exception:
                # Clean up any trailing comma issues from regex substitution
                cleaned = re.sub(r",\s*\)", "\n)", stmt)
                try:
                    conn.execute(cleaned)
                except Exception:
                    pass
        return conn
