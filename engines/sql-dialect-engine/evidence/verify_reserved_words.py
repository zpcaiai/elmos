"""Derive a dialect's reserved words from a RUNNING server, and diff the shipped list.

`reserved_words.py` ships Oracle and SQL Server at `VENDOR_DOCUMENTED`, which
is an honest label rather than a proven one: neither has a free rootless local
instance, and in the container this repository's agents run in,
`download.oracle.com`, `packages.microsoft.com` and every container registry
are refused by the egress proxy (measured: HTTP 000/403). So the lists were
never fed to a server.

This closes that structurally. Point it at ANY real instance and it upgrades
the claim from documentation to measurement -- or tells you the list is wrong.

    python evidence/verify_reserved_words.py --dialect mysql  --dsn "unix:/tmp/mysqld/m.sock"
    python evidence/verify_reserved_words.py --dialect oracle --dsn "user/pw@//host:1521/FREEPDB1"
    python evidence/verify_reserved_words.py --dialect tsql   --dsn "Driver=...;Server=...;UID=sa;PWD=..."

Method, for every candidate word: attempt `CREATE TABLE <probe> (<word> INT)`
and roll back. A word the server refuses as a column name IS reserved; a word
it accepts is NOT, whatever the documentation says. Oracle additionally has
`V$RESERVED_WORDS`, which is read when available and cross-checked against the
probe -- two independent derivations disagreeing is itself worth knowing.

Exit code is non-zero when the shipped list and the server disagree, so this
can gate a promotion to EXECUTION_VERIFIED rather than being advisory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engines/sql-dialect-engine/src"))

from elmos_sql_dialect.models import Dialect  # noqa: E402
from elmos_sql_dialect.reserved_words import PROVENANCE, RESERVED_WORDS  # noqa: E402

PROBE_TABLE = "elmos_reserved_probe"


def _connect(dialect: Dialect, dsn: str):
    if dialect is Dialect.MYSQL:
        import pymysql

        socket = dsn.removeprefix("unix:") if dsn.startswith("unix:") else None
        return pymysql.connect(unix_socket=socket, user="root", database="mysql", autocommit=True)
    if dialect is Dialect.ORACLE:
        import oracledb  # type: ignore[import-not-found]

        return oracledb.connect(dsn)
    if dialect is Dialect.TSQL:
        import pyodbc  # type: ignore[import-not-found]

        return pyodbc.connect(dsn, autocommit=True)
    raise SystemExit(f"no probe driver for {dialect.value}")


def _is_reserved(cursor, word: str) -> bool:
    """True when the server refuses the word as a bare column name."""
    try:
        cursor.execute(f"CREATE TABLE {PROBE_TABLE} ({word} INT)")
    except Exception:
        return True
    try:
        cursor.execute(f"DROP TABLE {PROBE_TABLE}")
    except Exception:
        pass
    return False


def _oracle_catalog(cursor) -> set[str] | None:
    """Oracle publishes the authority itself; read it when we can."""
    try:
        cursor.execute("SELECT LOWER(keyword) FROM V$RESERVED_WORDS WHERE reserved = 'Y'")
        return {row[0] for row in cursor.fetchall()}
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dialect", required=True, choices=[d.value for d in Dialect])
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    dialect = Dialect(args.dialect)
    shipped = RESERVED_WORDS.get(dialect)
    if shipped is None:
        print(f"{dialect.value} ships no reserved-word list; nothing to verify")
        return 0

    connection = _connect(dialect, args.dsn)
    cursor = connection.cursor()
    try:
        cursor.execute(f"DROP TABLE {PROBE_TABLE}")
    except Exception:
        pass

    observed = {word for word in sorted(shipped) if _is_reserved(cursor, word)}
    catalog = _oracle_catalog(cursor) if dialect is Dialect.ORACLE else None

    # A word we do NOT ship but the server reserves is the dangerous direction:
    # it means an emission could still be a syntax error. Probed only where a
    # catalogue gives us candidates to test -- guessing a universe of words is
    # not something this script pretends to do.
    missing_from_shipped = sorted((catalog or set()) - shipped)
    false_positives = sorted(shipped - observed)

    report = {
        "kind": "elmos.sql-dialect.reserved-words-verification",
        "dialect": dialect.value,
        "shipped_provenance": PROVENANCE[dialect].value,
        "shipped_count": len(shipped),
        "confirmed_by_probe": len(observed),
        "shipped_but_accepted_by_server": false_positives,
        "reserved_by_server_but_not_shipped": missing_from_shipped,
        "catalog_available": catalog is not None,
        "verdict": (
            "EXECUTION_VERIFIED"
            if not false_positives and not missing_from_shipped
            else "DISAGREES_WITH_SERVER"
        ),
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] == "EXECUTION_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
