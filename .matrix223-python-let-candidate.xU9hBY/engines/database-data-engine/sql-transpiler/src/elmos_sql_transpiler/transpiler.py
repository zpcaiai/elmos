from __future__ import annotations

import json
from hashlib import sha256
from importlib.metadata import version
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError, TokenError, UnsupportedError

from . import placeholders
from .adapters import target_adapter_for_profile
from .models import (
    Diagnostic,
    EvidenceState,
    StatementIr,
    TranspileRequest,
    TranspileResult,
)
from .profiles import directed_route, parser_pin, profile_by_id

_MAX_SQL_BYTES = 1_048_576
_SQLGLOT_VERSION = version("sqlglot")

#: Engines whose `/` truncates when both operands are integers. The other
#: engines in this profile set return a fractional result for the same
#: expression, so `SELECT total / count` is not the same query on both sides
#: of those routes -- and it is a value difference, not a syntax error, so
#: neither the emit nor the re-parse leg can see it.
#:
#:   postgres  7 / 2 = 3        mysql   7 / 2 = 3.5000
#:   tsql      7 / 2 = 3        oracle  7 / 2 = 3.5
#:   sqlite    7 / 2 = 3        duckdb  7 / 2 = 3.5
_INTEGER_DIVISION_TRUNCATES = frozenset({"postgres", "tsql", "sqlite"})

#: How each engine folds an *unquoted* identifier. Crossing a boundary here
#: means `SELECT Foo FROM Bar` resolves to different objects on the two sides.
_IDENTIFIER_FOLDING = {
    "postgres": "lower",
    "duckdb": "lower",
    "oracle": "upper",
    "mysql": "preserve",
    "sqlite": "preserve",
    "tsql": "preserve",
}
_PARAMETER_NODE_KEYS = frozenset({"placeholder", "parameter"})
_OBLIGATION_BY_NODE = {
    "aggregate": "AGGREGATION_SEMANTICS",
    "array": "ARRAY_SEMANTICS",
    "between": "BOUNDARY_COMPARISON_SEMANTICS",
    "cast": "TYPE_CAST_SEMANTICS",
    "collate": "COLLATION_SEMANTICS",
    "div": "INTEGER_DIVISION_SEMANTICS",
    "except": "SET_DIFFERENCE_SEMANTICS",
    "group": "GROUPING_SEMANTICS",
    "intersect": "SET_INTERSECTION_SEMANTICS",
    "is": "NULL_AND_BOOLEAN_SEMANTICS",
    "join": "JOIN_CARDINALITY_SEMANTICS",
    "json_extract": "JSON_PATH_SEMANTICS",
    "limit": "PAGINATION_SEMANTICS",
    "lock": "LOCKING_SEMANTICS",
    "merge": "MERGE_CONCURRENCY_SEMANTICS",
    "offset": "PAGINATION_SEMANTICS",
    "order": "ORDERING_SEMANTICS",
    "regexp_like": "REGULAR_EXPRESSION_SEMANTICS",
    "transaction": "TRANSACTION_SEMANTICS",
    "trycast": "TYPE_CAST_ERROR_SEMANTICS",
    "union": "SET_UNION_AND_DUPLICATE_SEMANTICS",
    "window": "WINDOW_FRAME_SEMANTICS",
}


def _digest(value: str) -> str:
    return f"sha256:{sha256(value.encode('utf-8')).hexdigest()}"


def _canonical_digest(value: Any) -> str:
    return _digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _transformation_trace(
    *,
    statement_index: int,
    rule_id: str,
    action: str,
    before: exp.Expression,
    after: exp.Expression,
) -> dict[str, Any]:
    rule_version = "1.0.0"
    return {
        "statementIndex": statement_index,
        "ruleId": rule_id,
        "ruleVersion": rule_version,
        "action": action,
        "inputDigest": _canonical_digest(before.dump()),
        "outputDigest": _canonical_digest(after.dump()),
        "ruleDigest": _canonical_digest(
            {
                "ruleId": rule_id,
                "ruleVersion": rule_version,
                "action": action,
            }
        ),
    }


def _require_pinned_parser() -> None:
    """The profile catalog names an exact parser build; refuse to translate
    with a different one.

    `runner.py` already refuses to run against an unpinned duckdb/psycopg, and
    `engines/polyglot-route-engine` refuses an unpinned JDK/CPython/Node. The
    parser is the component that decides what every statement *means* here, so
    it gets the same treatment instead of being recorded after the fact in
    result metadata.
    """
    pinned = parser_pin()["version"]
    if pinned != _SQLGLOT_VERSION:
        raise RuntimeError(
            f"EXACT_PARSER_MISMATCH: profile catalog pins sqlglot {pinned}, "
            f"found {_SQLGLOT_VERSION}"
        )


def _route_semantic_warnings(
    source_dialect: str,
    target_dialect: str,
    statements: list[exp.Expression],
) -> list[Diagnostic]:
    """Value-level divergences that are legal SQL on both sides.

    Neither the emit leg nor the re-parse leg can see these: the statement is
    valid in both dialects and simply computes something different.
    """
    warnings: list[Diagnostic] = []
    truncates_source = source_dialect in _INTEGER_DIVISION_TRUNCATES
    truncates_target = target_dialect in _INTEGER_DIVISION_TRUNCATES
    if truncates_source != truncates_target and any(
        statement.find(exp.Div) is not None for statement in statements
    ):
        truncating, fractional = (
            (source_dialect, target_dialect)
            if truncates_source
            else (target_dialect, source_dialect)
        )
        warnings.append(
            Diagnostic(
                code="INTEGER_DIVISION_SEMANTICS_DIFFER",
                severity="WARNING",
                statement_index=None,
                message=(
                    f"`/` on two integers truncates in {truncating} and returns a fractional "
                    f"result in {fractional} (7 / 2 is 3 versus 3.5), and division by zero "
                    "raises in one and yields NULL in the other. Verify every division site "
                    "against the column types before relying on this translation."
                ),
            )
        )

    source_folding = _IDENTIFIER_FOLDING.get(source_dialect)
    target_folding = _IDENTIFIER_FOLDING.get(target_dialect)
    if source_folding != target_folding:
        unfolded = [
            identifier.this
            for statement in statements
            for identifier in statement.find_all(exp.Identifier)
            if not identifier.args.get("quoted")
            and (
                (source_folding == "lower" and identifier.this != identifier.this.lower())
                or (source_folding == "upper" and identifier.this != identifier.this.upper())
                or (source_folding == "preserve" and identifier.this != identifier.this.lower())
            )
        ]
        if unfolded:
            warnings.append(
                Diagnostic(
                    code="IDENTIFIER_CASE_FOLDING_DIFFERS",
                    severity="WARNING",
                    statement_index=None,
                    message=(
                        f"{source_dialect} folds unquoted identifiers to {source_folding} and "
                        f"{target_dialect} to {target_folding}; "
                        f"{sorted(set(unfolded))[:5]} resolve to different object names on the "
                        "two sides. Quote them, or confirm the target schema was created with "
                        "the same folding."
                    ),
                )
            )
    return warnings


def _validate_request(request: TranspileRequest) -> None:
    if not request.query_id or len(request.query_id) > 160:
        raise ValueError("query id is required and must be at most 160 characters")
    if not request.sql.strip():
        raise ValueError("SQL input is required")
    if len(request.sql.encode("utf-8")) > _MAX_SQL_BYTES:
        raise ValueError("SQL input exceeds the one MiB local safety limit")
    if "\x00" in request.sql:
        raise ValueError("SQL input contains a prohibited NUL byte")
    if request.source_profile == request.target_profile:
        raise ValueError("source and target SQL profiles must differ")
    profile_by_id(request.source_profile)
    profile_by_id(request.target_profile)
    names = [parameter.name for parameter in request.parameters]
    if len(names) != len(set(names)):
        raise ValueError("parameter contract names must be unique")


def _parameter_nodes(expression: exp.Expression, dialect: str) -> tuple[str, ...]:
    nodes = []
    for node in expression.walk():
        if node.key in _PARAMETER_NODE_KEYS:
            nodes.append(node.sql(dialect=dialect))
    return tuple(nodes)


def _obligations(expression: exp.Expression) -> tuple[str, ...]:
    found = {
        obligation
        for node in expression.walk()
        if (obligation := _OBLIGATION_BY_NODE.get(node.key)) is not None
    }
    if isinstance(expression, (exp.Insert, exp.Update, exp.Delete, exp.Merge)):
        found.add("DML_ROW_COUNT_AND_ERROR_CONTRACT")
    if isinstance(expression, (exp.Create, exp.Alter, exp.Drop)):
        found.add("DDL_OBJECT_AND_TRANSACTION_CONTRACT")
    if not any(node.key == "order" for node in expression.walk()) and isinstance(
        expression, exp.Query
    ):
        found.add("RESULT_ORDER_UNDEFINED")
    return tuple(sorted(found))


def _is_wildcard(projection: exp.Expression) -> bool:
    """`*` or `t.*` as a whole projection.

    Deliberately not `projection.find(exp.Star)`: `COUNT(*)` contains a Star
    node but occupies exactly one, well-determined projection position.
    """
    if isinstance(projection, exp.Star):
        return True
    return isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star)


def _projection_reference(
    projections: list[exp.Expression],
    literal: exp.Expression,
    *,
    prefer_alias: bool,
) -> exp.Expression:
    if not isinstance(literal, exp.Literal) or not literal.is_int:
        return literal
    if any(_is_wildcard(projection) for projection in projections):
        # `SELECT * ... ORDER BY 1` cannot be resolved without the table's
        # column list: position 1 is whatever `*` expands to first, and any
        # position after a `*` shifts by the table's width. The pre-fix code
        # substituted the projection node itself and emitted `ORDER BY *` /
        # `GROUP BY *`, which sqlglot re-parses happily and every real server
        # rejects.
        raise UnsupportedError(
            "a positional GROUP BY/ORDER BY reference cannot be resolved against a "
            "wildcard projection without the table's column list"
        )
    position = int(literal.this)
    if position < 1 or position > len(projections):
        return literal
    projection = projections[position - 1]
    if prefer_alias and projection.alias:
        return exp.column(projection.alias)
    if isinstance(projection, exp.Alias):
        underlying = projection.this
        if isinstance(underlying, exp.Expression):
            return underlying.copy()
    return projection.copy()


def _normalize_positional_references(
    expression: exp.Expression,
) -> tuple[exp.Expression, bool]:
    normalized = expression.copy()
    changed = False
    for select in normalized.find_all(exp.Select):
        projections = list(select.expressions)
        group = select.args.get("group")
        if isinstance(group, exp.Group):
            replacements = [
                _projection_reference(projections, item, prefer_alias=False)
                for item in group.expressions
            ]
            if any(
                before is not after
                for before, after in zip(group.expressions, replacements, strict=True)
            ):
                group.set("expressions", replacements)
                changed = True
        order = select.args.get("order")
        if isinstance(order, exp.Order):
            for ordered in order.expressions:
                replacement = _projection_reference(
                    projections,
                    ordered.this,
                    prefer_alias=True,
                )
                if replacement is not ordered.this:
                    ordered.set("this", replacement)
                    changed = True
    return normalized, changed


def _blocked_result(
    request: TranspileRequest,
    *,
    diagnostic: Diagnostic,
    syntax_parse: EvidenceState,
    target_emit: EvidenceState,
    target_reparse: EvidenceState,
) -> TranspileResult:
    source = profile_by_id(request.source_profile)
    target = profile_by_id(request.target_profile)
    return TranspileResult(
        schema_version="1.0",
        query_id=request.query_id,
        source_profile=source,
        target_profile=target,
        route=directed_route(source.id, target.id),
        state="BLOCKED",
        source_digest=_digest(request.sql),
        target_digest=None,
        target_sql=None,
        statements=(),
        diagnostics=(diagnostic,),
        syntax_parse=syntax_parse,
        target_emit=target_emit,
        target_reparse=target_reparse,
        parameter_contract="FAILED",
        metadata={
            "parser": "sqlglot",
            "parserVersion": _SQLGLOT_VERSION,
            "rawSourceSqlPersisted": False,
            "sourceAstPersisted": False,
            "silentFallbackUsed": False,
        },
    )


def transpile(request: TranspileRequest) -> TranspileResult:
    _require_pinned_parser()
    _validate_request(request)
    source = profile_by_id(request.source_profile)
    target = profile_by_id(request.target_profile)
    route = directed_route(source.id, target.id)
    source_digest = _digest(request.sql)
    target_adapter = target_adapter_for_profile(target.id)
    if (
        target_adapter.target_profile_id != target.id
        or target_adapter.target_dialect != target.dialect
    ):
        raise RuntimeError("target adapter registration does not match the exact target profile")

    try:
        parsed_source_statements = sqlglot.parse(
            request.sql,
            read=source.dialect,
            error_level=ErrorLevel.RAISE,
        )
    except (ParseError, TokenError):
        return _blocked_result(
            request,
            diagnostic=Diagnostic(
                code="SOURCE_PARSE_FAILED",
                severity="ERROR",
                statement_index=None,
                message="The exact source dialect parser rejected the SQL.",
            ),
            syntax_parse="FAILED",
            target_emit="NOT_RUN",
            target_reparse="NOT_RUN",
        )

    if not parsed_source_statements or any(
        statement is None for statement in parsed_source_statements
    ):
        return _blocked_result(
            request,
            diagnostic=Diagnostic(
                code="SOURCE_EMPTY_AST",
                severity="ERROR",
                statement_index=None,
                message="The parser produced no typed statements.",
            ),
            syntax_parse="FAILED",
            target_emit="NOT_RUN",
            target_reparse="NOT_RUN",
        )
    source_statements = [
        statement for statement in parsed_source_statements if isinstance(statement, exp.Expression)
    ]

    target_sql_parts: list[str] = []
    statement_irs: list[StatementIr] = []
    diagnostics: list[Diagnostic] = []
    rule_trace: list[dict[str, Any]] = []
    try:
        for index, source_statement in enumerate(source_statements):
            if isinstance(source_statement, exp.Command):
                raise UnsupportedError("opaque command nodes are prohibited")
            parameter_nodes_before = _parameter_nodes(source_statement, source.dialect)
            canonical_statement, positional_rewrite = _normalize_positional_references(
                source_statement
            )
            if positional_rewrite:
                rule_trace.append(
                    _transformation_trace(
                        statement_index=index,
                        rule_id="core.normalize-positional-reference",
                        action="NORMALIZE_TYPED_AST",
                        before=source_statement,
                        after=canonical_statement,
                    )
                )
            before_placeholder_rewrite = canonical_statement
            canonical_statement, placeholder_mapping = placeholders.rewrite(
                before_placeholder_rewrite, source.dialect, target.dialect
            )
            if placeholder_mapping:
                rule_trace.append(
                    _transformation_trace(
                        statement_index=index,
                        rule_id="core.rewrite-parameter-binding",
                        action="REWRITE_TYPED_PARAMETER_NODES",
                        before=before_placeholder_rewrite,
                        after=canonical_statement,
                    )
                )
            emission = target_adapter.emit(canonical_statement)
            if (
                emission.adapter_id != target_adapter.adapter_id
                or emission.adapter_digest != target_adapter.adapter_digest
                or emission.protocol_version != target_adapter.protocol_version
            ):
                raise RuntimeError("target adapter returned an inconsistent emission identity")
            generated = emission.sql
            rule_trace.extend(
                {"statementIndex": index, **trace.to_dict()} for trace in emission.rules
            )
            parsed_target_statements = sqlglot.parse(
                generated,
                read=target.dialect,
                error_level=ErrorLevel.RAISE,
            )
            target_statements = [
                statement
                for statement in parsed_target_statements
                if isinstance(statement, exp.Expression)
            ]
            if (
                len(target_statements) != 1
                or len(target_statements) != len(parsed_target_statements)
                or isinstance(target_statements[0], exp.Command)
            ):
                raise UnsupportedError("target did not reparse to exactly one typed statement")
            target_statement = target_statements[0]
            placeholders.verify_tokens(target_statement, target.dialect)
            parameter_nodes_after = _parameter_nodes(target_statement, target.dialect)
            if len(parameter_nodes_before) != len(parameter_nodes_after):
                raise UnsupportedError("parameter node cardinality changed")
            obligations = set(_obligations(source_statement))
            if positional_rewrite:
                obligations.add("POSITIONAL_REFERENCE_NORMALIZED")
            if placeholder_mapping:
                obligations.add("PARAMETER_BINDING_REWRITTEN")
            statement_irs.append(
                StatementIr(
                    index=index,
                    kind=source_statement.key.upper(),
                    source_ast=source_statement.dump(),
                    target_ast=target_statement.dump(),
                    obligations=tuple(sorted(obligations)),
                    parameter_nodes_before=parameter_nodes_before,
                    parameter_nodes_after=parameter_nodes_after,
                )
            )
            target_sql_parts.append(generated.rstrip(";"))
    except (ParseError, TokenError, UnsupportedError) as error:
        code = (
            "TARGET_REPARSE_FAILED"
            if isinstance(error, (ParseError, TokenError))
            else "UNSUPPORTED_SEMANTICS"
        )
        return _blocked_result(
            request,
            diagnostic=Diagnostic(
                code=code,
                severity="ERROR",
                statement_index=len(statement_irs),
                message=(
                    "Target SQL failed exact-dialect reparsing."
                    if code == "TARGET_REPARSE_FAILED"
                    else "The parser reported unsupported or opaque semantics."
                ),
            ),
            syntax_parse="PASSED",
            target_emit="FAILED",
            target_reparse="FAILED" if code == "TARGET_REPARSE_FAILED" else "NOT_RUN",
        )

    target_sql = ";\n\n".join(target_sql_parts) + ";\n"
    all_obligations = sorted(
        {item for statement in statement_irs for item in statement.obligations}
    )
    if request.parameters:
        observed_count = sum(len(item.parameter_nodes_before) for item in statement_irs)
        if observed_count == 0:
            return _blocked_result(
                request,
                diagnostic=Diagnostic(
                    code="PARAMETER_CONTRACT_NOT_OBSERVED",
                    severity="ERROR",
                    statement_index=None,
                    message=(
                        "A parameter contract was supplied but no typed parameter node was parsed."
                    ),
                ),
                syntax_parse="PASSED",
                target_emit="PASSED",
                target_reparse="PASSED",
            )
    diagnostics.extend(
        _route_semantic_warnings(source.dialect, target.dialect, source_statements)
    )
    if "RESULT_ORDER_UNDEFINED" in all_obligations:
        diagnostics.append(
            Diagnostic(
                code="RESULT_ORDER_UNDEFINED",
                severity="WARNING",
                statement_index=None,
                message=(
                    "At least one query has no explicit ordering; "
                    "sequence equivalence cannot be claimed."
                ),
            )
        )
    diagnostics.append(
        Diagnostic(
            code="RUNTIME_EQUIVALENCE_NOT_RUN",
            severity="INFO",
            statement_index=None,
            message=(
                "Syntax transpilation passed; source/target execution "
                "and result equivalence remain NOT_RUN."
            ),
        )
    )
    return TranspileResult(
        schema_version="1.0",
        query_id=request.query_id,
        source_profile=source,
        target_profile=target,
        route=route,
        state="SYNTAX_READY",
        source_digest=source_digest,
        target_digest=_digest(target_sql),
        target_sql=target_sql,
        statements=tuple(statement_irs),
        diagnostics=tuple(diagnostics),
        syntax_parse="PASSED",
        target_emit="PASSED",
        target_reparse="PASSED",
        parameter_contract="PASSED",
        metadata={
            "parser": "sqlglot",
            "parserVersion": _SQLGLOT_VERSION,
            "statementCount": len(statement_irs),
            "semanticObligations": all_obligations,
            "targetAdapter": {
                "adapterId": target_adapter.adapter_id,
                "adapterVersion": target_adapter.adapter_version,
                "protocolVersion": target_adapter.protocol_version,
                "targetProfileId": target_adapter.target_profile_id,
                "targetDialect": target_adapter.target_dialect,
                "adapterDigest": target_adapter.adapter_digest,
            },
            "ruleTrace": rule_trace,
            "ruleTraceDigest": _canonical_digest(rule_trace),
            "rawSourceSqlPersisted": False,
            "sourceAstPersisted": True,
            "silentFallbackUsed": False,
        },
    )
