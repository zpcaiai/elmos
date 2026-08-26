"""How much of what the scan ADMITS can actually be emitted to every dialect?

`scan_repository` reports a SOURCE-SIDE upper bound: a statement is IN_SUBSET
when this engine's parser accepts it. Emission can still refuse -- SQL Server
has no regex predicate, Oracle has no ON UPDATE clause, and so on. The single
coverage percentage therefore overstates what a customer can actually
translate, and nothing in the repository measured the gap.

This does: every admitted statement is really emitted to all three other
dialects, and the result is reported per target and as an all-four intersection.
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

from elmos_sql_dialect import emitter, parser
from elmos_sql_dialect.advanced import (
    emit_comment,
    emit_privilege,
    emit_procedure,
    emit_table_function,
    emit_trigger,
    emit_view,
    parse_comment,
    parse_create_view,
    parse_privilege,
    parse_procedure,
    parse_table_function,
    parse_trigger,
)
from elmos_sql_dialect.models import Dialect, DialectError
from elmos_sql_dialect.routine import emit_create_function, parse_create_routine
from elmos_sql_dialect.scan import _classify, discover_sql_files
from elmos_sql_dialect.statement_splitter import split_statements

DDL_TYPES = ("Create", "Alter", "Drop", "Index", "Comment", "Grant", "Revoke", "Truncate")
ALL_DIALECTS = (Dialect.POSTGRES, Dialect.MYSQL, Dialect.ORACLE, Dialect.TSQL)


def statements_of(path: Path, dialect: Dialect):
    text = path.read_text(encoding="utf-8")
    try:
        for statement in sqlglot.parse(text, read=dialect.value):
            if statement is not None:
                yield statement
        return
    except Exception:  # noqa: S110 - bounded parser fallback for mixed-dialect corpus files
        pass
    for raw in split_statements(text):
        if raw.text.lstrip().startswith("\\"):
            continue
        try:
            parsed = [
                s for s in sqlglot.parse(raw.text, read=dialect.value) if s is not None
            ]
        except Exception:  # noqa: S112 - one malformed recovered chunk must not hide later units
            continue
        if len(parsed) == 1:
            yield parsed[0]


def emit_to(statement: exp.Expression, source: Dialect, target: Dialect) -> str | None:
    """Emitted SQL, or None with the refusal recorded by the caller."""
    if isinstance(statement, exp.Create):
        kind = str(statement.args.get("kind", "")).upper()
        if kind == "TABLE":
            return emitter.emit_create_table(
                parser.parse_create_table(statement, source), target
            )
        if kind == "SCHEMA":
            return emitter.emit_create_schema(
                parser.parse_create_schema(statement, source), target
            )
        if kind == "INDEX":
            return emitter.emit_create_index(
                parser.parse_create_index(statement, source), target
            )
        if kind == "VIEW":
            return emit_view(parse_create_view(statement, source), target)
        if kind == "FUNCTION":
            try:
                return emit_table_function(parse_table_function(statement, source), target)
            except DialectError as exc:
                if exc.code != "CERTIFIED_ROUTINE_NOT_TABLE_FUNCTION":
                    raise
                return emit_create_function(parse_create_routine(statement, source), target)
        if kind == "PROCEDURE":
            return emit_procedure(parse_procedure(statement, source), target)
        if kind == "TRIGGER":
            return emit_trigger(parse_trigger(statement, source), target)
    if isinstance(statement, exp.Alter):
        return emitter.emit_alter_table(
            parser.parse_alter_table(statement, source), target
        )
    if isinstance(statement, exp.Drop):
        return emitter.emit_drop_table(
            parser.parse_drop_table(statement, source), target
        )
    if isinstance(statement, exp.Comment):
        return emit_comment(parse_comment(statement, source), target)
    if isinstance(statement, exp.Grant | exp.Revoke):
        return emit_privilege(parse_privilege(statement, source), target)
    raise DialectError("UNROUTED", "no emitter for this statement kind")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="append", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    admitted = 0
    reachable_per_target: Counter[str] = Counter()
    refusals_per_target: dict[str, Counter[str]] = {
        d.value: Counter() for d in ALL_DIALECTS
    }
    all_four = 0
    lost_by_first_refusal: Counter[str] = Counter()

    for raw in args.corpus:
        name, path, dialect_name = raw.split("=", 2)
        source = Dialect(dialect_name)
        for file in discover_sql_files(Path(path).resolve(strict=True)):
            for statement in statements_of(file, source):
                if type(statement).__name__ not in DDL_TYPES:
                    continue
                with contextlib.redirect_stderr(io.StringIO()):
                    status, _code, _reason = _classify(statement, source)
                if status != "IN_SUBSET":
                    continue
                admitted += 1
                blocked_codes: list[str] = []
                for target in ALL_DIALECTS:
                    if target is source:
                        reachable_per_target[target.value] += 1
                        continue
                    try:
                        with contextlib.redirect_stderr(io.StringIO()):
                            emit_to(statement, source, target)
                        reachable_per_target[target.value] += 1
                    except DialectError as refusal:
                        refusals_per_target[target.value][refusal.code] += 1
                        blocked_codes.append(refusal.code)
                    except Exception as unexpected:  # engine defect, never laundered
                        refusals_per_target[target.value][
                            f"ENGINE_ERROR:{type(unexpected).__name__}"
                        ] += 1
                        blocked_codes.append("ENGINE_ERROR")
                if blocked_codes:
                    lost_by_first_refusal[blocked_codes[0]] += 1
                else:
                    all_four += 1

    out = {
        "kind": "elmos.sql-dialect.target-reachability",
        "admitted_source_side": admitted,
        "translatable_to_all_four": all_four,
        "all_four_ratio_of_admitted": round(all_four / admitted, 4)
        if admitted
        else 0.0,
        "reachable_per_target": dict(reachable_per_target),
        "refusals_per_target": {
            k: dict(v.most_common()) for k, v in refusals_per_target.items()
        },
        "lost_by_first_refusal": dict(lost_by_first_refusal.most_common()),
    }
    args.output.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"admitted source-side      {admitted}")
    print(
        f"translatable to ALL FOUR  {all_four}  ({out['all_four_ratio_of_admitted']:.1%} of admitted)"
    )
    print("\nreachable per target:")
    for d in ALL_DIALECTS:
        print(f"  {d.value:9} {reachable_per_target[d.value]:>6}")
    print("\nwhat stops the rest (first refusal per statement):")
    for code, count in out["lost_by_first_refusal"].items():
        print(f"  {count:>5}  {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
