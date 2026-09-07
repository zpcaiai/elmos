"""Execution-level evidence for the `IF NOT EXISTS` support table.

The support table in `emitter._IF_NOT_EXISTS_TABLE_SUPPORT` /
`_IF_NOT_EXISTS_INDEX_SUPPORT` decides which targets may carry the modifier and
which fail closed. A table like that asserted from documentation is exactly the
kind of premise this repository's own discipline says to distrust, so it is
measured here instead: every claim is executed against a real server.

Two claims per supported cell:
  1. the emitted statement runs;
  2. running it a SECOND time is a no-op -- which is the whole point of the
     modifier, and the property that would be silently lost if a target that
     cannot express it were emitted without it.

And one claim per refused cell: the server really does reject the spelling.
That is what justifies failing closed rather than dropping the modifier.

Servers used (both real, both local to this run):
  PostgreSQL 16.15   MySQL 8.0.46

MySQL, deliberately, NOT MariaDB: MariaDB accepts `CREATE INDEX IF NOT EXISTS`
and MySQL does not, so evidence gathered on MariaDB would give the wrong answer
for the `mysql` dialect.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import psycopg2
import pymysql

from elmos_sql_dialect.engine import translate_ddl

PG = dict(host="/tmp", port=55432, user="postgres", dbname="postgres")
MY = dict(unix_socket="/tmp/mysqlrun/m.sock", user="root", database="mysql")


def pg_exec(statements: list[str]) -> tuple[bool, str]:
    connection = psycopg2.connect(**PG)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        return True, ""
    except Exception as error:
        return False, f"{type(error).__name__}: {str(error).strip()[:160]}"
    finally:
        connection.close()


def my_exec(statements: list[str]) -> tuple[bool, str]:
    connection = pymysql.connect(**MY)
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        connection.commit()
        return True, ""
    except Exception as error:
        return False, f"{type(error).__name__}: {str(error).strip()[:160]}"
    finally:
        connection.close()


EXEC = {"postgres": pg_exec, "mysql": my_exec}


def server_version() -> dict[str, str]:
    connection = psycopg2.connect(**PG)
    with connection.cursor() as cursor:
        cursor.execute("select version()")
        pg = cursor.fetchone()[0]
    connection.close()
    connection = pymysql.connect(**MY)
    with connection.cursor() as cursor:
        cursor.execute("select version()")
        my = cursor.fetchone()[0]
    connection.close()
    return {"postgres": pg, "mysql": my}


def main() -> int:
    results: list[dict[str, Any]] = []

    # ---- supported cells: emitted statement runs, and re-runs as a no-op ----
    supported_cases = [
        ("postgres", "TABLE",
         "CREATE TABLE IF NOT EXISTS ev_orders (id BIGINT PRIMARY KEY, total INT NOT NULL)",
         ["DROP TABLE IF EXISTS ev_orders"]),
        ("mysql", "TABLE",
         "CREATE TABLE IF NOT EXISTS ev_orders (id BIGINT PRIMARY KEY, total INT NOT NULL)",
         ["DROP TABLE IF EXISTS ev_orders"]),
        ("postgres", "INDEX",
         "CREATE INDEX IF NOT EXISTS ev_idx_total ON ev_orders (total)",
         ["DROP TABLE IF EXISTS ev_orders",
          "CREATE TABLE ev_orders (id BIGINT PRIMARY KEY, total INT NOT NULL)"]),
    ]
    for target, kind, source_sql, setup in supported_cases:
        source_dialect = "mysql" if target == "postgres" else "postgres"
        report = translate_ddl(source_sql, source_dialect, target, statement_kind=kind)
        record: dict[str, Any] = {
            "target": target,
            "statement_kind": kind,
            "engine_status": report["status"],
            "emitted": report.get("emitted"),
        }
        if report["status"] == "PASSED":
            runner = EXEC[target]
            runner(setup)
            first_ok, first_error = runner([report["emitted"]])
            second_ok, second_error = runner([report["emitted"]])
            record["executed_first"] = "PASSED" if first_ok else f"FAILED {first_error}"
            record["executed_again_is_noop"] = "PASSED" if second_ok else f"FAILED {second_error}"
            runner(["DROP TABLE IF EXISTS ev_orders"])
        results.append(record)

    # ---- refused cells: prove the server really rejects the spelling --------
    refusal_cases = [
        ("mysql", "INDEX", "CREATE INDEX IF NOT EXISTS ev_idx_total ON ev_orders (total)"),
    ]
    refusals: list[dict[str, Any]] = []
    for target, kind, raw in refusal_cases:
        runner = EXEC[target]
        runner(["DROP TABLE IF EXISTS ev_orders",
                "CREATE TABLE ev_orders (id BIGINT PRIMARY KEY, total INT NOT NULL)"])
        accepted, error = runner([raw])
        runner(["DROP TABLE IF EXISTS ev_orders"])
        source_dialect = "postgres"
        report = translate_ddl(raw, source_dialect, target, statement_kind=kind)
        refusals.append({
            "target": target,
            "statement_kind": kind,
            "server_accepts_the_spelling": accepted,
            "server_error": error,
            "engine_status": report["status"],
            "engine_reason_code": report["reasonCode"],
            "verdict": (
                "CONSISTENT: server rejects it and the engine fails closed"
                if not accepted and report["status"] == "BLOCKED"
                else "INCONSISTENT -- support table is wrong"
            ),
        })

    # ---- targets with no local server: state it, do not guess --------------
    not_executable = {
        "oracle": "no freely licensed root-less local server; refused by the support table on the "
                  "separate ground that Dialect carries no version and IF NOT EXISTS only exists "
                  "from Oracle 23ai",
        "tsql": "no freely licensed root-less local server; refused because SQL Server has no "
                "CREATE ... IF NOT EXISTS in any shipping version",
    }

    evidence = {
        "kind": "elmos.sql-dialect-if-not-exists-execution-evidence",
        "schema_version": "1.0.0",
        "profile": "certified-ddl-v1",
        "servers": server_version(),
        "supported_cells": results,
        "refused_cells_verified_against_the_server": refusals,
        "targets_without_a_local_server": not_executable,
        "execution_status": "LOCAL_EXECUTED",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "limitations": [
            "Postgres and MySQL evidence is real execution on real servers of those exact "
            "versions. Oracle and SQL Server were NOT executed -- they are refused by the "
            "support table, so no emitted statement exists to run.",
            "This proves the modifier renders and re-runs as a no-op. It does not certify the "
            "route; certification needs the independent verifier and external evidence.",
        ],
    }
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
