"""Incremental CDC Event Stream Comparator and Event Ordering Reconciler.

Verifies transaction event sequences (INSERT, UPDATE, DELETE), checks
monotonicity and out-of-order deliveries, and validates eventual state consistency.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .data_comparator import normalize_row_dict


class CdcOpType(StrEnum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


@dataclass
class CdcEvent:
    event_id: str
    table: str
    op: CdcOpType
    primary_key: Any
    lsn: int  # Monotonic Log Sequence Number or sequence id
    tx_id: int | str = ""
    timestamp: str = ""
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "table": self.table,
            "op": self.op.value,
            "primaryKey": self.primary_key,
            "lsn": self.lsn,
            "txId": self.tx_id,
            "timestamp": self.timestamp,
            "before": self.before,
            "after": self.after,
        }


@dataclass
class EventStreamAnomaly:
    anomaly_type: str  # "OUT_OF_ORDER", "DUPLICATE_EVENT", "INVALID_TRANSITION"
    event_id: str
    lsn: int
    details: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "anomalyType": self.anomaly_type,
            "eventId": self.event_id,
            "lsn": self.lsn,
            "details": self.details,
        }


@dataclass
class EventReconciliationReport:
    table_name: str
    total_events: int
    inserts: int
    updates: int
    deletes: int
    out_of_order_count: int
    duplicate_count: int
    anomalies: list[EventStreamAnomaly] = field(default_factory=list)
    state_consistent: bool = True
    mismatched_pks: list[Any] = field(default_factory=list)
    status: str = "CONSISTENT"  # "CONSISTENT", "EVENT_DISORDER", "STATE_MISMATCH"
    execution_engine: str = "PYTHON_CANONICAL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tableName": self.table_name,
            "totalEvents": self.total_events,
            "inserts": self.inserts,
            "updates": self.updates,
            "deletes": self.deletes,
            "outOfOrderCount": self.out_of_order_count,
            "duplicateCount": self.duplicate_count,
            "stateConsistent": self.state_consistent,
            "mismatchedPks": self.mismatched_pks,
            "status": self.status,
            "executionEngine": self.execution_engine,
            "anomalies": [a.to_dict() for a in self.anomalies],
        }


class EventComparator:
    """Reconciles CDC event streams against initial and final states."""

    def __init__(
        self,
        pk_col: str = "id",
        rust_binary_path: str | None = None,
        use_rust: bool = False,
    ) -> None:
        self.pk_col = pk_col
        self.use_rust = use_rust
        self.rust_binary_path = rust_binary_path or self._find_rust_binary()

    @staticmethod
    def _find_rust_binary() -> str | None:
        base_dir = os.path.dirname(__file__)
        candidates = [
            os.path.join(base_dir, "..", "..", "..", "cdc-engine-rust", "target", "release", "cdc-engine-rust"),
            os.path.join(base_dir, "..", "..", "..", "cdc-engine-rust", "target", "debug", "cdc-engine-rust"),
        ]
        for c in candidates:
            abs_path = os.path.abspath(c)
            if os.path.isfile(abs_path) and os.access(abs_path, os.X_OK):
                return abs_path
        return None

    def _replay_and_verify_with_rust(
        self,
        initial_state: list[dict[str, Any]],
        events: list[CdcEvent],
        final_target_state: list[dict[str, Any]],
        table_name: str,
    ) -> EventReconciliationReport | None:
        if not self.rust_binary_path or not os.path.isfile(self.rust_binary_path):
            return None

        events_json = [ev.to_dict() for ev in events]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as e_file, tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False
        ) as i_file, tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as t_file:
            json.dump(events_json, e_file, default=str)
            json.dump(initial_state, i_file, default=str)
            json.dump(final_target_state, t_file, default=str)
            e_path = e_file.name
            i_path = i_file.name
            t_path = t_file.name

        try:
            cmd = [
                self.rust_binary_path,
                "compare-events",
                "--events",
                e_path,
                "--initial",
                i_path,
                "--target",
                t_path,
                "--pk",
                self.pk_col,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            out = json.loads(res.stdout)

            anomalies = [
                EventStreamAnomaly(
                    anomaly_type=a.get("anomaly_type", "UNKNOWN"),
                    event_id=a.get("event_id", ""),
                    lsn=a.get("lsn", 0),
                    details=a.get("details", ""),
                )
                for a in out.get("anomalies", [])
            ]

            out_of_order = out.get("out_of_order_count", 0)
            state_consistent = out.get("state_consistent", True)
            status = "CONSISTENT"
            if not state_consistent:
                status = "STATE_MISMATCH"
            elif out_of_order > 0:
                status = "EVENT_DISORDER"

            return EventReconciliationReport(
                table_name=table_name,
                total_events=out.get("total_events", len(events)),
                inserts=out.get("inserts", 0),
                updates=out.get("updates", 0),
                deletes=out.get("deletes", 0),
                out_of_order_count=out_of_order,
                duplicate_count=out.get("duplicate_count", 0),
                anomalies=anomalies,
                state_consistent=state_consistent,
                mismatched_pks=out.get("mismatched_pks", []),
                status=status,
                execution_engine="RUST_CDC_CORE",
            )
        except Exception:
            return None
        finally:
            for p in (e_path, i_path, t_path):
                if os.path.exists(p):
                    os.remove(p)

    def replay_and_verify(
        self,
        initial_state: list[dict[str, Any]],
        events: list[CdcEvent],
        final_target_state: list[dict[str, Any]],
        table_name: str = "default_table",
    ) -> EventReconciliationReport:
        """Replay CDC event stream onto initial state and verify against target."""
        if self.use_rust and self.rust_binary_path:
            rust_res = self._replay_and_verify_with_rust(
                initial_state=initial_state,
                events=events,
                final_target_state=final_target_state,
                table_name=table_name,
            )
            if rust_res is not None:
                return rust_res

        # 1. State simulation table indexed by PK
        current_state: dict[Any, dict[str, Any]] = {
            r[self.pk_col]: dict(r) for r in initial_state if self.pk_col in r
        }

        # 2. Check stream ordering and duplicates
        seen_event_ids: set[str] = set()
        highest_lsn = -1
        anomalies: list[EventStreamAnomaly] = []
        out_of_order_count = 0
        duplicate_count = 0
        inserts = 0
        updates = 0
        deletes = 0

        for ev in events:
            # Operation count
            if ev.op == CdcOpType.INSERT:
                inserts += 1
            elif ev.op == CdcOpType.UPDATE:
                updates += 1
            elif ev.op == CdcOpType.DELETE:
                deletes += 1

            # Duplicate check
            if ev.event_id in seen_event_ids:
                duplicate_count += 1
                anomalies.append(
                    EventStreamAnomaly(
                        anomaly_type="DUPLICATE_EVENT",
                        event_id=ev.event_id,
                        lsn=ev.lsn,
                        details=f"Event ID {ev.event_id} observed more than once.",
                    )
                )
            else:
                seen_event_ids.add(ev.event_id)

            # LSN monotonic ordering check
            if ev.lsn <= highest_lsn:
                out_of_order_count += 1
                anomalies.append(
                    EventStreamAnomaly(
                        anomaly_type="OUT_OF_ORDER",
                        event_id=ev.event_id,
                        lsn=ev.lsn,
                        details=f"Event with LSN {ev.lsn} appeared after higher LSN {highest_lsn}.",
                    )
                )
            else:
                highest_lsn = ev.lsn

            # Replay onto state
            pk = ev.primary_key
            if ev.op == CdcOpType.INSERT:
                if ev.after is not None:
                    current_state[pk] = dict(ev.after)
            elif ev.op == CdcOpType.UPDATE:
                if ev.after is not None:
                    current_state[pk] = dict(ev.after)
            elif ev.op == CdcOpType.DELETE:
                current_state.pop(pk, None)

        # 3. Compare replayed expected state with final target state
        target_state_by_pk = {
            r[self.pk_col]: r for r in final_target_state if self.pk_col in r
        }

        all_pks = set(current_state.keys()) | set(target_state_by_pk.keys())
        mismatched_pks: list[Any] = []

        for pk in sorted(all_pks):
            expected = current_state.get(pk)
            actual = target_state_by_pk.get(pk)

            if expected is None or actual is None:
                mismatched_pks.append(pk)
            else:
                if normalize_row_dict(expected) != normalize_row_dict(actual):
                    mismatched_pks.append(pk)

        state_consistent = len(mismatched_pks) == 0

        # Determine aggregate status
        if not state_consistent:
            status = "STATE_MISMATCH"
        elif out_of_order_count > 0:
            status = "EVENT_DISORDER"
        else:
            status = "CONSISTENT"

        return EventReconciliationReport(
            table_name=table_name,
            total_events=len(events),
            inserts=inserts,
            updates=updates,
            deletes=deletes,
            out_of_order_count=out_of_order_count,
            duplicate_count=duplicate_count,
            anomalies=anomalies,
            state_consistent=state_consistent,
            mismatched_pks=mismatched_pks,
            status=status,
        )

    @staticmethod
    def filter_lsn_window(
        events: list[CdcEvent],
        min_lsn: int | None = None,
        max_lsn: int | None = None,
    ) -> list[CdcEvent]:
        """Filter events strictly within [min_lsn, max_lsn] window."""
        filtered = events
        if min_lsn is not None:
            filtered = [e for e in filtered if e.lsn >= min_lsn]
        if max_lsn is not None:
            filtered = [e for e in filtered if e.lsn <= max_lsn]
        return filtered


def parse_debezium_event(payload: dict[str, Any], default_pk_col: str = "id") -> CdcEvent:
    """Parse a Debezium CDC JSON record into a canonical CdcEvent."""
    op_code = payload.get("op", "").lower()
    source_meta = payload.get("source", {})
    table = source_meta.get("table", "unknown_table")
    lsn_raw = source_meta.get("lsn", 0)
    if isinstance(lsn_raw, str):
        cleaned_lsn = lsn_raw.replace("/", "")
        try:
            lsn = int(cleaned_lsn, 16) if "/" in lsn_raw else int(cleaned_lsn)
        except ValueError:
            lsn = abs(hash(lsn_raw)) % (10**9)
    else:
        lsn = int(lsn_raw)

    tx_id = source_meta.get("txId", "")
    ts = str(payload.get("ts_ms", source_meta.get("ts_ms", "")))

    before = payload.get("before")
    after = payload.get("after")

    if op_code in ("c", "r"):
        op = CdcOpType.INSERT
        pk = (after or {}).get(default_pk_col)
    elif op_code == "u":
        op = CdcOpType.UPDATE
        pk = (after or before or {}).get(default_pk_col)
    elif op_code == "d":
        op = CdcOpType.DELETE
        pk = (before or {}).get(default_pk_col)
    else:
        op = CdcOpType.INSERT
        pk = (after or {}).get(default_pk_col)

    event_id = payload.get("eventId") or f"deb-{table}-{lsn}-{tx_id}-{pk}"
    return CdcEvent(
        event_id=str(event_id),
        table=table,
        op=op,
        primary_key=pk,
        lsn=lsn,
        tx_id=tx_id,
        timestamp=ts,
        before=before,
        after=after,
    )


def parse_canal_events(payload: dict[str, Any]) -> list[CdcEvent]:
    """Parse a Canal CDC JSON payload into canonical CdcEvents."""
    table = payload.get("table", "unknown_table")
    pk_names = payload.get("pkNames", ["id"])
    pk_col = pk_names[0] if pk_names else "id"
    event_type = payload.get("type", "INSERT").upper()
    ts = str(payload.get("ts", payload.get("es", "")))
    canal_id = payload.get("id", 0)

    data_list = payload.get("data", []) or []
    old_list = payload.get("old", []) or []

    events: list[CdcEvent] = []
    for idx, data_item in enumerate(data_list):
        old_item = old_list[idx] if idx < len(old_list) else None

        if event_type == "INSERT":
            op = CdcOpType.INSERT
            pk = data_item.get(pk_col)
            before = None
            after = data_item
        elif event_type == "UPDATE":
            op = CdcOpType.UPDATE
            pk = data_item.get(pk_col)
            before = old_item
            after = data_item
        elif event_type == "DELETE":
            op = CdcOpType.DELETE
            pk = data_item.get(pk_col)
            before = data_item
            after = None
        else:
            op = CdcOpType.INSERT
            pk = data_item.get(pk_col)
            before = old_item
            after = data_item

        ev_id = f"canal-{canal_id}-{table}-{idx}-{pk}"
        events.append(
            CdcEvent(
                event_id=ev_id,
                table=table,
                op=op,
                primary_key=pk,
                lsn=int(canal_id) + idx,
                timestamp=ts,
                before=before,
                after=after,
            )
        )
    return events
