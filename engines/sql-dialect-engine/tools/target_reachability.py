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
    looks_like_role_comment,
    parse_comment,
    parse_create_view,
    parse_privilege,
    parse_procedure,
    parse_table_function,
    parse_trigger,
)
from elmos_sql_dialect.capabilities import target_capability_matrix
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
from elmos_sql_dialect.parser import (
    _parse_source_statements,
    looks_like_row_security,
    parse_row_security,
    strip_leading_comments,
)
from elmos_sql_dialect.profiles import NamespaceProfile, resolve_namespace_profile
from elmos_sql_dialect.routine import emit_create_function, parse_create_routine
from elmos_sql_dialect.scan import (
    SourceSchemaCatalog,
    _classify,
    _record_catalog_statement,
    discover_sql_files,
    scan_repository,
)
from elmos_sql_dialect.statement_splitter import split_statements
from elmos_sql_dialect.static_do import emit_static_do, parse_static_do

DDL_TYPES = (
    "Create",
    "Alter",
    "Drop",
    "Command",
    "Index",
    "Comment",
    "Grant",
    "Revoke",
    "Insert",
    "Update",
    "Truncate",
)
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
        statements = list(_parse_source_statements(text, dialect))
        raw_statements = list(split_statements(text))
        if len(raw_statements) == len(statements):
            for statement, raw in zip(statements, raw_statements, strict=True):
                if isinstance(statement, exp.Command):
                    try:
                        recovered = _parse_source_statements(
                            strip_leading_comments(raw.text), dialect
                        )
                    except Exception:  # noqa: S112 - preserve the opaque blocker
                        recovered = []
                    if len(recovered) == 1 and not isinstance(recovered[0], exp.Command):
                        statement = recovered[0]
                yield statement
        else:
            yield from statements
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
    source_catalog: SourceSchemaCatalog | None = None,
) -> str | None:
    """Emitted SQL, or None with the refusal recorded by the caller."""
    if isinstance(statement, exp.Command) and looks_like_row_security(statement.sql(), source):
        return emitter.emit_row_security(parse_row_security(statement.sql(), source, namespace_map), target)
    if isinstance(statement, exp.Command) and looks_like_role_comment(statement.sql(), source):
        return emit_comment(
            parse_comment(statement.sql(), source, namespace_map),
            target,
            comment_catalog,
            source_catalog,
        )
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
    if isinstance(statement, exp.Command) and statement.sql().lstrip().upper().startswith("DO"):
        return emit_static_do(parse_static_do(statement.sql(), source, namespace_map), target, source_catalog)
    if isinstance(statement, exp.Alter):
        return emitter.emit_alter_table(
            parser.parse_alter_table(statement, source, namespace_map), target
        )
    if isinstance(statement, exp.Drop):
        return emitter.emit_drop_table(
            parser.parse_drop_table(statement, source, namespace_map), target
        )
    if isinstance(statement, exp.Insert):
        insert = parser.parse_insert_statement(statement, source, namespace_map)
        if hasattr(insert, "rows"):
            return emitter.emit_insert(insert, target)
        return emitter.emit_insert_select(insert, target)
    if isinstance(statement, exp.Update):
        return emitter.emit_update(
            parser.parse_update(statement, source, namespace_map, source_catalog), target
        )
    if isinstance(statement, exp.Comment):
        return emit_comment(
            parse_comment(statement, source, namespace_map),
            target,
            comment_catalog,
            source_catalog,
        )
    if isinstance(statement, exp.Grant | exp.Revoke):
        return emit_privilege(parse_privilege(statement, source, namespace_map), target, source_catalog)
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
    ap.add_argument(
        "--namespace-profile",
        default=None,
        help="JSON namespace profile with name, mapping and optional digest",
    )
    args = ap.parse_args()

    namespace_map = None
    namespace_profile: NamespaceProfile | None = None
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
    if args.namespace_profile is not None:
        if namespace_map is not None:
            ap.error("--namespace-profile cannot be combined with --namespace-map")
        try:
            raw_profile = json.loads(args.namespace_profile)
        except json.JSONDecodeError as exc:
            ap.error(f"--namespace-profile must be a JSON object: {exc}")
        if not isinstance(raw_profile, dict):
            ap.error("--namespace-profile must be a JSON object")
        namespace_profile = NamespaceProfile.from_payload(raw_profile)
    active_namespace_profile = resolve_namespace_profile(namespace_map, namespace_profile)
    namespace_map = active_namespace_profile

    admitted = 0
    discovered = 0
    reachable_per_target: Counter[str] = Counter()
    refusals_per_target: dict[str, Counter[str]] = {
        d.value: Counter() for d in ALL_DIALECTS
    }
    all_four = 0
    disposition_units = 0
    disposition_covered = 0
    disposition_unknown = 0
    catalog_evidence_units = 0
    lost_by_first_refusal: Counter[str] = Counter()
    source_dialects: set[Dialect] = set()

    for raw in args.corpus:
        _name, path, dialect_name = raw.split("=", 2)
        source = Dialect(dialect_name)
        source_dialects.add(source)
        scan_report = scan_repository(path, source, namespace_profile=active_namespace_profile)
        disposition_units += scan_report.totals["dispositionUnits"]
        disposition_covered += scan_report.totals["dispositionCovered"]
        disposition_unknown += scan_report.totals["dispositionUnknown"]
        catalog_evidence_units += len(scan_report.source_catalog_evidence)
        comment_catalog = ReachabilityCommentCatalog()
        source_catalog = SourceSchemaCatalog()
        for file in discover_sql_files(Path(path).resolve(strict=True)):
            # Keep the denominator identical to the authoritative scanner:
            # source-format failures are still discovered units with an
            # explicit disposition, not silently removed from the target
            # reachability denominator.
            discovered += len(split_statements(file.read_text(encoding="utf-8")))
            for statement in statements_of(file, source):
                if type(statement).__name__ not in DDL_TYPES:
                    continue
                # Build source facts before classifying the next unit.  This
                # mirrors scan_repository and is essential for later UPDATE
                # proofs; evidence-only catalog effects may come from a
                # source statement that is intentionally not itself
                # emittable (for example a dynamic DO block).
                _record_catalog_statement(source_catalog, statement, source, namespace_map)
                with contextlib.redirect_stderr(io.StringIO()):
                    status, _code, _reason = _classify(
                        statement,
                        source,
                        raw_sql=statement.sql() if isinstance(statement, exp.Command) else None,
                        namespace_map=namespace_map,
                        catalog=source_catalog,
                    )
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
                            emit_to(
                                statement,
                                source,
                                target,
                                namespace_map,
                                comment_catalog,
                                source_catalog,
                            )
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

    target_priority = sorted(
        (dialect.value for dialect in ALL_DIALECTS),
        key=lambda dialect: (-reachable_per_target[dialect], dialect),
    )
    non_source_priority = [dialect for dialect in target_priority if Dialect(dialect) not in source_dialects]
    out = {
        "kind": "elmos.sql-dialect.target-reachability",
        "discovered_units": discovered,
        "admitted_source_side": admitted,
        "source_candidate_rate": round(admitted / discovered, 4) if discovered else 0.0,
        "disposition_units": disposition_units,
        "disposition_covered": disposition_covered,
        "disposition_unknown": disposition_unknown,
        "disposition_coverage": round(disposition_covered / disposition_units, 4)
        if disposition_units
        else 0.0,
        "translatable_to_all_four": all_four,
        "all_four_ratio_of_admitted": round(all_four / admitted, 4)
        if admitted
        else 0.0,
        "reachable_per_target": dict(reachable_per_target),
        "target_route_rate": {
            dialect.value: round(reachable_per_target[dialect.value] / admitted, 4) if admitted else 0.0
            for dialect in ALL_DIALECTS
        },
        "all_target_intersection_rate": round(all_four / admitted, 4) if admitted else 0.0,
        "routeStrategy": {
            "mode": "target-specific-portfolio",
            "targetPriority": target_priority,
            "bestTarget": target_priority[0] if target_priority else None,
            "bestNonSourceTarget": non_source_priority[0] if non_source_priority else None,
            "reason": (
                "maximize exact target routes independently; the strict intersection remains a separate "
                "fail-closed metric and must not be widened by semantic downgrades"
            ),
        },
        "refusals_per_target": {
            k: dict(v.most_common()) for k, v in refusals_per_target.items()
        },
        "lost_by_first_refusal": dict(lost_by_first_refusal.most_common()),
        "namespaceProfile": None if active_namespace_profile is None else active_namespace_profile.to_dict(),
        "capabilityMatrix": target_capability_matrix(),
        "externalExecution": "NOT_RUN",
        "independentVerification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "sourceCatalogEvidenceUnits": catalog_evidence_units,
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
