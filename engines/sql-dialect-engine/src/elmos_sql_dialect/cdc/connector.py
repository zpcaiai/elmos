"""Database Stream Connector and Keyset Pagination Reader for CDC.

Provides memory-bounded streaming data extraction, keyset pagination,
deterministic chunk hashing, and streaming chunk comparison.
"""

from __future__ import annotations

import abc
import logging
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from .data_comparator import (
    ChunkDiffResult,
    RowDiff,
    SnapshotCompareReport,
    hash_rows,
    normalize_cell_value,
)

logger = logging.getLogger(__name__)


@dataclass
class TableChunk:
    """Represents a bounded slice of rows with metadata and aggregate hash."""

    chunk_index: int
    table_name: str
    pk_col: str
    start_pk: Any
    end_pk: Any
    row_count: int
    rows: list[dict[str, Any]]
    chunk_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunkIndex": self.chunk_index,
            "tableName": self.table_name,
            "pkCol": self.pk_col,
            "startPk": self.start_pk,
            "endPk": self.end_pk,
            "rowCount": self.row_count,
            "chunkHash": self.chunk_hash,
        }


class DatabaseStreamConnector(abc.ABC):
    """Abstract interface for streaming database access."""

    @abc.abstractmethod
    def fetch_rows_keyset(
        self,
        table: str,
        pk_col: str,
        last_pk: Any | None,
        chunk_size: int,
        columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch a page of rows using keyset pagination: WHERE pk > last_pk ORDER BY pk LIMIT chunk_size."""

    @abc.abstractmethod
    def fetch_count(self, table: str) -> int:
        """Fetch total row count for table."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release underlying connections or resources."""


class MockDatabaseStreamConnector(DatabaseStreamConnector):
    """In-memory stream connector for testing and synthetic validation workloads."""

    def __init__(self, tables: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = tables or {}

    def close(self) -> None:
        """No-op for in-memory connector."""

    def set_table_data(self, table: str, rows: list[dict[str, Any]]) -> None:
        self.tables[table] = rows

    def fetch_rows_keyset(
        self,
        table: str,
        pk_col: str,
        last_pk: Any | None,
        chunk_size: int,
        columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        raw_rows = self.tables.get(table, [])
        # Sort by primary key
        sorted_rows = sorted(raw_rows, key=lambda r: r.get(pk_col, 0))

        # Filter WHERE pk > last_pk
        if last_pk is not None:
            filtered = [r for r in sorted_rows if r.get(pk_col, 0) > last_pk]
        else:
            filtered = sorted_rows

        # Apply LIMIT chunk_size
        slice_rows = filtered[:chunk_size]

        # Project columns if specified
        if columns is not None:
            return [
                {k: r[k] for k in columns if k in r}
                for r in slice_rows
            ]
        return [dict(r) for r in slice_rows]

    def fetch_count(self, table: str) -> int:
        return len(self.tables.get(table, []))


class KeysetPaginationReader:
    """Streams data from a DatabaseStreamConnector in fixed-size chunks.

    Memory consumption is strictly bounded to O(chunk_size) regardless of total rows.
    """

    def __init__(
        self,
        connector: DatabaseStreamConnector,
        table_name: str,
        pk_col: str,
        columns: list[str] | None = None,
        chunk_size: int = 1000,
        hasher: str = "sha256",
    ) -> None:
        self.connector = connector
        self.table_name = table_name
        self.pk_col = pk_col
        self.columns = columns
        self.chunk_size = chunk_size
        self.hasher = hasher

    def iter_chunks(self) -> Generator[TableChunk, None, None]:
        """Iterate over table chunks one at a time."""
        last_pk: Any | None = None
        chunk_idx = 1

        while True:
            rows = self.connector.fetch_rows_keyset(
                table=self.table_name,
                pk_col=self.pk_col,
                last_pk=last_pk,
                chunk_size=self.chunk_size,
                columns=self.columns,
            )

            if not rows:
                break

            start_pk = rows[0].get(self.pk_col)
            end_pk = rows[-1].get(self.pk_col)
            chunk_hash = hash_rows(rows, columns=self.columns, algorithm=self.hasher)

            yield TableChunk(
                chunk_index=chunk_idx,
                table_name=self.table_name,
                pk_col=self.pk_col,
                start_pk=start_pk,
                end_pk=end_pk,
                row_count=len(rows),
                rows=rows,
                chunk_hash=chunk_hash,
            )

            last_pk = end_pk
            chunk_idx += 1

            # If fewer rows returned than chunk_size, we've reached the end
            if len(rows) < self.chunk_size:
                break


class StreamingDataComparator:
    """Reconciles two DatabaseStreamConnectors using streaming keyset pagination and Bisect Diff."""

    def __init__(
        self,
        chunk_size: int = 1000,
        hasher: str = "sha256",
    ) -> None:
        self.chunk_size = chunk_size
        self.hasher = hasher

    def compare_streams(
        self,
        source_connector: DatabaseStreamConnector,
        target_connector: DatabaseStreamConnector,
        table_name: str,
        pk_col: str,
        columns: list[str] | None = None,
    ) -> SnapshotCompareReport:
        """Stream both tables in parallel and perform fast chunk hash comparison and bisect diff."""
        src_reader = KeysetPaginationReader(
            connector=source_connector,
            table_name=table_name,
            pk_col=pk_col,
            columns=columns,
            chunk_size=self.chunk_size,
            hasher=self.hasher,
        )
        tgt_reader = KeysetPaginationReader(
            connector=target_connector,
            table_name=table_name,
            pk_col=pk_col,
            columns=columns,
            chunk_size=self.chunk_size,
            hasher=self.hasher,
        )

        src_gen = src_reader.iter_chunks()
        tgt_gen = tgt_reader.iter_chunks()

        total_chunks = 0
        matched_chunks = 0
        mismatched_chunks = 0
        total_src_rows = 0
        total_tgt_rows = 0
        aligned_rows = 0
        chunk_results: list[ChunkDiffResult] = []

        active_src_chunk: TableChunk | None = next(src_gen, None)
        active_tgt_chunk: TableChunk | None = next(tgt_gen, None)
        chunk_id = 1

        while active_src_chunk is not None or active_tgt_chunk is not None:
            total_chunks += 1

            if active_src_chunk is not None and active_tgt_chunk is not None:
                src_rows = active_src_chunk.rows
                tgt_rows = active_tgt_chunk.rows
                total_src_rows += len(src_rows)
                total_tgt_rows += len(tgt_rows)

                # Fast Path: Chunk hashes match!
                if (
                    active_src_chunk.chunk_hash == active_tgt_chunk.chunk_hash
                    and active_src_chunk.start_pk == active_tgt_chunk.start_pk
                    and active_src_chunk.end_pk == active_tgt_chunk.end_pk
                ):
                    matched_chunks += 1
                    aligned_rows += len(src_rows)
                    chunk_results.append(
                        ChunkDiffResult(
                            chunk_id=chunk_id,
                            start_pk=active_src_chunk.start_pk,
                            end_pk=active_src_chunk.end_pk,
                            matched=True,
                            source_row_count=len(src_rows),
                            target_row_count=len(tgt_rows),
                            source_hash=active_src_chunk.chunk_hash,
                            target_hash=active_tgt_chunk.chunk_hash,
                        )
                    )
                else:
                    # Mismatch: Bisect / fine-grained row diff within this chunk
                    mismatched_chunks += 1
                    diff_res = self._bisect_diff_chunk(
                        chunk_id=chunk_id,
                        src_chunk=active_src_chunk,
                        tgt_chunk=active_tgt_chunk,
                        pk_col=pk_col,
                        columns=columns,
                    )
                    aligned_rows += (len(src_rows) - len(diff_res.diff_samples))
                    chunk_results.append(diff_res)

                active_src_chunk = next(src_gen, None)
                active_tgt_chunk = next(tgt_gen, None)

            elif active_src_chunk is not None and active_tgt_chunk is None:
                # Target has missing chunk
                mismatched_chunks += 1
                src_rows = active_src_chunk.rows
                total_src_rows += len(src_rows)
                diff_samples = [
                    RowDiff(
                        primary_key=r.get(pk_col),
                        diff_type="MISSING_IN_TARGET",
                        source_row=r,
                        target_row=None,
                    )
                    for r in src_rows
                ]
                chunk_results.append(
                    ChunkDiffResult(
                        chunk_id=chunk_id,
                        start_pk=active_src_chunk.start_pk,
                        end_pk=active_src_chunk.end_pk,
                        matched=False,
                        source_row_count=len(src_rows),
                        target_row_count=0,
                        source_hash=active_src_chunk.chunk_hash,
                        target_hash="",
                        mismatched_pks=[r.get(pk_col) for r in src_rows],
                        diff_samples=diff_samples,
                    )
                )
                active_src_chunk = next(src_gen, None)

            elif active_src_chunk is None and active_tgt_chunk is not None:
                # Source has missing chunk (extra in target)
                mismatched_chunks += 1
                tgt_rows = active_tgt_chunk.rows
                total_tgt_rows += len(tgt_rows)
                diff_samples = [
                    RowDiff(
                        primary_key=r.get(pk_col),
                        diff_type="EXTRA_IN_TARGET",
                        source_row=None,
                        target_row=r,
                    )
                    for r in tgt_rows
                ]
                chunk_results.append(
                    ChunkDiffResult(
                        chunk_id=chunk_id,
                        start_pk=active_tgt_chunk.start_pk,
                        end_pk=active_tgt_chunk.end_pk,
                        matched=False,
                        source_row_count=0,
                        target_row_count=len(tgt_rows),
                        source_hash="",
                        target_hash=active_tgt_chunk.chunk_hash,
                        mismatched_pks=[r.get(pk_col) for r in tgt_rows],
                        diff_samples=diff_samples,
                    )
                )
                active_tgt_chunk = next(tgt_gen, None)

            chunk_id += 1

        total_rows = max(total_src_rows, total_tgt_rows)
        alignment_rate = round(aligned_rows / total_rows, 6) if total_rows > 0 else 1.0
        status = "ALIGNED" if mismatched_chunks == 0 else "DIVERGED"
        if total_chunks == 0:
            status = "EMPTY"

        return SnapshotCompareReport(
            table_name=table_name,
            primary_key=pk_col,
            total_chunks=total_chunks,
            matched_chunks=matched_chunks,
            mismatched_chunks=mismatched_chunks,
            total_source_rows=total_src_rows,
            total_target_rows=total_tgt_rows,
            aligned_rows=aligned_rows,
            alignment_rate=alignment_rate,
            status=status,
            chunk_results=chunk_results,
            execution_engine="STREAMING_KEYSET_DIALECT",
        )

    def _bisect_diff_chunk(
        self,
        chunk_id: int,
        src_chunk: TableChunk,
        tgt_chunk: TableChunk,
        pk_col: str,
        columns: list[str] | None = None,
    ) -> ChunkDiffResult:
        """Perform fine-grained row-level diffing on a mismatched chunk."""
        src_map = {r.get(pk_col): r for r in src_chunk.rows if pk_col in r}
        tgt_map = {r.get(pk_col): r for r in tgt_chunk.rows if pk_col in r}

        all_pks = sorted(set(src_map.keys()) | set(tgt_map.keys()))
        mismatched_pks: list[Any] = []
        diff_samples: list[RowDiff] = []

        for pk in all_pks:
            s_row = src_map.get(pk)
            t_row = tgt_map.get(pk)

            if s_row is not None and t_row is None:
                mismatched_pks.append(pk)
                diff_samples.append(
                    RowDiff(
                        primary_key=pk,
                        diff_type="MISSING_IN_TARGET",
                        source_row=s_row,
                        target_row=None,
                    )
                )
            elif s_row is None and t_row is not None:
                mismatched_pks.append(pk)
                diff_samples.append(
                    RowDiff(
                        primary_key=pk,
                        diff_type="EXTRA_IN_TARGET",
                        source_row=None,
                        target_row=t_row,
                    )
                )
            elif s_row is not None and t_row is not None:
                differing_fields: list[str] = []
                check_cols = columns or sorted(set(s_row.keys()) | set(t_row.keys()))
                for c in check_cols:
                    s_val = normalize_cell_value(s_row.get(c))
                    t_val = normalize_cell_value(t_row.get(c))
                    if s_val != t_val:
                        differing_fields.append(c)

                if differing_fields:
                    mismatched_pks.append(pk)
                    diff_samples.append(
                        RowDiff(
                            primary_key=pk,
                            diff_type="MODIFIED",
                            source_row=s_row,
                            target_row=t_row,
                            differing_fields=differing_fields,
                        )
                    )

        return ChunkDiffResult(
            chunk_id=chunk_id,
            start_pk=src_chunk.start_pk,
            end_pk=src_chunk.end_pk,
            matched=len(mismatched_pks) == 0,
            source_row_count=len(src_chunk.rows),
            target_row_count=len(tgt_chunk.rows),
            source_hash=src_chunk.chunk_hash,
            target_hash=tgt_chunk.chunk_hash,
            mismatched_pks=mismatched_pks,
            diff_samples=diff_samples,
        )
