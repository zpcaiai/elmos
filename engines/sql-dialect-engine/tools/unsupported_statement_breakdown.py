"""Sub-classify CERTIFIED_DDL_UNSUPPORTED_STATEMENT.

The engine emits ONE reason string ("only accepts a single CREATE TABLE
statement") for every unsupported statement kind, so the distinct-reason
column collapses ~680 statements onto 2 reasons and reports a leverage of 340.
That number is an artefact of the message, not of the work. This re-parses each
blocked statement and reports what it actually is.
"""

from __future__ import annotations
import argparse
import contextlib
import io
import json
from collections import Counter
from pathlib import Path

import sqlglot
from sqlglot import exp

from elmos_sql_dialect.models import Dialect
from elmos_sql_dialect.scan import scan_repository

DDL_KINDS = frozenset({"Create", "Alter", "Drop", "Index", "Comment", "Truncate"})


def label(node: exp.Expression) -> str:
    if isinstance(node, exp.Create):
        return f"CREATE {str(node.args.get('kind') or 'UNKNOWN').upper()}"
    if isinstance(node, exp.Drop):
        return f"DROP {str(node.args.get('kind') or 'UNKNOWN').upper()}"
    return type(node).__name__.upper()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="append", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    kinds: Counter[str] = Counter()
    per_corpus: dict[str, Counter[str]] = {}
    examples: dict[str, str] = {}

    for raw in args.corpus:
        name, path, dialect_name = raw.split("=", 2)
        dialect = Dialect(dialect_name)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            report = scan_repository(
                Path(path).resolve(strict=True),
                dialect,
                examples_per_blocker=1,
                include_all_findings=True,
            )
        local: Counter[str] = Counter()
        for f in report.findings:
            if f.status == "IN_SUBSET" or f.statement_kind not in DDL_KINDS:
                continue
            if f.reason_code != "CERTIFIED_DDL_UNSUPPORTED_STATEMENT":
                continue
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    parsed = sqlglot.parse_one(f.excerpt, read=dialect.value)
            except Exception:
                parsed = None
            name_ = (
                label(parsed) if parsed is not None else f"UNPARSED:{f.statement_kind}"
            )
            kinds[name_] += 1
            local[name_] += 1
            examples.setdefault(name_, f.excerpt[:180])
        per_corpus[name] = local

    out = {
        "kind": "elmos.sql-dialect.unsupported-statement-breakdown",
        "total": sum(kinds.values()),
        "by_actual_statement": [
            {"statement": k, "count": v, "example": examples.get(k, "")}
            for k, v in kinds.most_common()
        ],
        "by_corpus": {k: dict(v.most_common()) for k, v in per_corpus.items()},
    }
    args.output.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"total UNSUPPORTED_STATEMENT on schema statements: {out['total']}")
    print(f"{'actual statement':34} {'count':>6}")
    for row in out["by_actual_statement"]:
        print(f"{row['statement']:34} {row['count']:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
