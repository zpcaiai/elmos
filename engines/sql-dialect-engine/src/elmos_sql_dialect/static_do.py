"""Fail-closed static expansion for a tiny, declaration-free DO profile."""

from __future__ import annotations

import re
from collections.abc import Mapping

from sqlglot import exp

from . import emitter, parser
from .models import AlterTable, Dialect, DialectError, DropTable, Index, Schema, StaticDoBlock, Table
from .statement_splitter import split_statements


def _body(sql: str, _source_dialect: Dialect) -> str:
    match = re.fullmatch(
        r"\s*DO\s+(?P<tag>\$[A-Za-z_0-9]*\$)(?P<body>.*?)\1\s*;?\s*",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        raise DialectError(
            "CERTIFIED_STATIC_DO_UNSUPPORTED",
            "static DO requires one dollar-quoted body",
        )
    body = match.group("body").strip()
    outer = re.fullmatch(r"BEGIN\s+(?P<inner>.*?)\s*END\s*;?", body, flags=re.IGNORECASE | re.DOTALL)
    if outer is not None:
        body = outer.group("inner").strip()
    if re.search(r"\b(?:EXECUTE|FOR|FOREACH|WHILE|LOOP|IF|EXCEPTION|SELECT|INSERT|UPDATE|DELETE)\b", body, re.I):
        raise DialectError(
            "CERTIFIED_STATIC_DO_DYNAMIC_OR_CONTROL_FLOW",
            "DO block contains control flow, query/DML or dynamic SQL; manual migration is required",
        )
    return body


def parse_static_do(
    sql: str,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> StaticDoBlock:
    body = _body(sql, source_dialect)
    statements = split_statements(body)
    if len(statements) != 1:
        raise DialectError(
            "CERTIFIED_STATIC_DO_MULTIPLE_STATEMENTS",
            "static DO accepts exactly one statically expandable DDL statement",
        )
    parsed = parser._parse_source_statements(statements[0].text, source_dialect)
    if len(parsed) != 1 or not isinstance(parsed[0], exp.Expression):
        raise DialectError("CERTIFIED_STATIC_DO_UNSUPPORTED", "static DO inner statement is not one SQL statement")
    statement = parsed[0]
    kind = str(statement.args.get("kind", "")).upper() if isinstance(statement, exp.Create) else ""
    typed: object
    if isinstance(statement, exp.Create) and kind == "TABLE":
        typed = parser.parse_create_table(statement, source_dialect, namespace_map)
    elif isinstance(statement, exp.Create) and kind == "INDEX":
        typed = parser.parse_create_index(statement, source_dialect, namespace_map)
    elif isinstance(statement, exp.Create) and kind == "SCHEMA":
        typed = parser.parse_create_schema(statement, source_dialect, namespace_map)
    elif isinstance(statement, exp.Alter):
        typed = parser.parse_alter_table(statement, source_dialect, namespace_map)
    elif isinstance(statement, exp.Drop):
        typed = parser.parse_drop_table(statement, source_dialect, namespace_map)
    else:
        raise DialectError(
            "CERTIFIED_STATIC_DO_UNSUPPORTED_STATEMENT",
            "static DO only expands CREATE TABLE/INDEX/SCHEMA, ALTER TABLE or DROP TABLE",
        )
    return StaticDoBlock(typed)


def emit_static_do(
    block: StaticDoBlock,
    target_dialect: Dialect,
    catalog: emitter.ColumnCatalogLike | None = None,
) -> str:
    """Emit the already-typed inner DDL; the DO procedural wrapper is removed."""

    statement = block.statement
    if isinstance(statement, Table):
        return emitter.emit_create_table(statement, target_dialect)
    if isinstance(statement, Index):
        return emitter.emit_create_index(statement, target_dialect, catalog)
    if isinstance(statement, Schema):
        return emitter.emit_create_schema(statement, target_dialect)
    if isinstance(statement, AlterTable):
        return emitter.emit_alter_table(statement, target_dialect, catalog)
    if isinstance(statement, DropTable):
        return emitter.emit_drop_table(statement, target_dialect)
    raise DialectError("CERTIFIED_STATIC_DO_UNSUPPORTED", "static DO inner IR has no DDL emitter")
