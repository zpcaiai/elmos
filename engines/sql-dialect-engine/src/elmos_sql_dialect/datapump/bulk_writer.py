"""High-performance bulk database writer supporting COPY and batched parameter arrays."""

from __future__ import annotations

import logging
from typing import Any

try:
    from psycopg2.extras import execute_values
except ImportError:
    execute_values = None  # type: ignore[assignment]

from .chunk_reader import DataChunk

logger = logging.getLogger(__name__)


class BulkWriter:
    """Writes row chunks into target database with transactional batching."""

    def __init__(
        self,
        connection: Any,
        table_name: str,
        schema_name: str = "public",
        on_conflict: str = "ERROR",  # "ERROR", "NOTHING", or "UPDATE"
        conflict_keys: list[str] | None = None,
    ) -> None:
        self.conn = connection
        self.table_name = table_name
        self.schema_name = schema_name
        self.on_conflict = on_conflict.upper()
        self.conflict_keys = conflict_keys or []

    def write_chunk(self, chunk: DataChunk) -> int:
        """Writes a single DataChunk to the target table and commits transaction."""
        if not chunk.rows:
            return 0

        is_mysql = "pymysql" in type(self.conn).__module__ or "mysql" in type(self.conn).__module__
        q = "`" if is_mysql else '"'
        qualified_table = f"{q}{self.schema_name}{q}.{q}{self.table_name}{q}"
        col_names = [f"{q}{c}{q}" for c in chunk.columns]
        cols_str = ", ".join(col_names)

        with self.conn.cursor() as cur:
            if is_mysql:
                val_placeholders = ", ".join(["%s"] * len(chunk.columns))
                ignore_clause = "IGNORE" if self.on_conflict == "NOTHING" else ""
                query = f"INSERT {ignore_clause} INTO {qualified_table} ({cols_str}) VALUES ({val_placeholders});"
                cur.executemany(query, chunk.rows)
            else:
                conflict_clause = ""
                if self.on_conflict == "NOTHING":
                    if self.conflict_keys:
                        keys_str = ", ".join(f'"{k}"' for k in self.conflict_keys)
                        conflict_clause = f"ON CONFLICT ({keys_str}) DO NOTHING"
                    else:
                        conflict_clause = "ON CONFLICT DO NOTHING"

                query = f"INSERT INTO {qualified_table} ({cols_str}) VALUES %s {conflict_clause};"
                execute_values(cur, query, chunk.rows, page_size=len(chunk.rows))
        self.conn.commit()

        return len(chunk.rows)
