"""Typed, fail-closed SQL routine translation.

certified-routine-v1 intentionally covers a much smaller surface than a
vendor's procedural language. The admitted body is one SQL SELECT with one
expression. The expression is lowered from the real sqlglot AST into a closed
IR and then emitted by four hand-written target renderers. No body is
translated by replacing keywords in source text.

    The parser also records routine metadata which is not portable by default:
    schema qualification, replacement semantics, volatility, strict-null
    handling, definer security and search path. Source-side admission requires
    those facts to be represented in the typed IR; the emitter refuses them
    unless a future versioned target profile proves an exact mapping. This is
    important for the existing migration corpus, where most routines are
    security-sensitive PL/pgSQL and trigger code: target routes remain explicit
    blockers, not false automatic conversions.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

import sqlglot
from sqlglot import exp

from .dialects import render_type
from .identifiers import qualified_name, quote_identifier
from .models import (
    CanonicalType,
    CanonicalTypeRef,
    ColumnDefault,
    DefaultKind,
    Dialect,
    DialectError,
    Routine,
    RoutineAssignment,
    RoutineBinaryExpression,
    RoutineBinaryOperator,
    RoutineBlockBody,
    RoutineCharCode,
    RoutineFunction,
    RoutineFunctionCall,
    RoutineIdentity,
    RoutineKind,
    RoutineLanguage,
    RoutineLiteral,
    RoutineParameter,
    RoutineParameterReference,
    RoutineSelectBody,
    RoutineStability,
    RoutineValueExpression,
    RoutineVariable,
    RoutineVariableReference,
)
from .parser import _IDENTIFIER_RE, _parse_default, _parse_type, _plain_identifier, _require_single_statement
from .statement_splitter import split_statements

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


def _routine_signature_statement(
    statement: str | exp.Expression,
    source_dialect: Dialect,
) -> exp.Expression:
    """Recover only a routine signature from an opaque procedural statement.

    sqlglot intentionally leaves some valid PL/pgSQL bodies as ``Command``
    nodes.  Identity-sensitive metadata still needs the typed declaration
    preceding that body, but must not treat the body as executable or infer a
    portable routine route from it.  Truncate at the balanced parameter list
    and parse that prefix as a minimal CREATE statement.  This helper is
    therefore evidence-only: callers use the resulting parameter types for
    identity matching, never for body emission.
    """
    if not isinstance(statement, exp.Command):
        return (
            statement
            if isinstance(statement, exp.Expression)
            else _require_single_statement(statement, source_dialect)
        )
    expression = statement.args.get("expression")
    _require(
        isinstance(expression, str),
        "CERTIFIED_ROUTINE_IDENTITY_UNSUPPORTED",
        "opaque routine statement has no recoverable declaration",
    )
    assert isinstance(expression, str)
    source = "CREATE" + expression
    routine_match = re.search(r"\b(?:FUNCTION|PROCEDURE)\b", source, re.IGNORECASE)
    _require(
        routine_match is not None,
        "CERTIFIED_ROUTINE_IDENTITY_UNSUPPORTED",
        "opaque statement is not a routine declaration",
    )
    assert routine_match is not None
    open_paren = source.find("(", routine_match.end())
    _require(
        open_paren >= 0,
        "CERTIFIED_ROUTINE_IDENTITY_UNSUPPORTED",
        "routine declaration has no parameter list",
    )
    depth = 0
    quote: str | None = None
    index = open_paren
    while index < len(source):
        current = source[index]
        if quote is not None:
            if current == quote:
                if index + 1 < len(source) and source[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if current in {"'", '"', "`"}:
            quote = current
        elif current == "(":
            depth += 1
        elif current == ")":
            depth -= 1
            if depth == 0:
                return _require_single_statement(source[: index + 1], source_dialect)
        index += 1
    raise DialectError(
        "CERTIFIED_ROUTINE_IDENTITY_UNSUPPORTED",
        "routine declaration parameter list is not balanced",
    )


def _parse_routine_identity_type(data_type: exp.DataType, source_dialect: Dialect) -> CanonicalTypeRef:
    """Parse a routine argument type without confusing it with column policy.

    PostgreSQL permits an unparameterised NUMERIC as a routine *type identity*;
    it is still rejected for portable columns/returns because those require a
    fixed precision contract.  Keeping ``DECIMAL`` without precision only in
    the identity IR lets a comment/privilege target be proven unique without
    weakening the data-type route.
    """
    try:
        return _parse_type(data_type, source_dialect)
    except DialectError as exc:
        if (
            exc.code == "CERTIFIED_DDL_UNBOUNDED_DECIMAL"
            and data_type.this is exp.DataType.Type.DECIMAL
        ):
            return CanonicalTypeRef(canonical_type=CanonicalType.DECIMAL)
        raise


def _routine_name(
    node: exp.Expression,
    namespace_map: Mapping[str, str] | None = None,
) -> tuple[str | None, str]:
    _require(isinstance(node, exp.Table), "CERTIFIED_ROUTINE_MISSING_IDENTIFIER", "routine name is missing")
    assert isinstance(node, exp.Table)
    schema_node = node.args.get("db")
    schema: str | None = _plain_identifier(schema_node, "routine schema") if schema_node is not None else None
    source_schema = schema
    if schema is None and namespace_map is not None and "" in namespace_map:
        # The empty mapping entry is the explicit source default namespace.
        # Tables and views already apply it through _mapped_table_name; routine
        # identities must use the same typed rule or catalog-gated comments
        # and privileges will miss otherwise identical unqualified routines.
        source_schema = ""
    if source_schema is not None:
        target_schema = None if namespace_map is None else namespace_map.get(source_schema)
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


def parse_routine_identity(
    sql: str | exp.Expression,
    source_dialect: Dialect,
    namespace_map: Mapping[str, str] | None = None,
) -> RoutineIdentity:
    """Parse only the typed identity of a routine for catalog evidence.

    The body, security context and return contract are intentionally not
    interpreted here.  This helper is used when a routine itself is outside
    the portable execution route but a later GRANT/REVOKE or metadata
    statement needs proof that its target identity is unique.  Unsupported
    parameter types fail closed instead of becoming an untyped signature.
    """

    statement = _routine_signature_statement(sql, source_dialect)
    _require(
        isinstance(statement, exp.Create),
        "CERTIFIED_ROUTINE_IDENTITY_UNSUPPORTED",
        "routine identity requires one CREATE FUNCTION or CREATE PROCEDURE statement",
    )
    assert isinstance(statement, exp.Create)
    kind_name = str(statement.args.get("kind", "")).upper()
    _require(
        kind_name in {RoutineKind.FUNCTION.value, RoutineKind.PROCEDURE.value},
        "CERTIFIED_ROUTINE_IDENTITY_UNSUPPORTED",
        "routine identity requires CREATE FUNCTION or CREATE PROCEDURE",
    )
    _require(
        isinstance(statement.this, exp.UserDefinedFunction),
        "CERTIFIED_ROUTINE_IDENTITY_UNSUPPORTED",
        "routine identity signature is malformed",
    )
    assert isinstance(statement.this, exp.UserDefinedFunction)
    schema, name = _routine_name(statement.this.this, namespace_map)
    parameter_types: list[CanonicalTypeRef] = []
    for item in statement.this.expressions:
        _require(
            isinstance(item, exp.ColumnDef) and isinstance(item.kind, exp.DataType),
            "CERTIFIED_ROUTINE_IDENTITY_UNSUPPORTED",
            "routine identity parameters must carry typed declarations",
        )
        assert isinstance(item, exp.ColumnDef)
        assert isinstance(item.kind, exp.DataType)
        parameter_types.append(_parse_routine_identity_type(item.kind, source_dialect))
    return RoutineIdentity(
        kind=RoutineKind(kind_name),
        name=name,
        parameter_types=tuple(parameter_types),
        schema=schema,
    )


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
    parameters: Mapping[str, RoutineParameter | RoutineVariable],
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
        return (
            RoutineVariableReference(parameter.name)
            if isinstance(parameter, RoutineVariable)
            else RoutineParameterReference(parameter.name)
        )
    if isinstance(node, exp.Parameter):
        variable = node.this
        _require(
            isinstance(variable, exp.Var),
            "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
            "T-SQL parameter reference is not a plain variable",
        )
        assert isinstance(variable, exp.Var)
        parameter_name = str(variable.this)
        _require(
            bool(_IDENTIFIER_RE.match(parameter_name)),
            "CERTIFIED_ROUTINE_UNSUPPORTED_IDENTIFIER",
            f"routine parameter reference {parameter_name!r} is not a plain identifier",
        )
        parameter = parameters.get(parameter_name.casefold())
        _require(
            parameter is not None,
            "CERTIFIED_ROUTINE_UNKNOWN_PARAMETER",
            f"routine body references undeclared name {parameter_name!r}",
        )
        assert parameter is not None
        return (
            RoutineVariableReference(parameter.name)
            if isinstance(parameter, RoutineVariable)
            else RoutineParameterReference(parameter.name)
        )
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
    language: RoutineLanguage = RoutineLanguage.SQL,
) -> RoutineSelectBody | RoutineBlockBody:
    if language is RoutineLanguage.PLPGSQL:
        _require(
            isinstance(body, exp.Heredoc),
            "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
            "PL/pgSQL routine body must be a dollar-quoted block",
        )
        assert isinstance(body, exp.Heredoc)
        return _parse_plpgsql_block(str(body.this), parameters, source_dialect)
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


def _parse_plpgsql_block(
    raw_body: str,
    parameters: dict[str, RoutineParameter],
    source_dialect: Dialect,
) -> RoutineBlockBody:
    """Parse the deliberately tiny static PL/pgSQL subset.

    The grammar is structural and then every expression is parsed by sqlglot.
    It admits declarations, straight-line assignments and one final RETURN;
    no control flow, query, DML, exception handler or dynamic SQL can enter the
    canonical IR.
    """
    import re

    match = re.fullmatch(
        r"\s*(?:DECLARE\s+(?P<declare>.*?)\s+)?BEGIN\s+(?P<body>.*?)\s*END\s*;?\s*",
        raw_body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    _require(
        match is not None,
        "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
        "PL/pgSQL body must be DECLARE ... BEGIN ... END with a static block",
    )
    assert match is not None
    forbidden = re.compile(
        r"\b(?:FOR|WHILE|LOOP|IF|ELSIF|ELSE|EXCEPTION|EXECUTE|PERFORM|INSERT|UPDATE|DELETE|SELECT|OPEN|FETCH|COMMIT|ROLLBACK)\b",
        flags=re.IGNORECASE,
    )
    body_text = match.group("body")
    _require(
        forbidden.search(body_text) is None,
        "CERTIFIED_ROUTINE_UNSUPPORTED_LANGUAGE",
        "narrow PL/pgSQL route excludes control flow, queries, DML, exceptions and dynamic SQL",
    )

    declarations: list[RoutineVariable] = []
    symbols: dict[str, RoutineParameter | RoutineVariable] = dict(parameters)
    declaration_text = match.group("declare")
    if declaration_text:
        for raw_declaration in split_statements(declaration_text):
            text = raw_declaration.text.strip()
            declaration_match = re.fullmatch(
                r"(?P<name>(?:[A-Za-z_][A-Za-z0-9_]*|\"(?:\"\"|[^\"])+\"))\s+"
                r"(?P<type>.+?)(?:\s*:=\s*(?P<default>.+))?",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            _require(
                declaration_match is not None,
                "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
                f"local declaration {text!r} is not a typed static variable",
            )
            assert declaration_match is not None
            name_text = declaration_match.group("name")
            name_node = sqlglot.parse_one(name_text, read=source_dialect.value)
            assert isinstance(name_node, exp.Expression)
            name: str = _plain_identifier(name_node, "PL/pgSQL local variable")
            _require(
                name.casefold() not in symbols,
                "CERTIFIED_ROUTINE_DUPLICATE_PARAMETER",
                f"PL/pgSQL local variable {name!r} shadows a parameter or declaration",
            )
            type_node = sqlglot.parse_one(
                f"CREATE TABLE __routine_local ({name_text} {declaration_match.group('type')})",
                read=source_dialect.value,
            )
            _require(
                isinstance(type_node, exp.Create)
                and isinstance(type_node.this, exp.Schema)
                and len(type_node.this.expressions) == 1
                and isinstance(type_node.this.expressions[0], exp.ColumnDef)
                and isinstance(type_node.this.expressions[0].kind, exp.DataType),
                "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
                f"local variable {name!r} has no supported type",
            )
            assert isinstance(type_node, exp.Create)
            assert isinstance(type_node.this, exp.Schema)
            column = type_node.this.expressions[0]
            assert isinstance(column, exp.ColumnDef) and isinstance(column.kind, exp.DataType)
            type_ref = _parse_type(column.kind, source_dialect)
            default: ColumnDefault | None = None
            default_text = declaration_match.group("default")
            if default_text is not None:
                default_node = sqlglot.parse_one(default_text, read=source_dialect.value)
                assert isinstance(default_node, exp.Expression)
                default = _parse_default(default_node, type_ref, source_dialect)
            variable = RoutineVariable(name, type_ref, default)
            declarations.append(variable)
            symbols[name.casefold()] = variable

    assignments: list[RoutineAssignment] = []
    return_expression: RoutineValueExpression | None = None
    body_statements = split_statements(body_text)
    _require(bool(body_statements), "CERTIFIED_ROUTINE_UNSUPPORTED_BODY", "PL/pgSQL block is empty")
    for index, raw_statement in enumerate(body_statements):
        text = raw_statement.text.strip()
        return_match = re.fullmatch(r"RETURN\s+(.+)", text, flags=re.IGNORECASE | re.DOTALL)
        if return_match:
            _require(
                return_expression is None and index == len(body_statements) - 1,
                "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
                "PL/pgSQL block must have exactly one final RETURN",
            )
            expression_nodes = sqlglot.parse(return_match.group(1), read=source_dialect.value)
            _require(
                len(expression_nodes) == 1 and isinstance(expression_nodes[0], exp.Expression),
                "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
                "PL/pgSQL RETURN must contain one expression",
            )
            assert isinstance(expression_nodes[0], exp.Expression)
            return_expression = _parse_value(expression_nodes[0], symbols, source_dialect)
            continue
        assignment_match = re.fullmatch(
            r"(?P<target>(?:[A-Za-z_][A-Za-z0-9_]*|\"(?:\"\"|[^\"])+\"))\s*:=\s*(?P<value>.+)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        _require(
            assignment_match is not None,
            "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
            "PL/pgSQL statement must be a simple local assignment or final RETURN",
        )
        assert assignment_match is not None
        target_node = sqlglot.parse_one(assignment_match.group("target"), read=source_dialect.value)
        assert isinstance(target_node, exp.Expression)
        target = _plain_identifier(target_node, "PL/pgSQL assignment target")
        target_variable = symbols.get(target.casefold())
        _require(
            isinstance(target_variable, RoutineVariable),
            "CERTIFIED_ROUTINE_ASSIGNMENT_TARGET",
            f"assignment target {target!r} must be a declared local variable",
        )
        assert isinstance(target_variable, RoutineVariable)
        expression_nodes = sqlglot.parse(assignment_match.group("value"), read=source_dialect.value)
        _require(
            len(expression_nodes) == 1 and isinstance(expression_nodes[0], exp.Expression),
            "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
            "PL/pgSQL assignment must contain one expression",
        )
        assert isinstance(expression_nodes[0], exp.Expression)
        value = _parse_value(expression_nodes[0], symbols, source_dialect)
        _require(
            _value_kind(value, symbols) == _type_kind(target_variable.type_ref),
            "CERTIFIED_ROUTINE_ASSIGNMENT_TYPE_MISMATCH",
            f"assignment to {target!r} does not have the declared canonical type",
        )
        assignments.append(RoutineAssignment(target, value))
    _require(
        return_expression is not None,
        "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
        "PL/pgSQL block must contain one final RETURN",
    )
    assert return_expression is not None
    return RoutineBlockBody(tuple(declarations), tuple(assignments), return_expression)


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
    parameters: Mapping[str, RoutineParameter | RoutineVariable],
) -> str:
    if isinstance(value, RoutineLiteral):
        if value.is_string:
            return "TEXT"
        if value.is_boolean:
            return "BOOLEAN"
        return "DECIMAL" if any(token in value.value for token in (".", "e", "E")) else "INTEGER"
    if isinstance(value, RoutineParameterReference):
        return _type_kind(parameters[value.name.casefold()].type_ref)
    if isinstance(value, RoutineVariableReference):
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
    body: RoutineSelectBody | RoutineBlockBody,
    return_type: CanonicalTypeRef,
    parameters: Mapping[str, RoutineParameter | RoutineVariable],
) -> None:
    expression = body.expression if isinstance(body, RoutineSelectBody) else body.return_expression
    body_kind = _value_kind(expression, parameters)
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
        type_ref = _parse_type(parameter_type, source_dialect)
        default: ColumnDefault | None = None
        for constraint in item.args.get("constraints") or []:
            constraint_kind = constraint.kind if isinstance(constraint, exp.ColumnConstraint) else constraint
            if isinstance(constraint_kind, exp.InOutColumnConstraint):
                _require(
                    bool(constraint_kind.args.get("input_")) and not bool(constraint_kind.args.get("output")),
                    "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
                    "scalar functions only support explicit IN parameters",
                )
                continue
            _require(
                isinstance(constraint_kind, exp.DefaultColumnConstraint),
                "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
                "scalar function parameters only support a simple side-effect-free default",
            )
            assert isinstance(constraint_kind, exp.DefaultColumnConstraint)
            _require(
                default is None,
                "CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER",
                "routine parameter has more than one default",
            )
            default = _parse_default(constraint_kind.this, type_ref, source_dialect)
        parameters.append(RoutineParameter(parameter_name, type_ref, default=default))
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
        language in (RoutineLanguage.SQL, RoutineLanguage.PLPGSQL),
        "CERTIFIED_ROUTINE_UNSUPPORTED_LANGUAGE",
        f"routine language {language.value} is outside the narrow SQL/PLpgSQL expression route",
    )
    # These facts are retained by the canonical Routine model. They are
    # deliberately admitted on the SOURCE side once the declaration and body
    # are typed, while _require_emittable rejects them per target until an
    # exact security/nullability/volatility route is certified. Keeping the
    # two decisions separate makes the source-candidate metric useful without
    # laundering security context into a weaker target routine.
    body = _parse_body(statement.args.get("expression"), parameter_map, source_dialect, language)
    assert return_type is not None
    validation_symbols: dict[str, RoutineParameter | RoutineVariable] = dict(parameter_map)
    if isinstance(body, RoutineBlockBody):
        validation_symbols.update({item.name.casefold(): item for item in body.declarations})
    _validate_return_type(body, return_type, validation_symbols)
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
    if isinstance(value, RoutineVariableReference):
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


def _require_emittable(routine: Routine, target_dialect: Dialect, allow_routine_shim: bool = False) -> None:
    if routine.or_replace:
        if target_dialect not in (Dialect.POSTGRES, Dialect.ORACLE):
            raise DialectError(
                "CERTIFIED_ROUTINE_REPLACE_UNSUPPORTED_BY_TARGET",
                f"{target_dialect.value} has no exact CREATE OR REPLACE FUNCTION spelling",
            )
    if routine.strict and not allow_routine_shim:
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
    if routine.stability is not None and not allow_routine_shim:
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


def emit_create_function(routine: Routine, target_dialect: Dialect, allow_routine_shim: bool = False) -> str:
    """Emit one scalar SQL function in native target syntax."""
    _require_emittable(routine, target_dialect, allow_routine_shim=allow_routine_shim)
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

    def render_default(item: RoutineParameter) -> str:
        if item.default is None:
            return ""
        if target_dialect is Dialect.MYSQL:
            raise DialectError(
                "CERTIFIED_ROUTINE_PARAMETER_DEFAULT_UNSUPPORTED_BY_TARGET",
                "MySQL stored-function parameters do not have an exact default-value signature route",
            )
        value = item.default.literal
        if item.default.kind is DefaultKind.NULL:
            rendered = "NULL"
        elif item.default.kind is DefaultKind.CURRENT_TIMESTAMP:
            rendered = "CURRENT_TIMESTAMP"
        elif item.default.kind is DefaultKind.BOOLEAN:
            rendered = "1" if target_dialect in (Dialect.ORACLE, Dialect.TSQL) and value == "true" else (
                "0" if target_dialect in (Dialect.ORACLE, Dialect.TSQL) else ("TRUE" if value == "true" else "FALSE")
            )
        elif item.default.kind is DefaultKind.STRING:
            assert value is not None
            rendered = "'" + value.replace("'", "''") + "'"
        else:
            assert value is not None
            rendered = value
        keyword = "=" if target_dialect is Dialect.TSQL else "DEFAULT"
        return f" {keyword} {rendered}"

    params = ", ".join(
        ("@" if target_dialect is Dialect.TSQL else "")
        + quote_identifier(item.name, target_dialect)
        + " "
        + routine_type(item.type_ref)
        + render_default(item)
        for item in routine.parameters
    )
    return_type = routine_type(routine.return_type)
    qualified = qualified_name(routine.schema, routine.name, target_dialect)
    replace = " OR REPLACE" if routine.or_replace and target_dialect in (Dialect.POSTGRES, Dialect.ORACLE) else ""
    tsql_variables = target_dialect is Dialect.TSQL
    if isinstance(routine.body, RoutineSelectBody):
        value = _render_routine_value(routine.body.expression, target_dialect, tsql_parameters=tsql_variables)
        if routine.strict and allow_routine_shim and target_dialect is not Dialect.POSTGRES and routine.parameters:
            null_cond = " OR ".join(
                f"{('@' if tsql_variables else '') + quote_identifier(p.name, target_dialect)} IS NULL"
                for p in routine.parameters
            )
            value = f"CASE WHEN {null_cond} THEN NULL ELSE {value} END"
        if target_dialect is Dialect.POSTGRES:
            det = f" {routine.stability.value}" if routine.stability is not None else ""
            strict_clause = " STRICT" if routine.strict else ""
            return (
                f"CREATE{replace} FUNCTION {qualified}({params}) RETURNS {return_type} "
                f"LANGUAGE SQL{det}{strict_clause} AS $$ SELECT {value} $$"
            )
        if target_dialect is Dialect.MYSQL:
            det = " DETERMINISTIC" if routine.stability is RoutineStability.IMMUTABLE else ""
            return f"CREATE FUNCTION {qualified}({params}) RETURNS {return_type}{det} RETURN {value}"
        if target_dialect is Dialect.ORACLE:
            det = " DETERMINISTIC" if routine.stability is RoutineStability.IMMUTABLE else ""
            return f"CREATE{replace} FUNCTION {qualified}({params}) RETURN {return_type}{det} IS BEGIN RETURN {value}; END;"
        return f"CREATE FUNCTION {qualified}({params}) RETURNS {return_type} AS BEGIN RETURN {value} END"

    body = routine.body
    declarations = []
    for variable in body.declarations:
        default = ""
        if variable.default is not None:
            default_value = variable.default.literal
            if variable.default.kind is DefaultKind.NULL:
                default_value = "NULL"
            elif variable.default.kind is DefaultKind.CURRENT_TIMESTAMP:
                default_value = "CURRENT_TIMESTAMP"
            elif variable.default.kind is DefaultKind.STRING:
                default_value = "'" + default_value.replace("'", "''") + "'"
            elif variable.default.kind is DefaultKind.BOOLEAN and target_dialect in (Dialect.ORACLE, Dialect.TSQL):
                default_value = "1" if default_value == "true" else "0"
            assert default_value is not None
            default = (
                (
                    " = "
                    if target_dialect is Dialect.TSQL
                    else " := "
                    if target_dialect is Dialect.ORACLE
                    else " DEFAULT "
                )
                + default_value
            )
        variable_name = ("@" if tsql_variables else "") + quote_identifier(variable.name, target_dialect)
        declarations.append(f"{variable_name} {routine_type(variable.type_ref)}{default}")
    assignments = []
    for assignment in body.assignments:
        left = ("@" if tsql_variables else "") + quote_identifier(assignment.target, target_dialect)
        right = _render_routine_value(assignment.value, target_dialect, tsql_parameters=tsql_variables)
        if target_dialect is Dialect.TSQL:
            assignments.append(f"SET {left} = {right};")
        else:
            assignments.append(f"{left} := {right};")
    returned = _render_routine_value(body.return_expression, target_dialect, tsql_parameters=tsql_variables)
    if routine.strict and allow_routine_shim and target_dialect is not Dialect.POSTGRES and routine.parameters:
        null_cond = " OR ".join(
            f"{('@' if tsql_variables else '') + quote_identifier(p.name, target_dialect)} IS NULL"
            for p in routine.parameters
        )
        returned = f"CASE WHEN {null_cond} THEN NULL ELSE {returned} END"
    if target_dialect is Dialect.POSTGRES:
        declaration_sql = " ".join(item + ";" for item in declarations)
        det = f" {routine.stability.value}" if routine.stability is not None else ""
        strict_clause = " STRICT" if routine.strict else ""
        return (
            f"CREATE{replace} FUNCTION {qualified}({params}) RETURNS {return_type} LANGUAGE plpgsql{det}{strict_clause} AS $$ "
            f"DECLARE {declaration_sql} BEGIN {' '.join(assignments)} RETURN {returned}; END $$"
        )
    if target_dialect is Dialect.MYSQL:
        det = " DETERMINISTIC" if routine.stability is RoutineStability.IMMUTABLE else ""
        return f"CREATE FUNCTION {qualified}({params}) RETURNS {return_type}{det} BEGIN " \
            + " ".join(f"DECLARE {item};" for item in declarations) \
            + " " + " ".join(assignments) + f" RETURN {returned}; END"
    if target_dialect is Dialect.ORACLE:
        det = " DETERMINISTIC" if routine.stability is RoutineStability.IMMUTABLE else ""
        return f"CREATE{replace} FUNCTION {qualified}({params}) RETURN {return_type}{det} IS " \
            + " ".join(item + ";" for item in declarations) \
            + " BEGIN " + " ".join(assignments) + f" RETURN {returned}; END;"
    return f"CREATE FUNCTION {qualified}({params}) RETURNS {return_type} AS BEGIN " \
        + " ".join(f"DECLARE {item};" for item in declarations) \
        + " " + " ".join(assignments) + f" RETURN {returned} END"
