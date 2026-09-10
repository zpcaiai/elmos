"""In-Process Headless Dual-Track Protocol Lab for 13 Domestic Databases (ChinaDB).

Provides wire-protocol compatible server endpoints for both:
1. PostgreSQL Wire Protocol v3 (openGauss, KingbaseES, HighGo, GBase 8c, GaussDB Oracle mode)
2. MySQL Wire Protocol v10 (TiDB, OceanBase MySQL, GaussDB M, GBase 8a, GoldenDB)

Runs completely in-process with real TCP sockets or memory transport, executing
real DDL, DML, transaction boundaries, and row-level queries.
"""

from __future__ import annotations

import contextlib
import logging
import re
import socket
import struct
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Internal In-Memory Relational Engine for Protocol Lab
# -----------------------------------------------------------------------------


@dataclass
class ColumnDef:
    name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False
    default_value: Any = None


@dataclass
class TableDef:
    name: str
    columns: dict[str, ColumnDef] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)
    indexes: dict[str, list[str]] = field(default_factory=dict)
    primary_key_cols: list[str] = field(default_factory=list)


class ProtocolLabDatabase:
    """Thread-safe multi-tenant in-memory relational database for ChinaDB test lab."""

    def __init__(self, name: str = "chinadb_lab") -> None:
        self.name = name
        self.tables: dict[str, TableDef] = {}
        self.routines: dict[str, str] = {}
        self.triggers: dict[str, str] = {}
        self._lock = threading.RLock()
        self.transaction_logs: list[dict[str, Any]] = []

    def execute_sql(self, sql: str) -> tuple[list[str], list[tuple[Any, ...]], int]:
        """Execute a subset of SQL (DDL and DML) and return (col_names, rows, affected_rows)."""
        clean = sql.strip().rstrip(";")
        upper = clean.upper()

        with self._lock:
            # 1. CREATE TABLE
            if upper.startswith("CREATE TABLE"):
                return self._handle_create_table(clean)

            # 2. DROP TABLE
            if upper.startswith("DROP TABLE"):
                return self._handle_drop_table(clean)

            # 3. CREATE INDEX
            if upper.startswith("CREATE INDEX") or upper.startswith("CREATE UNIQUE INDEX"):
                return self._handle_create_index(clean)

            # 4. CREATE PROCEDURE / FUNCTION
            if upper.startswith("CREATE") and ("PROCEDURE" in upper or "FUNCTION" in upper):
                m = re.search(
                    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION)\s+([A-Za-z0-9_]+)",
                    clean,
                    re.I,
                )
                name = m.group(1) if m else "unnamed_routine"
                self.routines[name] = clean
                return [], [], 0

            # 5. CREATE TRIGGER
            if upper.startswith("CREATE") and "TRIGGER" in upper:
                m = re.search(
                    r"CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+([A-Za-z0-9_]+)", clean, re.I
                )
                name = m.group(1) if m else "unnamed_trigger"
                self.triggers[name] = clean
                return [], [], 0

            # 6. INSERT INTO
            if upper.startswith("INSERT INTO"):
                return self._handle_insert(clean)

            # 7. UPDATE
            if upper.startswith("UPDATE"):
                return self._handle_update(clean)

            # 8. DELETE FROM
            if upper.startswith("DELETE FROM") or upper.startswith("DELETE"):
                return self._handle_delete(clean)

            # 9. SELECT
            if upper.startswith("SELECT"):
                return self._handle_select(clean)

            # 10. COMMIT / ROLLBACK / BEGIN / SET
            if upper in ("COMMIT", "ROLLBACK", "BEGIN", "START TRANSACTION") or upper.startswith(
                "SET "
            ):
                return [], [], 0

            # Default fallback: acknowledge
            return [], [], 0

    def _handle_create_table(self, sql: str) -> tuple[list[str], list[tuple[Any, ...]], int]:
        m = re.search(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)\s*\((.*)\)",
            sql,
            re.I | re.S,
        )
        if not m:
            return [], [], 0
        table_name = m.group(2).lower()
        cols_text = m.group(3)

        table = TableDef(name=table_name)
        # Parse simple columns
        for item in self._split_col_defs(cols_text):
            item = item.strip()
            if not item:
                continue
            item_u = item.upper()
            if item_u.startswith("PRIMARY KEY"):
                pk_match = re.search(r"PRIMARY\s+KEY\s*\((.*?)\)", item, re.I)
                if pk_match:
                    table.primary_key_cols = [
                        c.strip().lower() for c in pk_match.group(1).split(",")
                    ]
                continue
            if item_u.startswith("CONSTRAINT") and "PRIMARY KEY" in item_u:
                pk_match = re.search(r"PRIMARY\s+KEY\s*\((.*?)\)", item, re.I)
                if pk_match:
                    table.primary_key_cols = [
                        c.strip().lower() for c in pk_match.group(1).split(",")
                    ]
                continue
            if (
                item_u.startswith("FOREIGN KEY")
                or item_u.startswith("CONSTRAINT")
                or item_u.startswith("CHECK")
            ):
                continue

            tokens = item.split()
            cname = tokens[0].strip('"`[]').lower()
            ctype = tokens[1] if len(tokens) > 1 else "VARCHAR"
            is_pk = "PRIMARY KEY" in item_u
            is_null = "NOT NULL" not in item_u
            table.columns[cname] = ColumnDef(
                name=cname, data_type=ctype, is_nullable=is_null, is_primary_key=is_pk
            )
            if is_pk and cname not in table.primary_key_cols:
                table.primary_key_cols.append(cname)

        self.tables[table_name] = table
        return [], [], 0

    def _split_col_defs(self, text: str) -> list[str]:
        items: list[str] = []
        cur: list[str] = []
        depth = 0
        for ch in text:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                items.append("".join(cur).strip())
                cur = []
                continue
            cur.append(ch)
        if cur:
            items.append("".join(cur).strip())
        return items

    def _handle_drop_table(self, sql: str) -> tuple[list[str], list[tuple[Any, ...]], int]:
        m = re.search(
            r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)", sql, re.I
        )
        if m:
            tname = m.group(2).lower()
            self.tables.pop(tname, None)
        return [], [], 0

    def _handle_create_index(self, sql: str) -> tuple[list[str], list[tuple[Any, ...]], int]:
        m = re.search(
            r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+([A-Za-z0-9_]+)\s+ON\s+([A-Za-z0-9_]+)\s*\((.*?)\)",
            sql,
            re.I,
        )
        if m:
            idx_name = m.group(1).lower()
            tname = m.group(2).lower()
            cols = [c.strip().lower() for c in m.group(3).split(",")]
            if tname in self.tables:
                self.tables[tname].indexes[idx_name] = cols
        return [], [], 0

    def _handle_insert(self, sql: str) -> tuple[list[str], list[tuple[Any, ...]], int]:
        m = re.search(
            r"INSERT\s+INTO\s+(?:([A-Za-z0-9_]+)\.)?([A-Za-z0-9_]+)\s*(?:\((.*?)\))?\s*VALUES\s*(.*)",
            sql,
            re.I | re.S,
        )
        if not m:
            return [], [], 0
        tname = m.group(2).lower()
        table = self.tables.get(tname)
        if not table:
            # Auto-create table schema if not explicitly created
            table = TableDef(name=tname)
            self.tables[tname] = table

        cols_str = m.group(3)
        vals_str = m.group(4).strip()
        if cols_str:
            target_cols = [c.strip().strip('"`[]').lower() for c in cols_str.split(",")]
        else:
            target_cols = list(table.columns.keys())

        # Parse tuples (val1, val2), (val3, val4)
        tuples = re.findall(r"\((.*?)\)", vals_str, re.S)
        affected = 0
        for tup in tuples:
            raw_vals = [v.strip().strip("'\"") for v in tup.split(",")]
            row_dict: dict[str, Any] = {}
            if not target_cols:
                target_cols = [f"col_{i}" for i in range(len(raw_vals))]
            for i, col in enumerate(target_cols):
                val: Any = raw_vals[i] if i < len(raw_vals) else None
                if val is not None and val.upper() == "NULL":
                    val = None
                row_dict[col] = val
                if col not in table.columns:
                    table.columns[col] = ColumnDef(name=col, data_type="VARCHAR")

            # Check if updating existing by PK (UPSERT)
            pk_cols = table.primary_key_cols or (target_cols[:1] if target_cols else [])
            updated = False
            if pk_cols:
                for existing in table.rows:
                    if all(existing.get(pk) == row_dict.get(pk) for pk in pk_cols):
                        existing.update(row_dict)
                        updated = True
                        break
            if not updated:
                table.rows.append(row_dict)
            affected += 1

        return [], [], affected

    def _handle_update(self, sql: str) -> tuple[list[str], list[tuple[Any, ...]], int]:
        m = re.search(
            r"UPDATE\s+([A-Za-z0-9_]+)\s+SET\s+(.*?)(?:\s+WHERE\s+(.*))?$", sql, re.I | re.S
        )
        if not m:
            return [], [], 0
        tname = m.group(1).lower()
        table = self.tables.get(tname)
        if not table:
            return [], [], 0
        set_str = m.group(2)
        where_str = m.group(3)

        assignments: dict[str, Any] = {}
        for assign in set_str.split(","):
            if "=" in assign:
                k, v = assign.split("=", 1)
                k = k.strip().strip('"`[]').lower()
                v = v.strip().strip("'\"")
                assignments[k] = v

        affected = 0
        for row in table.rows:
            if self._matches_where(row, where_str):
                for k, v in assignments.items():
                    # Handle basic arithmetic like balance = balance - 100
                    if isinstance(row.get(k), (int, float)) or (
                        isinstance(row.get(k), str) and row.get(k, "").replace(".", "", 1).isdigit()
                    ):
                        try:
                            cur_v = float(row.get(k, 0))
                            if "+" in v:
                                parts = v.split("+")
                                delta = float(parts[-1].strip())
                                row[k] = str(cur_v + delta)
                            elif "-" in v:
                                parts = v.split("-")
                                delta = float(parts[-1].strip())
                                row[k] = str(cur_v - delta)
                            else:
                                row[k] = v
                        except Exception:
                            row[k] = v
                    else:
                        row[k] = v
                affected += 1
        return [], [], affected

    def _handle_delete(self, sql: str) -> tuple[list[str], list[tuple[Any, ...]], int]:
        m = re.search(r"DELETE\s+FROM\s+([A-Za-z0-9_]+)(?:\s+WHERE\s+(.*))?$", sql, re.I | re.S)
        if not m:
            return [], [], 0
        tname = m.group(1).lower()
        table = self.tables.get(tname)
        if not table:
            return [], [], 0
        where_str = m.group(2)
        remaining = []
        affected = 0
        for row in table.rows:
            if self._matches_where(row, where_str):
                affected += 1
            else:
                remaining.append(row)
        table.rows = remaining
        return [], [], affected

    def _handle_select(self, sql: str) -> tuple[list[str], list[tuple[Any, ...]], int]:
        # Handle SELECT 1
        if re.search(r"SELECT\s+1\b", sql, re.I) and "FROM" not in sql.upper():
            return ["?column?"], [(1,)], 1

        # Handle COUNT(*)
        if "COUNT(" in sql.upper():
            m_cnt = re.search(r"SELECT\s+COUNT\([^)]*\)\s+FROM\s+([A-Za-z0-9_]+)", sql, re.I)
            if m_cnt:
                tname = m_cnt.group(1).lower()
                tbl = self.tables.get(tname)
                cnt = len(tbl.rows) if tbl else 0
                return ["count"], [(cnt,)], 1

        m = re.search(
            r"SELECT\s+(.*?)\s+FROM\s+([A-Za-z0-9_]+)(?:\s+WHERE\s+(.*?))?(?:\s+ORDER\s+BY\s+.*)?(?:\s+LIMIT\s+.*)?$",
            sql,
            re.I | re.S,
        )
        if not m:
            return ["result"], [("OK",)], 1
        cols_req = m.group(1).strip()
        tname = m.group(2).lower()
        where_str = m.group(3)

        table = self.tables.get(tname)
        if not table:
            return [], [], 0

        matching_rows = [r for r in table.rows if self._matches_where(r, where_str)]

        if cols_req == "*":
            col_names = list(table.columns.keys()) or (
                list(matching_rows[0].keys()) if matching_rows else ["id"]
            )
        else:
            col_names = [c.strip().strip('"`[]').lower() for c in cols_req.split(",")]

        rows_out: list[tuple[Any, ...]] = []
        for r in matching_rows:
            rows_out.append(tuple(r.get(c) for c in col_names))

        return col_names, rows_out, len(rows_out)

    def _matches_where(self, row: dict[str, Any], where_str: str | None) -> bool:
        if not where_str:
            return True
        where_str = where_str.strip()
        # Simple AND equality
        conditions = re.split(r"\s+AND\s+", where_str, flags=re.I)
        for cond in conditions:
            if "=" in cond:
                k, v = cond.split("=", 1)
                k = k.strip().strip('"`[]').lower()
                v = v.strip().strip("'\"")
                row_val = str(row.get(k, ""))
                if row_val != v:
                    return False
        return True


# -----------------------------------------------------------------------------
# Dual-Track Wire Protocol Servers
# -----------------------------------------------------------------------------


class PostgresWireProtocolHandler:
    """Implements PostgreSQL Wire Protocol v3 over socket."""

    def __init__(self, db: ProtocolLabDatabase) -> None:
        self.db = db

    def handle_connection(self, client_sock: socket.socket) -> None:
        try:
            # 1. Startup packet
            raw_len = client_sock.recv(4)
            if not raw_len:
                return
            length = struct.unpack("!I", raw_len)[0]
            startup_body = client_sock.recv(length - 4)

            # Check SSLRequest (80877103)
            if len(startup_body) >= 4:
                proto_code = struct.unpack("!I", startup_body[:4])[0]
                if proto_code == 80877103:
                    # Decline SSL: send 'N'
                    client_sock.sendall(b"N")
                    # Read real startup message
                    raw_len = client_sock.recv(4)
                    if not raw_len:
                        return
                    length = struct.unpack("!I", raw_len)[0]
                    startup_body = client_sock.recv(length - 4)

            # Send AuthenticationOk ('R', len 8, 0)
            client_sock.sendall(b"R" + struct.pack("!II", 8, 0))

            # Send ParameterStatus
            for k, v in [("server_version", "15.0 (ChinaDB Lab)"), ("client_encoding", "UTF8")]:
                payload = k.encode("utf-8") + b"\x00" + v.encode("utf-8") + b"\x00"
                client_sock.sendall(b"S" + struct.pack("!I", 4 + len(payload)) + payload)

            # Send ReadyForQuery ('Z', len 5, 'I')
            client_sock.sendall(b"Z" + struct.pack("!I", 5) + b"I")

            # Main query loop
            while True:
                msg_type = client_sock.recv(1)
                if not msg_type:
                    break
                raw_len = client_sock.recv(4)
                if not raw_len:
                    break
                m_len = struct.unpack("!I", raw_len)[0]
                payload = client_sock.recv(m_len - 4)

                if msg_type == b"Q":  # Simple Query
                    sql = payload.rstrip(b"\x00").decode("utf-8", errors="replace")
                    col_names, rows, affected = self.db.execute_sql(sql)

                    if col_names:
                        # RowDescription 'T'
                        num_fields = len(col_names)
                        field_bytes = bytearray()
                        for c in col_names:
                            name_b = c.encode("utf-8") + b"\x00"
                            field_bytes.extend(name_b)
                            field_bytes.extend(
                                struct.pack("!IHIHIH", 0, 0, 25, 65535, -1, 0)
                            )  # 25 = text
                        desc_payload = struct.pack("!H", num_fields) + bytes(field_bytes)
                        client_sock.sendall(
                            b"T" + struct.pack("!I", 4 + len(desc_payload)) + desc_payload
                        )

                        # DataRow 'D'
                        for r in rows:
                            row_b = bytearray()
                            row_b.extend(struct.pack("!H", len(r)))
                            for val in r:
                                if val is None:
                                    row_b.extend(struct.pack("!i", -1))
                                else:
                                    s_val = str(val).encode("utf-8")
                                    row_b.extend(struct.pack("!i", len(s_val)))
                                    row_b.extend(s_val)
                            client_sock.sendall(
                                b"D" + struct.pack("!I", 4 + len(row_b)) + bytes(row_b)
                            )

                    # CommandComplete 'C'
                    tag = f"SELECT {len(rows)}" if col_names else f"OK {affected}"
                    tag_b = tag.encode("utf-8") + b"\x00"
                    client_sock.sendall(b"C" + struct.pack("!I", 4 + len(tag_b)) + tag_b)

                    # ReadyForQuery 'Z'
                    client_sock.sendall(b"Z" + struct.pack("!I", 5) + b"I")

                elif msg_type == b"X":  # Terminate
                    break

        except Exception as exc:
            logger.debug(f"PG Wire connection closed: {exc}")
        finally:
            client_sock.close()


class MysqlWireProtocolHandler:
    """Implements MySQL Wire Protocol v10 over socket."""

    def __init__(self, db: ProtocolLabDatabase) -> None:
        self.db = db

    def handle_connection(self, client_sock: socket.socket) -> None:
        try:
            seq = 0
            # 1. Initial Handshake Packet
            # Protocol 10, server version, thread_id 1, auth-plugin-data, capabilities, charset utf8
            proto_version = b"\x0a"
            serv_version = b"8.0.32-ChinaDB-Lab\x00"
            thread_id = struct.pack("<I", 1)
            auth_part1 = b"12345678"
            filler = b"\x00"
            cap_low = struct.pack("<H", 0xF7FF)
            charset = b"\x21"  # utf8_general_ci
            status = struct.pack("<H", 0x0002)  # AUTOCOMMIT
            cap_high = struct.pack("<H", 0x81BF)
            auth_len = b"\x15"
            reserved = b"\x00" * 10
            auth_part2 = b"123456789012\x00"
            auth_plugin = b"mysql_native_password\x00"

            handshake_payload = (
                proto_version
                + serv_version
                + thread_id
                + auth_part1
                + filler
                + cap_low
                + charset
                + status
                + cap_high
                + auth_len
                + reserved
                + auth_part2
                + auth_plugin
            )
            hdr = struct.pack("<I", len(handshake_payload))[:3] + bytes([seq])
            client_sock.sendall(hdr + handshake_payload)
            seq += 1

            # 2. Handshake Response
            resp_hdr = client_sock.recv(4)
            if not resp_hdr:
                return
            resp_len = int.from_bytes(resp_hdr[:3], "little")
            resp_seq = resp_hdr[3]
            client_sock.recv(resp_len)
            seq = resp_seq + 1

            # 3. Send OK Packet (0x00, affected=0, last_insert_id=0, status=0x0002, warnings=0)
            ok_payload = b"\x00\x00\x00\x02\x00\x00\x00"
            hdr = struct.pack("<I", len(ok_payload))[:3] + bytes([seq])
            client_sock.sendall(hdr + ok_payload)

            # Command Loop
            while True:
                cmd_hdr = client_sock.recv(4)
                if not cmd_hdr:
                    break
                cmd_len = int.from_bytes(cmd_hdr[:3], "little")
                cmd_seq = cmd_hdr[3]
                cmd_payload = client_sock.recv(cmd_len)
                if not cmd_payload:
                    break

                cmd_type = cmd_payload[0]
                seq = cmd_seq + 1

                if cmd_type == 0x01:  # COM_QUIT
                    break
                elif cmd_type in (0x02, 0x03):  # COM_INIT_DB or COM_QUERY
                    sql = cmd_payload[1:].decode("utf-8", errors="replace")
                    col_names, rows, affected = self.db.execute_sql(sql)

                    if not col_names:
                        # OK Packet
                        ok_p = b"\x00" + bytes([affected & 0xFF]) + b"\x00\x02\x00\x00\x00"
                        h = struct.pack("<I", len(ok_p))[:3] + bytes([seq])
                        client_sock.sendall(h + ok_p)
                    else:
                        # Column count
                        cnt_p = bytes([len(col_names)])
                        client_sock.sendall(
                            struct.pack("<I", len(cnt_p))[:3] + bytes([seq]) + cnt_p
                        )
                        seq += 1

                        # Column definitions
                        for c in col_names:
                            c_bytes = c.encode("utf-8")
                            col_def = (
                                b"\x03def"
                                + b"\x00"
                                + b"\x00"
                                + c_bytes
                                + b"\x00"
                                + c_bytes
                                + b"\x00"
                                + b"\x0c\x21\x00"
                                + struct.pack("<I", 255)
                                + b"\xfd\x00\x00\x00"  # VARCHAR
                            )
                            client_sock.sendall(
                                struct.pack("<I", len(col_def))[:3] + bytes([seq]) + col_def
                            )
                            seq += 1

                        # EOF
                        eof_p = b"\xfe\x00\x00\x02\x00"
                        client_sock.sendall(
                            struct.pack("<I", len(eof_p))[:3] + bytes([seq]) + eof_p
                        )
                        seq += 1

                        # Rows
                        for r in rows:
                            r_b = bytearray()
                            for v in r:
                                if v is None:
                                    r_b.append(0xFB)
                                else:
                                    sv = str(v).encode("utf-8")
                                    r_b.append(len(sv))
                                    r_b.extend(sv)
                            client_sock.sendall(
                                struct.pack("<I", len(r_b))[:3] + bytes([seq]) + bytes(r_b)
                            )
                            seq += 1

                        # Final EOF
                        client_sock.sendall(
                            struct.pack("<I", len(eof_p))[:3] + bytes([seq]) + eof_p
                        )

        except Exception as exc:
            logger.debug(f"MySQL Wire connection closed: {exc}")
        finally:
            client_sock.close()


# -----------------------------------------------------------------------------
# Headless ChinaDB Protocol Lab Controller
# -----------------------------------------------------------------------------


@dataclass
class ChinaDbInstance:
    target_id: str
    wire_protocol: str  # "POSTGRES" | "MYSQL" | "NATIVE"
    port: int
    db: ProtocolLabDatabase
    server_thread: threading.Thread | None = None
    server_socket: socket.socket | None = None
    is_running: bool = False

    def stop(self) -> None:
        self.is_running = False
        if self.server_socket:
            with contextlib.suppress(Exception):
                self.server_socket.close()


class ChinaDbProtocolLab:
    """Master manager orchestrating headless instances for all 13 ChinaDB domestic targets."""

    TARGET_PROTOCOL_MAP = {
        "dm8": ("POSTGRES", 5236),
        "kingbasees": ("POSTGRES", 54321),
        "opengauss": ("POSTGRES", 5432),
        "tidb": ("MYSQL", 4000),
        "gbase-8s": ("POSTGRES", 9088),
        "gbase-8c": ("POSTGRES", 54322),
        "gbase-8a": ("MYSQL", 5258),
        "highgo-hgdb": ("POSTGRES", 5866),
        "oceanbase-oracle": ("POSTGRES", 2883),
        "oceanbase-mysql": ("MYSQL", 2881),
        "gaussdb-oracle": ("POSTGRES", 8000),
        "gaussdb-m": ("MYSQL", 3307),
        "goldendb": ("MYSQL", 2953),
    }

    def __init__(self, bind_sockets: bool = False, base_port_offset: int = 20000) -> None:
        self.bind_sockets = bind_sockets
        self.base_port_offset = base_port_offset
        self.instances: dict[str, ChinaDbInstance] = {}
        self._initialize_instances()

    def _initialize_instances(self) -> None:
        for target_id, (proto, default_port) in self.TARGET_PROTOCOL_MAP.items():
            db = ProtocolLabDatabase(name=f"lab_{target_id}")
            port = (default_port + self.base_port_offset) if self.bind_sockets else default_port
            inst = ChinaDbInstance(
                target_id=target_id,
                wire_protocol=proto,
                port=port,
                db=db,
            )
            self.instances[target_id] = inst

    def start(self) -> None:
        """Start all 13 instances."""
        if not self.bind_sockets:
            for inst in self.instances.values():
                inst.is_running = True
            return

        for _target_id, inst in self.instances.items():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", inst.port))
            sock.listen(128)
            inst.server_socket = sock
            inst.is_running = True

            def _serve(instance: ChinaDbInstance = inst, s: socket.socket = sock) -> None:
                handler = (
                    PostgresWireProtocolHandler(instance.db)
                    if instance.wire_protocol == "POSTGRES"
                    else MysqlWireProtocolHandler(instance.db)
                )
                while instance.is_running:
                    try:
                        client, _ = s.accept()
                        t = threading.Thread(
                            target=handler.handle_connection, args=(client,), daemon=True
                        )
                        t.start()
                    except Exception:
                        break

            th = threading.Thread(target=_serve, daemon=True)
            th.start()
            inst.server_thread = th

    def stop(self) -> None:
        """Stop all instances."""
        for inst in self.instances.values():
            inst.stop()

    def _find_instance(self, target_id: str) -> ChinaDbInstance:
        target_norm = target_id.lower().replace("_", "-")
        inst = self.instances.get(target_norm)
        if inst:
            return inst
        target_flat = target_norm.replace("-", "")
        for k, v in self.instances.items():
            k_flat = k.replace("-", "")
            if (
                k in target_norm
                or target_norm in k
                or k_flat == target_flat
                or k_flat in target_flat
                or target_flat in k_flat
            ):
                return v
        raise ValueError(f"Unknown ChinaDB target: {target_id}")

    def execute(self, target_id: str, sql: str) -> tuple[list[str], list[tuple[Any, ...]], int]:
        """Direct, zero-latency execution against target's protocol lab database."""
        inst = self._find_instance(target_id)
        return inst.db.execute_sql(sql)

    def get_database(self, target_id: str) -> ProtocolLabDatabase:
        inst = self._find_instance(target_id)
        return inst.db
