"""What do the regex CHECK constraints in the corpus actually look like?

Deciding whether regex belongs in the subset needs the patterns, not the count.
"""

from __future__ import annotations
import argparse
import contextlib
import io
import json
import re
from collections import Counter
from pathlib import Path

import sqlglot
from sqlglot import exp

from elmos_sql_dialect.models import Dialect
from elmos_sql_dialect.scan import discover_sql_files
from elmos_sql_dialect.statement_splitter import looks_like_client_directive, split_statements

# Constructs that do NOT mean the same thing in PostgreSQL ARE, MySQL 8 ICU and
# Oracle POSIX. Anything matching these cannot be admitted on pattern grounds.
NON_PORTABLE = [
    (r"\\[dwsDWSbB]", "perl-class-escape"),
    (r"\(\?", "group-extension (lookaround/non-capturing/flags)"),
    (r"\\[0-9]", "backreference"),
    (r"\[\[:", "posix-named-class"),
    (r"\\[pP]\{", "unicode-property"),
]


def scan_patterns(root: Path, dialect: Dialect) -> list[str]:
    found: list[str] = []
    for path in discover_sql_files(root):
        text = path.read_text(encoding="utf-8")
        try:
            statements = list(sqlglot.parse(text, read=dialect.value))
        except Exception:
            statements = []
            for raw in split_statements(text, dialect=dialect):
                if looks_like_client_directive(raw.text, dialect):
                    continue
                try:
                    statements.extend(sqlglot.parse(raw.text, read=dialect.value))
                except Exception:
                    continue
        for statement in statements:
            if statement is None:
                continue
            for node in statement.find_all(exp.RegexpLike):
                literal = node.expression
                if isinstance(literal, exp.Literal) and literal.is_string:
                    found.append(literal.this)
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="append", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    patterns: Counter[str] = Counter()
    for raw in args.corpus:
        name, path, dialect_name = raw.split("=", 2)
        with contextlib.redirect_stderr(io.StringIO()):
            for pattern in scan_patterns(
                Path(path).resolve(strict=True), Dialect(dialect_name)
            ):
                patterns[pattern] += 1

    portable, blocked = [], []
    for pattern, count in patterns.most_common():
        hits = [why for rx, why in NON_PORTABLE if re.search(rx, pattern)]
        (blocked if hits else portable).append(
            {"pattern": pattern, "count": count, "non_portable": hits}
        )
    out = {
        "kind": "elmos.sql-dialect.regex-check-survey",
        "distinct_patterns": len(patterns),
        "total_occurrences": sum(patterns.values()),
        "portable_core": {
            "distinct": len(portable),
            "occurrences": sum(r["count"] for r in portable),
        },
        "non_portable": {
            "distinct": len(blocked),
            "occurrences": sum(r["count"] for r in blocked),
        },
        "portable_patterns": portable,
        "non_portable_patterns": blocked,
    }
    args.output.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"distinct patterns {out['distinct_patterns']}, occurrences {out['total_occurrences']}"
    )
    print(f"  portable core : {out['portable_core']}")
    print(f"  non-portable  : {out['non_portable']}")
    print("\ntop portable:")
    for r in portable[:12]:
        print(f"  {r['count']:>4}  {r['pattern'][:90]}")
    print("\nnon-portable:")
    for r in blocked[:12]:
        print(
            f"  {r['count']:>4}  {r['pattern'][:70]}   <- {', '.join(r['non_portable'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
