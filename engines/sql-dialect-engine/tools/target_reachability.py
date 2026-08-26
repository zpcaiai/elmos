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
from dataclasses import dataclass, field
from pathlib import Path

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
from elmos_sql_dialect.models import (
    AddColumn,
    AlterTable,
    Column,
    Dialect,
    DialectError,
    DropColumn,
    RenameColumn,
    Table,
)
from elmos_sql_dialect.parser import _parse_source_statements
from elmos_sql_dialect.routine import emit_create_function, parse_create_routine
from elmos_sql_dialect.scan import _classify, discover_sql_files
from elmos_sql_dialect.statement_splitter import split_statements

DDL_TYPES = ("Create", "Alter", "Drop", "Index", "Comment", "Grant", "Revoke", "Insert", "Truncate")
ALL_DIALECTS = (Dialect.POSTGRES, Dialect.MYSQL, Dialect.ORACLE, Dialect.TSQL)


def _catalog_key(schema: str | None, table: str) -> tuple[str, str]:
    return ((schema or "").casefold(), table.casefold())


@dataclass
class ReachabilityCommentCatalog:
    """Source-only full column definitions for MySQL COMMENT lowering.

    This intentionally implements only the comment catalogue protocol. The
    target reachability report keeps the older type-blind index/ALTER profile;
    a separate type catalogue is required to make MySQL TEXT-key refusals
    stronger, and silently changing that denominator would make the metric
    incomparable across runs.
    """

    tables: dict[tuple[str, str], dict[str, Column]] = field(default_factory=dict)

    def add_table(self, table: Table) -> None:
        self.tables[_catalog_key(table.schema, table.name)] = {
            column.name.casefold(): column for column in table.columns
        }

    def apply_alter(self, alter: AlterTable) -> None:
        key = _catalog_key(alter.schema, alter.table)
        columns = self.tables.setdefault(key, {})
        for action in alter.actions:
            if isinstance(action, AddColumn):
                columns[action.column.name.casefold()] = action.column
            elif isinstance(action, DropColumn):
                columns.pop(action.column.casefold(), None)
            elif isinstance(action, RenameColumn):
                column = columns.pop(action.column.casefold(), None)
                if column is not None:
                    columns[action.new_name.casefold()] = Column(
                        name=action.new_name,
                        type_ref=column.type_ref,
                        nullable=column.nullable,
                        default=column.default,
                        auto_increment=column.auto_increment,
                    )

    def column_of(self, table_schema: str | None, table: str, column: str) -> Column | None:
        if table_schema is not None:
            return self.tables.get(_catalog_key(table_schema, table), {}).get(column.casefold())
        matches = [
            columns.get(column.casefold())
            for (schema, table_name), columns in self.tables.items()
            if table_name == table.casefold()
        ]
        present = [item for item in matches if item is not None]
        return present[0] if len(present) == 1 else None


def statements_of(path: Path, dialect: Dialect):
    text = path.read_text(encoding="utf-8")
    try:
        yield from _parse_source_statements(text, dialect)
        return
    except Exception:  # noqa: S110 - bounded parser fallback for mixed-dialect corpus files
        pass
    for raw in split_statements(text):
        if raw.text.lstrip().startswith("\\"):
            continue
        try:
            parsed = [
                s for s in _parse_source_statements(raw.text, dialect) if s is not None
            ]
        except Exception:  # noqa: S112 - one malformed recovered chunk must not hide later units
            continue
        if len(parsed) == 1:
            yield parsed[0]


def emit_to(
    statement: exp.Expression,
    source: Dialect,
    target: Dialect,
    namespace_map: dict[str, str] | None = None,
    comment_catalog: ReachabilityCommentCatalog | None = None,
) -> str | None:
    """Emitted SQL, or None with the refusal recorded by the caller."""
    if isinstance(statement, exp.Create):
        kind = str(statement.args.get("kind", "")).upper()
        if kind == "TABLE":
            return emitter.emit_create_table(
                parser.parse_create_table(statement, source, namespace_map), target
            )
        if kind == "SCHEMA":
            return emitter.emit_create_schema(
                parser.parse_create_schema(statement, source, namespace_map), target
            )
        if kind == "INDEX":
            return emitter.emit_create_index(
                parser.parse_create_index(statement, source, namespace_map), target
            )
        if kind == "VIEW":
            return emit_view(parse_create_view(statement, source, namespace_map), target)
        if kind == "FUNCTION":
            try:
                return emit_table_function(parse_table_function(statement, source, namespace_map), target)
            except DialectError as exc:
                if exc.code != "CERTIFIED_ROUTINE_NOT_TABLE_FUNCTION":
                    raise
                return emit_create_function(parse_create_routine(statement, source, namespace_map), target)
        if kind == "PROCEDURE":
            return emit_procedure(parse_procedure(statement, source, namespace_map), target)
        if kind == "TRIGGER":
            return emit_trigger(parse_trigger(statement, source, namespace_map), target)
    if isinstance(statement, exp.Alter):
        return emitter.emit_alter_table(
            parser.parse_alter_table(statement, source, namespace_map), target
        )
    if isinstance(statement, exp.Drop):
        return emitter.emit_drop_table(
            parser.parse_drop_table(statement, source, namespace_map), target
        )
    if isinstance(statement, exp.Insert):
        return emitter.emit_insert(parser.parse_insert(statement, source, namespace_map), target)
    if isinstance(statement, exp.Comment):
        return emit_comment(parse_comment(statement, source, namespace_map), target, comment_catalog)
    if isinstance(statement, exp.Grant | exp.Revoke):
        return emit_privilege(parse_privilege(statement, source, namespace_map), target)
    raise DialectError("UNROUTED", "no emitter for this statement kind")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="append", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument(
        "--namespace-map",
        default=None,
        help="JSON object mapping source namespaces; use an empty key for the source default namespace",
    )
    args = ap.parse_args()

    namespace_map = None
    if args.namespace_map is not None:
        try:
            raw_map = json.loads(args.namespace_map)
        except json.JSONDecodeError as exc:
            ap.error(f"--namespace-map must be a JSON object: {exc}")
        if not isinstance(raw_map, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in raw_map.items()
        ):
            ap.error("--namespace-map must be a JSON object of string-to-string mappings")
        namespace_map = raw_map

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
        comment_catalog = ReachabilityCommentCatalog()
        for file in discover_sql_files(Path(path).resolve(strict=True)):
            for statement in statements_of(file, source):
                if type(statement).__name__ not in DDL_TYPES:
                    continue
                with contextlib.redirect_stderr(io.StringIO()):
                    status, _code, _reason = _classify(statement, source, namespace_map=namespace_map)
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
                            emit_to(statement, source, target, namespace_map, comment_catalog)
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
                if isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() == "TABLE":
                    comment_catalog.add_table(parser.parse_create_table(statement, source, namespace_map))
                elif isinstance(statement, exp.Alter):
                    comment_catalog.apply_alter(parser.parse_alter_table(statement, source, namespace_map))

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
