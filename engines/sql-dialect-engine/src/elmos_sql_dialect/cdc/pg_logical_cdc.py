"""Real PostgreSQL Logical Decoding CDC Ingestion Client.

Uses PostgreSQL's native logical decoding slot (`pg_logical_slot_get_changes`
with `test_decoding`) to capture live WAL changes (INSERT, UPDATE, DELETE) and
converts them into structured ChangeEvent objects for real-time replication
and reconciliation.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from .event_comparator import CdcEvent, CdcOpType

logger = logging.getLogger(__name__)

# test_decoding format regex patterns:
# table public.customers: INSERT: customer_id[integer]:1 name[character varying]:'Alice'
# table public.customers: UPDATE: customer_id[integer]:1 name[character varying]:'Bob'
# table public.customers: DELETE: customer_id[integer]:1
TABLE_CHANGE_RE = re.compile(
    r"table\s+(?:\"?([A-Za-z0-9_]+)\"?\.)?\"?([A-Za-z0-9_]+)\"?:\s+(INSERT|UPDATE|DELETE):\s*(.*)",
    re.IGNORECASE,
)
COL_VAL_RE = re.compile(
    r"\"?([A-Za-z0-9_]+)\"?\[[^\]]+\]:(?:'((?:''|[^'])*)'|([^\s]+))",
)


def parse_test_decoding_row(data_str: str) -> tuple[str | None, str | None, CdcOpType | None, dict[str, Any]]:
    """Parses a raw test_decoding change string into structured components."""
    m = TABLE_CHANGE_RE.match(data_str.strip())
    if not m:
        return None, None, None, {}

    schema_name = m.group(1) or "public"
    table_name = m.group(2)
    raw_op = m.group(3).upper()
    col_str = m.group(4)

    op = CdcOpType.INSERT
    if raw_op == "UPDATE":
        op = CdcOpType.UPDATE
    elif raw_op == "DELETE":
        op = CdcOpType.DELETE

    values: dict[str, Any] = {}
    for col_match in COL_VAL_RE.finditer(col_str):
        cname = col_match.group(1)
        quoted_val = col_match.group(2)
        unquoted_val = col_match.group(3)

        if quoted_val is not None:
            val = quoted_val.replace("''", "'")
        elif unquoted_val is not None:
            if unquoted_val == "null":
                val = None
            else:
                val = unquoted_val
        else:
            val = None
        values[cname] = val

    return schema_name, table_name, op, values


class PostgresLogicalReplicationCdc:
    """Manages a live PostgreSQL logical decoding slot to capture CDC events."""

    def __init__(
        self,
        connection: Any,
        slot_name: str = "elmos_cdc_slot",
        plugin: str = "test_decoding",
    ) -> None:
        self.conn = connection
        self.slot_name = slot_name
        self.plugin = plugin
        self._is_active = False

    def create_slot_if_not_exists(self) -> None:
        """Creates a logical decoding slot if it does not already exist."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT slot_name FROM pg_replication_slots WHERE slot_name = %s;",
                (self.slot_name,),
            )
            if not cur.fetchone():
                try:
                    cur.execute(
                        "SELECT pg_create_logical_replication_slot(%s, %s);",
                        (self.slot_name, self.plugin),
                    )
                    self.conn.commit()
                    logger.info("Created logical replication slot %s with plugin %s", self.slot_name, self.plugin)
                except Exception as exc:
                    self.conn.rollback()
                    logger.warning("Could not create replication slot %s: %s", self.slot_name, exc)
                    raise

    def drop_slot_if_exists(self) -> None:
        """Drops the logical replication slot during teardown."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT slot_name FROM pg_replication_slots WHERE slot_name = %s;",
                (self.slot_name,),
            )
            if cur.fetchone():
                try:
                    cur.execute("SELECT pg_drop_replication_slot(%s);", (self.slot_name,))
                    self.conn.commit()
                    logger.info("Dropped logical replication slot %s", self.slot_name)
                except Exception as exc:
                    self.conn.rollback()
                    logger.warning("Could not drop replication slot %s: %s", self.slot_name, exc)

    def fetch_changes(self, up_to_n_changes: int = 100) -> list[CdcEvent]:
        """Polls for pending WAL changes from the logical replication slot."""
        events: list[CdcEvent] = []
        with self.conn.cursor() as cur:
            query = "SELECT lsn, xid, data FROM pg_logical_slot_get_changes(%s, NULL, %s);"
            cur.execute(query, (self.slot_name, up_to_n_changes))
            rows = cur.fetchall()

        self.conn.commit()

        seq = 0
        now_ts = str(time.time())
        for row in rows:
            lsn_str = str(row[0])
            # parse numeric part of lsn if possible, or hash
            try:
                # lsn is formatted like '0/16B2348'
                parts = lsn_str.split("/")
                numeric_lsn = (int(parts[0], 16) << 32) + int(parts[1], 16)
            except Exception:
                numeric_lsn = seq

            xid_str = str(row[1])
            data_str = str(row[2])

            schema_name, table_name, op, values = parse_test_decoding_row(data_str)
            if not table_name or not op:
                continue

            event = CdcEvent(
                event_id=f"{lsn_str}-{seq}",
                table=table_name,
                op=op,
                primary_key=values.get("id") or values.get(f"{table_name}_id") or next(iter(values.values()), seq),
                lsn=numeric_lsn,
                tx_id=xid_str,
                timestamp=now_ts,
                before=values if op == CdcOpType.DELETE else None,
                after=values if op in (CdcOpType.INSERT, CdcOpType.UPDATE) else None,
            )
            events.append(event)
            seq += 1

        return events
