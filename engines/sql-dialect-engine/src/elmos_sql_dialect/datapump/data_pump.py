"""End-to-end physical database migration Data Pump.

Streams live data from source database to target database in bounded chunks,
following foreign key topological dependency order, and records cryptographic
Merkle chunk receipts for bitwise verification.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..topological_sorter import TableDependencyGraph
from .bulk_writer import BulkWriter
from .chunk_reader import ChunkReader, DataChunk

logger = logging.getLogger(__name__)


@dataclass
class TablePumpStat:
    table_name: str
    total_rows: int
    chunks_count: int
    chunk_hashes: list[str]
    duration_ms: float
    throughput_rows_sec: float


@dataclass
class DataPumpReceipt:
    source_schema: str
    target_schema: str
    total_tables: int
    total_rows: int
    total_duration_ms: float
    overall_throughput_rows_sec: float
    table_stats: dict[str, TablePumpStat] = field(default_factory=dict)
    success: bool = True
    error: str | None = None


class PhysicalDataPump:
    """Coordinates chunked reading and bulk writing between live database connections."""

    def __init__(
        self,
        source_connection: Any,
        target_connection: Any,
        source_schema: str = "public",
        target_schema: str = "public",
        chunk_size: int = 5000,
    ) -> None:
        self.source_conn = source_connection
        self.target_conn = target_connection
        self.source_schema = source_schema
        self.target_schema = target_schema
        self.chunk_size = chunk_size

    def pump_table(
        self,
        table_name: str,
        primary_key_col: str | None = None,
        on_conflict: str = "ERROR",
        on_chunk_callback: Callable[[DataChunk], None] | None = None,
    ) -> TablePumpStat:
        """Pumps a single table from source to target in bounded chunks."""
        t0 = time.perf_counter()
        reader = ChunkReader(
            connection=self.source_conn,
            table_name=table_name,
            schema_name=self.source_schema,
            primary_key_col=primary_key_col,
            chunk_size=self.chunk_size,
        )
        writer = BulkWriter(
            connection=self.target_conn,
            table_name=table_name,
            schema_name=self.target_schema,
            on_conflict=on_conflict,
            conflict_keys=[primary_key_col] if primary_key_col else None,
        )

        total_rows = 0
        chunks_count = 0
        chunk_hashes: list[str] = []

        for chunk in reader.iter_chunks():
            writer.write_chunk(chunk)
            total_rows += chunk.row_count
            chunks_count += 1
            chunk_hashes.append(chunk.chunk_hash)
            if on_chunk_callback:
                on_chunk_callback(chunk)

        elapsed = time.perf_counter() - t0
        elapsed_ms = elapsed * 1000.0
        throughput = (total_rows / elapsed) if elapsed > 0 else 0.0

        return TablePumpStat(
            table_name=table_name,
            total_rows=total_rows,
            chunks_count=chunks_count,
            chunk_hashes=chunk_hashes,
            duration_ms=elapsed_ms,
            throughput_rows_sec=throughput,
        )

    def pump_tables(
        self,
        table_names: list[str],
        dependency_graph: TableDependencyGraph | None = None,
        on_conflict: str = "ERROR",
    ) -> DataPumpReceipt:
        """Pumps multiple tables, respecting topological foreign-key dependencies."""
        t0 = time.perf_counter()
        ordered_tables = table_names
        if dependency_graph:
            plan = dependency_graph.compute_creation_order()
            ordered_tables = [t for t in plan.ordered_tables if t in table_names]
            # Add any tables not in the graph
            for t in table_names:
                if t not in ordered_tables:
                    ordered_tables.append(t)

        stats: dict[str, TablePumpStat] = {}
        total_rows = 0

        try:
            for tbl in ordered_tables:
                stat = self.pump_table(tbl, on_conflict=on_conflict)
                stats[tbl] = stat
                total_rows += stat.total_rows

            elapsed = time.perf_counter() - t0
            elapsed_ms = elapsed * 1000.0
            overall_throughput = (total_rows / elapsed) if elapsed > 0 else 0.0

            return DataPumpReceipt(
                source_schema=self.source_schema,
                target_schema=self.target_schema,
                total_tables=len(ordered_tables),
                total_rows=total_rows,
                total_duration_ms=elapsed_ms,
                overall_throughput_rows_sec=overall_throughput,
                table_stats=stats,
                success=True,
            )
        except Exception as exc:
            logger.error("PhysicalDataPump failed: %s", exc)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return DataPumpReceipt(
                source_schema=self.source_schema,
                target_schema=self.target_schema,
                total_tables=len(stats),
                total_rows=total_rows,
                total_duration_ms=elapsed_ms,
                overall_throughput_rows_sec=0.0,
                table_stats=stats,
                success=False,
                error=str(exc),
            )
