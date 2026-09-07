"""Execution-level evidence for certified-ddl-v1's regex CHECK, on real servers.

Everything executed here is the engine's OWN emitted output -- the DDL text is
taken from `translate_ddl`, never hand-written, so the evidence is about the
engine and not about a convenient hand-typed statement.

Three claims are under test, and the FIRST one is the load-bearing one. If a
plain MySQL `REGEXP` under the 8.0 default collation does NOT in fact accept
uppercase, then pinning `'c'` is unnecessary and the whole rationale for
admitting regex into the subset is wrong.

  C1  counterfactual: `col REGEXP 'pat'` under utf8mb4_0900_ai_ci ACCEPTS
      uppercase hex -- i.e. the naive emission is strictly weaker than the
      PostgreSQL source.
  C2  the engine's emission `REGEXP_LIKE(col, 'pat', 'c')` REJECTS it.
  C3  PostgreSQL's `~` (the source semantics) REJECTS it.

C1 && C2 && C3 is what "the translation preserves the constraint" means.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engines/sql-dialect-engine/src"))

from elmos_sql_dialect.engine import translate_ddl  # noqa: E402

PG = ["psql", "-h", "/tmp", "-p", "55432", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-t", "-A"]
MY = ["mysql", "--socket=/tmp/mysqld/m.sock", "-u", "root", "-N", "-B"]

SOURCE = "CREATE TABLE artifact_digest (h VARCHAR(64), CHECK (h ~ '^[0-9a-f]{64}$'))"
LOWER = "a" * 64          # inside the pattern
UPPER = "A" * 64          # differs from LOWER only by case
SHORT = "abc"             # wrong length -- must be rejected everywhere
results: list[dict] = []


def run(cmd: list[str], sql: str, db: str | None = None) -> tuple[bool, str]:
    argv = list(cmd) + (["-d", db] if db and cmd is PG else [])
    if cmd is MY and db:
        argv = list(cmd) + [db]
    proc = subprocess.run(argv, input=sql, capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def pg(sql: str, db: str = "postgres") -> tuple[bool, str]:
    return run(PG, sql, db)


def my(sql: str, db: str = "mysql") -> tuple[bool, str]:
    return run(MY, sql, db)


def record(claim: str, engine: str, statement: str, expected: str, ok: bool, detail: str) -> None:
    verdict = "ACCEPTED" if ok else "REJECTED"
    passed = verdict == expected
    results.append(
        {
            "claim": claim,
            "engine": engine,
            "statement": statement[:200],
            "expected": expected,
            "observed": verdict,
            "pass": passed,
            "detail": detail[:300] if not passed or verdict == "REJECTED" else "",
        }
    )
    mark = "PASS" if passed else "**FAIL**"
    print(f"[{mark}] {claim:<34} {engine:<10} expect {expected:<8} got {verdict}")


# ---------------------------------------------------------------------------
# what the engine actually emits
# ---------------------------------------------------------------------------
emitted = {}
for target in ("mysql", "oracle", "tsql"):
    report = translate_ddl(SOURCE, "postgres", target, statement_kind="TABLE")
    emitted[target] = report
    print(f"emit -> {target:8} {report['status']:8} {report['reasonCode'] or ''}")
    if report["emitted"]:
        print(f"         {report['emitted'].splitlines()[-2].strip()}")
print()

assert emitted["mysql"]["status"] == "PASSED", emitted["mysql"]
MYSQL_DDL = emitted["mysql"]["emitted"]

# ---------------------------------------------------------------------------
# C1 -- the counterfactual. Naive emission under the default collation.
# ---------------------------------------------------------------------------
pg("DROP DATABASE IF EXISTS elmos_ev;")
pg("CREATE DATABASE elmos_ev;")
my("DROP DATABASE IF EXISTS elmos_ev;")
my("CREATE DATABASE elmos_ev;")

ok, out = my("SELECT @@collation_server;")
print(f"MySQL server collation: {out}\n")

NAIVE = "CREATE TABLE naive (h VARCHAR(64), CHECK (h REGEXP '^[0-9a-f]{64}$'))"
ok, out = my(NAIVE, "elmos_ev")
assert ok, out
ok, out = my(f"INSERT INTO naive VALUES ('{LOWER}');", "elmos_ev")
record("C1 naive REGEXP / lowercase", "mysql", NAIVE, "ACCEPTED", ok, out)
ok, out = my(f"INSERT INTO naive VALUES ('{UPPER}');", "elmos_ev")
record("C1 naive REGEXP / UPPERCASE", "mysql", NAIVE, "ACCEPTED", ok, out)

# ---------------------------------------------------------------------------
# C2 -- the engine's emission, same server, same collation
# ---------------------------------------------------------------------------
ok, out = my(MYSQL_DDL, "elmos_ev")
assert ok, f"engine-emitted MySQL DDL did not execute: {out}"
print("\n[OK  ] engine-emitted MySQL DDL executed on a real server\n")
ok, out = my(f"INSERT INTO artifact_digest VALUES ('{LOWER}');", "elmos_ev")
record("C2 emitted 'c' / lowercase", "mysql", MYSQL_DDL, "ACCEPTED", ok, out)
ok, out = my(f"INSERT INTO artifact_digest VALUES ('{UPPER}');", "elmos_ev")
record("C2 emitted 'c' / UPPERCASE", "mysql", MYSQL_DDL, "REJECTED", ok, out)
ok, out = my(f"INSERT INTO artifact_digest VALUES ('{SHORT}');", "elmos_ev")
record("C2 emitted 'c' / wrong length", "mysql", MYSQL_DDL, "REJECTED", ok, out)

# ---------------------------------------------------------------------------
# C3 -- the source semantics on PostgreSQL
# ---------------------------------------------------------------------------
ok, out = pg(SOURCE, "elmos_ev")
assert ok, out
ok, out = pg(f"INSERT INTO artifact_digest VALUES ('{LOWER}');", "elmos_ev")
record("C3 source ~ / lowercase", "postgres", SOURCE, "ACCEPTED", ok, out)
ok, out = pg(f"INSERT INTO artifact_digest VALUES ('{UPPER}');", "elmos_ev")
record("C3 source ~ / UPPERCASE", "postgres", SOURCE, "REJECTED", ok, out)
ok, out = pg(f"INSERT INTO artifact_digest VALUES ('{SHORT}');", "elmos_ev")
record("C3 source ~ / wrong length", "postgres", SOURCE, "REJECTED", ok, out)

# ---------------------------------------------------------------------------
# DROP TABLE emission, executed for real on both
# ---------------------------------------------------------------------------
drop_my = translate_ddl("DROP TABLE artifact_digest", "postgres", "mysql", statement_kind="DROP")
assert drop_my["status"] == "PASSED", drop_my
ok, out = my(drop_my["emitted"], "elmos_ev")
record("DROP emitted executes", "mysql", drop_my["emitted"], "ACCEPTED", ok, out)

drop_pg = translate_ddl("DROP TABLE artifact_digest", "mysql", "postgres", statement_kind="DROP")
assert drop_pg["status"] == "PASSED", drop_pg
ok, out = pg(drop_pg["emitted"], "elmos_ev")
record("DROP emitted executes", "postgres", drop_pg["emitted"], "ACCEPTED", ok, out)

# ---------------------------------------------------------------------------
summary = {
    "kind": "elmos.sql-dialect.regex-check-execution-evidence",
    "date": "2026-08-26",
    "servers": {},
    "emitted": {k: {"status": v["status"], "reasonCode": v["reasonCode"], "sql": v["emitted"]}
                for k, v in emitted.items()},
    "results": results,
    "passed": sum(1 for r in results if r["pass"]),
    "total": len(results),
}
_, pgv = pg("SELECT version();")
_, myv = my("SELECT CONCAT(VERSION(), ' / ', @@collation_server);")
summary["servers"] = {"postgres": pgv.strip(), "mysql": myv.strip()}
Path(os.environ.get("OUT", "regex-check-execution-evidence.json")).write_text(
    json.dumps(summary, indent=2), encoding="utf-8"
)
print(f"\n{summary['passed']}/{summary['total']} execution assertions passed")
sys.exit(0 if summary["passed"] == summary["total"] else 1)
