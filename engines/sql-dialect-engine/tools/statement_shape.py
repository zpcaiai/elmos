"""What the blocked schema statements ACTUALLY are.

`ScanFinding.excerpt` is a trimmed first line, so re-parsing it misclassifies
most statements. This mirrors `scan_repository`'s traversal but keeps the
parsed statement object, and reports CREATE/DROP by their `kind` argument.
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
from elmos_sql_dialect.scan import _classify, discover_sql_files
from elmos_sql_dialect.statement_splitter import looks_like_client_directive, split_statements

DDL_TYPES = ("Create", "Alter", "Drop", "Index", "Comment", "Truncate")


def shape(node: exp.Expression) -> str:
    name = type(node).__name__
    if isinstance(node, (exp.Create, exp.Drop)):
        kind = node.args.get("kind")
        return f"{name.upper()} {str(kind).upper() if kind else 'UNKNOWN'}"
    return name.upper()


def statements_of(path: Path, dialect: Dialect):
    text = path.read_text(encoding="utf-8")
    try:
        for s in sqlglot.parse(text, read=dialect.value):
            if s is not None:
                yield s
        return
    except Exception:
        pass
    for raw in split_statements(text, dialect=dialect):
        if looks_like_client_directive(raw.text, dialect):
            continue
        try:
            parsed = [
                s for s in sqlglot.parse(raw.text, read=dialect.value) if s is not None
            ]
        except Exception:
            continue
        if len(parsed) == 1:
            yield parsed[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="append", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    blocked: Counter[str] = Counter()
    admitted: Counter[str] = Counter()
    codes_per_shape: dict[str, Counter[str]] = {}
    corpora_per_shape: dict[str, Counter[str]] = {}
    examples: dict[str, str] = {}

    for raw in args.corpus:
        name, path, dialect_name = raw.split("=", 2)
        dialect = Dialect(dialect_name)
        root = Path(path).resolve(strict=True)
        for file in discover_sql_files(root):
            for statement in statements_of(file, dialect):
                if type(statement).__name__ not in DDL_TYPES:
                    continue
                with contextlib.redirect_stderr(io.StringIO()):
                    status, code, _reason = _classify(statement, dialect)
                key = shape(statement)
                if status == "IN_SUBSET":
                    admitted[key] += 1
                    continue
                blocked[key] += 1
                codes_per_shape.setdefault(key, Counter())[code or "UNKNOWN"] += 1
                corpora_per_shape.setdefault(key, Counter())[name] += 1
                examples.setdefault(key, statement.sql(dialect=dialect.value)[:160])

    rows = []
    for key, count in blocked.most_common():
        rows.append(
            {
                "statement": key,
                "blocked": count,
                "admitted": admitted.get(key, 0),
                "reason_codes": dict(codes_per_shape[key].most_common()),
                "corpora": dict(corpora_per_shape[key].most_common()),
                "example": examples.get(key, ""),
            }
        )
    out = {
        "kind": "elmos.sql-dialect.blocked-statement-shapes",
        "blocked_total": sum(blocked.values()),
        "admitted_total": sum(admitted.values()),
        "shapes": rows,
    }
    args.output.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"admitted {out['admitted_total']}  blocked {out['blocked_total']}")
    print(f"{'statement shape':26} {'blocked':>8} {'admitted':>9}  top reason codes")
    for r in rows:
        top = ", ".join(f"{k}={v}" for k, v in list(r["reason_codes"].items())[:2])
        print(f"{r['statement']:26} {r['blocked']:>8} {r['admitted']:>9}  {top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
