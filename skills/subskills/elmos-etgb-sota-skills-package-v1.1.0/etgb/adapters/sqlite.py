from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from etgb.normalize import first_difference, normalize


def _rows(conn: sqlite3.Connection, query: str) -> list[list[Any]]:
    cur = conn.execute(query)
    return [list(row) for row in cur.fetchall()]


def _schema(conn: sqlite3.Connection) -> list[list[Any]]:
    return _rows(conn, "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")


def _table_state(conn: sqlite3.Connection) -> dict[str, Any]:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    state: dict[str, Any] = {}
    for table in tables:
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        order = ",".join(f'"{c}"' for c in cols)
        state[table] = {"columns": cols, "rows": [list(r) for r in conn.execute(f'SELECT * FROM "{table}" ORDER BY {order}')]} if cols else {"columns": [], "rows": []}
    return state


def _execute_script(conn: sqlite3.Connection, path: Path) -> None:
    conn.executescript(path.read_text(encoding="utf-8"))
    conn.commit()


def execute_sqlite_differential(case: dict[str, Any], root: Path) -> tuple[str, list[dict[str, Any]], dict[str, Any], bool]:
    spec = case["execution"]
    seed_path = root / spec["seed_sql"]
    source_path = root / spec["source_sql"]
    target_path = root / spec["target_sql"]
    with tempfile.TemporaryDirectory(prefix="etgb-sql-") as tmp:
        source_db = Path(tmp) / "source.db"
        target_db = Path(tmp) / "target.db"
        source_conn = sqlite3.connect(source_db)
        target_conn = sqlite3.connect(target_db)
        try:
            for conn in (source_conn, target_conn):
                conn.execute("PRAGMA foreign_keys=ON")
                _execute_script(conn, seed_path)
            _execute_script(source_conn, source_path)
            _execute_script(target_conn, target_path)
            source_results = {q: _rows(source_conn, q) for q in spec["assertion_queries"]}
            target_results = {q: _rows(target_conn, q) for q in spec["assertion_queries"]}
            source_state = _table_state(source_conn)
            target_state = _table_state(target_conn)
            result_diff = first_difference(normalize(source_results), normalize(target_results))
            state_diff = first_difference(normalize(source_state), normalize(target_state))
            # DDL textual forms can differ; compare object names/types, not raw SQL text.
            source_schema = [[r[0], r[1], r[2]] for r in _schema(source_conn)]
            target_schema = [[r[0], r[1], r[2]] for r in _schema(target_conn)]
            schema_diff = first_difference(normalize(source_schema), normalize(target_schema))
            passed = result_diff is None and state_diff is None and schema_diff is None
            oracles = [
                {"type": "result-set-equivalence", "passed": result_diff is None, "first_difference": result_diff},
                {"type": "database-state-equivalence", "passed": state_diff is None, "first_difference": state_diff},
                {"type": "schema-object-equivalence", "passed": schema_diff is None, "first_difference": schema_diff},
            ]
            evidence = {
                "source_results": source_results, "target_results": target_results,
                "source_state": source_state, "target_state": target_state,
                "source_schema": source_schema, "target_schema": target_schema,
            }
            return ("passed" if passed else "failed", oracles, evidence, not passed)
        finally:
            source_conn.close()
            target_conn.close()
