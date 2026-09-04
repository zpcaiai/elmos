"""Typed routes for the next SQL coverage tranche.

This module intentionally keeps the new surface narrow and explicit:
ordinary views, comments, table privileges, bounded OUT-parameter procedures,
simple table-valued functions, trigger metadata, and one closed tenant-policy
shape. It does not turn a procedural body or security predicate into a text
blob. Unsupported control flow, dynamic SQL, non-PostgreSQL RLS emission,
materialization, and provider-specific options remain typed blockers.
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
    CursorLoop,
    Dialect,
    DialectError,
    DynamicExecuteStatement,
    ExceptionHandler,
    IfBranch,
    IfElseStatement,
    Privilege,
    PrivilegeAction,
    Procedure,
    RollbackSavepointStatement,
    RoutineAssignment,
    RoutineLanguage,
    RoutineParameter,
    RoutineParameterMode,
    RowPolicy,
    RowPolicyCommand,
    RowPolicyFunctionPredicate,
    RowPolicyMode,
    RowPolicySettingPredicate,
    SavepointStatement,
    TableFunction,
    TableFunctionColumn,
    Trigger,
    TriggerEvent,
    TriggerTiming,
    TypeMigrationPolicy,
    View,
    ViewQuery,
    WhileLoop,
)
from .parser import (
    _IDENTIFIER_RE,
    _mapped_table_name,
    _parse_check,
    _parse_type,
    _plain_identifier,
    _require,
    _require_single_statement,
    _row_security_tokens,
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
        argument_types = tuple(_plain_identifier(item, "comment function argument type") for item in target.expressions)
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

                default = _parse_default(
                    constraint_kind.this,
                    _parse_type(item.kind, source_dialect),
                    source_dialect,
                )
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
    raw = str(body.this).strip().rstrip(";")
    if raw.upper().startswith("BEGIN"):
        raw = raw[5:].strip()
    if raw.upper().endswith("END"):
        raw = raw[:-3].strip().rstrip(";").strip()

    try:
        statements: list[exp.Expression] = []
        for item in sqlglot.parse(raw, read=source_dialect.value):
            if isinstance(item, exp.Expression):
                statements.append(item)
        if statements:
            return statements
    except sqlglot.errors.SqlglotError:
        pass

    statements = []
    current: list[str] = []
    in_loop = False
    in_if = False
    for line in raw.splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        current.append(line_s)
        upper = line_s.upper()
        if "LOOP" in upper and "END LOOP" not in upper:
            in_loop = True
        if "END LOOP" in upper:
            in_loop = False
        if re.search(r"\bIF\b", upper) and not re.search(r"\bEND\s+IF\b", upper):
            in_if = True
        if re.search(r"\bEND\s+IF\b", upper):
            in_if = False
        if line_s.endswith(";") and not in_loop and not in_if:
            chunk = " ".join(current).rstrip(";").strip()
            current = []
            if chunk:
                try:
                    stmt = sqlglot.parse_one(chunk, read=source_dialect.value)
                    statements.append(stmt)
                except Exception:
                    statements.append(exp.Command(this=chunk))
    if current:
        chunk = " ".join(current).rstrip(";").strip()
        if chunk:
            try:
                stmt = sqlglot.parse_one(chunk, read=source_dialect.value)
                statements.append(stmt)
            except Exception:
                statements.append(exp.Command(this=chunk))
    return statements


def parse_procedure(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
    *,
    allow_dynamic_sql: bool = False,
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
    savepoints: list[SavepointStatement] = []
    rollback_savepoints: list[RollbackSavepointStatement] = []
    cursor_loops: list[CursorLoop] = []
    exception_handlers: list[ExceptionHandler] = []
    if_statements: list[IfElseStatement] = []
    while_loops: list[WhileLoop] = []
    dynamic_executes: list[DynamicExecuteStatement] = []

    for item in _body_statements(statement.args.get("expression"), source_dialect):
        if isinstance(item, exp.Set):
            for set_item in item.expressions:
                target = set_item.this
                _require(
                    isinstance(target, exp.EQ), "CERTIFIED_ROUTINE_UNSUPPORTED_BODY", "SET assignment is malformed"
                )
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
        elif isinstance(item, exp.PropertyEQ | exp.EQ):
            lhs = item.this
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
            value = _parse_value(item.expression, parameter_map, source_dialect)
            assignments.append(RoutineAssignment(target_name, value))
        elif isinstance(item, exp.Rollback):
            sp_id = item.args.get("savepoint")
            sp_name = str(sp_id.this if hasattr(sp_id, "this") else (sp_id or ""))
            if not sp_name:
                tokens = item.sql().split()
                sp_name = tokens[-1].rstrip(";")
            rollback_savepoints.append(RollbackSavepointStatement(name=sp_name))
        else:
            item_sql = item.sql().strip()
            item_upper = item_sql.upper()
            if item_upper.startswith("SAVEPOINT "):
                sp_name = item_sql.split()[-1].rstrip(";")
                savepoints.append(SavepointStatement(name=sp_name))
            elif item_upper.startswith("SAVE TRANSACTION ") or item_upper.startswith("SAVE TRAN "):
                sp_name = item_sql.split()[-1].rstrip(";")
                savepoints.append(SavepointStatement(name=sp_name))
            elif "ROLLBACK TO" in item_upper or "ROLLBACK TRANSACTION" in item_upper or "ROLLBACK TRAN" in item_upper:
                sp_name = item_sql.split()[-1].rstrip(";")
                rollback_savepoints.append(RollbackSavepointStatement(name=sp_name))
            elif item_upper.startswith("FOR ") and " IN " in item_upper and " LOOP" in item_upper:
                m = re.search(
                    r"FOR\s+(\w+)\s+IN\s*\((.*?)\)\s*LOOP(.*?)END\s+LOOP", item_sql, re.IGNORECASE | re.DOTALL
                )
                if m:
                    cur_name, cur_query, cur_body = m.groups()
                    cursor_loops.append(
                        CursorLoop(
                            cursor_name=cur_name.strip(),
                            query_sql=cur_query.strip(),
                            body_statements=(cur_body.strip(),),
                        )
                    )
                else:
                    raise DialectError("CERTIFIED_ROUTINE_UNSUPPORTED_BODY", f"cursor loop malformed: {item_sql}")
            elif item_upper.startswith("EXCEPTION"):
                m = re.search(r"EXCEPTION\s+WHEN\s+(\w+)\s+THEN(.*)", item_sql, re.IGNORECASE | re.DOTALL)
                if m:
                    cond, act = m.groups()
                    exception_handlers.append(
                        ExceptionHandler(condition=cond.strip(), action_statements=(act.strip(),))
                    )
                else:
                    raise DialectError("CERTIFIED_ROUTINE_UNSUPPORTED_BODY", f"exception block malformed: {item_sql}")
            elif item_upper.startswith("IF ") or item_upper.startswith("IF\n"):
                branches: list[IfBranch] = []
                else_stmts: list[str] = []
                if "END IF" in item_upper:
                    m_if = re.search(
                        r"IF\s+(.*?)\s+THEN\s+(.*?)(?=\s+(?:ELSIF|ELSEIF|ELSE|END\s+IF))",
                        item_sql,
                        re.IGNORECASE | re.DOTALL,
                    )
                    if m_if:
                        branches.append(IfBranch(condition=m_if.group(1).strip(), statements=(m_if.group(2).strip(),)))
                        for m_elsif in re.finditer(
                            r"(?:ELSIF|ELSEIF)\s+(.*?)\s+THEN\s+(.*?)(?=\s+(?:ELSIF|ELSEIF|ELSE|END\s+IF))",
                            item_sql,
                            re.IGNORECASE | re.DOTALL,
                        ):
                            branches.append(
                                IfBranch(condition=m_elsif.group(1).strip(), statements=(m_elsif.group(2).strip(),))
                            )
                        m_else = re.search(r"ELSE\s+(.*?)\s+END\s+IF", item_sql, re.IGNORECASE | re.DOTALL)
                        if m_else:
                            else_stmts.append(m_else.group(1).strip())
                    if branches:
                        if_statements.append(
                            IfElseStatement(branches=tuple(branches), else_statements=tuple(else_stmts))
                        )
                    else:
                        raise DialectError("CERTIFIED_ROUTINE_UNSUPPORTED_BODY", f"malformed IF statement: {item_sql}")
                elif "BEGIN" in item_upper and "END" in item_upper:
                    m_tsql_if = re.search(
                        r"IF\s+(.*?)\s+BEGIN\s+(.*?)\s+END(?:\s+ELSE\s+BEGIN\s+(.*?)\s+END)?",
                        item_sql,
                        re.IGNORECASE | re.DOTALL,
                    )
                    if m_tsql_if:
                        cond = m_tsql_if.group(1).strip()
                        then_stmt = m_tsql_if.group(2).strip()
                        branches.append(IfBranch(condition=cond, statements=(then_stmt,)))
                        if m_tsql_if.group(3):
                            else_stmts.append(m_tsql_if.group(3).strip())
                        if_statements.append(
                            IfElseStatement(branches=tuple(branches), else_statements=tuple(else_stmts))
                        )
                    else:
                        raise DialectError(
                            "CERTIFIED_ROUTINE_UNSUPPORTED_BODY", f"malformed T-SQL IF statement: {item_sql}"
                        )
                else:
                    raise DialectError("CERTIFIED_ROUTINE_UNSUPPORTED_BODY", f"unsupported IF structure: {item_sql}")
            elif item_upper.startswith("WHILE ") or item_upper.startswith("WHILE\n"):
                m_while = re.search(
                    r"WHILE\s+(.*?)\s+(?:LOOP|BEGIN)\s+(.*?)\s+(?:END\s+LOOP|END)", item_sql, re.IGNORECASE | re.DOTALL
                )
                if m_while:
                    cond, body = m_while.groups()
                    while_loops.append(WhileLoop(condition=cond.strip(), body_statements=(body.strip(),)))
                else:
                    raise DialectError("CERTIFIED_ROUTINE_UNSUPPORTED_BODY", f"malformed WHILE statement: {item_sql}")
            elif (
                item_upper.startswith("EXECUTE ")
                or item_upper.startswith("EXECUTE\n")
                or item_upper.startswith("EXEC ")
            ):
                if not allow_dynamic_sql:
                    raise DialectError(
                        "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
                        f"dynamic SQL is not certified in routine body: {item_sql}",
                    )
                m_dyn = re.search(
                    r"(?:EXECUTE\s+IMMEDIATE|EXECUTE|EXEC\s+sp_executesql)\s+(.*?)(?:\s+INTO\s+(\w+))?;?$",
                    item_sql,
                    re.IGNORECASE | re.DOTALL,
                )
                if m_dyn:
                    dyn_expr = m_dyn.group(1).strip().rstrip(";")
                    dyn_into = m_dyn.group(2).strip() if m_dyn.group(2) else None
                    dynamic_executes.append(DynamicExecuteStatement(query_expression=dyn_expr, into_variable=dyn_into))
                else:
                    raise DialectError(
                        "CERTIFIED_ROUTINE_UNSUPPORTED_BODY", f"dynamic SQL statement malformed: {item_sql}"
                    )
            else:
                raise DialectError(
                    "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
                    f"unsupported procedure statement {type(item).__name__}: {item_sql}",
                )

    _require(
        bool(assignments)
        or bool(savepoints)
        or bool(rollback_savepoints)
        or bool(cursor_loops)
        or bool(exception_handlers)
        or bool(if_statements)
        or bool(while_loops)
        or bool(dynamic_executes),
        "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
        "procedure has no supported statements",
    )
    return Procedure(
        name,
        parameters,
        tuple(assignments),
        schema=schema,
        or_replace=bool(statement.args.get("replace")),
        savepoints=tuple(savepoints),
        rollback_savepoints=tuple(rollback_savepoints),
        cursor_loops=tuple(cursor_loops),
        exception_handlers=tuple(exception_handlers),
        if_statements=tuple(if_statements),
        while_loops=tuple(while_loops),
        dynamic_executes=tuple(dynamic_executes),
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
    security_definer = False
    search_path: tuple[str, ...] = ()
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
                security_definer = str(prop.args.get("this", "")).upper() == "DEFINER"
                continue
            if isinstance(prop, exp.SetConfigProperty):
                search_path = ("<source-defined>",)
                continue
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
    if body is None and isinstance(properties, exp.Properties):
        for prop in properties.expressions:
            if isinstance(prop, exp.SetConfigProperty):
                for alias in prop.find_all(exp.Alias):
                    alias_id = alias.args.get("alias")
                    if isinstance(alias_id, exp.Identifier):
                        body = exp.Heredoc(this=alias_id.this)
                        break
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
        security_definer=security_definer,
        search_path=search_path,
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


def _row_policy_identifier(token: object, what: str) -> exp.Identifier:
    token_type = getattr(token, "token_type", None)
    kind_name = getattr(token_type, "name", "")
    _require(
        kind_name in {"VAR", "IDENTIFIER"},
        "CERTIFIED_RLS_UNSUPPORTED_IDENTIFIER_SHAPE",
        f"{what} must be a plain or double-quoted identifier",
    )
    return exp.Identifier(this=str(getattr(token, "text", "")), quoted=kind_name == "IDENTIFIER")


def _row_policy_group(tokens: list[object], start: int, what: str) -> tuple[list[object], int]:
    _require(
        start < len(tokens) and str(getattr(tokens[start], "text", "")) == "(",
        "CERTIFIED_RLS_UNSUPPORTED_STATEMENT",
        f"{what} must be parenthesized",
    )
    depth = 0
    for index in range(start, len(tokens)):
        value = str(getattr(tokens[index], "text", ""))
        if value == "(":
            depth += 1
        elif value == ")":
            depth -= 1
            if depth == 0:
                return tokens[start + 1 : index], index + 1
    raise DialectError("CERTIFIED_RLS_UNSUPPORTED_STATEMENT", f"{what} has no closing parenthesis")


def _parse_row_policy_predicate(
    tokens: list[object], what: str, namespace_map: Mapping[str, str] | None = None
) -> RowPolicySettingPredicate | RowPolicyFunctionPredicate:
    values = [str(getattr(token, "text", "")) for token in tokens]
    upper = [value.upper() for value in values]
    if len(tokens) == 8 and upper[1:4] == ["=", "CURRENT_SETTING", "("]:
        _require(
            upper[5] == "," and upper[6] in {"TRUE", "FALSE"} and upper[7] == ")",
            "CERTIFIED_RLS_UNSUPPORTED_PREDICATE",
            f"{what} must compare one column with current_setting(<key>, <missing_ok>)",
        )
        column = _plain_identifier(_row_policy_identifier(tokens[0], f"{what} column"), f"{what} column")
        setting_type = getattr(getattr(tokens[4], "token_type", None), "name", "")
        _require(
            setting_type == "STRING",
            "CERTIFIED_RLS_UNSUPPORTED_PREDICATE",
            f"{what} current_setting key must be a string literal",
        )
        return RowPolicySettingPredicate(
            column=column,
            setting_name=values[4],
            missing_ok=upper[6] == "TRUE",
        )
    if len(tokens) >= 4 and upper[1] == "=":
        column = _plain_identifier(_row_policy_identifier(tokens[0], f"{what} column"), f"{what} column")
        if len(tokens) == 7 and upper[3] == "." and upper[5:7] == ["(", ")"]:
            raw_schema = _plain_identifier(
                _row_policy_identifier(tokens[2], f"{what} function schema"), f"{what} function schema"
            )
            mapped_schema = namespace_map.get(raw_schema, raw_schema) if namespace_map else raw_schema
            function_name = _plain_identifier(
                _row_policy_identifier(tokens[4], f"{what} function name"), f"{what} function name"
            )
            return RowPolicyFunctionPredicate(
                column=column,
                function_name=function_name,
                function_schema=mapped_schema,
            )
        if len(tokens) == 5 and upper[3:5] == ["(", ")"]:
            function_name = _plain_identifier(
                _row_policy_identifier(tokens[2], f"{what} function name"), f"{what} function name"
            )
            return RowPolicyFunctionPredicate(
                column=column,
                function_name=function_name,
                function_schema=None,
            )
    raise DialectError(
        "CERTIFIED_RLS_UNSUPPORTED_PREDICATE",
        f"{what} must compare one column with current_setting(<key>, <missing_ok>) or [schema.]function()",
    )


def parse_row_policy(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> RowPolicy:
    """Parse the closed PostgreSQL tenant-policy shape into typed RLS IR.

    Only the default ``PERMISSIVE FOR ALL TO PUBLIC`` policy with explicit
    USING and WITH CHECK predicates is admitted. Both predicates must be a
    typed tenant-column/current_setting comparison or function call. Other command,
    role, composition, cast, or boolean semantics remain blocked.
    """

    _require(
        source_dialect is Dialect.POSTGRES,
        "CERTIFIED_RLS_UNSUPPORTED_SOURCE",
        "CREATE POLICY is admitted only from PostgreSQL",
    )
    raw_sql = sql if isinstance(sql, str) else sql.sql()
    tokens = _row_security_tokens(raw_sql, source_dialect)
    upper = [str(getattr(token, "text", "")).upper() for token in tokens]
    _require(
        len(tokens) >= 15 and upper[:2] == ["CREATE", "POLICY"] and upper[3] == "ON",
        "CERTIFIED_RLS_UNSUPPORTED_STATEMENT",
        "expected CREATE POLICY <name> ON <table> USING (...) WITH CHECK (...) ",
    )
    policy_name = _plain_identifier(_row_policy_identifier(tokens[2], "RLS policy name"), "RLS policy name")
    try:
        using_index = upper.index("USING", 4)
    except ValueError as exc:
        raise DialectError(
            "CERTIFIED_RLS_UNSUPPORTED_STATEMENT",
            "RLS policy requires an explicit USING predicate",
        ) from exc
    table_tokens = tokens[4:using_index]
    _require(
        len(table_tokens) in {1, 3},
        "CERTIFIED_RLS_UNSUPPORTED_MODIFIER",
        "AS, FOR, TO and other RLS policy modifiers are outside the default typed route",
    )
    if len(table_tokens) == 3:
        _require(
            str(getattr(table_tokens[1], "text", "")) == ".",
            "CERTIFIED_RLS_UNSUPPORTED_IDENTIFIER_SHAPE",
            "RLS policy table qualification must use one schema and one table",
        )
    table_node = exp.Table(
        this=_row_policy_identifier(table_tokens[-1], "RLS policy table"),
        db=_row_policy_identifier(table_tokens[0], "RLS policy schema") if len(table_tokens) == 3 else None,
    )
    schema, table = _mapped_table_name(table_node, "RLS policy table", namespace_map)
    using_tokens, next_index = _row_policy_group(tokens, using_index + 1, "RLS USING predicate")
    _require(
        upper[next_index : next_index + 2] == ["WITH", "CHECK"],
        "CERTIFIED_RLS_UNSUPPORTED_STATEMENT",
        "RLS policy requires an explicit WITH CHECK predicate",
    )
    check_tokens, end_index = _row_policy_group(tokens, next_index + 2, "RLS WITH CHECK predicate")
    _require(
        end_index == len(tokens),
        "CERTIFIED_RLS_UNSUPPORTED_MODIFIER",
        "trailing RLS policy clauses are outside the typed route",
    )
    return RowPolicy(
        name=policy_name,
        table=table,
        schema=schema,
        mode=RowPolicyMode.PERMISSIVE,
        command=RowPolicyCommand.ALL,
        roles=("PUBLIC",),
        using_predicate=_parse_row_policy_predicate(using_tokens, "RLS USING predicate", namespace_map),
        check_predicate=_parse_row_policy_predicate(check_tokens, "RLS WITH CHECK predicate", namespace_map),
    )


def emit_row_policy(policy: RowPolicy, target_dialect: Dialect, allow_rls_shim: bool = False) -> str:
    """Emit the typed policy only where PostgreSQL RLS semantics are native."""

    if target_dialect is not Dialect.POSTGRES:
        if not allow_rls_shim:
            raise DialectError(
                "CERTIFIED_RLS_TARGET_ROUTE_REQUIRED",
                f"{target_dialect.value} has no exact PostgreSQL policy evaluation and owner-bypass mapping; "
                "the route will not downgrade RLS to ordinary privileges",
            )
        col = quote_identifier(policy.using_predicate.column, target_dialect)
        if target_dialect is Dialect.TSQL:
            schema = policy.schema or "dbo"
            sec_schema = quote_identifier(schema, target_dialect)
            pol_name = quote_identifier(policy.name, target_dialect)
            tbl_name = _object_name(policy.schema, policy.table, target_dialect)
            return (
                f"CREATE SECURITY POLICY {sec_schema}.{pol_name} "
                f"ADD FILTER PREDICATE {sec_schema}.fn_rls({col}) "
                f"ON {tbl_name} WITH (STATE = ON)"
            )
        elif target_dialect is Dialect.ORACLE:
            schema_str = f"'{policy.schema}'" if policy.schema else "USER"
            return f"CALL DBMS_RLS.ADD_POLICY({schema_str}, '{policy.table}', '{policy.name}', {schema_str}, 'fn_rls')"
        elif target_dialect is Dialect.MYSQL:
            return f"CALL sys.add_row_policy('{policy.schema or ''}', '{policy.table}', '{policy.name}')"

    def predicate(value: RowPolicySettingPredicate | RowPolicyFunctionPredicate | None) -> str:
        if value is None:
            return ""
        if isinstance(value, RowPolicySettingPredicate):
            setting = value.setting_name.replace("'", "''")
            missing_ok = "TRUE" if value.missing_ok else "FALSE"
            return f"{quote_identifier(value.column, target_dialect)} = current_setting('{setting}', {missing_ok})"
        if isinstance(value, RowPolicyFunctionPredicate):
            fn = quote_identifier(value.function_name, target_dialect)
            if value.function_schema:
                schema_prefix = f"{quote_identifier(value.function_schema, target_dialect)}."
            else:
                schema_prefix = ""
            return f"{quote_identifier(value.column, target_dialect)} = {schema_prefix}{fn}()"
        raise TypeError(f"unhandled predicate type: {type(value).__name__}")

    roles = ", ".join(
        "PUBLIC" if str(role).upper() == "PUBLIC" else quote_identifier(role, target_dialect) for role in policy.roles
    )
    with_check = f" WITH CHECK ({predicate(policy.check_predicate)})" if policy.check_predicate is not None else ""
    return (
        f"CREATE POLICY {quote_identifier(policy.name, target_dialect)} "
        f"ON {_object_name(policy.schema, policy.table, target_dialect)} "
        f"AS {policy.mode.value} FOR {policy.command.value} TO {roles} "
        f"USING ({predicate(policy.using_predicate)}){with_check}"
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
    allow_comment_shim: bool = False,
    type_policy: TypeMigrationPolicy | None = None,
) -> str:
    def tsql_literal(value: str) -> str:
        return "N'" + value.replace(chr(39), chr(39) * 2) + "'"

    escaped = comment.text.replace(chr(39), chr(39) * 2)

    if comment.object_kind is CommentObjectKind.ROLE:
        if target_dialect is Dialect.TSQL:
            if len(comment.text.encode("utf-16-le")) > 7500:
                raise DialectError(
                    "CERTIFIED_COMMENT_TARGET_VALUE_TOO_LARGE",
                    "SQL Server extended-property values are limited to 7,500 bytes",
                )
            # SQL Server documents application-role metadata through the
            # database-principal level-0 USER scope.  Keeping the role name
            # at that level preserves the object identity; do not attach it
            # to a schema or silently turn it into a table comment.
            return (
                "EXEC sys.sp_addextendedproperty "
                "@name = N'MS_Description', "
                f"@value = {tsql_literal(comment.text)}, "
                "@level0type = N'USER', "
                f"@level0name = {tsql_literal(comment.object_name)}"
            )
        if target_dialect is not Dialect.POSTGRES:
            if not allow_comment_shim:
                raise DialectError(
                    "CERTIFIED_COMMENT_TARGET_UNSUPPORTED",
                    f"{target_dialect.value} has no exact standalone role-comment metadata route",
                )
            return f"-- COMMENT ON ROLE {quote_identifier(comment.object_name, target_dialect)} IS '{escaped}'"
        return f"COMMENT ON ROLE {quote_identifier(comment.object_name, target_dialect)} IS '{escaped}'"

    if comment.object_kind is CommentObjectKind.CONSTRAINT:
        if target_dialect is Dialect.TSQL:
            target_schema = comment.schema or ("dbo" if allow_comment_shim else None)
            if target_schema is None or comment.table_name is None:
                if allow_comment_shim:
                    return f"-- COMMENT ON CONSTRAINT {comment.object_name} IS '{escaped}'"
                raise DialectError(
                    "CERTIFIED_COMMENT_TARGET_SCHEMA_REQUIRED",
                    "SQL Server constraint properties require explicit schema and table identity",
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
                f"@level0name = {tsql_literal(target_schema)}, "
                "@level1type = N'TABLE', "
                f"@level1name = {tsql_literal(comment.table_name)}, "
                "@level2type = N'CONSTRAINT', "
                f"@level2name = {tsql_literal(comment.object_name)}"
            )
        if target_dialect is not Dialect.POSTGRES:
            if not allow_comment_shim:
                raise DialectError(
                    "CERTIFIED_COMMENT_TARGET_UNSUPPORTED",
                    f"{target_dialect.value} has no exact standalone constraint comment route",
                )
            return f"-- COMMENT ON CONSTRAINT {comment.object_name} IS '{escaped}'"
        table = _object_name(comment.schema, comment.table_name or "", target_dialect)
        return f"COMMENT ON CONSTRAINT {comment.object_name} ON {table} IS '{escaped}'"

    if comment.object_kind is CommentObjectKind.FUNCTION:
        if target_dialect is Dialect.ORACLE:
            if not allow_comment_shim:
                raise DialectError(
                    "CERTIFIED_COMMENT_TARGET_UNSUPPORTED",
                    f"{target_dialect.value} has no standalone COMMENT ON FUNCTION metadata route",
                )
            qualified = _object_name(comment.schema, comment.object_name, target_dialect)
            return f"-- COMMENT ON FUNCTION {qualified} IS '{escaped}'"
        qualified = _object_name(comment.schema, comment.object_name, target_dialect)
        signature = ", ".join(quote_identifier(item, target_dialect) for item in comment.routine_argument_types)
        if target_dialect is Dialect.MYSQL:
            if routine_catalog is None or comment.routine_argument_type_refs is None:
                if allow_comment_shim:
                    return f"ALTER FUNCTION {qualified} COMMENT '{escaped}'"
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
                if allow_comment_shim:
                    return f"ALTER FUNCTION {qualified} COMMENT '{escaped}'"
                raise DialectError(
                    "CERTIFIED_COMMENT_ROUTINE_IDENTITY_REQUIRED",
                    "source catalog cannot prove one exact routine identity for the MySQL function comment",
                )
            return f"ALTER FUNCTION {qualified} COMMENT '{escaped}'"
        if target_dialect is Dialect.TSQL:
            target_schema = comment.schema or ("dbo" if allow_comment_shim else None)
            if target_schema is None:
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
                f"@level0name = {tsql_literal(target_schema)}, "
                "@level1type = N'FUNCTION', "
                f"@level1name = {tsql_literal(comment.object_name)}"
            )
        target = f"FUNCTION {qualified}({signature})"
        return f"COMMENT ON {target} IS '{escaped}'"

    if target_dialect is Dialect.MYSQL:
        if comment.object_kind is CommentObjectKind.COLUMN:
            if catalog is None:
                if allow_comment_shim:
                    return f"-- COMMENT ON COLUMN {comment.table_name or ''}.{comment.object_name} IS '{escaped}'"
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
                if allow_comment_shim:
                    return f"-- COMMENT ON COLUMN {comment.table_name or ''}.{comment.object_name} IS '{escaped}'"
                raise DialectError(
                    "CERTIFIED_COMMENT_TARGET_COLUMN_TYPE_REQUIRED",
                    f"source catalogue has no complete definition for "
                    f"{comment.table_name or ''}.{comment.object_name}; "
                    "MySQL MODIFY COLUMN cannot be emitted without the full definition",
                )
            try:
                rendered_col = _render_column(column, target_dialect, type_policy=type_policy)
            except DialectError:
                if allow_comment_shim:
                    return f"-- COMMENT ON COLUMN {comment.table_name or ''}.{comment.object_name} IS '{escaped}'"
                raise
            return (
                f"ALTER TABLE {_object_name(comment.schema, comment.table_name or '', target_dialect)} "
                f"MODIFY COLUMN {rendered_col} COMMENT '{escaped}'"
            )
        return f"ALTER TABLE {_object_name(comment.schema, comment.object_name, target_dialect)} COMMENT = '{escaped}'"

    if target_dialect is Dialect.TSQL:
        target_schema = comment.schema or ("dbo" if allow_comment_shim else None)
        if target_schema is None:
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
            f"@level0name = {tsql_literal(target_schema)}",
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
    allow_privilege_shim: bool = False,
) -> str:
    if privilege.grant_option:
        raise DialectError(
            "CERTIFIED_PRIVILEGE_GRANT_OPTION_UNSUPPORTED",
            "grant-option lifecycle needs a target role/ownership policy",
        )
    privilege_list = ", ".join(privilege.privileges)
    principals = ", ".join(
        "'%'@'%'" if target_dialect is Dialect.MYSQL and p.casefold() == "public" and allow_privilege_shim else p
        for p in privilege.principals
    )
    if privilege.object_kind in {"FUNCTION", "PROCEDURE"}:
        target = _object_name(privilege.schema, privilege.object_name, target_dialect)
        if target_dialect is Dialect.POSTGRES:
            object_clause = f"{privilege.object_kind} {target}({', '.join(privilege.routine_argument_types)})"
        else:
            if not allow_privilege_shim and (routine_catalog is None or privilege.routine_argument_type_refs is None):
                raise DialectError(
                    "CERTIFIED_PRIVILEGE_ROUTINE_SIGNATURE_REQUIRED",
                    f"{target_dialect.value} routine privileges cannot safely drop the source "
                    "signature without a target routine-identity catalogue",
                )
            if not allow_privilege_shim and not routine_catalog.has_unique_routine(
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
                if (
                    any(principal.casefold() == "public" for principal in privilege.principals)
                    and not allow_privilege_shim
                ):
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
        if target_dialect is Dialect.MYSQL:
            if any(principal.casefold() == "public" for principal in privilege.principals) and not allow_privilege_shim:
                raise DialectError(
                    "CERTIFIED_PRIVILEGE_PRINCIPAL_UNSUPPORTED_BY_TARGET",
                    "MySQL has no PUBLIC grantee with PostgreSQL's all-account semantics",
                )
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

    for sp in procedure.savepoints:
        if target_dialect is Dialect.TSQL:
            statements.append(f"SAVE TRANSACTION {sp.name};")
        else:
            statements.append(f"SAVEPOINT {sp.name};")

    for cl in procedure.cursor_loops:
        inner = " ".join(cl.body_statements)
        if target_dialect in (Dialect.POSTGRES, Dialect.ORACLE):
            statements.append(f"FOR {cl.cursor_name} IN ({cl.query_sql}) LOOP {inner}; END LOOP;")
        elif target_dialect is Dialect.TSQL:
            statements.append(
                f"DECLARE {cl.cursor_name}_cur CURSOR FOR {cl.query_sql}; "
                f"OPEN {cl.cursor_name}_cur; {inner}; CLOSE {cl.cursor_name}_cur; "
                f"DEALLOCATE {cl.cursor_name}_cur;"
            )
        elif target_dialect is Dialect.MYSQL:
            statements.append(f"BEGIN DECLARE {cl.cursor_name}_cur CURSOR FOR {cl.query_sql}; {inner}; END;")

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

    for rsp in procedure.rollback_savepoints:
        if target_dialect is Dialect.TSQL:
            statements.append(f"ROLLBACK TRANSACTION {rsp.name};")
        elif target_dialect is Dialect.ORACLE:
            statements.append(f"ROLLBACK TO {rsp.name};")
        else:
            statements.append(f"ROLLBACK TO SAVEPOINT {rsp.name};")

    for if_stmt in procedure.if_statements:
        if target_dialect in (Dialect.POSTGRES, Dialect.ORACLE, Dialect.MYSQL):
            elsif_kw = "ELSEIF" if target_dialect is Dialect.MYSQL else "ELSIF"
            parts = [f"IF {if_stmt.branches[0].condition} THEN {' '.join(if_stmt.branches[0].statements)};"]
            for branch in if_stmt.branches[1:]:
                parts.append(f"{elsif_kw} {branch.condition} THEN {' '.join(branch.statements)};")
            if if_stmt.else_statements:
                parts.append(f"ELSE {' '.join(if_stmt.else_statements)};")
            parts.append("END IF;")
            statements.append(" ".join(parts))
        elif target_dialect is Dialect.TSQL:
            parts = [f"IF {if_stmt.branches[0].condition} BEGIN {' '.join(if_stmt.branches[0].statements)}; END"]
            for branch in if_stmt.branches[1:]:
                parts.append(f"ELSE IF {branch.condition} BEGIN {' '.join(branch.statements)}; END")
            if if_stmt.else_statements:
                parts.append(f"ELSE BEGIN {' '.join(if_stmt.else_statements)}; END")
            statements.append(" ".join(parts))

    for loop in procedure.while_loops:
        inner = " ".join(loop.body_statements)
        if target_dialect in (Dialect.POSTGRES, Dialect.ORACLE, Dialect.MYSQL):
            statements.append(f"WHILE {loop.condition} LOOP {inner}; END LOOP;")
        elif target_dialect is Dialect.TSQL:
            statements.append(f"WHILE {loop.condition} BEGIN {inner}; END")

    for dyn in procedure.dynamic_executes:
        if target_dialect is Dialect.POSTGRES:
            into_clause = f" INTO {dyn.into_variable}" if dyn.into_variable else ""
            statements.append(f"EXECUTE {dyn.query_expression}{into_clause};")
        elif target_dialect is Dialect.ORACLE:
            into_clause = f" INTO {dyn.into_variable}" if dyn.into_variable else ""
            statements.append(f"EXECUTE IMMEDIATE {dyn.query_expression}{into_clause};")
        elif target_dialect is Dialect.TSQL:
            statements.append(f"EXEC sp_executesql {dyn.query_expression};")
        elif target_dialect is Dialect.MYSQL:
            statements.append(
                f"SET @dyn_stmt = {dyn.query_expression}; PREPARE stmt FROM @dyn_stmt; "
                "EXECUTE stmt; DEALLOCATE PREPARE stmt;"
            )

    exc_statements: list[str] = []
    for handler in procedure.exception_handlers:
        act = " ".join(handler.action_statements)
        if target_dialect in (Dialect.POSTGRES, Dialect.ORACLE):
            exc_statements.append(f"EXCEPTION WHEN {handler.condition} THEN {act};")
        elif target_dialect is Dialect.TSQL:
            exc_statements.append(f"BEGIN CATCH {act}; END CATCH")
        elif target_dialect is Dialect.MYSQL:
            exc_statements.append(f"DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN {act}; END;")

    body = " ".join(statements)
    if exc_statements:
        if target_dialect is Dialect.TSQL:
            body = f"BEGIN TRY {body} END TRY " + " ".join(exc_statements)
        else:
            body = body + " " + " ".join(exc_statements)

    if target_dialect is Dialect.MYSQL:
        return f"CREATE PROCEDURE {qualified} ({params}) BEGIN {body} END"
    if target_dialect is Dialect.TSQL:
        return f"CREATE PROCEDURE {qualified} {params} AS BEGIN {body} END"
    if target_dialect is Dialect.ORACLE:
        return f"CREATE{replace} PROCEDURE {qualified}({params}) IS BEGIN {body} END;"
    return f"CREATE{replace} PROCEDURE {qualified}({params}) LANGUAGE plpgsql AS $$ BEGIN {body} END $$"


def emit_table_function(function: TableFunction, target_dialect: Dialect, allow_routine_shim: bool = False) -> str:
    if target_dialect not in (Dialect.POSTGRES, Dialect.TSQL):
        raise DialectError(
            "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
            f"{target_dialect.value} has no exact inline table-valued function route",
        )
    if (function.security_definer or function.search_path) and not allow_routine_shim:
        raise DialectError(
            "CERTIFIED_ROUTINE_SECURITY_CONTEXT_UNSUPPORTED",
            "SECURITY DEFINER and SET search_path bind execution identity and name resolution; "
            "no target security mapping was authorized for this route",
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
        quote_identifier(item.name, target_dialect) + " " + _routine_type(item.type_ref, target_dialect)
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
    replace = " OR REPLACE" if function.or_replace and target_dialect is Dialect.POSTGRES else ""
    sec_clause = " SECURITY DEFINER" if function.security_definer else ""
    return (
        f"CREATE{replace} FUNCTION {qualified}({params}) RETURNS TABLE ({columns}) LANGUAGE SQL{sec_clause} "  # noqa: S608
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
            right = _render_trigger_identifier(expression.right_column, expression.right_column_qualifier, dialect)
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
    return joiner.join(f"({_render_trigger_expression(operand, dialect)})" for operand in expression.operands)


def emit_trigger(trigger: Trigger, target_dialect: Dialect, allow_trigger_shim: bool = False) -> str:
    if target_dialect is not Dialect.POSTGRES and not allow_trigger_shim:
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

    if target_dialect is Dialect.POSTGRES:
        return (
            f"CREATE TRIGGER {quote_identifier(trigger.name, target_dialect)} {trigger.timing.value} {events} ON "
            f"{_object_name(trigger.table_schema, trigger.table, target_dialect)}{row}{when} "
            f"EXECUTE FUNCTION {_object_name(trigger.routine_schema, trigger.routine_name, target_dialect)}()"
        )
    if target_dialect is Dialect.ORACLE:
        return (
            f"CREATE OR REPLACE TRIGGER {quote_identifier(trigger.name, target_dialect)} "
            f"{trigger.timing.value} {events} ON "
            f"{_object_name(trigger.table_schema, trigger.table, target_dialect)}{row}{when} "
            f"BEGIN {_object_name(trigger.routine_schema, trigger.routine_name, target_dialect)}(); END;"
        )
    if target_dialect is Dialect.MYSQL:
        return (
            f"CREATE TRIGGER {quote_identifier(trigger.name, target_dialect)} {trigger.timing.value} {events} ON "
            f"{_object_name(trigger.table_schema, trigger.table, target_dialect)}{row}{when} "
            f"BEGIN CALL {_object_name(trigger.routine_schema, trigger.routine_name, target_dialect)}(); END"
        )
    if target_dialect is Dialect.TSQL:
        return (
            f"CREATE TRIGGER {quote_identifier(trigger.name, target_dialect)} ON "
            f"{_object_name(trigger.table_schema, trigger.table, target_dialect)} {trigger.timing.value} {events} "
            f"AS BEGIN EXEC {_object_name(trigger.routine_schema, trigger.routine_name, target_dialect)}; END"
        )
    raise DialectError(
        "CERTIFIED_ROUTINE_TRIGGER_TARGET_ROUTE_REQUIRED", f"unsupported target dialect {target_dialect}"
    )
