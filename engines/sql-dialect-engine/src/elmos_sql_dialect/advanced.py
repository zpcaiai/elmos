"""Typed routes for the next SQL coverage tranche.

This module intentionally keeps the new surface narrow and explicit:
ordinary views, comments, table privileges, bounded OUT-parameter procedures,
simple table-valued functions, and trigger metadata.  It does not turn a
procedural body or a security policy into a text blob.  Unsupported control
flow, dynamic SQL, RLS, materialization, and provider-specific options remain
typed blockers.
"""

from __future__ import annotations

from collections.abc import Mapping

import sqlglot
from sqlglot import exp

from .dialects import render_type
from .emitter import _object_name, _render_check_expression
from .models import (
    CheckBooleanExpression,
    CheckConnector,
    CheckExpression,
    Comment,
    CommentObjectKind,
    Dialect,
    DialectError,
    Privilege,
    PrivilegeAction,
    Procedure,
    RoutineAssignment,
    RoutineParameter,
    RoutineParameterMode,
    RowPolicy,
    TableFunction,
    TableFunctionColumn,
    Trigger,
    TriggerEvent,
    TriggerTiming,
    View,
    ViewQuery,
)
from .parser import (
    _IDENTIFIER_RE,
    _mapped_table_name,
    _parse_check,
    _parse_type,
    _plain_identifier,
    _require,
    _require_single_statement,
)
from .routine import _parse_value, _routine_name


def _create_statement(sql: str | exp.Expression, source_dialect: Dialect) -> exp.Create:
    statement = sql if isinstance(sql, exp.Expression) else _require_single_statement(sql, source_dialect)
    if isinstance(statement, exp.Block):
        creates = [item for item in statement.expressions if isinstance(item, exp.Create)]
        _require(
            len(creates) == 1, "CERTIFIED_SQL_MULTIPLE_STATEMENTS", "routine block must contain one CREATE statement"
        )
        statement = creates[0]
    _require(
        isinstance(statement, exp.Create), "CERTIFIED_ADVANCED_UNSUPPORTED_STATEMENT", "expected one CREATE statement"
    )
    assert isinstance(statement, exp.Create)
    return statement


def _parse_query(select: exp.Expression, source_dialect: Dialect, namespace_map: Mapping[str, str] | None) -> ViewQuery:
    _require(isinstance(select, exp.Select), "CERTIFIED_VIEW_UNSUPPORTED_QUERY", "view body must be one SELECT")
    assert isinstance(select, exp.Select)
    _require(
        select.args.get("joins") is None
        and select.args.get("group") is None
        and select.args.get("having") is None
        and select.args.get("qualify") is None
        and select.args.get("order") is None
        and select.args.get("limit") is None
        and select.args.get("distinct") is None
        and select.args.get("with") is None,
        "CERTIFIED_VIEW_UNSUPPORTED_QUERY",
        "view query is limited to a single table and a bounded WHERE predicate",
    )
    from_clause = select.args.get("from_")
    _require(isinstance(from_clause, exp.From), "CERTIFIED_VIEW_UNSUPPORTED_QUERY", "view needs one FROM table")
    assert isinstance(from_clause, exp.From)
    table_schema, table = _mapped_table_name(from_clause.this, "view source table", namespace_map)
    columns: list[str] = []
    for item in select.expressions:
        if isinstance(item, exp.Star):
            columns.append("*")
            continue
        _require(
            isinstance(item, exp.Column), "CERTIFIED_VIEW_UNSUPPORTED_QUERY", "view SELECT items must be plain columns"
        )
        assert isinstance(item, exp.Column)
        _require(
            item.args.get("table") is None,
            "CERTIFIED_VIEW_UNSUPPORTED_QUERY",
            "qualified view columns need a query scope map",
        )
        columns.append(_plain_identifier(item.this, "view selected column"))
    _require(bool(columns), "CERTIFIED_VIEW_UNSUPPORTED_QUERY", "view must select at least one column")
    where = select.args.get("where")
    predicate: CheckExpression | None = None
    if where is not None:
        _require(isinstance(where, exp.Where), "CERTIFIED_VIEW_UNSUPPORTED_QUERY", "view WHERE clause is malformed")
        comparisons, connector, expression = _parse_check(where.this, source_dialect)
        if expression is not None:
            predicate = expression
        elif len(comparisons) == 1:
            predicate = comparisons[0]
        else:
            predicate = CheckBooleanExpression(
                connector=connector or CheckConnector.AND,
                operands=tuple(comparisons),
            )
    return ViewQuery(tuple(columns), table, table_schema, predicate)


def parse_create_view(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> View:
    statement = _create_statement(sql, source_dialect)
    _require(
        str(statement.args.get("kind", "")).upper() == "VIEW",
        "CERTIFIED_VIEW_UNSUPPORTED_STATEMENT",
        "expected CREATE VIEW",
    )
    view_expression = statement.args.get("expression")
    _require(isinstance(view_expression, exp.Expression), "CERTIFIED_VIEW_UNSUPPORTED_QUERY", "view has no query body")
    assert isinstance(view_expression, exp.Expression)
    name_schema, name = _mapped_table_name(statement.this, "view name", namespace_map)
    return View(
        name=name,
        schema=name_schema,
        or_replace=bool(statement.args.get("replace")),
        query=_parse_query(view_expression, source_dialect, namespace_map),
    )


def parse_comment(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> Comment:
    statement = sql if isinstance(sql, exp.Expression) else _require_single_statement(sql, source_dialect)
    _require(isinstance(statement, exp.Comment), "CERTIFIED_COMMENT_UNSUPPORTED_STATEMENT", "expected COMMENT ON")
    assert isinstance(statement, exp.Comment)
    kind = str(statement.args.get("kind", "")).upper()
    _require(
        kind in {"TABLE", "COLUMN"},
        "CERTIFIED_COMMENT_UNSUPPORTED_OBJECT",
        "only table and column comments are supported",
    )
    value = statement.args.get("expression")
    _require(
        isinstance(value, exp.Literal) and value.is_string,
        "CERTIFIED_COMMENT_UNSUPPORTED_VALUE",
        "comment text must be a string literal",
    )
    assert isinstance(value, exp.Literal)
    if kind == "TABLE":
        schema, table = _mapped_table_name(statement.this, "comment table", namespace_map)
        return Comment(CommentObjectKind.TABLE, table, str(value.this), schema=schema)
    target = statement.this
    _require(
        isinstance(target, exp.Column), "CERTIFIED_COMMENT_UNSUPPORTED_OBJECT", "column comment target is malformed"
    )
    assert isinstance(target, exp.Column)
    table_node = target.args.get("table")
    _require(
        isinstance(table_node, exp.Identifier),
        "CERTIFIED_COMMENT_UNSUPPORTED_OBJECT",
        "column comment table is malformed",
    )
    assert isinstance(table_node, exp.Identifier)
    table_schema_node = target.args.get("db")
    if table_schema_node is not None:
        _require(
            isinstance(table_schema_node, exp.Identifier),
            "CERTIFIED_COMMENT_UNSUPPORTED_OBJECT",
            "column comment schema is malformed",
        )
    table_target = exp.Table(this=table_node, db=table_schema_node)
    table_schema, table = _mapped_table_name(table_target, "comment column table", namespace_map)
    return Comment(
        CommentObjectKind.COLUMN,
        _plain_identifier(target.this, "comment column"),
        str(value.this),
        table_name=table,
        schema=table_schema,
        table_schema=table_schema,
    )


def _principal(node: exp.Expression) -> str:
    principal = node.this if isinstance(node, exp.GrantPrincipal) else node
    if isinstance(principal, exp.Var) and str(principal.this).upper() == "PUBLIC":
        return "PUBLIC"
    return _plain_identifier(principal, "privilege principal")


def parse_privilege(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> Privilege:
    statement = sql if isinstance(sql, exp.Expression) else _require_single_statement(sql, source_dialect)
    if isinstance(statement, exp.Grant):
        action = PrivilegeAction.GRANT
    elif isinstance(statement, exp.Revoke):
        action = PrivilegeAction.REVOKE
    else:
        raise DialectError("CERTIFIED_PRIVILEGE_UNSUPPORTED_STATEMENT", "expected GRANT or REVOKE")
    securable = statement.args.get("securable")
    _require(
        isinstance(securable, exp.Table),
        "CERTIFIED_PRIVILEGE_UNSUPPORTED_OBJECT",
        "only table privileges are in the bounded privilege route",
    )
    assert isinstance(securable, exp.Table)
    # PostgreSQL permits the TABLE keyword to be omitted for ordinary table
    # grants/revokes.  Infer it only from a typed Table AST node; do not infer
    # object kinds from the raw SQL text.
    object_kind = str(statement.args.get("kind") or "TABLE").upper()
    _require(
        object_kind == "TABLE",
        "CERTIFIED_PRIVILEGE_UNSUPPORTED_OBJECT",
        "only table privileges are in the portable route",
    )
    schema, object_name = _mapped_table_name(securable, "privilege table", namespace_map)
    privileges = tuple(str(item.this).upper() for item in statement.args.get("privileges") or [])
    _require(bool(privileges), "CERTIFIED_PRIVILEGE_EMPTY", "privilege list is empty")
    allowed = {"SELECT", "INSERT", "UPDATE", "DELETE", "REFERENCES", "ALL"}
    _require(set(privileges) <= allowed, "CERTIFIED_PRIVILEGE_UNSUPPORTED_KIND", "privilege is outside the table route")
    principals = tuple(_principal(item) for item in statement.args.get("principals") or [])
    _require(bool(principals), "CERTIFIED_PRIVILEGE_EMPTY", "principal list is empty")
    return Privilege(
        action=action,
        privileges=privileges,
        object_name=object_name,
        principals=principals,
        object_kind=object_kind,
        schema=schema,
        grant_option=bool(statement.args.get("grant_option")),
    )


def _routine_parameters(
    udf: exp.UserDefinedFunction,
    source_dialect: Dialect,
) -> tuple[RoutineParameter, ...]:
    parameters: list[RoutineParameter] = []
    for item in udf.expressions:
        _require(
            isinstance(item, exp.ColumnDef),
            "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
            "routine parameters must be typed column definitions",
        )
        assert isinstance(item, exp.ColumnDef)
        parameter_node = item.this
        if isinstance(parameter_node, exp.Parameter):
            variable = parameter_node.this
            _require(
                isinstance(variable, exp.Var),
                "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
                "parameter variable is malformed",
            )
            assert isinstance(variable, exp.Var)
            name = str(variable.this)
        else:
            name = _plain_identifier(parameter_node, "routine parameter")
        _require(
            bool(_IDENTIFIER_RE.match(name)),
            "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
            f"parameter {name!r} is not a plain identifier",
        )
        _require(
            isinstance(item.kind, exp.DataType),
            "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
            f"parameter {name!r} has no type",
        )
        assert isinstance(item.kind, exp.DataType)
        mode = RoutineParameterMode.IN
        for constraint in item.args.get("constraints") or []:
            if isinstance(constraint, exp.InOutColumnConstraint):
                if constraint.args.get("input_") and constraint.args.get("output"):
                    mode = RoutineParameterMode.INOUT
                elif constraint.args.get("output"):
                    mode = RoutineParameterMode.OUT
                elif constraint.args.get("input_"):
                    mode = RoutineParameterMode.IN
                else:
                    raise DialectError(
                        "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER", "variadic parameters are outside the route"
                    )
            else:
                raise DialectError(
                    "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
                    "parameter defaults and constraints are outside the route",
                )
        parameters.append(RoutineParameter(name, _parse_type(item.kind, source_dialect), mode))
    return tuple(parameters)


def _body_statements(body: exp.Expression | None, source_dialect: Dialect) -> list[exp.Expression]:
    _require(
        isinstance(body, exp.Heredoc),
        "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
        "procedure body must be a dollar-quoted SQL block",
    )
    assert isinstance(body, exp.Heredoc)
    raw = str(body.this).strip()
    if raw.upper().startswith("BEGIN") and raw.upper().endswith("END"):
        raw = raw[5:-3].strip().strip(";")
    try:
        statements: list[exp.Expression] = []
        for item in sqlglot.parse(raw, read=source_dialect.value):
            if isinstance(item, exp.Expression):
                statements.append(item)
        return statements
    except sqlglot.errors.SqlglotError as exc:
        raise DialectError("CERTIFIED_ROUTINE_UNSUPPORTED_BODY", f"procedure body could not be parsed: {exc}") from exc


def parse_procedure(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> Procedure:
    statement = _create_statement(sql, source_dialect)
    _require(
        str(statement.args.get("kind", "")).upper() == "PROCEDURE",
        "CERTIFIED_ROUTINE_UNSUPPORTED_KIND",
        "expected CREATE PROCEDURE",
    )
    _require(
        isinstance(statement.this, exp.UserDefinedFunction),
        "CERTIFIED_ROUTINE_UNSUPPORTED_STATEMENT",
        "procedure signature is malformed",
    )
    udf = statement.this
    assert isinstance(udf, exp.UserDefinedFunction)
    schema, name = _routine_name(udf.this, namespace_map)
    parameters = _routine_parameters(udf, source_dialect)
    parameter_map = {item.name.casefold(): item for item in parameters}
    assignments: list[RoutineAssignment] = []
    for item in _body_statements(statement.args.get("expression"), source_dialect):
        _require(
            isinstance(item, exp.Set),
            "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
            "only one or more SET parameter assignments are supported",
        )
        assert isinstance(item, exp.Set)
        for set_item in item.expressions:
            target = set_item.this
            _require(isinstance(target, exp.EQ), "CERTIFIED_ROUTINE_UNSUPPORTED_BODY", "SET assignment is malformed")
            assert isinstance(target, exp.EQ)
            lhs = target.this
            if isinstance(lhs, exp.Parameter):
                lhs = lhs.this
                _require(
                    isinstance(lhs, exp.Var), "CERTIFIED_ROUTINE_ASSIGNMENT_TARGET", "procedure target is malformed"
                )
                target_name = str(lhs.this)
            else:
                target_name = _plain_identifier(lhs, "procedure assignment target")
            parameter = parameter_map.get(target_name.casefold())
            _require(
                parameter is not None and parameter.mode is not RoutineParameterMode.IN,
                "CERTIFIED_ROUTINE_ASSIGNMENT_TARGET",
                f"{target_name!r} must be an OUT or INOUT parameter",
            )
            value = _parse_value(target.expression, parameter_map, source_dialect)
            assignments.append(RoutineAssignment(target_name, value))
    _require(bool(assignments), "CERTIFIED_ROUTINE_UNSUPPORTED_BODY", "procedure has no supported parameter assignment")
    return Procedure(
        name, parameters, tuple(assignments), schema=schema, or_replace=bool(statement.args.get("replace"))
    )


def _returns_table(statement: exp.Create) -> exp.ReturnsProperty | None:
    properties = statement.args.get("properties")
    if not isinstance(properties, exp.Properties):
        return None
    for prop in properties.expressions:
        if isinstance(prop, exp.ReturnsProperty) and prop.args.get("is_table"):
            return prop
    return None


def parse_table_function(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> TableFunction:
    statement = _create_statement(sql, source_dialect)
    _require(
        str(statement.args.get("kind", "")).upper() == "FUNCTION",
        "CERTIFIED_ROUTINE_UNSUPPORTED_KIND",
        "expected CREATE FUNCTION",
    )
    returns = _returns_table(statement)
    _require(returns is not None, "CERTIFIED_ROUTINE_NOT_TABLE_FUNCTION", "function does not declare RETURNS TABLE")
    assert returns is not None
    _require(
        isinstance(statement.this, exp.UserDefinedFunction),
        "CERTIFIED_ROUTINE_UNSUPPORTED_STATEMENT",
        "function signature is malformed",
    )
    udf = statement.this
    assert isinstance(udf, exp.UserDefinedFunction)
    schema, name = _routine_name(udf.this, namespace_map)
    parameters = _routine_parameters(udf, source_dialect)
    return_schema = returns.args.get("this")
    _require(
        isinstance(return_schema, exp.Schema),
        "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
        "RETURNS TABLE row shape is malformed",
    )
    assert isinstance(return_schema, exp.Schema)
    return_columns: list[TableFunctionColumn] = []
    for item in return_schema.expressions:
        _require(
            isinstance(item, exp.ColumnDef),
            "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
            "table return columns must be typed",
        )
        assert isinstance(item, exp.ColumnDef)
        _require(
            isinstance(item.kind, exp.DataType),
            "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
            "table return column has no type",
        )
        assert isinstance(item.kind, exp.DataType)
        return_columns.append(
            TableFunctionColumn(
                _plain_identifier(item.this, "table return column"), _parse_type(item.kind, source_dialect)
            )
        )
    body = statement.args.get("expression")
    _require(
        isinstance(body, exp.Heredoc), "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED", "table function body must be SQL"
    )
    assert isinstance(body, exp.Heredoc)
    statements: list[exp.Expression] = []
    for item in sqlglot.parse(str(body.this).strip(), read=source_dialect.value):
        if isinstance(item, exp.Expression):
            statements.append(item)
    _require(
        len(statements) == 1,
        "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
        "table function body must contain one SELECT",
    )
    query = _parse_query(statements[0], source_dialect, namespace_map)
    _require(
        query.columns == tuple(item.name for item in return_columns),
        "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
        "table function SELECT shape must match declared return columns exactly",
    )
    return TableFunction(
        name, parameters, tuple(return_columns), query, schema=schema, or_replace=bool(statement.args.get("replace"))
    )


def parse_trigger(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> Trigger:
    statement = _create_statement(sql, source_dialect)
    _require(
        str(statement.args.get("kind", "")).upper() == "TRIGGER",
        "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED",
        "expected CREATE TRIGGER",
    )
    name = _plain_identifier(statement.this, "trigger name")
    properties = statement.args.get("properties")
    trigger_properties = (
        next(
            (item for item in properties.expressions if isinstance(item, exp.TriggerProperties)),
            None,
        )
        if isinstance(properties, exp.Properties)
        else None
    )
    _require(trigger_properties is not None, "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED", "trigger metadata is unavailable")
    assert trigger_properties is not None
    table_schema, table = _mapped_table_name(trigger_properties.args.get("table"), "trigger table", namespace_map)
    timing_value = str(trigger_properties.args.get("timing", "")).upper()
    timing = {"BEFORE": TriggerTiming.BEFORE, "AFTER": TriggerTiming.AFTER, "INSTEAD OF": TriggerTiming.INSTEAD_OF}.get(
        timing_value
    )
    _require(timing is not None, "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED", "trigger timing is unsupported")
    assert timing is not None
    event_values = tuple(
        TriggerEvent(str(item.this).upper())
        for item in trigger_properties.args.get("events") or []
        if str(item.this).upper() in {"INSERT", "UPDATE", "DELETE"}
    )
    _require(bool(event_values), "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED", "trigger has no supported event")
    execute = trigger_properties.args.get("execute")
    _require(
        isinstance(execute, exp.TriggerExecute) and isinstance(execute.this, exp.Anonymous),
        "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED",
        "trigger action must call one named routine",
    )
    assert isinstance(execute, exp.TriggerExecute)
    assert isinstance(execute.this, exp.Anonymous)
    routine_name = _plain_identifier(exp.Identifier(this=str(execute.this.this), quoted=False), "trigger routine")
    return Trigger(
        name=name,
        table=table,
        timing=timing,
        events=event_values,
        row_level=str(trigger_properties.args.get("for_each", "")).upper() == "ROW",
        routine_name=routine_name,
        schema=table_schema,
        table_schema=table_schema,
    )


def parse_row_policy(sql: str | exp.Expression, source_dialect: Dialect) -> RowPolicy:
    if isinstance(sql, str) and sql.lstrip().upper().startswith("CREATE POLICY"):
        raise DialectError(
            "CERTIFIED_RLS_TARGET_ROUTE_REQUIRED",
            "row-level security needs a target policy model, owner, command scope and execution "
            "evidence; it is not lowered to a permissive policy",
        )
    statement = _create_statement(sql, source_dialect)
    _require(
        str(statement.args.get("kind", "")).upper() == "POLICY",
        "CERTIFIED_RLS_UNSUPPORTED_STATEMENT",
        "expected CREATE POLICY",
    )
    raise DialectError(
        "CERTIFIED_RLS_TARGET_ROUTE_REQUIRED",
        "row-level security needs a target policy model, owner, command scope and execution "
        "evidence; it is not lowered to a permissive policy",
    )


def _routine_type(type_ref: object, dialect: Dialect) -> str:
    # CanonicalTypeRef is intentionally accepted structurally here to keep
    # this module independent from a duplicate type renderer.
    from .models import CanonicalType, CanonicalTypeRef

    assert isinstance(type_ref, CanonicalTypeRef)
    if dialect is Dialect.ORACLE and type_ref.canonical_type is CanonicalType.CHAR:
        return f"CHAR({type_ref.length or 1})"
    if dialect is Dialect.ORACLE and type_ref.canonical_type is CanonicalType.VARCHAR:
        assert type_ref.length is not None
        return f"VARCHAR2({type_ref.length})"
    return render_type(type_ref, dialect)


def emit_view(view: View, target_dialect: Dialect) -> str:
    if view.or_replace and target_dialect is Dialect.TSQL:
        raise DialectError(
            "CERTIFIED_VIEW_REPLACE_UNSUPPORTED_BY_TARGET",
            "SQL Server has no one version-independent CREATE OR REPLACE VIEW spelling",
        )
    replace = " OR REPLACE" if view.or_replace else ""
    query = view.query
    selected = ", ".join(query.columns)
    rendered = (
        f"CREATE{replace} VIEW {_object_name(view.schema, view.name)} AS SELECT {selected} "  # noqa: S608
        f"FROM {_object_name(query.table_schema, query.table)}"  # noqa: S608
    )
    if query.predicate is not None:
        rendered += f" WHERE {_render_check_expression(query.predicate, target_dialect)}"
    return rendered


def emit_comment(comment: Comment, target_dialect: Dialect) -> str:
    if target_dialect is Dialect.TSQL:
        raise DialectError(
            "CERTIFIED_COMMENT_TARGET_UNSUPPORTED",
            "SQL Server comments require extended-property ownership and schema identity",
        )
    target = (
        f"TABLE {_object_name(comment.schema, comment.object_name)}"
        if comment.object_kind is CommentObjectKind.TABLE
        else f"COLUMN {_object_name(comment.table_schema, comment.table_name or '')}.{comment.object_name}"
    )
    return f"COMMENT ON {target} IS '{comment.text.replace(chr(39), chr(39) * 2)}'"


def emit_privilege(privilege: Privilege, target_dialect: Dialect) -> str:
    if privilege.grant_option:
        raise DialectError(
            "CERTIFIED_PRIVILEGE_GRANT_OPTION_UNSUPPORTED",
            "grant-option lifecycle needs a target role/ownership policy",
        )
    target = _object_name(privilege.schema, privilege.object_name)
    privilege_list = ", ".join(privilege.privileges)
    principals = ", ".join(privilege.principals)
    if target_dialect is Dialect.TSQL:
        object_clause = f"OBJECT::{target}"
    else:
        object_clause = target
    table_keyword = "TABLE " if target_dialect is Dialect.POSTGRES else ""
    direction = "TO" if privilege.action is PrivilegeAction.GRANT else "FROM"
    return f"{privilege.action.value} {privilege_list} ON {table_keyword}{object_clause} {direction} {principals}"


def emit_procedure(procedure: Procedure, target_dialect: Dialect) -> str:
    if procedure.or_replace and target_dialect not in (Dialect.POSTGRES, Dialect.ORACLE):
        raise DialectError(
            "CERTIFIED_ROUTINE_REPLACE_UNSUPPORTED_BY_TARGET",
            f"{target_dialect.value} has no exact CREATE OR REPLACE PROCEDURE spelling",
        )
    qualified = _object_name(procedure.schema, procedure.name)
    replace = " OR REPLACE" if procedure.or_replace and target_dialect in (Dialect.POSTGRES, Dialect.ORACLE) else ""

    def param(item: RoutineParameter) -> str:
        if target_dialect is Dialect.TSQL:
            output = " OUTPUT" if item.mode is not RoutineParameterMode.IN else ""
            return f"@{item.name} {_routine_type(item.type_ref, target_dialect)}{output}"
        mode = item.mode.value if target_dialect in (Dialect.POSTGRES, Dialect.ORACLE, Dialect.MYSQL) else ""
        return f"{mode + ' ' if mode else ''}{item.name} {_routine_type(item.type_ref, target_dialect)}"

    params = ", ".join(param(item) for item in procedure.parameters)
    statements: list[str] = []
    for assignment in procedure.assignments:
        left = ("@" if target_dialect is Dialect.TSQL else "") + assignment.target
        from .routine import _render_routine_value

        right = _render_routine_value(assignment.value, target_dialect, tsql_parameters=target_dialect is Dialect.TSQL)
        if target_dialect is Dialect.ORACLE:
            statements.append(f":{left} := {right};")
        elif target_dialect in (Dialect.MYSQL, Dialect.TSQL):
            statements.append(f"SET {left} = {right};")
        else:
            statements.append(f"{left} := {right};")
    body = " ".join(statements)
    if target_dialect is Dialect.MYSQL:
        return f"CREATE PROCEDURE {qualified} ({params}) BEGIN {body} END"
    if target_dialect is Dialect.TSQL:
        return f"CREATE PROCEDURE {qualified} {params} AS BEGIN {body} END"
    if target_dialect is Dialect.ORACLE:
        return f"CREATE{replace} PROCEDURE {qualified}({params}) IS BEGIN {body} END;"
    return f"CREATE{replace} PROCEDURE {qualified}({params}) LANGUAGE plpgsql AS $$ BEGIN {body} END $$"


def emit_table_function(function: TableFunction, target_dialect: Dialect) -> str:
    if target_dialect not in (Dialect.POSTGRES, Dialect.TSQL):
        raise DialectError(
            "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
            f"{target_dialect.value} has no exact inline table-valued function route",
        )
    if function.or_replace and target_dialect is Dialect.TSQL:
        raise DialectError(
            "CERTIFIED_ROUTINE_REPLACE_UNSUPPORTED_BY_TARGET",
            "SQL Server CREATE OR ALTER version semantics are not pinned",
        )
    qualified = _object_name(function.schema, function.name)
    params = ", ".join(
        ("@" if target_dialect is Dialect.TSQL else "") + item.name + " " + _routine_type(item.type_ref, target_dialect)
        for item in function.parameters
    )
    columns = ", ".join(
        item.name + " " + _routine_type(item.type_ref, target_dialect) for item in function.return_columns
    )
    selected = ", ".join(function.query.columns)
    source = _object_name(function.query.table_schema, function.query.table)
    where = (
        ""
        if function.query.predicate is None
        else f" WHERE {_render_check_expression(function.query.predicate, target_dialect)}"
    )
    if target_dialect is Dialect.TSQL:
        return (
            f"CREATE FUNCTION {qualified}({params}) RETURNS TABLE AS RETURN "  # noqa: S608
            f"(SELECT {selected} FROM {source}{where})"  # noqa: S608
        )
    return (
        f"CREATE FUNCTION {qualified}({params}) RETURNS TABLE ({columns}) LANGUAGE SQL "  # noqa: S608
        f"AS $$ SELECT {selected} FROM {source}{where} $$"  # noqa: S608
    )


def emit_trigger(trigger: Trigger, target_dialect: Dialect) -> str:
    if target_dialect is not Dialect.POSTGRES:
        raise DialectError(
            "CERTIFIED_ROUTINE_TRIGGER_TARGET_ROUTE_REQUIRED",
            "trigger execution/action semantics are target-specific; this route emits only PostgreSQL trigger syntax",
        )
    events = " OR ".join(item.value for item in trigger.events)
    row = " FOR EACH ROW" if trigger.row_level else " FOR EACH STATEMENT"
    return (
        f"CREATE TRIGGER {trigger.name} {trigger.timing.value} {events} ON "
        f"{_object_name(trigger.table_schema, trigger.table)}{row} "
        f"EXECUTE FUNCTION {_object_name(trigger.routine_schema, trigger.routine_name)}()"
    )
