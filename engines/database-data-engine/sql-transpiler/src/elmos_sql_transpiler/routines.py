"""Bounded SQL-language routine and trigger conversion.

This is not a PL/SQL / T-SQL / PL/pgSQL translator. The admitted subset is:

* scalar ``LANGUAGE SQL`` (or MySQL ``RETURN`` / T-SQL ``RETURN``) functions
  whose body is one expression over literals, parameters, arithmetic and
  concatenation
* ``LANGUAGE SQL`` procedures whose body is one INSERT/UPDATE/DELETE
* row-level triggers that call one named nullary function

SQLite has no stored functions or procedures; DuckDB receives functions as
``CREATE MACRO`` under an explicit obligation. PL/pgSQL blocks, packages,
dynamic SQL, SECURITY DEFINER, STRICT, RETURNS TABLE and OUT parameters stay
fail-closed. Source/target execution remains ``NOT_RUN``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError, TokenError, UnsupportedError

from .rewrites import RewriteBlocked

ROUTINE_SQL_FUNCTION = "ROUTINE_SQL_SCALAR_FUNCTION"
ROUTINE_SQL_PROCEDURE = "ROUTINE_SQL_SINGLE_DML_PROCEDURE"
ROUTINE_ROW_TRIGGER = "ROUTINE_NAMED_FUNCTION_ROW_TRIGGER"
ROUTINE_DUCKDB_MACRO = "ROUTINE_DUCKDB_MACRO_SUBSTITUTE"
ROUTINE_TARGET_OPAQUE = "ROUTINE_TARGET_PARSER_OPAQUE"
ROUTINE_STABILITY_DROPPED = "ROUTINE_STABILITY_NOT_PORTED"

FUNCTION_RULE = "core.emit-sql-scalar-function"
PROCEDURE_RULE = "core.emit-sql-single-dml-procedure"
TRIGGER_RULE = "core.emit-named-function-row-trigger"

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ROUTINE_COMMAND = re.compile(r"\b(FUNCTION|PROCEDURE|TRIGGER)\b", re.IGNORECASE)
_ORACLE_FUNCTION = re.compile(
    r"^CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<params>.*)\)\s+"
    r"RETURN\s+(?P<ret>[A-Za-z_][A-Za-z0-9_]*(?:\s*\(\s*\d+\s*\))?)\s+"
    r"(?:AS|IS)\s+BEGIN\s+RETURN\s+(?P<body>.+?)\s*;\s*(?:END;?)?\s*$",
    re.IGNORECASE | re.DOTALL,
)
_TEXT_PROCEDURE = re.compile(
    r"^CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\s*\))?\s+"
    r"(?:LANGUAGE\s+SQL\s+AS\s+\$\$(?P<pg>.+?)\$\$|"
    r"(?:AS\s+)?BEGIN\s+(?P<body>.+?)\s*;?\s*END;?)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_TEXT_TRIGGER = re.compile(
    r"^CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+"
    r"(?P<timing>BEFORE|AFTER)\s+(?P<event>INSERT|UPDATE|DELETE)\s+ON\s+"
    r"(?P<table>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s+FOR\s+EACH\s+ROW)?"
    r"(?:\s+(?:EXECUTE\s+(?:FUNCTION|PROCEDURE)|BEGIN\s+(?:CALL|SELECT)?|AS\s+BEGIN\s+EXEC)\s+"
    r"(?P<fn>[A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)?\s*;?\s*(?:END;?)?)?\s*$",
    re.IGNORECASE | re.DOTALL,
)

_TYPE_TOKEN = {
    "INT": "INTEGER",
    "INT4": "INTEGER",
    "INTEGER": "INTEGER",
    "SMALLINT": "INTEGER",
    "BIGINT": "BIGINT",
    "INT8": "BIGINT",
}


class RoutineBlocked(RewriteBlocked):
    """A routine or trigger was recognized and refused."""


@dataclass(frozen=True)
class RoutineParameter:
    name: str
    canonical_type: str


@dataclass(frozen=True)
class ScalarFunction:
    name: str
    parameters: tuple[RoutineParameter, ...]
    return_type: str
    expression: exp.Expression
    stability_dropped: bool = False


@dataclass(frozen=True)
class SqlProcedure:
    name: str
    body: exp.Expression


@dataclass(frozen=True)
class SqlTrigger:
    name: str
    timing: str
    event: str
    table: str
    function_name: str


@dataclass(frozen=True)
class RoutineConversion:
    sql: str
    kind: str
    object_name: str
    obligations: tuple[str, ...]
    rule_ids: tuple[str, ...]
    skip_following_end: bool
    opaque_target: bool


def is_end_statement(statement: exp.Expression) -> bool:
    return isinstance(statement, exp.EndStatement)


def is_routine_command(statement: exp.Expression) -> bool:
    if not isinstance(statement, exp.Command):
        return False
    payload = str(statement.args.get("expression") or "")
    return _ROUTINE_COMMAND.search(payload) is not None


def convert(
    statement: exp.Expression,
    source_dialect: str,
    target_dialect: str,
) -> RoutineConversion | None:
    """Convert one routine/trigger statement or return None if it is not one."""
    if is_end_statement(statement):
        return None
    if isinstance(statement, exp.Create):
        kind = str(statement.args.get("kind") or "").upper()
        if kind == "FUNCTION":
            return _emit_function(_parse_create_function(statement, source_dialect), target_dialect)
        if kind == "PROCEDURE":
            return _emit_procedure(_parse_create_procedure(statement, source_dialect), target_dialect)
        if kind == "TRIGGER":
            return _emit_trigger(_parse_create_trigger(statement), target_dialect)
        if kind in {"MACRO", "AGGREGATE"}:
            raise RoutineBlocked(
                "ROUTINE_KIND_UNSUPPORTED",
                "DuckDB macros and aggregates are not a source-side stored-routine "
                "contract; only typed SQL functions are admitted",
            )
        return None
    if isinstance(statement, exp.Command) and is_routine_command(statement):
        # Oracle/T-SQL/SQLite parse CREATE FUNCTION/TRIGGER as Command plus a
        # trailing EndStatement. The conversion is of the Command; the END
        # token must be skipped regardless of which target we emit toward.
        return replace(_convert_command(statement, source_dialect, target_dialect), skip_following_end=True)
    return None


def reparse_routine_sql(sql: str, dialect: str, name: str) -> tuple[exp.Expression, bool]:
    """Reparse emitted routine SQL. Opaque Command is allowed only when the
    reconstructed text still names the same object; that fact is returned as
    the second tuple element so callers can record an obligation instead of
    pretending the target parser built a typed AST."""
    try:
        parsed = sqlglot.parse(sql, read=dialect, error_level=ErrorLevel.RAISE)
    except (ParseError, TokenError) as error:
        raise UnsupportedError("routine target SQL failed exact-dialect reparsing") from error
    statements = [item for item in parsed if not is_end_statement(item)]
    if len(statements) != 1:
        raise UnsupportedError("routine target re-parse did not yield one statement")
    target = statements[0]
    if isinstance(target, exp.Create):
        return target, False
    if isinstance(target, exp.Command) and name.casefold() in str(target.args.get("expression") or "").casefold():
        return target, True
    raise UnsupportedError("routine target re-parse did not preserve the emitted identity")


def _command_sql(statement: exp.Command) -> str:
    payload = str(statement.args.get("expression") or "").strip()
    text = "CREATE " + payload
    if not re.search(r"END\s*;?\s*$", text, re.IGNORECASE):
        text = text.rstrip(";") + "; END;"
    return text


def _convert_command(
    statement: exp.Command,
    source_dialect: str,
    target_dialect: str,
) -> RoutineConversion:
    text = _command_sql(statement)
    upper = text.upper()
    if " FUNCTION " in upper:
        return _emit_function(_parse_function_text(text, source_dialect), target_dialect)
    if " PROCEDURE " in upper:
        return _emit_procedure(_parse_procedure_text(text, source_dialect), target_dialect)
    if " TRIGGER " in upper:
        return _emit_trigger(_parse_trigger_text(text), target_dialect)
    raise RoutineBlocked(
        "ROUTINE_COMMAND_UNRECOGNIZED",
        "An opaque CREATE command looked like a routine but did not match the "
        "bounded function, procedure, or trigger subset",
    )


def _require_identifier(name: str, label: str) -> str:
    if _IDENTIFIER.fullmatch(name) is None:
        raise RoutineBlocked(
            "ROUTINE_IDENTIFIER_UNSUPPORTED",
            f"{label} must be a plain unquoted identifier",
        )
    return name


def _canonical_type(data_type: exp.DataType) -> str:
    token = str(getattr(data_type.this, "name", data_type.this)).upper()
    if token in _TYPE_TOKEN:
        if data_type.expressions:
            raise RoutineBlocked(
                "ROUTINE_TYPE_UNSUPPORTED",
                "integer routine types cannot carry precision or scale parameters",
            )
        return _TYPE_TOKEN[token]
    if token in {"VARCHAR", "NVARCHAR", "CHAR", "NCHAR"}:
        params = data_type.expressions or []
        if len(params) != 1:
            raise RoutineBlocked(
                "ROUTINE_TYPE_UNSUPPORTED",
                "character routine types require an explicit length",
            )
        literal = params[0].this if isinstance(params[0], exp.DataTypeParam) else params[0]
        if not (isinstance(literal, exp.Literal) and literal.is_int):
            raise RoutineBlocked(
                "ROUTINE_TYPE_UNSUPPORTED",
                "character routine length must be an integer literal",
            )
        length = int(literal.this)
        if length < 1 or length > 4000:
            raise RoutineBlocked(
                "ROUTINE_TYPE_UNSUPPORTED",
                "character routine length must be between 1 and 4000",
            )
        return f"VARCHAR({length})"
    raise RoutineBlocked(
        "ROUTINE_TYPE_UNSUPPORTED",
        "routine types are limited to INTEGER, BIGINT and VARCHAR(n)",
    )


def _canonical_type_token(token: str) -> str:
    stripped = " ".join(token.split())
    match = re.fullmatch(r"([A-Za-z]+)(?:\s*\(\s*(\d+)\s*\))?", stripped, re.IGNORECASE)
    if match is None:
        raise RoutineBlocked("ROUTINE_TYPE_UNSUPPORTED", "routine type token is malformed")
    name = match.group(1).upper()
    length = match.group(2)
    if name in _TYPE_TOKEN:
        if length is not None:
            raise RoutineBlocked(
                "ROUTINE_TYPE_UNSUPPORTED",
                "integer routine types cannot carry precision or scale parameters",
            )
        return _TYPE_TOKEN[name]
    if name in {"VARCHAR", "VARCHAR2", "NVARCHAR"} and length is not None:
        value = int(length)
        if value < 1 or value > 4000:
            raise RoutineBlocked(
                "ROUTINE_TYPE_UNSUPPORTED",
                "character routine length must be between 1 and 4000",
            )
        return f"VARCHAR({value})"
    raise RoutineBlocked(
        "ROUTINE_TYPE_UNSUPPORTED",
        "routine types are limited to INTEGER, BIGINT and VARCHAR(n)",
    )


def _render_type(canonical: str, dialect: str) -> str:
    if canonical == "INTEGER":
        return {"oracle": "NUMBER(10)", "tsql": "INT"}.get(dialect, "INTEGER")
    if canonical == "BIGINT":
        return {"oracle": "NUMBER(19)", "mysql": "BIGINT", "tsql": "BIGINT"}.get(dialect, "BIGINT")
    length = canonical[len("VARCHAR(") : -1]
    if dialect == "oracle":
        return f"VARCHAR2({length})"
    if dialect == "tsql":
        return f"VARCHAR({length})"
    return canonical


def _parameter_name(node: exp.Expression) -> str:
    if isinstance(node, exp.Parameter) and isinstance(node.this, exp.Var):
        return _require_identifier(str(node.this.this), "routine parameter")
    if isinstance(node, exp.Identifier):
        return _require_identifier(str(node.this), "routine parameter")
    if isinstance(node, exp.Column) and node.this is not None:
        return _parameter_name(node.this)
    raise RoutineBlocked(
        "ROUTINE_PARAMETER_UNSUPPORTED",
        "routine parameters must be plain typed names",
    )


def _parse_parameters(udf: exp.UserDefinedFunction) -> tuple[RoutineParameter, ...]:
    parameters: list[RoutineParameter] = []
    for item in udf.expressions:
        if isinstance(item, exp.Identifier):
            raise RoutineBlocked(
                "ROUTINE_PARAMETER_UNSUPPORTED",
                "routine parameters must carry a declared type",
            )
        if not isinstance(item, exp.ColumnDef) or not isinstance(item.kind, exp.DataType):
            raise RoutineBlocked(
                "ROUTINE_PARAMETER_UNSUPPORTED",
                "routine parameters must be typed plain parameters",
            )
        if item.args.get("constraints"):
            raise RoutineBlocked(
                "ROUTINE_PARAMETER_UNSUPPORTED",
                "parameter defaults, OUT/INOUT modes and constraints stay fail-closed",
            )
        parameters.append(
            RoutineParameter(
                name=_parameter_name(item.this),
                canonical_type=_canonical_type(item.kind),
            )
        )
    names = [item.name.casefold() for item in parameters]
    if len(names) != len(set(names)):
        raise RoutineBlocked(
            "ROUTINE_PARAMETER_UNSUPPORTED",
            "routine parameter names must be unique",
        )
    return tuple(parameters)


def _routine_name(udf: exp.UserDefinedFunction) -> str:
    table = udf.this
    if not isinstance(table, exp.Table):
        raise RoutineBlocked("ROUTINE_IDENTIFIER_UNSUPPORTED", "routine name is missing")
    if table.args.get("db") is not None or table.args.get("catalog") is not None:
        raise RoutineBlocked(
            "ROUTINE_NAMESPACE_UNSUPPORTED",
            "schema-qualified routines need an explicit namespace map and stay blocked",
        )
    ident = table.this
    if not isinstance(ident, exp.Identifier) or ident.args.get("quoted"):
        raise RoutineBlocked(
            "ROUTINE_IDENTIFIER_UNSUPPORTED",
            "routine name must be a plain unquoted identifier",
        )
    return _require_identifier(str(ident.this), "routine name")


def _allowed_expression(node: exp.Expression, parameters: frozenset[str]) -> None:
    if isinstance(node, (exp.Literal, exp.Boolean, exp.Null)):
        return
    if isinstance(node, exp.Paren) and node.this is not None:
        _allowed_expression(node.this, parameters)
        return
    if isinstance(node, (exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod, exp.DPipe)):
        if node.this is None or node.expression is None:
            raise RoutineBlocked("ROUTINE_BODY_UNSUPPORTED", "binary expression is incomplete")
        _allowed_expression(node.this, parameters)
        _allowed_expression(node.expression, parameters)
        return
    if isinstance(node, exp.Concat):
        if len(node.expressions) < 2:
            raise RoutineBlocked("ROUTINE_BODY_UNSUPPORTED", "CONCAT requires at least two arguments")
        for item in node.expressions:
            _allowed_expression(item, parameters)
        return
    if isinstance(node, exp.Column):
        if node.args.get("table") is not None:
            raise RoutineBlocked(
                "ROUTINE_BODY_UNSUPPORTED",
                "qualified column references are outside the scalar-function subset",
            )
        name = str(node.name)
        if name.casefold() not in parameters:
            raise RoutineBlocked(
                "ROUTINE_UNKNOWN_PARAMETER",
                "function body references a name that is not a declared parameter",
            )
        return
    if isinstance(node, exp.Parameter) and isinstance(node.this, exp.Var):
        name = str(node.this.this)
        if name.casefold() not in parameters:
            raise RoutineBlocked(
                "ROUTINE_UNKNOWN_PARAMETER",
                "function body references a name that is not a declared parameter",
            )
        return
    raise RoutineBlocked(
        "ROUTINE_BODY_UNSUPPORTED",
        "function bodies are limited to literals, parameters, arithmetic and concatenation",
    )


def _unwrap_return_expression(node: exp.Expression) -> exp.Expression:
    current = node
    if isinstance(current, exp.Return) and current.this is not None:
        current = current.this
    if (
        isinstance(current, exp.Alias)
        and isinstance(current.args.get("alias"), exp.Identifier)
        and str(current.args["alias"].this).upper() == "END"
    ):
        current = current.this
    if isinstance(current, exp.Paren) and current.this is not None:
        current = current.this
    return current


def _expression_from_body(body: exp.Expression, source_dialect: str, parameters: frozenset[str]) -> exp.Expression:
    if isinstance(body, exp.Heredoc):
        inner_sql = str(body.this)
        parsed = sqlglot.parse(inner_sql, read=source_dialect, error_level=ErrorLevel.RAISE)
        if len(parsed) != 1 or not isinstance(parsed[0], exp.Select):
            raise RoutineBlocked(
                "ROUTINE_BODY_UNSUPPORTED",
                "SQL function bodies must be a single SELECT of one expression",
            )
        return _expression_from_body(parsed[0], source_dialect, parameters)
    if isinstance(body, exp.Literal) and body.is_string:
        parsed = sqlglot.parse(str(body.this), read=source_dialect, error_level=ErrorLevel.RAISE)
        if len(parsed) != 1:
            raise RoutineBlocked(
                "ROUTINE_BODY_UNSUPPORTED",
                "SQL function bodies must be a single SELECT of one expression",
            )
        return _expression_from_body(parsed[0], source_dialect, parameters)
    if isinstance(body, exp.Select):
        if any(
            body.args.get(key) is not None
            for key in ("from_", "where", "group", "having", "order", "limit", "joins", "with_")
        ):
            raise RoutineBlocked(
                "ROUTINE_BODY_UNSUPPORTED",
                "SQL function SELECT bodies cannot include FROM, filters, grouping or ordering",
            )
        if len(body.expressions) != 1:
            raise RoutineBlocked(
                "ROUTINE_BODY_UNSUPPORTED",
                "SQL function bodies must select exactly one expression",
            )
        expression = body.expressions[0]
        if isinstance(expression, exp.Alias):
            expression = expression.this
        _allowed_expression(expression, parameters)
        return expression
    if isinstance(body, (exp.Return, exp.Paren)):
        expression = _unwrap_return_expression(body)
        _allowed_expression(expression, parameters)
        return expression
    raise RoutineBlocked(
        "ROUTINE_BODY_UNSUPPORTED",
        "function body is outside the SQL-language scalar subset",
    )


def _language_and_return(statement: exp.Create) -> tuple[str, bool]:
    properties = statement.args.get("properties")
    language = "SQL"
    return_type: str | None = None
    stability_dropped = False
    if isinstance(properties, exp.Properties):
        for prop in properties.expressions:
            if isinstance(prop, exp.ReturnsProperty):
                if prop.args.get("is_table"):
                    raise RoutineBlocked(
                        "ROUTINE_TABLE_RETURN_UNSUPPORTED",
                        "RETURNS TABLE is outside the scalar-function subset",
                    )
                if not isinstance(prop.this, exp.DataType):
                    raise RoutineBlocked(
                        "ROUTINE_TYPE_UNSUPPORTED",
                        "function return type is not a scalar data type",
                    )
                return_type = _canonical_type(prop.this)
            elif isinstance(prop, exp.LanguageProperty):
                language = str(prop.args.get("this") or "").upper()
            elif isinstance(prop, exp.StabilityProperty):
                # MySQL DETERMINISTIC arrives here as IMMUTABLE. The flag is
                # retained as an obligation rather than mapped to a weaker
                # target declaration.
                stability_dropped = True
            elif isinstance(prop, (exp.StrictProperty, exp.SqlSecurityProperty, exp.SetConfigProperty)):
                raise RoutineBlocked(
                    "ROUTINE_SECURITY_CONTEXT_UNSUPPORTED",
                    "STRICT, SECURITY DEFINER and SET search_path stay fail-closed",
                )
            else:
                raise RoutineBlocked(
                    "ROUTINE_PROPERTY_UNSUPPORTED",
                    f"routine property {type(prop).__name__} is outside the bounded subset",
                )
    if language not in {"", "SQL"}:
        raise RoutineBlocked(
            "ROUTINE_LANGUAGE_UNSUPPORTED",
            "only LANGUAGE SQL scalar functions are converted; PL/pgSQL, PL/SQL and T-SQL "
            "control flow stay fail-closed",
        )
    if return_type is None:
        raise RoutineBlocked(
            "ROUTINE_MISSING_RETURN_TYPE",
            "scalar functions require an explicit RETURNS type",
        )
    return return_type, stability_dropped


def _parse_create_function(statement: exp.Create, source_dialect: str) -> ScalarFunction:
    if statement.args.get("replace"):
        raise RoutineBlocked(
            "ROUTINE_REPLACE_UNSUPPORTED",
            "CREATE OR REPLACE FUNCTION is not portable to every target in this profile set",
        )
    if not isinstance(statement.this, exp.UserDefinedFunction):
        raise RoutineBlocked("ROUTINE_KIND_UNSUPPORTED", "CREATE FUNCTION payload is malformed")
    udf = statement.this
    parameters = _parse_parameters(udf)
    return_type, stability_dropped = _language_and_return(statement)
    body = statement.args.get("expression")
    if body is None:
        raise RoutineBlocked("ROUTINE_BODY_UNSUPPORTED", "function body is missing")
    names = frozenset(item.name.casefold() for item in parameters)
    expression = _expression_from_body(body, source_dialect, names)
    return ScalarFunction(
        name=_routine_name(udf),
        parameters=parameters,
        return_type=return_type,
        expression=expression,
        stability_dropped=stability_dropped,
    )


def _parse_function_text(sql: str, source_dialect: str) -> ScalarFunction:
    match = _ORACLE_FUNCTION.fullmatch(" ".join(sql.split()))
    if match is None:
        match = _ORACLE_FUNCTION.fullmatch(sql.strip())
    if match is None:
        raise RoutineBlocked(
            "ROUTINE_BODY_UNSUPPORTED",
            "opaque CREATE FUNCTION did not match the bounded Oracle/PL-SQL RETURN form",
        )
    parameters: list[RoutineParameter] = []
    raw_params = match.group("params").strip()
    if raw_params:
        for item in raw_params.split(","):
            parts = item.split()
            if len(parts) != 2:
                raise RoutineBlocked(
                    "ROUTINE_PARAMETER_UNSUPPORTED",
                    "opaque function parameters must be a name and a single type token",
                )
            parameters.append(
                RoutineParameter(
                    name=_require_identifier(parts[0], "routine parameter"),
                    canonical_type=_canonical_type_token(parts[1]),
                )
            )
    names = frozenset(item.name.casefold() for item in parameters)
    try:
        expression = sqlglot.parse_one(match.group("body"), read=source_dialect)
    except (ParseError, TokenError) as error:
        raise RoutineBlocked(
            "ROUTINE_BODY_UNSUPPORTED",
            "opaque function RETURN expression did not parse as a typed scalar",
        ) from error
    _allowed_expression(expression, names)
    return ScalarFunction(
        name=_require_identifier(match.group("name"), "routine name"),
        parameters=tuple(parameters),
        return_type=_canonical_type_token(match.group("ret")),
        expression=expression,
    )


def _single_dml(body: exp.Expression, source_dialect: str) -> exp.Expression:
    current: exp.Expression = body
    if isinstance(current, exp.Heredoc):
        parsed = sqlglot.parse(str(current.this), read=source_dialect, error_level=ErrorLevel.RAISE)
        if len(parsed) != 1:
            raise RoutineBlocked(
                "ROUTINE_PROCEDURE_UNSUPPORTED",
                "SQL procedures must contain exactly one DML statement",
            )
        current = parsed[0]
    if isinstance(current, exp.Block):
        statements = [item for item in current.expressions if not is_end_statement(item)]
        if len(statements) != 1:
            raise RoutineBlocked(
                "ROUTINE_PROCEDURE_UNSUPPORTED",
                "SQL procedures must contain exactly one DML statement",
            )
        current = statements[0]
    if not isinstance(current, (exp.Insert, exp.Update, exp.Delete)):
        raise RoutineBlocked(
            "ROUTINE_PROCEDURE_UNSUPPORTED",
            "SQL procedures are limited to one INSERT, UPDATE or DELETE",
        )
    if current.args.get("returning") is not None or current.args.get("with_") is not None:
        raise RoutineBlocked(
            "ROUTINE_PROCEDURE_UNSUPPORTED",
            "procedure DML cannot include WITH or RETURNING",
        )
    return current


def _parse_create_procedure(statement: exp.Create, source_dialect: str) -> SqlProcedure:
    if not isinstance(statement.this, exp.UserDefinedFunction):
        raise RoutineBlocked("ROUTINE_KIND_UNSUPPORTED", "CREATE PROCEDURE payload is malformed")
    udf = statement.this
    if udf.expressions:
        raise RoutineBlocked(
            "ROUTINE_PARAMETER_UNSUPPORTED",
            "bounded procedures do not admit parameters, OUT values or defaults",
        )
    properties = statement.args.get("properties")
    if isinstance(properties, exp.Properties):
        for prop in properties.expressions:
            if isinstance(prop, exp.LanguageProperty):
                if str(prop.args.get("this") or "").upper() not in {"", "SQL"}:
                    raise RoutineBlocked(
                        "ROUTINE_LANGUAGE_UNSUPPORTED",
                        "only LANGUAGE SQL procedures are converted",
                    )
            else:
                raise RoutineBlocked(
                    "ROUTINE_PROPERTY_UNSUPPORTED",
                    "procedure metadata outside LANGUAGE SQL stays fail-closed",
                )
    body = statement.args.get("expression")
    if body is None:
        raise RoutineBlocked("ROUTINE_PROCEDURE_UNSUPPORTED", "procedure body is missing")
    return SqlProcedure(name=_routine_name(udf), body=_single_dml(body, source_dialect))


def _parse_procedure_text(sql: str, source_dialect: str) -> SqlProcedure:
    match = _TEXT_PROCEDURE.fullmatch(sql.strip())
    if match is None:
        raise RoutineBlocked(
            "ROUTINE_PROCEDURE_UNSUPPORTED",
            "opaque CREATE PROCEDURE did not match the bounded single-DML form",
        )
    body_sql = (match.group("pg") or match.group("body") or "").strip().rstrip(";")
    try:
        parsed = sqlglot.parse(body_sql, read=source_dialect, error_level=ErrorLevel.RAISE)
    except (ParseError, TokenError) as error:
        raise RoutineBlocked(
            "ROUTINE_PROCEDURE_UNSUPPORTED",
            "procedure body did not parse as typed DML",
        ) from error
    if len(parsed) != 1:
        raise RoutineBlocked(
            "ROUTINE_PROCEDURE_UNSUPPORTED",
            "SQL procedures must contain exactly one DML statement",
        )
    return SqlProcedure(
        name=_require_identifier(match.group("name"), "routine name"),
        body=_single_dml(parsed[0], source_dialect),
    )


def _parse_create_trigger(statement: exp.Create) -> SqlTrigger:
    ident = statement.this
    if not isinstance(ident, exp.Identifier) or ident.args.get("quoted"):
        raise RoutineBlocked(
            "ROUTINE_IDENTIFIER_UNSUPPORTED",
            "trigger name must be a plain unquoted identifier",
        )
    properties = statement.args.get("properties")
    trigger_properties = next(
        (
            item
            for item in (properties.expressions if isinstance(properties, exp.Properties) else [])
            if isinstance(item, exp.TriggerProperties)
        ),
        None,
    )
    if trigger_properties is None:
        raise RoutineBlocked("ROUTINE_TRIGGER_UNSUPPORTED", "trigger metadata is unavailable")
    timing = str(trigger_properties.args.get("timing") or "").upper()
    if timing not in {"BEFORE", "AFTER"}:
        raise RoutineBlocked("ROUTINE_TRIGGER_UNSUPPORTED", "only BEFORE/AFTER row triggers are admitted")
    events = tuple(trigger_properties.args.get("events") or [])
    if len(events) != 1:
        raise RoutineBlocked("ROUTINE_TRIGGER_UNSUPPORTED", "triggers must declare exactly one event")
    event = str(events[0].this).upper() if isinstance(events[0], exp.TriggerEvent) else ""
    if event not in {"INSERT", "UPDATE", "DELETE"}:
        raise RoutineBlocked("ROUTINE_TRIGGER_UNSUPPORTED", "trigger event is unsupported")
    if events[0].args.get("columns"):
        raise RoutineBlocked(
            "ROUTINE_TRIGGER_UNSUPPORTED",
            "UPDATE OF column lists stay fail-closed",
        )
    if str(trigger_properties.args.get("for_each") or "").upper() != "ROW":
        raise RoutineBlocked(
            "ROUTINE_TRIGGER_UNSUPPORTED",
            "only FOR EACH ROW triggers are admitted",
        )
    if trigger_properties.args.get("when"):
        raise RoutineBlocked("ROUTINE_TRIGGER_UNSUPPORTED", "trigger WHEN clauses stay fail-closed")
    table = trigger_properties.args.get("table")
    if not isinstance(table, exp.Table) or table.args.get("db") is not None:
        raise RoutineBlocked(
            "ROUTINE_NAMESPACE_UNSUPPORTED",
            "schema-qualified trigger tables stay fail-closed",
        )
    table_ident = table.this
    if not isinstance(table_ident, exp.Identifier):
        raise RoutineBlocked("ROUTINE_IDENTIFIER_UNSUPPORTED", "trigger table is missing")
    execute = trigger_properties.args.get("execute")
    if not isinstance(execute, exp.TriggerExecute) or not isinstance(execute.this, exp.Anonymous):
        raise RoutineBlocked(
            "ROUTINE_TRIGGER_UNSUPPORTED",
            "trigger action must call one named nullary function",
        )
    function_name = str(execute.this.this)
    if execute.this.expressions:
        raise RoutineBlocked(
            "ROUTINE_TRIGGER_UNSUPPORTED",
            "trigger function arguments stay fail-closed",
        )
    return SqlTrigger(
        name=_require_identifier(str(ident.this), "trigger name"),
        timing=timing,
        event=event,
        table=_require_identifier(str(table_ident.this), "trigger table"),
        function_name=_require_identifier(function_name, "trigger routine"),
    )


def _parse_trigger_text(sql: str) -> SqlTrigger:
    match = _TEXT_TRIGGER.fullmatch(" ".join(sql.split()))
    if match is None or not match.group("fn"):
        raise RoutineBlocked(
            "ROUTINE_TRIGGER_UNSUPPORTED",
            "opaque CREATE TRIGGER did not match the named-function row-trigger subset",
        )
    return SqlTrigger(
        name=_require_identifier(match.group("name"), "trigger name"),
        timing=match.group("timing").upper(),
        event=match.group("event").upper(),
        table=_require_identifier(match.group("table"), "trigger table"),
        function_name=_require_identifier(match.group("fn"), "trigger routine"),
    )


def _retarget_expression(
    expression: exp.Expression,
    parameters: tuple[RoutineParameter, ...],
    target_dialect: str,
) -> exp.Expression:
    copied = expression.copy()
    names = {item.name.casefold(): item.name for item in parameters}
    if target_dialect == "tsql":
        for column in list(copied.find_all(exp.Column)):
            key = str(column.name).casefold()
            if key in names and column.args.get("table") is None:
                column.replace(exp.Parameter(this=exp.Var(this=names[key])))
    else:
        for parameter in list(copied.find_all(exp.Parameter)):
            variable = parameter.this
            if isinstance(variable, exp.Var):
                key = str(variable.this).casefold()
                if key in names:
                    parameter.replace(exp.column(names[key]))
    return copied


def _expression_sql(
    expression: exp.Expression,
    parameters: tuple[RoutineParameter, ...],
    target_dialect: str,
) -> str:
    retargeted = _retarget_expression(expression, parameters, target_dialect)
    rendered = retargeted.sql(dialect=target_dialect, pretty=False, unsupported_level=ErrorLevel.RAISE)
    return f"({rendered})"


def _parameter_sql(parameters: tuple[RoutineParameter, ...], dialect: str) -> str:
    parts: list[str] = []
    for item in parameters:
        prefix = "@" if dialect == "tsql" else ""
        parts.append(f"{prefix}{item.name} {_render_type(item.canonical_type, dialect)}")
    return ", ".join(parts)


def _function_obligations(function: ScalarFunction, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    obligations = [ROUTINE_SQL_FUNCTION, *extra]
    if function.stability_dropped:
        obligations.append(ROUTINE_STABILITY_DROPPED)
    return tuple(dict.fromkeys(obligations))


def _conversion(
    sql: str,
    kind: str,
    name: str,
    obligations: tuple[str, ...],
    rule_ids: tuple[str, ...],
    *,
    skip_end: bool = False,
    opaque: bool = False,
) -> RoutineConversion:
    return RoutineConversion(
        sql=sql,
        kind=kind,
        object_name=name,
        obligations=obligations,
        rule_ids=rule_ids,
        skip_following_end=skip_end,
        opaque_target=opaque,
    )


def _emit_function(function: ScalarFunction, target_dialect: str) -> RoutineConversion:
    params = _parameter_sql(function.parameters, target_dialect)
    returns = _render_type(function.return_type, target_dialect)
    value = _expression_sql(function.expression, function.parameters, target_dialect)
    if target_dialect in {"postgres", "postgresql"}:
        sql = (
            f"CREATE FUNCTION {function.name}({params}) RETURNS {returns} "
            f"LANGUAGE SQL AS $$ SELECT {value} $$"
        )
        return _conversion(sql, "FUNCTION", function.name, _function_obligations(function), (FUNCTION_RULE,))
    if target_dialect == "mysql":
        sql = f"CREATE FUNCTION {function.name}({params}) RETURNS {returns} RETURN {value}"
        return _conversion(sql, "FUNCTION", function.name, _function_obligations(function), (FUNCTION_RULE,))
    if target_dialect == "tsql":
        sql = (
            f"CREATE FUNCTION {function.name}({params}) RETURNS {returns} "
            f"AS BEGIN RETURN {value} END"
        )
        return _conversion(sql, "FUNCTION", function.name, _function_obligations(function), (FUNCTION_RULE,))
    if target_dialect == "oracle":
        sql = (
            f"CREATE FUNCTION {function.name}({params}) RETURN {returns} "
            f"IS BEGIN RETURN {value}; END;"
        )
        return _conversion(
            sql,
            "FUNCTION",
            function.name,
            _function_obligations(function),
            (FUNCTION_RULE,),
            skip_end=True,
            opaque=True,
        )
    if target_dialect == "duckdb":
        macro_params = ", ".join(item.name for item in function.parameters)
        sql = f"CREATE MACRO {function.name}({macro_params}) AS {value}"
        return _conversion(
            sql,
            "MACRO",
            function.name,
            _function_obligations(function, (ROUTINE_DUCKDB_MACRO,)),
            (FUNCTION_RULE,),
        )
    raise RoutineBlocked(
        "ROUTINE_TARGET_UNSUPPORTED",
        "SQLite has no stored-function contract; the scalar body is not silently inlined",
    )


def _dml_sql(body: exp.Expression, target_dialect: str) -> str:
    return body.sql(dialect=target_dialect, pretty=False, unsupported_level=ErrorLevel.RAISE).rstrip(";")


def _emit_procedure(procedure: SqlProcedure, target_dialect: str) -> RoutineConversion:
    body = _dml_sql(procedure.body, target_dialect)
    if target_dialect in {"postgres", "postgresql"}:
        sql = f"CREATE PROCEDURE {procedure.name}() LANGUAGE SQL AS $$ {body} $$"
        return _conversion(sql, "PROCEDURE", procedure.name, (ROUTINE_SQL_PROCEDURE,), (PROCEDURE_RULE,))
    if target_dialect == "mysql":
        sql = f"CREATE PROCEDURE {procedure.name}() BEGIN {body}; END"
        return _conversion(sql, "PROCEDURE", procedure.name, (ROUTINE_SQL_PROCEDURE,), (PROCEDURE_RULE,))
    if target_dialect == "oracle":
        sql = f"CREATE PROCEDURE {procedure.name} AS BEGIN {body}; END;"
        return _conversion(sql, "PROCEDURE", procedure.name, (ROUTINE_SQL_PROCEDURE,), (PROCEDURE_RULE,))
    if target_dialect == "tsql":
        sql = f"CREATE PROCEDURE {procedure.name} AS BEGIN {body} END"
        return _conversion(
            sql,
            "PROCEDURE",
            procedure.name,
            (ROUTINE_SQL_PROCEDURE,),
            (PROCEDURE_RULE,),
            skip_end=True,
            opaque=True,
        )
    raise RoutineBlocked(
        "ROUTINE_TARGET_UNSUPPORTED",
        "SQLite and DuckDB have no stored-procedure contract",
    )


def _emit_trigger(trigger: SqlTrigger, target_dialect: str) -> RoutineConversion:
    if target_dialect in {"postgres", "postgresql"}:
        sql = (
            f"CREATE TRIGGER {trigger.name} {trigger.timing} {trigger.event} ON {trigger.table} "
            f"FOR EACH ROW EXECUTE FUNCTION {trigger.function_name}()"
        )
        return _conversion(sql, "TRIGGER", trigger.name, (ROUTINE_ROW_TRIGGER,), (TRIGGER_RULE,))
    if target_dialect == "mysql":
        sql = (
            f"CREATE TRIGGER {trigger.name} {trigger.timing} {trigger.event} ON {trigger.table} "
            f"FOR EACH ROW BEGIN CALL {trigger.function_name}(); END"
        )
        return _conversion(
            sql, "TRIGGER", trigger.name, (ROUTINE_ROW_TRIGGER,), (TRIGGER_RULE,), skip_end=True, opaque=True
        )
    if target_dialect == "oracle":
        sql = (
            f"CREATE OR REPLACE TRIGGER {trigger.name} {trigger.timing} {trigger.event} "
            f"ON {trigger.table} FOR EACH ROW BEGIN {trigger.function_name}(); END;"
        )
        return _conversion(
            sql, "TRIGGER", trigger.name, (ROUTINE_ROW_TRIGGER,), (TRIGGER_RULE,), skip_end=True, opaque=True
        )
    if target_dialect == "tsql":
        sql = (
            f"CREATE TRIGGER {trigger.name} ON {trigger.table} {trigger.timing} {trigger.event} "
            f"AS BEGIN EXEC {trigger.function_name}; END"
        )
        return _conversion(
            sql, "TRIGGER", trigger.name, (ROUTINE_ROW_TRIGGER,), (TRIGGER_RULE,), skip_end=True, opaque=True
        )
    if target_dialect == "sqlite":
        sql = (
            f"CREATE TRIGGER {trigger.name} {trigger.timing} {trigger.event} ON {trigger.table} "
            f"BEGIN SELECT {trigger.function_name}(); END"
        )
        return _conversion(
            sql, "TRIGGER", trigger.name, (ROUTINE_ROW_TRIGGER,), (TRIGGER_RULE,), skip_end=True, opaque=True
        )
    raise RoutineBlocked(
        "ROUTINE_TARGET_UNSUPPORTED",
        "DuckDB has no trigger contract",
    )
