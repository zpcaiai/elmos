"""Chunked database table reader with Keyset Pagination and memory bounding.

Prevents Out-Of-Memory (OOM) on massive tables by streaming rows in deterministic
ordered chunks, calculating SHA-256 chunk digests for verification.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator

logger = logging.getLogger(__name__)


def _json_serial(obj: Any) -> str:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.hex()
    return str(obj)


def compute_row_hash(row: tuple[Any, ...]) -> str:
    """Computes a deterministic hash for a single row."""
    normalized = json.dumps(row, default=_json_serial, sort_keys=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_chunk_hash(rows: list[tuple[Any, ...]]) -> str:
    """Computes a Merkle-leaf hash for an entire chunk of rows."""
    hasher = hashlib.sha256()
    for row in rows:
        row_str = json.dumps(row, default=_json_serial, sort_keys=True)
        hasher.update(row_str.encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


@dataclass
class DataChunk:
    table_name: str
    chunk_index: int
    columns: list[str]
    rows: list[tuple[Any, ...]]
    min_key: Any | None = None
    max_key: Any | None = None
    chunk_hash: str = ""
    row_count: int = 0


class ChunkReader:
    """Reads rows from a live database connection in bounded chunks."""

    def __init__(
        self,
        connection: Any,
        table_name: str,
        columns: list[str] | None = None,
        primary_key_col: str | None = None,
        chunk_size: int = 5000,
        schema_name: str = "public",
    ) -> None:
        self.conn = connection
        self.table_name = table_name
        self.schema_name = schema_name
        self.columns = columns
        self.primary_key_col = primary_key_col
        self.chunk_size = chunk_size

    def _resolve_columns_and_pk(self, cur: Any) -> tuple[list[str], str | None]:
        """Auto-discovers columns and primary key if not provided."""
        cols = self.columns
        if not cols:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position;
                """,
                (self.schema_name, self.table_name),
            )
            cols = [r[0] for r in cur.fetchall()]

        pk = self.primary_key_col
        if not pk:
            cur.execute(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = %s
                  AND tc.table_name = %s
                ORDER BY kcu.ordinal_position
                LIMIT 1;
                """,
                (self.schema_name, self.table_name),
            )
            row = cur.fetchone()
            if row:
                pk = row[0]

        return cols, pk

    def iter_chunks(self) -> Iterator[DataChunk]:
        """Streams table rows chunk-by-chunk using Keyset Pagination."""
        with self.conn.cursor() as cur:
            cols, pk = self._resolve_columns_and_pk(cur)
            if not cols:
                logger.warning("No columns found for table %s.%s", self.schema_name, self.table_name)
                return

            qualified_table = f'"{self.schema_name}"."{self.table_name}"'
            col_list_str = ", ".join(f'"{c}"' for c in cols)

            chunk_idx = 0
            if pk:
                # Keyset Pagination: WHERE pk > last_val ORDER BY pk LIMIT chunk_size
                last_val: Any = None
                pk_quoted = f'"{pk}"'
                pk_idx = cols.index(pk) if pk in cols else -1

                while True:
                    if last_val is None:
                        query = f"SELECT {col_list_str} FROM {qualified_table} ORDER BY {pk_quoted} ASC LIMIT %s;"
                        cur.execute(query, (self.chunk_size,))
                    else:
                        query = f"SELECT {col_list_str} FROM {qualified_table} WHERE {pk_quoted} > %s ORDER BY {pk_quoted} ASC LIMIT %s;"
                        cur.execute(query, (last_val, self.chunk_size))

                    rows = cur.fetchall()
                    if not rows:
                        break

                    min_k = rows[0][pk_idx] if pk_idx >= 0 else None
                    max_k = rows[-1][pk_idx] if pk_idx >= 0 else None
                    last_val = max_k

                    c_hash = compute_chunk_hash(rows)
                    yield DataChunk(
                        table_name=self.table_name,
                        chunk_index=chunk_idx,
                        columns=cols,
                        rows=rows,
                        min_key=min_k,
                        max_key=max_k,
                        chunk_hash=c_hash,
                        row_count=len(rows),
                    )
                    chunk_idx += 1
                    if len(rows) < self.chunk_size:
                        break
            else:
                # Fallback to server-side named cursor
                cursor_name = f"chunk_cur_{self.table_name}_{id(self)}"
                with self.conn.cursor(name=cursor_name) as named_cur:
                    named_cur.execute(f"SELECT {col_list_str} FROM {qualified_table};")
                    while True:
                        rows = named_cur.fetchmany(self.chunk_size)
                        if not rows:
                            break
                        c_hash = compute_chunk_hash(rows)
                        yield DataChunk(
                            table_name=self.table_name,
                            chunk_index=chunk_idx,
                            columns=cols,
                            rows=rows,
                            chunk_hash=c_hash,
                            row_count=len(rows),
                        )
                        chunk_idx += 1
