"""Incremental CDC Event Stream Comparator and Event Ordering Reconciler.

Verifies transaction event sequences (INSERT, UPDATE, DELETE), checks
monotonicity and out-of-order deliveries, and validates eventual state consistency.
"""

from __future__ import annotations

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
            "anomalies": [a.to_dict() for a in self.anomalies],
        }


class EventComparator:
    """Reconciles CDC event streams against initial and final states."""

    def __init__(self, pk_col: str = "id") -> None:
        self.pk_col = pk_col

    def replay_and_verify(
        self,
        initial_state: list[dict[str, Any]],
        events: list[CdcEvent],
        final_target_state: list[dict[str, Any]],
        table_name: str = "default_table",
    ) -> EventReconciliationReport:
        """Replay CDC event stream onto initial state and verify against target."""
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
