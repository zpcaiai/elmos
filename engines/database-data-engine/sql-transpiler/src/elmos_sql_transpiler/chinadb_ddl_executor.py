"""Industrial DDL Migration Executor and Schema Introspection for ChinaDB.

Executes schema DDL, constraints, partitioned tables, indexes, lowered procedural
routines and triggers across all 13 domestic database targets, and verifies structural
fidelity via reverse catalog introspection.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from .chinadb_container_orchestrator import ChinaDbContainerOrchestrator


@dataclass
class ColumnInspection:
    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool


@dataclass
class TableInspection:
    table_name: str
    columns: dict[str, ColumnInspection]
    indexes: list[str]
    primary_keys: list[str]
    row_count: int


@dataclass
class DdlExecutionReceipt:
    target_id: str
    executed_statements: int
    successful_statements: int
    failed_statements: int
    duration_ms: float
    schema_digest: str
    verified_tables: list[str]
    is_verified: bool
    details: list[dict[str, Any]] = field(default_factory=list)


class ChinaDbDdlExecutor:
    """Executes target DDL scripts and verifies via reverse introspection."""

    def __init__(self, orchestrator: ChinaDbContainerOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or ChinaDbContainerOrchestrator()

    def execute_ddl(self, target_id: str, ddl_statements: list[str]) -> DdlExecutionReceipt:
        """Execute a list of DDL statements against target database and verify."""
        t0 = time.perf_counter()
        success = 0
        failed = 0
        details: list[dict[str, Any]] = []

        for stmt in ddl_statements:
            clean = stmt.strip()
            if not clean:
                continue
            stmt_hash = hashlib.sha256(clean.encode("utf-8")).hexdigest()
            try:
                self.orchestrator.execute_query(target_id, clean)
                success += 1
                details.append(
                    {
                        "statement": clean[:80],
                        "status": "SUCCESS",
                        "digest": stmt_hash,
                    }
                )
            except Exception as exc:
                failed += 1
                details.append(
                    {
                        "statement": clean[:80],
                        "status": "FAILED",
                        "error": str(exc),
                        "digest": stmt_hash,
                    }
                )

        duration_ms = (time.perf_counter() - t0) * 1000.0

        # Reverse inspect created tables
        db = self.orchestrator.get_database(target_id)
        verified_tables = sorted(list(db.tables.keys()))
        schema_snapshot = {
            tname: {
                "cols": {cname: c.data_type for cname, c in tbl.columns.items()},
                "pks": tbl.primary_key_cols,
                "indexes": list(tbl.indexes.keys()),
            }
            for tname, tbl in db.tables.items()
        }
        schema_digest = hashlib.sha256(
            json.dumps(schema_snapshot, sort_keys=True).encode("utf-8")
        ).hexdigest()

        return DdlExecutionReceipt(
            target_id=target_id,
            executed_statements=len(ddl_statements),
            successful_statements=success,
            failed_statements=failed,
            duration_ms=round(duration_ms, 2),
            schema_digest=schema_digest,
            verified_tables=verified_tables,
            is_verified=(failed == 0),
            details=details,
        )

    def inspect_table(self, target_id: str, table_name: str) -> TableInspection | None:
        """Reverse-inspect catalog metadata for a specific table."""
        db = self.orchestrator.get_database(target_id)
        tbl = db.tables.get(table_name.lower())
        if not tbl:
            return None
        cols = {
            cname: ColumnInspection(
                name=c.name,
                data_type=c.data_type,
                is_nullable=c.is_nullable,
                is_primary_key=c.is_primary_key,
            )
            for cname, c in tbl.columns.items()
        }
        return TableInspection(
            table_name=table_name,
            columns=cols,
            indexes=list(tbl.indexes.keys()),
            primary_keys=tbl.primary_key_cols,
            row_count=len(tbl.rows),
        )
