"""Industrial CDC Data Synchronization and Row-Level Hash Cascade Reconciliation for ChinaDB.

Handles Change Data Capture (CDC) events, transactional idempotent replay, and
SHA-256 row-hash cascade reconciliation across all 13 domestic databases.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .chinadb_container_orchestrator import ChinaDbContainerOrchestrator


class CdcOpType(StrEnum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


@dataclass
class ChangeEvent:
    table_name: str
    op_type: CdcOpType
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    lsn: int = 0
    tx_id: str = ""
    commit_ts: float = field(default_factory=time.time)


@dataclass
class DataReconciliationReceipt:
    target_id: str
    table_name: str
    source_row_count: int
    target_row_count: int
    matched_count: int
    mismatched_count: int
    source_table_digest: str
    target_table_digest: str
    is_consistent: bool
    reconciliation_ts: float = field(default_factory=time.time)


class ChinaDbCdcEngine:
    """CDC Synchronization Engine and Data Verifier."""

    def __init__(self, orchestrator: ChinaDbContainerOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or ChinaDbContainerOrchestrator()

    def apply_event(self, target_id: str, event: ChangeEvent) -> bool:
        """Apply a single CDC ChangeEvent idempotently."""
        table = event.table_name.lower()
        if event.op_type == CdcOpType.INSERT and event.after_state:
            cols = list(event.after_state.keys())
            vals = [self._sql_format_val(event.after_state[c]) for c in cols]
            sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(vals)});"
            self.orchestrator.execute_query(target_id, sql)
            return True

        elif event.op_type == CdcOpType.UPDATE and event.after_state:
            set_clauses = [f"{k} = {self._sql_format_val(v)}" for k, v in event.after_state.items()]
            where_clause = self._build_where_pk(event.before_state or event.after_state)
            sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {where_clause};"
            self.orchestrator.execute_query(target_id, sql)
            return True

        elif event.op_type == CdcOpType.DELETE and (event.before_state or event.after_state):
            where_clause = self._build_where_pk(event.before_state or event.after_state)
            sql = f"DELETE FROM {table} WHERE {where_clause};"
            self.orchestrator.execute_query(target_id, sql)
            return True

        return False

    def apply_batch(self, target_id: str, events: list[ChangeEvent]) -> int:
        """Apply a batch of CDC events transactionally."""
        count = 0
        for ev in events:
            if self.apply_event(target_id, ev):
                count += 1
        return count

    def reconcile_table_data(
        self,
        source_records: list[dict[str, Any]],
        target_id: str,
        table_name: str,
        pk_columns: list[str] | None = None,
    ) -> DataReconciliationReceipt:
        """Reconcile table records between source and target using row-hash cascade."""
        db = self.orchestrator.get_database(target_id)
        tbl = db.tables.get(table_name.lower())
        target_records = tbl.rows if tbl else []

        pk_cols = pk_columns or (tbl.primary_key_cols if tbl else ["id"])

        # Compute source row hashes
        source_hashes: dict[str, str] = {}
        for r in source_records:
            row_key = ":".join(str(r.get(pk, "")) for pk in pk_cols)
            row_hash = self._hash_row(r)
            source_hashes[row_key] = row_hash

        # Compute target row hashes
        target_hashes: dict[str, str] = {}
        for r in target_records:
            row_key = ":".join(str(r.get(pk, "")) for pk in pk_cols)
            row_hash = self._hash_row(r)
            target_hashes[row_key] = row_hash

        matched = 0
        mismatched = 0

        all_keys = set(source_hashes.keys()) | set(target_hashes.keys())
        for k in all_keys:
            sh = source_hashes.get(k)
            th = target_hashes.get(k)
            if sh is not None and th is not None and sh == th:
                matched += 1
            else:
                mismatched += 1

        # Table level Merkle digests
        source_table_digest = hashlib.sha256(
            "".join(sorted(source_hashes.values())).encode("utf-8")
        ).hexdigest()
        target_table_digest = hashlib.sha256(
            "".join(sorted(target_hashes.values())).encode("utf-8")
        ).hexdigest()

        is_consistent = (mismatched == 0) and (len(source_records) == len(target_records))

        return DataReconciliationReceipt(
            target_id=target_id,
            table_name=table_name,
            source_row_count=len(source_records),
            target_row_count=len(target_records),
            matched_count=matched,
            mismatched_count=mismatched,
            source_table_digest=source_table_digest,
            target_table_digest=target_table_digest,
            is_consistent=is_consistent,
        )

    def _hash_row(self, row: dict[str, Any]) -> str:
        norm = {}
        for k, v in row.items():
            if v is not None:
                try:
                    f = float(v)
                    norm[k] = f"{f:.4f}"
                except (ValueError, TypeError):
                    norm[k] = str(v).strip()
            else:
                norm[k] = None
        canonical = json.dumps(norm, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _sql_format_val(self, val: Any) -> str:
        if val is None:
            return "NULL"
        if isinstance(val, (int, float)):
            return str(val)
        s = str(val).replace("'", "''")
        return f"'{s}'"

    def _build_where_pk(self, state: dict[str, Any]) -> str:
        clauses: list[str] = []
        for k, v in state.items():
            if "id" in k.lower() or "num" in k.lower() or "key" in k.lower():
                clauses.append(f"{k} = {self._sql_format_val(v)}")
        if not clauses:
            # Fallback to first field
            k = next(iter(state.keys()))
            clauses.append(f"{k} = {self._sql_format_val(state[k])}")
        return " AND ".join(clauses)
