"""Typed, fail-closed SQL routine translation.

certified-routine-v1 intentionally covers a much smaller surface than a
vendor's procedural language. The admitted body is one SQL SELECT with one
expression. The expression is lowered from the real sqlglot AST into a closed
IR and then emitted by four hand-written target renderers. No body is
translated by replacing keywords in source text.

The parser also records routine metadata which is not portable by default:
schema qualification, replacement semantics, volatility, strict-null
handling, definer security and search path. The emitter refuses those facts
unless a future versioned target profile proves an exact mapping. This is
important for the existing migration corpus, where most routines are
security-sensitive PL/pgSQL and trigger code: they remain explicit blockers,
not false automatic conversions.
"""

from __future__ import annotations

from collections.abc import Mapping

import sqlglot
from sqlglot import exp

from .dialects import render_type
from .models import (
    CanonicalType,
    CanonicalTypeRef,
    Dialect,
    DialectError,
    Routine,
    RoutineBinaryExpression,
    RoutineBinaryOperator,
    RoutineCharCode,
    RoutineFunction,
    RoutineFunctionCall,
    RoutineKind,
    RoutineLanguage,
    RoutineLiteral,
    RoutineParameter,
    RoutineParameterReference,
    RoutineSelectBody,
    RoutineStability,
    RoutineValueExpression,
)
from .parser import _IDENTIFIER_RE, _parse_type, _plain_identifier, _require_single_statement

_BINARY_OPERATORS: dict[type[exp.Expression], RoutineBinaryOperator] = {
    exp.DPipe: RoutineBinaryOperator.CONCAT,
    exp.Add: RoutineBinaryOperator.ADD,
    exp.Sub: RoutineBinaryOperator.SUBTRACT,
    exp.Mul: RoutineBinaryOperator.MULTIPLY,
    exp.Div: RoutineBinaryOperator.DIVIDE,
    exp.Mod: RoutineBinaryOperator.MODULO,
}


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise DialectError(code, message)


def _routine_name(
    node: exp.Expression,
    namespace_map: Mapping[str, str] | None = None,
) -> tuple[str | None, str]:
    _require(isinstance(node, exp.Table), "CERTIFIED_ROUTINE_MISSING_IDENTIFIER", "routine name is missing")
    assert isinstance(node, exp.Table)
    schema_node = node.args.get("db")
    schema = _plain_identifier(schema_node, "routine schema") if schema_node is not None else None
    if schema is not None:
        target_schema = None if namespace_map is None else namespace_map.get(schema)
        _require(
            target_schema is not None,
            "CERTIFIED_ROUTINE_NAMESPACE_MAPPING_REQUIRED",
            f"routine schema {schema!r} needs an explicit namespace_map",
        )
        assert target_schema is not None
        _require(
            bool(_IDENTIFIER_RE.match(target_schema)),
            "CERTIFIED_ROUTINE_UNSUPPORTED_IDENTIFIER",
            f"mapped routine schema {target_schema!r} is not a plain identifier",
        )
        schema = target_schema
    name = _plain_identifier(node.this, "routine name")
    return schema, name


def _property_language(prop: exp.Expression) -> RoutineLanguage:
    value = str(prop.args.get("this", "")).upper()
    if value == "SQL":
        return RoutineLanguage.SQL
    if value == "PLPGSQL":
        return RoutineLanguage.PLPGSQL
    return RoutineLanguage.OTHER


def _property_stability(prop: exp.Expression) -> RoutineStability:
    value = str(prop.args.get("this", "")).strip("'").upper()
    try:
        return RoutineStability(value)
    except ValueError as exc:
        raise DialectError(
            "CERTIFIED_ROUTINE_UNSUPPORTED_STABILITY",
            f"routine stability {value!r} is not a recognized SQL stability declaration",
        ) from exc


def _parse_literal(node: exp.Literal | exp.Boolean) -> RoutineLiteral:
    if isinstance(node, exp.Boolean):
        return RoutineLiteral(str(node.this).lower(), is_boolean=True)
    if node.is_string:
        return RoutineLiteral(str(node.this), is_string=True)
    return RoutineLiteral(str(node.this))


def _parse_value(
    node: exp.Expression,
    parameters: dict[str, RoutineParameter],
    source_dialect: Dialect,
) -> RoutineValueExpression:
    if isinstance(node, exp.Paren):
        _require(
            node.this is not None,
            "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
            "empty parenthesised routine expression",
        )
        return _parse_value(node.this, parameters, source_dialect)
    if isinstance(node, exp.Literal):
        return _parse_literal(node)
    if isinstance(node, exp.Boolean):
        return _parse_literal(node)
    if isinstance(node, exp.Column):
        _require(
            node.args.get("table") is None,
            "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
            "qualified column references are not portable in this profile",
        )
        name = _plain_identifier(node.this, "routine parameter reference")
        parameter = parameters.get(name.casefold())
        _require(
            parameter is not None,
            "CERTIFIED_ROUTINE_UNKNOWN_PARAMETER",
            f"routine body references undeclared name {name!r}",
        )
        assert parameter is not None
        return RoutineParameterReference(parameter.name)
    if isinstance(node, exp.Parameter):
        variable = node.this
        _require(
            isinstance(variable, exp.Var),
            "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
            "T-SQL parameter reference is not a plain variable",
        )
        assert isinstance(variable, exp.Var)
        name = str(variable.this)
        _require(
            bool(_IDENTIFIER_RE.match(name)),
            "CERTIFIED_ROUTINE_UNSUPPORTED_IDENTIFIER",
            f"routine parameter reference {name!r} is not a plain identifier",
        )
        parameter = parameters.get(name.casefold())
        _require(
            parameter is not None,
            "CERTIFIED_ROUTINE_UNKNOWN_PARAMETER",
            f"routine body references undeclared name {name!r}",
        )
        assert parameter is not None
        return RoutineParameterReference(parameter.name)
    if isinstance(node, exp.Chr):
        args = list(node.expressions or [])
        _require(
            len(args) == 1 and isinstance(args[0], exp.Literal) and not args[0].is_string,
            "CERTIFIED_ROUTINE_UNSUPPORTED_FUNCTION",
            "CHR/CHAR requires one integer literal code point",
        )
        assert isinstance(args[0], exp.Literal)
        try:
            value = int(args[0].this)
        except ValueError as exc:
            raise DialectError(
                "CERTIFIED_ROUTINE_UNSUPPORTED_FUNCTION",
                "CHR code point is not an integer",
            ) from exc
        _require(
            0 <= value <= 0x10FFFF,
            "CERTIFIED_ROUTINE_UNSUPPORTED_FUNCTION",
            "CHR code point is outside Unicode range",
        )
        return RoutineCharCode(value)
    for node_type, operator in _BINARY_OPERATORS.items():
        if isinstance(node, node_type):
            left = node.this
            right = node.expression
            _require(
                left is not None and right is not None,
                "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
                "binary routine expression is incomplete",
            )
            return RoutineBinaryExpression(
                operator,
                _parse_value(left, parameters, source_dialect),
                _parse_value(right, parameters, source_dialect),
            )
    if isinstance(node, exp.Concat):
        values = tuple(_parse_value(item, parameters, source_dialect) for item in node.expressions)
        _require(
            len(values) >= 2,
            "CERTIFIED_ROUTINE_UNSUPPORTED_FUNCTION",
            "CONCAT requires at least two arguments",
        )
        result: RoutineValueExpression = values[0]
        for item in values[1:]:
            result = RoutineFunctionCall(RoutineFunction.CONCAT, (result, item))
        return result
    if isinstance(node, exp.Coalesce):
        _require(
            node.this is not None,
            "CERTIFIED_ROUTINE_UNSUPPORTED_FUNCTION",
            "COALESCE requires a first argument",
        )
        values = (
            _parse_value(node.this, parameters, source_dialect),
            *(_parse_value(item, parameters, source_dialect) for item in node.expressions),
        )
        _require(
            len(values) >= 2,
            "CERTIFIED_ROUTINE_UNSUPPORTED_FUNCTION",
            "COALESCE requires at least two arguments",
        )
        return RoutineFunctionCall(RoutineFunction.COALESCE, values)
    if isinstance(node, exp.Lower):
        return RoutineFunctionCall(
            RoutineFunction.LOWER,
            (_parse_value(node.this, parameters, source_dialect),),
        )
    if isinstance(node, exp.Upper):
        return RoutineFunctionCall(
            RoutineFunction.UPPER,
            (_parse_value(node.this, parameters, source_dialect),),
        )
    if isinstance(node, exp.Trim):
        _require(
            node.expression is None,
            "CERTIFIED_ROUTINE_UNSUPPORTED_FUNCTION",
            "TRIM character specification is not portable",
        )
        return RoutineFunctionCall(
            RoutineFunction.TRIM,
            (_parse_value(node.this, parameters, source_dialect),),
        )
    if isinstance(node, exp.Abs):
        return RoutineFunctionCall(
            RoutineFunction.ABS,
            (_parse_value(node.this, parameters, source_dialect),),
        )
    raise DialectError(
        "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
        f"routine SELECT expression node {type(node).__name__} is outside the typed portable expression core",
    )


def _parse_body(
    body: exp.Expression | None,
    parameters: dict[str, RoutineParameter],
    source_dialect: Dialect,
) -> RoutineSelectBody:
    if isinstance(body, exp.Return):
        expression = body.this
        if isinstance(expression, exp.Alias):
            alias = expression.args.get("alias")
            # sqlglot consumes the T-SQL block terminator as an alias when
            # the source omits a semicolon after RETURN. Accept only that
            # exact parser shape; an actual SQL alias is not a routine return
            # expression.
            _require(
                isinstance(alias, exp.Identifier) and str(alias.this).upper() == "END",
                "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
                "direct RETURN body contains an unsupported alias",
            )
            expression = expression.this
        _require(
            isinstance(expression, exp.Expression),
            "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
            "direct RETURN body has no expression",
        )
        return RoutineSelectBody(_parse_value(expression, parameters, source_dialect))
    _require(
        isinstance(body, exp.Heredoc),
        "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
        "routine body must be a dollar-quoted SQL body",
    )
    assert isinstance(body, exp.Heredoc)
    raw_body = str(body.this).strip()
    try:
        statements = [
            statement for statement in sqlglot.parse(raw_body, read=source_dialect.value) if statement is not None
        ]
    except sqlglot.errors.SqlglotError as exc:
        raise DialectError(
            "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
            f"routine SQL body could not be parsed: {exc}",
        ) from exc
    _require(
        len(statements) == 1 and isinstance(statements[0], exp.Select),
        "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
        "routine body must contain exactly one SELECT statement",
    )
    statement = statements[0]
    assert isinstance(statement, exp.Select)
    _require(
        len(statement.expressions) == 1
        and statement.args.get("from_") is None
        and statement.args.get("where") is None
        and statement.args.get("group") is None
        and statement.args.get("having") is None
        and statement.args.get("qualify") is None
        and statement.args.get("order") is None
        and statement.args.get("limit") is None
        and statement.args.get("distinct") is None
        and statement.args.get("with") is None,
        "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
        "routine body must be one table-free, non-distinct SELECT expression without query clauses",
    )
    return RoutineSelectBody(_parse_value(statement.expressions[0], parameters, source_dialect))


def _type_kind(type_ref: CanonicalTypeRef) -> str:
    if type_ref.canonical_type in (CanonicalType.CHAR, CanonicalType.VARCHAR, CanonicalType.TEXT):
        return "TEXT"
    if type_ref.canonical_type is CanonicalType.BOOLEAN:
        return "BOOLEAN"
    if type_ref.canonical_type in (
        CanonicalType.INT16,
        CanonicalType.INT32,
        CanonicalType.INT64,
    ):
        return "INTEGER"
    if type_ref.canonical_type is CanonicalType.DECIMAL:
        return "DECIMAL"
    if type_ref.canonical_type is CanonicalType.FLOAT64:
        return "FLOAT"
    return "UNSUPPORTED"


def _value_kind(
    value: RoutineValueExpression,
    parameters: dict[str, RoutineParameter],
) -> str:
    if isinstance(value, RoutineLiteral):
        if value.is_string:
            return "TEXT"
        if value.is_boolean:
            return "BOOLEAN"
        return "DECIMAL" if any(token in value.value for token in (".", "e", "E")) else "INTEGER"
    if isinstance(value, RoutineParameterReference):
        return _type_kind(parameters[value.name.casefold()].type_ref)
    if isinstance(value, RoutineCharCode):
        return "TEXT"
    if isinstance(value, RoutineBinaryExpression):
        left_kind = _value_kind(value.left, parameters)
        right_kind = _value_kind(value.right, parameters)
        if value.operator is RoutineBinaryOperator.CONCAT:
            _require(
                left_kind == "TEXT" and right_kind == "TEXT",
                "CERTIFIED_ROUTINE_UNSUPPORTED_OPERATOR",
                "concatenation requires text operands; implicit numeric casts are not portable",
            )
            return "TEXT"
        _require(
            left_kind in {"INTEGER", "DECIMAL", "FLOAT"} and right_kind in {"INTEGER", "DECIMAL", "FLOAT"},
            "CERTIFIED_ROUTINE_UNSUPPORTED_OPERATOR",
            f"{value.operator.value} requires numeric operands with explicit source types",
        )
        if value.operator is RoutineBinaryOperator.DIVIDE:
            _require(
                left_kind != "INTEGER" or right_kind != "INTEGER",
                "CERTIFIED_ROUTINE_UNSUPPORTED_OPERATOR",
                "integer division has different result semantics across the four targets; "
                "use an explicit DECIMAL/FLOAT parameter or cast in a target-specific route",
            )
        if "FLOAT" in (left_kind, right_kind):
            return "FLOAT"
        if "DECIMAL" in (left_kind, right_kind) or value.operator is RoutineBinaryOperator.DIVIDE:
            return "DECIMAL"
        return "INTEGER"
    if isinstance(value, RoutineFunctionCall):
        kinds = [_value_kind(item, parameters) for item in value.arguments]
        if value.name is RoutineFunction.CONCAT:
            _require(
                all(kind == "TEXT" for kind in kinds),
                "CERTIFIED_ROUTINE_UNSUPPORTED_OPERATOR",
                "CONCAT requires text operands; implicit numeric casts are not portable",
            )
            return "TEXT"
        if value.name is RoutineFunction.COALESCE:
            _require(
                len(set(kinds)) == 1,
                "CERTIFIED_ROUTINE_UNSUPPORTED_FUNCTION",
                "COALESCE operands must have one explicit common canonical type",
            )
            return kinds[0]
        if value.name in (
            RoutineFunction.LOWER,
            RoutineFunction.UPPER,
            RoutineFunction.TRIM,
        ):
            _require(
                kinds == ["TEXT"],
                "CERTIFIED_ROUTINE_UNSUPPORTED_FUNCTION",
                f"{value.name.value} requires one text operand",
            )
            return "TEXT"
        _require(
            len(kinds) == 1 and kinds[0] in {"INTEGER", "DECIMAL", "FLOAT"},
            "CERTIFIED_ROUTINE_UNSUPPORTED_FUNCTION",
            f"{value.name.value} requires one numeric operand",
        )
        return kinds[0]
    raise TypeError(f"unhandled routine IR node: {type(value).__name__}")  # pragma: no cover


def _validate_return_type(
    body: RoutineSelectBody,
    return_type: CanonicalTypeRef,
    parameters: dict[str, RoutineParameter],
) -> None:
    body_kind = _value_kind(body.expression, parameters)
    return_kind = _type_kind(return_type)
    _require(
        body_kind == return_kind,
        "CERTIFIED_ROUTINE_RETURN_TYPE_MISMATCH",
        f"routine body has canonical kind {body_kind}, but RETURNS declares {return_kind}",
    )


def parse_create_routine(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> Routine:
    """Parse one function/procedure and fail closed outside routine-v1."""
    statement = sql if isinstance(sql, exp.Expression) else _require_single_statement(sql, source_dialect)
    _require(
        isinstance(statement, exp.Create),
        "CERTIFIED_ROUTINE_UNSUPPORTED_STATEMENT",
        "routine profile accepts one CREATE FUNCTION or CREATE PROCEDURE",
    )
    assert isinstance(statement, exp.Create)
    kind_value = str(statement.args.get("kind", "")).upper()
    _require(
        kind_value in {RoutineKind.FUNCTION.value, RoutineKind.PROCEDURE.value},
        "CERTIFIED_ROUTINE_UNSUPPORTED_STATEMENT",
        "routine profile accepts CREATE FUNCTION or CREATE PROCEDURE",
    )
    kind = RoutineKind(kind_value)
    if kind is RoutineKind.PROCEDURE:
        raise DialectError(
            "CERTIFIED_ROUTINE_PROCEDURE_UNSUPPORTED",
            "procedures carry target-specific transaction, OUT-parameter and side-effect semantics; "
            "use an exact versioned procedure route rather than converting one as a scalar function",
        )
    _require(
        isinstance(statement.this, exp.UserDefinedFunction),
        "CERTIFIED_ROUTINE_UNSUPPORTED_STATEMENT",
        "CREATE routine payload is not a function signature",
    )
    udf = statement.this
    assert isinstance(udf, exp.UserDefinedFunction)
    _require(
        isinstance(udf.this, exp.Table),
        "CERTIFIED_ROUTINE_MISSING_IDENTIFIER",
        "routine name is missing",
    )
    schema, name = _routine_name(udf.this, namespace_map)
    parameters: list[RoutineParameter] = []
    for item in udf.expressions:
        _require(
            isinstance(item, exp.ColumnDef),
            "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
            "routine parameters must be typed plain parameters",
        )
        assert isinstance(item, exp.ColumnDef)
        _require(
            not item.args.get("constraints"),
            "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
            "parameter defaults, modes and constraints are not portable",
        )
        parameter_node = item.this
        if isinstance(parameter_node, exp.Parameter):
            variable = parameter_node.this
            _require(
                isinstance(variable, exp.Var),
                "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
                "T-SQL routine parameter is not a plain variable",
            )
            assert isinstance(variable, exp.Var)
            parameter_name = str(variable.this)
            _require(
                bool(_IDENTIFIER_RE.match(parameter_name)),
                "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
                f"routine parameter {parameter_name!r} is not a plain identifier",
            )
        else:
            parameter_name = _plain_identifier(parameter_node, "routine parameter")
        parameter_type = item.args.get("kind")
        _require(
            isinstance(parameter_type, exp.DataType),
            "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
            f"routine parameter {parameter_name!r} has no supported type",
        )
        assert isinstance(parameter_type, exp.DataType)
        parameters.append(RoutineParameter(parameter_name, _parse_type(parameter_type, source_dialect)))
    parameter_map = {item.name.casefold(): item for item in parameters}

    return_type: CanonicalTypeRef | None = None
    language = RoutineLanguage.SQL if source_dialect in (Dialect.MYSQL, Dialect.TSQL) else RoutineLanguage.OTHER
    stability: RoutineStability | None = None
    strict = False
    security_definer = False
    search_path: tuple[str, ...] = ()
    properties = statement.args.get("properties")
    if isinstance(properties, exp.Properties):
        for prop in properties.expressions:
            if isinstance(prop, exp.ReturnsProperty):
                _require(
                    not prop.args.get("is_table"),
                    "CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED",
                    "RETURNS TABLE needs a row-shape IR and is not a scalar routine",
                )
                return_node = prop.args.get("this")
                _require(
                    isinstance(return_node, exp.DataType),
                    "CERTIFIED_ROUTINE_UNSUPPORTED_RETURN",
                    "function return type is not a scalar data type",
                )
                assert isinstance(return_node, exp.DataType)
                return_type = _parse_type(return_node, source_dialect)
            elif isinstance(prop, exp.LanguageProperty):
                language = _property_language(prop)
            elif isinstance(prop, exp.StabilityProperty):
                stability = _property_stability(prop)
            elif isinstance(prop, exp.StrictProperty):
                strict = True
            elif isinstance(prop, exp.SqlSecurityProperty):
                security_definer = str(prop.args.get("this", "")).upper() == "DEFINER"
            elif isinstance(prop, exp.SetConfigProperty):
                # sqlglot keeps the full SET payload as a command. Retain an
                # opaque marker rather than interpreting search_path text as
                # executable SQL.
                search_path = ("<source-defined>",)
            else:
                raise DialectError(
                    "CERTIFIED_ROUTINE_UNSUPPORTED_PROPERTY",
                    f"routine property {type(prop).__name__} is outside certified-routine-v1",
                )
    _require(
        return_type is not None,
        "CERTIFIED_ROUTINE_MISSING_RETURN_TYPE",
        f"function {name!r} has no scalar RETURNS type",
    )
    _require(
        language is RoutineLanguage.SQL,
        "CERTIFIED_ROUTINE_UNSUPPORTED_LANGUAGE",
        f"routine language {language.value} is not a table-free SQL expression language",
    )
    # These facts are retained by the canonical Routine model, but there is
    # intentionally no default cross-dialect mapping for them. Rejecting here
    # keeps the scanner's automatic-candidate number honest: a source routine
    # with unportable metadata is a blocker, not a source-only candidate that
    # the emitter would later have to refuse.
    if strict:
        raise DialectError(
            "CERTIFIED_ROUTINE_STRICT_UNSUPPORTED_BY_TARGET",
            "PostgreSQL STRICT null short-circuiting is routine metadata; this profile does not "
            "synthesize a CASE wrapper with unverified type/null semantics",
        )
    if security_definer or search_path:
        raise DialectError(
            "CERTIFIED_ROUTINE_SECURITY_CONTEXT_UNSUPPORTED",
            "SECURITY DEFINER and SET search_path bind execution identity and name resolution; "
            "no target security mapping was authorized for this route",
        )
    if stability is not None:
        raise DialectError(
            "CERTIFIED_ROUTINE_STABILITY_UNSUPPORTED_BY_TARGET",
            f"{stability.value} is not one exact cross-dialect routine contract; "
            "do not silently map it to a weaker or different deterministic declaration",
        )
    body = _parse_body(statement.args.get("expression"), parameter_map, source_dialect)
    assert return_type is not None
    _validate_return_type(body, return_type, parameter_map)
    return Routine(
        kind=kind,
        name=name,
        parameters=tuple(parameters),
        return_type=return_type,
        body=body,
        schema=schema,
        language=language,
        stability=stability,
        strict=strict,
        security_definer=security_definer,
        search_path=search_path,
        or_replace=bool(statement.args.get("replace")),
    )


def parse_create_trigger(sql: str | exp.Expression, source_dialect: Dialect) -> None:
    """Give triggers their own explicit boundary instead of generic failure."""
    statement = sql if isinstance(sql, exp.Expression) else _require_single_statement(sql, source_dialect)
    if isinstance(statement, exp.Create) and str(statement.args.get("kind", "")).upper() == "TRIGGER":
        raise DialectError(
            "CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED",
            "triggers bind timing, row/statement scope, transition values and a target routine; "
            "they require a target-specific trigger route and cannot be lowered to a scalar function",
        )
    raise DialectError(
        "CERTIFIED_ROUTINE_UNSUPPORTED_STATEMENT",
        "routine profile accepts a CREATE TRIGGER statement here",
    )


def _render_routine_value(
    value: RoutineValueExpression,
    dialect: Dialect,
    *,
    tsql_parameters: bool = False,
) -> str:
    if isinstance(value, RoutineLiteral):
        if value.is_boolean:
            if dialect in (Dialect.ORACLE, Dialect.TSQL):
                return "1" if value.value == "true" else "0"
            return "TRUE" if value.value == "true" else "FALSE"
        if value.is_string:
            return "'" + value.value.replace("'", "''") + "'"
        return value.value
    if isinstance(value, RoutineParameterReference):
        return ("@" if tsql_parameters else "") + value.name
    if isinstance(value, RoutineCharCode):
        return ("CHAR" if dialect in (Dialect.MYSQL, Dialect.TSQL) else "CHR") + f"({value.value})"
    if isinstance(value, RoutineBinaryExpression):
        left = _render_routine_value(value.left, dialect, tsql_parameters=tsql_parameters)
        right = _render_routine_value(value.right, dialect, tsql_parameters=tsql_parameters)
        if value.operator is RoutineBinaryOperator.CONCAT:
            if dialect is Dialect.MYSQL:
                return f"CONCAT({left}, {right})"
            if dialect is Dialect.TSQL:
                return f"{left} + {right}"
        if value.operator is RoutineBinaryOperator.MODULO and dialect is Dialect.ORACLE:
            return f"MOD({left}, {right})"
        return f"({left} {value.operator.value} {right})"
    if isinstance(value, RoutineFunctionCall):
        args = ", ".join(
            _render_routine_value(item, dialect, tsql_parameters=tsql_parameters) for item in value.arguments
        )
        if value.name is RoutineFunction.CONCAT and dialect is not Dialect.MYSQL:
            return f"CONCAT({args})"
        return f"{value.name.value}({args})"
    raise TypeError(f"unhandled routine IR node: {type(value).__name__}")  # pragma: no cover


def _require_emittable(routine: Routine, target_dialect: Dialect) -> None:
    if routine.or_replace:
        if target_dialect not in (Dialect.POSTGRES, Dialect.ORACLE):
            raise DialectError(
                "CERTIFIED_ROUTINE_REPLACE_UNSUPPORTED_BY_TARGET",
                f"{target_dialect.value} has no exact CREATE OR REPLACE FUNCTION spelling",
            )
    if routine.strict:
        raise DialectError(
            "CERTIFIED_ROUTINE_STRICT_UNSUPPORTED_BY_TARGET",
            "PostgreSQL STRICT null short-circuiting is routine metadata; this profile does not "
            "synthesize a CASE wrapper with unverified type/null semantics",
        )
    if routine.security_definer or routine.search_path:
        raise DialectError(
            "CERTIFIED_ROUTINE_SECURITY_CONTEXT_UNSUPPORTED",
            "SECURITY DEFINER and SET search_path bind execution identity and name resolution; "
            "no target security mapping was authorized for this route",
        )
    if routine.stability is not None:
        raise DialectError(
            "CERTIFIED_ROUTINE_STABILITY_UNSUPPORTED_BY_TARGET",
            f"{routine.stability.value} is not one exact cross-dialect routine contract; "
            "do not silently map it to a weaker or different deterministic declaration",
        )
    if routine.kind is not RoutineKind.FUNCTION or routine.body is None or routine.return_type is None:
        raise DialectError(
            "CERTIFIED_ROUTINE_UNSUPPORTED_KIND",
            "only scalar SQL functions have an emitter in routine-v1",
        )
    if target_dialect not in (Dialect.POSTGRES, Dialect.MYSQL, Dialect.ORACLE, Dialect.TSQL):  # pragma: no cover
        raise DialectError(
            "CERTIFIED_ROUTINE_UNSUPPORTED_TARGET",
            f"no routine emitter for {target_dialect.value}",
        )


def emit_create_function(routine: Routine, target_dialect: Dialect) -> str:
    """Emit one scalar SQL function in native target syntax."""
    _require_emittable(routine, target_dialect)
    assert routine.return_type is not None and routine.body is not None

    def routine_type(type_ref: CanonicalTypeRef) -> str:
        # Oracle's CHAR length qualifier is a SQL column-definition concern.
        # PL/SQL formal parameters and function return declarations use the
        # PL/SQL spelling without the SQL CHAR/BYTE qualifier.
        if target_dialect is Dialect.ORACLE and type_ref.canonical_type is CanonicalType.CHAR:
            return f"CHAR({type_ref.length or 1})"
        if target_dialect is Dialect.ORACLE and type_ref.canonical_type is CanonicalType.VARCHAR:
            assert type_ref.length is not None
            return f"VARCHAR2({type_ref.length})"
        return render_type(type_ref, target_dialect)

    params = ", ".join(
        ("@" if target_dialect is Dialect.TSQL else "") + item.name + " " + routine_type(item.type_ref)
        for item in routine.parameters
    )
    return_type = routine_type(routine.return_type)
    value = _render_routine_value(
        routine.body.expression,
        target_dialect,
        tsql_parameters=target_dialect is Dialect.TSQL,
    )
    qualified_name = f"{routine.schema}.{routine.name}" if routine.schema else routine.name
    replace = " OR REPLACE" if routine.or_replace and target_dialect in (Dialect.POSTGRES, Dialect.ORACLE) else ""
    if target_dialect is Dialect.POSTGRES:
        return (
            f"CREATE{replace} FUNCTION {qualified_name}({params}) RETURNS {return_type} "
            f"LANGUAGE SQL AS $$ SELECT {value} $$"
        )
    if target_dialect is Dialect.MYSQL:
        return f"CREATE FUNCTION {qualified_name}({params}) RETURNS {return_type} RETURN {value}"
    if target_dialect is Dialect.ORACLE:
        return f"CREATE{replace} FUNCTION {qualified_name}({params}) RETURN {return_type} IS BEGIN RETURN {value}; END;"
    return f"CREATE FUNCTION {qualified_name}({params}) RETURNS {return_type} AS BEGIN RETURN {value} END"
