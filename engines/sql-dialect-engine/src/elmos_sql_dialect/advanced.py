"""Typed routes for the next SQL coverage tranche.

This module intentionally keeps the new surface narrow and explicit:
ordinary views, comments, table privileges, bounded OUT-parameter procedures,
simple table-valued functions, and trigger metadata.  It does not turn a
procedural body or a security policy into a text blob.  Unsupported control
flow, dynamic SQL, RLS, materialization, and provider-specific options remain
typed blockers.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Protocol

import sqlglot
from sqlglot import exp

from .dialects import check_operator_sql, render_type
from .emitter import CommentColumnCatalogLike, _object_name, _render_check_expression, _render_column
from .identifiers import quote_identifier
from .models import (
    CanonicalTypeRef,
    CheckBooleanExpression,
    CheckComparison,
    CheckConnector,
    CheckExpression,
    CheckNotExpression,
    CheckOperator,
    ColumnDefault,
    Comment,
    CommentObjectKind,
    Dialect,
    DialectError,
    Privilege,
    PrivilegeAction,
    Procedure,
    RoutineAssignment,
    RoutineLanguage,
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
from .routine import _parse_routine_identity_type, _parse_value, _property_language, _routine_name
from .statement_splitter import split_statements


class RoutineIdentityCatalogLike(Protocol):
    """Minimal catalog contract for signature-sensitive target routes."""

    def has_unique_routine(
        self,
        kind: str,
        schema: str | None,
        name: str,
        parameter_types: tuple[CanonicalTypeRef, ...],
    ) -> bool: ...


def _routine_argument_type_refs(
    routine: exp.UserDefinedFunction | exp.Anonymous,
    source_dialect: Dialect,
) -> tuple[CanonicalTypeRef, ...] | None:
    """Best-effort typed parsing for a privilege/comment routine signature.

    The legacy string tuple remains in the public IR for source rendering.
    This parallel typed tuple is populated only when every argument can be
    represented by the canonical type model; an unknown type intentionally
    disables catalog-gated lowering instead of being guessed.
    """

    refs: list[CanonicalTypeRef] = []
    try:
        for item in routine.expressions:
            name = _plain_identifier(item, "routine argument type")
            refs.append(
                _parse_routine_identity_type(
                    exp.DataType.build(name, dialect=source_dialect.value),
                    source_dialect,
                )
            )
    except (DialectError, TypeError, ValueError):
        return None
    return tuple(refs)


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
    if isinstance(statement, exp.Command) and looks_like_role_comment(statement.sql(), source_dialect):
        return parse_role_comment(statement.sql(), source_dialect)
    _require(isinstance(statement, exp.Comment), "CERTIFIED_COMMENT_UNSUPPORTED_STATEMENT", "expected COMMENT ON")
    assert isinstance(statement, exp.Comment)
    kind = str(statement.args.get("kind", "")).upper()
    _require(
        kind in {"TABLE", "COLUMN", "FUNCTION", "CONSTRAINT"},
        "CERTIFIED_COMMENT_UNSUPPORTED_OBJECT",
        "only table, column, constraint and scalar function comments are in the typed object route",
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
    if kind == "FUNCTION":
        target = statement.this
        _require(
            isinstance(target, exp.UserDefinedFunction),
            "CERTIFIED_COMMENT_UNSUPPORTED_OBJECT",
            "function comment target is malformed",
        )
        assert isinstance(target, exp.UserDefinedFunction)
        schema, name = _routine_name(target.this, namespace_map)
        argument_types = tuple(
            _plain_identifier(item, "comment function argument type") for item in target.expressions
        )
        return Comment(
            CommentObjectKind.FUNCTION,
            name,
            str(value.this),
            schema=schema,
            routine_argument_types=argument_types,
            routine_argument_type_refs=_routine_argument_type_refs(target, source_dialect),
        )
    if kind == "CONSTRAINT":
        target = statement.this
        _require(
            isinstance(target, exp.Table),
            "CERTIFIED_COMMENT_UNSUPPORTED_OBJECT",
            "constraint comment target is malformed",
        )
        assert isinstance(target, exp.Table)
        constraint_node = target.args.get("constraint")
        _require(
            isinstance(constraint_node, exp.Identifier),
            "CERTIFIED_COMMENT_UNSUPPORTED_OBJECT",
            "constraint comment name is missing",
        )
        assert isinstance(constraint_node, exp.Identifier)
        schema, table = _mapped_table_name(target, "comment constraint table", namespace_map)
        return Comment(
            CommentObjectKind.CONSTRAINT,
            _plain_identifier(constraint_node, "comment constraint"),
            str(value.this),
            table_name=table,
            schema=schema,
            table_schema=schema,
        )
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


def looks_like_role_comment(sql: str, source_dialect: Dialect) -> bool:
    """Recognize PostgreSQL's opaque ``COMMENT ON ROLE`` command shape."""

    if source_dialect is not Dialect.POSTGRES:
        return False
    try:
        tokens = list(sqlglot.tokenize(sql, read=source_dialect.value))
    except sqlglot.errors.SqlglotError:
        return False
    if len(tokens) != 6:
        return False
    values = [str(token.text).upper() for token in tokens]
    return (
        values[:3] == ["COMMENT", "ON", "ROLE"]
        and values[4] == "IS"
        and tokens[3].token_type.name in {"VAR", "IDENTIFIER"}
        and tokens[5].token_type.name == "STRING"
    )


def parse_role_comment(sql: str | exp.Expression, source_dialect: Dialect) -> Comment:
    """Parse one typed PostgreSQL role comment; other object kinds stay separate."""

    _require(
        source_dialect is Dialect.POSTGRES,
        "CERTIFIED_COMMENT_UNSUPPORTED_OBJECT",
        "role comments are admitted only from PostgreSQL",
    )
    statement_sql = sql if isinstance(sql, str) else sql.sql()
    try:
        tokens = list(sqlglot.tokenize(statement_sql, read=source_dialect.value))
    except sqlglot.errors.SqlglotError as exc:
        raise DialectError(
            "CERTIFIED_COMMENT_PARSE_FAILED",
            f"postgres parser rejected role comment: {exc}",
        ) from exc
    _require(
        looks_like_role_comment(statement_sql, source_dialect),
        "CERTIFIED_COMMENT_UNSUPPORTED_STATEMENT",
        "expected COMMENT ON ROLE <identifier> IS <string literal>",
    )
    role_token = tokens[3]
    role = _plain_identifier(
        exp.Identifier(this=str(role_token.text), quoted=role_token.token_type.name == "IDENTIFIER"),
        "comment role",
    )
    return Comment(CommentObjectKind.ROLE, role, str(tokens[5].text))


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
        "privilege target is not a table or routine reference",
    )
    assert isinstance(securable, exp.Table)
    # PostgreSQL permits the TABLE keyword to be omitted for ordinary table
    # grants/revokes.  Infer it only from a typed Table AST node; do not infer
    # object kinds from the raw SQL text.
    object_kind = str(statement.args.get("kind") or "TABLE").upper()
    privileges = tuple(str(item.this).upper() for item in statement.args.get("privileges") or [])
    _require(bool(privileges), "CERTIFIED_PRIVILEGE_EMPTY", "privilege list is empty")
    if object_kind in {"FUNCTION", "PROCEDURE"}:
        routine = securable.this
        _require(
            isinstance(routine, exp.Anonymous),
            "CERTIFIED_PRIVILEGE_UNSUPPORTED_OBJECT",
            "routine privilege target must carry a named routine reference",
        )
        assert isinstance(routine, exp.Anonymous)
        name = _plain_identifier(
            exp.Identifier(this=str(routine.this), quoted=False),
            "privilege routine",
        )
        schema_node = securable.args.get("db")
        source_schema: str | None = (
            None if schema_node is None else _plain_identifier(schema_node, "privilege routine schema")
        )
        schema: str | None = source_schema
        if source_schema is None and namespace_map is not None and "" in namespace_map:
            # Keep privilege targets on the same explicit default namespace as
            # routine definitions and comments. Without this, the catalog
            # proves `dbo.f(...)` while the privilege still asks for `f(...)`.
            schema = namespace_map[""]
            _require(
                bool(_IDENTIFIER_RE.match(schema)),
                "CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE",
                f"mapped routine schema {schema!r} is not a plain identifier",
            )
        if source_schema is not None:
            mapped_schema = None if namespace_map is None else namespace_map.get(source_schema)
            _require(
                mapped_schema is not None,
                "CERTIFIED_ROUTINE_NAMESPACE_MAPPING_REQUIRED",
                f"routine schema {source_schema!r} needs an explicit namespace_map",
            )
            assert mapped_schema is not None
            _require(
                bool(_IDENTIFIER_RE.match(mapped_schema)),
                "CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE",
                f"mapped routine schema {mapped_schema!r} is not a plain identifier",
            )
            schema = mapped_schema
        argument_types = tuple(
            _plain_identifier(item, "privilege routine argument type") for item in routine.expressions
        )
        _require(
            set(privileges) <= {"EXECUTE", "ALL"},
            "CERTIFIED_PRIVILEGE_UNSUPPORTED_KIND",
            "routine privilege route supports EXECUTE or ALL only",
        )
        principals = tuple(_principal(item) for item in statement.args.get("principals") or [])
        _require(bool(principals), "CERTIFIED_PRIVILEGE_EMPTY", "principal list is empty")
        return Privilege(
            action=action,
            privileges=privileges,
            object_name=name,
            principals=principals,
            object_kind=object_kind,
            schema=schema,
            grant_option=bool(statement.args.get("grant_option")),
            routine_argument_types=argument_types,
            routine_argument_type_refs=_routine_argument_type_refs(routine, source_dialect),
        )
    _require(
        object_kind == "TABLE",
        "CERTIFIED_PRIVILEGE_UNSUPPORTED_OBJECT",
        "only table, function and procedure privileges are in the typed route",
    )
    schema, object_name = _mapped_table_name(securable, "privilege table", namespace_map)
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
        default: ColumnDefault | None = None
        for constraint in item.args.get("constraints") or []:
            constraint_kind = constraint.kind if isinstance(constraint, exp.ColumnConstraint) else constraint
            if isinstance(constraint_kind, exp.InOutColumnConstraint):
                if constraint_kind.args.get("input_") and constraint_kind.args.get("output"):
                    mode = RoutineParameterMode.INOUT
                elif constraint_kind.args.get("output"):
                    mode = RoutineParameterMode.OUT
                elif constraint_kind.args.get("input_"):
                    mode = RoutineParameterMode.IN
                else:
                    raise DialectError(
                        "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER", "variadic parameters are outside the route"
                    )
            elif isinstance(constraint_kind, exp.DefaultColumnConstraint):
                _require(
                    default is None,
                    "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
                    f"parameter {name!r} has more than one default",
                )
                from .parser import _parse_default

                default = _parse_default(constraint_kind.this, _parse_type(item.kind, source_dialect))
            else:
                raise DialectError(
                    "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
                    "parameter constraints outside mode and side-effect-free defaults are outside the route",
                )
        parameters.append(RoutineParameter(name, _parse_type(item.kind, source_dialect), mode, default))
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
    language = RoutineLanguage.OTHER
    properties = statement.args.get("properties")
    if isinstance(properties, exp.Properties):
        for prop in properties.expressions:
            if isinstance(prop, exp.ReturnsProperty):
                continue
            if isinstance(prop, exp.LanguageProperty):
                language = _property_language(prop)
                continue
            if isinstance(prop, exp.StrictProperty):
                raise DialectError(
                    "CERTIFIED_ROUTINE_STRICT_UNSUPPORTED_BY_TARGET",
                    "PostgreSQL STRICT null short-circuiting is routine metadata; the table-function route "
                    "does not synthesize a wrapper with unverified type/null semantics",
                )
            if isinstance(prop, exp.SqlSecurityProperty):
                raise DialectError(
                    "CERTIFIED_ROUTINE_SECURITY_CONTEXT_UNSUPPORTED",
                    "SECURITY DEFINER/INVOKER changes table-function execution identity and needs an exact "
                    "target mapping",
                )
            if isinstance(prop, exp.SetConfigProperty):
                raise DialectError(
                    "CERTIFIED_ROUTINE_SECURITY_CONTEXT_UNSUPPORTED",
                    "SET configuration changes table-function name resolution or execution context and "
                    "needs an exact target mapping",
                )
            if isinstance(prop, exp.StabilityProperty):
                raise DialectError(
                    "CERTIFIED_ROUTINE_STABILITY_UNSUPPORTED_BY_TARGET",
                    "table-function volatility/stability has no one exact cross-dialect route",
                )
            raise DialectError(
                "CERTIFIED_ROUTINE_UNSUPPORTED_PROPERTY",
                f"table-function property {type(prop).__name__} is outside certified-routine-v1",
            )
    _require(
        language in (RoutineLanguage.SQL, RoutineLanguage.PLPGSQL),
        "CERTIFIED_ROUTINE_UNSUPPORTED_LANGUAGE",
        f"table-function language {language.value} is outside the narrow SQL/PLpgSQL route",
    )
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
        isinstance(body, exp.Heredoc),
        "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
        "table function body must be a dollar-quoted SQL body",
    )
    assert isinstance(body, exp.Heredoc)
    raw_body = str(body.this).strip()
    if language is RoutineLanguage.PLPGSQL:
        # This is intentionally smaller than the scalar PL/pgSQL subset: a
        # table function may expose only one read-only query. Declarations,
        # assignments, loops, EXCEPTION blocks, DML and EXECUTE all remain
        # outside the route instead of being reconstructed from source text.
        chunks = split_statements(raw_body)
        _require(
            len(chunks) == 2 and chunks[1].text.strip().upper() == "END",
            "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
            "PL/pgSQL table function must be BEGIN RETURN QUERY SELECT ...; END",
        )
        match = re.fullmatch(
            r"BEGIN\s+RETURN\s+QUERY\s+(?P<select>SELECT\b.*)",
            chunks[0].text.strip(),
            flags=re.IGNORECASE | re.DOTALL,
        )
        _require(
            match is not None,
            "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
            "PL/pgSQL table function must contain one static RETURN QUERY SELECT",
        )
        assert match is not None
        query_sql = match.group("select").strip()
    else:
        query_sql = raw_body
    try:
        statements = [
            item for item in sqlglot.parse(query_sql, read=source_dialect.value) if isinstance(item, exp.Expression)
        ]
    except sqlglot.errors.SqlglotError as exc:
        raise DialectError(
            "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
            f"table function query could not be parsed: {exc}",
        ) from exc
    _require(
        len(statements) == 1,
        "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
        "table function body must contain one SELECT",
    )
    try:
        query = _parse_query(statements[0], source_dialect, namespace_map)
    except DialectError as exc:
        raise DialectError(
            "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
            f"table function query is outside the static read-only route: {exc.message}",
        ) from exc
    parameter_names = {item.name.casefold() for item in parameters}
    for column in statements[0].find_all(exp.Column):
        if column.args.get("table") is None and str(column.this).casefold() in parameter_names:
            raise DialectError(
                "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
                "table-function query parameter references need a parameter-aware query IR; "
                "unqualified names remain fail-closed",
            )
    _require(
        query.columns == tuple(item.name for item in return_columns),
        "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
        "table function SELECT shape must match declared return columns exactly",
    )
    return TableFunction(
        name,
        parameters,
        tuple(return_columns),
        query,
        schema=schema,
        or_replace=bool(statement.args.get("replace")),
        language=language,
    )


def _trigger_identifier(node: exp.Expression, what: str) -> tuple[str, str | None]:
    """Read a trigger column and preserve the OLD/NEW pseudo-row qualifier."""

    _require(isinstance(node, exp.Column), "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED", f"{what} must be a column")
    assert isinstance(node, exp.Column)
    qualifier = node.args.get("table")
    qualifier_name: str | None = None
    if qualifier is not None:
        _require(
            isinstance(qualifier, exp.Identifier),
            "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED",
            f"{what} qualifier must be OLD or NEW",
        )
        qualifier_name = str(qualifier.this).upper()
        _require(
            qualifier_name in {"OLD", "NEW"},
            "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED",
            f"{what} qualifier must be OLD or NEW",
        )
    return _plain_identifier(node.this, what), qualifier_name


def _parse_trigger_when(node: exp.Expression, source_dialect: Dialect) -> CheckExpression:
    """Parse the small trigger WHEN subset without treating OLD/NEW as tables.

    Trigger predicates use the same SQL three-valued boolean model as CHECK,
    but their pseudo-row qualifiers have special syntax and are therefore
    parsed separately.  Only typed columns, literals, NULL tests, boolean
    composition, and the NULL-safe column comparison are admitted.
    """

    if isinstance(node, exp.Paren):
        return _parse_trigger_when(node.this, source_dialect)
    if isinstance(node, exp.And | exp.Or):
        left = _parse_trigger_when(node.this, source_dialect)
        right = _parse_trigger_when(node.expression, source_dialect)
        return CheckBooleanExpression(
            connector=CheckConnector.AND if isinstance(node, exp.And) else CheckConnector.OR,
            operands=(left, right),
        )
    if isinstance(node, exp.Not):
        return CheckNotExpression(_parse_trigger_when(node.this, source_dialect))
    if isinstance(node, exp.Is):
        _require(
            isinstance(node.expression, exp.Null),
            "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED",
            "trigger WHEN only supports IS [NOT] NULL",
        )
        column, qualifier = _trigger_identifier(node.this, "trigger WHEN left-hand column")
        return CheckComparison(
            column=column,
            column_qualifier=qualifier,
            operator=CheckOperator.IS_NOT_NULL if node.args.get("negate") else CheckOperator.IS_NULL,
        )

    operator_by_type: tuple[tuple[type[exp.Expression], CheckOperator], ...] = (
        (exp.NullSafeNEQ, CheckOperator.IS_DISTINCT_FROM),
        (exp.EQ, CheckOperator.EQ),
        (exp.NEQ, CheckOperator.NE),
        (exp.LT, CheckOperator.LT),
        (exp.LTE, CheckOperator.LE),
        (exp.GT, CheckOperator.GT),
        (exp.GTE, CheckOperator.GE),
    )
    for expression_type, operator in operator_by_type:
        if not isinstance(node, expression_type):
            continue
        column, qualifier = _trigger_identifier(node.this, "trigger WHEN left-hand column")
        right = node.expression
        if isinstance(right, exp.Column):
            right_column, right_qualifier = _trigger_identifier(right, "trigger WHEN right-hand column")
            return CheckComparison(
                column=column,
                column_qualifier=qualifier,
                operator=operator,
                right_column=right_column,
                right_column_qualifier=right_qualifier,
            )
        if isinstance(right, exp.Boolean):
            return CheckComparison(
                column=column,
                column_qualifier=qualifier,
                operator=operator,
                literal="true" if right.this else "false",
                literal_is_boolean=True,
            )
        _require(
            isinstance(right, exp.Literal),
            "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED",
            "trigger WHEN comparison requires a literal or OLD/NEW column",
        )
        return CheckComparison(
            column=column,
            column_qualifier=qualifier,
            operator=operator,
            literal=str(right.this),
            literal_is_string=bool(right.is_string),
        )
    raise DialectError(
        "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED",
        "trigger WHEN expression is outside the typed OLD/NEW predicate subset",
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
    raw_events = tuple(trigger_properties.args.get("events") or [])
    event_values = tuple(
        TriggerEvent(str(item.this).upper())
        for item in raw_events
        if str(item.this).upper() in {"INSERT", "UPDATE", "DELETE"}
    )
    _require(bool(event_values), "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED", "trigger has no supported event")
    update_columns: tuple[str, ...] = ()
    for item in raw_events:
        if str(item.this).upper() != "UPDATE":
            continue
        columns = tuple(
            _plain_identifier(column, "trigger UPDATE OF column") for column in item.args.get("columns") or []
        )
        _require(
            not update_columns or update_columns == columns,
            "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED",
            "multiple UPDATE OF event filters disagree",
        )
        update_columns = columns
    execute = trigger_properties.args.get("execute")
    _require(
        isinstance(execute, exp.TriggerExecute),
        "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED",
        "trigger action must call one named routine",
    )
    assert isinstance(execute, exp.TriggerExecute)
    action = execute.this
    routine_schema: str | None = None
    routine_name: str
    if isinstance(action, exp.Anonymous):
        routine_name = _plain_identifier(exp.Identifier(this=str(action.this), quoted=False), "trigger routine")
    else:
        _require(
            isinstance(action, exp.Dot) and isinstance(action.expression, exp.Anonymous),
            "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED",
            "trigger action must call one named routine",
        )
        assert isinstance(action, exp.Dot)
        assert isinstance(action.expression, exp.Anonymous)
        routine_schema, routine_name = _routine_name(
            exp.Table(
                this=exp.Identifier(this=str(action.expression.this), quoted=False),
                db=action.this,
            ),
            namespace_map,
        )
    when: CheckExpression | None = None
    when_node = trigger_properties.args.get("when")
    if isinstance(when_node, exp.Expression):
        when = _parse_trigger_when(when_node, source_dialect)
    referencing = trigger_properties.args.get("referencing")
    transition_new_table: str | None = None
    transition_old_table: str | None = None
    if isinstance(referencing, exp.TriggerReferencing):
        new_node = referencing.args.get("new")
        old_node = referencing.args.get("old")
        if new_node is not None:
            transition_new_table = _plain_identifier(new_node, "trigger NEW transition table")
        if old_node is not None:
            transition_old_table = _plain_identifier(old_node, "trigger OLD transition table")
    return Trigger(
        name=name,
        table=table,
        timing=timing,
        events=event_values,
        row_level=str(trigger_properties.args.get("for_each", "")).upper() == "ROW",
        routine_name=routine_name,
        schema=table_schema,
        table_schema=table_schema,
        routine_schema=routine_schema,
        when=when,
        transition_new_table=transition_new_table,
        transition_old_table=transition_old_table,
        update_columns=update_columns,
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
    selected = ", ".join(
        column if column == "*" else quote_identifier(column, target_dialect) for column in query.columns
    )
    rendered = (
        f"CREATE{replace} VIEW {_object_name(view.schema, view.name, target_dialect)} AS SELECT {selected} "  # noqa: S608
        f"FROM {_object_name(query.table_schema, query.table, target_dialect)}"  # noqa: S608
    )
    if query.predicate is not None:
        rendered += f" WHERE {_render_check_expression(query.predicate, target_dialect)}"
    return rendered


def emit_comment(
    comment: Comment,
    target_dialect: Dialect,
    catalog: CommentColumnCatalogLike | None = None,
    routine_catalog: RoutineIdentityCatalogLike | None = None,
) -> str:
    def tsql_literal(value: str) -> str:
        return "N'" + value.replace(chr(39), chr(39) * 2) + "'"

    escaped = comment.text.replace(chr(39), chr(39) * 2)

    if comment.object_kind is CommentObjectKind.ROLE:
        if target_dialect is not Dialect.POSTGRES:
            raise DialectError(
                "CERTIFIED_COMMENT_TARGET_UNSUPPORTED",
                f"{target_dialect.value} has no exact standalone role-comment metadata route",
            )
        return f"COMMENT ON ROLE {quote_identifier(comment.object_name, target_dialect)} IS '{escaped}'"

    if comment.object_kind is CommentObjectKind.CONSTRAINT:
        if target_dialect is not Dialect.POSTGRES:
            raise DialectError(
                "CERTIFIED_COMMENT_TARGET_UNSUPPORTED",
                f"{target_dialect.value} has no exact standalone constraint comment route",
            )
        table = _object_name(comment.schema, comment.table_name or "", target_dialect)
        return f"COMMENT ON CONSTRAINT {comment.object_name} ON {table} IS '{escaped}'"

    if comment.object_kind is CommentObjectKind.FUNCTION:
        if target_dialect is Dialect.ORACLE:
            raise DialectError(
                "CERTIFIED_COMMENT_TARGET_UNSUPPORTED",
                f"{target_dialect.value} has no standalone COMMENT ON FUNCTION metadata route",
            )
        qualified = _object_name(comment.schema, comment.object_name, target_dialect)
        signature = ", ".join(quote_identifier(item, target_dialect) for item in comment.routine_argument_types)
        if target_dialect is Dialect.MYSQL:
            if routine_catalog is None or comment.routine_argument_type_refs is None:
                raise DialectError(
                    "CERTIFIED_COMMENT_ROUTINE_IDENTITY_REQUIRED",
                    "MySQL function comments require a catalog proof of one exact target routine identity",
                )
            if not routine_catalog.has_unique_routine(
                "FUNCTION",
                comment.schema,
                comment.object_name,
                comment.routine_argument_type_refs,
            ):
                raise DialectError(
                    "CERTIFIED_COMMENT_ROUTINE_IDENTITY_REQUIRED",
                    "source catalog cannot prove one exact routine identity for the MySQL function comment",
                )
            return f"ALTER FUNCTION {qualified} COMMENT '{escaped}'"
        if target_dialect is Dialect.TSQL:
            if comment.schema is None:
                raise DialectError(
                    "CERTIFIED_COMMENT_TARGET_SCHEMA_REQUIRED",
                    "SQL Server function properties require an explicit target schema mapping",
                )
            if len(comment.text.encode("utf-16-le")) > 7500:
                raise DialectError(
                    "CERTIFIED_COMMENT_TARGET_VALUE_TOO_LARGE",
                    "SQL Server extended-property values are limited to 7,500 bytes",
                )
            return (
                "EXEC sys.sp_addextendedproperty "
                "@name = N'MS_Description', "
                f"@value = {tsql_literal(comment.text)}, "
                "@level0type = N'SCHEMA', "
                f"@level0name = {tsql_literal(comment.schema)}, "
                "@level1type = N'FUNCTION', "
                f"@level1name = {tsql_literal(comment.object_name)}"
            )
        target = f"FUNCTION {qualified}({signature})"
        return f"COMMENT ON {target} IS '{escaped}'"

    if target_dialect is Dialect.MYSQL:
        if comment.object_kind is CommentObjectKind.COLUMN:
            if catalog is None:
                raise DialectError(
                    "CERTIFIED_COMMENT_TARGET_COLUMN_TYPE_REQUIRED",
                    "MySQL column comments require a full MODIFY/CHANGE column definition; "
                    "the one-statement COMMENT profile has no type/nullability/default catalogue",
                )
            column = catalog.column_of(
                comment.table_schema or comment.schema,
                comment.table_name or "",
                comment.object_name,
            )
            if column is None:
                raise DialectError(
                    "CERTIFIED_COMMENT_TARGET_COLUMN_TYPE_REQUIRED",
                    f"source catalogue has no complete definition for "
                    f"{comment.table_name or ''}.{comment.object_name}; "
                    "MySQL MODIFY COLUMN cannot be emitted without the full definition",
                )
            return (
                f"ALTER TABLE {_object_name(comment.schema, comment.table_name or '', target_dialect)} "
                f"MODIFY COLUMN {_render_column(column, target_dialect)} COMMENT '{escaped}'"
            )
        return f"ALTER TABLE {_object_name(comment.schema, comment.object_name, target_dialect)} COMMENT = '{escaped}'"

    if target_dialect is Dialect.TSQL:
        if comment.schema is None:
            raise DialectError(
                "CERTIFIED_COMMENT_TARGET_SCHEMA_REQUIRED",
                "SQL Server extended properties require an explicit target schema; supply a "
                "namespace_map entry for the source default namespace",
            )
        if len(comment.text.encode("utf-16-le")) > 7500:
            raise DialectError(
                "CERTIFIED_COMMENT_TARGET_VALUE_TOO_LARGE",
                "SQL Server extended-property values are limited to 7,500 bytes",
            )
        parts = [
            "@name = N'MS_Description'",
            f"@value = {tsql_literal(comment.text)}",
            "@level0type = N'SCHEMA'",
            f"@level0name = {tsql_literal(comment.schema)}",
            "@level1type = N'TABLE'",
            f"@level1name = {tsql_literal(comment.table_name or comment.object_name)}",
        ]
        if comment.object_kind is CommentObjectKind.COLUMN:
            parts.extend(
                [
                    "@level2type = N'COLUMN'",
                    f"@level2name = {tsql_literal(comment.object_name)}",
                ]
            )
        return "EXEC sys.sp_addextendedproperty " + ", ".join(parts)
    target = (
        f"TABLE {_object_name(comment.schema, comment.object_name, target_dialect)}"
        if comment.object_kind is CommentObjectKind.TABLE
        else (
            f"COLUMN {_object_name(comment.table_schema, comment.table_name or '', target_dialect)}."
            f"{quote_identifier(comment.object_name, target_dialect)}"
        )
    )
    return f"COMMENT ON {target} IS '{escaped}'"


def emit_privilege(
    privilege: Privilege,
    target_dialect: Dialect,
    routine_catalog: RoutineIdentityCatalogLike | None = None,
) -> str:
    if privilege.grant_option:
        raise DialectError(
            "CERTIFIED_PRIVILEGE_GRANT_OPTION_UNSUPPORTED",
            "grant-option lifecycle needs a target role/ownership policy",
        )
    privilege_list = ", ".join(privilege.privileges)
    principals = ", ".join(privilege.principals)
    if privilege.object_kind in {"FUNCTION", "PROCEDURE"}:
        target = _object_name(privilege.schema, privilege.object_name, target_dialect)
        if target_dialect is Dialect.POSTGRES:
            object_clause = (
                f"{privilege.object_kind} {target}({', '.join(privilege.routine_argument_types)})"
            )
        else:
            if routine_catalog is None or privilege.routine_argument_type_refs is None:
                raise DialectError(
                    "CERTIFIED_PRIVILEGE_ROUTINE_SIGNATURE_REQUIRED",
                    f"{target_dialect.value} routine privileges cannot safely drop the source "
                    "signature without a target routine-identity catalogue",
                )
            if not routine_catalog.has_unique_routine(
                privilege.object_kind,
                privilege.schema,
                privilege.object_name,
                privilege.routine_argument_type_refs,
            ):
                raise DialectError(
                    "CERTIFIED_PRIVILEGE_ROUTINE_SIGNATURE_REQUIRED",
                    f"source catalog cannot prove one exact {target_dialect.value} routine identity",
                )
            if target_dialect is Dialect.MYSQL:
                if any(principal.casefold() == "public" for principal in privilege.principals):
                    raise DialectError(
                        "CERTIFIED_PRIVILEGE_PRINCIPAL_UNSUPPORTED_BY_TARGET",
                        "MySQL has no PUBLIC grantee with PostgreSQL's all-account semantics",
                    )
                object_clause = f"{privilege.object_kind} {target}"
            elif target_dialect is Dialect.TSQL:
                object_clause = f"OBJECT::{target}"
            else:
                object_clause = target
    else:
        target = _object_name(privilege.schema, privilege.object_name, target_dialect)
        if target_dialect is Dialect.TSQL:
            object_clause = f"OBJECT::{target}"
        else:
            object_clause = target
        table_keyword = "TABLE " if target_dialect is Dialect.POSTGRES else ""
        object_clause = table_keyword + object_clause
    direction = "TO" if privilege.action is PrivilegeAction.GRANT else "FROM"
    return f"{privilege.action.value} {privilege_list} ON {object_clause} {direction} {principals}"


def emit_procedure(procedure: Procedure, target_dialect: Dialect) -> str:
    if procedure.or_replace and target_dialect not in (Dialect.POSTGRES, Dialect.ORACLE):
        raise DialectError(
            "CERTIFIED_ROUTINE_REPLACE_UNSUPPORTED_BY_TARGET",
            f"{target_dialect.value} has no exact CREATE OR REPLACE PROCEDURE spelling",
        )
    qualified = _object_name(procedure.schema, procedure.name, target_dialect)
    replace = " OR REPLACE" if procedure.or_replace and target_dialect in (Dialect.POSTGRES, Dialect.ORACLE) else ""

    def param(item: RoutineParameter) -> str:
        default = ""
        if item.default is not None:
            if target_dialect is Dialect.MYSQL:
                raise DialectError(
                    "CERTIFIED_ROUTINE_PARAMETER_DEFAULT_UNSUPPORTED_BY_TARGET",
                    "MySQL procedure parameters do not have an exact default-value signature route",
                )
            value = item.default.literal
            if item.default.kind.value == "NULL":
                rendered_default = "NULL"
            elif item.default.kind.value == "CURRENT_TIMESTAMP":
                rendered_default = "CURRENT_TIMESTAMP"
            elif item.default.kind.value == "STRING":
                assert value is not None
                rendered_default = "'" + value.replace("'", "''") + "'"
            elif item.default.kind.value == "BOOLEAN" and target_dialect in (Dialect.ORACLE, Dialect.TSQL):
                rendered_default = "1" if value == "true" else "0"
            else:
                assert value is not None
                rendered_default = value
            default = (" = " if target_dialect is Dialect.TSQL else " DEFAULT ") + rendered_default
        if target_dialect is Dialect.TSQL:
            output = " OUTPUT" if item.mode is not RoutineParameterMode.IN else ""
            return f"@{item.name} {_routine_type(item.type_ref, target_dialect)}{default}{output}"
        mode = item.mode.value if target_dialect in (Dialect.POSTGRES, Dialect.ORACLE, Dialect.MYSQL) else ""
        rendered_name = quote_identifier(item.name, target_dialect)
        rendered_type = _routine_type(item.type_ref, target_dialect)
        return f"{mode + ' ' if mode else ''}{rendered_name} {rendered_type}{default}"

    params = ", ".join(param(item) for item in procedure.parameters)
    statements: list[str] = []
    for assignment in procedure.assignments:
        left = ("@" if target_dialect is Dialect.TSQL else "") + quote_identifier(assignment.target, target_dialect)
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
    qualified = _object_name(function.schema, function.name, target_dialect)
    for item in function.parameters:
        if item.default is not None and target_dialect is Dialect.TSQL:
            raise DialectError(
                "CERTIFIED_ROUTINE_PARAMETER_DEFAULT_UNSUPPORTED_BY_TARGET",
                "SQL Server table-valued function parameters do not have default values",
            )

    def default_sql(item: RoutineParameter) -> str:
        if item.default is None:
            return ""
        value = item.default.literal
        if item.default.kind.value == "NULL":
            rendered = "NULL"
        elif item.default.kind.value == "CURRENT_TIMESTAMP":
            rendered = "CURRENT_TIMESTAMP"
        elif item.default.kind.value == "STRING":
            assert value is not None
            rendered = "'" + value.replace("'", "''") + "'"
        elif item.default.kind.value == "BOOLEAN":
            rendered = "TRUE" if value == "true" else "FALSE"
        else:
            assert value is not None
            rendered = value
        return " DEFAULT " + rendered

    params = ", ".join(
        ("@" if target_dialect is Dialect.TSQL else "")
        + quote_identifier(item.name, target_dialect)
        + " "
        + _routine_type(item.type_ref, target_dialect)
        + default_sql(item)
        for item in function.parameters
    )
    columns = ", ".join(
        quote_identifier(item.name, target_dialect)
        + " "
        + _routine_type(item.type_ref, target_dialect)
        for item in function.return_columns
    )
    selected = ", ".join(
        column if column == "*" else quote_identifier(column, target_dialect) for column in function.query.columns
    )
    source = _object_name(function.query.table_schema, function.query.table, target_dialect)
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


def _render_trigger_identifier(name: str, qualifier: str | None, dialect: Dialect) -> str:
    # OLD and NEW are PostgreSQL trigger pseudo-records, not user tables.
    # Quoting them would change the identifier lookup and make the emitted
    # predicate invalid, so only those two typed qualifiers bypass quoting.
    rendered_name = quote_identifier(name, dialect)
    if qualifier is None:
        return rendered_name
    rendered_qualifier = qualifier if qualifier.upper() in {"OLD", "NEW"} else quote_identifier(qualifier, dialect)
    return f"{rendered_qualifier}.{rendered_name}"


def _render_trigger_expression(expression: CheckExpression, dialect: Dialect) -> str:
    if isinstance(expression, CheckComparison):
        left = _render_trigger_identifier(expression.column, expression.column_qualifier, dialect)
        if expression.operator in {CheckOperator.IS_NULL, CheckOperator.IS_NOT_NULL}:
            return f"{left} {expression.operator.value}"
        if expression.right_column is not None:
            right = _render_trigger_identifier(
                expression.right_column, expression.right_column_qualifier, dialect
            )
        elif expression.literal_is_boolean:
            right = "TRUE" if expression.literal == "true" else "FALSE"
        else:
            right = (
                "'" + expression.literal.replace("'", "''") + "'"
                if expression.literal_is_string
                else expression.literal
            )
        if expression.operator is CheckOperator.IS_DISTINCT_FROM:
            return f"{left} IS DISTINCT FROM {right}"
        return f"{left} {check_operator_sql(expression.operator)} {right}"
    if isinstance(expression, CheckNotExpression):
        return f"NOT ({_render_trigger_expression(expression.operand, dialect)})"
    joiner = f" {expression.connector.value} "
    return joiner.join(
        f"({_render_trigger_expression(operand, dialect)})" for operand in expression.operands
    )


def emit_trigger(trigger: Trigger, target_dialect: Dialect) -> str:
    if target_dialect is not Dialect.POSTGRES:
        raise DialectError(
            "CERTIFIED_ROUTINE_TRIGGER_TARGET_ROUTE_REQUIRED",
            "trigger execution/action semantics are target-specific; this route emits only PostgreSQL trigger syntax",
        )
    if trigger.transition_new_table is not None or trigger.transition_old_table is not None:
        raise DialectError(
            "CERTIFIED_ROUTINE_TRIGGER_TARGET_ROUTE_REQUIRED",
            "trigger transition-table semantics require a target action ABI and are not dropped from this route",
        )
    event_sql: list[str] = []
    for event in trigger.events:
        if event is TriggerEvent.UPDATE and trigger.update_columns:
            columns = ", ".join(quote_identifier(column, target_dialect) for column in trigger.update_columns)
            event_sql.append(f"UPDATE OF {columns}")
        else:
            event_sql.append(event.value)
    events = " OR ".join(event_sql)
    row = " FOR EACH ROW" if trigger.row_level else " FOR EACH STATEMENT"
    when = "" if trigger.when is None else f" WHEN ({_render_trigger_expression(trigger.when, target_dialect)})"
    return (
        f"CREATE TRIGGER {quote_identifier(trigger.name, target_dialect)} {trigger.timing.value} {events} ON "
        f"{_object_name(trigger.table_schema, trigger.table, target_dialect)}{row}{when} "
        f"EXECUTE FUNCTION {_object_name(trigger.routine_schema, trigger.routine_name, target_dialect)}()"
    )
