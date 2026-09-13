"""Industrial CDC Data Synchronization and Row-Level Hash Cascade Reconciliation for ChinaDB.

Handles Change Data Capture (CDC) events, transactional idempotent replay, and
SHA-256 row-hash cascade reconciliation across all 13 domestic databases.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
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


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,127}$")


@dataclass(frozen=True)
class CdcCheckpoint:
    target_id: str
    table_name: str
    lsn: int
    event_digest: str
    applied_count: int
    updated_at: float


class CdcCheckpointStore:
    """Durable, monotonic CDC checkpoint store with atomic replacement."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._state: dict[str, dict[str, Any]] = {}
        if path is not None and path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("schemaVersion") != 1:
                raise ValueError("CDC_CHECKPOINT_INVALID")
            checkpoints = raw.get("checkpoints")
            if not isinstance(checkpoints, dict):
                raise ValueError("CDC_CHECKPOINT_INVALID")
            self._state = checkpoints

    @staticmethod
    def _key(target_id: str, table_name: str) -> str:
        return f"{target_id}:{table_name.lower()}"

    def get(self, target_id: str, table_name: str) -> CdcCheckpoint | None:
        raw = self._state.get(self._key(target_id, table_name))
        if raw is None:
            return None
        try:
            checkpoint = CdcCheckpoint(
                target_id=str(raw["targetId"]),
                table_name=str(raw["tableName"]),
                lsn=int(raw["lsn"]),
                event_digest=str(raw["eventDigest"]),
                applied_count=int(raw["appliedCount"]),
                updated_at=float(raw["updatedAt"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("CDC_CHECKPOINT_INVALID") from error
        if (
            checkpoint.lsn < 1
            or checkpoint.applied_count < 1
            or not re.fullmatch(r"[0-9a-f]{64}", checkpoint.event_digest)
            or not math.isfinite(checkpoint.updated_at)
        ):
            raise ValueError("CDC_CHECKPOINT_INVALID")
        return checkpoint

    def record(self, checkpoint: CdcCheckpoint) -> None:
        current = self.get(checkpoint.target_id, checkpoint.table_name)
        if current is not None and checkpoint.lsn < current.lsn:
            raise ValueError("CDC_CHECKPOINT_REGRESSION")
        self._state[self._key(checkpoint.target_id, checkpoint.table_name)] = {
            "targetId": checkpoint.target_id,
            "tableName": checkpoint.table_name,
            "lsn": checkpoint.lsn,
            "eventDigest": checkpoint.event_digest,
            "appliedCount": checkpoint.applied_count,
            "updatedAt": checkpoint.updated_at,
        }
        self._persist()

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        payload = {"schemaVersion": 1, "checkpoints": self._state}
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(
                    payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary.exists():
                temporary.unlink()


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
    compared_field_count: int = 0
    field_mismatch_count: int = 0
    missing_source_key_count: int = 0
    missing_target_key_count: int = 0
    duplicate_source_key_count: int = 0
    duplicate_target_key_count: int = 0
    money_precision_scale_exact: bool = True
    mismatch_samples: list[dict[str, Any]] = field(default_factory=list)
    reconciliation_ts: float = field(default_factory=time.time)


@dataclass
class MultiTableReconciliationReceipt:
    target_id: str
    tables: dict[str, DataReconciliationReceipt]
    total_source_rows: int
    total_target_rows: int
    total_matched: int
    total_mismatched: int
    merkle_tree_root: str
    cross_table_referential_integrity: bool
    is_consistent: bool
    reconciliation_ts: float = field(default_factory=time.time)


class ChinaDbCdcEngine:
    """CDC Synchronization Engine and Data Verifier."""

    def __init__(
        self,
        orchestrator: ChinaDbContainerOrchestrator | None = None,
        checkpoint_store: CdcCheckpointStore | None = None,
    ) -> None:
        self.orchestrator = orchestrator or ChinaDbContainerOrchestrator()
        self.checkpoints = checkpoint_store or CdcCheckpointStore()

    def apply_event(self, target_id: str, event: ChangeEvent) -> bool:
        """Apply one event after monotonic checkpoint and duplicate admission."""
        table = self._identifier(event.table_name, "table_name").lower()
        digest = self._event_digest(event)
        self._ensure_target_ledger(target_id)
        local_current = self.checkpoints.get(target_id, table)
        target_current = self._target_checkpoint(target_id, table)
        current = self._merge_checkpoints(local_current, target_current)
        if not self._event_is_new(current, event, digest):
            if local_current is None or local_current.lsn < event.lsn:
                if current is None:
                    raise RuntimeError("CDC_CHECKPOINT_NORMALIZATION_FAILED")
                self._restore_checkpoint(current)
            return False
        committed = False
        self.orchestrator.execute_query(target_id, "BEGIN;")
        try:
            self._insert_target_ledger(target_id, table, event, digest)
            self._execute_event(target_id, table, event)
            self.orchestrator.execute_query(target_id, "COMMIT;")
            committed = True
            self._after_target_commit(target_id, [(table, event, digest)])
        except Exception:
            if not committed:
                self.orchestrator.execute_query(target_id, "ROLLBACK;")
            raise
        self._record_checkpoint(target_id, table, event, digest, current)
        return True

    def _execute_event(self, target_id: str, table: str, event: ChangeEvent) -> None:
        if event.op_type == CdcOpType.INSERT and event.after_state:
            cols = [self._identifier(column, "column") for column in event.after_state]
            vals = [self._sql_format_val(event.after_state[c]) for c in cols]
            sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(vals)});"
            _, _, affected = self.orchestrator.execute_query(target_id, sql)
            self._require_single_effect(affected)
            return
        if event.op_type == CdcOpType.UPDATE and event.after_state:
            set_clauses = [
                f"{self._identifier(key, 'column')} = {self._sql_format_val(value)}"
                for key, value in event.after_state.items()
            ]
            update_state = event.before_state or event.after_state
            if update_state:
                where_clause = self._build_where_pk(target_id, table, update_state)
                sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {where_clause};"
                _, _, affected = self.orchestrator.execute_query(target_id, sql)
                self._require_single_effect(affected)
                return
        if event.op_type == CdcOpType.DELETE:
            delete_state = event.before_state or event.after_state
            if delete_state:
                where_clause = self._build_where_pk(target_id, table, delete_state)
                sql = f"DELETE FROM {table} WHERE {where_clause};"
                _, _, affected = self.orchestrator.execute_query(target_id, sql)
                self._require_single_effect(affected)
                return
        raise ValueError("CDC_EVENT_STATE_INVALID")

    @staticmethod
    def _require_single_effect(affected: int) -> None:
        if affected != 1:
            raise ValueError(f"CDC_TARGET_EFFECT_COUNT_INVALID:{affected}")

    def apply_batch(self, target_id: str, events: list[ChangeEvent]) -> int:
        """Apply a batch of CDC events transactionally."""
        count = 0
        for ev in events:
            if self.apply_event(target_id, ev):
                count += 1
        return count

    def apply_transaction_batch(self, target_id: str, events: list[ChangeEvent]) -> int:
        """Apply a batch of CDC events inside a strict ACID transaction."""
        self._ensure_target_ledger(target_id)
        pending: list[tuple[str, ChangeEvent, str, CdcCheckpoint | None]] = []
        shadow: dict[str, CdcCheckpoint | None] = {}
        for event in events:
            table = self._identifier(event.table_name, "table_name").lower()
            current = shadow.get(table)
            if table not in shadow:
                current = self._merge_checkpoints(
                    self.checkpoints.get(target_id, table),
                    self._target_checkpoint(target_id, table),
                )
            digest = self._event_digest(event)
            if not self._event_is_new(current, event, digest):
                local_current = self.checkpoints.get(target_id, table)
                if local_current is None or local_current.lsn < event.lsn:
                    if current is None:
                        raise RuntimeError("CDC_CHECKPOINT_NORMALIZATION_FAILED")
                    self._restore_checkpoint(current)
                continue
            pending.append((table, event, digest, current))
            shadow[table] = CdcCheckpoint(
                target_id=target_id,
                table_name=table,
                lsn=event.lsn,
                event_digest=digest,
                applied_count=(current.applied_count if current else 0) + 1,
                updated_at=event.commit_ts,
            )
        committed = False
        self.orchestrator.execute_query(target_id, "BEGIN;")
        try:
            for table, event, digest, _ in pending:
                self._insert_target_ledger(target_id, table, event, digest)
                self._execute_event(target_id, table, event)
            self.orchestrator.execute_query(target_id, "COMMIT;")
            committed = True
            self._after_target_commit(
                target_id,
                [(table, event, digest) for table, event, digest, _ in pending],
            )
            for table, event, digest, current in pending:
                self._record_checkpoint(target_id, table, event, digest, current)
            return len(pending)
        except Exception:
            if not committed:
                self.orchestrator.execute_query(target_id, "ROLLBACK;")
            raise

    def reconcile_multi_table_data(
        self,
        source_dataset: dict[str, list[dict[str, Any]]],
        target_id: str,
        pk_map: dict[str, list[str]] | None = None,
    ) -> MultiTableReconciliationReceipt:
        """Reconcile multi-table datasets and verify cross-table Merkle root & foreign key referential integrity."""
        pk_map = pk_map or {}
        table_receipts: dict[str, DataReconciliationReceipt] = {}
        total_src = 0
        total_tgt = 0
        total_matched = 0
        total_mismatched = 0
        merkle_leaves: list[str] = []

        all_consistent = True
        for tname, records in source_dataset.items():
            pks = pk_map.get(tname)
            receipt = self.reconcile_table_data(records, target_id, tname, pk_columns=pks)
            table_receipts[tname] = receipt
            total_src += receipt.source_row_count
            total_tgt += receipt.target_row_count
            total_matched += receipt.matched_count
            total_mismatched += receipt.mismatched_count
            if not receipt.is_consistent:
                all_consistent = False
            merkle_leaves.append(f"{tname.lower()}:{receipt.target_table_digest}")

        merkle_leaves.sort()
        merkle_tree_root = hashlib.sha256("||".join(merkle_leaves).encode("utf-8")).hexdigest()

        # Check cross-table referential integrity if accounts and tx_history exist
        db = self.orchestrator.get_database(target_id)
        accounts_tbl = db.tables.get("accounts")
        tx_tbl = db.tables.get("tx_history")
        ref_integrity = True
        if accounts_tbl and tx_tbl:
            valid_accs = {str(r.get("acc_no", "")).strip() for r in accounts_tbl.rows}
            for tx in tx_tbl.rows:
                from_acc = str(tx.get("from_acc", "")).strip()
                to_acc = str(tx.get("to_acc", "")).strip()
                if (from_acc and from_acc not in valid_accs) or (
                    to_acc and to_acc not in valid_accs
                ):
                    ref_integrity = False
                    all_consistent = False
                    break

        return MultiTableReconciliationReceipt(
            target_id=target_id,
            tables=table_receipts,
            total_source_rows=total_src,
            total_target_rows=total_tgt,
            total_matched=total_matched,
            total_mismatched=total_mismatched,
            merkle_tree_root=merkle_tree_root,
            cross_table_referential_integrity=ref_integrity,
            is_consistent=all_consistent and (total_mismatched == 0),
        )

    def reconcile_table_data(
        self,
        source_records: list[dict[str, Any]],
        target_id: str,
        table_name: str,
        pk_columns: list[str] | None = None,
        money_scales: dict[str, int] | None = None,
        money_precisions: dict[str, int] | None = None,
    ) -> DataReconciliationReceipt:
        """Compare table, primary key, row, field, and exact money semantics."""
        db = self.orchestrator.get_database(target_id)
        tbl = db.tables.get(table_name.lower())
        target_records = tbl.rows if tbl else []

        if pk_columns is None:
            if tbl is None or not tbl.primary_key_cols:
                raise ValueError("RECONCILIATION_PRIMARY_KEY_METADATA_REQUIRED")
            pk_cols = list(tbl.primary_key_cols)
        else:
            pk_cols = list(pk_columns)
        if not pk_cols:
            raise ValueError("RECONCILIATION_PRIMARY_KEY_REQUIRED")
        for column in pk_cols:
            self._identifier(column, "primary key column")
        money_scales = money_scales or {}
        money_precisions = money_precisions or {}
        if set(money_scales) != set(money_precisions):
            raise ValueError("RECONCILIATION_MONEY_PRECISION_SCALE_PAIR_REQUIRED")
        for column, scale in money_scales.items():
            self._identifier(column, "money column")
            if isinstance(scale, bool) or not isinstance(scale, int) or not 0 <= scale <= 38:
                raise ValueError("RECONCILIATION_MONEY_SCALE_INVALID")
            precision = money_precisions[column]
            if (
                isinstance(precision, bool)
                or not isinstance(precision, int)
                or not 1 <= precision <= 38
                or scale > precision
            ):
                raise ValueError("RECONCILIATION_MONEY_PRECISION_INVALID")

        def index_records(
            records: list[dict[str, Any]],
        ) -> tuple[dict[str, dict[str, Any]], dict[str, str], int]:
            rows_by_key: dict[str, dict[str, Any]] = {}
            hashes: dict[str, str] = {}
            duplicates = 0
            for row in records:
                missing = [column for column in pk_cols if column not in row or row[column] is None]
                if missing:
                    raise ValueError(f"RECONCILIATION_PRIMARY_KEY_MISSING:{missing}")
                row_key = self._row_key(row, pk_cols)
                if row_key in rows_by_key:
                    duplicates += 1
                    continue
                rows_by_key[row_key] = row
                hashes[row_key] = self._hash_row(
                    row,
                    money_scales=money_scales,
                    money_precisions=money_precisions,
                )
            return rows_by_key, hashes, duplicates

        source_rows, source_hashes, duplicate_source = index_records(source_records)
        target_rows, target_hashes, duplicate_target = index_records(target_records)

        matched = 0
        field_mismatches = 0
        compared_fields = 0
        mismatch_samples: list[dict[str, Any]] = []
        missing_source = len(set(target_hashes) - set(source_hashes))
        missing_target = len(set(source_hashes) - set(target_hashes))
        money_exact = True

        all_keys = set(source_hashes.keys()) | set(target_hashes.keys())
        mismatched_rows = 0
        for row_key in sorted(all_keys):
            sh = source_hashes.get(row_key)
            th = target_hashes.get(row_key)
            if sh is not None and th is not None and sh == th:
                matched += 1
                compared_fields += len(set(source_rows[row_key]) | set(target_rows[row_key]))
                continue
            mismatched_rows += 1
            source_row = source_rows.get(row_key, {})
            target_row = target_rows.get(row_key, {})
            for column in sorted(set(source_row) | set(target_row)):
                compared_fields += 1
                source_value = self._canonical_value(
                    source_row.get(column),
                    money_scales.get(column),
                    money_precisions.get(column),
                )
                target_value = self._canonical_value(
                    target_row.get(column),
                    money_scales.get(column),
                    money_precisions.get(column),
                )
                if source_value != target_value:
                    field_mismatches += 1
                    if column in money_scales:
                        money_exact = False
                    if len(mismatch_samples) < 100:
                        mismatch_samples.append(
                            {"primaryKey": row_key, "column": column, "kind": "FIELD_MISMATCH"}
                        )

        mismatched = mismatched_rows + duplicate_source + duplicate_target

        # Table level Merkle digests
        source_table_digest = hashlib.sha256(
            "".join(sorted(source_hashes.values())).encode("utf-8")
        ).hexdigest()
        target_table_digest = hashlib.sha256(
            "".join(sorted(target_hashes.values())).encode("utf-8")
        ).hexdigest()

        is_consistent = (
            mismatched == 0
            and field_mismatches == 0
            and len(source_records) == len(target_records)
            and money_exact
        )

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
            compared_field_count=compared_fields,
            field_mismatch_count=field_mismatches,
            missing_source_key_count=missing_source,
            missing_target_key_count=missing_target,
            duplicate_source_key_count=duplicate_source,
            duplicate_target_key_count=duplicate_target,
            money_precision_scale_exact=money_exact,
            mismatch_samples=mismatch_samples,
        )

    def _hash_row(
        self,
        row: dict[str, Any],
        *,
        money_scales: dict[str, int] | None = None,
        money_precisions: dict[str, int] | None = None,
    ) -> str:
        scales = money_scales or {}
        norm = {
            key: self._canonical_value(
                value,
                scales.get(key),
                (money_precisions or {}).get(key),
            )
            for key, value in sorted(row.items())
        }
        canonical = json.dumps(norm, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _canonical_value(
        self,
        value: Any,
        money_scale: int | None = None,
        money_precision: int | None = None,
    ) -> dict[str, Any]:
        if money_scale is not None:
            if money_precision is None:
                raise ValueError("RECONCILIATION_MONEY_PRECISION_SCALE_PAIR_REQUIRED")
            if isinstance(value, float):
                raise ValueError("RECONCILIATION_MONEY_FLOAT_PROHIBITED")
            try:
                decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
            except Exception as error:
                raise ValueError("RECONCILIATION_MONEY_VALUE_INVALID") from error
            if not decimal_value.is_finite():
                raise ValueError("RECONCILIATION_MONEY_VALUE_INVALID")
            if decimal_value.as_tuple().exponent != -money_scale:
                raise ValueError("RECONCILIATION_MONEY_SCALE_MISMATCH")
            digits = len(decimal_value.as_tuple().digits)
            integer_digits = max(digits - money_scale, 0)
            if digits > money_precision or integer_digits > money_precision - money_scale:
                raise ValueError("RECONCILIATION_MONEY_PRECISION_OVERFLOW")
            return {
                "type": "money",
                "precision": money_precision,
                "scale": money_scale,
                "value": format(decimal_value, "f"),
            }
        if value is None:
            return {"type": "null", "value": None}
        if isinstance(value, bool):
            return {"type": "boolean", "value": value}
        if isinstance(value, int):
            return {"type": "number", "value": str(value)}
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError("RECONCILIATION_NON_FINITE_DECIMAL")
            return {"type": "number", "value": format(value.normalize(), "f")}
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("RECONCILIATION_NON_FINITE_FLOAT")
            return {"type": "number", "value": format(Decimal(repr(value)).normalize(), "f")}
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("RECONCILIATION_NAIVE_DATETIME")
            return {"type": "datetime", "value": value.isoformat()}
        if isinstance(value, date):
            return {"type": "date", "value": value.isoformat()}
        if isinstance(value, bytes):
            return {"type": "bytes", "value": value.hex()}
        if isinstance(value, str):
            return {"type": "string", "value": value}
        raise ValueError(f"RECONCILIATION_UNSUPPORTED_VALUE_TYPE:{type(value).__name__}")

    def _sql_format_val(self, val: Any) -> str:
        if val is None:
            return "NULL"
        if isinstance(val, bool):
            return "1" if val else "0"
        if isinstance(val, int):
            return str(val)
        if isinstance(val, Decimal):
            if not val.is_finite():
                raise ValueError("CDC_NON_FINITE_DECIMAL")
            return format(val, "f")
        if isinstance(val, float):
            if not math.isfinite(val):
                raise ValueError("CDC_NON_FINITE_FLOAT")
            return repr(val)
        if isinstance(val, datetime):
            if val.tzinfo is None:
                raise ValueError("CDC_NAIVE_DATETIME")
            val = val.isoformat()
        elif isinstance(val, date):
            val = val.isoformat()
        elif isinstance(val, bytes):
            return f"HEXTORAW('{val.hex()}')"
        s = str(val).replace("'", "''")
        return f"'{s}'"

    @staticmethod
    def _identifier(value: str, name: str) -> str:
        if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
            raise ValueError(f"CDC_INVALID_IDENTIFIER:{name}")
        return value

    def _build_where_pk(
        self,
        target_id: str,
        table_name: str,
        state: dict[str, Any],
    ) -> str:
        table = self.orchestrator.get_database(target_id).tables.get(table_name)
        primary_keys = list(table.primary_key_cols) if table else []
        if not primary_keys:
            raise ValueError("CDC_PRIMARY_KEY_METADATA_REQUIRED")
        missing = [column for column in primary_keys if column not in state]
        if missing:
            raise ValueError(f"CDC_PRIMARY_KEY_VALUE_REQUIRED:{missing}")
        clauses = [
            f"{self._identifier(column, 'primary key column')} = "
            f"{self._sql_format_val(state[column])}"
            for column in primary_keys
        ]
        return " AND ".join(clauses)

    def _event_digest(self, event: ChangeEvent) -> str:
        if isinstance(event.lsn, bool) or not isinstance(event.lsn, int) or event.lsn < 1:
            raise ValueError("CDC_LSN_MUST_BE_POSITIVE")
        if not math.isfinite(event.commit_ts):
            raise ValueError("CDC_COMMIT_TIMESTAMP_INVALID")
        payload = {
            "table": self._identifier(event.table_name, "table_name").lower(),
            "operation": event.op_type.value,
            "before": {
                key: self._canonical_value(value)
                for key, value in sorted((event.before_state or {}).items())
            },
            "after": {
                key: self._canonical_value(value)
                for key, value in sorted((event.after_state or {}).items())
            },
            "lsn": event.lsn,
            "transactionId": event.tx_id,
            "commitTimestamp": event.commit_ts,
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _event_is_new(
        current: CdcCheckpoint | None,
        event: ChangeEvent,
        digest: str,
    ) -> bool:
        if current is None:
            return True
        if event.lsn < current.lsn:
            raise ValueError("CDC_OUT_OF_ORDER_EVENT")
        if event.lsn == current.lsn:
            if digest == current.event_digest:
                return False
            raise ValueError("CDC_POSITION_CONFLICT")
        return True

    def _record_checkpoint(
        self,
        target_id: str,
        table: str,
        event: ChangeEvent,
        digest: str,
        current: CdcCheckpoint | None,
    ) -> None:
        self.checkpoints.record(
            CdcCheckpoint(
                target_id=target_id,
                table_name=table,
                lsn=event.lsn,
                event_digest=digest,
                applied_count=(current.applied_count if current else 0) + 1,
                updated_at=time.time(),
            )
        )

    def _restore_checkpoint(self, checkpoint: CdcCheckpoint) -> None:
        self.checkpoints.record(
            CdcCheckpoint(
                target_id=checkpoint.target_id,
                table_name=checkpoint.table_name,
                lsn=checkpoint.lsn,
                event_digest=checkpoint.event_digest,
                applied_count=checkpoint.applied_count,
                updated_at=time.time(),
            )
        )

    def _ensure_target_ledger(self, target_id: str) -> None:
        self.orchestrator.execute_query(
            target_id,
            "CREATE TABLE IF NOT EXISTS elmos_cdc_event_ledger ("
            "target_id VARCHAR(64) NOT NULL, "
            "table_name VARCHAR(128) NOT NULL, "
            "source_lsn BIGINT NOT NULL, "
            "event_digest VARCHAR(64) NOT NULL, "
            "tx_id VARCHAR(128) NOT NULL, "
            "applied_at DOUBLE NOT NULL, "
            "CONSTRAINT pk_elmos_cdc_event_ledger "
            "PRIMARY KEY (target_id, table_name, source_lsn), "
            "CONSTRAINT uq_elmos_cdc_event_digest UNIQUE (event_digest));",
        )

    def _target_checkpoint(self, target_id: str, table: str) -> CdcCheckpoint | None:
        target_literal = self._sql_format_val(target_id)
        table_literal = self._sql_format_val(table)
        _, rows, _ = self.orchestrator.execute_query(
            target_id,
            "SELECT source_lsn, event_digest, applied_at "
            "FROM elmos_cdc_event_ledger "
            f"WHERE target_id = {target_literal} AND table_name = {table_literal} "
            "ORDER BY source_lsn DESC LIMIT 1;",
        )
        if not rows:
            return None
        lsn, digest, applied_at = rows[0]
        _, count_rows, _ = self.orchestrator.execute_query(
            target_id,
            "SELECT COUNT(*) FROM elmos_cdc_event_ledger "
            f"WHERE target_id = {target_literal} AND table_name = {table_literal};",
        )
        applied_count = int(count_rows[0][0]) if count_rows else 1
        return CdcCheckpoint(
            target_id=target_id,
            table_name=table,
            lsn=int(lsn),
            event_digest=str(digest),
            applied_count=applied_count,
            updated_at=float(applied_at),
        )

    @staticmethod
    def _merge_checkpoints(
        local: CdcCheckpoint | None,
        target: CdcCheckpoint | None,
    ) -> CdcCheckpoint | None:
        if local is None:
            return target
        if target is None:
            raise ValueError("CDC_TARGET_LEDGER_MISSING_FOR_CHECKPOINT")
        if local.lsn == target.lsn and local.event_digest != target.event_digest:
            raise ValueError("CDC_CHECKPOINT_TARGET_CONFLICT")
        if local.lsn > target.lsn:
            raise ValueError("CDC_CHECKPOINT_AHEAD_OF_TARGET_LEDGER")
        return local if local.lsn == target.lsn else target

    def _insert_target_ledger(
        self,
        target_id: str,
        table: str,
        event: ChangeEvent,
        digest: str,
    ) -> None:
        values = (
            self._sql_format_val(target_id),
            self._sql_format_val(table),
            str(event.lsn),
            self._sql_format_val(digest),
            self._sql_format_val(event.tx_id),
            repr(event.commit_ts),
        )
        self.orchestrator.execute_query(
            target_id,
            "INSERT INTO elmos_cdc_event_ledger "
            "(target_id, table_name, source_lsn, event_digest, tx_id, applied_at) "
            f"VALUES ({', '.join(values)});",
        )

    def _after_target_commit(
        self,
        target_id: str,
        committed_events: list[tuple[str, ChangeEvent, str]],
    ) -> None:
        """Failure-injection seam after atomic target commit, before checkpoint."""
        del target_id, committed_events

    def _row_key(self, row: dict[str, Any], primary_keys: list[str]) -> str:
        canonical = [self._canonical_value(row[column]) for column in primary_keys]
        return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
