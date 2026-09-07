"""Re-appliable patch set for the 2026-08-25 fix pass.

Every replacement asserts an exact match count first, so a silent no-op is
impossible if the upstream file has moved (this repository has concurrent
sessions writing to it -- a `str.replace` that matches nothing looks like
success).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()


def patch(relative: str, old: str, new: str, *, expect: int = 1) -> None:
    path = ROOT / relative
    src = path.read_text(encoding="utf-8")
    found = src.count(old)
    if found != expect:
        raise SystemExit(f"ABORT {relative}: expected {expect} match(es), found {found}")
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  patched {relative}")


PG = "engines/polyglot-route-engine/src/elmos_polyglot_route"
TR = "engines/database-data-engine/sql-transpiler/src/elmos_sql_transpiler"

# =============================================================================
# FIX 1 -- sql-transpiler: unexpected emission faults must fail closed
# =============================================================================
print("FIX 1  target emission fail-closed backstop")
patch(
    f"{TR}/transpiler.py",
    '''            syntax_parse="PASSED",
            target_emit="FAILED",
            target_reparse="FAILED" if code == "TARGET_REPARSE_FAILED" else "NOT_RUN",
        )
''',
    '''            syntax_parse="PASSED",
            target_emit="FAILED",
            target_reparse="FAILED" if code == "TARGET_REPARSE_FAILED" else "NOT_RUN",
        )
    except RuntimeError:
        # Adapter-identity integrity violations are not subset boundaries. They
        # mean the registry and the emission disagree about who produced the SQL,
        # so they must stay loud instead of being laundered into a BLOCKED result.
        raise
    except Exception as error:  # noqa: BLE001 - deliberate fail-closed backstop
        # Anything else escaping emission or reparse is a DEFECT, in this path or
        # in the pinned parser. Batch 31 requires target emission to fail closed,
        # so it is reported as a blocked result with its own code rather than
        # propagating a raw exception to the caller -- and with a code distinct
        # from UNSUPPORTED_SEMANTICS, so a defect can never be counted as a
        # declared boundary.
        #
        # Real instance this guards: an aggregate FILTER combined with an explicit
        # window frame reaches sqlglot's `ordered_sql`, which calls `sql_name()` on
        # a `Filter` node that does not have it. Reproduced in bare sqlglot at both
        # 30.13.0 and 30.14.0, so pinning forward does not remove the need for this.
        #
        # Only the exception TYPE is recorded: a message could carry fragments of
        # the customer's SQL, and `rawSourceSqlPersisted` is false by contract.
        return _blocked_result(
            request,
            diagnostic=Diagnostic(
                code="TARGET_EMISSION_FAULTED",
                severity="ERROR",
                statement_index=len(statement_irs),
                message=(
                    f"Target emission raised an unexpected {type(error).__name__} and was "
                    "failed closed. This is a defect in the emission path or its pinned "
                    "parser, not a declared subset boundary; please report it."
                ),
            ),
            syntax_parse="PASSED",
            target_emit="FAILED",
            target_reparse="NOT_RUN",
        )
''',
)

patch(
    f"{TR}/commercial.py",
    '''    except (ParseError, TokenError):
        return _result(
            request,
            target,
            route_id=route_id,
            statements=(),
            blockers=(
                CommercialBlocker(
                    code="SOURCE_PARSE_FAILED",
                    severity="ERROR",
                    statement_index=None,
                    message="The exact source profile parser rejected the SQL.",
                ),
            ),
            source_parse="FAILED",
        )
''',
    '''    except (ParseError, TokenError):
        return _result(
            request,
            target,
            route_id=route_id,
            statements=(),
            blockers=(
                CommercialBlocker(
                    code="SOURCE_PARSE_FAILED",
                    severity="ERROR",
                    statement_index=None,
                    message="The exact source profile parser rejected the SQL.",
                ),
            ),
            source_parse="FAILED",
        )
    except Exception as error:  # noqa: BLE001 - deliberate fail-closed backstop
        # Same discipline as transpiler.transpile: anything the pinned parser
        # raises that is not a declared parse rejection is a DEFECT, and it gets
        # its own code so it can never be counted as a source-side boundary.
        # Only the exception type is recorded -- a message could carry fragments
        # of the customer's SQL.
        return _result(
            request,
            target,
            route_id=route_id,
            statements=(),
            blockers=(
                CommercialBlocker(
                    code="SOURCE_PARSE_FAULTED",
                    severity="ERROR",
                    statement_index=None,
                    message=(
                        f"The exact source profile parser raised an unexpected "
                        f"{type(error).__name__} and was failed closed. This is a defect, "
                        "not a declared boundary; please report it."
                    ),
                ),
            ),
            source_parse="FAILED",
        )
''',
)

# =============================================================================
# FIX 2 -- polyglot frontend: a docstring must not reject the function
# =============================================================================
print("FIX 2  Python docstrings enter the bounded subset as provenance")
patch(
    f"{PG}/models.py",
    '''class Function:
    name: str
    parameters: tuple[Parameter, ...]
    return_type: str
    body: tuple[Statement, ...]
    source_span: SourceSpan | None = None
''',
    '''class Function:
    name: str
    parameters: tuple[Parameter, ...]
    return_type: str
    body: tuple[Statement, ...]
    source_span: SourceSpan | None = None
    #: Source-language documentation attached to the declaration (a Python
    #: docstring; the equivalent in other frontends can follow).
    #:
    #: This is PROVENANCE, not semantics, and the distinction is load-bearing:
    #: it appears in `to_mapping` -- so nothing the source carried is silently
    #: dropped and the artifact digest reflects it -- and NOT in
    #: `semantic_mapping`, so source/target equivalence is never asked to
    #: compare a Python `__doc__` against a Java method that has no such
    #: concept. Functions without documentation serialize byte-identically to
    #: before this field existed, so previously recorded IR digests still hold.
    documentation: str | None = None
''',
)

patch(
    f"{PG}/models.py",
    '''        _require_exact_keys(
            value,
            frozenset({"name", "parameters", "return_type", "body"}),
            frozenset({"source_span"}),
            _path,
        )
        name = _require_string(value["name"], f"{_path}.name", nonempty=True)
        return_type = _require_string(value["return_type"], f"{_path}.return_type")''',
    '''        _require_exact_keys(
            value,
            frozenset({"name", "parameters", "return_type", "body"}),
            frozenset({"source_span", "documentation"}),
            _path,
        )
        name = _require_string(value["name"], f"{_path}.name", nonempty=True)
        return_type = _require_string(value["return_type"], f"{_path}.return_type")
        documentation = (
            # An empty docstring is legal Python and stays distinguishable from
            # "no docstring at all", so `nonempty` is deliberately not required.
            _require_string(value["documentation"], f"{_path}.documentation")
            if "documentation" in value
            else None
        )''',
)

patch(
    f"{PG}/models.py",
    '''            body=tuple(Statement.from_mapping(item, _path=f"{_path}.body[{index}]") for index, item in enumerate(body)),
            source_span=_optional_source_span(value, _path),
        )''',
    '''            body=tuple(Statement.from_mapping(item, _path=f"{_path}.body[{index}]") for index, item in enumerate(body)),
            source_span=_optional_source_span(value, _path),
            documentation=documentation,
        )''',
)

patch(
    f"{PG}/models.py",
    '''    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "parameters": [parameter.to_mapping() for parameter in self.parameters],
            "return_type": self.return_type,
            "body": [statement.to_mapping() for statement in self.body],
        }
        if self.source_span is not None:
            result["source_span"] = self.source_span.to_mapping()
        return result''',
    '''    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "parameters": [parameter.to_mapping() for parameter in self.parameters],
            "return_type": self.return_type,
            "body": [statement.to_mapping() for statement in self.body],
        }
        if self.source_span is not None:
            result["source_span"] = self.source_span.to_mapping()
        if self.documentation is not None:
            result["documentation"] = self.documentation
        return result''',
)

patch(
    f"{PG}/python_analyzer.py",
    "def analyze_python(path: Path, function_name: str, *, emitted_target: bool = False) -> SemanticIR:",
    '''def _split_leading_docstring(nodes: list[ast.stmt]) -> tuple[list[ast.stmt], str | None]:
    """Separate a leading docstring from the statements that follow it.

    A docstring is a bare string expression, so before this it hit the generic
    `PYTHON_UNSUPPORTED_STATEMENT:Expr` rejection and took the whole function
    with it. Measured on 20 real PyPI projects, 94 of the 109 functions whose
    signature was already fully inside the profile died on exactly this -- the
    single largest avoidable rejection in the frontend.

    Only the FIRST statement qualifies. A bare string anywhere else is a no-op
    expression, not documentation, and keeping it rejected is correct.

    The text is not discarded: `analyze_python` carries it into the IR as
    `Function.documentation` (provenance, not semantics), so the conversion
    never silently loses something the source declared.
    """

    if not nodes:
        return nodes, None
    first = nodes[0]
    if not (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return nodes, None
    remaining = nodes[1:]
    if not remaining:
        # A function whose entire body is its docstring has no behaviour to
        # convert. Fail closed with its own code rather than falling through to
        # a confusing empty-body error.
        raise RouteError("PYTHON_FUNCTION_BODY_IS_ONLY_DOCUMENTATION")
    return remaining, first.value.value


def analyze_python(path: Path, function_name: str, *, emitted_target: bool = False) -> SemanticIR:''',
)

patch(
    f"{PG}/python_analyzer.py",
    '''    body = _emitted_body(candidate.body, parameters) if emitted_target else candidate.body
    semantic = SemanticIR.from_mapping(
        {''',
    '''    documentation: str | None = None
    if emitted_target:
        # Deliberately NOT applied to the emitted-target re-analysis. This
        # engine's emitters never produce a docstring, so one appearing there
        # means the target did not come from them -- and the re-analysis gate
        # exists to catch exactly that. Accepting it would weaken the gate.
        body = _emitted_body(candidate.body, parameters)
    else:
        body, documentation = _split_leading_docstring(candidate.body)
    function_mapping: dict[str, Any] = {
        "name": candidate.name,
        "parameters": parameters,
        "return_type": return_type,
        "body": _statements(body, emitted_target=emitted_target),
    }
    if documentation is not None:
        function_mapping["documentation"] = documentation
    semantic = SemanticIR.from_mapping(
        {''',
)

patch(
    f"{PG}/python_analyzer.py",
    '''            "functions": [
                {
                    "name": candidate.name,
                    "parameters": parameters,
                    "return_type": return_type,
                    "body": _statements(body, emitted_target=emitted_target),
                }
            ],''',
    '''            "functions": [function_mapping],''',
)

print("all patches applied cleanly")


SQ = "engines/sql-dialect-engine/src/elmos_sql_dialect"

# =============================================================================
# FIX 3 -- certified-ddl-v1 accepts IF NOT EXISTS, and refuses to drop it
# =============================================================================
print("FIX 3  IF NOT EXISTS enters certified-ddl-v1 with per-dialect fail-close")

patch(
    f"{SQ}/models.py",
    '''class Table:
    name: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...] = ()
    unique_constraints: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    foreign_keys: tuple[ForeignKey, ...] = ()
    check_constraints: tuple[CheckConstraint, ...] = ()
''',
    '''class Table:
    name: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...] = ()
    unique_constraints: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    foreign_keys: tuple[ForeignKey, ...] = ()
    check_constraints: tuple[CheckConstraint, ...] = ()
    #: `CREATE TABLE IF NOT EXISTS`. Part of the model rather than dropped at
    #: the door, because it is not decoration: it decides whether re-running a
    #: migration is a no-op or an error. Not every target can express it, and
    #: `emitter` fails closed rather than emitting a statement with different
    #: rerun behaviour than the source had.
    if_not_exists: bool = False
''',
)

patch(
    f"{SQ}/models.py",
    '''class Index:
    name: str
    table: str
    columns: tuple[str, ...]
    unique: bool = False
''',
    '''class Index:
    name: str
    table: str
    columns: tuple[str, ...]
    unique: bool = False
    #: `CREATE INDEX IF NOT EXISTS`. Narrower than the table form -- MySQL has
    #: no such spelling for indexes even though it has one for tables.
    if_not_exists: bool = False
''',
)

patch(
    f"{SQ}/parser.py",
    '''    for flag in ("replace", "exists", "unique", "concurrently"):
        _require(not statement.args.get(flag), "CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER",
                  f"CREATE TABLE modifier {flag!r} is outside certified-ddl-v1")
''',
    '''    for flag in ("replace", "unique", "concurrently"):
        _require(not statement.args.get(flag), "CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER",
                  f"CREATE TABLE modifier {flag!r} is outside certified-ddl-v1")
    # `exists` (IF NOT EXISTS) is admitted and carried in the model instead of
    # being refused at the door. Measured on 89 real .sql files it was 54 of
    # the blocked statements across only 4 distinct reasons -- the densest
    # blocker in the profile that is a spelling rather than a semantic gap.
    # Whether it survives translation is the TARGET's question, decided in
    # `emitter`, because the answer differs per dialect.
    if_not_exists = bool(statement.args.get("exists"))
''',
)

patch(
    f"{SQ}/parser.py",
    '''    for flag in ("replace", "exists", "concurrently"):
        _require(not statement.args.get(flag), "CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER",
                  f"CREATE INDEX modifier {flag!r} is outside certified-ddl-v1")
''',
    '''    for flag in ("replace", "concurrently"):
        _require(not statement.args.get(flag), "CERTIFIED_DDL_UNSUPPORTED_STATEMENT_MODIFIER",
                  f"CREATE INDEX modifier {flag!r} is outside certified-ddl-v1")
    index_if_not_exists = bool(statement.args.get("exists"))
''',
)

patch(
    f"{SQ}/parser.py",
    '''    return Index(name=index_name, table=table_name, columns=columns, unique=bool(statement.args.get("unique")))''',
    '''    return Index(
        name=index_name,
        table=table_name,
        columns=columns,
        unique=bool(statement.args.get("unique")),
        if_not_exists=index_if_not_exists,
    )''',
)

patch(
    f"{SQ}/emitter.py",
    '''def emit_create_table(table: Table, dialect: Dialect) -> str:
    if dialect is Dialect.MYSQL:
        _require_mysql_auto_increment_key(table)''',
    '''#: Which targets can express `IF NOT EXISTS`, per statement kind.
#:
#: The two maps differ, and that asymmetry is the whole reason this is a table
#: rather than one boolean: MySQL has `CREATE TABLE IF NOT EXISTS` but has no
#: `CREATE INDEX IF NOT EXISTS` at all.
#:
#: Oracle is refused for both. Oracle only grew the syntax in 23ai, and
#: `Dialect` carries no version, so the engine cannot tell a 23ai target from
#: a 19c one. Refusing is the same discipline the rest of this repository
#: applies to unpinned versions: an exact tuple or nothing.
#:
#: SQL Server is refused for both -- it has `DROP ... IF EXISTS` but no
#: `CREATE ... IF NOT EXISTS` in any shipping version. The usual workaround
#: (`IF NOT EXISTS (SELECT ... FROM sys.tables) BEGIN ... END`) is a different
#: statement with different transactional and permission behaviour, so
#: synthesising one here would be this engine inventing semantics rather than
#: translating them.
_IF_NOT_EXISTS_TABLE_SUPPORT: frozenset[Dialect] = frozenset({Dialect.POSTGRES, Dialect.MYSQL})
_IF_NOT_EXISTS_INDEX_SUPPORT: frozenset[Dialect] = frozenset({Dialect.POSTGRES})


def _if_not_exists_clause(
    requested: bool,
    dialect: Dialect,
    *,
    object_kind: str,
    object_name: str,
    supported: frozenset[Dialect],
) -> str:
    """Render ` IF NOT EXISTS`, or fail closed when the target cannot say it.

    Dropping the modifier would compile and would look like a success, and the
    difference only shows up the second time the migration runs: the source
    statement is a no-op, the emitted one is an error. That is a behaviour
    change, so it fails closed like every other one in this profile.
    """

    if not requested:
        return ""
    if dialect in supported:
        return " IF NOT EXISTS"
    raise DialectError(
        "CERTIFIED_DDL_IF_NOT_EXISTS_UNSUPPORTED_BY_TARGET",
        f"the source declares CREATE {object_kind} IF NOT EXISTS for {object_name!r}, and "
        f"{dialect.value} has no equivalent spelling. Emitting it without the modifier would "
        "change what a re-run does -- a no-op in the source, an error in the target -- so the "
        "translation fails closed instead. Remove the modifier at the source, or guard the "
        "statement outside the DDL.",
    )


def emit_create_table(table: Table, dialect: Dialect) -> str:
    if dialect is Dialect.MYSQL:
        _require_mysql_auto_increment_key(table)
    existence = _if_not_exists_clause(
        table.if_not_exists,
        dialect,
        object_kind="TABLE",
        object_name=table.name,
        supported=_IF_NOT_EXISTS_TABLE_SUPPORT,
    )''',
)

patch(
    f"{SQ}/emitter.py",
    '''    body = ",\\n    ".join(lines)
    return f"CREATE TABLE {table.name} (\\n    {body}\\n)"''',
    '''    body = ",\\n    ".join(lines)
    return f"CREATE TABLE{existence} {table.name} (\\n    {body}\\n)"''',
)

patch(
    f"{SQ}/emitter.py",
    '''def emit_create_index(index: Index, dialect: Dialect) -> str:
    keyword = "CREATE UNIQUE INDEX" if index.unique else "CREATE INDEX"
    return f"{keyword} {index.name} ON {index.table} ({', '.join(index.columns)})"''',
    '''def emit_create_index(index: Index, dialect: Dialect) -> str:
    keyword = "CREATE UNIQUE INDEX" if index.unique else "CREATE INDEX"
    existence = _if_not_exists_clause(
        index.if_not_exists,
        dialect,
        object_kind="INDEX",
        object_name=index.name,
        supported=_IF_NOT_EXISTS_INDEX_SUPPORT,
    )
    return f"{keyword}{existence} {index.name} ON {index.table} ({', '.join(index.columns)})"''',
)

print("FIX 3 applied")

patch(
    f"{SQ}/parser.py",
    '''    return Table(name=table_name, columns=tuple(columns), primary_key=tuple(primary_key),
                 unique_constraints=tuple(unique_constraints), foreign_keys=tuple(foreign_keys),
                 check_constraints=tuple(check_constraints))''',
    '''    return Table(name=table_name, columns=tuple(columns), primary_key=tuple(primary_key),
                 unique_constraints=tuple(unique_constraints), foreign_keys=tuple(foreign_keys),
                 check_constraints=tuple(check_constraints), if_not_exists=if_not_exists)''',
)

print("FIX 3 model wiring applied")


# =============================================================================
# FIX 4 -- certified-ddl-v1 CHECK admits IS NULL / IN / BETWEEN
# =============================================================================
# Measured: CERTIFIED_DDL_UNSUPPORTED_CHECK is 458 blocked constraints across
# only 6 distinct reasons, and three of them are 429 of the 458:
#
#     376x  Is         (IS NULL / IS NOT NULL)
#      49x  In         (IN (literal, ...))
#       4x  Between    (BETWEEN literal AND literal)
#
# The profile's stated reason for being narrow is "no function calls, no
# subqueries, since function names are exactly where dialects diverge most".
# These three are OPERATORS, not function calls: SQL-92 core, rendered with the
# same spelling and the same meaning by PostgreSQL, MySQL, Oracle and SQL
# Server. Admitting them is consistent with that rationale rather than an
# exception to it.
#
# Deliberately still refused, and each for a real divergence:
#   RegexpLike (21x)  `~` / REGEXP / REGEXP_LIKE / nothing at all in T-SQL
#   Like        (2x)  MySQL's default collation is case-insensitive, so the
#                     same predicate accepts different rows
#   IS TRUE           parses as `Is` too, but Oracle has no boolean IS
#   BETWEEN SYMMETRIC PostgreSQL-only
#   NOT IN            not present in the measured corpus; left out rather than
#                     shipped untested
print("FIX 4  CHECK admits IS NULL / IN / BETWEEN")

patch(
    f"{SQ}/models.py",
    '''class CheckOperator(str, Enum):
    EQ = "="
    NE = "<>"
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
''',
    '''class CheckOperator(str, Enum):
    EQ = "="
    NE = "<>"
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    # Null tests and set/range membership. Every one of the four certified
    # dialects spells these identically and means the same thing by them,
    # which is why they need no per-dialect rendering while LIKE and regex
    # (which do diverge) stay out.
    IS_NULL = "IS NULL"
    IS_NOT_NULL = "IS NOT NULL"
    IN = "IN"
    BETWEEN = "BETWEEN"


#: Operators whose right-hand side is a single literal. The rest carry either
#: no operand (the null tests) or several (`IN`, `BETWEEN`), which is why
#: `CheckComparison` has both `literal` and `literals`.
BINARY_CHECK_OPERATORS: frozenset[CheckOperator] = frozenset(
    {
        CheckOperator.EQ,
        CheckOperator.NE,
        CheckOperator.LT,
        CheckOperator.LE,
        CheckOperator.GT,
        CheckOperator.GE,
    }
)
NULLARY_CHECK_OPERATORS: frozenset[CheckOperator] = frozenset(
    {CheckOperator.IS_NULL, CheckOperator.IS_NOT_NULL}
)


@dataclass(frozen=True)
class CheckLiteral:
    """One literal operand, carrying whether it needs quoting on emission."""

    value: str
    is_string: bool = False
''',
)

patch(
    f"{SQ}/models.py",
    '''    column: str
    operator: CheckOperator
    literal: str
    literal_is_string: bool = False
''',
    '''    column: str
    operator: CheckOperator
    #: Right-hand side for the binary operators. Empty for the null tests and
    #: unused by `IN` / `BETWEEN`, which use `literals` instead.
    literal: str = ""
    literal_is_string: bool = False
    #: Operands for `IN` (one or more) and `BETWEEN` (exactly two, low then
    #: high). Empty for every other operator.
    literals: tuple[CheckLiteral, ...] = ()

    def __post_init__(self) -> None:
        if self.operator in NULLARY_CHECK_OPERATORS:
            if self.literal or self.literals:
                raise DialectError(
                    "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                    f"{self.operator.value} takes no operand",
                )
        elif self.operator is CheckOperator.IN:
            if not self.literals:
                raise DialectError(
                    "CERTIFIED_DDL_UNSUPPORTED_CHECK", "IN requires at least one literal"
                )
        elif self.operator is CheckOperator.BETWEEN:
            if len(self.literals) != 2:
                raise DialectError(
                    "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                    "BETWEEN requires exactly two literals (low, high)",
                )
        elif not self.literal and not self.literal_is_string:
            raise DialectError(
                "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                f"{self.operator.value} requires a right-hand literal",
            )
''',
)

patch(
    f"{SQ}/parser.py",
    '''def _parse_check_comparison(node: exp.Expression) -> CheckComparison:
    operator = _CHECK_OPERATOR_MAP.get(type(node))
    _require(operator is not None, "CERTIFIED_DDL_UNSUPPORTED_CHECK",
              f"CHECK comparison operator {type(node).__name__} is outside certified-ddl-v1")
    assert operator is not None  # narrows for mypy; _require already enforced this at runtime
    column = _plain_identifier(node.this, "CHECK left-hand column")
    literal = node.expression
    _require(isinstance(literal, exp.Literal), "CERTIFIED_DDL_UNSUPPORTED_CHECK",
              "CHECK right-hand side must be a plain literal")
    return CheckComparison(column=column, operator=operator, literal=str(literal.this),
                            literal_is_string=bool(literal.is_string))''',
    '''def _check_literal(node: exp.Expression | None, what: str) -> CheckLiteral:
    _require(isinstance(node, exp.Literal), "CERTIFIED_DDL_UNSUPPORTED_CHECK",
              f"{what} must be a plain literal")
    assert isinstance(node, exp.Literal)  # narrows for mypy
    return CheckLiteral(value=str(node.this), is_string=bool(node.is_string))


def _parse_check_comparison(node: exp.Expression) -> CheckComparison:
    # --- null tests -------------------------------------------------------
    # `IS NULL` and `IS NOT NULL` are the same sqlglot node, told apart by a
    # `negate` flag. `IS TRUE` is also an `Is`, and is refused: Oracle has no
    # boolean type and no `IS TRUE`.
    if isinstance(node, exp.Is):
        _require(isinstance(node.expression, exp.Null), "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                  "certified-ddl-v1 supports IS [NOT] NULL only; IS TRUE/FALSE has no Oracle equivalent")
        column = _plain_identifier(node.this, "CHECK left-hand column")
        operator = CheckOperator.IS_NOT_NULL if node.args.get("negate") else CheckOperator.IS_NULL
        return CheckComparison(column=column, operator=operator)

    # --- set membership ---------------------------------------------------
    if isinstance(node, exp.In):
        _require(not node.args.get("query"), "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                  "CHECK IN (subquery) is outside certified-ddl-v1")
        column = _plain_identifier(node.this, "CHECK left-hand column")
        members = node.args.get("expressions") or []
        _require(bool(members), "CERTIFIED_DDL_UNSUPPORTED_CHECK", "CHECK IN requires a literal list")
        return CheckComparison(
            column=column,
            operator=CheckOperator.IN,
            literals=tuple(_check_literal(m, "CHECK IN member") for m in members),
        )

    # --- range membership -------------------------------------------------
    # `BETWEEN SYMMETRIC` is PostgreSQL-only, so it is refused rather than
    # normalised away.
    if isinstance(node, exp.Between):
        _require(not node.args.get("symmetric"), "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                  "BETWEEN SYMMETRIC is PostgreSQL-only and outside certified-ddl-v1")
        column = _plain_identifier(node.this, "CHECK left-hand column")
        return CheckComparison(
            column=column,
            operator=CheckOperator.BETWEEN,
            literals=(
                _check_literal(node.args.get("low"), "CHECK BETWEEN lower bound"),
                _check_literal(node.args.get("high"), "CHECK BETWEEN upper bound"),
            ),
        )

    # --- binary comparisons ----------------------------------------------
    operator = _CHECK_OPERATOR_MAP.get(type(node))
    _require(operator is not None, "CERTIFIED_DDL_UNSUPPORTED_CHECK",
              f"CHECK comparison operator {type(node).__name__} is outside certified-ddl-v1")
    assert operator is not None  # narrows for mypy; _require already enforced this at runtime
    column = _plain_identifier(node.this, "CHECK left-hand column")
    literal = node.expression
    _require(isinstance(literal, exp.Literal), "CERTIFIED_DDL_UNSUPPORTED_CHECK",
              "CHECK right-hand side must be a plain literal")
    return CheckComparison(column=column, operator=operator, literal=str(literal.this),
                            literal_is_string=bool(literal.is_string))''',
)

patch(
    f"{SQ}/emitter.py",
    '''def _render_check_comparison(comparison: CheckComparison) -> str:
    literal = (
        f"'{comparison.literal.replace(chr(39), chr(39) * 2)}'"
        if comparison.literal_is_string
        else comparison.literal
    )
    return f"{comparison.column} {check_operator_sql(comparison.operator)} {literal}"''',
    '''def _render_literal(value: str, is_string: bool) -> str:
    return f"'{value.replace(chr(39), chr(39) * 2)}'" if is_string else value


def _render_check_comparison(comparison: CheckComparison) -> str:
    operator = comparison.operator
    if operator in NULLARY_CHECK_OPERATORS:
        return f"{comparison.column} {operator.value}"
    if operator is CheckOperator.IN:
        members = ", ".join(
            _render_literal(item.value, item.is_string) for item in comparison.literals
        )
        return f"{comparison.column} IN ({members})"
    if operator is CheckOperator.BETWEEN:
        low, high = comparison.literals
        return (
            f"{comparison.column} BETWEEN {_render_literal(low.value, low.is_string)}"
            f" AND {_render_literal(high.value, high.is_string)}"
        )
    literal = _render_literal(comparison.literal, comparison.literal_is_string)
    return f"{comparison.column} {check_operator_sql(comparison.operator)} {literal}"''',
)

print("FIX 4 applied")

# imports for the widened CHECK model
patch(
    f"{SQ}/emitter.py",
    '''    CheckComparison,
    CheckConstraint,
    Column,
    Dialect,
    DialectError,''',
    '''    NULLARY_CHECK_OPERATORS,
    CheckComparison,
    CheckConstraint,
    CheckOperator,
    Column,
    Dialect,
    DialectError,''',
)

patch(
    f"{SQ}/parser.py",
    '''    CheckComparison,''',
    '''    CheckComparison,
    CheckLiteral,''',
)

print("FIX 4 imports applied")

# `IS NOT NULL` has two different sqlglot shapes depending on the READ dialect:
#   postgres -> Is(negate=True)
#   mysql / oracle / tsql -> Not(this=Is(...))
# Only handling the first meant the single most common CHECK in real schemas
# (376 of 458 blocked constraints) was admitted from a PostgreSQL source and
# refused from the other three. Found by running all four, not by reading.
patch(
    f"{SQ}/parser.py",
    '''def _parse_check_comparison(node: exp.Expression) -> CheckComparison:
    # --- null tests -------------------------------------------------------''',
    '''def _parse_check_comparison(node: exp.Expression) -> CheckComparison:
    # --- `NOT (x IS NULL)`, which is how mysql/oracle/tsql spell IS NOT NULL --
    # Only the null test is unwrapped here. `NOT IN` and every other negation
    # stay outside the profile rather than being admitted as a side effect.
    if isinstance(node, exp.Not) and isinstance(node.this, exp.Is):
        inner = node.this
        _require(isinstance(inner.expression, exp.Null), "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                  "certified-ddl-v1 supports IS [NOT] NULL only; IS TRUE/FALSE has no Oracle equivalent")
        _require(not inner.args.get("negate"), "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                  "doubly negated null test is outside certified-ddl-v1")
        return CheckComparison(
            column=_plain_identifier(inner.this, "CHECK left-hand column"),
            operator=CheckOperator.IS_NOT_NULL,
        )

    # --- null tests -------------------------------------------------------''',
)

print("FIX 4 dialect-shape handling applied")

# `CHECK ((a > 0))` -- a redundant parenthesis wrapper. 19 occurrences in the
# measured corpus, and unlike regex or LIKE it carries no semantics at all:
# every dialect parses and renders it the same way with or without the parens.
# Unwrapped with a bounded depth so a pathological input cannot recurse away.
patch(
    f"{SQ}/parser.py",
    '''def _parse_check(node: exp.Expression) -> tuple[tuple[CheckComparison, ...], CheckConnector | None]:
    if isinstance(node, exp.And | exp.Or):''',
    '''_MAX_CHECK_PAREN_DEPTH = 8


def _unwrap_check_parens(node: exp.Expression) -> exp.Expression:
    """Strip redundant parentheses around a CHECK body.

    Purely syntactic: `CHECK ((a > 0))` and `CHECK (a > 0)` are the same
    constraint to all four dialects, and both re-render identically. Bounded
    so deeply nested input fails closed rather than recursing.
    """

    depth = 0
    while isinstance(node, exp.Paren):
        depth += 1
        if depth > _MAX_CHECK_PAREN_DEPTH:
            raise DialectError(
                "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                f"CHECK nests more than {_MAX_CHECK_PAREN_DEPTH} redundant parentheses",
            )
        node = node.this
    return node


def _parse_check(node: exp.Expression) -> tuple[tuple[CheckComparison, ...], CheckConnector | None]:
    node = _unwrap_check_parens(node)
    if isinstance(node, exp.And | exp.Or):''',
)

patch(
    f"{SQ}/parser.py",
    '''        connector = CheckConnector.AND if isinstance(node, exp.And) else CheckConnector.OR
        return (_parse_check_comparison(left), _parse_check_comparison(right)), connector''',
    '''        connector = CheckConnector.AND if isinstance(node, exp.And) else CheckConnector.OR
        left = _unwrap_check_parens(left)
        right = _unwrap_check_parens(right)
        return (_parse_check_comparison(left), _parse_check_comparison(right)), connector''',
)

print("FIX 4 redundant-paren unwrapping applied")
