"""Schema-only blocker table for certified-ddl-v1 / certified-alter-v1.

The headline coverage number hides WHICH constructs to widen next. This groups
every OUT_OF_SUBSET finding on a *schema* statement by (reason_code, reason),
so the roadmap is driven by distinct constructs rather than by how often one
copy-pasted idiom appears.
"""

from __future__ import annotations
import argparse
import contextlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path

from elmos_sql_dialect.models import Dialect
from elmos_sql_dialect.scan import scan_repository

DDL_KINDS = frozenset({"Create", "Alter", "Drop", "Index", "Comment", "Truncate"})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--corpus", action="append", required=True, metavar="NAME=PATH=DIALECT"
    )
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    per_reason: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"count": 0, "kinds": Counter(), "corpora": Counter(), "examples": []}
    )
    code_totals: Counter[str] = Counter()
    kind_blocked: Counter[str] = Counter()
    schema_total = schema_in = 0

    for raw in args.corpus:
        name, path, dialect_name = raw.split("=", 2)
        dialect = Dialect(dialect_name)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            report = scan_repository(
                Path(path).resolve(strict=True),
                dialect,
                examples_per_blocker=5,
                include_all_findings=True,
            )
        for f in report.findings:
            if f.statement_kind not in DDL_KINDS:
                continue
            schema_total += 1
            if f.status == "IN_SUBSET":
                schema_in += 1
                continue
            code = f.reason_code or "UNKNOWN"
            reason = (f.reason or "").strip()
            code_totals[code] += 1
            kind_blocked[f.statement_kind or "?"] += 1
            slot = per_reason[(code, reason)]
            slot["count"] += 1
            slot["kinds"][f.statement_kind or "?"] += 1
            slot["corpora"][name] += 1
            if len(slot["examples"]) < 2:
                slot["examples"].append(f.excerpt[:200])

    rows = []
    for (code, reason), slot in per_reason.items():
        rows.append(
            {
                "reason_code": code,
                "reason": reason,
                "count": slot["count"],
                "statement_kinds": dict(slot["kinds"]),
                "corpora": dict(slot["corpora"]),
                "examples": slot["examples"],
            }
        )
    rows.sort(key=lambda r: (-r["count"], r["reason_code"], r["reason"]))

    by_code = []
    for code, total in code_totals.most_common():
        distinct = sum(1 for (c, _r) in per_reason if c == code)
        by_code.append(
            {
                "reason_code": code,
                "schema_statements_blocked": total,
                "distinct_reasons": distinct,
                # statements unlocked per distinct construct implemented -- the
                # leverage number. Ranking by raw count alone misdirects the roadmap.
                "leverage": round(total / distinct, 1),
            }
        )

    out = {
        "kind": "elmos.sql-dialect.schema-blocker-table",
        "schema_statements": schema_total,
        "schema_in_subset": schema_in,
        "coverage_schema_only": round(schema_in / schema_total, 4)
        if schema_total
        else 0.0,
        "schema_blocked": schema_total - schema_in,
        "blocked_by_statement_kind": dict(kind_blocked.most_common()),
        "by_reason_code": by_code,
        "by_distinct_reason": rows,
    }
    args.output.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"schema {schema_in}/{schema_total} = {out['coverage_schema_only']:.4f}")
    print(f"{'reason_code':46} {'blocked':>8} {'distinct':>9} {'leverage':>9}")
    for r in by_code:
        print(
            f"{r['reason_code']:46} {r['schema_statements_blocked']:>8} {r['distinct_reasons']:>9} {r['leverage']:>9}"
        )
    print("\nblocked by statement kind:", out["blocked_by_statement_kind"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
