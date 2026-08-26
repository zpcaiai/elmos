"""Are the two refusals this change added actually justified, or over-cautious?

A refusal nobody can justify gets patched away by the next person. Both are
therefore demonstrated against real servers rather than argued.

  R1  CERTIFIED_DDL_COLLATION_DEPENDENT_REGEX
      A MySQL `REGEXP` with no match parameter is refused because its case
      sensitivity comes from the column collation. Demonstrated by running the
      SAME statement under two collations and observing two different verdicts.

  R2  CERTIFIED_DDL_UNSUPPORTED_CHECK_MATCH_PARAMETER
      `'i'` is refused rather than translated. Demonstrated by showing that
      emitting it as `'c'` -- which is what the engine would have done before
      the gate existed -- rejects a row the source accepts.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engines/sql-dialect-engine/src"))

from elmos_sql_dialect.engine import translate_ddl  # noqa: E402

MY = ["mysql", "--socket=/tmp/mysqld/m.sock", "-u", "root", "-N", "-B"]
HEX = "a" * 64
UPPER = "A" * 64
findings: list[dict] = []


def my(sql: str, db: str = "elmos_rj") -> tuple[bool, str]:
    p = subprocess.run(MY + [db], input=sql, capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


subprocess.run(MY + ["mysql"], input="DROP DATABASE IF EXISTS elmos_rj; CREATE DATABASE elmos_rj;",
               capture_output=True, text=True)

# ---------------------------------------------------------------------------
# R1 -- same statement, two collations, two behaviours
# ---------------------------------------------------------------------------
print("R1  a bare MySQL REGEXP under two collations")
observed = {}
for collation in ("utf8mb4_0900_ai_ci", "utf8mb4_0900_as_cs"):
    table = "ci" if collation.endswith("ai_ci") else "cs"
    ddl = (f"CREATE TABLE {table} (v VARCHAR(64) COLLATE {collation}, "
           f"CHECK (v REGEXP '^[0-9a-f]{{64}}$'))")
    ok, out = my(ddl)
    assert ok, out
    accepted, detail = my(f"INSERT INTO {table} VALUES ('{UPPER}');")
    observed[collation] = "ACCEPTED" if accepted else "REJECTED"
    print(f"    {collation:<22} uppercase -> {observed[collation]}")

r1_justified = len(set(observed.values())) > 1
findings.append({
    "refusal": "CERTIFIED_DDL_COLLATION_DEPENDENT_REGEX",
    "observed": observed,
    "justified": r1_justified,
    "why": ("the identical statement means different things under two collations, so the "
            "statement alone does not determine its semantics"),
})
print(f"    -> refusal justified: {r1_justified}\n")

# the engine must actually refuse it
report = translate_ddl(
    "CREATE TABLE t (h VARCHAR(64), CHECK (h REGEXP '^[0-9a-f]{64}$'))",
    "mysql", "postgres", statement_kind="TABLE")
findings.append({
    "refusal": "CERTIFIED_DDL_COLLATION_DEPENDENT_REGEX",
    "engine_status": report["status"],
    "engine_reason_code": report["reasonCode"],
    "enforced": report["reasonCode"] == "CERTIFIED_DDL_COLLATION_DEPENDENT_REGEX",
})
print(f"    engine verdict: {report['status']} {report['reasonCode']}\n")

# ---------------------------------------------------------------------------
# R2 -- what accepting 'i' and emitting 'c' would have cost
# ---------------------------------------------------------------------------
print("R2  a case-INsensitive source, translated naively to 'c'")
ok, out = my("CREATE TABLE src (v VARCHAR(64), CHECK (REGEXP_LIKE(v, '^[0-9a-f]{64}$', 'i')))")
assert ok, out
src_accepts, _ = my(f"INSERT INTO src VALUES ('{UPPER}');")
ok, out = my("CREATE TABLE naive_c (v VARCHAR(64), CHECK (REGEXP_LIKE(v, '^[0-9a-f]{64}$', 'c')))")
assert ok, out
naive_accepts, _ = my(f"INSERT INTO naive_c VALUES ('{UPPER}');")
print(f"    source  'i' uppercase -> {'ACCEPTED' if src_accepts else 'REJECTED'}")
print(f"    naive   'c' uppercase -> {'ACCEPTED' if naive_accepts else 'REJECTED'}")

r2_justified = src_accepts and not naive_accepts
findings.append({
    "refusal": "CERTIFIED_DDL_UNSUPPORTED_CHECK_MATCH_PARAMETER",
    "source_i_accepts_uppercase": src_accepts,
    "naive_c_accepts_uppercase": naive_accepts,
    "justified": r2_justified,
    "why": ("translating 'i' as 'c' produces a STRICTER target constraint that rejects rows "
            "the source accepts -- a migration that silently loses data"),
})
report = translate_ddl(
    "CREATE TABLE t (h VARCHAR(64), CHECK (REGEXP_LIKE(h, '^[0-9a-f]{64}$', 'i')))",
    "oracle", "postgres", statement_kind="TABLE")
findings.append({
    "refusal": "CERTIFIED_DDL_UNSUPPORTED_CHECK_MATCH_PARAMETER",
    "engine_status": report["status"],
    "engine_reason_code": report["reasonCode"],
    "enforced": report["reasonCode"] == "CERTIFIED_DDL_UNSUPPORTED_CHECK_MATCH_PARAMETER",
})
print(f"    -> refusal justified: {r2_justified}")
print(f"    engine verdict: {report['status']} {report['reasonCode']}")

summary = {
    "kind": "elmos.sql-dialect.refusal-justification-evidence",
    "date": "2026-08-26",
    "findings": findings,
    "all_justified": all(f.get("justified", True) and f.get("enforced", True) for f in findings),
}
Path(os.environ.get("OUT", "refusal-justification-evidence.json")).write_text(
    json.dumps(summary, indent=2), encoding="utf-8")
print(f"\nall refusals justified AND enforced: {summary['all_justified']}")
sys.exit(0 if summary["all_justified"] else 1)
