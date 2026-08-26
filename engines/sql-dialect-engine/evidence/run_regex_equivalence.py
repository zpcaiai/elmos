"""Behavioural equivalence for every regex pattern the corpus actually uses.

Spot-checking one pattern proves the mechanism. This proves the CLAIM: for each
of the 8 distinct patterns found in the 97-file corpus, the PostgreSQL source
constraint and the engine's MySQL emission accept and reject exactly the same
strings. Any row where the two verdicts differ is a translation defect.

The DDL executed on both servers is the engine's own output.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engines/sql-dialect-engine/src"))

from elmos_sql_dialect.engine import translate_ddl  # noqa: E402

HEX64 = "a" * 64
# (pattern, [probe strings]) -- probes chosen to straddle each pattern's edges,
# and every pattern gets a case-flipped probe because case is the divergence
# this profile pins.
CASES: list[tuple[str, list[str]]] = [
    ("^[0-9a-f]{64}$", [HEX64, HEX64.upper(), "a" * 63, "a" * 65, "g" * 64, ""]),
    ("^sha256:[0-9a-f]{64}$", [f"sha256:{HEX64}", f"SHA256:{HEX64}", f"sha256:{HEX64.upper()}", HEX64]),
    ("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", ["a", "A", "a.b_c:d-e", "_leading", "a" * 128, "a" * 129, ""]),
    ("^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$", ["z", "a" * 64, "a" * 65, "-nope"]),
    ("^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$",
     [f"repo/img:5000/x@sha256:{HEX64}", f"REPO/img@sha256:{HEX64}", f"repo@sha256:{HEX64.upper()}"]),
    ("^[0-9]+$", ["0", "1234567890", "12a", "", " 1"]),
    ("^[0-9a-f]{40}$", ["b" * 40, "B" * 40, "b" * 39]),
    ("@sha256:[0-9a-f]{64}$", [f"x@sha256:{HEX64}", f"x@SHA256:{HEX64}", f"@sha256:{HEX64}"]),
]

PG = ["psql", "-h", "/tmp", "-p", "55432", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-t", "-A", "-d"]
MY = ["mysql", "--socket=/tmp/mysqld/m.sock", "-u", "root", "-N", "-B"]


def pg(sql: str, db: str = "elmos_eq") -> tuple[bool, str]:
    p = subprocess.run(PG + [db], input=sql, capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def my(sql: str, db: str = "elmos_eq") -> tuple[bool, str]:
    p = subprocess.run(MY + [db], input=sql, capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


subprocess.run(PG[:-1] + ["-d", "postgres"], input="DROP DATABASE IF EXISTS elmos_eq; CREATE DATABASE elmos_eq;",
               capture_output=True, text=True)
subprocess.run(MY + ["mysql"], input="DROP DATABASE IF EXISTS elmos_eq; CREATE DATABASE elmos_eq;",
               capture_output=True, text=True)

rows: list[dict] = []
divergences: list[dict] = []
for index, (pattern, probes) in enumerate(CASES):
    table = f"p{index}"
    source = f"CREATE TABLE {table} (v VARCHAR(255), CHECK (v ~ '{pattern}'))"
    report = translate_ddl(source, "postgres", "mysql", statement_kind="TABLE")
    if report["status"] != "PASSED":
        divergences.append({"pattern": pattern, "stage": "emit", "reason": report["reasonCode"]})
        print(f"[EMIT-BLOCKED] {pattern}  {report['reasonCode']}")
        continue

    ok_pg, out_pg = pg(source)
    ok_my, out_my = my(report["emitted"])
    if not (ok_pg and ok_my):
        divergences.append({"pattern": pattern, "stage": "ddl",
                            "postgres_ok": ok_pg, "mysql_ok": ok_my,
                            "detail": (out_pg or out_my)[:200]})
        print(f"[DDL-FAILED]   {pattern}  pg={ok_pg} mysql={ok_my}")
        continue

    for probe in probes:
        a_pg, _ = pg(f"INSERT INTO {table} VALUES ({lit(probe)});")
        a_my, _ = my(f"INSERT INTO {table} VALUES ({lit(probe)});")
        agree = a_pg == a_my
        rows.append({
            "pattern": pattern,
            "probe": probe if len(probe) <= 24 else f"{probe[:12]}...({len(probe)} chars)",
            "postgres": "ACCEPTED" if a_pg else "REJECTED",
            "mysql": "ACCEPTED" if a_my else "REJECTED",
            "agree": agree,
        })
        if not agree:
            divergences.append(rows[-1])

    verdicts = [r for r in rows if r["pattern"] == pattern]
    disagreed = sum(1 for r in verdicts if not r["agree"])
    mark = "PASS" if disagreed == 0 else f"**{disagreed} DIVERGENT**"
    print(f"[{mark:>16}] {len(verdicts):>2} probes  {pattern[:58]}")

summary = {
    "kind": "elmos.sql-dialect.regex-equivalence-execution-evidence",
    "date": "2026-08-26",
    "patterns": len(CASES),
    "probes": len(rows),
    "agreements": sum(1 for r in rows if r["agree"]),
    "divergences": divergences,
    "rows": rows,
}
Path(os.environ.get("OUT", "regex-equivalence-evidence.json")).write_text(
    json.dumps(summary, indent=2), encoding="utf-8")
print(f"\n{summary['agreements']}/{summary['probes']} probes agree across PostgreSQL and MySQL"
      f"; {len(divergences)} divergence(s)")
sys.exit(0 if not divergences else 1)
