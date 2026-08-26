"""Canonical DDL model for the certified SQL migration profiles.

This mirrors the type-name subset of `CanonicalDatabaseIr.CanonicalType` in
`engines/database-data-engine` (Java) deliberately -- this engine is a
narrower, real, certified DDL translator that could feed that engine's
`SqlNode`/`SchemaObjectNode` IR in the future, not a competing type system.

Every dataclass here is intentionally small and closed: the profiles are fixed,
precisely bounded subsets of CREATE TABLE, CREATE INDEX, ALTER TABLE, DROP
TABLE, CREATE SCHEMA, and side-effect-free SQL FUNCTION syntax (see
`README.md`). Anything the parser
encounters outside these subsets must raise `DialectError`, never be silently
approximated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RouteError(Exception):
    """Raised for a caller mistake (e.g. same source and target dialect)."""


class DialectError(Exception):
    """Raised whenever input is outside the certified-ddl-v1 subset, or a
    parsed statement cannot be re-validated in the target dialect. This is the
    fail-closed signal: callers must treat this as BLOCKED, never as a
    degraded success.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class Dialect(str, Enum):
    POSTGRES = "postgres"
    MYSQL = "mysql"
    ORACLE = "oracle"
    TSQL = "tsql"  # SQL Server


# Real, self-hosting database engines this sandbox can execute a real
# CREATE TABLE against for execution-level validation, given real
# `psycopg2`/`PyMySQL` drivers and a reachable DSN. Oracle and SQL Server have
# no freely licensed, root-less local server available, so execution
# validation for those two dialects is always EXECUTION_NOT_AVAILABLE unless
# the caller supplies their own reachable instance via `--dsn`.
EXECUTABLE_DIALECTS = frozenset({Dialect.POSTGRES, Dialect.MYSQL})


class CanonicalType(str, Enum):
    """A certified-ddl-v1 subset of `CanonicalDatabaseIr.CanonicalType`."""

    BOOLEAN = "BOOLEAN"
    INT16 = "INT16"
    INT32 = "INT32"
    INT64 = "INT64"
    FLOAT64 = "FLOAT64"
    DECIMAL = "DECIMAL"
    CHAR = "CHAR"
    VARCHAR = "VARCHAR"
    TEXT = "TEXT"
    DATE = "DATE"
    TIMESTAMP = "TIMESTAMP"
    JSON = "JSON"
    ARRAY = "ARRAY"
    BINARY = "BINARY"


@dataclass(frozen=True)
class CanonicalTypeRef:
    canonical_type: CanonicalType
    precision: int | None = None
    scale: int | None = None
    length: int | None = None
    element_type: CanonicalTypeRef | None = None
    #: True only for PostgreSQL JSONB. JSON text and JSONB have different
    #: indexing, ordering and operator semantics; retaining this bit prevents
    #: an apparently harmless JSONB -> JSON downgrade.
    json_binary: bool = False
    binary_fixed: bool = False


class DefaultKind(str, Enum):
    NUMBER = "NUMBER"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    CURRENT_TIMESTAMP = "CURRENT_TIMESTAMP"


@dataclass(frozen=True)
class ColumnDefault:
    kind: DefaultKind
    literal: str | None = None  # unset for CURRENT_TIMESTAMP
    #: The explicit source cast for typed literal defaults such as
    #: PostgreSQL `'{}'::jsonb`.  Keeping the cast in the IR prevents a
    #: renderer from silently turning a JSONB default into an untyped string.
    #: It is intentionally optional and currently only admits the JSONB
    #: literal profile in ``parser._parse_default``.
    cast_type: CanonicalTypeRef | None = None


@dataclass(frozen=True)
class Column:
    name: str
    type_ref: CanonicalTypeRef
    nullable: bool = True
    default: ColumnDefault | None = None
    auto_increment: bool = False


class ReferentialAction(str, Enum):
    CASCADE = "CASCADE"
    SET_NULL = "SET_NULL"
    RESTRICT = "RESTRICT"
    NO_ACTION = "NO_ACTION"


@dataclass(frozen=True)
class ForeignKey:
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]
    on_delete: ReferentialAction = ReferentialAction.NO_ACTION
    on_update: ReferentialAction = ReferentialAction.NO_ACTION
    name: str | None = None
    ref_schema: str | None = None


class CheckOperator(str, Enum):
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
    IS_TRUE = "IS TRUE"
    IN = "IN"
    BETWEEN = "BETWEEN"
    LIKE = "LIKE"
    MATCHES_REGEX = "MATCHES_REGEX"


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
NULLARY_CHECK_OPERATORS: frozenset[CheckOperator] = frozenset({CheckOperator.IS_NULL, CheckOperator.IS_NOT_NULL})


def require_portable_regex(pattern: str) -> None:
    """Reject regex syntax whose meaning is not stable on all certified targets.

    The four dialects do not share one regex implementation.  The certified
    profile therefore accepts the small common POSIX/ARE core used by the
    measured migration corpus and refuses engine-specific escapes, Unicode
    properties, backreferences, and inline flags instead of guessing.
    """
    forbidden = (
        r"\\d",
        r"\\w",
        r"\\s",
        r"\\p{",
        r"\\P{",
        r"\\b",
        r"\\B",
        r"\\1",
        "(?",
        "[[:",
    )
    if any(token in pattern for token in forbidden):
        raise DialectError(
            "CERTIFIED_DDL_UNSUPPORTED_CHECK_PATTERN",
            f"regex pattern {pattern!r} uses syntax outside the portable cross-dialect core",
        )
    if "\\" in pattern:
        raise DialectError(
            "CERTIFIED_DDL_UNSUPPORTED_CHECK_PATTERN",
            f"regex pattern {pattern!r} contains an unclassified escape",
        )


def require_portable_like(pattern: str) -> None:
    """Allow only LIKE patterns whose result is independent of collation.

    The target engines disagree on case sensitivity and escaping defaults. A
    pattern made only of ASCII non-letters, `%`, and `_` has no case-bearing
    text and preserves the path/host-shape checks in this corpus without
    pretending arbitrary LIKE is portable.
    """
    if "\\" in pattern or "[" in pattern or "]" in pattern or any(not c.isascii() or c.isalpha() for c in pattern):
        raise DialectError(
            "CERTIFIED_DDL_UNSUPPORTED_CHECK_PATTERN",
            f"LIKE pattern {pattern!r} depends on collation, escaping, or vendor pattern syntax",
        )


@dataclass(frozen=True)
class CheckLiteral:
    """One literal operand, carrying whether it needs quoting on emission."""

    value: str
    is_string: bool = False
    is_boolean: bool = False


class CheckIntervalUnit(str, Enum):
    SECOND = "SECOND"
    MINUTE = "MINUTE"
    HOUR = "HOUR"
    DAY = "DAY"


@dataclass(frozen=True)
class CheckComparison:
    """One typed portable CHECK leaf.

    The leaf may compare a column with a literal, another same-typed column,
    or a bounded timestamp interval. Function calls and subqueries remain out
    of the IR because their names and null/type rules diverge by engine.
    """

    column: str
    operator: CheckOperator
    #: Right-hand side for the binary operators. Empty for the null tests and
    #: unused by `IN` / `BETWEEN`, which use `literals` instead.
    literal: str = ""
    literal_is_string: bool = False
    literal_is_boolean: bool = False
    #: A column-to-column comparison. This is mutually exclusive with
    #: `literal`; both are preserved in the canonical IR rather than reducing
    #: the right side to text and risking a literal/identifier confusion.
    right_column: str | None = None
    #: A bounded timestamp interval expression such as
    #: `issued_at + INTERVAL '15 minutes'`. It is typed so emitters can use
    #: DATEADD/DATE_ADD/interval syntax without textual substitution.
    right_interval_column: str | None = None
    right_interval_value: int | None = None
    right_interval_unit: CheckIntervalUnit | None = None
    #: Operands for `IN` (one or more) and `BETWEEN` (exactly two, low then
    #: high). Empty for every other operator.
    literals: tuple[CheckLiteral, ...] = ()

    def __post_init__(self) -> None:
        if self.operator is CheckOperator.MATCHES_REGEX:
            if not self.literal_is_string:
                raise DialectError(
                    "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                    "regex CHECK patterns must be string literals",
                )
            require_portable_regex(self.literal)
            return
        if self.operator is CheckOperator.LIKE:
            if not self.literal_is_string or self.right_column is not None or self.right_interval_column is not None:
                raise DialectError(
                    "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                    "LIKE CHECK patterns must be string literals",
                )
            require_portable_like(self.literal)
            return
        if self.operator is CheckOperator.IS_TRUE:
            if self.literal or self.literals or self.right_column is not None or self.right_interval_column is not None:
                raise DialectError(
                    "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                    "IS TRUE column assertions take no operand",
                )
            return
        if self.operator in NULLARY_CHECK_OPERATORS:
            if self.literal or self.literals or self.right_column is not None or self.right_interval_column is not None:
                raise DialectError(
                    "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                    f"{self.operator.value} takes no operand",
                )
        elif self.operator is CheckOperator.IN:
            if (
                self.literal
                or self.right_column is not None
                or self.right_interval_column is not None
                or not self.literals
            ):
                raise DialectError("CERTIFIED_DDL_UNSUPPORTED_CHECK", "IN requires at least one literal")
        elif self.operator is CheckOperator.BETWEEN:
            if (
                self.literal
                or self.right_column is not None
                or self.right_interval_column is not None
                or len(self.literals) != 2
            ):
                raise DialectError(
                    "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                    "BETWEEN requires exactly two literals (low, high)",
                )
        elif self.right_interval_column is not None:
            if (
                self.right_column is not None
                or self.literal
                or self.literal_is_string
                or self.literal_is_boolean
                or self.literals
                or self.right_interval_value is None
                or self.right_interval_unit is None
                or self.right_interval_value < 0
            ):
                raise DialectError(
                    "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                    "timestamp interval comparisons require a non-negative integer interval",
                )
        elif self.right_column is not None:
            if (
                self.literal
                or self.literal_is_string
                or self.literal_is_boolean
                or self.literals
                or self.right_interval_value is not None
                or self.right_interval_unit is not None
            ):
                raise DialectError(
                    "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                    "a column-to-column CHECK comparison cannot also carry a literal",
                )
        elif not self.literal and not self.literal_is_string and not self.literal_is_boolean:
            raise DialectError(
                "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                f"{self.operator.value} requires a right-hand literal",
            )


class CheckConnector(str, Enum):
    AND = "AND"
    OR = "OR"


@dataclass(frozen=True)
class CheckBooleanExpression:
    """A bounded boolean tree whose leaves are portable comparisons.

    AND/OR precedence and three-valued NULL semantics are shared by all four
    target dialects. Keeping the tree, including its connector at every
    level, is therefore safer than flattening mixed levels or refusing a
    comparison-only expression that can be emitted without semantic change.
    """

    connector: CheckConnector
    operands: tuple[CheckExpression, ...]

    def __post_init__(self) -> None:
        if len(self.operands) < 2:
            raise DialectError(
                "CERTIFIED_DDL_MULTI_LEVEL_CHECK",
                "a boolean CHECK expression requires at least two operands",
            )


@dataclass(frozen=True)
class CheckNotExpression:
    """A portable boolean negation preserving the source expression tree.

    `NOT` has the same three-valued SQL semantics on all four certified
    targets. Keeping it as a typed node means `NOT IN`, `NOT BETWEEN`, and
    nested state predicates are emitted without a regex rewrite or a lossy
    De Morgan transformation.
    """

    operand: CheckExpression


CheckExpression = CheckComparison | CheckBooleanExpression | CheckNotExpression


def _check_comparisons(expression: CheckExpression) -> tuple[CheckComparison, ...]:
    if isinstance(expression, CheckComparison):
        return (expression,)
    comparisons: list[CheckComparison] = []
    if isinstance(expression, CheckNotExpression):
        return _check_comparisons(expression.operand)
    for operand in expression.operands:
        comparisons.extend(_check_comparisons(operand))
    return tuple(comparisons)


@dataclass(frozen=True)
class CheckConstraint:
    #: Legacy flat fields are retained for stable canonical JSON and callers.
    #: Mixed AND/OR trees use `expression` instead, never a lossy flattening.
    comparisons: tuple[CheckComparison, ...] = ()
    connector: CheckConnector | None = None  # None when len(comparisons) == 1
    expression: CheckExpression | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        if self.expression is not None:
            if self.comparisons or self.connector is not None:
                raise DialectError(
                    "CERTIFIED_DDL_MULTI_LEVEL_CHECK",
                    "a CHECK constraint cannot mix a boolean tree with flat fields",
                )
            return
        if not self.comparisons:
            raise DialectError("CERTIFIED_DDL_EMPTY_CHECK", "CHECK constraint has no comparisons")
        if len(self.comparisons) > 1 and self.connector is None:
            raise DialectError(
                "CERTIFIED_DDL_MISSING_CONNECTOR",
                "multi-comparison CHECK constraint requires an AND/OR connector",
            )


@dataclass(frozen=True)
class Table:
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
    schema: str | None = None

    def __post_init__(self) -> None:
        if not self.columns:
            raise DialectError("CERTIFIED_DDL_EMPTY_TABLE", f"table {self.name!r} has no columns")
        names = {c.name for c in self.columns}
        column_types = {c.name: c.type_ref.canonical_type for c in self.columns}
        if len(names) != len(self.columns):
            raise DialectError("CERTIFIED_DDL_DUPLICATE_COLUMN", f"table {self.name!r} has duplicate column names")
        for pk_col in self.primary_key:
            if pk_col not in names:
                raise DialectError("CERTIFIED_DDL_UNKNOWN_COLUMN", f"PRIMARY KEY references unknown column {pk_col!r}")
        for unique in self.unique_constraints:
            for unique_col in unique:
                if unique_col not in names:
                    raise DialectError(
                        "CERTIFIED_DDL_UNKNOWN_COLUMN", f"UNIQUE references unknown column {unique_col!r}"
                    )
        for fk in self.foreign_keys:
            for fk_col in fk.columns:
                if fk_col not in names:
                    raise DialectError(
                        "CERTIFIED_DDL_UNKNOWN_COLUMN", f"FOREIGN KEY references unknown column {fk_col!r}"
                    )
        for check in self.check_constraints:
            comparisons = _check_comparisons(check.expression) if check.expression is not None else check.comparisons
            for comparison in comparisons:
                if comparison.column not in names:
                    raise DialectError(
                        "CERTIFIED_DDL_UNKNOWN_COLUMN", f"CHECK references unknown column {comparison.column!r}"
                    )
                if comparison.right_column is not None and comparison.right_column not in names:
                    raise DialectError(
                        "CERTIFIED_DDL_UNKNOWN_COLUMN",
                        f"CHECK references unknown column {comparison.right_column!r}",
                    )
                if (
                    comparison.right_column is not None
                    and column_types[comparison.column] is not column_types[comparison.right_column]
                ):
                    raise DialectError(
                        "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                        "column-to-column CHECK comparisons require the same canonical type",
                    )
                if comparison.right_interval_column is not None:
                    if comparison.right_interval_column not in names:
                        raise DialectError(
                            "CERTIFIED_DDL_UNKNOWN_COLUMN",
                            f"CHECK references unknown column {comparison.right_interval_column!r}",
                        )
                    if (
                        column_types[comparison.column] is not CanonicalType.TIMESTAMP
                        or column_types[comparison.right_interval_column] is not CanonicalType.TIMESTAMP
                    ):
                        raise DialectError(
                            "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                            "timestamp interval CHECK comparisons require TIMESTAMP columns",
                        )
                if (
                    comparison.operator is CheckOperator.IS_TRUE
                    or comparison.literal_is_boolean
                    or any(item.is_boolean for item in comparison.literals)
                ) and column_types[comparison.column] is not CanonicalType.BOOLEAN:
                    raise DialectError(
                        "CERTIFIED_DDL_UNSUPPORTED_CHECK",
                        f"boolean CHECK predicate references non-BOOLEAN column {comparison.column!r}",
                    )


@dataclass(frozen=True)
class IndexColumn:
    """One plain index key with its optional descending order preserved."""

    name: str
    descending: bool = False


@dataclass(frozen=True)
class Index:
    name: str
    table: str
    columns: tuple[IndexColumn, ...]
    unique: bool = False
    #: `CREATE INDEX IF NOT EXISTS`. Narrower than the table form -- MySQL has
    #: no such spelling for indexes even though it has one for tables.
    if_not_exists: bool = False
    table_schema: str | None = None
    include: tuple[str, ...] = ()
    predicate: CheckExpression | None = None
    using: str | None = None

    def __post_init__(self) -> None:
        if not self.columns:
            raise DialectError("CERTIFIED_DDL_EMPTY_INDEX", f"index {self.name!r} has no columns")


# ---------------------------------------------------------------------------
# certified-alter-v1
#
# Scope chosen by measurement, not intuition: a scan of 64 real migration
# files found 635 ALTER TABLE actions, of which 603 were ADD COLUMN, 29 ADD
# CONSTRAINT, 2 RENAME COLUMN and 1 DROP CONSTRAINT. Those five operations
# are the profile; everything else fails closed.
#
# Deliberately OUT, and this is the interesting boundary:
#
#   ALTER COLUMN TYPE / SET NOT NULL / SET DEFAULT / DROP DEFAULT.
#
# MySQL spells a column change `MODIFY c <TYPE> NOT NULL` and SQL Server
# `ALTER COLUMN c <TYPE> NOT NULL` -- BOTH require the column's full type to
# be restated. An `ALTER TABLE t ALTER COLUMN c SET NOT NULL` statement does
# not carry that type, and this engine reads one statement at a time with no
# catalog to look it up in. Emitting those targets would mean inventing a
# type, which is precisely the class of silent corruption the profile exists
# to prevent. They appeared 0 times in the corpus, so refusing them costs
# nothing measurable.
# ---------------------------------------------------------------------------


class AlterActionKind(str, Enum):
    ADD_COLUMN = "ADD_COLUMN"
    DROP_COLUMN = "DROP_COLUMN"
    RENAME_COLUMN = "RENAME_COLUMN"
    ADD_CONSTRAINT = "ADD_CONSTRAINT"
    DROP_CONSTRAINT = "DROP_CONSTRAINT"


@dataclass(frozen=True)
class AddColumn:
    column: Column
    #: An inline `REFERENCES` on the added column, lifted to the same
    #: canonical shape a table-level FOREIGN KEY produces.
    foreign_key: ForeignKey | None = None
    check: CheckConstraint | None = None
    kind: AlterActionKind = AlterActionKind.ADD_COLUMN


@dataclass(frozen=True)
class DropColumn:
    column: str
    kind: AlterActionKind = AlterActionKind.DROP_COLUMN


@dataclass(frozen=True)
class RenameColumn:
    column: str
    new_name: str
    kind: AlterActionKind = AlterActionKind.RENAME_COLUMN


@dataclass(frozen=True)
class AddConstraint:
    """Exactly one of the four constraint shapes is populated."""

    name: str | None = None
    primary_key: tuple[str, ...] = ()
    unique: tuple[str, ...] = ()
    foreign_key: ForeignKey | None = None
    check: CheckConstraint | None = None
    kind: AlterActionKind = AlterActionKind.ADD_CONSTRAINT

    def __post_init__(self) -> None:
        populated = sum(1 for v in (self.primary_key, self.unique, self.foreign_key, self.check) if v)
        if populated != 1:
            raise DialectError(
                "CERTIFIED_ALTER_UNSUPPORTED_CONSTRAINT",
                "ADD CONSTRAINT must carry exactly one of PRIMARY KEY / UNIQUE / FOREIGN KEY / CHECK",
            )


@dataclass(frozen=True)
class DropConstraint:
    name: str
    kind: AlterActionKind = AlterActionKind.DROP_CONSTRAINT


AlterAction = AddColumn | DropColumn | RenameColumn | AddConstraint | DropConstraint


@dataclass(frozen=True)
class DropTable:
    """The measured portable DROP TABLE subset.

    CASCADE/RESTRICT and temporary tables are intentionally not represented:
    their dependency and lifecycle semantics differ across the four targets.
    """

    name: str
    if_exists: bool = False
    schema: str | None = None


@dataclass(frozen=True)
class Schema:
    """A logical namespace created by the portable schema profile.

    PostgreSQL, MySQL and SQL Server can all create a named namespace with
    this minimal shape. Oracle schemas are users, so the emitter refuses that
    target rather than inventing an account/authorization side effect.
    """

    name: str
    if_not_exists: bool = False


# ---------------------------------------------------------------------------
# certified-insert-v1
#
# This is deliberately a literal-seed profile, not a general DML translator.
# A row made only of typed SQL literals has no source query plan, conflict
# policy, trigger interaction, or target-side expression to reinterpret.  The
# model therefore carries the literal kind explicitly. INSERT ... SELECT,
# DEFAULT VALUES, generated expressions, conflict/upsert clauses and hints
# remain outside the route until they have their own semantic IR.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InsertLiteral:
    """One literal value in a portable seed row."""

    value: str | None = None
    is_string: bool = False
    is_boolean: bool = False
    is_null: bool = False

    def __post_init__(self) -> None:
        kinds = sum((self.is_string, self.is_boolean, self.is_null))
        if kinds > 1:
            raise DialectError(
                "CERTIFIED_INSERT_INVALID_LITERAL",
                "an INSERT literal cannot be string, boolean and NULL at the same time",
            )
        if self.is_null:
            if self.value is not None:
                raise DialectError("CERTIFIED_INSERT_INVALID_LITERAL", "NULL carries no literal payload")
        elif self.value is None:
            raise DialectError("CERTIFIED_INSERT_INVALID_LITERAL", "non-NULL INSERT literals need a payload")


@dataclass(frozen=True)
class InsertStatement:
    """A fixed-column, literal-only INSERT statement."""

    table: str
    columns: tuple[str, ...]
    rows: tuple[tuple[InsertLiteral, ...], ...]
    schema: str | None = None

    def __post_init__(self) -> None:
        if not self.columns:
            raise DialectError(
                "CERTIFIED_INSERT_COLUMN_LIST_REQUIRED",
                "literal INSERT requires an explicit target column list",
            )
        if not self.rows:
            raise DialectError("CERTIFIED_INSERT_EMPTY_VALUES", "literal INSERT requires at least one VALUES row")
        if len(set(self.columns)) != len(self.columns):
            raise DialectError("CERTIFIED_INSERT_DUPLICATE_COLUMN", "INSERT target columns must be unique")
        for row in self.rows:
            if len(row) != len(self.columns):
                raise DialectError(
                    "CERTIFIED_INSERT_ARITY_MISMATCH",
                    "every INSERT VALUES row must match the target column list",
                )


# ---------------------------------------------------------------------------
# certified-routine-v1
#
# This is deliberately a small typed IR, not a text/template representation
# of a stored program. The initial cross-dialect subset is a scalar SQL
# function whose body is exactly one SELECT expression made from literals,
# declared parameters, arithmetic, concatenation, and CHR/CHAR code points.
# A routine may carry security/search-path/volatility facts in the model even
# though the portable emitter rejects them unless an exact target mapping is
# added. That distinction prevents metadata from disappearing during a
# translation and turning a blocked security boundary into a false success.
# Procedures, trigger functions, query DML, table reads, control flow,
# exceptions, dynamic SQL, and dialect-specific routine languages stay outside
# this IR. Literal seed INSERTs have their own certified-insert-v1 model above.
# ---------------------------------------------------------------------------


class RoutineKind(str, Enum):
    FUNCTION = "FUNCTION"
    PROCEDURE = "PROCEDURE"


class RoutineLanguage(str, Enum):
    SQL = "SQL"
    PLPGSQL = "PLPGSQL"
    OTHER = "OTHER"


class RoutineStability(str, Enum):
    IMMUTABLE = "IMMUTABLE"
    STABLE = "STABLE"
    VOLATILE = "VOLATILE"


class RoutineBinaryOperator(str, Enum):
    CONCAT = "||"
    ADD = "+"
    SUBTRACT = "-"
    MULTIPLY = "*"
    DIVIDE = "/"
    MODULO = "%"


class RoutineFunction(str, Enum):
    CONCAT = "CONCAT"
    COALESCE = "COALESCE"
    LOWER = "LOWER"
    UPPER = "UPPER"
    TRIM = "TRIM"
    ABS = "ABS"


@dataclass(frozen=True)
class RoutineLiteral:
    value: str
    is_string: bool = False
    is_boolean: bool = False


@dataclass(frozen=True)
class RoutineParameterReference:
    name: str


@dataclass(frozen=True)
class RoutineCharCode:
    value: int


@dataclass(frozen=True)
class RoutineBinaryExpression:
    operator: RoutineBinaryOperator
    left: RoutineValueExpression
    right: RoutineValueExpression


@dataclass(frozen=True)
class RoutineFunctionCall:
    name: RoutineFunction
    arguments: tuple[RoutineValueExpression, ...]


RoutineValueExpression = (
    RoutineLiteral | RoutineParameterReference | RoutineCharCode | RoutineBinaryExpression | RoutineFunctionCall
)


@dataclass(frozen=True)
class RoutineSelectBody:
    expression: RoutineValueExpression


@dataclass(frozen=True)
class RoutineParameterMode(str, Enum):
    IN = "IN"
    OUT = "OUT"
    INOUT = "INOUT"


@dataclass(frozen=True)
class RoutineParameter:
    name: str
    type_ref: CanonicalTypeRef
    mode: RoutineParameterMode = RoutineParameterMode.IN


@dataclass(frozen=True)
class Routine:
    """A routine with security and lifecycle metadata retained explicitly."""

    kind: RoutineKind
    name: str
    parameters: tuple[RoutineParameter, ...]
    return_type: CanonicalTypeRef | None
    body: RoutineSelectBody | None
    schema: str | None = None
    language: RoutineLanguage = RoutineLanguage.SQL
    stability: RoutineStability | None = None
    strict: bool = False
    security_definer: bool = False
    search_path: tuple[str, ...] = ()
    or_replace: bool = False

    def __post_init__(self) -> None:
        if self.kind is RoutineKind.FUNCTION and self.return_type is None:
            raise DialectError(
                "CERTIFIED_ROUTINE_MISSING_RETURN_TYPE",
                f"function {self.name!r} has no scalar RETURNS type",
            )
        if self.kind is RoutineKind.FUNCTION and self.body is None:
            raise DialectError(
                "CERTIFIED_ROUTINE_UNSUPPORTED_BODY",
                f"function {self.name!r} has no single-expression SQL body",
            )
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise DialectError(
                "CERTIFIED_ROUTINE_DUPLICATE_PARAMETER",
                f"routine {self.name!r} declares a parameter more than once",
            )


@dataclass(frozen=True)
class RoutineAssignment:
    target: str
    value: RoutineValueExpression


@dataclass(frozen=True)
class Procedure:
    """A deliberately bounded procedure IR.

    The first procedural slice only admits assignments to declared OUT/INOUT
    parameters. It has no table effects, transaction commands, dynamic SQL,
    cursors, exception swallowing, or hidden side effects.
    """

    name: str
    parameters: tuple[RoutineParameter, ...]
    assignments: tuple[RoutineAssignment, ...]
    schema: str | None = None
    or_replace: bool = False

    def __post_init__(self) -> None:
        names = {p.name.casefold(): p for p in self.parameters}
        if len(names) != len(self.parameters):
            raise DialectError(
                "CERTIFIED_ROUTINE_DUPLICATE_PARAMETER", f"procedure {self.name!r} has duplicate parameters"
            )
        for assignment in self.assignments:
            parameter = names.get(assignment.target.casefold())
            if parameter is None or parameter.mode is RoutineParameterMode.IN:
                raise DialectError(
                    "CERTIFIED_ROUTINE_ASSIGNMENT_TARGET",
                    f"procedure assignment target {assignment.target!r} must be an OUT or INOUT parameter",
                )


@dataclass(frozen=True)
class ViewQuery:
    columns: tuple[str, ...]
    table: str
    table_schema: str | None = None
    predicate: CheckExpression | None = None


@dataclass(frozen=True)
class TableFunctionColumn:
    name: str
    type_ref: CanonicalTypeRef


@dataclass(frozen=True)
class TableFunction:
    name: str
    parameters: tuple[RoutineParameter, ...]
    return_columns: tuple[TableFunctionColumn, ...]
    query: ViewQuery
    schema: str | None = None
    or_replace: bool = False


@dataclass(frozen=True)
class View:
    name: str
    query: ViewQuery
    schema: str | None = None
    or_replace: bool = False


class CommentObjectKind(str, Enum):
    TABLE = "TABLE"
    COLUMN = "COLUMN"


@dataclass(frozen=True)
class Comment:
    object_kind: CommentObjectKind
    object_name: str
    text: str
    table_name: str | None = None
    schema: str | None = None
    table_schema: str | None = None


class PrivilegeAction(str, Enum):
    GRANT = "GRANT"
    REVOKE = "REVOKE"


@dataclass(frozen=True)
class Privilege:
    action: PrivilegeAction
    privileges: tuple[str, ...]
    object_name: str
    principals: tuple[str, ...]
    object_kind: str = "TABLE"
    schema: str | None = None
    grant_option: bool = False


class TriggerTiming(str, Enum):
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    INSTEAD_OF = "INSTEAD OF"


class TriggerEvent(str, Enum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


@dataclass(frozen=True)
class Trigger:
    name: str
    table: str
    timing: TriggerTiming
    events: tuple[TriggerEvent, ...]
    row_level: bool
    routine_name: str
    schema: str | None = None
    table_schema: str | None = None
    routine_schema: str | None = None


@dataclass(frozen=True)
class RowPolicy:
    """Typed record for RLS facts; no cross-engine emitter is provided."""

    name: str
    table: str
    using_expression: str | None = None
    check_expression: str | None = None
    schema: str | None = None


@dataclass(frozen=True)
class AlterTable:
    table: str
    actions: tuple[AlterAction, ...]
    schema: str | None = None

    def __post_init__(self) -> None:
        if not self.actions:
            raise DialectError("CERTIFIED_ALTER_EMPTY", f"ALTER TABLE {self.table!r} carries no action")
