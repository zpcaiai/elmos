"""High-performance bulk database writer supporting COPY and batched parameter arrays."""

from __future__ import annotations

import logging
from typing import Any

try:
    from psycopg2.extras import execute_values
except ImportError:
    execute_values = None

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

        qualified_table = f'"{self.schema_name}"."{self.table_name}"'
        col_names = [f'"{c}"' for c in chunk.columns]
        cols_str = ", ".join(col_names)

        conflict_clause = ""
        if self.on_conflict == "NOTHING":
            if self.conflict_keys:
                keys_str = ", ".join(f'"{k}"' for k in self.conflict_keys)
                conflict_clause = f"ON CONFLICT ({keys_str}) DO NOTHING"
            else:
                conflict_clause = "ON CONFLICT DO NOTHING"

        query = f"INSERT INTO {qualified_table} ({cols_str}) VALUES %s {conflict_clause};"

        with self.conn.cursor() as cur:
            execute_values(cur, query, chunk.rows, page_size=len(chunk.rows))
        self.conn.commit()

        return len(chunk.rows)
